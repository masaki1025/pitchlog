import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { Script, createContext, runInContext, type Context } from 'node:vm'
import type { CalculationAdapter, GeneratedNormalizer } from './vectorRunner'

export type ArtifactCall = Readonly<{
  operation: string
  requestJson: string
  responseJson: string
}>

export class VmArtifactError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'VmArtifactError'
  }
}

function rejectNumbers(value: unknown): void {
  if (typeof value === 'number') {
    throw new VmArtifactError('整数は十進文字列で渡す')
  }
  if (Array.isArray(value)) {
    for (const item of value) rejectNumbers(item)
  } else if (typeof value === 'object' && value !== null) {
    for (const item of Object.values(value)) rejectNumbers(item)
  }
}

export class VmArtifactAdapter
  implements GeneratedNormalizer, CalculationAdapter
{
  readonly generatedId: string
  readonly sourceHash: string
  readonly calls: ArtifactCall[] = []
  private readonly context: Context
  private readonly timeoutMs: number

  constructor(artifactPath: string, generatedId: string, timeoutMs = 100) {
    const source = readFileSync(artifactPath)
    this.generatedId = generatedId
    this.sourceHash = `sha256:${createHash('sha256').update(source).digest('hex')}`
    this.timeoutMs = timeoutMs
    this.context = createContext(Object.create(null) as object, {
      codeGeneration: { strings: false, wasm: false },
    })
    runInContext('delete globalThis.console', this.context, {
      timeout: timeoutMs,
    })
    new Script(source.toString('utf8'), {
      filename: 'pitchlog-domain.js',
    }).runInContext(this.context, { timeout: timeoutMs })
    const ready = runInContext(
      'typeof globalThis.PitchlogDomain === "object" && Object.isFrozen(globalThis.PitchlogDomain)',
      this.context,
      { timeout: timeoutMs },
    ) as unknown
    if (ready !== true) throw new VmArtifactError('公開口の検査に失敗')
  }

  call(operation: string, requestJson: string): string {
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(operation)) {
      throw new VmArtifactError('操作名が不正')
    }
    rejectNumbers(JSON.parse(requestJson) as unknown)
    const expression = `globalThis.PitchlogDomain[${JSON.stringify(operation)}](${JSON.stringify(requestJson)})`
    const result = new Script(expression, {
      filename: 'domain-call.js',
    }).runInContext(this.context, { timeout: this.timeoutMs }) as unknown
    if (typeof result !== 'string') {
      throw new VmArtifactError('結果が JSON 文字列でない')
    }
    rejectNumbers(JSON.parse(result) as unknown)
    this.calls.push({ operation, requestJson, responseJson: result })
    return result
  }

  private invoke(operation: string, request: unknown): unknown {
    rejectNumbers(request)
    const requestJson = JSON.stringify(request)
    if (typeof requestJson !== 'string') {
      throw new VmArtifactError('入力が JSON 値でない')
    }
    return JSON.parse(this.call(operation, requestJson)) as unknown
  }

  normalize(raw: unknown): unknown {
    return this.invoke('normalize', raw)
  }

  execute(caseId: string, normalized: unknown): unknown {
    return this.invoke('calculate', { caseId, normalized })
  }
}
