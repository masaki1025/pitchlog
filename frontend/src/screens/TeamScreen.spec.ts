import { setVerifiedAuthForTest } from '../api/auth.test-support'
import {
  focusManager,
  onlineManager,
  VueQueryPlugin,
} from '@tanstack/vue-query'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  ApiNetworkError,
  ApiTenantVerificationError,
} from '../api/client'
import type { Page } from '../api/types'
import {
  listPlayers,
  listTeamRecords,
  readSelfTeamRecord,
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
  readSelfTeamRecord: vi.fn(),
}))

const wrappers: VueWrapper[] = []
const piniaInstances: Pinia[] = []
const listPlayersMock = vi.mocked(listPlayers)
const listTeamRecordsMock = vi.mocked(listTeamRecords)
const readSelfTeamRecordMock = vi.mocked(readSelfTeamRecord)

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
  reject: (reason: unknown) => void
} {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((currentResolve, currentReject) => {
    resolve = currentResolve
    reject = currentReject
  })
  return { promise, resolve, reject }
}

function mountScreen(authenticated = true): {
  auth: ReturnType<typeof useAuthStore>
  pinia: Pinia
  wrapper: VueWrapper
} {
  const pinia = createPinia()
  piniaInstances.push(pinia)
  setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  if (authenticated) {
    setVerifiedAuthForTest(auth, {
      teamId: '9a5850ac-ec9f-5d1e-92d9-be2cb61ccbb0',
      teamName: 'チーム A',
    })
  }
  const wrapper = mount(TeamScreen, {
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
    },
  })
  wrappers.push(wrapper)
  return { auth, pinia, wrapper }
}

beforeEach(() => {
  localStorage.clear()
  queryClient.clear()
  focusManager.setFocused(true)
  onlineManager.setOnline(true)
  queryClient.setDefaultOptions({
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
      staleTime: 30_000,
    },
  })
  listPlayersMock.mockReset()
  listTeamRecordsMock.mockReset()
  readSelfTeamRecordMock.mockReset()
  listPlayersMock.mockResolvedValue(page([]))
  listTeamRecordsMock.mockResolvedValue(page([]))
  readSelfTeamRecordMock.mockResolvedValue(
    teamRecord('self-a', 'チーム A', 'self'),
  )
})

