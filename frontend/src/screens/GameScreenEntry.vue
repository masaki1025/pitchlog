<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import GameScreenEntryPremises from './GameScreenEntryPremises.vue'
import {
  currentEntrySupply,
  datumLabel,
  entryStatusLabel,
  existingStateLabel,
  areStartCandidates,
  isEntryEnvironment,
  isGameListPage,
  type EntryEnvironment,
  type EntrySupply,
  type GameListPage,
  type StartCandidate,
} from './GameScreenEntryTypes'

const props = defineProps<{
  mode?: 'preparing-read'
  page?: EntrySupply<GameListPage> | null
  starts?: EntrySupply<readonly StartCandidate[]> | null
  environment?: EntrySupply<EntryEnvironment> | null
}>()
const emit = defineEmits<{ 'page-request': [key: string | null] }>()
const auth = useAuthStore()
const route = useRoute()
const requestedPageKey = ref<string | null>(null)
const priorPageKey = ref<string | null | undefined>(undefined)
const pageRequestPending = ref(false)
const selectedGameId = ref('')
const keyword = ref('')
const searchOpen = ref(false)

// 供給値の参照交換では保持し、認証または経路の実変更時だけ旧選択を破棄する。
watch(
  () => [auth.authEpoch, auth.teamId, route.path],
  () => {
    requestedPageKey.value = null
    priorPageKey.value = undefined
    pageRequestPending.value = false
    selectedGameId.value = ''
  },
  { flush: 'sync' },
)

const pageSource = computed(() =>
  currentEntrySupply(props.page, auth, route, requestedPageKey.value),
)
watch(
  () => props.page,
  (next, previous) => {
    if (
      pageRequestPending.value &&
      next !== previous &&
      currentEntrySupply(next, auth, route, requestedPageKey.value) !== null
    )
      pageRequestPending.value = false
  },
  { flush: 'sync' },
)
const visiblePage = computed(() => {
  const source = pageSource.value
  return source?.status === 'ready' &&
    auth.teamId !== null &&
    source.data &&
    isGameListPage(source.data, auth.teamId)
    ? source.data
    : null
})
function gameDate(value: string | undefined): string {
  return value ? value.slice(0, 10).replaceAll('-', '/') : '日時未取得'
}
const filteredItems = computed(() => {
  const items = visiblePage.value?.items ?? []
  const needle = keyword.value.trim()
  if (!needle) return items
  return items.filter(
    (item) => item.label.includes(needle) || item.stateLabel.includes(needle),
  )
})
const pageMessage = computed(() => {
  if (pageRequestPending.value) return '確認中'
  if (pageSource.value?.status === 'pending') return '確認中'
  if (pageSource.value?.status === 'failed') return '読み取れません'
  if (pageSource.value?.status === 'denied') return 'このページを確認できません'
  return '未取得'
})
const pageRecoveryAvailable = computed(
  () =>
    !pageRequestPending.value &&
    (pageSource.value?.status === 'failed' ||
      pageSource.value?.status === 'denied'),
)
const startSource = computed(() =>
  currentEntrySupply(props.starts, auth, route),
)
const environment = computed(() => {
  const source = currentEntrySupply(props.environment, auth, route, null)
  return source?.status === 'ready' && isEntryEnvironment(source.data)
    ? source.data
    : null
})
const candidates = computed(() => {
  const source = startSource.value
  return source?.status === 'ready' &&
    auth.teamId !== null &&
    Array.isArray(source.data) &&
    areStartCandidates(source.data, auth.teamId)
    ? source.data
    : null
})
const selected = computed(
  () =>
    candidates.value?.find((game) => game.gameId === selectedGameId.value) ??
    null,
)

function requestPage(key: string | null): void {
  if (
    pageRequestPending.value ||
    visiblePage.value === null ||
    (key === null && !visiblePage.value.canPrevious) ||
    (key !== visiblePage.value.previousKey && key !== visiblePage.value.nextKey)
  )
    return
  priorPageKey.value = requestedPageKey.value
  issuePageRequest(key)
}

