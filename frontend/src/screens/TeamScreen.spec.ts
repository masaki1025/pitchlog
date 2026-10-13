import { VueQueryPlugin } from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, ApiNetworkError } from '../api/client'
import type { Page } from '../api/types'
import {
  listPlayers,
  listTeamRecords,
  type PlayerRead,
  type TeamRecordRead,
} from '../api/roster'
import { queryClient } from '../lib/queryClient'
import { rosterQueryKeys } from '../lib/rosterQueryKeys'
import { useAuthStore } from '../stores/authStore'
import TeamScreen from './TeamScreen.vue'

vi.mock('../api/roster', () => ({
  listPlayers: vi.fn(),
  listTeamRecords: vi.fn(),
}))

const wrappers: VueWrapper[] = []
const piniaInstances: Pinia[] = []
const listPlayersMock = vi.mocked(listPlayers)
const listTeamRecordsMock = vi.mocked(listTeamRecords)

function teamRecord(
  id: string,
  name: string,
  kind: TeamRecordRead['kind'] = 'opponent',
): TeamRecordRead {
  return { hidden_at: null, id, kind, name }
}

function player(id: string, teamRecordId: string, name: string): PlayerRead {
  return {
    bats: 'left',
    hidden_at: null,
    id,
    name,
    roster_label_key: null,
    roster_status_key: 'active',
    team_record_id: teamRecordId,
    throws: 'right',
    uniform_number: '18',
  }
}

function page<T>(items: T[], nextCursor: string | null = null): Page<T> {
  return { items, next_cursor: nextCursor }
}

function deferred<T>(): {
  promise: Promise<T>
  resolve: (value: T) => void
} {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((currentResolve) => {
    resolve = currentResolve
  })
  return { promise, resolve }
}

function mountScreen(authenticated = true): {
  auth: ReturnType<typeof useAuthStore>
  wrapper: VueWrapper
} {
  const pinia = createPinia()
  piniaInstances.push(pinia)
  setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  if (authenticated) {
    auth.signIn({ teamId: 'tenant-a', teamName: 'チーム A' })
  }
  const wrapper = mount(TeamScreen, {
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
    },
  })
  wrappers.push(wrapper)
  return { auth, wrapper }
}

beforeEach(() => {
  localStorage.clear()
  queryClient.clear()
  queryClient.setDefaultOptions({
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
      staleTime: 30_000,
    },
  })
  listPlayersMock.mockReset()
  listTeamRecordsMock.mockReset()
  listPlayersMock.mockResolvedValue(page([]))
  listTeamRecordsMock.mockResolvedValue(page([]))
})

