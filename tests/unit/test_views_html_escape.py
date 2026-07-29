"""Generated HTML escaping and view path safety."""

from __future__ import annotations

from pathlib import Path

from bhava_library.config import load_settings
from bhava_library.curation.views import _write_html, run_build_views
from bhava_library.infrastructure.database import Database
from bhava_library.infrastructure.hashing import sha256_file


def test_html_escapes_script_title(tmp_path: Path) -> None:
    path = tmp_path / "index.html"
    _write_html(
        path,
        'View <script>alert("test")</script>',
        [
            {
                "resource_id": "BL<script>",
                "display_title": '<script>alert("test")</script>',
                "relative_path": 'data/originals/x"<b>.pdf',
            }
        ],
    )
    text = path.read_text(encoding="utf-8")
    assert "<script>alert" not in text
    assert "&lt;script&gt;alert(&quot;test&quot;)&lt;/script&gt;" in text
    assert "BL&lt;script&gt;" in text
    assert "data/originals/x&quot;&lt;b&gt;.pdf" in text


def test_build_views_escapes_and_does_not_copy_originals(tmp_path: Path) -> None:
    settings = load_settings()
    settings = settings.model_copy(
        update={"paths": settings.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    orig = settings.data_dir / "originals" / "iskcon-education" / "documents"
    orig.mkdir(parents=True)
    pdf = orig / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    before = sha256_file(pdf)
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
              'BL-VIEW-001', 'iskcon-education', 'k1', '<script>alert("x")</script>',
              'script', 'https://example.org/a.pdf', 'core', 10, 'verified',
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
            ("data/originals/iskcon-education/documents/sample.pdf", pdf.stat().st_size, before),
        )
        conn.execute(
            """
            INSERT INTO resource_names(
              resource_id, display_title, display_filename, slug,
              ascii_aliases_json, alternate_titles_json, export_filename, updated_at
            ) VALUES (
              'BL-VIEW-001', '<script>alert("x")</script>', 'safe.pdf', 'script',
              '[]', '[]', 'safe.pdf', datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO resource_classifications(
              resource_id, dimension, term, confidence, source, rule_version, review_state, created_at
            ) VALUES (
              'BL-VIEW-001', 'content-form', 'worksheet', 0.9, 'rule', 'rules-v2.0',
              'auto_accepted', datetime('now')
            )
            """
        )
    result = run_build_views(settings)
    assert result["resources"] == 1
    html_files = list((settings.data_dir / "views").rglob("*.html"))
    assert html_files
    for path in html_files:
        text = path.read_text(encoding="utf-8")
        assert "<script>alert" not in text
        assert "&lt;script&gt;" in text
    assert sha256_file(pdf) == before
