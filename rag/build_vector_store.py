"""
Builds (or rebuilds) the local Chroma vector store from the markdown files
in rag/knowledge_base/. Run this once, and again whenever the knowledge base
content changes.

Usage:
    python -m rag.build_vector_store
"""

import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import MarkdownTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma

KNOWLEDGE_BASE_DIR = os.path.join(os.path.dirname(__file__), "knowledge_base")
PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_store")
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "araf_knowledge_base"


def load_documents():
    loader = DirectoryLoader(
        KNOWLEDGE_BASE_DIR,
        glob="*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    return loader.load()


def split_documents(documents):
    splitter = MarkdownTextSplitter(chunk_size=800, chunk_overlap=100)
    return splitter.split_documents(documents)


def build_vector_store():
    print(f"Loading markdown files from {KNOWLEDGE_BASE_DIR}...")
    documents = load_documents()
    print(f"Loaded {len(documents)} documents.")

    chunks = split_documents(documents)
    print(f"Split into {len(chunks)} chunks.")

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME)

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIR,
    )

    print(f"Vector store built and persisted at {PERSIST_DIR}")
    return vector_store


if __name__ == "__main__":
    build_vector_store()