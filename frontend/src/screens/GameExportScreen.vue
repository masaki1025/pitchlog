<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import GameCsvExport from '../components/game/GameCsvExport.vue'

const route = useRoute()
const gameId = computed(() => String(route.params.gameId ?? ''))
</script>

<template>
  <main class="mx-auto max-w-4xl space-y-4 px-4 py-6">
    <h1 class="text-2xl font-bold">試合データ出力</h1>
    <p class="text-sm break-all">試合ID: {{ gameId }}</p>
    <GameCsvExport v-if="gameId.length > 0" :game-id="gameId" />
    <p v-else class="text-sm">試合IDがありません</p>
  </main>
</template>
