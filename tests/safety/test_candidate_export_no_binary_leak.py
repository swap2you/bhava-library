"""Candidate export must not include binaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.classify import run_classify
from bhava_library.curation.provenance import run_candidates
from bhava_library.infrastructure.database import Database


@pytest.fixture
def settings(tmp_path: Path):
    s = load_settings()
    s = s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
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
              'BL-CAND-001', 'iskcon-education', 'k1', 'Printable Coloring Page',
              'printable coloring page', 'https://example.org/a.pdf', 'core', 10, 'verified',
              datetime('now'), datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at, read_only
            ) VALUES (
              'f1', 'BL-CAND-001', 'data/originals/iskcon-education/documents/coloring.pdf',
              100, 'abc', datetime('now'), 1
            )
            """
        )
    return s


def test_candidate_export_metadata_only(settings) -> None:
    run_classify(settings)
    result = run_candidates(settings)
    assert result["candidates"] >= 1
    export_root = settings.data_dir / "exports" / "bhava-candidates"
    for path in export_root.rglob("*"):
        if path.is_file():
            assert path.suffix in {".json", ".md"}
            content = path.read_bytes()
            assert not content.startswith(b"%PDF")
            assert b"PK\x03\x04" not in content
