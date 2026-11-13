<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAuthStore } from '../stores/authStore'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import GameScreenSubstitutions from './GameScreenSubstitutions.vue'
import {
  GameScreenSubstitutionProductController,
  type SubstitutionProductResult,
} from './GameScreenSubstitutionProductController'
import {
  substitutionRequest,
  substitutionContextKey,
  validateSubstitutionDraft,
  type PendingRegistrationChoice,
  type VerifiedSubstitutionContext,
} from './GameScreenSubstitutionProductProvider'
import {
  GameScreenPlayerRegistrationProductController,
  type PlayerRegistrationCommitResult,
  type PlayerRegistrationPanelResult,
  type PlayerRegistrationView,
} from './GameScreenPlayerRegistrationProductController'
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
const registrationStatus = ref<PlayerRegistrationPanelResult>('blocked')
const registrations = ref<readonly PlayerRegistrationView[]>([])
const sameProfile = ref(false)
const sameMode = ref(false)
const sameBucket = ref(false)
const noLockdown = ref(false)
const manualSide = ref<'away' | 'home'>('away')
const manualName = ref('')
const manualThrows = ref<'right' | 'left'>('right')
const manualBats = ref<'right' | 'left' | 'both'>('right')
const manualUniform = ref('')
const offline = ref(globalThis.navigator?.onLine === false)
const onOffline = () => {
  offline.value = true
  void reload()
}
const onOnline = () => {
  offline.value = false
  void reload()
}
window.addEventListener('offline', onOffline)
window.addEventListener('online', onOnline)
let controller: GameScreenSubstitutionProductController | null = null
let registrationController: GameScreenPlayerRegistrationProductController | null =
  null
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
const pendingRegistrations = computed<readonly PendingRegistrationChoice[]>(
  () =>
    registrations.value
      .filter(
        (registration) =>
          registration.state === 'unsent' ||
          registration.state === 'unconfirmed',
      )
      .map((registration) => ({
        temporaryId: registration.temporaryId,
        name: registration.name,
        side: registration.side,
      })),
)
const offer = computed(() =>
  context.value === null
    ? null
    : substitutionRequest(context.value, pendingRegistrations.value),
)
const canCommit = computed(
  () =>
    !busy.value &&
    confirmed.value &&
    identity().verified &&
    context.value !== null &&
    status.value === 'ready',
)
// 断中登録は端末キューへ積む。開始資格と登録文脈があればオンラインに限らない。
const canRegister = computed(
  () =>
    !busy.value &&
    confirmed.value &&
    identity().verified &&
    registrationStatus.value !== 'blocked',
)
const message = computed(() =>
  busy.value
    ? '交代原本と送信結果を確認しています'
    : status.value === 'awaiting-registration'
      ? '未送信の選手登録が先に残っています。選手登録を同期してください'
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
  registrationController?.dispose()
  registrationController = null
  context.value = null
  validation.value = null
  status.value = 'blocked'
  registrations.value = []
  registrationStatus.value = 'blocked'
  if (!identity().verified) return
  const current = new GameScreenSubstitutionProductController(
    props.gameId,
    identity,
    writer,
  )
  controller = current
  const registration = new GameScreenPlayerRegistrationProductController(
    props.gameId,
    identity,
    writer,
  )
  registrationController = registration
  busy.value = true
  try {
    const [substitution, offlineRegistration] = await Promise.allSettled([
      current.load(),
      registration.load(),
    ])
    if (own !== sequence) return
    if (substitution.status === 'fulfilled') {
      status.value = substitution.value
      context.value = current.context
    } else {
      status.value = 'blocked'
    }
    if (offlineRegistration.status === 'fulfilled') {
      registrationStatus.value = offlineRegistration.value
      registrations.value = registration.registrations
    } else {
      registrationStatus.value = 'blocked'
    }
  } finally {
    if (own === sequence) busy.value = false
  }
}

function refreshRegistrations(): void {
  const current = registrationController
  if (!current) return
  registrations.value = current.registrations
  registrationStatus.value = registrations.value.some(
    (registration) =>
      registration.state === 'unsent' ||
      registration.state === 'action-required' ||
      registration.state === 'unconfirmed',
  )
    ? 'pending'
    : 'ready'
}

