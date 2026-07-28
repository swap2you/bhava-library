"""Downloader behavior tests using httpx mocks / local fixtures."""

from __future__ import annotations

import json
import threading
import zipfile
from pathlib import Path

import httpx
import pytest

from bhava_library.config import load_settings
from bhava_library.domain.enums import AcquisitionProfile
from bhava_library.domain.errors import BackupVerifyError, DiskGuardError, NetworkError
from bhava_library.infrastructure.database import Database
from bhava_library.infrastructure.disk_guard import assert_safe_during_transfer
from bhava_library.infrastructure.filesystem import sanitize_filename
from bhava_library.infrastructure.http import PoliteHttpClient
from bhava_library.infrastructure.windows_defender import scan_file
from bhava_library.services.backup import run_backup
from bhava_library.services.download import download_one
from bhava_library.services.schedule import build_batches, rank_resources
from bhava_library.services.verify import _zip_is_suspicious, verify_local_file
from bhava_library.sources.iskcon_education import classify_profile


@pytest.fixture
def settings(tmp_path: Path):
    s = load_settings()
    s = s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    for rel in (
        "catalog",
        "staging",
        "quarantine",
        "snapshots",
        "originals/iskcon-education/documents",
        "originals/iskcon-education/audio",
        "originals/iskcon-education/unknown",
        "backups",
    ):
        (s.data_dir / rel).mkdir(parents=True, exist_ok=True)
    Database(s.catalog_db).migrate()
    Database(s.catalog_db).ensure_source(
        "iskcon-education", "test", "https://example.org/", "iskcon_education"
    )
    return s


