import json
from langchain_ollama import ChatOllama


class RecommendationGenerator:

    def __init__(self):

        self.llm = ChatOllama(
            model="llama3.2",
            temperature=0
        )


    def _make_serializable(self, obj):

        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj

        if isinstance(obj, list):
            return [
                self._make_serializable(x)
                for x in obj
            ]

        if isinstance(obj, dict):
            return {
                k: self._make_serializable(v)
                for k, v in obj.items()
                if k != "entry"
            }

        if hasattr(obj, "__dict__"):
            return {
                k: self._make_serializable(v)
                for k, v in obj.__dict__.items()
            }

        return str(obj)


    def _extract_json(self, text):
        """
        Robustly pull a single JSON object (or array) out of an LLM
        response. Handles:
          - fenced code blocks (```json ... ```)
          - a plain object {...}
          - a plain array [...]
          - trailing junk after the JSON (uses json.JSONDecoder.raw_decode
            instead of str.rfind, since rfind breaks as soon as there is
            more than one bracket/array in the text).
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


    def _build_prompt(self, item):

        issue = item.get("issue", "")
        base_recommendation = item.get("base_recommendation", "")
        rag_context = item.get("rag_context", "") or ""

        # Keep the prompt small: ONE issue + a trimmed context is what a
        # small local model like llama3.2 can reliably follow. A prompt
        # built from every issue at once (several issues x several KB of
        # rag_context each) makes the model lose track of the format and
        # simply echo the input back instead of generating anything.
        max_context_chars = 2000
        if len(rag_context) > max_context_chars:
            rag_context = rag_context[:max_context_chars] + "\n...(truncated)"

        return f"""

You are an expert Agentic Web engineer.

Generate ONE implementation recommendation for the issue below.

Rules:

- Use the detected issue and the RAG context only.
- Use RAG context only as technical knowledge (do not summarize it).
- Return ONLY JSON, a single object, no markdown, no explanations.

Format:

{{
  "issue": "",
  "recommendation": "",
  "how_to_apply": [
    "",
    "",
    ""
  ]
}}

Detected issue:
{issue}

Base recommendation:
{base_recommendation}

RAG context:
{rag_context}

Generate the JSON object now.

"""


    def _generate_one(self, item):
        """Call the LLM for a single issue and return a parsed dict,
        or None if the call/parsing failed."""

        prompt = self._build_prompt(item)

        try:
            response = self.llm.invoke(prompt)
            raw = response.content.strip()
        except Exception as e:
            print(
                "LLM call failed (is the Ollama server running and "
                "reachable at OLLAMA_HOST? is 'llama3.2' pulled?):",
                e
            )
            return None

        print("\n========== RAW LLM RESPONSE ==========")
        print(raw)
        print("======================================")

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


    def _fallback_for(self, item):

        return {
            "issue": item.get("issue", "Unknown"),

            "recommendation": item.get(
                "base_recommendation",
                "Improve this capability."
            ),

            "how_to_apply": [
                "Consult the related technical documentation.",
                "Implement the recommended standard.",
                "Run ARAS assessment again."
            ],

            "rag_sources": [
                s.get("source")
                for s in item.get("rag_sources", [])
            ]
        }


    def generate_all(self, issues):

        if not issues:
            return []

        clean_issues = self._make_serializable(issues)

        results = []

        # One LLM call per issue: a short, focused prompt that a small
        # local model like llama3.2 can actually follow, instead of one
        # giant prompt covering every issue plus its full RAG context.
        for item in clean_issues:

            generated = self._generate_one(item)

            if generated is None:
                print("Using fallback recommendation for issue:", item.get("issue"))
                generated = self._fallback_for(item)
            else:
                generated.setdefault(
                    "rag_sources",
                    [
                        s.get("source")
                        for s in item.get("rag_sources", [])
                    ]
                )

            results.append(generated)

        return results