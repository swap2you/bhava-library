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
            (
                "BL-TEST-004",
                "Preschool Presentation",
                "data/originals/iskcon-education/documents/preschool-presentation.pdf",
                "Documents",
                "PDF",
                None,
                "",
            ),
            (
                "BL-TEST-005",
                "Curriculum Ages 9-12",
                "data/originals/iskcon-education/documents/ages-9-12.pdf",
                "Curriculum",
                "PDF",
                None,
                "",
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


def _content_form_hit(row: dict[str, object]):
    return next(hit for hit in classify_resource(row) if hit.dimension == "content-form")


@pytest.mark.parametrize("title", ["Comic", "Comics", "Comic Book"])
def test_comic_singular_plural_and_book_titles(title: str) -> None:
    hit = _content_form_hit(
        {
            "title_original": title,
            "relative_path": "data/originals/item.pdf",
            "media_type": "Documents",
            "media_format": "PDF",
        }
    )
    assert hit.term == "comic"
    assert hit.classifier == "title"


def test_comics_media_type_and_unrelated_words() -> None:
    media_hit = _content_form_hit(
        {
            "title_original": "Krishna Pastimes",
            "relative_path": "data/originals/item.pdf",
            "media_type": "Comics",
            "media_format": "Documents",
        }
    )
    assert media_hit.term == "comic"
    assert media_hit.classifier == "media_type"

    unrelated = _content_form_hit(
        {
            "title_original": "Comical Timing and Comicology",
            "relative_path": "data/originals/item.pdf",
            "media_type": "Documents",
            "media_format": "PDF",
        }
    )
    assert unrelated.term != "comic"


@pytest.mark.parametrize(
    ("row", "expected", "evidence_source"),
    [
        (
            {
                "title_original": "BG in Crossword Puzzles Book",
                "relative_path": "data/originals/bg.pdf",
                "media_type": "Curriculum",
            },
            "crossword",
            "title",
        ),
        (
            {
                "title_original": "Activity",
                "relative_path": "data/originals/AA wordsearch.rtf",
                "media_type": "Curriculum",
            },
            "word-search",
            "filename",
        ),
        (
            {
                "title_original": "Evening Kirtan",
                "relative_path": "data/originals/kirtan.doc",
                "media_type": "Play Scripts",
            },
            "kirtan",
            "title",
        ),
        (
            {
                "title_original": "Bhagavad Gita Course",
                "relative_path": "data/originals/course.bin",
                "media_type": "Curriculum",
            },
            "curriculum",
            "media_type",
        ),
        (
            {
                "title_original": "Govardhana Play",
                "relative_path": "data/originals/play.doc",
                "media_type": "Play Scripts",
            },
            "drama-script",
            "title",
        ),
    ],
)
def test_specific_forms_precede_broad_metadata(
    row: dict[str, object], expected: str, evidence_source: str
) -> None:
    hit = _content_form_hit(row)
    assert hit.term == expected
    assert hit.classifier == evidence_source


@pytest.mark.parametrize("form", ["coloring-page", "coloring-book"])
def test_coloring_forms_create_printable_proposals(form: str) -> None:
    title = form.replace("-", " ").title()
    hits = classify_resource({"title_original": title, "relative_path": "item.pdf"})
    opportunity = next(hit for hit in hits if hit.dimension == "production-opportunity")
    assert opportunity.term == "printable-candidate"


def test_comic_creates_original_comic_proposal() -> None:
    hits = classify_resource({"title_original": "Comics", "relative_path": "item.pdf"})
    opportunity = next(hit for hit in hits if hit.dimension == "production-opportunity")
    assert opportunity.term == "original-comic-candidate"


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
    preschool_youth = db.execute(
        """
        SELECT confidence, review_state, assumptions_json
        FROM program_mappings
        WHERE resource_id = 'BL-TEST-004' AND program = 'youth'
        """
    )
    assert len(preschool_youth) == 1
    assert preschool_youth[0]["review_state"] == "needs_review"
    assert preschool_youth[0]["confidence"] < 0.55
    assert "form-only-unverified-age" in preschool_youth[0]["assumptions_json"]
    verified_age = db.execute(
        """
        SELECT confidence, review_state, assumptions_json
        FROM program_mappings
        WHERE resource_id = 'BL-TEST-005' AND program = 'sunday-school'
        """
    )
    assert len(verified_age) == 1
    assert verified_age[0]["review_state"] == "auto_accepted"
    assert verified_age[0]["confidence"] >= 0.55
    assert "form-and-verified-age" in verified_age[0]["assumptions_json"]

    names = run_names(settings)
    assert names["updated"] == 5
    display = db.execute(
        "SELECT display_filename FROM resource_names WHERE resource_id='BL-TEST-001'"
    )[0]["display_filename"]
    assert "BL-TEST-001.pdf" in display
    assert "Coloring Book" in display
