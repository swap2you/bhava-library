"""Read-only local UAT sampling for curation outputs.

This helper opens SQLite in read-only mode, samples at most 50 catalog records,
checks count availability for major content forms, reports audio metadata and
quarantine/terminal states, and scans candidate exports for binary signatures.
It never opens or mutates files under ``data/originals``.
"""

from __future__ import annotations

import argparse
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
            ORDER BY random()
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
    finally:
        connection.close()

    export_violations = _scan_candidate_exports(repo_root / "data" / "exports" / "bhava-candidates")
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
        "ok": not export_violations,
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
