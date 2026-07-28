"""Parser unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from bhava_library.domain.enums import AcquisitionProfile
from bhava_library.domain.errors import SourceDriftError
from bhava_library.sources.iskcon_education import IskconEducationSourceAdapter

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "iskcon_education" / "sample.html"


def test_fixture_row_count() -> None:
    adapter = IskconEducationSourceAdapter()
    rows = adapter.parse_file(FIXTURE)
    assert len(rows) == 12


def test_taxonomy_and_unicode() -> None:
    adapter = IskconEducationSourceAdapter()
    rows = adapter.parse_file(FIXTURE)
    lesson = next(r for r in rows if "Lesson Plan" in r.title_original)
    assert "worksheet" in lesson.taxonomy_slugs
    assert "Rāma" in (lesson.theme or "") or "rama" in lesson.taxonomy_slugs


def test_profiles_audio_video_core() -> None:
    adapter = IskconEducationSourceAdapter()
    rows = {r.title_original: r for r in adapter.parse_file(FIXTURE)}
    assert rows["Audio Story"].profile == AcquisitionProfile.AUDIO
    assert rows["Video Clip"].profile == AcquisitionProfile.VIDEO
    assert rows["Sample Curriculum PDF"].profile == AcquisitionProfile.CORE


def test_deterministic_ids() -> None:
    adapter = IskconEducationSourceAdapter()
    a = adapter.parse_file(FIXTURE)
    b = adapter.parse_file(FIXTURE)
    assert [r.resource_id for r in a] == [r.resource_id for r in b]
    assert all(r.resource_id.startswith("BL-IE-") for r in a)


def test_duplicate_url_distinct_ids() -> None:
    adapter = IskconEducationSourceAdapter()
    rows = adapter.parse_file(FIXTURE)
    pdfs = [r for r in rows if r.original_url.endswith("curriculum.pdf")]
    assert len(pdfs) == 2
    assert pdfs[0].resource_id != pdfs[1].resource_id


def test_structure_drift() -> None:
    adapter = IskconEducationSourceAdapter()
    with pytest.raises(SourceDriftError):
        adapter.parse_rows("<html><body>no table</body></html>")


def test_empty_cells_row() -> None:
    adapter = IskconEducationSourceAdapter()
    rows = adapter.parse_file(FIXTURE)
    empty = next(r for r in rows if r.title_original == "Empty Cells Row")
    assert empty.original_url.startswith("urn:")
    assert "missing_url" in empty.parser_warnings
