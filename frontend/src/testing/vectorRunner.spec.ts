import { ChildProcess } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { expect, it, vi } from 'vitest'
import {
  DEFAULT_RESPONSE_TIMEOUT_MS,
  runVectors,
  UnsupportedVectorCase,
  VectorRunError,
  VectorRunnerError,
  type CalculationAdapter,
  type GeneratedNormalizer,
  type VectorContract,
} from './vectorRunner'

vi.setConfig({ testTimeout: 3 * DEFAULT_RESPONSE_TIMEOUT_MS + 5_000 })

const REPOSITORY_ROOT = resolve(process.cwd(), '..')
const fixture = JSON.parse(
  readFileSync(
    resolve(
      REPOSITORY_ROOT,
      'tests/domain/runners/fixtures/vector-conformance/vector_conformance_v1.json',
    ),
    'utf8',
  ),
) as {
  scenarios: {
    id: string
    cases: unknown[]
    contract: Omit<VectorContract, 'runner'>
    normalizer: {
      generatedId: string
      sourceHash: string
      table: { normalized: unknown }[]
    }
  }[]
}
const selected = fixture.scenarios.find(
  (scenario) => scenario.id === 'valid-two-cases',
)
if (!selected) throw new Error('valid-two-cases がない')
const valid = selected

const contract: VectorContract = { ...valid.contract, runner: 'vitest' }
const cases = valid.cases
const values = valid.normalizer.table.map((entry) => entry.normalized)
function standardNormalizer(): GeneratedNormalizer {
  let index = 0
  return {
    generatedId: valid.normalizer.generatedId,
    sourceHash: valid.normalizer.sourceHash,
    normalize: () => values[index++],
  }
}
const echo: CalculationAdapter = { execute: (_caseId, value) => value }

async function expectInternal(
  command: readonly [string, ...string[]],
  responseTimeoutMs?: number,
): Promise<VectorRunnerError> {
  let caught: unknown
  try {
    await runVectors(cases, contract, standardNormalizer(), echo, {
      command,
      responseTimeoutMs,
    })
  } catch (error) {
    caught = error
  }
  expect(caught).toBeInstanceOf(VectorRunnerError)
  return caught as VectorRunnerError
}

function expectReaped(error: Error): void {
  const match = /PID=(\d+)/.exec(error.message)
  expect(match).not.toBeNull()
  expectPidGone(Number(match?.[1]))
}

function expectPidGone(pid: number): void {
  let code: string | undefined
  try {
    process.kill(pid, 0)
  } catch (failure) {
    code = (failure as NodeJS.ErrnoException).code
  }
  expect(code).toBe('ESRCH')
}

function stopRecordedProcess(pid: number | undefined): void {
  if (pid === undefined) return
  try {
    process.kill(pid, 'SIGKILL')
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ESRCH') throw error
  }
}

function readRecordedPid(path: string): number | undefined {
  let text: string
  try {
    text = readFileSync(path, 'utf8')
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return undefined
    throw error
  }
  const complete = /^([1-9]\d*)\n$/.exec(text)
  if (!complete) return undefined
  const pid = Number(complete[1])
  if (!Number.isSafeInteger(pid))
    throw new Error(`記録された PID が不正: ${text}`)
  return pid
}

async function waitForRecordedPid(path: string): Promise<number | undefined> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    const pid = readRecordedPid(path)
    if (pid !== undefined) return pid
    await new Promise((resolveWait) => setTimeout(resolveWait, 10))
  }
  return undefined
}

async function withPidFile<T>(
  run: (pidFile: string) => Promise<T>,
): Promise<T> {
  const directory = mkdtempSync(join(tmpdir(), 'vector-runner-'))
  const pidFile = join(directory, 'process.pid')
  try {
    return await run(pidFile)
  } finally {
    try {
      // runner が先に失敗しても、子が直後に書く PID を待って停止する。
      const pid = await waitForRecordedPid(pidFile)
      stopRecordedProcess(pid)
      if (pid !== undefined) await expectPidStopped(pid)
    } finally {
      rmSync(directory, { recursive: true, force: true })
    }
  }
}

