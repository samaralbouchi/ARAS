"""Data contract for the Simulation Agent.

This module defines the output types produced by the
`SimulationAgent`: a before/after score comparison per category,
computed from the fixes that were `APPROVED` by the Human validation
agent, and the aggregate `SimulationResult` for a whole run.

No re-scoring logic, diff application, or file I/O belongs here —
this is a data container only, following the same pattern as
`models/fix.py` and `models/validation.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, List, Optional

from models.fix import ProposedFix


@dataclass(frozen=True)
class CategorySimulation:
    """Before/after comparison for one analysis category.

    All `APPROVED` fixes for this category are applied together and
    scored once (cumulative simulation), not one score per fix. Each
    fix stays individually listed in `fixes_applied` so a future
    per-fix breakdown can be added without changing this contract.

    Attributes:
        category: The category being simulated (e.g.
            `"discoverability"`, `"security"`), matching
            `ProposedFix.category`.
        mode: The `OperatingMode` value this simulation ran in,
            copied from `ModeSelection.mode.value`.
        score_before: The category's original score, in [0, 100],
            copied from the source `AssessmentResult`.
        score_after: The category's recomputed score after applying
            `fixes_applied`, in [0, 100]. `None` when `skipped` is
            `True`.
        delta: `score_after - score_before`, rounded to 2 decimals.
            `None` when `skipped` is `True`.
        fixes_applied: The `APPROVED` fixes for this category that
            were actually applied for this simulation. Empty when
            `skipped` is `True`.
        skipped: Whether this category was left unsimulated (e.g.
            `BLACK_BOX` mode, no `repo_path`, or the diff could not
            be applied).
        skip_reason: Human-readable explanation, populated only when
            `skipped` is `True`.
    """

    category: str
    mode: str
    score_before: float
    score_after: Optional[float] = None
    delta: Optional[float] = None
    fixes_applied: List[ProposedFix] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return {
            "category": self.category,
            "mode": self.mode,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "delta": self.delta,
            "fixes_applied": [f.to_dict() for f in self.fixes_applied],
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass(frozen=True)
class SimulationResult:
    """Aggregate result of running the Simulation agent over an
    `AutoFixPipelineResult`.

    Attributes:
        category_simulations: One `CategorySimulation` per category
            that had at least one `APPROVED` fix. Categories with no
            approved fixes are not represented here.
        overall_score_before: The original `AssessmentResult.overall_score`.
        overall_score_after: Recomputed overall score: for each of
            the four categories, `score_after` when simulated,
            otherwise the original (unchanged) score — never zero or
            skipped by default. Rounded to 2 decimals.
        mode: The `OperatingMode` value this run used, copied
            through from the `ModeSelection`.
    """

    category_simulations: List[CategorySimulation] = field(default_factory=list)
    overall_score_before: float = 0.0
    overall_score_after: float = 0.0
    mode: str = ""

    @property
    def overall_delta(self) -> float:
        """`overall_score_after - overall_score_before`, rounded to 2 decimals."""
        return round(self.overall_score_after - self.overall_score_before, 2)

    @property
    def simulated_categories(self) -> List[CategorySimulation]:
        """All categories that were actually re-scored (not skipped)."""
        return [c for c in self.category_simulations if not c.skipped]

    @property
    def skipped_categories(self) -> List[CategorySimulation]:
        """All categories left unsimulated, with their `skip_reason`."""
        return [c for c in self.category_simulations if c.skipped]

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return {
            "mode": self.mode,
            "category_simulations": [c.to_dict() for c in self.category_simulations],
            "overall_score_before": self.overall_score_before,
            "overall_score_after": self.overall_score_after,
            "overall_delta": self.overall_delta,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)