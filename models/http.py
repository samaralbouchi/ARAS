"""Data contract for the HTTP client layer.

This module defines the single output type produced by `HttpClient`: a
raw, unopinionated snapshot of an HTTP response. No HTML parsing,
metadata extraction, or scoring logic belongs here — this is a data
container only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class HttpResponseEvidence:
    """Raw snapshot of a single HTTP response.

    Attributes:
        requested_url: The URL that was originally requested.
        final_url: The URL after following any redirects.
        status_code: HTTP status code returned by the server.
        headers: Response headers as a plain string-keyed dict.
        content: Decoded response body text.
        content_type: Value of the `Content-Type` response header, if any.
        response_time: Total request duration, in seconds.
        content_length: Size of the response body, in bytes.
    """

    requested_url: str
    final_url: str
    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    content: str = ""
    content_type: Optional[str] = None
    response_time: float = 0.0
    content_length: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert this response snapshot into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)
