import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import * as ordinaryRead from '../api/recordedPrefixGame'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia } from 'pinia'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { readStartedGame, type StartedGameRead } from '../api/startedGame'
import { pinia } from '../appProviders'
import { createAppRouter } from '../router'
import { useAuthStore } from '../stores/authStore'
import GameScreenRecordedRestore from './GameScreenRecordedRestore.vue'
import GameScreenOrdinaryPitch from './GameScreenOrdinaryPitch.vue'
import { ApiError } from '../api/client'
import { GameStartPersistence } from '../lib/gameStartPersistence'

vi.mock('../api/startedGame', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/startedGame')>()),
  readStartedGame: vi.fn(),
}))

const tenant = '10000000-0000-4000-8000-000000000001'
const game = '10000000-0000-4000-8000-000000000002'
const wrappers: VueWrapper[] = []

function snapshot(balls: string) {
  return {
    stateFields: {
      'state.half': 'top',
      'state.count.strikes': '0',
      'state.count.balls': balls,
      'state.outs': '0',
      'state.runners': 'empty',
      'state.battingOrder': '1',
      'state.tiebreakActive': false,
      'state.gameEnded': false,
      'state.inning': '1',
      'state.score': { home: '0', away: '0' },
    },
    scoreboard: {
      inningScores: { home: '0', away: '0' },
      hits: '0',
      errors: '0',
      strikeouts: '0',
      walks: '0',
    },
  }
}

function recorded(): StartedGameRead {
  return {
    read_kind: 'recorded',
    id: game,
    state: snapshot('0'),
    after: snapshot('1'),
    history: [
      {
        kind: 'confirmed-play',
        difference: {
          stateFields: {
            'state.count.balls': { before: '0', after: '1' },
          },
          scoreboard: {},
          statFlags: {},
        },
      },
    ],
    play_rows: [{}],
  } as unknown as StartedGameRead
}

function initial(): StartedGameRead {
  return {
    read_kind: 'initial',
    id: game,
    state: snapshot('0'),
  } as unknown as StartedGameRead
}

async function mountRestore(
  props: { auto?: boolean } = { auto: true },
): Promise<VueWrapper> {
  const router = createAppRouter()
  await router.push(`/games/${game}/record`)
  await router.isReady()
  const wrapper = mount(GameScreenRecordedRestore, {
    props,
    global: { plugins: [pinia, router] },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.spyOn(ordinaryRead, 'readPlayPrefixGame').mockResolvedValue({
    kind: 'unsupported',
  })
  vi.spyOn(ordinaryRead, 'readRecordedPrefixGame').mockResolvedValue({
    kind: 'unsupported',
  })
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), { teamId: tenant, teamName: 'A' })
  vi.mocked(readStartedGame).mockReset()
})

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  vi.restoreAllMocks()
})

it('記録済みはafterを現在として表示し、beforeへ戻さない', async () => {
  vi.mocked(readStartedGame).mockResolvedValue({
    kind: 'found',
    game: recorded(),
  })
  const wrapper = await mountRestore()
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('1')
  expect(wrapper.get('[data-testid="restore-strikes"]').text()).toBe('0')
  expect(wrapper.get('[data-testid="restore-outs"]').text()).toBe('0')
  expect(wrapper.get('[data-testid="restore-runners"]').text()).toBe('empty')
  expect(wrapper.get('[data-testid="restore-before-balls"]').text()).toBe('0')
  expect(wrapper.get('[data-testid="restore-history"]').text()).toBe('1件')
  expect(wrapper.get('[data-testid="restore-plays"]').text()).toBe('1件')
  expect(wrapper.text()).toContain('state.count.balls: 0→1')
})

it('開始済み（記録前）はstateを現在として表示し、before行を出さない', async () => {
  vi.mocked(readStartedGame).mockResolvedValue({
    kind: 'found',
    game: initial(),
  })
  const wrapper = await mountRestore()
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('0')
  expect(wrapper.find('[data-testid="restore-before-balls"]').exists()).toBe(
    false,
  )
  expect(wrapper.get('[data-testid="restore-history"]').text()).toBe('0件')
  expect(wrapper.get('[data-testid="restore-plays"]').text()).toBe('0件')
})

