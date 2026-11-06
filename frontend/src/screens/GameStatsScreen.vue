<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  downloadGameStatsCsv,
  fetchGameStats,
  type GameBasicStats,
  type GameStatsMode,
} from '../api/stats'
import BasicStatsTable from '../components/stats/BasicStatsTable.vue'

const route = useRoute()
const gameId = computed(() => String(route.params.gameId ?? ''))
const mode = ref<GameStatsMode>('current')
const data = ref<GameBasicStats | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const downloading = ref(false)

let requestGeneration = 0
let activeController: AbortController | null = null
const pageCursors = ref<(string | undefined)[]>([undefined])
const pageIndex = computed(() => pageCursors.value.length - 1)
const visibleRange = computed(() => {
  const count = data.value?.players.length ?? 0
  if (count === 0) return '0名を表示中'
  const first = pageIndex.value * 200 + 1
  return `${first}–${first + count - 1}名を表示中`
})

async function load(): Promise<void> {
  const generation = ++requestGeneration
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  const requestedGameId = gameId.value
  const requestedMode = mode.value
  const cursor = pageCursors.value.at(-1)
  data.value = null
  error.value = null
  if (requestedGameId.length === 0) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const page = await fetchGameStats(
      requestedGameId,
      requestedMode,
      controller.signal,
      cursor,
    )
    if (generation !== requestGeneration) return
    if (page.game_id !== requestedGameId || page.mode !== requestedMode)
      throw new Error('成績の取得条件が一致しません')
    data.value = page
  } catch {
    if (generation === requestGeneration) {
      data.value = null
      error.value = '試合成績を取得できませんでした'
    }
  } finally {
    if (generation === requestGeneration) loading.value = false
  }
}

function nextPage(): void {
  const cursor = data.value?.next_cursor
  if (!cursor || loading.value || pageCursors.value.includes(cursor)) return
  pageCursors.value = [...pageCursors.value, cursor]
  void load()
}

function previousPage(): void {
  if (pageCursors.value.length <= 1 || loading.value) return
  pageCursors.value = pageCursors.value.slice(0, -1)
  void load()
}

function resetPages(): void {
  pageCursors.value = [undefined]
  void load()
}

async function download(): Promise<void> {
  if (downloading.value) return
  downloading.value = true
  error.value = null
  try {
    const { blob, filename } = await downloadGameStatsCsv(
      gameId.value,
      mode.value,
    )
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download =
      filename ?? `game-basic-stats-${gameId.value}-${mode.value}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch {
    error.value = 'CSVを取得できませんでした'
  } finally {
    downloading.value = false
  }
}

onMounted(load)
watch([gameId, mode], resetPages)
</script>

<template>
  <main class="mx-auto max-w-6xl space-y-4 px-4 py-6">
    <h1 class="text-2xl font-bold">試合別基本成績</h1>
    <p class="text-sm">試合ID: {{ gameId }}</p>
    <div class="flex flex-wrap items-center gap-3">
      <label class="text-sm">
        表示
        <select v-model="mode" class="ml-1 border px-2 py-1">
          <option value="current">暫定</option>
          <option value="official">公式（終了確定）</option>
        </select>
      </label>
      <button
        type="button"
        class="border px-3 py-1"
        :disabled="downloading"
        @click="download"
      >
        CSVダウンロード
      </button>
    </div>
    <p v-if="error !== null" class="text-sm text-red-700">{{ error }}</p>
    <p v-if="loading" class="text-sm">読み込み中…</p>
    <p v-else-if="data !== null && data.players.length === 0" class="text-sm">
      {{
        mode === 'official'
          ? '終了確定した成績がありません'
          : 'まだ成績がありません'
      }}
    </p>
    <nav
      v-if="data !== null && !loading"
      class="flex items-center gap-3"
      aria-label="成績ページ"
    >
      <button
        type="button"
        class="border px-3 py-1"
        :disabled="pageIndex === 0"
        @click="previousPage"
      >
        前へ
      </button>
      <span>{{ visibleRange }}（{{ pageIndex + 1 }}ページ）</span>
      <button
        type="button"
        class="border px-3 py-1"
        :disabled="data.next_cursor === null"
        @click="nextPage"
      >
        次へ
      </button>
    </nav>
    <BasicStatsTable
      v-if="data !== null && !loading"
      :players="data.players"
      :period-label="mode === 'official' ? '公式' : '暫定'"
    />
  </main>
</template>
