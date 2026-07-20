import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

const DashboardContext = createContext(null);

export function useDashboard() {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error("useDashboard must be used within DashboardProvider");
  return ctx;
}

function looksLikeKeywordArgs(code) {
  if (!code || typeof code !== "string") return false;
  return /\b[A-Za-z_][A-Za-z0-9_]*\(\s*[a-zA-Z_][a-zA-Z0-9_]*\s*:/.test(code);
}

function normalizeDsl(code) {
  if (!code || typeof code !== "string") return code;
  let t = code.trim();
  if (t.startsWith("```")) {
    const end = t.indexOf("```", 3);
    if (end !== -1) t = t.slice(3, end).trim();
    const nl = t.indexOf("\n");
    if (nl > -1) t = t.slice(nl).trim();
  }
  if (t.startsWith("=")) t = t.slice(1).trim();
  const respMatch = t.match(/^[a-zA-Z_$][a-zA-Z0-9_$]*\s*=\s*/);
  if (respMatch) return t;
  const lines = t.split("\n");
  for (const line of lines) {
    const l = line.trim();
    if (/^[a-zA-Z_$][a-zA-Z0-9_$]*\s*=\s*/.test(l)) return l;
    if (/^(Stack|Card|Table|TextContent|BarChart|LineChart|PieChart|KpiCard)\s*\(/.test(l)) {
      return "root = " + l;
    }
  }
  if (/^(Stack|Card|Table|TextContent|BarChart|LineChart|PieChart|KpiCard)\s*\(/.test(t)) {
    return "root = " + t;
  }
  return "root = " + t;
}

function getOrCreateThreadId() {
  let id = localStorage.getItem("aiko_dashboard_thread_id");
  if (!id) {
    id = frappe.utils.get_random(12);
    localStorage.setItem("aiko_dashboard_thread_id", id);
  }
  return id;
}

export function DashboardProvider({ children }) {
  const [dashboardCode, setDashboardCode] = useState(null);
  const [conversation, setConversation] = useState([]);
  const [streamingText, setStreamingText] = useState("");
  const [streamingHasCode, setStreamingHasCode] = useState(false);
  const [startTime, setStartTime] = useState(null);
  const [elapsed, setElapsed] = useState(null);
  const [stage, setStage] = useState("");
  const [toolCalls, setToolCalls] = useState([]);
  const [currentThreadId, setCurrentThreadId] = useState(getOrCreateThreadId());
  const [showHistory, setShowHistory] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [showMailMenu, setShowMailMenu] = useState(false);
  const [showScheduleMenu, setShowScheduleMenu] = useState(false);
  const [mailTo, setMailTo] = useState("");
  const [mailFormat, setMailFormat] = useState("png");
  const [mailStatus, setMailStatus] = useState("");
  const [pendingThreads, setPendingThreads] = useState({});
  const threadId = useRef(currentThreadId);
  const abortRef = useRef(null);
  const lastPromptRef = useRef(null);
  useEffect(() => {
    frappe.call({
      method: "frappe_assistant_core.aiko.api.get_dashboard_session_messages",
      args: { thread_id: currentThreadId },
      callback: (r) => {
        const data = r.message;
        if (!data || !data.messages || data.messages.length === 0) return;
        let latestUi = null;
        const rebuilt = data.messages.map((m) => {
          if (m.role === "assistant") {
            const hasCode = !!m.ui;
            if (hasCode) latestUi = m.ui;
            return { role: "assistant", content: m.ui || m.content, text: m.content || undefined, hasCode };
          }
          return { role: "user", content: m.content, hasCode: false };
        });
        setConversation(rebuilt);
        setDashboardCode(latestUi ? normalizeDsl(latestUi) : null);
      },
      error: () => {
      },
    });
  }, []);
  const isStreaming = !!pendingThreads[currentThreadId];

  useEffect(() => {
    if (!isStreaming || !startTime) return;
    const iv = setInterval(() => setElapsed(Date.now() - startTime), 100);
    return () => clearInterval(iv);
  }, [isStreaming, startTime]);

  useEffect(() => {
    const stageHandler = (data) => {
      setPendingThreads((prev) => {
        if (!prev[data.thread_id] || prev[data.thread_id] !== data.request_id) return prev;
        return prev;
      });
      if (data.thread_id === threadId.current) {
        setStage(data.stage);
        if (data.tool_calls) setToolCalls(data.tool_calls);
        setStartTime((prevStart) => prevStart || Date.now());
      }
    };

    const doneHandler = (data) => {
      setPendingThreads((prev) => {
        if (prev[data.thread_id] !== data.request_id) return prev;
        const next = { ...prev };
        delete next[data.thread_id];
        return next;
      });
      if (data.thread_id !== threadId.current) return;

      setStreamingText("");
      setStartTime(null);
      setElapsed(null);

      if (data.success) {
        const rawText = data.data || "";
        const rawUi = data.ui || "";
        const hasCode = !!rawUi;
        const hasText = !!rawText;
        const toolsUsed = data.tool_calls || [];

        setConversation((prev) => [
          ...prev,
          {
            role: "assistant",
            content: rawUi || rawText,
            text: hasText ? rawText : undefined,
            hasCode,
            tools: toolsUsed,
            suggestions: data.suggestions || [],
          },
        ]);

        if (hasCode && rawUi) {
          if (looksLikeKeywordArgs(rawUi)) {
            setConversation((prev) => [
              ...prev,
              {
                role: "assistant",
                content: "The generated dashboard used invalid syntax (keyword arguments) and could not be rendered. Try refreshing.",
                text: "The generated dashboard used invalid syntax (keyword arguments) and could not be rendered. Try refreshing.",
                hasCode: false,
              },
            ]);
          } else {
            setDashboardCode(normalizeDsl(rawUi));
          }
        }
      } else {
        setConversation((prev) => [
          ...prev,
          { role: "assistant", content: data.error || "An error occurred.", text: data.error || "An error occurred.", hasCode: false },
        ]);
      }
    };

    frappe.realtime.on("aiko_dashboard_stage", stageHandler);
    frappe.realtime.on("aiko_dashboard_done", doneHandler);
    return () => {
      frappe.realtime.off("aiko_dashboard_stage", stageHandler);
      frappe.realtime.off("aiko_dashboard_done", doneHandler);
    };
  }, []);

  const send = useCallback(
    (text) => {
      if (!text.trim()) return;
      if (pendingThreads[threadId.current]) return;
      const trimmed = text.trim();

      setStreamingText("");
      setStreamingHasCode(false);
      setStage("Thinking…");
      setStartTime(null);
      setElapsed(null);
      setToolCalls([]);
      lastPromptRef.current = trimmed;

      const userMsg = { role: "user", content: trimmed, hasCode: false };
      setConversation((prev) => [...prev, userMsg]);

      const requestId = frappe.utils.get_random(10);
      const thisThread = threadId.current;

      setPendingThreads((prev) => ({ ...prev, [thisThread]: requestId }));

      frappe.call({
        method: "frappe_assistant_core.aiko.api.dashboard_chat",
        args: { message: trimmed, thread_id: thisThread, request_id: requestId },
        callback: (r) => {
          if (!r.message || !r.message.success) {
            setPendingThreads((prev) => {
              const next = { ...prev };
              delete next[thisThread];
              return next;
            });
            if (thisThread === threadId.current) {
              setConversation((prev) => [
                ...prev,
                { role: "assistant", content: "Could not start the request.", text: "Could not start the request.", hasCode: false },
              ]);
            }
          }
        },
        error: () => {
          setPendingThreads((prev) => {
            const next = { ...prev };
            delete next[thisThread];
            return next;
          });
          if (thisThread === threadId.current) {
            setConversation((prev) => [
              ...prev,
              { role: "assistant", content: "Network error or server unavailable.", text: "Network error or server unavailable.", hasCode: false },
            ]);
          }
        },
      });
    },
    [pendingThreads],
  );

  const refresh = useCallback(() => {
    if (!lastPromptRef.current || isStreaming) return;
    send(lastPromptRef.current);
  }, [send, isStreaming]);
  const loadSession = useCallback((newThreadId) => {
    threadId.current = newThreadId;
    localStorage.setItem("aiko_dashboard_thread_id", newThreadId);
    setCurrentThreadId(newThreadId);
    setStage(pendingThreads[newThreadId] ? "Still generating…" : "");

    frappe.call({
      method: "frappe_assistant_core.aiko.api.get_dashboard_session_messages",
      args: { thread_id: newThreadId },
      callback: (r) => {
        const data = r.message;
        if (!data) return;
        let latestUi = null;
        const rebuilt = (data.messages || []).map((m) => {
          if (m.role === "assistant") {
            const hasCode = !!m.ui;
            if (hasCode) latestUi = m.ui;
            return { role: "assistant", content: m.ui || m.content, text: m.content || undefined, hasCode };
          }
          return { role: "user", content: m.content, hasCode: false };
        });
        setConversation(rebuilt);
        setDashboardCode(latestUi ? normalizeDsl(latestUi) : null);
        lastPromptRef.current = null;
      },
      error: () => {
        setConversation((prev) => [...prev, {
          role: "assistant", content: "Could not load that session.",
          text: "Could not load that session.", hasCode: false,
        }]);
      },
    });
  }, [pendingThreads]);

  const startNewSession = useCallback(() => {
    const newId = frappe.utils.get_random(12);
    threadId.current = newId;
    localStorage.setItem("aiko_dashboard_thread_id", newId);
    setCurrentThreadId(newId);
    setConversation([]);
    setDashboardCode(null);
    lastPromptRef.current = null;
  }, []);

  const clear = () => {
    abortRef.current?.abort();
    setDashboardCode(null);
    setConversation([]);
    setStreamingText("");
    setStreamingHasCode(false);
    setStartTime(null);
    setElapsed(null);
    setToolCalls([]);
  };

  return (
    <DashboardContext.Provider
      value={{
        conversation,
        dashboardCode,
        isStreaming,
        streamingText,
        streamingHasCode,
        elapsed,
        stage,
        toolCalls,
        send,
        clear,
        refresh,
        canRefresh: !!lastPromptRef.current && !isStreaming,
        currentThreadId,
        loadSession,
        startNewSession,
        pendingThreads,
        showHistory, setShowHistory,
        showExportMenu, setShowExportMenu,
        showMailMenu, setShowMailMenu,
        showScheduleMenu, setShowScheduleMenu,
        mailTo, setMailTo,
        mailFormat, setMailFormat,
        mailStatus, setMailStatus,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
}