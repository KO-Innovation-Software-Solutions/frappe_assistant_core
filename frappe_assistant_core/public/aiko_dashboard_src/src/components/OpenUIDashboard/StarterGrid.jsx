import { BarChart3, Truck, Bell, BatteryCharging, User, Wrench } from "lucide-react";
import { useDashboard } from "./context";

const ICON_MAP = {
  BarChart3, Truck, Bell, BatteryCharging, User, Wrench,
};

export function StarterGrid({ starters }) {
  const { send } = useDashboard();

  return (
    <div style={{
      maxWidth: 700, width: "100%",
      display: "grid",
      gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
      gap: 10,
    }}>
      {starters.map((s) => {
        const IconComp = ICON_MAP[s.icon];
        return (
          <button key={s.prompt} onClick={() => send(s.prompt)} style={{
            padding: 16, border: `1px solid #E5E7EB`, borderRadius: 12,
            background: "white", cursor: "pointer", fontSize: 13, textAlign: "left",
            transition: "all 0.12s ease", lineHeight: 1.4,
            fontFamily: "Inter, sans-serif",
            boxShadow: "0 1px 2px rgba(124,58,237,0.04)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "#7C3AED";
            e.currentTarget.style.background = "#FCFAFF";
            e.currentTarget.style.boxShadow = "0 4px 12px rgba(124,58,237,0.12)";
            e.currentTarget.style.transform = "translateY(-1px)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "#E5E7EB";
            e.currentTarget.style.background = "white";
            e.currentTarget.style.boxShadow = "0 1px 2px rgba(31,38,33,0.04)";
            e.currentTarget.style.transform = "translateY(0)";
          }}
          >
            <span style={{
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              width: 34, height: 34, borderRadius: "50%",
              background: "#F3EFFA",
            }}>
              {IconComp ? <IconComp size={18} stroke="#7C3AED" strokeWidth={1.5} /> : null}
            </span>
            <div style={{
              fontWeight: 600, marginTop: 10, fontSize: 13.5, color: "#1F2621",
              fontFamily: "Fraunces, Georgia, serif",
            }}>{s.label}</div>
            <div style={{ color: "#8A8478", fontSize: 11.5, marginTop: 3, minHeight: 17 }}>
              {s.prompt}
            </div>
          </button>
        );
      })}
    </div>
  );
}
