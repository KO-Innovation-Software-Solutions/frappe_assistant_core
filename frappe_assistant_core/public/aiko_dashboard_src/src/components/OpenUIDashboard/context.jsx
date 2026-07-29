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

  // --- Strategy-A state: live Query cache + Renderer re-mount control.
  const queryMapRef = useRef({});          // canonical frontend key → live data
  const queriesMetaRef = useRef([]);       // [{key, tool, args, statementId}]
  const lastRefreshAtRef = useRef(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [lastRefreshAt, setLastRefreshAt] = useState(null);

  // Canonical, cross-platform stable key for (tool_name + args).  Backend
  // uses hashlib.sha1, frontend uses base64(JSON with sorted keys) — these
  // can never match directly, so we always translate via (tool,args) metadata.
  const makeCanonicalKey = useCallback((tool_name, args) => {
    const tn = String(tool_name || "");
    const a = (args && typeof args === "object") ? args : {};
    try {
      const stable = JSON.stringify(a, Object.keys(a).sort());
      return `${tn}::${btoa(unescape(encodeURIComponent(stable)))}`;
    } catch {
      // Fallback: naive stringification (acceptable as a cache key for the
      // life of this page load; collisions = re-fetch once, not data loss).
      return `${tn}::${JSON.stringify(a)}`;
    }
  }, []);

  // Tools whose result should be treated as a LIST OF ROWS for @Each/@Filter.
  // Their return shape is {success: true, data: [rows], count, total_count}.
  const ROW_LIST_TOOLS = new Set([
    "list_documents", "run_database_query", "search_documents",
    "search_doctype", "get_pending_approvals",
  ]);

  const THROW_AWAY_KEYS_ON_RESULT = new Set([
    // Strip success-flag boilerplate before we put anything into the cache
    // for the Renderer to read.  This prevents e.g. Count({..}) returning 3
    // for the number of keys in a status dict, when the user expected the
    // actual row count inside .data list.
    "success", "error", "error_type", "error_code", "execution_time",
    "audit_logged", "traceback", "message",
  ]);

  const normaliseToolResultForFrontend = useCallback((toolName, rawPayload) => {
    // rawPayload = whatever the backend execute_tool returned: the tool's
    // actual return dict (e.g. {success, label, value, groups, count, data}).
    if (rawPayload == null) return rawPayload;
    let out = rawPayload;
    // ---- For row-list tools: promote the data list to be the primary value
    if (ROW_LIST_TOOLS.has(toolName) && typeof out === "object") {
      const data = out.data;
      if (Array.isArray(data)) {
        // Decorate the rows array with sibling properties (label/value/count
        // etc.) so expressions like Query("run_database_query", ...).label
        // still resolve even though the "resolved Query" is a list.
        const extras = {};
        for (const [k, v] of Object.entries(out)) {
          if (THROW_AWAY_KEYS_ON_RESULT.has(k)) continue;
          extras[k] = v;
        }
        // Attach props directly onto the Array.  React / the Renderer do not
        // mutate this; they just read fields.
        const decorated = Array.from(data);
        Object.assign(decorated, extras);
        out = decorated;
      }
    } else if (typeof out === "object" && !Array.isArray(out)) {
      // Non-row tool (aggregate_documents / create_dashboard_chart / ...).
      // Expose it as a plain object with label/value/labels/values etc.,
      // but strip noisy boilerplate keys.
      const cleaned = {};
      for (const [k, v] of Object.entries(out)) {
        if (THROW_AWAY_KEYS_ON_RESULT.has(k)) continue;
        cleaned[k] = v;
      }
      // .label ← .labels alias, .value ← .values alias (and vice versa)
      // to accommodate both accessor shapes the LLM emits.
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

  // --- Strategy-A Query resolver. Called by Renderer via any of 4 possible prop
  // names (see DashboardCanvas). Also handles @Run(statementId) for targeted
  // Query refresh on button click.
  const queryResolver = useCallback((call) => {
    // @Run(queryRef) targeted refresh from DSL button clicks or @Run-based
    // re-execution.  `call` shape depends on how the Renderer encodes Run
    // events — Step 0 diagnostics will tell us exact payload.
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

    // --- Normal Query(tool, args) resolve on Renderer evaluation.
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
    if (Object.prototype.hasOwnProperty.call(cache, key) && cache[key] !== undefined) {
      return cache[key];
    }
    // Cache miss → fire async re-fetch, populate cache, force remount. Renderer
    // will see undefined this frame, then we bump refreshTick → Renderer
    // re-mounts and hits the cache on 2nd render.
    frappe.call({
      method: "frappe_assistant_core.api.assistant_api.execute_tool",
      args: { tool_name, arguments: args || {} },
      callback: (r) => {
        const raw = r.message?.result !== undefined
          ? r.message.result
          : r.message;
        queryMapRef.current[key] = normaliseToolResultForFrontend(tool_name, raw);
        // Also remember metadata entry (for @Run by statementId later)
        if (!queriesMetaRef.current.some((m) => m.tool === tool_name && JSON.stringify(m.args || {}) === JSON.stringify(args || {}))) {
          queriesMetaRef.current.push({ key, tool: tool_name, args: args || {}, statement_id: null });
        }
        setRefreshTick((n) => n + 1);
      },
      error: () => {
        // Store sentinel null so we don't retry this exact query every render
        // tick.  User can click Refresh to flush sentinels.
        queryMapRef.current[key] = null;
      },
    });
    return undefined;
  }, [makeCanonicalKey, normaliseToolResultForFrontend]);


  const refresh = useCallback(() => {
    if (isStreaming) return;
    setStage("Refreshing data…");

    // --- Phase 1: Strategy-A — run UNIQUE queries, get {queryMap, queries} back.
    frappe.call({
      method: "frappe_assistant_core.aiko.api.refresh_dashboard_queries",
      args: { thread_id: threadId.current, legacy_fallback: false },
      callback: (r) => {
        const msg = r.message;
        if (msg?.success) {
          // -------- BACKEND → FRONTEND KEY MAPPING STEP --------
          // Backend produces msg.queryMap = { <sha1>: <result> } AND
          // msg.queries = [{tool, args, key: <sha1>, ...}].
          // We re-index cache entries by our CANONICAL frontend key so the
          // resolver finds them regardless of hash algorithm mismatch.
          if (Array.isArray(msg.queries) && msg.queryMap && typeof msg.queryMap === "object") {
            for (const q of msg.queries) {
              const canonicalKey = makeCanonicalKey(q.tool, q.args || {});
              const backendVal = (msg.queryMap || {})[q.key];
              if (backendVal === undefined) continue;
              const normalised = normaliseToolResultForFrontend(q.tool, backendVal);
              queryMapRef.current[canonicalKey] = normalised;
              // Also enrich metadata.
              q._canonical_key = canonicalKey;
            }
          } else if (msg.queryMap && typeof msg.queryMap === "object") {
            // Old backend (no queries metadata): put values as-is under the
            // same keys they came in with; resolver will cache-miss on next
            // query and re-fetch with the canonical key as a fallback.
            queryMapRef.current = { ...queryMapRef.current, ...msg.queryMap };
          }
          if (Array.isArray(msg.queries)) {
            queriesMetaRef.current = msg.queries;
          }
          if (msg.refreshed_at) {
            lastRefreshAtRef.current = msg.refreshed_at;
            setLastRefreshAt(msg.refreshed_at);
          }
          // Force Renderer re-mount so it resolves Queries against fresh cache.
          setRefreshTick((n) => n + 1);
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

        // --- Phase 2: Strategy-B (legacy) literal replacement for dashboards
        // that DON'T have Query bindings. This handles Fuel Entry / Asset
        // Movements style panels where numbers are baked literals. Runs in
        // parallel and silently no-ops if there's nothing to refresh.
        try {
          frappe.call({
            method: "frappe_assistant_core.aiko.api.refresh_dashboard",
            args: { thread_id: threadId.current },
            callback: (r2) => {
              if (r2.message?.success && r2.message?.ui) {
                // If legacy produced a refreshed UI string, set it as
                // dashboardCode. Strategy-A Query values still win during
                // render via the resolveQuery cache for Query-bound KPIs —
                // the two pipelines update different, non-overlapping subsets
                // of displayed values.
                setDashboardCode(normalizeDsl(r2.message.ui));
              }
            },
            error: () => {},
          });
        } catch { /* ignore legacy errors */ }
      },
      error: () => {
        setStage("");
        // On total network/endpoint failure, still try the legacy path once
        // (it's a different code path and might still work).
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
  }, [isStreaming]);

  // --- Tool provider for @openuidev/react-lang Renderer.
  // The Renderer natively understands Query(tool, args, []) and calls
  // toolProvider[toolName](args) to resolve each one.  This Proxy maps
  // any tool name to an async function that fetches via execute_tool
  // and normalises the result shape for frontend components.
  const toolProvider = useMemo(() => new Proxy({}, {
    get: (_, toolName) => {
      if (typeof toolName !== "string") return undefined;
      return async (args) => {
        try {
          const response = await frappe.call({
            method: "frappe_assistant_core.api.assistant_api.execute_tool",
            args: { tool_name: toolName, arguments: args || {} },
          });
          const raw = response.message?.result !== undefined
            ? response.message.result
            : response.message;
          return normaliseToolResultForFrontend(toolName, raw);
        } catch (err) {
          console.error(`[toolProvider] ${toolName} failed`, err);
          return null;
        }
      };
    },
  }), [normaliseToolResultForFrontend]);

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