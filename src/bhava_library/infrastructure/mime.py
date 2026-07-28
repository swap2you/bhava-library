"""MIME / signature helpers."""

from __future__ import annotations

from pathlib import Path

import filetype

AUDIO_MIMES = frozenset(
    {
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/mp4",
        "audio/aac",
        "audio/ogg",
        "audio/flac",
    }
)
VIDEO_MIMES = frozenset(
    {
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/x-matroska",
        "video/webm",
    }
)


def detect_type(path: Path) -> str | None:
    kind = filetype.guess(str(path))
    if kind is None:
        return None
    mime: str = kind.mime
    return mime


def extension_of(url_or_path: str) -> str:
    name = url_or_path.split("?")[0].split("#")[0]
    return Path(name).suffix.lower()


def is_audio_ext(ext: str) -> bool:
    return ext.lower() in {
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".ogg",
        ".flac",
    }


def is_video_ext(ext: str) -> bool:
    return ext.lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m3u8"}


def is_audio_mime(mime: str | None) -> bool:
    return bool(mime and mime.lower() in AUDIO_MIMES)


def is_video_mime(mime: str | None) -> bool:
    return bool(mime and mime.lower() in VIDEO_MIMES)
