import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds a single self-contained bundle (no hashed filenames, no code
// splitting) so aiko_dashboard.js can frappe.require() it by a fixed
// path: public/dist/aiko_dashboard/index.js + index.css
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../dist/aiko_dashboard", // -> frappe_assistant_core/public/dist/aiko_dashboard
    emptyOutDir: true,
    rollupOptions: {
      input: "src/main.jsx",
      output: {
        entryFileNames: "index.js",
        assetFileNames: "index[extname]", // index.css
        format: "iife", // sets window.AikoDashboard as a side effect on load
      },
    },
  },
});