import { useEffect, useRef, useState, useCallback } from "react";
import { Renderer } from "@openuidev/react-lang";
import { ThemeProvider } from "@openuidev/react-ui";
import { library } from "../../library";

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

function ArtifactSidebar({ artifacts, loading, currentArtifactName, onSelect, onRefreshList, collapsed, onToggleCollapsed }) {
  if (collapsed) {
    return (
      <div style={{
        width: 32, flexShrink: 0, borderRight: "1px solid #E5E7EB",
        background: "white", height: "100%", display: "flex",
        flexDirection: "column", alignItems: "center", paddingTop: 10,
      }}>
        <button
          onClick={onToggleCollapsed}
          title="Show saved dashboards"
          style={{
            background: "none", border: "none", cursor: "pointer",
            color: "#7C3AED", fontSize: 14, padding: 4,
          }}
        >☰</button>
      </div>
    );
  }

  return (
    <div style={{
      width: 240, flexShrink: 0, borderRight: "1px solid #E5E7EB",
      background: "white", height: "100%", overflowY: "auto",
      paddingTop: 4,
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 14px 8px 14px",
      }}>
        <span style={{
          fontSize: 11, fontWeight: 700, letterSpacing: "0.04em", color: "#8A8478",
          textTransform: "uppercase", fontFamily: "Inter, sans-serif",
        }}>
          Saved Dashboards
        </span>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={onRefreshList}
            title="Refresh list"
            style={{ background: "none", border: "none", cursor: "pointer", color: "#8A8478", fontSize: 12, padding: 2 }}
          >⟳</button>
          <button
            onClick={onToggleCollapsed}
            title="Hide sidebar"
            style={{ background: "none", border: "none", cursor: "pointer", color: "#8A8478", fontSize: 12, padding: 2 }}
          >⟨</button>
        </div>
      </div>

      {loading && (
        <div style={{ padding: "8px 14px", fontSize: 12, color: "#8A8478", fontFamily: "Inter, sans-serif" }}>
          Loading…
        </div>
      )}

      {!loading && artifacts.length === 0 && (
        <div style={{ padding: "8px 14px", fontSize: 12, color: "#8A8478", fontFamily: "Inter, sans-serif" }}>
          No saved dashboards yet.
        </div>
      )}

      {artifacts.map((a) => {
        const isActive = a.name === currentArtifactName;
        return (
          <div
            key={a.name}
            onClick={() => onSelect(a.name)}
            style={{
              padding: "10px 14px", cursor: "pointer",
              borderLeft: isActive ? "3px solid #7C3AED" : "3px solid transparent",
              background: isActive ? "#F6F5F9" : "transparent",
            }}
            onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = "#FAFAFA"; }}
            onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent"; }}
          >
            <div style={{
              fontSize: 13, fontWeight: isActive ? 700 : 500,
              color: isActive ? "#1F2621" : "#3A342C",
              fontFamily: "Inter, sans-serif",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
            }}>
              {a.title || a.name}
            </div>
            <div style={{
              fontSize: 11, color: "#8A8478", marginTop: 2,
              fontFamily: "IBM Plex Mono, monospace",
            }}>
              {a.last_refreshed_at ? `Refreshed ${timeAgo(a.last_refreshed_at)}` : "Never refreshed"}
            </div>
          </div>
        );
      })}
    </div>
  );
}

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

  const queriesRef = useRef([]);
  const queryMapRef = useRef({});

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
    setDashboardCode(null);
    setTitle("");
    setLastRefreshedAt(null);
    setLoadError(null);
    queriesRef.current = [];
    queryMapRef.current = {};

    frappe.call({
      method: "frappe_assistant_core.aiko.api.get_dashboard_artifact",
      args: { artifact_name: artifactName },
      callback: (r) => {
        const data = r.message;
        if (!data || !data.ui) {
          setLoadError("This artifact has no dashboard content.");
          return;
        }
        setTitle(data.title || "");
        setLastRefreshedAt(data.last_refreshed_at || null);
        setDashboardCode(normalizeDsl(data.ui));
        setTimeout(() => refresh(), 0);
      },
      error: () => setLoadError("Could not load this artifact."),
    });
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
    return <div style={{ padding: 40, color: "#8A8478", fontFamily: "Inter, sans-serif" }}>{loadError}</div>;
  }
  if (!dashboardCode) {
    return <div style={{ padding: 40, color: "#8A8478", fontFamily: "Inter, sans-serif" }}>Loading…</div>;
  }

  return (
    <div style={{ padding: 20, flex: 1, minWidth: 0, overflowY: "auto" }}>
      {isExporting && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 1000,
          background: "rgba(33,27,46,0.35)", backdropFilter: "blur(1px)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div style={{
            background: "white", borderRadius: 8, padding: "18px 28px",
            display: "flex", alignItems: "center", gap: 12,
            boxShadow: "0 12px 32px rgba(91,44,141,0.25)",
            fontFamily: "Inter, sans-serif", fontSize: 13, fontWeight: 600, color: "#211B2E",
          }}>
            <span style={{
              width: 16, height: 16, borderRadius: "50%",
              border: "2px solid #DDD2EE", borderTopColor: "#5B2C8D",
              animation: "openui-spin 0.7s linear infinite", display: "inline-block",
            }} />
            Preparing export…
          </div>
          <style>{`@keyframes openui-spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", marginBottom: 12, gap: 12 }}>
        <div style={{ fontFamily: "Fraunces, Georgia, serif", fontSize: 18, fontWeight: 600, color: "#1F2621" }}>
          {title}
        </div>
        {lastRefreshedAt && (
          <span style={{ fontSize: 11, color: "#8A8478", fontFamily: "IBM Plex Mono, monospace" }}>
            Last refreshed: {lastRefreshedAt}
          </span>
        )}

        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setShowExportMenu((v) => !v)}
              disabled={isExporting}
              style={{
                background: "white", border: "1px solid #7C3AED", borderRadius: 4,
                color: "#7C3AED", fontSize: 11, padding: "5px 10px", fontWeight: 700,
                fontFamily: "Inter, sans-serif", cursor: isExporting ? "not-allowed" : "pointer",
              }}
            >
              {isExporting ? "Exporting…" : "↓ Export"}
            </button>
            {showExportMenu && (
              <div style={{
                position: "absolute", top: "100%", right: 0, marginTop: 4,
                background: "white", border: "1px solid #E5E7EB", borderRadius: 4,
                boxShadow: "0 4px 12px rgba(124,58,237,0.12)", zIndex: 100, minWidth: 140, padding: 4,
              }}>
                <div
                  onClick={() => handleExport("png")}
                  style={{
                    padding: "8px 12px", fontSize: 12, cursor: "pointer", borderRadius: 3,
                    color: "#1F2621", fontFamily: "Inter, sans-serif", fontWeight: 500,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "#F6F5F9"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                >📸 PNG Image</div>
                <div
                  onClick={() => handleExport("pdf")}
                  style={{
                    padding: "8px 12px", fontSize: 12, cursor: "pointer", borderRadius: 3,
                    color: "#1F2621", fontFamily: "Inter, sans-serif", fontWeight: 500,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = "#F6F5F9"; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                >📄 PDF Document</div>
              </div>
            )}
          </div>

          <button
            onClick={refresh}
            disabled={isRefreshing}
            style={{
              background: "#7C3AED", border: "none", borderRadius: 4,
              color: "white", fontSize: 11, padding: "5px 10px", fontWeight: 700,
              fontFamily: "Inter, sans-serif", cursor: isRefreshing ? "not-allowed" : "pointer",
            }}
          >
            {isRefreshing ? "Refreshing…" : "⟳ Refresh"}
          </button>
        </div>
      </div>

      <div
        ref={dashboardRef}
        style={{
          border: "1px solid #E5E7EB", borderRadius: 4, padding: 20,
          background: "#F6F5F9", minHeight: 200,
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

export function ArtifactView({ artifactName: initialArtifactName }) {
  const [currentArtifactName, setCurrentArtifactName] = useState(initialArtifactName || null);
  const [artifacts, setArtifacts] = useState([]);
  const [listLoading, setListLoading] = useState(true);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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

  return (
    <div style={{ display: "flex", height: "100%", minHeight: 500 }}>
      <ArtifactSidebar
        artifacts={artifacts}
        loading={listLoading}
        currentArtifactName={currentArtifactName}
        onSelect={handleSelect}
        onRefreshList={() => loadList(false)}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((v) => !v)}
      />
      {currentArtifactName ? (
        <DashboardPane artifactName={currentArtifactName} />
      ) : (
        <div style={{
          flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
          color: "#8A8478", fontFamily: "Inter, sans-serif", fontSize: 13,
        }}>
          {listLoading ? "Loading dashboards…" : "No saved dashboards yet — save one from the AIKO Dashboard chat."}
        </div>
      )}
    </div>
  );
}