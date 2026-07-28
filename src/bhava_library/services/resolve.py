"""Link resolution service."""

from __future__ import annotations

import json

from bhava_library.config import Settings
from bhava_library.domain.enums import AcquisitionProfile, ResourceStatus
from bhava_library.domain.models import ResourceCandidate
from bhava_library.infrastructure.database import Database, utc_now
from bhava_library.infrastructure.http import PoliteHttpClient
from bhava_library.logging import get_logger
from bhava_library.sources.iskcon_education import IskconEducationSourceAdapter

logger = get_logger("bhava.resolve")


def run_resolve(
    settings: Settings,
    *,
    limit: int | None = None,
    client: PoliteHttpClient | None = None,
) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    adapter = IskconEducationSourceAdapter(settings.source_iskcon.index_url)
    own = client is None
    http = client or PoliteHttpClient(
        user_agent=settings.source_iskcon.user_agent,
        request_delay_seconds=settings.source_iskcon.request_delay_seconds,
        verify_tls=settings.download.verify_tls,
    )
    counts = {"resolved": 0, "unresolved": 0, "inaccessible": 0, "skipped": 0}
    try:
        with db.session() as conn:
            sql = """
              SELECT * FROM resources
              WHERE removed_at IS NULL
                AND (resolved_url IS NULL OR status IN ('discovered','unresolved','resolving'))
              ORDER BY priority ASC, resource_id ASC
            """
            rows = list(conn.execute(sql))
            if limit is not None:
                rows = rows[:limit]

            for row in rows:
                candidate = ResourceCandidate(
                    resource_id=row["resource_id"],
                    source_id=row["source_id"],
                    source_row_key=row["source_row_key"],
                    title_original=row["title_original"],
                    title_normalized=row["title_normalized"] or "",
                    level=row["level"],
                    media_type=row["media_type"],
                    media_format=row["media_format"],
                    theme=row["theme"],
                    source_label=row["source_label"],
                    original_url=row["original_url"],
                    profile=AcquisitionProfile(row["profile"] or "unknown"),
                    priority=row["priority"] or 100,
                )
                try:
                    db.set_resource_status(conn, candidate.resource_id, ResourceStatus.RESOLVING)
                except Exception:  # noqa: BLE001
                    conn.execute(
                        "UPDATE resources SET status=? WHERE resource_id=?",
                        (ResourceStatus.RESOLVING.value, candidate.resource_id),
                    )

                result = adapter.resolve_link(http, candidate)
                conn.execute(
                    """
                    UPDATE resources SET
                      resolved_url=?, resolution_method=?, resolution_confidence=?,
                      status=?, last_seen_at=?
                    WHERE resource_id=?
                    """,
                    (
                        result.resolved_url,
                        result.method,
                        result.confidence,
                        result.status.value,
                        utc_now(),
                        candidate.resource_id,
                    ),
                )
                if result.status == ResourceStatus.RESOLVED:
                    counts["resolved"] += 1
                elif result.status == ResourceStatus.INACCESSIBLE:
                    counts["inaccessible"] += 1
                else:
                    counts["unresolved"] += 1
                logger.info(
                    "Resolved %s -> %s (%s)",
                    candidate.resource_id,
                    result.status.value,
                    result.method,
                )
    finally:
        if own:
            http.close()

    db.add_event("resolve", payload_json=json.dumps(counts))
    return counts
