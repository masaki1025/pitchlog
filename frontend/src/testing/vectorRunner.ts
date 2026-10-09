import { spawn } from 'node:child_process'
import { resolve } from 'node:path'
import { isDeepStrictEqual } from 'node:util'
import type { Readable } from 'node:stream'

export const DEFAULT_RESPONSE_TIMEOUT_MS = 10_000
const MAX_RESPONSE_TIMEOUT_MS = 2 ** 31 - 1
const REAP_TIMEOUT_MS = 1_000

export type VectorContract = Readonly<{
  calculation: string
  vector: string
  runner: 'vitest'
  entrypointId: string
  directTargetId: string
  caseSchema: unknown
  normalizationComparison: ComparisonContract
  outputComparison: ComparisonContract
}>

export type ComparisonContract = Readonly<{
  surface: string
  fields: readonly Readonly<{
    field: string
    role: string
    valueType: string
    nullable: boolean
    scale: number | null
  }>[]
  normalizations: readonly string[]
}>

export type GeneratedNormalizer = Readonly<{
  generatedId: string
  sourceHash: string
  normalize: (raw: unknown) => unknown
}>

export type CalculationAdapter = Readonly<{
  execute: (caseId: string, normalized: unknown) => unknown
}>

export type VectorRunReport = Readonly<{
  declaredCaseIds: readonly string[]
  consumedCaseIds: readonly string[]
  executions: readonly Readonly<{
    caseId: string
    generatedId: string
    sourceHash: string
    normalizationMatched: boolean
    outputMatched: boolean
  }>[]
  complete: boolean
}>

export class VectorRunError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'VectorRunError'
  }
}

export class UnsupportedVectorCase extends Error {
  constructor(message = '未対応 case') {
    super(message)
    this.name = 'UnsupportedVectorCase'
  }
}

export class VectorRunnerError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'VectorRunnerError'
  }
}

type Options = Readonly<{
  command?: readonly [string, ...string[]]
  responseTimeoutMs?: number
}>

type JsonRecord = Record<string, unknown>
type CloseStatus = Readonly<{
  code: number | null
  signal: NodeJS.Signals | null
}>
type PendingLine = {
  resolve: (line: string) => void
  reject: (error: Error) => void
  timer: ReturnType<typeof setTimeout>
}

class LineReader {
  private buffer = ''
  private readonly lines: string[] = []
  private pending: PendingLine | undefined
  private failure: Error | undefined

  constructor(stream: Readable) {
    stream.setEncoding('utf8')
    stream.on('data', (chunk: string) => this.accept(chunk))
    stream.once('end', () => this.fail(new Error('終端前に stdout が閉じた')))
    stream.once('error', (error: Error) => this.fail(error))
  }

  private accept(chunk: string): void {
    this.buffer += chunk
    let boundary = this.buffer.indexOf('\n')
    while (boundary >= 0) {
      const line = this.buffer.slice(0, boundary).replace(/\r$/, '')
      this.buffer = this.buffer.slice(boundary + 1)
      if (this.pending) {
        const pending = this.pending
        this.pending = undefined
        clearTimeout(pending.timer)
        pending.resolve(line)
      } else {
        this.lines.push(line)
      }
      boundary = this.buffer.indexOf('\n')
    }
  }

  fail(error: Error): void {
    this.failure ??= error
    if (this.pending) {
      const pending = this.pending
      this.pending = undefined
      clearTimeout(pending.timer)
      pending.reject(this.failure)
    }
  }

  next(timeoutMs: number): Promise<string> {
    const line = this.lines.shift()
    if (line !== undefined) return Promise.resolve(line)
    if (this.failure) return Promise.reject(this.failure)
    return new Promise<string>((resolveLine, rejectLine) => {
      const timer = setTimeout(() => {
        this.pending = undefined
        rejectLine(new Error(`応答が ${timeoutMs} ms を超えた`))
      }, timeoutMs)
      this.pending = { resolve: resolveLine, reject: rejectLine, timer }
    })
  }
}

function requireRecord(value: unknown, label: string): JsonRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new VectorRunnerError(`${label} が object でない`)
  }
  return value as JsonRecord
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== 'string') {
    throw new VectorRunnerError(`${label} が文字列でない`)
  }
  return value
}

function rejectThenable(value: unknown): void {
  if (
    ((typeof value === 'object' && value !== null) ||
      typeof value === 'function') &&
    typeof (value as { then?: unknown }).then === 'function'
  ) {
    throw new VectorRunnerError('adapter は同期値を返す必要がある')
  }
}

