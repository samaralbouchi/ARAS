"""Frontend JavaScript analysis layer for the Evidence Collector.

This module is responsible ONLY for downloading frontend JavaScript
resources and statically scanning their raw text for references to
backend APIs (REST, GraphQL, WebSocket) and known external services.
It performs no HTTP requests beyond fetching the given JavaScript
files, no scoring, no quality analysis, no recommendation generation,
and no LLM calls — those concerns live elsewhere.

Extraction is regular-expression based only. No JavaScript is ever
executed: no browser automation, no Selenium, no Playwright.
"""

from __future__ import annotations

import re

from models.frontend import FrontendAnalysisResult
from tools.http_client import HttpClient, HttpClientError

# Quoted string literals, e.g. the "/api/products" in `fetch("/api/products")`.
# Bounded in length and excludes whitespace/angle brackets to avoid matching
# across unrelated code or into HTML fragments embedded as strings.
_QUOTED_STRING_RE = re.compile(r'["\']([^"\'<>\s]{1,300})["\']')

_GRAPHQL_RE = re.compile(r"/graphql/?", re.IGNORECASE)
_REST_VERSIONED_RE = re.compile(r"/api/v\d+/")
_REST_RE = re.compile(r"/api/")
_WEBSOCKET_PREFIX = ("ws://", "wss://")
_HTTP_PREFIX = ("http://", "https://")

# Known third-party service domains that indicate reliance on an external
# backend. Not exhaustive — extend as new commonly seen providers surface.
_EXTERNAL_SERVICE_DOMAINS = [
    "stripe.com",
    "firebaseio.com",
    "firebase",
    "api.openai.com",
    "googleapis.com",
    "google-analytics.com",
    "sentry.io",
    "auth0.com",
    "amazonaws.com",
]


class FrontendAnalyzer:
    """Statically scans frontend JavaScript for backend API references.

    This class holds no scoring or recommendation logic. It downloads
    each given JavaScript file and pattern-matches its raw text for
    evidence of REST/GraphQL/WebSocket endpoints and known external
    services, collecting the results into a `FrontendAnalysisResult`.
    """

    def __init__(self, javascript_files: list[str], http_client: HttpClient) -> None:
        """Initialize the analyzer with candidate JavaScript files.

        Args:
            javascript_files: Absolute URLs of JavaScript resources to
                download and scan (typically `HtmlParser`'s
                `javascript_files` output).
            http_client: A configured `HttpClient` used to download
                each file.
        """
        self._javascript_files = javascript_files
        self._http_client = http_client

    def analyze(self) -> FrontendAnalysisResult:
        """Download and scan every candidate JavaScript file.

        A failure to download or scan any single file (404, timeout,
        connection error, empty body, minified content, etc.) never
        stops the overall analysis.

        Returns:
            A `FrontendAnalysisResult` describing every API reference
            observed across all successfully analyzed files.
        """
        result = FrontendAnalysisResult()
        seen_urls: set[str] = set()
        seen_websocket: set[str] = set()
        seen_services: set[str] = set()

        for js_url in self._javascript_files:
            content = self._download(js_url)
            if content is None:
                continue
            result.javascript_files_analyzed.append(js_url)
            self._extract_api_references(content, result, seen_urls)
            self._extract_websocket_references(content, result, seen_websocket)
            self._extract_external_services(content, result, seen_services)

        return result

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download(self, js_url: str) -> str | None:
        """Download a single JavaScript file, tolerating any failure.

        Args:
            js_url: The absolute URL of the JavaScript resource.

        Returns:
            The response body text, or `None` if the file could not be
            retrieved, was not successful, or was empty.
        """
        try:
            response = self._http_client.get(js_url)
        except HttpClientError:
            return None
        if response.status_code != 200 or not response.content:
            return None
        return response.content

    # ------------------------------------------------------------------
    # REST / GraphQL API references
    # ------------------------------------------------------------------

    def _extract_api_references(
        self, content: str, result: FrontendAnalysisResult, seen: set[str]
    ) -> None:
        """Extract REST and GraphQL API references from quoted string literals.

        Args:
            content: Raw JavaScript source text.
            result: The in-progress result to populate.
            seen: URLs already recorded, across all files, to dedupe.
        """
        for match in _QUOTED_STRING_RE.finditer(content):
            candidate = match.group(1)
            if not (candidate.startswith("/") or candidate.startswith(_HTTP_PREFIX)):
                continue

            pattern = self._classify_api_pattern(candidate)
            if pattern is None:
                continue
            if candidate in seen:
                continue
            seen.add(candidate)

            result.discovered_api_urls.append(candidate)
            result.discovered_api_patterns.append(pattern)
            if pattern == "graphql":
                result.graphql_references.append(candidate)

    @staticmethod
    def _classify_api_pattern(candidate: str) -> str | None:
        """Classify a candidate path/URL as a known API pattern.

        Args:
            candidate: A path or absolute URL found in a quoted string.

        Returns:
            `"graphql"`, `"rest_versioned"`, `"rest"`, or `None` if the
            candidate does not match any known API pattern.
        """
        if _GRAPHQL_RE.search(candidate):
            return "graphql"
        if _REST_VERSIONED_RE.search(candidate):
            return "rest_versioned"
        if _REST_RE.search(candidate):
            return "rest"
        return None

    # ------------------------------------------------------------------
    # WebSocket references
    # ------------------------------------------------------------------

    def _extract_websocket_references(
        self, content: str, result: FrontendAnalysisResult, seen: set[str]
    ) -> None:
        """Extract `ws://`/`wss://` URLs from quoted string literals.

        Args:
            content: Raw JavaScript source text.
            result: The in-progress result to populate.
            seen: WebSocket URLs already recorded, across all files, to
                dedupe.
        """
        for match in _QUOTED_STRING_RE.finditer(content):
            candidate = match.group(1)
            if not candidate.lower().startswith(_WEBSOCKET_PREFIX):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            result.websocket_references.append(candidate)

    # ------------------------------------------------------------------
    # External services
    # ------------------------------------------------------------------

    def _extract_external_services(
        self, content: str, result: FrontendAnalysisResult, seen: set[str]
    ) -> None:
        """Detect references to known third-party service domains.

        Args:
            content: Raw JavaScript source text.
            result: The in-progress result to populate.
            seen: Service domains already recorded, across all files,
                to dedupe.
        """
        lowered = content.lower()
        for domain in _EXTERNAL_SERVICE_DOMAINS:
            if domain in seen:
                continue
            if domain in lowered:
                seen.add(domain)
                result.external_services.append(domain)
