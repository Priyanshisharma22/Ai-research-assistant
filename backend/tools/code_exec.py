# tools/code_exec.py
import subprocess
import sys
import tempfile
import os
from fastapi import APIRouter

code_router = APIRouter()

@code_router.post("/execute")
async def execute_code(payload: dict):
    code = payload.get("code", "")
    language = payload.get("language", "python")

    if language != "python":
        return {"output": "", "error": f"Language '{language}' not supported. Only Python is supported."}

    # Write code to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=30,  # 30s for Render
        )
        return {
            "output": result.stdout,
            "error": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "output": "",
            "error": "Execution timed out after 30s.",
        }
    except Exception as e:
        return {
            "output": "",
            "error": str(e),
        }
    finally:
        os.unlink(tmp_path)  # clean up temp file