function assertJsonValue(
  value: unknown,
  location: string,
  ancestors: WeakSet<object> = new WeakSet(),
): void {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'boolean'
  ) {
    return
  }
  if (typeof value === 'number') {
    if (
      !Number.isFinite(value) ||
      Object.is(value, -0) ||
      (Number.isInteger(value) && !Number.isSafeInteger(value))
    ) {
      throw new VectorRunnerError(`${location} に往復できない数値がある`)
    }
    return
  }
  if (typeof value !== 'object') {
    throw new VectorRunnerError(`${location} に JSON で往復できない値がある`)
  }
  if (ancestors.has(value)) {
    throw new VectorRunnerError(`${location} に循環参照がある`)
  }
  ancestors.add(value)
  try {
    if (Array.isArray(value)) {
      for (let index = 0; index < value.length; index += 1) {
        const descriptor = Object.getOwnPropertyDescriptor(value, index)
        if (!descriptor?.enumerable || !('value' in descriptor)) {
          throw new VectorRunnerError(`${location}[${index}] が JSON 値でない`)
        }
        assertJsonValue(descriptor.value, `${location}[${index}]`, ancestors)
      }
      for (const key of Reflect.ownKeys(value)) {
        if (key === 'length') continue
        const index = typeof key === 'string' ? Number(key) : NaN
        if (
          typeof key !== 'string' ||
          !Number.isInteger(index) ||
          index < 0 ||
          index >= value.length ||
          String(index) !== key
        ) {
          throw new VectorRunnerError(`${location} に JSON 外の配列属性がある`)
        }
      }
      return
    }
    const prototype = Object.getPrototypeOf(value)
    if (prototype !== Object.prototype && prototype !== null) {
      throw new VectorRunnerError(`${location} にプレーンでない object がある`)
    }
    for (const key of Reflect.ownKeys(value)) {
      if (typeof key !== 'string') {
        throw new VectorRunnerError(`${location} に symbol キーがある`)
      }
      const descriptor = Object.getOwnPropertyDescriptor(value, key)
      if (!descriptor?.enumerable || !('value' in descriptor)) {
        throw new VectorRunnerError(`${location}.${key} が JSON に含まれない`)
      }
      assertJsonValue(descriptor.value, `${location}.${key}`, ancestors)
    }
  } finally {
    ancestors.delete(value)
  }
}

function encodeLine(value: unknown): string {
  assertJsonValue(value, '送信値')
  try {
    return `${JSON.stringify(value)}\n`
  } catch (error) {
    throw new VectorRunnerError(`JSON の送信値を作れない: ${String(error)}`)
  }
}

function parseLine(line: string): JsonRecord {
  let value: unknown
  try {
    value = JSON.parse(line) as unknown
  } catch (error) {
    throw new VectorRunnerError(`ブリッジの JSON 行が不正: ${String(error)}`)
  }
  return requireRecord(value, 'ブリッジの応答')
}

function reportFrom(message: JsonRecord): VectorRunReport {
  if (
    !Array.isArray(message.declaredCaseIds) ||
    !Array.isArray(message.consumedCaseIds) ||
    !Array.isArray(message.executions) ||
    typeof message.complete !== 'boolean'
  ) {
    throw new VectorRunnerError('ブリッジの report が不正')
  }
  return {
    declaredCaseIds: message.declaredCaseIds as string[],
    consumedCaseIds: message.consumedCaseIds as string[],
    executions: message.executions as VectorRunReport['executions'],
    complete: message.complete,
  }
}

function waitForExit(
  exitPromise: Promise<CloseStatus>,
  timeoutMs: number,
): Promise<CloseStatus> {
  return new Promise((resolveExit, rejectExit) => {
    const timer = setTimeout(
      () =>
        rejectExit(
          new VectorRunnerError(`子の終了が ${timeoutMs} ms を超えた`),
        ),
      timeoutMs,
    )
    exitPromise.then((status) => {
      clearTimeout(timer)
      resolveExit(status)
    })
  })
}

