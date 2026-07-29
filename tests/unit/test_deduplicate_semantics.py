"""Duplicate grouping must preserve empty/truncated source semantics."""

from __future__ import annotations

import json
from pathlib import Path

from bhava_library.config import load_settings
from bhava_library.infrastructure.database import Database
from bhava_library.services.deduplicate import run_deduplicate


def test_duplicate_kinds_and_reacquisition_queue(tmp_path: Path) -> None:
    settings = load_settings()
    settings = settings.model_copy(
        update={"paths": settings.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    db = Database(settings.catalog_db)
    db.migrate()
    db.ensure_source("test", "Test", "https://example.org/", "test")
    fixtures = (
        ("empty-a", 0, "empty-hash"),
        ("empty-b", 0, "empty-hash"),
        ("tiny-a", 3, "tiny-hash"),
        ("tiny-b", 3, "tiny-hash"),
        ("content-a", 1024, "content-hash"),
        ("content-b", 1024, "content-hash"),
        ("empty-single", 0, "single-empty-hash"),
    )
    with db.session() as conn:
        for resource_id, size_bytes, digest in fixtures:
            conn.execute(
                """
                INSERT INTO resources(
                  resource_id, source_id, source_row_key, title_original, original_url,
                  status, first_seen_at, last_seen_at
                ) VALUES (
                  ?, 'test', ?, ?, ?, 'verified', datetime('now'), datetime('now')
                )
                """,
                (
                    resource_id,
                    resource_id,
                    f"Source work {resource_id}",
                    f"https://example.org/{resource_id}",
                ),
            )
            conn.execute(
                """
                INSERT INTO local_files(
                  file_id, resource_id, relative_path, size_bytes, sha256,
                  verified_at, read_only
                ) VALUES (?, ?, ?, ?, ?, datetime('now'), 1)
                """,
                (
                    f"file-{resource_id}",
                    resource_id,
                    f"data/originals/{resource_id}.bin",
                    size_bytes,
                    digest,
                ),
            )

    result = run_deduplicate(settings)
    assert result == {
        "groups": 3,
        "linked": 3,
        "duplicate_content_groups": 1,
        "empty_collision_groups": 1,
        "truncated_collision_groups": 1,
        "reacquisition_queue": 5,
    }

    kinds = {
        row["resource_id"]: row["duplicate_kind"]
        for row in db.execute(
            "SELECT resource_id, duplicate_kind FROM local_files ORDER BY resource_id"
        )
    }
    assert kinds["empty-a"] == "empty-source-collision"
    assert kinds["empty-b"] == "empty-source-collision"
    assert kinds["tiny-a"] == "truncated-source-collision"
    assert kinds["tiny-b"] == "truncated-source-collision"
    assert kinds["content-a"] == "duplicate-content"
    assert kinds["content-b"] == "duplicate-content"
    assert kinds["empty-single"] is None

    report_path = settings.data_dir / "derived" / "reports" / "reacquisition_queue.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["queue_count"] == 5
    assert report["delete_recommendations"] == 0
    assert all(item["delete_duplicate"] is False for item in report["items"])
    assert {item["resource_id"] for item in report["items"]} == {
        "empty-a",
        "empty-b",
        "tiny-a",
        "tiny-b",
        "empty-single",
    }
