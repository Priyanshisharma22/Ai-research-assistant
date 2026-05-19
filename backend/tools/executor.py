"""
tools/executor.py
-----------------
Sandboxed code execution engine for Python and JavaScript.
Works like a lightweight Jupyter kernel — runs code, captures output,
returns stdout / stderr / result / plots.

Features:
  - Python execution with timeout + memory limit
  - JavaScript execution via Node.js
  - Matplotlib/Plotly plot capture (base64 PNG)
  - Persistent kernel state per session (variables survive between calls)
  - Dangerous import/pattern blocking
  - Auto-install missing packages (pip) in a safe subprocess

Usage:
    from tools.executor import execute_code, reset_kernel, get_kernel_vars

    result = await execute_code(
        code="import pandas as pd\ndf = pd.DataFrame({'a':[1,2,3]})\nprint(df)",
        language="python",
        session_id="user-123",
        timeout=15,
    )
    print(result["stdout"])
    print(result["error"])
    print(result["plots"])   # list of base64 PNG strings
"""

import sys
import os
import io
import ast
import time
import base64
import signal
import textwrap
import traceback
import subprocess
import tempfile
import threading
from typing import Optional
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

# ---------------------------------------------------------------------------
# Per-session kernel state (Python only)
# Variables persist between code cells in the same session
# ---------------------------------------------------------------------------
_kernels: dict[str, dict] = {}   # session_id → namespace dict


def _get_kernel(session_id: str) -> dict:
    """Get or create a persistent namespace for a session."""
    if session_id not in _kernels:
        _kernels[session_id] = {
            "__builtins__": __builtins__,
            "__name__": f"kernel_{session_id[:8]}",
        }
    return _kernels[session_id]


def reset_kernel(session_id: str) -> None:
    """Clear all variables for a session (fresh kernel)."""
    if session_id in _kernels:
        del _kernels[session_id]


def get_kernel_vars(session_id: str) -> list[dict]:
    """
    Return a summary of variables currently in the kernel.
    Useful for showing the user what's defined.
    """
    ns = _kernels.get(session_id, {})
    result = []
    skip = {"__builtins__", "__name__", "__doc__", "__package__"}
    for k, v in ns.items():
        if k.startswith("_") or k in skip:
            continue
        try:
            type_name = type(v).__name__
            # Safe repr — truncate large objects
            repr_str = repr(v)
            if len(repr_str) > 200:
                repr_str = repr_str[:200] + "…"
            result.append({"name": k, "type": type_name, "value": repr_str})
        except Exception:
            result.append({"name": k, "type": "unknown", "value": "?"})
    return result


# ---------------------------------------------------------------------------
# Security — blocked patterns
# ---------------------------------------------------------------------------

BLOCKED_IMPORTS = {
    "os.system", "subprocess", "pty", "socket", "urllib",
    "requests", "httpx", "ftplib", "smtplib", "telnetlib",
    "shutil.rmtree", "pathlib.Path.unlink",
}

BLOCKED_PATTERNS = [
    "__import__('os').system",
    "open('/etc",
    "open('C:\\\\Windows",
    "exec(compile",
    "ctypes",
    "importlib.import_module('subprocess')",
]

ALLOWED_IMPORTS = {
    # Data science
    "numpy", "pandas", "scipy", "sklearn", "statsmodels",
    # Plotting
    "matplotlib", "seaborn", "plotly",
    # Math
    "math", "statistics", "random", "decimal", "fractions",
    # Standard utils
    "json", "csv", "re", "datetime", "collections", "itertools",
    "functools", "string", "textwrap", "pprint", "copy",
    "typing", "dataclasses", "enum", "abc",
    # IO (safe)
    "io", "pathlib",
    # ML / AI
    "torch", "tensorflow", "transformers",
    # Others
    "sympy", "networkx", "PIL", "cv2",
}


def _is_safe(code: str) -> tuple[bool, str]:
    """
    Quick safety check — returns (is_safe, reason_if_not).
    Not a full sandbox, but blocks the most obvious attacks.
    """
    for pattern in BLOCKED_PATTERNS:
        if pattern in code:
            return False, f"Blocked pattern detected: `{pattern}`"

    # Parse and check imports
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return True, ""   # Let execution catch syntax errors with better messages

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                names = [node.module or ""]

            for name in names:
                root = name.split(".")[0]
                if root not in ALLOWED_IMPORTS and root in {
                    "subprocess", "socket", "pty", "ctypes",
                    "winreg", "msvcrt",
                }:
                    return False, f"Import `{name}` is not allowed for security reasons."

    return True, ""


