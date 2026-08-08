"""AutoFix Orchestrator Agent.

This module is the coordination layer of the AutoFix extension
pipeline, mirroring the role `OrchestratorAgent` plays for the base
ARAS pipeline. It sits between the existing Agentic Readiness Report
(a `RecommendationResult`, produced upstream by `RecommendationAgent`)
and the future Simulation agent:

    1. `ModeSelectorAgent` decides GIT_REPO vs BLACK_BOX.
    2. `AutoFixAgent` proposes one fix per issue.
    3. `HumanValidationAgent` builds the review queue (security fixes
       always PENDING until a human decides; others may be
       auto-approved above a configured confidence threshold).

It also owns the "Rejeté" loop from the architecture diagram: when a
human rejects a fix via `decide()`, `retry_rejected()` sends only the
rejected issues back through the AutoFix agent for a fresh attempt,
and merges the result back into the pipeline without disturbing fixes
that were already approved or are still pending review.

This agent MUST NOT:
    - generate fixes itself (`AutoFixAgent`'s job)
    - decide whether a fix is acceptable (`HumanValidationAgent`'s
      job)
    - score anything or re-run the assessment (Simulation agent's
      job, not built yet)
    - compute recommendations itself (`RecommendationAgent`'s job —
      a `RecommendationResult` is a required input, not produced
      here)

It only calls the three collaborators above and combines their
outputs into one `AutoFixPipelineResult`.
"""

from __future__ import annotations

from typing import Any, Optional

from agents.autofix_agent import AutoFixAgent
from agents.human_validation_agent import HumanValidationAgent
from agents.mode_selector_agent import ModeSelectorAgent
from models.autofix_pipeline import AutoFixPipelineResult
from models.fix import AutoFixResult, ProposedFix
from models.recommendation import Recommendation, RecommendationResult
from models.validation import FixValidation, ValidationResult, ValidationStatus


