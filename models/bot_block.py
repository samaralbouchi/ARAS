"""Data contract for the Bot/WAF Block Detector tool.

This module defines the single output type produced by
:class:`BotBlockDetector`: a flat, JSON-serializable verdict describing
whether an HTTP response looks like a known bot-blocking / WAF
challenge page (Akamai, Cloudflare, or an unbranded generic block)
rather than the real page content. No scoring, weighting, or
Agentic Readiness judgment belongs here — this is a raw detection
result only. Whatever an agent decides to do with `blocked=True`
(e.g. penalize a score, short-circuit further analysis) is a decision
made elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class BotBlockDetectionResult:
    """Verdict of a single bot/WAF block detection pass.

    This dataclass is the sole output of :class:`BotBlockDetector`. It
    never contains derived scores, judgments, or recommendations —
    only the raw observation that a response does or does not look
    like a known anti-bot block page, and which signals led to that
    conclusion.

    Attributes:
        blocked: Whether the response looks like a bot-blocking / WAF
            challenge page rather than genuine site content.
        provider: Best-guess identity of the blocking system, one of
            `"akamai"`, `"cloudflare"`, `"generic"`, or `None` if
            `blocked` is False.
        reason: Short, human-readable explanation of the verdict
            (e.g. `"Cloudflare block/challenge page detected (cf-ray
            header + 'checking your browser' text)"`).
        matched_signals: Names of the individual signals that fired
            (e.g. `"header:cf-ray"`, `"content:checking_your_browser"`).
            Empty if `blocked` is False.
        status_code: The HTTP status code that was analyzed, if any.
    """

    blocked: bool = False
    provider: Optional[str] = None
    reason: Optional[str] = None
    matched_signals: list[str] = field(default_factory=list)
    status_code: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert this detection result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)