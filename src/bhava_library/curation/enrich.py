"""Technical metadata extraction with graceful optional-deps degradation."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database, utc_now

EXTRACTOR_VERSION = "enrich-v1.0"


def _guess_mime(path: Path) -> str | None:
    try:
        import filetype

        kind = filetype.guess(str(path))
        return kind.mime if kind else None
    except Exception:  # noqa: BLE001
        return None


def _pdf_metadata(path: Path) -> dict[str, Any]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        info = reader.metadata or {}
        return {
            "page_count": len(reader.pages),
            "pdf_info": {k: str(v) for k, v in info.items() if v is not None},
            "extractor": "pypdf",
        }
    except Exception:  # noqa: BLE001
        return {"page_count": None, "extractor": "filetype-only"}


def _audio_metadata(path: Path) -> dict[str, Any]:
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path)
        if audio is None:
            return {"extractor": "filetype-only"}
        tags = {}
        if hasattr(audio, "tags") and audio.tags:
            for key, val in audio.tags.items():
                tags[str(key)] = str(val)
        return {
            "duration_seconds": getattr(getattr(audio, "info", None), "length", None),
            "tags": tags,
            "extractor": "mutagen",
        }
    except Exception:  # noqa: BLE001
        return {"extractor": "filetype-only"}


def _archive_metadata(path: Path) -> dict[str, Any]:
    if not zipfile.is_zipfile(path):
        return {}
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()[:50]
            return {
                "archive_type": "zip",
                "member_count": len(zf.namelist()),
                "sample_members": names,
            }
    except Exception as exc:  # noqa: BLE001
        return {"archive_type": "zip", "error": str(exc)}


def extract_technical_metadata(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    payload: dict[str, Any] = {
        "filename": path.name,
        "extension": suffix,
        "size_bytes": path.stat().st_size if path.exists() else None,
        "mime_guess": _guess_mime(path) if path.exists() else None,
    }
    if suffix == ".pdf" and path.exists():
        payload["pdf"] = _pdf_metadata(path)
    elif suffix in {".mp3", ".m4a", ".ogg", ".wav", ".flac"} and path.exists():
        payload["audio"] = _audio_metadata(path)
    elif suffix in {".zip", ".tar", ".gz"} and path.exists():
        payload["archive"] = _archive_metadata(path)
    return payload


def _sidecar_paths(settings: Settings, resource_id: str) -> tuple[Path, Path]:
    technical = settings.data_dir / "derived" / "technical" / f"{resource_id}.json"
    metadata = settings.data_dir / "derived" / "metadata" / f"{resource_id}.json"
    technical.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)
    return technical, metadata


def write_sidecars(
    settings: Settings,
    resource_id: str,
    payload: dict[str, Any],
    *,
    catalog_row: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    technical_path, metadata_path = _sidecar_paths(settings, resource_id)
    envelope = {
        "resource_id": resource_id,
        "extractor_version": EXTRACTOR_VERSION,
        "extracted_at": utc_now(),
        "technical": payload,
    }
    technical_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    meta = {
        "resource_id": resource_id,
        "display_sidecar": str(metadata_path.relative_to(settings.data_dir)),
        "catalog": catalog_row or {},
    }
    metadata_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return technical_path, metadata_path


def run_enrich(settings: Settings, *, limit: int | None = None) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    sql = """
        SELECT r.resource_id, r.title_original, r.media_type, r.media_format,
               lf.relative_path, lf.size_bytes, lf.sha256
        FROM resources r
        JOIN local_files lf ON lf.resource_id = r.resource_id
        WHERE r.removed_at IS NULL
        ORDER BY r.resource_id
    """
    params: tuple[()] | tuple[int] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    rows = db.execute(sql, params)
    enriched = 0
    with db.session() as conn:
        for row in rows:
            rel = row["relative_path"]
            disk_path = settings.repo_root / rel if not Path(rel).is_absolute() else Path(rel)
            if not disk_path.exists():
                disk_path = settings.data_dir.parent / rel
            if not disk_path.exists() and rel.startswith("data/"):
                disk_path = settings.repo_root / rel
            payload = extract_technical_metadata(disk_path) if disk_path.exists() else {}
            write_sidecars(
                settings,
                row["resource_id"],
                payload,
                catalog_row={
                    "title_original": row["title_original"],
                    "relative_path": rel,
                    "size_bytes": row["size_bytes"],
                    "sha256": row["sha256"],
                },
            )
            conn.execute(
                """
                INSERT INTO technical_metadata(resource_id, payload_json, extracted_at, extractor_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  extracted_at = excluded.extracted_at,
                  extractor_version = excluded.extractor_version
                """,
                (
                    row["resource_id"],
                    json.dumps(payload),
                    utc_now(),
                    EXTRACTOR_VERSION,
                ),
            )
            enriched += 1
    return {"candidates": len(rows), "enriched": enriched}
