#!/usr/bin/env python3
"""Reject binary / oversized files from Git commits."""

from __future__ import annotations

import sys
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
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

# Explicit tiny fixture allowlist (relative posix paths)
ALLOWLIST = {
    "tests/fixtures/iskcon_education/tiny.txt",
}


def main(argv: list[str]) -> int:
    blocked: list[str] = []
    for raw in argv:
        path = Path(raw)
        posix = path.as_posix()
        if posix in ALLOWLIST:
            continue
        if path.suffix.lower() in BLOCKED_EXT:
            blocked.append(f"{posix}: blocked extension {path.suffix}")
            continue
        if "data/" in posix or posix.startswith("data/"):
            if path.name != ".gitkeep":
                blocked.append(f"{posix}: data/** must not be committed")
                continue
        try:
            if path.is_file() and path.stat().st_size > MAX_BYTES:
                blocked.append(f"{posix}: exceeds 5 MiB")
        except OSError:
            continue
    if blocked:
        print("Bhāva binary/size guard failed:")
        for item in blocked:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
