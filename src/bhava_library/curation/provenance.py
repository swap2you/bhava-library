"""Source dossiers and controlled Bhāva candidate exports (metadata only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bhava_library.config import Settings
from bhava_library.curation.audit import audited_curation_command
from bhava_library.infrastructure.catalog_queries import PREFERRED_LOCAL_FILE_JOIN
from bhava_library.infrastructure.database import Database, utc_now

CANDIDATE_TYPES = (
    "original-comic-candidate",
    "original-story-candidate",
    "printable-candidate",
    "activity-candidate",
    "teacher-guide-candidate",
    "sunday-school-candidate",
)
MIN_APPROVAL_CONFIDENCE = 0.75
CANDIDATE_STATUSES = frozenset(
    {
        "candidate_proposal",
        "dossier_shell",
        "independent_creation_not_started",
        "reviewed_dossier",
        "approved_production_candidate",
    }
)
GENERATED_CANDIDATE_STATUSES = frozenset({"proposed", "candidate_proposal", "dossier_shell"})
GENERATED_DOSSIER_STATUSES = frozenset({"pending", "dossier_shell"})
GENERATED_CREATION_STATUSES = frozenset({"not_started", "independent_creation_not_started"})
REQUIRED_DOSSIER_FIELDS = (
    "primary_bona_fide_sources",
    "chapter_verse_references",
    "factual_learning_objectives",
    "references_consulted",
    "protected_expression_excluded",
    "proposed_original_structure",
    "original_design_requirements",
    "reviewer",
    "review_status",
)


def _has_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return value is not None


def validate_candidate_promotion(
    candidate: dict[str, Any],
    dossier: dict[str, Any],
    *,
    target_status: str,
) -> list[str]:
    """Return every reason a candidate cannot enter a human-reviewed state."""
    if target_status not in {"reviewed_dossier", "approved_production_candidate"}:
        return [f"unsupported promotion target: {target_status}"]
    errors = [
        f"missing required dossier field: {field}"
        for field in REQUIRED_DOSSIER_FIELDS
        if not _has_value(dossier.get(field))
    ]
    review_status = dossier.get("review_status")
    if review_status not in {"reviewed", "approved"}:
        errors.append("dossier review_status must be reviewed or approved")
    if dossier.get("protected_expression_excluded") is not True:
        errors.append("protected_expression_excluded must be explicitly confirmed")
    if target_status == "approved_production_candidate":
        if review_status != "approved":
            errors.append("approved candidate requires an approved dossier")
        confidence = candidate.get("classification_confidence")
        if not isinstance(confidence, (int, float)) or confidence < MIN_APPROVAL_CONFIDENCE:
            errors.append(f"classification confidence must be at least {MIN_APPROVAL_CONFIDENCE}")
        if candidate.get("classification_review_status") not in {"reviewed", "approved"}:
            errors.append("classification must receive human review before approval")
    return errors


def _dossier_shell(candidate_id: str, source_title: str, reference_path: str | None) -> dict:
    """Create an intentionally blank shell; source references require human research."""
    return {
        "candidate_id": candidate_id,
        "source_title": source_title,
        "reference_path": reference_path,
        "status": "dossier_shell",
        "primary_bona_fide_sources": [],
        "chapter_verse_references": [],
        "factual_learning_objectives": [],
        "references_consulted": [],
        "protected_expression_excluded": None,
        "proposed_original_structure": None,
        "original_design_requirements": [],
        "reviewer": None,
        "review_status": "dossier_shell",
        "note": "Shell only. References and review decisions must not be inferred or fabricated.",
    }


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


@audited_curation_command("candidates")
def run_candidates(settings: Settings, *, limit: int | None = None) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    candidate_markers = ",".join("?" * len(CANDIDATE_TYPES))
    sql = f"""
        SELECT rc.resource_id, rc.term AS product_type, rc.confidence,
               rc.review_state AS automatic_review_state,
               r.title_original, rn.display_title, lf.relative_path
        FROM resource_classifications rc
        JOIN resources r ON r.resource_id = rc.resource_id
        LEFT JOIN resource_names rn ON rn.resource_id = r.resource_id
        {PREFERRED_LOCAL_FILE_JOIN}
        WHERE rc.dimension = 'production-opportunity'
          AND rc.term IN ({candidate_markers})
          AND r.removed_at IS NULL
        ORDER BY rc.confidence DESC
    """  # nosec B608 — fixed join and bind markers only
    params: tuple[object, ...] = CANDIDATE_TYPES
    if limit is not None:
        sql += " LIMIT ?"
        params = (*params, limit)
    rows = db.execute(sql, params)
    desired_candidate_ids = {
        _candidate_id(str(row["resource_id"]), str(row["product_type"])) for row in rows
    }

    export_root = settings.data_dir / "exports" / "bhava-candidates"
    meta_dir = export_root / "metadata"
    briefs_dir = export_root / "briefs"
    meta_dir.mkdir(parents=True, exist_ok=True)
    briefs_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    exported = 0
    removed = 0
    stale_candidate_ids: list[str] = []
    with db.session() as conn:
        existing_generated = conn.execute(
            """
            SELECT pc.candidate_id, pc.status AS candidate_status,
                   sd.review_state AS dossier_status,
                   ic.similarity_status AS creation_status
            FROM production_candidates pc
            LEFT JOIN source_dossiers sd ON sd.candidate_id = pc.candidate_id
            LEFT JOIN independent_creation_records ic ON ic.candidate_id = pc.candidate_id
            """
        ).fetchall()
        for existing in existing_generated:
            candidate_id = str(existing["candidate_id"])
            if candidate_id in desired_candidate_ids:
                continue
            if existing["candidate_status"] not in GENERATED_CANDIDATE_STATUSES:
                continue
            if (
                existing["dossier_status"] is not None
                and existing["dossier_status"] not in GENERATED_DOSSIER_STATUSES
            ):
                continue
            if (
                existing["creation_status"] is not None
                and existing["creation_status"] not in GENERATED_CREATION_STATUSES
            ):
                continue
            conn.execute(
                "DELETE FROM independent_creation_records WHERE candidate_id = ?",
                (candidate_id,),
            )
            conn.execute(
                "DELETE FROM source_dossiers WHERE candidate_id = ?",
                (candidate_id,),
            )
            conn.execute(
                "DELETE FROM production_candidates WHERE candidate_id = ?",
                (candidate_id,),
            )
            stale_candidate_ids.append(candidate_id)
            removed += 1

        for row in rows:
            cid = _candidate_id(row["resource_id"], row["product_type"])
            payload = {
                "candidate_id": cid,
                "resource_id": row["resource_id"],
                "product_type": row["product_type"],
                "confidence": row["confidence"],
                "classification_confidence": row["confidence"],
                "classification_review_status": "unreviewed",
                "status": "candidate_proposal",
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
                  status = CASE
                    WHEN production_candidates.status IN ('proposed', 'candidate_proposal', 'dossier_shell')
                    THEN excluded.status ELSE production_candidates.status END,
                  payload_json = CASE
                    WHEN production_candidates.status IN ('proposed', 'candidate_proposal', 'dossier_shell')
                    THEN excluded.payload_json ELSE production_candidates.payload_json END
                """,
                (
                    cid,
                    row["resource_id"],
                    row["product_type"],
                    row["confidence"],
                    "candidate_proposal",
                    json.dumps(payload),
                    utc_now(),
                ),
            )
            dossier = _dossier_shell(cid, row["title_original"], row["relative_path"])
            conn.execute(
                """
                INSERT INTO source_dossiers(candidate_id, payload_json, review_state, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  payload_json = CASE
                    WHEN source_dossiers.review_state IN ('pending', 'dossier_shell')
                    THEN excluded.payload_json ELSE source_dossiers.payload_json END,
                  review_state = CASE
                    WHEN source_dossiers.review_state IN ('pending', 'dossier_shell')
                    THEN excluded.review_state ELSE source_dossiers.review_state END,
                  updated_at = CASE
                    WHEN source_dossiers.review_state IN ('pending', 'dossier_shell')
                    THEN excluded.updated_at ELSE source_dossiers.updated_at END
                """,
                (cid, json.dumps(dossier), "dossier_shell", utc_now()),
            )
            conn.execute(
                """
                INSERT INTO independent_creation_records(
                  candidate_id, payload_json, similarity_status, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  payload_json = CASE
                    WHEN independent_creation_records.similarity_status
                      IN ('not_started', 'independent_creation_not_started')
                    THEN excluded.payload_json ELSE independent_creation_records.payload_json END,
                  similarity_status = CASE
                    WHEN independent_creation_records.similarity_status
                      IN ('not_started', 'independent_creation_not_started')
                    THEN excluded.similarity_status
                    ELSE independent_creation_records.similarity_status END,
                  updated_at = CASE
                    WHEN independent_creation_records.similarity_status
                      IN ('not_started', 'independent_creation_not_started')
                    THEN excluded.updated_at ELSE independent_creation_records.updated_at END
                """,
                (
                    cid,
                    json.dumps(
                        {
                            "required": True,
                            "status": "independent_creation_not_started",
                        }
                    ),
                    "independent_creation_not_started",
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
            if _is_binary(meta_path) or _is_binary(brief_path):
                raise RuntimeError("candidate export produced a binary file")
            exported += 2

    for candidate_id in stale_candidate_ids:
        stem = candidate_id.replace("::", "--")
        for stale_path in (meta_dir / f"{stem}.json", briefs_dir / f"{stem}.md"):
            stale_path.unlink(missing_ok=True)

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
    return {"candidates": created, "export_files": exported, "removed_stale_shells": removed}
