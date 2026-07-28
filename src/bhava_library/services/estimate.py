"""Size estimation and batch planning."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from uuid import uuid4

from bhava_library.config import Settings
from bhava_library.constants import GIB
from bhava_library.domain.enums import AcquisitionProfile, ResourceStatus
from bhava_library.domain.models import EstimateSummary, RemoteProbe
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.infrastructure.disk_guard import (
    compute_overhead_bytes,
    compute_reserve_bytes,
    disk_usage,
)
from bhava_library.infrastructure.filesystem import ensure_dirs
from bhava_library.infrastructure.http import PoliteHttpClient
from bhava_library.infrastructure.mime import is_audio_mime, is_video_mime
from bhava_library.logging import get_logger
from bhava_library.services.schedule import build_batches, rank_resources

logger = get_logger("bhava.estimate")


def _parse_content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        length = int(value.strip())
    except ValueError:
        return None
    return length if length >= 0 else None


def probe_url(client: PoliteHttpClient, resource_id: str, url: str) -> RemoteProbe:
    now = datetime.now(UTC)
    try:
        head = client.head(url)
        length = _parse_content_length(head.headers.get("content-length"))
        accept = "bytes" in (head.headers.get("accept-ranges") or "").lower()
        mime = (head.headers.get("content-type") or "").split(";")[0].strip() or None
        if length is not None:
            return RemoteProbe(
                resource_id=resource_id,
                url=url,
                final_url=str(head.url),
                http_status=head.status_code,
                mime_type=mime,
                content_length=length,
                accept_ranges=accept,
                etag=head.headers.get("etag"),
                last_modified=head.headers.get("last-modified"),
                probed_at=now,
                size_known=True,
            )
        # Range fallback
        ranged = client.get_range(url, 0, 0)
        content_range = ranged.headers.get("content-range", "")
        # bytes 0-0/12345
        total = None
        if "/" in content_range:
            tail = content_range.rsplit("/", 1)[-1]
            if tail.isdigit():
                total = int(tail)
        mime = (ranged.headers.get("content-type") or mime or "").split(";")[0].strip() or None
        return RemoteProbe(
            resource_id=resource_id,
            url=url,
            final_url=str(ranged.url),
            http_status=ranged.status_code,
            mime_type=mime,
            content_length=total,
            accept_ranges=True if total is not None else accept,
            etag=ranged.headers.get("etag") or head.headers.get("etag"),
            last_modified=ranged.headers.get("last-modified") or head.headers.get("last-modified"),
            probed_at=now,
            size_known=total is not None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Probe failed for %s: %s", resource_id, exc)
        return RemoteProbe(
            resource_id=resource_id,
            url=url,
            probed_at=now,
            size_known=False,
        )


def run_estimate(
    settings: Settings,
    *,
    profile: str = "core",
    client: PoliteHttpClient | None = None,
    probe: bool = True,
) -> EstimateSummary:
    ensure_dirs(settings.reports_dir)
    db = Database(settings.catalog_db)
    db.migrate()

    with db.session() as conn:
        rows = list(
            conn.execute(
                """
                SELECT * FROM resources
                WHERE removed_at IS NULL
                ORDER BY priority ASC, resource_id ASC
                """
            )
        )

    deferred_audio = [r for r in rows if (r["profile"] or "") == "audio"]
    deferred_video = [r for r in rows if (r["profile"] or "") == "video"]

    if profile == "core":
        candidates = [
            r
            for r in rows
            if (r["profile"] or "") in {"core", "unknown", "metadata"}
            and (r["profile"] or "") not in {"audio", "video"}
        ]
        # Extra safety: exclude by format text
        candidates = [
            r
            for r in candidates
            if "audio" not in (r["media_format"] or "").lower()
            and "video" not in (r["media_format"] or "").lower()
            and (r["profile"] or "") != "audio"
            and (r["profile"] or "") != "video"
        ]
    elif profile == "audio":
        candidates = deferred_audio
    elif profile == "video":
        candidates = deferred_video
    else:
        candidates = list(rows)

    resolved = [r for r in candidates if r["resolved_url"] or r["status"] == "resolved"]
    unresolved = [r for r in candidates if r["status"] in {"unresolved", "discovered"}]
    broken = [r for r in candidates if r["status"] == "inaccessible"]

    own = client is None
    probe_delay = min(settings.source_iskcon.request_delay_seconds, 0.5)
    http = client or PoliteHttpClient(
        user_agent=settings.source_iskcon.user_agent,
        request_delay_seconds=probe_delay,
        verify_tls=settings.download.verify_tls,
    )
    probes: list[RemoteProbe] = []
    try:
        if probe:
            for row in resolved:
                url = row["resolved_url"] or row["original_url"]
                if not url or url.startswith("urn:"):
                    continue
                result = probe_url(http, row["resource_id"], url)
                # Reclassify audio/video discovered via MIME
                if is_audio_mime(result.mime_type):
                    with db.session() as conn:
                        conn.execute(
                            "UPDATE resources SET profile=? WHERE resource_id=?",
                            (AcquisitionProfile.AUDIO.value, row["resource_id"]),
                        )
                    if profile == "core":
                        continue
                if is_video_mime(result.mime_type):
                    with db.session() as conn:
                        conn.execute(
                            "UPDATE resources SET profile=? WHERE resource_id=?",
                            (AcquisitionProfile.VIDEO.value, row["resource_id"]),
                        )
                    if profile == "core":
                        continue
                probes.append(result)
                with db.session() as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO remote_objects(
                          remote_object_id, resource_id, url, final_url, http_status,
                          mime_type, content_length, accept_ranges, etag, last_modified, probed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"ro-{row['resource_id']}",
                            row["resource_id"],
                            result.url,
                            result.final_url,
                            result.http_status,
                            result.mime_type,
                            result.content_length,
                            1 if result.accept_ranges else 0,
                            result.etag,
                            result.last_modified,
                            (result.probed_at or datetime.now(UTC)).isoformat(),
                        ),
                    )
                    status = (
                        ResourceStatus.ESTIMATED
                        if result.size_known
                        else ResourceStatus.SIZE_UNKNOWN
                    )
                    conn.execute(
                        "UPDATE resources SET status=?, last_seen_at=? WHERE resource_id=?",
                        (status.value, utc_now(), row["resource_id"]),
                    )
    finally:
        if own:
            http.close()

    known_bytes = sum(p.content_length or 0 for p in probes if p.size_known)
    unknown_count = sum(1 for p in probes if not p.size_known)

    # Size map for scheduling
    size_by_id = {p.resource_id: p.content_length for p in probes}
    ranked = rank_resources(candidates, size_by_id)
    # Filter core again after mime reclass — reload profiles
    if profile == "core":
        with db.session() as conn:
            core_ids = {
                r["resource_id"]
                for r in conn.execute(
                    "SELECT resource_id FROM resources WHERE profile IN ('core','unknown') AND removed_at IS NULL"
                )
            }
        ranked = [r for r in ranked if r["resource_id"] in core_ids]

    cap = int(settings.download.initial_batch_cap_gib * GIB)
    max_file = int(settings.download.max_file_gib * GIB)
    batches = build_batches(ranked, size_by_id, cap_bytes=cap, max_file_bytes=max_file)
    first = batches[0] if batches else []
    first_bytes = sum(size_by_id.get(r["resource_id"]) or 0 for r in first)

    snap = disk_usage(settings.data_dir if settings.data_dir.exists() else settings.repo_root)
    reserve = compute_reserve_bytes(
        snap.total_bytes, settings.download.reserve_gib, settings.download.reserve_percent
    )
    overhead = compute_overhead_bytes(
        first_bytes,
        settings.download.temporary_overhead_percent,
        settings.download.temporary_overhead_gib,
    )
    projected = snap.free_bytes - first_bytes - overhead
    safe = projected >= reserve and len(first) > 0

    # Persist batch assignments as pending jobs for first batch
    batch_id = f"batch-{profile}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:6]}"
    with db.session() as conn:
        for row in first:
            rid = row["resource_id"]
            url = row["resolved_url"] or row["original_url"]
            expected = size_by_id.get(rid)
            job_id = f"job-{rid}"
            existing = conn.execute(
                "SELECT job_id FROM download_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT INTO download_jobs(
                  job_id, resource_id, batch_id, state, attempt_count,
                  bytes_downloaded, expected_bytes, updated_at
                ) VALUES (?, ?, ?, 'pending', 0, 0, ?, ?)
                """,
                (job_id, rid, batch_id, expected, utc_now()),
            )
            conn.execute(
                "UPDATE resources SET status=?, last_seen_at=? WHERE resource_id=? AND status IN ('estimated','size_unknown','resolved')",
                (ResourceStatus.QUEUED.value, utc_now(), rid),
            )

    summary = EstimateSummary(
        profile=profile,
        total_candidates=len(candidates),
        resolved=len(resolved),
        unresolved=len(unresolved),
        broken=len(broken),
        known_bytes=known_bytes,
        unknown_size_count=unknown_count,
        deferred_audio=len(deferred_audio),
        deferred_video=len(deferred_video),
        free_disk_bytes=snap.free_bytes,
        reserve_bytes=reserve,
        overhead_bytes=overhead,
        projected_free_bytes=projected,
        batch_cap_bytes=cap,
        first_batch_bytes=first_bytes,
        first_batch_count=len(first),
        pending_batch_count=max(0, len(batches) - 1),
        safe_to_acquire=safe,
        notes=[
            f"batch_id={batch_id}",
            f"batches_total={len(batches)}",
            f"max_file_bytes={max_file}",
        ],
    )

    _write_reports(settings, summary, probes, batches)
    db.add_event("estimate", payload_json=summary.model_dump_json())
    return summary


