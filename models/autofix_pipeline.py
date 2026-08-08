"""Data contract for the AutoFix Pipeline Orchestrator.

This module defines the single output type produced by
`AutoFixOrchestratorAgent`: the bundled result of running the
`ModeSelectorAgent`, `AutoFixAgent`, and `HumanValidationAgent` in
sequence for one set of recommendations.

No coordination logic belongs here — this is a data container only,
following the same pattern as `models/mode.py`, `models/fix.py`, and
`models/validation.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from models.fix import AutoFixResult
from models.mode import ModeSelection
from models.validation import ValidationResult


@dataclass(frozen=True)
class AutoFixPipelineResult:
    """Aggregate result of running the whole AutoFix extension pipeline.

    Attributes:
        mode_selection: Output of `ModeSelectorAgent.select`.
        autofix_result: Output of `AutoFixAgent.propose_fixes`.
        validation_result: Output of `HumanValidationAgent.review`
            (or the latest `HumanValidationAgent.decide` /
            `AutoFixOrchestratorAgent.retry_rejected` call).
        ready_for_simulation: Convenience flag: `True` once every
            fix has been reviewed (no `PENDING` entries left) and at
            least one fix was `APPROVED`. This is the signal the
            (future) Simulation agent should wait for.
    """

    mode_selection: ModeSelection
    autofix_result: AutoFixResult
    validation_result: ValidationResult

    @property
    def ready_for_simulation(self) -> bool:
        """Whether this result is ready to hand off to the Simulation agent."""
        return (
            self.validation_result.is_fully_reviewed
            and self.validation_result.approved_count > 0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return {
            "mode_selection": self.mode_selection.to_dict(),
            "autofix_result": self.autofix_result.to_dict(),
            "validation_result": self.validation_result.to_dict(),
            "ready_for_simulation": self.ready_for_simulation,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string.

        Args:
            indent: Number of spaces to indent nested JSON structures.

        Returns:
            A JSON string representation of the result.
        """
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)