import { useRef, useState } from "react";
import { Send } from "lucide-react";
import { DashboardProvider, useDashboard } from "./context";
import { ConversationPanel } from "./ConversationPanel";
import { DashboardCanvas } from "./DashboardCanvas";
import { StarterGrid } from "./StarterGrid";

export { useDashboard } from "./context";

const TOP_BAR_BG = "#F3EFFA";

const THEME = {
  ink: "#1F2621",
  paper: "#F6F5F9",
  green: "#7C3AED",
  sage: "#A78BFA",
  line: "#E5E7EB",
  white: "#FFFFFF",
  accent: "#7C3AED",
};

function getGreetingName() {
  try {
    if (window.frappe?.session?.user_fullname) return window.frappe.session.user_fullname.split(" ")[0];
    if (window.frappe?.boot?.user?.first_name) return window.frappe.boot.user.first_name;
    if (window.frappe?.session?.user && window.frappe.session.user !== "Guest") {
      return window.frappe.session.user.split("@")[0];
    }
  } catch (e) { /* ignore */ }
  return "there";
}

function DashboardLayout({ library, starters }) {
  const { conversation, dashboardCode, isStreaming, clear } = useDashboard();
  const hasDashboard = dashboardCode !== null;
  const isEmpty = conversation.length === 0 && !hasDashboard;

  return (
    <div style={{
      minHeight: "100vh",
      background: THEME.paper,
      fontFamily: "'Inter', system-ui, sans-serif",
      color: THEME.ink,
    }}>
      {/* Header */}
      <div style={{
        background: TOP_BAR_BG,
        padding: "12px 28px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        position: "sticky",
        top: 0,
        zIndex: 20,
      }}>
        <span style={{
          width: 28, height: 28, borderRadius: 4,
          background: THEME.green,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, color: THEME.white, fontWeight: 700,
          fontFamily: "Fraunces, Georgia, serif",
        }}>A</span>
        <h1 style={{
          fontSize: 15, fontWeight: 600, margin: 0, color: THEME.ink,
          letterSpacing: "-0.01em", fontFamily: "Fraunces, Georgia, serif",
        }}>AIKO</h1>
        <span style={{
          fontSize: 12, color: "#8A8478", paddingLeft: 10,
          borderLeft: `1px solid ${THEME.line}`,
          fontFamily: "Inter, sans-serif",
        }}>Dashboard Assistant</span>

        <div style={{ marginLeft: "auto" }} />

        {(hasDashboard || conversation.length > 0) && (
          <button onClick={clear} style={{
            padding: "5px 14px", border: `1px solid ${THEME.line}`,
            borderRadius: 3, background: "transparent", cursor: "pointer",
            fontSize: 12, color: "#8A8478", fontWeight: 600,
            fontFamily: "Inter, sans-serif", transition: "all 0.12s",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = THEME.green; e.currentTarget.style.color = "white"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "#8A8478"; }}
          >
            Clear
          </button>
        )}
      </div>

      {/* Body */}
      {isEmpty ? (
        <EmptyState starters={starters} />
      ) : (
        <div style={{ display: "flex", height: "calc(100vh - 49px)" }}>
          <div style={{
            flex: hasDashboard ? "1 1 60%" : "1 1 100%",
            overflow: "auto", padding: 24, transition: "flex 0.3s",
          }}>
            <DashboardCanvas library={library} />
          </div>
          {(conversation.length > 0 || isStreaming) && <ConversationPanel />}
        </div>
      )}
    </div>
  );
}

function EmptyState({ starters }) {
  const name = getGreetingName();
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div style={{
      minHeight: "calc(100vh - 49px)",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      padding: "80px 24px",
    }}>
      <div style={{ textAlign: "center", marginBottom: 40 }}>
        <div style={{
          fontSize: 14, fontWeight: 600, color: THEME.accent, marginBottom: 10,
          fontFamily: "Fraunces, Georgia, serif",
        }}>
          {greeting}, {name}
        </div>
        <div style={{
          fontSize: 24, fontWeight: 600, color: "#1F1B24",
          letterSpacing: "-0.01em", lineHeight: 1.3, maxWidth: 520,
          fontFamily: "Inter, sans-serif",
        }}>
          Build your dashboard — pick a starter or describe what you need
        </div>
        <div style={{ fontSize: 13, color: "#6B7280", marginTop: 6, fontFamily: "Inter, sans-serif" }}>
          Ask for summaries, charts, comparisons, or any fleet data
        </div>
      </div>

      <StarterGrid starters={starters} />

      <div style={{ marginTop: 24, width: "100%", maxWidth: 700 }}>
        <CenteredInput />
      </div>
    </div>
  );
}

function CenteredInput() {
  const { send, isStreaming } = useDashboard();
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef(null);
  const canSend = input.trim().length > 0 && !isStreaming;

  const handleSend = () => {
    if (!canSend) return;
    send(input);
    setInput("");
  };

  return (
    <div style={{
      display: "flex", gap: 8, padding: 8,
      background: "#FCFAFF", borderRadius: 12,
      border: `1px solid ${focused ? THEME.accent : "#DDD6FE"}`,
      boxShadow: focused
        ? `0 4px 16px ${THEME.accent}30`
        : "0 2px 8px rgba(31,38,33,0.06)",
      transition: "all 0.15s",
    }}>
      <input
        ref={inputRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") handleSend(); }}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder="Describe a dashboard..."
        disabled={isStreaming}
        className="dashboard-input"
        style={{
          flex: 1, padding: "14px 18px", border: "none",
          borderRadius: 8, fontSize: 14, outline: "none",
          background: "transparent", color: THEME.ink,
          fontFamily: "Inter, sans-serif",
        }}
      />
      <button
        onClick={handleSend}
        disabled={!canSend}
        style={{
          padding: "14px 18px", border: "none", borderRadius: 8,
          background: THEME.accent,
          color: THEME.white,
          opacity: canSend ? 1 : 0.45,
          display: "inline-flex", alignItems: "center", gap: 6,
          cursor: canSend ? "pointer" : "not-allowed",
          fontSize: 14, fontWeight: 700, flexShrink: 0,
          fontFamily: "Inter, sans-serif",
          transition: "all 0.15s",
        }}
        onMouseEnter={(e) => { if (canSend) e.currentTarget.style.background = "#6D28D9"; }}
        onMouseLeave={(e) => { if (canSend) e.currentTarget.style.background = THEME.accent; }}
      >
        <Send size={16} strokeWidth={2.5} />
      </button>
    </div>
  );
}

export function OpenUIDashboard({ library, starters = [] }) {
  return (
    <DashboardProvider>
      <DashboardLayout library={library} starters={starters} />
    </DashboardProvider>
  );
}
