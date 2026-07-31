import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../dist/aiko_dashboard_artifact_view",
    emptyOutDir: true,
    rollupOptions: {
      input: "src/artifact_view_main.jsx",
      output: {
        entryFileNames: "index.js",
        assetFileNames: "index[extname]",
        format: "iife",
      },
    },
  },
});
