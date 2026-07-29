"""Compare current originals/quarantine inventory to pre-curation snapshot."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def _norm(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def find_latest_snapshot(repo: Path) -> Path:
    snaps = sorted((repo / "data" / "snapshots").glob("pre-curation-*"))
    if not snaps:
        raise FileNotFoundError("No pre-curation snapshot found")
    return snaps[-1]


def compare(repo: Path) -> dict:
    snap = find_latest_snapshot(repo)
    inv = json.loads((snap / "ORIGINAL_INVENTORY.json").read_text(encoding="utf-8"))
    expected = {
        _norm(f["relative_path"]): f
        for f in inv["files"]
        if f.get("sha256") and not f.get("orphan_disk")
    }

    catalog = repo / "data" / "catalog" / "bhava-library.sqlite3"
    conn = sqlite3.connect(catalog)
    conn.row_factory = sqlite3.Row
    current = {}
    for row in conn.execute("SELECT relative_path, size_bytes, sha256 FROM local_files"):
        current[_norm(row["relative_path"])] = {
            "size_bytes": int(row["size_bytes"]),
            "sha256": row["sha256"],
        }
    conn.close()

    missing = sorted(set(expected) - set(current))
    extra = sorted(set(current) - set(expected))
    hash_mismatch = []
    size_mismatch = []
    for rel, exp in expected.items():
        cur = current.get(rel)
        if not cur:
            continue
        if cur["sha256"] != exp["sha256"]:
            hash_mismatch.append(rel)
        if int(cur["size_bytes"]) != int(exp["size_bytes"]):
            size_mismatch.append(rel)

    # Disk presence
    disk_missing = []
    for rel in expected:
        if not (repo / rel).exists():
            disk_missing.append(rel)

    ok = not (missing or extra or hash_mismatch or size_mismatch or disk_missing)
    return {
        "snapshot_id": inv["snapshot_id"],
        "expected_count": len(expected),
        "current_count": len(current),
        "missing_from_catalog": missing,
        "extra_in_catalog": extra,
        "hash_mismatches": hash_mismatch,
        "size_mismatches": size_mismatch,
        "missing_on_disk": disk_missing,
        "ok": ok,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    result = compare(root)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)
