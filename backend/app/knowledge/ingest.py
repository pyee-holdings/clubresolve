"""Knowledge base ingestion script.

Reads curated markdown documents from sources/ directory,
chunks them, and stores in ChromaDB for retrieval.

Usage:
    python -m app.knowledge.ingest
"""

import os
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

SOURCES_DIR = Path(__file__).parent / "sources"


def ingest_knowledge_base():
    """Ingest all markdown sources into ChromaDB."""
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

    # Delete and recreate collection for clean re-ingestion
    try:
        client.delete_collection("bc_sports_governance")
    except Exception:
        pass

    collection = client.create_collection(
        name="bc_sports_governance",
        metadata={"hnsw:space": "cosine"},
    )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " "],
    )

    total_chunks = 0

    for md_file in sorted(SOURCES_DIR.glob("*.md")):
        print(f"Processing: {md_file.name}")
        text = md_file.read_text(encoding="utf-8")

        # Determine category from filename
        category = md_file.stem.replace("_", " ").replace("-", " ")

        chunks = splitter.split_text(text)
        print(f"  -> {len(chunks)} chunks")

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{md_file.stem}_{i:04d}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "source": md_file.name,
                "category": category,
                "chunk_index": i,
            })

        if documents:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
            total_chunks += len(documents)

    print(f"\nIngestion complete: {total_chunks} chunks from {len(list(SOURCES_DIR.glob('*.md')))} files")
    return total_chunks


if __name__ == "__main__":
    ingest_knowledge_base()