function denyGroupSignal(onAttempt: () => void): ReturnType<typeof vi.spyOn> {
  const realKill = process.kill.bind(process)
  return vi.spyOn(process, 'kill').mockImplementation((pid, signal) => {
    if (pid < 0 && signal === 'SIGKILL') {
      onAttempt()
      throw Object.assign(new Error('注入したグループ signal 失敗'), {
        code: 'EPERM',
      })
    }
    return realKill(pid, signal)
  })
}

function recordGroupSignals(calls: number[]): ReturnType<typeof vi.spyOn> {
  const realKill = process.kill.bind(process)
  return vi.spyOn(process, 'kill').mockImplementation((pid, signal) => {
    if (pid < 0) {
      calls.push(pid)
      return true
    }
    return realKill(pid, signal)
  })
}

async function expectPidStopped(pid: number): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    let state: string | undefined
    try {
      state = readFileSync(`/proc/${pid}/stat`, 'utf8').split(') ')[1]?.[0]
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    }
    // 親が先に終了すると、停止済みの孫が一時的に zombie として残る。
    if (state === undefined || state === 'Z') return
    await new Promise((resolveWait) => setTimeout(resolveWait, 10))
  }
  throw new Error(`孫プロセス ${pid} が実行中のまま残った`)
}

function script(body: string): readonly [string, string, string] {
  return [
    'python3',
    '-c',
    `import os,sys,time\nprint('PID='+str(os.getpid()), file=sys.stderr, flush=True)\n${body}`,
  ]
}

function inheritedPipeCommand(
  terminal: 'vector-run-error' | 'adapter-error',
  pidFile: string,
): readonly [string, string, string] {
  const message =
    terminal === 'vector-run-error'
      ? "{'type':'vector-run-error','message':'意図したベクタ異常'}"
      : "{'type':'adapter-error'}"
  return script(
    `import json,pathlib,subprocess\ngrandchild=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)\npathlib.Path(${JSON.stringify(pidFile)}).write_text(str(grandchild.pid)+chr(10), encoding='utf-8')\nprint(json.dumps({'type':'normalize','raw':{}}), flush=True)\nsys.stdin.readline()\nprint(json.dumps(${message}), flush=True)`,
  )
}

function arrayWithLostNumericKey<T>(items: T[]): T[] {
  Object.defineProperty(items, '4294967295', {
    value: 'JSON に含まれない値',
    enumerable: true,
  })
  return items
}

it('正規化出力の元のオブジェクトを計算 adapter へ渡す', async () => {
  const outputs: unknown[] = []
  let index = 0
  const report = await runVectors(
    cases,
    contract,
    {
      generatedId: valid.normalizer.generatedId,
      sourceHash: valid.normalizer.sourceHash,
      normalize: () => {
        const output = structuredClone(values[index++])
        outputs.push(output)
        return output
      },
    },
    {
      execute: (_caseId, value) => {
        expect(value).toBe(outputs.shift())
        return value
      },
    },
  )
  expect(report.complete).toBe(true)
  expect(report.declaredCaseIds).toEqual(['caseOne', 'caseTwo'])
  expect(report.consumedCaseIds).toEqual(['caseOne', 'caseTwo'])
  expect(report.executions).toHaveLength(2)
})

it('report の complete を再計算せず運び、成功した子も回収する', async () => {
  const report = await runVectors(cases, contract, standardNormalizer(), echo, {
    command: script(
      `print('{"type":"report","declaredCaseIds":["'+str(os.getpid())+'"],"consumedCaseIds":[],"executions":[],"complete":false}', flush=True)`,
    ),
  })
  expect(report.complete).toBe(false)
  expectPidGone(Number(report.declaredCaseIds[0]))
})

it('正規化 adapter の UnsupportedVectorCase を元の例外のまま送出する', async () => {
  const failure = new UnsupportedVectorCase('正規化に失敗')
  await expect(
    runVectors(
      cases,
      contract,
      {
        ...standardNormalizer(),
        normalize: () => {
          throw failure
        },
      },
      echo,
    ),
  ).rejects.toBe(failure)
})

it('計算 adapter の一般例外を元の例外のまま送出する', async () => {
  const failure = new Error('計算に失敗')
  await expect(
    runVectors(cases, contract, standardNormalizer(), {
      execute: () => {
        throw failure
      },
    }),
  ).rejects.toBe(failure)
})

