"""Print remediation catalog counts (read-only)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    db = root / "data" / "catalog" / "bhava-library.sqlite3"
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    def count(sql: str, params: tuple[object, ...] = ()) -> int:
        return int(conn.execute(sql, params).fetchone()[0])

    report = {
        "schema": max(
            (int(row["version"]) for row in conn.execute("SELECT version FROM schema_migrations")),
            default=0,
        ),
        "resources": count("SELECT COUNT(*) FROM resources WHERE removed_at IS NULL"),
        "classifications": count("SELECT COUNT(*) FROM resource_classifications"),
        "evidence": count("SELECT COUNT(*) FROM classification_evidence"),
        "program_mappings": count("SELECT COUNT(*) FROM program_mappings"),
        "names": count("SELECT COUNT(*) FROM resource_names"),
        "technical": count("SELECT COUNT(*) FROM technical_metadata"),
        "candidates": count("SELECT COUNT(*) FROM production_candidates"),
        "dossiers": count("SELECT COUNT(*) FROM source_dossiers"),
        "candidate_statuses": {
            row["status"]: row["c"]
            for row in conn.execute(
                "SELECT status, COUNT(*) c FROM production_candidates GROUP BY 1"
            )
        },
        "dossier_statuses": {
            row["review_state"]: row["c"]
            for row in conn.execute(
                "SELECT review_state, COUNT(*) c FROM source_dossiers GROUP BY 1"
            )
        },
        "review_states": {
            row["review_state"]: row["c"]
            for row in conn.execute(
                "SELECT review_state, COUNT(*) c FROM resource_classifications GROUP BY 1"
            )
        },
        "unknown_content_form": count(
            "SELECT COUNT(*) FROM resource_classifications "
            "WHERE dimension='content-form' AND term='unknown'"
        ),
        "language_english": count(
            "SELECT COUNT(*) FROM resource_classifications "
            "WHERE dimension='language' AND term='english'"
        ),
        "language_unknown": count(
            "SELECT COUNT(*) FROM resource_classifications "
            "WHERE dimension='language' AND term='unknown'"
        ),
        "program_keys": {
            row["program"]: row["c"]
            for row in conn.execute(
                "SELECT program, COUNT(*) c FROM program_mappings GROUP BY 1 ORDER BY 1"
            )
        },
        "display_samples": [
            dict(row)
            for row in conn.execute(
                "SELECT resource_id, display_filename FROM resource_names "
                "ORDER BY resource_id LIMIT 5"
            )
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
