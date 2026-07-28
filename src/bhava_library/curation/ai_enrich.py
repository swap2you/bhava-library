"""Optional AI enrichment — proposals only, skipped without API key."""

from __future__ import annotations

import os

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database, utc_now


def run_ai_enrich(settings: Settings, *, limit: int | None = None) -> dict[str, object]:
    """
    AI outputs are optional proposals requiring human review.

    When BHAVA_AI_API_KEY (or OPENAI_API_KEY) is unset, this step is a no-op.
    Never uploads full third-party binaries to external models.
    """
    api_key = os.environ.get("BHAVA_AI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    db = Database(settings.catalog_db)
    db.migrate()
    if not api_key:
        return {"skipped": True, "reason": "no API key configured", "proposals": 0}

    run_id = f"ai-{utc_now()}"
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO curation_runs(run_id, kind, started_at, completed_at, stats_json)
            VALUES (?, 'ai_enrich', ?, ?, ?)
            """,
            (run_id, utc_now(), utc_now(), '{"proposals": 0, "note": "stub"}'),
        )
    return {"skipped": False, "run_id": run_id, "proposals": 0, "note": "AI enrich stub"}
