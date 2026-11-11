import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fixture from '../api/fixtures/lineupPrefixGame.v3.json'
import * as roster from '../api/roster'
import * as lineupRead from '../api/lineupPrefixGame'
import * as playRead from '../api/recordedPrefixGame'
import * as startedRead from '../api/startedGame'
import { setVerifiedAuthForTest } from '../api/auth.test-support'
import { useAuthStore } from '../stores/authStore'
import GameLineupChangeScreen from './GameLineupChangeScreen.vue'
import GameScreenSubstitutionProduct from './GameScreenSubstitutionProduct.vue'

const game = fixture.value
const awayId = game.lineup.away.teamId
const homeId = game.lineup.home.teamId
let pinia: ReturnType<typeof createPinia>

function player(teamId: string, id: string, name: string, number: string) {
  return {
    id,
    team_record_id: teamId,
    name,
    throws: 'right' as const,
    bats: 'right' as const,
    uniform_number: number,
    roster_status_key: 'active',
    roster_label_key: null,
    hidden_at: null,
  }
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setVerifiedAuthForTest(useAuthStore(), {
    teamId: game.prefix_ref.tenantId,
    teamName: 'A',
  })
  vi.spyOn(roster, 'listTeamRecords').mockResolvedValue({
    items: [
      { id: awayId, kind: 'self', name: '先攻チーム', hidden_at: null },
      { id: homeId, kind: 'opponent', name: '後攻チーム', hidden_at: null },
    ],
    next_cursor: null,
  })
  vi.spyOn(roster, 'readSelfTeamRecord').mockResolvedValue({
    id: awayId,
    kind: 'self',
    name: '先攻チーム',
    hidden_at: null,
  })
  vi.spyOn(roster, 'listPlayers').mockImplementation(async (query) => {
    const team = query.team_record_id
    const participants =
      game.roster.teams.find((value) => value.team_id === team)?.participants ??
      []
    return {
      items: participants.map((value, index) =>
        player(
          team ?? '',
          value.player.player_id,
          `${team === awayId ? '先攻' : '後攻'}${index + 1}号`,
          String(index + 1),
        ),
      ),
      next_cursor: null,
    }
  })
  vi.spyOn(lineupRead, 'readLineupPrefixGame').mockResolvedValue({
    kind: 'found',
    game,
  })
  vi.spyOn(playRead, 'readPlayPrefixGame').mockResolvedValue({
    kind: 'unavailable',
  })
  vi.spyOn(startedRead, 'readStartedGame').mockResolvedValue({
    kind: 'recorded-unavailable',
  })
})

afterEach(() => {
  disposePinia(pinia)
  vi.restoreAllMocks()
})

async function mountScreen() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/games/:gameId/lineup',
        name: 'game-lineup',
        component: { template: '<div />' },
      },
      {
        path: '/games/:gameId/record',
        name: 'game-record',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push(`/games/${game.id}/lineup`)
  await router.isReady()
  const wrapper = mount(GameLineupChangeScreen, {
    global: {
      plugins: [pinia, router],
      stubs: { GameScreenSubstitutionProduct: true },
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('GameLineupChangeScreen', () => {
  it('v3の現在lineupと両チームの名簿を旧画面の表で表示する', async () => {
    const { wrapper } = await mountScreen()
    expect(wrapper.text()).toContain('選手交代')
    expect(wrapper.text()).toContain('先攻チーム')
    expect(wrapper.text()).toContain('後攻チーム')
    expect(wrapper.text()).toContain('先攻1号')
    expect(wrapper.text()).toContain('後攻1号')
    expect(wrapper.findAll('tbody tr')).toHaveLength(18)
    expect(wrapper.text()).toContain('選手交代を記録')
  })

  it('交代シートを開き、戻る操作で記録画面へ遷移する', async () => {
    const { wrapper, router } = await mountScreen()
    const record = wrapper
      .findAll('button')
      .find((button) => button.text() === '選手交代を記録')
    expect(record).toBeDefined()
    await record!.trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(GameScreenSubstitutionProduct).exists()).toBe(
      true,
    )
    await wrapper.get('button[aria-label="記録画面へ戻る"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('game-record')
  })
})
