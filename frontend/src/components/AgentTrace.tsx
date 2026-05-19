import type { AgentEvent } from "../types"

const AGENT_META: Record<string, { label: string; bg: string; color: string }> = {
  orchestrator: { label: "Orchestrator", bg: "#EEEDFE", color: "#3C3489" },
  retrieval:    { label: "Retrieval",    bg: "#E1F5EE", color: "#085041" },
  web_search:   { label: "Web Search",  bg: "#E6F1FB", color: "#0C447C" },
  writer:       { label: "Writer",      bg: "#EAF3DE", color: "#27500A" },
  critic:       { label: "Critic",      bg: "#FAECE7", color: "#712B13" },
}

const DOT_COLOR: Record<AgentEvent["status"], string> = {
  thinking:  "#EF9F27",
  streaming: "#378ADD",
  done:      "#1D9E75",
  error:     "#E24B4A",
}

function StatusDot({ status }: { status: AgentEvent["status"] }) {
  const animated = status === "thinking" || status === "streaming"
  return (
    <span style={{
      display: "inline-block",
      width: 8, height: 8,
      borderRadius: "50%",
      background: DOT_COLOR[status] ?? "#B4B2A9",
      flexShrink: 0,
      marginTop: 5,
      animation: animated ? "atrace-pulse 1s infinite" : undefined,
    }} />
  )
}

export default function AgentTrace({ events }: { events: AgentEvent[] }) {
  if (!events.length) return null

  const isLive = events.some(e => e.status === "thinking" || e.status === "streaming")
  const t0 = (events[0] as any)._ts as number | undefined

  return (
    <div style={{
      border: "0.5px solid #2a2a3a",
      borderRadius: 10,
      background: "#0d0d18",
      marginBottom: 12,
      overflow: "hidden",
      fontSize: 13,
    }}>
      <style>{`
        @keyframes atrace-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        @keyframes atrace-spin  { to{transform:rotate(360deg)} }
        .atrace-cursor { display:inline-block; animation:atrace-pulse .8s infinite; margin-left:2px }
      `}</style>

      {/* header */}
      <div style={{
        padding: "7px 14px",
        borderBottom: "0.5px solid #2a2a3a",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{ fontSize: 11, fontWeight: 500, color: "#666",
                       textTransform: "uppercase", letterSpacing: "0.05em", flex: 1 }}>
          Agent trace
        </span>
        {isLive && (
          <span style={{
            width: 10, height: 10, borderRadius: "50%",
            border: "1.5px solid #333", borderTopColor: "#EF9F27",
            display: "inline-block",
            animation: "atrace-spin .7s linear infinite",
          }} />
        )}
      </div>

      {/* rows */}
      {events.map((ev, i) => {
        const meta = AGENT_META[ev.agent] ?? { label: ev.agent, bg: "#2a2a3a", color: "#888" }
        const isLast = i === events.length - 1
        const elapsed = t0 ? (((ev as any)._ts - t0) / 1000).toFixed(1) : null

        return (
          <div key={i} style={{
            display: "flex", alignItems: "flex-start", gap: 10,
            padding: "8px 14px",
            borderBottom: isLast ? "none" : "0.5px solid #1e1e2e",
          }}>
            {/* dot + connector */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 5 }}>
              <StatusDot status={ev.status} />
              {!isLast && (
                <div style={{ width: 1, flex: 1, minHeight: 10, background: "#2a2a3a", marginTop: 3 }} />
              )}
            </div>

            {/* content */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                <span style={{ fontSize: 11, fontWeight: 500, color: "#888" }}>
                  {meta.label}
                </span>
                <span style={{
                  fontSize: 10, padding: "1px 7px", borderRadius: 20, fontWeight: 500,
                  background: meta.bg + "22",   // 13% opacity so it works on dark bg
                  color: meta.color,
                  border: `0.5px solid ${meta.color}44`,
                }}>
                  {ev.agent}
                </span>
              </div>

              <div style={{
                color: ev.status === "thinking" || ev.status === "streaming" ? "#555" : "#ccc",
                lineHeight: 1.5,
              }}>
                {ev.status === "streaming" ? ev.message : ev.message}
                {ev.status === "streaming" && <span className="atrace-cursor">▍</span>}
              </div>

              {ev.sources?.length ? (
                <div style={{ fontSize: 11, color: "#555", fontFamily: "monospace", marginTop: 3 }}>
                  → {ev.sources.length} source{ev.sources.length !== 1 ? "s" : ""} (top: {ev.sources[0].score.toFixed(2)})
                </div>
              ) : null}
            </div>

            {elapsed && (
              <div style={{ fontSize: 11, color: "#444", flexShrink: 0, marginTop: 4 }}>
                {elapsed}s
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}