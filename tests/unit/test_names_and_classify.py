"""Names and classification behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.classify import classify_resource, run_classify
from bhava_library.curation.names import (
    build_resource_name_record,
    clean_display_title,
    run_names,
    slugify,
)
from bhava_library.infrastructure.database import Database


@pytest.fixture
def settings(tmp_path: Path):
    s = load_settings()
    s = s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    (s.data_dir / "catalog").mkdir(parents=True)
    db = Database(s.catalog_db)
    db.migrate()
    db.ensure_source("iskcon-education", "test", "https://example.org/", "iskcon_education")
    with db.session() as conn:
        conn.execute(
            """
            INSERT INTO resources(
              resource_id, source_id, source_row_key, title_original, title_normalized,
              media_type, language, original_url, profile, priority, status,
              first_seen_at, last_seen_at
            ) VALUES (
              'BL-TEST-001', 'iskcon-education', 'k1', 'Sunday School Coloring Page',
              'sunday school coloring page', 'document', 'English',
              'https://example.org/a.pdf', 'core', 10, 'verified',
              datetime('now'), datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at, read_only
            ) VALUES (
              'f1', 'BL-TEST-001', 'data/originals/iskcon-education/documents/coloring.pdf',
              100, 'abc', datetime('now'), 1
            )
            """
        )
    return s


def test_clean_display_title_and_slug() -> None:
    assert clean_display_title("Sunday_School-Coloring Page") == "Sunday School Coloring Page"
    assert slugify("Bhāva Gītā Lesson") == "bhava-gita-lesson"


def test_build_resource_name_record() -> None:
    rec = build_resource_name_record(
        "BL-TEST-001",
        "Sunday School Coloring Page",
        "data/originals/iskcon-education/documents/coloring.pdf",
    )
    assert rec["display_title"] == "Sunday School Coloring Page"
    assert rec["slug"] == "sunday-school-coloring-page"


def test_classify_resource_hits_form_and_program() -> None:
    hits = classify_resource(
        {
            "title_original": "Sunday School Coloring Page",
            "relative_path": "data/originals/iskcon-education/documents/coloring.pdf",
            "media_type": "document",
            "profile": "core",
            "language": "English",
        }
    )
    dims = {h.dimension: h.term for h in hits}
    assert dims["content-form"] == "coloring-page"
    assert dims["program-use"] == "sunday-school"


def test_run_names_and_classify(settings) -> None:
    names = run_names(settings)
    assert names["updated"] == 1
    rows = Database(settings.catalog_db).execute(
        "SELECT display_title FROM resource_names WHERE resource_id = 'BL-TEST-001'"
    )
    assert rows[0]["display_title"] == "Sunday School Coloring Page"

    result = run_classify(settings)
    assert result["classified"] == 1
    cls = Database(settings.catalog_db).execute(
        "SELECT dimension, term FROM resource_classifications WHERE resource_id = 'BL-TEST-001'"
    )
    assert any(r["dimension"] == "content-form" and r["term"] == "coloring-page" for r in cls)
