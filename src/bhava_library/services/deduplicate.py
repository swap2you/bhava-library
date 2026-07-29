"""Non-destructive duplicate grouping."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database

TRUNCATED_SOURCE_MAX_BYTES = 511


def _collision_kind(size_bytes: int) -> str:
    if size_bytes == 0:
        return "empty-source-collision"
    if size_bytes <= TRUNCATED_SOURCE_MAX_BYTES:
        return "truncated-source-collision"
    return "duplicate-content"


def _write_reacquisition_report(settings: Settings, rows: list[dict[str, object]]) -> Path:
    report_dir = settings.data_dir / "derived" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    destination = report_dir / "reacquisition_queue.json"
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    payload = {
        "queue_count": len(rows),
        "delete_recommendations": 0,
        "items": rows,
    }
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def run_deduplicate(settings: Settings) -> dict[str, int]:
    """Group exact bytes without treating empty/truncated source collisions as deletable."""
    db = Database(settings.catalog_db)
    db.migrate()
    groups = 0
    linked = 0
    duplicate_content = 0
    empty_collisions = 0
    truncated_collisions = 0
    with db.session() as conn:
        conn.execute(
            """
            UPDATE local_files
            SET duplicate_of_file_id = NULL,
                duplicate_kind = NULL,
                reacquisition_required = CASE
                  WHEN size_bytes <= ? THEN 1 ELSE 0 END
            """,
            (TRUNCATED_SOURCE_MAX_BYTES,),
        )
        rows = list(
            conn.execute(
                """
                SELECT sha256, MIN(file_id) AS canonical, COUNT(*) AS n
                FROM local_files
                WHERE sha256 <> ''
                GROUP BY sha256
                HAVING n > 1
                """
            )
        )
        for row in rows:
            groups += 1
            canonical = row["canonical"]
            members = list(
                conn.execute(
                    """
                    SELECT file_id, size_bytes
                    FROM local_files
                    WHERE sha256 = ?
                    ORDER BY file_id
                    """,
                    (row["sha256"],),
                )
            )
            kind = _collision_kind(int(members[0]["size_bytes"]))
            if kind == "duplicate-content":
                duplicate_content += 1
            elif kind == "empty-source-collision":
                empty_collisions += 1
            else:
                truncated_collisions += 1
            for member in members:
                is_canonical = member["file_id"] == canonical
                conn.execute(
                    """
                    UPDATE local_files
                    SET duplicate_of_file_id = ?,
                        duplicate_kind = ?,
                        reacquisition_required = ?
                    WHERE file_id = ?
                    """,
                    (
                        None if is_canonical else canonical,
                        kind,
                        0 if kind == "duplicate-content" else 1,
                        member["file_id"],
                    ),
                )
                if not is_canonical:
                    linked += 1

        queue = [
            {
                "file_id": row["file_id"],
                "resource_id": row["resource_id"],
                "title": row["title_original"],
                "relative_path": row["relative_path"],
                "original_url": row["original_url"],
                "size_bytes": row["size_bytes"],
                "sha256": row["sha256"],
                "collision_kind": row["duplicate_kind"]
                or ("empty-source" if row["size_bytes"] == 0 else "truncated-source"),
                "recommended_action": "reacquire-from-source",
                "delete_duplicate": False,
            }
            for row in conn.execute(
                """
                SELECT lf.file_id, lf.resource_id, lf.relative_path, lf.size_bytes,
                       lf.sha256, lf.duplicate_kind, r.title_original, r.original_url
                FROM local_files lf
                JOIN resources r ON r.resource_id = lf.resource_id
                WHERE lf.reacquisition_required = 1
                ORDER BY lf.resource_id, lf.file_id
                """
            )
        ]
    report_path = _write_reacquisition_report(settings, queue)
    stats = {
        "groups": groups,
        "linked": linked,
        "duplicate_content_groups": duplicate_content,
        "empty_collision_groups": empty_collisions,
        "truncated_collision_groups": truncated_collisions,
        "reacquisition_queue": len(queue),
    }
    db.add_event(
        "deduplicate",
        payload_json=json.dumps({**stats, "report": str(report_path)}),
    )
    return stats
