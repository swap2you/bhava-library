"""Classification review queue export."""

from __future__ import annotations

import csv
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database


def run_review_report(settings: Settings) -> Path:
    db = Database(settings.catalog_db)
    db.migrate()
    out = settings.data_dir / "exports" / "classification_review_queue.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = db.execute(
        """
        SELECT rc.resource_id,
               COALESCE(rn.display_title, r.title_original) AS display_title,
               rc.dimension, rc.term, rc.confidence, rc.review_state, rc.rule_version,
               lf.relative_path
        FROM resource_classifications rc
        JOIN resources r ON r.resource_id = rc.resource_id
        LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
        LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
        WHERE r.removed_at IS NULL
          AND (
            rc.review_state = 'needs_review'
            OR rc.confidence < 0.55
            OR rc.term = 'unknown'
          )
        ORDER BY rc.confidence ASC, rc.resource_id
        """
    )

    fields = [
        "resource_id",
        "display_title",
        "dimension",
        "term",
        "confidence",
        "review_state",
        "rule_version",
        "relative_path",
    ]
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in fields})
    return out
