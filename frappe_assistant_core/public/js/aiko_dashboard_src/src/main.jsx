// public/js/aiko_dashboard_src/src/main.jsx
//
// Entry point. Builds to public/dist/aiko_dashboard/index.js and exposes
// window.AikoDashboard.mount(el) — called from
// assistant_core/page/aiko_dashboard/aiko_dashboard.js after frappe.require
// loads this bundle.

import "./frappe-mock";
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "@openuidev/react-ui/styles/index.css";
import "@openuidev/react-ui/defaults.css";
import "./styles.css";

window.AikoDashboard = {
  mount(el) {
    const root = createRoot(el);
    root.render(<App />);
  },
};