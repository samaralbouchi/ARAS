"""Unit tests for :class:`ResourceDiscovery`.

Covers, using mocked HTTP responses only: successful discovery of all
three resources, all resources missing (404), a partial-failure mix
(one hit, one timeout, one 404), and a fully unreachable site. This
verifies that discovery degrades gracefully; it performs no scoring or
assertions about Agentic Readiness.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly (e.g. from an IDE "Run" button) by
# ensuring the project root is importable, not just the `tests/` folder.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.http import HttpResponseEvidence
from tools.http_client import (
    ConnectionFailedError,
    RequestTimeoutError,
)
from tools.resource_discovery import ResourceDiscovery

BASE_URL = "https://www.example.com"

ROBOTS_URL = "https://www.example.com/robots.txt"
SITEMAP_URL = "https://www.example.com/sitemap.xml"
LLMS_URL = "https://www.example.com/llms.txt"


class FakeHttpClient:
    """Stand-in for `HttpClient` that serves canned responses or errors by URL."""

    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses

    def get(self, url: str) -> HttpResponseEvidence:
        outcome = self._responses.get(url)
        if outcome is None:
            raise ConnectionFailedError(f"no mocked response for '{url}'")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(url: str, status_code: int, content: str = "") -> HttpResponseEvidence:
    return HttpResponseEvidence(
        requested_url=url,
        final_url=url,
        status_code=status_code,
        content=content,
    )


def test_successful_discovery() -> None:
    """All three resources exist and return 200."""
    client = FakeHttpClient(
        {
            ROBOTS_URL: _response(ROBOTS_URL, 200, "User-agent: *\nAllow: /"),
            SITEMAP_URL: _response(
                SITEMAP_URL, 200, "<urlset></urlset>"
            ),
            LLMS_URL: _response(LLMS_URL, 200, "# example.com\n> An example site."),
        }
    )

    result = ResourceDiscovery(BASE_URL, client).discover()

    assert result.robots_txt == "User-agent: *\nAllow: /"
    assert result.sitemap_xml == "<urlset></urlset>"
    assert result.llms_txt == "# example.com\n> An example site."
    assert result.robots_status_code == 200
    assert result.sitemap_status_code == 200
    assert result.llms_status_code == 200
    assert sorted(result.discovered_resources) == [
        "llms_txt",
        "robots_txt",
        "sitemap_xml",
    ]
    assert result.errors == []


def test_missing_resources() -> None:
    """All endpoints respond, but with 404."""
    client = FakeHttpClient(
        {
            ROBOTS_URL: _response(ROBOTS_URL, 404),
            SITEMAP_URL: _response(SITEMAP_URL, 404),
            LLMS_URL: _response(LLMS_URL, 404),
        }
    )

    result = ResourceDiscovery(BASE_URL, client).discover()

    assert result.robots_txt is None
    assert result.sitemap_xml is None
    assert result.llms_txt is None
    assert result.robots_status_code == 404
    assert result.sitemap_status_code == 404
    assert result.llms_status_code == 404
    assert result.discovered_resources == []
    assert result.errors == []


def test_partial_failure() -> None:
    """robots.txt succeeds, sitemap times out, llms.txt is missing entirely."""
    client = FakeHttpClient(
        {
            ROBOTS_URL: _response(ROBOTS_URL, 200, "User-agent: *"),
            SITEMAP_URL: RequestTimeoutError("timed out"),
            # LLMS_URL intentionally absent -> connection failure
        }
    )

    result = ResourceDiscovery(BASE_URL, client).discover()

    assert result.robots_txt == "User-agent: *"
    assert result.robots_status_code == 200
    assert result.discovered_resources == ["robots_txt"]

    assert result.sitemap_xml is None
    assert result.sitemap_status_code is None

    assert result.llms_txt is None
    assert result.llms_status_code is None

    error_steps = {error.step for error in result.errors}
    assert error_steps == {"sitemap_xml", "llms_txt"}


def test_website_unreachable() -> None:
    """Every request fails at the transport level: result stays empty, no exception."""
    client = FakeHttpClient(
        {
            ROBOTS_URL: ConnectionFailedError("connection refused"),
            SITEMAP_URL: ConnectionFailedError("connection refused"),
            LLMS_URL: ConnectionFailedError("connection refused"),
        }
    )

    result = ResourceDiscovery(BASE_URL, client).discover()

    assert result.robots_txt is None
    assert result.sitemap_xml is None
    assert result.llms_txt is None
    assert result.robots_status_code is None
    assert result.sitemap_status_code is None
    assert result.llms_status_code is None
    assert result.discovered_resources == []
    assert len(result.errors) == 3
    assert {error.step for error in result.errors} == {
        "robots_txt",
        "sitemap_xml",
        "llms_txt",
    }


if __name__ == "__main__":
    test_successful_discovery()
    test_missing_resources()
    test_partial_failure()
    test_website_unreachable()
    print("All tests passed.")
