"""Disk guard unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.domain.errors import DiskGuardError
from bhava_library.infrastructure.disk_guard import (
    assert_safe_to_start,
    compute_overhead_bytes,
    compute_reserve_bytes,
)


def test_reserve_is_max_of_fixed_and_percent() -> None:
    total = 1000
    assert compute_reserve_bytes(total, reserve_gib=0.0000001, reserve_percent=50) == 500


def test_overhead() -> None:
    assert compute_overhead_bytes(1000, 10, 0) == 100


def test_assert_safe_fails_when_projected_below_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Fake:
        total = 100 * 1024**3
        used = 10 * 1024**3
        free = 60 * 1024**3

    monkeypatch.setattr(
        "bhava_library.infrastructure.disk_guard.shutil.disk_usage",
        lambda path: Fake(),
    )
    with pytest.raises(DiskGuardError):
        assert_safe_to_start(
            data_dir=tmp_path,
            planned_bytes=20 * 1024**3,
            known_queue_bytes=20 * 1024**3,
            reserve_gib=50,
            reserve_percent=15,
            overhead_percent=10,
            overhead_gib=2,
        )
