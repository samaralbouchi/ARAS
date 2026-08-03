"""
Thin wrapper around the Chroma vector store used to fetch RAG context
for the Recommendation Agent.
"""

import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "araf_knowledge_base"


class KnowledgeBaseRetriever:
    def __init__(self, persist_dir: str = PERSIST_DIR, k: int = 4):
        if not os.path.isdir(persist_dir):
            raise FileNotFoundError(
                f"No vector store found at {persist_dir}. "
                "Run `python -m rag.build_vector_store` first."
            )
        self.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)
        self.vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=persist_dir,
        )
        self.k = k

    def get_context(self, query: str, k: int | None = None) -> str:
        """
        Returns a single formatted string of the top-k relevant chunks,
        ready to inject into a prompt as 'RAG context'.
        """
        results = self.vector_store.similarity_search(query, k=k or self.k)
        if not results:
            return ""
        formatted = []
        for i, doc in enumerate(results, start=1):
            source = os.path.basename(doc.metadata.get("source", "unknown"))
            formatted.append(f"[{i}] (source: {source})\n{doc.page_content.strip()}")
        return "\n\n".join(formatted)

    def get_context_for_topics(
        self, topics: list[str], k_per_topic: int = 2, source_type: str | None = None
    ) -> tuple[str, list[dict]]:
        """
        Runs one retrieval per topic (e.g. per detected issue) and merges
        results, deduplicating by content. Returns both the formatted
        context string and a structured list of sources used.
        """
        seen = set()
        merged = []
        sources = []
        filter_dict = {"source_type": source_type} if source_type else None
        for topic in topics:
            results = self.vector_store.similarity_search(
                topic, k=k_per_topic, filter=filter_dict
            )
            for doc in results:
                key = doc.page_content[:80]
                if key not in seen:
                    seen.add(key)
                    source = os.path.basename(doc.metadata.get("source", "unknown"))
                    stype = doc.metadata.get("source_type", "unknown")
                    merged.append(f"(source: {source} [{stype}])\n{doc.page_content.strip()}")
                    sources.append({"source": source, "source_type": stype})
        return "\n\n".join(merged), sources