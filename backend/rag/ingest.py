import fitz
import json
import os
import uuid
from rag.summarizer import summarize_document
from config import settings

SUMMARIES_FILE = os.path.join(settings.upload_dir, "summaries.json")
CHUNKS_FILE = os.path.join(settings.upload_dir, "chunks.json")


def load_summaries():
    os.makedirs(settings.upload_dir, exist_ok=True)
    if os.path.exists(SUMMARIES_FILE):
        with open(SUMMARIES_FILE) as f:
            return json.load(f)
    return {}


def save_summary(filename, summary, chunk_count):
    summaries = load_summaries()
    summaries[filename] = {
        "summary": summary,
        "chunks": chunk_count,
        "filename": filename
    }
    with open(SUMMARIES_FILE, "w") as f:
        json.dump(summaries, f, indent=2)


def load_chunks():
    if os.path.exists(CHUNKS_FILE):
        with open(CHUNKS_FILE) as f:
            return json.load(f)
    return []


def save_chunks(chunks):
    os.makedirs(settings.upload_dir, exist_ok=True)
    with open(CHUNKS_FILE, "w") as f:
        json.dump(chunks, f, indent=2)


def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def search_chunks(query: str, top_k: int = 5) -> list[dict]:
    """Lightweight keyword search — replaces ChromaDB vector search."""
    all_chunks = load_chunks()
    if not all_chunks:
        return []

    query_terms = set(query.lower().split())
    scored = []
    for chunk in all_chunks:
        doc_words = chunk["text"].lower().split()
        doc_term_set = set(doc_words)
        tf = sum(doc_words.count(t) for t in query_terms)
        overlap = len(query_terms & doc_term_set)
        score = tf + overlap * 2
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for _, chunk in scored[:top_k]]


def ingest_pdf(file_path: str, filename: str) -> dict:
    # Extract text from PDF
    doc = fitz.open(file_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()

    if not full_text.strip():
        return {"chunks": 0, "summary": "Could not extract text from PDF."}

    # Generate summary
    summary = summarize_document(full_text, filename)

    # Chunk the text
    text_chunks = chunk_text(full_text)
    all_texts = [f"DOCUMENT SUMMARY - {filename}: {summary}"] + text_chunks

    # Load existing chunks, remove old ones for this file
    existing = load_chunks()
    existing = [c for c in existing if c.get("source") != filename]

    # Build new chunk records
    new_chunks = [
        {
            "id": str(uuid.uuid4()),
            "text": text,
            "source": filename,
            "chunk": i,
            "is_summary": i == 0
        }
        for i, text in enumerate(all_texts)
    ]

    save_chunks(existing + new_chunks)
    save_summary(filename, summary, len(text_chunks))

    return {"chunks": len(text_chunks), "summary": summary}