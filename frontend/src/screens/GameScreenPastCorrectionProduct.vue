<script setup lang="ts">
/** 実v3履歴の有限P3対象だけを原版照会後に確認・送信する。 */
import { computed, onScopeDispose, ref, toRaw, watch } from 'vue'
import StrikeZone from '../components/zone/StrikeZone.vue'
import {
  isLineupPrefixGame,
  type LineupPrefixGame,
} from '../api/lineupPrefixGame'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  readPitchTypeOptions,
  type PitchTypeOption,
} from '../api/pitchTypeOptions'
import type {
  P3ReplacementResult,
  P3TargetOffer,
} from '../api/pastCorrectionProduct'
import { useAuthStore } from '../stores/authStore'
import geometry from '../../../contracts/display_geometry_263_v1.json'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import type { FirstBallObservations } from '../api/firstBallWire'
import {
  GameScreenPastCorrectionProductController,
  type P3ScreenResult,
} from './GameScreenPastCorrectionProductController'

const props = withDefaults(
  defineProps<{ game: LineupPrefixGame; suspended?: boolean }>(),
  { suspended: false },
)
const emit = defineEmits<{ saved: [] }>()
const auth = useAuthStore()
const sameProfile = ref(false)
const sameMode = ref(false)
const sameBucket = ref(false)
const noLockdown = ref(false)
const httpsTopLevel = () =>
  globalThis.isSecureContext === true &&
  window.location.protocol === 'https:' &&
  window.top === window.self
const confirmed = computed(
  () =>
    sameProfile.value &&
    sameMode.value &&
    sameBucket.value &&
    noLockdown.value &&
    httpsTopLevel(),
)
const identity = () => ({
  tenantId: auth.teamId,
  epoch: auth.authEpoch,
  verified: auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null,
})
const writer = {
  resolvePreconditions: () => ({
    topLevelHttps: httpsTopLevel(),
    sameBrowserProfile: sameProfile.value,
    sameBrowsingMode: sameMode.value,
    sameStorageBucket: sameBucket.value,
    siteStorageAvailable: typeof indexedDB !== 'undefined',
    lockdownModeNotApplied: noLockdown.value,
  }),
  revalidateSingleWriter: () =>
    confirmed.value && identity().verified && !props.suspended,
}
const game = ref<LineupPrefixGame>(structuredClone(toRaw(props.game)))
const targetD1 = ref(0)
const offer = ref<P3TargetOffer | null>(null)
const replacement = ref<P3ReplacementResult | ''>('')
const pitchType = ref('')
const point = ref<{ x: number; y: number } | null>(null)
const viewpoint = ref<'catcher' | 'pitcher'>('catcher')
const unrecordedDetailsConfirmed = ref(false)
const previewConfirmed = ref(false)
const status = ref<P3ScreenResult>('blocked')
const busy = ref(false)
const vocabulary = ref<readonly PitchTypeOption[]>([])
const nextCursor = ref<string | null>(null)
const vocabularyFailed = ref(false)
let controller: GameScreenPastCorrectionProductController | null = null
let sequence = 0
let request: AbortController | null = null
let watchedInput: unknown = null

const finite = computed(
  () =>
    game.value.page.next_cursor === null && game.value.page.items.length <= 25,
)
const targets = computed(() =>
  game.value.page.items
    .map((item, index) => ({
      d1: index + 1,
      row: item.play_row,
    }))
    .filter(
      ({ row }) =>
        row.batting_result_key !== null &&
        [
          'batting-result.ball',
          'batting-result.called-pitch',
          'batting-result.called-strikeout',
        ].includes(row.batting_result_key),
    ),
)
const canInput = computed(
  () =>
    !props.suspended &&
    !busy.value &&
    confirmed.value &&
    identity().verified &&
    status.value === 'ready' &&
    finite.value,
)
const canSave = computed(
  () =>
    canInput.value &&
    offer.value !== null &&
    replacement.value !== '' &&
    pitchType.value !== '' &&
    point.value !== null &&
    unrecordedDetailsConfirmed.value &&
    previewConfirmed.value,
)
const message = computed(() => {
  if (props.suspended)
    return 'サーバーの状態を確認中です。訂正入力を停止しています。'
  if (busy.value) return '対象版と保存結果を確認中です。'
  if (status.value === 'saved')
    return '訂正を保存し、再取得と現行成績を確認しました。'
  if (status.value === 'saved-awaiting-read')
    return '受理結果は端末へ保存しました。再取得が未完了です。'
  if (status.value === 'pending')
    return '先の訂正要求の結果が不明です。新D5を作らず同じ原文を再送してください。'
  if (status.value === 'blocked')
    return '認証、現在版、未同期記録、端末保存または入力前提を確認できません。'
  return '保存済みの過去球と現在版を照合してから変更できます。'
})

