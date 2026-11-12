<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useRoute } from 'vue-router'
import { pinia } from '../appProviders'
import { useAuthStore } from '../stores/authStore'
import GameScreenEntry from './GameScreenEntry.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
import GameScreenPreparingCreate from './GameScreenPreparingCreate.vue'
const { page, requestPage, retry } = usePreparingEntryProvider('list')
const auth = useAuthStore(pinia)
const route = useRoute()
const creating = ref(route.query.create === '1')
watch(
  () => [auth.authEpoch, auth.teamId, route.path],
  () => {
    creating.value = route.query.create === '1'
  },
  { flush: 'sync' },
)
function inspect() {
  creating.value = false
  retry()
}
</script>
<template>
  <div class="mx-auto flex max-w-4xl justify-end gap-2 px-4 pt-4">
    <RouterLink
      :to="{ name: 'games-archive' }"
      class="inline-flex min-h-12 items-center rounded-xl border border-slate-300 bg-white px-4 font-bold dark:border-slate-600 dark:bg-slate-800"
    >
      開始済み一覧
    </RouterLink>
    <button
      v-if="!creating"
      type="button"
      class="min-h-12 rounded-xl bg-sky-600 px-5 font-bold text-white shadow-sm hover:bg-sky-700 disabled:opacity-40"
      :disabled="!auth.hasHydrated || !auth.isAuthenticated"
      @click="creating = true"
    >
      新しい試合
    </button>
  </div>
  <GameScreenPreparingCreate
    v-if="creating"
    @close="creating = false"
    @inspect="inspect"
  />
  <GameScreenEntry
    mode="preparing-read"
    :page="page"
    @page-request="requestPage"
  />
</template>
