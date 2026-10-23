<script setup lang="ts">
import GameScreenEntry from './GameScreenEntry.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
const { page, requestPage } = usePreparingEntryProvider('list')
</script>
<template>
  <GameScreenEntry
    mode="preparing-read"
    :page="page"
    @page-request="requestPage"
  />
</template>