it('409は値を表示せず、初球1件として返せない旨を出す', async () => {
  vi.mocked(readStartedGame).mockResolvedValue({
    kind: 'recorded-unavailable',
  })
  const wrapper = await mountRestore()
  expect(wrapper.text()).toContain('初球1件として返せない記録です')
  expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
})

it('503・通信断は値を表示せず、再取得で旧値を残さない', async () => {
  vi.mocked(readStartedGame)
    .mockResolvedValueOnce({ kind: 'found', game: recorded() })
    .mockRejectedValueOnce(new Error('503'))
  const wrapper = await mountRestore()
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('1')
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
  expect(wrapper.text()).toContain('サーバーの記録を取得できません')
})

it('認証世代が変わった応答は採用しない', async () => {
  let firstResolve!: (
    value: Awaited<ReturnType<typeof readStartedGame>>,
  ) => void
  const never = new Promise<Awaited<ReturnType<typeof readStartedGame>>>(
    () => {},
  )
  vi.mocked(readStartedGame)
    .mockReturnValueOnce(
      new Promise((resolve) => {
        firstResolve = resolve
      }),
    )
    .mockReturnValue(never)
  const wrapper = await mountRestore()
  // 認証世代が変わると新しい要求が始まり、旧要求の応答は採用しない。
  useAuthStore().expireSession()
  firstResolve({ kind: 'found', game: recorded() })
  await flushPromises()
  expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('を取得しました')
})

it('auto省略時は端末の開始保存を確認してサーバーから自動復元する', async () => {
  const readStart = vi.fn().mockResolvedValue({ status: 'received' })
  const close = vi.fn()
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readStart,
    close,
  } as unknown as GameStartPersistence)
  vi.mocked(readStartedGame).mockResolvedValue({
    kind: 'found',
    game: recorded(),
  })
  const wrapper = await mountRestore({})
  expect(readStart).toHaveBeenCalledWith(tenant, game)
  expect(close).toHaveBeenCalled()
  expect(readStartedGame).toHaveBeenCalledWith(game)
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('1')
})
it('auto明示falseでは開始保存の照合もサーバー取得も自動実行しない', async () => {
  const open = vi.spyOn(GameStartPersistence, 'open')
  await mountRestore({ auto: false })
  expect(open).not.toHaveBeenCalled()
  expect(readStartedGame).not.toHaveBeenCalled()
})
it('auto省略でも開始保存がない試合を自動取得しない', async () => {
  vi.spyOn(GameStartPersistence, 'open').mockResolvedValue({
    readStart: vi.fn().mockResolvedValue(null),
    close: vi.fn(),
  } as unknown as GameStartPersistence)
  await mountRestore({})
  expect(readStartedGame).not.toHaveBeenCalled()
})

function prefixFixture(index = 2) {
  const value = JSON.parse(
    readFileSync(
      resolve(process.cwd(), 'src/api/fixtures/recordedPrefixGame.v1.json'),
      'utf8',
    ),
  ).positive[index].value
  value.id = game
  value.prefix_ref.gameId = game
  value.prefix_ref.tenantId = tenant
  for (const item of value.page.items) item.play_row.game_id = game
  return value
}
it('新prefixの現在after/実保存日時/有限pageを表示し、旧開始snapshotへ戻さない', async () => {
  const value = prefixFixture()
  vi.mocked(readStartedGame).mockResolvedValue({ kind: 'recorded-unavailable' })
  vi.mocked(ordinaryRead.readRecordedPrefixGame).mockResolvedValue({
    kind: 'found',
    game: value,
  })
  const wrapper = await mountRestore()
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('2')
  expect(wrapper.get('[data-testid="restore-before-balls"]').text()).toBe('0')
  expect(wrapper.get('[data-testid="restore-last-saved-at"]').text()).toBe(
    value.last_saved_at,
  )
  expect(wrapper.text()).toContain('有限ページ')
  expect(wrapper.text()).toContain('通常投球の確定水位')
  expect(wrapper.find('section[aria-label="通常投球を記録"]').exists()).toBe(
    true,
  )
})
it('新prefixの通信断は未更新と明示して最後の確認値を保ち、409失効では閉じる', async () => {
  const value = prefixFixture()
  vi.mocked(readStartedGame).mockRejectedValue(
    new ApiError(503, 'legacy unavailable', [], undefined, undefined),
  )
  vi.mocked(ordinaryRead.readRecordedPrefixGame)
    .mockResolvedValueOnce({ kind: 'found', game: value })
    .mockRejectedValueOnce(new TypeError('network failure'))
    .mockResolvedValueOnce({ kind: 'unavailable' })
  const wrapper = await mountRestore()
  const reload = () =>
    wrapper
      .findAll('button')
      .find((button) => button.text() === 'サーバーから再取得')!
  await reload().trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('未更新')
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('2')
  expect(wrapper.get('[data-testid="restore-last-saved-at"]').text()).toBe(
    value.last_saved_at,
  )
  await reload().trigger('click')
  await flushPromises()
  expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
})

