"""UI path containment and faceted search tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.infrastructure.database import Database
from bhava_library.ui.app import create_app, is_allowed_original_path


@pytest.fixture
def settings(tmp_path: Path):
    s = load_settings()
    s = s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    (s.data_dir / "originals" / "iskcon-education" / "documents").mkdir(parents=True)
    s.quarantine_dir.mkdir(parents=True)
    db = Database(s.catalog_db)
    db.migrate()
    db.ensure_source("iskcon-education", "test", "https://example.org/", "iskcon_education")
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO resources(
              resource_id, source_id, source_row_key, title_original, title_normalized,
              media_type, media_format, original_url, profile, priority, status,
              first_seen_at, last_seen_at
            ) VALUES (
              'BL-UI-001', 'iskcon-education', 'k1', 'Krishna Worksheet',
              'krishna worksheet', 'Documents', 'PDF', 'https://example.org/a.pdf',
              'core', 10, 'verified', datetime('now'), datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at, read_only
            ) VALUES (
              'f1', 'BL-UI-001',
              'data/originals/iskcon-education/documents/a.pdf',
              10, 'abc', datetime('now'), 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO resource_names(
              resource_id, display_title, display_filename, slug,
              ascii_aliases_json, alternate_titles_json, export_filename, updated_at
            ) VALUES (
              'BL-UI-001', 'Krishna Worksheet', 'Krishna Worksheet — Worksheet — BL-UI-001.pdf',
              'krishna-worksheet', '[]', '[]', 'Krishna Worksheet - Worksheet - BL-UI-001.pdf',
              datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO resource_classifications(
              resource_id, dimension, term, confidence, source, rule_version, review_state, created_at
            ) VALUES
              ('BL-UI-001', 'content-form', 'worksheet', 0.9, 'rule', 'rules-v2.0',
               'needs_review', datetime('now')),
              ('BL-UI-001', 'topic', 'krishna', 0.88, 'rule', 'rules-v2.0',
               'auto_accepted', datetime('now'))
            """
        )
        conn.execute(
            """
            INSERT INTO classification_evidence(
              resource_id, dimension, term, classifier, excerpt, confidence, rule_version, created_at
            ) VALUES (
              'BL-UI-001', 'topic', 'krishna', 'regex', 'krishna', 0.88, 'rules-v2.0', datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO technical_metadata(resource_id, payload_json, extracted_at, extractor_version)
            VALUES ('BL-UI-001', '{"extraction_status":"partial"}', datetime('now'), 'test')
            """
        )
    return s


def test_is_allowed_original_path(settings) -> None:
    good = "data/originals/iskcon-education/documents/a.pdf"
    bad = "data/exports/secret.pdf"
    assert is_allowed_original_path(settings, good)
    assert not is_allowed_original_path(settings, bad)
    assert not is_allowed_original_path(settings, "../../../etc/passwd")


def test_path_check_endpoint(settings) -> None:
    pytest.importorskip("fastapi")
    app = create_app(settings)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    ok = client.get(
        "/path-check",
        params={"path": "data/originals/iskcon-education/documents/a.pdf"},
    )
    assert ok.status_code == 200
    denied = client.get("/path-check", params={"path": "data/exports/leak.pdf"})
    assert denied.status_code == 403


def test_faceted_search_and_detail_page(settings) -> None:
    pytest.importorskip("fastapi")
    app = create_app(settings)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    home = client.get("/", params={"content_form": "worksheet", "review_state": "needs_review"})
    assert home.status_code == 200
    assert "Krishna Worksheet" in home.text
    assert 'name="content_form"' in home.text
    assert 'name="production_opportunity"' in home.text

    detail = client.get("/resource/BL-UI-001")
    assert detail.status_code == 200
    assert "Technical metadata" in detail.text
    assert "extraction_status" in detail.text
    assert "Classification" in detail.text or "Classifications" in detail.text
    assert "krishna" in detail.text
    assert "Evidence" in detail.text
