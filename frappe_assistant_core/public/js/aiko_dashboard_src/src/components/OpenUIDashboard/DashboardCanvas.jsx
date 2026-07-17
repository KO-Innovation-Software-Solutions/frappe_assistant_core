import { useCallback, useRef, useState } from "react";
import { Download, Mail, Clock, Code2, RefreshCw } from "lucide-react";
import { Renderer } from "@openuidev/react-lang";
import { ThemeProvider } from "@openuidev/react-ui";
import { useDashboard } from "./context";

function ToolbarButton({ label, color, isOpen, onClick, icon }) {
  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={onClick}
        style={{
          background: isOpen ? color : "white",
          border: `1px solid ${color}`,
          borderRadius: 6,
          cursor: "pointer",
          color: isOpen ? "white" : color,
          fontSize: 11,
          fontWeight: 700,
          padding: "5px 10px",
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          transition: "all 0.15s",
          fontFamily: "Inter, sans-serif",
          letterSpacing: "0.02em",
        }}
        onMouseEnter={(e) => { if (!isOpen) { e.currentTarget.style.background = color; e.currentTarget.style.color = "white"; } }}
        onMouseLeave={(e) => { if (!isOpen) { e.currentTarget.style.background = "white"; e.currentTarget.style.color = color; } }}
      >
        {icon}
        {label}
      </button>
      {isOpen && (
        <div style={{
          position: "absolute", top: "100%", left: 0, marginTop: 4,
          background: "white", border: "1px solid #E5E7EB", borderRadius: 8,
          boxShadow: "0 8px 24px rgba(124,58,237,0.15)",
          zIndex: 100, minWidth: 180, padding: 6,
        }}>
          <DropdownMenuContent />
        </div>
      )}
    </div>
  );
}

