"""Metadata-only source scan."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlparse

from bhava_library.config import Settings
from bhava_library.constants import SOURCE_ID_ISKCON
from bhava_library.domain.enums import ResourceStatus
from bhava_library.domain.models import ResourceCandidate, ScanSummary
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.infrastructure.filesystem import ensure_dirs
from bhava_library.infrastructure.hashing import sha256_text
from bhava_library.infrastructure.http import PoliteHttpClient
from bhava_library.logging import get_logger
from bhava_library.sources.iskcon_education import IskconEducationSourceAdapter

logger = get_logger("bhava.scan")


def _snapshot_id(sha: str, when: datetime) -> str:
    return f"snap-{when.strftime('%Y%m%dT%H%M%SZ')}-{sha[:8]}"


def _upsert_resource(conn, candidate: ResourceCandidate, now: str) -> str:
    """Insert or update resource; return change kind: new|changed|same."""
    existing = conn.execute(
        "SELECT * FROM resources WHERE resource_id = ?",
        (candidate.resource_id,),
    ).fetchone()
    domain = candidate.raw.get("source_domain") or urlparse(candidate.original_url).netloc
    if existing is None:
        conn.execute(
            """
            INSERT INTO resources(
              resource_id, source_id, source_row_key, title_original, title_normalized,
              level, media_type, media_format, theme, source_label, language,
              original_url, source_domain, profile, priority, status,
              first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.resource_id,
                candidate.source_id,
                candidate.source_row_key,
                candidate.title_original,
                candidate.title_normalized,
                candidate.level,
                candidate.media_type,
                candidate.media_format,
                candidate.theme,
                candidate.source_label,
                candidate.language,
                candidate.original_url,
                domain,
                candidate.profile.value,
                candidate.priority,
                ResourceStatus.DISCOVERED.value,
                now,
                now,
            ),
        )
        return "new"

    changed = (
        existing["title_original"] != candidate.title_original
        or existing["original_url"] != candidate.original_url
        or existing["media_type"] != candidate.media_type
        or existing["media_format"] != candidate.media_format
        or existing["theme"] != candidate.theme
        or existing["level"] != candidate.level
        or existing["source_label"] != candidate.source_label
    )
    conn.execute(
        """
        UPDATE resources SET
          title_original=?, title_normalized=?, level=?, media_type=?, media_format=?,
          theme=?, source_label=?, original_url=?, source_domain=?, profile=?,
          priority=?, last_seen_at=?, removed_at=NULL
        WHERE resource_id=?
        """,
        (
            candidate.title_original,
            candidate.title_normalized,
            candidate.level,
            candidate.media_type,
            candidate.media_format,
            candidate.theme,
            candidate.source_label,
            candidate.original_url,
            domain,
            candidate.profile.value,
            candidate.priority,
            now,
            candidate.resource_id,
        ),
    )
    return "changed" if changed else "same"


def run_scan(
    settings: Settings,
    *,
    html: str | None = None,
    client: PoliteHttpClient | None = None,
) -> ScanSummary:
    """Perform metadata-only scan. Never downloads resource bodies."""
    ensure_dirs(
        settings.snapshots_dir,
        settings.manifests_dir / "sources",
        settings.manifests_dir / "snapshots",
        settings.data_dir / "catalog",
    )
    db = Database(settings.catalog_db)
    db.migrate()
    db.ensure_source(
        SOURCE_ID_ISKCON,
        "ISKCON Ministry of Education Media Library",
        "https://iskconeducation.org/",
        "iskcon_education",
    )

    adapter = IskconEducationSourceAdapter(settings.source_iskcon.index_url)
    own_client = client is None
    http = client or PoliteHttpClient(
        user_agent=settings.source_iskcon.user_agent,
        request_delay_seconds=settings.source_iskcon.request_delay_seconds,
        verify_tls=settings.download.verify_tls,
    )
    try:
        if html is None:
            html, final_url, status = adapter.fetch_index(http)
        else:
            final_url, status = settings.source_iskcon.index_url, 200
    finally:
        if own_client:
            http.close()

    when = datetime.now(UTC)
    sha = sha256_text(html)
    snap_id = _snapshot_id(sha, when)
    html_path = settings.snapshots_dir / f"{snap_id}.html"
    headers_path = settings.snapshots_dir / f"{snap_id}.headers.json"
    html_path.write_text(html, encoding="utf-8")
    headers_path.write_text(
        json.dumps(
            {
                "final_url": final_url,
                "http_status": status,
                "retrieved_at": when.isoformat(),
                "html_sha256": sha,
                "parser_version": adapter.parser_version,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    candidates = adapter.parse_rows(html, base_url=final_url)
    now = utc_now()
    new_count = changed_count = 0
    seen_ids: set[str] = set()
    types: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    themes: Counter[str] = Counter()
    domains: Counter[str] = Counter()

    with db.session() as conn:
        prior = {
            row["resource_id"]
            for row in conn.execute(
                "SELECT resource_id FROM resources WHERE source_id = ? AND removed_at IS NULL",
                (SOURCE_ID_ISKCON,),
            )
        }
        for candidate in candidates:
            seen_ids.add(candidate.resource_id)
            kind = _upsert_resource(conn, candidate, now)
            if kind == "new":
                new_count += 1
            elif kind == "changed":
                changed_count += 1
            types[candidate.media_type or "(none)"] += 1
            formats[candidate.media_format or "(none)"] += 1
            themes[candidate.theme or "(none)"] += 1
            domains[urlparse(candidate.original_url).netloc or "(none)"] += 1

        removed = prior - seen_ids
        for rid in removed:
            conn.execute(
                "UPDATE resources SET removed_at = ? WHERE resource_id = ?",
                (now, rid),
            )

        try:
            html_rel = str(html_path.relative_to(settings.repo_root))
        except ValueError:
            html_rel = str(html_path)
        conn.execute(
            """
            INSERT INTO source_snapshots(
              snapshot_id, source_id, retrieved_at, html_path, html_sha256,
              http_status, final_url, parser_version, row_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap_id,
                SOURCE_ID_ISKCON,
                when.isoformat(),
                html_rel,
                sha,
                status,
                final_url,
                adapter.parser_version,
                len(candidates),
            ),
        )
        conn.execute(
            "UPDATE sources SET last_scan_at = ? WHERE source_id = ?",
            (now, SOURCE_ID_ISKCON),
        )

    # JSONL manifest (Git-trackable lightweight copy under manifests/)
    manifest_path = settings.manifests_dir / "sources" / f"{SOURCE_ID_ISKCON}-resources.jsonl"
    with manifest_path.open("w", encoding="utf-8") as fh:
        for candidate in candidates:
            fh.write(candidate.model_dump_json() + "\n")

    db.add_event("scan", payload_json=json.dumps({"snapshot_id": snap_id, "rows": len(candidates)}))
    logger.info("Scan complete: %s rows snapshot=%s", len(candidates), snap_id)

    return ScanSummary(
        source_id=SOURCE_ID_ISKCON,
        snapshot_id=snap_id,
        row_count=len(candidates),
        new_count=new_count,
        removed_count=len(removed),
        changed_count=changed_count,
        types=dict(types),
        formats=dict(formats),
        themes=dict(themes),
        domains=dict(domains),
        html_sha256=sha,
        parser_version=adapter.parser_version,
    )