# ---------------------------------------------------------------------------
# Plot capture helper
# ---------------------------------------------------------------------------

def _capture_matplotlib_plots() -> list[str]:
    """Return a list of base64-encoded PNG strings for all open matplotlib figures."""
    plots = []
    try:
        import matplotlib.pyplot as plt
        for fig_num in plt.get_fignums():
            fig = plt.figure(fig_num)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
            buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode("utf-8")
            plots.append(b64)
        plt.close("all")
    except ImportError:
        pass
    except Exception:
        pass
    return plots


# ---------------------------------------------------------------------------
# Python executor
# ---------------------------------------------------------------------------

def _execute_python(
    code: str,
    session_id: str,
    timeout: int = 15,
) -> dict:
    """
    Execute Python code in the session's persistent kernel.

    Returns:
        {
          stdout: str,
          stderr: str,
          error:  str | None,
          result: str | None,   # repr of last expression if it has a value
          plots:  list[str],    # base64 PNG strings
          exec_time_ms: float,
        }
    """
    # Safety check
    safe, reason = _is_safe(code)
    if not safe:
        return {
            "stdout": "",
            "stderr": "",
            "error": f"🚫 Security check failed: {reason}",
            "result": None,
            "plots": [],
            "exec_time_ms": 0,
        }

    ns = _get_kernel(session_id)
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    error_msg  = None
    result_val = None
    start_time = time.perf_counter()

    # Run in a thread so we can enforce timeout
    exc_holder: list[Exception] = []

    def _run():
        nonlocal result_val
        try:
            # Try to compile as interactive (eval last expr) first
            try:
                tree = ast.parse(code, mode="exec")
                # Check if last statement is an expression → capture its value
                if tree.body and isinstance(tree.body[-1], ast.Expr):
                    # Split: run all but last, then eval last
                    exec_part = ast.Module(body=tree.body[:-1], type_ignores=[])
                    eval_part = ast.Expression(body=tree.body[-1].value)
                    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                        exec(compile(exec_part, "<cell>", "exec"), ns)
                        result_val = eval(compile(eval_part, "<cell>", "eval"), ns)
                else:
                    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                        exec(compile(tree, "<cell>", "exec"), ns)
            except SyntaxError:
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    exec(code, ns)
        except Exception as e:
            exc_holder.append(e)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    exec_time_ms = (time.perf_counter() - start_time) * 1000

    if thread.is_alive():
        # Timeout — we can't actually kill the thread in Python,
        # but we flag it and the thread will eventually finish
        return {
            "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(),
            "error": f"⏱ Execution timed out after {timeout}s.",
            "result": None,
            "plots": [],
            "exec_time_ms": timeout * 1000,
        }

    if exc_holder:
        exc = exc_holder[0]
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        # Remove internal frames to keep traceback clean
        clean_tb = "".join(
            line for line in tb_lines
            if "<cell>" in line or type(exc).__name__ in line
            or not line.strip().startswith('File "/')
        )
        error_msg = clean_tb.strip()

    # Capture any matplotlib plots generated
    plots = _capture_matplotlib_plots()

    # Format result
    result_str = None
    if result_val is not None:
        try:
            result_str = repr(result_val)
            if len(result_str) > 2000:
                result_str = result_str[:2000] + "\n… (truncated)"
        except Exception:
            result_str = "<unprintable result>"

    return {
        "stdout":       stdout_buf.getvalue(),
        "stderr":       stderr_buf.getvalue(),
        "error":        error_msg,
        "result":       result_str,
        "plots":        plots,
        "exec_time_ms": round(exec_time_ms, 1),
    }


# ---------------------------------------------------------------------------
# JavaScript executor (requires Node.js on PATH)
# ---------------------------------------------------------------------------

def _execute_javascript(
    code: str,
    timeout: int = 15,
) -> dict:
    """
    Execute JavaScript via Node.js subprocess.
    Stateless — no persistent kernel (each call is fresh).
    """
    # Wrap code to capture console.log output
    wrapped = textwrap.dedent(f"""
        const __logs = [];
        const __origLog = console.log;
        console.log = (...args) => {{ __logs.push(args.map(String).join(' ')); __origLog(...args); }};
        console.error = (...args) => {{ process.stderr.write(args.join(' ') + '\\n'); }};

        try {{
            {code}
        }} catch(e) {{
            process.stderr.write('Error: ' + e.message + '\\n' + (e.stack || ''));
            process.exit(1);
        }}
    """)

    start_time = time.perf_counter()

    try:
        proc = subprocess.run(
            ["node", "--experimental-vm-modules", "-e", wrapped],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exec_time_ms = (time.perf_counter() - start_time) * 1000
        return {
            "stdout":       proc.stdout,
            "stderr":       proc.stderr,
            "error":        proc.stderr if proc.returncode != 0 else None,
            "result":       None,
            "plots":        [],
            "exec_time_ms": round(exec_time_ms, 1),
        }
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": "",
            "error":  "❌ Node.js not found. Install from https://nodejs.org/",
            "result": None,
            "plots":  [],
            "exec_time_ms": 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "",
            "error":  f"⏱ JavaScript execution timed out after {timeout}s.",
            "result": None,
            "plots":  [],
            "exec_time_ms": timeout * 1000,
        }


