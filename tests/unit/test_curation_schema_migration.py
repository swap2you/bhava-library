"""Curation schema migration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.taxonomy_seed import TAXONOMY
from bhava_library.infrastructure.database import SCHEMA_VERSION, Database


@pytest.fixture
def curation_settings(tmp_path: Path):
    s = load_settings()
    return s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )


def test_schema_version_is_four() -> None:
    assert SCHEMA_VERSION == 4


def test_migration_creates_curation_tables(curation_settings) -> None:
    db = Database(curation_settings.catalog_db)
    db.migrate()
    rows = db.execute("SELECT version FROM schema_migrations ORDER BY version")
    versions = [r["version"] for r in rows]
    assert versions == [1, 2, 3, 4]
    indexes = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index' ORDER BY name")
    }
    assert "uq_classification_evidence_rule" in indexes
    assert "uq_program_mapping_version" in indexes
    mapping_columns = {row["name"] for row in db.execute("PRAGMA table_info(program_mappings)")}
    assert {"confidence", "review_state"} <= mapping_columns
    local_file_columns = {row["name"] for row in db.execute("PRAGMA table_info(local_files)")}
    assert {"duplicate_kind", "reacquisition_required"} <= local_file_columns

    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    }
    for name in (
        "taxonomy_relations",
        "resource_classifications",
        "classification_evidence",
        "classification_reviews",
        "resource_names",
        "technical_metadata",
        "educational_profiles",
        "program_mappings",
        "production_candidates",
        "source_dossiers",
        "independent_creation_records",
        "curation_runs",
        "curation_events",
        "taxonomy_terms",
        "resource_terms",
    ):
        assert name in tables


def test_seed_taxonomy_populates_terms(curation_settings) -> None:
    db = Database(curation_settings.catalog_db)
    db.migrate()
    count = db.execute("SELECT COUNT(*) AS n FROM taxonomy_terms")[0]["n"]
    expected = sum(len(v) for v in TAXONOMY.values())
    assert count == expected
