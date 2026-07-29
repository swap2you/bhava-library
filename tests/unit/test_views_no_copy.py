"""Views must not copy originals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation import views as views_module
from bhava_library.curation.classify import run_classify
from bhava_library.curation.names import run_names
from bhava_library.curation.views import (
    VIEW_DIMENSIONS,
    _write_html,
    build_safe_view_slugs,
    run_build_views,
    safe_view_slug,
)
from bhava_library.infrastructure.database import Database
from bhava_library.infrastructure.hashing import sha256_file


@pytest.fixture
def settings(tmp_path: Path):
    s = load_settings()
    s = s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    orig = s.data_dir / "originals" / "iskcon-education" / "documents"
    orig.mkdir(parents=True)
    pdf = orig / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    before_hash = sha256_file(pdf)

    db = Database(s.catalog_db)
    db.migrate()
    db.ensure_source("iskcon-education", "test", "https://example.org/", "iskcon_education")
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO resources(
              resource_id, source_id, source_row_key, title_original, title_normalized,
              original_url, profile, priority, status, first_seen_at, last_seen_at
            ) VALUES (
              'BL-VIEW-001', 'iskcon-education', 'k1', 'Sample Worksheet',
              'sample worksheet', 'https://example.org/a.pdf', 'core', 10, 'verified',
              datetime('now'), datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at, read_only
            ) VALUES (
              'f1', 'BL-VIEW-001', ?, ?, ?, datetime('now'), 1
            )
            """,
            (
                "data/originals/iskcon-education/documents/sample.pdf",
                pdf.stat().st_size,
                before_hash,
            ),
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at,
              read_only, duplicate_of_file_id, quarantine_reason
            ) VALUES (
              'f0-quarantined', 'BL-VIEW-001',
              'data/quarantine/iskcon-education/documents/sample.pdf',
              ?, 'quarantined', datetime('now'), 1, 'f1', 'signature review'
            )
            """,
            (pdf.stat().st_size,),
        )
    s._pdf_path = pdf  # type: ignore[attr-defined]
    s._before_hash = before_hash  # type: ignore[attr-defined]
    return s


def test_views_write_metadata_only(settings) -> None:
    run_names(settings)
    run_classify(settings)
    dangerous_terms = ["../../outside", "/topic/name", r"C:\outside", "<script>", r"a\b"]
    db = Database(settings.catalog_db)
    with db.session() as conn:
        for term in dangerous_terms:
            conn.execute(
                """
                INSERT INTO resource_classifications(
                  resource_id, dimension, term, confidence, source, rule_version,
                  review_state, created_at
                ) VALUES (
                  'BL-VIEW-001', 'topic', ?, 0.5, 'test', 'test',
                  'needs_review', datetime('now')
                )
                """,
                (term,),
            )
    result = run_build_views(settings)
    assert result["resources"] == 1

    views_root = settings.data_dir / "views"
    assert views_root.exists()
    catalog = json.loads((views_root / "by-all" / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog) == 1
    assert catalog[0]["resource_id"] == "BL-VIEW-001"
    assert catalog[0]["relative_path"] == ("data/originals/iskcon-education/documents/sample.pdf")

    dimensions = ",".join("?" for _ in VIEW_DIMENSIONS)
    expected_terms = db.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM (
          SELECT DISTINCT dimension, term
          FROM resource_classifications
          WHERE dimension IN ({dimensions})
        )
        """,  # nosec B608 — fixed bind markers only
        VIEW_DIMENSIONS,
    )[0]["count"]
    assert result["artifacts"] == 4 + (4 * expected_terms)

    for index in views_root.glob("by-*/**/index.json"):
        records = json.loads(index.read_text(encoding="utf-8"))
        resource_ids = [record["resource_id"] for record in records]
        assert resource_ids == list(dict.fromkeys(resource_ids))

    term_slugs, collisions = build_safe_view_slugs(dangerous_terms)
    assert collisions == 1
    for term, slug in term_slugs.items():
        assert slug.startswith(safe_view_slug(term))
        output = (views_root / "by-topic" / slug).resolve()
        assert output.is_relative_to(views_root.resolve())
        assert output.is_dir()

    for path in views_root.rglob("*"):
        assert path.resolve().is_relative_to(views_root.resolve())
        assert path.suffix in {".json", ".csv", ".md", ".html", ""}
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "%PDF" not in text

    assert sha256_file(settings._pdf_path) == settings._before_hash  # type: ignore[attr-defined]
    assert not (views_root / "originals").exists()


