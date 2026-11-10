<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { pinia } from '../appProviders'
import { getPlayer } from '../api/roster'
import type { ViewerGame } from '../api/viewerGame'
import { useAuthStore } from '../stores/authStore'
import {
  GameScreenViewerLiveController,
  viewerCurrent,
  viewerHistory,
  viewerLineup,
  viewerNextCursor,
  viewerPageLabels,
  viewerPeriodLabel,
  viewerRunners,
  viewerSavedAt,
  viewerStatusLabel,
  type ViewerFreshness,
} from './GameScreenViewerLiveController'

const route = useRoute()
const auth = useAuthStore(pinia)
const gameId = computed(() => String(route.params.gameId ?? ''))
const game = shallowRef<ViewerGame | null>(null)
const freshness = ref<ViewerFreshness>('loading')
const refreshing = ref(false)
const checkedAt = ref<number | null>(null)
const pageCursors = ref<readonly (string | null)[]>([null])
const names = ref<Record<string, string>>({})
// 初回名簿取得中に版が変わっても、同じ選手を二重取得しない。
const pendingNames = new Set<string>()

const identity = computed(() =>
  JSON.stringify([
    auth.authEpoch,
    auth.teamId,
    auth.isAuthenticated,
    gameId.value,
  ]),
)
const controller = new GameScreenViewerLiveController(
  () => ({
    authenticated: auth.isAuthenticated,
    tenantId: auth.teamId,
    authEpoch: auth.authEpoch,
    gameId: gameId.value,
  }),
  {
    onChange: (state) => {
      const previous = game.value
      game.value = state.game
      freshness.value = state.freshness
      refreshing.value = state.refreshing
      checkedAt.value = state.checkedAt
      pageCursors.value = state.pageCursors
      if (state.game === null) names.value = {}
      else if (state.game !== previous) void loadNames(state.game)
    },
  },
)

const current = computed(() => viewerCurrent(game.value))
const lineup = computed(() => viewerLineup(game.value))
const runners = computed(() => viewerRunners(game.value))
const savedAt = computed(() => viewerSavedAt(game.value))
const history = computed(() => viewerHistory(game.value))
const nextCursor = computed(() => viewerNextCursor(game.value))
const pageLabels = computed(() => viewerPageLabels(game.value))
const pageIndex = computed(() => pageCursors.value.length - 1)
const periodLabel = computed(() => viewerPeriodLabel(game.value))
const statusText = computed(() => viewerStatusLabel(freshness.value, false))
const refreshingText = computed(() =>
  refreshing.value && freshness.value === 'fresh' ? '更新中' : null,
)
const hasState = computed(
  () => game.value !== null && current.value !== null && lineup.value !== null,
)
const canPreviousPage = computed(() => pageIndex.value > 0 && !refreshing.value)
const canNextPage = computed(
  () => nextCursor.value !== null && !refreshing.value,
)

function playerLabel(id: string): string {
  return names.value[id] ?? `選手 ${id.slice(0, 8)}`
}
async function loadNames(source: ViewerGame): Promise<void> {
  const tenant = auth.teamId
  if (!auth.isAuthenticated || tenant === null) return
  const sourceLineup =
    source.read_kind === 'lineup-prefix'
      ? source.lineup
      : source.checkpoint.content.restored.lineup
  if (sourceLineup === null) return
  const expected = new Map<string, string>()
  for (const side of ['away', 'home'] as const) {
    const team = sourceLineup[side]
    for (const id of Object.values(team.battingOrder))
      expected.set(id, team.teamId)
    expected.set(team.pitcherId, team.teamId)
    expected.set(team.catcherId, team.teamId)
  }
  const missing = [...expected].filter(
    ([id]) => names.value[id] === undefined && !pendingNames.has(id),
  )
  await Promise.all(
    missing.map(async ([id, teamId]) => {
      pendingNames.add(id)
      try {
        const player = await getPlayer(id)
        if (
          auth.teamId === tenant &&
          auth.isAuthenticated &&
          game.value === source &&
          player.id === id &&
          player.team_record_id === teamId &&
          player.name.length > 0
        )
          names.value = { ...names.value, [id]: player.name }
      } catch {
        // 名簿名の再取得失敗を保存済みscoreの成功へ混ぜない。
      } finally {
        pendingNames.delete(id)
      }
    }),
  )
}
function nextPage(): void {
  controller.nextPage()
}
function previousPage(): void {
  controller.previousPage()
}
function retry(): void {
  controller.reload(true)
}
watch(identity, () => controller.resetAndLoad(), { flush: 'sync' })
onMounted(() => controller.start())
onUnmounted(() => controller.stop())
</script>