it('savedイベント後は旧reader503に依存せず新prefixを再取得して保存後afterを表示する', async () => {
  const initial = prefixFixture(0),
    saved = prefixFixture(1)
  vi.mocked(readStartedGame).mockRejectedValue(
    new ApiError(503, 'legacy unavailable', [], undefined, undefined),
  )
  vi.mocked(ordinaryRead.readRecordedPrefixGame)
    .mockResolvedValueOnce({ kind: 'found', game: initial })
    .mockResolvedValueOnce({ kind: 'found', game: saved })
  const wrapper = await mountRestore()
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('0')
  wrapper.getComponent(GameScreenOrdinaryPitch).vm.$emit('saved')
  await flushPromises()
  expect(ordinaryRead.readRecordedPrefixGame).toHaveBeenCalledTimes(2)
  expect(ordinaryRead.readRecordedPrefixGame).toHaveBeenLastCalledWith(game)
  expect(readStartedGame).not.toHaveBeenCalled()
  expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe('1')
  expect(wrapper.get('[data-testid="restore-history"]').text()).toBe('1件')
})

it.each([0, 1, 3])(
  'n0/通常n1/旧初球n1のprefix正例index=%iを旧ABIなしで復元する',
  async (index) => {
    const value = prefixFixture(index)
    vi.mocked(readStartedGame).mockRejectedValue(
      new ApiError(503, 'legacy unavailable', [], undefined, undefined),
    )
    vi.mocked(ordinaryRead.readRecordedPrefixGame).mockResolvedValue({
      kind: 'found',
      game: value,
    })
    const wrapper = await mountRestore()
    expect(wrapper.get('[data-testid="restore-balls"]').text()).toBe(
      value.after.stateFields['state.count.balls'],
    )
    expect(readStartedGame).not.toHaveBeenCalled()
  },
)

it.each([401, 403, 404, 409, 503])(
  '新projectionのHTTP%sを旧ABI成功で覆わない',
  async (status) => {
    vi.mocked(readStartedGame).mockResolvedValue({
      kind: 'found',
      game: recorded(),
    })
    vi.mocked(ordinaryRead.readRecordedPrefixGame).mockRejectedValue(
      new ApiError(status, 'unit rejection', [], undefined, undefined),
    )
    const wrapper = await mountRestore()
    expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
    expect(readStartedGame).not.toHaveBeenCalled()
  },
)

it('新projectionの破損DTOも旧ABIへfallbackしない', async () => {
  vi.mocked(readStartedGame).mockResolvedValue({
    kind: 'found',
    game: recorded(),
  })
  vi.mocked(ordinaryRead.readRecordedPrefixGame).mockRejectedValue(
    new Error('invalid DTO'),
  )
  const wrapper = await mountRestore()
  expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
  expect(readStartedGame).not.toHaveBeenCalled()
})