function resetSelection() {
  offer.value = null
  replacement.value = ''
  pitchType.value = ''
  point.value = null
  unrecordedDetailsConfirmed.value = false
  previewConfirmed.value = false
}

async function loadVocabulary(cursor: string | null) {
  if (!identity().verified || props.suspended) return
  const own = sequence
  request?.abort()
  const pending = new AbortController()
  request = pending
  vocabularyFailed.value = false
  try {
    const page = await readPitchTypeOptions(cursor, 25, pending.signal)
    if (own !== sequence || pending.signal.aborted || props.suspended) return
    vocabulary.value = page.items
    nextCursor.value = page.next_cursor
    if (!page.items.some((item) => item.key === pitchType.value))
      pitchType.value = ''
  } catch {
    if (own === sequence && !pending.signal.aborted) {
      vocabulary.value = []
      nextCursor.value = null
      vocabularyFailed.value = true
    }
  }
}

async function inspectTarget() {
  if (!controller || !canInput.value || targetD1.value < 1) return
  const own = sequence
  busy.value = true
  resetSelection()
  try {
    const read = await controller.inspect(targetD1.value)
    if (own === sequence && !props.suspended && read) offer.value = read
  } finally {
    if (own === sequence) busy.value = false
  }
}

async function save() {
  const current = controller
  const selected = offer.value
  const position = point.value
  if (
    !current ||
    !selected ||
    !position ||
    !canSave.value ||
    replacement.value === ''
  )
    return
  const own = sequence
  busy.value = true
  try {
    const course = invokeFirstBallDomain('quantizeCourse', {
      x: String(position.x),
      y: String(position.y),
      view: viewpoint.value,
      size: String(geometry.size),
    }) as FirstBallObservations['course']
    const result = await current.commit(selected, replacement.value, {
      pitchTypeKey: pitchType.value,
      course,
      pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
      stance: null,
      battingSide: null,
    })
    if (own !== sequence || props.suspended) return
    status.value = result
    if (result === 'saved') emit('saved')
  } catch {
    if (own === sequence) status.value = 'blocked'
  } finally {
    if (own === sequence) busy.value = false
  }
}

async function retry() {
  const current = controller
  if (!current || props.suspended || busy.value || !confirmed.value) return
  const own = sequence
  busy.value = true
  try {
    const result = await current.retry()
    if (own !== sequence || props.suspended) return
    status.value = result
    if (result === 'saved') emit('saved')
  } finally {
    if (own === sequence) busy.value = false
  }
}

watch(
  [
    () => props.game,
    () => auth.teamId,
    () => auth.authEpoch,
    () => auth.hasHydrated,
    () => auth.isAuthenticated,
  ],
  async () => {
    const input = { game: toRaw(props.game), identity: identity() }
    if (watchedInput !== null && sameOrdinaryWire(watchedInput, input)) return
    controller?.dispose()
    controller = null
    request?.abort()
    sequence++
    const own = sequence
    watchedInput = null
    status.value = 'blocked'
    resetSelection()
    targetD1.value = 0
    if (!identity().verified || !isLineupPrefixGame(input.game)) return
    watchedInput = structuredClone(input)
    game.value = structuredClone(input.game)
    if (!finite.value) return
    const current = new GameScreenPastCorrectionProductController(
      game.value.id,
      identity,
      writer,
    )
    controller = current
    const inspected = await current.inspectPending()
    if (own !== sequence || props.suspended) return
    status.value = inspected
    if (inspected === 'ready') await loadVocabulary(null)
  },
  { immediate: true, deep: true },
)
watch(
  () => props.suspended,
  async (suspended) => {
    if (suspended || !controller) return
    const own = sequence
    const inspected = await controller.inspectPending()
    if (own !== sequence || props.suspended) return
    status.value = inspected
    if (inspected === 'ready' && vocabulary.value.length === 0)
      await loadVocabulary(null)
  },
)
watch(targetD1, resetSelection)
watch([replacement, pitchType, point, viewpoint], () => {
  previewConfirmed.value = false
})
onScopeDispose(() => {
  sequence++
  request?.abort()
  controller?.dispose()
  controller = null
})
</script>

