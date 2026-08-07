"""Data contract for the Human Validation Agent.

This module defines the output types produced by the
`HumanValidationAgent`: a `FixValidation` decision per `ProposedFix`
coming out of the AutoFix agent, and the aggregate `ValidationResult`
for a whole run.

No decision logic, security policy, or persistence belongs here —
this is a data container only, following the same pattern as
`models/mode.py` and `models/fix.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from models.fix import ProposedFix


class ValidationStatus(str, Enum):
    """The lifecycle of a single fix through human review.

    Attributes:
        PENDING: Awaiting a human decision. Nothing downstream may
            act on this fix yet.
        APPROVED: Cleared to move on to the Simulation agent, either
            by a human or (for non-security fixes only) by the
            configured auto-approve threshold.
        REJECTED: A human declined this fix. It should be routed back
            to the AutoFix agent for another attempt.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class FixValidation:
    """The validation state of a single proposed fix.

    Attributes:
        fix: The `ProposedFix` being reviewed.
        status: Current `ValidationStatus`.
        reviewer: Identifier of the human who made the decision
            (`None` while `PENDING`; `"system"` only for an
            auto-approval, which is never used for `security` fixes).
        note: Optional free-text reviewer comment (e.g. why a fix was
            rejected, to help the next AutoFix attempt).
        auto_approved: `True` only when `status` is `APPROVED` and no
            human reviewed it (confidence-threshold auto-approval).
            Always `False` for `security`-category fixes.
    """

    fix: ProposedFix
    status: ValidationStatus
    reviewer: Optional[str] = None
    note: str = ""
    auto_approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return {
            "fix": self.fix.to_dict(),
            "status": self.status.value,
            "reviewer": self.reviewer,
            "note": self.note,
            "auto_approved": self.auto_approved,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass(frozen=True)
class ValidationResult:
    """Aggregate result of running the Human validation agent over an
    `AutoFixResult`.

    Attributes:
        validations: One `FixValidation` per input fix, in the same
            order as `AutoFixResult.fixes`.
        mode: The `OperatingMode` value this run used (copied through
            from the `AutoFixResult`).
        approved_count: Convenience count of `APPROVED` validations.
        rejected_count: Convenience count of `REJECTED` validations.
        pending_count: Convenience count of `PENDING` validations.
    """

    validations: List[FixValidation] = field(default_factory=list)
    mode: str = ""
    approved_count: int = 0
    rejected_count: int = 0
    pending_count: int = 0

    @property
    def approved_fixes(self) -> List[ProposedFix]:
        """All fixes currently `APPROVED`, ready for the Simulation agent."""
        return [
            v.fix for v in self.validations
            if v.status == ValidationStatus.APPROVED
        ]

    @property
    def rejected_fixes(self) -> List[ProposedFix]:
        """All fixes currently `REJECTED`, to route back to AutoFix."""
        return [
            v.fix for v in self.validations
            if v.status == ValidationStatus.REJECTED
        ]

    @property
    def is_fully_reviewed(self) -> bool:
        """Whether no `PENDING` validation remains."""
        return self.pending_count == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert this result into a plain JSON-serializable dict.

        Returns:
            A dict representation suitable for `json.dumps`.
        """
        return {
            "mode": self.mode,
            "validations": [v.to_dict() for v in self.validations],
            "approved_count": self.approved_count,
            "rejected_count": self.rejected_count,
            "pending_count": self.pending_count,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize this result to a JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=indent, default=str)