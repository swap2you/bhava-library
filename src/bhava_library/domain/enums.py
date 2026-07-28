"""Domain enumerations."""

from __future__ import annotations

from enum import StrEnum


class ResourceStatus(StrEnum):
    DISCOVERED = "discovered"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    INACCESSIBLE = "inaccessible"
    ESTIMATED = "estimated"
    SIZE_UNKNOWN = "size_unknown"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    DOWNLOADED = "downloaded"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    QUARANTINED = "quarantined"
    CORRUPT = "corrupt"
    INDEXED = "indexed"


class AcquisitionProfile(StrEnum):
    METADATA = "metadata"
    CORE = "core"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"
    ALL = "all"


class JobState(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    RETRYABLE = "retryable"
    TERMINAL_FAILURE = "terminal_failure"
    COMPLETE = "complete"


class ResolutionMethod(StrEnum):
    DIRECT_EXTENSION = "direct_extension"
    CONTENT_DISPOSITION = "content_disposition"
    FINAL_REDIRECT = "final_redirect"
    A_DOWNLOAD = "a_download"
    DOWNLOAD_BUTTON = "download_button"
    MEDIA_SOURCE = "media_source"
    IFRAME_EMBED = "iframe_embed"
    OBJECT_PDF = "object_pdf"
    WP_ATTACHMENT = "wp_attachment"
    NONE = "none"


# Valid status transitions (from -> allowed tos)
ALLOWED_TRANSITIONS: dict[ResourceStatus, frozenset[ResourceStatus]] = {
    ResourceStatus.DISCOVERED: frozenset(
        {
            ResourceStatus.RESOLVING,
            ResourceStatus.UNRESOLVED,
            ResourceStatus.INACCESSIBLE,
        }
    ),
    ResourceStatus.RESOLVING: frozenset(
        {
            ResourceStatus.RESOLVED,
            ResourceStatus.UNRESOLVED,
            ResourceStatus.INACCESSIBLE,
        }
    ),
    ResourceStatus.RESOLVED: frozenset(
        {
            ResourceStatus.ESTIMATED,
            ResourceStatus.SIZE_UNKNOWN,
            ResourceStatus.QUEUED,
            ResourceStatus.INACCESSIBLE,
        }
    ),
    ResourceStatus.UNRESOLVED: frozenset(
        {
            ResourceStatus.RESOLVING,
            ResourceStatus.RESOLVED,
            ResourceStatus.INACCESSIBLE,
        }
    ),
    ResourceStatus.INACCESSIBLE: frozenset({ResourceStatus.RESOLVING, ResourceStatus.RESOLVED}),
    ResourceStatus.ESTIMATED: frozenset({ResourceStatus.QUEUED, ResourceStatus.SIZE_UNKNOWN}),
    ResourceStatus.SIZE_UNKNOWN: frozenset({ResourceStatus.QUEUED, ResourceStatus.ESTIMATED}),
    ResourceStatus.QUEUED: frozenset(
        {
            ResourceStatus.DOWNLOADING,
            ResourceStatus.PAUSED,
            ResourceStatus.FAILED_RETRYABLE,
            ResourceStatus.FAILED_TERMINAL,
        }
    ),
    ResourceStatus.DOWNLOADING: frozenset(
        {
            ResourceStatus.DOWNLOADED,
            ResourceStatus.PAUSED,
            ResourceStatus.FAILED_RETRYABLE,
            ResourceStatus.FAILED_TERMINAL,
        }
    ),
    ResourceStatus.PAUSED: frozenset(
        {
            ResourceStatus.QUEUED,
            ResourceStatus.DOWNLOADING,
            ResourceStatus.FAILED_TERMINAL,
        }
    ),
    ResourceStatus.FAILED_RETRYABLE: frozenset(
        {
            ResourceStatus.QUEUED,
            ResourceStatus.DOWNLOADING,
            ResourceStatus.FAILED_TERMINAL,
            ResourceStatus.PAUSED,
        }
    ),
    ResourceStatus.FAILED_TERMINAL: frozenset({ResourceStatus.QUEUED, ResourceStatus.RESOLVING}),
    ResourceStatus.DOWNLOADED: frozenset({ResourceStatus.VERIFYING}),
    ResourceStatus.VERIFYING: frozenset(
        {
            ResourceStatus.VERIFIED,
            ResourceStatus.QUARANTINED,
            ResourceStatus.CORRUPT,
        }
    ),
    ResourceStatus.VERIFIED: frozenset({ResourceStatus.INDEXED}),
    ResourceStatus.QUARANTINED: frozenset({ResourceStatus.VERIFYING}),
    ResourceStatus.CORRUPT: frozenset({ResourceStatus.QUEUED, ResourceStatus.VERIFYING}),
    ResourceStatus.INDEXED: frozenset({ResourceStatus.VERIFIED}),
}


def validate_transition(current: ResourceStatus, new: ResourceStatus) -> bool:
    """Return True if the status transition is allowed."""
    if current == new:
        return True
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    return new in allowed