function DropdownItem({ onClick, children }) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "8px 12px", fontSize: 12, cursor: "pointer",
        borderRadius: 6, color: "#1F2621", display: "flex", alignItems: "center", gap: 6,
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
      const canvas = await html2canvas(el, { backgroundColor: "#F6F5F9", useCORS: true, scale: 2 });
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
        dashboardRef.current, { backgroundColor: "#F6F5F9", useCORS: true, scale: 2 }
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

  function DropdownMenuContent() {
    if (showExportMenu) {
      return (
        <>
          <DropdownItem onClick={() => handleExport("png")}><Download size={14} /> PNG Image</DropdownItem>
          <DropdownItem onClick={() => handleExport("pdf")}><Download size={14} /> PDF Document</DropdownItem>
          <DropdownItem onClick={() => handleExport("xlsx")}><Download size={14} /> Excel Spreadsheet</DropdownItem>
        </>
      );
    }
    if (showMailMenu) {
      return (
        <div style={{ padding: 8, width: 220 }}>
          <input
            value={mailTo}
            onChange={(e) => setMailTo(e.target.value)}
            placeholder="recipient@email.com"
            style={{
              width: "100%", padding: "6px 8px", border: "1px solid #E5E7EB", borderRadius: 6,
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
                  borderRadius: 6, background: mailFormat === f ? "#7C3AED" : "white",
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
              width: "100%", padding: "6px 0", border: "none", borderRadius: 6,
              background: "#7C3AED", color: "white",
              opacity: mailTo.trim() ? 1 : 0.45,
              cursor: mailTo.trim() ? "pointer" : "not-allowed",
              fontSize: 12, fontWeight: 600, fontFamily: "Inter, sans-serif",
              transition: "background 0.12s",
            }}
            onMouseEnter={(e) => { if (mailTo.trim()) e.currentTarget.style.background = "#6D28D9"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "#7C3AED"; }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4 }}>
              <Mail size={12} /> Send
            </div>
          </button>
          {mailStatus && (
            <div style={{ fontSize: 11, marginTop: 4, color: "#8B5CF6", textAlign: "center" }}>{mailStatus}</div>
          )}
        </div>
      );
    }
    if (showScheduleMenu) {
      return (
        <div style={{ padding: 12, width: 280 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: "#1F2621", fontFamily: "Inter, sans-serif" }}>
            Schedule Report
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: "#8B5CF6", display: "block", marginBottom: 2 }}>Frequency</label>
            <select style={{ width: "100%", padding: "5px 8px", border: "1px solid #E5E7EB", borderRadius: 6, fontSize: 12 }}>
              <option>Daily</option>
              <option>Weekly</option>
              <option>Monthly</option>
            </select>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 11, color: "#8B5CF6", display: "block", marginBottom: 2 }}>Format</label>
            <div style={{ display: "flex", gap: 4 }}>
              {["png", "pdf", "xlsx"].map((f) => (
                <button key={f} style={{
                  flex: 1, padding: "4px 6px", border: "1px solid #E5E7EB", borderRadius: 6,
                  background: "white", cursor: "pointer", fontSize: 10, fontWeight: 600,
                  fontFamily: "Inter, sans-serif", textTransform: "uppercase",
                }}>{f}</button>
              ))}
            </div>
          </div>
          <button style={{
            width: "100%", padding: "6px 0", border: "none", borderRadius: 6,
            background: "#7C3AED", color: "white", cursor: "pointer",
            fontSize: 12, fontWeight: 600, fontFamily: "Inter, sans-serif",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 4,
          }}>
            <Clock size={12} /> Schedule Report
          </button>
        </div>
      );
    }
    return null;
  }

  const dropdownToggle = (setter, value) => () => {
    closeAllDropdowns();
    setter(!value);
  };

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
              icon={<Download size={12} />}
              isOpen={showExportMenu}
              onClick={dropdownToggle(setShowExportMenu, showExportMenu)}
            />

            <ToolbarButton
              label="Send Mail"
              color="#D99A3D"
              icon={<Mail size={12} />}
              isOpen={showMailMenu}
              onClick={dropdownToggle(setShowMailMenu, showMailMenu)}
            />

            <ToolbarButton
              label="Schedule"
              color="#8A8478"
              icon={<Clock size={12} />}
              isOpen={showScheduleMenu}
              onClick={dropdownToggle(setShowScheduleMenu, showScheduleMenu)}
            />

            <div style={{ width: 1, height: 20, background: "#E5E7EB", margin: "0 4px" }} />

            <button onClick={() => { closeAllDropdowns(); setShowSource(!showSource); }} style={{
              background: "none", border: "1px solid #E5E7EB", borderRadius: 6, cursor: "pointer",
              color: "#8B5CF6", fontSize: 11, padding: "5px 10px", fontWeight: 600,
              fontFamily: "Inter, sans-serif", display: "inline-flex", alignItems: "center", gap: 4,
              transition: "all 0.12s",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "#F6F5F9"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "none"; }}
            >
              <Code2 size={12} />
              {showSource ? "Hide" : "View"}
            </button>

            <button onClick={refresh} disabled={!canRefresh} style={{
              background: "#7C3AED", opacity: canRefresh ? 1 : 0.45,
              border: "none", borderRadius: 6, cursor: canRefresh ? "pointer" : "not-allowed",
              color: "white", fontSize: 11, padding: "5px 10px", fontWeight: 700,
              fontFamily: "Inter, sans-serif", display: "inline-flex", alignItems: "center", gap: 4,
              transition: "all 0.12s",
            }}
            onMouseEnter={(e) => { if (canRefresh) e.currentTarget.style.background = "#6D28D9"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "#7C3AED"; }}
            >
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>
      )}

      {showSource && dashboardCode && (
        <pre style={{
          background: "#1F2621", color: "#A78BFA", padding: 14, borderRadius: 10,
          fontSize: 11, overflow: "auto", whiteSpace: "pre-wrap", maxHeight: 250,
          lineHeight: 1.4, marginBottom: 14, border: "1px solid #7C3AED",
          fontFamily: "IBM Plex Mono, monospace",
        }}>{typeof dashboardCode === "string" ? dashboardCode : JSON.stringify(dashboardCode, null, 2)}</pre>
      )}

      {dashboardCode && (
        <div ref={dashboardRef} style={{
          border: "1px solid #EDE9FE", borderRadius: 10, padding: 20,
          background: "linear-gradient(135deg, #F6F5F9 0%, #F3EFFA 50%, #F6F5F9 100%)",
          minHeight: 200,
          boxShadow: "0 1px 3px rgba(124,58,237,0.04), 0 8px 24px rgba(124,58,237,0.08), inset 0 0 0 1px rgba(255,255,255,0.6)",
        }}>
          <ThemeProvider
            barChartPalette={["#7C3AED","#8B5CF6","#A78BFA","#C4B5FD","#DDD6FE"]}
            lineChartPalette={["#0D9488","#14B8A6","#2DD4BF","#5EEAD4","#99F6E4"]}
            areaChartPalette={["#0D9488","#14B8A6","#2DD4BF","#5EEAD4","#99F6E4"]}
            pieChartPalette={["#7C3AED","#D99A3D","#2563EB","#0D9488","#DC2626"]}
            radialChartPalette={["#7C3AED","#8B5CF6","#A78BFA"]}
            horizontalBarChartPalette={["#2563EB","#3B82F6","#60A5FA","#93C5FD","#BFDBFE"]}
            singleStackedBarChartPalette={["#7C3AED","#8B5CF6","#A78BFA"]}
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
            />
          </ThemeProvider>
        </div>
      )}

      {isStreaming && !dashboardCode && (
        <div style={{
          textAlign: "center", padding: 60, color: "#8A8478",
          border: "1px solid #EDE9FE", borderRadius: 10, background: "white",
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
