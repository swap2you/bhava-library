import sqlite3
from pathlib import Path

db = Path("data/catalog/bhava-library.sqlite3")
conn = sqlite3.connect(db)
print("remote_objects", conn.execute("select count(*) from remote_objects").fetchone()[0])
print("statuses", conn.execute("select status, count(*) from resources group by status").fetchall())
print("profiles", conn.execute("select profile, count(*) from resources group by profile").fetchall())
