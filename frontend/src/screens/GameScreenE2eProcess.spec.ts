// @vitest-environment node

import { spawn, spawnSync } from 'node:child_process'
import { chmodSync, existsSync, mkdtempSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import {
  gameScreenE2eOrigin,
  type GameScreenE2eMode,
} from './GameScreenE2eSupport'
import {
  cleanupGameScreenOutputDirectory,
  finishGameScreenChild,
  gameScreenOutputDirectory,
  waitForGameScreenChildExit,
} from './GameScreenE2eProcess'

describe('自分のE2E子プロセスの終了契約', () => {
  it.each([
    ['preparing-read', 'https://127.0.0.1:43210'],
    ['sealed-ui', 'http://127.0.0.1:43210'],
    ['preparing-read', 'http://example.test:43210'],
  ])('%sはモード外origin %sをDB起動前に拒否する', (mode, origin) => {
    const backend = fileURLToPath(new URL('../../../backend/', import.meta.url))
    const script = fileURLToPath(
      new URL('./GameScreenE2eSupport.py', import.meta.url),
    )
    const directory = mkdtempSync(
      resolve(tmpdir(), 'pitchlog-e2e-origin-check-'),
    )
    try {
      chmodSync(directory, 0o700)
      const result = spawnSync(resolve(backend, '.venv/bin/python'), [script], {
        cwd: backend,
        encoding: 'utf8',
        timeout: 10_000,
        env: {
          PATH: process.env.PATH,
          PYTHONPATH: [resolve(backend, 'tests'), resolve(backend, 'src')].join(
            ':',
          ),
          PITCHLOG_E2E_READY_FILE: resolve(directory, 'backend-ready.json'),
          PITCHLOG_E2E_STOP_FILE: resolve(directory, 'stop'),
          PITCHLOG_E2E_MODE: mode,
          PITCHLOG_E2E_FRONTEND_ORIGIN: origin,
        },
      })
      expect(result.status).toBe(1)
      expect(result.stderr).toContain(
        'E2E origin は明示モードの専用loopbackポートだけ許す',
      )
      expect(existsSync(resolve(directory, 'backend-ready.json'))).toBe(false)
    } finally {
      rmSync(directory, { recursive: true })
    }
  })
  it('readだけHTTPのloopbackを使い、封鎖画面のHTTPSを保持する', () => {
    expect(gameScreenE2eOrigin('preparing-read', 43210)).toBe(
      'http://127.0.0.1:43210',
    )
    expect(gameScreenE2eOrigin('sealed-ui', 43210)).toBe(
      'https://127.0.0.1:43210',
    )
    expect(() =>
      gameScreenE2eOrigin('unknown' as GameScreenE2eMode, 43210),
    ).toThrow('明示モード')
    for (const port of [0, -1, 65536, 1.5, NaN, Infinity])
      expect(() => gameScreenE2eOrigin('preparing-read', port)).toThrow(
        '専用ポート',
      )
  })
  it('config再評価は同じ0700出力先を使い、自分の終端で消す', () => {
    const names = [
      'PITCHLOG_E2E_OUTPUT_DIR',
      'PITCHLOG_E2E_OUTPUT_TOKEN',
      'PITCHLOG_E2E_OUTPUT_OWNER_PID',
    ] as const
    const saved = names.map((name) => process.env[name])
    try {
      for (const name of names) delete process.env[name]
      const first = gameScreenOutputDirectory()
      expect(gameScreenOutputDirectory()).toBe(first)
      expect(statSync(first).mode & 0o777).toBe(0o700)
      // Playwrightが子出力を消しても、親の所有markerで同じrunを復元する。
      rmSync(first, { recursive: true })
      expect(gameScreenOutputDirectory()).toBe(first)
      const root = process.env.PITCHLOG_E2E_OUTPUT_DIR
      if (!root) throw new Error('試験用の親出力先がない')
      chmodSync(root, 0o755)
      try {
        expect(() => gameScreenOutputDirectory()).toThrow('所有証跡が不正')
      } finally {
        chmodSync(root, 0o700)
      }
      cleanupGameScreenOutputDirectory()
      expect(existsSync(first)).toBe(false)
    } finally {
      for (const [index, name] of names.entries()) {
        if (saved[index] === undefined) delete process.env[name]
        else process.env[name] = saved[index]
      }
    }
  })

  it('正常終了0だけを成功として回収する', async () => {
    const child = spawn(process.execPath, ['-e', 'process.exit(0)'], {
      stdio: 'ignore',
    })
    await expect(
      finishGameScreenChild(child, 5_000, 5_000),
    ).resolves.toBeUndefined()
  })

  it('異常終了を成功へ変換しない', async () => {
    const child = spawn(process.execPath, ['-e', 'process.exit(7)'], {
      stdio: 'ignore',
    })
    await expect(finishGameScreenChild(child, 5_000, 5_000)).rejects.toThrow(
      '異常終了',
    )
  })

  it('自分の子への正常なSIGTERM後の非0を失敗とする', async () => {
    const child = spawn(
      process.execPath,
      [
        '-e',
        'process.on("SIGTERM", () => process.exit(143)); setInterval(() => {}, 100)',
      ],
      { stdio: 'ignore' },
    )
    await expect(finishGameScreenChild(child, 200, 5_000)).rejects.toThrow(
      '異常終了',
    )
    const exit = await waitForGameScreenChildExit(child, 100)
    expect(exit?.code === 143 || exit?.signal === 'SIGTERM').toBe(true)
  })
})
