"""HTTP client with polite defaults."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from bhava_library.domain.errors import AccessRestrictedError, NetworkError


class PoliteHttpClient:
    """httpx wrapper enforcing per-host delay and connection limits."""

    def __init__(
        self,
        *,
        user_agent: str,
        request_delay_seconds: float = 2.0,
        verify_tls: bool = True,
        timeout: float = 60.0,
        connect_timeout: float = 15.0,
        max_redirects: int = 10,
    ) -> None:
        self.request_delay_seconds = request_delay_seconds
        self._last_request: dict[str, float] = defaultdict(float)
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "*/*"},
            verify=verify_tls,
            timeout=httpx.Timeout(timeout, connect=connect_timeout),
            follow_redirects=True,
            max_redirects=max_redirects,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteHttpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _wait_host(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        elapsed = time.monotonic() - self._last_request[host]
        if elapsed < self.request_delay_seconds:
            time.sleep(self.request_delay_seconds - elapsed)
        self._last_request[host] = time.monotonic()

    def _raise_access(self, response: httpx.Response, *, peek_body: bool = True) -> None:
        if response.status_code in {401, 403}:
            raise AccessRestrictedError(
                f"Access restricted: HTTP {response.status_code} for {response.url}"
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "")
            raise NetworkError(f"Rate limited (429) Retry-After={retry_after}")
        if not peek_body:
            return
        text_sample = (response.text or "")[:500].lower()
        if "captcha" in text_sample or "cf-challenge" in text_sample:
            raise AccessRestrictedError(f"CAPTCHA/challenge detected at {response.url}")

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, NetworkError)),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self._wait_host(url)
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise NetworkError(str(exc)) from exc
        if response.status_code >= 500:
            raise NetworkError(f"Server error {response.status_code} for {url}")
        self._raise_access(response)
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, **kwargs)

    def get_range(self, url: str, start: int = 0, end: int = 0, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["Range"] = f"bytes={start}-{end}"
        return self.request("GET", url, headers=headers, **kwargs)

    def stream_get(self, url: str, **kwargs: Any) -> httpx.Response:
        self._wait_host(url)
        headers = kwargs.pop("headers", None)
        try:
            request = self._client.build_request("GET", url, headers=headers, **kwargs)
            response = self._client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise NetworkError(str(exc)) from exc
        if response.status_code >= 500:
            response.close()
            raise NetworkError(f"Server error {response.status_code} for {url}")
        try:
            self._raise_access(response, peek_body=False)
        except Exception:
            response.close()
            raise
        return response
