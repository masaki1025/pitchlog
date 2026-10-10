// ゲストへ渡すホスト関数は空集合。標準出力は JSON 行プロトコル専用とする。
import vm from 'node:vm'
import readline from 'node:readline'

const HOST_FUNCTIONS = Object.freeze({})
const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity })

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`)
}

function errorCode(error) {
  if (error?.code === 'ERR_SCRIPT_EXECUTION_TIMEOUT') return 'TIME_LIMIT'
  if (error?.code === 'ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING') return 'DYNAMIC_IMPORT_DISABLED'
  if (error instanceof SyntaxError) return 'INVALID_ARTIFACT'
  return 'GUEST_ERROR'
}

let context
let timeout
let initialized = false

for await (const line of input) {
  let message
  try {
    message = JSON.parse(line)
  } catch {
    send({ error: { code: 'PROTOCOL_ERROR' } })
    continue
  }

  if (!initialized) {
    try {
      if (message?.type !== 'init' || typeof message.source !== 'string') {
        throw new Error('invalid initialization')
      }
      if (!Number.isInteger(message.vmTimeoutMs) || message.vmTimeoutMs < 1) {
        throw new Error('invalid timeout')
      }
      timeout = message.vmTimeoutMs
      context = vm.createContext(Object.assign(Object.create(null), HOST_FUNCTIONS), {
        codeGeneration: { strings: false, wasm: false },
      })
      // vm の既定 console はホスト能力なので、artifact の評価前に取り除く。
      vm.runInContext('delete globalThis.console', context, { timeout })
      new vm.Script(message.source, { filename: 'pitchlog-domain.js' }).runInContext(context, {
        timeout,
      })
      const valid = vm.runInContext(
        'typeof globalThis.PitchlogDomain === "object" && Object.isFrozen(globalThis.PitchlogDomain)',
        context,
        { timeout },
      )
      if (!valid) throw new Error('missing frozen entry')
      initialized = true
      send({ type: 'ready' })
    } catch (error) {
      process.stderr.write(`domainrt load failed: ${errorCode(error)}\n`)
      send({ type: 'failed', error: { code: errorCode(error) } })
      break
    }
    continue
  }

  const id = message?.id
  try {
    if (typeof id !== 'string' || typeof message.operation !== 'string' || typeof message.input !== 'string') {
      throw new Error('invalid request')
    }
    // JSON.stringify が操作名と入力を JS ソースへ安全に埋め込む。
    const expression = `globalThis.PitchlogDomain[${JSON.stringify(message.operation)}](${JSON.stringify(message.input)})`
    const result = new vm.Script(expression, { filename: 'domain-call.js' }).runInContext(context, {
      timeout,
    })
    const settled = await result
    if (typeof settled !== 'string') throw new Error('non-string result')
    JSON.parse(settled)
    send({ id, result: settled })
  } catch (error) {
    const code = errorCode(error)
    process.stderr.write(`domainrt call failed: ${code}\n`)
    send({ id, error: { code } })
    if (code === 'TIME_LIMIT') break
  }
}
