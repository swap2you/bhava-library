"""Taxonomy seed vocabulary tests."""

from __future__ import annotations

from bhava_library.curation.taxonomy_seed import RULE_VERSION, TAXONOMY, term_id


def test_rule_version_present() -> None:
    assert RULE_VERSION == "rules-v2.1"


def test_term_id_format() -> None:
    assert term_id("content-form", "worksheet") == "content-form:worksheet"


def test_required_dimensions_exist() -> None:
    for dim in (
        "content-form",
        "audience",
        "program-use",
        "topic",
        "person",
        "festival",
        "scripture",
        "language",
        "production-opportunity",
        "reference-boundary",
    ):
        assert dim in TAXONOMY
        assert len(TAXONOMY[dim]) > 0


def test_unknown_terms_where_expected() -> None:
    assert "unknown" in TAXONOMY["content-form"]
    assert "unknown" in TAXONOMY["audience"]
