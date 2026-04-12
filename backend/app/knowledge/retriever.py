"""Knowledge base retriever — ChromaDB-backed RAG for BC sports governance."""

from pathlib import Path

import chromadb
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import PrivateAttr

from app.config import settings


class KnowledgeBaseRetriever(BaseRetriever):
    """Retriever that searches the BC sports governance knowledge base.

    Uses ChromaDB with local sentence-transformer embeddings (no API key needed).
    """

    collection_name: str = "bc_sports_governance"
    n_results: int = 5
    _client: chromadb.ClientAPI = PrivateAttr()
    _collection: chromadb.Collection = PrivateAttr()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _get_relevant_documents(self, query: str, **kwargs) -> list[Document]:
        """Synchronous retrieval."""
        category_filter = kwargs.get("filter", {})

        query_params = {
            "query_texts": [query],
            "n_results": self.n_results,
        }
        if category_filter:
            query_params["where"] = category_filter

        results = self._collection.query(**query_params)

        docs = []
        if results and results["documents"]:
            for i, doc_text in enumerate(results["documents"][0]):
                metadata = {}
                if results.get("metadatas") and results["metadatas"][0]:
                    metadata = results["metadatas"][0][i]
                docs.append(Document(page_content=doc_text, metadata=metadata))

        return docs

    async def _aget_relevant_documents(self, query: str, **kwargs) -> list[Document]:
        """Async retrieval (ChromaDB doesn't have native async, so we wrap sync)."""
        return self._get_relevant_documents(query, **kwargs)


def get_retriever() -> KnowledgeBaseRetriever:
    """Get the knowledge base retriever instance."""
    return KnowledgeBaseRetriever()
