"""Archive pack volume limits and public GitHub refusal."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.archive_pack import (
    PublicGitHubUploadRefused,
    refuse_public_github_upload,
    run_archive_pack,
    run_archive_restore_check,
)
from bhava_library.infrastructure.hashing import sha256_file


@pytest.fixture
def tiny_tree(tmp_path: Path):
    """Legacy fixture name kept for clarity; unused directly."""
    return tmp_path


def test_refuse_public_github_upload(monkeypatch) -> None:
    monkeypatch.setenv("BHAVA_GITHUB_VISIBILITY", "public")
    with pytest.raises(PublicGitHubUploadRefused):
        refuse_public_github_upload()


def test_archive_pack_and_restore_check(tmp_path: Path) -> None:
    s = load_settings()
    s = s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    docs = s.data_dir / "originals" / "iskcon-education" / "documents"
    docs.mkdir(parents=True)
    files = []
    for i in range(3):
        p = docs / f"file{i}.txt"
        p.write_text(f"content-{i}", encoding="utf-8")
        files.append(p)
    (s.data_dir / "catalog").mkdir(parents=True)
    (s.data_dir / "catalog" / "bhava-library.sqlite3").write_bytes(b"sqlite")

    dest = tmp_path / "pack"
    manifest = run_archive_pack(
        s,
        dest=dest,
        volume_size_mib=1,
        dry_run=False,
        limit_files=10,
    )
    assert manifest["file_count"] >= 1
    assert (dest / "ARCHIVE_MANIFEST.json").exists()
    for vol in manifest["volumes"]:
        vol_path = dest / str(vol["volume"])
        assert vol_path.exists()
        assert vol_path.stat().st_size <= 1 * 1024 * 1024 + 4096

    check = run_archive_restore_check(dest, full=True)
    assert check["ok"], check["errors"]

    # Originals unchanged
    for p in files:
        assert p.exists()
        assert sha256_file(p) == sha256_file(p)
