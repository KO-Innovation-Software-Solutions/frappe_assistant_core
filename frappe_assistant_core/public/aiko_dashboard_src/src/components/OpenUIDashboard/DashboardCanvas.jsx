import { useCallback, useEffect, useRef, useState } from "react";
import { Renderer } from "@openuidev/react-lang";
import { ThemeProvider } from "@openuidev/react-ui";
import { useDashboard } from "./context";

function ToolbarButton({ label, color, dropdown, isOpen, onClick, icon, disabled }) {
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={onClick}
        disabled={disabled}
        style={{
          background: isOpen ? color : "white",
          border: `1px solid ${color}`,
          borderRadius: 4,
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.5 : 1,
          color: isOpen ? "white" : color,
          fontSize: 11,
          fontWeight: 700,
          padding: "5px 10px",
          display: "flex",
          alignItems: "center",
          gap: 4,
          transition: "all 0.12s",
          fontFamily: "Inter, sans-serif",
          letterSpacing: "0.02em",
        }}
        onMouseEnter={(e) => { if (!isOpen && !disabled) { e.currentTarget.style.background = color; e.currentTarget.style.color = "white"; } }}
        onMouseLeave={(e) => { if (!isOpen && !disabled) { e.currentTarget.style.background = "white"; e.currentTarget.style.color = color; } }}
      >
        {icon && <span>{icon}</span>}
        {label}
      </button>
      {isOpen && dropdown && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4,
          background: "white", border: "1px solid #E5E7EB", borderRadius: 4,
          boxShadow: "0 4px 12px rgba(124,58,237,0.12)",
          zIndex: 100, minWidth: 160, padding: 4,
        }}>
          {dropdown}
        </div>
      )}
    </div>
  );
}

function DropdownItem({ onClick, children, color }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "8px 12px", fontSize: 12, cursor: "pointer",
        borderRadius: 3, color: "#1F2621", display: "flex", alignItems: "center", gap: 6,
        fontFamily: "Inter, sans-serif", fontWeight: 500,
      }}
      onMouseEnter={(e) => { e.currentTarget.style.background = "#F6F5F9"; }}
      onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
    >
      {children}
    </div>
  );
}

