"""Data contract for the AutoFix Agent.

This module defines the output types produced by the `AutoFixAgent`:
one `ProposedFix` per issue coming from the Recommendation Agent, and
the aggregate `AutoFixResult` for a full run.

No fix generation, git operations, or LLM calls belong here — this is
a data container only, following the same pattern as
`models/mode.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, List


@dataclass(frozen=True)
class ProposedFix:
    """A single proposed fix for one detected issue.

    Attributes:
        issue: The issue text this fix addresses (matches
            `Recommendation.issue`).
        category: The originating category (e.g. `"discoverability"`,
            `"security"`).
        fix_type: How this fix was produced: `"rule_based"` (a small,
            deterministic, framework-agnostic patch) or
            `"llm_generated"` (produced by the LLM using RAG
            context).
        mode: The `OperatingMode` value (`"git_repo"` or
            `"black_box"`) the pipeline was running in when this fix
            was produced — copied from `ModeSelection.mode.value`.
        confidence: Confidence score in [0, 1]. Rule-based fixes are
            high confidence (0.9); LLM-generated fixes are medium
            confidence (0.5-0.7).
        diff: A real unified diff, only populated when `mode` is
            `"git_repo"`, fixes may be applied, and the target file
            was actually found on disk. Empty otherwise.
        instruction: Human-readable, always-populated fallback
            describing how to apply the fix manually. This is what a
            human sees in `black_box` mode, or when no diff could be
            computed.
        requires_human_validation: Whether this fix must go through
            the Human validation agent before being applied. Always
            `True` for now — security-relevant fixes are never
            auto-applied.
    """

    issue: str
    category: str
    fix_type: str
    mode: str
    confidence: float
    diff: str = ""
    instruction: str = ""
    requires_human_validation: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string.

        Args:
            indent: Number of spaces to indent nested JSON structures.

        Returns:
            A JSON string representation of the result.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass(frozen=True)
class AutoFixResult:
    """Aggregate result of running the AutoFix agent over a set of
    recommendations.

    Attributes:
        fixes: One `ProposedFix` per input issue.
        total_fixes: `len(fixes)`, kept explicit for easy reporting
            (same convention as `RecommendationResult.total_issues`).
        rule_based_count: Number of fixes produced by deterministic
            rules.
        llm_generated_count: Number of fixes produced by the LLM.
        mode: The `OperatingMode` value used for this entire run.
    """

    fixes: List[ProposedFix] = field(default_factory=list)
    total_fixes: int = 0
    rule_based_count: int = 0
    llm_generated_count: int = 0
    mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string.

        Args:
            indent: Number of spaces to indent nested JSON structures.

        Returns:
            A JSON string representation of the result.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)