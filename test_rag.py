from rag.generator import RecommendationGenerator

gen = RecommendationGenerator()

issues = [
    {
        "issue": "No llms.txt found",
        "base_recommendation": "Add an llms.txt file.",
        "rag_sources": []
    }
]

result = gen.generate_all(issues)

print(result)