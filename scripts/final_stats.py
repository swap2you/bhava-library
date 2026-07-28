"""Collect final acquisition statistics for the completion report."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
conn = sqlite3.connect(ROOT / "data" / "catalog" / "bhava-library.sqlite3")
conn.row_factory = sqlite3.Row

stats = {
    "resources_total": conn.execute(
        "SELECT COUNT(*) FROM resources WHERE removed_at IS NULL"
    ).fetchone()[0],
    "by_status": dict(
        conn.execute(
            "SELECT status, COUNT(*) FROM resources WHERE removed_at IS NULL GROUP BY status"
        ).fetchall()
    ),
    "by_profile": dict(
        conn.execute(
            "SELECT profile, COUNT(*) FROM resources WHERE removed_at IS NULL GROUP BY profile"
        ).fetchall()
    ),
    "resolved": conn.execute(
        "SELECT COUNT(*) FROM resources WHERE resolved_url IS NOT NULL AND removed_at IS NULL"
    ).fetchone()[0],
    "unresolved": conn.execute(
        "SELECT COUNT(*) FROM resources WHERE status='unresolved' AND removed_at IS NULL"
    ).fetchone()[0],
    "broken": conn.execute(
        "SELECT COUNT(*) FROM resources WHERE status='inaccessible' AND removed_at IS NULL"
    ).fetchone()[0],
    "jobs": dict(
        conn.execute("SELECT state, COUNT(*) FROM download_jobs GROUP BY state").fetchall()
    ),
    "local_files": conn.execute("SELECT COUNT(*) FROM local_files").fetchone()[0],
    "verified_bytes": conn.execute(
        "SELECT COALESCE(SUM(size_bytes),0) FROM local_files WHERE quarantine_reason IS NULL"
    ).fetchone()[0],
    "quarantined": conn.execute(
        "SELECT COUNT(*) FROM local_files WHERE quarantine_reason IS NOT NULL"
    ).fetchone()[0],
    "duplicates": conn.execute(
        "SELECT COUNT(*) FROM local_files WHERE duplicate_of_file_id IS NOT NULL"
    ).fetchone()[0],
    "empty_remote_errors": conn.execute(
        "SELECT COUNT(*) FROM download_jobs WHERE last_error_code='EMPTY_REMOTE'"
    ).fetchone()[0],
    "retryable_errors": list(
        conn.execute(
            """
            SELECT last_error_code, COUNT(*) AS n
            FROM download_jobs
            WHERE state='retryable'
            GROUP BY last_error_code
            """
        )
    ),
    "known_core_bytes_estimate": conn.execute(
        """
        SELECT COALESCE(SUM(content_length),0) FROM remote_objects ro
        JOIN resources r ON r.resource_id=ro.resource_id
        WHERE r.profile='core'
        """
    ).fetchone()[0],
}

out = ROOT / "reports" / "generated" / "completion-stats.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
print(json.dumps(stats, indent=2, default=str))