<template>
  <section
    aria-label="過去の投球を訂正"
    class="space-y-3 rounded-xl border p-4"
  >
    <h3 class="font-bold">過去の投球を訂正</h3>
    <p role="status" data-testid="p3-status">{{ message }}</p>
    <p v-if="!finite" role="alert">
      履歴の全件を確認できないため、この画面からは訂正できません。
    </p>
    <div class="grid gap-2 sm:grid-cols-2">
      <label
        ><input v-model="sameProfile" type="checkbox" />
        同じブラウザプロファイル</label
      >
      <label><input v-model="sameMode" type="checkbox" /> 同じ閲覧モード</label>
      <label><input v-model="sameBucket" type="checkbox" /> 同じ保存領域</label>
      <label
        ><input v-model="noLockdown" type="checkbox" />
        ロックダウンモードではない</label
      >
    </div>
    <template v-if="status === 'ready' && finite">
      <label class="block"
        >対象の投球
        <select
          v-model.number="targetD1"
          :disabled="!canInput"
          data-testid="p3-target"
        >
          <option :value="0">選択してください</option>
          <option v-for="item in targets" :key="item.d1" :value="item.d1">
            第{{ item.d1 }}球（{{ item.row.batting_result_key }}）
          </option>
        </select>
      </label>
      <button
        type="button"
        :disabled="!canInput || targetD1 < 1"
        data-testid="p3-inspect"
        @click="inspectTarget"
      >
        対象の現在版を照合
      </button>
      <template v-if="offer">
        <p>
          対象版 {{ offer.expected_version }}、元結果
          {{ offer.original_result_id }}
        </p>
        <label class="block"
          >訂正後の結果
          <select
            v-model="replacement"
            :disabled="!canInput"
            data-testid="p3-result"
          >
            <option value="">選択してください</option>
            <option value="batting-result.ball">ボール</option>
            <option value="batting-result.called-pitch">見逃し球</option>
          </select>
        </label>
        <label class="block"
          >球種
          <select
            v-model="pitchType"
            :disabled="!canInput || vocabularyFailed"
            data-testid="p3-pitch-type"
          >
            <option value="">選択してください</option>
            <option
              v-for="item in vocabulary"
              :key="item.key"
              :value="item.key"
            >
              {{ item.display_name }}
            </option>
          </select>
        </label>
        <button
          type="button"
          :disabled="!canInput || nextCursor === null"
          @click="loadVocabulary(nextCursor)"
        >
          次の球種
        </button>
        <button
          v-if="vocabularyFailed"
          type="button"
          :disabled="!canInput"
          @click="loadVocabulary(null)"
        >
          球種を再取得
        </button>
        <label class="block"
          >視点
          <select
            v-model="viewpoint"
            :disabled="!canInput"
            @change="point = null"
          >
            <option value="catcher">捕手視点</option>
            <option value="pitcher">投手後方視点</option>
          </select>
        </label>
        <div class="max-w-sm">
          <StrikeZone
            :point="point"
            plate-side=""
            :viewpoint="viewpoint"
            :disabled="!canInput"
            @tap="(x, y) => (point = { x, y })"
          />
        </div>
        <label class="block"
          ><input
            v-model="unrecordedDetailsConfirmed"
            type="checkbox"
            :disabled="!canInput"
          />
          球速・構え・打席左右は記録しないことを確認しました</label
        >
        <div class="rounded border p-2" data-testid="p3-preview">
          <p>
            入力差分: {{ offer.original_result_id }} →
            {{ replacement || '未選択' }}
          </p>
          <p>保存前の状態・成績の変化は、サーバーの単一計算で確定します。</p>
        </div>
        <label class="block"
          ><input
            v-model="previewConfirmed"
            type="checkbox"
            :disabled="
              !canInput ||
              !replacement ||
              !pitchType ||
              !point ||
              !unrecordedDetailsConfirmed
            "
          />
          対象と入力差分を確認しました</label
        >
        <button
          type="button"
          :disabled="!canSave"
          data-testid="p3-apply"
          @click="save"
        >
          この内容で訂正を保存
        </button>
      </template>
    </template>
    <button
      v-if="status === 'pending' || status === 'saved-awaiting-read'"
      type="button"
      :disabled="props.suspended || busy || !confirmed"
      data-testid="p3-retry"
      @click="retry"
    >
      同じD5・同じ本文で結果を確認
    </button>
  </section>
</template>
