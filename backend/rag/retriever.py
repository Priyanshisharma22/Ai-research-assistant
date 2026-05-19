import chromadb
from rag.embeddings import embed_texts
from config import settings

client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
collection = client.get_or_create_collection("research_docs")

def retrieve(query: str, top_k: int = 5) -> list[dict]:
    query_embedding = embed_texts([query])[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    sources = []
    for i, doc in enumerate(results["documents"][0]):
        sources.append({
            "content": doc,
            "source": results["metadatas"][0][i].get("source", "unknown"),
            "score": round(1 - results["distances"][0][i], 3) if results.get("distances") else 0.0,
        })
    return sources
