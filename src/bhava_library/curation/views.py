"""Generate logical catalog views (metadata only, no file copies)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from bhava_library.config import Settings
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
        """
        SELECT r.resource_id, r.title_original, r.media_type, r.status,
               rn.display_title, lf.relative_path
        FROM resources r
        LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
        LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
        WHERE r.removed_at IS NULL
        ORDER BY r.resource_id
        """
    )


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
    body = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title></head><body>",
        f"<h1>{title}</h1><p>{len(rows)} records (paths as text only).</p><ul>",
    ]
    for row in rows[:500]:
        body.append(
            f"<li><strong>{row.get('display_title')}</strong> "
            f"<code>{row.get('resource_id')}</code> "
            f"<span>{row.get('relative_path') or ''}</span></li>"
        )
    body.append("</ul></body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")


def run_build_views(settings: Settings) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    views_root = settings.data_dir / "views"
    resources = _fetch_resources(db)
    base_records = [_resource_record(r) for r in resources]

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
    written = 4

    for dimension in VIEW_DIMENSIONS:
        rows = db.execute(
            """
            SELECT rc.term, r.resource_id, r.title_original, r.media_type, r.status,
                   rn.display_title, lf.relative_path
            FROM resource_classifications rc
            JOIN resources r ON r.resource_id = rc.resource_id
            LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
            LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
            WHERE rc.dimension = ? AND r.removed_at IS NULL
            ORDER BY rc.term, r.resource_id
            """,
            (dimension,),
        )
        by_term: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            rec = _resource_record(row)
            rec["term"] = row["term"]
            by_term.setdefault(row["term"], []).append(rec)

        dim_slug = dimension.replace("_", "-")
        for term, term_rows in by_term.items():
            out = views_root / f"by-{dim_slug}" / term
            _write_json(out / "index.json", term_rows)
            _write_csv(out / "index.csv", term_rows, [*fields, "term"])
            _write_md(out / "index.md", f"{dimension}: {term}", term_rows)
            _write_html(out / "index.html", f"{dimension}: {term}", term_rows)
            written += 4

    return {"resources": len(resources), "artifacts": written}
