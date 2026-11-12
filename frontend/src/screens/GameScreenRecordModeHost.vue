<script setup lang="ts">
import { computed, onScopeDispose, ref, toRaw, watch } from 'vue'
import { useRouter } from 'vue-router'
import GameScreenEntryRecordHost from './GameScreenEntryRecordHost.vue'
import GameScreenOrdinaryPitch from './GameScreenOrdinaryPitch.vue'
import {
  isLocalRecordingSession,
  type LocalRecordingSession,
} from '../lib/localRecordingSession'
const props = defineProps<{ localSession?: LocalRecordingSession }>()
const router = useRouter()
const revision = ref(0)
const session = computed(() => {
  void revision.value
  const value = props.localSession ? toRaw(props.localSession) : null
  return isLocalRecordingSession(value) ? value : null
})
const usable = computed(() => session.value?.current === true)
const context = computed(() => session.value?.context)
function changed() {
  revision.value += 1
}
window.addEventListener('storage', changed)
onScopeDispose(() => {
  window.removeEventListener('storage', changed)
  session.value?.dispose()
})
watch(
  () => props.localSession,
  (value, old) => {
    if (old && old !== value) toRaw(old).dispose()
  },
)
async function reconnect() {
  if (!session.value) return
  await router.replace({
    name: 'game-record',
    params: { gameId: session.value.gameId },
    query: { recording: 'play-prefix-v3' },
    force: true,
  })
}
</script>
<template>
  <template v-if="localSession">
    <h1 class="sr-only">端末内の記録</h1>
    <p class="sr-only" role="status">
      通信を確認できません。表示は端末内の暫定状態です。追加記録は未送信で、サーバーの保存・現在の記録権は未確認です。
    </p>
    <GameScreenOrdinaryPitch
      v-if="usable && context && session"
      :context="context"
      :local-session="session"
    />
    <p v-else role="alert">
      保存資格が変わりました。オンラインで再認証し、記録を再取得してください。
    </p>
    <button type="button" @click="reconnect">
      接続を確認して未送信記録を同期する
    </button>
  </template>
  <template v-else>
    <GameScreenEntryRecordHost />
    <nav aria-label="試合データ出力" class="mx-auto max-w-4xl px-4 pb-6">
      <RouterLink
        :to="{
          name: 'game-export',
          params: { gameId: router.currentRoute.value.params.gameId },
        }"
        class="inline-block rounded border px-3 py-2 underline"
        >毎球CSVへ</RouterLink
      >
      <p class="text-sm">未送信の記録はサーバーのCSVに含まれません。</p>
    </nav>
  </template>
</template>
