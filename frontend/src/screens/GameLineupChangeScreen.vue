<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { readStartedGame } from '../api/startedGame'
import { readPlayPrefixGame } from '../api/recordedPrefixGame'
import { readLineupPrefixGame } from '../api/lineupPrefixGame'
import type { StartedGameMetadata } from '../api/startedGame'
import type { Lineup } from '../../../contracts/state-transition/lineup_play_prefix_v1'
import GameScreenSubstitutionProduct from './GameScreenSubstitutionProduct.vue'
import Sheet from '../components/ui/Sheet.vue'
import { useRecordDisplay } from './GameScreenRecordDisplayProvider'

type GameRead = StartedGameMetadata & {
  lineup?: Lineup
  after?: unknown
}
type Side = 'away' | 'home'
type Row = {
  slot: string
  playerId: string
  name: string
  number: string
  bats: string
  position: string
  initial: boolean
}
const route = useRoute()
const router = useRouter()
const gameId = computed(() =>
  typeof route.params.gameId === 'string' ? route.params.gameId : '',
)
const game = ref<GameRead | null>(null)
const status = ref<'loading' | 'ready' | 'not-found' | 'unavailable' | 'error'>(
  'loading',
)
const sheetOpen = ref(false)
const display = useRecordDisplay(computed(() => game.value))
let sequence = 0
let request: AbortController | null = null

function currentLineup(side: Side): Lineup[Side] | null {
  const lineup = game.value?.lineup
  if (!lineup) return null
  return lineup[side]
}
function teamId(side: Side): string {
  const current = currentLineup(side)
  if (current) return current.teamId
  return game.value?.lineups[side].team_record_id ?? ''
}
function teamName(side: Side): string {
  return display.teamName(teamId(side), side === 'away' ? '先攻' : '後攻')
}
function roster(side: Side) {
  const id = teamId(side)
  return (
    game.value?.roster.teams.find((team) => team.team_id === id)
      ?.participants ?? []
  )
}
function fieldingPosition(side: Side, playerId: string): string {
  const person = roster(side).find(
    (participant) => participant.player.player_id === playerId,
  )
  if (!person) return '—'
  const fielding = person.roles.find((role) => role.kind === 'fielding')
  if (fielding && fielding.kind === 'fielding') return fielding.position
  if (person.roles.some((role) => role.kind === 'designated-hitter'))
    return 'DH'
  return '—'
}
function batsLabel(playerId: string): string {
  const bats = display.player(playerId)?.bats
  if (bats === 'left') return '左'
  if (bats === 'both') return '両'
  if (bats === 'right') return '右'
  return '—'
}
function playerNumber(playerId: string, fallback: string | null): string {
  return display.playerNumber(playerId) ?? fallback ?? '—'
}
function playerName(playerId: string, slot: string): string {
  return display.playerName(playerId, `${slot}番の選手`)
}
function rows(side: Side): Row[] {
  const source = game.value
  if (!source) return []
  const current = currentLineup(side)
  if (current) {
    return Object.entries(current.battingOrder)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([slot, playerId]) => ({
        slot,
        playerId,
        name: playerName(playerId, slot),
        number: playerNumber(playerId, null),
        bats: batsLabel(playerId),
        position: fieldingPosition(side, playerId),
        initial: false,
      }))
  }
  return source.lineups[side].entries
    .filter((entry) => entry.batting_order !== null)
    .sort((a, b) => Number(a.batting_order) - Number(b.batting_order))
    .map((entry) => {
      const slot = entry.batting_order ?? ''
      return {
        slot,
        playerId: entry.player_id,
        name: playerName(entry.player_id, slot),
        number: playerNumber(entry.player_id, entry.uniform_number_snapshot),
        bats: batsLabel(entry.player_id),
        position:
          entry.fielding_position.kind === 'fielding'
            ? entry.fielding_position.position
            : 'DH',
        initial: true,
      }
    })
}
function rosterEntries(side: Side) {
  return roster(side).map((participant) => {
    const playerId = participant.player.player_id
    const fielding = participant.roles.find((role) => role.kind === 'fielding')
    return {
      key: playerId,
      name: display.playerName(playerId, '選手'),
      number: display.playerNumber(playerId) ?? '—',
      bats: batsLabel(playerId),
      position:
        fielding && fielding.kind === 'fielding' ? fielding.position : 'DH',
    }
  })
}
const awayRows = computed(() => rows('away'))
const homeRows = computed(() => rows('home'))
const awayRoster = computed(() => rosterEntries('away'))
const homeRoster = computed(() => rosterEntries('home'))

async function load() {
  const id = gameId.value
  if (!id) {
    status.value = 'not-found'
    return
  }
  const own = ++sequence
  request?.abort()
  request = new AbortController()
  status.value = 'loading'
  game.value = null
  try {
    const v3 = await readLineupPrefixGame(id, null, 25, request.signal)
    if (own !== sequence) return
    if (v3.kind === 'found') {
      game.value = v3.game
      status.value = 'ready'
      return
    }
    if (v3.kind === 'unavailable' || v3.kind === 'unsupported') {
      const v2 = await readPlayPrefixGame(id, null, 25, request.signal)
      if (own !== sequence) return
      if (v2.kind === 'found') {
        game.value = v2.game
        status.value = 'ready'
        return
      }
    }
    const started = await readStartedGame(id, request.signal)
    if (own !== sequence) return
    if (started.kind === 'found') {
      game.value = started.game
      status.value = 'ready'
      return
    }
    status.value = started.kind === 'not-found' ? 'not-found' : 'unavailable'
  } catch {
    if (own === sequence) status.value = 'error'
  }
}
watch(gameId, load, { immediate: true })
onScopeDispose(() => {
  sequence++
  request?.abort()
})

