"""Shared constants and exit codes."""

from __future__ import annotations

PARSER_VERSION = "1.0.0"
SOURCE_ID_ISKCON = "iskcon-education"
USER_AGENT_DEFAULT = "BhavaLibrary/1.0 (+mailto:svarnagaurangdas@gmail.com)"

# Stable CLI exit codes
EXIT_SUCCESS = 0
EXIT_PARTIAL = 10
EXIT_DISK_GUARD_PAUSE = 20
EXIT_NETWORK = 21
EXIT_SOURCE_DRIFT = 22
EXIT_ACCESS_RESTRICTED = 23
EXIT_INTEGRITY = 24
EXIT_CONFIG = 25
EXIT_BACKUP_VERIFY = 26
EXIT_INTERNAL = 30

# Disk / download defaults (overridable via config)
GIB = 1024**3
MIB = 1024**2
DEFAULT_RESERVE_GIB = 50
DEFAULT_RESERVE_PERCENT = 15
DEFAULT_BATCH_CAP_GIB = 20
DEFAULT_MAX_FILE_GIB = 2
DEFAULT_CHUNK_MIB = 4
DISK_CHECK_EVERY_MIB = 64
MAX_GLOBAL_DOWNLOADS = 2
MAX_PER_HOST = 1

BINARY_EXTENSIONS_BLOCKED_FROM_GIT = frozenset(
    {
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
)
MAX_COMMIT_FILE_BYTES = 5 * MIB

DIRECT_FILE_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".epub",
        ".txt",
        ".rtf",
        ".html",
        ".htm",
        ".doc",
        ".docx",
        ".odt",
        ".ppt",
        ".pptx",
        ".odp",
        ".xls",
        ".xlsx",
        ".ods",
        ".csv",
        ".json",
        ".xml",
        ".zip",
        ".rar",
        ".7z",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".svg",
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
    }
)

AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm", ".m3u8"})

WINDOWS_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "COM1",
        "COM2",
        "COM3",
        "COM4",
        "COM5",
        "COM6",
        "COM7",
        "COM8",
        "COM9",
        "LPT1",
        "LPT2",
        "LPT3",
        "LPT4",
        "LPT5",
        "LPT6",
        "LPT7",
        "LPT8",
        "LPT9",
    }
)
