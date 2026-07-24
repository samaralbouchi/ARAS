"""HTTP communication layer for the Evidence Collector.

This module is responsible ONLY for issuing HTTP GET requests and
returning a raw, unopinionated snapshot of the response. It performs
no HTML parsing, no metadata extraction, and no scoring — those
concerns live in other `tools/` modules and in the agent layer.

Errors are surfaced as typed exceptions rather than swallowed here;
callers (the Evidence Collector Agent) decide how to degrade
gracefully on a per-step basis.
"""

from __future__ import annotations

import ssl
import time
from types import TracebackType
from typing import Optional
from urllib.parse import urlparse

import httpx

from models.http import HttpResponseEvidence


# ---------------------------------------------------------------------------
# Exceptions
#
# Scoped locally to this module for now since `exceptions.py` has not been
# created yet. These may be relocated into a shared exception hierarchy in
# a later step without changing HttpClient's public behavior.
# ---------------------------------------------------------------------------


class HttpClientError(Exception):
    """Base class for all errors raised by :class:`HttpClient`."""


class InvalidURLError(HttpClientError):
    """Raised when the given URL is malformed or missing a scheme/host."""


class ConnectionFailedError(HttpClientError):
    """Raised when the target host refuses or cannot establish a connection."""


class RequestTimeoutError(HttpClientError):
    """Raised when a request exceeds the configured timeout."""


class SSLVerificationError(HttpClientError):
    """Raised when the TLS/SSL handshake or certificate validation fails."""


class RedirectLoopError(HttpClientError):
    """Raised when a request exceeds the maximum allowed redirects."""


class HttpRequestError(HttpClientError):
    """Raised for any other transport-level HTTP failure."""


class HttpClient:
    """Thin, reusable wrapper around `httpx.Client` for GET requests.

    This class centralizes timeout, user-agent, header, and redirect
    configuration so that all evidence-collection HTTP calls behave
    consistently. It holds no knowledge of what the response body
    means (HTML, XML, JSON, etc.).
    """

    DEFAULT_USER_AGENT = "ARAS-EvidenceCollector/1.0 (+agentic-readiness-assessment)"

    def __init__(
        self,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: Optional[dict[str, str]] = None,
        follow_redirects: bool = True,
        max_redirects: int = 10,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the HTTP client with shared request configuration.

        Args:
            timeout: Maximum time, in seconds, to wait for a response.
            user_agent: Value sent as the `User-Agent` header.
            headers: Additional headers merged into every request.
            follow_redirects: Whether to automatically follow HTTP redirects.
            max_redirects: Maximum number of redirects to follow before
                treating the chain as a redirect loop.
            verify_ssl: Whether to verify TLS certificates.
        """
        merged_headers = {"User-Agent": user_agent}
        if headers:
            merged_headers.update(headers)

        self._client = httpx.Client(
            timeout=timeout,
            headers=merged_headers,
            follow_redirects=follow_redirects,
            max_redirects=max_redirects,
            verify=verify_ssl,
        )

    def get(self, url: str) -> HttpResponseEvidence:
        """Issue a GET request and return a raw response snapshot.

        Args:
            url: The absolute URL to request.

        Returns:
            An `HttpResponseEvidence` describing the response.

        Raises:
            InvalidURLError: If `url` is malformed or missing a scheme/host.
            ConnectionFailedError: If the connection could not be established.
            RequestTimeoutError: If the request exceeded the configured timeout.
            SSLVerificationError: If the TLS handshake or certificate failed.
            RedirectLoopError: If the redirect chain exceeded the configured limit.
            HttpRequestError: For any other transport-level failure.
        """
        self._validate_url(url)

        start = time.monotonic()
        try:
            response = self._client.get(url)
        except httpx.TooManyRedirects as exc:
            raise RedirectLoopError(f"Too many redirects for '{url}': {exc}") from exc
        except httpx.ConnectError as exc:
            if self._is_ssl_error(exc):
                raise SSLVerificationError(
                    f"SSL verification failed for '{url}': {exc}"
                ) from exc
            raise ConnectionFailedError(
                f"Could not connect to '{url}': {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RequestTimeoutError(
                f"Request to '{url}' timed out: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise HttpRequestError(f"Request to '{url}' failed: {exc}") from exc
        elapsed = time.monotonic() - start

        return HttpResponseEvidence(
            requested_url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.text,
            content_type=response.headers.get("content-type"),
            response_time=elapsed,
            content_length=len(response.content),
        )

    def close(self) -> None:
        """Close the underlying connection pool.

        Should be called when the client is no longer needed, unless
        used as a context manager.
        """
        self._client.close()

    def __enter__(self) -> "HttpClient":
        """Enter the runtime context, returning this client instance."""
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Exit the runtime context, closing the underlying connection pool."""
        self.close()

    @staticmethod
    def _validate_url(url: str) -> None:
        """Validate that a URL has a supported scheme and a host.

        Args:
            url: The URL to validate.

        Raises:
            InvalidURLError: If the URL is malformed or unsupported.
        """
        try:
            parsed = urlparse(url)
        except ValueError as exc:
            raise InvalidURLError(f"Malformed URL '{url}': {exc}") from exc

        if parsed.scheme not in ("http", "https"):
            raise InvalidURLError(
                f"Unsupported or missing scheme in URL '{url}' "
                f"(expected 'http' or 'https')"
            )
        if not parsed.netloc:
            raise InvalidURLError(f"URL '{url}' is missing a host")

    @staticmethod
    def _is_ssl_error(exc: httpx.ConnectError) -> bool:
        """Determine whether a connect error was caused by an SSL failure.

        Args:
            exc: The `httpx.ConnectError` raised during the request.

        Returns:
            True if the underlying cause was an SSL/TLS error.
        """
        cause = exc.__cause__
        return isinstance(cause, ssl.SSLError) or "ssl" in str(exc).lower()
