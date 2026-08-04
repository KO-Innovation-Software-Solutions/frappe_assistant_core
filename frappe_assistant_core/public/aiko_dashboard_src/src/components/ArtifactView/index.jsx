import { useEffect, useRef, useState, useCallback } from "react";
import { Renderer } from "@openuidev/react-lang";
import { ThemeProvider } from "@openuidev/react-ui";
import {
  PanelLeftClose, PanelLeft, RotateCw, Download,
  ImageIcon, FileText, LayoutTemplate, Search, Plus, Clock,
} from "lucide-react";
import { library } from "../../library";

const COLORS = {
  text: "#1F2621",
  textMuted: "#8A8478",
  textMutedSoft: "#A9A296",
  border: "#E5E7EB",
  primary: "#7C3AED",
  primaryHover: "#6D28D9",
  hoverBg: "#FAFAFA",
  activeBg: "#F6F5F9",
};

const FONT_UI = "Inter, sans-serif";
const FONT_MONO = "IBM Plex Mono, monospace";
const FONT_DISPLAY = "Fraunces, Georgia, serif";

let stylesInjected = false;
function ensureGlobalStyles() {
  if (stylesInjected) return;
  stylesInjected = true;
  const style = document.createElement("style");
  style.textContent = `
    @keyframes openui-spin { to { transform: rotate(360deg); } }
    @keyframes openui-fade-in { from { opacity: 0; } to { opacity: 1; } }
    @keyframes openui-shimmer {
      0% { background-position: -200px 0; }
      100% { background-position: calc(200px + 100%) 0; }
    }
    .openui-spin { animation: openui-spin 0.7s linear infinite; }
    .openui-icon-btn {
      display: inline-flex; align-items: center; justify-content: center;
      width: 28px; height: 28px; border-radius: 6px;
      background: none; border: none; cursor: pointer;
      color: ${COLORS.textMuted}; transition: background 0.12s ease, color 0.12s ease;
    }
    .openui-icon-btn:hover { background: ${COLORS.activeBg}; color: ${COLORS.primary}; }
    .openui-toggle-btn {
      display: inline-flex; align-items: center; justify-content: center;
      width: 32px; height: 32px; border-radius: 8px;
      background: ${COLORS.primary}; border: none; cursor: pointer;
      color: white;
      box-shadow: 0 1px 3px rgba(124,58,237,0.35);
      transition: background 0.12s ease, transform 0.08s ease;
    }
    .openui-toggle-btn:hover { background: ${COLORS.primaryHover}; }
    .openui-toggle-btn:active { transform: scale(0.94); }
    .openui-skeleton-row {
      height: 14px; border-radius: 3px; margin: 4px 0;
      background: linear-gradient(90deg, #EFEDF3 25%, #F6F5F9 37%, #EFEDF3 63%);
      background-size: 400px 100%;
      animation: openui-shimmer 1.3s ease-in-out infinite;
    }
  `;
  document.head.appendChild(style);
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
  return t;
}

function argsEqual(a, b) {
  const norm = (o) => JSON.stringify(o || {}, Object.keys(o || {}).sort());
  return norm(a) === norm(b);
}

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr.replace(" ", "T"));
  if (isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

/** Pick the most-recently-refreshed artifact; falls back to most recently
 * created if none have been refreshed yet. Returns null for an empty list. */
function pickMostRecent(artifacts) {
  if (!artifacts || artifacts.length === 0) return null;
  const withRefresh = artifacts.filter((a) => a.last_refreshed_at);
  const pool = withRefresh.length ? withRefresh : artifacts;
  const dateOf = (a) => new Date((a.last_refreshed_at || a.creation || "").replace(" ", "T")).getTime() || 0;
  return pool.reduce((best, cur) => (dateOf(cur) > dateOf(best) ? cur : best), pool[0]);
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------
function SidebarSkeleton() {
  return (
    <div style={{ padding: "8px 14px" }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ padding: "8px 0" }}>
          <div className="openui-skeleton-row" style={{ width: `${70 - i * 10}%` }} />
          <div className="openui-skeleton-row" style={{ width: "40%", height: 10 }} />
        </div>
      ))}
    </div>
  );
}

