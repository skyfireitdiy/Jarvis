import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks: {
          'vue': ['vue'],
          'monaco': ['monaco-editor'],
          'xterm': ['xterm', '@xterm/addon-fit'],
          'markdown': ['marked', 'highlight.js'],
          'diagram': ['mermaid', 'd3-graphviz', 'plantuml-encoder']
        }
      }
    }
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    allowedHosts: ['jarvis-front.tocmcc.cn', 'jvs-ai.cn'],
  },
})
