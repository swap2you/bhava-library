"""Print remediation catalog counts (read-only)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    db = args.database or root / "data" / "catalog" / "bhava-library.sqlite3"
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    local_file_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(local_files)")
    }
    program_mapping_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(program_mappings)")
    }

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
        "content_form_counts": {
            row["term"]: row["c"]
            for row in conn.execute(
                """
                SELECT term, COUNT(DISTINCT resource_id) c
                FROM resource_classifications
                WHERE dimension = 'content-form'
                GROUP BY term ORDER BY term
                """
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
        "program_mapping_review_states": (
            {
                row["review_state"]: row["c"]
                for row in conn.execute(
                    "SELECT review_state, COUNT(*) c FROM program_mappings GROUP BY 1 ORDER BY 1"
                )
            }
            if "review_state" in program_mapping_columns
            else {}
        ),
        "program_mapping_reasons": {
            row["reason"]: row["c"]
            for row in conn.execute(
                """
                SELECT json_extract(assumptions_json, '$.match_reason') AS reason,
                       COUNT(*) c
                FROM program_mappings
                GROUP BY 1 ORDER BY 1
                """
            )
        },
        "candidate_product_types": {
            row["product_type"]: row["c"]
            for row in conn.execute(
                """
                SELECT product_type, COUNT(*) c
                FROM production_candidates
                GROUP BY 1 ORDER BY 1
                """
            )
        },
        "duplicate_kinds": (
            {
                row["duplicate_kind"]: row["c"]
                for row in conn.execute(
                    """
                    SELECT duplicate_kind, COUNT(*) c
                    FROM local_files
                    WHERE duplicate_kind IS NOT NULL
                    GROUP BY 1 ORDER BY 1
                    """
                )
            }
            if "duplicate_kind" in local_file_columns
            else {}
        ),
        "reacquisition_queue": (
            count("SELECT COUNT(*) FROM local_files WHERE reacquisition_required = 1")
            if "reacquisition_required" in local_file_columns
            else 0
        ),
        "curation_runs": {
            row["kind"]: row["c"]
            for row in conn.execute(
                "SELECT kind, COUNT(*) c FROM curation_runs GROUP BY 1 ORDER BY 1"
            )
        },
        "curation_events": count("SELECT COUNT(*) FROM curation_events"),
        "classification_reviews": count("SELECT COUNT(*) FROM classification_reviews"),
        "taxonomy_relations": count("SELECT COUNT(*) FROM taxonomy_relations"),
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