export function DashboardCanvas({ library }) {
 const {
    dashboardCode, isStreaming, elapsed, refresh, canRefresh,
    showExportMenu, setShowExportMenu,
    showMailMenu, setShowMailMenu,
    showScheduleMenu, setShowScheduleMenu,
    mailTo, setMailTo,
    mailFormat, setMailFormat,
    mailStatus, setMailStatus,
    send,
    queryResolver: externalQueryResolver,
    toolProvider,
    refreshTick,
    currentThreadId,
  } = useDashboard();
  const [showSource, setShowSource] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const dashboardRef = useRef(null);
  const queryResolverRef = useRef(externalQueryResolver);
  useEffect(() => {
    queryResolverRef.current = externalQueryResolver;
  }, [externalQueryResolver]);

  const handleRendererOnAction = useCallback((event) => {
    const isObj = typeof event === "object" && event != null;
    const type = isObj ? (event.type ?? event.action ?? event.name) : event;
    const params = isObj ? (event.params ?? event) : {};

    switch (type) {
      case "continue_conversation":
      case "ContinueConversation": {
        const contextText = typeof params?.context === "string" ? params.context : "";
        const text = contextText || (isObj ? (event.humanFriendlyMessage ?? event.message) : "") || "";
        if (text && typeof send === "function") send(text);
        return;
      }
      case "open_url":
      case "OpenUrl": {
        const url = params?.url ?? params?.open_url ?? event?.url;
        if (typeof url === "string" && url) window.open(url, "_blank", "noopener");
        return;
      }
      case "run":
      case "Run":
      case "run_tool":
      case "run_query":
      case "execute": {
        const statementId = params?.statementId ?? event?.statementId;
        const refType     = params?.refType     ?? event?.refType;
        console.log("[Renderer @Run event ←", { statementId, refType, event });
        try {
          const resolver = queryResolverRef.current;
          if (typeof resolver === "function") {
            resolver({ _kind: "run", statementId, refType, params });
          }
        } catch { /* ignore */ }
        return;
      }
      default:
        console.warn("[Renderer onAction] UNKNOWN event type — paste this into chat:", { event });
    }
  }, [send]);

  const closeAllDropdowns = useCallback(() => {
    setShowExportMenu(false);
    setShowMailMenu(false);
    setShowScheduleMenu(false);
  }, []);

  const captureDashboard = useCallback(async () => {
    const el = dashboardRef.current;
    if (!el) return null;

    const html2canvas = (await import("html2canvas-pro")).default;
    let scrollParent = el.parentElement;
    while (scrollParent && scrollParent !== document.body) {
      const style = window.getComputedStyle(scrollParent);
      if (style.overflowY === "auto" || style.overflowY === "scroll") break;
      scrollParent = scrollParent.parentElement;
    }
    const prevScrollTop = scrollParent ? scrollParent.scrollTop : 0;
    if (scrollParent) scrollParent.scrollTop = 0;
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
        scrollX: 0,
        scrollY: 0,
        logging: false,
      });
    } finally {
      el.classList.remove("exporting-freeze");
      if (scrollParent) scrollParent.scrollTop = prevScrollTop;
    }
    return canvas;
  }, []);

  const handleExport = useCallback(async (format) => {
    closeAllDropdowns();
    setIsExporting(true);
    try {
      const canvas = await captureDashboard();
      if (!canvas) return;

      if (format === "png") {
        const link = document.createElement("a");
        link.download = "dashboard.png";
        link.href = canvas.toDataURL("image/png");
        link.click();
      } else if (format === "pdf") {
        const { jsPDF } = await import("jspdf");
        const imgData = canvas.toDataURL("image/png");
        const pxToMm = (px) => (px * 25.4) / 96;
        const pageWidthMm = pxToMm(canvas.width / (Math.max(2, window.devicePixelRatio || 1)));
        const pageHeightMm = pxToMm(canvas.height / (Math.max(2, window.devicePixelRatio || 1)));

        const pdf = new jsPDF({
          orientation: pageWidthMm >= pageHeightMm ? "landscape" : "portrait",
          unit: "mm",
          format: [pageWidthMm, pageHeightMm],
        });
        pdf.addImage(imgData, "PNG", 0, 0, pageWidthMm, pageHeightMm);
        pdf.save("dashboard.pdf");
      }
    } catch (e) {
      console.error("Export failed:", e);
    } finally {
      setIsExporting(false);
    }
  }, [closeAllDropdowns, captureDashboard]);
  const handleSaveArtifact = useCallback(async () => {
  if (!dashboardCode || isSaving) return;
  setIsSaving(true);
  setSaveStatus("");

  frappe.call({
    method: "frappe_assistant_core.aiko.api.save_dashboard_artifact",
    args: {
      thread_id: currentThreadId,
    },
    callback: (r) => {
      setIsSaving(false);
      if (r.message?.success) {
        setSaveStatus("Saved ✓");
      } else {
        setSaveStatus("Save failed");
      }
      setTimeout(() => setSaveStatus(""), 2500);
    },
    error: () => {
      setIsSaving(false);
      setSaveStatus("Save failed");
      setTimeout(() => setSaveStatus(""), 2500);
    },
  });
}, [dashboardCode, isSaving, currentThreadId]);

  const handleSendMail = useCallback(async () => {
    if (!mailTo.trim()) return;
    setMailStatus("sending...");
    setIsExporting(true);
    try {
      const canvas = await captureDashboard();
      const imgData = canvas.toDataURL("image/png");
      frappe.call({
        method: "frappe_assistant_core.api.admin_api.send_dashboard_mail",
        args: {
          recipient: mailTo.trim(),
          format: mailFormat || "png",
          attachment: imgData,
        },
        callback: (r) => {
          if (r.message && r.message.success) {
            setMailStatus("Sent!");
            setTimeout(() => setMailStatus(""), 3000);
          } else {
            setMailStatus("Failed to send");
          }
        },
        error: () => setMailStatus("Error sending"),
      });
    } catch (e) {
      setMailStatus("Error: " + e.message);
    } finally {
      setIsExporting(false);
    }
  }, [mailTo, mailFormat, captureDashboard]);

  if (!dashboardCode && !isStreaming) return null;

  return (
    <>
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

      {dashboardCode && !isStreaming && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8, marginBottom: 12, fontSize: 12, flexWrap: "wrap",
        }}>
          {elapsed && (
            <span style={{ color: "#8A8478", fontWeight: 600, fontFamily: "IBM Plex Mono, monospace", fontSize: 11 }}>
              {(elapsed / 1000).toFixed(1)}s
            </span>
          )}

          <div style={{ display: "flex", gap: 4, marginLeft: "auto", alignItems: "center" }}>
            <ToolbarButton
              label="Export"
              color="#7C3AED"
              icon="↓"
              isOpen={showExportMenu}
              disabled={isExporting}
              onClick={() => { closeAllDropdowns(); setShowExportMenu(!showExportMenu); }}
              dropdown={
                <>
                  <DropdownItem onClick={() => handleExport("png")}>📸 PNG Image</DropdownItem>
                  <DropdownItem onClick={() => handleExport("pdf")}>📄 PDF Document</DropdownItem>
                </>
              }
            />

            <ToolbarButton
              label="Send Mail"
              color="#D99A3D"
              icon="✉"
              isOpen={showMailMenu}
              disabled={isExporting}
              onClick={() => { closeAllDropdowns(); setShowMailMenu(!showMailMenu); }}
              dropdown={
                <div style={{ padding: 8, width: 220 }}>
                  <input
                    value={mailTo}
                    onChange={(e) => setMailTo(e.target.value)}
                    placeholder="recipient@email.com"
                    style={{
                      width: "100%", padding: "6px 8px", border: "1px solid #E5E7EB", borderRadius: 3,
                      fontSize: 12, fontFamily: "Inter, sans-serif", marginBottom: 8, outline: "none",
                    }}
                  />
                  <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                    {["png", "pdf"].map((f) => (
                      <button
                        key={f}
                        onClick={() => setMailFormat(f)}
                        style={{
                          flex: 1, padding: "4px 6px", border: `1px solid ${mailFormat === f ? "#7C3AED" : "#E5E7EB"}`,
                          borderRadius: 3, background: mailFormat === f ? "#7C3AED" : "white",
                          color: mailFormat === f ? "white" : "#1F2621", cursor: "pointer",
                          fontSize: 10, fontWeight: 600, fontFamily: "Inter, sans-serif", textTransform: "uppercase",
                        }}
                      >{f}</button>
                    ))}
                  </div>
                  <button
                    onClick={handleSendMail}
                    disabled={!mailTo.trim() || isExporting}
                    style={{
                      width: "100%", padding: "6px 0", border: "none", borderRadius: 3,
                      background: mailTo.trim() ? "#D99A3D" : "#E5E7EB",
                      color: mailTo.trim() ? "white" : "#8A8478", cursor: mailTo.trim() ? "pointer" : "not-allowed",
                      fontSize: 12, fontWeight: 600, fontFamily: "Inter, sans-serif",
                    }}
                  >Send</button>
                  {mailStatus && (
                    <div style={{ fontSize: 11, marginTop: 4, color: "#8B5CF6", textAlign: "center" }}>{mailStatus}</div>
                  )}
                </div>
              }
            />

            <ToolbarButton
              label="Schedule"
              color="#6d6357"
              icon="⏱"
              isOpen={showScheduleMenu}
              onClick={() => { closeAllDropdowns(); setShowScheduleMenu(!showScheduleMenu); }}
              dropdown={
                <div style={{ padding: 12, width: 280 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: "#1F2621", fontFamily: "Inter, sans-serif" }}>
                    Schedule Report
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <label style={{ fontSize: 11, color: "#8B5CF6", display: "block", marginBottom: 2 }}>Frequency</label>
                    <select style={{ width: "100%", padding: "5px 8px", border: "1px solid #E5E7EB", borderRadius: 3, fontSize: 12 }}>
                      <option>Daily</option>
                      <option>Weekly</option>
                      <option>Monthly</option>
                    </select>
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <label style={{ fontSize: 11, color: "#8B5CF6", display: "block", marginBottom: 2 }}>Format</label>
                    <div style={{ display: "flex", gap: 4 }}>
                      {["png", "pdf"].map((f) => (
                        <button key={f} style={{ flex: 1, padding: "4px 6px", border: "1px solid #E5E7EB", borderRadius: 3, background: "white", cursor: "pointer", fontSize: 10, fontWeight: 600, fontFamily: "Inter, sans-serif", textTransform: "uppercase" }}>{f}</button>
                      ))}
                    </div>
                  </div>
                  <button style={{ width: "100%", padding: "6px 0", border: "none", borderRadius: 3, background: "#7C3AED", color: "white", cursor: "pointer", fontSize: 12, fontWeight: 600, fontFamily: "Inter, sans-serif" }}>
                    Schedule Report
                  </button>
                </div>
              }
            />

            <div style={{ width: 1, height: 20, background: "#E5E7EB", margin: "0 4px" }} />

            <button onClick={() => { closeAllDropdowns(); setShowSource(!showSource); }} style={{
              background: "none", border: "1px solid #9ca3af", borderRadius: 4, cursor: "pointer",
              color: "#6d3fa6", fontSize: 11, padding: "5px 10px", fontWeight: 600, fontFamily: "Inter, sans-serif",
              transition: "all 0.12s",
            }}
