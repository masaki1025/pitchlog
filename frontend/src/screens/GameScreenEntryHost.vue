<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { pinia } from '../appProviders'
import { useAuthStore } from '../stores/authStore'
import GameScreenEntry from './GameScreenEntry.vue'
import { usePreparingEntryProvider } from './GameScreenEntryProvider'
import GameScreenPreparingCreate from './GameScreenPreparingCreate.vue'
const { page, requestPage, retry } = usePreparingEntryProvider('list')
const auth = useAuthStore(pinia)
const route = useRoute()
const creating = ref(false)
watch(
  () => [auth.authEpoch, auth.teamId, route.path],
  () => {
    creating.value = false
  },
  { flush: 'sync' },
)
function inspect() {
  creating.value = false
  retry()
}
</script>
<template>
  <div class="mx-auto max-w-4xl px-4 pt-4">
    <button
      v-if="!creating"
      type="button"
      :disabled="!auth.hasHydrated || !auth.isAuthenticated"
      @click="creating = true"
    >
      新規作成
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
