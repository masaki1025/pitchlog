<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  downloadSeasonStatsCsv,
  fetchSeasonStats,
  type SeasonBasicStats,
  type StatsCategory,
} from '../api/stats'
import BasicStatsTable from '../components/stats/BasicStatsTable.vue'

const router = useRouter()
const currentYear = Number(
  new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Tokyo',
    year: 'numeric',
  }).format(new Date()),
)
const year = ref(currentYear)
const category = ref<StatsCategory>('all')
const data = ref<SeasonBasicStats | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const downloading = ref(false)
const gameId = ref('')

const pendingLabels = computed(() => {
  const labels = new Set<string>()
  for (const player of data.value?.players ?? []) {
    for (const pending of player.pending) {
      if (pending === 'D03_SOURCE_PENDING') labels.add('登板の正式source未接続')
      if (pending === 'D04_SOURCE_PENDING')
        labels.add('打者数の責任帰属source未接続')
    }
  }
  return [...labels]
})

function categoryLabel(value: StatsCategory): string {
  if (value === 'official') return '公式'
  if (value === 'practice') return '練習'
  return '合算'
}

async function load(): Promise<void> {
  if (loading.value) return
  if (!Number.isInteger(year.value) || year.value < 1 || year.value > 9999) {
    data.value = null
    error.value = '年は1〜9999の整数で指定してください'
    return
  }
  loading.value = true
  error.value = null
  try {
    data.value = await fetchSeasonStats(year.value, category.value)
  } catch {
    data.value = null
    error.value = '成績を取得できませんでした'
  } finally {
    loading.value = false
  }
}

async function download(): Promise<void> {
  if (downloading.value) return
  downloading.value = true
  error.value = null
  try {
    const { blob, filename } = await downloadSeasonStatsCsv(
      year.value,
      category.value,
    )
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download =
      filename ?? `season-basic-stats-${year.value}-${category.value}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch {
    error.value = 'CSVを取得できませんでした'
  } finally {
    downloading.value = false
  }
}

function openGame(): void {
  const value = gameId.value.trim()
  if (value.length === 0) return
  void router.push({ name: 'game-stats', params: { gameId: value } })
}

function playerCount(): number {
  return data.value?.players.length ?? 0
}

onMounted(load)
watch([year, category], load)
</script>

<template>
  <main class="mx-auto max-w-6xl space-y-4 px-4 py-6">
    <h1 class="text-2xl font-bold">シーズン基本成績</h1>
    <div class="flex flex-wrap items-end gap-3">
      <label class="text-sm">
        年
        <input
          v-model.number="year"
          type="number"
          min="1"
          max="9999"
          class="ml-1 w-24 border px-2 py-1"
        />
      </label>
      <label class="text-sm">
        区分
        <select v-model="category" class="ml-1 border px-2 py-1">
          <option value="official">公式</option>
          <option value="practice">練習</option>
          <option value="all">合算</option>
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
      <span class="text-sm">{{ categoryLabel(category) }}</span>
    </div>
    <p v-if="error !== null" class="text-sm text-red-700">{{ error }}</p>
    <p v-if="loading" class="text-sm">読み込み中…</p>
    <p v-if="data !== null && !loading" class="text-sm">
      {{ data.period_label }}・{{ playerCount() }}名
    </p>
    <p v-if="pendingLabels.length > 0" class="text-sm text-amber-800">
      未接続: {{ pendingLabels.join(' / ') }}
    </p>
    <p v-if="data !== null && !loading && playerCount() === 0" class="text-sm">
      データなし
    </p>
    <BasicStatsTable
      v-if="data !== null && !loading"
      :players="data.players"
      :period-label="data.period_label"
    />
    <section class="border-t pt-4">
      <h2 class="mb-2 text-lg font-semibold">試合別成績</h2>
      <label class="text-sm">
        試合ID
        <input v-model="gameId" class="ml-1 w-80 border px-2 py-1" />
      </label>
      <button type="button" class="ml-2 border px-3 py-1" @click="openGame">
        表示
      </button>
    </section>
  </main>
</template>