onMouseEnter={(e) => { e.currentTarget.style.background = "#F6F5F9"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "white"; }}
            >
              {showSource ? "Hide code" : "View code"}
            </button>
            <button onClick={handleSaveArtifact} disabled={!dashboardCode || isSaving} style={{
              background: dashboardCode ? "#1F2621" : "#E5E7EB",
              border: "none", borderRadius: 4, cursor: dashboardCode ? "pointer" : "not-allowed",
              color: "white", fontSize: 11, padding: "5px 10px", fontWeight: 700, fontFamily: "Inter, sans-serif",
            }}>
              {isSaving ? "Saving…" : saveStatus || "💾 Save"}
            </button>
            
            <button onClick={refresh} disabled={!canRefresh} style={{
              background: canRefresh ? "#7C3AED" : "#E5E7EB",
              border: "none", borderRadius: 4, cursor: canRefresh ? "pointer" : "not-allowed",
              color: "white", fontSize: 11, padding: "5px 10px", fontWeight: 700, fontFamily: "Inter, sans-serif",
            }}>⟳ Refresh</button>
          </div>
        </div>
      )}

      {showSource && dashboardCode && (
        <pre style={{
          background: "#1F2621", color: "#A78BFA", padding: 14, borderRadius: 4,
          fontSize: 11, overflow: "auto", whiteSpace: "pre-wrap", maxHeight: 250,
          lineHeight: 1.4, marginBottom: 14, border: "1px solid #7C3AED",
          fontFamily: "IBM Plex Mono, monospace",
        }}>{typeof dashboardCode === "string" ? dashboardCode : JSON.stringify(dashboardCode, null, 2)}</pre>
      )}

      {dashboardCode && (
        <div ref={dashboardRef} style={{
          border: "1px solid #E5E7EB", borderRadius: 4, padding: 20,
          background: "#F6F5F9", minHeight: 200,
          boxShadow: "0 1px 2px rgba(124,58,237,0.03), 0 8px 24px rgba(124,58,237,0.06)",
        }}>
          <ThemeProvider
            defaultChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
            barChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
            lineChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
            areaChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
            pieChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
            radialChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
            horizontalBarChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
            singleStackedBarChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#D99A3D","#B54A3F","#8A8478","#6C757D"]}
          >
            <Renderer
              key={`aiko-dash-${refreshTick ?? 0}`}
              response={dashboardCode}
              library={library}
              isStreaming={isStreaming}
              queryLoader={
                <div style={{
                  position: "absolute", top: 0, left: 0, right: 0, height: 3,
                  background: "linear-gradient(90deg, transparent 0%, #7C3AED 50%, transparent 100%)",
                  backgroundSize: "200% 100%",
                  animation: "openui-loading-bar 1.5s ease-in-out infinite",
                  zIndex: 10,
                }} />
              }
              onAction={handleRendererOnAction}
              toolProvider={toolProvider}
            />
          </ThemeProvider>
        </div>
      )}

      {isStreaming && !dashboardCode && (
        <div style={{
          textAlign: "center", padding: 60, color: "#8A8478",
          border: "1px solid #E5E7EB", borderRadius: 4, background: "white",
        }}>
          <div style={{
            fontFamily: "Fraunces, Georgia, serif", fontSize: 18, fontWeight: 500, color: "#1F2621", marginBottom: 8,
          }}>Generating dashboard...</div>
          {elapsed && (
            <div style={{ fontSize: 12, fontFamily: "IBM Plex Mono, monospace", color: "#8A8478" }}>
              {(elapsed / 1000).toFixed(1)}s
            </div>
          )}
        </div>
      )}
    </>
  );
}