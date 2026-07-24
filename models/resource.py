"""Data contract for the Resource Discovery tool.

This module defines the single output type produced by
:class:`ResourceDiscovery`: a flat, JSON-serializable snapshot of the
standard discoverability resources (robots.txt, sitemap.xml, llms.txt)
found on a website. No scoring, quality judgment, or recommendation
logic belongs here — this is a data container only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from models.evidence import CollectionError


@dataclass
class ResourceDiscoveryResult:
    """Standard discoverability resources found for a single website.

    This dataclass is the sole output of :class:`ResourceDiscovery`. It
    never contains derived scores, judgments, or recommendations — only
    facts observed during discovery. A resource that could not be
    retrieved is left at its default (None) rather than causing the
    whole discovery process to fail.

    Attributes:
        robots_txt: Raw contents of `/robots.txt`, if retrieved
            successfully.
        sitemap_xml: Raw contents of `/sitemap.xml`, if retrieved
            successfully.
        llms_txt: Raw contents of `/llms.txt`, if retrieved
            successfully.
        robots_status_code: HTTP status code observed for the
            `/robots.txt` request, if the request completed.
        sitemap_status_code: HTTP status code observed for the
            `/sitemap.xml` request, if the request completed.
        llms_status_code: HTTP status code observed for the
            `/llms.txt` request, if the request completed.
        discovered_resources: Names of resources that were found
            (returned a successful response), e.g. `"robots_txt"`.
        errors: Non-fatal failures encountered while retrieving
            individual resources.
    """

    robots_txt: Optional[str] = None
    sitemap_xml: Optional[str] = None
    llms_txt: Optional[str] = None

    robots_status_code: Optional[int] = None
    sitemap_status_code: Optional[int] = None
    llms_status_code: Optional[int] = None

    discovered_resources: list[str] = field(default_factory=list)

    errors: list[CollectionError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert this discovery result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)
