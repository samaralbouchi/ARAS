"""LLM-based fix generator used by the AutoFix Agent.

This mirrors the pattern of `rag.generator.RecommendationGenerator`
(LangChain + local Ollama model, strict JSON-only prompt, robust JSON
extraction, per-item fallback) but is scoped to the AutoFix agent's
needs: turning an already-scored `Recommendation` (issue +
recommendation text + `how_to_apply` + `rag_context`) into a single,
concrete, step-by-step `instruction` a human can follow to apply the
fix.

Crucially, this generator does NOT perform any RAG retrieval itself:
`Recommendation.rag_context` was already computed once by the
`RecommendationAgent`, and reusing it here avoids querying the vector
store a second time for the same issue.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_ollama import ChatOllama

from models.recommendation import Recommendation

_MAX_RAG_CONTEXT_CHARS = 2000


class FixGenerator:
    """Generates a concrete `instruction` for issues the AutoFix
    agent's deterministic rules do not cover."""

    def __init__(self) -> None:
        self.llm = ChatOllama(
            model="llama3.2",
            temperature=0,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_all(
        self, recommendations: list[Recommendation]
    ) -> list[dict[str, Any]]:
        """Generate one fix instruction per recommendation.

        Args:
            recommendations: Issues the AutoFix agent's rule-based
                fixes did not handle. Each is used as-is; no RAG
                retrieval is performed here.

        Returns:
            One dict per input recommendation, in the same order,
            each with at least an `"instruction"` key. Falls back to
            `recommendation.how_to_apply` / `recommendation.recommendation`
            for any item the LLM call or JSON parsing fails on, so the
            caller never has to special-case a missing entry.
        """
        if not recommendations:
            return []

        results = []

        # One LLM call per issue, like RecommendationGenerator: a
        # short, focused prompt is what a small local model can
        # reliably follow.
        for recommendation in recommendations:
            generated = self._generate_one(recommendation)

            if generated is None:
                generated = self._fallback_for(recommendation)

            results.append(generated)

        return results

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(recommendation: Recommendation) -> str:
        rag_context = recommendation.rag_context or ""

        if len(rag_context) > _MAX_RAG_CONTEXT_CHARS:
            rag_context = rag_context[:_MAX_RAG_CONTEXT_CHARS] + "\n...(truncated)"

        return f"""

You are an expert Agentic Web engineer helping apply a fix.

Generate ONE concrete, step-by-step instruction for how to fix the
issue below. Be specific and actionable (file names, config keys,
header names, code snippets where relevant).

Rules:

- Use the detected issue, the base recommendation, and the RAG
  context only.
- Use RAG context only as technical knowledge (do not summarize it).
- Return ONLY JSON, a single object, no markdown, no explanations.

Format:

{{
  "issue": "",
  "instruction": [
    "",
    "",
    ""
  ]
}}

Detected issue:
{recommendation.issue}

Base recommendation:
{recommendation.recommendation}

Existing guidance:
{recommendation.how_to_apply}

RAG context:
{rag_context}

Generate the JSON object now.

"""

    # ------------------------------------------------------------------
    # LLM call + JSON parsing
    # ------------------------------------------------------------------

    def _generate_one(
        self, recommendation: Recommendation
    ) -> dict[str, Any] | None:
        """Call the LLM for a single recommendation and return a
        parsed dict, or `None` if the call/parsing failed."""

        prompt = self._build_prompt(recommendation)

        try:
            response = self.llm.invoke(prompt)
            raw = response.content.strip()
        except Exception as e:
            print(
                "LLM call failed (is the Ollama server running and "
                "reachable at OLLAMA_HOST? is 'llama3.2' pulled?):",
                e,
            )
            return None

        parsed = self._extract_json(raw)

        if parsed is None:
            print("JSON parsing error: no valid JSON object found")
            return None

        # The model sometimes wraps the single object in a one-item list.
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else None

        if not isinstance(parsed, dict):
            return None

        return parsed

    @staticmethod
    def _extract_json(text: str) -> Any:
        """Robustly pull a single JSON object (or array) out of an LLM
        response.

        Handles fenced code blocks (```json ... ```), a plain object
        or array, and trailing junk after the JSON (uses
        `json.JSONDecoder.raw_decode` rather than `str.rfind`, since
        `rfind` breaks as soon as there is more than one
        bracket/array in the text).
        """
        text = text.replace("```json", "").replace("```", "").strip()

        candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]

        if not candidates:
            return None

        start = min(candidates)

        decoder = json.JSONDecoder()

        try:
            obj, _end = decoder.raw_decode(text[start:])
            return obj
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_for(recommendation: Recommendation) -> dict[str, Any]:
        instruction = (
            recommendation.how_to_apply
            or recommendation.recommendation
            or "Consulter la documentation technique associée et appliquer "
            "la pratique recommandée."
        )

        return {
            "issue": recommendation.issue,
            "instruction": instruction,
        }