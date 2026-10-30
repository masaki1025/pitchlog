import { mount, type VueWrapper } from '@vue/test-utils'
import { setActivePinia } from 'pinia'
import { ref, shallowRef } from 'vue'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { installAppProviders, pinia } from '../appProviders'
import { useAuthStore } from '../stores/authStore'
import GameScreenPreparingCreate from './GameScreenPreparingCreate.vue'
import type { usePreparingCreateProvider } from './GameScreenPreparingCreateProvider'

let state: ReturnType<typeof usePreparingCreateProvider>
vi.mock('./GameScreenPreparingCreateProvider', () => ({
  usePreparingCreateProvider: () => state,
}))
const tenant = '11111111-1111-4111-8111-111111111111'
const self = '21111111-1111-4111-8111-111111111111'
const other = '31111111-1111-4111-8111-111111111111'
let wrapper: VueWrapper
beforeEach(async () => {
  localStorage.clear()
  setActivePinia(pinia)
  vi.stubGlobal('navigator', {
    onLine: true,
    locks: {
      request: vi.fn(async (_name, _options, action) =>
        action({ name: 'create-view' }),
      ),
    },
  })
  setVerifiedAuthForTest(useAuthStore(pinia), { teamId: tenant, teamName: 'A' })
  state = {
    status: ref('ready'),
    choices: shallowRef({
      options: {
        game_types: [{ key: 'game_open', display_name: '<b>オープン戦</b>' }],
        tournaments: {
          items: [{ key: 'opaque-key', display_name: '<img src=x>' }],
          next_cursor: null,
        },
      },
      self: {
        id: self,
        kind: 'self',
        name: '<svg onload=alert(1)>',
        hidden_at: null,
      },
      opponents: {
        items: [{ id: other, kind: 'opponent', name: '相手', hidden_at: null }],
        next_cursor: null,
      },
    }),
    created: shallowRef(null),
    message: ref(''),
    online: ref(true),
    canPreviousOptions: ref(false),
    canPreviousTeams: ref(false),
    load: vi.fn(async () => {}),
    page: vi.fn(),
    confirmCreated: vi.fn(async () => {}),
    submit: vi.fn(async () => {
      state.status.value = 'sending'
    }),
  }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/games', component: GameScreenPreparingCreate }],
  })
  await router.push('/games')
  wrapper = mount(GameScreenPreparingCreate, {
    global: { plugins: [{ install: installAppProviders }, router] },
  })
})
afterEach(() => {
  wrapper?.unmount()
  useAuthStore(pinia).signOut()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
async function fill() {
  await wrapper.get('[data-testid="scheduled"]').setValue('2026-10-24T10:00')
  await wrapper.get('[data-testid="game-type"]').setValue('game_open')
  await wrapper.get('[data-testid="away"]').setValue(self)
  await wrapper.get('[data-testid="home"]').setValue(other)
  await wrapper.get('[data-testid="tournament"]').setValue('opaque-key')
}
it('必須大会/両team/5任意欄をフォームから運び、表示文字列を構造にしない', async () => {
  expect(
    wrapper.get('[data-testid="create-submit"]').attributes('disabled'),
  ).toBeDefined()
  await fill()
  await wrapper.get('[data-testid="umpire"]').setValue(' =主審 ')
  await wrapper.get('[data-testid="section"]').setValue(' 第１節　')
  await wrapper.get('[data-testid="week"]').setValue('W')
  await wrapper.get('[data-testid="day"]').setValue('D')
  await wrapper.get('[data-testid="number"]').setValue('G')
  expect(wrapper.text()).toContain('<img src=x>')
  expect(wrapper.text()).toContain('<b>オープン戦</b>')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('b').exists()).toBe(false)
  expect(wrapper.find('svg').exists()).toBe(false)
  expect(
    wrapper.get('[data-testid="create-submit"]').attributes('disabled'),
  ).toBeUndefined()
  await wrapper.get('form').trigger('submit')
  expect(state.submit).toHaveBeenCalledWith({
    scheduled_at: '2026-10-24T10:00:00+09:00',
    game_type_key: 'game_open',
    away_team_record_id: self,
    home_team_record_id: other,
    tournament: { kind: 'existing', key: 'opaque-key' },
    plate_umpire: ' =主審 ',
    section_label: ' 第１節　',
    week_label: 'W',
    day_label: 'D',
    game_number_label: 'G',
  })
  await wrapper.get('form').trigger('submit')
  expect(state.submit).toHaveBeenCalledTimes(1)
})
it('同teamを許し、新大会名を無変換で送る・空白onlyは送らない', async () => {
  await fill()
  await wrapper.get('[data-testid="home"]').setValue(self)
  await wrapper.get('[data-testid="tournament-kind"]').setValue('new')
  await wrapper.get('[data-testid="tournament-name"]').setValue('　 ')
  await wrapper.get('form').trigger('submit')
  expect(state.submit).not.toHaveBeenCalled()
  await wrapper.get('[data-testid="tournament-name"]').setValue(' Ａ大会　')
  await wrapper.get('form').trigger('submit')
  expect(state.submit).toHaveBeenCalledWith(
    expect.objectContaining({
      away_team_record_id: self,
      home_team_record_id: self,
      tournament: { kind: 'new', display_name: ' Ａ大会　' },
    }),
  )
})
it('offline/unknownは作成を封鎖し、unknownは一覧確認へだけ戻す', async () => {
  await fill()
  state.online.value = false
  await wrapper.get('form').trigger('submit')
  expect(state.submit).not.toHaveBeenCalled()
  state.online.value = true
  state.status.value = 'unknown'
  await wrapper.get('form').trigger('submit')
  expect(state.submit).not.toHaveBeenCalled()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '一覧で保存結果を確認')!
    .trigger('click')
  expect(wrapper.emitted('inspect')).toHaveLength(1)
  expect(
    wrapper
      .findAll('button')
      .find((button) => button.text() === '作成入力を閉じる')!
      .attributes('disabled'),
  ).toBeDefined()
})
it('認証epoch切替は旧フォーム値を同期的に破棄する', async () => {
  await fill()
  setVerifiedAuthForTest(useAuthStore(pinia), { teamId: other, teamName: 'B' })
  await wrapper.vm.$nextTick()
  expect(
    (wrapper.get('[data-testid="scheduled"]').element as HTMLInputElement)
      .value,
  ).toBe('')
  expect(
    (wrapper.get('[data-testid="away"]').element as HTMLSelectElement).value,
  ).toBe('')
  expect(state.submit).not.toHaveBeenCalled()
})
