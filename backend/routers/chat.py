from fastapi import APIRouter, Response, Request
from fastapi.responses import StreamingResponse
from models.schemas import QueryRequest
from agents.orchestrator import run
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.options("/chat")
async def chat_options(request: Request):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

@router.post("/chat")
async def chat(request: QueryRequest):
    async def event_stream():
        try:
            async for event in run(
                request.query,
                request.session_id,
                request.model_id,
                request.image_b64,
                request.image_media_type,
                request.persona,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )

@router.get("/personas")
def get_personas():
    from agents.orchestrator import PERSONA_PROMPTS
    return PERSONA_PROMPTS