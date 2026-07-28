"""Disk space guardrails."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from bhava_library.constants import GIB
from bhava_library.domain.errors import DiskGuardError


@dataclass(frozen=True)
class DiskSnapshot:
    path: Path
    total_bytes: int
    used_bytes: int
    free_bytes: int


def disk_usage(path: Path) -> DiskSnapshot:
    usage = shutil.disk_usage(path)
    return DiskSnapshot(
        path=path,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
    )


def compute_reserve_bytes(
    total_bytes: int,
    reserve_gib: float,
    reserve_percent: float,
) -> int:
    fixed = int(reserve_gib * GIB)
    percent = int(total_bytes * (reserve_percent / 100.0))
    return max(fixed, percent)


def compute_overhead_bytes(
    known_queue_bytes: int,
    overhead_percent: float,
    overhead_gib: float,
) -> int:
    return int(known_queue_bytes * (overhead_percent / 100.0) + overhead_gib * GIB)


def assert_safe_to_start(
    *,
    data_dir: Path,
    planned_bytes: int,
    known_queue_bytes: int,
    reserve_gib: float,
    reserve_percent: float,
    overhead_percent: float,
    overhead_gib: float,
) -> DiskSnapshot:
    snap = disk_usage(data_dir)
    reserve = compute_reserve_bytes(snap.total_bytes, reserve_gib, reserve_percent)
    overhead = compute_overhead_bytes(known_queue_bytes, overhead_percent, overhead_gib)
    projected = snap.free_bytes - planned_bytes - overhead
    if projected < reserve:
        raise DiskGuardError(
            f"DISK_GUARD_PAUSE: projected free {projected} < reserve {reserve} "
            f"(free={snap.free_bytes}, planned={planned_bytes}, overhead={overhead})"
        )
    return snap


def assert_safe_during_transfer(
    *,
    data_dir: Path,
    reserve_gib: float,
    reserve_percent: float,
) -> DiskSnapshot:
    snap = disk_usage(data_dir)
    reserve = compute_reserve_bytes(snap.total_bytes, reserve_gib, reserve_percent)
    if snap.free_bytes <= reserve:
        raise DiskGuardError(
            f"DISK_GUARD_PAUSE: free {snap.free_bytes} approached reserve {reserve}"
        )
    return snap