function ArtifactSidebar({ artifacts, loading, currentArtifactName, onSelect, onRefreshList, onNewDashboard, collapsed, onToggleCollapsed }) {
  const [search, setSearch] = useState("");

  const filteredArtifacts = search.trim()
    ? artifacts.filter((a) =>
        String(a.first_message || a.title || a.name || "")
          .toLowerCase()
          .includes(search.trim().toLowerCase())
      )
    : artifacts;

  const railBtnStyle = (active) => ({
    display: "flex", alignItems: "center", justifyContent: "center",
    width: 34, height: 34, borderRadius: 8,
    background: active ? COLORS.primary : "transparent",
    color: active ? "white" : COLORS.textMuted,
    border: "none", cursor: "pointer",
    transition: "background 0.12s ease, color 0.12s ease",
  });

  return (
    <div style={{ display: "flex", height: "100%", background: "#F3F1F7" }}>
      {/* Slim icon rail — always visible */}
      <div style={{
        width: 48, flexShrink: 0, height: "100%",
        display: "flex", flexDirection: "column", alignItems: "center",
        paddingTop: 12, gap: 8,
      }}>
        <button
          onClick={onToggleCollapsed}
          title={collapsed ? "Show history" : "Hide history"}
          style={railBtnStyle(false)}
          onMouseEnter={(e) => { e.currentTarget.style.background = "white"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
        >
          <PanelLeft size={16} strokeWidth={2} />
        </button>

        <button
          onClick={onNewDashboard}
          title="New dashboard"
          style={railBtnStyle(false)}
          onMouseEnter={(e) => { e.currentTarget.style.background = "white"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
        >
          <Plus size={16} strokeWidth={2} />
        </button>

        <button
          onClick={onToggleCollapsed}
          title="History"
          style={railBtnStyle(!collapsed)}
        >
          <Clock size={16} strokeWidth={2} />
        </button>
      </div>

      {/* White panel — flush, full height */}
      {!collapsed && (
        <div style={{
          width: 280, minWidth: 280, height: "100%",
          background: "white", borderRight: `1px solid ${COLORS.border}`,
          boxShadow: "4px 0 16px rgba(0,0,0,0.06)",
          display: "flex", flexDirection: "column", overflow: "hidden",
        }}>
          <div style={{
            padding: "13px 14px", borderBottom: `1px solid ${COLORS.border}`,
            fontSize: 13, fontWeight: 700, color: COLORS.text,
            display: "flex", alignItems: "center", gap: 6,
            fontFamily: FONT_DISPLAY,
          }}>
            <LayoutTemplate size={16} stroke={COLORS.primary} strokeWidth={1.5} /> History
          </div>

          <div style={{ padding: "10px 12px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", flexDirection: "column", gap: 8 }}>
            <button
              onClick={onRefreshList}
              style={{
                width: "100%", padding: "8px 12px", borderRadius: 6,
                border: `1px solid ${COLORS.primary}`, background: "#F5F3FF",
                color: COLORS.primary, fontWeight: 600, fontSize: 12.5, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                fontFamily: FONT_UI,
              }}
            >
              <RotateCw size={14} strokeWidth={2.5} /> Refresh List
            </button>

            <div style={{ position: "relative" }}>
              <Search
                size={14}
                strokeWidth={2}
                color={COLORS.textMuted}
                style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search dashboards…"
                style={{
                  width: "100%", boxSizing: "border-box",
                  padding: "8px 10px 8px 30px", borderRadius: 6,
                  border: `1px solid ${COLORS.border}`, fontSize: 12.5,
                  fontFamily: FONT_UI, color: COLORS.text, outline: "none",
                  transition: "border-color 0.12s ease",
                }}
                onFocus={(e) => { e.currentTarget.style.borderColor = COLORS.primary; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = COLORS.border; }}
              />
            </div>
          </div>

          <div style={{ flex: 1, overflow: "auto", padding: 8 }}>
            {loading && <SidebarSkeleton />}

            {!loading && filteredArtifacts.length === 0 && (
              <div style={{ padding: 12, fontSize: 12.5, color: COLORS.textMuted }}>
                {search.trim() ? "No dashboards match your search." : "No past dashboards yet."}
              </div>
            )}

            {filteredArtifacts.map((a) => {
              const isActive = a.name === currentArtifactName;
              return (
                <button
                  key={a.name}
                  onClick={() => onSelect(a.name)}
                  style={{
                    display: "block", width: "100%", textAlign: "left",
                    padding: "10px 12px", borderRadius: 6, marginBottom: 4,
                    border: `1px solid ${isActive ? COLORS.primary : "transparent"}`,
                    background: isActive ? "#F5F3FF" : "transparent",
                    cursor: "pointer", fontFamily: FONT_UI,
                  }}
                  onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = COLORS.hoverBg; }}
                  onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {a.first_message || a.title || a.name}
                  </div>
                  <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 3 }}>
                    {a.last_refreshed_at ? `Refreshed ${timeAgo(a.last_refreshed_at)}` : "Never refreshed"}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Export dropdown (extracted so it can own its own outside-click handling)
// ---------------------------------------------------------------------------
function ExportMenu({ onExport, onClose }) {
  const menuRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) onClose();
    }
    function handleEscape(e) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [onClose]);

  const itemStyle = {
    display: "flex", alignItems: "center", gap: 8,
    padding: "8px 12px", fontSize: 12, cursor: "pointer", borderRadius: 3,
    color: COLORS.text, fontFamily: FONT_UI, fontWeight: 500,
  };

  return (
    <div
      ref={menuRef}
      style={{
        position: "absolute", top: "100%", right: 0, marginTop: 4,
        background: "white", border: `1px solid ${COLORS.border}`, borderRadius: 4,
        boxShadow: "0 4px 12px rgba(124,58,237,0.12)", zIndex: 100, minWidth: 150, padding: 4,
        animation: "openui-fade-in 0.1s ease",
      }}
    >
      <div
        onClick={() => onExport("png")}
        style={itemStyle}
        onMouseEnter={(e) => { e.currentTarget.style.background = COLORS.activeBg; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
      >
        <ImageIcon size={14} strokeWidth={2.5} color={COLORS.primary} /> PNG Image
      </div>
      <div
        onClick={() => onExport("pdf")}
        style={itemStyle}
        onMouseEnter={(e) => { e.currentTarget.style.background = COLORS.activeBg; }}
        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
      >
        <FileText size={14} strokeWidth={2.5} color={COLORS.primary} /> PDF Document
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard pane
// ---------------------------------------------------------------------------
function DashboardPane({ artifactName }) {
  const [dashboardCode, setDashboardCode] = useState(null);
  const [title, setTitle] = useState("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const dashboardRef = useRef(null);
  const [isExporting, setIsExporting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const [refreshHover, setRefreshHover] = useState(false);
  const [exportHover, setExportHover] = useState(false);

  const queriesRef = useRef([]);
  const queryMapRef = useRef({});
  const artifactLoadTokenRef = useRef(0);

  useEffect(() => { ensureGlobalStyles(); }, []);

  const refresh = useCallback(() => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    frappe.call({
      method: "frappe_assistant_core.aiko.api.refresh_dashboard_artifact",
      args: { artifact_name: artifactName },
      callback: (r) => {
        setIsRefreshing(false);
        const msg = r.message;
        if (msg?.success) {
          queriesRef.current = msg.queries || [];
          queryMapRef.current = msg.queryMap || {};
          setLastRefreshedAt(msg.refreshed_at || null);
          setRefreshTick((n) => n + 1);
        }
      },
      error: () => setIsRefreshing(false),
    });
  }, [artifactName, isRefreshing]);

  useEffect(() => {
    if (!artifactName) return;
    // Token guard so a slow response for a previously-selected artifact can't
    // clobber the one the user has since navigated to (stale-response race).
    const loadToken = ++artifactLoadTokenRef.current;
    setDashboardCode(null);
    setTitle("");
    setLastRefreshedAt(null);
    setLoadError(null);
    queriesRef.current = [];
    queryMapRef.current = {};

    let refreshTimer = null;
    frappe.call({
      method: "frappe_assistant_core.aiko.api.get_dashboard_artifact",
      args: { artifact_name: artifactName },
      callback: (r) => {
        if (loadToken !== artifactLoadTokenRef.current) return;
        const data = r.message;
        if (!data || !data.ui) {
          setLoadError("This artifact has no dashboard content.");
          return;
        }
        setTitle(data.title || "");
        setLastRefreshedAt(data.last_refreshed_at || null);
        setDashboardCode(normalizeDsl(data.ui));
        refreshTimer = setTimeout(() => refresh(), 0);
      },
      error: () => {
        if (loadToken === artifactLoadTokenRef.current) {
          setLoadError("Could not load this artifact.");
        }
      },
    });
    return () => {
      if (refreshTimer) clearTimeout(refreshTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifactName]);

  const captureDashboard = useCallback(async () => {
    const el = dashboardRef.current;
    if (!el) return null;

    const html2canvas = (await import("html2canvas-pro")).default;
    el.classList.add("exporting-freeze");
    await document.fonts?.ready?.catch(() => {});
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

    let canvas;
    try {
      canvas = await html2canvas(el, {
        backgroundColor: "#F6F5F9",
        useCORS: true,
        allowTaint: true,
        scale: Math.max(2, window.devicePixelRatio || 1),
        logging: false,
      });
    } finally {
      el.classList.remove("exporting-freeze");
    }
    return canvas;
  }, []);

  const handleExport = useCallback(async (format) => {
    setShowExportMenu(false);
    setIsExporting(true);
    try {
      const canvas = await captureDashboard();
      if (!canvas) return;

      if (format === "png") {
        const link = document.createElement("a");
        link.download = `${title || "dashboard"}.png`;
        link.href = canvas.toDataURL("image/png");
        link.click();
      } else if (format === "pdf") {
        const { jsPDF } = await import("jspdf");
        const imgData = canvas.toDataURL("image/png");
        const pxToMm = (px) => (px * 25.4) / 96;
        const scale = Math.max(2, window.devicePixelRatio || 1);
        const pageWidthMm = pxToMm(canvas.width / scale);
        const pageHeightMm = pxToMm(canvas.height / scale);

        const pdf = new jsPDF({
          orientation: pageWidthMm >= pageHeightMm ? "landscape" : "portrait",
          unit: "mm",
          format: [pageWidthMm, pageHeightMm],
        });
        pdf.addImage(imgData, "PNG", 0, 0, pageWidthMm, pageHeightMm);
        pdf.save(`${title || "dashboard"}.pdf`);
      }
    } catch (e) {
      console.error("Export failed:", e);
    } finally {
      setIsExporting(false);
    }
  }, [captureDashboard, title]);

  const toolProvider = useRef({
    callTool: async (toolName, args) => {
      if (toolName && typeof toolName === "object") {
        args = toolName.arguments ?? toolName.args ?? {};
        toolName = toolName.name ?? toolName.tool ?? "";
      }
      const match = (queriesRef.current || []).find(
        (q) => q.tool === toolName && argsEqual(q.args, args)
      );
      if (match && queryMapRef.current[match.key] !== undefined) {
        return {
          isError: false,
          content: [{ type: "text", text: JSON.stringify(queryMapRef.current[match.key]) }],
        };
      }
      try {
        const r = await new Promise((resolve, reject) => {
          frappe.call({
            method: "frappe_assistant_core.api.assistant_api.execute_tool",
            args: { tool_name: toolName, arguments: args || {} },
            callback: resolve,
            error: reject,
          });
        });
        const raw = r.message?.result !== undefined ? r.message.result : r.message;
        return { isError: false, content: [{ type: "text", text: JSON.stringify(raw) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: String(err?.message || err) }] };
      }
    },
  }).current;

  if (!artifactName) {
    return null; // parent shows an empty/select-a-dashboard state
  }
  if (loadError) {
    return <div style={{ padding: 40, color: COLORS.textMuted, fontFamily: FONT_UI }}>{loadError}</div>;
  }
  if (!dashboardCode) {
    return (
      <div style={{ padding: 40, display: "flex", flexDirection: "column", gap: 16 }}>
        <div className="openui-skeleton-row" style={{ width: "40%" }} />
        <div className="openui-skeleton-row" style={{ width: "100%", height: 200 }} />
        <div className="openui-skeleton-row" style={{ width: "70%" }} />
        <div className="openui-skeleton-row" style={{ width: "50%" }} />
      </div>
    );
  }

  const baseActionBtn = {
    borderRadius: 6, fontSize: 11, padding: "7px 14px", fontWeight: 700,
    fontFamily: FONT_UI, transition: "background 0.12s ease, box-shadow 0.12s ease",
    display: "inline-flex", alignItems: "center", gap: 4,
  };

  return (
    <div style={{ padding: "24px 28px", flex: 1, minWidth: 0, overflowY: "auto", background: "#FAFAFC" }}>
      {isExporting && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(33,27,46,0.35)", backdropFilter: "blur(1px)",
          display: "flex", alignItems: "center", justifyContent: "center",
          animation: "openui-fade-in 0.15s ease",
        }}>
          <div style={{
            background: "white", borderRadius: 8, padding: "18px 28px",
            display: "flex", alignItems: "center", gap: 12,
            boxShadow: "0 12px 32px rgba(91,44,141,0.25)",
            fontFamily: FONT_UI, fontSize: 13, fontWeight: 600, color: "#211B2E",
          }}>
            <span style={{
              width: 16, height: 16, borderRadius: "50%",
              border: "2px solid #DDD2EE", borderTopColor: "#5B2C8D",
              animation: "openui-spin 0.7s linear infinite", display: "inline-block",
            }} />
            Preparing export…
          </div>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", marginBottom: 16, gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <LayoutTemplate size={18} strokeWidth={2} color={COLORS.primary} />
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 18, fontWeight: 600, color: COLORS.text }}>
            {title}
          </div>
        </div>
        {lastRefreshedAt && (
          <span style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: FONT_MONO, marginTop: 2 }}>
            · Refreshed {timeAgo(lastRefreshedAt)}
          </span>
        )}

        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setShowExportMenu((v) => !v)}
              onMouseEnter={() => setExportHover(true)}
              onMouseLeave={() => setExportHover(false)}
              disabled={isExporting}
              style={{
                ...baseActionBtn,
                background: exportHover ? COLORS.activeBg : "white",
                border: `1px solid ${COLORS.primary}`,
                color: COLORS.primary,
                cursor: isExporting ? "not-allowed" : "pointer",
              }}
            >
              {isExporting ? "Exporting…" : <><Download size={12} strokeWidth={3} style={{ marginRight: 4 }} /> Export</>}
            </button>
            {showExportMenu && (
              <ExportMenu onExport={handleExport} onClose={() => setShowExportMenu(false)} />
            )}
          </div>

          <button
            onClick={refresh}
            onMouseEnter={() => setRefreshHover(true)}
            onMouseLeave={() => setRefreshHover(false)}
            disabled={isRefreshing}
            style={{
              ...baseActionBtn,
              background: refreshHover ? COLORS.primaryHover : COLORS.primary,
              border: "none",
              color: "white",
              cursor: isRefreshing ? "not-allowed" : "pointer",
            }}
          >
            {isRefreshing ? "Refreshing…" : <><RotateCw size={12} strokeWidth={3} style={{ marginRight: 4 }} /> Refresh</>}
          </button>
        </div>
      </div>

      <div
        ref={dashboardRef}
        style={{
          border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 24,
          background: "white", minHeight: 200,
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        }}
      >
        <ThemeProvider
          defaultChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
          barChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
          lineChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
        >
         <Renderer
            key={`artifact-${artifactName}-${refreshTick}`}
            response={dashboardCode}
            library={library}
            toolProvider={toolProvider}
          />
        </ThemeProvider>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Top-level view
// ---------------------------------------------------------------------------
export function ArtifactView({ artifactName: initialArtifactName }) {
  const [currentArtifactName, setCurrentArtifactName] = useState(initialArtifactName || null);
  const [artifacts, setArtifacts] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const rootRef = useRef(null);
  const [rootHeight, setRootHeight] = useState(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const recompute = () => {
      const top = el.getBoundingClientRect().top;
      setRootHeight(Math.max(200, window.innerHeight - top));
    };
    recompute();
    window.addEventListener("resize", recompute);
    const ro = new ResizeObserver(recompute);
    ro.observe(document.body);
    return () => {
      window.removeEventListener("resize", recompute);
      ro.disconnect();
    };
  }, []);

  const updateUrl = useCallback((name) => {
    const newPath = `/app/aiko-dashboard-artifact-view/${name}`;
    window.history.replaceState(null, "", newPath);
  }, []);

  const loadList = useCallback((autoSelectIfMissing) => {
    setListLoading(true);
    frappe.call({
      method: "frappe_assistant_core.aiko.api.list_dashboard_artifacts",
      callback: (r) => {
        setListLoading(false);
        const list = r.message || [];
        setArtifacts(list);
        if (autoSelectIfMissing && !initialArtifactName) {
          const best = pickMostRecent(list);
          if (best) {
            setCurrentArtifactName(best.name);
            updateUrl(best.name);
          }
        }
      },
      error: () => setListLoading(false),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    ensureGlobalStyles();
    // Always fetch the list (sidebar needs it); auto-select only when the
    // URL didn't already specify a specific artifact.
    loadList(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelect = useCallback((name) => {
    if (name === currentArtifactName) return;
    setCurrentArtifactName(name);
    updateUrl(name);
  }, [currentArtifactName, updateUrl]);

  const handleNewDashboard = useCallback(() => {
    // Wire this up to whatever flow starts a new dashboard chat/creation.
    window.location.href = "/app/aiko-dashboard";
  }, []);

  return (
  <div
      ref={rootRef}
      style={{
        display: "flex",
        alignItems: "stretch",
        height: rootHeight != null ? `${rootHeight}px` : "100vh",
      }}
    >
      <ArtifactSidebar
        artifacts={artifacts}
        loading={listLoading}
        currentArtifactName={currentArtifactName}
        onSelect={handleSelect}
        onRefreshList={() => loadList(false)}
        onNewDashboard={handleNewDashboard}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((v) => !v)}
      />
      {currentArtifactName ? (
        <DashboardPane artifactName={currentArtifactName} />
      ) : (
        <div style={{
          flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          gap: 12, color: COLORS.textMutedSoft, fontFamily: FONT_UI, fontSize: 13,
        }}>
          {listLoading ? (
            <>
              <RotateCw size={24} strokeWidth={1.5} className="openui-spin" />
              <span>Loading dashboards…</span>
            </>
          ) : (
            <>
              <LayoutTemplate size={36} strokeWidth={1.5} style={{ opacity: 0.3 }} />
              <span style={{ maxWidth: 260, textAlign: "center", lineHeight: 1.5 }}>
                No saved dashboards yet — save one from the AIKO Dashboard chat.
              </span>
            </>
          )}
        </div>
      )}
    </div>
  );
}