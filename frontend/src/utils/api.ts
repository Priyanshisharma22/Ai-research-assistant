// frontend/src/utils/api.ts

const BASE =
  import.meta.env.VITE_API_URL ?? "https://ai-research-assistant-gvtn.onrender.com"

export const API = BASE + "/api"

// ── Wake up Render ────────────────────────────────────────────────────────────
export async function wakeBackend(): Promise<void> {
  try {
    await fetch(`${BASE}/health`)
  } catch {
    // silently ignore
  }
}

// ── Generic request helper ────────────────────────────────────────────────────
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {   // ✅ use API (with /api)
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
  return request<{ status: string }>("/health")  // → BASE/api/health
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
  return request<ChatResponse>("/chat", {    // ✅ just /chat, not /api/chat
    method: "POST",
    body: JSON.stringify(payload),
  })
}

// ── PDF Upload ────────────────────────────────────────────────────────────────
export interface UploadResponse {
  message: string
  filename: string
  chunks?: number
}

export async function uploadPDF(file: File): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("file", file)

  const res = await fetch(`${API}/upload`, {   // ✅ API + /upload
    method: "POST",
    body: formData,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(text || `Upload failed: ${res.status} ${res.statusText}`)
  }

  return res.json() as Promise<UploadResponse>
}