"""Source dossiers and controlled Bhāva candidate exports (metadata only)."""

from __future__ import annotations

import json
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database, utc_now

CANDIDATE_TYPES = (
    "original-comic-candidate",
    "original-story-candidate",
    "printable-candidate",
    "activity-candidate",
    "teacher-guide-candidate",
    "sunday-school-candidate",
)


def _is_binary(path: Path) -> bool:
    return path.suffix.lower() in {
        ".pdf",
        ".mp3",
        ".mp4",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".wav",
        ".m4a",
    }


def _candidate_id(resource_id: str, product_type: str) -> str:
    return f"{resource_id}::{product_type}"


def run_candidates(settings: Settings, *, limit: int | None = None) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    sql = """
        SELECT rc.resource_id, rc.term AS product_type, rc.confidence,
               r.title_original, rn.display_title, lf.relative_path
        FROM resource_classifications rc
        JOIN resources r ON r.resource_id = rc.resource_id
        LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
        LEFT JOIN local_files lf ON lf.resource_id = r.resource_id
        WHERE rc.dimension = 'production-opportunity'
          AND rc.term IN ({})
          AND r.removed_at IS NULL
        ORDER BY rc.confidence DESC
    """.format(",".join("?" * len(CANDIDATE_TYPES)))
    params: tuple[object, ...] = CANDIDATE_TYPES
    if limit is not None:
        sql += " LIMIT ?"
        params = (*params, limit)
    rows = db.execute(sql, params)

    export_root = settings.data_dir / "exports" / "bhava-candidates"
    meta_dir = export_root / "metadata"
    briefs_dir = export_root / "briefs"
    meta_dir.mkdir(parents=True, exist_ok=True)
    briefs_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    exported = 0
    with db.session() as conn:
        for row in rows:
            cid = _candidate_id(row["resource_id"], row["product_type"])
            payload = {
                "candidate_id": cid,
                "resource_id": row["resource_id"],
                "product_type": row["product_type"],
                "confidence": row["confidence"],
                "display_title": row["display_title"] or row["title_original"],
                "relative_path": row["relative_path"],
                "copyright_owner": settings.copyright.owner,
                "contact_email": settings.copyright.contact_email,
                "note": "Metadata/brief only — no third-party binaries exported.",
            }
            conn.execute(
                """
                INSERT INTO production_candidates(
                  candidate_id, resource_id, product_type, score, status, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  score = excluded.score,
                  status = excluded.status,
                  payload_json = excluded.payload_json
                """,
                (
                    cid,
                    row["resource_id"],
                    row["product_type"],
                    row["confidence"],
                    "proposed",
                    json.dumps(payload),
                    utc_now(),
                ),
            )
            dossier = {
                "candidate_id": cid,
                "source_title": row["title_original"],
                "reference_path": row["relative_path"],
                "review_state": "pending",
            }
            conn.execute(
                """
                INSERT INTO source_dossiers(candidate_id, payload_json, review_state, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  review_state = excluded.review_state,
                  updated_at = excluded.updated_at
                """,
                (cid, json.dumps(dossier), "pending", utc_now()),
            )
            conn.execute(
                """
                INSERT INTO independent_creation_records(
                  candidate_id, payload_json, similarity_status, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  similarity_status = excluded.similarity_status,
                  updated_at = excluded.updated_at
                """,
                (
                    cid,
                    json.dumps({"required": True, "status": "not_started"}),
                    "not_started",
                    utc_now(),
                ),
            )
            created += 1

            meta_path = meta_dir / f"{cid.replace('::', '--')}.json"
            meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            brief_path = briefs_dir / f"{cid.replace('::', '--')}.md"
            brief_path.write_text(
                f"# Candidate: {payload['display_title']}\n\n"
                f"- Resource: `{row['resource_id']}`\n"
                f"- Type: {row['product_type']}\n"
                f"- Reference path (not copied): `{row['relative_path']}`\n",
                encoding="utf-8",
            )
            assert not _is_binary(meta_path)
            assert not _is_binary(brief_path)
            exported += 2

    try:
        export_rel = str(export_root.relative_to(settings.repo_root))
    except ValueError:
        export_rel = str(export_root)
    manifest = {
        "candidates": created,
        "export_root": export_rel,
        "binary_files": 0,
    }
    (export_root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"candidates": created, "export_files": exported}
