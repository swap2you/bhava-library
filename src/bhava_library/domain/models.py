"""Domain models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from bhava_library.domain.enums import AcquisitionProfile, JobState, ResourceStatus


class ResourceCandidate(BaseModel):
    resource_id: str
    source_id: str
    source_row_key: str
    title_original: str
    title_normalized: str = ""
    level: str | None = None
    media_type: str | None = None
    media_format: str | None = None
    theme: str | None = None
    source_label: str | None = None
    language: str | None = None
    original_url: str
    taxonomy_slugs: list[str] = Field(default_factory=list)
    profile: AcquisitionProfile = AcquisitionProfile.UNKNOWN
    priority: int = 100
    status: ResourceStatus = ResourceStatus.DISCOVERED
    parser_warnings: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ResolutionResult(BaseModel):
    resource_id: str
    original_url: str
    resolved_url: str | None = None
    method: str = "none"
    evidence: str = ""
    confidence: float = 0.0
    status: ResourceStatus = ResourceStatus.UNRESOLVED
    http_status: int | None = None
    mime_type: str | None = None
    timestamp: datetime | None = None


class RemoteProbe(BaseModel):
    resource_id: str
    url: str
    final_url: str | None = None
    http_status: int | None = None
    mime_type: str | None = None
    content_length: int | None = None
    accept_ranges: bool = False
    etag: str | None = None
    last_modified: str | None = None
    probed_at: datetime | None = None
    size_known: bool = False


class DownloadJob(BaseModel):
    job_id: str
    resource_id: str
    batch_id: str
    state: JobState = JobState.PENDING
    url: str
    attempt_count: int = 0
    bytes_downloaded: int = 0
    expected_bytes: int | None = None
    part_path: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    sha256: str | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None


class EstimateSummary(BaseModel):
    profile: str
    total_candidates: int = 0
    resolved: int = 0
    unresolved: int = 0
    broken: int = 0
    known_bytes: int = 0
    unknown_size_count: int = 0
    deferred_audio: int = 0
    deferred_video: int = 0
    deferred_audio_bytes: int | None = None
    deferred_video_bytes: int | None = None
    free_disk_bytes: int = 0
    reserve_bytes: int = 0
    overhead_bytes: int = 0
    projected_free_bytes: int = 0
    batch_cap_bytes: int = 0
    first_batch_bytes: int = 0
    first_batch_count: int = 0
    pending_batch_count: int = 0
    safe_to_acquire: bool = False
    notes: list[str] = Field(default_factory=list)


class ScanSummary(BaseModel):
    source_id: str
    snapshot_id: str
    row_count: int
    new_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    types: dict[str, int] = Field(default_factory=dict)
    formats: dict[str, int] = Field(default_factory=dict)
    themes: dict[str, int] = Field(default_factory=dict)
    domains: dict[str, int] = Field(default_factory=dict)
    html_sha256: str = ""
    parser_version: str = ""
