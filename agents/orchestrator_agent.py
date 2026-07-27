"""Orchestrator Agent.

This module is the coordination layer of ARAS. It sits above the
Evidence Collector and the four parallel analysis agents
(Discoverability, Comprehension, Interaction, Security): it drives the
whole "perception -> judgment" pipeline for a single website and
assembles the result into one `AssessmentResult`.

This agent MUST NOT:
    - perform HTTP requests itself
    - parse HTML itself
    - implement any scoring criterion itself

It only calls the Evidence Collector (perception) and the four
analysis agents (judgment), and combines their outputs. All evidence
collection belongs to `EvidenceCollectorAgent`; all scoring logic
belongs to the four analysis agents.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from agents.comprehension_agent import ComprehensionAgent
from agents.discoverability_agent import DiscoverabilityAgent
from agents.evidence_collector import EvidenceCollectorAgent
from agents.interaction_agent import InteractionAgent
from agents.security_agent import SecurityAgent
from models.assessment import AssessmentResult
from models.evidence import WebsiteEvidence

# Number of analysis agents run per assessment. Kept as a named
# constant (rather than len(...)) so the intent reads clearly at the
# call site and the worker pool is sized to exactly match.
_ANALYSIS_AGENT_COUNT = 4


class OrchestratorAgent:
    """Coordinates the full Agentic Readiness Assessment pipeline.

    This class holds no evidence-collection or scoring logic of its
    own. It is a pure coordination step:

        1. Delegate to the Evidence Collector to gather a
           `WebsiteEvidence` snapshot for the given URL.
        2. Run the four analysis agents against that snapshot
           concurrently (they are independent, read-only consumers of
           the same evidence, so nothing serializes them).
        3. Aggregate the four scores and assemble an
           `AssessmentResult`.

    Every collaborator is injectable so callers (tests, in particular)
    can substitute fakes without monkeypatching or real network
    access.
    """

    def __init__(
        self,
        evidence_collector: Optional[EvidenceCollectorAgent] = None,
        discoverability_agent: Optional[DiscoverabilityAgent] = None,
        comprehension_agent: Optional[ComprehensionAgent] = None,
        interaction_agent: Optional[InteractionAgent] = None,
        security_agent: Optional[SecurityAgent] = None,
    ) -> None:
        """Initialize the orchestrator, optionally overriding its collaborators.

        Args:
            evidence_collector: Collaborator used to gather evidence.
                Must expose `.collect(url) -> WebsiteEvidence`.
                Defaults to a real `EvidenceCollectorAgent`.
            discoverability_agent: Collaborator used to score
                discoverability. Must expose
                `.evaluate(evidence) -> DiscoverabilityResult`.
            comprehension_agent: Collaborator used to score
                comprehension. Must expose
                `.evaluate(evidence) -> ComprehensionResult`.
            interaction_agent: Collaborator used to score interaction
                (actionability). Must expose
                `.evaluate(evidence) -> InteractionResult`.
            security_agent: Collaborator used to score security
                posture. Must expose
                `.evaluate(evidence) -> SecurityResult`.
        """
        self._evidence_collector = evidence_collector or EvidenceCollectorAgent()
        self._discoverability_agent = discoverability_agent or DiscoverabilityAgent()
        self._comprehension_agent = comprehension_agent or ComprehensionAgent()
        self._interaction_agent = interaction_agent or InteractionAgent()
        self._security_agent = security_agent or SecurityAgent()

    def run(self, input_data: dict[str, Any]) -> AssessmentResult:
        """Run a full assessment given the agent's standard input contract.

        Args:
            input_data: A dict of the form `{"url": "https://example.com"}`.

        Returns:
            The resulting `AssessmentResult`.
        """
        return self.assess(input_data["url"])

    def assess(self, url: str) -> AssessmentResult:
        """Run the full Agentic Readiness Assessment pipeline for one URL.

        Args:
            url: The website URL to assess.

        Returns:
            An `AssessmentResult` combining the raw evidence and all
            four analysis results, plus an aggregate `overall_score`.
        """
        evidence = self._evidence_collector.collect(url)

        discoverability, comprehension, interaction, security = self._run_analysis_agents(
            evidence
        )

        scores = [
            discoverability.score,
            comprehension.score,
            interaction.score,
            security.score,
        ]

        return AssessmentResult(
            url=url,
            evidence=evidence.to_dict(),
            discoverability=discoverability.to_dict(),
            comprehension=comprehension.to_dict(),
            interaction=interaction.to_dict(),
            security=security.to_dict(),
            overall_score=self._compute_overall_score(scores),
            collection_errors=[
                {"step": error.step, "message": error.message}
                for error in evidence.errors
            ],
        )

    # ------------------------------------------------------------------
    # Parallel analysis
    # ------------------------------------------------------------------

    def _run_analysis_agents(
        self, evidence: WebsiteEvidence
    ) -> tuple[Any, Any, Any, Any]:
        """Run the four analysis agents concurrently against the same evidence.

        The four agents are independent, read-only consumers of the
        same `WebsiteEvidence` snapshot, so they carry no ordering
        dependency and are safe to run in a thread pool. Today they are
        pure CPU-bound functions (no I/O), so the pool mainly documents
        the "parallel analysis" boundary of the architecture; it also
        means any agent that later needs to make an I/O-bound call
        (e.g. an LLM-based check) benefits from real concurrency
        without any change to this method.

        Args:
            evidence: The `WebsiteEvidence` snapshot to evaluate.

        Returns:
            A 4-tuple of `(DiscoverabilityResult, ComprehensionResult,
            InteractionResult, SecurityResult)`.
        """
        jobs: list[Callable[[], Any]] = [
            lambda: self._discoverability_agent.evaluate(evidence),
            lambda: self._comprehension_agent.evaluate(evidence),
            lambda: self._interaction_agent.evaluate(evidence),
            lambda: self._security_agent.evaluate(evidence),
        ]

        with ThreadPoolExecutor(max_workers=_ANALYSIS_AGENT_COUNT) as executor:
            futures = [executor.submit(job) for job in jobs]
            results = [future.result() for future in futures]

        return tuple(results)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Score aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_overall_score(scores: list[float]) -> float:
        """Compute the unweighted average of the four analysis scores.

        Args:
            scores: The four individual analysis scores, each in
                [0, 100].

        Returns:
            The average score, rounded to 2 decimal places, or 0.0 if
            no scores were provided.
        """
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 2)