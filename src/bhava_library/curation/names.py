"""Display names and slugs without renaming originals."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database, utc_now

_NON_WORD = re.compile(r"[^\w\s-]", re.UNICODE)
_MULTI_SPACE = re.compile(r"\s+")
_SLUG_INVALID = re.compile(r"[^a-z0-9-]+")


def ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def slugify(text: str, *, max_len: int = 120) -> str:
    folded = ascii_fold(text).lower()
    folded = _NON_WORD.sub(" ", folded)
    folded = _MULTI_SPACE.sub("-", folded.strip())
    folded = _SLUG_INVALID.sub("-", folded)
    folded = re.sub(r"-{2,}", "-", folded).strip("-")
    return folded[:max_len] or "untitled"


def clean_display_title(title_original: str | None, filename: str | None = None) -> str:
    raw = (title_original or "").strip()
    if not raw and filename:
        raw = Path(filename).stem
    # Decode common HTML entities from source titles
    raw = (
        raw.replace("&#039;", "'")
        .replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
    )
    raw = raw.replace("_", " ").replace("-", " ")
    raw = _MULTI_SPACE.sub(" ", raw).strip()
    if not raw:
        return "Untitled"
    return raw[:500]


def build_ascii_aliases(title: str) -> list[str]:
    aliases: list[str] = []
    folded = ascii_fold(title).strip()
    if folded and folded.lower() != title.lower():
        aliases.append(folded)
    compact = re.sub(r"\s+", " ", title).strip()
    if compact and compact not in aliases and compact != title:
        aliases.append(compact)
    return aliases


def build_resource_name_record(
    resource_id: str,
    title_original: str,
    relative_path: str | None,
) -> dict[str, object]:
    filename = Path(relative_path).name if relative_path else None
    display_title = clean_display_title(title_original, filename)
    slug = slugify(display_title)
    export_filename = f"{slug}-{resource_id[-8:]}" if resource_id else slug
    return {
        "resource_id": resource_id,
        "display_title": display_title,
        "display_filename": filename,
        "slug": slug,
        "ascii_aliases_json": json.dumps(build_ascii_aliases(display_title)),
        "alternate_titles_json": json.dumps([]),
        "export_filename": export_filename,
    }


def upsert_resource_names(conn, record: dict[str, object]) -> None:
    conn.execute(
        """
        INSERT INTO resource_names(
          resource_id, display_title, display_filename, slug,
          ascii_aliases_json, alternate_titles_json, export_filename, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(resource_id) DO UPDATE SET
          display_title = excluded.display_title,
          display_filename = excluded.display_filename,
          slug = excluded.slug,
          ascii_aliases_json = excluded.ascii_aliases_json,
          alternate_titles_json = excluded.alternate_titles_json,
          export_filename = excluded.export_filename,
          updated_at = excluded.updated_at
        """,
        (
            record["resource_id"],
            record["display_title"],
            record.get("display_filename"),
            record.get("slug"),
            record["ascii_aliases_json"],
            record["alternate_titles_json"],
            record.get("export_filename"),
            utc_now(),
        ),
    )


def run_names(settings: Settings, *, limit: int | None = None) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    sql = """
        SELECT r.resource_id, r.title_original, lf.relative_path
        FROM resources r
        LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
        WHERE r.removed_at IS NULL
        ORDER BY r.resource_id
    """
    params: tuple[()] | tuple[int] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    rows = db.execute(sql, params)
    updated = 0
    with db.session() as conn:
        for row in rows:
            record = build_resource_name_record(
                row["resource_id"],
                row["title_original"],
                row["relative_path"],
            )
            upsert_resource_names(conn, record)
            updated += 1
    return {"resources": len(rows), "updated": updated}