it('文字列化できない adapter 例外も元のオブジェクトのまま送出する', async () => {
  const failure = {
    toString: () => {
      throw new Error('文字列化は不可')
    },
  }
  await expect(
    runVectors(cases, contract, standardNormalizer(), {
      execute: () => {
        throw failure
      },
    }),
  ).rejects.toBe(failure)
})

it('計算 adapter の UnsupportedVectorCase は既存 runner のエラーになる', async () => {
  await expect(
    runVectors(cases, contract, standardNormalizer(), {
      execute: () => {
        throw new UnsupportedVectorCase()
      },
    }),
  ).rejects.toMatchObject({
    name: 'VectorRunError',
    message: '未対応 case: caseOne',
  } satisfies Partial<VectorRunError>)
})

it.each([
  ['undefined', undefined],
  ['bigint', 1n],
  ['NaN', NaN],
  ['Infinity', Infinity],
  ['negative zero', -0],
  ['unsafe integer', 2 ** 53],
  ['function', () => 1],
  ['symbol', Symbol('value')],
  ['nested undefined', { rows: [{ value: undefined }] }],
  ['nested bigint', { rows: [{ value: 1n }] }],
  ['nested NaN', { rows: [{ value: NaN }] }],
  ['nested negative zero', { rows: [{ value: -0 }] }],
  ['nested unsafe integer', { rows: [{ value: 2 ** 53 }] }],
  ['nonplain object', new Date()],
])('送信前に JSON で往復できない %s を拒否する', async (_label, value) => {
  await expect(
    runVectors(value, contract, standardNormalizer(), echo),
  ).rejects.toBeInstanceOf(VectorRunnerError)
  await expect(
    runVectors(
      cases,
      contract,
      { ...standardNormalizer(), normalize: () => value },
      echo,
    ),
  ).rejects.toBeInstanceOf(VectorRunnerError)
})

it('start の cases に添字でない数字キーがある配列を拒否する', async () => {
  await expect(
    runVectors(
      arrayWithLostNumericKey([...cases]),
      contract,
      standardNormalizer(),
      echo,
    ),
  ).rejects.toBeInstanceOf(VectorRunnerError)
})

it.each(['normalizer', 'calculation'])(
  '%s の戻り値に添字でない数字キーがある配列を拒否する',
  async (phase) => {
    if (phase === 'normalizer') {
      await expect(
        runVectors(
          cases,
          contract,
          {
            ...standardNormalizer(),
            normalize: () => arrayWithLostNumericKey([values[0]]),
          },
          echo,
        ),
      ).rejects.toBeInstanceOf(VectorRunnerError)
    } else {
      await expect(
        runVectors(cases, contract, standardNormalizer(), {
          execute: () => arrayWithLostNumericKey([values[0]]),
        }),
      ).rejects.toBeInstanceOf(VectorRunnerError)
    }
  },
)

it.each(['normalizer', 'calculation'])(
  '%s の thenable を拒否する',
  async (phase) => {
    if (phase === 'normalizer') {
      await expect(
        runVectors(
          cases,
          contract,
          {
            ...standardNormalizer(),
            normalize: () => Promise.resolve(values[0]),
          },
          echo,
        ),
      ).rejects.toBeInstanceOf(VectorRunnerError)
    } else {
      await expect(
        runVectors(cases, contract, standardNormalizer(), {
          execute: () => Promise.resolve(values[0]),
        }),
      ).rejects.toBeInstanceOf(VectorRunnerError)
    }
  },
)

it('計算 adapter の戻り値も送信前に再帰的に検査する', async () => {
  await expect(
    runVectors(cases, contract, standardNormalizer(), {
      execute: () => ({ nested: [2 ** 53] }),
    }),
  ).rejects.toBeInstanceOf(VectorRunnerError)
})

it('Node のタイマー上限を超える応答期限を拒否する', async () => {
  await expect(
    runVectors(cases, contract, standardNormalizer(), echo, {
      command: ['/definitely/missing/vector-bridge'],
      responseTimeoutMs: 2 ** 31,
    }),
  ).rejects.toMatchObject({
    name: 'VectorRunnerError',
    message: expect.stringContaining('タイマー範囲'),
  } satisfies Partial<VectorRunnerError>)
})

