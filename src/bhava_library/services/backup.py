"""Non-destructive backup and restore sampling."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.constants import EXIT_BACKUP_VERIFY, EXIT_SUCCESS
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
    """Return a path string suitable for copy on the current OS.

    On Windows, prefix with ``\\\\?\\`` so long paths work. On POSIX, return the
    resolved path unchanged — the Windows long-path prefix breaks Linux/macOS.
    """
    resolved = str(path.resolve())
    if sys.platform != "win32":
        return resolved
    if resolved.startswith("\\\\?\\"):
        return resolved
    return "\\\\?\\" + resolved


def _rel_for(settings: Settings, path: Path) -> Path:
    if path.is_relative_to(settings.repo_root):
        return path.relative_to(settings.repo_root)
    return Path(path.name)


def run_backup(
    settings: Settings,
    target: str | None = None,
    *,
    full_verify: bool = False,
) -> dict[str, object]:
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
    skipped_entries: list[dict[str, str]] = []
    manifest: list[dict[str, str | int]] = []
    source_file_count = 0

    for src in sources:
        if not src.exists():
            continue
        for path in src.rglob("*"):
            if not path.is_file():
                continue
            rel = _rel_for(settings, path)
            if _should_skip(rel):
                continue
            source_file_count += 1
            out = dest / rel
            try:
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
                    {
                        "path": str(rel).replace("\\", "/"),
                        "sha256": digest,
                        "size": size,
                        "status": "copied",
                    }
                )
            except OSError as exc:
                skipped_entries.append(
                    {
                        "path": str(rel).replace("\\", "/"),
                        "reason": str(exc),
                        "status": "skipped",
                    }
                )
                logger.warning("Backup skipped %s: %s", path, exc)

    incomplete = len(skipped_entries) > 0
    verification_ok = (not incomplete) and copied_files == source_file_count

    # Verification pass
    verify_ok = True
    verify_checked = 0
    to_check = manifest if full_verify else manifest[:5]
    for entry in to_check:
        sample_path = dest / str(entry["path"])
        verify_checked += 1
        if not sample_path.exists() or sha256_file(sample_path) != entry["sha256"]:
            verify_ok = False
            break
    if full_verify and len(manifest) != copied_files:
        verify_ok = False

    restore_sample_ok = verify_ok and not incomplete
    verification_ok = verification_ok and restore_sample_ok

    manifest_path = dest / "BACKUP_MANIFEST.json"
    payload = {
        "created_at": stamp,
        "source_file_count": source_file_count,
        "copied_file_count": copied_files,
        "copied_bytes": copied_bytes,
        "skipped_count": len(skipped_entries),
        "incomplete": incomplete,
        "verification_ok": verification_ok,
        "files": manifest,
        "skipped": skipped_entries,
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    backup_id = f"backup-{stamp}"
    db = Database(settings.catalog_db)
    db.migrate()
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO backups(
              backup_id, target_path, started_at, completed_at, file_count,
              byte_count, verification_ok, restore_sample_ok, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                backup_id,
                str(dest),
                utc_now(),
                utc_now(),
                copied_files,
                copied_bytes,
                1 if verification_ok else 0,
                1 if restore_sample_ok else 0,
                (
                    "complete"
                    if verification_ok
                    else f"incomplete; skipped={len(skipped_entries)}; "
                    f"source={source_file_count}; copied={copied_files}"
                ),
            ),
        )

    result = {
        "backup_id": backup_id,
        "target": str(dest),
        "file_count": copied_files,
        "byte_count": copied_bytes,
        "source_file_count": source_file_count,
        "skipped": len(skipped_entries),
        "skipped_paths": skipped_entries,
        "incomplete": incomplete,
        "verification_ok": verification_ok,
        "restore_sample_ok": restore_sample_ok,
        "verify_checked": verify_checked,
        "exit_code": EXIT_SUCCESS if verification_ok else EXIT_BACKUP_VERIFY,
    }
    db.add_event("backup", payload_json=json.dumps(result, default=str))
    logger.info(
        "Backup finished: copied=%s skipped=%s verification_ok=%s -> %s",
        copied_files,
        len(skipped_entries),
        verification_ok,
        dest,
    )
    if incomplete:
        raise BackupVerifyError(
            f"Backup incomplete: {len(skipped_entries)} required file(s) skipped"
        )
    if not verification_ok:
        raise BackupVerifyError("Backup verification failed")
    return result


def run_restore_check(
    settings: Settings,
    target: str,
    *,
    full: bool = False,
) -> dict[str, object]:
    root = Path(target)
    if not root.is_absolute():
        root = settings.repo_root / root
    if not (root / "BACKUP_MANIFEST.json").exists():
        candidates = sorted(root.glob("bhava-library-backup-*"), reverse=True)
        if not candidates:
            raise BackupVerifyError(f"No backup found under {root}")
        root = candidates[0]
    data = json.loads((root / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    if data.get("incomplete") or data.get("skipped"):
        skipped = data.get("skipped") or []
        if skipped:
            raise BackupVerifyError(
                f"Backup marked incomplete with {len(skipped)} skipped required files"
            )
    files = data.get("files", [])
    sample = files if full else files[:25]
    checked = 0
    for entry in sample:
        path = root / entry["path"]
        if not path.exists():
            raise BackupVerifyError(f"Missing {entry['path']}")
        if sha256_file(path) != entry["sha256"]:
            raise BackupVerifyError(f"Hash mismatch {entry['path']}")
        checked += 1
    result = {
        "target": str(root),
        "checked": checked,
        "full": full,
        "ok": True,
        "source_file_count": data.get("source_file_count"),
        "copied_file_count": data.get("copied_file_count"),
    }
    Database(settings.catalog_db).add_event("restore_check", payload_json=json.dumps(result))
    return result