<template>
  <main class="mx-auto max-w-5xl space-y-5 p-4 pb-12">
    <h1 class="text-2xl font-bold">試合のライブ閲覧</h1>
    <p data-testid="viewer-server-only-notice">
      サーバー確定分のみ表示。記録端末の未送信分は含まれません。
    </p>
    <p role="status" aria-live="polite" data-testid="viewer-status">
      {{ statusText }}
    </p>
    <p v-if="refreshingText" data-testid="viewer-refreshing" aria-hidden="true">
      {{ refreshingText }}
    </p>
    <p>
      最終保存:
      <span data-testid="viewer-saved-at">{{ savedAt ?? '未取得' }}</span>
      / 閲覧確認:
      <span data-testid="viewer-checked-at">
        {{
          checkedAt === null
            ? '未取得'
            : new Date(checkedAt).toLocaleString('ja-JP')
        }}
      </span>
    </p>
    <button
      v-if="freshness === 'unupdated' || freshness === 'not-found'"
      type="button"
      class="min-h-11 rounded-lg border px-3 py-2"
      @click="retry"
    >
      再取得
    </button>
    <template v-if="hasState && current && lineup">
      <section aria-label="スコア" data-testid="viewer-score">
        <h2 class="text-lg font-bold">スコア</h2>
        <p>
          先攻 {{ current['state.score'].away }} – 後攻
          {{ current['state.score'].home }}
        </p>
        <p>
          {{ periodLabel }} / {{ current['state.outs'] }}アウト /
          {{ current['state.count.balls'] }}ボール
          {{ current['state.count.strikes'] }}ストライク
        </p>
        <p>
          走者:
          {{
            runners.length === 0
              ? 'なし'
              : runners
                  .map(
                    (runner) =>
                      `${runner.base}塁 ${playerLabel(runner.runnerId)}`,
                  )
                  .join('、')
          }}
        </p>
      </section>
      <section
        aria-label="出場選手"
        class="grid gap-4 md:grid-cols-2"
        data-testid="viewer-lineup"
      >
        <div v-for="side in ['away', 'home'] as const" :key="side">
          <h2 class="text-lg font-bold">
            {{ side === 'away' ? '先攻' : '後攻' }}の出場選手
          </h2>
          <p>
            投手 {{ playerLabel(lineup[side].pitcherId) }} / 捕手
            {{ playerLabel(lineup[side].catcherId) }}
          </p>
          <ol class="list-inside list-decimal">
            <li
              v-for="[order, id] in Object.entries(lineup[side].battingOrder)"
              :key="order"
            >
              {{ order }}番 {{ playerLabel(id) }}
            </li>
          </ol>
        </div>
      </section>
      <section aria-label="投球履歴" data-testid="viewer-history">
        <h2 class="text-lg font-bold">確定済み投球履歴（1ページ25件）</h2>
        <p v-if="history.length === 0">まだ確定済みの投球はありません。</p>
        <ol v-else class="list-inside list-decimal">
          <li v-for="item in history" :key="item.key">
            第{{ item.number }}球: {{ item.result }}
          </li>
        </ol>
        <p data-testid="viewer-page-index">表示ページ: {{ pageIndex + 1 }}</p>
        <button
          type="button"
          :disabled="!canPreviousPage"
          data-testid="viewer-previous-page"
          @click="previousPage"
        >
          {{ pageLabels.previous }}
        </button>
        <button
          type="button"
          :disabled="!canNextPage"
          data-testid="viewer-next-page"
          @click="nextPage"
        >
          {{ pageLabels.next }}
        </button>
      </section>
    </template>
  </main>
</template>
