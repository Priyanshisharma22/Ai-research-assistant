import { useRef, useState, useEffect } from "react"
import type { ChangeEvent } from "react"
import { useChat, MODELS } from "../hooks/useChat"
import { API } from "../utils/api"
import PersonaSwitcher from "./PersonaSwitcher"

interface DocSummary {
  filename: string
  summary: string
  chunks: number
}

interface ProfileFact {
  summary: string
  event_type: string
  importance: number
  session_date: string
  tags: string[]
}

interface ProfileData {
  total: number
  profile: {
    identity: ProfileFact[]
    preferences: ProfileFact[]
    projects: ProfileFact[]
    other: ProfileFact[]
  }
}

interface SidebarProps {
  onOpenProfile?: () => void
}

type UploadStatus = "idle" | "reading" | "summarizing" | "indexing" | "done" | "error"
type SyncSource = "google_drive" | "notion"
type SyncItemStatus = "idle" | "syncing" | "done" | "error"

interface DriveFile {
  id: string
  name: string
  mimeType: string
  modifiedTime: string
}

interface NotionPage {
  id: string
  title: string
  url: string
  last_edited_time: string
}

type ExternalItem = (DriveFile | NotionPage) & { _source: SyncSource }

export default function Sidebar({ onOpenProfile }: SidebarProps) {
  const { selectedModel, setSelectedModel } = useChat()
  const ref = useRef<HTMLInputElement>(null)
  const [status, setStatus] = useState<UploadStatus>("idle")
  const [progress, setProgress] = useState("")
  const [summaries, setSummaries] = useState<DocSummary[]>([])
  const [lastSummary, setLastSummary] = useState<DocSummary | null>(null)

  // Profile state
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [profileOpen, setProfileOpen] = useState(false)
  const [clearing, setClearing] = useState(false)

  // ── Import / Sync state ──────────────────────────────────────
  const [importOpen, setImportOpen] = useState(false)
  const [syncSource, setSyncSource] = useState<SyncSource>("google_drive")
  const [externalItems, setExternalItems] = useState<ExternalItem[]>([])
  const [fetchingItems, setFetchingItems] = useState(false)
  const [fetchError, setFetchError] = useState("")
  const [syncStatus, setSyncStatus] = useState<Record<string, SyncItemStatus>>({})
  const [importFilter, setImportFilter] = useState("")

  useEffect(() => {
    fetch(API + "/summaries")
      .then(r => r.json())
      .then(data => setSummaries(Object.values(data) as DocSummary[]))
      .catch(() => {})
  }, [])

  useEffect(() => { fetchProfile() }, [])
  useEffect(() => { if (!profileOpen) return; fetchProfile() }, [profileOpen])
  useEffect(() => { if (profile && profile.total > 0) setProfileOpen(true) }, [profile])

  const fetchProfile = () => {
    fetch(API + "/profile")
      .then(r => r.json())
      .then(setProfile)
      .catch(() => {})
  }

  const clearProfile = async () => {
    setClearing(true)
    try {
      await fetch(API + "/profile", { method: "DELETE" })
      setProfile(null)
      await fetchProfile()
    } finally {
      setClearing(false)
    }
  }

  const handleUpload = async (e: ChangeEvent<HTMLInputElement>) => {
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
      if (!res.ok) {
        const errorText = await res.text().catch(() => "")
        throw new Error(errorText || `Upload failed with status ${res.status}`)
      }
      if (!res.body) {
        throw new Error("Upload succeeded but no response stream was returned.")
      }
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const lines = decoder.decode(value).split("\n").filter(l => l.startsWith("data: "))
        for (const line of lines) {
          // ✅ FIX: use slice instead of replace to correctly strip the "data: " prefix
          const data = line.slice("data: ".length).trim()
          if (data === "[DONE]") break
          try {
            const event = JSON.parse(data)
            setStatus(event.status)
            setProgress(event.message)
            if (event.status === "done") {
              const doc = { filename: event.filename, summary: event.summary, chunks: event.chunks }
              setLastSummary(doc)
              setSummaries((prev: DocSummary[]) => [doc, ...prev.filter((d: DocSummary) => d.filename !== event.filename)])
            }
          } catch(err) {}
        }
      }
    } catch(err) {
      setStatus("error")
      console.error("Upload error:", err)                          // ✅ ADD: log real error
      setProgress("Upload failed: " + String(err))                // ✅ FIX: show real error
    }
  }

  // ── External source fetch ─────────────────────────────────────
  // Both Google Drive and Notion now use server .env credentials — no token input needed
  const fetchExternalItems = async () => {
    setFetchError("")
    setFetchingItems(true)
    setExternalItems([])
    try {
      if (syncSource === "google_drive") {
        const res = await fetch(API + "/integrations/google-drive/list", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ page_size: 20 }),
        })
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        setExternalItems((data.files || []).map((f: DriveFile) => ({ ...f, _source: "google_drive" as SyncSource })))
      } else {
        // Notion: no token sent — backend reads NOTION_TOKEN from .env automatically
        const res = await fetch(API + "/integrations/notion/list", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ page_size: 20 }),
        })
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        setExternalItems((data.pages || []).map((p: NotionPage) => ({ ...p, _source: "notion" as SyncSource })))
      }
    } catch (e: any) {
      setFetchError(e.message || "Failed to connect.")
    } finally {
      setFetchingItems(false)
    }
  }

  const syncItem = async (item: ExternalItem) => {
    setSyncStatus((s: Record<string, SyncItemStatus>) => ({ ...s, [item.id]: "syncing" as SyncItemStatus }))
    const isDrive = item._source === "google_drive"
    const driveItem = item as DriveFile & { _source: SyncSource }
    const notionItem = item as NotionPage & { _source: SyncSource }

    // Both sources now use empty credentials — backend handles auth via .env
    const body = isDrive
      ? {
          source: "google_drive",
          item_id: driveItem.id,
          item_name: driveItem.name,
          mime_type: driveItem.mimeType,
          credentials: {},
        }
      : {
          source: "notion",
          item_id: notionItem.id,
          item_name: notionItem.title,
          credentials: {},  // backend reads NOTION_TOKEN from .env
        }

    try {
      const res = await fetch(API + "/integrations/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error()
      setSyncStatus((s: Record<string, SyncItemStatus>) => ({ ...s, [item.id]: "done" as SyncItemStatus }))
    } catch {
      setSyncStatus((s: Record<string, SyncItemStatus>) => ({ ...s, [item.id]: "error" as SyncItemStatus }))
    }
  }

  const filteredItems = externalItems.filter(item => {
    const name = "name" in item ? (item as DriveFile).name : (item as NotionPage).title
    return name.toLowerCase().includes(importFilter.toLowerCase())
  })

  const statusColor: Record<UploadStatus, string> = {
    idle: "#555", reading: "#a78bfa", summarizing: "#f59e0b",
    indexing: "#34d399", done: "#6ee7b7", error: "#f87171",
  }
  const statusLabel: Record<UploadStatus, string> = {
    idle: "", reading: "[reading]", summarizing: "[summarizing]",
    indexing: "[indexing]", done: "[done]", error: "[error]",
  }

  const isVision =
    selectedModel.startsWith("anthropic/") ||
    selectedModel.startsWith("openai/") ||
    selectedModel.startsWith("gemini/") ||
    selectedModel.includes("vision")

  const totalFacts = profile?.total ?? 0
  const allFacts = profile ? [
    ...profile.profile.identity,
    ...profile.profile.preferences,
    ...profile.profile.projects,
    ...profile.profile.other,
  ] : []

  const factIcon: Record<string, string> = {
    fact: "👤", preference: "⚙️", insight: "🎯", question: "❓",
  }

  return (
    <div style={{
      width: 240,
      background: "#0d0d1a",
      borderRight: "1px solid #1e1e2e",
      display: "flex",
      flexDirection: "column",
      padding: 16,
      gap: 4,
      overflowY: "auto",
      height: "100vh",
    }}>
      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: 18, color: "#a78bfa" }}>AI</span>
        <span style={{ fontWeight: 600, color: "#e2e8f0", fontSize: 15 }}>ResearchAI</span>
      </div>

      <PersonaSwitcher />

      {/* Model Selector */}
      <div style={{ marginTop: 8 }}>
        <p style={{ fontSize: 11, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 8px" }}>
          Model
        </p>
        <select
          value={selectedModel}
          onChange={(e: ChangeEvent<HTMLSelectElement>) => setSelectedModel((e.target as HTMLSelectElement).value)}
          style={{
            width: "100%", padding: "8px 10px", background: "#1a1a2e",
            border: "1px solid #3a3a5a", borderRadius: 8,
            color: "#a78bfa", fontSize: 12, cursor: "pointer",
          }}
        >
          {MODELS.map((m) => (
            <option key={m.id} value={m.id}>{m.provider} — {m.label}</option>
          ))}
        </select>

        {isVision ? (
          <div style={{ marginTop: 6, padding: "4px 8px", background: "#1a2e1a", border: "1px solid #2a4a2a", borderRadius: 6, fontSize: 11, color: "#4ade80", textAlign: "center" }}>
            👁 Vision enabled
          </div>
        ) : (
          <div style={{ marginTop: 6, padding: "4px 8px", background: "#2e1a1a", border: "1px solid #4a2a2a", borderRadius: 6, fontSize: 11, color: "#f87171", textAlign: "center" }}>
            ⚠️ Text only — no vision
          </div>
        )}
      </div>

      {/* ── User Profile Panel ── */}
      <div style={{ borderTop: "1px solid #1e1e2e", paddingTop: 12, marginTop: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: profileOpen ? 8 : 0 }}>
          <button
            onClick={() => setProfileOpen((o: boolean) => !o)}
            style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex", alignItems: "center", gap: 6, flex: 1 }}
          >
            <p style={{ fontSize: 11, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", margin: 0 }}>
              My Profile
            </p>
            <span style={{ fontSize: 10, color: "#555" }}>
              {totalFacts > 0 && (
                <span style={{ background: "#a78bfa22", color: "#a78bfa", borderRadius: 10, padding: "1px 6px", marginRight: 4, fontSize: 10 }}>
                  {totalFacts}
                </span>
              )}
              {profileOpen ? "▲" : "▼"}
            </span>
          </button>
          <button
            onClick={onOpenProfile}
            title="Edit profile"
            style={{ background: "none", border: "1px solid #2a2a3a", borderRadius: 6, color: "#555", fontSize: 11, cursor: "pointer", padding: "2px 7px", fontFamily: "inherit", marginLeft: 6, flexShrink: 0 }}
          >
            ✏️
          </button>
        </div>

        {profileOpen && (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {allFacts.length === 0 ? (
              <div style={{ padding: "10px", background: "#111", borderRadius: 8, border: "1px solid #1e1e2e", fontSize: 11, color: "#444", textAlign: "center", lineHeight: 1.5 }}>
                No profile yet.<br />
                <span onClick={onOpenProfile} style={{ color: "#a78bfa", cursor: "pointer", textDecoration: "underline" }}>
                  Set up your profile
                </span>
              </div>
            ) : (
              <>
                {profile!.profile.identity.length > 0 && (
                  <div>
                    <p style={{ fontSize: 10, color: "#444", margin: "0 0 4px", textTransform: "uppercase" }}>Identity</p>
                    {profile!.profile.identity.map((f, i) => <FactRow key={i} fact={f} icon={factIcon["fact"]} />)}
                  </div>
                )}
                {profile!.profile.preferences.length > 0 && (
                  <div>
                    <p style={{ fontSize: 10, color: "#444", margin: "4px 0 4px", textTransform: "uppercase" }}>Preferences</p>
                    {profile!.profile.preferences.map((f, i) => <FactRow key={i} fact={f} icon={factIcon["preference"]} />)}
                  </div>
                )}
                {profile!.profile.projects.length > 0 && (
                  <div>
                    <p style={{ fontSize: 10, color: "#444", margin: "4px 0 4px", textTransform: "uppercase" }}>Projects & Goals</p>
                    {profile!.profile.projects.map((f, i) => <FactRow key={i} fact={f} icon={factIcon["insight"]} />)}
                  </div>
                )}
                <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                  <button
                    onClick={onOpenProfile}
                    style={{ flex: 1, padding: "6px", background: "none", border: "1px solid #3a3a5a", borderRadius: 6, color: "#a78bfa", fontSize: 11, cursor: "pointer" }}
                  >
                    ✏️ Edit
                  </button>
                  <button
                    onClick={clearProfile}
                    disabled={clearing}
                    style={{ flex: 1, padding: "6px", background: "none", border: "1px solid #3a1a1a", borderRadius: 6, color: "#f87171", fontSize: 11, cursor: "pointer", opacity: clearing ? 0.5 : 1 }}
                  >
                    {clearing ? "Clearing..." : "🗑 Clear"}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* ── Import from Google Drive / Notion ── */}
      <div style={{ borderTop: "1px solid #1e1e2e", paddingTop: 12, marginTop: 8 }}>
        <button
          onClick={() => setImportOpen((o: boolean) => !o)}
          style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}
        >
          <p style={{ fontSize: 11, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", margin: 0 }}>
            📥 Import Sources
          </p>
          <span style={{ fontSize: 10, color: "#555" }}>{importOpen ? "▲" : "▼"}</span>
        </button>

        {importOpen && (
          <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>

            {/* Source Tabs */}
            <div style={{ display: "flex", background: "#111", borderRadius: 8, padding: 3, gap: 2 }}>
              {(["google_drive", "notion"] as SyncSource[]).map(src => (
                <button
                  key={src}
                  onClick={() => { setSyncSource(src); setExternalItems([]); setFetchError("") }}
                  style={{
                    flex: 1, padding: "5px 4px", border: "none", borderRadius: 6,
                    cursor: "pointer", fontSize: 10, fontFamily: "inherit",
                    background: syncSource === src ? "#1a1a2e" : "transparent",
                    color: syncSource === src ? "#a78bfa" : "#555",
                    fontWeight: syncSource === src ? 600 : 400,
                    transition: "all 0.15s",
                  }}
                >
                  {src === "google_drive" ? "🗂️ Drive" : "🗒️ Notion"}
                </button>
              ))}
            </div>

            {/* Both sources now show "Connected via server credentials" — no token input */}
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "7px 10px", background: "#0d1a0d",
              border: "1px solid #1a3a1a", borderRadius: 7,
            }}>
              <span style={{ fontSize: 12 }}>🔑</span>
              <span style={{ fontSize: 10, color: "#4ade80", flex: 1 }}>
                {syncSource === "google_drive"
                  ? "Connected via server credentials"
                  : "Connected via server credentials"}
              </span>
            </div>

            {/* Browse Button */}
            <button
              onClick={fetchExternalItems}
              disabled={fetchingItems}
              style={{
                width: "100%", padding: "8px", background: "#1a1a2e",
                border: "1px solid #3a3a5a", borderRadius: 7,
                color: "#a78bfa", fontSize: 12, cursor: "pointer",
                fontFamily: "inherit", fontWeight: 600,
                opacity: fetchingItems ? 0.6 : 1,
              }}
            >
              {fetchingItems ? "Loading..." : "Browse Files"}
            </button>

            {/* Error */}
            {fetchError && (
              <div style={{ padding: "6px 8px", background: "#1a0a0a", border: "1px solid #3a1515", borderRadius: 6, fontSize: 10, color: "#f87171" }}>
                ⚠️ {fetchError}
              </div>
            )}

            {/* Filter */}
            {externalItems.length > 0 && (
              <input
                type="text"
                placeholder="Filter files..."
                value={importFilter}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setImportFilter((e.target as HTMLInputElement).value)}
                style={{
                  width: "100%", padding: "6px 10px", background: "#111",
                  border: "1px solid #2a2a3a", borderRadius: 7,
                  color: "#e2e8f0", fontSize: 11, fontFamily: "inherit",
                  outline: "none", boxSizing: "border-box",
                }}
              />
            )}

            {/* File List */}
            {filteredItems.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 220, overflowY: "auto" }}>
                {filteredItems.map(item => {
                  const isDrive = item._source === "google_drive"
                  const name = isDrive ? (item as DriveFile).name : (item as NotionPage).title
                  const itemSyncStatus = syncStatus[item.id] || "idle"
                  return (
                    <div
                      key={item.id}
                      style={{
                        display: "flex", alignItems: "center", gap: 6,
                        padding: "7px 8px", background: "#111",
                        border: "1px solid #1e1e2e", borderRadius: 8,
                      }}
                    >
                      <span style={{ fontSize: 14, flexShrink: 0 }}>{isDrive ? "📄" : "🗒️"}</span>
                      <span style={{
                        flex: 1, fontSize: 10, color: "#aaa",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>
                        {name}
                      </span>
                      <button
                        onClick={() => syncItem(item)}
                        disabled={itemSyncStatus === "syncing" || itemSyncStatus === "done"}
                        style={{
                          padding: "3px 8px", border: "none", borderRadius: 5,
                          fontSize: 10, fontFamily: "inherit", cursor: "pointer", flexShrink: 0,
                          background: itemSyncStatus === "done" ? "#1a2e1a"
                            : itemSyncStatus === "error" ? "#2e1a1a"
                            : "#1a1a2e",
                          color: itemSyncStatus === "done" ? "#4ade80"
                            : itemSyncStatus === "error" ? "#f87171"
                            : "#a78bfa",
                          opacity: itemSyncStatus === "syncing" ? 0.5 : 1,
                        }}
                      >
                        {itemSyncStatus === "idle" && "Import"}
                        {itemSyncStatus === "syncing" && "..."}
                        {itemSyncStatus === "done" && "✓"}
                        {itemSyncStatus === "error" && "Retry"}
                      </button>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Empty state */}
            {!fetchingItems && externalItems.length === 0 && !fetchError && (
              <p style={{ fontSize: 10, color: "#333", textAlign: "center", margin: "4px 0" }}>
                Click Browse Files to load your {syncSource === "google_drive" ? "Drive" : "Notion"} pages
              </p>
            )}
          </div>
        )}
      </div>

      {/* Knowledge Base */}
      <div style={{ borderTop: "1px solid #1e1e2e", paddingTop: 12, marginTop: 8 }}>
        <p style={{ fontSize: 11, color: "#555", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 8px" }}>
          Knowledge Base
        </p>
        <button
          onClick={() => ref.current?.click()}
          disabled={status === "reading" || status === "summarizing" || status === "indexing"}
          style={{
            width: "100%", padding: "10px", background: "#1a1a2e",
            border: "1px dashed #3a3a5a", borderRadius: 8, color: "#a78bfa",
            cursor: "pointer", fontSize: 13,
            opacity: status === "idle" || status === "done" || status === "error" ? 1 : 0.6,
          }}
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
      <div style={{ fontSize: 11, color: "#333", textAlign: "center", paddingTop: 8 }}>
        powered by Claude
      </div>
    </div>
  )
}

function FactRow({ fact, icon, key: _key }: { fact: ProfileFact; icon: string; key?: number }) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 6,
      padding: "5px 8px", background: "#111", borderRadius: 6,
      border: "1px solid #1e1e2e", marginBottom: 3,
    }}>
      <span style={{ fontSize: 11, flexShrink: 0, marginTop: 1 }}>{icon}</span>
      <span style={{ fontSize: 11, color: "#aaa", lineHeight: 1.4, wordBreak: "break-word" }}>
        {fact.summary}
      </span>
    </div>
  )
}