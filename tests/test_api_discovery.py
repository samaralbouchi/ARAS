"""Manual smoke test for :class:`ApiDiscovery`.

Covers a real page with no exposed APIs (mytek.tn) plus mocked HTTP
responses, against that same site, for: successful endpoint detection,
failed endpoint handling (404s and transport errors), and MCP JSON
parsing. This verifies that discovery works end-to-end; it performs no
scoring or assertions about Agentic Readiness.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.http import HttpResponseEvidence
from tools.api_discovery import ApiDiscovery
from tools.http_client import HttpClient, RequestTimeoutError

TEST_URL = "https://www.mytek.tn/?srsltid=AfmBOoq_PPpgNPOLkGr81RClAry7rBVLMqDx0Zkne9EHc8TNQv5aftsF"


class FakeHttpClient:
    """Stand-in for `HttpClient` that serves canned responses by path.

    Any URL not present in `responses` raises `RequestTimeoutError`,
    mimicking a transport-level failure so discovery's error-handling
    path is exercised too.
    """

    def __init__(self, responses: dict[str, HttpResponseEvidence]) -> None:
        self._responses = responses

    def get(self, url: str) -> HttpResponseEvidence:
        if url not in self._responses:
            raise RequestTimeoutError(f"no mocked response for '{url}'")
        return self._responses[url]


def _response(url: str, status_code: int, content: str = "") -> HttpResponseEvidence:
    return HttpResponseEvidence(
        requested_url=url,
        final_url=url,
        status_code=status_code,
        content=content,
    )


def _print_result(label: str, result) -> None:
    print(f"--- {label} ---")
    print(f"openapi_urls:           {result.openapi_urls}")
    print(f"swagger_urls:           {result.swagger_urls}")
    print(f"redoc_urls:             {result.redoc_urls}")
    print(f"api_documentation_urls: {result.api_documentation_urls}")
    print(f"api_endpoints:          {result.api_endpoints}")
    print(f"graphql_endpoints:      {result.graphql_endpoints}")
    print(f"mcp_endpoints:          {result.mcp_endpoints}")
    print(f"mcp_tools:              {result.mcp_tools}")
    print(f"mcp_resources:          {result.mcp_resources}")
    print(f"tested_urls:            {result.tested_urls}")
    print()


def test_no_api_exposure() -> None:
    """mytek.tn should not expose any known API surface."""
    with HttpClient() as client:
        result = ApiDiscovery(TEST_URL, client).discover()
    _print_result("mytek.tn (no API exposure)", result)
    assert result.openapi_urls == []
    assert result.swagger_urls == []
    assert result.redoc_urls == []
    assert result.mcp_endpoints == []


def test_successful_endpoint_detection() -> None:
    """A 200 response on a candidate path should be recorded as a hit."""
    responses = {
        "https://www.mytek.tn/openapi.json": _response(
            "https://www.mytek.tn/openapi.json", 200, "{}"
        ),
        "https://www.mytek.tn/swagger": _response(
            "https://www.mytek.tn/swagger", 200, "<html></html>"
        ),
        "https://www.mytek.tn/graphql": _response(
            "https://www.mytek.tn/graphql", 200, "{}"
        ),
    }
    result = ApiDiscovery(TEST_URL, FakeHttpClient(responses)).discover()
    _print_result("mocked successful hits", result)
    assert result.openapi_urls == ["https://www.mytek.tn/openapi.json"]
    assert result.swagger_urls == ["https://www.mytek.tn/swagger"]
    assert "https://www.mytek.tn/graphql" in result.api_endpoints
    assert result.graphql_endpoints == ["https://www.mytek.tn/graphql"]
    assert result.tested_urls["https://www.mytek.tn/openapi.json"] == 200


def test_failed_endpoint_handling() -> None:
    """404s and transport errors must not raise or produce false hits."""
    responses = {
        "https://www.mytek.tn/openapi.json": _response(
            "https://www.mytek.tn/openapi.json", 404
        ),
    }
    result = ApiDiscovery(TEST_URL, FakeHttpClient(responses)).discover()
    _print_result("mocked failures (404 + timeouts)", result)
    assert result.openapi_urls == []
    assert result.tested_urls["https://www.mytek.tn/openapi.json"] == 404
    # Paths with no mocked response raise RequestTimeoutError inside the
    # fake client; these must be swallowed and simply absent from
    # tested_urls rather than propagating or crashing discovery.
    assert "https://www.mytek.tn/swagger" not in result.tested_urls


def test_mcp_json_parsing() -> None:
    """tools/resources names in an MCP endpoint's JSON body are collected."""
    mcp_body = json.dumps(
        {
            "tools": [{"name": "search_products"}, {"name": "get_order"}],
            "resources": [{"name": "catalog"}],
        }
    )
    responses = {
        "https://www.mytek.tn/mcp": _response(
            "https://www.mytek.tn/mcp", 200, mcp_body
        ),
    }
    result = ApiDiscovery(TEST_URL, FakeHttpClient(responses)).discover()
    _print_result("mocked MCP endpoint", result)
    assert result.mcp_endpoints == ["https://www.mytek.tn/mcp"]
    assert result.mcp_tools == ["search_products", "get_order"]
    assert result.mcp_resources == ["catalog"]


def test_mcp_malformed_json_is_ignored() -> None:
    """A non-JSON MCP endpoint body must not raise; endpoint is still recorded."""
    responses = {
        "https://www.mytek.tn/mcp": _response(
            "https://www.mytek.tn/mcp", 200, "not json"
        ),
    }
    result = ApiDiscovery(TEST_URL, FakeHttpClient(responses)).discover()
    _print_result("mocked MCP endpoint (malformed body)", result)
    assert result.mcp_endpoints == ["https://www.mytek.tn/mcp"]
    assert result.mcp_tools == []
    assert result.mcp_resources == []


if __name__ == "__main__":
    test_no_api_exposure()
    test_successful_endpoint_detection()
    test_failed_endpoint_handling()
    test_mcp_json_parsing()
    test_mcp_malformed_json_is_ignored()
    print("All tests passed.")
