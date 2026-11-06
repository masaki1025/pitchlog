<script setup lang="ts">
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GameScreenEntryRecord from './GameScreenEntryRecord.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
import GameScreenStart from './GameScreenStart.vue'
import { useGameStartProvider } from './GameScreenStartProvider'
const { preparing, retry } = usePreparingEntryProvider('detail')
const start = useGameStartProvider(preparing)
const route = useRoute()
const router = useRouter()
// 開始応答を端末へ保存した後、実サーバーから準備中情報を再取得する。
// 開始済みを準備中として保持せず、既recorded/initial復元入口へ移る。
watch(
  () => start.state.value.phase,
  (phase, previous) => {
    if (phase === 'received' && previous !== 'received') {
      retry()
      // この画面で今受理した開始だけをv3へ接ぎ、旧復旧queryは保存する。
      if (previous === 'sending' && route.query.recording === undefined)
        void router.replace({
          query: { ...route.query, recording: 'play-prefix-v3' },
        })
    }
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
</template>
