from config import settings
from rag.retriever import retrieve
from tools.search import web_search
from tools.executor import execute_code, format_execution_result
from memory.short_term import get_history, add_message, set_history
from memory.long_term import (
    save_message          as lt_save,
    get_session_history   as lt_get_history,
    get_cross_session_context,
)
from memory.user_profile import extract_and_save, build_profile_block
from typing import AsyncGenerator
import asyncio
import os
import re
import json
import glob
import time

PERSONA_PROMPTS = {
    "student":    "Explain clearly and simply, avoid jargon, use analogies and examples.",
    "researcher": "Be technically precise, include methodology, cite sources rigorously.",
    "executive":  "Be concise, focus on key insights and actionable takeaways only.",
    "creative":   "Use storytelling, vivid examples, and engaging narrative style.",
}

# ---------------------------------------------------------------------------
# Groq vision model registry
# ---------------------------------------------------------------------------
GROQ_VISION_MODELS = {
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
}

GEMINI_DEPRECATED = {
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-1.0-pro",
}
GEMINI_FALLBACK = "gemini-2.0-flash"

# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------
FALLBACK_CHAIN: list[str] = [
    "groq/llama-3.3-70b-versatile",
    "groq/llama-3.1-8b-instant",
    "gemini/gemini-2.0-flash",
    "openai/gpt-4o-mini",
    "anthropic/claude-haiku-4-5-20251001",
    "mistral/mistral-small-latest",
]

FALLBACK_TRIGGER_PATTERNS = [
    "429", "quota", "rate limit", "rate_limit",
    "overloaded", "capacity", "503", "502", "504",
    "model not found", "404", "does not exist",
    "context length", "token limit",
]

# FIX: Models with small context windows — skip when prompt is large
SMALL_CONTEXT_MODELS = {
    "groq/llama-3.1-8b-instant",
    "mistral/mistral-small-latest",
}

# FIX: If the total prompt exceeds this char count, skip small-context models
MAX_PROMPT_CHARS_FOR_SMALL_MODELS = 8_000

# FIX: Gemini retry config — reduced from 30s/60s to avoid blocking fallback chain
GEMINI_RETRY_WAIT_SECONDS = [10, 20]   # wait before attempt 2, wait before attempt 3
GEMINI_MAX_RETRIES = 3

