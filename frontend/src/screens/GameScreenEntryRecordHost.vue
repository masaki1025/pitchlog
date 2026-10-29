<script setup lang="ts">
import GameScreenEntryRecord from './GameScreenEntryRecord.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
import GameScreenStart from './GameScreenStart.vue'
import { useGameStartProvider } from './GameScreenStartProvider'
const { preparing, retry } = usePreparingEntryProvider('detail')
const start = useGameStartProvider(preparing)
</script>
<template>
  <GameScreenEntryRecord
    mode="preparing-read"
    :preparing="preparing"
    @retry="retry"
  />
  <GameScreenStart :preparing="preparing" :connection="start" />
</template>
