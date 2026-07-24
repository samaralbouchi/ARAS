"""Data contract for the Schema Extractor.

This module defines the single output type produced by the Schema
Extractor: a flat, JSON-serializable snapshot of structured data
formats found in a raw HTML document. No quality analysis, scoring,
or recommendation logic belongs here — this is a data container only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class StructuredDataResult:
    """Structured data extracted from a single HTML document.

    This dataclass is the sole output of :class:`SchemaExtractor`. It
    never contains derived scores, judgments, or recommendations — only
    facts observed during extraction. Any format that yielded nothing
    is left as an empty list rather than causing the whole extraction
    to fail.

    Attributes:
        json_ld: Objects extracted from `<script type="application/ld+json">`
            tags. JSON arrays are flattened into individual objects.
        microdata: Objects extracted from elements using the
            `itemscope`/`itemtype`/`itemprop` microdata attributes.
        rdfa: Objects extracted from elements using the
            `vocab`/`typeof`/`property` RDFa attributes.
    """

    json_ld: list[dict[str, Any]] = field(default_factory=list)
    microdata: list[dict[str, Any]] = field(default_factory=list)
    rdfa: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert this extraction result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)
