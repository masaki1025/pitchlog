<script setup lang="ts">
import { computed, onScopeDispose, ref, toRaw, watch } from 'vue'
import {
  isPlayRecordingContext,
  type RecordingContext,
  type PlayScreenObservation,
} from './GameScreenOrdinaryPitchProvider'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  readPitchTypeOptions,
  type PitchTypeOption,
} from '../api/pitchTypeOptions'
import StrikeZone from '../components/zone/StrikeZone.vue'
import { useAuthStore } from '../stores/authStore'
import {
  GameScreenOrdinaryPitchController,
  type OrdinaryOperationResult,
} from './GameScreenOrdinaryPitchController'
const props = defineProps<{ context: RecordingContext }>()
const emit = defineEmits<{ saved: [] }>()
const auth = useAuthStore()
const point = ref<{ x: number; y: number } | null>(null)
const viewpoint = ref<'catcher' | 'pitcher'>('catcher')
const selected = ref('')
const resultId = ref<PlayScreenObservation['resultId']>('batting-result.ball')
const nextBatterId = ref('')
const terminal = computed(
  () =>
    resultId.value === 'batting-result.walk' ||
    resultId.value === 'batting-result.hit-by-pitch',
)
const nextBatters = computed(() => {
  const c = displayed.value,
    side = c.after.stateFields['state.half'] === 'top' ? 'away' : 'home'
  return (
    c.game.roster.teams
      .find((t) => t.side === side)
      ?.participants.filter((p) => p.batting_slot.kind === 'slot') ?? []
  )
})
const canAppend = ref(false)
const retryEvidenceUnavailable = ref(false)
const displayed = ref<RecordingContext>(structuredClone(toRaw(props.context)))
watch(
  [resultId, () => displayed.value.after.stateFields['state.battingOrder']],
  () => {
    nextBatterId.value = ''
  },
)
const items = ref<readonly PitchTypeOption[]>([])
const cursor = ref<string | null>(null)
const history = ref<(string | null)[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const failed = ref(false)
const busy = ref(false)
const status = ref<OrdinaryOperationResult>('blocked')
const sameProfile = ref(false),
  sameMode = ref(false),
  sameBucket = ref(false),
  noLockdown = ref(false)
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
const writer = {
  resolvePreconditions: () => ({
    topLevelHttps: httpsTopLevel(),
    sameBrowserProfile: sameProfile.value,
    sameBrowsingMode: sameMode.value,
    sameStorageBucket: sameBucket.value,
    siteStorageAvailable: typeof indexedDB !== 'undefined',
    lockdownModeNotApplied: noLockdown.value,
  }),
  revalidateSingleWriter: () => confirmed.value && identity().verified,
}

let controller: GameScreenOrdinaryPitchController | null = null
let generation = 0
let request: AbortController | null = null
const identity = () => ({
  tenantId: auth.teamId,
  epoch: auth.authEpoch,
  verified: auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null,
})
const message = computed(() => {
  if (retryEvidenceUnavailable.value)
    return '再送に必要な元要求の送信記録を確認できません。新しい要求に置き換えず、運用責任者に確認してください'
  if (busy.value) return '記録要求の保存・送信結果を確認しています'
  if (status.value === 'saved')
    return '保存応答を受け取りました。サーバーから再取得しています'
  if (status.value === 'pending')
    return canAppend.value
      ? '未確認の要求が端末に残っています。同じ要求を順序どおり再送します。端末の次の独立操作は記録できます'
      : '未確認の要求が端末に残っています。同じ要求を再送した後、サーバーから再取得してください'
  if (status.value === 'blocked')
    return 'この入力を確定できません。結果・打者と最新の記録を確認してください'
  return '投球を記録できます'
})
async function load(page: string | null) {
  const own = ++generation
  request?.abort()
  request = new AbortController()
  loading.value = true
  failed.value = false
  items.value = []
  selected.value = ''
  const captured = identity()
  try {
    const result = await readPitchTypeOptions(page, 25, request.signal)
    if (
      own !== generation ||
      captured.tenantId !== auth.teamId ||
      captured.epoch !== auth.authEpoch
    )
      return
    items.value = result.items
    cursor.value = page
    nextCursor.value = result.next_cursor
  } catch {
    if (own === generation) {
      failed.value = true
      nextCursor.value = null
    }
  } finally {
    if (own === generation) loading.value = false
  }
}
async function next() {
  if (nextCursor.value !== null) {
    history.value.push(cursor.value)
    await load(nextCursor.value)
  }
}
async function previous() {
  if (history.value.length > 0) await load(history.value.pop() ?? null)
}
async function save() {
  if (
    !controller ||
    busy.value ||
    !canAppend.value ||
    !confirmed.value ||
    !point.value ||
    !items.value.some((i) => i.key === selected.value)
  )
    return
  const current = controller
  busy.value = true
  try {
    const result = await current.submit(
      {
        resultId: resultId.value,
        nextBatter: terminal.value
          ? (() => {
              const p = nextBatters.value.find(
                (p) => p.player.player_id === nextBatterId.value,
              )
              return p?.batting_slot.kind === 'slot'
                ? {
                    batterId: p.player.player_id,
                    battingOrder: p.batting_slot.slot,
                  }
                : null
            })()
          : null,
        pitchTypeKey: selected.value,
        screenX: point.value.x,
        screenY: point.value.y,
        view: viewpoint.value,
        pitchSpeed: { kmh: null, outsideRangeConfirmed: false },
        stance: null,
        battingSide: null,
      },
      { tenantId: auth.teamId!, pitchTypeKeys: items.value.map((i) => i.key) },
    )
    if (controller !== current) return
    status.value = result
    displayed.value = current.context
    canAppend.value = current.canAppend
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    if (result === 'saved' || result === 'pending') point.value = null
    if (result === 'saved') emit('saved')
  } finally {
    if (controller === current) busy.value = false
  }
}
async function retry() {
  if (!controller || busy.value || !confirmed.value) return
  const current = controller
  busy.value = true
  try {
    const result = await current.retry()
    if (controller !== current) return
    status.value = result
    displayed.value = current.context
    canAppend.value = current.canAppend
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    if (result === 'saved' || result === 'pending') point.value = null
    if (result === 'saved') emit('saved')
  } finally {
    if (controller === current) busy.value = false
  }
}
let watchedInput: {
  context: RecordingContext
  identity: ReturnType<typeof identity>
  hydrated: boolean
} | null = null
watch(
  () =>
    [
      props.context,
      props.context.game.id,
      props.context.game.current_d4,
      props.context.prefixRef.length,
      props.context.nextPosition.d1,
      auth.authEpoch,
      auth.teamId,
      auth.isAuthenticated,
      auth.hasHydrated,
    ] as const,
  async () => {
    const input = {
      context: toRaw(props.context),
      identity: identity(),
      hydrated: auth.hasHydrated,
    }
    // 親の同値DTO再供給では送信中の所有者を失効させない。
    // anchor/世代/状態/位置を含む全値と認証scopeが変われば必ず失効する。
    if (watchedInput !== null && sameOrdinaryWire(watchedInput, input)) return
    controller?.dispose()
    controller = null
    watchedInput = null
    generation++
    request?.abort()
    items.value = []
    point.value = null
    selected.value = ''
    history.value = []
    nextCursor.value = null
    busy.value = false
    status.value = 'blocked'
    if (!identity().verified) return
    try {
      watchedInput = structuredClone(input)
      // APIで閉DTO検証された値からVueの観測Proxyだけを外す。
      // controllerは独立した固定snapshotへcloneし、元のreactive値を保持しない。
      const current = new GameScreenOrdinaryPitchController(
        watchedInput.context,
        identity,
        writer,
      )
      controller = current
      const result = await current.inspect()
      if (controller !== current) return
      status.value = result
      displayed.value = current.context
      canAppend.value = current.canAppend
      retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
      if (
        items.value.length === 0 &&
        (result === 'ready' || result === 'pending')
      )
        await load(null)
    } catch {
      controller?.dispose()
      controller = null
      status.value = 'blocked'
    }
  },
  { immediate: true, deep: true },
)
onScopeDispose(() => {
  generation++
  request?.abort()
  controller?.dispose()
  controller = null
})
</script>
<template>
  <section aria-label="通常投球を記録" class="space-y-3 rounded-xl border p-4">
    <h2 class="text-lg font-bold">通常投球を記録</h2>
    <fieldset class="space-y-1 rounded border p-2" :disabled="busy">
      <legend>この記録端末の利用条件</legend>
      <label class="block"
        ><input
          v-model="sameProfile"
          type="checkbox"
          data-testid="first-ball-env-profile"
        />ほかの記録タブと同じブラウザプロファイルを使います</label
      >
      <label class="block"
        ><input
          v-model="sameMode"
          type="checkbox"
          data-testid="first-ball-env-mode"
        />通常・プライベートなどの閲覧モードを統一します</label
      >
      <label class="block"
        ><input
          v-model="sameBucket"
          type="checkbox"
          data-testid="first-ball-env-bucket"
        />同じサイトの保存領域を使うタブだけで記録します</label
      >
      <label class="block"
        ><input
          v-model="noLockdown"
          type="checkbox"
          data-testid="first-ball-env-lockdown"
        />この端末でLockdownモードを適用していません</label
      >
    </fieldset>
    <p v-if="!httpsTopLevel()" role="alert">
      記録にはHTTPSで直接開いた画面が必要です。
    </p>
    <p role="status" data-testid="first-ball-status">{{ message }}</p>
    <p>
      ボール・見逃し・空振り・通常のファウル、無走者の四球・死球を記録できます。四球・死球では次の打者を確認してください。
    </p>
    <p data-testid="ordinary-state-source">
      {{
        displayed.source === 'local-provisional'
          ? '端末の未確認分を含む暫定状態'
          : 'サーバー確認済みの状態'
      }}
    </p>
    <p>
      暫定カウント:
      <span data-testid="ordinary-local-balls">{{
        displayed.after.stateFields['state.count.balls']
      }}</span
      >ボール・<span data-testid="ordinary-local-strikes">{{
        displayed.after.stateFields['state.count.strikes']
      }}</span
      >ストライク
    </p>
    <template v-if="canAppend">
      <label class="block"
        >結果<select
          v-model="resultId"
          data-testid="ordinary-pitch-result"
          :disabled="busy"
        >
          <option value="batting-result.ball">ボール</option>
          <option value="batting-result.called-pitch">見逃しストライク</option>
          <option value="batting-result.swinging-strike">
            空振りストライク
          </option>
          <option
            v-if="isPlayRecordingContext(displayed)"
            value="batting-result.walk"
          >
            四球
          </option>
          <option
            v-if="isPlayRecordingContext(displayed)"
            value="batting-result.hit-by-pitch"
          >
            死球
          </option>
          <option value="batting-result.foul">
            ファウル（通常・非バント）
          </option>
        </select></label
      >
      <label v-if="terminal" class="block"
        >次の打者を確認
        <select
          v-model="nextBatterId"
          data-testid="terminal-next-batter"
          :disabled="busy"
        >
          <option value="">次の打者を選択</option>
          <option
            v-for="p in nextBatters"
            :key="p.player.player_id"
            :value="p.player.player_id"
          >
            {{
              p.batting_slot.kind === 'slot' ? p.batting_slot.slot : ''
            }}番の打者
          </option>
        </select>
      </label>
      <label class="block"
        >球種
        <select
          v-model="selected"
          data-testid="first-ball-pitch-type"
          :disabled="busy || loading || failed"
          class="min-h-11 rounded border p-2"
        >
          <option value="">球種を選択</option>
          <option v-for="item in items" :key="item.key" :value="item.key">
            {{ item.display_name }}
          </option>
        </select>
      </label>
      <p v-if="failed" role="alert">
        球種を取得できません。再取得してください。
      </p>
      <button
        v-if="failed"
        type="button"
        :disabled="loading"
        @click="load(cursor)"
      >
        球種を再取得
      </button>
      <button
        type="button"
        :disabled="loading || busy || history.length === 0"
        @click="previous"
      >
        前の球種
      </button>
      <button
        type="button"
        :disabled="loading || busy || nextCursor === null"
        @click="next"
      >
        次の球種
      </button>
      <label class="block"
        >視点<select
          v-model="viewpoint"
          :disabled="busy"
          @change="point = null"
        >
          <option value="catcher">捕手視点</option>
          <option value="pitcher">投手後方視点</option>
        </select></label
      >
      <div class="max-w-sm" data-testid="first-ball-course">
        <StrikeZone
          :point="point"
          plate-side=""
          :viewpoint="viewpoint"
          :disabled="busy"
          @tap="(x, y) => (point = { x, y })"
        />
      </div>
      <p>打席側・球速・構えは未入力として保存します。</p>
      <button
        type="button"
        data-testid="first-ball-save"
        class="min-h-11 rounded border px-4 py-2"
        :disabled="
          busy ||
          !confirmed ||
          loading ||
          failed ||
          (terminal && nextBatterId === '') ||
          selected === '' ||
          point === null
        "
        @click="save"
      >
        投球を確定・保存
      </button>
    </template>
    <button
      v-if="status === 'pending'"
      type="button"
      :disabled="busy || !confirmed"
      class="min-h-11 rounded border px-4 py-2"
      data-testid="first-ball-retry"
      @click="retry"
    >
      先頭の未確認要求を同じ内容で再送
    </button>
  </section>
</template>
