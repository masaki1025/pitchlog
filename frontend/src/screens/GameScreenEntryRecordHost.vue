<script setup lang="ts">
import GameScreenEntryRecord from './GameScreenEntryRecord.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
const { preparing, retry } = usePreparingEntryProvider('detail')
</script>
<template>
  <GameScreenEntryRecord
    mode="preparing-read"
    :preparing="preparing"
    @retry="retry"
  />
</template>
