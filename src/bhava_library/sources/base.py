"""Source adapter base protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from bhava_library.domain.models import ResolutionResult, ResourceCandidate
from bhava_library.infrastructure.http import PoliteHttpClient


class SourceAdapter(ABC):
    source_id: str
    name: str

    @abstractmethod
    def fetch_index(self, client: PoliteHttpClient) -> tuple[str, str, int]:
        """Return (html, final_url, http_status)."""

    @abstractmethod
    def parse_rows(self, html: str, *, base_url: str | None = None) -> list[ResourceCandidate]:
        """Parse resource candidates from HTML."""

    def parse_file(self, path: Path, *, base_url: str | None = None) -> list[ResourceCandidate]:
        return self.parse_rows(path.read_text(encoding="utf-8"), base_url=base_url)

    @abstractmethod
    def resolve_link(
        self,
        client: PoliteHttpClient,
        candidate: ResourceCandidate,
    ) -> ResolutionResult:
        """Resolve a candidate URL to a downloadable artifact when possible."""
