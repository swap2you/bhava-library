"""Non-destructive backup and restore sampling."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.domain.errors import BackupVerifyError, ConfigError
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.infrastructure.filesystem import ensure_dirs
from bhava_library.infrastructure.hashing import sha256_file
from bhava_library.logging import get_logger

logger = get_logger("bhava.backup")

EXCLUDE_DIR_NAMES = frozenset({"cache", "staging", "__pycache__", ".tmp", "backups"})


def _should_skip(path: Path) -> bool:
    return any(part in EXCLUDE_DIR_NAMES for part in path.parts)


def _win_long(path: Path) -> str:
    resolved = str(path.resolve())
    if resolved.startswith("\\\\?\\"):
        return resolved
    return "\\\\?\\" + resolved


def run_backup(settings: Settings, target: str | None = None) -> dict[str, object]:
    dest_root = Path(target or (settings.backup.target or ""))
    if not str(dest_root):
        raise ConfigError(
            "Backup target required: pass --target or set [backup].target in local.toml"
        )
    if not dest_root.is_absolute():
        dest_root = settings.repo_root / dest_root

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_root / f"bhava-library-backup-{stamp}"
    ensure_dirs(dest)

    sources = [
        settings.repo_root / "config",
        settings.repo_root / "manifests",
        settings.repo_root / "copyright",
        settings.data_dir / "catalog",
        settings.data_dir / "originals",
        settings.data_dir / "snapshots",
    ]

    copied_files = 0
    copied_bytes = 0
    skipped = 0
    manifest: list[dict[str, str | int]] = []

    for src in sources:
        if not src.exists():
            continue
        for path in src.rglob("*"):
            try:
                if not path.is_file():
                    continue
                rel = (
                    path.relative_to(settings.repo_root)
                    if path.is_relative_to(settings.repo_root)
                    else Path(path.name)
                )
                if _should_skip(rel):
                    continue
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                src_s = _win_long(path)
                dst_s = _win_long(out)
                Path(dst_s).parent.mkdir(parents=True, exist_ok=True)
                if out.exists() and out.stat().st_size == path.stat().st_size:
                    pass
                else:
                    shutil.copy2(src_s, dst_s)
                digest = sha256_file(out)
                src_digest = sha256_file(path)
                if digest != src_digest:
                    raise BackupVerifyError(f"Hash mismatch for {rel}")
                size = out.stat().st_size
                copied_files += 1
                copied_bytes += size
                manifest.append(
                    {"path": str(rel).replace("\\", "/"), "sha256": digest, "size": size}
                )
            except OSError as exc:
                skipped += 1
                logger.warning("Backup skipped %s: %s", path, exc)
                continue

    manifest_path = dest / "BACKUP_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(
            {"files": manifest, "created_at": stamp, "skipped": skipped},
            indent=2,
        ),
        encoding="utf-8",
    )

    sample_ok = True
    for entry in manifest[:5]:
        sample_path = dest / str(entry["path"])
        if not sample_path.exists() or sha256_file(sample_path) != entry["sha256"]:
            sample_ok = False
            break

    backup_id = f"backup-{stamp}"
    db = Database(settings.catalog_db)
    db.migrate()
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO backups(
              backup_id, target_path, started_at, completed_at, file_count,
              byte_count, verification_ok, restore_sample_ok, notes
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                backup_id,
                str(dest),
                utc_now(),
                utc_now(),
                copied_files,
                copied_bytes,
                1 if sample_ok else 0,
                f"non-destructive timestamped backup; skipped={skipped}",
            ),
        )
    if not sample_ok and copied_files > 0:
        raise BackupVerifyError("Sampled restore hash check failed")

    result = {
        "backup_id": backup_id,
        "target": str(dest),
        "file_count": copied_files,
        "byte_count": copied_bytes,
        "skipped": skipped,
        "restore_sample_ok": sample_ok,
    }
    db.add_event("backup", payload_json=json.dumps(result))
    logger.info("Backup complete: %s files to %s (skipped=%s)", copied_files, dest, skipped)
    return result


def run_restore_check(settings: Settings, target: str) -> dict[str, object]:
    root = Path(target)
    if not root.is_absolute():
        root = settings.repo_root / root
    if not (root / "BACKUP_MANIFEST.json").exists():
        candidates = sorted(root.glob("bhava-library-backup-*"), reverse=True)
        if not candidates:
            raise BackupVerifyError(f"No backup found under {root}")
        root = candidates[0]
    data = json.loads((root / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    checked = 0
    for entry in data.get("files", [])[:25]:
        path = root / entry["path"]
        if not path.exists():
            raise BackupVerifyError(f"Missing {entry['path']}")
        if sha256_file(path) != entry["sha256"]:
            raise BackupVerifyError(f"Hash mismatch {entry['path']}")
        checked += 1
    result = {"target": str(root), "checked": checked, "ok": True}
    Database(settings.catalog_db).add_event("restore_check", payload_json=json.dumps(result))
    return result