afterEach(() => {
  for (const wrapper of wrappers) wrapper.unmount()
  wrappers.length = 0
  for (const pinia of piniaInstances) disposePinia(pinia)
  piniaInstances.length = 0
  queryClient.clear()
  queryClient.setDefaultOptions({
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30_000,
    },
  })
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('TeamScreen', () => {
  it('teamId がない間は API を呼ばない', async () => {
    const { wrapper } = mountScreen(false)

    await flushPromises()

    expect(wrapper.text()).toContain('認証済みチーム情報の確認待ちです')
    expect(listTeamRecordsMock).not.toHaveBeenCalled()
    expect(listPlayersMock).not.toHaveBeenCalled()
  })

  it('取得したチーム一覧が空なら空状態を表示する', async () => {
    const { wrapper } = mountScreen()

    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('表示できるチームがありません'),
    )

    expect(listTeamRecordsMock).toHaveBeenCalledTimes(1)
    expect(listPlayersMock).not.toHaveBeenCalled()
  })

  it('初回取得に失敗した一覧を旧データなしで再試行する', async () => {
    listTeamRecordsMock
      .mockRejectedValueOnce(new Error('初回取得失敗'))
      .mockResolvedValueOnce(page([teamRecord('self-a', 'チーム A', 'self')]))

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('チーム一覧を取得できませんでした'),
    )
    expect(wrapper.find('[data-testid="team-record-list"]').exists()).toBe(
      false,
    )

    const retry = wrapper
      .findAll('button')
      .find((button) => button.text() === '再試行')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="team-record-list"]').exists()).toBe(
        true,
      ),
    )

    expect(listTeamRecordsMock).toHaveBeenCalledTimes(2)
  })

  it('一覧の再取得失敗時は旧データの鮮度を警告して再試行する', async () => {
    listTeamRecordsMock
      .mockResolvedValueOnce(page([teamRecord('self-a', 'チーム A', 'self')]))
      .mockRejectedValueOnce(new ApiNetworkError(new Error('接続失敗')))
      .mockResolvedValueOnce(
        page([teamRecord('self-a', 'チーム A 更新', 'self')]),
      )

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="team-record-list"]').exists()).toBe(
        true,
      ),
    )

    void queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.teamRecords.all('tenant-a'),
    })
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('表示中の情報は古い可能性があります'),
    )
    expect(wrapper.text()).toContain('チーム A')

    const retry = wrapper
      .findAll('[role="alert"] button')
      .find((button) => button.text() === '再試行')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('チーム A 更新'))
    expect(wrapper.text()).not.toContain('表示中の情報は古い可能性があります')
  })

  it('選手一覧の再取得が404なら取得済み行を隠す', async () => {
    listTeamRecordsMock.mockResolvedValue(
      page([teamRecord('self-a', 'チーム A', 'self')]),
    )
    listPlayersMock
      .mockResolvedValueOnce(page([player('player-a', 'self-a', '選手 A')]))
      .mockRejectedValueOnce(
        new ApiError(404, 'not found', [], undefined, null),
      )

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 A'))
    await wrapper.get('select[name="player-edit-target"]').setValue('player-a')
    expect(wrapper.find('input[name="player-edit-name"]').exists()).toBe(true)

    void queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.players.all('tenant-a'),
    })
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('表示中だった情報を隠しました'),
    )

    expect(wrapper.text()).not.toContain('選手 A')
    expect(wrapper.find('[data-testid="player-list"]').exists()).toBe(false)
    expect(wrapper.find('input[name="player-edit-name"]').exists()).toBe(false)
  })

  it('チームと選手を cursor 付きでページングし、選択チームを切り替える', async () => {
    listTeamRecordsMock
      .mockResolvedValueOnce(
        page(
          [
            teamRecord('self-a', 'チーム A', 'self'),
            teamRecord('opponent-b', '対戦相手 B'),
          ],
          'teams-next',
        ),
      )
      .mockResolvedValueOnce(page([teamRecord('opponent-c', '対戦相手 C')]))
    listPlayersMock.mockImplementation(async (query) => {
      if (query.team_record_id === 'self-a' && query.cursor === null) {
        return page([player('player-a1', 'self-a', '選手 A1')], 'players-next')
      }
      if (
        query.team_record_id === 'self-a' &&
        query.cursor === 'players-next'
      ) {
        return page([player('player-a2', 'self-a', '選手 A2')])
      }
      if (query.team_record_id === 'opponent-b') {
        return page([player('player-b1', 'opponent-b', '選手 B1')])
      }
      return page([])
    })

    const { wrapper } = mountScreen()

    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 A1'))
    expect(listTeamRecordsMock).toHaveBeenNthCalledWith(
      1,
      { cursor: null, include_hidden: false, limit: 25 },
      { signal: expect.any(AbortSignal) },
    )
    expect(listPlayersMock).toHaveBeenNthCalledWith(
      1,
      {
        cursor: null,
        include_hidden: false,
        limit: 25,
        team_record_id: 'self-a',
      },
      { signal: expect.any(AbortSignal) },
    )

    await wrapper
      .get('button[aria-label="選手をさらに読み込む"]')
      .trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 A2'))
    expect(listPlayersMock).toHaveBeenNthCalledWith(
      2,
      {
        cursor: 'players-next',
        include_hidden: false,
        limit: 25,
        team_record_id: 'self-a',
      },
      { signal: expect.any(AbortSignal) },
    )
    expect(
      wrapper.find('button[aria-label="選手をさらに読み込む"]').exists(),
    ).toBe(false)

    await wrapper
      .get('button[aria-label="チームをさらに読み込む"]')
      .trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 C'))
    expect(listTeamRecordsMock).toHaveBeenNthCalledWith(
      2,
      { cursor: 'teams-next', include_hidden: false, limit: 25 },
      { signal: expect.any(AbortSignal) },
    )

    const opponentButton = wrapper
      .findAll('[data-testid="team-record-list"] button')
      .find((button) => button.text().includes('対戦相手 B'))
    expect(opponentButton).toBeDefined()
    await opponentButton!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 B1'))
    expect(wrapper.text()).not.toContain('選手 A1')
  })

  it('追加取得の失敗時に取得済み行を残して同じ cursor を再試行する', async () => {
    listTeamRecordsMock
      .mockResolvedValueOnce(
        page([teamRecord('self-a', 'チーム A', 'self')], 'teams-next'),
      )
      .mockRejectedValueOnce(new Error('接続失敗'))
      .mockResolvedValueOnce(page([teamRecord('opponent-b', '対戦相手 B')]))

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(
        wrapper.find('button[aria-label="チームをさらに読み込む"]').exists(),
      ).toBe(true),
    )

    await wrapper
      .get('button[aria-label="チームをさらに読み込む"]')
      .trigger('click')
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('次のチームを取得できませんでした'),
    )
    expect(wrapper.text()).toContain('チーム A')

    const retry = wrapper
      .findAll('button')
      .find((button) => button.text() === '再試行')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 B'))

    expect(listTeamRecordsMock).toHaveBeenNthCalledWith(
      3,
      { cursor: 'teams-next', include_hidden: false, limit: 25 },
      { signal: expect.any(AbortSignal) },
    )
  })

  it('認証切替時に旧一覧と選択を直ちに隠して新チームだけを表示する', async () => {
    const teamB = deferred<Page<TeamRecordRead>>()
    listTeamRecordsMock
      .mockResolvedValueOnce(page([teamRecord('self-a', 'チーム A', 'self')]))
      .mockImplementationOnce(() => teamB.promise)
    listPlayersMock
      .mockResolvedValueOnce(page([player('player-a1', 'self-a', '選手 A1')]))
      .mockResolvedValueOnce(page([player('player-b1', 'self-b', '選手 B1')]))

    const { auth, wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 A1'))

    auth.signIn({ teamId: 'tenant-b', teamName: 'チーム B' })
    await flushPromises()

    expect(wrapper.text()).not.toContain('選手 A1')
    expect(wrapper.text()).not.toContain('チーム A自チーム')
    expect(wrapper.text()).toContain('チームを読み込んでいます')

    teamB.resolve(page([teamRecord('self-b', 'チーム B', 'self')]))
    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 B1'))
    expect(wrapper.text()).not.toContain('選手 A1')
    expect(listPlayersMock).toHaveBeenLastCalledWith(
      {
        cursor: null,
        include_hidden: false,
        limit: 25,
        team_record_id: 'self-b',
      },
      { signal: expect.any(AbortSignal) },
    )
  })

  it('切替前の遅延応答が後から完了しても新認証の表示へ混ぜない', async () => {
    const oldResponse = deferred<Page<TeamRecordRead>>()
    listTeamRecordsMock
      .mockImplementationOnce(() => oldResponse.promise)
      .mockResolvedValueOnce(page([teamRecord('self-b', 'チーム B', 'self')]))
    listPlayersMock.mockResolvedValue(
      page([player('player-b1', 'self-b', '選手 B1')]),
    )

    const { auth, wrapper } = mountScreen()
    await vi.waitFor(() => expect(listTeamRecordsMock).toHaveBeenCalledTimes(1))

    auth.signIn({ teamId: 'tenant-b', teamName: 'チーム B' })
    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 B1'))

    oldResponse.resolve(page([teamRecord('self-a', '古いチーム A', 'self')]))
    await flushPromises()

    expect(wrapper.text()).toContain('選手 B1')
    expect(wrapper.text()).not.toContain('古いチーム A')
    expect(listPlayersMock).toHaveBeenCalledTimes(1)
  })

  it('利用者入力を HTML として挿入しない', async () => {
    listTeamRecordsMock.mockResolvedValue(
      page([teamRecord('self-a', '<img src=x onerror=alert(1)>', 'self')]),
    )
    listPlayersMock.mockResolvedValue(
      page([player('player-a1', 'self-a', '<script>alert(1)</script>')]),
    )

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('<script>alert(1)</script>'),
    )

    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  })
})
