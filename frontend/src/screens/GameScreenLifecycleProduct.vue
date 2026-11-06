<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAuthStore } from '../stores/authStore'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import GameScreenLifecyclePanel from './GameScreenLifecyclePanel.vue'
import {
  createGameLifecycleWriter,
  GameLifecycleController,
  type GameLifecycleHandoff,
  type GameLifecycleView,
} from './gameLifecycleController'

const props = defineProps<{ gameId: string }>()
const emit = defineEmits<{
  'resume-recording': [handoff: GameLifecycleHandoff]
}>()
const auth = useAuthStore()
const sameProfile = ref(false)
const sameMode = ref(false)
const sameBucket = ref(false)
const noLockdown = ref(false)
const view = ref<GameLifecycleView | null>(null)
const unavailable = ref(false)
const pending = ref(false)
const verified = computed(
  () => auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null,
)
let controller: GameLifecycleController | null = null
let sequence = 0
const writer = createGameLifecycleWriter({
  topLevelHttps: () =>
    globalThis.isSecureContext === true &&
    location.protocol === 'https:' &&
    window.top === window.self,
  sameBrowserProfile: () => sameProfile.value,
  sameBrowsingMode: () => sameMode.value,
  sameStorageBucket: () => sameBucket.value,
  siteStorageAvailable: () => typeof indexedDB !== 'undefined',
  lockdownModeNotApplied: () => noLockdown.value,
  identityVerified: () => verified.value,
})

async function act(kind: 'refresh' | 'end' | 'reopen' | 'retry') {
  const current = controller
  if (!current || pending.value) return
  const own = sequence
  pending.value = true
  unavailable.value = false
  try {
    const operation = current[kind]()
    view.value = current.view
    await operation
    if (own === sequence) view.value = current.view
  } catch {
    if (own === sequence) unavailable.value = true
  } finally {
    if (own === sequence) pending.value = false
  }
}

function resume(handoff: GameLifecycleHandoff) {
  if (
    verified.value &&
    handoff.gameId === props.gameId &&
    handoff.tenantId === auth.teamId &&
    controller?.view.resumeHandoff !== null &&
    controller?.view.refresh === 'done' &&
    sameOrdinaryWire(controller.view.resumeHandoff, handoff)
  )
    emit('resume-recording', handoff)
}

watch(
  () => [props.gameId, auth.authEpoch, auth.teamId, verified.value] as const,
  () => {
    sequence += 1
    controller?.dispose()
    controller = null
    view.value = null
    pending.value = false
    unavailable.value = false
    sameProfile.value =
      sameMode.value =
      sameBucket.value =
      noLockdown.value =
        false
    if (!verified.value) return
    controller = new GameLifecycleController(
      props.gameId,
      () => ({
        tenantId: auth.teamId,
        epoch: auth.authEpoch,
        verified: verified.value,
      }),
      { writer },
    )
    void act('refresh')
  },
  { immediate: true },
)
onScopeDispose(() => {
  sequence += 1
  controller?.dispose()
  controller = null
})
</script>

<template>
  <section aria-label="終了・再開の操作環境" data-testid="lifecycle-product">
    <fieldset :disabled="pending">
      <legend>この端末で記録を続けるための確認</legend>
      <label
        ><input
          v-model="sameProfile"
          type="checkbox"
        />同じブラウザプロファイルです</label
      >
      <label
        ><input v-model="sameMode" type="checkbox" />同じ閲覧モードです</label
      >
      <label
        ><input
          v-model="sameBucket"
          type="checkbox"
        />同じ保存領域を使用しています</label
      >
      <label
        ><input
          v-model="noLockdown"
          type="checkbox"
        />Lockdownモードは適用されていません</label
      >
    </fieldset>
    <p v-if="unavailable" role="alert">
      終了・再開の状態を確認できません。再取得してください。
    </p>
    <GameScreenLifecyclePanel
      :view="view"
      @refresh="act('refresh')"
      @end="act('end')"
      @reopen="act('reopen')"
      @retry="act('retry')"
      @resume-recording="resume"
      @back="act('refresh')"
    />
  </section>
</template>
