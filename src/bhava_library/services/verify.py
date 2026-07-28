"""File verification, quarantine, and read-only finalization."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.domain.enums import ResourceStatus
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.infrastructure.filesystem import ensure_dirs, mark_readonly, path_is_within
from bhava_library.infrastructure.hashing import sha256_file
from bhava_library.infrastructure.mime import detect_type, extension_of
from bhava_library.infrastructure.windows_defender import scan_file
from bhava_library.logging import get_logger

logger = get_logger("bhava.verify")

EXECUTABLE_MIMES = frozenset(
    {
        "application/x-msdownload",
        "application/x-executable",
        "application/x-dosexec",
        "application/vnd.microsoft.portable-executable",
    }
)


def _zip_is_suspicious(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            total_uncomp = 0
            total_comp = 0
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    return "zip_slip"
                if name.lower().endswith((".exe", ".dll", ".bat", ".cmd", ".ps1", ".scr")):
                    return "zip_contains_executable"
                total_uncomp += info.file_size
                total_comp += max(info.compress_size, 1)
            if total_comp and total_uncomp / total_comp > 100 and total_uncomp > 100 * 1024 * 1024:
                return "zip_bomb_ratio"
    except zipfile.BadZipFile:
        return "malformed_zip"
    except RuntimeError as exc:
        if "encrypted" in str(exc).lower() or "password" in str(exc).lower():
            return "encrypted_archive"
        return f"zip_error:{exc}"
    return None


def quarantine(
    settings: Settings,
    *,
    path: Path,
    resource_id: str,
    reason: str,
) -> Path:
    ensure_dirs(settings.quarantine_dir)
    dest = settings.quarantine_dir / f"{resource_id}_{path.name}"
    if path.exists():
        path.replace(dest)
    db = Database(settings.catalog_db)
    with db.session() as conn:
        conn.execute(
            "UPDATE resources SET status=? WHERE resource_id=?",
            (ResourceStatus.QUARANTINED.value, resource_id),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256,
              detected_type, verified_at, read_only, quarantine_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                f"file-{resource_id}",
                resource_id,
                str(dest.relative_to(settings.repo_root)) if dest.exists() else str(dest),
                dest.stat().st_size if dest.exists() else 0,
                sha256_file(dest) if dest.exists() else "",
                detect_type(dest) if dest.exists() else None,
                utc_now(),
                reason,
            ),
        )
    db.add_event("quarantine", resource_id=resource_id, payload_json=json.dumps({"reason": reason}))
    return dest


def verify_local_file(
    settings: Settings,
    *,
    resource_id: str,
    path: Path,
    expected_bytes: int | None = None,
    precomputed_sha256: str | None = None,
) -> dict[str, object]:
    db = Database(settings.catalog_db)
    if not path.exists():
        return {"ok": False, "reason": "missing"}

    size = path.stat().st_size
    if (
        settings.verification.content_length
        and expected_bytes is not None
        and size != expected_bytes
    ):
        quarantine(settings, path=path, resource_id=resource_id, reason="byte_mismatch")
        return {"ok": False, "reason": "byte_mismatch"}

    digest = precomputed_sha256 or (sha256_file(path) if settings.verification.sha256 else "")
    detected = detect_type(path) if settings.verification.signature_detection else None
    ext = extension_of(path.name)

    if detected in EXECUTABLE_MIMES:
        quarantine(settings, path=path, resource_id=resource_id, reason="executable_content")
        return {"ok": False, "reason": "executable_content"}

    if ext == ".zip" or (detected and "zip" in detected):
        reason = _zip_is_suspicious(path)
        if reason:
            quarantine(settings, path=path, resource_id=resource_id, reason=reason)
            return {"ok": False, "reason": reason}

    # Extension vs signature soft check — quarantine only on severe mismatch families
    if detected and ext == ".pdf" and detected not in {"application/pdf"}:
        quarantine(settings, path=path, resource_id=resource_id, reason="signature_mismatch")
        return {"ok": False, "reason": "signature_mismatch"}

    if settings.verification.windows_defender:
        result = scan_file(path)
        # Only quarantine on explicit unclean result; treat unavailable/inconclusive as pass.
        if result.available and result.clean is False:
            quarantine(settings, path=path, resource_id=resource_id, reason="defender_detection")
            return {"ok": False, "reason": "defender_detection", "detail": result.detail}

    if settings.verification.mark_verified_read_only:
        mark_readonly(path)

    rel = (
        str(path.relative_to(settings.repo_root))
        if path_is_within(path, settings.repo_root)
        else str(path)
    )
    with db.session() as conn:
        # Duplicate grouping
        dup = conn.execute(
            "SELECT file_id FROM local_files WHERE sha256=? AND resource_id<>? AND quarantine_reason IS NULL",
            (digest, resource_id),
        ).fetchone()
        conn.execute(
            """
            INSERT OR REPLACE INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256,
              detected_type, verified_at, read_only, duplicate_of_file_id, quarantine_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                f"file-{resource_id}",
                resource_id,
                rel,
                size,
                digest,
                detected,
                utc_now(),
                1 if settings.verification.mark_verified_read_only else 0,
                dup["file_id"] if dup else None,
            ),
        )
        conn.execute(
            "UPDATE resources SET status=? WHERE resource_id=?",
            (ResourceStatus.VERIFIED.value, resource_id),
        )
    db.add_event(
        "verify", resource_id=resource_id, payload_json=json.dumps({"sha256": digest, "size": size})
    )
    return {"ok": True, "sha256": digest, "size": size, "duplicate": bool(dup)}


def run_verify(settings: Settings, *, full: bool = False) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    with db.session() as conn:
        if full:
            rows = list(conn.execute("SELECT * FROM local_files WHERE quarantine_reason IS NULL"))
        else:
            rows = list(
                conn.execute(
                    """
                    SELECT lf.* FROM local_files lf
                    JOIN resources r ON r.resource_id = lf.resource_id
                    WHERE r.status IN ('downloaded','verifying','verified')
                      AND lf.quarantine_reason IS NULL
                    """
                )
            )
        pending = list(
            conn.execute(
                """
                SELECT resource_id FROM resources
                WHERE status='downloaded'
                  AND resource_id NOT IN (SELECT resource_id FROM local_files)
                """
            )
        )
    counts = {"verified": 0, "quarantined": 0, "missing": 0, "duplicates": 0}
    for row in rows:
        path = settings.repo_root / row["relative_path"]
        if not path.exists():
            path = Path(row["relative_path"])
        result = verify_local_file(
            settings,
            resource_id=row["resource_id"],
            path=path,
            expected_bytes=row["size_bytes"],
            precomputed_sha256=row["sha256"],
        )
        if result.get("ok"):
            counts["verified"] += 1
            if result.get("duplicate"):
                counts["duplicates"] += 1
        elif result.get("reason") == "missing":
            counts["missing"] += 1
        else:
            counts["quarantined"] += 1

    for prow in pending:
        matches = list(settings.originals_dir.rglob(f"{prow['resource_id']}_*"))
        if not matches:
            counts["missing"] += 1
            continue
        result = verify_local_file(settings, resource_id=prow["resource_id"], path=matches[0])
        if result.get("ok"):
            counts["verified"] += 1
        else:
            counts["quarantined"] += 1

    db.add_event("verify_batch", payload_json=json.dumps(counts))
    return counts
