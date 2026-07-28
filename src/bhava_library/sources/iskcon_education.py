"""ISKCON Ministry of Education Media Library source adapter."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from bhava_library.constants import (
    AUDIO_EXTENSIONS,
    DIRECT_FILE_EXTENSIONS,
    PARSER_VERSION,
    SOURCE_ID_ISKCON,
    VIDEO_EXTENSIONS,
)
from bhava_library.domain.enums import AcquisitionProfile, ResolutionMethod, ResourceStatus
from bhava_library.domain.errors import AccessRestrictedError, SourceDriftError
from bhava_library.domain.models import ResolutionResult, ResourceCandidate
from bhava_library.infrastructure.http import PoliteHttpClient
from bhava_library.infrastructure.mime import extension_of, is_audio_ext, is_video_ext
from bhava_library.sources.base import SourceAdapter

EXPECTED_VISIBLE_HEADERS = ("Name", "Level", "Type", "Format", "Theme", "Source")

CONTENT_PRIORITY_BOOST = {
    "curriculum": -5,
    "book": -4,
    "comics": -4,
    "comic": -4,
    "storybook": -4,
    "lesson": -3,
    "activity": -2,
    "printable": -2,
    "worksheet": -2,
    "article": -1,
}


def _normalize_title(title: str) -> str:
    text = unquote(title)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _cell_text(td: Tag | None) -> str:
    if td is None:
        return ""
    return td.get_text(" ", strip=True)


def _cell_slug(td: Tag | None) -> str | None:
    if td is None:
        return None
    tagged = td.find(attrs={"data-slug": True})
    if tagged and isinstance(tagged, Tag):
        slug = tagged.get("data-slug")
        return str(slug) if slug else None
    return None


def _deterministic_id(source_row_key: str) -> str:
    digest = hashlib.sha256(source_row_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"BL-IE-{digest}"


def classify_profile(
    *,
    media_type: str | None,
    media_format: str | None,
    url: str,
) -> AcquisitionProfile:
    ext = extension_of(url)
    blob = " ".join(filter(None, [media_type, media_format, ext])).lower()
    if is_audio_ext(ext) or "audio" in blob:
        return AcquisitionProfile.AUDIO
    if is_video_ext(ext) or "video" in blob:
        return AcquisitionProfile.VIDEO
    if ext in DIRECT_FILE_EXTENSIONS - AUDIO_EXTENSIONS - VIDEO_EXTENSIONS:
        return AcquisitionProfile.CORE
    if any(
        token in blob
        for token in (
            "document",
            "pdf",
            "epub",
            "comic",
            "curriculum",
            "worksheet",
            "book",
            "office",
            "spreadsheet",
            "image",
            "archive",
            "zip",
            "rar",
        )
    ):
        return AcquisitionProfile.CORE
    if not ext:
        # Landing pages often wrap documents; treat as core until resolved.
        return AcquisitionProfile.CORE
    return AcquisitionProfile.UNKNOWN


def compute_priority(
    *,
    profile: AcquisitionProfile,
    media_type: str | None,
    media_format: str | None,
    url: str,
) -> int:
    if profile == AcquisitionProfile.AUDIO:
        return 900
    if profile == AcquisitionProfile.VIDEO:
        return 950
    ext = extension_of(url)
    if ext in {".pdf", ".epub", ".txt", ".rtf", ".html", ".htm"}:
        base = 10
    elif ext in {".doc", ".docx", ".odt", ".ppt", ".pptx", ".odp"}:
        base = 20
    elif ext in {".xls", ".xlsx", ".ods", ".csv"}:
        base = 30
    elif ext in {".json", ".xml"}:
        base = 35
    elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        base = 40
    elif ext in {".zip", ".rar", ".7z"}:
        base = 50
    else:
        base = 60
    blob = " ".join(filter(None, [media_type, media_format])).lower()
    for token, boost in CONTENT_PRIORITY_BOOST.items():
        if token in blob:
            base += boost
            break
    return max(1, base)


class IskconEducationSourceAdapter(SourceAdapter):
    source_id = SOURCE_ID_ISKCON
    name = "ISKCON Ministry of Education Media Library"
    parser_version = PARSER_VERSION

    def __init__(self, index_url: str = "https://iskconeducation.org/media_library/") -> None:
        self.index_url = index_url

    def fetch_index(self, client: PoliteHttpClient) -> tuple[str, str, int]:
        response = client.get(self.index_url)
        return response.text, str(response.url), response.status_code

    def parse_rows(self, html: str, *, base_url: str | None = None) -> list[ResourceCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table.posts-data-table") or soup.find("table")
        if table is None or not isinstance(table, Tag):
            raise SourceDriftError("Source structure changed: no table found")

        headers = [th.get_text(" ", strip=True) for th in table.select("thead th")]
        visible = [h for h in headers if not h.lower().startswith("hf:")]
        missing = [h for h in EXPECTED_VISIBLE_HEADERS if h not in visible]
        if missing:
            raise SourceDriftError(
                f"Source structure changed: missing columns {missing}; found {visible}"
            )

        body = table.find("tbody")
        if body is None or not isinstance(body, Tag):
            raise SourceDriftError("Source structure changed: no tbody found")

        base = base_url or self.index_url
        candidates: list[ResourceCandidate] = []
        for row in body.find_all("tr", recursive=False):
            if not isinstance(row, Tag):
                continue
            parsed = self._parse_row(row, base=base)
            if parsed is not None:
                candidates.append(parsed)
        return candidates

    def _parse_row(self, row: Tag, *, base: str) -> ResourceCandidate | None:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 6:
            return None
        name_cell = cells[0]
        anchor = name_cell.find("a")
        title = _cell_text(name_cell)
        href = ""
        if isinstance(anchor, Tag) and anchor.get("href"):
            href = urljoin(base, str(anchor.get("href")))
        if not title and not href:
            return None

        level = _cell_text(cells[1]) or None
        media_type = _cell_text(cells[2]) or None
        media_format = _cell_text(cells[3]) or None
        theme = _cell_text(cells[4]) or None
        source_label = _cell_text(cells[5]) or None

        slugs: list[str] = []
        for idx in range(1, min(6, len(cells))):
            slug = _cell_slug(cells[idx])
            if slug:
                slugs.append(slug)
        for idx in range(6, len(cells)):
            slug_text = _cell_text(cells[idx])
            if slug_text:
                slugs.append(slug_text)

        warnings: list[str] = []
        if not href:
            warnings.append("missing_url")
            href = f"urn:bhava:missing:{_normalize_title(title)}"

        row_key = f"{_normalize_title(title)}|{href}"
        resource_id = _deterministic_id(row_key)
        profile = classify_profile(media_type=media_type, media_format=media_format, url=href)
        priority = compute_priority(
            profile=profile,
            media_type=media_type,
            media_format=media_format,
            url=href,
        )
        domain = urlparse(href).netloc.lower() if href.startswith("http") else ""

        post_id = None
        row_id = row.get("id")
        if isinstance(row_id, str) and row_id.startswith("post-row-"):
            post_id = row_id.removeprefix("post-row-")

        return ResourceCandidate(
            resource_id=resource_id,
            source_id=self.source_id,
            source_row_key=row_key,
            title_original=title,
            title_normalized=_normalize_title(title),
            level=level,
            media_type=media_type,
            media_format=media_format,
            theme=theme,
            source_label=source_label,
            original_url=href,
            taxonomy_slugs=slugs,
            profile=profile,
            priority=priority,
            status=ResourceStatus.DISCOVERED,
            parser_warnings=warnings,
            raw={
                "post_id": post_id,
                "source_domain": domain,
                "parser_version": self.parser_version,
            },
        )

    def resolve_link(
        self,
        client: PoliteHttpClient,
        candidate: ResourceCandidate,
    ) -> ResolutionResult:
        url = candidate.original_url
        now = datetime.now(UTC)
        if url.startswith("urn:"):
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=url,
                method=ResolutionMethod.NONE.value,
                evidence="missing original URL",
                confidence=0.0,
                status=ResourceStatus.UNRESOLVED,
                timestamp=now,
            )

        ext = extension_of(url)
        if ext in DIRECT_FILE_EXTENSIONS:
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=url,
                resolved_url=url,
                method=ResolutionMethod.DIRECT_EXTENSION.value,
                evidence=f"direct extension {ext}",
                confidence=0.95,
                status=ResourceStatus.RESOLVED,
                timestamp=now,
            )

        try:
            head = client.head(url)
        except AccessRestrictedError as exc:
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=url,
                method=ResolutionMethod.NONE.value,
                evidence=str(exc),
                confidence=0.0,
                status=ResourceStatus.INACCESSIBLE,
                timestamp=now,
            )
        except Exception as exc:  # noqa: BLE001 — recorded as unresolved
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=url,
                method=ResolutionMethod.NONE.value,
                evidence=str(exc),
                confidence=0.0,
                status=ResourceStatus.UNRESOLVED,
                timestamp=now,
            )

        final_url = str(head.url)
        disposition = head.headers.get("content-disposition", "")
        content_type = (head.headers.get("content-type") or "").split(";")[0].strip()
        if "attachment" in disposition.lower() or "filename=" in disposition.lower():
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=url,
                resolved_url=final_url,
                method=ResolutionMethod.CONTENT_DISPOSITION.value,
                evidence=disposition[:200],
                confidence=0.9,
                status=ResourceStatus.RESOLVED,
                http_status=head.status_code,
                mime_type=content_type or None,
                timestamp=now,
            )

        if extension_of(final_url) in DIRECT_FILE_EXTENSIONS:
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=url,
                resolved_url=final_url,
                method=ResolutionMethod.FINAL_REDIRECT.value,
                evidence=f"redirected to {final_url}",
                confidence=0.9,
                status=ResourceStatus.RESOLVED,
                http_status=head.status_code,
                mime_type=content_type or None,
                timestamp=now,
            )

        # Landing / attachment page: inspect HTML without recursive crawl.
        if "text/html" in content_type or not content_type:
            try:
                page = client.get(final_url)
            except Exception as exc:  # noqa: BLE001
                return ResolutionResult(
                    resource_id=candidate.resource_id,
                    original_url=url,
                    method=ResolutionMethod.NONE.value,
                    evidence=str(exc),
                    confidence=0.0,
                    status=ResourceStatus.UNRESOLVED,
                    http_status=getattr(exc, "status_code", None),
                    timestamp=now,
                )
            return self._resolve_from_html(
                candidate=candidate,
                original_url=url,
                page_url=str(page.url),
                html=page.text,
                http_status=page.status_code,
                now=now,
            )

        # Non-HTML but no extension: accept as resolved remote object.
        if head.status_code < 400 and content_type and "text/html" not in content_type:
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=url,
                resolved_url=final_url,
                method=ResolutionMethod.FINAL_REDIRECT.value,
                evidence=f"content-type {content_type}",
                confidence=0.7,
                status=ResourceStatus.RESOLVED,
                http_status=head.status_code,
                mime_type=content_type,
                timestamp=now,
            )

        return ResolutionResult(
            resource_id=candidate.resource_id,
            original_url=url,
            method=ResolutionMethod.NONE.value,
            evidence="no downloadable candidate found",
            confidence=0.0,
            status=ResourceStatus.UNRESOLVED,
            http_status=head.status_code,
            mime_type=content_type or None,
            timestamp=now,
        )

    def _resolve_from_html(
        self,
        *,
        candidate: ResourceCandidate,
        original_url: str,
        page_url: str,
        html: str,
        http_status: int,
        now: datetime,
    ) -> ResolutionResult:
        soup = BeautifulSoup(html, "html.parser")

        def accept(
            href: str, method: ResolutionMethod, evidence: str, confidence: float
        ) -> ResolutionResult:
            absolute = urljoin(page_url, href)
            return ResolutionResult(
                resource_id=candidate.resource_id,
                original_url=original_url,
                resolved_url=absolute,
                method=method.value,
                evidence=evidence,
                confidence=confidence,
                status=ResourceStatus.RESOLVED,
                http_status=http_status,
                timestamp=now,
            )

        for a in soup.select("a[download]"):
            href = a.get("href")
            if href:
                return accept(str(href), ResolutionMethod.A_DOWNLOAD, "a[download]", 0.92)

        for a in soup.select("a"):
            href = a.get("href")
            text = a.get_text(" ", strip=True).lower()
            classes = " ".join(a.get("class") or []).lower()
            if href and (
                "download" in text
                or "download" in classes
                or "wp-block-file" in classes
                or "attachment" in classes
            ):
                return accept(
                    str(href),
                    ResolutionMethod.DOWNLOAD_BUTTON,
                    f"download-like link text={text[:80]}",
                    0.85,
                )
            if href and extension_of(str(href)) in DIRECT_FILE_EXTENSIONS:
                return accept(
                    str(href),
                    ResolutionMethod.WP_ATTACHMENT,
                    "anchor with direct file extension",
                    0.88,
                )

        for sel, method in (
            ("audio source[src], audio[src]", ResolutionMethod.MEDIA_SOURCE),
            ("video source[src], video[src]", ResolutionMethod.MEDIA_SOURCE),
            ("embed[src], object[data], iframe[src]", ResolutionMethod.IFRAME_EMBED),
            ("object[type*='pdf'], embed[type*='pdf']", ResolutionMethod.OBJECT_PDF),
        ):
            el = soup.select_one(sel)
            if el and isinstance(el, Tag):
                href = el.get("src") or el.get("data")
                if href:
                    return accept(str(href), method, sel, 0.8)

        # WordPress attachment: often has class attachment or og:url file.
        og = soup.select_one('meta[property="og:url"]')
        if og and og.get("content"):
            content = str(og.get("content"))
            if extension_of(content) in DIRECT_FILE_EXTENSIONS:
                return accept(content, ResolutionMethod.WP_ATTACHMENT, "og:url", 0.75)

        return ResolutionResult(
            resource_id=candidate.resource_id,
            original_url=original_url,
            method=ResolutionMethod.NONE.value,
            evidence="landing page inspected; no file candidate",
            confidence=0.0,
            status=ResourceStatus.UNRESOLVED,
            http_status=http_status,
            timestamp=now,
        )
