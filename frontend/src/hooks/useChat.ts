import { useChatStore } from "../store/chatStore"
import type { Message } from "../types"
import { API } from "../utils/api"

export const MODELS = [
  { id: "groq/llama-3.3-70b-versatile",                   label: "Llama 3.3 70B",        provider: "Groq" },
  { id: "groq/meta-llama/llama-4-scout-17b-16e-instruct", label: "Llama 4 Scout Vision", provider: "Groq" },
  { id: "gemini/gemini-1.5-flash",                        label: "Gemini 1.5 Flash",     provider: "Google" },
  { id: "mistral/mistral-small-latest",                   label: "Mistral Small",        provider: "Mistral" },
]

export function useChat() {
  const store = useChatStore()

  const streamResponse = async (body: object) => {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split("\n")
      buffer = lines.pop() ?? ""

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        const data = line.slice(6).trim()
        if (data === "[DONE]") break
        try {
          const event = JSON.parse(data)
          store.setAgentEvent(event)
          if (event.status === "streaming") {
            store.appendToLastAssistant(event.message ?? "")
          }
          if (event.status === "done" && event.sources) {
            store.finalizeLastAssistant(event.sources)
          }
        } catch {}
      }
    }
  }

  const sendMessage = async (query: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      timestamp: new Date(),
    }
    store.addMessage(userMsg)
    store.setLoading(true)
    store.clearEvents()
    store.addMessage({
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
    })

    try {
      await streamResponse({
        query,
        session_id: store.currentSessionId,
        conversation_history: [],
        model_id: store.selectedModel,
        persona: store.persona,
      })
    } catch {
      store.updateLastAssistant("Error connecting to backend.")
    } finally {
      store.setLoading(false)
    }
  }

  const sendMessageWithImage = async (query: string, imageB64: string, mediaType: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: query,
      image: { b64: imageB64, mediaType },
      timestamp: new Date(),
    }
    store.addMessage(userMsg)
    store.setLoading(true)
    store.clearEvents()
    store.addMessage({
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
    })

    try {
      await streamResponse({
        query,
        session_id: store.currentSessionId,
        conversation_history: [],
        model_id: store.selectedModel,
        image_b64: imageB64,
        image_media_type: mediaType,
        persona: store.persona,
      })
    } catch {
      store.updateLastAssistant("Error connecting to backend.")
    } finally {
      store.setLoading(false)
    }
  }

  const uploadFile = async (file: File) => {
    const form = new FormData()
    form.append("file", file)
    const res = await fetch(`${API}/upload`, { method: "POST", body: form })
    return res.json()
  }

  return {
    sendMessage,
    sendMessageWithImage,
    uploadFile,
    models: MODELS,
    ...store,
  }
}