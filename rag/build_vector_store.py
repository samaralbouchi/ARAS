"""
Builds (or rebuilds) the local Chroma vector store from the markdown files
in rag/knowledge_base/. Run this once, and again whenever the knowledge base
content changes.

Usage:
    python -m rag.build_vector_store
"""

"""
Builds (or rebuilds) the local Chroma vector store from markdown files
in:
- rag/knowledge_base
- rag/external_sources

Run this once, and again whenever documents change.
"""

import os

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import MarkdownTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


BASE_DIR = os.path.dirname(__file__)

KNOWLEDGE_BASE_DIR = os.path.join(
    BASE_DIR,
    "knowledge_base"
)

EXTERNAL_SOURCES_DIR = os.path.join(
    BASE_DIR,
    "external_sources"
)

PERSIST_DIR = os.path.join(
    BASE_DIR,
    "chroma_store"
)

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

COLLECTION_NAME = "araf_knowledge_base"


def load_documents_from_directory(directory):
    """
    Load markdown documents from a directory.
    """

    loader = DirectoryLoader(
        directory,
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={
            "encoding": "utf-8"
        },
    )

    return loader.load()


def load_documents():

    documents = []

    print("Loading internal knowledge base...")

    documents.extend(
        load_documents_from_directory(
            KNOWLEDGE_BASE_DIR
        )
    )


    print("Loading external official sources...")

    documents.extend(
        load_documents_from_directory(
            EXTERNAL_SOURCES_DIR
        )
    )


    return documents



def split_documents(documents):

    splitter = MarkdownTextSplitter(
        chunk_size=800,
        chunk_overlap=100
    )

    return splitter.split_documents(documents)



def build_vector_store():

    print("Loading documents...")

    documents = load_documents()

    print(
        f"Loaded {len(documents)} documents."
    )


    chunks = split_documents(documents)

    print(
        f"Split into {len(chunks)} chunks."
    )


    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME
    )


    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=PERSIST_DIR,
    )


    print(
        f"Vector store built at {PERSIST_DIR}"
    )


    return vector_store



if __name__ == "__main__":
    build_vector_store()