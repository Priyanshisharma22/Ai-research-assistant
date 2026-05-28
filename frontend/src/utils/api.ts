// frontend/src/utils/api.ts

const BASE =
  import.meta.env.VITE_API_URL ?? "https://ai-research-assistant-gvtn.onrender.com"

export const API = BASE + "/api"

// ── Wake up Render (free tier sleeps after 15 min) ────────────────────────────
export async function wakeBackend(): Promise<void> {
  try {
    await fetch(`${BASE}/health`)
  } catch {
    // silently ignore — backend may still be booting
  }
}

// ── Generic request helper ────────────────────────────────────────────────────
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  })

  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(text || `Request failed: ${res.status} ${res.statusText}`)
  }

  return res.json() as Promise<T>
}

// ── Health check ──────────────────────────────────────────────────────────────
export async function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health")
}

// ── Chat ──────────────────────────────────────────────────────────────────────
export interface ChatMessage {
  role: "user" | "assistant"
  content: string
}

export interface ChatRequest {
  messages: ChatMessage[]
  persona?: string
  model?: string
  session_id?: string
}

export interface Source {
  title: string
  url?: string
  snippet?: string
}

export interface ChatResponse {
  response: string
  session_id?: string
  sources?: Source[]
}

export async function sendChatMessage(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

// ── PDF Upload (SSE streaming) ────────────────────────────────────────────────
export interface UploadProgress {
  status: "reading" | "summarizing" | "indexing" | "done"
  message: string
  summary?: string
  filename?: string
  chunks?: number
}

export async function uploadPDF(
  file: File,
  onProgress?: (update: UploadProgress) => void
): Promise<UploadProgress> {
  const formData = new FormData()
  formData.append("file", file)

  const res = await fetch(`${API}/upload`, {
    method: "POST",
    body: formData,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(text || `Upload failed: ${res.status} ${res.statusText}`)
  }

  // Backend returns text/event-stream — read it chunk by chunk
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let finalResult: UploadProgress = { status: "reading", message: "Starting..." }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const chunk = decoder.decode(value, { stream: true })
    const lines = chunk.split("\n")

    for (const line of lines) {
      if (line.startsWith("data: ") && line.trim() !== "data: [DONE]") {
        try {
          const data: UploadProgress = JSON.parse(line.slice(6))
          onProgress?.(data)
          if (data.status === "done") finalResult = data
        } catch {
          // skip malformed lines
        }
      }
    }
  }

  return finalResult
}