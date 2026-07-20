import { useEffect, useState } from "react";
import { Clock, Plus } from "lucide-react";
import { useDashboard } from "./context";

const THEME = {
  accent: "#7C3AED",
  accentTint: "#F5F3FF",
  border: "#E5E7EB",
  ink: "#1F2621",
};

function formatRelative(dateStr) {
  const d = new Date(dateStr);
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

export function HistoryPanel({ onClose }) {
  const { loadSession, startNewSession, currentThreadId, pendingThreads } = useDashboard();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  

  useEffect(() => {
    frappe.call({
      method: "frappe_assistant_core.aiko.api.list_dashboard_sessions",
      args: { limit: 50 },
      callback: (r) => { setSessions(r.message || []); setLoading(false); },
      error: () => { setError("Could not load history."); setLoading(false); },
    });
  }, []);

  return (
    <div style={{
      width: 300, minWidth: 300, height: "100%", borderRight: `1px solid ${THEME.border}`,
      background: "white", display: "flex", flexDirection: "column",
      boxShadow: "8px 0 24px rgba(0,0,0,0.08)",
    }}>
      <div style={{
        padding: "13px 16px", borderBottom: `1px solid ${THEME.border}`,
        fontSize: 13, fontWeight: 700, color: THEME.ink,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        fontFamily: "Fraunces, Georgia, serif",
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Clock size={16} stroke={THEME.accent} strokeWidth={1.5} /> History
        </span>
        <button onClick={onClose} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 13, color: "#8A8478" }}>✕</button>
      </div>

      <div style={{ padding: "10px 12px", borderBottom: `1px solid ${THEME.border}` }}>
        <button
          onClick={() => { startNewSession(); onClose(); }}
          style={{
            width: "100%", padding: "8px 12px", borderRadius: 4,
            border: `1px solid ${THEME.accent}`, background: THEME.accentTint,
            color: THEME.accent, fontWeight: 600, fontSize: 12.5, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
            fontFamily: "Inter, sans-serif",
          }}
        >
          <Plus size={14} strokeWidth={2.5} /> New Dashboard
        </button>
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
        {loading && <div style={{ padding: 12, fontSize: 12.5, color: "#8A8478" }}>Loading…</div>}
        {error && <div style={{ padding: 12, fontSize: 12.5, color: "#B54A3F" }}>{error}</div>}
        {!loading && sessions.length === 0 && (
          <div style={{ padding: 12, fontSize: 12.5, color: "#8A8478" }}>No past dashboards yet.</div>
        )}
        {sessions.map((s) => {
          const isActive = s.thread_id === currentThreadId;
          return (
            <button
              key={s.name}
              onClick={() => { loadSession(s.thread_id); onClose(); }}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "10px 12px", borderRadius: 4, marginBottom: 4,
                border: `1px solid ${isActive ? THEME.accent : "transparent"}`,
                background: isActive ? THEME.accentTint : "transparent",
                cursor: "pointer", fontFamily: "Inter, sans-serif",
              }}
              onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = "#FAFAFA"; }}
              onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
            >
              <div style={{ fontSize: 13, fontWeight: 600, color: THEME.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {s.name}
                {pendingThreads[s.thread_id] && (
                  <span style={{
                    fontSize: 10, fontWeight: 700, color: "#D99A3D",
                    background: "#FBF6EC", padding: "1px 6px", borderRadius: 10, marginLeft: 6,
                  }}>● generating</span>
                )}
              </div>
              {s.preview && (
                <div style={{
                  fontSize: 12, color: "#5B5650", marginTop: 3,
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}>
                  {s.preview}
                </div>
              )}
              <div style={{ fontSize: 11, color: "#8A8478", marginTop: 2, display: "flex", gap: 6 }}>
                <span>{formatRelative(s.last_active || s.creation)}</span>
                <span>·</span>
                <span>{s.message_count || 0} msgs</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}