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
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [streamingHasCode, setStreamingHasCode] = useState(false);
  const [startTime, setStartTime] = useState(null);
  const [elapsed, setElapsed] = useState(null);
  const [conversation, setConversation] = useState([]);
  const [stage, setStage] = useState("");
  const [toolCalls, setToolCalls] = useState([]);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [showMailMenu, setShowMailMenu] = useState(false);
  const [showScheduleMenu, setShowScheduleMenu] = useState(false);
  const [mailTo, setMailTo] = useState("");
  const [mailFormat, setMailFormat] = useState("png");
  const [mailStatus, setMailStatus] = useState("");
  const threadId = useRef(getOrCreateThreadId());
  const abortRef = useRef(null);
  const lastPromptRef = useRef(null);

  useEffect(() => {
    if (!isStreaming || !startTime) return;
    const iv = setInterval(() => setElapsed(Date.now() - startTime), 100);
    return () => clearInterval(iv);
  }, [isStreaming, startTime]);

  const send = useCallback(
    async (text) => {
      if (!text.trim() || isStreaming) return;
      const trimmed = text.trim();

      setIsStreaming(true);
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
      let streamStartTime = null;

      const stageHandler = (data) => {
        if (data.thread_id !== threadId.current) return;
        if (data.request_id !== requestId) return;
        setStage(data.stage);

        if (data.tool_calls) {
          setToolCalls(data.tool_calls);
        }

        if (!streamStartTime) { streamStartTime = Date.now(); setStartTime(streamStartTime); }
      };

      const doneHandler = (data) => {
        if (data.thread_id !== threadId.current) return;
        if (data.request_id !== requestId) return;
        cleanup();
        setIsStreaming(false);
        setStreamingText("");
        if (streamStartTime) setElapsed(Date.now() - streamStartTime);

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
          const errMsg = {
            role: "assistant",
            content: data.error || "An error occurred.",
            text: data.error || "An error occurred.",
            hasCode: false,
          };
          setConversation((prev) => [...prev, errMsg]);
        }
      };

      function cleanup() {
        frappe.realtime.off("aiko_dashboard_stage", stageHandler);
        frappe.realtime.off("aiko_dashboard_done", doneHandler);
      }

      frappe.realtime.on("aiko_dashboard_stage", stageHandler);
      frappe.realtime.on("aiko_dashboard_done", doneHandler);

      frappe.call({
        method: "frappe_assistant_core.aiko.api.dashboard_chat",
        args: { message: trimmed, thread_id: threadId.current, request_id: requestId },
        callback: (r) => {
          if (!r.message || !r.message.success) {
            cleanup();
            setIsStreaming(false);
            setStreamingText("");
            setConversation((prev) => [
              ...prev,
              { role: "assistant", content: "Could not start the request.", text: "Could not start the request.", hasCode: false },
            ]);
          }
        },
        error: () => {
          cleanup();
          setIsStreaming(false);
          setStreamingText("");
          setConversation((prev) => [
            ...prev,
            { role: "assistant", content: "Network error or server unavailable.", text: "Network error or server unavailable.", hasCode: false },
          ]);
        },
      });
    },
    [isStreaming],
  );

  const refresh = useCallback(() => {
    if (!lastPromptRef.current || isStreaming) return;
    send(lastPromptRef.current);
  }, [send, isStreaming]);

  const clear = () => {
    abortRef.current?.abort();
    setDashboardCode(null);
    setConversation([]);
    setIsStreaming(false);
    setStreamingText("");
    setStreamingHasCode(false);
    setStartTime(null);
    setElapsed(null);
    setToolCalls([]);
    setShowExportMenu(false);
    setShowMailMenu(false);
    setShowScheduleMenu(false);
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
