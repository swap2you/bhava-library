"""Curation command audit records are machine events, not human reviews."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import Settings, load_settings
from bhava_library.curation.audit import audited_curation_command
from bhava_library.curation.classify import run_classify
from bhava_library.curation.enrich import run_enrich
from bhava_library.curation.integrity import run_integrity
from bhava_library.curation.provenance import run_candidates
from bhava_library.curation.sunday_school import run_sunday_school
from bhava_library.curation.views import run_build_views
from bhava_library.infrastructure.database import Database


def _settings(tmp_path: Path) -> Settings:
    settings = load_settings()
    return settings.model_copy(
        update={
            "repo_root": tmp_path,
            "paths": settings.paths.model_copy(update={"data_dir": str(tmp_path / "data")}),
        }
    )


def test_actual_curation_commands_record_runs_without_human_reviews(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    (settings.repo_root / "config").mkdir(parents=True)
    source_config = Path(__file__).resolve().parents[2] / "config" / "programs.toml"
    (settings.repo_root / "config" / "programs.toml").write_bytes(source_config.read_bytes())
    (settings.repo_root / "scripts").mkdir()
    compare_script = (
        Path(__file__).resolve().parents[2] / "scripts" / "compare_original_integrity.py"
    )
    (settings.repo_root / "scripts" / compare_script.name).write_bytes(compare_script.read_bytes())

    run_enrich(settings)
    run_classify(settings)
    run_sunday_school(settings)
    run_candidates(settings)
    run_build_views(settings)
    run_integrity(settings)

    db = Database(settings.catalog_db)
    runs = db.execute("SELECT kind, completed_at, stats_json FROM curation_runs ORDER BY kind")
    assert {row["kind"] for row in runs} == {
        "build-views",
        "candidates",
        "classify",
        "enrich",
        "integrity",
        "sunday-school",
    }
    assert all(row["completed_at"] and row["stats_json"] for row in runs)
    events = db.execute("SELECT kind, COUNT(*) AS count FROM curation_events GROUP BY kind")
    assert {row["kind"]: row["count"] for row in events} == {
        "completed": 6,
        "started": 6,
    }
    assert db.execute("SELECT COUNT(*) AS count FROM classification_reviews")[0]["count"] == 0
    assert db.execute("SELECT COUNT(*) AS count FROM taxonomy_relations")[0]["count"] == 0


def test_failed_curation_command_records_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    @audited_curation_command("forced-failure")
    def fail(_settings: Settings) -> dict[str, int]:
        raise RuntimeError("expected failure")

    with pytest.raises(RuntimeError, match="expected failure"):
        fail(settings)
    db = Database(settings.catalog_db)
    run = db.execute(
        "SELECT completed_at, stats_json FROM curation_runs WHERE kind = 'forced-failure'"
    )[0]
    assert run["completed_at"] is not None
    assert "expected failure" in run["stats_json"]
    events = db.execute(
        "SELECT kind FROM curation_events WHERE run_id = "
        "(SELECT run_id FROM curation_runs WHERE kind = 'forced-failure') ORDER BY id"
    )
    assert [row["kind"] for row in events] == ["started", "failed"]
