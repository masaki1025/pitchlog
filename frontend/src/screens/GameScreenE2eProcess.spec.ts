import { spawn } from 'node:child_process'
import { chmodSync, existsSync, rmSync, statSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import {
  cleanupGameScreenOutputDirectory,
  finishGameScreenChild,
  gameScreenOutputDirectory,
  waitForGameScreenChildExit,
} from './GameScreenE2eProcess'

describe('自分のE2E子プロセスの終了契約', () => {
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
