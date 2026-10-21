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
    visiblePage.value === null ||
    key === null ||
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
    <header class="space-y-2">
      <h1 class="text-2xl font-extrabold">試合</h1>
      <p>
        正式な試合一覧・開始情報は未接続です。ここから試合の開始・再開・保存・送信はできません。
      </p>
    </header>

    <GameScreenEntryPremises :environment="environment" />

    <section
      aria-label="試合一覧"
      class="min-w-0 space-y-3 rounded-2xl border p-4"
    >
      <h2 class="text-lg font-bold">試合一覧</h2>
      <template v-if="visiblePage === null">
        <p role="status">試合一覧：{{ pageMessage }}</p>
        <div
          v-if="pageRecoveryAvailable"
          class="flex flex-col gap-2 sm:flex-row"
        >
          <button
            type="button"
            class="min-h-11 rounded-lg border px-3 py-2"
            @click="retryPage"
          >
            このページを再試行
          </button>
          <button
            v-if="priorPageKey !== undefined"
            type="button"
            class="min-h-11 rounded-lg border px-3 py-2"
            @click="returnToPriorPage"
          >
            直前のページに戻る
          </button>
        </div>
      </template>
      <template v-else>
        <p>表示ページ：{{ visiblePage.pageLabel }}</p>
        <p v-if="visiblePage.items.length === 0">
          このページに試合はありません。
        </p>
        <ul class="space-y-3">
          <li
            v-for="game in visiblePage.items"
            :key="game.gameId"
            class="min-w-0 space-y-2 rounded-xl border p-3"
          >
            <p class="font-bold">{{ game.label }}</p>
            <p>状態：{{ game.stateLabel }}</p>
            <RouterLink
              :to="{ name: 'game-record', params: { gameId: game.gameId } }"
              class="inline-block min-h-11 rounded-lg border px-3 py-2 underline"
              >閲覧画面へ</RouterLink
            >
            <button
              type="button"
              disabled
              class="block min-h-11 rounded-lg border px-3 py-2"
            >
              再開（未提供）
            </button>
          </li>
        </ul>
        <nav
          aria-label="試合一覧のページ"
          class="flex flex-col gap-2 sm:flex-row"
        >
          <button
            type="button"
            :disabled="visiblePage.previousKey === null"
            class="min-h-11 rounded-lg border px-3 py-2 disabled:opacity-50"
            @click="requestPage(visiblePage.previousKey)"
          >
            前のページ
          </button>
          <button
            type="button"
            :disabled="visiblePage.nextKey === null"
            class="min-h-11 rounded-lg border px-3 py-2 disabled:opacity-50"
            @click="requestPage(visiblePage.nextKey)"
          >
            次のページ
          </button>
        </nav>
      </template>
    </section>

    <section
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