# Regex to find code blocks in LLM responses
CODE_BLOCK_RE = re.compile(
    r"```(python|javascript|js|py)\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def should_fallback(error_str: str) -> bool:
    """Return True if the error is retriable and we should try the next model."""
    lower = error_str.lower()
    # FIX: 413 (request too large) should NOT trigger a generic fallback —
    # it will be handled separately by skipping small-context models.
    if "413" in error_str:
        return False
    return any(p in lower for p in FALLBACK_TRIGGER_PATTERNS)


def estimate_prompt_chars(messages: list, system: str) -> int:
    """Rough character count of the full prompt sent to the LLM."""
    total = len(system)
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(part.get("text", ""))
    return total


def get_fallback_chain(primary_model_id: str, prompt_char_len: int = 0) -> list[str]:
    """
    Build the ordered fallback list after the primary model.

    FIX: Skip small-context models when the prompt is too large (avoids 413 errors).
    """
    try:
        idx = FALLBACK_CHAIN.index(primary_model_id)
        candidates = FALLBACK_CHAIN[idx + 1:]
    except ValueError:
        candidates = FALLBACK_CHAIN[:]

    available = []
    for model_id in candidates:
        # FIX: Skip small-context models for large prompts
        if (
            prompt_char_len > MAX_PROMPT_CHARS_FOR_SMALL_MODELS
            and model_id in SMALL_CONTEXT_MODELS
        ):
            print(
                f"[orchestrator] ⏭  Skipping {model_id!r} — "
                f"prompt ({prompt_char_len:,} chars) exceeds small-model limit"
            )
            continue

        provider = model_id.split("/")[0]
        key_map = {
            "groq":      getattr(settings, "groq_api_key",      None),
            "gemini":    getattr(settings, "gemini_api_key",    None),
            "openai":    getattr(settings, "openai_api_key",    None),
            "anthropic": getattr(settings, "anthropic_api_key", None),
            "mistral":   getattr(settings, "mistral_api_key",   None),
        }
        key = key_map.get(provider, "")
        if key and key.strip() and key != f"your-{provider}-key-here":
            available.append(model_id)
    return available


def is_groq_vision_model(model_name: str) -> bool:
    lower = model_name.lower()
    return (
        model_name in GROQ_VISION_MODELS
        or "vision" in lower
        or "llama-4" in lower
        or "scout" in lower
        or "maverick" in lower
    )


def load_images_for_query(upload_dir: str) -> list[dict]:
    images = []
    pattern = os.path.join(upload_dir, "images", "*.json")
    for path in glob.glob(pattern):
        with open(path) as f:
            images.extend(json.load(f))
    return images


def parse_model_id(model_id: str) -> tuple[str, str]:
    parts = model_id.split("/")
    provider = parts[0]
    model_name = "/".join(parts[1:])
    return provider, model_name


def format_error(provider: str, model_id: str, model_name: str, error_str: str) -> str:
    err_lower = error_str.lower()

    if "429" in error_str or "quota" in err_lower or "rate" in err_lower:
        tips = {
            "gemini": (
                "- Wait ~1 min and retry (free tier = 15 req/min, 1 500 req/day)\n"
                "- Switch to **Groq — Llama 4 Scout Vision** (free & fast)\n"
                "- Upgrade at https://ai.google.dev/pricing"
            ),
            "groq": (
                "- Wait ~1 min and retry\n"
                "- Switch to a different Groq model\n"
                "- Check limits at https://console.groq.com"
            ),
            "openai": (
                "- Check billing at https://platform.openai.com/usage\n"
                "- Add credits or upgrade your plan"
            ),
            "anthropic": (
                "- Check usage at https://console.anthropic.com\n"
                "- Add credits or upgrade your plan"
            ),
            "mistral": "- Check usage at https://console.mistral.ai",
        }
        tip = tips.get(provider, "- Try a different model or wait and retry.")
        return (
            f"⚠️ **{provider.title()} quota / rate-limit exceeded** for `{model_name}`.\n\n"
            f"**What to do:**\n{tip}"
        )

    if "413" in error_str:
        return (
            f"⚠️ **Request too large** for `{model_name}`.\n\n"
            "The conversation context is too long for this model's context window.\n"
            "Try starting a new session or switching to a model with a larger context window."
        )

    if "404" in error_str or "not found" in err_lower:
        return (
            f"⚠️ **Model not found**: `{model_name}`.\n\n"
            "Please select a different model from the dropdown.\n\n"
            f"Details: `{error_str[:200]}`"
        )

    if "401" in error_str or "403" in error_str or "authentication" in err_lower or "api key" in err_lower:
        return (
            f"⚠️ **Invalid or missing API key** for provider `{provider}`.\n\n"
            "Check your `.env` file and make sure the correct key is set."
        )

    return (
        f"⚠️ **Error from `{model_id}`**:\n"
        f"```\n{error_str[:400]}\n```"
    )


# ---------------------------------------------------------------------------
# Code execution helper
# ---------------------------------------------------------------------------

async def auto_execute_code_blocks(
    response_text: str,
    session_id: str,
) -> tuple[str, list[dict]]:
    """
    Detect ```python / ```javascript blocks in the LLM response,
    execute each one, and append the output inline after the block.

    Returns:
        (augmented_response_text, list_of_execution_results)
    """
    execution_results = []
    augmented = response_text

    for match in CODE_BLOCK_RE.finditer(response_text):
        lang = match.group(1).lower()
        code = match.group(2).strip()

        result = await execute_code(
            code=code,
            language=lang,
            session_id=session_id,
            timeout=15,
            auto_install=True,
        )
        execution_results.append(result)

        formatted = format_execution_result(result)
        augmented = augmented.replace(
            match.group(0),
            match.group(0) + f"\n\n{formatted}",
            1,
        )

    return augmented, execution_results


# ---------------------------------------------------------------------------
# Core streaming helper — sync, called via asyncio.to_thread
# ---------------------------------------------------------------------------

def get_stream_chunks(
    model_id: str,
    messages: list,
    system: str,
    images: list[dict],
) -> list[str]:
    provider, model_name = parse_model_id(model_id)

    # ── Groq ──────────────────────────────────────────────────────────────
    if provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)

        if is_groq_vision_model(model_name) and images:
            last_user_msg = messages[-1]["content"] if messages else ""
            user_content: list = [
                {"type": "text", "text": f"{system}\n\n{last_user_msg}"}
            ]
            for img in images[:5]:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{img['media_type']};base64,{img['b64']}"},
                })
            api_messages = [{"role": "user", "content": user_content}]
        else:
            api_messages = [{"role": "system", "content": system}] + messages

        stream = client.chat.completions.create(
            model=model_name,
            messages=api_messages,
            max_tokens=2000,
            stream=True,
        )
        return [chunk.choices[0].delta.content or "" for chunk in stream]

    # ── Anthropic ─────────────────────────────────────────────────────────
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

        user_content: list = []
        for img in images[:5]:
            user_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img["media_type"],
                    "data": img["b64"],
                },
            })
        last_user_msg = messages[-1]["content"] if messages else ""
        user_content.append({"type": "text", "text": last_user_msg})
        history_messages = messages[:-1] + [{"role": "user", "content": user_content}]

        chunks: list[str] = []
        with client.messages.stream(
            model=model_name,
            max_tokens=2000,
            system=system,
            messages=history_messages,
        ) as stream:
            for text in stream.text_stream:
                chunks.append(text)
        return chunks

    # ── OpenAI ────────────────────────────────────────────────────────────
    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)

        last_user_msg = messages[-1]["content"] if messages else ""
        user_content: list = [{"type": "text", "text": last_user_msg}]
        for img in images[:5]:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img['media_type']};base64,{img['b64']}"},
            })
        history_messages = messages[:-1] + [{"role": "user", "content": user_content}]

        stream = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": system}] + history_messages,
            max_tokens=2000,
            stream=True,
        )
        return [chunk.choices[0].delta.content or "" for chunk in stream]

    # ── Google Gemini ─────────────────────────────────────────────────────
    elif provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)

        if model_name in GEMINI_DEPRECATED:
            print(f"[orchestrator] WARNING: '{model_name}' deprecated → using '{GEMINI_FALLBACK}'")
            model_name = GEMINI_FALLBACK

        model = genai.GenerativeModel(model_name=model_name, system_instruction=system)

        parts: list = []
        for img in images[:5]:
            parts.append({"inline_data": {"mime_type": img["media_type"], "data": img["b64"]}})

        history_text = ""
        for msg in messages[:-1]:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_text += f"{role}: {msg['content']}\n"

        last_user_msg = messages[-1]["content"] if messages else ""
        parts.append({"text": f"{history_text}User: {last_user_msg}"})

        last_exc: Exception | None = None
        for attempt in range(GEMINI_MAX_RETRIES):
            try:
                response = model.generate_content(parts)
                return [response.text]
            except Exception as exc:
                last_exc = exc
                err_str = str(exc)
                is_quota = "429" in err_str or "quota" in err_str.lower()
                # FIX: Use shorter wait times (10s, 20s) instead of 30s, 60s
                # to avoid blocking the fallback chain for too long.
                if is_quota and attempt < GEMINI_MAX_RETRIES - 1:
                    wait_sec = GEMINI_RETRY_WAIT_SECONDS[attempt]
                    print(
                        f"[orchestrator] Gemini 429 (attempt {attempt + 1}/{GEMINI_MAX_RETRIES}). "
                        f"Retrying in {wait_sec}s..."
                    )
                    time.sleep(wait_sec)
                else:
                    break
        raise last_exc  # type: ignore[misc]

    # ── Mistral ───────────────────────────────────────────────────────────
    elif provider == "mistral":
        from mistralai import Mistral
        client = Mistral(api_key=settings.mistral_api_key)
        response = client.chat.complete(
            model=model_name,
            messages=[{"role": "system", "content": system}] + messages,
        )
        return [response.choices[0].message.content or ""]

    else:
        raise ValueError(
            f"Unknown provider: '{provider}' in model_id='{model_id}'. "
            "Supported: groq, anthropic, openai, gemini, mistral"
        )


