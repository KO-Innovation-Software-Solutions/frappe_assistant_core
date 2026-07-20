import React from "react";
import { defineComponent, createLibrary } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui/genui-lib";
import { z } from "zod";

const SAP_PALETTE = ["#2F5233", "#4C6E51", "#A9BFA8", "#D99A3D", "#B54A3F", "#8A8478", "#6C757D"];

const PALETTE_FAMILIES = [
  ["#2F5233", "#4C6E51", "#A9BFA8", "#D99A3D", "#B54A3F"],
  ["#4C6E51", "#6B8F70", "#8FB093", "#D99A3D", "#C97B4A"],
  ["#D99A3D", "#E8B86D", "#F0D099", "#B54A3F", "#A37B65"],
  ["#B54A3F", "#C97065", "#D9948A", "#8A8478", "#A09B90"],
  ["#8A8478", "#A09B90", "#B8B3A8", "#2F5233", "#4C6E51"],
  ["#6C757D", "#8B9399", "#ABB1B5", "#A9BFA8", "#C4D5C3"],
  ["#2F5233", "#D99A3D", "#B54A3F", "#8A8478", "#A9BFA8"],
  ["#4C6E51", "#2F5233", "#6B8F70", "#A9BFA8", "#C4D5C3"],
  ["#B54A3F", "#D99A3D", "#C97B4A", "#A37B65", "#8A8478"],
  ["#8A8478", "#6C757D", "#A09B90", "#D99A3D", "#B54A3F"],
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

const TREND_ICON = { up: "\u25B2", down: "\u25BC", flat: "\u25CF" };
const TREND_COLOR = { up: "#2F5233", down: "#B54A3F", flat: "#8A8478" };

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
        background: "linear-gradient(135deg, #2F5233, #4C6E51)",
        display: "flex", alignItems: "center", justifyContent: "center",
        boxShadow: "0 4px 12px rgba(47,82,51,0.35)",
      }}>
        <span style={{ color: "white", fontSize: 14, fontWeight: 700 }}>
          {props.label?.trim()?.[0]?.toUpperCase() || "\u2022"}
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
              return { ...result, props: { ...result.props, ...aggregated, customPalette: SAP_PALETTE } };
            }
            if (result && result.props) {
              return { ...result, props: { ...result.props, customPalette: SAP_PALETTE } };
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
