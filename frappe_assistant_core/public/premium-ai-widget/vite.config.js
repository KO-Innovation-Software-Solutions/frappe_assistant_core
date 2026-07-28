import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const isFullpage = mode === 'fullpage'
  return {
    plugins: [react()],
    base: '/assets/frappe_assistant_core/premium-ai-widget/dist/',
    build: {
      outDir: path.resolve(__dirname, 'dist'),
      emptyOutDir: !isFullpage,
      rollupOptions: {
        input: path.resolve(__dirname, isFullpage ? 'fullpage.html' : 'index.html'),
        output: {
          format: 'iife',
          entryFileNames: `js/${isFullpage ? 'fullpage' : 'index'}.js`,
          inlineDynamicImports: true,
          assetFileNames: 'assets/[name][extname]',
        },
      },
    },
  }
})