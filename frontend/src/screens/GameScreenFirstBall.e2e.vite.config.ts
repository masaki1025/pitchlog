import { readFileSync } from 'node:fs'
import { isAbsolute } from 'node:path'
import { defineConfig } from 'vite'
import base, { stripApiPrefix } from '../../vite.config'

// TLS資材は外部で明示供給する。このconfigは生成・配置・内容のログ出力を行わない。
const cert = process.env.PITCHLOG_E2E_TLS_CERT_PATH
const key = process.env.PITCHLOG_E2E_TLS_KEY_PATH
const port = process.env.PITCHLOG_E2E_BACKEND_PORT
if (!cert || !key || !isAbsolute(cert) || !isAbsolute(key))
  throw new Error('HTTPS E2Eには証明書/鍵の絶対PATHが必要です')
if (!port || !/^[0-9]+$/.test(port))
  throw new Error('HTTPS E2Eのbackend portが不正です')
export default defineConfig({
  ...base,
  server: {
    ...base.server,
    host: '127.0.0.1',
    https: { cert: readFileSync(cert), key: readFileSync(key) },
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${port}`,
        changeOrigin: true,
        rewrite: stripApiPrefix,
      },
    },
  },
})
