import { useState } from "react"

const API = "http://localhost:8000/api"

interface ProfileForm {
  name: string
  role: string
  field: string
  organisation: string
  bio: string
  topics: string[]
  response_style: string[]
  technical_depth: string
  primary_goal: string
}

interface ProfilePageProps {
  onBack?: () => void
}

const TOPIC_OPTIONS = [
  "Machine learning", "NLP", "Computer vision", "Reinforcement learning",
  "Data science", "Robotics", "Bioinformatics", "Finance", "Physics", "Climate",
  "Quantum computing", "Cybersecurity", "Neuroscience", "Economics",
]

const STYLE_OPTIONS = [
  "Concise", "Detailed", "Bullet points", "Prose",
  "With examples", "With citations", "Include code", "Step by step",
]

const DEPTH_LABELS: Record<number, string> = {
  1: "Beginner — plain language, no jargon",
  2: "Basic — some technical terms explained",
  3: "Intermediate — assumes familiarity with fundamentals",
  4: "Advanced — technical depth, skip basics",
  5: "Expert — assume deep domain expertise",
}

const GOAL_OPTIONS = [
  { value: "", label: "Select a goal…" },
  { value: "research papers", label: "Reading & understanding research papers" },
  { value: "thesis / dissertation", label: "Writing a thesis or dissertation" },
  { value: "build projects", label: "Building ML / software projects" },
  { value: "literature review", label: "Conducting a literature review" },
  { value: "stay updated", label: "Staying updated in my field" },
  { value: "interview prep", label: "Interview / exam preparation" },
  { value: "general learning", label: "General learning" },
]

