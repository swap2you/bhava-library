"""Names, classification rules, and idempotency tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.classify import classify_resource, run_classify
from bhava_library.curation.names import build_resource_name_record, run_names
from bhava_library.curation.sunday_school import run_sunday_school
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
        for rid, title, path, media_type, media_format, language, theme in (
            (
                "BL-TEST-001",
                "Sunday School Coloring Book for Ages 4-7",
                "data/originals/iskcon-education/documents/coloring-book.pdf",
                "Documents",
                "PDF",
                None,
                "Janmastami Krishna",
            ),
            (
                "BL-TEST-002",
                "Bal Gopal Maze and Matching Activity",
                "data/originals/iskcon-education/documents/maze.pdf",
                "Documents",
                "PDF",
                "English",
                "Balarama",
            ),
            (
                "BL-TEST-003",
                "Damodara Class Curriculum Syllabus",
                "data/originals/iskcon-education/documents/curriculum.pdf",
                "Curriculum",
                "Documents",
                "",
                "Damodara",
            ),
        ):
            conn.execute(
                """
                INSERT INTO resources(
                  resource_id, source_id, source_row_key, title_original, title_normalized,
                  media_type, media_format, theme, language, original_url, profile, priority,
                  status, first_seen_at, last_seen_at
                ) VALUES (
                  ?, 'iskcon-education', ?, ?, ?, ?, ?, ?, ?,
                  'https://example.org/a.pdf', 'core', 10, 'verified',
                  datetime('now'), datetime('now')
                )
                """,
                (rid, rid, title, title.lower(), media_type, media_format, theme, language),
            )
            conn.execute(
                """
                INSERT INTO local_files(
                  file_id, resource_id, relative_path, size_bytes, sha256, verified_at, read_only
                ) VALUES (?, ?, ?, 100, 'abc', datetime('now'), 1)
                """,
                (f"f-{rid}", rid, path),
            )
            conn.execute(
                """
                INSERT INTO technical_metadata(resource_id, payload_json, extracted_at, extractor_version)
                VALUES (?, ?, datetime('now'), 'test')
                """,
                (rid, '{"extension":".pdf","mime_guess":"application/pdf"}'),
            )
    return s


def test_coloring_book_before_page_and_unknown_language() -> None:
    book = classify_resource(
        {
            "title_original": "Coloring Book of Krishna Pastimes",
            "relative_path": "data/originals/iskcon-education/documents/book.pdf",
            "media_type": "Documents",
            "media_format": "PDF",
            "profile": "core",
            "language": None,
            "theme": "Krishna",
            "source_label": "Ministry",
        }
    )
    forms = [h.term for h in book if h.dimension == "content-form"]
    assert forms == ["coloring-book"]
    language = [h for h in book if h.dimension == "language"][0]
    assert language.term == "unknown"
    assert language.confidence < 0.55

    page = classify_resource(
        {
            "title_original": "Coloring Page Sheet",
            "relative_path": "x.pdf",
            "media_type": "Documents",
            "media_format": "PDF",
            "language": "English",
        }
    )
    assert [h.term for h in page if h.dimension == "content-form"] == ["coloring-page"]


def test_multi_label_topic_festival_and_person() -> None:
    hits = classify_resource(
        {
            "title_original": "Janmastami Krishna and Balarama Drama Script",
            "relative_path": "data/originals/iskcon-education/documents/drama.pdf",
            "media_type": "Documents",
            "media_format": "PDF",
            "theme": "Festival",
            "language": "English",
        }
    )
    topics = {h.term for h in hits if h.dimension == "topic"}
    festivals = {h.term for h in hits if h.dimension == "festival"}
    persons = {h.term for h in hits if h.dimension == "person"}
    forms = {h.term for h in hits if h.dimension == "content-form"}
    assert "krishna" in topics
    assert "balarama" in topics or "balarama" in persons
    assert "janmastami" in festivals
    assert "drama-script" in forms


def test_display_filename_uses_known_dimensions_only() -> None:
    rec = build_resource_name_record(
        "BL-TEST-001",
        "Sunday School Coloring Book",
        "data/originals/iskcon-education/documents/coloring-book.pdf",
        {
            "content-form": ["coloring-book"],
            "audience": ["ages-4-7"],
            "language": ["english"],
        },
    )
    assert rec["display_filename"] == (
        "Sunday School Coloring Book — Coloring Book — Ages 4-7 — English — BL-TEST-001.pdf"
    )
    assert "unknown" not in str(rec["display_filename"]).lower()


def test_classify_and_sunday_school_are_idempotent(settings) -> None:
    first = run_classify(settings)
    second = run_classify(settings)
    assert first["labels"] == second["labels"]

    db = Database(settings.catalog_db)
    class_count_1 = db.execute("SELECT COUNT(*) AS n FROM resource_classifications")[0]["n"]
    evidence_count_1 = db.execute("SELECT COUNT(*) AS n FROM classification_evidence")[0]["n"]
    class_rows_1 = [
        (r["resource_id"], r["dimension"], r["term"], r["confidence"], r["review_state"])
        for r in db.execute(
            "SELECT resource_id, dimension, term, confidence, review_state "
            "FROM resource_classifications ORDER BY 1,2,3"
        )
    ]
    evidence_rows_1 = [
        (
            r["resource_id"],
            r["dimension"],
            r["term"],
            r["classifier"],
            r["excerpt"],
            r["confidence"],
        )
        for r in db.execute(
            "SELECT resource_id, dimension, term, classifier, excerpt, confidence "
            "FROM classification_evidence ORDER BY 1,2,3,4"
        )
    ]

    run_classify(settings)
    assert db.execute("SELECT COUNT(*) AS n FROM resource_classifications")[0]["n"] == class_count_1
    assert (
        db.execute("SELECT COUNT(*) AS n FROM classification_evidence")[0]["n"] == evidence_count_1
    )
    class_rows_2 = [
        (r["resource_id"], r["dimension"], r["term"], r["confidence"], r["review_state"])
        for r in db.execute(
            "SELECT resource_id, dimension, term, confidence, review_state "
            "FROM resource_classifications ORDER BY 1,2,3"
        )
    ]
    evidence_rows_2 = [
        (
            r["resource_id"],
            r["dimension"],
            r["term"],
            r["classifier"],
            r["excerpt"],
            r["confidence"],
        )
        for r in db.execute(
            "SELECT resource_id, dimension, term, classifier, excerpt, confidence "
            "FROM classification_evidence ORDER BY 1,2,3,4"
        )
    ]
    assert class_rows_1 == class_rows_2
    assert evidence_rows_1 == evidence_rows_2

    map1 = run_sunday_school(settings)
    map2 = run_sunday_school(settings)
    assert map1["mappings"] == map2["mappings"]
    mapping_count = db.execute("SELECT COUNT(*) AS n FROM program_mappings")[0]["n"]
    run_sunday_school(settings)
    assert db.execute("SELECT COUNT(*) AS n FROM program_mappings")[0]["n"] == mapping_count
    programs = {r["program"] for r in db.execute("SELECT DISTINCT program FROM program_mappings")}
    assert {"sunday-school", "bal-gopal", "damodara"} & programs
    assert len(programs) >= 2

    names = run_names(settings)
    assert names["updated"] == 3
    display = db.execute(
        "SELECT display_filename FROM resource_names WHERE resource_id='BL-TEST-001'"
    )[0]["display_filename"]
    assert "BL-TEST-001.pdf" in display
    assert "Coloring Book" in display
