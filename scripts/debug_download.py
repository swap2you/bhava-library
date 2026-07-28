import sqlite3
from pathlib import Path

import httpx

conn = sqlite3.connect("data/catalog/bhava-library.sqlite3")
rows = conn.execute(
    """
    SELECT r.resource_id, r.resolved_url, r.original_url, lf.quarantine_reason, lf.size_bytes
    FROM resources r
    LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
    WHERE r.status='quarantined'
    LIMIT 5
    """
).fetchall()
print("quarantine samples", rows)

# Test one pending URL
row = conn.execute(
    """
    SELECT r.resolved_url, j.expected_bytes
    FROM download_jobs j
    JOIN resources r ON r.resource_id=j.resource_id
    WHERE j.state='pending' AND j.expected_bytes > 1000
    LIMIT 1
    """
).fetchone()
print("probe row", row)
url = row[0]
r = httpx.get(
    url,
    headers={"User-Agent": "BhavaLibrary/1.0 (+mailto:svarnagaurangdas@gmail.com)"},
    follow_redirects=True,
    timeout=60,
)
print("status", r.status_code, "len", len(r.content), "ct", r.headers.get("content-type"))
print("cl", r.headers.get("content-length"))
print("url final", r.url)
print("first bytes", r.content[:20])
