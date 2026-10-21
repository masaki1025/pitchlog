import type { ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, resolve } from 'node:path'

const outputName = 'PITCHLOG_E2E_OUTPUT_DIR'
const outputTokenName = 'PITCHLOG_E2E_OUTPUT_TOKEN'
const outputOwnerName = 'PITCHLOG_E2E_OUTPUT_OWNER_PID'
const outputChildName = 'playwright-output'

function validatedOutputDirectory(): string {
  const directory = process.env[outputName]
  const token = process.env[outputTokenName]
  const ownerPid = process.env[outputOwnerName]
  if (
    !directory ||
    !token ||
    !ownerPid ||
    !/^[1-9][0-9]*$/.test(ownerPid) ||
    !/^[0-9a-f]{32}$/.test(token) ||
    !basename(directory).startsWith('pitchlog-game-e2e-output-') ||
    realpathSync(dirname(directory)) !== realpathSync(tmpdir()) ||
    !existsSync(directory)
  )
    throw new Error('自分専用のPlaywright出力先を確認できない')
  const stat = lstatSync(directory)
  const marker = resolve(directory, '.owner')
  const markerStat = lstatSync(marker)
  if (
    !stat.isDirectory() ||
    stat.uid !== process.getuid?.() ||
    (stat.mode & 0o777) !== 0o700 ||
    !markerStat.isFile() ||
    markerStat.uid !== stat.uid ||
    (markerStat.mode & 0o777) !== 0o600 ||
    readFileSync(marker, 'utf8') !== token
  )
    throw new Error('Playwright出力先の所有証跡が不正')
  return directory
}

function outputChild(root: string): string {
  const child = resolve(root, outputChildName)
  if (!existsSync(child)) mkdirSync(child, { mode: 0o700 })
  const stat = lstatSync(child)
  if (!stat.isDirectory() || stat.uid !== process.getuid?.())
    throw new Error('Playwright子出力先の所有を確認できない')
  chmodSync(child, 0o700)
  return child
}

/** config再評価やworkerも同じ自分専用0700出力先だけを使う。 */
export function gameScreenOutputDirectory(): string {
  if (process.env[outputName]) {
    return outputChild(validatedOutputDirectory())
  }
  const directory = mkdtempSync(resolve(tmpdir(), 'pitchlog-game-e2e-output-'))
  chmodSync(directory, 0o700)
  const token = randomBytes(16).toString('hex')
  writeFileSync(resolve(directory, '.owner'), token, {
    flag: 'wx',
    mode: 0o600,
  })
  chmodSync(resolve(directory, '.owner'), 0o600)
  process.env[outputName] = directory
  process.env[outputTokenName] = token
  process.env[outputOwnerName] = String(process.pid)
  process.once('exit', () => {
    if (process.env[outputOwnerName] === String(process.pid)) {
      try {
        cleanupGameScreenOutputDirectory()
      } catch {
        // exit時は同期cleanupの二重失敗を投げず、通常teardownの結果を優先する。
      }
    }
  })
  return outputChild(validatedOutputDirectory())
}

/** 同じrunの所有証跡を再確認し、自分の出力だけ削除する。 */
export function cleanupGameScreenOutputDirectory(): void {
  const directory = process.env[outputName]
  if (!directory || !existsSync(directory)) return
  validatedOutputDirectory()
  rmSync(directory, { recursive: true })
}

export interface GameScreenChildExit {
  code: number | null
  signal: NodeJS.Signals | null
}

/** 自分が起動した子プロセスの終了を、期限を区切って回収する。 */
export async function waitForGameScreenChildExit(
  child: ChildProcess,
  timeoutMs: number,
): Promise<GameScreenChildExit | null> {
  if (child.exitCode !== null || child.signalCode !== null)
    return { code: child.exitCode, signal: child.signalCode }
  return new Promise((resolveExit) => {
    let settled = false
    const finish = (result: GameScreenChildExit | null): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      child.off('exit', onExit)
      child.off('error', onError)
      resolveExit(result)
    }
    const onExit = (code: number | null, signal: NodeJS.Signals | null): void =>
      finish({ code, signal })
    const onError = (): void => finish({ code: null, signal: null })
    const timer = setTimeout(() => finish(null), timeoutMs)
    child.once('exit', onExit)
    child.once('error', onError)
  })
}

/** 停止通知後の自然終了を待ち、期限超過時だけ自分の子へSIGTERMを送る。 */
export async function finishGameScreenChild(
  child: ChildProcess,
  normalWaitMs: number,
  signalWaitMs: number,
): Promise<void> {
  let result = await waitForGameScreenChildExit(child, normalWaitMs)
  if (result === null) {
    child.kill('SIGTERM')
    result = await waitForGameScreenChildExit(child, signalWaitMs)
  }
  if (result === null)
    throw new Error('自分の製品DB補助プロセスが期限内に終了しない')
  if (result.code !== 0 || result.signal !== null)
    throw new Error('自分の製品DB補助プロセスが異常終了した')
}
