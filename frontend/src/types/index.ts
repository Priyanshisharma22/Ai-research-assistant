export interface Source {
  content: string
  source: string
  score: number
}

export interface AgentEvent {
  agent: string
  status: "thinking" | "streaming" | "done" | "error"
  message: string
  sources?: Source[]
  _ts?: number
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: Source[]
  image?: { b64: string; mediaType: string }
  pdfName?: string
  timestamp: Date
}