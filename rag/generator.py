import json
from langchain_ollama import ChatOllama


class RecommendationGenerator:

    def __init__(self):

        self.llm = ChatOllama(
            model="llama3.2",
            temperature=0
        )


    def generate_all(
        self,
        recommendations_data: list[dict]
    ) -> list[dict]:


        prompt = """
You are an expert in Agentic Web optimization.

Your task is to transform website issues into actionable technical recommendations.

For each issue:

- Write a clear recommendation.
- Write a detailed "how_to_apply" section with concrete implementation steps.
- Use the provided documentation context as the technical reference.
- If the documentation contains examples, adapt them.
- Never leave how_to_apply empty.
- Provide practical steps that a developer can follow.

Return ONLY valid JSON.

Format:

[
 {
  "issue": "",
  "recommendation": "",
  "how_to_apply": ""
 }
]


Detected issues:
"""


        for item in recommendations_data:

            prompt += f"""

Issue:
{item['issue']}

Existing recommendation:
{item['base_recommendation']}

The documentation context is:
{item['rag_context']}

Generate concrete implementation steps.

---
"""


        response = self.llm.invoke(prompt)


        content = response.content.strip()


        try:

            # Convert JSON string returned by Llama
            results = json.loads(content)

            return results


        except json.JSONDecodeError:

            print("LLM returned invalid JSON:")
            print(content)


            # fallback to avoid crashing the pipeline
            return [
                {
                    "issue": item["issue"],
                    "recommendation": item["base_recommendation"],
                    "how_to_apply": ""
                }
                for item in recommendations_data
            ]