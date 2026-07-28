"""Split-volume archive pack with restore verification."""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.infrastructure.filesystem import ensure_dirs
from bhava_library.infrastructure.hashing import sha256_file

DEFAULT_VOLUME_MIB = 1900
EXCLUDE_NAMES = frozenset({"cache", "staging", "__pycache__", ".tmp", "backups"})


class PublicGitHubUploadRefused(Exception):
    """Raised when a public GitHub target is detected."""


def refuse_public_github_upload(
    *,
    repo_visibility: str | None = None,
    upload_target: str | None = None,
) -> None:
    vis = (repo_visibility or os.environ.get("BHAVA_GITHUB_VISIBILITY", "")).lower()
    target = (upload_target or os.environ.get("BHAVA_GITHUB_UPLOAD_TARGET", "")).lower()
    if vis == "public" or "github.com" in target and "/public" in target:
        raise PublicGitHubUploadRefused(
            "Refusing archive upload to a public GitHub repository. "
            "Use private release assets with explicit owner approval."
        )
    if vis == "public":
        raise PublicGitHubUploadRefused("BHAVA_GITHUB_VISIBILITY=public is not allowed.")


def _should_include(path: Path, data_dir: Path, repo_root: Path) -> bool:
    if any(part in EXCLUDE_NAMES for part in path.parts):
        return False
    allowed_roots = (
        data_dir / "originals",
        data_dir / "catalog",
        data_dir / "derived",
        data_dir / "views",
        data_dir / "exports",
        data_dir / "snapshots",
        data_dir / "quarantine",
        repo_root / "manifests",
    )
    return any(path.is_relative_to(root) for root in allowed_roots if root.exists())


def _collect_files(settings: Settings) -> list[Path]:
    files: list[Path] = []
    for root in (
        settings.data_dir / "originals",
        settings.data_dir / "catalog",
        settings.data_dir / "derived",
        settings.data_dir / "views",
        settings.data_dir / "exports",
        settings.data_dir / "snapshots",
        settings.data_dir / "quarantine",
        settings.manifests_dir,
    ):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and _should_include(path, settings.data_dir, settings.repo_root):
                files.append(path)
    return files


def _rel(settings: Settings, path: Path) -> str:
    if path.is_relative_to(settings.repo_root):
        return path.relative_to(settings.repo_root).as_posix()
    if path.is_relative_to(settings.data_dir):
        parent = settings.data_dir.parent
        if settings.data_dir.name == "data":
            return path.relative_to(parent).as_posix()
        return path.relative_to(settings.data_dir).as_posix()
    return path.name


def run_archive_pack(
    settings: Settings,
    *,
    dest: Path | None = None,
    volume_size_mib: int = DEFAULT_VOLUME_MIB,
    dry_run: bool = False,
    limit_files: int | None = None,
) -> dict[str, object]:
    refuse_public_github_upload()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    pack_root = dest or (settings.data_dir / "backups" / f"archive-pack-{stamp}")
    if dry_run:
        pack_root = settings.data_dir / "backups" / f"archive-pack-dryrun-{stamp}"

    files = _collect_files(settings)
    if limit_files is not None:
        files = files[:limit_files]

    volume_limit = volume_size_mib * 1024 * 1024
    volumes: list[dict[str, object]] = []
    manifest_entries: list[dict[str, object]] = []
    current_size = 0
    vol_idx = 1
    current_members: list[tuple[Path, str]] = []

    def flush_volume() -> None:
        nonlocal vol_idx, current_size, current_members
        if not current_members:
            return
        vol_name = f"volume-{vol_idx:03d}.tar.gz"
        vol_path = pack_root / vol_name
        if not dry_run:
            ensure_dirs(pack_root)
            with tarfile.open(vol_path, "w:gz") as tar:
                for src, arcname in current_members:
                    tar.add(src, arcname=arcname)
            vol_sha = sha256_file(vol_path)
        else:
            vol_sha = "dry-run"
        volumes.append(
            {
                "volume": vol_name,
                "sha256": vol_sha,
                "file_count": len(current_members),
                "bytes": current_size,
            }
        )
        vol_idx += 1
        current_size = 0
        current_members = []

    for path in files:
        rel = _rel(settings, path)
        size = path.stat().st_size
        if current_size + size > volume_limit and current_members:
            flush_volume()
        current_members.append((path, rel))
        current_size += size
        manifest_entries.append(
            {
                "relative_path": rel,
                "size_bytes": size,
                "sha256": sha256_file(path) if not dry_run else "dry-run",
                "volume_hint": f"volume-{vol_idx:03d}.tar.gz",
            }
        )
    flush_volume()

    manifest = {
        "archive_id": f"archive-pack-{stamp}",
        "created_at": stamp,
        "volume_size_mib": volume_size_mib,
        "dry_run": dry_run,
        "file_count": len(files),
        "volumes": volumes,
        "entries": manifest_entries,
    }
    if not dry_run:
        ensure_dirs(pack_root)
        manifest_path = pack_root / "ARCHIVE_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest["manifest_sha256"] = sha256_file(manifest_path)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def run_archive_restore_check(
    pack_root: Path,
    *,
    extract_to: Path | None = None,
    full: bool = False,
) -> dict[str, object]:
    manifest_path = pack_root / "ARCHIVE_MANIFEST.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tmp = extract_to or (pack_root / f"_restore-check-{uuid.uuid4().hex[:8]}")
    tmp.mkdir(parents=True, exist_ok=True)

    verified = 0
    errors: list[str] = []
    try:
        for vol in manifest.get("volumes", []):
            vol_path = pack_root / str(vol["volume"])
            if not vol_path.exists():
                errors.append(f"missing volume {vol_path.name}")
                continue
            if sha256_file(vol_path) != vol.get("sha256"):
                errors.append(f"hash mismatch {vol_path.name}")
            with tarfile.open(vol_path, "r:gz") as tar:
                tar.extractall(path=tmp, filter="data")
            verified += 1

        sample = manifest.get("entries", [])
        if not full:
            sample = sample[: min(20, len(sample))]
        for entry in sample:
            rel = entry["relative_path"]
            extracted = tmp / rel
            if not extracted.exists():
                errors.append(f"missing extracted {rel}")
                continue
            if sha256_file(extracted) != entry.get("sha256"):
                errors.append(f"entry hash mismatch {rel}")
    finally:
        if extract_to is None and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)

    return {
        "volumes_checked": verified,
        "entries_checked": len(sample) if not full else len(manifest.get("entries", [])),
        "errors": errors,
        "ok": not errors,
    }