function draftChanged(value: SubstitutionDraftsSnapshot): void {
  const current = context.value
  if (!current || !value.normal || !canCommit.value) {
    validation.value = null
    return
  }
  try {
    validation.value = validateSubstitutionDraft(
      current,
      value.normal,
      pendingRegistrations.value,
    )
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

function registrationMessageFor(
  result: PlayerRegistrationCommitResult,
): string {
  switch (result) {
    case 'saved':
      return '選手を登録し、正式IDを確認しました。登録済み選手から交代を記録できます'
    case 'pending':
      return '選手登録を端末に保存しました。未送信の操作があれば順に同期します'
    case 'ready':
      return '未送信の選手登録はありません'
    case 'awaiting-substitution':
      return '未送信の交代が先にあります。交代を同期してから登録してください'
    case 'invalid':
      return '選手名・投・打を確認してください'
    case 'blocked':
      return '登録結果を確認できません。端末の保存状態を確認してください'
    default:
      return '選手登録の状態を確認できません'
  }
}

async function register(draft: PlayerRegistrationDraft): Promise<void> {
  if (!canRegister.value || !registrationController) return
  busy.value = true
  registrationMessage.value = '選手登録を端末に保存しています'
  try {
    const result = await registrationController.register(draft)
    refreshRegistrations()
    registrationMessage.value = registrationMessageFor(result)
    if (result === 'saved') await reload()
  } catch {
    registrationMessage.value = registrationMessageFor('blocked')
  } finally {
    busy.value = false
  }
}

async function retryRegistration(): Promise<void> {
  if (busy.value || !registrationController) return
  busy.value = true
  registrationMessage.value = '端末の選手登録を送信しています'
  try {
    const result = await registrationController.retry()
    refreshRegistrations()
    registrationMessage.value = registrationMessageFor(result)
    if (result === 'saved') await reload()
  } catch {
    registrationMessage.value = registrationMessageFor('blocked')
  } finally {
    busy.value = false
  }
}

function submitOfflineRegistration(): void {
  void register({
    side: manualSide.value,
    answers: {
      name: manualName.value,
      throws: manualThrows.value,
      bats: manualBats.value,
      uniformNumber: manualUniform.value,
    },
  })
}

function registrationStateLabel(
  state: PlayerRegistrationView['state'],
): string {
  switch (state) {
    case 'unsent':
      return '未送信'
    case 'confirmed':
      return '確定済み'
    case 'action-required':
      return '要操作'
    case 'evacuated':
      return '退避済み'
    case 'unconfirmed':
      return '写像未確認'
    default:
      return '不明'
  }
}

function shortId(value: string): string {
  return value.slice(0, 8)
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
  window.removeEventListener('offline', onOffline)
  window.removeEventListener('online', onOnline)
  controller?.dispose()
  registrationController?.dispose()
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
      v-if="registrationStatus === 'pending'"
      type="button"
      :disabled="busy || !confirmed"
      data-testid="player-registration-retry"
      @click="retryRegistration"
    >
      端末の選手登録を再送
    </button>
    <ul
      v-if="registrations.length > 0"
      aria-label="端末の選手登録"
      data-testid="player-registrations"
    >
      <li
        v-for="registration in registrations"
        :key="registration.temporaryId"
        :data-state="registration.state"
      >
        {{ registration.name }}（{{
          registration.side === 'away' ? '先攻' : '後攻'
        }}）: {{ registrationStateLabel(registration.state) }}
        <span data-testid="player-registration-temporary-id"
          >一時ID {{ shortId(registration.temporaryId) }}</span
        >
        <span
          v-if="registration.officialId"
          data-testid="player-registration-official-id"
          >正式ID {{ shortId(registration.officialId) }}</span
        >
      </li>
    </ul>
    <form
      v-if="offer === null && offline"
      aria-label="断中のその場登録"
      data-testid="offline-player-registration"
      @submit.prevent="submitOfflineRegistration"
    >
      <fieldset :disabled="busy || !canRegister">
        <legend>その場で選手を登録（断中）</legend>
        <label
          >チーム
          <select v-model="manualSide">
            <option value="away">先攻</option>
            <option value="home">後攻</option>
          </select>
        </label>
        <label
          >選手名 <input v-model="manualName" type="text" required
        /></label>
        <label
          >投
          <select v-model="manualThrows">
            <option value="right">右</option>
            <option value="left">左</option>
          </select>
        </label>
        <label
          >打
          <select v-model="manualBats">
            <option value="right">右</option>
            <option value="left">左</option>
            <option value="both">両</option>
          </select>
        </label>
        <label
          >背番号（任意） <input v-model="manualUniform" type="text"
        /></label>
        <button type="submit" :disabled="busy || !canRegister">
          登録を端末に保存
        </button>
      </fieldset>
    </form>
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