it.each(['not-found', 'unavailable'] as const)(
  '新projectionの%s結果から旧ABI成功へfallbackしない',
  async (kind) => {
    vi.mocked(readStartedGame).mockResolvedValue({
      kind: 'found',
      game: recorded(),
    })
    vi.mocked(ordinaryRead.readRecordedPrefixGame).mockResolvedValue({ kind })
    const wrapper = await mountRestore()
    expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
    expect(readStartedGame).not.toHaveBeenCalled()
  },
)

it('新prefix取得中の認証世代変更後は旧応答を表示せず旧ABIも呼ばない', async () => {
  let finish!: (
    value: Awaited<ReturnType<typeof ordinaryRead.readRecordedPrefixGame>>,
  ) => void
  vi.mocked(ordinaryRead.readRecordedPrefixGame).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve
    }),
  )
  const wrapper = await mountRestore()
  expect(ordinaryRead.readRecordedPrefixGame).toHaveBeenCalledOnce()
  useAuthStore().expireSession()
  await flushPromises()
  finish({ kind: 'found', game: prefixFixture(1) })
  await flushPromises()
  expect(wrapper.find('[data-testid="restore-balls"]').exists()).toBe(false)
  expect(readStartedGame).not.toHaveBeenCalled()
})
it('通常画面の既定はv2 GETで、欠落/拒否を旧成功へfallbackしない', async () => {
  vi.mocked(ordinaryRead.readPlayPrefixGame).mockResolvedValue({
    kind: 'unavailable',
  })
  const wrapper = await mountRestore()
  expect(ordinaryRead.readPlayPrefixGame).toHaveBeenCalledWith(game)
  expect(ordinaryRead.readRecordedPrefixGame).not.toHaveBeenCalled()
  expect(readStartedGame).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('サーバーの記録を取得できません')
})