# ---------------------------------------------------------------------------
# Fallback-aware wrapper
# ---------------------------------------------------------------------------

def get_stream_chunks_with_fallback(
    primary_model_id: str,
    messages: list,
    system: str,
    images: list[dict],
) -> tuple[list[str], str]:
    """
    Try primary model. On retriable error, walk down the fallback chain.

    FIX: Passes prompt_char_len to get_fallback_chain so small-context
    models are skipped automatically when the prompt is too large.

    Returns (chunks, model_id_that_succeeded).
    """
    # FIX: Estimate prompt size once so we can skip unsuitable fallbacks
    prompt_char_len = estimate_prompt_chars(messages, system)

    chain = [primary_model_id] + get_fallback_chain(primary_model_id, prompt_char_len)
    last_error = ""

    for attempt_num, model_id in enumerate(chain):
        try:
            if attempt_num > 0:
                print(f"[orchestrator] 🔄 Fallback attempt {attempt_num}: trying {model_id!r}")
            chunks = get_stream_chunks(model_id, messages, system, images)
            if attempt_num > 0:
                print(f"[orchestrator] ✅ Fallback succeeded with {model_id!r}")
            return chunks, model_id

        except Exception as exc:
            error_str = str(exc)
            last_error = error_str
            print(f"[orchestrator] ✖ {model_id!r} failed: {error_str[:120]}")

            # FIX: If the error is 413 for the primary model, rebuild the
            # fallback chain with the updated prompt size so small models
            # are excluded even if they weren't excluded initially.
            if "413" in error_str and attempt_num == 0:
                print(
                    f"[orchestrator] ⚠️  413 on primary — rebuilding fallback chain "
                    f"excluding small-context models (prompt={prompt_char_len:,} chars)"
                )
                chain = [primary_model_id] + get_fallback_chain(
                    primary_model_id,
                    max(prompt_char_len, MAX_PROMPT_CHARS_FOR_SMALL_MODELS + 1),
                )
                continue

            if attempt_num < len(chain) - 1 and should_fallback(error_str):
                time.sleep(1)
                continue
            else:
                break

    raise RuntimeError(f"All models in fallback chain failed. Last error: {last_error[:300]}")