function issuePageRequest(key: string | null): void {
  pageRequestPending.value = true
  requestedPageKey.value = key
  emit('page-request', key)
}

function retryPage(): void {
  if (!pageRecoveryAvailable.value) return
  issuePageRequest(requestedPageKey.value)
}

function returnToPriorPage(): void {
  if (!pageRecoveryAvailable.value || priorPageKey.value === undefined) return
  const key = priorPageKey.value
  priorPageKey.value = undefined
  issuePageRequest(key)
}
</script>

<template>
  <main class="mx-auto max-w-4xl space-y-5 p-4 pb-12 wrap-anywhere">
    <header class="mb-4 flex items-end justify-between gap-3">
      <div class="min-w-0">
        <p class="text-xs font-bold uppercase tracking-widest text-sky-600">
          Baseball scoring
        </p>
        <h1 class="text-2xl font-extrabold">
          {{ mode === 'preparing-read' ? '準備中の試合' : '試合一覧' }}
        </h1>
        <p v-if="mode === 'preparing-read'" class="mt-1 text-sm text-slate-500">
          準備中の試合だけを表示します。開始・再開・保存・送信はできません。
        </p>
        <p v-else class="mt-1 text-sm text-slate-500">
          試合の開始・再開・保存・送信の正式な入口です。
        </p>
      </div>
    </header>

    <details
      class="mb-4 rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
    >
      <summary class="cursor-pointer px-4 py-3 text-sm font-bold">
        通信・端末の前提
      </summary>
      <div class="px-4 pb-3">
        <GameScreenEntryPremises :environment="environment" />
      </div>
    </details>

    <section aria-label="試合一覧" class="min-w-0 space-y-3">
      <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
        <h2 class="text-lg font-bold">試合一覧</h2>
        <div class="ml-auto flex items-center gap-2">
          <button
            type="button"
            class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold dark:border-slate-600 dark:bg-slate-800"
            :aria-expanded="searchOpen"
            @click="searchOpen = !searchOpen"
          >
            {{ searchOpen ? '検索を閉じる' : '検索' }}
          </button>
          <label
            v-if="
              searchOpen &&
              visiblePage &&
              auth.hasHydrated &&
              auth.isAuthenticated
            "
            class="relative block w-full sm:w-64"
          >
            <span class="sr-only">試合を検索</span>
            <input
              v-model="keyword"
              type="search"
              placeholder="試合を検索"
              class="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 pr-9 text-sm dark:border-slate-600 dark:bg-slate-800"
            />
            <span
              class="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
              >⌕</span
            >
          </label>
        </div>
      </div>
      <template v-if="visiblePage === null">
        <p
          role="status"
          class="rounded-xl border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-900"
        >
          試合一覧：{{ pageMessage }}
        </p>
        <div
          v-if="pageRecoveryAvailable"
          class="flex flex-col gap-2 sm:flex-row"
        >
          <button
            type="button"
            class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 font-bold dark:border-slate-600 dark:bg-slate-800"
            @click="retryPage"
          >
            このページを再試行
          </button>
          <button
            v-if="priorPageKey !== undefined"
            type="button"
            class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 font-bold dark:border-slate-600 dark:bg-slate-800"
            @click="returnToPriorPage"
          >
            直前のページに戻る
          </button>
        </div>
      </template>
      <template v-else>
        <p class="text-xs font-semibold text-slate-500">
          表示ページ：{{ visiblePage.pageLabel }}
        </p>
        <p
          v-if="filteredItems.length === 0"
          class="rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900"
        >
          {{
            visiblePage.items.length === 0
              ? 'このページに試合はありません。'
              : '検索条件に一致する試合はありません。'
          }}
        </p>
        <ul class="grid gap-3 sm:grid-cols-2">
          <li
            v-for="game in filteredItems"
            :key="game.gameId"
            class="flex min-w-0 flex-col gap-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900"
          >
            <div class="flex items-center justify-between gap-2">
              <span
                :class="[
                  'rounded-full px-2 py-0.5 text-[11px] font-extrabold',
                  game.stateLabel === '準備中'
                    ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200'
                    : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200',
                ]"
              >
                {{ game.stateLabel }}
              </span>
              <span class="text-[11px] font-semibold text-slate-400">
                {{ game.gameId.slice(0, 8) }}
              </span>
            </div>
            <div class="min-w-0">
              <p class="text-xs font-semibold text-slate-500">
                {{ gameDate(game.scheduledAt) }}
              </p>
              <p class="mt-0.5 min-w-0 break-words text-sm font-extrabold">
                {{ game.label }}
              </p>
              <p class="mt-1 break-all text-[10px] text-slate-400">
                {{ game.gameId }}
              </p>
            </div>
            <div class="mt-auto flex flex-wrap items-center gap-2">
              <RouterLink
                :to="{ name: 'game-record', params: { gameId: game.gameId } }"
                class="inline-flex min-h-10 items-center rounded-xl border border-sky-300 bg-sky-50 px-3 text-sm font-bold text-sky-800 hover:bg-sky-100 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-200"
                >閲覧画面へ</RouterLink
              >
              <button
                type="button"
                disabled
                class="min-h-10 rounded-xl border border-slate-200 px-3 text-sm font-bold text-slate-400 dark:border-slate-700"
              >
                再開（未提供）
              </button>
            </div>
          </li>
        </ul>
        <nav
          aria-label="試合一覧のページ"
          class="flex flex-col gap-2 sm:flex-row"
        >
          <button
            type="button"
            :disabled="
              !visiblePage.canPrevious && visiblePage.previousKey === null
            "
            class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 font-bold disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800"
            @click="requestPage(visiblePage?.previousKey ?? null)"
          >
            前のページ
          </button>
          <button
            type="button"
            :disabled="visiblePage.nextKey === null"
            class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 py-2 font-bold disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800"
            @click="requestPage(visiblePage?.nextKey ?? null)"
          >
            次のページ
          </button>
        </nav>
      </template>
    </section>

    <section
      v-if="mode !== 'preparing-read'"
      aria-label="試合開始"
      class="min-w-0 space-y-3 rounded-2xl border p-4"
    >
      <h2 class="text-lg font-bold">試合開始</h2>
      <p v-if="candidates === null" role="status">
        開始候補・スタメン・適用規則：{{
          entryStatusLabel(startSource?.status)
        }}
      </p>
      <template v-else>
        <label for="entry-game" class="block font-semibold">開始候補</label>
        <select
          id="entry-game"
          v-model="selectedGameId"
          class="min-h-11 w-full min-w-0 rounded-lg border p-2"
        >
          <option value="">選択してください</option>
          <option
            v-for="game in candidates"
            :key="game.gameId"
            :value="game.gameId"
          >
            {{ game.label }}
          </option>
        </select>
        <dl v-if="selected" class="grid min-w-0 gap-2">
          <div>
            <dt>スタメン</dt>
            <dd>{{ datumLabel(selected.lineup) }}</dd>
          </div>
          <div>
            <dt>適用規則</dt>
            <dd>{{ datumLabel(selected.rules) }}</dd>
          </div>
          <div>
            <dt>記録権</dt>
            <dd>
              {{
                selected.recordingRight === 'held'
                  ? '保持'
                  : selected.recordingRight === 'denied'
                    ? '非保持'
                    : '未取得'
              }}
            </dd>
          </div>
          <div>
            <dt>既存状態</dt>
            <dd>
              {{ existingStateLabel(selected.existingState) }}
            </dd>
          </div>
        </dl>
        <p
          v-if="
            selected?.existingState === 'in-progress' ||
            selected?.existingState === 'suspended'
          "
        >
          既存の試合は新規開始できません。再開状態の正式提供が必要です。
        </p>
      </template>
      <button
        type="button"
        disabled
        class="min-h-11 rounded-lg border px-3 py-2"
      >
        スタメンを確認・設定（未提供）
      </button>
      <button
        type="button"
        disabled
        class="min-h-11 rounded-lg border px-3 py-2"
      >
        試合を開始（未提供）
      </button>
    </section>
  </main>
</template>