import * as recordingProvider from './GameScreenOrdinaryPitchProvider'
import * as pitchOptions from '../api/pitchTypeOptions'
import { GameScreenOrdinaryPitchController } from './GameScreenOrdinaryPitchController'
import StrikeZone from '../components/zone/StrikeZone.vue'
function initialV2Read(): ordinaryRead.PlayPrefixGame {
  const value = prefixFixture(0)
  return {
    ...value,
    read_kind: 'play-prefix',
    last_source: null,
    prior_artifact_sha256:
      '052f5c0a61d861176a2de5ae06055e16c9a0b2a192cfdc861a740cde4d5bedc4',
    pa_start_source: { kind: 'started-game', id: value.id },
    bridge_checkpoint: {
      id: '10000000-0000-4000-8000-000000000099',
      revision: '1',
      digest: 'a'.repeat(64),
    },
    storage_anchor: null,
    bridge_origin: null,
    runners: [],
    participants: null,
  }
}
function setupParentInput(read = initialV2Read()) {
  useAuthStore().hasHydrated = true
  // ここではHTTP/記録権/queueの成功を主張せず、実子componentの入力寿命だけを検査する。
  vi.spyOn(
    GameScreenOrdinaryPitchController.prototype,
    'inspect',
  ).mockResolvedValue('ready')
  vi.spyOn(
    GameScreenOrdinaryPitchController.prototype,
    'canAppend',
    'get',
  ).mockReturnValue(true)
  vi.spyOn(pitchOptions, 'readPitchTypeOptions').mockResolvedValue({
    items: [{ key: 'unit.straight', display_name: '直球' }],
    next_cursor: null,
  })
  vi.mocked(ordinaryRead.readPlayPrefixGame).mockImplementation(async () => ({
    kind: 'found',
    game: structuredClone(read),
  }))
  return read
}
async function filledParent() {
  const read = setupParentInput(),
    wrapper = await mountRestore()
  await vi.waitFor(() =>
    expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(true),
  )
  await vi.waitFor(() =>
    expect(wrapper.find('[data-testid="first-ball-pitch-type"]').exists()).toBe(
      true,
    ),
  )
  for (const key of ['profile', 'mode', 'bucket', 'lockdown'])
    await wrapper.get(`[data-testid="first-ball-env-${key}"]`).setValue(true)
  await wrapper
    .get('[data-testid="ordinary-pitch-result"]')
    .setValue('batting-result.hit-by-pitch')
  const candidate = read.roster.teams[0].participants.find(
    (p) => p.batting_slot.kind === 'slot' && p.batting_slot.slot === '2',
  )!
  await wrapper
    .get('[data-testid="terminal-next-batter"]')
    .setValue(candidate.player.player_id)
  await wrapper
    .get('[data-testid="first-ball-pitch-type"]')
    .setValue('unit.straight')
  wrapper.getComponent(StrikeZone).vm.$emit('tap', 131.5, 124)
  await flushPromises()
  return {
    read,
    wrapper,
    candidate,
    child: wrapper.getComponent(GameScreenOrdinaryPitch).vm,
  }
}
function reloadParent(wrapper: VueWrapper) {
  return wrapper
    .findAll('button')
    .find((b) => b.text() === 'サーバーから再取得')!
    .trigger('click')
}
it('同値v2全DTO再供給は親で子を作り直さず四確認/result/次打者/球種/pointを保持する', async () => {
  const { wrapper, child, candidate } = await filledParent()
  await reloadParent(wrapper)
  await flushPromises()
  await vi.waitFor(() =>
    expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(true),
  )
  expect(wrapper.getComponent(GameScreenOrdinaryPitch).vm.$ === child.$).toBe(
    true,
  )
  for (const key of ['profile', 'mode', 'bucket', 'lockdown'])
    expect(
      (
        wrapper.get(`[data-testid="first-ball-env-${key}"]`)
          .element as HTMLInputElement
      ).checked,
    ).toBe(true)
  expect(
    (
      wrapper.get('[data-testid="ordinary-pitch-result"]')
        .element as HTMLSelectElement
    ).value,
  ).toBe('batting-result.hit-by-pitch')
  expect(
    (
      wrapper.get('[data-testid="terminal-next-batter"]')
        .element as HTMLSelectElement
    ).value,
  ).toBe(candidate.player.player_id)
  expect(
    (
      wrapper.get('[data-testid="first-ball-pitch-type"]')
        .element as HTMLSelectElement
    ).value,
  ).toBe('unit.straight')
  expect(wrapper.getComponent(StrikeZone).props('point')).toEqual({
    x: 131.5,
    y: 124,
  })
})
it.each([
  'snapshot',
  'bridge',
  'epoch',
  'tenant',
  'hydration',
  'authentication',
  'error',
  'corrupt',
] as const)('%s真正変更/失敗は親の旧入力ownerを失効させる', async (kind) => {
  const { wrapper, read, child } = await filledParent()
  if (kind === 'epoch') useAuthStore().authEpoch += 1
  else if (kind === 'tenant')
    setVerifiedAuthForTest(useAuthStore(), {
      teamId: '20000000-0000-4000-8000-000000000001',
      teamName: '別の単体fixture',
    })
  else if (kind === 'hydration') useAuthStore().hasHydrated = false
  else if (kind === 'authentication') useAuthStore().expireSession()
  else {
    if (kind === 'error')
      vi.mocked(ordinaryRead.readPlayPrefixGame).mockRejectedValueOnce(
        new TypeError('unit network'),
      )
    else {
      const base = structuredClone(read)
      const changed =
        kind === 'snapshot'
          ? {
              ...base,
              after: {
                ...base.after,
                scoreboard: { ...base.after.scoreboard, walks: '1' },
              },
              state: {
                ...base.state,
                scoreboard: { ...base.state.scoreboard, walks: '1' },
              },
            }
          : kind === 'bridge'
            ? {
                ...base,
                bridge_checkpoint: {
                  ...base.bridge_checkpoint!,
                  digest: 'b'.repeat(64),
                },
              }
            : kind === 'corrupt'
              ? { ...base, bridge_checkpoint: null }
              : base
      vi.mocked(ordinaryRead.readPlayPrefixGame).mockResolvedValueOnce({
        kind: 'found',
        game: changed,
      })
    }
    await reloadParent(wrapper)
  }
  await flushPromises()
  await vi.waitFor(() => expect(child.$.isUnmounted).toBe(true))
  if (wrapper.findComponent(GameScreenOrdinaryPitch).exists()) {
    expect(wrapper.getComponent(GameScreenOrdinaryPitch).vm.$ === child.$).toBe(
      false,
    )
    expect(wrapper.getComponent(StrikeZone).props('point')).toBeNull()
    expect(
      (
        wrapper.get('[data-testid="first-ball-env-profile"]')
          .element as HTMLInputElement
      ).checked,
    ).toBe(false)
  } else
    expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(false)
})
it('同値DTOがpending中は同じasyncを保ち、derive失敗後の同値再取得は再試行する', async () => {
  const read = setupParentInput(),
    actual = recordingProvider.playContextFromRead
  let finish!: (v: recordingProvider.PlayRecordingContext) => void
  const derive = vi
    .spyOn(recordingProvider, 'playContextFromRead')
    .mockReturnValueOnce(
      new Promise((r) => {
        finish = r
      }),
    )
    .mockRejectedValueOnce(new Error('unit derive failure'))
    .mockImplementation(actual)
  const wrapper = await mountRestore()
  expect(derive).toHaveBeenCalledTimes(1)
  await reloadParent(wrapper)
  await flushPromises()
  expect(derive).toHaveBeenCalledTimes(1)
  finish(await actual(read, tenant))
  await flushPromises()
  await vi.waitFor(() =>
    expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(true),
  )
  const changed = {
    ...structuredClone(read),
    bridge_checkpoint: { ...read.bridge_checkpoint!, digest: 'b'.repeat(64) },
  }
  vi.mocked(ordinaryRead.readPlayPrefixGame).mockImplementation(async () => ({
    kind: 'found',
    game: structuredClone(changed),
  }))
  await reloadParent(wrapper)
  await flushPromises()
  expect(derive).toHaveBeenCalledTimes(2)
  expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(false)
  await reloadParent(wrapper)
  await flushPromises()
  await vi.waitFor(() =>
    expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(true),
  )
  expect(derive).toHaveBeenCalledTimes(3)
})
it('新context計算中の認証変更後に完了した旧asyncを親へ再採用しない', async () => {
  const read = setupParentInput(),
    actual = recordingProvider.playContextFromRead
  let finish!: (v: recordingProvider.PlayRecordingContext) => void
  vi.spyOn(recordingProvider, 'playContextFromRead').mockReturnValueOnce(
    new Promise((r) => {
      finish = r
    }),
  )
  const wrapper = await mountRestore()
  useAuthStore().expireSession()
  await flushPromises()
  finish(await actual(read, tenant))
  await flushPromises()
  expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(false)
})

