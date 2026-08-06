import json
import re
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

        text = text.replace("```json", "")
        text = text.replace("```", "")

        start = text.find("[")
        end = text.rfind("]")


        if start != -1 and end != -1:
            return text[start:end+1]


        return None



    def generate_all(
        self,
        issues
    ):


        if not issues:
            return []


        clean_issues = self._make_serializable(
            issues
        )


        prompt = f"""

You are an expert Agentic Web engineer.

Generate implementation recommendations.

Rules:

- Use detected issues only.
- Use RAG context only as technical knowledge.
- Do not summarize documentation.
- Return ONLY JSON.
- No markdown.
- No explanations.

Format:

[
 {{
   "issue":"",
   "recommendation":"",
   "how_to_apply":[
      "",
      "",
      ""
   ],
   "rag_sources":[]
 }}
]


Detected issues:

{json.dumps(clean_issues, indent=2)}


Generate JSON now.

"""


        response = self.llm.invoke(prompt)


        raw = response.content.strip()


        print("\n========== RAW LLM RESPONSE ==========")
        print(raw)
        print("======================================")


        json_text = self._extract_json(raw)


        if json_text:

            try:

                result = json.loads(json_text)


                if isinstance(result,list):
                    return result


            except Exception as e:

                print(
                    "JSON parsing error:",
                    e
                )



        print(
            "Using fallback recommendations"
        )


        fallback=[]


        for item in clean_issues:


            fallback.append(
                {
                    "issue": item.get(
                        "issue",
                        "Unknown"
                    ),

                    "recommendation": item.get(
                        "base_recommendation",
                        "Improve this capability."
                    ),

                    "how_to_apply":[

                        "Consult the related technical documentation.",

                        "Implement the recommended standard.",

                        "Run ARAS assessment again."

                    ],

                    "rag_sources":
                        [
                            s.get("source")
                            for s in item.get(
                                "rag_sources",
                                []
                            )
                        ]

                }
            )


        return fallback