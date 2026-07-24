"""Data contract for the Frontend Analyzer.

This module defines the single output type produced by the Frontend
Analyzer: a flat, JSON-serializable snapshot of API references found
via static analysis of frontend JavaScript resources. No scoring,
grading, or interpretation logic belongs here — this is a data
container only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class FrontendAnalysisResult:
    """API references extracted from a website's frontend JavaScript.

    This dataclass is the sole output of :class:`FrontendAnalyzer`. It
    never contains derived scores, judgments, or recommendations — only
    facts observed during static analysis. Any category that yielded
    nothing is left as an empty list rather than causing the whole
    analysis to fail.

    Attributes:
        javascript_files_analyzed: URLs of the JavaScript files that
            were successfully downloaded and scanned.
        discovered_api_urls: Concrete API-looking URL paths or full
            URLs found in the scanned JavaScript (e.g. `/api/products`,
            `/graphql`).
        discovered_api_patterns: The raw pattern category that matched
            for each discovery (e.g. `rest`, `rest_versioned`,
            `graphql`), aligned by occurrence rather than by index.
        graphql_references: GraphQL-specific endpoint references found
            in the scanned JavaScript.
        websocket_references: `ws://` or `wss://` URLs found in the
            scanned JavaScript.
        external_services: Known third-party service domains (e.g.
            `stripe.com`, `googleapis.com`) referenced in the scanned
            JavaScript.
    """

    javascript_files_analyzed: list[str] = field(default_factory=list)
    discovered_api_urls: list[str] = field(default_factory=list)
    discovered_api_patterns: list[str] = field(default_factory=list)
    graphql_references: list[str] = field(default_factory=list)
    websocket_references: list[str] = field(default_factory=list)
    external_services: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert this analysis result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)
