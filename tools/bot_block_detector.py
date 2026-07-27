"""Bot/WAF block detection layer for the Evidence Collector.

This module is responsible ONLY for looking at a single already-fetched
HTTP response (status code, headers, and body) and deciding whether it
looks like a known anti-bot / WAF challenge or block page rather than
the site's real content. It performs no scoring, no quality judgment,
no recommendation generation, and no LLM calls — those concerns live
elsewhere.

Why this matters for ARAS: a site that is actually well-structured for
agents can still score near zero if every collection request was
silently served a Cloudflare/Akamai challenge page instead of the real
homepage. Surfacing `blocked=True` lets downstream agents (and human
readers of the report) distinguish "this site is not agent-ready" from
"we never actually saw this site."

The detector consumes only the raw response already collected by
`HttpClient`; it makes no network calls of its own.
"""

from __future__ import annotations

from typing import Optional

from models.bot_block import BotBlockDetectionResult
from models.http import HttpResponseEvidence

_BLOCK_STATUS_CODES = frozenset({403, 429, 503})

# Header values/names that strongly identify a specific WAF/CDN vendor.
_CLOUDFLARE_SERVER_HEADER_VALUES = ("cloudflare",)
_CLOUDFLARE_IDENTIFYING_HEADERS = ("cf-ray", "cf-mitigated")
_AKAMAI_SERVER_HEADER_VALUES = ("akamaighost",)
_AKAMAI_IDENTIFYING_HEADERS = ("x-akamai-transformed",)

# Body substrings (checked case-insensitively) that identify a specific
# vendor's challenge/block page copy.
_CLOUDFLARE_CONTENT_MARKERS = (
    "checking your browser before accessing",
    "attention required! | cloudflare",
    "cf-browser-verification",
    "cf_chl_",
    "cloudflare ray id",
    "please stand by, while we are checking your browser",
)
_AKAMAI_CONTENT_MARKERS = (
    "access denied</h1>\nyou don't have permission",
    "reference #",  # combined with "akamai" below to avoid false positives
)

# Body substrings (checked case-insensitively) that indicate an
# unbranded/generic bot-blocking or "prove you're human" page.
_GENERIC_CONTENT_MARKERS = (
    "verify you are human",
    "verify you are a human",
    "are you a robot",
    "unusual traffic from your computer",
    "unusual traffic from your network",
    "please enable javascript and cookies",
    "automated access to this",
    "bot detected",
    "detected unusual activity",
    "our systems have detected unusual traffic",
    "complete the security check to continue",
    "please complete the captcha",
    "access to this page has been denied",
)


