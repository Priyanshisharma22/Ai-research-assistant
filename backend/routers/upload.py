# routers/upload.py
import os
import json
import asyncio
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
from rag.ingest import ingest_pdf, load_summaries
from config import settings

router = APIRouter()
os.makedirs(settings.upload_dir, exist_ok=True)

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_path = os.path.join(settings.upload_dir, file.filename)
    
    # Read and save file
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    async def progress_stream():
        try:
            yield "data: " + json.dumps({
                "status": "reading",
                "message": f"Reading {file.filename}..."
            }) + "\n\n"

            yield "data: " + json.dumps({
                "status": "summarizing",
                "message": "Generating AI summary..."
            }) + "\n\n"

            # Run blocking ingest_pdf in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, ingest_pdf, file_path, file.filename)

            yield "data: " + json.dumps({
                "status": "indexing",
                "message": f"Indexed {result['chunks']} chunks"
            }) + "\n\n"

            yield "data: " + json.dumps({
                "status": "done",
                "message": "Ready",
                "summary": result["summary"],
                "filename": file.filename,
                "chunks": result["chunks"]
            }) + "\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            # Send error back to frontend via SSE
            yield "data: " + json.dumps({
                "status": "error",
                "message": f"Upload failed: {str(e)}"
            }) + "\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        progress_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

@router.get("/summaries")
def get_summaries():
    return load_summaries()