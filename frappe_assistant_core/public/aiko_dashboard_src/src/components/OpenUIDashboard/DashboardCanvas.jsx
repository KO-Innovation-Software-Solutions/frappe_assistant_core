import { useCallback, useRef, useState } from "react";
import { Renderer } from "@openuidev/react-lang";
import { ThemeProvider } from "@openuidev/react-ui";
import { useDashboard } from "./context";

function ToolbarButton({ label, color, dropdown, isOpen, onClick, icon }) {
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={onClick}
        style={{
          background: isOpen ? color : "white",
          border: `1px solid ${color}`,
          borderRadius: 4,
          cursor: "pointer",
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
        onMouseEnter={(e) => { if (!isOpen) { e.currentTarget.style.background = color; e.currentTarget.style.color = "white"; } }}
        onMouseLeave={(e) => { if (!isOpen) { e.currentTarget.style.background = "white"; e.currentTarget.style.color = color; } }}
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
  } = useDashboard();
  const [showSource, setShowSource] = useState(false);
  const dashboardRef = useRef(null);

  const closeAllDropdowns = useCallback(() => {
    setShowExportMenu(false);
    setShowMailMenu(false);
    setShowScheduleMenu(false);
  }, []);

  const handleExport = useCallback(async (format) => {
    closeAllDropdowns();
    try {
      const html2canvas = (await import("html2canvas-pro")).default;
      const el = dashboardRef.current;
      if (!el) return;
      const canvas = await html2canvas(el, { backgroundColor: "#F6F5F9", useCORS: true });
      if (format === "png") {
        const link = document.createElement("a");
        link.download = "dashboard.png";
        link.href = canvas.toDataURL("image/png");
        link.click();
      } else if (format === "pdf") {
        const { jsPDF } = await import("jspdf");
        const imgData = canvas.toDataURL("image/png");
        const pdf = new jsPDF("landscape", "mm", "a4");
        const pdfWidth = pdf.internal.pageSize.getWidth();
        const pdfHeight = (canvas.height * pdfWidth) / canvas.width;
        pdf.addImage(imgData, "PNG", 0, 0, pdfWidth, pdfHeight);
        pdf.save("dashboard.pdf");
      } else if (format === "xlsx") {
        const XLSX = await import("xlsx");
        const wb = XLSX.utils.book_new();
        const tables = el.querySelectorAll(".openui-table-table");
        tables.forEach((table, i) => {
          const rows = [];
          table.querySelectorAll("tr").forEach((tr) => {
            const row = [];
            tr.querySelectorAll("th, td").forEach((td) => row.push(td.textContent.trim()));
            rows.push(row);
          });
          if (rows.length) {
            const ws = XLSX.utils.aoa_to_sheet(rows);
            XLSX.utils.book_append_sheet(wb, ws, `Table${i + 1}`);
          }
        });
        XLSX.writeFile(wb, "dashboard.xlsx");
      }
    } catch (e) {
      console.error("Export failed:", e);
    }
  }, [closeAllDropdowns]);

  const handleSendMail = useCallback(async () => {
    if (!mailTo.trim()) return;
    setMailStatus("sending...");
    try {
      const canvas = await (await import("html2canvas-pro")).default(
        dashboardRef.current, { backgroundColor: "#F6F5F9", useCORS: true }
      );
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
    }
  }, [mailTo, mailFormat]);

  if (!dashboardCode && !isStreaming) return null;

  return (
    <>
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
              onClick={() => { closeAllDropdowns(); setShowExportMenu(!showExportMenu); }}
              dropdown={
                <>
                  <DropdownItem onClick={() => handleExport("png")}>📸 PNG Image</DropdownItem>
                  <DropdownItem onClick={() => handleExport("pdf")}>📄 PDF Document</DropdownItem>
                  <DropdownItem onClick={() => handleExport("xlsx")}>📊 Excel Spreadsheet</DropdownItem>
                </>
              }
            />

            <ToolbarButton
              label="Send Mail"
              color="#D99A3D"
              icon="✉"
              isOpen={showMailMenu}
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
                    {["png", "pdf", "xlsx"].map((f) => (
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
                    disabled={!mailTo.trim()}
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
              color="#8A8478"
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
                      {["png", "pdf", "xlsx"].map((f) => (
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

            <button onClick={() => closeAllDropdowns() || setShowSource(!showSource)} style={{
              background: "none", border: "1px solid #E5E7EB", borderRadius: 4, cursor: "pointer",
              color: "#8B5CF6", fontSize: 11, padding: "5px 10px", fontWeight: 600, fontFamily: "Inter, sans-serif",
              transition: "all 0.12s",
            }}
onMouseEnter={(e) => { e.currentTarget.style.background = "#F6F5F9"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "white"; }}
            >
              {showSource ? "Hide code" : "View code"}
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
              onAction={(event) => {
                if (event.type === "continue_conversation") {
                  const contextText = typeof event.params?.context === "string"
                    ? event.params.context : "";
                  const text = contextText || event.humanFriendlyMessage || "";
                  if (text && typeof send === "function") send(text);
                }
              }}
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