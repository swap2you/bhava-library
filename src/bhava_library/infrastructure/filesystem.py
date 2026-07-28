"""Filesystem helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

from bhava_library.constants import WINDOWS_RESERVED_NAMES

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Produce a Windows-safe filename stem+suffix fragment."""
    cleaned = _UNSAFE_CHARS.sub("_", name).strip(" .")
    if not cleaned:
        cleaned = "unnamed"
    stem = Path(cleaned).stem
    suffix = Path(cleaned).suffix
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    out = f"{stem}{suffix}"
    if len(out) > max_len:
        keep = max_len - len(suffix)
        out = f"{stem[: max(1, keep)]}{suffix}"
    return out


def atomic_rename(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dest)


def mark_readonly(path: Path) -> None:
    if not path.exists():
        return
    mode = path.stat().st_mode
    path.chmod(mode & ~0o222)


def path_is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def safe_join(base: Path, *parts: str) -> Path:
    """Join paths and reject traversal outside base."""
    candidate = base.joinpath(*parts).resolve()
    if not path_is_within(candidate, base.resolve()):
        raise ValueError(f"Path escapes base directory: {candidate}")
    return candidate
