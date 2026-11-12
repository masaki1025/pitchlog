<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import {
  listGameArchive,
  type GameArchiveGame,
  type GameArchiveStatus,
} from '../api/games'
import { listTeamRecords } from '../api/roster'
import { useAuthStore } from '../stores/authStore'

type LoadState = 'idle' | 'loading' | 'ready' | 'failed'
const auth = useAuthStore()
const state = ref<LoadState>('idle')
const items = ref<GameArchiveGame[]>([])
const nextCursor = ref<string | null>(null)
const pageCursors = ref<(string | null)[]>([null])
const pageIndex = ref(0)
const teamNames = ref(new Map<string, string>())
const teamsLoaded = ref(false)
const keyword = ref('')
const statusFilter = ref<'all' | GameArchiveStatus>('all')
const message = ref('')
let generation = 0
let controller: AbortController | null = null

const statusLabels: Record<GameArchiveStatus, string> = {
  preparing: '準備中',
  in_progress: '進行中',
  finished: '終了',
}
const statusClasses: Record<GameArchiveStatus, string> = {
  preparing:
    'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-200',
  in_progress:
    'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-700 dark:bg-sky-950/50 dark:text-sky-200',
  finished:
    'border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200',
}
const filters: readonly { key: 'all' | GameArchiveStatus; label: string }[] = [
  { key: 'all', label: 'すべて' },
  { key: 'preparing', label: '準備中' },
  { key: 'in_progress', label: '進行中' },
  { key: 'finished', label: '終了' },
]

