import { useEffect, useRef, useState } from "react";
import { MessageCircle } from "lucide-react";
import { MarkDownRenderer } from "@openuidev/react-ui";
import { useDashboard } from "./context";

const THEME = {
  accent: "#7C3AED",
  accentHover: "#6D28D9",
  accentTint: "#F5F3FF",
  accentTintDark: "#EDE9FE",
  accentBorder: "#DDD6FE",
  border: "#E5E7EB",
  green: "#7C3AED",
  greenSoft: "#8B5CF6",
  sage: "#A78BFA",
  amber: "#D99A3D",
  rust: "#B54A3F",
  ink: "#1F2621",
  paper: "#F6F5F9",
  white: "#FFFFFF",
};

function ToolCallBadge({ tool }) {
  const statusColor = tool.status === "completed" ? THEME.green
    : tool.status === "error" ? THEME.rust
    : THEME.amber;
  const statusLabel = tool.status === "completed" ? "✓"
    : tool.status === "error" ? "✗"
    : "⏳";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "2px 6px", borderRadius: 3, fontSize: 10, fontWeight: 600,
      background: statusColor + "15", color: statusColor,
      fontFamily: "Inter, sans-serif", letterSpacing: "0.02em",
    }}>
      {statusLabel} {tool.name || tool}
    </span>
  );
}

function AssistantMessage({ msg }) {
  return (
    <div style={{ marginRight: 20 }}>
      {msg.tools && msg.tools.length > 0 && (
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 3, marginBottom: 6,
        }}>
          {msg.tools.map((t, i) => <ToolCallBadge key={i} tool={t} />)}
        </div>
      )}
      {msg.text ? (
        <div style={{
          background: THEME.accentTint, border: `1px solid ${THEME.accentBorder}`,
          padding: "8px 12px", borderRadius: 4, fontSize: 13,
          lineHeight: 1.5, color: THEME.ink,
          fontFamily: "Inter, sans-serif",
        }}>
          <MarkDownRenderer textMarkdown={msg.text} />
        </div>
      ) : msg.hasCode ? null : (
        <div style={{ fontSize: 12, color: "#8A8478", fontStyle: "italic" }}>
          (empty response)
        </div>
      )}
      {msg.hasCode && (
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 4,
          padding: "2px 8px", borderRadius: 3, fontSize: 11, fontWeight: 700,
          background: THEME.green, color: "white", marginTop: msg.text ? 4 : 0,
          fontFamily: "Inter, sans-serif", letterSpacing: "0.02em",
        }}>✓ dashboard updated</div>
      )}
    </div>
  );
}

function StreamingIndicator({ elapsed, stage, toolCalls }) {
  const hasTools = toolCalls && toolCalls.length > 0;
  return (
    <div style={{ marginBottom: 12, marginRight: 20 }}>
      <div style={{
        background: `linear-gradient(90deg, ${THEME.accentTint}, #EDE9FE)`,
        border: `1px solid ${THEME.accentBorder}`,
        padding: "8px 12px", borderRadius: 4, fontSize: 13, color: THEME.accent, fontWeight: 600,
        fontFamily: "Inter, sans-serif",
      }}>
        {elapsed ? `${(elapsed / 1000).toFixed(1)}s — ` : ""}
        {hasTools ? `🔍 Querying ${toolCalls.length} tool(s)...` : (stage || "thinking...")}
      </div>
      {hasTools && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 3, marginTop: 4 }}>
          {toolCalls.map((t, i) => <ToolCallBadge key={i} tool={t} />)}
        </div>
      )}
    </div>
  );
}

export function ConversationPanel() {
  const {
    conversation, isStreaming, streamingText, streamingHasCode,
    elapsed, dashboardCode, send, stage, toolCalls,
  } = useDashboard();
  const [input, setInput] = useState("");
  const inputRef = useRef(null);
  const chatEndRef = useRef(null);

  const hasDashboard = dashboardCode !== null;
  const canSend = input.trim().length > 0 && !isStreaming;

  useEffect(() => { inputRef.current?.focus(); }, [isStreaming]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [conversation]);

  const handleSend = () => {
    if (!canSend) return;
    send(input);
    setInput("");
  };

  return (
    <div style={{
      width: 340, minWidth: 340, borderLeft: `1px solid ${THEME.border}`,
      background: THEME.white, display: "flex", flexDirection: "column",
      boxShadow: "-8px 0 24px rgba(31,38,33,0.03)",
    }}>
      <div style={{
        padding: "13px 16px", background: THEME.white,
        borderBottom: `1px solid ${THEME.border}`,
        fontSize: 13, fontWeight: 700, color: THEME.ink,
        letterSpacing: "-0.01em", display: "flex", alignItems: "center", gap: 6,
        fontFamily: "Fraunces, Georgia, serif",
      }}>
        <MessageCircle size={16} stroke={THEME.accent} strokeWidth={1.5} /> Conversation
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "12px 16px" }}>
        {conversation.map((msg, i) => (
          <div key={i} style={{ marginBottom: 12 }}>
            {msg.role === "user" ? (
              <div style={{
                background: THEME.accent, color: THEME.white, padding: "8px 12px",
                borderRadius: 4, fontSize: 13, lineHeight: 1.4,
                marginLeft: 40, fontFamily: "Inter, sans-serif",
              }}>{msg.content}</div>
            ) : (
              <AssistantMessage msg={msg} />
            )}
          </div>
        ))}

        {isStreaming && (
          <StreamingIndicator elapsed={elapsed} stage={stage} toolCalls={toolCalls} />
        )}
        <div ref={chatEndRef} />
      </div>

      <div style={{ padding: "12px 16px", borderTop: `1px solid ${THEME.border}`, background: THEME.white }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSend(); }}
            placeholder={hasDashboard ? "Ask or edit..." : "Describe a dashboard..."}
            disabled={isStreaming}
            style={{
              flex: 1, padding: "8px 12px", border: `1px solid ${THEME.accentBorder}`,
              borderRadius: 3, fontSize: 13, outline: "none", fontFamily: "Inter, sans-serif",
              transition: "border-color 0.15s, box-shadow 0.15s",
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = THEME.accent;
              e.currentTarget.style.boxShadow = `0 0 0 3px ${THEME.accentTintDark}`;
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = THEME.accentBorder;
              e.currentTarget.style.boxShadow = "none";
            }}
          />
          <button
            onClick={handleSend}
            disabled={!canSend}
            style={{
              padding: "8px 16px", border: "none", borderRadius: 8,
              background: THEME.accent, color: THEME.white,
              opacity: canSend ? 1 : 0.45,
              cursor: canSend ? "pointer" : "not-allowed",
              fontSize: 13, fontWeight: 700, fontFamily: "Inter, sans-serif",
              transition: "all 0.15s",
            }}
            onMouseEnter={(e) => { if (canSend) e.currentTarget.style.background = THEME.accentHover; }}
            onMouseLeave={(e) => { if (canSend) e.currentTarget.style.background = THEME.accent; }}
          >{isStreaming ? "..." : "Send"}</button>
        </div>
      </div>
    </div>
  );
}
