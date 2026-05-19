import { useEffect, useRef, useState } from "react"
import { useChat } from "../hooks/useChat"
import MessageBubble from "./MessageBubble"
import AgentTrace from "./AgentTrace"
import type { Message } from "../types"

export default function ChatWindow() {
  const { sendMessage, sendMessageWithImage, isLoading, agentEvents, messages, selectedModel } = useChat()
  const [input, setInput] = useState("")
  const [pastedImage, setPastedImage] = useState<{ b64: string; mediaType: string } | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const imageRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, agentEvents])

  const handleSend = () => {
    if (!input.trim() || isLoading) return
    if (pastedImage) {
      sendMessageWithImage(input.trim(), pastedImage.b64, pastedImage.mediaType)
      setPastedImage(null)
    } else {
      sendMessage(input.trim())
    }
    setInput("")
  }

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      const b64 = result.split(",")[1]
      const mediaType = file.type
      setPastedImage({ b64, mediaType })
    }
    reader.readAsDataURL(file)
  }

  const isVisionModel = selectedModel.startsWith("anthropic/") || selectedModel.startsWith("openai/")

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#0a0a15", height: "100vh" }}>
      {/* Header */}
      <div style={{ padding: "14px 20px", borderBottom: "1px solid #1e1e2e", background: "#0d0d1a" }}>
        <p style={{ margin: 0, fontSize: 14, color: "#e2e8f0", fontWeight: 500 }}>AI Research Assistant</p>
        <p style={{ margin: 0, fontSize: 11, color: "#555" }}>RAG · Web Search · Multi-Agent · Memory · Vision</p>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 0" }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", marginTop: 80, color: "#444" }}>
            <p style={{ fontSize: 32, marginBottom: 12 }}>✦</p>
            <p style={{ fontSize: 16, color: "#666" }}>Ask anything. I will search your docs and the web.</p>
            <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 20, flexWrap: "wrap" }}>
              {[
                "Explain transformer architecture",
                "Describe the figures in my PDF",
                "Summarize my uploaded paper",
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  style={{
                    background: "#16162a",
                    border: "1px solid #2a2a3a",
                    borderRadius: 20,
                    padding: "8px 14px",
                    color: "#a78bfa",
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {isLoading && agentEvents.length > 0 && <AgentTrace events={agentEvents} />}
        {messages.map((m: Message) => <MessageBubble key={m.id} msg={m} />)}
        <div ref={bottomRef} />
      </div>

      {/* Pasted image preview */}
      {pastedImage && (
        <div style={{
          padding: "8px 16px",
          background: "#0d0d1a",
          borderTop: "1px solid #1e1e2e",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <img
            src={`data:${pastedImage.mediaType};base64,${pastedImage.b64}`}
            alt="attached"
            style={{ height: 60, borderRadius: 6, border: "1px solid #3a3a5a", objectFit: "cover" }}
          />
          <div style={{ flex: 1 }}>
            <p style={{ margin: 0, fontSize: 12, color: "#a78bfa" }}>Image attached</p>
            <p style={{ margin: 0, fontSize: 11, color: "#555" }}>Will be sent with your next message</p>
          </div>
          <button
            onClick={() => setPastedImage(null)}
            style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 18 }}
          >
            ×
          </button>
        </div>
      )}

      {/* Input bar */}
      <div style={{
        padding: "12px 16px",
        borderTop: "1px solid #1e1e2e",
        background: "#0d0d1a",
        display: "flex",
        gap: 10,
        alignItems: "flex-end",
      }}>
        {/* Image attach button — only shown for vision models */}
        {isVisionModel && (
          <>
            <button
              onClick={() => imageRef.current?.click()}
              title="Attach image"
              style={{
                background: "#1a1a2e",
                border: "1px solid #3a3a5a",
                borderRadius: 10,
                padding: "10px 12px",
                color: "#a78bfa",
                cursor: "pointer",
                fontSize: 16,
                lineHeight: 1,
              }}
            >
              🖼
            </button>
            <input
              ref={imageRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={handleImageUpload}
            />
          </>
        )}

        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder={
            isVisionModel
              ? "Ask about figures, diagrams, or any research question..."
              : "Ask a research question..."
          }
          rows={2}
          style={{
            flex: 1,
            background: "#16162a",
            border: "1px solid #2a2a3a",
            borderRadius: 12,
            padding: "10px 14px",
            color: "#e2e8f0",
            fontSize: 14,
            resize: "none",
            outline: "none",
            fontFamily: "inherit",
            lineHeight: 1.5,
          }}
        />
        <button
          onClick={handleSend}
          disabled={isLoading || !input.trim()}
          style={{
            background: isLoading ? "#3a2a5a" : "#7c3aed",
            border: "none",
            borderRadius: 12,
            padding: "12px 18px",
            color: "white",
            cursor: isLoading ? "not-allowed" : "pointer",
            fontSize: 16,
          }}
        >
          {isLoading ? "..." : "Send"}
        </button>
      </div>
    </div>
  )
}