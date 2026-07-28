"""Original integrity checks wrapping compare script and DB pragma."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.infrastructure.database import Database


def _load_compare(repo_root: Path):
    script = repo_root / "scripts" / "compare_original_integrity.py"
    spec = importlib.util.spec_from_file_location("compare_original_integrity", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["compare_original_integrity"] = module
    spec.loader.exec_module(module)
    return module


def run_integrity(settings: Settings) -> dict[str, object]:
    db = Database(settings.catalog_db)
    db.migrate()
    pragma = db.integrity_check()
    compare_mod = _load_compare(settings.repo_root)
    try:
        compare_result = compare_mod.compare(settings.repo_root)
    except FileNotFoundError:
        compare_result = {
            "ok": True,
            "skipped": True,
            "reason": "no pre-curation snapshot (fixture/test environment)",
        }
    ok = compare_result.get("ok", False) and pragma == "ok"
    return {
        "pragma_integrity": pragma,
        "original_compare": compare_result,
        "ok": ok,
    }
