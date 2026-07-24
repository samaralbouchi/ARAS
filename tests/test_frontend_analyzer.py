"""Manual smoke test for :class:`FrontendAnalyzer`.

Covers static detection of REST, versioned REST, GraphQL, WebSocket,
and external-service references in mocked JavaScript file contents, as
well as graceful handling of 404s, timeouts, empty bodies, and
minified content. No JavaScript is executed; everything here is
regex-based static analysis over canned response bodies.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.http import HttpResponseEvidence
from tools.frontend_analyzer import FrontendAnalyzer
from tools.http_client import RequestTimeoutError


class FakeHttpClient:
    """Stand-in for `HttpClient` that serves canned responses by URL.

    Any URL not present in `responses` raises `RequestTimeoutError`,
    mimicking a transport-level failure so the analyzer's
    error-handling path is exercised too.
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
    print(f"javascript_files_analyzed: {result.javascript_files_analyzed}")
    print(f"discovered_api_urls:       {result.discovered_api_urls}")
    print(f"discovered_api_patterns:   {result.discovered_api_patterns}")
    print(f"graphql_references:        {result.graphql_references}")
    print(f"websocket_references:      {result.websocket_references}")
    print(f"external_services:         {result.external_services}")
    print()


def test_detects_rest_api() -> None:
    """A plain `/api/...` reference should be classified as REST."""
    js_url = "https://www.mytek.tn/assets/app.js"
    responses = {js_url: _response(js_url, 200, 'fetch("/api/products")')}
    result = FrontendAnalyzer([js_url], FakeHttpClient(responses)).analyze()
    _print_result("REST API detection", result)
    assert result.javascript_files_analyzed == [js_url]
    assert result.discovered_api_urls == ["/api/products"]
    assert result.discovered_api_patterns == ["rest"]


def test_detects_versioned_rest_api() -> None:
    """A `/api/v1/...` reference should be classified as versioned REST."""
    js_url = "https://www.mytek.tn/assets/main.js"
    responses = {js_url: _response(js_url, 200, 'axios.get("/api/v1/users")')}
    result = FrontendAnalyzer([js_url], FakeHttpClient(responses)).analyze()
    _print_result("versioned REST API detection", result)
    assert result.discovered_api_urls == ["/api/v1/users"]
    assert result.discovered_api_patterns == ["rest_versioned"]


def test_detects_graphql() -> None:
    """A `/graphql` reference should be classified as GraphQL and tracked separately."""
    js_url = "https://www.mytek.tn/assets/graphql.js"
    responses = {js_url: _response(js_url, 200, 'fetch("/graphql", {method: "POST"})')}
    result = FrontendAnalyzer([js_url], FakeHttpClient(responses)).analyze()
    _print_result("GraphQL detection", result)
    assert result.discovered_api_urls == ["/graphql"]
    assert result.discovered_api_patterns == ["graphql"]
    assert result.graphql_references == ["/graphql"]


def test_detects_websocket_and_external_services() -> None:
    """`wss://` URLs and known third-party domains should both be captured."""
    js_url = "https://www.mytek.tn/assets/vendor.js"
    content = (
        'const socket = new WebSocket("wss://live.mytek.tn/updates");\n'
        'const stripe = Stripe("pk_test_123");\n'
        'fetch("https://api.stripe.com/v1/tokens");\n'
    )
    responses = {js_url: _response(js_url, 200, content)}
    result = FrontendAnalyzer([js_url], FakeHttpClient(responses)).analyze()
    _print_result("WebSocket + external service detection", result)
    assert result.websocket_references == ["wss://live.mytek.tn/updates"]
    assert "stripe.com" in result.external_services


def test_ignores_failed_and_empty_files() -> None:
    """404s, timeouts, and empty bodies must not raise or produce false hits."""
    ok_url = "https://www.mytek.tn/assets/app.js"
    missing_url = "https://www.mytek.tn/assets/missing.js"
    empty_url = "https://www.mytek.tn/assets/empty.js"
    timeout_url = "https://www.mytek.tn/assets/unreachable.js"

    responses = {
        ok_url: _response(ok_url, 200, 'fetch("/api/search")'),
        missing_url: _response(missing_url, 404, ""),
        empty_url: _response(empty_url, 200, ""),
    }
    result = FrontendAnalyzer(
        [ok_url, missing_url, empty_url, timeout_url], FakeHttpClient(responses)
    ).analyze()
    _print_result("failure handling", result)
    assert result.javascript_files_analyzed == [ok_url]
    assert result.discovered_api_urls == ["/api/search"]


def test_handles_minified_content() -> None:
    """A dense, minified bundle should still yield matches without crashing."""
    js_url = "https://www.mytek.tn/assets/bundle.min.js"
    content = (
        '!function(e){var t=e.fetch("/api/v1/cart",{method:"GET"});'
        'return e.axios.get("/api/wishlist"),t}(window);'
    )
    responses = {js_url: _response(js_url, 200, content)}
    result = FrontendAnalyzer([js_url], FakeHttpClient(responses)).analyze()
    _print_result("minified content", result)
    assert "/api/v1/cart" in result.discovered_api_urls
    assert "/api/wishlist" in result.discovered_api_urls


if __name__ == "__main__":
    test_detects_rest_api()
    test_detects_versioned_rest_api()
    test_detects_graphql()
    test_detects_websocket_and_external_services()
    test_ignores_failed_and_empty_files()
    test_handles_minified_content()
    print("All tests passed.")
