"""Git safety tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_gitignore_blocks_data_and_binaries() -> None:
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/data/**" in text or "data/**" in text
    for ext in (".pdf", ".mp3", ".zip", ".sqlite3", ".part"):
        assert ext in text


def test_cursorignore_blocks_binaries() -> None:
    text = (ROOT / ".cursorignore").read_text(encoding="utf-8")
    assert "data/**" in text
    assert "**/*.pdf" in text


def test_binary_guard_script_rejects_pdf(tmp_path: Path) -> None:
    import importlib.util

    path = ROOT / "scripts" / "precommit_binary_guard.py"
    spec = importlib.util.spec_from_file_location("precommit_binary_guard", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF")
    assert mod.main([str(pdf)]) == 1
