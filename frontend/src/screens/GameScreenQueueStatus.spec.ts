import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { DEFAULT_UNSENT_WARNING_THRESHOLD } from '../lib/sync/clientDiscipline'
import {
  actionRequiredLabelId,
  QUEUE_STATES,
  queueStateId,
} from '../lib/sync/queueState'
import { createSyncNotice } from '../lib/sync/syncNotices'
import GameScreen from './GameScreen.vue'
import { deriveQueueStatus } from './GameScreenQueueStatus'
import queueStatusSource from './GameScreenQueueStatus.ts?raw'

describe('キューの状態の導出', () => {
  it('件数を受け取り、状態ごとに正本の ID で引ける形で返す', () => {
    const view = deriveQueueStatus({
      unsentCount: 2,
      actionRequired: {
        count: 1,
        labels: [actionRequiredLabelId('管理者対応待ち')],
      },
      evacuatedCount: 3,
      storagePersistenceGranted: true,
    })

    expect(view.countsByState[queueStateId('未送信')]).toBe(2)
    expect(view.countsByState[queueStateId('要操作')]).toBe(1)
    expect(view.countsByState[queueStateId('退避済み')]).toBe(3)
    expect(view.actionRequiredLabels).toEqual(['管理者対応待ち'])
  })

  it('正本の状態のうち件数が供給されていないものを顕在化する', () => {
    const view = deriveQueueStatus({
      unsentCount: 1,
      storagePersistenceGranted: true,
    })

    // 同期済みは供給していないので、0 と見せず未供給として出す。
    expect(view.unsuppliedStates).toContain(queueStateId('同期済み'))
    expect(view.countsByState[queueStateId('同期済み')]).toBeUndefined()
  })

  it('正本の状態をすべて供給すれば未供給が無くなる', () => {
    const view = deriveQueueStatus({
      unsentCount: 1,
      actionRequired: { count: 0, labels: [] },
      evacuatedCount: 0,
      syncedCount: 2,
      storagePersistenceGranted: true,
    })

    expect(view.unsuppliedStates).toEqual([])
    expect(Object.keys(view.countsByState).sort()).toEqual(
      QUEUE_STATES.map((state) => state.id).sort(),
    )
  })

  it('未送信件数がまだ読めていなければ、0 と偽らない', () => {
    const view = deriveQueueStatus({
      unsentCount: undefined,
      storagePersistenceGranted: true,
    })

    expect(view.unsentCount).toBeUndefined()
    expect(view.countsByState[queueStateId('未送信')]).toBeUndefined()
    // 件数が無いのに「0 件です」という通知を出さない。
    expect(view.notices).toEqual([])
  })

  it('未送信件数の通知が実際の件数を運ぶ', () => {
    const view = deriveQueueStatus({
      unsentCount: 7,
      storagePersistenceGranted: true,
    })

    expect(view.notices).toEqual([createSyncNotice('Q4', { unsentCount: 7 })])
  })

  it('永続ストレージが拒否されたときだけ警告の通知を足す', () => {
    const ids = (granted: boolean | undefined) =>
      deriveQueueStatus({
        unsentCount: 0,
        storagePersistenceGranted: granted,
      }).notices.map((notice) => notice.noticeId)

    expect(ids(true)).toEqual(['Q4'])
    expect(ids(false)).toEqual(['Q4', 'Q6'])
    // 未確定のうちは拒否と断定しない。
    expect(ids(undefined)).toEqual(['Q4'])
  })

  it('受け取った B 区分の通知をそのまま並べる', () => {
    const view = deriveQueueStatus({
      unsentCount: 0,
      storagePersistenceGranted: true,
      receivedNotices: [createSyncNotice('B4', {})],
    })

    expect(view.notices.map((notice) => notice.noticeId)).toEqual(['Q4', 'B4'])
  })

  it('警告の判定が渡されればそれを使う', () => {
    expect(
      deriveQueueStatus({
        unsentCount: 999,
        unsentWarning: false,
        storagePersistenceGranted: true,
      }).unsentWarning,
    ).toBe(false)
    expect(
      deriveQueueStatus({
        unsentCount: 1,
        unsentWarning: true,
        storagePersistenceGranted: true,
      }).unsentWarning,
    ).toBe(true)
  })

  it('判定が渡されなければ件数から導き、閾値は clientDiscipline の既定に従う', () => {
    const at = (count: number) =>
      deriveQueueStatus({
        unsentCount: count,
        storagePersistenceGranted: true,
      }).unsentWarning

    expect(at(DEFAULT_UNSENT_WARNING_THRESHOLD - 1)).toBe(false)
    expect(at(DEFAULT_UNSENT_WARNING_THRESHOLD)).toBe(true)
  })
})

