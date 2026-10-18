import { VueQueryPlugin } from '@tanstack/vue-query'
import {
  flushPromises,
  mount,
  type DOMWrapper,
  type VueWrapper,
} from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  apiRequest,
  ApiError,
  ApiNetworkError,
  ApiStaleAuthError,
  ApiTenantVerificationError,
} from '../../api/client'
import {
  createPlayer,
  createTeamRecord,
  listPlayers,
  listTeamRecords,
  updatePlayer,
  updateTeamRecord,
  type PlayerCreated,
  type PlayerRead,
  type TeamRecordCreated,
  type TeamRecordRead,
} from '../../api/roster'
import type { Page } from '../../api/types'
import { queryClient } from '../../lib/queryClient'
import { rosterQueryKeys } from '../../lib/rosterQueryKeys'
import TeamScreen from '../../screens/TeamScreen.vue'
import { useAuthStore } from '../../stores/authStore'

vi.mock('../../api/roster', () => ({
  createPlayer: vi.fn(),
  createTeamRecord: vi.fn(),
  listPlayers: vi.fn(),
  listTeamRecords: vi.fn(),
  updatePlayer: vi.fn(),
  updateTeamRecord: vi.fn(),
}))

const wrappers: VueWrapper[] = []
const piniaInstances: Pinia[] = []
const createPlayerMock = vi.mocked(createPlayer)
const createTeamRecordMock = vi.mocked(createTeamRecord)
const listPlayersMock = vi.mocked(listPlayers)
const listTeamRecordsMock = vi.mocked(listTeamRecords)
const updatePlayerMock = vi.mocked(updatePlayer)
const updateTeamRecordMock = vi.mocked(updateTeamRecord)

function teamRecord(
  id: string,
  name: string,
  kind: TeamRecordRead['kind'] = 'opponent',
): TeamRecordRead {
  return { hidden_at: null, id, kind, name }
}

function player(
  id: string,
  teamRecordId: string,
  name: string,
  uniformNumber: string | null = '18',
): PlayerRead {
  return {
    bats: 'left',
    hidden_at: null,
    id,
    name,
    roster_label_key: null,
    roster_status_key: 'active',
    team_record_id: teamRecordId,
    throws: 'right',
    uniform_number: uniformNumber,
  }
}

function page<T>(items: T[]): Page<T> {
  return { items, next_cursor: null }
}

function deferred<T>(): {
  promise: Promise<T>
  reject: (error: unknown) => void
  resolve: (value: T) => void
} {
  let reject!: (error: unknown) => void
  let resolve!: (value: T) => void
  const promise = new Promise<T>((currentResolve, currentReject) => {
    resolve = currentResolve
    reject = currentReject
  })
  return { promise, reject, resolve }
}

function mountScreen(teamId = 'tenant-a'): {
  auth: ReturnType<typeof useAuthStore>
  wrapper: VueWrapper
} {
  const pinia = createPinia()
  piniaInstances.push(pinia)
  setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  auth.signIn({ teamId, teamName: 'チーム A' })
  const wrapper = mount(TeamScreen, {
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
    },
  })
  wrappers.push(wrapper)
  return { auth, wrapper }
}

function buttonWithText(
  wrapper: VueWrapper,
  text: string,
): DOMWrapper<Element> {
  const button = wrapper
    .findAll('button')
    .find((candidate) => candidate.text() === text)
  expect(button).toBeDefined()
  return button!
}

