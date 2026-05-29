async def retrieve_context(query: str) -> str:
    """
    RAG retriever entry point.
    Receives the user's prompt and should:
    1. Embed the query
    2. Search ChromaDB for relevant chunks
    3. Return them as a single context string
    """
    return ""