export async function runVectors(
  cases: unknown,
  contract: VectorContract,
  normalizer: GeneratedNormalizer,
  calculation: CalculationAdapter,
  options: Options = {},
): Promise<VectorRunReport> {
  const timeoutMs = options.responseTimeoutMs ?? DEFAULT_RESPONSE_TIMEOUT_MS
  if (
    !Number.isSafeInteger(timeoutMs) ||
    timeoutMs <= 0 ||
    timeoutMs > MAX_RESPONSE_TIMEOUT_MS
  ) {
    throw new VectorRunnerError(
      '応答期限が Node のタイマー範囲内の正の整数でない',
    )
  }
  const command = options.command ?? [
    'python3',
    '-m',
    'pitchlog.domaincheck.runners.vector_bridge',
  ]
  const [program, ...args] = command
  if (!program) throw new VectorRunnerError('起動コマンドが空')

  // 子を起動する前に、開始メッセージで値が失われないことを確認する。
  const start = encodeLine({
    type: 'start',
    cases,
    contract,
    normalizer: {
      generatedId: normalizer.generatedId,
      sourceHash: normalizer.sourceHash,
    },
  })
  const root = resolve(process.cwd(), '..')
  const child = spawn(program, args, {
    cwd: root,
    env: { ...process.env, PYTHONPATH: resolve(root, 'backend/src') },
    stdio: ['pipe', 'pipe', 'pipe'],
    detached: process.platform !== 'win32',
  })
  const reader = new LineReader(child.stdout)
  let stderr = ''
  let exited = false
  let spawnFailure: Error | undefined
  let inputFailure: Error | undefined
  child.stderr.setEncoding('utf8')
  child.stderr.on('data', (chunk: string) => {
    stderr += chunk
  })
  child.stdin.on('error', (error: Error) => {
    inputFailure = error
    reader.fail(error)
  })
  const exitPromise = new Promise<CloseStatus>((resolveExit) => {
    child.once('exit', (code, signal) => {
      exited = true
      resolveExit({ code, signal })
    })
    child.once('error', (error: Error) => {
      spawnFailure = error
      reader.fail(error)
      exited = true
      resolveExit({ code: null, signal: null })
    })
  })
  const stopProcessGroup = (): void => {
    let groupError: unknown
    if (process.platform !== 'win32' && child.pid !== undefined) {
      try {
        process.kill(-child.pid, 'SIGKILL')
        return
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== 'ESRCH') {
          groupError = error
        }
      }
    }
    if (!exited) child.kill('SIGKILL')
    if (groupError) throw groupError
  }
  const send = (message: unknown): void => {
    const line = encodeLine(message)
    if (child.stdin.destroyed || !child.stdin.writable) {
      throw new VectorRunnerError('子の stdin に書けない')
    }
    child.stdin.write(line)
  }
  const internal = (message: string): VectorRunnerError =>
    new VectorRunnerError(`${message}; stderr: ${stderr || '(空)'}`)

  let normalized: unknown
  let hasNormalized = false
  let adapterError: unknown
  let hasAdapterError = false
  let rethrowAdapterError = false
  try {
    child.stdin.write(start)
    let terminal: JsonRecord | undefined
    while (!terminal) {
      const message = parseLine(await reader.next(timeoutMs))
      const type = requireString(message.type, 'ブリッジの type')
      if (type === 'normalize') {
        let result: unknown
        try {
          result = normalizer.normalize(message.raw)
        } catch (error) {
          adapterError = error
          hasAdapterError = true
          send({ type: 'adapter-error', message: 'adapter failed' })
          continue
        }
        rejectThenable(result)
        send({ type: 'normalized', value: result })
        normalized = result
        hasNormalized = true
      } else if (type === 'execute') {
        const caseId = requireString(message.caseId, 'execute.caseId')
        if (
          !hasNormalized ||
          !isDeepStrictEqual(message.normalized, normalized)
        ) {
          throw new VectorRunnerError('計算入力が直前の正規化出力と異なる')
        }
        hasNormalized = false
        let result: unknown
        try {
          result = calculation.execute(caseId, normalized)
        } catch (error) {
          if (error instanceof UnsupportedVectorCase) {
            send({ type: 'unsupported' })
          } else {
            adapterError = error
            hasAdapterError = true
            send({ type: 'adapter-error', message: 'adapter failed' })
          }
          continue
        }
        rejectThenable(result)
        send({ type: 'executed', value: result })
      } else if (
        type === 'report' ||
        type === 'vector-run-error' ||
        type === 'adapter-error' ||
        type === 'protocol-error'
      ) {
        terminal = message
      } else {
        throw new VectorRunnerError(`未知のブリッジ type: ${type}`)
      }
    }
    child.stdin.end()
    const status = await waitForExit(exitPromise, timeoutMs)
    if (spawnFailure || inputFailure || status.code !== 0) {
      throw internal(
        `子の終了が異常: code=${status.code}, signal=${status.signal}, ` +
          `spawn=${String(spawnFailure)}, stdin=${String(inputFailure)}`,
      )
    }
    if (terminal.type === 'report') return reportFrom(terminal)
    if (terminal.type === 'vector-run-error') {
      throw new VectorRunError(
        requireString(terminal.message, 'vector-run-error.message'),
      )
    }
    if (terminal.type === 'protocol-error') {
      throw internal(requireString(terminal.message, 'protocol-error.message'))
    }
    if (!hasAdapterError) throw internal('対応する adapter 例外がない')
    rethrowAdapterError = true
    throw adapterError
  } catch (error) {
    if (rethrowAdapterError || error instanceof VectorRunError) throw error
    if (error instanceof VectorRunnerError) throw internal(error.message)
    throw internal(`ブリッジの実行に失敗: ${String(error)}`)
  } finally {
    let cleanupError: unknown
    try {
      if (!exited) {
        stopProcessGroup()
        await waitForExit(exitPromise, REAP_TIMEOUT_MS)
      }
    } catch (error) {
      cleanupError = error
    }
    // 子が先に終了しても、パイプを継承した孫を止めて入出力を閉じる。
    try {
      stopProcessGroup()
    } catch (error) {
      cleanupError ??= error
    }
    child.stdin.destroy()
    child.stdout.destroy()
    child.stderr.destroy()
    if (cleanupError)
      throw internal(`子を回収できない: ${String(cleanupError)}`)
  }
}
