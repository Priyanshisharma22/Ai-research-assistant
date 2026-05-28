const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? "https://ai-research-assistant-gvtn.onrender.com";

// ── Wake up Render (free tier sleeps after 15 min) ────────────────────────────
export async function wakeBackend(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/health`);
  } catch {
    // silently ignore — backend may still be booting
  }
}

// ── Generic request helper ────────────────────────────────────────────────────
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Request failed: ${res.status} ${res.statusText}`);
  }

  return res.json() as Promise<T>;
}

// ── Health check ──────────────────────────────────────────────────────────────
export async function checkHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/health");
}

// ── Chat ──────────────────────────────────────────────────────────────────────
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  persona?: string;
  model?: string;
  session_id?: string;
}

export interface Source {
  title: string;
  url?: string;
  snippet?: string;
}

export interface ChatResponse {
  response: string;
  session_id?: string;
  sources?: Source[];
}

export async function sendChatMessage(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── PDF Upload ────────────────────────────────────────────────────────────────
export interface UploadResponse {
  message: string;
  filename: string;
  chunks?: number;
}

export async function uploadPDF(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  // ⚠️ Do NOT set Content-Type manually — browser sets multipart boundary
  const res = await fetch(`${API_BASE_URL}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Upload failed: ${res.status} ${res.statusText}`);
  }

  return res.json() as Promise<UploadResponse>;
}