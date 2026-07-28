"""Deterministic download scheduling."""

from __future__ import annotations

from typing import Any


def rank_resources(
    rows: list[Any],
    size_by_id: dict[str, int | None],
) -> list[Any]:
    """Sort by priority ascending, then known smaller sizes first, then id."""

    def key(row: Any) -> tuple[int, int, int, str]:
        rid = row["resource_id"]
        size = size_by_id.get(rid)
        size_key = size if size is not None else 2**62
        unknown_flag = 0 if size is not None else 1
        return (int(row["priority"] or 100), unknown_flag, size_key, rid)

    return sorted(rows, key=key)


def build_batches(
    ranked: list[Any],
    size_by_id: dict[str, int | None],
    *,
    cap_bytes: int,
    max_file_bytes: int,
) -> list[list[Any]]:
    """Partition into deterministic batches respecting cap and max file size."""
    batches: list[list[Any]] = []
    current: list[Any] = []
    current_bytes = 0
    for row in ranked:
        rid = row["resource_id"]
        size = size_by_id.get(rid)
        if size is not None and size > max_file_bytes:
            # Skip oversized files into their own deferred note batch later
            continue
        add = size or 0
        if current and current_bytes + add > cap_bytes:
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(row)
        current_bytes += add
    if current:
        batches.append(current)
    return batches
