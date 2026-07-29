"""Ensure curation never mutates originals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.curation.classify import run_classify
from bhava_library.curation.enrich import run_enrich
from bhava_library.curation.names import run_names
from bhava_library.infrastructure.database import Database


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@pytest.fixture
def settings_with_original(tmp_path: Path):
    s = load_settings()
    s = s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    docs = s.data_dir / "originals" / "iskcon-education" / "documents"
    docs.mkdir(parents=True)
    pdf = docs / "lesson.pdf"
    pdf.write_bytes(b"%PDF-1.4 immutable original")
    before = _sha256(pdf)

    snap_dir = s.data_dir / "snapshots" / "pre-curation-test"
    snap_dir.mkdir(parents=True)
    rel = "data/originals/iskcon-education/documents/lesson.pdf"
    inventory = {
        "snapshot_id": "pre-curation-test",
        "files": [
            {
                "resource_id": "BL-IMM-001",
                "relative_path": rel,
                "size_bytes": pdf.stat().st_size,
                "sha256": before,
                "on_disk": True,
            }
        ],
    }
    (snap_dir / "ORIGINAL_INVENTORY.json").write_text(json.dumps(inventory), encoding="utf-8")

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
              'BL-IMM-001', 'iskcon-education', 'k1', 'Krishna Coloring Worksheet',
              'krishna coloring worksheet', 'https://example.org/a.pdf', 'core', 10, 'verified',
              datetime('now'), datetime('now')
            )
            """
        )
        conn.execute(
            """
            INSERT INTO local_files(
              file_id, resource_id, relative_path, size_bytes, sha256, verified_at, read_only
            ) VALUES ('f1', 'BL-IMM-001', ?, ?, ?, datetime('now'), 1)
            """,
            (rel, pdf.stat().st_size, before),
        )
    return s, pdf, before


def test_no_original_mutation_after_curation(settings_with_original) -> None:
    settings, pdf, before = settings_with_original
    run_names(settings)
    run_enrich(settings)
    run_classify(settings)
    assert _sha256(pdf) == before
    assert pdf.read_bytes() == b"%PDF-1.4 immutable original"