# ---------------------------------------------------------------------------
# Main async orchestrator
# ---------------------------------------------------------------------------

async def run(
    query: str,
    session_id: str,
    model_id: str = "groq/llama-3.3-70b-versatile",
    image_b64: str | None = None,
    image_media_type: str | None = None,
    persona: str = "researcher",
) -> AsyncGenerator[dict, None]:

    print(
        f"[orchestrator] ▶  model_id={model_id!r}  "
        f"persona={persona!r}  session={session_id!r}"
    )

    provider, model_name = parse_model_id(model_id)

    yield {
        "agent": "orchestrator",
        "status": "thinking",
        "message": f"Using model: {model_id}",
    }

    # ── Step 1: Extract user profile facts ────────────────────────────────
    extracted = await asyncio.to_thread(extract_and_save, session_id, query)
    if extracted:
        print(f"[orchestrator] 🧠 Profile extracted: {extracted}")

    # ── Step 2: Memory ─────────────────────────────────────────────────────
    history = get_history(session_id)

    if not history:
        history = lt_get_history(session_id, limit=30)
        if history:
            set_history(session_id, history)
            print(
                f"[orchestrator] ♻  Reloaded {len(history)} messages "
                f"from long-term memory for session '{session_id}'"
            )

    past_context = get_cross_session_context(
        query=query,
        current_session_id=session_id,
        limit=3,
    )

    # ── Step 3: RAG retrieval ──────────────────────────────────────────────
    yield {"agent": "retrieval", "status": "thinking", "message": "Searching knowledge base..."}
    rag_sources = retrieve(query, top_k=4)

    # ── Step 4: Web search ─────────────────────────────────────────────────
    yield {"agent": "web_search", "status": "thinking", "message": "Searching web via DuckDuckGo..."}
    web_sources = await asyncio.to_thread(web_search, query, max_results=3)

    # ── Step 5: Vision ─────────────────────────────────────────────────────
    supports_vision = (
        provider in ("anthropic", "openai", "gemini")
        or (provider == "groq" and is_groq_vision_model(model_name))
    )

    images: list[dict] = []
    if supports_vision:
        yield {"agent": "vision", "status": "thinking", "message": "Loading figures from PDFs..."}
        images = await asyncio.to_thread(load_images_for_query, settings.upload_dir)
        yield {"agent": "vision", "status": "thinking", "message": f"Found {len(images)} figure(s)"}
    else:
        yield {"agent": "vision", "status": "thinking", "message": "⚠ Text-only model — image input skipped."}

    if image_b64 and image_media_type:
        images.insert(0, {"b64": image_b64, "media_type": image_media_type, "filename": "inline", "page": 0})

    # ── Step 6: Build context ──────────────────────────────────────────────
    all_sources = rag_sources + [
        {"content": s["content"], "source": s["url"], "score": 0.7}
        for s in web_sources
    ]
    context = "\n\n".join([
        f"[Source {i+1}: {s.get('source', 'web')}]\n{s['content']}"
        for i, s in enumerate(all_sources)
    ])

    # ── Step 7: Memory blocks ──────────────────────────────────────────────
    profile_block = await asyncio.to_thread(build_profile_block, session_id)

    session_memory_block = ""
    if history:
        recent = history[-6:]
        lines = []
        for m in recent:
            label = "User previously said" if m["role"] == "user" else "You previously answered"
            lines.append(f"- {label}: {m['content'][:300]}")
        session_memory_block = "\n\nCURRENT SESSION MEMORY:\n" + "\n".join(lines)

    cross_session_block = ""
    if past_context:
        cross_session_block = "\n\nPAST SESSION MEMORY:\n"
        for m in past_context:
            cross_session_block += f"- [{m['timestamp'][:10]}] {m['content'][:300]}\n"

    # ── Step 8: Build system prompt ────────────────────────────────────────
    yield {"agent": "writer", "status": "thinking", "message": "Synthesizing answer..."}

    messages_for_llm = history + [{"role": "user", "content": query}]
    persona_instruction = PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["researcher"])

    system = f"""You are an expert AI Research Assistant with vision capabilities.
Style: {persona_instruction}
Use the sources and any provided figures/diagrams to answer accurately.
Always cite sources as [Source N]. When referencing figures, describe what you see.
Be thorough, structured, and clear.

{profile_block}

IMPORTANT MEMORY INSTRUCTIONS:
- If the user asks about themselves (name, field, expertise, preferences), check the
  USER PROFILE above first and answer from it — NEVER say you don't know if it's there.
- If they share new information about themselves, acknowledge it naturally.
- Address the user by name if known and it feels natural.

CODE EXECUTION:
- When the user asks you to run, calculate, plot, or analyse data, write the code
  in a ```python or ```javascript block.
- Code is automatically executed and output is shown to the user.
- Variables from earlier cells persist across calls in the same session.
- For plots, use matplotlib. Do NOT call plt.show() — figures are captured automatically.

SOURCES:
{context}{session_memory_block}{cross_session_block}"""

    # ── Step 9: Save user message ──────────────────────────────────────────
    add_message(session_id, "user", query)
    lt_save(session_id=session_id, role="user", content=query, persona=persona, model_id=model_id)

    full_response = ""
    actual_model_used = model_id

    try:
        chunks, actual_model_used = await asyncio.to_thread(
            get_stream_chunks_with_fallback,
            model_id,
            messages_for_llm,
            system,
            images,
        )

        if actual_model_used != model_id:
            yield {
                "agent": "orchestrator",
                "status": "thinking",
                "message": f"⚠️ Switched to fallback model: `{actual_model_used}`",
            }

        for text in chunks:
            if text:
                full_response += text
                yield {"agent": "writer", "status": "streaming", "message": text}

    except Exception as exc:
        error_str = str(exc)
        print(f"[orchestrator] ✖ ALL FALLBACKS EXHAUSTED: {error_str}")
        clean_msg = (
            "⚠️ **All available models are currently unavailable.**\n\n"
            "Please try again in a few minutes, or check your API keys in `.env`.\n\n"
            f"Last error: `{error_str[:200]}`"
        )
        full_response = clean_msg
        yield {"agent": "writer", "status": "streaming", "message": clean_msg}

    # ── Step 10: Auto-execute code blocks ──────────────────────────────────
    has_code = bool(CODE_BLOCK_RE.search(full_response))
    code_results: list[dict] = []

    if has_code:
        yield {"agent": "writer", "status": "thinking", "message": "⚙️ Executing code blocks..."}

        full_response, code_results = await auto_execute_code_blocks(full_response, session_id)

        for res in code_results:
            if res.get("stdout") or res.get("result") or res.get("error"):
                yield {
                    "agent": "writer",
                    "status": "streaming",
                    "message": f"\n\n{format_execution_result(res)}",
                }

            # Send plots as special tagged messages (frontend detects [PLOT_B64] prefix)
            for b64 in res.get("plots", []):
                yield {"agent": "writer", "status": "streaming", "message": f"[PLOT_B64]{b64}"}

            if res.get("install_msg"):
                print(f"[orchestrator] 📦 {res['install_msg']}")

        total_plots = sum(len(r.get("plots", [])) for r in code_results)
        if total_plots:
            yield {
                "agent": "vision",
                "status": "thinking",
                "message": f"📊 {total_plots} plot(s) generated",
            }

    # ── Step 11: Save assistant response ───────────────────────────────────
    add_message(session_id, "assistant", full_response)
    lt_save(
        session_id=session_id,
        role="assistant",
        content=full_response,
        persona=persona,
        model_id=actual_model_used,
        metadata={
            "sources":         [s.get("source") for s in all_sources[:5]],
            "image_count":     len(images),
            "fallback_used":   actual_model_used != model_id,
            "original_model":  model_id,
            "code_executed":   len(code_results),
            "plots_generated": sum(len(r.get("plots", [])) for r in code_results),
        },
    )

    image_previews = [
        {
            "filename":   img.get("filename", "unknown"),
            "page":       img.get("page", 0),
            "media_type": img.get("media_type", "image/png"),
            "b64":        img["b64"][:100],
        }
        for img in images[:5]
    ]

    yield {
        "agent": "orchestrator",
        "status": "done",
        "message": "Complete",
        "sources":    all_sources,
        "images":     image_previews,
        "model_used": actual_model_used,
    }