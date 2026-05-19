import os

files = {
'rag/ingest.py': """import fitz
import chromadb
import json
import os
from rag.embeddings import embed_texts
from rag.summarizer import summarize_document
from config import settings
import uuid

client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
collection = client.get_or_create_collection("research_docs")
SUMMARIES_FILE = os.path.join(settings.chroma_persist_dir, "summaries.json")

def load_summaries():
    os.makedirs(settings.chroma_persist_dir, exist_ok=True)
    if os.path.exists(SUMMARIES_FILE):
        with open(SUMMARIES_FILE) as f:
            return json.load(f)
    return {}

def save_summary(filename, summary, chunk_count):
    summaries = load_summaries()
    summaries[filename] = {"summary": summary, "chunks": chunk_count, "filename": filename}
    with open(SUMMARIES_FILE, "w") as f:
        json.dump(summaries, f, indent=2)

def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks

def ingest_pdf(file_path, filename):
    doc = fitz.open(file_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()
    if not full_text.strip():
        return {"chunks": 0, "summary": "Could not extract text from PDF."}
    summary = summarize_document(full_text, filename)
    summary_chunk = "DOCUMENT SUMMARY - " + filename + ": " + summary
    all_chunks = [summary_chunk] + chunk_text(full_text)
    embeddings = embed_texts(all_chunks)
    ids = [str(uuid.uuid4()) for _ in all_chunks]
    metadatas = [{"source": filename, "chunk": i, "is_summary": i == 0} for i in range(len(all_chunks))]
    collection.add(documents=all_chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)
    save_summary(filename, summary, len(all_chunks) - 1)
    return {"chunks": len(all_chunks) - 1, "summary": summary}
""",

'rag/summarizer.py': """import anthropic
from config import settings

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

def summarize_document(text, filename):
    truncated = text[:8000]
    prompt = "Summarize this document in 3-5 sentences covering main topic, key findings, and conclusions. Document: " + filename + ". Content: " + truncated
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text
""",

'routers/upload.py': """import os
import json
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
from rag.ingest import ingest_pdf, load_summaries
from config import settings

router = APIRouter()
os.makedirs(settings.upload_dir, exist_ok=True)

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join(settings.upload_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    async def progress_stream():
        yield "data: " + json.dumps({"status": "reading", "message": "Reading " + file.filename + "..."}) + "\\n\\n"
        yield "data: " + json.dumps({"status": "summarizing", "message": "Generating AI summary..."}) + "\\n\\n"
        result = ingest_pdf(file_path, file.filename)
        yield "data: " + json.dumps({"status": "indexing", "message": "Indexed " + str(result["chunks"]) + " chunks"}) + "\\n\\n"
        yield "data: " + json.dumps({"status": "done", "message": "Ready", "summary": result["summary"], "filename": file.filename, "chunks": result["chunks"]}) + "\\n\\n"
        yield "data: [DONE]\\n\\n"

    return StreamingResponse(progress_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.get("/summaries")
def get_summaries():
    return load_summaries()
""",
}

for path, content in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(path + " OK")