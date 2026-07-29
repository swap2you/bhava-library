"""Dynamic Git provenance tests for pre-curation snapshots."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType


def _load_snapshot_module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "pre_curation_snapshot.py"
    spec = importlib.util.spec_from_file_location("pre_curation_snapshot_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_records_dynamic_git_provenance(tmp_path: Path, monkeypatch) -> None:
    module = _load_snapshot_module()
    outputs = {
        ("rev-parse", "HEAD"): "abc123\n",
        ("branch", "--show-current"): "feature/test\n",
        ("status", "--porcelain"): " M tracked.py\n",
    }

    def fake_run(command, **kwargs):
        assert command[0] == "git"
        assert kwargs["cwd"] == tmp_path
        assert kwargs["shell"] is False
        return subprocess.CompletedProcess(command, 0, outputs[tuple(command[1:])], "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    snapshot = module.create_pre_curation_snapshot(tmp_path)
    manifest = json.loads((snapshot / "ORIGINAL_INVENTORY.json").read_text(encoding="utf-8"))
    assert manifest["repo_commit"] == "abc123"
    assert manifest["branch"] == "feature/test"
    assert manifest["dirty_working_tree"] is True
    assert manifest["repository_root"] == str(tmp_path.resolve())
    assert manifest["git_warnings"] == []

    report = (tmp_path / "reports" / "PRE_CURATION_SNAPSHOT.md").read_text(encoding="utf-8")
    assert "feature/test" in report
    assert "abc123" in report
    assert "Dirty working tree: **True**" in report


def test_git_unavailable_records_unknown_and_warning(tmp_path: Path, monkeypatch) -> None:
    module = _load_snapshot_module()

    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git executable not found")

    monkeypatch.setattr(module.subprocess, "run", unavailable)
    provenance = module._git_provenance(tmp_path)
    assert provenance["repo_commit"] == "unknown"
    assert provenance["branch"] == "unknown"
    assert provenance["dirty_working_tree"] == "unknown"
    assert provenance["git_warnings"]
    assert all("unavailable" in warning for warning in provenance["git_warnings"])