function teamName(id: string): string {
  return teamNames.value.get(id) ?? `チーム ${id.slice(0, 8)}`
}
function gameDate(value: string): string {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return '日時未取得'
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
function gameLabel(game: GameArchiveGame): string {
  return [
    gameDate(game.scheduled_at),
    teamName(game.away_team_record_id),
    'vs',
    teamName(game.home_team_record_id),
  ].join(' ')
}
function recordLabel(game: GameArchiveGame): string {
  if (game.status === 'preparing') return '開始'
  if (game.status === 'in_progress') return '再開'
  return '追記・再開'
}
const visibleItems = computed(() => {
  const needle = keyword.value.trim()
  return items.value.filter((game) => {
    if (statusFilter.value !== 'all' && game.status !== statusFilter.value)
      return false
    if (!needle) return true
    return (
      gameLabel(game).includes(needle) ||
      statusLabels[game.status].includes(needle) ||
      game.id.includes(needle)
    )
  })
})
const pageLabel = computed(() => `${pageIndex.value + 1}ページ目`)
const canPrevious = computed(
  () => pageIndex.value > 0 && state.value !== 'loading',
)
const canNext = computed(
  () => nextCursor.value !== null && state.value !== 'loading',
)
const emptyMessage = computed(() => {
  if (state.value === 'loading') return '読み込み中…'
  if (state.value === 'failed') return message.value
  if (items.value.length === 0) return '表示できる試合がありません'
  return '条件に一致する試合がありません'
})

async function loadTeams(signal: AbortSignal): Promise<Map<string, string>> {
  const names = new Map<string, string>()
  let cursor: string | null = null
  for (let page = 0; page < 5; page += 1) {
    const result = await listTeamRecords(
      { limit: 100, cursor, include_hidden: true },
      { signal },
    )
    if (!Array.isArray(result.items)) break
    for (const team of result.items) {
      if (typeof team.id === 'string' && typeof team.name === 'string')
        names.set(team.id, team.name)
    }
    cursor = typeof result.next_cursor === 'string' ? result.next_cursor : null
    if (cursor === null) break
  }
  return names
}

async function load(cursor: string | null): Promise<void> {
  const request = ++generation
  controller?.abort()
  const active = new AbortController()
  controller = active
  state.value = 'loading'
  message.value = ''
  try {
    const [page, names] = await Promise.all([
      listGameArchive(cursor, active.signal),
      teamsLoaded.value
        ? Promise.resolve(teamNames.value)
        : loadTeams(active.signal).catch(() => new Map<string, string>()),
    ])
    if (request !== generation) return
    items.value = page.items
    nextCursor.value = page.next_cursor
    if (names.size > 0) {
      teamNames.value = names
      teamsLoaded.value = true
    }
    state.value = 'ready'
  } catch {
    if (request !== generation) return
    items.value = []
    nextCursor.value = null
    state.value = 'failed'
    message.value = '試合一覧を取得できませんでした'
  }
}

function selectPage(index: number): void {
  if (state.value === 'loading') return
  if (index < 0 || index >= pageCursors.value.length) return
  pageIndex.value = index
  void load(pageCursors.value[index] ?? null)
}
function nextPage(): void {
  if (!canNext.value || nextCursor.value === null) return
  const cursor = nextCursor.value
  if (pageCursors.value.includes(cursor)) return
  pageCursors.value = [...pageCursors.value, cursor]
  selectPage(pageCursors.value.length - 1)
}
function previousPage(): void {
  if (!canPrevious.value) return
  selectPage(pageIndex.value - 1)
}
function retry(): void {
  void load(pageCursors.value[pageIndex.value] ?? null)
}
function resetPages(): void {
  pageCursors.value = [null]
  pageIndex.value = 0
  void load(null)
}

onMounted(() => void load(null))
watch(
  () => [auth.authEpoch, auth.teamId] as const,
  () => {
    if (!auth.hasHydrated || !auth.isAuthenticated || auth.teamId === null)
      return
    teamNames.value = new Map()
    teamsLoaded.value = false
    resetPages()
  },
)
onBeforeUnmount(() => {
  generation += 1
  controller?.abort()
})
</script>

<template>
  <main class="mx-auto max-w-6xl space-y-5 px-4 py-6 pb-12 wrap-anywhere">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div class="min-w-0">
        <p class="text-xs font-bold uppercase tracking-widest text-sky-600">
          Baseball scoring
        </p>
        <h1 class="text-2xl font-extrabold">試合一覧</h1>
        <p class="mt-1 text-sm text-slate-500">
          準備中・進行中・終了の試合を確認し、記録・閲覧・成績・CSVへ進みます。
        </p>
      </div>
      <RouterLink
        :to="{ name: 'games', query: { create: '1' } }"
        class="inline-flex min-h-11 items-center rounded-xl bg-sky-600 px-4 font-bold text-white shadow-sm hover:bg-sky-700"
      >
        新しい試合
      </RouterLink>
    </header>

    <section
      aria-label="試合一覧の絞り込み"
      class="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900 sm:flex-row sm:items-center"
    >
      <div class="flex flex-wrap gap-1" role="group" aria-label="状態">
        <button
          v-for="filter in filters"
          :key="filter.key"
          type="button"
          class="min-h-9 rounded-lg border px-3 text-xs font-bold"
          :class="
            statusFilter === filter.key
              ? 'border-sky-500 bg-sky-50 text-sky-800 dark:bg-sky-950/50 dark:text-sky-200'
              : 'border-slate-300 bg-white text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300'
          "
          :aria-pressed="statusFilter === filter.key"
          @click="statusFilter = filter.key"
        >
          {{ filter.label }}
        </button>
      </div>
      <label class="relative block w-full sm:ml-auto sm:w-72">
        <span class="sr-only">このページ内の試合を検索</span>
        <input
          v-model="keyword"
          type="search"
          placeholder="このページ内を検索"
          class="min-h-10 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm dark:border-slate-600 dark:bg-slate-800"
        />
      </label>
    </section>

    <p v-if="state === 'loading'" role="status" class="text-sm text-slate-500">
      読み込み中…
    </p>
    <div
      v-else-if="state === 'failed'"
      role="alert"
      class="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-200"
    >
      <p>{{ message }}</p>
      <button
        type="button"
        class="mt-2 min-h-9 rounded-lg border border-red-300 bg-white px-3 font-bold text-red-800"
        @click="retry"
      >
        再試行
      </button>
    </div>
    <p v-else-if="visibleItems.length === 0" class="text-sm text-slate-500">
      {{ emptyMessage }}
    </p>

    <section v-else aria-label="試合" class="grid gap-3 md:grid-cols-2">
      <article
        v-for="game in visibleItems"
        :key="game.id"
        class="flex min-w-0 flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="text-sm font-extrabold">
              {{ teamName(game.away_team_record_id) }}
              <span class="px-1 text-slate-400">vs</span>
              {{ teamName(game.home_team_record_id) }}
            </p>
            <p class="mt-1 text-xs text-slate-500">
              {{ gameDate(game.scheduled_at) }}
            </p>
          </div>
          <span
            class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-bold"
            :class="statusClasses[game.status]"
          >
            {{ statusLabels[game.status] }}
          </span>
        </div>
        <p class="break-all text-[11px] text-slate-400">
          試合ID: {{ game.id }}
        </p>
        <div class="mt-auto flex flex-wrap gap-1.5">
          <RouterLink
            :to="{ name: 'game-record', params: { gameId: game.id } }"
            class="inline-flex min-h-9 items-center rounded-lg bg-sky-600 px-3 text-xs font-bold text-white hover:bg-sky-700"
          >
            {{ recordLabel(game) }}
          </RouterLink>
          <RouterLink
            v-if="game.status !== 'preparing'"
            :to="{ name: 'game-viewer', params: { gameId: game.id } }"
            class="inline-flex min-h-9 items-center rounded-lg border border-slate-300 bg-white px-3 text-xs font-bold dark:border-slate-600 dark:bg-slate-800"
          >
            閲覧
          </RouterLink>
          <RouterLink
            :to="{ name: 'game-stats', params: { gameId: game.id } }"
            class="inline-flex min-h-9 items-center rounded-lg border border-slate-300 bg-white px-3 text-xs font-bold dark:border-slate-600 dark:bg-slate-800"
          >
            成績
          </RouterLink>
          <RouterLink
            :to="{ name: 'game-export', params: { gameId: game.id } }"
            class="inline-flex min-h-9 items-center rounded-lg border border-slate-300 bg-white px-3 text-xs font-bold dark:border-slate-600 dark:bg-slate-800"
          >
            CSV
          </RouterLink>
        </div>
      </article>
    </section>

    <nav
      aria-label="試合一覧のページ"
      class="flex flex-wrap items-center justify-between gap-2"
    >
      <button
        type="button"
        class="min-h-10 rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800"
        :disabled="!canPrevious"
        @click="previousPage"
      >
        前のページ
      </button>
      <span class="text-xs text-slate-500">{{ pageLabel }}</span>
      <button
        type="button"
        class="min-h-10 rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800"
        :disabled="!canNext"
        @click="nextPage"
      >
        次のページ
      </button>
    </nav>
  </main>
</template>