beforeEach(() => {
  localStorage.clear()
  queryClient.clear()
  queryClient.setDefaultOptions({
    mutations: { retry: false },
    queries: {
      refetchOnWindowFocus: false,
      retry: false,
      staleTime: 30_000,
    },
  })
  createPlayerMock.mockReset()
  createTeamRecordMock.mockReset()
  listPlayersMock.mockReset()
  listTeamRecordsMock.mockReset()
  updatePlayerMock.mockReset()
  updateTeamRecordMock.mockReset()
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

describe('TeamMembersContent', () => {
  it('選手を登録・通常編集し、共有 prefix を無効化して一覧を再取得する', async () => {
    const self = teamRecord('self-a', 'チーム A', 'self')
    const duplicate = player('player-old', self.id, '既存選手', '18')
    let playerRows = [duplicate]
    listTeamRecordsMock.mockResolvedValue(page([self]))
    listPlayersMock.mockImplementation(async () => page(playerRows))
    createPlayerMock.mockImplementation(async (body) => {
      const created: PlayerCreated = {
        ...player(
          'player-new',
          self.id,
          body.name,
          body.uniform_number ?? null,
        ),
        bats: body.bats ?? null,
        same_number_players: [duplicate],
        throws: body.throws ?? null,
      }
      playerRows = [...playerRows, created]
      return created
    })
    updatePlayerMock.mockImplementation(async (id, body) => {
      const current = playerRows.find((row) => row.id === id)!
      const updated: PlayerRead = { ...current, ...body }
      playerRows = playerRows.map((row) => (row.id === id ? updated : row))
      return updated
    })
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('既存選手'))

    await wrapper.get('input[name="player-name"]').setValue('新規選手')
    await wrapper.get('select[name="player-throws"]').setValue('left')
    await wrapper.get('select[name="player-bats"]').setValue('both')
    await wrapper.get('input[name="player-uniform-number"]').setValue('18')
    await buttonWithText(wrapper, '選手を登録').trigger('click')

    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('選手「新規選手」を登録しました'),
    )
    expect(createPlayerMock).toHaveBeenCalledWith({
      bats: 'both',
      name: '新規選手',
      roster_label_key: null,
      roster_status_key: 'active',
      team_record_id: 'self-a',
      throws: 'left',
      uniform_number: '18',
    })
    expect(wrapper.text()).toContain('同じ背番号の在籍選手がいます')
    expect(wrapper.text()).toContain('18 既存選手')
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: rosterQueryKeys.players.all('tenant-a'),
    })
    expect(listPlayersMock.mock.calls.length).toBeGreaterThanOrEqual(2)

    await wrapper
      .get('select[name="player-edit-target"]')
      .setValue('player-new')
    await wrapper.get('input[name="player-edit-name"]').setValue('更新選手')
    await wrapper.get('select[name="player-edit-throws"]').setValue('right')
    await wrapper.get('select[name="player-edit-bats"]').setValue('left')
    await wrapper.get('input[name="player-edit-uniform-number"]').setValue('')
    await buttonWithText(wrapper, '選手情報を保存').trigger('click')

    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('選手「更新選手」を更新しました'),
    )
    expect(updatePlayerMock).toHaveBeenCalledWith('player-new', {
      bats: 'left',
      name: '更新選手',
      throws: 'right',
      uniform_number: null,
    })
    expect(wrapper.text()).toContain('更新選手')
    expect(updatePlayerMock.mock.calls[0]?.[1]).not.toHaveProperty(
      'roster_status_key',
    )
    expect(updatePlayerMock.mock.calls[0]?.[1]).not.toHaveProperty(
      'roster_label_key',
    )
  })

  it('対戦相手を登録して類似名を示し、作成した opponent の名称を編集する', async () => {
    const self = teamRecord('self-a', 'チーム A', 'self')
    let teamRows = [self, teamRecord('opponent-old', '東京クラブ')]
    listTeamRecordsMock.mockImplementation(async () => page(teamRows))
    listPlayersMock.mockResolvedValue(page([]))
    createTeamRecordMock.mockImplementation(async ({ name }) => {
      const created: TeamRecordCreated = {
        ...teamRecord('opponent-new', name),
        similar_names: ['東京クラブ'],
      }
      teamRows = [...teamRows, created]
      return created
    })
    updateTeamRecordMock.mockImplementation(async (id, { name }) => {
      const current = teamRows.find((row) => row.id === id)!
      const updated = { ...current, name }
      teamRows = teamRows.map((row) => (row.id === id ? updated : row))
      return updated
    })
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('東京クラブ'))

    await wrapper.get('input[name="opponent-name"]').setValue('東京倶楽部')
    await buttonWithText(wrapper, '対戦相手を登録').trigger('click')

    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('対戦相手「東京倶楽部」を登録しました'),
    )
    expect(createTeamRecordMock).toHaveBeenCalledWith({ name: '東京倶楽部' })
    expect(wrapper.text()).toContain('類似する登録済み名称があります')
    expect(wrapper.text()).toContain('東京クラブ')
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: rosterQueryKeys.teamRecords.all('tenant-a'),
    })

    await buttonWithText(wrapper, '登録した対戦相手名を編集').trigger('click')
    await wrapper
      .get('input[name="opponent-edit-name"]')
      .setValue('東京倶楽部 更新')
    await buttonWithText(wrapper, '名称を保存').trigger('click')

    await vi.waitFor(() =>
      expect(wrapper.text()).toContain(
        '対戦相手名を「東京倶楽部 更新」へ更新しました',
      ),
    )
    expect(updateTeamRecordMock).toHaveBeenCalledWith('opponent-new', {
      name: '東京倶楽部 更新',
    })
    expect(wrapper.text()).toContain('東京倶楽部 更新')
    const editOptions = wrapper
      .get('select[name="opponent-edit-target"]')
      .findAll('option')
      .map((option) => option.attributes('value'))
    expect(editOptions).not.toContain('self-a')
  })

  it('送信中の対戦相手登録をフォームから重複送信しない', async () => {
    const self = teamRecord('self-a', 'チーム A', 'self')
    const delayed = deferred<TeamRecordCreated>()
    listTeamRecordsMock.mockResolvedValue(page([self]))
    listPlayersMock.mockResolvedValue(page([]))
    createTeamRecordMock.mockImplementationOnce(() => delayed.promise)

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('チーム Aの選手管理'),
    )
    await wrapper.get('input[name="opponent-name"]').setValue('対戦相手 A')
    const form = wrapper
      .findAll('form')
      .find((candidate) =>
        candidate.find('input[name="opponent-name"]').exists(),
      )
    expect(form).toBeDefined()

    await form!.trigger('submit')
    await form!.trigger('submit')

    expect(createTeamRecordMock).toHaveBeenCalledTimes(1)
    delayed.resolve({
      ...teamRecord('opponent-a', '対戦相手 A'),
      similar_names: [],
    })
    await flushPromises()
  })

  it('送信中の対戦相手編集をフォームから重複送信しない', async () => {
    const self = teamRecord('self-a', 'チーム A', 'self')
    const opponent = teamRecord('opponent-a', '対戦相手 A')
    const delayed = deferred<TeamRecordRead>()
    listTeamRecordsMock.mockResolvedValue(page([self, opponent]))
    listPlayersMock.mockResolvedValue(page([]))
    updateTeamRecordMock.mockImplementationOnce(() => delayed.promise)

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(wrapper.text()).toContain('対戦相手 A'))
    await wrapper
      .get('select[name="opponent-edit-target"]')
      .setValue('opponent-a')
    await wrapper
      .get('input[name="opponent-edit-name"]')
      .setValue('対戦相手 A 更新')
    const form = wrapper
      .findAll('form')
      .find((candidate) =>
        candidate.find('input[name="opponent-edit-name"]').exists(),
      )
    expect(form).toBeDefined()

    await form!.trigger('submit')
    await form!.trigger('submit')

    expect(updateTeamRecordMock).toHaveBeenCalledTimes(1)
    delayed.resolve({ ...opponent, name: '対戦相手 A 更新' })
    await flushPromises()
  })

  it('旧 tenant の送信待ち中は新 tenant を許可し、戻った旧 tenant の再送を止める', async () => {
    const selfA = teamRecord('self-a', 'チーム A', 'self')
    const selfB = teamRecord('self-b', 'チーム B', 'self')
    const delayedA = deferred<TeamRecordCreated>()
    let activeTenant: 'a' | 'b' = 'a'
    listTeamRecordsMock.mockImplementation(async () =>
      page([activeTenant === 'a' ? selfA : selfB]),
    )
    listPlayersMock.mockResolvedValue(page([]))
    createTeamRecordMock
      .mockImplementationOnce(() => delayedA.promise)
      .mockResolvedValueOnce({
        ...teamRecord('opponent-b', '対戦相手 B'),
        similar_names: [],
      })
      .mockResolvedValueOnce({
        ...teamRecord('opponent-a-retry', '対戦相手 A 再送'),
        similar_names: [],
      })

    const mounted = mountScreen()
    const { auth } = mounted
    let { wrapper } = mounted
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('チーム Aの選手管理'),
    )
    await wrapper.get('input[name="opponent-name"]').setValue('対戦相手 A')
    await buttonWithText(wrapper, '対戦相手を登録').trigger('click')

    activeTenant = 'b'
    auth.signIn({ teamId: 'tenant-b', teamName: 'チーム B' })
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('チーム Bの選手管理'),
    )
    await wrapper.get('input[name="opponent-name"]').setValue('対戦相手 B')
    await buttonWithText(wrapper, '対戦相手を登録').trigger('click')

    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('対戦相手「対戦相手 B」を登録しました'),
    )
    expect(createTeamRecordMock).toHaveBeenCalledTimes(2)

    wrapper.unmount()
    activeTenant = 'a'
    wrapper = mountScreen().wrapper
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('チーム Aの選手管理'),
    )
    await wrapper.get('input[name="opponent-name"]').setValue('対戦相手 A 再送')
    expect(buttonWithText(wrapper, '登録中').attributes()).toHaveProperty(
      'disabled',
    )
    const createForm = wrapper
      .findAll('form')
      .find((candidate) =>
        candidate.find('input[name="opponent-name"]').exists(),
      )
    expect(createForm).toBeDefined()
    await createForm!.trigger('submit')
    expect(createTeamRecordMock).toHaveBeenCalledTimes(2)

    delayedA.resolve({
      ...teamRecord('opponent-a', '対戦相手 A'),
      similar_names: [],
    })
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain(
        'チーム Aでの対戦相手の登録は結果未確認です',
      ),
    )
    await vi.waitFor(() =>
      expect(
        buttonWithText(wrapper, '対戦相手を登録').attributes(),
      ).not.toHaveProperty('disabled'),
    )
    await buttonWithText(wrapper, '案内を閉じる').trigger('click')
    await createForm!.trigger('submit')
    await vi.waitFor(() =>
      expect(createTeamRecordMock).toHaveBeenCalledTimes(3),
    )
    expect(wrapper.text()).not.toContain('対戦相手「対戦相手 A」を登録しました')
  })

  it('初回一覧取得中の登録後も新しい一覧を取得する', async () => {
    const initialList = deferred<Page<TeamRecordRead>>()
    const created: TeamRecordCreated = {
      ...teamRecord('opponent-a', '対戦相手 A'),
      similar_names: [],
    }
    listTeamRecordsMock
      .mockImplementationOnce(() => initialList.promise)
      .mockResolvedValueOnce(page([created]))
    listPlayersMock.mockResolvedValue(page([]))
    createTeamRecordMock.mockResolvedValue(created)

    const { wrapper } = mountScreen()
    await vi.waitFor(() => expect(listTeamRecordsMock).toHaveBeenCalledTimes(1))
    await wrapper.get('input[name="opponent-name"]').setValue('対戦相手 A')
    await buttonWithText(wrapper, '対戦相手を登録').trigger('click')

    await vi.waitFor(() => expect(listTeamRecordsMock).toHaveBeenCalledTimes(2))
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('対戦相手 A対戦相手'),
    )
    initialList.resolve(page([]))
    await flushPromises()
    expect(wrapper.text()).toContain('対戦相手 A対戦相手')
  })

  it('同じ tenant で表示チームを切り替えても成功済み選手 cache を無効化する', async () => {
    const self = teamRecord('self-a', 'チーム A', 'self')
    const opponent = teamRecord('opponent-a', '対戦相手 A')
    const delayed = deferred<PlayerCreated>()
    listTeamRecordsMock.mockResolvedValue(page([self, opponent]))
    listPlayersMock.mockResolvedValue(page([]))
    createPlayerMock.mockImplementationOnce(() => delayed.promise)
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    const { wrapper } = mountScreen()
    await vi.waitFor(() =>
      expect(wrapper.text()).toContain('チーム Aの選手管理'),
    )
    await wrapper.get('input[name="player-name"]').setValue('遅延選手')
    await wrapper.get('select[name="player-throws"]').setValue('right')
    await wrapper.get('select[name="player-bats"]').setValue('left')
    await buttonWithText(wrapper, '選手を登録').trigger('click')

    const opponentButton = wrapper
      .findAll('[data-testid="team-record-list"] button')
      .find((button) => button.text().includes('対戦相手 A'))
    expect(opponentButton).toBeDefined()
    await opponentButton!.trigger('click')
    delayed.resolve({
      ...player('player-delayed', self.id, '遅延選手'),
      same_number_players: [],
    })

    await vi.waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: rosterQueryKeys.players.all('tenant-a'),
      }),
    )
    expect(wrapper.text()).toContain('対戦相手 Aの選手管理')
    expect(wrapper.text()).not.toContain('選手「遅延選手」を登録しました')
  })

  it.each([
    'success',
    'failure',
    'verification',
    'server-error',
    'response-error',
    'abort',
  ] as const)(
    '認証切替中の遅延 mutation %s が新 tenant の画面・cacheを変更しない',
    async (outcome) => {
      const selfA = teamRecord('self-a', 'チーム A', 'self')
      const selfB = teamRecord('self-b', 'チーム B', 'self')
      let activeTenant: 'a' | 'b' = 'a'
      listTeamRecordsMock.mockImplementation(async () =>
        page([activeTenant === 'a' ? selfA : selfB]),
      )
      listPlayersMock.mockImplementation(async () =>
        page(
          activeTenant === 'a'
            ? [player('player-a', selfA.id, '選手 A')]
            : [player('player-b', selfB.id, '選手 B')],
        ),
      )
      const delayed = deferred<PlayerCreated>()
      createPlayerMock.mockImplementationOnce(() => delayed.promise)
      const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

      const { auth, wrapper } = mountScreen()
      await vi.waitFor(() => expect(wrapper.text()).toContain('選手 A'))
      await wrapper.get('input[name="player-name"]').setValue('遅延選手 A')
      await wrapper.get('select[name="player-throws"]').setValue('right')
      await wrapper.get('select[name="player-bats"]').setValue('right')
      await buttonWithText(wrapper, '選手を登録').trigger('click')
      expect(createPlayerMock).toHaveBeenCalledTimes(1)

      activeTenant = 'b'
      auth.signIn({ teamId: 'tenant-b', teamName: 'チーム B' })
      await vi.waitFor(() => expect(wrapper.text()).toContain('選手 B'))
      queryClient.setQueryData(
        ['players', 'tenant-b', 'sentinel'],
        'keep-b-cache',
      )

      if (outcome === 'success') {
        delayed.resolve({
          ...player('player-delayed', selfA.id, '遅延選手 A'),
          same_number_players: [],
        })
      } else if (outcome === 'verification') {
        delayed.reject(new ApiTenantVerificationError('POST', '/players', 201))
      } else if (outcome === 'abort') {
        delayed.reject(new DOMException('通信中止', 'AbortError'))
      } else if (outcome === 'response-error') {
        delayed.reject(
          new ApiError(201, '応答を解釈できません', [], undefined, '{'),
        )
      } else if (outcome === 'server-error') {
        delayed.reject(new ApiError(500, '失敗', [], undefined, undefined))
      } else {
        delayed.reject(new ApiNetworkError(new Error('A の通信失敗')))
      }
      await flushPromises()

      expect(wrapper.text()).toContain('選手 B')
      expect(wrapper.text()).not.toContain('遅延選手 A')
      expect(wrapper.text()).not.toContain('登録しました')
      expect(wrapper.get('input[name="player-name"]').element).toHaveProperty(
        'value',
        '',
      )
      expect(invalidate).not.toHaveBeenCalled()
      expect(
        queryClient.getQueryData(['players', 'tenant-b', 'sentinel']),
      ).toBe('keep-b-cache')
      expect(createPlayerMock).toHaveBeenCalledTimes(1)
      expect(wrapper.text()).not.toContain(
        'チーム Aでの選手の登録は結果未確認です',
      )

      activeTenant = 'a'
      auth.signIn({ teamId: 'tenant-a', teamName: 'チーム A' })
      await vi.waitFor(() =>
        expect(wrapper.text()).toContain(
          'チーム Aでの選手の登録は結果未確認です',
        ),
      )
      expect(wrapper.text()).toContain('送信元チームへ戻って一覧を再読込')
      await buttonWithText(wrapper, '案内を閉じる').trigger('click')
    },
  )

  it.each([
    [200, 'application/json'],
    [201, 'application/json'],
    [200, 'text/plain'],
    [201, 'text/plain'],
  ] as const)(
    '実clientのack一致%s/%sでも解釈不能本文は未確認として再送・成功・cache更新をしない',
    async (status, contentType) => {
      const self = teamRecord('self-a', 'チーム A', 'self')
      const tenant = '11111111-1111-1111-1111-111111111111'
      listTeamRecordsMock.mockResolvedValue(page([self]))
      listPlayersMock.mockResolvedValue(page([]))
      createPlayerMock.mockImplementation((body) =>
        apiRequest('POST', '/players', { body, tenantBound: true }),
      )
      const fetchSpy = vi
        .spyOn(globalThis, 'fetch')
        .mockImplementation(async (_url, init) => {
          const headers = new Headers(init?.headers)
          expect(headers.get('X-Pitchlog-Expected-Tenant')).toBe(tenant)
          return new Response('{', {
            status,
            headers: {
              'Content-Type': contentType,
              'X-Pitchlog-Tenant-Match': '1',
              'X-Pitchlog-Tenant-Challenge': headers.get(
                'X-Pitchlog-Tenant-Challenge',
              )!,
            },
          })
        })
      const { wrapper } = mountScreen(tenant)
      await vi.waitFor(() =>
        expect(wrapper.text()).toContain('チーム Aの選手管理'),
      )
      queryClient.setQueryData(['players', tenant, 'sentinel'], '保存済みcache')
      const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
      await wrapper.get('input[name="player-name"]').setValue('未確認選手')
      await wrapper.get('select[name="player-throws"]').setValue('right')
      await wrapper.get('select[name="player-bats"]').setValue('left')
      await buttonWithText(wrapper, '選手を登録').trigger('click')
      await vi.waitFor(() =>
        expect(wrapper.text()).toContain('結果は未確認です'),
      )
      await flushPromises()
      expect(wrapper.text()).toContain('自動再送はしていません')
      expect(wrapper.text()).not.toContain('登録しました')
      expect(wrapper.text()).not.toContain('に失敗しました')
      expect(createPlayerMock).toHaveBeenCalledTimes(1)
      expect(fetchSpy).toHaveBeenCalledTimes(1)
      expect(invalidate).not.toHaveBeenCalled()
      expect(queryClient.getQueryData(['players', tenant, 'sentinel'])).toBe(
        '保存済みcache',
      )
      expect(listPlayersMock).toHaveBeenCalledTimes(1)
      expect(listTeamRecordsMock).toHaveBeenCalledTimes(1)
    },
  )

  it.each([
    new ApiStaleAuthError('POST', '/players', 201),
    new ApiTenantVerificationError('POST', '/players', 201),
    new ApiError(500, '失敗', [], undefined, undefined),
    new ApiError(200, '応答を解釈できません', [], undefined, '{'),
    new ApiError(201, '応答を解釈できません', [], undefined, '{'),
    new DOMException('通信中止', 'AbortError'),
  ])(
    '結果未確認の mutation %s を成功表示せず、自動再送しない',
    async (error) => {
      const self = teamRecord('self-a', 'チーム A', 'self')
      listTeamRecordsMock.mockResolvedValue(page([self]))
      listPlayersMock.mockResolvedValue(page([]))
      createPlayerMock.mockRejectedValue(error)

      const { wrapper } = mountScreen()
      await vi.waitFor(() =>
        expect(wrapper.text()).toContain('チーム Aの選手管理'),
      )
      await wrapper.get('input[name="player-name"]').setValue('未確認選手')
      await wrapper.get('select[name="player-throws"]').setValue('right')
      await wrapper.get('select[name="player-bats"]').setValue('left')
      await buttonWithText(wrapper, '選手を登録').trigger('click')

      await vi.waitFor(() =>
        expect(wrapper.text()).toContain('結果は未確認です'),
      )
      expect(wrapper.text()).toContain('一覧を再読込')
      expect(wrapper.text()).not.toContain('登録しました')
      expect(createPlayerMock).toHaveBeenCalledTimes(1)
    },
  )
})
