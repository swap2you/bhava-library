"""Probe the ISKCON media library HTML structure."""

from __future__ import annotations

from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "snapshots" / "_probe.html"
OUT.parent.mkdir(parents=True, exist_ok=True)

UA = "BhavaLibrary/1.0 (+mailto:svarnagaurangdas@gmail.com)"


def main() -> None:
    r = httpx.get(
        "https://iskconeducation.org/media_library/",
        headers={"User-Agent": UA},
        follow_redirects=True,
        timeout=90.0,
    )
    print("status", r.status_code)
    print("final", r.url)
    print("len", len(r.text))
    OUT.write_text(r.text, encoding="utf-8")
    text = r.text
    for pat in ("<table", "dataTable", "thead", "tbody", "media_library"):
        print(pat, text.lower().count(pat.lower()))
    idx = text.lower().find("<table")
    snippet = text[idx : idx + 3000] if idx >= 0 else text[:3000]
    print("---snippet---")
    print(snippet)


if __name__ == "__main__":
    main()
