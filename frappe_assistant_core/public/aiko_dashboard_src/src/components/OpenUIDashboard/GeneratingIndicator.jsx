export function GeneratingIndicator({ elapsed, stage }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", padding: "60px 20px", gap: 16,
    }}>
      <div style={{ position: "relative", width: 240, height: 60 }}>
        <div style={{
          position: "absolute", bottom: 6, left: 0, right: 0, height: 2,
          background: "repeating-linear-gradient(90deg, #DDD6FE 0 12px, transparent 12px 24px)",
        }} />
        <div style={{
          position: "absolute", bottom: 10, fontSize: 32,
          animation: "truckDrive 2.2s linear infinite",
        }}>🚚</div>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "#7C3AED", fontFamily: "Inter, sans-serif" }}>
        {stage || "Generating dashboard…"}
      </div>
      {elapsed != null && (
        <div style={{ fontSize: 12, color: "#8A8478", fontFamily: "IBM Plex Mono, monospace" }}>
          {(elapsed / 1000).toFixed(1)}s
        </div>
      )}
      <style>{`
        @keyframes truckDrive {
          0%   { transform: translateX(-20px); }
          50%  { transform: translateX(200px) scaleX(1); }
          51%  { transform: translateX(200px) scaleX(-1); }
          100% { transform: translateX(-20px) scaleX(-1); }
        }
      `}</style>
    </div>
  );
}