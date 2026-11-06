<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useAuthStore } from '../stores/authStore'
import StrikeZone from '../components/zone/StrikeZone.vue'
import {
  readPitchTypeOptions,
  type PitchTypeOption,
} from '../api/pitchTypeOptions'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import { isPlayDefinition, observationsValid } from '../api/terminalPitchWire'
import type { Observations } from '../../../contracts/state-transition/play_prefix_v2_payload_v1'
import {
  GameScreenUndoProductController,
  type UndoProductResult,
} from './GameScreenUndoProductController'
import type { UndoProductContext } from './GameScreenUndoProductProvider'
const props = defineProps<{ gameId: string }>(),
  emit = defineEmits<{ saved: []; state: [storedNative: boolean] }>(),
  auth = useAuthStore()
const context = ref<UndoProductContext | null>(null),
  status = ref<UndoProductResult>('blocked'),
  busy = ref(false)
const sameProfile = ref(false),
  sameMode = ref(false),
  sameBucket = ref(false),
  noLockdown = ref(false)
const point = ref<{ x: number; y: number } | null>(null),
  view = ref<'catcher' | 'pitcher'>('catcher'),
  selected = ref(''),
  options = ref<PitchTypeOption[]>([]),
  cursor = ref<string | null>(null),
  vocabularyFailed = ref(false)