def test_view_slug_collisions_are_detected_and_disambiguated() -> None:
    slugs, collisions = build_safe_view_slugs(["a/b", r"a\b"])
    assert collisions == 1
    assert slugs["a/b"] != slugs[r"a\b"]
    assert all("/" not in slug and "\\" not in slug for slug in slugs.values())


def test_full_rebuild_removes_stale_term_and_language_views(settings) -> None:
    run_names(settings)
    run_classify(settings)
    db = Database(settings.catalog_db)
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO resource_classifications(
              resource_id, dimension, term, confidence, source, rule_version,
              review_state, created_at
            ) VALUES
              ('BL-VIEW-001', 'topic', 'obsolete-term', 0.8, 'test', 'test',
               'auto_accepted', datetime('now')),
              ('BL-VIEW-001', 'language', 'english', 0.8, 'test', 'test',
               'auto_accepted', datetime('now'))
            """
        )
    run_build_views(settings)
    root = settings.data_dir / "views"
    assert (root / "by-topic" / "obsolete-term").is_dir()
    assert (root / "by-language" / "english").is_dir()

    with db.session() as conn:
        conn.execute(
            """
            DELETE FROM resource_classifications
            WHERE resource_id = 'BL-VIEW-001'
              AND ((dimension = 'topic' AND term = 'obsolete-term')
                OR (dimension = 'language' AND term = 'english'))
            """
        )
    run_build_views(settings)
    assert not (root / "by-topic" / "obsolete-term").exists()
    assert not (root / "by-language" / "english").exists()

    unknown_count = db.execute(
        """
        SELECT COUNT(DISTINCT resource_id) AS count
        FROM resource_classifications
        WHERE dimension = 'language' AND term = 'unknown'
        """
    )[0]["count"]
    unknown_records = json.loads(
        (root / "by-language" / "unknown" / "index.json").read_text(encoding="utf-8")
    )
    assert len(unknown_records) == unknown_count


def test_failed_rebuild_does_not_publish_partial_tree(settings, monkeypatch) -> None:
    run_names(settings)
    run_classify(settings)
    run_build_views(settings)
    root = settings.data_dir / "views"
    before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }

    def fail_validation(*args, **kwargs) -> None:
        raise ValueError("forced validation failure")

    monkeypatch.setattr(views_module, "_validate_view_tree", fail_validation)
    with pytest.raises(ValueError, match="forced validation failure"):
        run_build_views(settings)

    after = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    assert after == before
    assert not list(settings.data_dir.glob(".views-staging-*"))
    assert not list(settings.data_dir.glob(".views-backup-*"))


def test_generated_html_escapes_title_ids_terms_paths_and_labels(tmp_path: Path) -> None:
    output = tmp_path / "view.html"
    _write_html(
        output,
        "<script>alert('title')</script>",
        [
            {
                "display_title": "<img src=x onerror=alert('label')>",
                "resource_id": "id<&>",
                "relative_path": "data/originals/<script>.pdf",
                "term": "<b>term</b>",
            }
        ],
    )
    rendered = output.read_text(encoding="utf-8")
    assert "<script>" not in rendered
    assert "<img" not in rendered
    assert "<b>term</b>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "id&lt;&amp;&gt;" in rendered
    assert "data/originals/&lt;script&gt;.pdf" in rendered
