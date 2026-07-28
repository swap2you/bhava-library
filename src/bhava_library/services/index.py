"""SQLite FTS5 indexing."""

from __future__ import annotations

import json
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.domain.enums import ResourceStatus
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.logging import get_logger

logger = get_logger("bhava.index")


def run_index(settings: Settings) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    indexed = 0
    with db.session() as conn:
        conn.execute("DELETE FROM resources_fts")
        rows = list(
            conn.execute(
                """
                SELECT * FROM resources
                WHERE removed_at IS NULL
                """
            )
        )
        for row in rows:
            conn.execute(
                """
                INSERT INTO resources_fts(
                  resource_id, title, source_label, theme, media_type,
                  media_format, level, language, description, extracted_text, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["resource_id"],
                    row["title_original"] or "",
                    row["source_label"] or "",
                    row["theme"] or "",
                    row["media_type"] or "",
                    row["media_format"] or "",
                    row["level"] or "",
                    row["language"] or "",
                    "",
                    "",
                    "",
                ),
            )
            if row["status"] in {
                ResourceStatus.VERIFIED.value,
                ResourceStatus.DOWNLOADED.value,
                ResourceStatus.INDEXED.value,
            }:
                conn.execute(
                    "UPDATE resources SET status=? WHERE resource_id=? AND status IN ('verified','downloaded')",
                    (ResourceStatus.INDEXED.value, row["resource_id"]),
                )
            indexed += 1
    db.add_event("index", payload_json=json.dumps({"indexed": indexed}))
    logger.info("Indexed %s resources into FTS5", indexed)
    return {"indexed": indexed}


def rebuild_from_jsonl(settings: Settings, jsonl_path: Path) -> int:
    """Rebuild resources table entries from a JSONL manifest (idempotent upsert)."""
    db = Database(settings.catalog_db)
    db.migrate()
    count = 0
    with db.session() as conn, jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            now = utc_now()
            conn.execute(
                """
                INSERT INTO resources(
                  resource_id, source_id, source_row_key, title_original, title_normalized,
                  level, media_type, media_format, theme, source_label, language,
                  original_url, profile, priority, status, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                  title_original=excluded.title_original,
                  title_normalized=excluded.title_normalized,
                  level=excluded.level,
                  media_type=excluded.media_type,
                  media_format=excluded.media_format,
                  theme=excluded.theme,
                  source_label=excluded.source_label,
                  original_url=excluded.original_url,
                  profile=excluded.profile,
                  priority=excluded.priority,
                  last_seen_at=excluded.last_seen_at
                """,
                (
                    data["resource_id"],
                    data["source_id"],
                    data["source_row_key"],
                    data["title_original"],
                    data.get("title_normalized") or "",
                    data.get("level"),
                    data.get("media_type"),
                    data.get("media_format"),
                    data.get("theme"),
                    data.get("source_label"),
                    data.get("language"),
                    data["original_url"],
                    data.get("profile") or "unknown",
                    data.get("priority") or 100,
                    data.get("status") or "discovered",
                    now,
                    now,
                ),
            )
            count += 1
    run_index(settings)
    return count