let controller: GameScreenUndoProductController | null = null,
  sequence = 0,
  request: AbortController | null = null
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
const canOperate = computed(
  () =>
    !busy.value &&
    confirmed.value &&
    identity().verified &&
    context.value !== null &&
    ['ready', 'saved', 'empty'].includes(status.value),
)
const balls = computed(
  () =>
    context.value?.source.checkpoint.content.restored.current.stateFields[
      'state.count.balls'
    ],
)
const depth = computed(
  () => context.value?.source.checkpoint.content.activeDepth,
)
const message = computed(() =>
  busy.value
    ? '原本と送信結果を確認しています'
    : status.value === 'pending'
      ? '結果未確認の要求が端末に残っています。同じ要求を再送してください'
      : status.value === 'saved-awaiting-read'
        ? '保存応答を受領しました。表示の更新はサーバー再取得待ちです'
        : status.value === 'blocked'
          ? '取消用の原本または開始資格を確認できません。新しい要求に置き換えず再取得してください'
          : status.value === 'empty'
            ? '取り消せる操作はありません'
            : 'サーバーで確認した記録を表示しています',
)
async function vocabulary(next: string | null = null) {
  const own = sequence,
    epoch = auth.authEpoch
  vocabularyFailed.value = false
  try {
    const value = await readPitchTypeOptions(next, 25, request?.signal)
    if (own !== sequence || epoch !== auth.authEpoch) return
    options.value = [...value.items]
    selected.value = ''
    cursor.value = value.next_cursor
  } catch {
    if (own === sequence) {
      options.value = []
      vocabularyFailed.value = true
    }
  }
}
async function act(action: () => Promise<UndoProductResult>) {
  if (busy.value || !controller) return
  busy.value = true
  const own = sequence,
    c = controller
  try {
    const result = await action()
    if (own !== sequence) return
    status.value = result
    context.value = c.context
    emit('state', context.value?.storedNative === true)
    if (status.value === 'saved') emit('saved')
  } finally {
    if (own === sequence) busy.value = false
  }
}
async function undo() {
  if (canOperate.value) await act(() => controller!.undo())
}
async function ball() {
  if (
    !canOperate.value ||
    !context.value?.storedNative ||
    !point.value ||
    !options.value.some((x) => x.key === selected.value)
  )
    return
  try {
    const course = invokeFirstBallDomain('quantizeCourse', {
      x: String(point.value.x),
      y: String(point.value.y),
      view: view.value,
      size: '263',
    })
    const observations: unknown = {
      pitchTypeKey: selected.value,
      course,
      pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
      stance: null,
      battingSide: null,
    }
    if (
      !isPlayDefinition<Observations>(observations, 'PayloadObservations') ||
      !observationsValid(observations)
    )
      return
    const c = controller
    if (c) await act(() => c.ball(observations))
  } catch {
    status.value = 'blocked'
  }
}
async function retry() {
  const c = controller
  if (c) await act(() => c.retry())
}
async function reload() {
  const c = controller
  if (c) await act(() => c.load())
}
watch(
  () =>
    [
      props.gameId,
      auth.teamId,
      auth.authEpoch,
      auth.hasHydrated,
      auth.isAuthenticated,
    ] as const,
  async () => {
    const own = ++sequence
    request?.abort()
    request = new AbortController()
    controller?.dispose()
    controller = null
    context.value = null
    emit('state', false)
    busy.value = false
    status.value = 'blocked'
    selected.value = ''
    point.value = null
    options.value = []
    if (!identity().verified) return
    const c = new GameScreenUndoProductController(
      props.gameId,
      identity,
      writer,
    )
    controller = c
    busy.value = true
    try {
      const result = await c.load()
      if (own !== sequence) return
      status.value = result
      context.value = c.context
      emit('state', context.value?.storedNative === true)
      await vocabulary()
    } finally {
      if (own === sequence) busy.value = false
    }
  },
  { immediate: true },
)
onScopeDispose(() => {
  sequence++
  request?.abort()
  controller?.dispose()
})
</script>
<template>
  <section aria-label="取消と取消後の記録" data-testid="undo-product-panel">
    <h2>直前の記録を取り消す</h2>
    <p role="status" data-testid="undo-product-status">{{ message }}</p>
    <template v-if="context"
      ><p>
        サーバー確認済み：<span data-testid="undo-product-balls">{{
          balls
        }}</span
        >ボール・<span data-testid="undo-product-depth">{{ depth }}</span
        >件の履歴
      </p>
      <p>最終更新：{{ context.game.last_saved_at }}</p></template
    >
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
        />開始時と同じ保存領域を使っています</label
      >
      <label
        ><input
          v-model="noLockdown"
          type="checkbox"
        />ロックダウンモードではありません</label
      >
    </fieldset>
    <button
      data-testid="undo-product-apply"
      :disabled="!canOperate || depth === '0'"
      @click="undo"
    >
      直前の記録を取り消す
    </button>
    <button
      data-testid="undo-product-retry"
      :disabled="busy || !confirmed"
      @click="retry"
    >
      同じ要求を再送する
    </button>
    <button data-testid="undo-product-reload" :disabled="busy" @click="reload">
      サーバーから再取得
    </button>
    <fieldset v-if="context?.storedNative" :disabled="busy">
      <legend>取消後の通常投球（ボール）</legend>
      <p>現在接続しているのは通常ボールです。他の操作もMVPの完成対象です。</p>
      <label
        >球種<select v-model="selected" data-testid="undo-product-pitch-type">
          <option value="">選択してください</option>
          <option
            v-for="option in options"
            :key="option.key"
            :value="option.key"
          >
            {{ option.display_name }}
          </option>
        </select></label
      >
      <p v-if="vocabularyFailed" role="alert">球種を取得できません。</p>
      <button
        v-if="cursor !== null"
        :disabled="busy"
        @click="vocabulary(cursor)"
      >
        次の球種
      </button>
      <label
        >視点<select v-model="view" @change="point = null">
          <option value="catcher">捕手視点</option>
          <option value="pitcher">投手後方視点</option>
        </select></label
      >
      <div data-testid="undo-product-course">
        <StrikeZone
          :point="point"
          plate-side=""
          :viewpoint="view"
          :disabled="busy"
          @tap="(x, y) => (point = { x, y })"
        />
      </div>
      <p>球速・構え・打席側は未入力として保存します。</p>
      <button
        data-testid="undo-product-ball"
        :disabled="!canOperate || !point || !selected"
        @click="ball"
      >
        ボールを記録する
      </button>
    </fieldset>
  </section>
</template>
