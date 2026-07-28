"""Clean empty verified files and re-queue incomplete jobs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
conn = sqlite3.connect(ROOT / "data" / "catalog" / "bhava-library.sqlite3")
conn.row_factory = sqlite3.Row

# Remove empty local files and mark terminal
rows = list(conn.execute("SELECT * FROM local_files WHERE size_bytes = 0"))
for row in rows:
    path = ROOT / row["relative_path"]
    if path.exists():
        path.unlink()
    conn.execute("DELETE FROM local_files WHERE file_id=?", (row["file_id"],))
    conn.execute(
        "UPDATE download_jobs SET state='terminal_failure', last_error_code='EMPTY_REMOTE' WHERE resource_id=?",
        (row["resource_id"],),
    )
    conn.execute(
        "UPDATE resources SET status='failed_terminal' WHERE resource_id=?",
        (row["resource_id"],),
    )

# Re-queue incomplete/non-terminal jobs
conn.execute(
    """
    UPDATE download_jobs
    SET state='pending', bytes_downloaded=0, part_path=NULL, completed_at=NULL,
        last_error_code=NULL, last_error_message=NULL
    WHERE state IN ('retryable','active','paused')
       OR (state='complete' AND resource_id NOT IN (
            SELECT resource_id FROM local_files WHERE size_bytes > 0
       ) AND last_error_code IS NULL)
    """
)
# Don't re-queue terminal empty
conn.execute(
    """
    UPDATE download_jobs SET state='terminal_failure'
    WHERE last_error_code='EMPTY_REMOTE'
    """
)
conn.execute(
    """
    UPDATE resources SET status='queued'
    WHERE resource_id IN (SELECT resource_id FROM download_jobs WHERE state='pending')
    """
)
conn.commit()
print("jobs", conn.execute("SELECT state, COUNT(*) FROM download_jobs GROUP BY state").fetchall())
print("local_files", conn.execute("SELECT COUNT(*), COALESCE(SUM(size_bytes),0) FROM local_files").fetchone())
