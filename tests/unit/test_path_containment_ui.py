"""UI path containment tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.config import load_settings
from bhava_library.ui.app import create_app, is_allowed_original_path


@pytest.fixture
def settings(tmp_path: Path):
    s = load_settings()
    return s.model_copy(
        update={"paths": s.paths.model_copy(update={"data_dir": str(tmp_path / "data")})}
    )


def test_is_allowed_original_path(settings) -> None:
    (settings.data_dir / "originals" / "iskcon-education").mkdir(parents=True)
    settings.quarantine_dir.mkdir(parents=True)
    good = "data/originals/iskcon-education/documents/a.pdf"
    bad = "data/exports/secret.pdf"
    assert is_allowed_original_path(settings, good)
    assert not is_allowed_original_path(settings, bad)
    assert not is_allowed_original_path(settings, "../../../etc/passwd")


def test_path_check_endpoint(settings) -> None:
    pytest.importorskip("fastapi")
    (settings.data_dir / "originals" / "iskcon-education").mkdir(parents=True)
    app = create_app(settings)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    ok = client.get(
        "/path-check",
        params={"path": "data/originals/iskcon-education/documents/a.pdf"},
    )
    assert ok.status_code == 200
    denied = client.get("/path-check", params={"path": "data/exports/leak.pdf"})
    assert denied.status_code == 403
