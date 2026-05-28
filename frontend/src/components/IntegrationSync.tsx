import { useState, useCallback } from "react";
import type { ChangeEvent } from "react";
import { API } from "../utils/api";

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type Source = "google_drive" | "notion";

interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  modifiedTime: string;
  size?: string;
}

interface NotionPage {
  id: string;
  title: string;
  url: string;
  last_edited_time: string;
}

type Item = (DriveFile | NotionPage) & { _source: Source };

interface SyncStatus {
  [id: string]: "idle" | "syncing" | "done" | "error";
}

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

function formatDate(iso: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getMimeIcon(mime: string) {
  if (mime?.includes("document")) return "📝";
  if (mime?.includes("pdf")) return "📄";
  if (mime?.includes("text")) return "📃";
  return "📁";
}

// ─────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────

export default function IntegrationSync() {
  const [activeSource, setActiveSource] = useState<Source>("google_drive");
  const [googleToken, setGoogleToken] = useState("");
  const [notionToken, setNotionToken] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>({});
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // ── Fetch list ──────────────────────────────

  const fetchItems = useCallback(async () => {
    setError("");
    setLoading(true);
    setItems([]);

    try {
      if (activeSource === "google_drive") {
        const res = await fetch(`${API}/integrations/google-drive/list`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ access_token: googleToken }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        setItems((data.files || []).map((f: DriveFile) => ({ ...f, _source: "google_drive" })));
      } else {
        const res = await fetch(`${API}/integrations/notion/list`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ notion_token: notionToken }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        setItems((data.pages || []).map((p: NotionPage) => ({ ...p, _source: "notion" })));
      }
    } catch (e: any) {
      setError(e.message || "Failed to fetch. Check your token.");
    } finally {
      setLoading(false);
    }
  }, [activeSource, googleToken, notionToken]);

  // ── Sync single item ────────────────────────

  const syncItem = useCallback(async (item: Item) => {
    setSyncStatus((s: SyncStatus) => ({ ...s, [item.id]: "syncing" as SyncStatus[keyof SyncStatus] }));

    const isDrive = item._source === "google_drive";
    const driveItem = item as DriveFile & { _source: Source };
    const notionItem = item as NotionPage & { _source: Source };

    const body = isDrive
      ? {
          source: "google_drive",
          item_id: driveItem.id,
          item_name: driveItem.name,
          mime_type: driveItem.mimeType,
          credentials: { access_token: googleToken },
        }
      : {
          source: "notion",
          item_id: notionItem.id,
          item_name: notionItem.title,
          credentials: { notion_token: notionToken },
        };

    try {
      const res = await fetch(`${API}/integrations/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await res.text());
      setSyncStatus((s: SyncStatus) => ({ ...s, [item.id]: "done" as SyncStatus[keyof SyncStatus] }));
    } catch {
      setSyncStatus((s: SyncStatus) => ({ ...s, [item.id]: "error" as SyncStatus[keyof SyncStatus] }));
    }
  }, [googleToken, notionToken]);

  // ── Filtered items ──────────────────────────

  const filtered = items.filter((item) => {
    const name = "name" in item ? item.name : (item as NotionPage).title;
    return name.toLowerCase().includes(searchQuery.toLowerCase());
  });

  // ── Render ──────────────────────────────────

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerTop}>
          <h2 style={styles.title}>
            <span style={styles.titleIcon}>⚡</span>
            Import Sources
          </h2>
          <p style={styles.subtitle}>Sync documents into your knowledge base</p>
        </div>

        {/* Source Tabs */}
        <div style={styles.tabs}>
          {(["google_drive", "notion"] as Source[]).map((src) => (
            <button
              key={src}
              style={{
                ...styles.tab,
                ...(activeSource === src ? styles.tabActive : {}),
              }}
              onClick={() => { setActiveSource(src); setItems([]); setError(""); }}
            >
              {src === "google_drive" ? (
                <><span>🗂️</span> Google Drive</>
              ) : (
                <><span>🗒️</span> Notion</>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Token Input */}
      <div style={styles.tokenSection}>
        {activeSource === "google_drive" ? (
          <div style={styles.inputGroup}>
            <label style={styles.label}>Google OAuth Access Token</label>
            <div style={styles.inputRow}>
              <input
                type="password"
                placeholder="ya29.a0AfH6..."
                value={googleToken}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setGoogleToken(e.target.value)}
                style={styles.input}
              />
              <a
                href="https://developers.google.com/oauthplayground"
                target="_blank"
                rel="noreferrer"
                style={styles.helpLink}
              >
                Get token ↗
              </a>
            </div>
          </div>
        ) : (
          <div style={styles.inputGroup}>
            <label style={styles.label}>Notion Integration Token</label>
            <div style={styles.inputRow}>
              <input
                type="password"
                placeholder="secret_..."
                value={notionToken}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setNotionToken(e.target.value)}
                style={styles.input}
              />
              <a
                href="https://www.notion.so/my-integrations"
                target="_blank"
                rel="noreferrer"
                style={styles.helpLink}
              >
                Get token ↗
              </a>
            </div>
          </div>
        )}

        <button
          style={{
            ...styles.fetchBtn,
            ...(loading ? styles.fetchBtnLoading : {}),
          }}
          onClick={fetchItems}
          disabled={loading || (activeSource === "google_drive" ? !googleToken : !notionToken)}
        >
          {loading ? (
            <span style={styles.spinner}>⟳</span>
          ) : (
            "Browse Files"
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={styles.errorBox}>
          <span>⚠️</span> {error}
        </div>
      )}

      {/* Search */}
      {items.length > 0 && (
        <div style={styles.searchRow}>
          <input
            type="text"
            placeholder="Filter files..."
            value={searchQuery}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
            style={styles.searchInput}
          />
          <span style={styles.countBadge}>{filtered.length} files</span>
        </div>
      )}

      {/* File List */}
      {filtered.length > 0 && (
        <div style={styles.fileList}>
          {filtered.map((item) => {
            const isDrive = item._source === "google_drive";
            const driveItem = item as DriveFile & { _source: Source };
            const notionItem = item as NotionPage & { _source: Source };
            const name = isDrive ? driveItem.name : notionItem.title;
            const date = isDrive ? driveItem.modifiedTime : notionItem.last_edited_time;
            const status = syncStatus[item.id] || "idle";

            return (
              <div key={item.id} style={styles.fileCard}>
                <div style={styles.fileIcon}>
                  {isDrive ? getMimeIcon(driveItem.mimeType) : "🗒️"}
                </div>
                <div style={styles.fileInfo}>
                  <div style={styles.fileName}>{name}</div>
                  <div style={styles.fileMeta}>
                    {isDrive && (
                      <span style={styles.mimeTag}>
                        {driveItem.mimeType.split(".").pop()?.split("/").pop()}
                      </span>
                    )}
                    <span style={styles.fileDate}>{formatDate(date)}</span>
                  </div>
                </div>
                <button
                  style={{
                    ...styles.syncBtn,
                    ...(status === "done" ? styles.syncBtnDone : {}),
                    ...(status === "error" ? styles.syncBtnError : {}),
                    ...(status === "syncing" ? styles.syncBtnLoading : {}),
                  }}
                  onClick={() => syncItem(item)}
                  disabled={status === "syncing" || status === "done"}
                >
                  {status === "idle" && "Import"}
                  {status === "syncing" && "⟳"}
                  {status === "done" && "✓ Done"}
                  {status === "error" && "Retry"}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {!loading && items.length === 0 && !error && (
        <div style={styles.emptyState}>
          <div style={styles.emptyIcon}>
            {activeSource === "google_drive" ? "🗂️" : "🗒️"}
          </div>
          <p style={styles.emptyText}>
            Enter your token and click Browse Files to see your documents
          </p>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  container: {
    fontFamily: "'IBM Plex Mono', 'Courier New', monospace",
    background: "#0d0d0f",
    color: "#e8e8e8",
    borderRadius: "16px",
    border: "1px solid #1e1e24",
    overflow: "hidden",
    maxWidth: "640px",
    width: "100%",
    boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
  },
  header: {
    padding: "28px 28px 0",
    background: "linear-gradient(180deg, #13131a 0%, #0d0d0f 100%)",
  },
  headerTop: { marginBottom: "20px" },
  title: {
    margin: 0,
    fontSize: "18px",
    fontWeight: 700,
    letterSpacing: "-0.3px",
    color: "#f0f0f0",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  titleIcon: { fontSize: "20px" },
  subtitle: {
    margin: "4px 0 0",
    fontSize: "12px",
    color: "#666",
    letterSpacing: "0.5px",
    textTransform: "uppercase",
  },
  tabs: {
    display: "flex",
    gap: "2px",
    background: "#0a0a0c",
    padding: "4px",
    borderRadius: "10px",
    marginBottom: "24px",
  },
  tab: {
    flex: 1,
    padding: "8px 16px",
    border: "none",
    borderRadius: "7px",
    cursor: "pointer",
    fontSize: "13px",
    fontFamily: "inherit",
    fontWeight: 500,
    color: "#555",
    background: "transparent",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    transition: "all 0.15s",
  },
  tabActive: {
    background: "#1a1a22",
    color: "#c8f542",
    boxShadow: "0 0 0 1px #2a2a3a",
  },
  tokenSection: {
    padding: "0 28px 24px",
    display: "flex",
    flexDirection: "column",
    gap: "14px",
  },
  inputGroup: { display: "flex", flexDirection: "column", gap: "6px" },
  label: { fontSize: "11px", color: "#666", textTransform: "uppercase", letterSpacing: "0.8px" },
  inputRow: { display: "flex", gap: "8px", alignItems: "center" },
  input: {
    flex: 1,
    padding: "10px 14px",
    background: "#111116",
    border: "1px solid #222228",
    borderRadius: "8px",
    color: "#e8e8e8",
    fontSize: "13px",
    fontFamily: "inherit",
    outline: "none",
    transition: "border-color 0.15s",
  },
  helpLink: {
    fontSize: "11px",
    color: "#c8f542",
    textDecoration: "none",
    whiteSpace: "nowrap",
    opacity: 0.8,
  },
  fetchBtn: {
    padding: "11px 24px",
    background: "#c8f542",
    color: "#0a0a0c",
    border: "none",
    borderRadius: "8px",
    fontSize: "13px",
    fontWeight: 700,
    fontFamily: "inherit",
    cursor: "pointer",
    letterSpacing: "0.3px",
    alignSelf: "flex-start",
    transition: "all 0.15s",
  },
  fetchBtnLoading: { opacity: 0.6, cursor: "not-allowed" },
  spinner: {
    display: "inline-block",
    animation: "spin 1s linear infinite",
    fontSize: "16px",
  },
  errorBox: {
    margin: "0 28px 20px",
    padding: "12px 16px",
    background: "#1a0a0a",
    border: "1px solid #3a1515",
    borderRadius: "8px",
    fontSize: "13px",
    color: "#ff7070",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  searchRow: {
    padding: "0 28px 16px",
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  searchInput: {
    flex: 1,
    padding: "8px 14px",
    background: "#111116",
    border: "1px solid #222228",
    borderRadius: "7px",
    color: "#e8e8e8",
    fontSize: "13px",
    fontFamily: "inherit",
    outline: "none",
  },
  countBadge: {
    fontSize: "11px",
    color: "#555",
    whiteSpace: "nowrap",
  },
  fileList: {
    padding: "0 16px 20px",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    maxHeight: "400px",
    overflowY: "auto",
  },
  fileCard: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "12px 14px",
    background: "#111116",
    borderRadius: "10px",
    border: "1px solid #1a1a22",
    transition: "border-color 0.15s",
  },
  fileIcon: { fontSize: "22px", flexShrink: 0 },
  fileInfo: { flex: 1, minWidth: 0 },
  fileName: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#e8e8e8",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  fileMeta: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginTop: "3px",
  },
  mimeTag: {
    fontSize: "10px",
    padding: "1px 6px",
    background: "#1e1e28",
    borderRadius: "4px",
    color: "#888",
    textTransform: "uppercase",
  },
  fileDate: { fontSize: "11px", color: "#555" },
  syncBtn: {
    padding: "7px 16px",
    background: "#1a1a28",
    border: "1px solid #2a2a3a",
    borderRadius: "7px",
    color: "#c8f542",
    fontSize: "12px",
    fontFamily: "inherit",
    fontWeight: 600,
    cursor: "pointer",
    flexShrink: 0,
    transition: "all 0.15s",
    letterSpacing: "0.3px",
  },
  syncBtnDone: {
    background: "#0f1f0a",
    border: "1px solid #1e3a10",
    color: "#6ddb4f",
    cursor: "default",
  },
  syncBtnError: {
    background: "#1a0a0a",
    border: "1px solid #3a1515",
    color: "#ff7070",
  },
  syncBtnLoading: { opacity: 0.5, cursor: "not-allowed" },
  emptyState: {
    padding: "48px 28px",
    textAlign: "center",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "12px",
  },
  emptyIcon: { fontSize: "40px", opacity: 0.3 },
  emptyText: { fontSize: "13px", color: "#444", margin: 0, lineHeight: 1.6 },
};