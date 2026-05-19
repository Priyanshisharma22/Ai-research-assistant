"""
routers/code.py
---------------
FastAPI router exposing the code execution tool via REST + SSE.

Mount in main.py:
    from routers.code import code_router
    app.include_router(code_router, prefix="/api")

Endpoints:
    POST /api/execute          — run code, get full result JSON
    POST /api/execute/stream   — run code, stream output line by line
    GET  /api/kernel/{sid}     — list variables in a session kernel
    DELETE /api/kernel/{sid}   — reset (clear) a session kernel
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import asyncio
import json

from tools.executor import (
    execute_code,
    reset_kernel,
    get_kernel_vars,
    format_execution_result,
)

code_router = APIRouter(tags=["code-execution"])


# ── Request / Response models ─────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    code:         str  = Field(..., min_length=1, description="Source code to execute.")
    language:     str  = Field(default="python", description="'python' or 'javascript'")
    session_id:   str  = Field(default="default", description="Kernel namespace (Python only).")
    timeout:      int  = Field(default=15, ge=1, le=60, description="Max seconds to run.")
    auto_install: bool = Field(default=True, description="Auto pip-install missing packages.")


class ExecuteResponse(BaseModel):
    stdout:       str
    stderr:       str
    error:        Optional[str]
    result:       Optional[str]
    plots:        list[str]        # base64 PNG strings
    exec_time_ms: float
    language:     str
    install_msg:  Optional[str]
    formatted:    str              # pre-formatted markdown summary


# ── Endpoints ─────────────────────────────────────────────────────────────

@code_router.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest):
    """
    Execute Python or JavaScript code and return the full result.
    Python kernels are stateful — variables persist across calls with the same session_id.
    """
    result = await execute_code(
        code=req.code,
        language=req.language,
        session_id=req.session_id,
        timeout=req.timeout,
        auto_install=req.auto_install,
    )
    result["formatted"] = format_execution_result(result)
    return result


@code_router.post("/execute/stream")
async def execute_stream(req: ExecuteRequest):
    """
    Execute code and stream output line-by-line as Server-Sent Events.
    Useful for long-running cells with lots of print() output.
    """
    async def event_generator():
        # Start execution
        yield f"data: {json.dumps({'type': 'start', 'language': req.language})}\n\n"

        result = await execute_code(
            code=req.code,
            language=req.language,
            session_id=req.session_id,
            timeout=req.timeout,
            auto_install=req.auto_install,
        )

        # Stream install message if any
        if result.get("install_msg"):
            yield f"data: {json.dumps({'type': 'install', 'data': result['install_msg']})}\n\n"

        # Stream stdout line by line
        if result.get("stdout"):
            for line in result["stdout"].splitlines():
                yield f"data: {json.dumps({'type': 'stdout', 'data': line})}\n\n"
                await asyncio.sleep(0)   # yield control to event loop

        # Stream result value
        if result.get("result"):
            yield f"data: {json.dumps({'type': 'result', 'data': result['result']})}\n\n"

        # Stream error
        if result.get("error"):
            yield f"data: {json.dumps({'type': 'error', 'data': result['error']})}\n\n"

        # Stream plot count
        if result.get("plots"):
            for i, b64 in enumerate(result["plots"]):
                yield f"data: {json.dumps({'type': 'plot', 'index': i, 'data': b64})}\n\n"

        # Done
        yield f"data: {json.dumps({'type': 'done', 'exec_time_ms': result['exec_time_ms']})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@code_router.get("/kernel/{session_id}")
async def kernel_variables(session_id: str):
    """List all variables currently defined in a session's Python kernel."""
    variables = get_kernel_vars(session_id)
    return {
        "session_id": session_id,
        "variable_count": len(variables),
        "variables": variables,
    }


@code_router.delete("/kernel/{session_id}")
async def kernel_reset(session_id: str):
    """Reset (clear) a session's Python kernel — all variables are lost."""
    reset_kernel(session_id)
    return {"session_id": session_id, "status": "reset", "message": "Kernel cleared."}