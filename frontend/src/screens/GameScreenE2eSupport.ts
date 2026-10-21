import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import {
  closeSync,
  existsSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { setTimeout as delay } from 'node:timers/promises'
import { createServer as createPortReservation } from 'node:net'
import { createServer, type ViteDevServer } from 'vite'
import { stripApiPrefix } from '../../vite.config.ts'
import {
  cleanupGameScreenOutputDirectory,
  finishGameScreenChild,
} from './GameScreenE2eProcess'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const repositoryRoot = resolve(frontendRoot, '..')
const backendRoot = resolve(repositoryRoot, 'backend')

export interface GameScreenE2eRuntime {
  baseURL: string
  identities: readonly { name: string; password: string; tenantId: string }[]
}

function ownedRuntimePath(): string {
  const value = process.env.PITCHLOG_E2E_RUNTIME_FILE
  if (!value || !value.startsWith(`${tmpdir()}/pitchlog-e2e-`)) {
    throw new Error('E2E 専用一時ディレクトリを確認できない')
  }
  return value
}

export function readGameScreenE2eRuntime(): GameScreenE2eRuntime {
  return JSON.parse(
    readFileSync(ownedRuntimePath(), 'utf8'),
  ) as GameScreenE2eRuntime
}

async function awaitReady(
  path: string,
  child: ChildProcess,
  spawnFailed: () => boolean,
): Promise<void> {
  for (let attempt = 0; attempt < 900; attempt += 1) {
    if (existsSync(path)) return
    if (spawnFailed() || child.exitCode !== null || child.signalCode !== null)
      throw new Error('製品 DB または App の起動に失敗')
    await delay(100)
  }
  throw new Error('製品 DB または App の起動がタイムアウト')
}

async function chooseOwnFrontendPort(): Promise<number> {
  return new Promise((resolvePort, rejectPort) => {
    const reservation = createPortReservation()
    reservation.once('error', rejectPort)
    reservation.listen(0, '127.0.0.1', () => {
      const address = reservation.address()
      reservation.close((error) => {
        if (error) return rejectPort(error)
        if (typeof address !== 'object' || address === null)
          return rejectPort(new Error('E2E HTTPS の一時ポートを取得できない'))
        resolvePort(address.port)
      })
    })
  })
}

/** 実製品 App と専用 DB を HTTPS の画面へ接続し、終了時に自分の資源だけ破棄する。 */
export default async function setupGameScreenE2e(): Promise<
  () => Promise<void>
> {
  if (process.env.PLAYWRIGHT_NO_COPY_PROMPT !== '1')
    throw new Error('失敗時DOM snapshotの抑止設定がない')
  const frontendPort = await chooseOwnFrontendPort()
  const frontendOrigin = `https://127.0.0.1:${frontendPort}`
  const directory = mkdtempSync(resolve(tmpdir(), 'pitchlog-e2e-'))
  const readyPath = resolve(directory, 'backend-ready.json')
  const stopPath = resolve(directory, 'stop')
  const runtimePath = resolve(directory, 'runtime.json')
  const keyPath = resolve(directory, 'localhost.key')
  const certPath = resolve(directory, 'localhost.crt')
  closeSync(openSync(keyPath, 'wx', 0o600))
  const certificate = spawnSync(
    'openssl',
    [
      'req',
      '-x509',
      '-newkey',
      'rsa:2048',
      '-nodes',
      '-days',
      '1',
      '-subj',
      '/CN=localhost',
      '-addext',
      'subjectAltName=DNS:localhost,IP:127.0.0.1',
      '-keyout',
      keyPath,
      '-out',
      certPath,
    ],
    { stdio: 'ignore' },
  )
  if (certificate.status !== 0 || (statSync(keyPath).mode & 0o777) !== 0o600) {
    rmSync(directory, { recursive: true, force: true })
    throw new Error('E2E 用の一時 HTTPS 証明書を生成できない')
  }

  const inherited = Object.fromEntries(
    ['PATH', 'HOME', 'USER', 'TMPDIR', 'LANG', 'LC_ALL']
      .filter((key) => process.env[key] !== undefined)
      .map((key) => [key, process.env[key]]),
  )
  const backend = spawn(
    resolve(backendRoot, '.venv/bin/python'),
    ['../frontend/src/screens/GameScreenE2eSupport.py'],
    {
      cwd: backendRoot,
      stdio: 'ignore',
      env: {
        ...inherited,
        // 外部 PITCHLOG_* は継承せず、Python driver が専用クラスタの DSN を生成する。
        PITCHLOG_E2E_READY_FILE: readyPath,
        PITCHLOG_E2E_STOP_FILE: stopPath,
        PITCHLOG_E2E_FRONTEND_ORIGIN: frontendOrigin,
        PYTHONPATH: [
          resolve(backendRoot, 'tests'),
          resolve(backendRoot, 'src'),
        ].join(':'),
      },
    },
  )
  let spawnFailed = false
  backend.once('error', () => {
    spawnFailed = true
  })
  let vite: ViteDevServer | undefined
  const cleanup = async (): Promise<void> => {
    let failed = false
    try {
      await vite?.close()
    } catch {
      failed = true
    }
    try {
      writeFileSync(stopPath, '', { flag: 'wx', mode: 0o600 })
    } catch {
      failed = true
    }
    try {
      if (spawnFailed) throw new Error('自分の補助プロセスを起動できない')
      await finishGameScreenChild(backend, 90_000, 90_000)
    } catch {
      failed = true
    } finally {
      delete process.env.PITCHLOG_E2E_RUNTIME_FILE
      rmSync(directory, { recursive: true, force: true })
      cleanupGameScreenOutputDirectory()
    }
    if (failed) throw new Error('E2Eの自分専用DBまたはAppの終了・後始末に失敗')
  }
  try {
    await awaitReady(readyPath, backend, () => spawnFailed)
    const supplied = JSON.parse(readFileSync(readyPath, 'utf8')) as {
      port: number
      identities: GameScreenE2eRuntime['identities']
    }
    if (!Number.isInteger(supplied.port) || supplied.port < 1) {
      throw new Error('製品 App の待受ポートが不正')
    }
    vite = await createServer({
      configFile: resolve(frontendRoot, 'vite.config.ts'),
      envDir: false,
      server: {
        host: '127.0.0.1',
        port: frontendPort,
        strictPort: true,
        https: { key: readFileSync(keyPath), cert: readFileSync(certPath) },
        proxy: {
          '/api': {
            target: `http://127.0.0.1:${supplied.port}`,
            changeOrigin: true,
            rewrite: stripApiPrefix,
          },
        },
      },
    })
    await vite.listen()
    const address = vite.httpServer?.address()
    if (
      typeof address !== 'object' ||
      address === null ||
      address.port !== frontendPort
    ) {
      throw new Error('HTTPS 画面が予約した専用ポートを使っていない')
    }
    writeFileSync(
      runtimePath,
      JSON.stringify({
        baseURL: frontendOrigin,
        identities: supplied.identities,
      } satisfies GameScreenE2eRuntime),
      { mode: 0o600 },
    )
    process.env.PITCHLOG_E2E_RUNTIME_FILE = runtimePath
    return cleanup
  } catch {
    try {
      await cleanup()
    } catch {
      // setup失敗自体を成功へ変えず、秘密と自前出力の削除を先に行う。
    }
    throw new Error(
      'E2E の専用クラスタ・既存認証fixture・実製品 App の起動に失敗',
    )
  }
}
