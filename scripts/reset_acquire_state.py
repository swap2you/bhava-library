"""Reset failed/quarantined acquisition state for a clean resume."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
conn = sqlite3.connect(ROOT / "data" / "catalog" / "bhava-library.sqlite3")

# Clear local_files quarantine records so files can be re-verified after re-download
conn.execute("DELETE FROM local_files")
conn.execute(
    """
    UPDATE download_jobs
    SET state='pending', bytes_downloaded=0, part_path=NULL,
        last_error_code=NULL, last_error_message=NULL, completed_at=NULL
    WHERE state IN ('retryable','active','paused','terminal_failure','complete')
    """
)
conn.execute(
    """
    UPDATE resources
    SET status='queued'
    WHERE resource_id IN (SELECT resource_id FROM download_jobs)
      AND profile IN ('core','unknown')
    """
)
conn.commit()
print("jobs", conn.execute("SELECT state, COUNT(*) FROM download_jobs GROUP BY state").fetchall())

# Clear staging/quarantine/originals for core re-acquire (safe: gitignored data only)
for rel in (
    "data/staging",
    "data/quarantine",
    "data/originals/iskcon-education/documents",
    "data/originals/iskcon-education/office",
    "data/originals/iskcon-education/images",
    "data/originals/iskcon-education/archives",
    "data/originals/iskcon-education/unknown",
):
    path = ROOT / rel
    if path.exists():
        for child in path.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
print("cleared local download artifacts")