export default function ProfilePage({ onBack }: ProfilePageProps) {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")
  const [depth, setDepth] = useState(3)

  const [form, setForm] = useState<ProfileForm>({
    name: "",
    role: "",
    field: "",
    organisation: "",
    bio: "",
    topics: [],
    response_style: ["Detailed"],
    technical_depth: DEPTH_LABELS[3],
    primary_goal: "",
  })

  const initials = form.name
    ? form.name.split(" ").map((p: string) => p[0]?.toUpperCase()).filter(Boolean).slice(0, 2).join("")
    : null

  const setField = (key: keyof ProfileForm, value: string) =>
    setForm(prev => ({ ...prev, [key]: value }))

  const toggleChip = (key: "topics" | "response_style", val: string) => {
    setForm(prev => ({
      ...prev,
      [key]: prev[key].includes(val)
        ? prev[key].filter((v: string) => v !== val)
        : [...prev[key], val],
    }))
  }

  const handleDepth = (val: number) => {
    setDepth(val)
    setForm(prev => ({ ...prev, technical_depth: DEPTH_LABELS[val] }))
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      setError("Please enter your name.")
      return
    }
    setError("")
    setSaving(true)
    try {
      const res = await fetch(API + "/profile/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          name: form.name.trim(),
          role: form.role.trim(),
          field: form.field.trim(),
          organisation: form.organisation.trim(),
          bio: form.bio.trim(),
        }),
      })
      if (!res.ok) throw new Error("Save failed")
      setSaved(true)
      setTimeout(() => onBack?.(), 1200)
    } catch {
      setError("Could not save profile. Is the backend running?")
    } finally {
      setSaving(false)
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "9px 12px",
    fontSize: 14,
    background: "#0d0d1a",
    border: "1px solid #2a2a3a",
    borderRadius: 8,
    color: "#e2e8f0",
    outline: "none",
    fontFamily: "inherit",
    boxSizing: "border-box",
    marginBottom: 12,
  }

  const sectionStyle: React.CSSProperties = {
    background: "#111827",
    border: "1px solid #1e1e2e",
    borderRadius: 12,
    padding: "1.25rem",
    marginBottom: "1rem",
  }

  const sectionTitle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 500,
    color: "#555",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    margin: "0 0 14px",
  }

  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: 13,
    color: "#888",
    marginBottom: 6,
  }

  const chipStyle = (selected: boolean): React.CSSProperties => ({
    padding: "5px 13px",
    borderRadius: 20,
    border: "1px solid",
    borderColor: selected ? "#7f77dd" : "#2a2a3a",
    background: selected ? "#1e1a3a" : "#0d0d1a",
    color: selected ? "#a78bfa" : "#666",
    fontSize: 13,
    cursor: "pointer",
    transition: "all 0.15s",
    fontFamily: "inherit",
  })

  return (
    <div style={{ flex: 1, overflowY: "auto", background: "#0d0d1a" }}>
      <div style={{ maxWidth: 640, margin: "0 auto", padding: "2rem 1.25rem 4rem" }}>

        {/* Top bar */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 28 }}>
          <button
            onClick={onBack}
            style={{
              background: "none", border: "1px solid #2a2a3a", borderRadius: 8,
              color: "#666", fontSize: 13, cursor: "pointer",
              padding: "6px 12px", fontFamily: "inherit",
            }}
          >
            ← Back
          </button>
          <span style={{ fontSize: 18, fontWeight: 600, color: "#e2e8f0" }}>Edit profile</span>
        </div>

        {/* Avatar + name preview */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 28 }}>
          <div style={{
            width: 72, height: 72, borderRadius: "50%",
            background: initials ? "#1e1a3a" : "#1a1a2e",
            border: "2px dashed #3a3a5a",
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          }}>
            {initials
              ? <span style={{ fontSize: 22, fontWeight: 500, color: "#a78bfa" }}>{initials}</span>
              : <span style={{ fontSize: 22, color: "#333" }}>?</span>
            }
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 600, color: "#e2e8f0", minHeight: 28 }}>
              {form.name || "Your name"}
            </div>
            <div style={{ fontSize: 13, color: "#555", marginTop: 2 }}>
              {form.role && form.field
                ? `${form.role} · ${form.field}`
                : form.role || form.field || "ResearchAI will personalise every response using this"}
            </div>
          </div>
        </div>

        {/* ── Section 1: Basic info ── */}
        <div style={sectionStyle}>
          <p style={sectionTitle}>Basic info</p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={labelStyle}>Name *</label>
              <input
                style={inputStyle}
                placeholder="Priyanshi Sharma"
                value={form.name}
                onChange={e => setField("name", e.target.value)}
              />
            </div>
            <div>
              <label style={labelStyle}>Role / occupation</label>
              <input
                style={inputStyle}
                placeholder="B.Tech student"
                value={form.role}
                onChange={e => setField("role", e.target.value)}
              />
            </div>
          </div>

          <label style={labelStyle}>Field or domain</label>
          <input
            style={inputStyle}
            placeholder="Machine learning, NLP, computer vision…"
            value={form.field}
            onChange={e => setField("field", e.target.value)}
          />

          <label style={labelStyle}>
            Institution / organisation{" "}
            <span style={{ color: "#444" }}>(optional)</span>
          </label>
          <input
            style={inputStyle}
            placeholder="IIT Delhi, startup name…"
            value={form.organisation}
            onChange={e => setField("organisation", e.target.value)}
          />

          <label style={labelStyle}>
            Short bio <span style={{ color: "#444" }}>(optional)</span>
          </label>
          <textarea
            style={{ ...inputStyle, minHeight: 80, resize: "vertical", lineHeight: 1.6, marginBottom: 0 }}
            placeholder="A sentence about your background or current focus…"
            value={form.bio}
            onChange={e => setField("bio", e.target.value)}
          />
        </div>

        {/* ── Section 2: Research preferences ── */}
        <div style={sectionStyle}>
          <p style={sectionTitle}>Research preferences</p>

          <label style={{ ...labelStyle, marginBottom: 10 }}>Topics you care about</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
            {TOPIC_OPTIONS.map(t => (
              <button key={t} style={chipStyle(form.topics.includes(t))}
                onClick={() => toggleChip("topics", t)}>
                {t}
              </button>
            ))}
          </div>

          <label style={{ ...labelStyle, marginBottom: 10 }}>Response style</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
            {STYLE_OPTIONS.map(st => (
              <button key={st} style={chipStyle(form.response_style.includes(st))}
                onClick={() => toggleChip("response_style", st)}>
                {st}
              </button>
            ))}
          </div>

          <label style={{ ...labelStyle, marginBottom: 10 }}>Technical depth</label>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <span style={{ fontSize: 12, color: "#444", minWidth: 58 }}>Beginner</span>
            <input
              type="range" min={1} max={5} step={1} value={depth}
              onChange={e => handleDepth(Number(e.target.value))}
              style={{ flex: 1, accentColor: "#a78bfa" }}
            />
            <span style={{ fontSize: 12, color: "#444", minWidth: 42, textAlign: "right" }}>Expert</span>
          </div>
          <div style={{ fontSize: 13, color: "#777", textAlign: "center", marginBottom: 20 }}>
            {DEPTH_LABELS[depth]}
          </div>

          <label style={labelStyle}>Primary goal</label>
          <select
            value={form.primary_goal}
            onChange={e => setField("primary_goal", e.target.value)}
            style={{
              width: "100%", padding: "9px 12px", fontSize: 14,
              background: "#0d0d1a", border: "1px solid #2a2a3a",
              borderRadius: 8, color: form.primary_goal ? "#e2e8f0" : "#555",
              outline: "none", fontFamily: "inherit", cursor: "pointer",
            }}
          >
            {GOAL_OPTIONS.map(g => (
              <option key={g.value} value={g.value}>{g.label}</option>
            ))}
          </select>
        </div>

        {/* Error / success banners */}
        {error && (
          <div style={{
            padding: "10px 14px", background: "#2e1a1a", border: "1px solid #4a2a2a",
            borderRadius: 8, color: "#f87171", fontSize: 13, marginBottom: 12,
          }}>
            {error}
          </div>
        )}
        {saved && (
          <div style={{
            padding: "10px 14px", background: "#0f2e1a", border: "1px solid #1a4a2a",
            borderRadius: 8, color: "#4ade80", fontSize: 13, marginBottom: 12,
          }}>
            ✓ Profile saved! Going back…
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
          <button
            onClick={onBack}
            style={{
              padding: "9px 20px", border: "1px solid #2a2a3a", borderRadius: 8,
              background: "none", color: "#666", fontSize: 14,
              cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || saved}
            style={{
              padding: "9px 24px", border: "none", borderRadius: 8,
              background: saving || saved ? "#3a3a5a" : "#534AB7",
              color: "#e2e8f0", fontSize: 14, fontWeight: 500,
              cursor: saving || saved ? "not-allowed" : "pointer",
              fontFamily: "inherit", transition: "background 0.15s",
            }}
          >
            {saving ? "Saving…" : saved ? "Saved ✓" : "Save profile"}
          </button>
        </div>

      </div>
    </div>
  )
}