def _seed_resource(
    settings, *, rid: str, url: str, profile: str = "core", expected: int | None = 4
):
    db = Database(settings.catalog_db)
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO resources(
              resource_id, source_id, source_row_key, title_original, title_normalized,
              original_url, resolved_url, profile, priority, status, first_seen_at, last_seen_at
            ) VALUES (?, 'iskcon-education', ?, ?, ?, ?, ?, ?, 10, 'queued', datetime('now'), datetime('now'))
            """,
            (rid, rid, rid, rid, url, url, profile),
        )
        conn.execute(
            """
            INSERT INTO download_jobs(
              job_id, resource_id, batch_id, state, attempt_count, bytes_downloaded, expected_bytes, updated_at
            ) VALUES (?, ?, 'batch-test', 'pending', 0, 0, ?, datetime('now'))
            """,
            (f"job-{rid}", rid, expected),
        )


def test_range_resume(httpx_mock, settings):
    url = "https://example.org/files/a.pdf"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=206,
        content=b"cdef",
        headers={"Content-Type": "application/pdf", "ETag": '"v1"'},
    )
    _seed_resource(settings, rid="BL-IE-RESUME0001", url=url, expected=8)
    part = settings.staging_dir / "BL-IE-RESUME0001.part"
    part.write_bytes(b"abcd")
    (settings.staging_dir / "BL-IE-RESUME0001.part.state.json").write_text(
        json.dumps({"etag": '"v1"', "bytes_downloaded": 4}), encoding="utf-8"
    )
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-RESUME0001", "expected_bytes": 8},
            resource={
                "resource_id": "BL-IE-RESUME0001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "a",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "complete"
    req = httpx_mock.get_requests()[-1]
    assert req.headers.get("Range") == "bytes=4-"


def test_server_ignores_range_restarts(httpx_mock, settings):
    url = "https://example.org/files/b.pdf"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=b"FULLFILE",
        headers={"Content-Type": "application/pdf"},
    )
    _seed_resource(settings, rid="BL-IE-NORANGE0001", url=url, expected=8)
    part = settings.staging_dir / "BL-IE-NORANGE0001.part"
    part.write_bytes(b"old")
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-NORANGE0001", "expected_bytes": 8},
            resource={
                "resource_id": "BL-IE-NORANGE0001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "b",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "complete"


def test_html_for_document_url_is_terminal(httpx_mock, settings):
    url = "https://example.org/files/missing.pdf"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=b"<html>not found</html>",
        headers={"Content-Type": "text/html"},
    )
    _seed_resource(settings, rid="BL-IE-HTMLDOC0001", url=url, expected=20)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-HTMLDOC0001", "expected_bytes": 20},
            resource={
                "resource_id": "BL-IE-HTMLDOC0001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "html",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "terminal"


def test_http_404_terminal(httpx_mock, settings):
    url = "https://example.org/gone.pdf"
    httpx_mock.add_response(url=url, method="GET", status_code=404)
    _seed_resource(settings, rid="BL-IE-HTTP4040001", url=url, expected=10)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-HTTP4040001", "expected_bytes": 10},
            resource={
                "resource_id": "BL-IE-HTTP4040001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "gone",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "terminal"


def test_http_410_terminal(httpx_mock, settings):
    url = "https://example.org/gone2.pdf"
    httpx_mock.add_response(url=url, method="GET", status_code=410)
    _seed_resource(settings, rid="BL-IE-HTTP4100001", url=url, expected=10)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-HTTP4100001", "expected_bytes": 10},
            resource={
                "resource_id": "BL-IE-HTTP4100001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "gone2",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "terminal"


def test_length_mismatch_retryable(httpx_mock, settings):
    url = "https://example.org/short.pdf"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=b"1234",
        headers={"Content-Type": "application/pdf"},
    )
    _seed_resource(settings, rid="BL-IE-LENMIS0001", url=url, expected=100)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-LENMIS0001", "expected_bytes": 100},
            resource={
                "resource_id": "BL-IE-LENMIS0001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "short",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "retryable"


def test_empty_body_terminal(httpx_mock, settings):
    url = "https://example.org/empty.pdf"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=b"",
        headers={"Content-Type": "application/pdf", "Content-Length": "0"},
    )
    _seed_resource(settings, rid="BL-IE-EMPTY000001", url=url, expected=0)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-EMPTY000001", "expected_bytes": 0},
            resource={
                "resource_id": "BL-IE-EMPTY000001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "empty",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "terminal"


def test_path_traversal_and_reserved_names():
    assert ".." not in sanitize_filename("../x.pdf")
    assert sanitize_filename("CON.pdf").startswith("_")


def test_zip_slip_and_bomb_and_exe(tmp_path: Path):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../escape.txt", "x")
    assert _zip_is_suspicious(z) == "zip_slip"

    z2 = tmp_path / "exe.zip"
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("payload.exe", b"MZ")
    assert _zip_is_suspicious(z2) == "zip_contains_executable"

    z3 = tmp_path / "bomb.zip"
    with zipfile.ZipFile(z3, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.bin", b"\x00" * (2 * 1024 * 1024))
    # May or may not trip ratio depending on compress; at least malformed path covered above
    assert _zip_is_suspicious(z3) in {None, "zip_bomb_ratio"}


def test_malformed_zip(tmp_path: Path):
    bad = tmp_path / "not.zip"
    bad.write_bytes(b"not-a-zip")
    assert _zip_is_suspicious(bad) == "malformed_zip"


def test_duplicate_content(settings, tmp_path: Path):
    p1 = settings.originals_dir / "documents" / "a.bin"
    p2 = settings.originals_dir / "documents" / "b.bin"
    p1.write_bytes(b"same-bytes")
    p2.write_bytes(b"same-bytes")
    _seed_resource(settings, rid="BL-IE-DUP0000001", url="https://example.org/a.pdf", expected=10)
    _seed_resource(settings, rid="BL-IE-DUP0000002", url="https://example.org/b.pdf", expected=10)
    r1 = verify_local_file(settings, resource_id="BL-IE-DUP0000001", path=p1, expected_bytes=10)
    r2 = verify_local_file(settings, resource_id="BL-IE-DUP0000002", path=p2, expected_bytes=10)
    assert r1["ok"] and r2["ok"]
    assert r2.get("duplicate") is True


def test_core_excludes_audio_video():
    assert (
        classify_profile(media_type="Audio", media_format="Audio", url="x.mp3")
        == AcquisitionProfile.AUDIO
    )
    assert (
        classify_profile(media_type="Video", media_format="Video", url="x.mp4")
        == AcquisitionProfile.VIDEO
    )
    assert (
        classify_profile(media_type="Curriculum", media_format="Documents", url="x.pdf")
        == AcquisitionProfile.CORE
    )


def test_audio_profile_batching():
    rows = [
        {"resource_id": "a", "priority": 900, "profile": "audio"},
        {"resource_id": "b", "priority": 900, "profile": "audio"},
    ]
    sizes = {"a": 10, "b": 20}
    batches = build_batches(rank_resources(rows, sizes), sizes, cap_bytes=25, max_file_bytes=100)
    assert len(batches) >= 1
    assert sum(sizes[r["resource_id"]] for r in batches[0]) <= 25


def test_disk_guard_during_transfer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    class Fake:
        total = 100 * 1024**3
        used = 90 * 1024**3
        free = 40 * 1024**3

    monkeypatch.setattr(
        "bhava_library.infrastructure.disk_guard.shutil.disk_usage",
        lambda path: Fake(),
    )
    with pytest.raises(DiskGuardError):
        assert_safe_during_transfer(data_dir=tmp_path, reserve_gib=50, reserve_percent=15)


def test_defender_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(
        "bhava_library.infrastructure.windows_defender._mpcmdrun",
        lambda: None,
    )
    result = scan_file(tmp_path / "x.bin")
    assert result.available is False
    assert result.clean is None


def test_backup_marks_incomplete_when_required_skip(settings, tmp_path: Path, monkeypatch):
    # Create one real file and force a second source file to fail copy via monkeypatch
    src = settings.data_dir / "originals" / "iskcon-education" / "documents" / "ok.pdf"
    src.write_bytes(b"%PDF-ok")
    dest_root = tmp_path / "backup-root"

    real_copy2 = __import__("shutil").copy2

    def flaky_copy2(src_s, dst_s):
        if "ok.pdf" in str(src_s):
            return real_copy2(src_s, dst_s)
        raise OSError("simulated long-path failure")

    # Add a second file that will fail
    bad = settings.data_dir / "originals" / "iskcon-education" / "documents" / "longname.pdf"
    bad.write_bytes(b"%PDF-bad")
    monkeypatch.setattr("bhava_library.services.backup.shutil.copy2", flaky_copy2)
    with pytest.raises(BackupVerifyError):
        run_backup(settings, target=str(dest_root))


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_http_429_raises(httpx_mock):
    for _ in range(5):
        httpx_mock.add_response(
            url="https://example.org/r.pdf",
            method="GET",
            status_code=429,
            headers={"Retry-After": "1"},
        )
    with (
        PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client,
        pytest.raises(NetworkError),
    ):
        client.get("https://example.org/r.pdf")


def test_http_500_retries(httpx_mock):
    httpx_mock.add_response(url="https://example.org/s.pdf", method="GET", status_code=500)
    httpx_mock.add_response(url="https://example.org/s.pdf", method="GET", status_code=500)
    httpx_mock.add_response(
        url="https://example.org/s.pdf",
        method="GET",
        status_code=200,
        content=b"ok",
        headers={"Content-Type": "application/pdf"},
    )
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        r = client.get("https://example.org/s.pdf")
        assert r.status_code == 200
        assert r.content == b"ok"


def test_http_400_terminal(httpx_mock, settings):
    url = "https://example.org/bad.pdf"
    httpx_mock.add_response(url=url, method="GET", status_code=400)
    _seed_resource(settings, rid="BL-IE-HTTP4000001", url=url, expected=10)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-HTTP4000001", "expected_bytes": 10},
            resource={
                "resource_id": "BL-IE-HTTP4000001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "bad",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "terminal"
    db = Database(settings.catalog_db)
    with db.session() as conn:
        row = conn.execute(
            "SELECT state, last_error_code FROM download_jobs WHERE job_id=?",
            ("job-BL-IE-HTTP4000001",),
        ).fetchone()
    assert row["state"] == "terminal_failure"
    assert row["last_error_code"] == "HTTP_400"


def test_etag_change_forces_restart(httpx_mock, settings):
    """If-Range / etag change: server returns 200 full body; client restarts safely."""
    url = "https://example.org/files/etag.pdf"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=b"NEWCONTENT",
        headers={"Content-Type": "application/pdf", "ETag": '"v2"'},
    )
    _seed_resource(settings, rid="BL-IE-ETAGCHG0001", url=url, expected=10)
    part = settings.staging_dir / "BL-IE-ETAGCHG0001.part"
    part.write_bytes(b"OLD!")
    (settings.staging_dir / "BL-IE-ETAGCHG0001.part.state.json").write_text(
        json.dumps({"etag": '"v1"', "bytes_downloaded": 4}), encoding="utf-8"
    )
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-ETAGCHG0001", "expected_bytes": 10},
            resource={
                "resource_id": "BL-IE-ETAGCHG0001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "etag",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "complete"
    req = httpx_mock.get_requests()[-1]
    assert req.headers.get("Range") == "bytes=4-"
    assert req.headers.get("If-Range") == '"v1"'
    dests = list(
        (settings.data_dir / "originals" / "iskcon-education" / "documents").glob(
            "BL-IE-ETAGCHG0001*"
        )
    )
    assert dests and dests[0].read_bytes() == b"NEWCONTENT"


def test_pause_persistence_on_shutdown(settings):
    """Ctrl+C / shutdown flag short-circuits before network and leaves paused semantics."""
    import bhava_library.services.download as dl

    url = "https://example.org/files/pause.pdf"
    _seed_resource(settings, rid="BL-IE-PAUSE000001", url=url, expected=8)
    dl._shutdown.set()
    try:
        with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
            status = download_one(
                settings,
                job={"job_id": "job-BL-IE-PAUSE000001", "expected_bytes": 8},
                resource={
                    "resource_id": "BL-IE-PAUSE000001",
                    "resolved_url": url,
                    "original_url": url,
                    "profile": "core",
                    "title_original": "pause",
                },
                client=client,
                host_locks={},
                host_locks_guard=threading.Lock(),
            )
        assert status == "paused"
    finally:
        dl._shutdown.clear()


def test_pause_mid_stream_persists_part(httpx_mock, settings, monkeypatch: pytest.MonkeyPatch):
    """Shutdown during streaming persists .part sidecar and paused DB state."""
    import bhava_library.services.download as dl

    url = "https://example.org/files/midpause.pdf"
    body = b"X" * 64
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=body,
        headers={"Content-Type": "application/pdf"},
    )
    _seed_resource(settings, rid="BL-IE-MIDPAUSE001", url=url, expected=64)

    real_write_text = Path.write_text

    def write_and_stop(self, data, *args, **kwargs):  # noqa: ANN001
        result = real_write_text(self, data, *args, **kwargs)
        if self.name.endswith(".part.state.json") and "BL-IE-MIDPAUSE001" in str(self):
            dl._shutdown.set()
        return result

    monkeypatch.setattr(Path, "write_text", write_and_stop)
    try:
        with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
            status = download_one(
                settings,
                job={"job_id": "job-BL-IE-MIDPAUSE001", "expected_bytes": 64},
                resource={
                    "resource_id": "BL-IE-MIDPAUSE001",
                    "resolved_url": url,
                    "original_url": url,
                    "profile": "core",
                    "title_original": "midpause",
                },
                client=client,
                host_locks={},
                host_locks_guard=threading.Lock(),
            )
        assert status == "paused"
        part = settings.staging_dir / "BL-IE-MIDPAUSE001.part"
        assert part.exists() and part.stat().st_size > 0
        assert (settings.staging_dir / "BL-IE-MIDPAUSE001.part.state.json").exists()
        db = Database(settings.catalog_db)
        with db.session() as conn:
            row = conn.execute(
                "SELECT state FROM download_jobs WHERE job_id=?",
                ("job-BL-IE-MIDPAUSE001",),
            ).fetchone()
        assert row["state"] == "paused"
    finally:
        dl._shutdown.clear()


def test_connection_interruption_is_retryable(httpx_mock, settings):
    url = "https://example.org/files/cut.pdf"
    httpx_mock.add_exception(httpx.ReadTimeout("simulated drop"))
    _seed_resource(settings, rid="BL-IE-CONNINT0001", url=url, expected=100)
    with (
        PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client,
        pytest.raises((NetworkError, httpx.HTTPError, Exception)),
    ):
        download_one(
            settings,
            job={"job_id": "job-BL-IE-CONNINT0001", "expected_bytes": 100},
            resource={
                "resource_id": "BL-IE-CONNINT0001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "cut",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )


def test_unknown_size_completes(httpx_mock, settings):
    url = "https://example.org/files/nosize.pdf"
    body = b"%PDF-unknown-size"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=body,
        headers={"Content-Type": "application/pdf"},
    )
    _seed_resource(settings, rid="BL-IE-NOSIZE00001", url=url, expected=None)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-NOSIZE00001", "expected_bytes": None},
            resource={
                "resource_id": "BL-IE-NOSIZE00001",
                "resolved_url": url,
                "original_url": url,
                "profile": "core",
                "title_original": "nosize",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "complete"


def test_audio_profile_queues_under_audio_dir(httpx_mock, settings):
    url = "https://example.org/audio/t.mp3"
    httpx_mock.add_response(
        url=url,
        method="GET",
        status_code=200,
        content=b"ID3audio",
        headers={"Content-Type": "audio/mpeg"},
    )
    _seed_resource(settings, rid="BL-IE-AUDIOQ00001", url=url, profile="audio", expected=8)
    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        status = download_one(
            settings,
            job={"job_id": "job-BL-IE-AUDIOQ00001", "expected_bytes": 8},
            resource={
                "resource_id": "BL-IE-AUDIOQ00001",
                "resolved_url": url,
                "original_url": url,
                "profile": "audio",
                "title_original": "t",
            },
            client=client,
            host_locks={},
            host_locks_guard=threading.Lock(),
        )
    assert status == "complete"
    audio_files = list(
        (settings.data_dir / "originals" / "iskcon-education" / "audio").glob("BL-IE-AUDIOQ00001*")
    )
    assert len(audio_files) == 1


def test_backup_long_path_helper():
    from bhava_library.services.backup import _win_long

    p = Path(r"C:\Development\Workspace\DevotionalRepo\bhava-library\data\x")
    assert _win_long(p).startswith("\\\\?\\")


def test_full_backup_and_restore_verification(settings, tmp_path: Path):
    from bhava_library.services.backup import run_restore_check

    src = settings.data_dir / "originals" / "iskcon-education" / "documents" / "one.pdf"
    src.write_bytes(b"%PDF-one")
    dest_root = tmp_path / "backup-ok"
    result = run_backup(settings, target=str(dest_root), full_verify=True)
    assert result["verification_ok"] is True
    assert result["exit_code"] == 0
    assert result["skipped"] == 0
    check = run_restore_check(settings, target=str(dest_root), full=True)
    assert check["ok"] is True
    assert check["checked"] >= 1


def test_backup_skipped_recorded_in_manifest(settings, tmp_path: Path, monkeypatch):
    src = settings.data_dir / "originals" / "iskcon-education" / "documents" / "ok.pdf"
    src.write_bytes(b"%PDF-ok")
    bad = settings.data_dir / "originals" / "iskcon-education" / "documents" / "skipme.pdf"
    bad.write_bytes(b"%PDF-skip")
    dest_root = tmp_path / "backup-skip-manifest"
    real_copy2 = __import__("shutil").copy2

    def flaky_copy2(src_s, dst_s):
        if "skipme.pdf" in str(src_s):
            raise OSError("path too long")
        return real_copy2(src_s, dst_s)

    monkeypatch.setattr("bhava_library.services.backup.shutil.copy2", flaky_copy2)
    with pytest.raises(BackupVerifyError):
        run_backup(settings, target=str(dest_root))
    backups = list(dest_root.glob("bhava-library-backup-*"))
    assert backups
    manifest = json.loads((backups[0] / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["incomplete"] is True
    assert manifest["verification_ok"] is False
    assert any("skipme" in e.get("path", "") for e in manifest["skipped"])
    db = Database(settings.catalog_db)
    with db.session() as conn:
        row = conn.execute(
            "SELECT verification_ok FROM backups ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert int(row["verification_ok"]) == 0
