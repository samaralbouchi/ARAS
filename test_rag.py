from rag.retriever import KnowledgeBaseRetriever


retriever = KnowledgeBaseRetriever(k=3)


questions = [
    "Why should a website provide an OpenAPI specification?",
    "What is MCP for AI agents?",
    "Why is Schema.org structured data important?",
    "What are important security headers?"
]


for q in questions:
    print("\n====================")
    print("QUESTION:")
    print(q)

    print("\nRESULT:")
    print(
        retriever.get_context(q)
    )