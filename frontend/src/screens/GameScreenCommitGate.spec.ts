import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GameScreen from './GameScreen.vue'
import gameScreenSource from './GameScreen.vue?raw'
import {
  PITCH_COMMIT_BLOCK_REASON,
  resolvePitchCommitGate,
} from './GameScreenCommitGate'
import commitGateSource from './GameScreenCommitGate.ts?raw'

const openedDatabases: string[] = []

function observation() {
  return {
    battedBall: false,
    rbiRulingRequired: false,
    scoringCandidateRunners: [],
  }
}

beforeEach(() => {
  openedDatabases.length = 0
  vi.stubGlobal('fetch', vi.fn())
  // キューを開こうとしたら記録する(開かないことを挙動で確かめるため)。
  vi.stubGlobal('indexedDB', {
    open: (name: string) => {
      openedDatabases.push(name)
      throw new Error('試験中はキューを開かせない')
    },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('確定の封鎖', () => {
  it('第 1 期は確定できず、理由を伴う', () => {
    const gate = resolvePitchCommitGate()

    expect(gate.committable).toBe(false)
    if (gate.committable) return
    expect(gate.reason).toBe(PITCH_COMMIT_BLOCK_REASON)
    expect(gate.reason).toContain('状況計算核')
  })

  it('封鎖を外す箇所が 1 つに閉じている', () => {
    const switchDeclarations = commitGateSource
      .split(/\r\n?|\n/)
      .filter((line) => /PITCH_COMMIT_BLOCKED\s*:\s*boolean\s*=/.test(line))

    expect(switchDeclarations).toHaveLength(1)
    expect(switchDeclarations[0]).toContain('= true')
    // 判断の複製を防ぐため、スイッチは外へ出さない。
    expect(commitGateSource).not.toMatch(
      /export\s+const\s+PITCH_COMMIT_BLOCKED/,
    )
  })
})

describe('画面から確定の経路へ到達できない', () => {
  it('確定の操作が無効化され、理由が表示される', () => {
    const wrapper = mount(GameScreen)

    const button = wrapper.get<HTMLButtonElement>(
      '[data-testid="commit-pitch"]',
    )
    expect(button.element.disabled).toBe(true)
    expect(wrapper.get('[data-testid="commit-blocked-reason"]').text()).toBe(
      PITCH_COMMIT_BLOCK_REASON,
    )
    expect(button.attributes('aria-describedby')).toBe('commit-blocked-reason')
  })

  it('確定の操作に処理が結び付いていない', () => {
    const commitButton = /<button[^>]*data-testid="commit-pitch"[\s\S]*?>/.exec(
      gameScreenSource,
    )

    expect(commitButton).not.toBeNull()
    expect(commitButton?.[0]).not.toContain('@click')
    expect(commitButton?.[0]).not.toContain('type="submit"')
  })

  it('画面が確定の経路のモジュールを import しない', () => {
    // 文字列の有無ではなく import 文の宛先を見る(注釈に出てくる名前で
    // 誤検知せず、import を足す変異を確実に捕まえるため)。
    const imported = [...gameScreenSource.matchAll(/from\s+'([^']+)'/g)].map(
      (match) => match[1] ?? '',
    )

    expect(imported.length).toBeGreaterThan(0)
    for (const forbidden of [
      './GameScreenPitchCommit',
      './GameScreenPitchAcceptance',
      './GameScreenAckApplication',
      '../api/client.syncEvents',
      '../lib/sync/durableQueue',
      '../lib/sync/singleWriter',
      '../lib/sync/clientDiscipline',
    ]) {
      expect(imported).not.toContain(forbidden)
    }
  })

  it.each([
    ['確定の経路', 'commitPitchEvent'],
    ['採番・永続追記・受理', 'acceptPitchEvent'],
    ['排他なしの追記', 'appendPitchEventUnderLock'],
    ['送信', 'postSyncEvents'],
    ['ACK の適用', 'applyAckToSlot'],
    ['キューの開設', 'openDurableQueue'],
  ])('画面が %s を呼ばない', (_label, identifier) => {
    expect(gameScreenSource).not.toContain(identifier)
  })

  it('画面を操作しても送信もキューの開設も起きない', async () => {
    const wrapper = mount(GameScreen, {
      props: { unsentCount: 0, inputObservation: observation() },
    })

    for (const button of wrapper.findAll('button')) {
      await button.trigger('click')
    }
    for (const input of wrapper.findAll('input, select')) {
      await input.trigger('change')
      await input.trigger('input')
    }
    for (const form of wrapper.findAll('form')) {
      await form.trigger('submit')
    }

    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
    expect(openedDatabases).toEqual([])
  })

  it('画面が確定の可否を単一のゲートからだけ読む', () => {
    expect(gameScreenSource).toContain('resolvePitchCommitGate()')
    expect(gameScreenSource).not.toContain('PITCH_COMMIT_BLOCKED')
  })
})
