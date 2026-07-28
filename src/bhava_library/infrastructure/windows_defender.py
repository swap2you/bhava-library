"""Optional Windows Defender scan integration."""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 — Defender MpCmdRun only
from dataclasses import dataclass
from pathlib import Path

from bhava_library.logging import get_logger

logger = get_logger("bhava.defender")


@dataclass(frozen=True)
class DefenderResult:
    available: bool
    clean: bool | None
    detail: str


def defender_available() -> bool:
    return (
        shutil.which("MpCmdRun.exe") is not None
        or Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe").exists()
    )


def _mpcmdrun() -> str | None:
    which = shutil.which("MpCmdRun.exe")
    if which:
        return which
    candidate = Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe")
    if candidate.exists():
        return str(candidate)
    return None


def scan_file(path: Path) -> DefenderResult:
    """Scan a file with Windows Defender when available.

    MpCmdRun -Scan -ScanType 3 -File <path> returns 0 when clean.
    """
    exe = _mpcmdrun()
    if exe is None:
        return DefenderResult(available=False, clean=None, detail="Windows Defender CLI not found")
    try:
        completed = subprocess.run(  # nosec B603
            [exe, "-Scan", "-ScanType", "3", "-File", str(path)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Defender scan failed: %s", exc)
        return DefenderResult(available=True, clean=None, detail=str(exc))
    clean = completed.returncode == 0
    detail = (completed.stdout or completed.stderr or "").strip()[:500]
    lower = detail.lower()
    threat_markers = (
        "threat",
        "detected",
        "infected",
        "malware",
        "virus",
        "trojan",
    )
    if completed.returncode != 0 and not any(m in lower for m in threat_markers):
        # Non-zero often means path/permissions issues, not a positive detection.
        logger.warning(
            "Defender inconclusive for %s exit=%s detail=%s",
            path,
            completed.returncode,
            detail,
        )
        return DefenderResult(available=True, clean=None, detail=detail or f"exit={completed.returncode}")
    return DefenderResult(
        available=True, clean=clean, detail=detail or f"exit={completed.returncode}"
    )
