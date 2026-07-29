"""Candidate shell generation and promotion validation tests."""

from __future__ import annotations

import json
from pathlib import Path

from bhava_library.config import load_settings
from bhava_library.curation.provenance import run_candidates, validate_candidate_promotion
from bhava_library.infrastructure.database import Database


def _complete_dossier(review_status: str = "approved") -> dict:
    return {
        "primary_bona_fide_sources": ["human-entered source"],
        "chapter_verse_references": ["human-entered chapter/verse"],
        "factual_learning_objectives": ["human-reviewed factual objective"],
        "references_consulted": ["human-entered reference"],
        "protected_expression_excluded": True,
        "proposed_original_structure": "human-authored structure",
        "original_design_requirements": ["independent visual design"],
        "reviewer": "Human Reviewer",
        "review_status": review_status,
    }


def test_shell_cannot_be_promoted_and_approval_requires_human_review() -> None:
    candidate = {
        "classification_confidence": 0.9,
        "classification_review_status": "unreviewed",
    }
    shell_errors = validate_candidate_promotion(
        candidate, {"review_status": "dossier_shell"}, target_status="reviewed_dossier"
    )
    assert any("primary_bona_fide_sources" in error for error in shell_errors)
    assert any("review_status" in error for error in shell_errors)

    unreviewed_errors = validate_candidate_promotion(
        candidate,
        _complete_dossier(),
        target_status="approved_production_candidate",
    )
    assert "classification must receive human review before approval" in unreviewed_errors

    candidate["classification_review_status"] = "approved"
    candidate["classification_confidence"] = 0.4
    low_confidence_errors = validate_candidate_promotion(
        candidate,
        _complete_dossier(),
        target_status="approved_production_candidate",
    )
    assert any("confidence" in error for error in low_confidence_errors)

    candidate["classification_confidence"] = 0.9
    assert (
        validate_candidate_promotion(
            candidate,
            _complete_dossier(),
            target_status="approved_production_candidate",
        )
        == []
    )
    incomplete = _complete_dossier()
    incomplete["protected_expression_excluded"] = False
    assert "protected_expression_excluded must be explicitly confirmed" in (
        validate_candidate_promotion(
            candidate,
            incomplete,
            target_status="approved_production_candidate",
        )
    )


def test_rerun_remediates_legacy_shells_and_preserves_reviews(tmp_path: Path) -> None:
    settings = load_settings()
    settings = settings.model_copy(
        update={"paths": settings.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    db = Database(settings.catalog_db)
    db.migrate()
    db.ensure_source("iskcon-education", "test", "https://example.org/", "iskcon_education")
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO resources(
              resource_id, source_id, source_row_key, title_original, title_normalized,
              original_url, profile, priority, status, first_seen_at, last_seen_at
            ) VALUES (
              'BL-PROV-001', 'iskcon-education', 'one', 'Human Review Needed',
              'human review needed', 'https://example.org/item', 'core', 1, 'verified',
              datetime('now'), datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO resource_classifications(
              resource_id, dimension, term, confidence, source, rule_version,
              review_state, created_at
            ) VALUES (
              'BL-PROV-001', 'production-opportunity', 'activity-candidate', 0.9,
              'test', 'test', 'auto_accepted', datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at, read_only
            ) VALUES (
              'f1-primary', 'BL-PROV-001', 'data/originals/reference.pdf',
              10, 'primary', datetime('now'), 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at,
              read_only, duplicate_of_file_id, quarantine_reason
            ) VALUES (
              'f0-quarantine', 'BL-PROV-001', 'data/quarantine/reference.pdf',
              10, 'quarantine', datetime('now'), 1, 'f1-primary', 'signature review'
            )
            """
        )

    run_candidates(settings)
    first_candidate = db.execute("SELECT * FROM production_candidates")[0]
    first_payload = json.loads(first_candidate["payload_json"])
    assert first_payload["relative_path"] == "data/originals/reference.pdf"
    with db.session() as conn:
        conn.execute(
            "UPDATE production_candidates SET status = 'proposed' WHERE candidate_id = ?",
            (first_candidate["candidate_id"],),
        )
        conn.execute(
            "UPDATE source_dossiers SET review_state = 'pending' WHERE candidate_id = ?",
            (first_candidate["candidate_id"],),
        )
        conn.execute(
            """
            UPDATE independent_creation_records SET similarity_status = 'not_started'
            WHERE candidate_id = ?
            """,
            (first_candidate["candidate_id"],),
        )
    run_candidates(settings)
    candidate = db.execute("SELECT * FROM production_candidates")[0]
    dossier = db.execute("SELECT * FROM source_dossiers")[0]
    creation = db.execute("SELECT * FROM independent_creation_records")[0]
    assert candidate["status"] == "candidate_proposal"
    assert dossier["review_state"] == "dossier_shell"
    assert creation["similarity_status"] == "independent_creation_not_started"
    shell = json.loads(dossier["payload_json"])
    assert shell["primary_bona_fide_sources"] == []
    assert shell["chapter_verse_references"] == []
    assert shell["reviewer"] is None
    assert "%PDF" not in dossier["payload_json"]
    assert "PK\\x03\\x04" not in dossier["payload_json"]

    reviewed = _complete_dossier("reviewed")
    with db.session() as conn:
        conn.execute(
            "UPDATE production_candidates SET status = 'reviewed_dossier' WHERE candidate_id = ?",
            (candidate["candidate_id"],),
        )
        conn.execute(
            """
            UPDATE source_dossiers SET payload_json = ?, review_state = 'reviewed_dossier'
            WHERE candidate_id = ?
            """,
            (json.dumps(reviewed), candidate["candidate_id"]),
        )
    run_candidates(settings)
    preserved_candidate = db.execute("SELECT * FROM production_candidates")[0]
    preserved_dossier = db.execute("SELECT * FROM source_dossiers")[0]
    assert preserved_candidate["status"] == "reviewed_dossier"
    assert json.loads(preserved_dossier["payload_json"]) == reviewed