it('起動に失敗した子を内部異常として扱う', async () => {
  const error = await expectInternal(['/definitely/missing/vector-bridge'])
  expect(error.message).toContain('spawn')
})

it('終端前に終了した子を回収する', async () => {
  const error = await expectInternal(script('sys.exit(0)'))
  expectReaped(error)
})

it('終端前に終了した子のコードと stderr を診断に残す', async () => {
  const error = await expectInternal(
    script("print('診断用 stderr', file=sys.stderr, flush=True)\nsys.exit(7)"),
  )
  expect(error.message).toContain('code=7')
  expect(error.message).toContain('診断用 stderr')
  expectReaped(error)
})

it('無応答の子を期限後に停止し回収する', async () => {
  const error = await expectInternal(script('time.sleep(60)'), 300)
  expect(error.message).toContain('応答')
  expectReaped(error)
})

it('report 後も終了しない子を停止し回収する', async () => {
  const error = await expectInternal(
    script(
      `print('''{"type":"report","declaredCaseIds":[],"consumedCaseIds":[],"executions":[],"complete":true}''', flush=True)\ntime.sleep(60)`,
    ),
    300,
  )
  expect(error.message).toContain('終了')
  expectReaped(error)
})

it('子が終了して孫がパイプを保持しても signal せず決着する', async () => {
  await withPidFile(async (pidFile) => {
    // 別セッションの孫がパイプを保持しても元のグループへ signal しない。
    const timeoutMs = 300
    const started = Date.now()
    const groupSignals: number[] = []
    const spy = recordGroupSignals(groupSignals)
    try {
      const report = await runVectors(
        cases,
        contract,
        standardNormalizer(),
        echo,
        {
          command: script(
            `import json,pathlib,subprocess\ngrandchild=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, start_new_session=True)\npathlib.Path(${JSON.stringify(pidFile)}).write_text(str(grandchild.pid)+chr(10), encoding='utf-8')\nprint(json.dumps({'type':'report','declaredCaseIds':[str(os.getpid())],'consumedCaseIds':[],'executions':[],'complete':False}), flush=True)`,
          ),
          responseTimeoutMs: timeoutMs,
        },
      )
      expect(Date.now() - started).toBeLessThan(timeoutMs + 1_000)
      expect(report.complete).toBe(false)
      expectPidGone(Number(report.declaredCaseIds[0]))
      expect(groupSignals).toEqual([])
    } finally {
      spy.mockRestore()
    }
  })
})

it('パイプを継承しない孫は成功後も生存する', async () => {
  await withPidFile(async (pidFile) => {
    const report = await runVectors(
      cases,
      contract,
      standardNormalizer(),
      echo,
      {
        command: script(
          `import json,pathlib,subprocess\ngrandchild=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\npathlib.Path(${JSON.stringify(pidFile)}).write_text(str(grandchild.pid)+chr(10), encoding='utf-8')\nprint(json.dumps({'type':'report','declaredCaseIds':[],'consumedCaseIds':[],'executions':[],'complete':False}), flush=True)`,
        ),
        responseTimeoutMs: 300,
      },
    )
    expect(report.complete).toBe(false)
    const grandchildPid = readRecordedPid(pidFile)
    expect(grandchildPid).toBeDefined()
    if (grandchildPid === undefined) return
    expect(process.kill(grandchildPid, 0)).toBe(true)
    expect(
      readFileSync(`/proc/${grandchildPid}/stat`, 'utf8').split(') ')[1]?.[0],
    ).not.toBe('Z')
  })
})

it('子の exit 後は VectorRunError でもグループへ signal しない', async () => {
  await withPidFile(async (pidFile) => {
    let signalAttempts = 0
    const spy = denyGroupSignal(() => {
      signalAttempts += 1
    })
    let caught: unknown
    try {
      await runVectors(cases, contract, standardNormalizer(), echo, {
        command: inheritedPipeCommand('vector-run-error', pidFile),
      })
    } catch (error) {
      caught = error
    } finally {
      spy.mockRestore()
    }
    expect(signalAttempts).toBe(0)
    expect(caught).toBeInstanceOf(VectorRunError)
    expect((caught as VectorRunError).message).toBe('意図したベクタ異常')
  })
})

