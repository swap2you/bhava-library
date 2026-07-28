import sqlite3

conn = sqlite3.connect("data/catalog/bhava-library.sqlite3")
conn.execute(
    "UPDATE download_jobs SET state='pending' WHERE state IN ('retryable','active','paused','terminal_failure')"
)
conn.execute(
    "UPDATE resources SET status='queued' WHERE resource_id IN "
    "(SELECT resource_id FROM download_jobs WHERE state='pending')"
)
conn.commit()
print(conn.execute("SELECT state, COUNT(*) FROM download_jobs GROUP BY state").fetchall())