class AutoFixOrchestratorAgent:
    """Coordinates the full AutoFix extension pipeline.

    This class holds no mode-detection, fix-generation, or
    validation-policy logic of its own. Like `OrchestratorAgent`, it
    is a pure coordination step, and every collaborator is injectable
    so callers (tests, in particular) can substitute fakes without
    monkeypatching or real git/network/LLM access.
    """

    def __init__(
        self,
        mode_selector_agent: Optional[ModeSelectorAgent] = None,
        autofix_agent: Optional[AutoFixAgent] = None,
        human_validation_agent: Optional[HumanValidationAgent] = None,
    ) -> None:
        """Initialize the orchestrator, optionally overriding its collaborators.

        Args:
            mode_selector_agent: Collaborator used to pick GIT_REPO vs
                BLACK_BOX. Must expose
                `.select(repo_path, repo_url) -> ModeSelection`.
                Defaults to a real `ModeSelectorAgent`.
            autofix_agent: Collaborator used to propose fixes. Must
                expose
                `.propose_fixes(recommendation_result, mode_selection)
                -> AutoFixResult`. Defaults to a real `AutoFixAgent`.
            human_validation_agent: Collaborator used to build and
                update the review queue. Must expose
                `.review(autofix_result) -> ValidationResult` and
                `.decide(validation_result, fix_index, approved,
                reviewer, note) -> ValidationResult`. Defaults to a
                real `HumanValidationAgent` (auto-approval disabled).
        """
        self._mode_selector_agent = mode_selector_agent or ModeSelectorAgent()
        self._autofix_agent = autofix_agent or AutoFixAgent()
        self._human_validation_agent = (
            human_validation_agent or HumanValidationAgent()
        )

    def run(self, input_data: dict[str, Any]) -> AutoFixPipelineResult:
        """Run the pipeline given the standard AutoFix input contract.

        Args:
            input_data: A dict of the form
                `{"recommendation_result": RecommendationResult,
                "repo_path": "...", "repo_url": "..."}`.
                `repo_path` and `repo_url` are optional (see
                `ModeSelectorAgent.select`).

        Returns:
            The resulting `AutoFixPipelineResult`.
        """
        return self.execute(
            recommendation_result=input_data["recommendation_result"],
            repo_path=input_data.get("repo_path"),
            repo_url=input_data.get("repo_url"),
        )

    def execute(
        self,
        recommendation_result: RecommendationResult,
        repo_path: Optional[str] = None,
        repo_url: Optional[str] = None,
    ) -> AutoFixPipelineResult:
        """Run mode selection, AutoFix, and human validation in sequence.

        Args:
            recommendation_result: Output of
                `RecommendationAgent.evaluate` — the Agentic Readiness
                Report's recommendations, i.e. the "Extension
                proposée" input from the architecture diagram.
            repo_path: Local git working directory, if the caller
                already has one checked out. Forwarded to
                `ModeSelectorAgent.select`.
            repo_url: Remote git URL to clone, used only when
                `repo_path` is absent or invalid. Forwarded to
                `ModeSelectorAgent.select`.

        Returns:
            An `AutoFixPipelineResult` bundling the mode selection,
            the proposed fixes, and the initial review queue.
        """
        mode_selection = self._mode_selector_agent.select(
            repo_path=repo_path,
            repo_url=repo_url,
        )

        autofix_result = self._autofix_agent.propose_fixes(
            recommendation_result,
            mode_selection,
        )

        validation_result = self._human_validation_agent.review(autofix_result)

        return AutoFixPipelineResult(
            mode_selection=mode_selection,
            autofix_result=autofix_result,
            validation_result=validation_result,
        )

    def decide(
        self,
        pipeline_result: AutoFixPipelineResult,
        fix_index: int,
        approved: bool,
        reviewer: str,
        note: str = "",
    ) -> AutoFixPipelineResult:
        """Record a human decision for one fix, without touching the rest.

        Thin pass-through to `HumanValidationAgent.decide` that keeps
        callers working with a single `AutoFixPipelineResult` instead
        of juggling the underlying `ValidationResult` directly.

        Args:
            pipeline_result: The `AutoFixPipelineResult` to update.
            fix_index: Index into
                `pipeline_result.validation_result.validations`.
            approved: `True` to approve the fix, `False` to reject it.
            reviewer: Identifier of the human making the decision.
                Required and non-empty (see
                `HumanValidationAgent.decide`).
            note: Optional free-text reviewer comment.

        Returns:
            A new `AutoFixPipelineResult` with the updated
            `validation_result`, leaving `mode_selection` and
            `autofix_result` untouched.
        """
        updated_validation = self._human_validation_agent.decide(
            pipeline_result.validation_result,
            fix_index=fix_index,
            approved=approved,
            reviewer=reviewer,
            note=note,
        )

        return AutoFixPipelineResult(
            mode_selection=pipeline_result.mode_selection,
            autofix_result=pipeline_result.autofix_result,
            validation_result=updated_validation,
        )

    def retry_rejected(
        self,
        pipeline_result: AutoFixPipelineResult,
        recommendation_result: RecommendationResult,
    ) -> AutoFixPipelineResult:
        """Send every REJECTED fix back through the AutoFix agent.

        This is the "Rejeté" loop from the architecture diagram: a
        human rejection routes back to the AutoFix agent, not to Mode
        Selector (the operating mode doesn't change mid-review) and
        not to the caller (no manual re-invocation of `execute()`
        should be needed).

        Fixes that are `APPROVED` or still `PENDING` are left exactly
        as they are; only `REJECTED` entries are replaced by a fresh
        `AutoFixAgent` attempt and re-enter the queue as `PENDING`
        (or auto-approved, per the same policy `execute()` uses).

        Args:
            pipeline_result: The `AutoFixPipelineResult` containing
                the rejected fixes to retry. Its `mode_selection` is
                reused unchanged for the retry.
            recommendation_result: The same `RecommendationResult`
                originally passed to `execute()`, used to look back up
                the full `Recommendation` (issue, category, RAG
                context, ...) behind each rejected fix.

        Returns:
            A new `AutoFixPipelineResult` with rejected fixes
            replaced by new proposals. If nothing was `REJECTED`,
            returns `pipeline_result` unchanged.
        """
        rejected_issues = {
            fix.issue for fix in pipeline_result.validation_result.rejected_fixes
        }

        if not rejected_issues:
            return pipeline_result

        retry_recommendations = [
            recommendation
            for recommendation in recommendation_result.recommendations
            if recommendation.issue in rejected_issues
        ]

        retry_recommendation_result = RecommendationResult(
            recommendations=retry_recommendations,
            total_issues=len(retry_recommendations),
            rag_sources_used=recommendation_result.rag_sources_used,
        )

        retry_autofix_result = self._autofix_agent.propose_fixes(
            retry_recommendation_result,
            pipeline_result.mode_selection,
        )

        retry_validation_result = self._human_validation_agent.review(
            retry_autofix_result
        )

        merged_autofix_result = self._merge_autofix_results(
            pipeline_result.autofix_result,
            retry_autofix_result,
            rejected_issues,
        )

        merged_validation_result = self._merge_validation_results(
            pipeline_result.validation_result,
            retry_validation_result,
            rejected_issues,
        )

        return AutoFixPipelineResult(
            mode_selection=pipeline_result.mode_selection,
            autofix_result=merged_autofix_result,
            validation_result=merged_validation_result,
        )

    # ------------------------------------------------------------------
    # Merge helpers for the "Rejeté" retry loop
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_autofix_results(
        original: AutoFixResult,
        retry: AutoFixResult,
        retried_issues: set[str],
    ) -> AutoFixResult:
        """Replace retried fixes in `original.fixes`, keeping the rest as-is.

        Args:
            original: The `AutoFixResult` from the previous attempt.
            retry: The `AutoFixResult` from re-running just the
                rejected issues.
            retried_issues: The set of issue texts that were retried.

        Returns:
            A new `AutoFixResult` with retried entries swapped in and
            aggregate counts recomputed.
        """
        retry_by_issue = {fix.issue: fix for fix in retry.fixes}

        merged_fixes: list[ProposedFix] = [
            retry_by_issue.get(fix.issue, fix)
            for fix in original.fixes
            if fix.issue not in retried_issues or fix.issue in retry_by_issue
        ]

        rule_based_count = sum(
            1 for fix in merged_fixes if fix.fix_type == "rule_based"
        )
        llm_generated_count = sum(
            1 for fix in merged_fixes if fix.fix_type == "llm_generated"
        )

        return AutoFixResult(
            fixes=merged_fixes,
            total_fixes=len(merged_fixes),
            rule_based_count=rule_based_count,
            llm_generated_count=llm_generated_count,
            mode=original.mode,
        )

    @staticmethod
    def _merge_validation_results(
        original: ValidationResult,
        retry: ValidationResult,
        retried_issues: set[str],
    ) -> ValidationResult:
        """Replace retried validations in `original.validations`, keeping the rest.

        Args:
            original: The `ValidationResult` from the previous
                attempt (the one containing the REJECTED entries).
            retry: The `ValidationResult` for the fresh proposals
                covering just the retried issues.
            retried_issues: The set of issue texts that were retried.

        Returns:
            A new `ValidationResult` with retried entries swapped in
            (each reset to whatever `HumanValidationAgent.review`
            decided: PENDING, or auto-APPROVED) and aggregate counts
            recomputed.
        """
        retry_by_issue = {v.fix.issue: v for v in retry.validations}

        merged_validations: list[FixValidation] = [
            retry_by_issue.get(validation.fix.issue, validation)
            for validation in original.validations
            if validation.fix.issue not in retried_issues
            or validation.fix.issue in retry_by_issue
        ]

        approved = sum(
            1 for v in merged_validations if v.status == ValidationStatus.APPROVED
        )
        rejected = sum(
            1 for v in merged_validations if v.status == ValidationStatus.REJECTED
        )
        pending = sum(
            1 for v in merged_validations if v.status == ValidationStatus.PENDING
        )

        return ValidationResult(
            validations=merged_validations,
            mode=original.mode,
            approved_count=approved,
            rejected_count=rejected,
            pending_count=pending,
        )