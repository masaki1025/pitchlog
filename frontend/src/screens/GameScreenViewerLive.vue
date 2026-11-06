<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { pinia } from '../appProviders'
import { getPlayer } from '../api/roster'
import {
  readViewerGame,
  readViewerHead,
  viewerFailure,
  type ViewerGame,
  type ViewerHead,
} from '../api/viewerGame'
import { canonicalUuid } from '../api/authIntent'
import { useAuthStore } from '../stores/authStore'

const route = useRoute()
const auth = useAuthStore(pinia)
const gameId = computed(() => String(route.params.gameId ?? ''))
const game = shallowRef<ViewerGame | null>(null)
const head = ref<ViewerHead | null>(null)
const names = ref<Record<string, string>>({})
const freshness = ref<'loading' | 'fresh' | 'unupdated' | 'not-found'>('loading')
const checkedAt = ref<number | null>(null)
const pageCursors = ref<(string | null)[]>([null])
const pageIndex = computed(() => pageCursors.value.length - 1)
const nextCursor = computed(() => game.value?.page.next_cursor ?? null)
let runId = 0
let request: AbortController | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null
let staleTimer: ReturnType<typeof setInterval> | null = null
let mounted = false

const identity = computed(() =>
  JSON.stringify([
    auth.authEpoch,
    auth.teamId,
    auth.isAuthenticated,
    gameId.value,
  ]),
)
const validIdentity = computed(
  () =>
    auth.isAuthenticated &&
    auth.teamId !== null &&
    canonicalUuid.test(auth.teamId) &&
    canonicalUuid.test(gameId.value),
)
const current = computed(() => game.value?.after.stateFields ?? null)
const lineup = computed(() =>
  game.value?.read_kind === 'lineup-prefix'
    ? game.value.lineup
    : game.value?.checkpoint.content.restored.lineup ?? null,
)
const runners = computed(() =>
  game.value?.read_kind === 'lineup-prefix'
    ? game.value.runners
    : game.value?.checkpoint.content.restored.runners ?? [],
)
const savedAt = computed(() => game.value?.last_saved_at ?? null)
const history = computed(() => {
  const source = game.value
  if (source === null) return []
  return source.read_kind === 'lineup-prefix'
    ? source.page.items.map((item) => ({
        key: item.play_row.id,
        number: String(item.play_row.play_number),
        result: item.play_row.batting_result_key,
      }))
    : source.page.items.map((item) => ({
        key: item.play.playId,
        number: item.play.physicalPlayNumber,
        result: '確定済みの投球',
      }))
})
function playerLabel(id: string): string {
  return names.value[id] ?? `選手 ${id.slice(0, 8)}`
}
function clearTimer(): void {
  if (pollTimer !== null) clearTimeout(pollTimer)
  pollTimer = null
}
function clearCurrent(status: typeof freshness.value): void {
  game.value = null
  head.value = null
  names.value = {}
  checkedAt.value = null
  pageCursors.value = [null]
  freshness.value = status
}
function stop(): void {
  runId += 1
  request?.abort()
  request = null
  clearTimer()
}
function schedule(): void {
  clearTimer()
  if (mounted && validIdentity.value)
    pollTimer = setTimeout(() => void load(false), 3000)
}
async function load(force: boolean): Promise<void> {
  if (!mounted || !validIdentity.value) return
  const currentRun = ++runId
  request?.abort()
  const controller = new AbortController()
  request = controller
  const tenant = auth.teamId!
  const target = gameId.value
  const capturedIdentity = identity.value
  try {
    const nextHead = await readViewerHead(target, controller.signal)
    if (currentRun !== runId || identity.value !== capturedIdentity) return
    const changed =
      head.value === null ||
      head.value.status !== nextHead.status ||
      head.value.generation !== nextHead.generation ||
      head.value.watermark !== nextHead.watermark
    if (changed) {
      game.value = null
      pageCursors.value = [null]
      freshness.value = 'loading'
    }
    if (changed || force || game.value === null) {
      const nextGame = await readViewerGame(
        target,
        tenant,
        nextHead,
        pageCursors.value.at(-1) ?? null,
        controller.signal,
      )
      if (currentRun !== runId || identity.value !== capturedIdentity) return
      game.value = nextGame
      void loadNames(nextGame, tenant, capturedIdentity, controller.signal)
    }
    head.value = nextHead
    checkedAt.value = Date.now()
    freshness.value = 'fresh'
  } catch (error) {
    if (currentRun !== runId || identity.value !== capturedIdentity) return
    clearCurrent(viewerFailure(error))
  } finally {
    if (currentRun === runId) {
      request = null
      schedule()
    }
  }
}
async function loadNames(
  source: ViewerGame,
  tenant: string,
  capturedIdentity: string,
  signal: AbortSignal,
): Promise<void> {
  const sourceLineup =
    source.read_kind === 'lineup-prefix'
      ? source.lineup
      : source.checkpoint.content.restored.lineup
  const expected = new Map<string, string>()
  for (const side of ['away', 'home'] as const) {
    const team = sourceLineup[side]
    for (const id of Object.values(team.battingOrder)) expected.set(id, team.teamId)
    expected.set(team.pitcherId, team.teamId)
    expected.set(team.catcherId, team.teamId)
  }
  const missing = [...expected].filter(([id]) => names.value[id] === undefined)
  await Promise.all(
    missing.map(async ([id, teamId]) => {
      try {
        const player = await getPlayer(id, { signal })
        if (
          identity.value === capturedIdentity &&
          auth.teamId === tenant &&
          game.value === source &&
          player.id === id &&
          player.team_record_id === teamId &&
          player.name.length > 0
        )
          names.value = { ...names.value, [id]: player.name }
      } catch {
        // 名簿名の再取得失敗を保存済みscoreの成功へ混ぜない。
      }
    }),
  )
}
function nextPage(): void {
  const cursor = nextCursor.value
  if (cursor === null || freshness.value !== 'fresh') return
  if (pageCursors.value.includes(cursor)) return
  pageCursors.value = [...pageCursors.value, cursor]
  void load(true)
}
function previousPage(): void {
  if (pageIndex.value === 0 || freshness.value !== 'fresh') return
  pageCursors.value = pageCursors.value.slice(0, -1)
  void load(true)
}
watch(
  identity,
  () => {
    stop()
    clearCurrent('loading')
    if (mounted && validIdentity.value) void load(true)
  },
  { flush: 'sync' },
)
onMounted(() => {
  mounted = true
  staleTimer = setInterval(() => {
    if (
      freshness.value === 'fresh' &&
      checkedAt.value !== null &&
      Date.now() - checkedAt.value > 10000
    ) {
      game.value = null
      freshness.value = 'unupdated'
    }
  }, 1000)
  if (validIdentity.value) void load(true)
})
onUnmounted(() => {
  mounted = false
  stop()
  if (staleTimer !== null) clearInterval(staleTimer)
})
</script>

