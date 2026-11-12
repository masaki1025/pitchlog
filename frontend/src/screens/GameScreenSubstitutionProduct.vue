<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAuthStore } from '../stores/authStore'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import { createPlayer } from '../api/roster'
import GameScreenSubstitutions from './GameScreenSubstitutions.vue'
import {
  GameScreenSubstitutionProductController,
  type SubstitutionProductResult,
} from './GameScreenSubstitutionProductController'
import {
  playerRegistration,
  registrationFailure,
  substitutionRequest,
  substitutionContextKey,
  validateSubstitutionDraft,
  type VerifiedSubstitutionContext,
} from './GameScreenSubstitutionProductProvider'
import type {
  PlayerRegistrationDraft,
  RawSubstitutionDraft,
  SubstitutionDraftsSnapshot,
  SubstitutionValidation,
} from './GameScreenSubstitutionTypes'

const props = defineProps<{ gameId: string }>()
const emit = defineEmits<{ saved: [] }>()
const auth = useAuthStore()
const context = ref<VerifiedSubstitutionContext | null>(null)
const validation = ref<SubstitutionValidation | null>(null)
const status = ref<SubstitutionProductResult>('blocked')
const busy = ref(false)
const registrationMessage = ref('')
const sameProfile = ref(false)
const sameMode = ref(false)
const sameBucket = ref(false)
const noLockdown = ref(false)
let controller: GameScreenSubstitutionProductController | null = null
let sequence = 0
const identity = () => ({
  tenantId: auth.teamId,
  epoch: auth.authEpoch,
  verified: auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null,
})
const https = () =>
  globalThis.isSecureContext === true &&
  window.location.protocol === 'https:' &&
  window.top === window.self
const confirmed = computed(
  () =>
    sameProfile.value &&
    sameMode.value &&
    sameBucket.value &&
    noLockdown.value &&
    https(),
)
const writer = {
  resolvePreconditions: () => ({
    topLevelHttps: https(),
    sameBrowserProfile: sameProfile.value,
    sameBrowsingMode: sameMode.value,
    sameStorageBucket: sameBucket.value,
    siteStorageAvailable: typeof indexedDB !== 'undefined',
    lockdownModeNotApplied: noLockdown.value,
  }),
  revalidateSingleWriter: () => confirmed.value && identity().verified,
}
const key = computed(() =>
  context.value === null ? null : substitutionContextKey(context.value),
)
const offer = computed(() =>
  context.value === null ? null : substitutionRequest(context.value),
)
const canCommit = computed(
  () =>
    !busy.value &&
    confirmed.value &&
    identity().verified &&
    context.value !== null &&
    status.value === 'ready',
)
// 名簿登録はオンラインの正式APIだけを使い、断中は登録済み選手の選択に留める。
const canRegister = computed(
  () => canCommit.value && navigator.onLine !== false && context.value !== null,
)
const message = computed(() =>
  busy.value
    ? '交代原本と送信結果を確認しています'
    : status.value === 'pending'
      ? '結果未確認の交代が端末に残っています。同じ要求を再送してください'
      : status.value === 'saved-awaiting-read'
        ? '保存応答を受領しました。画面更新は再取得待ちです'
        : status.value === 'blocked'
          ? '交代原本または開始資格を確認できません。再取得してください'
          : status.value === 'saved'
            ? '交代を保存し、現在状態を再取得しました'
            : '交代を選んでください',
)

async function reload(): Promise<void> {
  const own = ++sequence
  controller?.dispose()
  controller = null
  context.value = null
  validation.value = null
  status.value = 'blocked'
  if (!identity().verified) return
  const current = new GameScreenSubstitutionProductController(
    props.gameId,
    identity,
    writer,
  )
  controller = current
  busy.value = true
  try {
    status.value = await current.load()
    if (own === sequence) context.value = current.context
  } catch {
    if (own === sequence) status.value = 'blocked'
  } finally {
    if (own === sequence) busy.value = false
  }
}

