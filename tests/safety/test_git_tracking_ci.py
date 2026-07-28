"""CI gate: fail if data/, secrets, or blocked binaries are tracked."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BLOCKED_EXT = {
    ".pdf",
    ".epub",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".ogg",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".zip",
    ".rar",
    ".7z",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".part",
    ".partial",
}
ALLOWLIST = {
    "tests/fixtures/iskcon_education/tiny.txt",
}
MAX_BYTES = 5 * 1024 * 1024
SECRET_NAMES = {"config/local.toml", ".env"}


def tracked_files() -> list[str]:
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def test_no_data_tracked() -> None:
    bad = [p for p in tracked_files() if p.startswith("data/") and p != "data/.gitkeep"]
    assert not bad, f"data/ must not be tracked except .gitkeep: {bad[:20]}"


def test_no_secrets_tracked() -> None:
    tracked = set(tracked_files())
    leaked = sorted(tracked & SECRET_NAMES)
    assert not leaked, f"Secret/local config tracked: {leaked}"


def test_no_blocked_binaries_tracked() -> None:
    bad: list[str] = []
    for rel in tracked_files():
        if rel in ALLOWLIST:
            continue
        suffix = Path(rel).suffix.lower()
        if suffix in BLOCKED_EXT:
            bad.append(rel)
    assert not bad, f"Blocked binary formats tracked: {bad[:20]}"


def test_no_oversized_tracked_files() -> None:
    bad: list[str] = []
    for rel in tracked_files():
        path = ROOT / rel
        if path.is_file() and path.stat().st_size > MAX_BYTES:
            bad.append(f"{rel}={path.stat().st_size}")
    assert not bad, f"Tracked files exceed 5 MiB: {bad[:20]}"


def test_package_directory_not_tracked() -> None:
    bad = [
        p
        for p in tracked_files()
        if p.startswith("Bhava_Library_Cursor_Implementation_Package_v1.0/")
    ]
    assert not bad, "Extracted package must not remain Git-tracked"
