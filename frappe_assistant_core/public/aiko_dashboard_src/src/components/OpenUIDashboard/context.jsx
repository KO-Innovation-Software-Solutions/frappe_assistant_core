import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

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
function unwrapRegistryWrapper(value) {
  if (value && typeof value === "object" && !Array.isArray(value) && "result" in value) {
    const inner = value.result;
    if (inner !== undefined && inner !== null) return inner;
  }
  return value;
}
function cleanCachedResult(value) {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "string") return value;
  const t = value.trim();
  if (t.startsWith("{") || t.startsWith("[")) {
    try {
      return unwrapRegistryWrapper(JSON.parse(t));
    } catch { /* fall through to repr parsing */ }
  }
  const m = t.match(/text=['"]([\s\S]*?)['"]\s+(annotations|meta)\s*=/);
  if (m) {
    const blob = m[1].replace(/\\'/g, "'");
    try {
      return unwrapRegistryWrapper(JSON.parse(blob));
    } catch { /* ignore */ }
  }
  try {
    const arr = JSON.parse(t);
    if (Array.isArray(arr)) {
      const texts = arr
        .filter((i) => i && typeof i === "object" && i.type === "text" && typeof i.text === "string")
        .map((i) => i.text);
      if (texts.length) {
        const payload = texts.join("\n");
        try {
          return unwrapRegistryWrapper(JSON.parse(payload));
        } catch {
          return texts.length > 1 ? payload : texts[0];
        }
      }
    }
  } catch { /* ignore */ }

  return undefined;
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

  const queryMapRef = useRef({});
  const queriesMetaRef = useRef([]);
  const [refreshTick, setRefreshTick] = useState(0);
  const [lastRefreshAt, setLastRefreshAt] = useState(null);
  const makeCanonicalKey = useCallback((tool_name, args) => {
    const tn = String(tool_name || "");
    const a = (args && typeof args === "object") ? args : {};
    try {
      const stable = JSON.stringify(a, Object.keys(a).sort());
      return `${tn}::${btoa(unescape(encodeURIComponent(stable)))}`;
    } catch {
      return `${tn}::${JSON.stringify(a)}`;
    }
  }, []);
  const ROW_LIST_TOOLS = new Set([
    "list_documents", "run_database_query", "search_documents",
    "search_doctype", "get_pending_approvals",
  ]);

  const THROW_AWAY_KEYS_ON_RESULT = new Set([
    "success", "error", "error_type", "error_code", "execution_time",
    "audit_logged", "traceback", "message",
  ]);

  const normaliseToolResultForFrontend = useCallback((toolName, rawPayload) => {
    if (rawPayload == null) return rawPayload;
    let out = rawPayload;
    if (ROW_LIST_TOOLS.has(toolName) && typeof out === "object") {
      const data = out.data;
      if (Array.isArray(data)) {
        const extras = {};
        for (const [k, v] of Object.entries(out)) {
          if (THROW_AWAY_KEYS_ON_RESULT.has(k)) continue;
          extras[k] = v;
        }
        const decorated = Array.from(data);
        Object.assign(decorated, extras);
        out = decorated;
      }
    } else if (typeof out === "object" && !Array.isArray(out)) {
      const cleaned = {};
      for (const [k, v] of Object.entries(out)) {
        if (THROW_AWAY_KEYS_ON_RESULT.has(k)) continue;
        cleaned[k] = v;
      }
      if ("label" in cleaned && !("labels" in cleaned)) cleaned.labels = cleaned.label;
      if ("labels" in cleaned && !("label" in cleaned)) cleaned.label = cleaned.labels;
      if ("value" in cleaned && !("values" in cleaned)) cleaned.values = cleaned.value;
      if ("values" in cleaned && !("value" in cleaned)) cleaned.value = cleaned.values;
      out = cleaned;
    }
    return out;
  }, []);

  const threadId = useRef(currentThreadId);
  const abortRef = useRef(null);
  const lastPromptRef = useRef(null);
  // Mirror of pendingThreads kept in a ref so guards/handlers can read the
  // current value synchronously (React state is stale within the same tick,
  // which allowed a fast double-click to enqueue two jobs for one thread).
  const pendingThreadsRef = useRef({});

  const updatePendingThreads = useCallback((updater) => {
    // Update the ref synchronously so guards read the fresh value even
    // within the same tick (React's state updater only runs at render time).
    const next = updater(pendingThreadsRef.current);
    pendingThreadsRef.current = next;
    setPendingThreads(next);
  }, []);

  // Pre-fills queryMapRef/queriesMetaRef from a session's saved
  // tool_calls_snapshot so Query(tool, args, []) bindings in a loaded
  // dashboard resolve from cache instead of every switch re-firing every
  // tool call live. Purely additive to the cache — never clears it, so it
  // can't clobber data from whatever thread you were just looking at.
  const hydrateQueryCache = useCallback((messages) => {
    if (!Array.isArray(messages)) return;
    for (const m of messages) {
      if (m.role !== "assistant" || !m.tool_calls_snapshot) continue;
      let calls;
      try {
        calls = JSON.parse(m.tool_calls_snapshot);
      } catch {
        continue;
      }
      if (!Array.isArray(calls)) continue;
      for (const c of calls) {
        const toolName = c?.name;
        const args = c?.args || {};
        if (!toolName) continue;
        const key = makeCanonicalKey(toolName, args);
        if (queryMapRef.current[key] !== undefined) continue; // don't clobber a live/refreshed value
        const clean = cleanCachedResult(c?.result);
        if (clean !== undefined) {
          queryMapRef.current[key] = normaliseToolResultForFrontend(toolName, clean);
        }
        if (!queriesMetaRef.current.some((q) => q.tool === toolName && JSON.stringify(q.args || {}) === JSON.stringify(args))) {
          queriesMetaRef.current.push({ key, tool: toolName, args, statement_id: null });
        }
      }
    }
  }, [makeCanonicalKey, normaliseToolResultForFrontend]);

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
        hydrateQueryCache(data.messages);
        setConversation(rebuilt);
        setDashboardCode(latestUi ? normalizeDsl(latestUi) : null);
        setRefreshTick((n) => n + 1);
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
      if (pendingThreadsRef.current[data.thread_id] !== data.request_id) return;
      if (data.thread_id === threadId.current) {
        setStage(data.stage);
        if (data.tool_calls) setToolCalls(data.tool_calls);
        setStartTime((prevStart) => prevStart || Date.now());
      }
    };

    const doneHandler = (data) => {
      if (pendingThreadsRef.current[data.thread_id] !== data.request_id) return;
      updatePendingThreads((prev) => {
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
        const invalid = hasCode && rawUi && looksLikeKeywordArgs(rawUi);
        const content = invalid
          ? "The generated dashboard used invalid syntax (keyword arguments) and could not be rendered. Try refreshing."
          : (rawUi || rawText);

        setConversation((prev) => [
          ...prev,
          {
            role: "assistant",
            content,
            text: invalid ? content : (hasText ? rawText : undefined),
            hasCode: invalid ? false : hasCode,
            tools: toolsUsed,
            suggestions: data.suggestions || [],
          },
        ]);

        if (hasCode && rawUi && !invalid) {
          setDashboardCode(normalizeDsl(rawUi));
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
      if (pendingThreadsRef.current[threadId.current]) return;
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

      const controller = new AbortController();
      abortRef.current = controller;

      updatePendingThreads((prev) => ({ ...prev, [thisThread]: requestId }));

      frappe.call({
        method: "frappe_assistant_core.aiko.api.dashboard_chat",
        args: { message: trimmed, thread_id: thisThread, request_id: requestId },
        callback: (r) => {
          if (controller.signal.aborted) return;
          if (!r.message || !r.message.success) {
            updatePendingThreads((prev) => {
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
          if (controller.signal.aborted) return;
          updatePendingThreads((prev) => {
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
    [updatePendingThreads],
  );
  // Stops generation for a given thread (defaults to the currently active
  // one). Fires cancel_chat (already used by the chat surface's stop
  // button) with that thread's in-flight request_id, then optimistically
  // clears pendingThreads for it so the UI doesn't wait on a realtime event
  // that a cancelled backend job may be slow to publish.
  const stopGeneration = useCallback((targetThreadId) => {
    const tId = targetThreadId || threadId.current;
    const requestId = pendingThreadsRef.current[tId];
    if (!requestId) return;
    frappe.call({
      method: "frappe_assistant_core.aiko.api.cancel_chat",
      args: { request_id: requestId },
    });
    // Optimistically drop the tracked request so the UI resets immediately.
    // cancel_chat also hard-kills the RQ job, so a done event may never
    // arrive; and if one does, doneHandler ignores it because the
    // request_id no longer matches. A stale/second job for this thread is
    // ignored by the request_id filter in stageHandler/doneHandler.
    updatePendingThreads((prev) => {
      const next = { ...prev };
      delete next[tId];
      return next;
    });
    if (tId === threadId.current) {
      setStage("");
      setStartTime(null);
      setElapsed(null);
      setToolCalls([]);
      setConversation((prev) => [
        ...prev,
        { role: "assistant", content: "Stopped.", text: "Stopped.", hasCode: false },
      ]);
    }
  }, [updatePendingThreads]);

  const unwrapCallToolShape = useCallback((call) => {
    if (
      call && typeof call === "object" &&
      (call.name === "callTool" || call.tool === "callTool") &&
      call.arguments && typeof call.arguments === "object" &&
      call.arguments.name
    ) {
      return { tool: call.arguments.name, args: call.arguments.arguments || {} };
    }
    return call;
  }, []);
  const queryResolver = useCallback((call) => {
    call = unwrapCallToolShape(call);
    if (call?._kind === "run" || call?.kind === "run") {
      const sid = call.statementId ?? call?.statement_id;
      if (sid) {
        const meta = queriesMetaRef.current.find(
          (q) => (q.statement_id === sid || q.statementId === sid)
        );
        if (meta && meta.tool) {
          const canonicalKey = makeCanonicalKey(meta.tool, meta.args || {});
          frappe.call({
            method: "frappe_assistant_core.api.assistant_api.execute_tool",
            args: { tool_name: meta.tool, arguments: meta.args || {} },
            callback: (r) => {
              const raw = r.message?.result !== undefined
                ? r.message.result
                : r.message;
              queryMapRef.current[canonicalKey] = normaliseToolResultForFrontend(meta.tool, raw);
              queriesMetaRef.current = queriesMetaRef.current.map((q) =>
                (q.key === meta.key || q.statement_id === sid || q.statementId === sid)
                  ? { ...q, key: canonicalKey }
                  : q
              );
              setRefreshTick((n) => n + 1);
            },
          });
        }
      }
      return undefined;
    }

    let tool_name = call?.tool ?? call?.toolName ?? call?.name ?? call?.callee ?? null;
    let args      = call?.args ?? call?.arguments ?? call?.params ?? call?.input ?? call?.options ?? {};
    if (typeof call === "string") tool_name = call;
    if (!tool_name) {
      // eslint-disable-next-line no-console
      console.warn("[queryResolver] can't determine tool_name from call", call);
      return undefined;
    }
    const key = makeCanonicalKey(tool_name, args);
    const cache = queryMapRef.current || {};
    const cached = cleanCachedResult(cache[key]);
    if (cached !== undefined) {
      return cached;
    }
    frappe.call({
      method: "frappe_assistant_core.api.assistant_api.execute_tool",
      args: { tool_name, arguments: args || {} },
      callback: (r) => {
        const raw = r.message?.result !== undefined
          ? r.message.result
          : r.message;
        queryMapRef.current[key] = normaliseToolResultForFrontend(tool_name, raw);
        if (!queriesMetaRef.current.some((m) => m.tool === tool_name && JSON.stringify(m.args || {}) === JSON.stringify(args || {}))) {
          queriesMetaRef.current.push({ key, tool: tool_name, args: args || {}, statement_id: null });
        }
        setRefreshTick((n) => n + 1);
      },
      error: () => {
        delete queryMapRef.current[key];
      },
    });
    return undefined;
  }, [makeCanonicalKey, normaliseToolResultForFrontend, unwrapCallToolShape]);


  const applyRefreshResult = useCallback((msg) => {
    if (!msg?.success) return false;
    if (Array.isArray(msg.queries) && msg.queryMap) {
      for (const q of msg.queries) {
        const canonicalKey = makeCanonicalKey(q.tool, q.args || {});
        const backendVal = msg.queryMap[q.key];
        if (backendVal === undefined) continue;
        queryMapRef.current[canonicalKey] = normaliseToolResultForFrontend(q.tool, backendVal);
        q._canonical_key = canonicalKey;
      }
      queriesMetaRef.current = msg.queries;
    }
    if (msg.refreshed_at) setLastRefreshAt(msg.refreshed_at);
    setRefreshTick((n) => n + 1);
    return true;
  }, [makeCanonicalKey, normaliseToolResultForFrontend]);


  const refresh = useCallback(() => {
    if (isStreaming) return;
    setStage("Refreshing data…");
    frappe.call({
      method: "frappe_assistant_core.aiko.api.refresh_dashboard_queries",
      args: { thread_id: threadId.current, legacy_fallback: false },
      callback: (r) => {
        const msg = r.message;
        if (applyRefreshResult(msg)) {
          setStage("");
        } else {
          setStage("");
          setConversation((prev) => [...prev, {
            role: "assistant",
            content: msg?.error || "Could not refresh live queries.",
            text: msg?.error || "Could not refresh live queries.",
            hasCode: false,
          }]);
        }
        try {
          frappe.call({
            method: "frappe_assistant_core.aiko.api.refresh_dashboard",
            args: { thread_id: threadId.current },
            callback: (r2) => {
              if (r2.message?.success && r2.message?.ui) {
                setDashboardCode(normalizeDsl(r2.message.ui));
              }
            },
            error: () => {},
          });
        } catch { /* ignore legacy errors */ }
      },
      error: () => {
        setStage("");
        try {
          frappe.call({
            method: "frappe_assistant_core.aiko.api.refresh_dashboard",
            args: { thread_id: threadId.current },
            callback: (r) => {
              if (r.message?.success && r.message?.ui) {
                setDashboardCode(normalizeDsl(r.message.ui));
              }
            },
            error: () => {},
          });
        } catch {}
      },
    });
  }, [isStreaming, applyRefreshResult]);

  const toolProvider = useMemo(() => ({
  callTool: async (toolName, args) => {
    if (toolName && typeof toolName === "object") {
      args = toolName.arguments ?? toolName.args ?? {};
      toolName = toolName.name ?? toolName.tool ?? toolName.toolName ?? "";
    }
    let realToolName = toolName;
    let realArgs = args || {};
    if (toolName === "callTool" && realArgs && typeof realArgs === "object" && realArgs.name) {
      realToolName = realArgs.name;
      realArgs = realArgs.arguments || {};
    }

    const canonicalKey = makeCanonicalKey(realToolName, realArgs);
    const cached = cleanCachedResult(queryMapRef.current[canonicalKey]);
    if (cached !== undefined) {
      return { isError: false, content: [{ type: "text", text: JSON.stringify(cached) }] };
    }

    try {
      const r = await new Promise((resolve, reject) => {
        frappe.call({
          method: "frappe_assistant_core.api.assistant_api.execute_tool",
          args: { tool_name: realToolName, arguments: realArgs },
          callback: resolve,
          error: reject,
        });
      });
      const raw = r.message?.result !== undefined ? r.message.result : r.message;
      const normalised = normaliseToolResultForFrontend(realToolName, raw);
      queryMapRef.current[canonicalKey] = normalised;
      setRefreshTick((n) => n + 1);
      return { isError: false, content: [{ type: "text", text: JSON.stringify(normalised) }] };
    } catch (err) {
      console.error(`[toolProvider] ${realToolName} failed`, err);
      return { isError: true, content: [{ type: "text", text: String(err?.message || err) }] };
    }
  },
}), [normaliseToolResultForFrontend, makeCanonicalKey]);

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
        hydrateQueryCache(data.messages || []);
        setConversation(rebuilt);
        setDashboardCode(latestUi ? normalizeDsl(latestUi) : null);
        setRefreshTick((n) => n + 1);
        lastPromptRef.current = null;
      },
      error: () => {
        setConversation((prev) => [...prev, {
          role: "assistant", content: "Could not load that session.",
          text: "Could not load that session.", hasCode: false,
        }]);
      },
    });
  }, [pendingThreads, hydrateQueryCache]);

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
    abortRef.current = null;
    // Drop the tracked in-flight request so late realtime events
    // (aiko_dashboard_stage/aiko_dashboard_done) are rejected by the
    // request_id guard and never land into the cleared conversation.
    updatePendingThreads((prev) => {
      const next = { ...prev };
      delete next[threadId.current];
      return next;
    });
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
        stopGeneration,
        clear,
        refresh,
        applyRefreshResult,
        canRefresh: dashboardCode !== null && !isStreaming,
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
        queryResolver,
        refreshTick,
        lastRefreshAt,
        toolProvider,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
}