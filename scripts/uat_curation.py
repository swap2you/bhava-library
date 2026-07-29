"""Read-only local UAT sampling for curation outputs.

This helper opens SQLite in read-only mode, samples at most 50 catalog records,
checks count availability for major content forms, reports audio metadata and
quarantine/terminal states, and scans candidate exports for binary signatures.
It never opens or mutates files under ``data/originals``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

MAJOR_FORMS = (
    "audio-story",
    "worksheet",
    "coloring-page",
    "quiz",
    "kirtan",
    "word-search",
    "crossword",
    "comic",
    "archive-bundle",
)
BINARY_SIGNATURES = (
    b"%PDF",
    b"PK\x03\x04",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"ID3",
)
ALLOWED_CANDIDATE_SUFFIXES = {".json", ".md"}
VIEW_DIMENSIONS = (
    "content-form",
    "audience",
    "program-use",
    "topic",
    "festival",
    "language",
    "production-opportunity",
)


def _rows(connection: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()) -> list[dict]:
    return [dict(row) for row in connection.execute(sql, params)]


def _scan_candidate_exports(root: Path) -> list[str]:
    violations: list[str] = []
    if not root.exists():
        return violations
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() not in ALLOWED_CANDIDATE_SUFFIXES:
            violations.append(f"disallowed candidate export extension: {relative}")
            continue
        with path.open("rb") as stream:
            prefix = stream.read(4096)
        if any(signature in prefix for signature in BINARY_SIGNATURES):
            violations.append(f"binary signature in candidate export: {relative}")
    return violations


def _classification_records(
    connection: sqlite3.Connection,
    terms: tuple[str, ...],
    *,
    limit: int | None = None,
) -> list[dict]:
    markers = ",".join("?" for _ in terms)
    sql = f"""
        SELECT rc.resource_id, r.title_original, rc.term, rc.confidence,
               rc.review_state, ce.classifier AS evidence_source, ce.excerpt
        FROM resource_classifications rc
        JOIN resources r ON r.resource_id = rc.resource_id
        LEFT JOIN classification_evidence ce
          ON ce.resource_id = rc.resource_id
         AND ce.dimension = rc.dimension
         AND ce.term = rc.term
         AND ce.rule_version = rc.rule_version
        WHERE rc.dimension = 'content-form' AND rc.term IN ({markers})
        ORDER BY rc.term, rc.resource_id
    """  # nosec B608 — bind markers are generated only from the fixed tuple length
    params: tuple[object, ...] = terms
    if limit is not None:
        sql += " LIMIT ?"
        params = (*params, limit)
    return _rows(connection, sql, params)


def _validate_views(
    connection: sqlite3.Connection,
    views_root: Path,
) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    reconciled: dict[str, int] = {}
    expected_all = int(
        connection.execute("SELECT COUNT(*) FROM resources WHERE removed_at IS NULL").fetchone()[0]
    )
    all_json = views_root / "by-all" / "catalog.json"
    if not all_json.is_file():
        errors.append("missing by-all/catalog.json")
    else:
        all_payload = json.loads(all_json.read_text(encoding="utf-8"))
        reconciled["by-all"] = len(all_payload)
        if len(all_payload) != expected_all:
            errors.append(f"by-all expected {expected_all}, found {len(all_payload)}")

    expected = {
        (str(row["dimension"]), str(row["term"])): int(row["count"])
        for row in connection.execute(
            """
            SELECT dimension, term, COUNT(DISTINCT resource_id) AS count
            FROM resource_classifications
            WHERE dimension IN (?, ?, ?, ?, ?, ?, ?)
            GROUP BY dimension, term
            """,
            VIEW_DIMENSIONS,
        )
    }
    found: dict[tuple[str, str], int] = {}
    for dimension in VIEW_DIMENSIONS:
        dimension_root = views_root / f"by-{dimension}"
        if not dimension_root.exists():
            if any(key[0] == dimension for key in expected):
                errors.append(f"missing dimension directory: by-{dimension}")
            continue
        for index_json in sorted(dimension_root.glob("*/index.json")):
            payload = json.loads(index_json.read_text(encoding="utf-8"))
            if not payload:
                errors.append(f"empty generated term view: {index_json}")
                continue
            term = str(payload[0].get("term"))
            key = (dimension, term)
            count = len(payload)
            found[key] = count
            reconciled[f"{dimension}:{term}"] = count
            expected_count = expected.get(key)
            if expected_count != count:
                errors.append(f"{dimension}:{term} expected {expected_count}, found {count}")
            resource_ids = [str(record.get("resource_id")) for record in payload]
            if len(resource_ids) != len(set(resource_ids)):
                errors.append(f"duplicate resources in {dimension}:{term}")
            csv_path = index_json.with_suffix(".csv")
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                csv_count = sum(1 for _ in csv.DictReader(handle))
            if csv_count != count:
                errors.append(f"CSV mismatch for {dimension}:{term}: {csv_count} vs {count}")
            markdown = index_json.with_suffix(".md").read_text(encoding="utf-8")
            rendered_html = index_json.with_suffix(".html").read_text(encoding="utf-8")
            if f"Records: {count}" not in markdown:
                errors.append(f"Markdown mismatch for {dimension}:{term}")
            if f"<p>{count} records " not in rendered_html:
                errors.append(f"HTML mismatch for {dimension}:{term}")

    missing = sorted(set(expected) - set(found))
    unexpected = sorted(set(found) - set(expected))
    errors.extend(f"missing generated term view: {dimension}:{term}" for dimension, term in missing)
    errors.extend(
        f"unexpected generated term view: {dimension}:{term}" for dimension, term in unexpected
    )
    return reconciled, errors


def run_uat(repo_root: Path, *, sample_size: int = 50) -> dict[str, Any]:
    if not 1 <= sample_size <= 50:
        raise ValueError("sample_size must be between 1 and 50")
    database = repo_root / "data" / "catalog" / "bhava-library.sqlite3"
    if not database.is_file():
        raise FileNotFoundError(f"Catalog database not found: {database}")
    uri = f"{database.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        sample = _rows(
            connection,
            """
            SELECT r.resource_id, r.title_original, r.media_type, r.media_format,
                   r.status, lf.relative_path, lf.size_bytes, lf.sha256,
                   lf.quarantine_reason, lf.duplicate_of_file_id
            FROM resources r
            LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
            WHERE r.removed_at IS NULL
            ORDER BY r.resource_id
            LIMIT ?
            """,
            (sample_size,),
        )
        form_rows = _rows(
            connection,
            """
            SELECT term, COUNT(DISTINCT resource_id) AS resource_count
            FROM resource_classifications
            WHERE dimension = 'content-form'
            GROUP BY term ORDER BY term
            """,
        )
        form_counts = {str(row["term"]): int(row["resource_count"]) for row in form_rows}
        audio_sample = _rows(
            connection,
            """
            SELECT r.resource_id, r.title_original, r.media_type, r.media_format,
                   tm.payload_json AS technical_metadata
            FROM resources r
            LEFT JOIN technical_metadata tm ON tm.resource_id = r.resource_id
            WHERE r.media_type LIKE 'audio%' OR r.media_format LIKE 'audio%'
               OR EXISTS (
                 SELECT 1 FROM resource_classifications rc
                 WHERE rc.resource_id = r.resource_id
                   AND rc.dimension = 'content-form' AND rc.term = 'audio-story'
               )
            ORDER BY r.resource_id LIMIT 10
            """,
        )
        quarantine = _rows(
            connection,
            """
            SELECT COALESCE(quarantine_reason, '(quarantine path)') AS representation,
                   COUNT(*) AS file_count
            FROM local_files
            WHERE quarantine_reason IS NOT NULL
               OR relative_path LIKE 'data/quarantine/%'
            GROUP BY representation ORDER BY representation
            """,
        )
        terminal_states = _rows(
            connection,
            """
            SELECT state, COUNT(*) AS job_count
            FROM download_jobs
            WHERE state IN ('complete', 'completed', 'failed', 'quarantined',
                            'blocked', 'skipped', 'cancelled')
            GROUP BY state ORDER BY state
            """,
        )
        focused_samples = {
            "comics_30": _classification_records(connection, ("comic",), limit=30),
            "crosswords_all": _classification_records(connection, ("crossword",)),
            "word_searches_all": _classification_records(connection, ("word-search",)),
            "kirtan_bhajan_all": _classification_records(
                connection,
                ("kirtan", "bhajan"),
            ),
            "coloring_all": _classification_records(
                connection,
                ("coloring-book", "coloring-page"),
            ),
            "unknown_20": _classification_records(connection, ("unknown",), limit=20),
        }
        program_counts = {
            str(row["program"]): int(row["count"])
            for row in connection.execute(
                "SELECT program, COUNT(*) AS count FROM program_mappings GROUP BY program"
            )
        }
        program_samples = {
            program: _rows(
                connection,
                """
                SELECT pm.resource_id, r.title_original, pm.program, pm.collection,
                       pm.confidence, pm.review_state, pm.assumptions_json
                FROM program_mappings pm
                JOIN resources r ON r.resource_id = pm.resource_id
                WHERE pm.program = ?
                ORDER BY pm.resource_id, pm.collection
                LIMIT 10
                """,
                (program,),
            )
            for program in sorted(program_counts)
        }
        mapping_semantic_violations = _rows(
            connection,
            """
            SELECT resource_id, program, confidence, review_state, assumptions_json
            FROM program_mappings
            WHERE (
              json_extract(assumptions_json, '$.match_reason') = 'form-only-unverified-age'
              AND (review_state <> 'needs_review' OR confidence >= 0.55)
            ) OR (
              json_extract(assumptions_json, '$.match_reason') = 'form-and-verified-age'
              AND (review_state <> 'auto_accepted'
                   OR json_extract(assumptions_json, '$.resource_age_min') IS NULL
                   OR json_extract(assumptions_json, '$.resource_age_max') IS NULL)
            )
            ORDER BY resource_id, program
            """,
        )
        preschool_youth_approved = _rows(
            connection,
            """
            SELECT pm.resource_id, r.title_original, pm.review_state, pm.assumptions_json
            FROM program_mappings pm
            JOIN resources r ON r.resource_id = pm.resource_id
            WHERE pm.program = 'youth'
              AND lower(r.title_original) LIKE '%preschool%'
              AND pm.review_state <> 'needs_review'
            ORDER BY pm.resource_id
            """,
        )
        view_counts, view_errors = _validate_views(connection, repo_root / "data" / "views")
    finally:
        connection.close()

    export_violations = _scan_candidate_exports(repo_root / "data" / "exports" / "bhava-candidates")
    focused_sample_errors: list[str] = []
    expected_sample_sizes = {
        "comics_30": min(30, form_counts.get("comic", 0)),
        "crosswords_all": form_counts.get("crossword", 0),
        "word_searches_all": form_counts.get("word-search", 0),
        "kirtan_bhajan_all": form_counts.get("kirtan", 0) + form_counts.get("bhajan", 0),
        "coloring_all": form_counts.get("coloring-book", 0) + form_counts.get("coloring-page", 0),
        "unknown_20": min(20, form_counts.get("unknown", 0)),
    }
    for name, expected_size in expected_sample_sizes.items():
        actual_size = len(focused_samples[name])
        if actual_size != expected_size:
            focused_sample_errors.append(
                f"{name} expected {expected_size} records, found {actual_size}"
            )
    for program, count in program_counts.items():
        expected_size = min(10, count)
        if len(program_samples[program]) != expected_size:
            focused_sample_errors.append(
                f"{program} expected {expected_size} mappings, found "
                f"{len(program_samples[program])}"
            )
    ok = not (
        export_violations
        or focused_sample_errors
        or mapping_semantic_violations
        or preschool_youth_approved
        or view_errors
    )
    return {
        "database_mode": "read-only",
        "sample_requested": sample_size,
        "sample_returned": len(sample),
        "sample": sample,
        "major_form_counts": {form: form_counts.get(form, 0) for form in MAJOR_FORMS},
        "all_content_form_counts": form_counts,
        "audio_metadata_sample": audio_sample,
        "quarantine_representation": quarantine,
        "terminal_state_representation": terminal_states,
        "candidate_export_binary_violations": export_violations,
        "focused_classification_samples": focused_samples,
        "focused_sample_errors": focused_sample_errors,
        "program_mapping_counts": program_counts,
        "program_mapping_samples": program_samples,
        "mapping_semantic_violations": mapping_semantic_violations,
        "preschool_youth_approved": preschool_youth_approved,
        "generated_view_counts": view_counts,
        "generated_view_errors": view_errors,
        "ok": ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="bhava-library repository root",
    )
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_uat(args.repo.resolve(), sample_size=args.sample_size)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output = args.output.resolve()
        originals = (args.repo.resolve() / "data" / "originals").resolve()
        if output.is_relative_to(originals):
            raise ValueError("UAT output must not be written under data/originals")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
