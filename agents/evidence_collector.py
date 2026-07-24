"""Evidence Collector Agent.

This module is the orchestration ("perception") layer of ARAS. It
calls each `tools/` module in a fixed order, isolates the failure of
any single tool so the rest of collection can proceed, and aggregates
every raw observation into a single `WebsiteEvidence` snapshot.

This agent MUST NOT:
    - calculate scores
    - evaluate Agentic Readiness criteria
    - generate recommendations
    - use LLM reasoning
    - make any decision about readiness

It only calls tools and copies their raw output onto `WebsiteEvidence`.
Scoring and judgment belong to a later, separate layer.
"""

from __future__ import annotations

from typing import Any, Callable, Optional
from urllib.parse import urlparse

from models.evidence import WebsiteEvidence
from tools.api_discovery import ApiDiscovery
from tools.frontend_analyzer import FrontendAnalyzer
from tools.html_parser import HtmlParser
from tools.http_client import HttpClient
from tools.resource_discovery import ResourceDiscovery
from tools.schema_extractor import SchemaExtractor


class EvidenceCollectorAgent:
    """Orchestrates the evidence-collection tools for a single website.

    Every tool is called independently and every step is isolated: a
    failure in one step is recorded on `WebsiteEvidence.errors` and
    collection continues with the remaining steps rather than aborting.
    The tool classes used for each step are injectable so callers
    (tests, in particular) can substitute fakes without monkeypatching.
    """

    def __init__(
        self,
        http_client: Optional[HttpClient] = None,
        html_parser_cls: type = HtmlParser,
        schema_extractor_cls: type = SchemaExtractor,
        resource_discovery_cls: type = ResourceDiscovery,
        api_discovery_cls: type = ApiDiscovery,
        frontend_analyzer_cls: type = FrontendAnalyzer,
    ) -> None:
        """Initialize the agent, optionally overriding its collaborators.

        Args:
            http_client: A pre-configured `HttpClient` (or compatible
                fake) to use for every network call. If omitted, a new
                `HttpClient` is created for the duration of `collect`
                and closed afterwards.
            html_parser_cls: Class used to parse the homepage HTML.
                Must accept `(html, base_url=...)` and expose `.parse()`.
            schema_extractor_cls: Class used to extract structured data.
                Must accept `(html)` and expose `.extract()`.
            resource_discovery_cls: Class used to discover standard
                resources. Must accept `(url, http_client)` and expose
                `.discover()`.
            api_discovery_cls: Class used to discover API exposure.
                Must accept `(url, http_client)` and expose `.discover()`.
            frontend_analyzer_cls: Class used to analyze frontend
                JavaScript. Must accept `(javascript_files, http_client)`
                and expose `.analyze()`.
        """
        self._http_client = http_client
        self._html_parser_cls = html_parser_cls
        self._schema_extractor_cls = schema_extractor_cls
        self._resource_discovery_cls = resource_discovery_cls
        self._api_discovery_cls = api_discovery_cls
        self._frontend_analyzer_cls = frontend_analyzer_cls

    def run(self, input_data: dict[str, Any]) -> WebsiteEvidence:
        """Collect evidence given the agent's standard input contract.

        Args:
            input_data: A dict of the form `{"url": "https://example.com"}`.

        Returns:
            The resulting `WebsiteEvidence`.
        """
        return self.collect(input_data["url"])

    def collect(self, url: str) -> WebsiteEvidence:
        """Collect all raw evidence available for a single website.

        Args:
            url: The website URL to collect evidence from.

        Returns:
            A `WebsiteEvidence` snapshot. Every field that could not be
            collected is left at its default; failures are recorded in
            `errors` rather than raised.
        """
        evidence = WebsiteEvidence(url=url)

        if not self._is_valid_url(url):
            evidence.add_error("url_validation", f"Invalid URL: '{url}'")
            return evidence

        owns_client = self._http_client is None
        http_client = self._http_client or HttpClient()
        try:
            self._run_step(
                "http_fetch", evidence, lambda: self._collect_homepage(url, http_client, evidence)
            )
            self._run_step(
                "schema_extraction",
                evidence,
                lambda: self._collect_structured_data(evidence),
            )
            self._run_step(
                "resource_discovery",
                evidence,
                lambda: self._collect_resources(url, http_client, evidence),
            )
            self._run_step(
                "api_discovery",
                evidence,
                lambda: self._collect_api_analysis(url, http_client, evidence),
            )
            self._run_step(
                "frontend_analysis",
                evidence,
                lambda: self._collect_frontend_analysis(http_client, evidence),
            )
        finally:
            if owns_client:
                http_client.close()

        return evidence

    # ------------------------------------------------------------------
    # URL validation
    # ------------------------------------------------------------------

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Determine whether a URL is well-formed enough to attempt collection.

        Args:
            url: The URL to validate.

        Returns:
            True if the URL has an `http`/`https` scheme and a host.
        """
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    # ------------------------------------------------------------------
    # Step isolation
    # ------------------------------------------------------------------

    @staticmethod
    def _run_step(
        step_name: str, evidence: WebsiteEvidence, step: Callable[[], None]
    ) -> None:
        """Run a single collection step, isolating any failure it raises.

        Args:
            step_name: Name recorded on `WebsiteEvidence.errors` if the
                step fails.
            evidence: The in-progress evidence record.
            step: A zero-argument callable performing the step.
        """
        try:
            step()
        except Exception as exc:  # noqa: BLE001 - isolate any tool failure
            evidence.add_error(step_name, str(exc))

    # ------------------------------------------------------------------
    # Homepage: HttpClient + HtmlParser
    # ------------------------------------------------------------------

    def _collect_homepage(
        self, url: str, http_client: HttpClient, evidence: WebsiteEvidence
    ) -> None:
        """Fetch the homepage and parse it into `evidence`.

        Args:
            url: The website URL to fetch.
            http_client: The `HttpClient` to issue the request with.
            evidence: The in-progress evidence record to populate.

        Raises:
            HttpClientError: If the homepage request fails at the
                transport level. Caught by `_run_step`.
        """
        response = http_client.get(url)

        evidence.html = response.content
        evidence.headers = dict(response.headers)
        evidence.status_code = response.status_code
        evidence.response_time = response.response_time

        parsed = self._html_parser_cls(response.content, base_url=response.final_url).parse()
        evidence.title = parsed.title
        evidence.language = parsed.language
        evidence.meta_tags = parsed.meta_tags
        evidence.canonical = parsed.canonical
        evidence.open_graph = parsed.open_graph
        evidence.robots_meta = parsed.robots_meta
        evidence.favicon = parsed.favicon
        evidence.internal_links = parsed.internal_links
        evidence.external_links = parsed.external_links
        evidence.javascript_files = parsed.javascript_files
        evidence.css_files = parsed.css_files
        evidence.semantic_tags = parsed.semantic_tags
        evidence.headings = parsed.headings
        evidence.images_total = parsed.images_total
        evidence.images_with_alt = parsed.images_with_alt
        evidence.text_length = parsed.text_length
        evidence.html_length = parsed.html_length

    # ------------------------------------------------------------------
    # Structured data: SchemaExtractor
    # ------------------------------------------------------------------

    def _collect_structured_data(self, evidence: WebsiteEvidence) -> None:
        """Extract structured data from the already-collected homepage HTML.

        A no-op if the homepage HTML was never retrieved.

        Args:
            evidence: The in-progress evidence record to populate.
        """
        if not evidence.html:
            return
        result = self._schema_extractor_cls(evidence.html).extract()
        evidence.structured_data = {
            "json-ld": result.json_ld,
            "microdata": result.microdata,
            "rdfa": result.rdfa,
        }

    # ------------------------------------------------------------------
    # Standard resources: ResourceDiscovery
    # ------------------------------------------------------------------

    def _collect_resources(
        self, url: str, http_client: HttpClient, evidence: WebsiteEvidence
    ) -> None:
        """Discover robots.txt, sitemap.xml, and llms.txt into `evidence`.

        Args:
            url: The website URL to discover resources for.
            http_client: The `HttpClient` to issue requests with.
            evidence: The in-progress evidence record to populate.
        """
        result = self._resource_discovery_cls(url, http_client).discover()
        evidence.robots_txt = result.robots_txt
        evidence.sitemap_xml = result.sitemap_xml
        evidence.llms_txt = result.llms_txt
        for error in result.errors:
            evidence.add_error(error.step, error.message)

    # ------------------------------------------------------------------
    # API exposure: ApiDiscovery
    # ------------------------------------------------------------------

    def _collect_api_analysis(
        self, url: str, http_client: HttpClient, evidence: WebsiteEvidence
    ) -> None:
        """Discover API exposure into `evidence`.

        Args:
            url: The website URL to discover API exposure for.
            http_client: The `HttpClient` to issue requests with.
            evidence: The in-progress evidence record to populate.
        """
        result = self._api_discovery_cls(url, http_client).discover()
        evidence.api_analysis = result.to_dict()
        evidence.api_candidates = dict(result.tested_urls)

    # ------------------------------------------------------------------
    # Frontend JavaScript: FrontendAnalyzer
    # ------------------------------------------------------------------

    def _collect_frontend_analysis(
        self, http_client: HttpClient, evidence: WebsiteEvidence
    ) -> None:
        """Analyze the homepage's JavaScript files into `evidence`.

        A no-op (produces an empty analysis) if the homepage had no
        `<script src="...">` resources, e.g. because the homepage fetch
        failed.

        Args:
            http_client: The `HttpClient` to download JavaScript with.
            evidence: The in-progress evidence record to populate.
        """
        result = self._frontend_analyzer_cls(evidence.javascript_files, http_client).analyze()
        evidence.frontend_analysis = result.to_dict()