it('子の exit 後は adapter の元の例外でもグループへ signal しない', async () => {
  await withPidFile(async (pidFile) => {
    const failure = new Error('元の adapter 例外')
    let signalAttempts = 0
    const spy = denyGroupSignal(() => {
      signalAttempts += 1
    })
    let caught: unknown
    try {
      await runVectors(
        cases,
        contract,
        {
          ...standardNormalizer(),
          normalize: () => {
            throw failure
          },
        },
        echo,
        { command: inheritedPipeCommand('adapter-error', pidFile) },
      )
    } catch (error) {
      caught = error
    } finally {
      spy.mockRestore()
    }
    expect(signalAttempts).toBe(0)
    expect(caught).toBe(failure)
  })
})

it('主処理の内部異常は回収中の signal 失敗で上書きしない', async () => {
  let signalAttempts = 0
  const spy = denyGroupSignal(() => {
    signalAttempts += 1
  })
  let error: VectorRunnerError
  try {
    error = await expectInternal(
      script("print('not json', flush=True)\ntime.sleep(30)"),
    )
  } finally {
    spy.mockRestore()
  }
  expect(signalAttempts).toBeGreaterThan(0)
  expect(error.message).toContain('ブリッジの JSON 行が不正')
  expectReaped(error)
})

it('起動後の error を exit と誤認せず回収失敗を診断する', async () => {
  await withPidFile(async (pidFile) => {
    const groupSpy = denyGroupSignal(() => undefined)
    const childKillSpy = vi
      .spyOn(ChildProcess.prototype, 'kill')
      .mockImplementation(function (this: ChildProcess) {
        this.emit(
          'error',
          Object.assign(new Error('注入した子 kill 失敗'), { code: 'EPERM' }),
        )
        return false
      })
    try {
      const error = await expectInternal(
        script(
          `import pathlib\npathlib.Path(${JSON.stringify(pidFile)}).write_text(str(os.getpid())+chr(10), encoding='utf-8')\ntime.sleep(30)`,
        ),
        300,
      )
      expect(error.message).toContain('応答')
      expect(error.message).toContain('子を回収できない')
      expect(error.message).toContain('注入した子 kill 失敗')
      expect(error.message).toContain('終了未観測')
    } finally {
      childKillSpy.mockRestore()
      groupSpy.mockRestore()
    }
  })
})

it('終端前に子が終了して孫がパイプを保持しても期限内に回収する', async () => {
  await withPidFile(async (pidFile) => {
    const timeoutMs = 300
    const started = Date.now()
    const error = await expectInternal(
      script(
        `import pathlib,subprocess\ngrandchild=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)\npathlib.Path(${JSON.stringify(pidFile)}).write_text(str(grandchild.pid)+chr(10), encoding='utf-8')`,
      ),
      timeoutMs,
    )
    // 応答期限のあと、パイプの閉鎖を最大 1 秒待つ。
    expect(Date.now() - started).toBeLessThan(timeoutMs + 1_500)
    expectReaped(error)
  })
})

it('report 後の非 0 終了を内部異常として扱い子を回収する', async () => {
  const error = await expectInternal(
    script(
      `print('''{"type":"report","declaredCaseIds":[],"consumedCaseIds":[],"executions":[],"complete":true}''', flush=True)\nsys.exit(7)`,
    ),
  )
  expect(error.message).toContain('code=7')
  expectReaped(error)
})

it('既定の期限でも無応答の子をテスト期限内に回収する', async () => {
  const started = Date.now()
  const error = await expectInternal(script('time.sleep(60)'))
  expect(Date.now() - started).toBeLessThan(3 * DEFAULT_RESPONSE_TIMEOUT_MS)
  expectReaped(error)
})

it('判定の語を runner のソースに持たない', () => {
  const source = readFileSync(
    resolve(process.cwd(), 'src/testing/vectorRunner.ts'),
    'utf8',
  )
  expect(source).not.toContain('additionalProperties')
  expect(source).not.toContain('total-order')
  expect(source).not.toContain('exact-numeric-representation')
})
