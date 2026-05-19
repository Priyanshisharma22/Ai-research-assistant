import { create } from "zustand"
import type { Message, AgentEvent, Source } from "../types"

// ---------------------------------------------------------------------------
// Persistent session ID — survives page refreshes via localStorage.
// Previously: crypto.randomUUID() was called fresh on every page load,
// creating a new session each time and making the backend "forget" the user.
// ---------------------------------------------------------------------------
const SESSION_KEY = "research_assistant_session_id"

function getOrCreateSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

interface ChatStore {
  messages: Message[]
  agentEvents: AgentEvent[]
  isLoading: boolean
  currentSessionId: string
  selectedModel: string
  persona: string

  addMessage: (msg: Message) => void
  updateLastAssistant: (content: string) => void
  appendToLastAssistant: (content: string) => void
  finalizeLastAssistant: (sources: Source[]) => void
  clearMessages: () => void

  setAgentEvent: (event: AgentEvent) => void
  clearEvents: () => void

  setLoading: (val: boolean) => void
  setSessionId: (id: string) => void
  setSelectedModel: (model: string) => void
  setPersona: (persona: string) => void

  // New: start a brand-new conversation (e.g. "New Chat" button)
  newSession: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  agentEvents: [],
  isLoading: false,

  // FIX: read from localStorage instead of generating a fresh UUID every time
  currentSessionId: getOrCreateSessionId(),

  selectedModel: "groq/llama-3.3-70b-versatile",
  persona: "researcher",

  addMessage: (msg) =>
    set((state) => ({ messages: [...state.messages, msg] })),

  updateLastAssistant: (content) =>
    set((state) => {
      const messages = [...state.messages]
      const idx = messages.findLastIndex((m) => m.role === "assistant")
      if (idx === -1) return {}
      messages[idx] = { ...messages[idx], content }
      return { messages }
    }),

  appendToLastAssistant: (content) =>
    set((state) => {
      const messages = [...state.messages]
      const idx = messages.findLastIndex((m) => m.role === "assistant")
      if (idx === -1) return {}
      messages[idx] = {
        ...messages[idx],
        content: messages[idx].content + content,
      }
      return { messages }
    }),

  finalizeLastAssistant: (sources) =>
    set((state) => {
      const messages = [...state.messages]
      const idx = messages.findLastIndex((m) => m.role === "assistant")
      if (idx === -1) return {}
      messages[idx] = { ...messages[idx], sources }
      return { messages }
    }),

  clearMessages: () => set({ messages: [] }),

  setAgentEvent: (event) =>
    set((state) => {
      const stamped: AgentEvent = { ...event, _ts: Date.now() }
      const existing = state.agentEvents
      const idx = existing.findIndex((e) => e.agent === event.agent)
      if (idx !== -1) {
        const next = [...existing]
        next[idx] = stamped
        return { agentEvents: next }
      }
      if (existing.length === 0) {
        return { agentEvents: [{ ...stamped, _ts: Date.now() }] }
      }
      return { agentEvents: [...existing, stamped] }
    }),

  clearEvents: () => set({ agentEvents: [] }),

  setLoading: (val) => set({ isLoading: val }),
  setSessionId: (id) => set({ currentSessionId: id }),
  setSelectedModel: (model) => set({ selectedModel: model }),
  setPersona: (persona) => set({ persona }),

  // Generates a new session ID, persists it, and clears the chat
  newSession: () => {
    const id = crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
    set({ currentSessionId: id, messages: [], agentEvents: [] })
  },
}))