"""Data contract for the API Discovery tool.

This module defines the single output type produced by
:class:`ApiDiscovery`: a flat, JSON-serializable snapshot of
machine-readable interfaces (OpenAPI/Swagger docs, raw API endpoints,
GraphQL, MCP) found on a website. No quality analysis, scoring, or
recommendation logic belongs here — this is a data container only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ApiDiscoveryResult:
    """Machine-readable interfaces discovered for a single website.

    This dataclass is the sole output of :class:`ApiDiscovery`. It
    never contains derived scores, judgments, or recommendations — only
    facts observed during discovery. Any category that yielded nothing
    is left as an empty list rather than causing the whole discovery
    process to fail.

    Attributes:
        openapi_urls: URLs that returned a successful response for a
            candidate OpenAPI specification location.
        swagger_urls: URLs that returned a successful response for a
            candidate Swagger UI location.
        redoc_urls: URLs that returned a successful response for a
            candidate ReDoc documentation location.
        api_documentation_urls: URLs that returned a successful
            response for a candidate general API documentation
            location.
        api_endpoints: URLs that returned a successful response for a
            candidate raw API entry point.
        graphql_endpoints: URLs that returned a successful response for
            a candidate GraphQL endpoint.
        mcp_endpoints: URLs that returned a successful response for a
            candidate MCP (Model Context Protocol) endpoint.
        mcp_resources: Names of MCP resources found in the JSON body of
            a discovered MCP endpoint.
        mcp_tools: Names of MCP tools found in the JSON body of a
            discovered MCP endpoint.
        tested_urls: Every URL that was probed during discovery, mapped
            to the HTTP status code returned. URLs that raised a
            transport-level error (timeout, connection failure, etc.)
            are omitted from this mapping.
    """

    openapi_urls: list[str] = field(default_factory=list)
    swagger_urls: list[str] = field(default_factory=list)
    redoc_urls: list[str] = field(default_factory=list)
    api_documentation_urls: list[str] = field(default_factory=list)
    api_endpoints: list[str] = field(default_factory=list)
    graphql_endpoints: list[str] = field(default_factory=list)
    mcp_endpoints: list[str] = field(default_factory=list)
    mcp_resources: list[str] = field(default_factory=list)
    mcp_tools: list[str] = field(default_factory=list)
    tested_urls: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert this discovery result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)