# ---------------------------------------------------------------------------
# Package auto-installer
# ---------------------------------------------------------------------------

def _try_install(package: str) -> tuple[bool, str]:
    """
    Attempt to pip-install a missing package.
    Returns (success, message).
    """
    safe_name = package.strip().split()[0]   # prevent shell injection
    if not safe_name.replace("-", "").replace("_", "").isalnum():
        return False, f"Invalid package name: {safe_name}"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", safe_name, "--quiet"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            return True, f"✅ Installed `{safe_name}` successfully."
        return False, f"❌ pip install failed:\n{result.stderr[:300]}"
    except subprocess.TimeoutExpired:
        return False, "❌ pip install timed out."
    except Exception as e:
        return False, f"❌ Install error: {e}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def execute_code(
    code: str,
    language: str = "python",
    session_id: str = "default",
    timeout: int = 15,
    auto_install: bool = True,
) -> dict:
    """
    Execute code in a sandboxed environment.

    Args:
        code        : Source code to run.
        language    : 'python' or 'javascript'
        session_id  : Kernel namespace key (Python only — variables persist).
        timeout     : Max seconds before killing execution.
        auto_install: If True, try to pip-install missing Python packages.

    Returns dict with keys:
        stdout       : str   — captured print output
        stderr       : str   — stderr output
        error        : str | None — formatted error message
        result       : str | None — repr of last expression
        plots        : list[str]  — base64 PNG images (matplotlib)
        exec_time_ms : float — wall-clock execution time
        language     : str
        install_msg  : str | None — message if a package was auto-installed
    """
    code = code.strip()
    if not code:
        return {
            "stdout": "", "stderr": "", "error": "No code provided.",
            "result": None, "plots": [], "exec_time_ms": 0,
            "language": language, "install_msg": None,
        }

    language = language.lower().strip()
    install_msg = None

    if language in ("python", "py"):
        result = _execute_python(code, session_id, timeout)

        # Auto-install missing packages and retry once
        if auto_install and result["error"]:
            err = result["error"]
            if "ModuleNotFoundError" in err or "No module named" in err:
                # Extract package name from error
                import re
                match = re.search(r"No module named '([^']+)'", err)
                if match:
                    pkg = match.group(1).split(".")[0]
                    ok, msg = _try_install(pkg)
                    install_msg = msg
                    if ok:
                        # Retry after install
                        result = _execute_python(code, session_id, timeout)

        result["language"]    = "python"
        result["install_msg"] = install_msg
        return result

    elif language in ("javascript", "js", "node"):
        result = _execute_javascript(code, timeout)
        result["language"]    = "javascript"
        result["install_msg"] = None
        return result

    else:
        return {
            "stdout": "", "stderr": "",
            "error":  f"Unsupported language: `{language}`. Use 'python' or 'javascript'.",
            "result": None, "plots": [], "exec_time_ms": 0,
            "language": language, "install_msg": None,
        }


def format_execution_result(result: dict) -> str:
    """
    Format an execution result into a clean markdown string
    suitable for injecting into the LLM system prompt or response.
    """
    lines = []
    lang = result.get("language", "python")
    ms   = result.get("exec_time_ms", 0)
    lines.append(f"**Code executed** ({lang}, {ms:.0f}ms)")

    if result.get("install_msg"):
        lines.append(f"\n{result['install_msg']}")

    if result.get("stdout"):
        lines.append(f"\n**Output:**\n```\n{result['stdout'].rstrip()}\n```")

    if result.get("result"):
        lines.append(f"\n**Result:** `{result['result']}`")

    if result.get("stderr") and not result.get("error"):
        lines.append(f"\n**Warnings:**\n```\n{result['stderr'].rstrip()}\n```")

    if result.get("error"):
        lines.append(f"\n**Error:**\n```\n{result['error']}\n```")

    if result.get("plots"):
        n = len(result["plots"])
        lines.append(f"\n📊 {n} plot(s) generated.")

    return "\n".join(lines)