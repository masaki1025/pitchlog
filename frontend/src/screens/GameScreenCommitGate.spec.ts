import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GameScreen from './GameScreen.vue'
import gameScreenSource from './GameScreen.vue?raw'
import {
  PITCH_COMMIT_BLOCK_REASON,
  resolvePitchCommitGate,
} from './GameScreenCommitGate'
import commitGateSource from './GameScreenCommitGate.ts?raw'

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

  it.each([
    ['採番・永続追記・受理', 'GameScreenPitchAcceptance'],
    ['送信', 'client.syncEvents'],
    ['ACK の適用', 'GameScreenAckApplication'],
    ['永続キュー', 'durableQueue'],
    ['単一書き手', 'singleWriter'],
    ['キューの規律', 'clientDiscipline'],
  ])('画面が %s の経路を参照しない', (_label, moduleName) => {
    expect(gameScreenSource).not.toContain(moduleName)
  })

  it('画面が確定の可否を単一のゲートからだけ読む', () => {
    expect(gameScreenSource).toContain('resolvePitchCommitGate()')
    expect(gameScreenSource).not.toContain('PITCH_COMMIT_BLOCKED')
  })
})
