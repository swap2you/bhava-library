"""Archive pack correctness, restore reconciliation, and public refusal."""

from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.archive_pack import (
    ArchivePackError,
    PublicGitHubUploadRefused,
    _manifest_sha256,
    refuse_public_github_upload,
    run_archive_pack,
    run_archive_restore_check,
)
from bhava_library.infrastructure.hashing import sha256_file


def _settings(tmp_path: Path):
    s = load_settings()
    return s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )


def _seed_files(settings, *, count: int = 3, size: int = 32) -> dict[Path, str]:
    docs = settings.data_dir / "originals" / "iskcon-education" / "documents"
    docs.mkdir(parents=True)
    (settings.data_dir / "catalog").mkdir(parents=True)
    (settings.data_dir / "catalog" / "bhava-library.sqlite3").write_bytes(b"sqlite")
    hashes: dict[Path, str] = {}
    for i in range(count):
        path = docs / f"file{i}.bin"
        path.write_bytes(bytes((i % 256,) * size))
        hashes[path] = sha256_file(path)
    return hashes


def test_refuse_public_github_upload(monkeypatch) -> None:
    monkeypatch.setenv("BHAVA_GITHUB_VISIBILITY", "public")
    with pytest.raises(PublicGitHubUploadRefused):
        refuse_public_github_upload()
    monkeypatch.delenv("BHAVA_GITHUB_VISIBILITY")
    with pytest.raises(PublicGitHubUploadRefused):
        refuse_public_github_upload(
            repo_visibility="private",
            upload_target="https://github.com/example/public/releases",
        )
    refuse_public_github_upload(
        repo_visibility="private",
        upload_target="https://github.com/example/private/releases",
    )


def test_archive_pack_and_restore_preserves_source_hashes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    before = _seed_files(settings)
    dest = tmp_path / "pack"
    manifest = run_archive_pack(settings, dest=dest, volume_size_mib=1)
    assert manifest["file_count"] >= 1
    assert manifest["manifest_sha256"] == _manifest_sha256(manifest)
    for vol in manifest["volumes"]:
        vol_path = dest / str(vol["volume"])
        assert vol_path.exists()
        assert vol_path.stat().st_size < 1 * 1024 * 1024
        assert vol["compressed_size_bytes"] == vol_path.stat().st_size
        assert vol["sha256"] == sha256_file(vol_path)

    check = run_archive_restore_check(dest, full=True)
    assert check["ok"], check["errors"]
    for path, digest in before.items():
        assert path.exists()
        assert sha256_file(path) == digest


def test_manifest_self_hash_is_independently_verifiable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_files(settings, count=2)
    dest = tmp_path / "pack-hash"
    manifest = run_archive_pack(settings, dest=dest, volume_size_mib=1)
    on_disk = json.loads((dest / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    assert on_disk["manifest_sha256"] == _manifest_sha256(on_disk)
    assert on_disk["manifest_sha256"] == manifest["manifest_sha256"]


def test_single_file_over_limit_is_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = settings.data_dir / "originals" / "iskcon-education" / "documents"
    docs.mkdir(parents=True)
    (settings.data_dir / "catalog").mkdir(parents=True)
    huge = docs / "huge.bin"
    huge.write_bytes(os.urandom(2 * 1024 * 1024))
    with pytest.raises(ArchivePackError, match="cannot fit safely"):
        run_archive_pack(settings, dest=tmp_path / "pack-huge", volume_size_mib=1)


def test_incompressible_near_limit_splits_or_fits(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    docs = settings.data_dir / "originals" / "iskcon-education" / "documents"
    docs.mkdir(parents=True)
    (settings.data_dir / "catalog").mkdir(parents=True)
    for i in range(3):
        (docs / f"block{i}.bin").write_bytes(os.urandom(400_000))
    dest = tmp_path / "pack-near"
    manifest = run_archive_pack(settings, dest=dest, volume_size_mib=1)
    for vol in manifest["volumes"]:
        assert (dest / str(vol["volume"])).stat().st_size < 1 * 1024 * 1024
    assert run_archive_restore_check(dest, full=True)["ok"]


def test_corrupt_manifest_and_missing_volume(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_files(settings, count=2)
    dest = tmp_path / "pack-ok"
    run_archive_pack(settings, dest=dest, volume_size_mib=1)

    bad = tmp_path / "pack-bad"
    bad.mkdir()
    (bad / "ARCHIVE_MANIFEST.json").write_text("{not-json", encoding="utf-8")
    assert run_archive_restore_check(bad)["ok"] is False

    manifest_path = dest / "ARCHIVE_MANIFEST.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = dest / str(data["volumes"][0]["volume"])
    first.unlink()
    assert run_archive_restore_check(dest)["ok"] is False


def test_corrupt_volume_and_unexpected_entry(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_files(settings, count=2)
    dest = tmp_path / "pack-entries"
    run_archive_pack(settings, dest=dest, volume_size_mib=1)
    manifest_path = dest / "ARCHIVE_MANIFEST.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    vol_path = dest / str(data["volumes"][0]["volume"])
    vol_path.write_bytes(b"not-a-tar")
    assert run_archive_restore_check(dest)["ok"] is False

    # Rebuild clean pack and inject unexpected member into a volume.
    dest2 = tmp_path / "pack-extra"
    run_archive_pack(settings, dest=dest2, volume_size_mib=1)
    data2 = json.loads((dest2 / "ARCHIVE_MANIFEST.json").read_text(encoding="utf-8"))
    vol2 = dest2 / str(data2["volumes"][0]["volume"])
    members: list[tuple[str, bytes]] = []
    with tarfile.open(vol2, "r:gz") as tar:
        for member in tar.getmembers():
            extracted = tar.extractfile(member)
            assert extracted is not None
            members.append((member.name, extracted.read()))
    rebuilt = dest2 / "volume-rebuilt.tar.gz"
    with tarfile.open(rebuilt, "w:gz") as tar:
        for name, payload in members:
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, fileobj=__import__("io").BytesIO(payload))
        extra = b"surprise"
        info = tarfile.TarInfo(name="data/originals/iskcon-education/documents/extra.bin")
        info.size = len(extra)
        tar.addfile(info, fileobj=__import__("io").BytesIO(extra))
    vol2.unlink()
    rebuilt.replace(vol2)
    data2["volumes"][0]["sha256"] = sha256_file(vol2)
    data2["volumes"][0]["compressed_size_bytes"] = vol2.stat().st_size
    data2["manifest_sha256"] = _manifest_sha256(data2)
    (dest2 / "ARCHIVE_MANIFEST.json").write_text(
        json.dumps(data2, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = run_archive_restore_check(dest2)
    assert result["ok"] is False
    assert any("unexpected" in err or "extra" in err for err in result["errors"])


def test_interrupted_pack_cleans_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path)
    _seed_files(settings, count=2)
    dest = tmp_path / "pack-interrupt"
    real_write = json.dumps

    def boom(*args, **kwargs):
        if kwargs.get("indent") == 2:
            raise RuntimeError("interrupt")
        return real_write(*args, **kwargs)

    monkeypatch.setattr("bhava_library.curation.archive_pack.json.dumps", boom)
    with pytest.raises(RuntimeError, match="interrupt"):
        run_archive_pack(settings, dest=dest, volume_size_mib=1)
    assert not dest.exists()
    assert list(dest.parent.glob(f".{dest.name}.tmp-*")) == []
