"""Resource discovery layer for the Evidence Collector.

This module is responsible ONLY for retrieving a fixed set of
well-known standard resources that indicate a website's discoverability
and accessibility for AI agents: `robots.txt`, `sitemap.xml`, and
`llms.txt`. It performs no scoring, no quality judgment, no
recommendation generation, and no LLM calls — those concerns live
elsewhere.

The discoverer consumes only a base URL and an `HttpClient`.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urljoin

from models.evidence import CollectionError
from models.http import HttpResponseEvidence
from models.resource import ResourceDiscoveryResult
from tools.http_client import HttpClient, HttpClientError

_ROBOTS_PATH = "/robots.txt"
_SITEMAP_PATH = "/sitemap.xml"
_LLMS_PATH = "/llms.txt"


class ResourceDiscovery:
    """Discovers standard discoverability resources exposed by a website.

    This class holds no scoring or recommendation logic. It is a pure
    discovery step: it requests a fixed set of well-known resource
    paths and records what it observes into a `ResourceDiscoveryResult`.
    """

    def __init__(self, base_url: str, http_client: HttpClient) -> None:
        """Initialize the discoverer with a target site and HTTP client.

        Args:
            base_url: The absolute base URL of the website to probe
                (e.g. `https://example.com`).
            http_client: A configured `HttpClient` used to issue every
                probe request.
        """
        self._base_url = base_url
        self._http_client = http_client

    def discover(self) -> ResourceDiscoveryResult:
        """Retrieve every standard resource and collect the results.

        A failure to reach any single resource (timeout, 404,
        connection error, etc.) never stops the overall discovery
        process.

        Returns:
            A `ResourceDiscoveryResult` describing every standard
            resource observed.
        """
        result = ResourceDiscoveryResult()
        self._discover_robots(result)
        self._discover_sitemap(result)
        self._discover_llms(result)
        return result

    # ------------------------------------------------------------------
    # Shared fetch helper
    # ------------------------------------------------------------------

    def _fetch(
        self, path: str, step: str, result: ResourceDiscoveryResult
    ) -> Optional[HttpResponseEvidence]:
        """Fetch a single candidate resource relative to the base URL.

        Transport-level failures (timeouts, connection errors,
        malformed URLs, etc.) are caught here and recorded as a
        `CollectionError` so a single bad resource can never abort
        discovery.

        Args:
            path: A path relative to the base URL (e.g. `/robots.txt`).
            step: Name of this collection step, used when recording
                errors (e.g. `"robots_txt"`).
            result: The in-progress result to record the outcome into.

        Returns:
            The `HttpResponseEvidence` if the request completed, or
            `None` if it raised a transport-level error.
        """
        url = urljoin(self._base_url, path)
        try:
            return self._http_client.get(url)
        except HttpClientError as exc:
            result.errors.append(CollectionError(step=step, message=str(exc)))
            return None

    @staticmethod
    def _is_success(response: Optional[HttpResponseEvidence]) -> bool:
        """Determine whether a fetch response counts as a successful hit.

        Args:
            response: The response returned by `_fetch`, if any.

        Returns:
            True if a response was received with a 200 status code.
        """
        return response is not None and response.status_code == 200

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------

    def _discover_robots(self, result: ResourceDiscoveryResult) -> None:
        """Fetch `/robots.txt`.

        Args:
            result: The in-progress result to populate.
        """
        response = self._fetch(_ROBOTS_PATH, "robots_txt", result)
        if response is not None:
            result.robots_status_code = response.status_code
        if self._is_success(response):
            result.robots_txt = response.content
            result.discovered_resources.append("robots_txt")

    # ------------------------------------------------------------------
    # sitemap.xml
    # ------------------------------------------------------------------

    def _discover_sitemap(self, result: ResourceDiscoveryResult) -> None:
        """Fetch `/sitemap.xml`.

        Args:
            result: The in-progress result to populate.
        """
        response = self._fetch(_SITEMAP_PATH, "sitemap_xml", result)
        if response is not None:
            result.sitemap_status_code = response.status_code
        if self._is_success(response):
            result.sitemap_xml = response.content
            result.discovered_resources.append("sitemap_xml")

    # ------------------------------------------------------------------
    # llms.txt
    # ------------------------------------------------------------------

    def _discover_llms(self, result: ResourceDiscoveryResult) -> None:
        """Fetch `/llms.txt`.

        Args:
            result: The in-progress result to populate.
        """
        response = self._fetch(_LLMS_PATH, "llms_txt", result)
        if response is not None:
            result.llms_status_code = response.status_code
        if self._is_success(response):
            result.llms_txt = response.content
            result.discovered_resources.append("llms_txt")
