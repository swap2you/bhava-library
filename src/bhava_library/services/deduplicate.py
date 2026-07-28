"""Non-destructive duplicate grouping."""

from __future__ import annotations

import json

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database


def run_deduplicate(settings: Settings) -> dict[str, int]:
    """Group files by SHA-256. Never deletes duplicates in V1."""
    db = Database(settings.catalog_db)
    db.migrate()
    groups = 0
    linked = 0
    with db.session() as conn:
        rows = list(
            conn.execute(
                """
                SELECT sha256, MIN(file_id) AS canonical, COUNT(*) AS n
                FROM local_files
                WHERE quarantine_reason IS NULL AND sha256 <> ''
                GROUP BY sha256
                HAVING n > 1
                """
            )
        )
        for row in rows:
            groups += 1
            canonical = row["canonical"]
            dupes = list(
                conn.execute(
                    "SELECT file_id FROM local_files WHERE sha256=? AND file_id<>?",
                    (row["sha256"], canonical),
                )
            )
            for dupe in dupes:
                conn.execute(
                    "UPDATE local_files SET duplicate_of_file_id=? WHERE file_id=?",
                    (canonical, dupe["file_id"]),
                )
                linked += 1
    db.add_event("deduplicate", payload_json=json.dumps({"groups": groups, "linked": linked}))
    return {"groups": groups, "linked": linked}
