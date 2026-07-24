"""API discovery layer for the Evidence Collector.

This module is responsible ONLY for probing a fixed set of well-known
paths where APIs and API documentation are commonly exposed, and
recording which of them respond successfully. It performs no scoring,
no quality judgment, no recommendation generation, and no LLM calls —
those concerns live elsewhere.

The discoverer consumes only a base URL and an `HttpClient`.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib.parse import urljoin

from models.api import ApiDiscoveryResult
from models.http import HttpResponseEvidence
from tools.http_client import HttpClient, HttpClientError

_OPENAPI_PATHS = [
    "/openapi.json",
    "/openapi.yaml",
    "/openapi.yml",
    "/api/openapi.json",
    "/api/openapi.yaml",
    "/v1/openapi.json",
]

_SWAGGER_PATHS = [
    "/swagger",
    "/swagger/",
    "/swagger-ui",
    "/swagger-ui/",
    "/swagger-ui.html",
    "/api/swagger",
]

_REDOC_PATHS = [
    "/redoc",
    "/redoc/",
    "/docs",
]

_DOCUMENTATION_PATHS = [
    "/api-docs",
    "/api/docs",
    "/reference",
    "/documentation",
]

_API_ENDPOINT_PATHS = [
    "/api",
    "/api/",
    "/api/v1",
    "/v1",
    "/v2",
]

_GRAPHQL_PATHS = [
    "/graphql",
    "/graphql/",
]

_MCP_PATHS = [
    "/mcp",
    "/mcp/",
    "/mcp.json",
    "/.well-known/mcp",
    "/.well-known/mcp.json",
]


class ApiDiscovery:
    """Discovers machine-readable interfaces exposed by a website.

    This class holds no scoring or recommendation logic. It is a pure
    discovery step: it probes a fixed set of well-known candidate
    paths and records what it observes into an `ApiDiscoveryResult`.
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

    def discover(self) -> ApiDiscoveryResult:
        """Run every discovery strategy and collect the results.

        A failure to reach any single candidate path (timeout, 404,
        connection error, etc.) never stops the overall discovery
        process.

        Returns:
            An `ApiDiscoveryResult` describing every machine-readable
            interface observed.
        """
        result = ApiDiscoveryResult()
        self._discover_openapi(result)
        self._discover_swagger(result)
        self._discover_redoc(result)
        self._discover_documentation(result)
        self._discover_api_endpoints(result)
        self._discover_mcp(result)
        return result

    # ------------------------------------------------------------------
    # Shared probing helper
    # ------------------------------------------------------------------

    def _test_endpoint(
        self, path: str, result: ApiDiscoveryResult
    ) -> Optional[HttpResponseEvidence]:
        """Probe a single candidate path relative to the base URL.

        Records the outcome in `result.tested_urls`. Transport-level
        failures (timeouts, connection errors, malformed URLs, etc.)
        are swallowed here so a single bad path can never abort
        discovery.

        Args:
            path: A path relative to the base URL (e.g. `/openapi.json`).
            result: The in-progress result to record the probe into.

        Returns:
            The `HttpResponseEvidence` if the request completed, or
            `None` if it raised a transport-level error.
        """
        url = urljoin(self._base_url, path)
        try:
            response = self._http_client.get(url)
        except HttpClientError:
            return None
        result.tested_urls[url] = response.status_code
        return response

    @staticmethod
    def _is_success(response: Optional[HttpResponseEvidence]) -> bool:
        """Determine whether a probe response counts as a successful hit.

        Args:
            response: The response returned by `_test_endpoint`, if any.

        Returns:
            True if a response was received with a 200 status code.
        """
        return response is not None and response.status_code == 200

    # ------------------------------------------------------------------
    # OpenAPI
    # ------------------------------------------------------------------

    def _discover_openapi(self, result: ApiDiscoveryResult) -> None:
        """Probe well-known OpenAPI specification locations.

        Existence detection only; the specification content is not
        validated here.

        Args:
            result: The in-progress result to populate.
        """
        for path in _OPENAPI_PATHS:
            response = self._test_endpoint(path, result)
            if self._is_success(response):
                result.openapi_urls.append(response.final_url)

    # ------------------------------------------------------------------
    # Swagger
    # ------------------------------------------------------------------

    def _discover_swagger(self, result: ApiDiscoveryResult) -> None:
        """Probe well-known Swagger UI locations.

        Args:
            result: The in-progress result to populate.
        """
        for path in _SWAGGER_PATHS:
            response = self._test_endpoint(path, result)
            if self._is_success(response):
                result.swagger_urls.append(response.final_url)

    # ------------------------------------------------------------------
    # ReDoc
    # ------------------------------------------------------------------

    def _discover_redoc(self, result: ApiDiscoveryResult) -> None:
        """Probe well-known ReDoc documentation locations.

        Args:
            result: The in-progress result to populate.
        """
        for path in _REDOC_PATHS:
            response = self._test_endpoint(path, result)
            if self._is_success(response):
                result.redoc_urls.append(response.final_url)

    # ------------------------------------------------------------------
    # General API documentation
    # ------------------------------------------------------------------

    def _discover_documentation(self, result: ApiDiscoveryResult) -> None:
        """Probe well-known general API documentation locations.

        Args:
            result: The in-progress result to populate.
        """
        for path in _DOCUMENTATION_PATHS:
            response = self._test_endpoint(path, result)
            if self._is_success(response):
                result.api_documentation_urls.append(response.final_url)

    # ------------------------------------------------------------------
    # Raw API endpoints (including GraphQL)
    # ------------------------------------------------------------------

    def _discover_api_endpoints(self, result: ApiDiscoveryResult) -> None:
        """Probe well-known raw API entry points, including GraphQL.

        GraphQL endpoints are recorded both as generic API endpoints
        and, separately, in `graphql_endpoints`.

        Args:
            result: The in-progress result to populate.
        """
        for path in _API_ENDPOINT_PATHS:
            response = self._test_endpoint(path, result)
            if self._is_success(response):
                result.api_endpoints.append(response.final_url)

        for path in _GRAPHQL_PATHS:
            response = self._test_endpoint(path, result)
            if self._is_success(response):
                result.api_endpoints.append(response.final_url)
                result.graphql_endpoints.append(response.final_url)

    # ------------------------------------------------------------------
    # MCP
    # ------------------------------------------------------------------

    def _discover_mcp(self, result: ApiDiscoveryResult) -> None:
        """Probe well-known MCP (Model Context Protocol) locations.

        When a discovered endpoint returns a JSON body containing
        `tools` or `resources` arrays, the `name` of each entry is
        collected as additional evidence. Full MCP protocol
        communication (handshakes, JSON-RPC calls) is out of scope
        here — this only inspects whatever JSON the endpoint already
        returns on a plain GET.

        Args:
            result: The in-progress result to populate.
        """
        for path in _MCP_PATHS:
            response = self._test_endpoint(path, result)
            if not self._is_success(response):
                continue
            result.mcp_endpoints.append(response.final_url)
            self._extract_mcp_payload(response, result)

    @staticmethod
    def _extract_mcp_payload(
        response: HttpResponseEvidence, result: ApiDiscoveryResult
    ) -> None:
        """Extract `tools`/`resources` names from an MCP endpoint's JSON body.

        Malformed or non-JSON bodies are silently ignored.

        Args:
            response: The successful response from an MCP endpoint.
            result: The in-progress result to populate.
        """
        try:
            payload: Any = json.loads(response.content)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(payload, dict):
            return

        for tool in payload.get("tools") or []:
            if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                result.mcp_tools.append(tool["name"])

        for resource in payload.get("resources") or []:
            if isinstance(resource, dict) and isinstance(resource.get("name"), str):
                result.mcp_resources.append(resource["name"])
