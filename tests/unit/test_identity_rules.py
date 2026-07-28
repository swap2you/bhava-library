"""Copyright rule identity regression."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cursor_copyright_rule_uses_svarna() -> None:
    text = (ROOT / ".cursor" / "rules" / "03-copyright.mdc").read_text(encoding="utf-8")
    assert "Svarna Gauranga Das" in text
    assert "svarnagaurangdas@gmail.com" in text
    # Obsolete spelling may appear only as an explicit "never use" warning.
    assert "Use `Svarna Gauranga Das`" in text or "Use `Svarna Gauranga Das`" in text.replace(
        "Use ", "Use "
    )
    assert "Never use the obsolete spelling" in text
