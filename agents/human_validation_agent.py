"""Human Validation Agent.

This module is the third step of the AutoFix extension pipeline,
sitting between the `AutoFixAgent` and the Simulation agent. It never
decides anything by itself for security-sensitive fixes: its only job
is to build the review queue from an `AutoFixResult` and to record
human decisions against it.

Policy ("Sécurité toujours validée" from the architecture diagram):
    - Any fix with `category == "security"` is ALWAYS left `PENDING`
      after `review()`, no matter its confidence. The only way to
      move it to `APPROVED` is a real human calling `decide()` with a
      non-empty `reviewer`. It can never be auto-approved.
    - Non-security fixes MAY be auto-approved by `review()` if an
      `auto_approve_threshold` was configured and
      `fix.confidence >= auto_approve_threshold`.
    - Everything else stays `PENDING`, waiting for `decide()`.

This agent MUST NOT:
    - generate or edit fix content (AutoFix agent's job)
    - apply any fix to disk (a later step, once APPROVED)
    - re-run any assessment or scoring (Simulation agent's job)
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from models.fix import AutoFixResult, ProposedFix
from models.validation import FixValidation, ValidationResult, ValidationStatus

_SECURITY_CATEGORY = "security"
_AUTO_APPROVE_REVIEWER = "system"


class HumanValidationAgent:
    """Builds and updates the human review queue for proposed fixes."""

    def __init__(self, auto_approve_threshold: Optional[float] = None) -> None:
        """Initialize the agent.

        Args:
            auto_approve_threshold: If set, non-`security` fixes with
                `confidence >= auto_approve_threshold` are
                auto-approved by `review()` instead of waiting for a
                human. `None` (default) disables auto-approval
                entirely: every fix starts `PENDING`.

        Raises:
            ValueError: If `auto_approve_threshold` is provided but
                not within `[0, 1]`.
        """
        if auto_approve_threshold is not None and not (0.0 <= auto_approve_threshold <= 1.0):
            raise ValueError("auto_approve_threshold doit être dans [0, 1].")
        self._auto_approve_threshold = auto_approve_threshold

    def review(self, autofix_result: AutoFixResult) -> ValidationResult:
        """Build the initial review queue from an `AutoFixResult`.

        Args:
            autofix_result: Output of `AutoFixAgent.propose_fixes`.

        Returns:
            A `ValidationResult` with one `FixValidation` per input
            fix: `security` fixes and low-confidence fixes are
            `PENDING`; high-confidence non-security fixes are
            `APPROVED` only if `auto_approve_threshold` was set.
        """
        validations = [
            self._initial_validation(fix) for fix in autofix_result.fixes
        ]
        return self._build_result(validations, autofix_result.mode)

    def decide(
        self,
        validation_result: ValidationResult,
        fix_index: int,
        approved: bool,
        reviewer: str,
        note: str = "",
    ) -> ValidationResult:
        """Record a human decision for one fix in the queue.

        Args:
            validation_result: The `ValidationResult` to update.
            fix_index: Index into `validation_result.validations`
                (same order as the original `AutoFixResult.fixes`).
            approved: `True` to approve the fix, `False` to reject it.
            reviewer: Identifier of the human making the decision.
                Required and must be non-empty — this is what
                guarantees a `security` fix can never be approved
                without a real person behind the decision.
            note: Optional free-text comment, e.g. why a fix was
                rejected (useful context for the next AutoFix pass).

        Returns:
            A new `ValidationResult` with `validations[fix_index]`
            updated, leaving the input `validation_result` untouched.

        Raises:
            IndexError: If `fix_index` is out of range.
            ValueError: If `reviewer` is empty or blank.
        """
        if not reviewer or not reviewer.strip():
            raise ValueError("Un reviewer humain (non vide) est requis pour décider.")

        if not (0 <= fix_index < len(validation_result.validations)):
            raise IndexError(f"fix_index {fix_index} hors limites.")

        current = validation_result.validations[fix_index]
        new_status = ValidationStatus.APPROVED if approved else ValidationStatus.REJECTED

        updated = replace(
            current,
            status=new_status,
            reviewer=reviewer,
            note=note,
            auto_approved=False,
        )

        new_validations = list(validation_result.validations)
        new_validations[fix_index] = updated

        return self._build_result(new_validations, validation_result.mode)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _initial_validation(self, fix: ProposedFix) -> FixValidation:
        """Decide the starting `FixValidation` state for one fix.

        Args:
            fix: The `ProposedFix` to classify.

        Returns:
            A `PENDING` validation for `security` fixes and for any
            fix that doesn't clear the auto-approve threshold; an
            auto-`APPROVED` validation otherwise.
        """
        if fix.category == _SECURITY_CATEGORY:
            return FixValidation(fix=fix, status=ValidationStatus.PENDING)

        if (
            self._auto_approve_threshold is not None
            and fix.confidence >= self._auto_approve_threshold
        ):
            return FixValidation(
                fix=fix,
                status=ValidationStatus.APPROVED,
                reviewer=_AUTO_APPROVE_REVIEWER,
                note=(
                    f"Auto-approuvé : confiance {fix.confidence:.2f} "
                    f">= seuil {self._auto_approve_threshold:.2f}."
                ),
                auto_approved=True,
            )

        return FixValidation(fix=fix, status=ValidationStatus.PENDING)

    @staticmethod
    def _build_result(
        validations: list[FixValidation],
        mode: str,
    ) -> ValidationResult:
        """Assemble a `ValidationResult` and its convenience counts.

        Args:
            validations: The full list of `FixValidation` entries.
            mode: The `OperatingMode` value to carry through.

        Returns:
            The aggregate `ValidationResult`.
        """
        approved = sum(1 for v in validations if v.status == ValidationStatus.APPROVED)
        rejected = sum(1 for v in validations if v.status == ValidationStatus.REJECTED)
        pending = sum(1 for v in validations if v.status == ValidationStatus.PENDING)

        return ValidationResult(
            validations=validations,
            mode=mode,
            approved_count=approved,
            rejected_count=rejected,
            pending_count=pending,
        )