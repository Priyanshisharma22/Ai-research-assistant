import chromadb
from rag.embeddings import embed_texts
from config import settings

client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
collection = client.get_or_create_collection("research_docs")

def retrieve(query: str, top_k: int = 5) -> list[dict]:
    try:
        # Guard: empty query
        if not query or not query.strip():
            return []

        embeddings = embed_texts([query])

        # Guard: embedding failed or returned empty
        if not embeddings or len(embeddings) == 0:
            return []

        query_embedding = embeddings[0]

        # Guard: collection is empty
        if collection.count() == 0:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),  # can't request more than exists
        )

        sources = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc in enumerate(docs):
            sources.append({
                "content": doc,
                "source": metas[i].get("source", "unknown") if i < len(metas) else "unknown",
                "score": round(1 - distances[i], 3) if i < len(distances) else 0.0,
            })

        return sources

    except Exception as e:
        print(f"[retriever] Error during retrieval: {e}")
        return []