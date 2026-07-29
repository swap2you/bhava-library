"""Deterministic split-volume archive packing and full restore verification.

The manifest self-hash is SHA-256 over UTF-8 canonical JSON (keys sorted,
``ensure_ascii=False``, separators ``,`` and ``:``), excluding only the
top-level ``manifest_sha256`` field. This makes the stored manifest
independently verifiable without relying on a hash of an earlier file version.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, cast

from bhava_library.config import Settings
from bhava_library.infrastructure.filesystem import ensure_dirs
from bhava_library.infrastructure.hashing import sha256_file

DEFAULT_VOLUME_MIB = 1900
EXCLUDE_NAMES = frozenset({"cache", "staging", "__pycache__", ".tmp", "backups"})
MANIFEST_NAME = "ARCHIVE_MANIFEST.json"
MANIFEST_HASH_ALGORITHM = (
    "sha256 of UTF-8 canonical JSON (sort_keys=true, ensure_ascii=false, "
    "separators=[',',':']) excluding top-level manifest_sha256"
)


class ArchivePackError(ValueError):
    """Raised when a safe archive pack cannot be produced."""


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


def _canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_manifest_bytes(manifest)).hexdigest()


def _safe_relative_path(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _estimated_tar_bytes(entries: list[dict[str, Any]]) -> int:
    # POSIX tar has one 512-byte header per file and pads contents to 512 bytes.
    return 10_240 + sum(512 + ((int(entry["size_bytes"]) + 511) // 512) * 512 for entry in entries)


def _write_deterministic_volume(
    destination: Path,
    entries: list[dict[str, Any]],
) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    try:
        with (
            temporary.open("wb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar,
        ):
            for entry in entries:
                source = Path(entry["_source"])
                info = tar.gettarinfo(str(source), arcname=str(entry["relative_path"]))
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                info.mode = 0o644
                with source.open("rb") as stream:
                    tar.addfile(info, stream)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _cleanup_incomplete_staging(destination: Path) -> None:
    for stale in destination.parent.glob(f".{destination.name}.tmp-*"):
        if stale.is_dir():
            shutil.rmtree(stale, ignore_errors=True)
        else:
            stale.unlink(missing_ok=True)


def run_archive_pack(
    settings: Settings,
    *,
    dest: Path | None = None,
    volume_size_mib: int = DEFAULT_VOLUME_MIB,
    dry_run: bool = False,
    limit_files: int | None = None,
) -> dict[str, object]:
    refuse_public_github_upload()
    if volume_size_mib <= 0:
        raise ArchivePackError("volume_size_mib must be positive")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    pack_root = dest or (settings.data_dir / "backups" / f"archive-pack-{stamp}")

    files = _collect_files(settings)
    if limit_files is not None:
        files = files[:limit_files]

    volume_limit = volume_size_mib * 1024 * 1024
    manifest_entries: list[dict[str, Any]] = []
    for path in files:
        rel = _rel(settings, path)
        size = path.stat().st_size
        manifest_entries.append(
            {
                "relative_path": rel,
                "size_bytes": size,
                "sha256": sha256_file(path) if not dry_run else "dry-run",
                "_source": str(path),
            }
        )

    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for entry in manifest_entries:
        candidate = [*current, entry]
        if current and _estimated_tar_bytes(candidate) >= volume_limit:
            groups.append(current)
            current = [entry]
        else:
            current = candidate
    if current:
        groups.append(current)

    volumes: list[dict[str, object]] = []
    published_entries: list[dict[str, object]] = []
    archive_id = f"archive-pack-{stamp}"
    manifest: dict[str, Any] = {
        "archive_id": archive_id,
        "created_at": stamp,
        "format_version": 2,
        "manifest_hash_algorithm": MANIFEST_HASH_ALGORITHM,
        "volume_size_mib": volume_size_mib,
        "volume_limit_bytes_exclusive": volume_limit,
        "dry_run": dry_run,
        "file_count": len(files),
        "total_size_bytes": sum(int(entry["size_bytes"]) for entry in manifest_entries),
        "volumes": volumes,
        "entries": published_entries,
    }
    if dry_run:
        for index, group in enumerate(groups, start=1):
            volume_name = f"volume-{index:03d}.tar.gz"
            volumes.append(
                {
                    "volume": volume_name,
                    "sha256": "dry-run",
                    "compressed_size_bytes": None,
                    "source_size_bytes": sum(int(entry["size_bytes"]) for entry in group),
                    "file_count": len(group),
                }
            )
            for entry in group:
                published_entries.append(
                    {
                        key: value
                        for key, value in {**entry, "volume_hint": volume_name}.items()
                        if key != "_source"
                    }
                )
        return manifest

    pack_root = pack_root.resolve()
    ensure_dirs(pack_root.parent)
    _cleanup_incomplete_staging(pack_root)
    if pack_root.exists():
        raise FileExistsError(f"Archive destination already exists: {pack_root}")
    staging = pack_root.parent / f".{pack_root.name}.tmp-{uuid.uuid4().hex}"
    staging.mkdir()

    def publish_group(group: list[dict[str, Any]]) -> None:
        volume_name = f"volume-{len(volumes) + 1:03d}.tar.gz"
        volume_path = staging / volume_name
        _write_deterministic_volume(volume_path, group)
        compressed_size = volume_path.stat().st_size
        if compressed_size >= volume_limit:
            volume_path.unlink(missing_ok=True)
            if len(group) == 1:
                raise ArchivePackError(
                    f"{group[0]['relative_path']} cannot fit safely below "
                    f"the {volume_limit}-byte volume limit"
                )
            midpoint = len(group) // 2
            publish_group(group[:midpoint])
            publish_group(group[midpoint:])
            return
        volumes.append(
            {
                "volume": volume_name,
                "sha256": sha256_file(volume_path),
                "compressed_size_bytes": compressed_size,
                "source_size_bytes": sum(int(entry["size_bytes"]) for entry in group),
                "file_count": len(group),
            }
        )
        for entry in group:
            published_entries.append(
                {
                    key: value
                    for key, value in {**entry, "volume_hint": volume_name}.items()
                    if key != "_source"
                }
            )

    try:
        for group in groups:
            publish_group(group)
        manifest["manifest_sha256"] = _manifest_sha256(manifest)
        manifest_path = staging / MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verification = run_archive_restore_check(staging, full=True)
        if not verification["ok"]:
            restore_errors = verification["errors"]
            if not isinstance(restore_errors, list):
                raise ArchivePackError("Staged archive failed full verification")
            raise ArchivePackError(
                "Staged archive failed full verification: "
                + "; ".join(str(error) for error in restore_errors)
            )
        os.replace(staging, pack_root)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def _failed_restore(*errors: str) -> dict[str, object]:
    return {
        "volumes_checked": 0,
        "entries_checked": 0,
        "files_restored": 0,
        "bytes_restored": 0,
        "errors": list(errors),
        "ok": False,
    }


def _copy_and_hash(source: BinaryIO, destination: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with destination.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def run_archive_restore_check(
    pack_root: Path,
    *,
    extract_to: Path | None = None,
    full: bool = False,
) -> dict[str, object]:
    del full  # All restore checks are intentionally full; retained for CLI compatibility.
    pack_root = pack_root.resolve()
    manifest_path = pack_root / MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _failed_restore(f"corrupt manifest: {exc}")
    if not isinstance(manifest, dict):
        return _failed_restore("corrupt manifest: top-level value is not an object")

    errors: list[str] = []
    stored_manifest_hash = manifest.get("manifest_sha256")
    if not isinstance(stored_manifest_hash, str):
        errors.append("manifest self-hash missing")
    elif stored_manifest_hash != _manifest_sha256(manifest):
        errors.append("manifest self-hash mismatch")

    raw_volumes = manifest.get("volumes")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_volumes, list) or not isinstance(raw_entries, list):
        return _failed_restore(*errors, "corrupt manifest: volumes/entries must be arrays")
    volume_limit = _nonnegative_int(manifest.get("volume_limit_bytes_exclusive"))
    if volume_limit is None or volume_limit == 0:
        errors.append("corrupt manifest: invalid exclusive volume limit")

    entries: dict[str, dict[str, Any]] = {}
    expected_by_volume: dict[str, set[str]] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            errors.append("corrupt manifest: entry is not an object")
            continue
        relative_path = _safe_relative_path(raw_entry.get("relative_path"))
        if relative_path is None:
            errors.append(f"unsafe manifest path {raw_entry.get('relative_path')!r}")
            continue
        if relative_path in entries:
            errors.append(f"duplicate manifest entry {relative_path}")
            continue
        if _nonnegative_int(raw_entry.get("size_bytes")) is None:
            errors.append(f"invalid entry size {relative_path}")
            continue
        if not _is_sha256(raw_entry.get("sha256")):
            errors.append(f"invalid entry hash {relative_path}")
            continue
        volume_hint = raw_entry.get("volume_hint")
        if not isinstance(volume_hint, str):
            errors.append(f"missing volume hint {relative_path}")
            continue
        entries[relative_path] = raw_entry
        expected_by_volume.setdefault(volume_hint, set()).add(relative_path)

    volume_records: dict[str, dict[str, Any]] = {}
    for raw_volume in raw_volumes:
        if not isinstance(raw_volume, dict):
            errors.append("corrupt manifest: volume is not an object")
            continue
        volume_name = raw_volume.get("volume")
        if (
            not isinstance(volume_name, str)
            or Path(volume_name).name != volume_name
            or not volume_name.startswith("volume-")
            or not volume_name.endswith(".tar.gz")
        ):
            errors.append(f"unsafe volume name {volume_name!r}")
            continue
        if volume_name in volume_records:
            errors.append(f"duplicate volume record {volume_name}")
            continue
        if (
            _nonnegative_int(raw_volume.get("compressed_size_bytes")) is None
            or _nonnegative_int(raw_volume.get("source_size_bytes")) is None
            or _nonnegative_int(raw_volume.get("file_count")) is None
            or not _is_sha256(raw_volume.get("sha256"))
        ):
            errors.append(f"invalid volume metadata {volume_name}")
            continue
        volume_records[volume_name] = raw_volume

    disk_volumes = {path.name for path in pack_root.glob("*.tar.gz") if path.is_file()}
    expected_volumes = set(volume_records)
    for name in sorted(expected_volumes - disk_volumes):
        errors.append(f"missing volume {name}")
    for name in sorted(disk_volumes - expected_volumes):
        errors.append(f"extra volume {name}")
    for name in sorted(set(expected_by_volume) - expected_volumes):
        errors.append(f"entry references unknown volume {name}")

    restore_parent = extract_to.resolve().parent if extract_to else pack_root
    ensure_dirs(restore_parent)
    restore_root = restore_parent / f"._restore.tmp-{uuid.uuid4().hex}"
    restore_root.mkdir()
    volumes_checked = 0
    extracted_paths: set[str] = set()
    restored_bytes = 0
    try:
        for volume_name in sorted(expected_volumes & disk_volumes):
            volume = volume_records[volume_name]
            volume_path = pack_root / volume_name
            actual_compressed_size = volume_path.stat().st_size
            if actual_compressed_size != volume.get("compressed_size_bytes"):
                errors.append(f"compressed size mismatch {volume_name}")
            if volume_limit is not None and actual_compressed_size >= volume_limit:
                errors.append(f"volume exceeds exclusive limit {volume_name}")
            if sha256_file(volume_path) != volume.get("sha256"):
                errors.append(f"hash mismatch {volume_name}")
            expected_members = expected_by_volume.get(volume_name, set())
            seen_members: set[str] = set()
            try:
                with tarfile.open(volume_path, "r:gz") as tar:
                    members = tar.getmembers()
                    for member in members:
                        member_name = _safe_relative_path(member.name)
                        if member_name is None:
                            errors.append(f"path traversal or unsafe archive entry {member.name!r}")
                            continue
                        if member_name in seen_members:
                            errors.append(f"duplicate archive entry {member_name}")
                            continue
                        seen_members.add(member_name)
                        if not member.isfile():
                            errors.append(f"unexpected non-file archive entry {member_name}")
                            continue
                        if member_name not in expected_members:
                            errors.append(f"unexpected archive entry {member_name}")
                            continue
                        entry = entries[member_name]
                        if member.size != entry.get("size_bytes"):
                            errors.append(f"entry size mismatch {member_name}")
                            continue
                        stream = tar.extractfile(member)
                        if stream is None:
                            errors.append(f"unreadable archive entry {member_name}")
                            continue
                        destination = restore_root.joinpath(*PurePosixPath(member_name).parts)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            size, digest = _copy_and_hash(cast(BinaryIO, stream), destination)
                        except FileExistsError:
                            errors.append(f"duplicate extracted entry {member_name}")
                            continue
                        extracted_paths.add(member_name)
                        restored_bytes += size
                        if size != entry.get("size_bytes"):
                            errors.append(f"restored size mismatch {member_name}")
                        if digest != entry.get("sha256"):
                            errors.append(f"entry hash mismatch {member_name}")
                for missing in sorted(expected_members - seen_members):
                    errors.append(f"missing archive entry {missing}")
            except (OSError, EOFError, tarfile.TarError) as exc:
                errors.append(f"corrupt volume {volume_name}: {exc}")
            volumes_checked += 1

        for missing in sorted(set(entries) - extracted_paths):
            errors.append(f"missing extracted {missing}")
        actual_files = [path for path in restore_root.rglob("*") if path.is_file()]
        actual_relative = {path.relative_to(restore_root).as_posix() for path in actual_files}
        for unexpected in sorted(actual_relative - set(entries)):
            errors.append(f"unexpected restored file {unexpected}")
        if manifest.get("file_count") != len(entries):
            errors.append("manifest file count mismatch")
        if len(actual_files) != len(entries):
            errors.append("restored file count mismatch")
        expected_total = sum(int(entry["size_bytes"]) for entry in entries.values())
        if manifest.get("total_size_bytes") != expected_total:
            errors.append("manifest total byte count mismatch")
        if restored_bytes != expected_total:
            errors.append("restored total byte count mismatch")
        if sum(int(volume["file_count"]) for volume in volume_records.values()) != len(entries):
            errors.append("volume file count reconciliation mismatch")
        if (
            sum(int(volume["source_size_bytes"]) for volume in volume_records.values())
            != expected_total
        ):
            errors.append("volume byte reconciliation mismatch")

        if extract_to is not None and not errors:
            destination = extract_to.resolve()
            if destination.exists():
                raise FileExistsError(f"Restore destination already exists: {destination}")
            os.replace(restore_root, destination)
    finally:
        if restore_root.exists():
            shutil.rmtree(restore_root, ignore_errors=True)

    return {
        "volumes_checked": volumes_checked,
        "entries_checked": len(extracted_paths),
        "files_restored": len(extracted_paths),
        "bytes_restored": restored_bytes,
        "errors": errors,
        "ok": not errors,
    }