afterEach(() => {
  for (const wrapper of wrappers) wrapper.unmount()
  wrappers.length = 0
  for (const pinia of piniaInstances) disposePinia(pinia)
  piniaInstances.length = 0
  queryClient.clear()
  focusManager.setFocused(true)
  onlineManager.setOnline(true)
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
    expect(readSelfTeamRecordMock).not.toHaveBeenCalled()
    expect(listTeamRecordsMock).not.toHaveBeenCalled()
    expect(listPlayersMock).not.toHaveBeenCalled()
  })

  it.each(['teams', 'players'] as const)(
    '%sのtenant照合失敗はquery既定retryが有効でも自動再送しない',
    async (target) => {
      queryClient.setDefaultOptions({ queries: { retry: 2, retryDelay: 0 } })
      if (target === 'teams') {
        listTeamRecordsMock.mockRejectedValue(
          new ApiTenantVerificationError('GET', '/team-records', 200),
        )
      } else {
        listTeamRecordsMock.mockResolvedValue(
          page([teamRecord('self-a', 'チーム A', 'self')]),
        )
        listPlayersMock.mockRejectedValue(
          new ApiTenantVerificationError('GET', '/players', 200),
        )
      }
      const { wrapper } = mountScreen()
      await vi.waitFor(() =>
        expect(wrapper.text()).toContain('テナントの照合を確認できない'),
      )
      await flushPromises()
      expect(
        target === 'teams' ? listTeamRecordsMock : listPlayersMock,
      ).toHaveBeenCalledTimes(1)
    },
  )

  it('取得したチーム一覧が空なら空状態を表示する', async () => {
    const { wrapper } = mountScreen()

    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('表示できる対戦相手がありません'),
    )

    expect(readSelfTeamRecordMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('チーム A')
    expect(listTeamRecordsMock).toHaveBeenCalledTimes(1)
    expect(listPlayersMock).toHaveBeenCalledWith(
      {
        cursor: null,
        include_hidden: false,
        limit: 25,
        team_record_id: 'self-a',
      },
      { signal: expect.any(AbortSignal) },
    )
  })

  it('selfが404でも対戦相手を別に表示し、selfを捏造しない', async () => {
    readSelfTeamRecordMock.mockRejectedValue(
      new ApiError(404, 'not found', [], undefined, null),
    )
    listTeamRecordsMock.mockResolvedValue(
      page([
        teamRecord('fake-self', '一覧のself', 'self'),
        teamRecord('opponent-a', '対戦相手 A'),
      ]),
    )

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('自チームが見つかりません'),
    )
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 A'))

    expect(wrapper.text()).not.toContain('一覧のself')
    expect(listPlayersMock).toHaveBeenCalledWith(
      expect.objectContaining({ team_record_id: 'opponent-a' }),
      { signal: expect.any(AbortSignal) },
    )
    expect(listPlayersMock).not.toHaveBeenCalledWith(
      expect.objectContaining({ team_record_id: 'fake-self' }),
      expect.anything(),
    )
  })

  it('self通信失敗を対戦相手成功と独立表示する', async () => {
    readSelfTeamRecordMock.mockRejectedValue(
      new ApiNetworkError(new Error('接続失敗')),
    )
    listTeamRecordsMock.mockResolvedValue(
      page([teamRecord('opponent-a', '対戦相手 A')]),
    )

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('自チームを取得できませんでした'),
    )
    expect(wrapper.text()).toContain('対戦相手 A')
    expect(readSelfTeamRecordMock).toHaveBeenCalledTimes(1)
  })

  it('後着selfを初回優先選択し、明示した対戦相手は上書きしない', async () => {
    const selfResponse = deferred<TeamRecordRead>()
    readSelfTeamRecordMock.mockImplementation(() => selfResponse.promise)
    listTeamRecordsMock.mockResolvedValue(
      page([teamRecord('opponent-a', '対戦相手 A')]),
    )

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 A'))
    expect(wrapper.text()).toContain('自チームを読み込んでいます')
    expect(wrapper.get('#players-heading').text()).toBe('選手')
    expect(listPlayersMock).not.toHaveBeenCalled()

    selfResponse.resolve(teamRecord('self-a', 'チーム A', 'self'))
    await vi.waitFor(() =>
      expect(wrapper.get('#players-heading').text()).toContain('チーム A'),
    )
    expect(listPlayersMock).toHaveBeenCalledWith(
      expect.objectContaining({ team_record_id: 'self-a' }),
      { signal: expect.any(AbortSignal) },
    )

    const opponent = wrapper
      .findAll('[data-testid="team-record-list"] button')
      .find((button) => button.text().includes('対戦相手 A'))
    await opponent!.trigger('click')
    expect(wrapper.get('#players-heading').text()).toContain('対戦相手 A')
    void queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.teamRecords.all(
        '9a5850ac-ec9f-5d1e-92d9-be2cb61ccbb0',
      ),
    })
    await flushPromises()
    expect(wrapper.get('#players-heading').text()).toContain('対戦相手 A')
  })

  it('self待機中に明示選択した対戦相手を後着selfで上書きしない', async () => {
    const selfResponse = deferred<TeamRecordRead>()
    readSelfTeamRecordMock.mockImplementation(() => selfResponse.promise)
    listTeamRecordsMock.mockResolvedValue(
      page([
        teamRecord('opponent-a', '対戦相手 A'),
        teamRecord('opponent-b', '対戦相手 B'),
      ]),
    )

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 B'))
    const opponent = wrapper
      .findAll('[data-testid="team-record-list"] button')
      .find((button) => button.text().includes('対戦相手 B'))
    expect(listPlayersMock).not.toHaveBeenCalled()
    await opponent!.trigger('click')
    await vi.waitFor(() =>
      expect(listPlayersMock).toHaveBeenCalledWith(
        expect.objectContaining({ team_record_id: 'opponent-b' }),
        { signal: expect.any(AbortSignal) },
      ),
    )
    await wrapper.get('input[name="player-name"]').setValue('入力中の選手')
    selfResponse.resolve(teamRecord('self-a', 'チーム A', 'self'))
    await vi.waitFor(() => expect(wrapper.text()).toContain('チーム A自チーム'))

    expect(wrapper.get('#players-heading').text()).toContain('対戦相手 B')
    expect(
      (wrapper.get('input[name="player-name"]').element as HTMLInputElement)
        .value,
    ).toBe('入力中の選手')
    expect(listPlayersMock).not.toHaveBeenCalledWith(
      expect.objectContaining({ team_record_id: 'self-a' }),
      expect.anything(),
    )
  })

  it.each(['404', 'network'] as const)(
    'self待機後の%s失敗で既存対戦相手を自動選択する',
    async (failureKind) => {
      const selfResponse = deferred<TeamRecordRead>()
      readSelfTeamRecordMock.mockImplementation(() => selfResponse.promise)
      listTeamRecordsMock.mockResolvedValue(
        page([teamRecord('opponent-a', '対戦相手 A')]),
      )

      const { wrapper } = mountScreen()
      await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 A'))
      expect(wrapper.get('#players-heading').text()).toBe('選手')
      expect(listPlayersMock).not.toHaveBeenCalled()

      selfResponse.reject(
        failureKind === '404'
          ? new ApiError(404, 'not found', [], undefined, null)
          : new ApiNetworkError(new Error('接続失敗')),
      )
      await vi.waitFor(() =>
        expect(wrapper.get('#players-heading').text()).toContain('対戦相手 A'),
      )
      expect(listTeamRecordsMock).toHaveBeenCalledTimes(1)
      expect(listPlayersMock).toHaveBeenCalledWith(
        expect.objectContaining({ team_record_id: 'opponent-a' }),
        { signal: expect.any(AbortSignal) },
      )
    },
  )

  it.each(['dto', 'network'] as const)(
    'selfの%s失敗後は再接続・focus・remount・GC後も明示操作まで再送しない',
    async (failureKind) => {
      queryClient.setDefaultOptions({
        queries: {
          gcTime: 10,
          refetchOnMount: true,
          refetchOnReconnect: true,
          refetchOnWindowFocus: true,
          retry: 2,
          retryDelay: 0,
          staleTime: 0,
        },
      })
      const failure =
        failureKind === 'dto'
          ? new ApiError(
              200,
              '自チームの応答を確認できません',
              [],
              undefined,
              undefined,
            )
          : new ApiNetworkError(new Error('接続失敗'))
      readSelfTeamRecordMock
        .mockRejectedValueOnce(failure)
        .mockResolvedValueOnce(teamRecord('self-a', 'チーム A', 'self'))

      const { pinia, wrapper } = mountScreen()
      await vi.waitFor(() =>
        expect(wrapper.find('[data-testid="self-team-error"]').exists()).toBe(
          true,
        ),
      )
      const key = rosterQueryKeys.selfTeamRecord(
        '9a5850ac-ec9f-5d1e-92d9-be2cb61ccbb0',
        useAuthStore(pinia).authEpoch,
      )
      expect(
        queryClient.getQueryCache().find({ queryKey: key })?.options,
      ).toMatchObject({
        gcTime: Infinity,
        retry: false,
        retryOnMount: false,
        refetchOnMount: false,
        refetchOnReconnect: false,
        refetchOnWindowFocus: false,
        refetchInterval: false,
      })
      expect(listPlayersMock).not.toHaveBeenCalled()
      focusManager.setFocused(false)
      focusManager.setFocused(true)
      onlineManager.setOnline(false)
      onlineManager.setOnline(true)
      await flushPromises()
      wrapper.unmount()
      await new Promise((resolve) => setTimeout(resolve, 30))
      expect(queryClient.getQueryState(key)?.status).toBe('error')

      const remounted = mount(TeamScreen, {
        global: { plugins: [pinia, [VueQueryPlugin, { queryClient }]] },
      })
      wrappers.push(remounted)
      await flushPromises()
      focusManager.setFocused(false)
      focusManager.setFocused(true)
      onlineManager.setOnline(false)
      onlineManager.setOnline(true)
      await flushPromises()
      expect(readSelfTeamRecordMock).toHaveBeenCalledTimes(1)

      await remounted
        .get('[data-testid="self-team-error"] button')
        .trigger('click')
      await vi.waitFor(() =>
        expect(remounted.get('#players-heading').text()).toContain('チーム A'),
      )
      expect(readSelfTeamRecordMock).toHaveBeenCalledTimes(2)
    },
  )

  it('初回取得に失敗した一覧を旧データなしで再試行する', async () => {
    listTeamRecordsMock
      .mockRejectedValueOnce(new Error('初回取得失敗'))
      .mockResolvedValueOnce(page([teamRecord('opponent-a', '対戦相手 A')]))

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('チーム一覧を取得できませんでした'),
    )
    expect(wrapper.text()).not.toContain('対戦相手 A')

    const retry = wrapper
      .findAll('button')
      .find((button) => button.text() === '再試行')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 A'))

    expect(listTeamRecordsMock).toHaveBeenCalledTimes(2)
  })

  it('一覧の再取得失敗時は旧データの鮮度を警告して再試行する', async () => {
    listTeamRecordsMock
      .mockResolvedValueOnce(page([teamRecord('opponent-a', '対戦相手 A')]))
      .mockRejectedValueOnce(new ApiNetworkError(new Error('接続失敗')))
      .mockResolvedValueOnce(
        page([teamRecord('opponent-a', '対戦相手 A 更新')]),
      )

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="team-record-list"]').exists()).toBe(
        true,
      ),
    )

    void queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.teamRecords.all(
        '9a5850ac-ec9f-5d1e-92d9-be2cb61ccbb0',
      ),
    })
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('表示中の情報は古い可能性があります'),
    )
    expect(wrapper.text()).toContain('対戦相手 A')

    const retry = wrapper
      .findAll('[role="alert"] button')
      .find((button) => button.text() === '再試行')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 A 更新'))
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
      queryKey: rosterQueryKeys.players.all(
        '9a5850ac-ec9f-5d1e-92d9-be2cb61ccbb0',
      ),
    })
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('表示中だった情報を隠しました'),
    )

    expect(wrapper.text()).not.toContain('選手 A')
    expect(wrapper.find('[data-testid="player-list"]').exists()).toBe(false)
    expect(wrapper.find('input[name="player-edit-name"]').exists()).toBe(false)
  })

  it('チーム一覧の再取得が404なら旧対戦相手の編集状態を消す', async () => {
    listTeamRecordsMock
      .mockResolvedValueOnce(
        page([
          teamRecord('self-a', 'チーム A', 'self'),
          teamRecord('opponent-a', '対戦相手 A'),
        ]),
      )
      .mockRejectedValueOnce(
        new ApiError(404, 'not found', [], undefined, null),
      )

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 A'))
    await wrapper
      .get('select[name="opponent-edit-target"]')
      .setValue('opponent-a')
    expect(wrapper.find('input[name="opponent-edit-name"]').exists()).toBe(true)

    void queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.teamRecords.all(
        '9a5850ac-ec9f-5d1e-92d9-be2cb61ccbb0',
      ),
    })
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('表示中だった情報を隠しました'),
    )

    expect(wrapper.text()).not.toContain('対戦相手 A')
    expect(wrapper.find('[data-testid="team-record-list"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('チーム A')
    expect(wrapper.find('input[name="opponent-edit-name"]').exists()).toBe(
      false,
    )
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
        page([teamRecord('opponent-a', '既存の対戦相手 A')], 'teams-next'),
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
    expect(wrapper.text()).toContain('既存の対戦相手 A')
    expect(wrapper.text()).toContain('チーム A')

    const retry = wrapper
      .findAll('button')
      .find((button) => button.text() === '再試行')
    expect(retry).toBeDefined()
    await retry!.trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 B'))
    expect(wrapper.text()).toContain('既存の対戦相手 A')

    expect(listTeamRecordsMock).toHaveBeenNthCalledWith(
      3,
      { cursor: 'teams-next', include_hidden: false, limit: 25 },
      { signal: expect.any(AbortSignal) },
    )
  })

  it('認証切替時に旧一覧と選択を直ちに隠して新チームだけを表示する', async () => {
    const teamB = deferred<Page<TeamRecordRead>>()
    readSelfTeamRecordMock
      .mockResolvedValueOnce(teamRecord('self-a', 'チーム A', 'self'))
      .mockResolvedValueOnce(teamRecord('self-b', 'チーム B', 'self'))
    listTeamRecordsMock
      .mockResolvedValueOnce(page([teamRecord('opponent-a', '旧対戦相手 A')]))
      .mockImplementationOnce(() => teamB.promise)
    listPlayersMock
      .mockResolvedValueOnce(page([player('player-a1', 'self-a', '選手 A1')]))
      .mockResolvedValueOnce(page([player('player-b1', 'self-b', '選手 B1')]))

    const { auth, wrapper } = mountScreen()
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('選手 A1')
      expect(wrapper.text()).toContain('旧対戦相手 A')
    })

    setVerifiedAuthForTest(auth, {
      teamId: '659a85f2-ccb4-5725-a7b8-81c34caf8870',
      teamName: 'チーム B',
    })
    await flushPromises()

    expect(wrapper.text()).not.toContain('選手 A1')
    expect(wrapper.text()).not.toContain('旧対戦相手 A')
    expect(wrapper.text()).not.toContain('チーム A自チーム')
    expect(wrapper.text()).toContain('対戦相手を読み込んでいます')

    teamB.resolve(page([teamRecord('opponent-b', '新対戦相手 B')]))
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('新対戦相手 B')
      expect(wrapper.text()).toContain('選手 B1')
    })
    expect(wrapper.text()).not.toContain('旧対戦相手 A')
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
    readSelfTeamRecordMock
      .mockResolvedValueOnce(teamRecord('self-a', 'チーム A', 'self'))
      .mockResolvedValueOnce(teamRecord('self-b', 'チーム B', 'self'))
    listTeamRecordsMock
      .mockImplementationOnce(() => oldResponse.promise)
      .mockResolvedValueOnce(page([teamRecord('opponent-b', '新対戦相手 B')]))
    listPlayersMock.mockResolvedValue(
      page([player('player-b1', 'self-b', '選手 B1')]),
    )

    const { auth, wrapper } = mountScreen()
    await vi.waitFor(() => expect(listTeamRecordsMock).toHaveBeenCalledTimes(1))

    setVerifiedAuthForTest(auth, {
      teamId: '659a85f2-ccb4-5725-a7b8-81c34caf8870',
      teamName: 'チーム B',
    })
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain('選手 B1')
      expect(wrapper.text()).toContain('新対戦相手 B')
    })

    oldResponse.resolve(page([teamRecord('opponent-a', '古い対戦相手 A')]))
    await flushPromises()

    expect(wrapper.text()).toContain('選手 B1')
    expect(wrapper.text()).toContain('新対戦相手 B')
    expect(wrapper.text()).not.toContain('古い対戦相手 A')
    expect(listPlayersMock).toHaveBeenCalledTimes(1)
  })

  it('遅延self応答を別tenant・新epochへ採用しない', async () => {
    const oldSelf = deferred<TeamRecordRead>()
    readSelfTeamRecordMock
      .mockImplementationOnce(() => oldSelf.promise)
      .mockResolvedValueOnce(teamRecord('self-b', 'チーム B', 'self'))
    listPlayersMock.mockResolvedValue(
      page([player('player-b', 'self-b', '選手 B')]),
    )

    const { auth, wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(readSelfTeamRecordMock).toHaveBeenCalledTimes(1),
    )
    setVerifiedAuthForTest(auth, {
      teamId: '659a85f2-ccb4-5725-a7b8-81c34caf8870',
      teamName: 'チーム B',
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('選手 B'))

    oldSelf.resolve(teamRecord('self-a', '古い自チーム A', 'self'))
    await flushPromises()
    expect(wrapper.text()).not.toContain('古い自チーム A')
    expect(wrapper.get('#players-heading').text()).toContain('チーム B')
    expect(listPlayersMock).not.toHaveBeenCalledWith(
      expect.objectContaining({ team_record_id: 'self-a' }),
      expect.anything(),
    )
  })

  it('旧epochのself失敗cacheを新しい検証済みtenantへ引き継がない', async () => {
    readSelfTeamRecordMock
      .mockRejectedValueOnce(
        new ApiError(
          200,
          '自チームの応答を確認できません',
          [],
          undefined,
          undefined,
        ),
      )
      .mockResolvedValueOnce(teamRecord('self-b', 'チーム B', 'self'))
    const { auth, wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.find('[data-testid="self-team-error"]').exists()).toBe(
        true,
      ),
    )

    setVerifiedAuthForTest(auth, {
      teamId: '659a85f2-ccb4-5725-a7b8-81c34caf8870',
      teamName: 'チーム B',
    })
    await vi.waitFor(() =>
      expect(wrapper.get('#players-heading').text()).toContain('チーム B'),
    )
    expect(wrapper.find('[data-testid="self-team-error"]').exists()).toBe(false)
    expect(readSelfTeamRecordMock).toHaveBeenCalledTimes(2)
  })

  it('利用者入力を HTML として挿入しない', async () => {
    readSelfTeamRecordMock.mockResolvedValue(
      teamRecord('self-a', '<img src=x onerror=alert(1)>', 'self'),
    )
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
