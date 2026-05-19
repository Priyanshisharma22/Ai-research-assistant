import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { Message } from "../types"
import CitationCard from "./CitationCard"

export default function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user"
  return (
    <div style={{
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: 16,
      padding: "0 16px",
    }}>
      {!isUser && (
        <div style={{
          width: 32,
          height: 32,
          borderRadius: "50%",
          background: "linear-gradient(135deg,#7c3aed,#a78bfa)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 14,
          marginRight: 10,
          flexShrink: 0,
          marginTop: 4,
        }}>
          ✦
        </div>
      )}
      <div style={{ maxWidth: "78%", minWidth: 60 }}>

        {/* Show attached image if present */}
        {isUser && msg.image && (
          <div style={{ marginBottom: 8, display: "flex", justifyContent: "flex-end" }}>
            <img
              src={`data:${msg.image.mediaType};base64,${msg.image.b64}`}
              alt="attached"
              style={{
                maxWidth: 260,
                maxHeight: 180,
                borderRadius: 12,
                border: "1px solid #3a3a5a",
                objectFit: "cover",
              }}
            />
          </div>
        )}

        {/* Show PDF upload card if present */}
        {isUser && msg.pdfName && (
          <div style={{
            marginBottom: 8,
            padding: "10px 14px",
            background: "#1a1a2e",
            border: "1px solid #3a3a5a",
            borderRadius: 12,
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}>
            <span style={{ fontSize: 24 }}>📄</span>
            <div>
              <p style={{ margin: 0, fontSize: 13, color: "#e2e8f0", fontWeight: 500 }}>{msg.pdfName}</p>
              <p style={{ margin: 0, fontSize: 11, color: "#555" }}>Added to knowledge base</p>
            </div>
          </div>
        )}

        <div style={{
          background: isUser ? "#7c3aed" : "#16162a",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          padding: "12px 16px",
          border: isUser ? "none" : "1px solid #2a2a3a",
          color: "#e2e8f0",
          fontSize: 14,
          lineHeight: 1.7,
        }}>
          {isUser ? (
            <p style={{ margin: 0 }}>{msg.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code: ({ children }) => (
                  <code style={{
                    background: "#0d0d1a",
                    padding: "2px 6px",
                    borderRadius: 4,
                    fontSize: 12,
                    color: "#a78bfa",
                  }}>
                    {children}
                  </code>
                ),
                pre: ({ children }) => (
                  <pre style={{
                    background: "#0d0d1a",
                    padding: 12,
                    borderRadius: 8,
                    overflow: "auto",
                    fontSize: 12,
                  }}>
                    {children}
                  </pre>
                ),
                p: ({ children }) => <p style={{ margin: "0 0 8px" }}>{children}</p>,
              }}
            >
              {msg.content || "…"}
            </ReactMarkdown>
          )}
        </div>

        {!isUser && msg.sources && msg.sources.length > 0 && (
          <CitationCard sources={msg.sources} />
        )}
      </div>
    </div>
  )
}