describe('件数の導出と閾値の式を画面側に持たないこと', () => {
  it('件数を数える処理も閾値の比較も本モジュールに無い', () => {
    const code = queueStatusSource
      .split(/\r\n?|\n/)
      .map((line) => line.replace(/\/\/.*$/, ''))
      .join('\n')

    // 入力を走査して数え直さない(NFR-005 の型)。回してよいのは正本の
    // 状態表(QUEUE_STATES・4 件の定数)だけで、input は走査しない。
    expect(code).not.toMatch(/for\s*\([^)]*\binput\b/)
    expect(code).not.toMatch(
      /input\.[A-Za-z]+\.(?:filter|reduce|map|forEach|some)\(/,
    )
    expect(code).toContain('for (const state of QUEUE_STATES)')
    // 閾値の「値」を自前で持たない(比較は clientDiscipline の定数で行う)。
    expect(code).not.toMatch(/=\s*350\b/)
    expect(code).toContain('DEFAULT_UNSENT_WARNING_THRESHOLD')
    // 通知 ID を自前で組み立てない(カタログから作る)。
    expect(code).not.toMatch(/'Q6'/)
    expect(code).not.toMatch(/noticeId\s*:/)
    // 状態 ID は正本の照合器を通す。
    expect(code).toContain("queueStateId('未送信')")
    expect(code).toContain("queueStateId('要操作')")
    expect(code).toContain("queueStateId('退避済み')")
  })
})

describe('画面に出る同期の状態', () => {
  it('未送信・要操作・退避済みを別の件数として併記する', () => {
    const wrapper = mount(GameScreen, {
      props: {
        unsentCount: 2,
        actionRequired: {
          count: 1,
          labels: [actionRequiredLabelId('改訂待ち')],
        },
        evacuatedCount: 4,
      },
    })

    expect(wrapper.get('[data-testid="unsent-count"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="action-required-count"]').text()).toBe(
      '1',
    )
    expect(wrapper.get('[data-testid="evacuated-count"]').text()).toBe('4')
    expect(wrapper.get('[data-testid="action-required-labels"]').text()).toBe(
      '改訂待ち',
    )
  })

  it('未送信件数が未取得なら 0 と見せない', () => {
    const wrapper = mount(GameScreen)

    expect(wrapper.get('[data-testid="unsent-count"]').text()).toBe('未取得')
  })

  it('未送信の警告は渡されたときだけ出す', () => {
    expect(
      mount(GameScreen, { props: { unsentCount: 400 } })
        .find('[data-testid="unsent-warning"]')
        .exists(),
    ).toBe(false)
    expect(
      mount(GameScreen, {
        props: { unsentCount: 400, unsentWarning: true },
      })
        .get('[data-testid="unsent-warning"]')
        .text(),
    ).toContain('未送信が多く')
  })

  it('永続ストレージが拒否されたら警告の文面を出す', () => {
    const wrapper = mount(GameScreen, {
      props: { unsentCount: 0, storagePersistence: 'denied' },
    })

    const notices = wrapper.get('[data-testid="sync-notices"]')
    expect(notices.find('[data-notice-id="Q6"]').exists()).toBe(true)
    expect(notices.text()).toContain('永続ストレージの要求が拒否された')
  })

  it('契約の説明文である Q4 を利用者向けの通知として出さない', () => {
    const wrapper = mount(GameScreen, { props: { unsentCount: 3 } })

    expect(wrapper.find('[data-notice-id="Q4"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('未送信件数を表示します')
  })
})