<template>
  <main class="mx-auto max-w-5xl space-y-5 p-4 pb-12">
    <h1 class="text-2xl font-bold">試合のライブ閲覧</h1>
    <p>サーバー確定分のみ表示。記録端末の未送信分は含まれません。</p>
    <p role="status" data-testid="viewer-status">
      {{ freshness === 'fresh' ? '更新済み' : freshness === 'not-found' ? '閲覧できません' : freshness === 'loading' ? '確認中' : '未更新' }}
    </p>
    <p>最終保存: {{ savedAt ?? '未取得' }} / 閲覧確認: {{ checkedAt === null ? '未取得' : new Date(checkedAt).toLocaleString('ja-JP') }}</p>
    <template v-if="freshness === 'fresh' && game !== null && current !== null && lineup !== null">
      <section aria-label="スコア">
        <h2 class="text-lg font-bold">スコア</h2>
        <p>先攻 {{ current['state.score'].away }} – 後攻 {{ current['state.score'].home }}</p>
        <p>{{ current['state.inning'] }}回 {{ current['state.half'] === 'top' ? '表' : '裏' }} / {{ current['state.outs'] }}アウト / {{ current['state.count.balls'] }}ボール {{ current['state.count.strikes'] }}ストライク</p>
        <p>走者: {{ runners.length === 0 ? 'なし' : runners.map((runner) => `${runner.base}塁 ${playerLabel(runner.runnerId)}`).join('、') }}</p>
      </section>
      <section aria-label="出場選手" class="grid gap-4 md:grid-cols-2">
        <div v-for="side in (['away', 'home'] as const)" :key="side">
          <h2 class="text-lg font-bold">{{ side === 'away' ? '先攻' : '後攻' }}の出場選手</h2>
          <p>投手 {{ playerLabel(lineup[side].pitcherId) }} / 捕手 {{ playerLabel(lineup[side].catcherId) }}</p>
          <ol class="list-inside list-decimal">
            <li v-for="[order, id] in Object.entries(lineup[side].battingOrder)" :key="order">
              {{ order }}番 {{ playerLabel(id) }}
            </li>
          </ol>
        </div>
      </section>
      <section aria-label="投球履歴">
        <h2 class="text-lg font-bold">確定済み投球履歴（1ページ25件）</h2>
        <p v-if="history.length === 0">まだ確定済みの投球はありません。</p>
        <ol v-else class="list-inside list-decimal">
          <li v-for="item in history" :key="item.key">第{{ item.number }}球: {{ item.result }}</li>
        </ol>
        <button type="button" :disabled="pageIndex === 0" @click="previousPage">前のページ</button>
        <button type="button" :disabled="nextCursor === null" @click="nextPage">次のページ</button>
      </section>
    </template>
  </main>
</template>
