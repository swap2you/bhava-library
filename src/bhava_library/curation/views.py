"""Generate logical catalog views (metadata only, no file copies)."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.curation.audit import audited_curation_command
from bhava_library.infrastructure.catalog_queries import PREFERRED_LOCAL_FILE_JOIN
from bhava_library.infrastructure.database import Database

VIEW_DIMENSIONS = (
    "content-form",
    "audience",
    "program-use",
    "topic",
    "festival",
    "language",
    "production-opportunity",
)
_UNSAFE_VIEW_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_MULTI_SEPARATOR = re.compile(r"[\s._-]+")
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_VIEW_SUFFIXES = {".json", ".csv", ".md", ".html"}
_BINARY_SIGNATURES = (b"%PDF", b"PK\x03\x04", b"\x89PNG", b"\xff\xd8\xff", b"ID3")


def _resource_record(row) -> dict[str, object]:
    return {
        "resource_id": row["resource_id"],
        "display_title": row["display_title"] or row["title_original"],
        "title_original": row["title_original"],
        "relative_path": row["relative_path"],
        "media_type": row["media_type"],
        "status": row["status"],
    }


def _fetch_resources(db: Database) -> list:
    return db.execute(
        f"""
        SELECT r.resource_id, r.title_original, r.media_type, r.status,
               rn.display_title, lf.relative_path
        FROM resources r
        LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
        {PREFERRED_LOCAL_FILE_JOIN}
        WHERE r.removed_at IS NULL
        ORDER BY r.resource_id
        """  # nosec B608 — fixed reusable SQL fragment
    )


def safe_view_slug(value: str) -> str:
    """Return one Unicode-preserving, Windows-safe path component."""
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = _DRIVE_PREFIX.sub("", normalized)
    normalized = _UNSAFE_VIEW_CHARS.sub("-", normalized)
    parts = [part for part in normalized.split(".") if part not in {"", ".", ".."}]
    normalized = "-".join(parts)
    normalized = _MULTI_SEPARATOR.sub("-", normalized).strip(" .-")
    if not normalized:
        normalized = "term"
    if normalized.casefold() in _WINDOWS_RESERVED:
        normalized = f"term-{normalized}"
    return normalized[:120].rstrip(" .-") or "term"


def build_safe_view_slugs(terms: list[str]) -> tuple[dict[str, str], int]:
    """Build stable slugs and suffix every member of a collision group."""
    bases = {term: safe_view_slug(term) for term in sorted(set(terms))}
    grouped: dict[str, list[str]] = {}
    for term, base in bases.items():
        grouped.setdefault(base.casefold(), []).append(term)
    slugs: dict[str, str] = {}
    collisions = 0
    for collision_terms in grouped.values():
        if len(collision_terms) == 1:
            term = collision_terms[0]
            slugs[term] = bases[term]
            continue
        collisions += 1
        for term in collision_terms:
            digest = hashlib.sha256(term.encode("utf-8")).hexdigest()[:8]
            slugs[term] = f"{bases[term]}--{digest}"
    return slugs, collisions


def _safe_term_output(views_root: Path, dimension: str, slug: str) -> Path:
    output = (views_root / f"by-{safe_view_slug(dimension)}" / slug).resolve()
    root = views_root.resolve()
    if not output.is_relative_to(root):
        raise ValueError(f"View output escaped views root: {output}")
    return output


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def _write_md(path: Path, title: str, rows: list[dict[str, object]]) -> None:
    lines = [f"# {title}", "", f"Records: {len(rows)}", ""]
    for row in rows[:500]:
        lines.append(
            f"- **{row.get('display_title', row.get('resource_id'))}** "
            f"(`{row.get('resource_id')}`) — `{row.get('relative_path') or 'no-local-file'}`"
        )
    if len(rows) > 500:
        lines.append(f"\n… and {len(rows) - 500} more (see JSON/CSV).")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_html(path: Path, title: str, rows: list[dict[str, object]]) -> None:
    safe_title = html.escape(title, quote=True)
    body = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{safe_title}</title></head><body>",
        f"<h1>{safe_title}</h1><p>{len(rows)} records (paths as text only).</p><ul>",
    ]
    for row in rows[:500]:
        display_title = html.escape(str(row.get("display_title") or ""), quote=True)
        resource_id = html.escape(str(row.get("resource_id") or ""), quote=True)
        relative_path = html.escape(str(row.get("relative_path") or ""), quote=True)
        body.append(
            f"<li><strong>{display_title}</strong> "
            f"<code>{resource_id}</code> "
            f"<span>{relative_path}</span></li>"
        )
    body.append("</ul></body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")


def _build_view_tree(db: Database, views_root: Path) -> dict[str, int]:
    resources = _fetch_resources(db)
    base_records = [_resource_record(r) for r in resources]
    expected_counts: dict[Path, int] = {}

    all_view = views_root / "by-all"
    fields = [
        "resource_id",
        "display_title",
        "title_original",
        "relative_path",
        "media_type",
        "status",
    ]
    _write_json(all_view / "catalog.json", base_records)
    _write_csv(all_view / "catalog.csv", base_records, fields)
    _write_md(all_view / "catalog.md", "All catalog resources", base_records)
    _write_html(all_view / "catalog.html", "All catalog resources", base_records)
    expected_counts[Path("by-all/catalog.json")] = len(base_records)
    written = 4
    slug_collisions = 0

    for dimension in VIEW_DIMENSIONS:
        rows = db.execute(
            f"""
            SELECT DISTINCT rc.term, r.resource_id, r.title_original, r.media_type, r.status,
                   rn.display_title, lf.relative_path
            FROM resource_classifications rc
            JOIN resources r ON r.resource_id = rc.resource_id
            LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
            {PREFERRED_LOCAL_FILE_JOIN}
            WHERE rc.dimension = ? AND r.removed_at IS NULL
            ORDER BY rc.term, r.resource_id
            """,  # nosec B608 — fixed reusable SQL fragment
            (dimension,),
        )
        by_term: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            rec = _resource_record(row)
            rec["term"] = row["term"]
            by_term.setdefault(row["term"], []).append(rec)

        term_slugs, collisions = build_safe_view_slugs(list(by_term))
        slug_collisions += collisions
        for term, term_rows in by_term.items():
            out = _safe_term_output(views_root, dimension, term_slugs[term])
            _write_json(out / "index.json", term_rows)
            _write_csv(out / "index.csv", term_rows, [*fields, "term"])
            _write_md(out / "index.md", f"{dimension}: {term}", term_rows)
            _write_html(out / "index.html", f"{dimension}: {term}", term_rows)
            expected_counts[(out / "index.json").relative_to(views_root)] = len(term_rows)
            written += 4

    _validate_view_tree(views_root, expected_counts, expected_artifacts=written)
    return {
        "resources": len(resources),
        "artifacts": written,
        "slug_collisions": slug_collisions,
    }


def _validate_view_tree(
    views_root: Path,
    expected_counts: dict[Path, int],
    *,
    expected_artifacts: int,
) -> None:
    root = views_root.resolve()
    files = sorted(path for path in views_root.rglob("*") if path.is_file())
    if len(files) != expected_artifacts:
        raise ValueError(
            f"View artifact count mismatch: expected {expected_artifacts}, found {len(files)}"
        )
    for path in files:
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"Generated view escaped staging root: {path}")
        if path.suffix.lower() not in _VIEW_SUFFIXES:
            raise ValueError(f"Unexpected generated view type: {path}")
        prefix = path.read_bytes()[:16]
        if any(prefix.startswith(signature) for signature in _BINARY_SIGNATURES):
            raise ValueError(f"Binary content found in generated view: {path}")
        path.read_text(encoding="utf-8")

    for relative_json, expected_count in expected_counts.items():
        json_path = views_root / relative_json
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list) or len(payload) != expected_count:
            raise ValueError(f"JSON record count mismatch: {relative_json}")
        resource_ids = [record.get("resource_id") for record in payload if isinstance(record, dict)]
        if len(resource_ids) != len(set(resource_ids)):
            raise ValueError(f"Duplicate resource in generated view: {relative_json}")

        csv_path = json_path.with_suffix(".csv")
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            csv_count = sum(1 for _ in csv.DictReader(handle))
        if csv_count != expected_count:
            raise ValueError(f"CSV record count mismatch: {csv_path.relative_to(views_root)}")

        markdown = json_path.with_suffix(".md").read_text(encoding="utf-8")
        if f"Records: {expected_count}" not in markdown:
            raise ValueError(f"Markdown record count mismatch: {relative_json}")
        rendered_html = json_path.with_suffix(".html").read_text(encoding="utf-8")
        if f"<p>{expected_count} records " not in rendered_html:
            raise ValueError(f"HTML record count mismatch: {relative_json}")


def _publish_view_tree(staging: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}-backup-{uuid.uuid4().hex}")
    moved_existing = False
    try:
        if destination.exists():
            os.replace(destination, backup)
            moved_existing = True
        os.replace(staging, destination)
    except BaseException:
        if moved_existing and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


@audited_curation_command("build-views")
def run_build_views(settings: Settings) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    views_root = settings.data_dir / "views"
    views_root.parent.mkdir(parents=True, exist_ok=True)
    staging = views_root.with_name(f".{views_root.name}-staging-{uuid.uuid4().hex}")
    try:
        result = _build_view_tree(db, staging)
        _publish_view_tree(staging, views_root)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
