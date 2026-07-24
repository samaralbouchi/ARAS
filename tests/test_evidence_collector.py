"""Unit tests for :class:`EvidenceCollectorAgent`.

Covers, using fakes for every tool (no real network access): a fully
successful collection, a site with no API exposure, a fully
unreachable homepage, an isolated single-tool failure, and a resource
discovery failure. This verifies that the agent orchestrates and
isolates failures correctly; it performs no scoring or assertions
about Agentic Readiness.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.evidence_collector import EvidenceCollectorAgent
from models.api import ApiDiscoveryResult
from models.evidence import CollectionError
from models.frontend import FrontendAnalysisResult
from models.html import HtmlParseResult
from models.http import HttpResponseEvidence
from models.resource import ResourceDiscoveryResult
from models.schema import StructuredDataResult
from tools.http_client import ConnectionFailedError

URL = "https://www.example.com"

SAMPLE_HTML = """
<html lang="en">
<head><title>Example</title></head>
<body>
<script src="https://www.example.com/app.js"></script>
</body>
</html>
"""


class FakeHttpClient:
    """Stand-in for `HttpClient` that serves a canned homepage response or fails."""

    def __init__(self, homepage_response=None, homepage_error=None) -> None:
        self._homepage_response = homepage_response
        self._homepage_error = homepage_error

    def get(self, url: str) -> HttpResponseEvidence:
        if url == URL:
            if self._homepage_error is not None:
                raise self._homepage_error
            return self._homepage_response
        # Any other URL (JS files downloaded by FrontendAnalyzer, if it were
        # real) is irrelevant here since FrontendAnalyzer is always faked out.
        raise ConnectionFailedError(f"no mocked response for '{url}'")

    def close(self) -> None:
        pass


def _print_evidence(label: str, evidence) -> None:
    print(f"--- {label} ---")
    print(f"url:                {evidence.url}")
    print(f"status_code:        {evidence.status_code}")
    print(f"title:              {evidence.title}")
    print(f"language:           {evidence.language}")
    print(f"html (len):         {len(evidence.html) if evidence.html else 0}")
    print(f"javascript_files:   {evidence.javascript_files}")
    print(f"structured_data:    {evidence.structured_data}")
    print(f"robots_txt:         {evidence.robots_txt}")
    print(f"sitemap_xml:        {evidence.sitemap_xml}")
    print(f"llms_txt:           {evidence.llms_txt}")
    print(f"api_analysis:       {evidence.api_analysis}")
    print(f"api_candidates:     {evidence.api_candidates}")
    print(f"frontend_analysis:  {evidence.frontend_analysis}")
    print(f"errors:             {evidence.errors}")
    print()


def _homepage_response(status_code: int = 200, content: str = SAMPLE_HTML) -> HttpResponseEvidence:
    return HttpResponseEvidence(
        requested_url=URL,
        final_url=URL,
        status_code=status_code,
        content=content,
        headers={"content-type": "text/html"},
        response_time=0.05,
    )


class FakeHtmlParser:
    """Stand-in for `HtmlParser` returning a fixed, minimal parse result."""

    def __init__(self, html: str, base_url=None) -> None:
        self._html = html

    def parse(self) -> HtmlParseResult:
        return HtmlParseResult(
            title="Example",
            language="en",
            javascript_files=["https://www.example.com/app.js"],
        )


class FakeSchemaExtractor:
    """Stand-in for `SchemaExtractor` returning fixed structured data."""

    def __init__(self, html: str) -> None:
        self._html = html

    def extract(self) -> StructuredDataResult:
        return StructuredDataResult(json_ld=[{"@type": "Organization"}])


class FailingTool:
    """Generic stand-in for any tool whose construction/use always raises."""

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError("simulated tool failure")


def _make_agent(
    homepage_response=None,
    homepage_error=None,
    html_parser_cls=FakeHtmlParser,
    schema_extractor_cls=FakeSchemaExtractor,
    resource_discovery_cls=None,
    api_discovery_cls=None,
    frontend_analyzer_cls=None,
) -> EvidenceCollectorAgent:
    return EvidenceCollectorAgent(
        http_client=FakeHttpClient(homepage_response, homepage_error),
        html_parser_cls=html_parser_cls,
        schema_extractor_cls=schema_extractor_cls,
        resource_discovery_cls=resource_discovery_cls or _FakeResourceDiscovery,
        api_discovery_cls=api_discovery_cls or _FakeApiDiscovery,
        frontend_analyzer_cls=frontend_analyzer_cls or _FakeFrontendAnalyzer,
    )


class _FakeResourceDiscovery:
    def __init__(self, url: str, http_client) -> None:
        pass

    def discover(self) -> ResourceDiscoveryResult:
        return ResourceDiscoveryResult(
            robots_txt="User-agent: *",
            sitemap_xml="<urlset></urlset>",
            llms_txt="# Example",
            robots_status_code=200,
            sitemap_status_code=200,
            llms_status_code=200,
            discovered_resources=["robots_txt", "sitemap_xml", "llms_txt"],
        )


class _FakeApiDiscovery:
    def __init__(self, url: str, http_client) -> None:
        pass

    def discover(self) -> ApiDiscoveryResult:
        return ApiDiscoveryResult(
            openapi_urls=["https://www.example.com/openapi.json"],
            tested_urls={"https://www.example.com/openapi.json": 200},
        )


class _FakeFrontendAnalyzer:
    def __init__(self, javascript_files, http_client) -> None:
        self._javascript_files = javascript_files

    def analyze(self) -> FrontendAnalysisResult:
        return FrontendAnalysisResult(
            javascript_files_analyzed=list(self._javascript_files),
            discovered_api_urls=["/api/products"],
            discovered_api_patterns=["rest"],
        )


class _NoApiExposureDiscovery:
    def __init__(self, url: str, http_client) -> None:
        pass

    def discover(self) -> ApiDiscoveryResult:
        return ApiDiscoveryResult(tested_urls={"https://www.example.com/openapi.json": 404})


class _NoJsFrontendAnalyzer:
    def __init__(self, javascript_files, http_client) -> None:
        pass

    def analyze(self) -> FrontendAnalysisResult:
        return FrontendAnalysisResult()


class _FailingResourceDiscovery:
    """Simulates ResourceDiscovery itself surfacing per-resource errors."""

    def __init__(self, url: str, http_client) -> None:
        pass

    def discover(self) -> ResourceDiscoveryResult:
        return ResourceDiscoveryResult(
            errors=[
                CollectionError(step="robots_txt", message="timed out"),
                CollectionError(step="sitemap_xml", message="connection refused"),
                CollectionError(step="llms_txt", message="connection refused"),
            ]
        )


def test_complete_successful_collection() -> None:
    """All tools succeed: every WebsiteEvidence field should be populated."""
    agent = _make_agent(homepage_response=_homepage_response())

    evidence = agent.collect(URL)
    _print_evidence("complete successful collection", evidence)

    assert evidence.url == URL
    assert evidence.html == SAMPLE_HTML
    assert evidence.status_code == 200
    assert evidence.title == "Example"
    assert evidence.language == "en"
    assert evidence.javascript_files == ["https://www.example.com/app.js"]
    assert evidence.structured_data == {
        "json-ld": [{"@type": "Organization"}],
        "microdata": [],
        "rdfa": [],
    }
    assert evidence.robots_txt == "User-agent: *"
    assert evidence.sitemap_xml == "<urlset></urlset>"
    assert evidence.llms_txt == "# Example"
    assert evidence.api_analysis["openapi_urls"] == [
        "https://www.example.com/openapi.json"
    ]
    assert evidence.api_candidates == {"https://www.example.com/openapi.json": 200}
    assert evidence.frontend_analysis["discovered_api_urls"] == ["/api/products"]
    assert evidence.errors == []


def test_website_without_api_exposure() -> None:
    """HTTP + HTML succeed, but no API/MCP surface is detected."""
    agent = _make_agent(
        homepage_response=_homepage_response(),
        api_discovery_cls=_NoApiExposureDiscovery,
        frontend_analyzer_cls=_NoJsFrontendAnalyzer,
    )

    evidence = agent.collect(URL)
    _print_evidence("website without API exposure", evidence)

    assert evidence.status_code == 200
    assert evidence.title == "Example"
    assert evidence.api_analysis["openapi_urls"] == []
    assert evidence.api_candidates == {"https://www.example.com/openapi.json": 404}
    assert evidence.frontend_analysis["discovered_api_urls"] == []
    assert evidence.errors == []


def test_website_unavailable() -> None:
    """HttpClient fails outright: evidence stays mostly empty, no exception."""
    agent = _make_agent(homepage_error=ConnectionFailedError("connection refused"))

    evidence = agent.collect(URL)
    _print_evidence("website unavailable", evidence)

    assert evidence.html is None
    assert evidence.status_code is None
    assert evidence.title is None
    assert evidence.javascript_files == []
    # Resource/API discovery are independent of the homepage fetch and
    # still run.
    assert evidence.robots_txt == "User-agent: *"
    assert evidence.api_analysis["openapi_urls"] == [
        "https://www.example.com/openapi.json"
    ]

    error_steps = {error.step for error in evidence.errors}
    assert "http_fetch" in error_steps


def test_partial_tool_failure_is_isolated() -> None:
    """One tool (ApiDiscovery) raises; the rest of collection still completes."""
    agent = _make_agent(
        homepage_response=_homepage_response(),
        api_discovery_cls=FailingTool,
    )

    evidence = agent.collect(URL)
    _print_evidence("partial tool failure (api_discovery)", evidence)

    # Unaffected steps still populated.
    assert evidence.html == SAMPLE_HTML
    assert evidence.title == "Example"
    assert evidence.structured_data["json-ld"] == [{"@type": "Organization"}]
    assert evidence.robots_txt == "User-agent: *"
    assert evidence.frontend_analysis["discovered_api_urls"] == ["/api/products"]

    # Failing step recorded, but did not affect anything else and API
    # fields stay at their defaults.
    assert evidence.api_analysis == {}
    assert evidence.api_candidates == {}
    error_steps = {error.step for error in evidence.errors}
    assert error_steps == {"api_discovery"}


def test_resource_discovery_failure() -> None:
    """robots.txt/sitemap.xml/llms.txt are all unavailable."""
    agent = _make_agent(
        homepage_response=_homepage_response(),
        resource_discovery_cls=_FailingResourceDiscovery,
    )

    evidence = agent.collect(URL)
    _print_evidence("resource discovery failure", evidence)

    assert evidence.robots_txt is None
    assert evidence.sitemap_xml is None
    assert evidence.llms_txt is None

    # Unaffected steps still populated.
    assert evidence.title == "Example"
    assert evidence.api_analysis["openapi_urls"] == [
        "https://www.example.com/openapi.json"
    ]

    error_steps = {error.step for error in evidence.errors}
    assert error_steps == {"robots_txt", "sitemap_xml", "llms_txt"}


def test_run_accepts_standard_input_contract() -> None:
    """`run({"url": ...})` delegates to `collect` with that URL."""
    agent = _make_agent(homepage_response=_homepage_response())

    evidence = agent.run({"url": URL})
    _print_evidence("run() with standard input contract", evidence)

    assert evidence.url == URL
    assert evidence.title == "Example"


def test_invalid_url_short_circuits() -> None:
    """A malformed URL never reaches any tool and is reported as an error."""
    agent = _make_agent(homepage_response=_homepage_response())

    evidence = agent.collect("not-a-url")
    _print_evidence("invalid URL", evidence)

    assert evidence.html is None
    assert evidence.errors[0].step == "url_validation"


if __name__ == "__main__":
    test_complete_successful_collection()
    test_website_without_api_exposure()
    test_website_unavailable()
    test_partial_tool_failure_is_isolated()
    test_resource_discovery_failure()
    test_run_accepts_standard_input_contract()
    test_invalid_url_short_circuits()
    print("All tests passed.")
