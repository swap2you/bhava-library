"""Report generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.constants import GIB
from bhava_library.infrastructure.database import Database
from bhava_library.infrastructure.disk_guard import disk_usage
from bhava_library.infrastructure.filesystem import ensure_dirs


def run_report(settings: Settings) -> Path:
    ensure_dirs(settings.reports_dir)
    db = Database(settings.catalog_db)
    db.migrate()

    def count(sql: str, params: tuple = ()) -> int:
        rows = db.execute(sql, params)
        return int(rows[0][0]) if rows else 0

    resources = count("SELECT COUNT(*) FROM resources WHERE removed_at IS NULL")
    resolved = count(
        "SELECT COUNT(*) FROM resources WHERE removed_at IS NULL AND resolved_url IS NOT NULL"
    )
    unresolved = count(
        "SELECT COUNT(*) FROM resources WHERE removed_at IS NULL AND status='unresolved'"
    )
    broken = count(
        "SELECT COUNT(*) FROM resources WHERE removed_at IS NULL AND status='inaccessible'"
    )
    audio = count("SELECT COUNT(*) FROM resources WHERE profile='audio' AND removed_at IS NULL")
    video = count("SELECT COUNT(*) FROM resources WHERE profile='video' AND removed_at IS NULL")
    verified = count("SELECT COUNT(*) FROM local_files WHERE quarantine_reason IS NULL")
    quarantined = count("SELECT COUNT(*) FROM local_files WHERE quarantine_reason IS NOT NULL")
    duplicates = count("SELECT COUNT(*) FROM local_files WHERE duplicate_of_file_id IS NOT NULL")
    bytes_downloaded = count(
        "SELECT COALESCE(SUM(size_bytes),0) FROM local_files WHERE quarantine_reason IS NULL"
    )
    jobs_complete = count("SELECT COUNT(*) FROM download_jobs WHERE state='complete'")
    jobs_pending = count(
        "SELECT COUNT(*) FROM download_jobs WHERE state IN ('pending','paused','retryable','active')"
    )

    snap = disk_usage(settings.data_dir if settings.data_dir.exists() else settings.repo_root)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    payload = {
        "generated_at": stamp,
        "resources": resources,
        "resolved": resolved,
        "unresolved": unresolved,
        "broken": broken,
        "audio_deferred": audio,
        "video_deferred": video,
        "files_verified": verified,
        "quarantined": quarantined,
        "duplicates": duplicates,
        "bytes_downloaded": bytes_downloaded,
        "jobs_complete": jobs_complete,
        "jobs_pending": jobs_pending,
        "free_disk_bytes": snap.free_bytes,
        "copyright_owner": settings.copyright.owner,
        "copyright_email": settings.copyright.contact_email,
    }
    json_path = settings.reports_dir / f"final-report-{stamp}.json"
    md_path = settings.reports_dir / f"final-report-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = f"""# Bhāva Library Final Report

Generated: {stamp}

## Catalog
- Resources: {resources}
- Resolved / unresolved / broken: {resolved} / {unresolved} / {broken}
- Audio resources: {audio}
- Video resources: {video}

## Acquisition
- Jobs complete / pending: {jobs_complete} / {jobs_pending}
- Files verified: {verified}
- Quarantined: {quarantined}
- Duplicates (linked, not deleted): {duplicates}
- Bytes downloaded: {bytes_downloaded} ({bytes_downloaded / GIB:.3f} GiB)

## Disk
- Free: {snap.free_bytes / GIB:.2f} GiB

## Identity (original works only)
- Owner: {settings.copyright.owner}
- Publisher: {settings.copyright.publisher}
- Project: {settings.copyright.project}
- Contact: {settings.copyright.contact_email}

## Continuation
```powershell
.\\bhava.ps1 acquire --profile audio
.\\bhava.ps1 backup --target "<EXTERNAL_BACKUP_PATH>" --full-verify
.\\bhava.ps1 restore-check --target "<EXTERNAL_BACKUP_PATH>" --full
```
"""
    md_path.write_text(md, encoding="utf-8")
    # Also write stable latest pointers
    (settings.reports_dir / "latest-report.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    (settings.reports_dir / "latest-report.md").write_text(md, encoding="utf-8")
    db.add_event("report", payload_json=json.dumps({"path": str(md_path)}))
    return md_path
