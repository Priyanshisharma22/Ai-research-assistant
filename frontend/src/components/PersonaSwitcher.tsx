import { useChat } from "../hooks/useChat"

const PERSONAS = [
  { id: "student",    emoji: "🎓", label: "Student",    desc: "Simple & clear" },
  { id: "researcher", emoji: "🔬", label: "Researcher", desc: "Technical depth" },
  { id: "executive",  emoji: "💼", label: "Executive",  desc: "Concise insights" },
  { id: "creative",   emoji: "🎨", label: "Creative",   desc: "Storytelling" },
]

export default function PersonaSwitcher() {
  const { persona, setPersona } = useChat()

  return (
    <div style={{ padding: "12px 0" }}>
      <p style={{
        fontSize: 11,
        color: "#555",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        margin: "0 0 8px",
      }}>
        Response Style
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {PERSONAS.map((p) => (
          <button
            key={p.id}
            onClick={() => setPersona(p.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "9px 12px",
              borderRadius: 10,
              cursor: "pointer",
              border: persona === p.id ? "1px solid #7c3aed" : "1px solid #1e1e2e",
              background: persona === p.id ? "#1e1030" : "transparent",
              textAlign: "left",
              transition: "all 0.15s",
            }}
          >
            <span style={{ fontSize: 16 }}>{p.emoji}</span>
            <div>
              <p style={{
                margin: 0,
                fontSize: 12,
                fontWeight: 500,
                color: persona === p.id ? "#a78bfa" : "#ccc",
              }}>
                {p.label}
              </p>
              <p style={{ margin: 0, fontSize: 10, color: "#555" }}>{p.desc}</p>
            </div>
            {persona === p.id && (
              <span style={{
                marginLeft: "auto",
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "#7c3aed",
              }} />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}