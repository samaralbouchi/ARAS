"""Simulation Agent.

This module is the closing step of the AutoFix extension pipeline. It
sits between the Human validation agent and the final enriched report:
given the fixes that were `APPROVED`, it answers the question the rest
of the pipeline cannot — "does this fix actually improve the score?"

    1. Group `APPROVED` fixes by category.
    2. In `GIT_REPO` mode, apply each fix's diff to a patched copy of
       the relevant `WebsiteEvidence` fields (never to the real repo
       on disk) and re-run the matching category agent to get a real
       before/after score.
    3. In `BLACK_BOX` mode — or when a diff cannot be applied — skip
       that category with a clear reason instead of guessing a score.

This agent MUST NOT:
    - decide whether a fix is acceptable (the Human validation
      agent's job)
    - propose fixes itself (the AutoFix agent's job)
    - implement any scoring criterion itself (the four analysis
      agents' job — this agent only re-runs them)
    - write anything to the caller's real repo (only to an in-memory
      patched `WebsiteEvidence` copy)

It only calls the four analysis agents already used by
`OrchestratorAgent` and combines their outputs into one
`SimulationResult`.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Callable, Optional

from agents.comprehension_agent import ComprehensionAgent
from agents.discoverability_agent import DiscoverabilityAgent
from agents.interaction_agent import InteractionAgent
from agents.security_agent import SecurityAgent
from models.assessment import AssessmentResult
from models.autofix_pipeline import AutoFixPipelineResult
from models.evidence import WebsiteEvidence
from models.fix import ProposedFix
from models.mode import OperatingMode
from models.simulation import CategorySimulation, SimulationResult

# Maps a patched file's basename (parsed from a `ProposedFix.diff`
# header, e.g. "+++ b/robots.txt") to the `WebsiteEvidence` field it
# corresponds to. Only files an analysis agent actually reads from
# `WebsiteEvidence` belong here. Extend this alongside new rule-based
# fix types in `AutoFixAgent` — a fix whose target file is not listed
# here is left unapplied (its category falls back to skipped, or to
# whatever other approved fixes in the same category *could* be
# applied).
_FILE_TO_EVIDENCE_FIELD: dict[str, str] = {
    "robots.txt": "robots_txt",
}

_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
_DIFF_TARGET_RE = re.compile(r"^\+\+\+ b/(.+)$")

_BLACK_BOX_SKIP_REASON = (
    "Mode black_box : pas d'accès au code source, impossible de "
    "réappliquer un fix pour re-scorer honnêtement."
)
_NO_APPLICABLE_FIX_REASON = (
    "Aucun fix approuvé de cette catégorie n'a pu être appliqué "
    "(diff vide ou fichier cible non pris en charge par la simulation)."
)


class SimulationAgent:
    """Computes real before/after scores for approved AutoFix fixes.

    Every collaborator is injectable so callers (tests, in
    particular) can substitute fakes without monkeypatching or real
    file-system access.
    """

    def __init__(
        self,
        discoverability_agent: Optional[DiscoverabilityAgent] = None,
        comprehension_agent: Optional[ComprehensionAgent] = None,
        interaction_agent: Optional[InteractionAgent] = None,
        security_agent: Optional[SecurityAgent] = None,
    ) -> None:
        """Initialize the agent, optionally overriding its collaborators.

        Args:
            discoverability_agent: Collaborator used to re-score
                discoverability. Must expose
                `.evaluate(evidence) -> DiscoverabilityResult`.
            comprehension_agent: Collaborator used to re-score
                comprehension. Must expose
                `.evaluate(evidence) -> ComprehensionResult`.
            interaction_agent: Collaborator used to re-score
                interaction. Must expose
                `.evaluate(evidence) -> InteractionResult`.
            security_agent: Collaborator used to re-score security.
                Must expose `.evaluate(evidence) -> SecurityResult`.
        """
        self._category_agents: dict[str, Callable[[WebsiteEvidence], Any]] = {
            "discoverability": (discoverability_agent or DiscoverabilityAgent()).evaluate,
            "comprehension": (comprehension_agent or ComprehensionAgent()).evaluate,
            "interaction": (interaction_agent or InteractionAgent()).evaluate,
            "security": (security_agent or SecurityAgent()).evaluate,
        }

    def run(self, input_data: dict[str, Any]) -> SimulationResult:
        """Run the agent given the standard AutoFix input contract.

        Args:
            input_data: A dict of the form
                `{"evidence": WebsiteEvidence,
                "assessment_result": AssessmentResult,
                "pipeline_result": AutoFixPipelineResult}`.

        Returns:
            The resulting `SimulationResult`.
        """
        return self.simulate(
            evidence=input_data["evidence"],
            assessment_result=input_data["assessment_result"],
            pipeline_result=input_data["pipeline_result"],
        )

    def simulate(
        self,
        evidence: WebsiteEvidence,
        assessment_result: AssessmentResult,
        pipeline_result: AutoFixPipelineResult,
    ) -> SimulationResult:
        """Simulate the effect of every `APPROVED` fix, grouped by category.

        Args:
            evidence: The original `WebsiteEvidence` snapshot the
                assessment was based on. Never mutated — a deep copy
                is patched per category instead.
            assessment_result: The original `AssessmentResult`, used
                for `score_before` per category and
                `overall_score_before`.
            pipeline_result: The `AutoFixPipelineResult` holding the
                `ModeSelection` (git_repo vs black_box) and the
                `ValidationResult` (which fixes are `APPROVED`).

        Returns:
            A `SimulationResult` with one `CategorySimulation` per
            category that had at least one approved fix.
        """
        mode_selection = pipeline_result.mode_selection
        approved_by_category = self._group_by_category(
            pipeline_result.validation_result.approved_fixes
        )

        category_simulations = [
            self._simulate_category(
                category=category,
                fixes=fixes,
                evidence=evidence,
                assessment_result=assessment_result,
                can_apply_fixes=mode_selection.mode == OperatingMode.GIT_REPO
                and mode_selection.can_apply_fixes,
            )
            for category, fixes in approved_by_category.items()
        ]

        overall_score_before = assessment_result.overall_score
        overall_score_after = self._compute_overall_score_after(
            assessment_result, category_simulations
        )

        return SimulationResult(
            category_simulations=category_simulations,
            overall_score_before=overall_score_before,
            overall_score_after=overall_score_after,
            mode=mode_selection.mode.value,
        )

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_category(
        fixes: list[ProposedFix],
    ) -> dict[str, list[ProposedFix]]:
        """Group approved fixes by `ProposedFix.category`, preserving order."""
        grouped: dict[str, list[ProposedFix]] = {}
        for fix in fixes:
            grouped.setdefault(fix.category, []).append(fix)
        return grouped

    # ------------------------------------------------------------------
    # Per-category simulation
    # ------------------------------------------------------------------

    def _simulate_category(
        self,
        category: str,
        fixes: list[ProposedFix],
        evidence: WebsiteEvidence,
        assessment_result: AssessmentResult,
        can_apply_fixes: bool,
    ) -> CategorySimulation:
        """Simulate one category's cumulative fixes, or skip it.

        Args:
            category: The category name (e.g. `"discoverability"`).
            fixes: The `APPROVED` fixes belonging to this category.
            evidence: The original evidence snapshot to patch a copy
                of.
            assessment_result: The original assessment, for
                `score_before`.
            can_apply_fixes: Whether the pipeline is in a mode where
                diffs may be applied at all.

        Returns:
            A `CategorySimulation` for this category, either
            re-scored or marked `skipped`.
        """
        mode_value = fixes[0].mode
        score_before = self._score_before(assessment_result, category)

        if not can_apply_fixes:
            return CategorySimulation(
                category=category,
                mode=mode_value,
                score_before=score_before,
                fixes_applied=[],
                skipped=True,
                skip_reason=_BLACK_BOX_SKIP_REASON,
            )

        patched_evidence = copy.deepcopy(evidence)
        applied_fixes: list[ProposedFix] = []

        for fix in fixes:
            if self._apply_fix(patched_evidence, fix):
                applied_fixes.append(fix)

        if not applied_fixes:
            return CategorySimulation(
                category=category,
                mode=mode_value,
                score_before=score_before,
                fixes_applied=[],
                skipped=True,
                skip_reason=_NO_APPLICABLE_FIX_REASON,
            )

        category_agent = self._category_agents.get(category)
        if category_agent is None:
            return CategorySimulation(
                category=category,
                mode=mode_value,
                score_before=score_before,
                fixes_applied=[],
                skipped=True,
                skip_reason=f"Catégorie inconnue de la simulation : '{category}'.",
            )

        new_result = category_agent(patched_evidence)
        score_after = new_result.score

        return CategorySimulation(
            category=category,
            mode=mode_value,
            score_before=score_before,
            score_after=score_after,
            delta=round(score_after - score_before, 2),
            fixes_applied=applied_fixes,
            skipped=False,
        )

    @staticmethod
    def _score_before(assessment_result: AssessmentResult, category: str) -> float:
        """Read a category's original score out of `AssessmentResult`.

        Args:
            assessment_result: The original assessment.
            category: One of `"discoverability"`, `"comprehension"`,
                `"interaction"`, `"security"`.

        Returns:
            The category's `score` field, or `0.0` if the category is
            unrecognized or missing.
        """
        category_result = getattr(assessment_result, category, None)
        if not isinstance(category_result, dict):
            return 0.0
        return float(category_result.get("score", 0.0))

    # ------------------------------------------------------------------
    # Diff application (in-memory only, never touches the real repo)
    # ------------------------------------------------------------------

    def _apply_fix(self, patched_evidence: WebsiteEvidence, fix: ProposedFix) -> bool:
        """Apply one fix's diff to `patched_evidence`, in place.

        Args:
            patched_evidence: The evidence copy to mutate.
            fix: The approved fix to apply. Fixes with an empty
                `diff`, or whose target file is not in
                `_FILE_TO_EVIDENCE_FIELD`, are left unapplied.

        Returns:
            `True` if the fix was applied, `False` otherwise.
        """
        if not fix.diff.strip():
            return False

        target_file = self._parse_diff_target(fix.diff)
        if target_file is None:
            return False

        evidence_field = _FILE_TO_EVIDENCE_FIELD.get(target_file)
        if evidence_field is None:
            return False

        original_content = getattr(patched_evidence, evidence_field, None) or ""

        try:
            new_content = self._apply_unified_diff(original_content, fix.diff)
        except ValueError:
            return False

        setattr(patched_evidence, evidence_field, new_content)
        return True

    @staticmethod
    def _parse_diff_target(diff: str) -> Optional[str]:
        """Extract the patched file's basename from a unified diff header.

        Args:
            diff: A unified diff produced by
                `AutoFixAgent._build_diff` (headers `--- a/<path>` /
                `+++ b/<path>`).

        Returns:
            The `<path>` from the `+++ b/<path>` header, or `None` if
            no such header is present.
        """
        for line in diff.splitlines():
            match = _DIFF_TARGET_RE.match(line)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _apply_unified_diff(original_content: str, diff: str) -> str:
        """Apply a unified diff (as produced by `difflib.unified_diff`) to text.

        This is a small, self-contained counterpart to
        `AutoFixAgent._build_diff` — it only needs to understand
        diffs this codebase itself generates (no fuzzy matching, no
        offset tolerance), so it stays dependency-free and testable
        without a `git` binary or real filesystem access.

        Args:
            original_content: The pre-patch text (e.g. the current
                `robots_txt` field). Empty string if the file did not
                exist.
            diff: The unified diff to apply, in the
                `difflib.unified_diff(..., lineterm="")` format used
                throughout this codebase.

        Returns:
            The patched text.

        Raises:
            ValueError: If a hunk header is malformed or a hunk line
                has an unrecognized prefix — signals the diff was not
                produced by this codebase's own generator.
        """
        original_lines = original_content.splitlines()
        diff_lines = diff.splitlines()

        result: list[str] = []
        orig_idx = 0
        i = 0

        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            i += 1

        while i < len(diff_lines):
            header = diff_lines[i]
            match = _HUNK_HEADER_RE.match(header)
            if not match:
                raise ValueError(f"Malformed diff hunk header: {header!r}")

            old_start = int(match.group(1))
            target_idx = max(old_start - 1, 0)
            while orig_idx < target_idx and orig_idx < len(original_lines):
                result.append(original_lines[orig_idx])
                orig_idx += 1

            i += 1
            while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                line = diff_lines[i]
                if line.startswith(" "):
                    result.append(line[1:])
                    orig_idx += 1
                elif line.startswith("-"):
                    orig_idx += 1
                elif line.startswith("+"):
                    result.append(line[1:])
                elif line == "":
                    pass
                else:
                    raise ValueError(f"Unexpected diff line: {line!r}")
                i += 1

        while orig_idx < len(original_lines):
            result.append(original_lines[orig_idx])
            orig_idx += 1

        patched = "\n".join(result)
        if result and (original_content == "" or original_content.endswith("\n")):
            patched += "\n"
        return patched

    # ------------------------------------------------------------------
    # Overall score aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_overall_score_after(
        assessment_result: AssessmentResult,
        category_simulations: list[CategorySimulation],
    ) -> float:
        """Recompute the overall score after simulation.

        For each of the four fixed categories, uses `score_after`
        when that category was actually simulated, and falls back to
        the original (unchanged) score otherwise — a category that
        was skipped, or had no approved fixes at all, never
        contributes a penalty or a bonus it didn't earn.

        Args:
            assessment_result: The original assessment, for
                unsimulated categories' scores.
            category_simulations: The simulations actually run.

        Returns:
            The average of the four category scores, rounded to 2
            decimals.
        """
        simulated_scores = {
            sim.category: sim.score_after
            for sim in category_simulations
            if not sim.skipped and sim.score_after is not None
        }

        scores = [
            simulated_scores.get(
                category,
                SimulationAgent._score_before(assessment_result, category),
            )
            for category in (
                "discoverability",
                "comprehension",
                "interaction",
                "security",
            )
        ]

        return round(sum(scores) / len(scores), 2)