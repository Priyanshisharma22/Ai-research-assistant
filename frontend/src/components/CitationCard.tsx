import type { Source } from "../types"

export default function CitationCard({ sources }: { sources: Source[] }) {
  if (!sources?.length) return null
  return (
    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
      <p style={{ fontSize: 11, color: "#666", margin: 0, textTransform: "uppercase", letterSpacing: "0.05em" }}>Sources</p>
      {sources.slice(0, 4).map((s, i) => (
        <div key={i} style={{ background: "#1a1a2e", border: "1px solid #2a2a3a", borderRadius: 8, padding: "8px 12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span style={{ fontSize: 11, color: "#a78bfa", fontWeight: 500 }}>
              {s.source.startsWith("http") ? new URL(s.source).hostname : s.source}
            </span>
            <span style={{ fontSize: 10, color: "#555", background: "#111", padding: "1px 6px", borderRadius: 4 }}>
              {Math.round((s.score || 0) * 100)}%
            </span>
          </div>
          <p style={{ fontSize: 12, color: "#888", margin: 0, lineHeight: 1.5, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
            {s.content}
          </p>
        </div>
      ))}
    </div>
  )
}
