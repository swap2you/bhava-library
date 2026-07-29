"""Views must not copy originals."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.classify import run_classify
from bhava_library.curation.names import run_names
from bhava_library.curation.views import _write_html, run_build_views
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
    s._pdf_path = pdf  # type: ignore[attr-defined]
    s._before_hash = before_hash  # type: ignore[attr-defined]
    return s


def test_views_write_metadata_only(settings) -> None:
    run_names(settings)
    run_classify(settings)
    result = run_build_views(settings)
    assert result["resources"] == 1

    views_root = settings.data_dir / "views"
    assert views_root.exists()
    for path in views_root.rglob("*"):
        assert path.suffix in {".json", ".csv", ".md", ".html", ""}
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "%PDF" not in text

    assert sha256_file(settings._pdf_path) == settings._before_hash  # type: ignore[attr-defined]
    assert not (views_root / "originals").exists()


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
