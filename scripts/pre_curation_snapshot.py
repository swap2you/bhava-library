"""Create immutable pre-curation snapshot of originals inventory + catalog DB."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _norm(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def create_pre_curation_snapshot(repo_root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snap_dir = repo_root / "data" / "snapshots" / f"pre-curation-{stamp}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    catalog_db = repo_root / "data" / "catalog" / "bhava-library.sqlite3"
    if catalog_db.exists():
        shutil.copy2(catalog_db, snap_dir / "bhava-library.sqlite3")

    # Catalog is source of truth for hashes from verified acquisition
    catalog_rows: list[dict[str, object]] = []
    if catalog_db.exists():
        conn = sqlite3.connect(catalog_db)
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            "SELECT resource_id, relative_path, size_bytes, sha256, quarantine_reason "
            "FROM local_files ORDER BY relative_path"
        ):
            catalog_rows.append(
                {
                    "resource_id": row["resource_id"],
                    "relative_path": _norm(row["relative_path"]),
                    "size_bytes": int(row["size_bytes"]),
                    "sha256": row["sha256"],
                    "quarantine_reason": row["quarantine_reason"],
                }
            )
        conn.close()

    # Filesystem walk for originals + quarantine
    fs_entries: list[dict[str, object]] = []
    total_bytes = 0
    for scope, root in (
        ("originals", repo_root / "data" / "originals"),
        ("quarantine", repo_root / "data" / "quarantine"),
    ):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = _norm(str(path.relative_to(repo_root)))
            size = path.stat().st_size
            total_bytes += size
            fs_entries.append(
                {
                    "scope": scope,
                    "relative_path": rel,
                    "size_bytes": size,
                }
            )

    # Reconcile catalog vs filesystem (size + path; hash from catalog)
    catalog_by_path = {str(r["relative_path"]): r for r in catalog_rows}
    fs_by_path = {str(e["relative_path"]): e for e in fs_entries}

    missing_on_disk = sorted(set(catalog_by_path) - set(fs_by_path))
    extra_on_disk = sorted(set(fs_by_path) - set(catalog_by_path))
    size_mismatches: list[dict[str, object]] = []
    for rel, crow in catalog_by_path.items():
        few = fs_by_path.get(rel)
        if few and int(few["size_bytes"]) != int(crow["size_bytes"]):
            size_mismatches.append(
                {
                    "relative_path": rel,
                    "catalog_bytes": crow["size_bytes"],
                    "disk_bytes": few["size_bytes"],
                }
            )

    inventory_files = []
    for rel, crow in sorted(catalog_by_path.items()):
        few = fs_by_path.get(rel)
        inventory_files.append(
            {
                "resource_id": crow["resource_id"],
                "relative_path": rel,
                "size_bytes": crow["size_bytes"],
                "sha256": crow["sha256"],
                "on_disk": few is not None,
                "disk_bytes": few["size_bytes"] if few else None,
                "quarantine_reason": crow["quarantine_reason"],
            }
        )

    # Also record orphan disk files (not in catalog)
    for rel in extra_on_disk:
        few = fs_by_path[rel]
        inventory_files.append(
            {
                "resource_id": None,
                "relative_path": rel,
                "size_bytes": few["size_bytes"],
                "sha256": None,
                "on_disk": True,
                "disk_bytes": few["size_bytes"],
                "quarantine_reason": None,
                "orphan_disk": True,
            }
        )

    manifest = {
        "snapshot_id": f"pre-curation-{stamp}",
        "created_at": stamp,
        "repo_commit": "17ac6d1ad7fddb3dfe8e47645e43d86476652614",
        "branch": "feature/library-curation-v1",
        "catalog_file_count": len(catalog_rows),
        "disk_file_count": len(fs_entries),
        "disk_total_bytes": total_bytes,
        "catalog_total_bytes": sum(int(r["size_bytes"]) for r in catalog_rows),
        "missing_on_disk": missing_on_disk,
        "extra_on_disk": extra_on_disk,
        "size_mismatches": size_mismatches,
        "files": inventory_files,
    }
    inv_path = snap_dir / "ORIGINAL_INVENTORY.json"
    inv_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    csv_lines = ["relative_path,size_bytes,sha256,on_disk"]
    for e in inventory_files:
        csv_lines.append(
            f"{e['relative_path']},{e['size_bytes']},{e.get('sha256') or ''},{e['on_disk']}"
        )
    (snap_dir / "ORIGINAL_INVENTORY.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    summary = {
        "snapshot_id": manifest["snapshot_id"],
        "created_at": stamp,
        "catalog_file_count": len(catalog_rows),
        "disk_file_count": len(fs_entries),
        "disk_total_bytes": total_bytes,
        "disk_total_gib": round(total_bytes / (1024**3), 3),
        "catalog_total_bytes": manifest["catalog_total_bytes"],
        "missing_on_disk_count": len(missing_on_disk),
        "extra_on_disk_count": len(extra_on_disk),
        "size_mismatch_count": len(size_mismatches),
        "snapshot_dir": str(snap_dir),
        "inventory_sha256": _sha256_file(inv_path),
        "integrity_ok": (
            len(missing_on_disk) == 0 and len(size_mismatches) == 0 and len(catalog_rows) > 0
        ),
    }
    (snap_dir / "SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    reports = repo_root / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "PRE_CURATION_SNAPSHOT.md").write_text(
        f"""# Pre-curation snapshot

- Snapshot ID: `{summary["snapshot_id"]}`
- Branch: `feature/library-curation-v1`
- Baseline commit: `17ac6d1ad7fddb3dfe8e47645e43d86476652614`
- Catalog files: **{summary["catalog_file_count"]}**
- Disk files (originals+quarantine): **{summary["disk_file_count"]}**
- Disk bytes: **{summary["disk_total_bytes"]}** ({summary["disk_total_gib"]} GiB)
- Catalog bytes: **{summary["catalog_total_bytes"]}**
- Missing on disk: **{summary["missing_on_disk_count"]}**
- Extra on disk: **{summary["extra_on_disk_count"]}**
- Size mismatches: **{summary["size_mismatch_count"]}**
- Integrity OK: **{summary["integrity_ok"]}**
- Local snapshot dir: `{summary["snapshot_dir"]}` (gitignored)
- Inventory SHA-256: `{summary["inventory_sha256"]}`

Originals were not modified.
""",
        encoding="utf-8",
    )
    (reports / "PRE_CURATION_SNAPSHOT_SUMMARY.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return snap_dir


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    out = create_pre_curation_snapshot(root)
    print((out / "SUMMARY.json").read_text(encoding="utf-8"))