def _write_reports(
    settings: Settings,
    summary: EstimateSummary,
    probes: list[RemoteProbe],
    batches: list[list],
) -> None:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = settings.reports_dir / f"estimate-{summary.profile}-{stamp}"
    ensure_dirs(settings.reports_dir)
    (base.with_suffix(".json")).write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    md = [
        f"# Estimate report — profile `{summary.profile}`",
        "",
        f"- Candidates: {summary.total_candidates}",
        f"- Resolved / unresolved / broken: {summary.resolved} / {summary.unresolved} / {summary.broken}",
        f"- Known bytes: {summary.known_bytes / GIB:.3f} GiB",
        f"- Unknown size count: {summary.unknown_size_count}",
        f"- Deferred audio/video: {summary.deferred_audio} / {summary.deferred_video}",
        f"- Free disk: {summary.free_disk_bytes / GIB:.2f} GiB",
        f"- Reserve: {summary.reserve_bytes / GIB:.2f} GiB",
        f"- First batch: {summary.first_batch_count} files / {summary.first_batch_bytes / GIB:.3f} GiB",
        f"- Pending batches: {summary.pending_batch_count}",
        f"- Safe to acquire: {summary.safe_to_acquire}",
        "",
    ]
    (base.with_suffix(".md")).write_text("\n".join(md), encoding="utf-8")
    with base.with_suffix(".csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["resource_id", "url", "content_length", "mime_type", "size_known", "http_status"]
        )
        for p in probes:
            writer.writerow(
                [
                    p.resource_id,
                    p.final_url or p.url,
                    p.content_length,
                    p.mime_type,
                    p.size_known,
                    p.http_status,
                ]
            )
    # batch overview
    batch_path = settings.reports_dir / f"batches-{summary.profile}-{stamp}.json"
    batch_path.write_text(
        json.dumps(
            [
                {
                    "index": i,
                    "count": len(batch),
                    "resource_ids": [r["resource_id"] for r in batch],
                }
                for i, batch in enumerate(batches)
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
