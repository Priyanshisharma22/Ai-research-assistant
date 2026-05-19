import os
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
        yield "data: " + json.dumps({"status": "reading", "message": "Reading " + file.filename + "..."}) + "\n\n"
        yield "data: " + json.dumps({"status": "summarizing", "message": "Generating AI summary..."}) + "\n\n"
        result = ingest_pdf(file_path, file.filename)
        yield "data: " + json.dumps({"status": "indexing", "message": "Indexed " + str(result["chunks"]) + " chunks"}) + "\n\n"
        yield "data: " + json.dumps({"status": "done", "message": "Ready", "summary": result["summary"], "filename": file.filename, "chunks": result["chunks"]}) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(progress_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.get("/summaries")
def get_summaries():
    return load_summaries()
