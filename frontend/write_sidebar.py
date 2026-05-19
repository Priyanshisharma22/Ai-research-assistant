content = """import { useRef, useState, useEffect } from "react"
import { useChat } from "../hooks/useChat"
import PersonaSwitcher from "./PersonaSwitcher"

const API = "http://localhost:8000/api"

interface DocSummary {
  filename: string
  summary: string
  chunks: number
}

type UploadStatus = "idle" | "reading" | "summarizing" | "indexing" | "done" | "error"

export default function Sidebar() {
  const ref = useRef<HTMLInputElement>(null)
  const { persona, setPersona } = useChat()
  const [status, setStatus] = useState<UploadStatus>("idle")
  const [progress, setProgress] = useState("")
  const [summaries, setSummaries] = useState<DocSummary[]>([])
  const [lastSummary, setLastSummary] = useState<DocSummary | null>(null)

  useEffect(() => {
    fetch(API + "/summaries")
      .then(r => r.json())
      .then(data => setSummaries(Object.values(data) as DocSummary[]))
      .catch(() => {})
  }, [])

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ""
    setStatus("reading")
    setProgress("Reading file...")
    setLastSummary(null)
    const form = new FormData()
    form.append("file", file)
    try {
      const res = await fetch(API + "/upload", { method: "POST", body: form })
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const lines = decoder.decode(value).split("\\n").filter(l => l.startsWith("data: "))
        for (const line of lines) {
          const data = line.replace("data: ", "").trim()
          if (data === "[DONE]") break
          try {
            const event = JSON.parse(data)
            setStatus(event.status)
            setProgress(event.message)
            if (event.status === "done") {
              const doc = { filename: event.filename, summary: event.summary, chunks: event.chunks }
              setLastSummary(doc)
              setSummaries(prev => [doc, ...prev.filter(d => d.filename !== event.filename)])
            }
          } catch(err) {}
        }
      }
    } catch(err) {
      setStatus("error")
      setProgress("Upload failed. Is the backend running?")
    }
  }

  const statusColor: Record<UploadStatus, string> = {
    idle: "#555", reading: "#a78bfa", summarizing: "#f59e0b",
    indexing: "#34d399", done: "#6ee7b7", error: "#f87171"
  }

  const statusLabel: Record<UploadStatus, string> = {
    idle: "", reading: "[reading]", summarizing: "[summarizing]",
    indexing: "[indexing]", done: "[done]", error: "[error]"
  }

  return (
    <div style={{ width: 240, background: "#0d0d1a", borderRight: "1px solid #1e1e2e", display: "flex", flexDirection: "column", padding: 16, gap: 4, overflowY: "auto", height: "100vh" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: 18, color: "#a78bfa" }}>AI</span>
        <span style={{ fontWeight: 600, color: "#e2e8f0", fontSize: 15 }}>ResearchAI</span>
      </div>

      <PersonaSwitcher />

      <div style={{ borderTop: "1px solid #1e1e2e", paddingTop: 12, marginTop: 8 }}>
        <p style={{ fontSize: 11, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 8px" }}>
          Knowledge Base
        </p>
        <button
          onClick={() => ref.current?.click()}
          disabled={status === "reading" || status === "summarizing" || status === "indexing"}
          style={{ width: "100%", padding: "10px", background: "#1a1a2e", border: "1px dashed #3a3a5a", borderRadius: 8, color: "#a78bfa", cursor: "pointer", fontSize: 13, opacity: status === "idle" || status === "done" || status === "error" ? 1 : 0.6 }}
        >
          + Upload PDF
        </button>
        <input ref={ref} type="file" accept=".pdf" style={{ display: "none" }} onChange={handleUpload} />

        {status !== "idle" && (
          <div style={{ marginTop: 8, padding: "8px 10px", background: "#111", borderRadius: 8, border: "1px solid #1e1e2e" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: status === "done" ? 6 : 0 }}>
              <span style={{ fontSize: 11, color: statusColor[status], fontWeight: 600 }}>{statusLabel[status]}</span>
              <span style={{ fontSize: 11, color: statusColor[status] }}>{progress}</span>
            </div>
            {status === "done" && lastSummary && (
              <div>
                <p style={{ fontSize: 10, color: "#666", margin: "4px 0 2px", textTransform: "uppercase" }}>AI Summary</p>
                <p style={{ fontSize: 11, color: "#aaa", lineHeight: 1.5, margin: 0 }}>{lastSummary.summary}</p>
                <p style={{ fontSize: 10, color: "#555", marginTop: 4 }}>{lastSummary.chunks} chunks indexed</p>
              </div>
            )}
          </div>
        )}

        {summaries.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <p style={{ fontSize: 10, color: "#444", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 6px" }}>
              Indexed Docs ({summaries.length})
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {summaries.map((doc, i) => (
                <div key={i} style={{ background: "#111", border: "1px solid #1e1e2e", borderRadius: 8, padding: "8px 10px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
                    <span style={{ fontSize: 11, color: "#a78bfa", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140 }}>
                      {doc.filename}
                    </span>
                    <span style={{ fontSize: 9, color: "#444", background: "#0d0d1a", padding: "1px 5px", borderRadius: 4 }}>
                      {doc.chunks}
                    </span>
                  </div>
                  <p style={{ fontSize: 10, color: "#666", margin: 0, lineHeight: 1.4 }}>{doc.summary}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ fontSize: 11, color: "#333", textAlign: "center", paddingTop: 8 }}>powered by Claude</div>
    </div>
  )
}
"""

with open('src/components/Sidebar.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print("Sidebar.tsx written OK")