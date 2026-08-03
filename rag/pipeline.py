from rag.retriever import KnowledgeBaseRetriever
from rag.generator import RAGGenerator


class RAGPipeline:

    def __init__(self):
        self.retriever = KnowledgeBaseRetriever()
        self.generator = RAGGenerator()


    def run(self, issue):

        context, sources = self.retriever.get_context_for_topics(
            [issue]
        )

        answer = self.generator.generate_recommendation(
            issue,
            context
        )

        return {
            "answer": answer,
            "sources": sources,
            "context": context
        }