class BotBlockDetector:
    """Detects whether an HTTP response is a bot-blocking / WAF page.

    This class holds no scoring or recommendation logic. It is a pure
    classification step: it inspects the status code, headers, and
    body of a single response and records what it observes into a
    `BotBlockDetectionResult`.
    """

    def __init__(self, response: Optional[HttpResponseEvidence]) -> None:
        """Initialize the detector with the response to analyze.

        Args:
            response: The `HttpResponseEvidence` to inspect (e.g. the
                homepage response returned by `HttpClient.get`), or
                `None` if no response was ever obtained (in which case
                `detect()` returns a non-blocked, empty result — an
                unreachable site is not the same thing as a blocked
                one).
        """
        self._response = response

    def detect(self) -> BotBlockDetectionResult:
        """Analyze the response and return a block-detection verdict.

        Returns:
            A `BotBlockDetectionResult` describing whether the
            response looks like a known bot/WAF block page and, if
            so, which provider and signals led to that conclusion.
        """
        if self._response is None:
            return BotBlockDetectionResult()

        status_code = self._response.status_code
        headers = {
            (key or "").lower(): (value or "").lower()
            for key, value in (self._response.headers or {}).items()
        }
        content_lower = (self._response.content or "").lower()

        result = BotBlockDetectionResult(status_code=status_code)

        cloudflare_signals = self._match_cloudflare(headers, content_lower)
        if cloudflare_signals:
            result.blocked = True
            result.provider = "cloudflare"
            result.matched_signals = cloudflare_signals
            result.reason = self._build_reason("Cloudflare", cloudflare_signals)
            return result

        akamai_signals = self._match_akamai(headers, content_lower)
        if akamai_signals:
            result.blocked = True
            result.provider = "akamai"
            result.matched_signals = akamai_signals
            result.reason = self._build_reason("Akamai", akamai_signals)
            return result

        generic_signals = self._match_generic(status_code, content_lower)
        if generic_signals:
            result.blocked = True
            result.provider = "generic"
            result.matched_signals = generic_signals
            result.reason = self._build_reason(
                "an unbranded anti-bot/WAF", generic_signals
            )
            return result

        return result

    # ------------------------------------------------------------------
    # Cloudflare
    # ------------------------------------------------------------------

    @staticmethod
    def _match_cloudflare(headers: dict[str, str], content_lower: str) -> list[str]:
        """Check for signals identifying a Cloudflare challenge/block page.

        Args:
            headers: Lower-cased response headers (names and values).
            content_lower: Lower-cased response body.

        Returns:
            Names of every Cloudflare-identifying signal that matched.
        """
        signals: list[str] = []

        server = headers.get("server", "")
        if any(marker in server for marker in _CLOUDFLARE_SERVER_HEADER_VALUES):
            signals.append(f"header:server={server}")

        for header_name in _CLOUDFLARE_IDENTIFYING_HEADERS:
            if header_name in headers:
                signals.append(f"header:{header_name}")

        for marker in _CLOUDFLARE_CONTENT_MARKERS:
            if marker in content_lower:
                signals.append(f"content:{marker}")

        return signals

    # ------------------------------------------------------------------
    # Akamai
    # ------------------------------------------------------------------

    @staticmethod
    def _match_akamai(headers: dict[str, str], content_lower: str) -> list[str]:
        """Check for signals identifying an Akamai challenge/block page.

        Args:
            headers: Lower-cased response headers (names and values).
            content_lower: Lower-cased response body.

        Returns:
            Names of every Akamai-identifying signal that matched.
        """
        signals: list[str] = []

        server = headers.get("server", "")
        if any(marker in server for marker in _AKAMAI_SERVER_HEADER_VALUES):
            signals.append(f"header:server={server}")

        for header_name in _AKAMAI_IDENTIFYING_HEADERS:
            if header_name in headers:
                signals.append(f"header:{header_name}")

        # "Reference #" alone is too generic (used by other vendors too),
        # so only count it once the word "akamai" itself also appears
        # somewhere in the body.
        if "akamai" in content_lower and "reference #" in content_lower:
            signals.append("content:akamai_reference_id")

        if "access denied" in content_lower and "you don't have permission" in content_lower:
            signals.append("content:access_denied_permission_page")

        return signals

    # ------------------------------------------------------------------
    # Generic / unbranded
    # ------------------------------------------------------------------

    @staticmethod
    def _match_generic(status_code: Optional[int], content_lower: str) -> list[str]:
        """Check for signals identifying an unbranded bot-blocking page.

        A generic verdict requires both a block-ish status code AND at
        least one "prove you're human" style phrase in the body, so a
        plain 403/503 error page (with no anti-bot copy) is never
        misclassified as a block.

        Args:
            status_code: The HTTP status code of the response.
            content_lower: Lower-cased response body.

        Returns:
            Names of every generic-block signal that matched, empty if
            the status code doesn't qualify as block-ish.
        """
        if status_code not in _BLOCK_STATUS_CODES:
            return []

        signals = [
            f"content:{marker}"
            for marker in _GENERIC_CONTENT_MARKERS
            if marker in content_lower
        ]
        if signals:
            signals.insert(0, f"status_code:{status_code}")
        return signals

    # ------------------------------------------------------------------
    # Reason formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _build_reason(label: str, signals: list[str]) -> str:
        """Build a short, human-readable explanation from matched signals.

        Args:
            label: Human-readable provider name (e.g. `"Cloudflare"`).
            signals: The matched signal names to summarize.

        Returns:
            A one-line reason string suitable for reports/logs.
        """
        preview = ", ".join(signals[:3])
        return f"{label} block/challenge page detected ({preview})"