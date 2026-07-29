"""Curation-phase snapshot helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bhava_library.config import Settings


def _load_snapshot(repo_root: Path):
    script = repo_root / "scripts" / "pre_curation_snapshot.py"
    spec = importlib.util.spec_from_file_location("pre_curation_snapshot", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pre_curation_snapshot"] = module
    spec.loader.exec_module(module)
    return module


def run_snapshot(settings: Settings) -> Path:
    mod = _load_snapshot(settings.repo_root)
    return mod.create_pre_curation_snapshot(settings.repo_root)