function draftChanged(value: SubstitutionDraftsSnapshot): void {
  const current = context.value
  if (!current || !value.normal || !canCommit.value) {
    validation.value = null
    return
  }
  try {
    validation.value = validateSubstitutionDraft(current, value.normal)
  } catch {
    validation.value = { identity: value.normal.identity, kind: 'failed' }
  }
}

async function apply(draft: RawSubstitutionDraft): Promise<void> {
  if (
    !canCommit.value ||
    validation.value?.kind !== 'valid' ||
    !sameOrdinaryWire(validation.value.identity, draft.identity) ||
    !controller
  )
    return
  busy.value = true
  try {
    status.value = await controller.commit(draft)
    context.value = controller.context
    validation.value = null
    if (status.value === 'saved') emit('saved')
  } finally {
    busy.value = false
  }
}

async function register(draft: PlayerRegistrationDraft): Promise<void> {
  const current = context.value
  if (!canRegister.value || current === null) return
  const body = playerRegistration(draft, current.state[draft.side].teamId)
  if (body === null) {
    registrationMessage.value = '選手名・投・打を確認してください'
    return
  }
  busy.value = true
  registrationMessage.value = '選手を名簿へ登録しています'
  try {
    const created = await createPlayer(body)
    const sameNumber = created.same_number_players
      .map((player) => player.name)
      .filter((name) => name.length > 0)
    registrationMessage.value =
      sameNumber.length > 0
        ? `選手を名簿へ登録しました。同じ背番号の選手がいます: ${sameNumber.join('、')}。登録済み選手から選んで交代を記録してください`
        : '選手を名簿へ登録しました。登録済み選手から選んで交代を記録してください'
    await reload()
  } catch (error) {
    // 4xxは入力拒否として確定できる。通信断・応答喪失は登録済みか不明なので
    // 失敗と決めず、名簿を再取得して同じ選手がいないか確認させる。
    const failure = registrationFailure(error)
    registrationMessage.value = failure.message
    if (failure.reload) await reload()
  } finally {
    busy.value = false
  }
}

async function retry(): Promise<void> {
  if (
    busy.value ||
    status.value !== 'pending' ||
    !confirmed.value ||
    !controller
  )
    return
  busy.value = true
  try {
    status.value = await controller.retry()
    context.value = controller.context
    if (status.value === 'saved') emit('saved')
  } finally {
    busy.value = false
  }
}

watch(
  () => [
    props.gameId,
    auth.teamId,
    auth.authEpoch,
    auth.hasHydrated,
    auth.isAuthenticated,
  ],
  reload,
  { immediate: true },
)
onScopeDispose(() => {
  sequence++
  controller?.dispose()
})
</script>

<template>
  <section aria-label="選手交代の記録" data-testid="substitution-product-panel">
    <h2>選手交代を記録する</h2>
    <p role="status" data-testid="substitution-product-status">{{ message }}</p>
    <fieldset :disabled="busy">
      <legend>この記録端末の条件</legend>
      <label
        ><input
          v-model="sameProfile"
          type="checkbox"
        />開始時と同じブラウザのプロフィールです</label
      >
      <label
        ><input
          v-model="sameMode"
          type="checkbox"
        />開始時と同じ通常・プライベートモードです</label
      >
      <label
        ><input
          v-model="sameBucket"
          type="checkbox"
        />開始時と同じ保存領域です</label
      >
      <label
        ><input
          v-model="noLockdown"
          type="checkbox"
        />ブラウザの保存制限がかかっていません</label
      >
    </fieldset>
    <button type="button" :disabled="busy" @click="reload">
      現在の交代原本を再取得
    </button>
    <p role="status" data-testid="substitution-registration-status">
      {{ registrationMessage }}
    </p>
    <button
      v-if="status === 'pending'"
      type="button"
      :disabled="busy || !confirmed"
      @click="retry"
    >
      同じ交代要求を再送
    </button>
    <GameScreenSubstitutions
      :request="offer"
      :active-context-key="key"
      :lock-state="key ? { contextKey: key, state: 'open' } : null"
      :validation="validation"
      :commit-enabled="canCommit"
      :registration-enabled="canRegister"
      @draft-change="draftChanged"
      @apply-normal="apply"
      @register-player="register"
    />
  </section>
</template>
