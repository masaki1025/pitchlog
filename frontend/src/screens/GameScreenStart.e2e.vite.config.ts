import { defineConfig } from 'vite'
import base, { stripApiPrefix } from '../../vite.config'

// E2E専用: /api を pytest が起動した app コンテナの実ポートへ転送する。
const target = process.env.PITCHLOG_E2E_BACKEND_PORT
if (!target) throw new Error('E2E backend port がない')
export default defineConfig({
  ...base,
  server: {
    ...base.server,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${target}`,
        changeOrigin: true,
        rewrite: stripApiPrefix,
      },
    },
  },
})
