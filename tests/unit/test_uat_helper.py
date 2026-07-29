"""Read-only curation UAT helper tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bhava_library.config import load_settings
from bhava_library.curation.views import run_build_views
from bhava_library.infrastructure.database import Database
from bhava_library.infrastructure.hashing import sha256_file

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "uat_curation.py"
_SPEC = importlib.util.spec_from_file_location("uat_curation", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["uat_curation"] = _MODULE
_SPEC.loader.exec_module(_MODULE)
run_uat = _MODULE.run_uat


def test_uat_helper_samples_and_reports_without_mutating_originals(tmp_path: Path) -> None:
    settings = load_settings().model_copy(update={"repo_root": tmp_path})
    original = settings.data_dir / "originals" / "iskcon-education" / "audio" / "story.mp3"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"ID3-reference")
    before = (original.stat().st_size, sha256_file(original))

    db = Database(settings.catalog_db)
    db.migrate()
    db.ensure_source("uat", "UAT", "https://example.org/", "test")
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO resources(
              resource_id, source_id, source_row_key, title_original, original_url,
              media_type, media_format, status, first_seen_at, last_seen_at
            ) VALUES (
              'BL-UAT-001', 'uat', 'one', 'Audio Story', 'https://example.org/story',
              'audio', 'audio/mpeg', 'verified', datetime('now'), datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256,
              quarantine_reason, read_only
            ) VALUES (
              'uat-file', 'BL-UAT-001',
              'data/quarantine/iskcon-education/audio/story.mp3',
              ?, ?, 'signature review', 1
            )
            """,
            before,
        )
        conn.execute(
            """
            INSERT INTO resource_classifications(
              resource_id, dimension, term, confidence, review_state, created_at
            ) VALUES (
              'BL-UAT-001', 'content-form', 'audio-story', 0.9,
              'needs_review', datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO technical_metadata(resource_id, payload_json, extracted_at)
            VALUES ('BL-UAT-001', '{"duration_seconds": 60}', datetime('now'))
            """
        )
        conn.execute(
            """
            INSERT INTO download_jobs(
              job_id, resource_id, batch_id, state, updated_at
            ) VALUES ('uat-job', 'BL-UAT-001', 'uat', 'failed', datetime('now'))
            """
        )

    exports = settings.data_dir / "exports" / "bhava-candidates"
    exports.mkdir(parents=True)
    candidate = exports / "candidate.md"
    candidate.write_text("# Metadata only\n", encoding="utf-8")
    run_build_views(settings)

    result = run_uat(settings.repo_root, sample_size=50)

    assert result["database_mode"] == "read-only"
    assert result["sample_returned"] == 1
    assert result["major_form_counts"]["audio-story"] == 1
    assert result["audio_metadata_sample"]
    assert result["quarantine_representation"]
    assert result["terminal_state_representation"] == [{"state": "failed", "job_count": 1}]
    assert not result["generated_view_errors"]
    assert result["ok"]
    assert (original.stat().st_size, sha256_file(original)) == before

    candidate.write_bytes(b"%PDF-1.7")
    violated = run_uat(settings.repo_root, sample_size=1)
    assert not violated["ok"]
    assert violated["candidate_export_binary_violations"]
