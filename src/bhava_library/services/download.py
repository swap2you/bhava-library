"""Resumable streaming downloader."""

from __future__ import annotations

import json
import signal
import threading
from pathlib import Path
from urllib.parse import urlparse

from bhava_library.config import Settings
from bhava_library.constants import (
    DISK_CHECK_EVERY_MIB,
    EXIT_DISK_GUARD_PAUSE,
    EXIT_PARTIAL,
    EXIT_SUCCESS,
    GIB,
    MIB,
)
from bhava_library.domain.enums import JobState, ResourceStatus
from bhava_library.domain.errors import DiskGuardError
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.infrastructure.disk_guard import (
    assert_safe_during_transfer,
    assert_safe_to_start,
)
from bhava_library.infrastructure.filesystem import (
    atomic_rename,
    ensure_dirs,
    sanitize_filename,
)
from bhava_library.infrastructure.hashing import sha256_file
from bhava_library.infrastructure.http import PoliteHttpClient
from bhava_library.infrastructure.mime import extension_of
from bhava_library.logging import get_logger
from bhava_library.services.verify import verify_local_file

logger = get_logger("bhava.download")

_shutdown = threading.Event()


def _install_signal_handlers() -> None:
    def _handler(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.warning("Shutdown requested; finishing current chunk then pausing")
        _shutdown.set()

    try:
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        # Not in main thread
        pass


def _category_dir(settings: Settings, profile: str, ext: str) -> Path:
    base = settings.originals_dir
    if ext in {".pdf", ".epub", ".txt", ".rtf", ".html", ".htm"}:
        return base / "documents"
    if ext in {".doc", ".docx", ".odt", ".ppt", ".pptx", ".odp", ".xls", ".xlsx", ".ods", ".csv"}:
        return base / "office"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return base / "images"
    if ext in {".zip", ".rar", ".7z"}:
        return base / "archives"
    if profile == "audio" or ext in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
        return base / "audio"
    if profile == "video" or ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        return base / "video"
    return base / "unknown"


def _sidecar_path(part_path: Path) -> Path:
    return part_path.with_suffix(part_path.suffix + ".state.json")


def download_one(
    settings: Settings,
    *,
    job: dict,
    resource: dict,
    client: PoliteHttpClient,
    host_locks: dict[str, threading.Lock],
    host_locks_guard: threading.Lock,
) -> str:
    """Download a single job. Returns status token."""
    if _shutdown.is_set():
        return "paused"

    db = Database(settings.catalog_db)
    rid = resource["resource_id"]
    url = resource["resolved_url"] or resource["original_url"]
    if not url or url.startswith("urn:"):
        return "terminal"

    host = urlparse(url).netloc.lower()
    with host_locks_guard:
        lock = host_locks.setdefault(host, threading.Lock())

    expected = job.get("expected_bytes")
    ext = extension_of(url) or ".bin"
    filename = sanitize_filename(
        f"{rid}_{Path(urlparse(url).path).name or 'file'}{ext if not Path(urlparse(url).path).suffix else ''}"
    )
    # Avoid double extensions
    if not filename.lower().endswith(ext.lower()) and ext != ".bin":
        filename = sanitize_filename(f"{rid}_{Path(urlparse(url).path).stem}{ext}")

    dest_dir = _category_dir(settings, resource.get("profile") or "core", ext)
    ensure_dirs(dest_dir, settings.staging_dir)
    final_path = dest_dir / filename
    if final_path.exists():
        logger.info("Skip existing %s", final_path)
        with db.session() as conn:
            conn.execute(
                "UPDATE download_jobs SET state=?, completed_at=?, updated_at=? WHERE job_id=?",
                (JobState.COMPLETE.value, utc_now(), utc_now(), job["job_id"]),
            )
            conn.execute(
                "UPDATE resources SET status=? WHERE resource_id=?",
                (ResourceStatus.DOWNLOADED.value, rid),
            )
        verify_local_file(settings, resource_id=rid, path=final_path, expected_bytes=expected)
        return "exists"

    part_path = settings.staging_dir / f"{rid}.part"
    state_path = _sidecar_path(part_path)
    bytes_have = part_path.stat().st_size if part_path.exists() else 0
    state: dict = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    max_file = int(settings.download.max_file_gib * GIB)
    if expected and expected > max_file:
        with db.session() as conn:
            conn.execute(
                "UPDATE download_jobs SET state=?, last_error_code=?, last_error_message=?, updated_at=? WHERE job_id=?",
                (
                    JobState.TERMINAL_FAILURE.value,
                    "FILE_TOO_LARGE",
                    f"expected {expected} > max {max_file}",
                    utc_now(),
                    job["job_id"],
                ),
            )
        return "terminal"

    with lock:
        try:
            assert_safe_during_transfer(
                data_dir=settings.data_dir,
                reserve_gib=settings.download.reserve_gib,
                reserve_percent=settings.download.reserve_percent,
            )
        except DiskGuardError:
            with db.session() as conn:
                conn.execute(
                    "UPDATE download_jobs SET state=?, updated_at=? WHERE job_id=?",
                    (JobState.PAUSED.value, utc_now(), job["job_id"]),
                )
                conn.execute(
                    "UPDATE resources SET status=? WHERE resource_id=?",
                    (ResourceStatus.PAUSED.value, rid),
                )
            raise

        headers: dict[str, str] = {}
        if bytes_have > 0 and settings.download.resume:
            headers["Range"] = f"bytes={bytes_have}-"
            if state.get("etag"):
                headers["If-Range"] = state["etag"]

        with db.session() as conn:
            conn.execute(
                "UPDATE download_jobs SET state=?, part_path=?, started_at=COALESCE(started_at, ?), updated_at=?, attempt_count=attempt_count+1 WHERE job_id=?",
                (JobState.ACTIVE.value, str(part_path), utc_now(), utc_now(), job["job_id"]),
            )
            conn.execute(
                "UPDATE resources SET status=? WHERE resource_id=?",
                (ResourceStatus.DOWNLOADING.value, rid),
            )

        response = client.stream_get(url, headers=headers)
        try:
            if response.status_code == 404:
                with db.session() as conn:
                    conn.execute(
                        "UPDATE download_jobs SET state=?, last_error_code=?, last_error_message=?, updated_at=? WHERE job_id=?",
                        (
                            JobState.TERMINAL_FAILURE.value,
                            "HTTP_404",
                            "Not found",
                            utc_now(),
                            job["job_id"],
                        ),
                    )
                    conn.execute(
                        "UPDATE resources SET status=? WHERE resource_id=?",
                        (ResourceStatus.FAILED_TERMINAL.value, rid),
                    )
                return "terminal"

            # If server ignored Range, restart
            if bytes_have > 0 and response.status_code == 200:
                bytes_have = 0
                part_path.unlink(missing_ok=True)

            etag = response.headers.get("etag")
            last_modified = response.headers.get("last-modified")
            mode = "ab" if bytes_have > 0 and response.status_code == 206 else "wb"
            if mode == "wb":
                bytes_have = 0

            since_check = 0
            with part_path.open(mode) as fh:
                for chunk in response.iter_bytes(chunk_size=int(settings.download.chunk_mib * MIB)):
                    if _shutdown.is_set():
                        break
                    fh.write(chunk)
                    bytes_have += len(chunk)
                    since_check += len(chunk)
                    if since_check >= DISK_CHECK_EVERY_MIB * MIB:
                        since_check = 0
                        assert_safe_during_transfer(
                            data_dir=settings.data_dir,
                            reserve_gib=settings.download.reserve_gib,
                            reserve_percent=settings.download.reserve_percent,
                        )
                    state = {
                        "resource_id": rid,
                        "url": url,
                        "etag": etag,
                        "last_modified": last_modified,
                        "bytes_downloaded": bytes_have,
                        "expected_bytes": expected,
                    }
                    state_path.write_text(json.dumps(state), encoding="utf-8")
                    with db.session() as conn:
                        conn.execute(
                            "UPDATE download_jobs SET bytes_downloaded=?, updated_at=? WHERE job_id=?",
                            (bytes_have, utc_now(), job["job_id"]),
                        )
        finally:
            response.close()

        if _shutdown.is_set():
            with db.session() as conn:
                conn.execute(
                    "UPDATE download_jobs SET state=?, updated_at=? WHERE job_id=?",
                    (JobState.PAUSED.value, utc_now(), job["job_id"]),
                )
                conn.execute(
                    "UPDATE resources SET status=? WHERE resource_id=?",
                    (ResourceStatus.PAUSED.value, rid),
                )
            return "paused"

        if bytes_have == 0:
            with db.session() as conn:
                conn.execute(
                    "UPDATE download_jobs SET state=?, last_error_code=?, last_error_message=?, updated_at=? WHERE job_id=?",
                    (
                        JobState.TERMINAL_FAILURE.value,
                        "EMPTY_REMOTE",
                        "remote body empty (Content-Length 0 or empty GET)",
                        utc_now(),
                        job["job_id"],
                    ),
                )
                conn.execute(
                    "UPDATE resources SET status=? WHERE resource_id=?",
                    (ResourceStatus.FAILED_TERMINAL.value, rid),
                )
            part_path.unlink(missing_ok=True)
            state_path.unlink(missing_ok=True)
            return "terminal"

        if expected is not None and bytes_have != expected:
            # Allow if server omitted length and we finished cleanly — only fail if Content-Length known mismatch
            cl = expected
            if cl and bytes_have != cl:
                with db.session() as conn:
                    conn.execute(
                        "UPDATE download_jobs SET state=?, last_error_code=?, last_error_message=?, updated_at=? WHERE job_id=?",
                        (
                            JobState.RETRYABLE.value,
                            "LENGTH_MISMATCH",
                            f"have={bytes_have} expected={expected}",
                            utc_now(),
                            job["job_id"],
                        ),
                    )
                return "retryable"

        # Atomic finalize
        if final_path.exists():
            raise FileExistsError(final_path)
        atomic_rename(part_path, final_path)
        state_path.unlink(missing_ok=True)
        digest = sha256_file(final_path)
        with db.session() as conn:
            conn.execute(
                "UPDATE download_jobs SET state=?, bytes_downloaded=?, completed_at=?, updated_at=? WHERE job_id=?",
                (JobState.COMPLETE.value, bytes_have, utc_now(), utc_now(), job["job_id"]),
            )
            conn.execute(
                "UPDATE resources SET status=? WHERE resource_id=?",
                (ResourceStatus.DOWNLOADED.value, rid),
            )
        verify_local_file(
            settings,
            resource_id=rid,
            path=final_path,
            expected_bytes=expected,
            precomputed_sha256=digest,
        )
        logger.info("Downloaded %s (%s bytes) sha256=%s", rid, bytes_have, digest[:12])
        return "complete"


def run_acquire(settings: Settings, *, profile: str = "core") -> int:
    """Acquire queued jobs for profile. Returns process exit code."""
    _shutdown.clear()
    _install_signal_handlers()
    db = Database(settings.catalog_db)
    db.migrate()
    ensure_dirs(settings.staging_dir, settings.originals_dir)

    with db.session() as conn:
        jobs = list(
            conn.execute(
                """
                SELECT j.*, r.resolved_url, r.original_url, r.profile, r.title_original, r.resource_id AS rid
                FROM download_jobs j
                JOIN resources r ON r.resource_id = j.resource_id
                WHERE j.state IN ('pending','retryable','paused','active')
                  AND r.removed_at IS NULL
                  AND (? = 'all' OR r.profile = ? OR ( ? = 'core' AND r.profile IN ('core','unknown')))
                ORDER BY r.priority ASC, j.job_id ASC
                """,
                (profile, profile, profile),
            )
        )

    # Exclude audio/video hard for core
    if profile == "core":
        jobs = [j for j in jobs if (j["profile"] or "") not in {"audio", "video"}]

    known = sum(j["expected_bytes"] or 0 for j in jobs)
    try:
        assert_safe_to_start(
            data_dir=settings.data_dir,
            planned_bytes=min(known, int(settings.download.initial_batch_cap_gib * GIB)),
            known_queue_bytes=known,
            reserve_gib=settings.download.reserve_gib,
            reserve_percent=settings.download.reserve_percent,
            overhead_percent=settings.download.temporary_overhead_percent,
            overhead_gib=settings.download.temporary_overhead_gib,
        )
    except DiskGuardError as exc:
        logger.error("%s", exc)
        db.add_event("disk_guard_pause", payload_json=json.dumps({"error": str(exc)}))
        return EXIT_DISK_GUARD_PAUSE

    host_locks: dict[str, threading.Lock] = {}
    host_locks_guard = threading.Lock()
    results: list[str] = []

    # Unknown-size concurrency = 1; known sizes also run serially because nearly all
    # URLs share one host and httpx streaming clients are not thread-safe.
    unknown_jobs = [j for j in jobs if not j["expected_bytes"]]
    known_jobs = [j for j in jobs if j["expected_bytes"]]

    def _run_one(job_row: dict, client: PoliteHttpClient) -> str:
        resource = {
            "resource_id": job_row["resource_id"],
            "resolved_url": job_row["resolved_url"],
            "original_url": job_row["original_url"],
            "profile": job_row["profile"],
            "title_original": job_row["title_original"],
        }
        job = {
            "job_id": job_row["job_id"],
            "expected_bytes": job_row["expected_bytes"],
        }
        try:
            return download_one(
                settings,
                job=job,
                resource=resource,
                client=client,
                host_locks=host_locks,
                host_locks_guard=host_locks_guard,
            )
        except DiskGuardError as exc:
            logger.error("%s", exc)
            return "disk_pause"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Download failed for %s: %s", job_row["resource_id"], exc)
            with db.session() as conn:
                conn.execute(
                    "UPDATE download_jobs SET state=?, last_error_message=?, updated_at=? WHERE job_id=?",
                    (JobState.RETRYABLE.value, str(exc)[:500], utc_now(), job_row["job_id"]),
                )
            return "retryable"

    with PoliteHttpClient(
        user_agent=settings.source_iskcon.user_agent,
        request_delay_seconds=settings.source_iskcon.request_delay_seconds,
        verify_tls=settings.download.verify_tls,
        timeout=120.0,
    ) as client:
        for job_row in list(unknown_jobs) + list(known_jobs):
            if _shutdown.is_set():
                break
            status = _run_one(dict(job_row), client)
            results.append(status)
            if status == "disk_pause":
                db.add_event(
                    "acquire",
                    payload_json=json.dumps({"results": results, "profile": profile}),
                )
                return EXIT_DISK_GUARD_PAUSE

    db.add_event("acquire", payload_json=json.dumps({"results": results, "profile": profile}))
    if any(r == "paused" for r in results) or _shutdown.is_set():
        return EXIT_PARTIAL
    if any(r in {"retryable", "terminal"} for r in results) and any(
        r in {"complete", "exists"} for r in results
    ):
        return EXIT_PARTIAL
    return EXIT_SUCCESS


def run_resume(settings: Settings) -> int:
    return run_acquire(settings, profile="core")
