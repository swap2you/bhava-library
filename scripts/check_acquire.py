import sqlite3
from pathlib import Path

conn = sqlite3.connect("data/catalog/bhava-library.sqlite3")
print("jobs", conn.execute("select state, count(*) from download_jobs group by state").fetchall())
print("local_files", conn.execute("select count(*) from local_files").fetchone()[0])
print(
    "bytes",
    conn.execute(
        "select coalesce(sum(size_bytes),0) from local_files where quarantine_reason is null"
    ).fetchone()[0],
)
print("resources", conn.execute("select status, count(*) from resources group by status").fetchall())
# count files on disk
root = Path("data/originals")
n = sum(1 for p in root.rglob("*") if p.is_file())
print("files_on_disk", n)
