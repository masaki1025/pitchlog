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
import {
  deriveQueueStatus,
  type QueueStatusSlot,
} from './GameScreenQueueStatus'
import queueStatusSource from './GameScreenQueueStatus.ts?raw'

function slot(
  state: QueueStatusSlot['state'],
  actionRequiredLabel?: QueueStatusSlot['actionRequiredLabel'],
): QueueStatusSlot {
  return actionRequiredLabel ? { state, actionRequiredLabel } : { state }
}

describe('キューの状態の導出', () => {
  it('状態ごとの件数を正本の状態集合の形で返す', () => {
    const view = deriveQueueStatus({
      slots: [
        slot(queueStateId('未送信')),
        slot(queueStateId('未送信')),
        slot(queueStateId('同期済み')),
        slot(queueStateId('要操作'), actionRequiredLabelId('管理者対応待ち')),
        slot(queueStateId('退避済み')),
      ],
      storagePersistenceGranted: true,
    })

    expect(Object.keys(view.countsByState).sort()).toEqual(
      QUEUE_STATES.map((state) => state.id).sort(),
    )
    expect(view.countsByState).toEqual({
      未送信: 2,
      同期済み: 1,
      要操作: 1,
      退避済み: 1,
    })
    expect(view.unsentCount).toBe(2)
    expect(view.actionRequiredCount).toBe(1)
    expect(view.actionRequiredLabels).toEqual(['管理者対応待ち'])
    expect(view.unrecognizedStateCount).toBe(0)
  })

  it('正本の状態集合に無い値を黙って落とさない', () => {
    const view = deriveQueueStatus({
      slots: [{ state: '未知の状態' as QueueStatusSlot['state'] }],
      storagePersistenceGranted: true,
    })

    expect(view.unrecognizedStateCount).toBe(1)
    expect(view.unsentCount).toBe(0)
  })

  it('未送信件数の通知を常に出す', () => {
    const view = deriveQueueStatus({
      slots: [],
      storagePersistenceGranted: true,
    })

    expect(view.notices).toEqual([createSyncNotice('Q4', { unsentCount: 0 })])
  })

  it('永続ストレージが拒否されたときだけ警告の通知を足す', () => {
    const granted = deriveQueueStatus({
      slots: [],
      storagePersistenceGranted: true,
    })
    const denied = deriveQueueStatus({
      slots: [],
      storagePersistenceGranted: false,
    })
    const unknown = deriveQueueStatus({
      slots: [],
      storagePersistenceGranted: undefined,
    })

    expect(granted.notices.map((notice) => notice.noticeId)).toEqual(['Q4'])
    expect(denied.notices.map((notice) => notice.noticeId)).toEqual([
      'Q4',
      'Q6',
    ])
    // 未確定のうちは拒否と断定しない。
    expect(unknown.notices.map((notice) => notice.noticeId)).toEqual(['Q4'])
  })

  it('受け取った B 区分の通知をそのまま並べる', () => {
    const received = createSyncNotice('B4', {})

    const view = deriveQueueStatus({
      slots: [],
      storagePersistenceGranted: true,
      receivedNotices: [received],
    })

    expect(view.notices.map((notice) => notice.noticeId)).toEqual(['Q4', 'B4'])
  })

  it('未送信の警告の閾値は clientDiscipline の既定に従う', () => {
    const below = deriveQueueStatus({
      slots: Array.from({ length: DEFAULT_UNSENT_WARNING_THRESHOLD - 1 }, () =>
        slot(queueStateId('未送信')),
      ),
      storagePersistenceGranted: true,
    })
    const reached = deriveQueueStatus({
      slots: Array.from({ length: DEFAULT_UNSENT_WARNING_THRESHOLD }, () =>
        slot(queueStateId('未送信')),
      ),
      storagePersistenceGranted: true,
    })

    expect(below.unsentWarning).toBe(false)
    expect(reached.unsentWarning).toBe(true)
  })
})

describe('未同期判定を再実装していないこと', () => {
  it('状態集合と通知のカタログを自前で持たない', () => {
    const code = queueStatusSource
      .split(/\r\n?|\n/)
      .map((line) => line.replace(/\/\/.*$/, ''))
      .join('\n')

    // 状態 ID は正本の照合器を通してから使う。
    expect(code).toContain("queueStateId('未送信')")
    expect(code).toContain("queueStateId('要操作')")
    // 状態の一覧・通知の文面・閾値を自前で持たない。
    expect(code).not.toContain('同期済み')
    expect(code).not.toContain('退避済み')
    expect(code).not.toMatch(/'Q6'/)
    expect(code).not.toMatch(/=\s*350\b/)
  })
})

describe('画面に出る同期の状態', () => {
  it('未送信件数を常に出す', () => {
    const wrapper = mount(GameScreen, {
      props: { queueSlots: [slot(queueStateId('未送信'))] },
    })

    expect(wrapper.get('[data-testid="unsent-count"]').text()).toBe('1')
  })

  it('要操作が利用者に見える', () => {
    const wrapper = mount(GameScreen, {
      props: {
        queueSlots: [
          slot(queueStateId('要操作'), actionRequiredLabelId('改訂待ち')),
        ],
      },
    })

    expect(wrapper.get('[data-testid="action-required-count"]').text()).toBe(
      '1',
    )
    expect(wrapper.get('[data-testid="action-required-labels"]').text()).toBe(
      '改訂待ち',
    )
  })

  it('永続ストレージが拒否されたら警告の文面を出す', () => {
    const wrapper = mount(GameScreen, {
      props: { queueSlots: [], storagePersistence: 'denied' },
    })

    const notices = wrapper.get('[data-testid="sync-notices"]')
    expect(notices.find('[data-notice-id="Q6"]').exists()).toBe(true)
    expect(notices.text()).toContain('永続ストレージの要求が拒否された')
  })

  it('スロットが渡されないときも未送信 0 件として壊れない', () => {
    const wrapper = mount(GameScreen)

    expect(wrapper.get('[data-testid="unsent-count"]').text()).toBe('0')
    expect(wrapper.find('[data-notice-id="Q6"]').exists()).toBe(false)
  })

  it('永続ストレージが許可されていれば警告を出さない', () => {
    const wrapper = mount(GameScreen, {
      props: { queueSlots: [], storagePersistence: 'granted' },
    })

    expect(wrapper.find('[data-notice-id="Q6"]').exists()).toBe(false)
  })
})
