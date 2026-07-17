import React from "react";
import { defineComponent, createLibrary } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui/genui-lib";
import { z } from "zod";

const PALETTE_FAMILIES = [
  ["#7C3AED", "#8B5CF6", "#A78BFA", "#C4B5FD", "#DDD6FE"],
  ["#0D9488", "#14B8A6", "#2DD4BF", "#5EEAD4", "#99F6E4"],
  ["#D97706", "#F59E0B", "#FBBF24", "#FCD34D", "#FDE68A"],
  ["#2563EB", "#3B82F6", "#60A5FA", "#93C5FD", "#BFDBFE"],
  ["#DC2626", "#EF4444", "#F87171", "#FCA5A5", "#FECACA"],
  ["#DB2777", "#EC4899", "#F472B6", "#F9A8D4", "#FBCFE8"],
  ["#059669", "#10B981", "#34D399", "#6EE7B7", "#A7F3D0"],
  ["#CA8A04", "#EAB308", "#FACC15", "#FDE047", "#FEF08A"],
  ["#9333EA", "#A855F7", "#C084FC", "#D8B4FE", "#E9D5FF"],
  ["#0891B2", "#06B6D4", "#22D3EE", "#67E8F9", "#A5F3FC"],
];

function pickPalette(props) {
  const arr = props?.labels || props?.values || [];
  let hash = 0;
  for (const item of arr) {
    const str = String(item);
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash = hash & hash;
    }
  }
  return PALETTE_FAMILIES[Math.abs(hash) % PALETTE_FAMILIES.length];
}

function formatKpiValue(value) {
  if (value === 0 || value === "0") return "\u2014";
  const num = typeof value === "string" ? parseFloat(value.replace(/[^0-9.-]/g, "")) : value;
  if (isNaN(num)) return String(value);
  if (Number.isInteger(num)) return num.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  return num.toLocaleString("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

function aggregateLabels(labels, series) {
  const seen = new Set();
  const deduped = [];
  const indices = [];
  labels.forEach((l, i) => {
    const key = String(l);
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(l);
      indices.push(i);
    }
  });
  if (deduped.length === labels.length) return { labels, series };
  const newSeries = series.map((s) => {
    const values = s.values || [];
    return { ...s, values: indices.map((idx) => values[idx] ?? 0) };
  });
  return { labels: deduped, series: newSeries };
}

const TREND_ICON = { up: "▲", down: "▼", flat: "●" };
const TREND_COLOR = { up: "#059669", down: "#DC2626", flat: "#8A8478" };

const KpiCard = defineComponent({
  name: "KpiCard",
  description: "A single metric with label, value, and optional trend delta.",
  props: z.object({
    label: z.string(),
    value: z.union([z.string(), z.number()]),
    delta: z.string().optional().describe("e.g. '+12%'"),
    trend: z.enum(["up", "down", "flat"]).optional(),
  }),
  component: ({ props }) => (
    <div className="sap-receipt-line" style={{ position: "relative" }}>
      <div style={{
        width: 34, height: 34, borderRadius: "50%", marginBottom: 8,
        background: "linear-gradient(135deg, #7C3AED, #2563EB)",
        display: "flex", alignItems: "center", justifyContent: "center",
        boxShadow: "0 4px 12px rgba(124,58,237,0.35)",
      }}>
        <span style={{ color: "white", fontSize: 14, fontWeight: 700 }}>
          {props.label?.trim()?.[0]?.toUpperCase() || "•"}
        </span>
      </div>
      <div className="label">{props.label}</div>
      <div className="value">{formatKpiValue(props.value)}</div>
      {props.delta && (
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 4, marginTop: 6,
          fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 20,
          background: `${TREND_COLOR[props.trend || "flat"]}18`,
          color: TREND_COLOR[props.trend || "flat"],
        }}>
          <span>{TREND_ICON[props.trend || "flat"]}</span>{props.delta}
        </div>
      )}
    </div>
  ),
});

const DataTableRow = z.record(z.string(), z.union([z.string(), z.number()]));

const DataTable = defineComponent({
  name: "DataTable",
  description: "Tabular data with sortable columns.",
  props: z.object({
    columns: z.array(z.object({ key: z.string(), label: z.string() })),
    rows: z.array(DataTableRow),
  }),
  component: ({ props }) => (
    <table className="openui-table-table">
      <thead>
        <tr>{props.columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
      </thead>
      <tbody>
        {props.rows.map((row, i) => (
          <tr key={i}>{props.columns.map((c) => {
            const val = row[c.key];
            const isNumeric = typeof val === "number" || (!isNaN(parseFloat(val)) && isFinite(val));
            return <td key={c.key} className={isNumeric ? "numeric" : ""}>{String(val ?? "")}</td>;
          })}</tr>
        ))}
      </tbody>
    </table>
  ),
});

const DashboardLinkCard = defineComponent({
  name: "DashboardLinkCard",
  description:
    "Link to a saved Frappe Dashboard (from create_dashboard or " +
    "list_user_dashboards results). Use instead of rebuilding the whole " +
    "dashboard when a tool already created/found one.",
  props: z.object({
    title: z.string(),
    url: z.string(),
    subtitle: z.string().optional(),
  }),
  component: ({ props }) => (
    <a className="oui-dashboard-link-card" href={props.url} target="_blank" rel="noreferrer">
      <div className="oui-dlc-title">{props.title}</div>
      {props.subtitle && <div className="oui-dlc-subtitle">{props.subtitle}</div>}
    </a>
  ),
});

export const library = createLibrary({
  root: openuiLibrary.root ?? "Stack",
  componentGroups: openuiLibrary.componentGroups,
  components: [
    ...Object.values(openuiLibrary.components).map((comp) => {
      if (comp.name === "BarChart" || comp.name === "LineChart" || comp.name === "AreaChart" ||
          comp.name === "PieChart" || comp.name === "RadarChart" || comp.name === "RadialChart" ||
          comp.name === "HorizontalBarChart" || comp.name === "SingleStackedBarChart") {
        const original = comp.component;
        return {
          ...comp,
          component: (args) => {
            const result = original(args);
            if (result && result.props && result.props.labels && result.props.series) {
              const aggregated = aggregateLabels(result.props.labels, result.props.series);
              return { ...result, props: { ...result.props, ...aggregated, customPalette: pickPalette(result.props) } };
            }
            if (result && result.props) {
              return { ...result, props: { ...result.props, customPalette: pickPalette(result.props) } };
            }
            return result;
          },
        };
      }
      return comp;
    }),
    KpiCard,
    DataTable,
    DashboardLinkCard,
  ],
});
