<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import GameCsvExport from '../components/game/GameCsvExport.vue'
import GameScreenEntryRecord from './GameScreenEntryRecord.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
import GameScreenStart from './GameScreenStart.vue'
import { useGameStartProvider } from './GameScreenStartProvider'
const { preparing, retry } = usePreparingEntryProvider('detail')
const start = useGameStartProvider(preparing)
const route = useRoute()
const gameId = computed(() =>
  typeof route.params.gameId === 'string' ? route.params.gameId : '',
)
// 開始応答を端末へ保存した後、実サーバーから準備中情報を再取得する。
// 開始済みを準備中として保持せず、既recorded/initial復元入口へ移る。
watch(
  () => start.state.value.phase,
  (phase, previous) => {
    if (phase === 'received' && previous !== 'received') retry()
  },
)
</script>
<template>
  <GameScreenEntryRecord
    mode="preparing-read"
    :preparing="preparing"
    @retry="retry"
  />
  <GameScreenStart :preparing="preparing" :connection="start" />
  <GameCsvExport v-if="gameId" :game-id="gameId" />
</template>
