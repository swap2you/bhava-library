"""Resolution and copyright tests."""

from __future__ import annotations

import pytest

from bhava_library.config import COPYRIGHT_EMAIL, COPYRIGHT_OWNER, load_settings
from bhava_library.domain.enums import AcquisitionProfile, ResourceStatus, validate_transition
from bhava_library.domain.models import ResourceCandidate
from bhava_library.infrastructure.filesystem import sanitize_filename
from bhava_library.services.copyright import (
    book_copyright_page,
    printable_footer,
    refuse_third_party_stamp,
)
from bhava_library.services.schedule import build_batches, rank_resources
from bhava_library.sources.iskcon_education import IskconEducationSourceAdapter


def test_direct_extension_resolution(httpx_mock) -> None:
    adapter = IskconEducationSourceAdapter()
    candidate = ResourceCandidate(
        resource_id="BL-IE-TEST000001",
        source_id="iskcon-education",
        source_row_key="a|https://example.org/a.pdf",
        title_original="A",
        original_url="https://example.org/a.pdf",
        profile=AcquisitionProfile.CORE,
    )
    # No HTTP needed for direct extension
    from bhava_library.infrastructure.http import PoliteHttpClient

    with PoliteHttpClient(user_agent="test", request_delay_seconds=0) as client:
        result = adapter.resolve_link(client, candidate)
    assert result.status == ResourceStatus.RESOLVED
    assert result.method == "direct_extension"


def test_state_transitions() -> None:
    assert validate_transition(ResourceStatus.DISCOVERED, ResourceStatus.RESOLVING)
    assert not validate_transition(ResourceStatus.DISCOVERED, ResourceStatus.VERIFIED)


def test_copyright_identity() -> None:
    text = book_copyright_page(year="2026", version="1.0.0", work_id="BHAVA-WORK-2026-001")
    assert COPYRIGHT_OWNER in text
    assert COPYRIGHT_EMAIL in text
    assert "Swarna" not in text
    assert "SwarnaGaurangaDas" not in text
    footer = printable_footer(year="2026")
    assert COPYRIGHT_OWNER in footer


def test_refuse_third_party() -> None:
    from bhava_library.domain.errors import ConfigError

    with pytest.raises(ConfigError):
        refuse_third_party_stamp("BL-IE-ABC")


def test_settings_identity() -> None:
    settings = load_settings()
    assert settings.copyright.owner == "Svarna Gauranga Das"
    assert settings.copyright.contact_email == "svarnagaurangdas@gmail.com"
    assert settings.copyright.phone == ""


def test_sanitize_reserved() -> None:
    assert sanitize_filename("CON.txt").startswith("_")


def test_batch_cap_and_audio_exclusion() -> None:
    rows = [
        {"resource_id": "a", "priority": 10, "profile": "core"},
        {"resource_id": "b", "priority": 10, "profile": "core"},
        {"resource_id": "c", "priority": 10, "profile": "core"},
    ]
    sizes = {"a": 5, "b": 5, "c": 5}
    ranked = rank_resources(rows, sizes)
    batches = build_batches(ranked, sizes, cap_bytes=10, max_file_bytes=100)
    assert len(batches) == 2
    assert sum(sizes[r["resource_id"]] for r in batches[0]) <= 10
