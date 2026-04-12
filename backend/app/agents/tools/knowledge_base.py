"""RAG retrieval tool for the Counsel agent."""

from langchain_core.tools import tool


@tool
def search_bc_regulations(query: str, category: str | None = None) -> str:
    """Search BC sports governance regulations, laws, and dispute resolution guides.

    Use this tool to find relevant policies, bylaws, and regulations
    related to a parent's dispute with a BC sports club.

    Args:
        query: What to search for (e.g., "member rights to financial records")
        category: Optional category filter (e.g., "bc societies act", "safesport policies")
    """
    from app.knowledge.retriever import get_retriever

    retriever = get_retriever()
    filter_dict = {"category": category} if category else {}
    docs = retriever.invoke(query, filter=filter_dict)

    if not docs:
        return "No relevant documents found. The knowledge base may need to be updated."

    results = []
    for doc in docs:
        source = doc.metadata.get("source", "Unknown")
        results.append(f"**Source: {source}**\n{doc.page_content}\n")

    return "\n---\n".join(results)