async function back() {
  await router.push({
    name: 'game-record',
    params: { gameId: gameId.value },
    query: { recording: 'play-prefix-v3' },
  })
}
async function saved() {
  sheetOpen.value = false
  await load()
}
</script>

<template>
  <div class="min-h-dvh bg-slate-100 dark:bg-slate-950">
    <header
      class="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900"
    >
      <button
        type="button"
        class="grid min-h-11 min-w-11 place-items-center rounded-lg text-xl font-bold hover:bg-slate-100 dark:hover:bg-slate-800"
        aria-label="記録画面へ戻る"
        @click="back"
      >
        ←
      </button>
      <div class="min-w-0">
        <h1 class="truncate text-lg font-extrabold">選手交代</h1>
        <p class="text-xs text-slate-500">
          両チームの打順・守備・名簿を確認して交代を記録します
        </p>
      </div>
    </header>

    <main class="mx-auto max-w-6xl space-y-4 p-4 pb-24">
      <p
        v-if="status === 'loading'"
        role="status"
        class="rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-700 dark:bg-slate-900"
      >
        現在のスタメンを取得しています。
      </p>
      <p
        v-else-if="status === 'not-found'"
        role="alert"
        class="rounded-xl border border-red-300 bg-red-50 p-4 text-sm font-bold text-red-800"
      >
        試合が見つかりません。試合一覧へ戻ってください。
      </p>
      <p
        v-else-if="status === 'unavailable' || status === 'error'"
        role="alert"
        class="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm font-bold text-amber-900"
      >
        現在のスタメンを取得できません。通信を確認して再取得してください。
        <button
          type="button"
          class="ml-2 min-h-10 rounded-lg border border-amber-400 bg-white px-3"
          @click="load"
        >
          再取得
        </button>
      </p>

      <template v-if="status === 'ready' && game">
        <div class="grid gap-4 lg:grid-cols-2">
          <section
            v-for="side in ['away', 'home'] as const"
            :key="side"
            class="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <div class="mb-2 flex items-center gap-2">
              <span
                :class="[
                  'rounded-full px-2 py-0.5 text-xs font-extrabold text-white',
                  side === 'away' ? 'bg-slate-800' : 'bg-sky-700',
                ]"
              >
                {{ side === 'away' ? '先攻' : '後攻' }}
              </span>
              <h2 class="min-w-0 truncate text-base font-extrabold">
                {{ teamName(side) }}
              </h2>
            </div>
            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_11rem]">
              <div class="min-w-0 overflow-x-auto">
                <table class="w-full min-w-[20rem] text-xs">
                  <thead>
                    <tr class="text-slate-400">
                      <th class="w-8 py-1 text-left font-semibold">打順</th>
                      <th class="w-8 py-1 text-left font-semibold">守備</th>
                      <th class="w-10 py-1 text-left font-semibold">背番号</th>
                      <th class="py-1 text-left font-semibold">氏名</th>
                      <th class="w-8 py-1 text-left font-semibold">左右</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="row in side === 'away' ? awayRows : homeRows"
                      :key="row.slot"
                      class="border-t border-slate-100 dark:border-slate-800"
                    >
                      <td class="py-1.5 font-bold tabular-nums">
                        {{ row.slot }}
                      </td>
                      <td class="py-1.5">{{ row.position }}</td>
                      <td class="py-1.5 tabular-nums">{{ row.number }}</td>
                      <td class="max-w-[10rem] truncate py-1.5 font-semibold">
                        {{ row.name }}
                      </td>
                      <td class="py-1.5">{{ row.bats }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <aside class="rounded-xl bg-slate-50 p-2 dark:bg-slate-800/60">
                <h3 class="mb-1 text-[11px] font-extrabold text-slate-500">
                  名簿
                </h3>
                <ol class="space-y-0.5 text-[11px]">
                  <li
                    v-for="person in side === 'away' ? awayRoster : homeRoster"
                    :key="person.key"
                    class="flex min-w-0 items-center gap-1"
                  >
                    <span
                      class="w-5 shrink-0 text-right font-bold tabular-nums text-slate-500"
                      >{{ person.number }}</span
                    >
                    <span class="min-w-0 flex-1 truncate">{{
                      person.name
                    }}</span>
                    <span class="shrink-0 text-slate-400"
                      >{{ person.position }}・{{ person.bats }}</span
                    >
                  </li>
                </ol>
              </aside>
            </div>
          </section>
        </div>

        <div
          class="rounded-2xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100"
        >
          <p class="font-bold">交代の入力</p>
          <p class="mt-1 text-xs">
            旧画面の全画面スタメン変更に合わせ、両チームの現在値を表示しています。交代の種類・退出選手・入る選手は次の画面で選択します。
          </p>
          <button
            type="button"
            class="mt-3 min-h-14 w-full rounded-xl bg-sky-600 px-4 text-lg font-extrabold text-white hover:bg-sky-700"
            @click="sheetOpen = true"
          >
            選手交代を記録
          </button>
        </div>
      </template>
    </main>

    <Sheet
      :open="sheetOpen"
      title="選手交代を記録"
      side="right"
      wide
      @close="sheetOpen = false"
    >
      <GameScreenSubstitutionProduct
        v-if="sheetOpen && game"
        :game-id="game.id"
        @saved="saved"
      />
    </Sheet>
  </div>
</template>