it('真正DTO変更後に遅れて完了した旧contextを新ownerへ戻さない', async () => {
  const read = setupParentInput(),
    actual = recordingProvider.playContextFromRead
  let finish!: (v: recordingProvider.PlayRecordingContext) => void
  vi.spyOn(recordingProvider, 'playContextFromRead')
    .mockReturnValueOnce(
      new Promise((r) => {
        finish = r
      }),
    )
    .mockImplementation(actual)
  const wrapper = await mountRestore()
  const changed = {
    ...structuredClone(read),
    bridge_checkpoint: { ...read.bridge_checkpoint!, digest: 'b'.repeat(64) },
  }
  vi.mocked(ordinaryRead.readPlayPrefixGame).mockResolvedValueOnce({
    kind: 'found',
    game: changed,
  })
  await reloadParent(wrapper)
  await flushPromises()
  await vi.waitFor(() =>
    expect(wrapper.findComponent(GameScreenOrdinaryPitch).exists()).toBe(true),
  )
  const owner = wrapper.getComponent(GameScreenOrdinaryPitch).vm.$
  finish(await actual(read, tenant))
  await flushPromises()
  expect(wrapper.getComponent(GameScreenOrdinaryPitch).vm.$ === owner).toBe(
    true,
  )
  const ref = wrapper
    .getComponent(GameScreenOrdinaryPitch)
    .props('context').prefixRef
  expect(ref.version).toBe('2')
  if (ref.version !== '2') throw new Error('v2 contextが失われました')
  expect(ref.checkpoint.digest).toBe('b'.repeat(64))
})
