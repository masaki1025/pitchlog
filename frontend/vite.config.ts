import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

const frontendRoot = fileURLToPath(new URL('.', import.meta.url))
const contractsRoot = fileURLToPath(new URL('../contracts/', import.meta.url))

// /api は FastAPI (port 8800) へプロキシ（docs/api_contract_v1.md 共通事項）
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@contracts': contractsRoot,
    },
  },
  server: {
    fs: {
      allow: [frontendRoot, contractsRoot],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8800',
        changeOrigin: true,
      },
    },
  },
})
