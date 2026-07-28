"""Scan integration with fixture HTML."""

from __future__ import annotations

from pathlib import Path

from bhava_library.config import load_settings
from bhava_library.services.scan import run_scan

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "iskcon_education" / "sample.html"


def test_scan_fixture(tmp_path: Path) -> None:
    settings = load_settings()
    settings = settings.model_copy(
        update={"paths": settings.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )
    html = FIXTURE.read_text(encoding="utf-8")
    summary = run_scan(settings, html=html)
    assert summary.row_count == 12
    assert summary.html_sha256
