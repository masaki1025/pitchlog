<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  readGameLifecycle,
  type GameLifecycleRead,
} from '../api/gameLifecycleSpike'
import { useAuthStore } from '../stores/authStore'
import GameScreenLifecyclePanel from './GameScreenLifecyclePanel.vue'

const route = useRoute()
const auth = useAuthStore()
const gameId = computed(() =>
  typeof route.params.gameId === 'string' ? route.params.gameId : '',
)
const lifecycle = ref<GameLifecycleRead | null>(null)
const loading = ref(false)
const message = ref('')
let sequence = 0

async function load(): Promise<void> {
  if (gameId.value === '' || auth.teamId === null) {
    lifecycle.value = null
    message.value = 'ログイン状態と試合IDを確認できません'
    return
  }
  const epoch = auth.authEpoch
  const request = ++sequence
  loading.value = true
  try {
    const value = await readGameLifecycle(gameId.value)
    if (request !== sequence || auth.authEpoch !== epoch) return
    lifecycle.value = value
    message.value =
      value.status === 'finished'
        ? '終了確定版を取得しました'
        : '試合は進行中です'
  } catch {
    if (request !== sequence || auth.authEpoch !== epoch) return
    lifecycle.value = null
    message.value = '試合の終了状態を取得できません'
  } finally {
    if (request === sequence) loading.value = false
  }
}

const reopened = computed(
  () =>
    lifecycle.value?.finalizations.some(
      (item) => item.invalidatedBy !== null,
    ) === true,
)

onMounted(load)
</script>

<template>
  <main
    data-testid="lifecycle-screen"
    class="mx-auto max-w-3xl space-y-5 p-4 pb-12 wrap-anywhere"
  >
    <header class="space-y-2">
      <RouterLink
        :to="{ name: 'games' }"
        class="inline-block min-h-11 underline"
      >
        試合一覧へ
      </RouterLink>
      <p class="text-sm">試合の終了・再開spike（正式統合前の候補）</p>
      <h1 class="text-2xl font-extrabold">終了確定版と追記再開</h1>
      <p class="text-sm">
        試合作成・開始・最初の記録は製品画面で行い、この画面は保存済みイベントから
        終了確定版・再開による失効・再終了の版を読みます。
      </p>
    </header>
    <GameScreenLifecyclePanel
      v-if="gameId"
      :game-id="gameId"
      :lifecycle="lifecycle"
      :loading="loading"
      :message="message"
      @refresh="load"
      @changed="load"
    />
    <p
      v-if="reopened && lifecycle?.status === 'in_progress'"
      data-testid="lifecycle-reopen-gap"
      class="rounded-xl border border-slate-300 bg-slate-50 p-4 text-sm"
    >
      再開は保存済みです。再開後の通常投球は、製品 prefix 境界が非 play
      イベントをまだ橋渡ししないため未接続です（残件）。
    </p>
  </main>
</template>
