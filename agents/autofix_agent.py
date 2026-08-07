"""AutoFix Agent.

This module is the second step of the AutoFix extension pipeline,
sitting between the `ModeSelectorAgent` and the Human validation
agent. It takes the `RecommendationResult` already produced by the
existing `RecommendationAgent`, plus the `ModeSelection` describing
whether real diffs can be computed, and produces one `ProposedFix`
per issue.

Two fix strategies, chosen per issue:

    1. Rule-based (confidence 0.9): a small, deterministic,
       framework-agnostic set of fixes. Currently limited to
       `robots.txt` (missing, or blocking known AI agents), computed
       via `difflib` when a real file is reachable in `GIT_REPO`
       mode, otherwise a plain-text instruction.
    2. LLM-generated (confidence 0.5-0.7): everything else, produced
       by `FixGenerator`, reusing the `rag_context` already computed
       by the `RecommendationAgent` so the RAG retrieval is never
       redone.

This agent MUST NOT:
    - decide whether a fix is acceptable (Human validation agent)
    - write anything to disk (it only proposes; application happens
      after human validation, in a later step)
    - re-run any assessment or scoring (Simulation agent)
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from models.fix import AutoFixResult, ProposedFix
from models.mode import ModeSelection
from models.recommendation import Recommendation, RecommendationResult
from rag.fix_generator import FixGenerator


_RULE_BASED_CONFIDENCE = 0.9
_LLM_CONFIDENCE_WITH_RAG_CONTEXT = 0.7
_LLM_CONFIDENCE_WITHOUT_RAG_CONTEXT = 0.5

# Exact issue text emitted by DiscoverabilityAgent for a missing file.
_ROBOTS_MISSING_ISSUE = "No robots.txt found"

# Prefix of the issue text emitted by DiscoverabilityAgent when known
# AI bots are blocked (the full text also lists the blocked bots).
_ROBOTS_BLOCKED_PREFIX = "robots.txt disallows known AI agents:"

# Common locations for robots.txt across static sites and popular
# frameworks. First match wins; this is a heuristic, not exhaustive.
_ROBOTS_CANDIDATE_RELATIVE_PATHS = (
    "robots.txt",
    "public/robots.txt",
    "static/robots.txt",
)

_DEFAULT_ROBOTS_TXT = (
    "User-agent: *\n"
    "Allow: /\n"
    "\n"
    "User-agent: GPTBot\n"
    "Allow: /\n"
    "\n"
    "User-agent: ClaudeBot\n"
    "Allow: /\n"
    "\n"
    "User-agent: Google-Extended\n"
    "Allow: /\n"
)


class _SupportsFixGeneration(Protocol):

    def generate_all(
        self,
        recommendations: list[Recommendation]
    ) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class _PendingLlmFix:
    index: int
    recommendation: Recommendation


class AutoFixAgent:
    """Produces one `ProposedFix` per issue coming out of the
    Recommendation Agent, using deterministic rules where safe and an
    LLM (via RAG context) everywhere else."""

    def __init__(
        self,
        generator: Optional[_SupportsFixGeneration] = None,
    ) -> None:
        self._generator = generator or FixGenerator()

    def propose_fixes(
        self,
        recommendation_result: RecommendationResult,
        mode_selection: ModeSelection,
    ) -> AutoFixResult:
        """Propose a fix for every issue in `recommendation_result`.

        Args:
            recommendation_result: Output of `RecommendationAgent.evaluate`.
            mode_selection: Output of `ModeSelectorAgent.select`, telling
                this agent whether real diffs may be computed and where
                the repo lives.

        Returns:
            The aggregate `AutoFixResult` for this run.
        """

        mode_value = mode_selection.mode.value

        recommendations = recommendation_result.recommendations

        fixes: list[Optional[ProposedFix]] = [None] * len(recommendations)

        pending_llm_fixes: list[_PendingLlmFix] = []

        for index, recommendation in enumerate(recommendations):

            if self._is_robots_missing(recommendation.issue):
                fixes[index] = self._fix_robots_missing(
                    recommendation,
                    mode_selection,
                    mode_value,
                )

            elif self._is_robots_blocked(recommendation.issue):
                fixes[index] = self._fix_robots_blocked(
                    recommendation,
                    mode_selection,
                    mode_value,
                )

            else:
                pending_llm_fixes.append(
                    _PendingLlmFix(index=index, recommendation=recommendation)
                )

        generated = self._generate_llm_fixes(pending_llm_fixes)

        for pending, generated_item in zip(pending_llm_fixes, generated):
            fixes[pending.index] = self._build_llm_fix(
                pending.recommendation,
                generated_item,
                mode_value,
            )

        final_fixes = [fix for fix in fixes if fix is not None]

        rule_based_count = sum(
            1 for fix in final_fixes if fix.fix_type == "rule_based"
        )
        llm_generated_count = sum(
            1 for fix in final_fixes if fix.fix_type == "llm_generated"
        )

        return AutoFixResult(
            fixes=final_fixes,
            total_fixes=len(final_fixes),
            rule_based_count=rule_based_count,
            llm_generated_count=llm_generated_count,
            mode=mode_value,
        )

    # ------------------------------------------------------------------
    # Issue classification
    # ------------------------------------------------------------------

    @staticmethod
    def _is_robots_missing(issue: str) -> bool:
        return issue.strip() == _ROBOTS_MISSING_ISSUE

    @staticmethod
    def _is_robots_blocked(issue: str) -> bool:
        return issue.strip().startswith(_ROBOTS_BLOCKED_PREFIX)

    # ------------------------------------------------------------------
    # Rule-based fix: robots.txt missing
    # ------------------------------------------------------------------

    def _fix_robots_missing(
        self,
        recommendation: Recommendation,
        mode_selection: ModeSelection,
        mode_value: str,
    ) -> ProposedFix:

        instruction = (
            "Créer un fichier robots.txt à la racine du site avec, au "
            "minimum, le contenu suivant :\n" + _DEFAULT_ROBOTS_TXT
        )

        diff = ""

        if mode_selection.can_apply_fixes and mode_selection.repo_path:
            diff = self._build_diff(
                before_lines=[],
                after_lines=_DEFAULT_ROBOTS_TXT.splitlines(),
                path_label="robots.txt",
            )

        return ProposedFix(
            issue=recommendation.issue,
            category=recommendation.category,
            fix_type="rule_based",
            mode=mode_value,
            confidence=_RULE_BASED_CONFIDENCE,
            diff=diff,
            instruction=instruction,
        )

    # ------------------------------------------------------------------
    # Rule-based fix: robots.txt blocks known AI agents
    # ------------------------------------------------------------------

    def _fix_robots_blocked(
        self,
        recommendation: Recommendation,
        mode_selection: ModeSelection,
        mode_value: str,
    ) -> ProposedFix:

        blocked_bots = self._extract_blocked_bots(recommendation.issue)

        instruction = (
            "Retirer les règles 'Disallow: /' pour les agents IA suivants "
            "dans robots.txt : " + ", ".join(blocked_bots) + ". "
            "Remplacer chaque règle par 'Allow: /' si l'accès de ces "
            "agents doit être autorisé."
        )

        diff = ""

        if mode_selection.can_apply_fixes and mode_selection.repo_path:

            robots_path = self._find_robots_path(mode_selection.repo_path)

            if robots_path is not None:

                original = self._read_text_safely(robots_path)

                if original is not None:

                    fixed = self._unblock_robots_txt(original, blocked_bots)

                    if fixed != original:
                        diff = self._build_diff(
                            before_lines=original.splitlines(),
                            after_lines=fixed.splitlines(),
                            path_label="robots.txt",
                        )

        return ProposedFix(
            issue=recommendation.issue,
            category=recommendation.category,
            fix_type="rule_based",
            mode=mode_value,
            confidence=_RULE_BASED_CONFIDENCE,
            diff=diff,
            instruction=instruction,
        )

    @staticmethod
    def _extract_blocked_bots(issue: str) -> list[str]:
        """Parse the bot names out of a robots-blocked issue string.

        Args:
            issue: e.g. `"robots.txt disallows known AI agents: gptbot, claudebot"`.

        Returns:
            The list of bot tokens, e.g. `["gptbot", "claudebot"]`.
        """
        _, _, tail = issue.partition(_ROBOTS_BLOCKED_PREFIX)
        return [bot.strip() for bot in tail.split(",") if bot.strip()]

    @staticmethod
    def _find_robots_path(repo_path: str) -> Optional[Path]:
        base = Path(repo_path)
        for candidate in _ROBOTS_CANDIDATE_RELATIVE_PATHS:
            path = base / candidate
            if path.is_file():
                return path
        return None

    @staticmethod
    def _read_text_safely(path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    @staticmethod
    def _unblock_robots_txt(content: str, bots_to_unblock: list[str]) -> str:
        """Turn 'Disallow: /' into 'Allow: /' for the given bots' blocks.

        Mirrors the block-tracking heuristic used by
        `DiscoverabilityAgent._find_blocked_ai_bots` (consecutive
        `User-agent:` lines share the rules that follow), but rewrites
        instead of only detecting.

        Args:
            content: Raw current `robots.txt` contents.
            bots_to_unblock: Bot tokens (as reported in the issue text)
                whose full-site `Disallow: /` rule should become `Allow: /`.

        Returns:
            The rewritten `robots.txt` contents.
        """
        bots_lower = {bot.lower() for bot in bots_to_unblock}
        current_agents: list[str] = []
        output_lines: list[str] = []

        for raw_line in content.splitlines():
            line = raw_line.split("#", 1)[0].strip()

            if line and ":" in line:
                key, _, value = line.partition(":")
                key_lower = key.strip().lower()
                value_stripped = value.strip()

                if key_lower == "user-agent":
                    token = value_stripped.lower()
                    if token == "*":
                        current_agents = []
                    elif token in bots_lower:
                        current_agents.append(token)
                    else:
                        current_agents = []

                elif (
                    key_lower == "disallow"
                    and value_stripped.replace(" ", "") == "/"
                    and current_agents
                ):
                    output_lines.append(
                        raw_line.replace("Disallow", "Allow", 1)
                    )
                    continue

            output_lines.append(raw_line)

        rewritten = "\n".join(output_lines)
        if content.endswith("\n") and not rewritten.endswith("\n"):
            rewritten += "\n"
        return rewritten

    # ------------------------------------------------------------------
    # LLM-generated fixes (everything else)
    # ------------------------------------------------------------------

    def _generate_llm_fixes(
        self,
        pending: list[_PendingLlmFix],
    ) -> list[dict[str, Any]]:

        if not pending:
            return []

        recommendations = [item.recommendation for item in pending]

        try:
            return self._generator.generate_all(recommendations)
        except Exception:
            # Defensive: FixGenerator already falls back internally per
            # issue, but never let a generator-level failure take down
            # the whole AutoFix run.
            return [
                {
                    "issue": rec.issue,
                    "instruction": rec.how_to_apply or rec.recommendation,
                }
                for rec in recommendations
            ]

    def _build_llm_fix(
        self,
        recommendation: Recommendation,
        generated: dict[str, Any],
        mode_value: str,
    ) -> ProposedFix:

        instruction = generated.get("instruction") or (
            recommendation.how_to_apply or recommendation.recommendation
        )

        if isinstance(instruction, list):
            instruction = "\n".join(str(line) for line in instruction)

        confidence = (
            _LLM_CONFIDENCE_WITH_RAG_CONTEXT
            if recommendation.rag_context
            else _LLM_CONFIDENCE_WITHOUT_RAG_CONTEXT
        )

        return ProposedFix(
            issue=recommendation.issue,
            category=recommendation.category,
            fix_type="llm_generated",
            mode=mode_value,
            confidence=confidence,
            diff="",
            instruction=instruction,
        )

    # ------------------------------------------------------------------
    # Diff helper
    # ------------------------------------------------------------------

    @staticmethod
    def _build_diff(
        before_lines: list[str],
        after_lines: list[str],
        path_label: str,
    ) -> str:
        diff_lines = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path_label}",
            tofile=f"b/{path_label}",
            lineterm="",
        )
        return "\n".join(diff_lines)