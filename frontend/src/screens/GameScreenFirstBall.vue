<script setup lang="ts">
import { computed, onScopeDispose, ref, toRaw, watch } from 'vue'
import type { StartedGameRead } from '../api/startedGame'
import {
  readPitchTypeOptions,
  type PitchTypeOption,
} from '../api/pitchTypeOptions'
import StrikeZone from '../components/zone/StrikeZone.vue'
import { useAuthStore } from '../stores/authStore'
import {
  GameScreenFirstBallController,
  type FirstBallOperationResult,
} from './GameScreenFirstBallController'
const props = defineProps<{ game: StartedGameRead }>()
const emit = defineEmits<{ saved: [] }>()
const auth = useAuthStore()
const point = ref<{ x: number; y: number } | null>(null)
const viewpoint = ref<'catcher' | 'pitcher'>('catcher')
const selected = ref('')
const items = ref<readonly PitchTypeOption[]>([])
const cursor = ref<string | null>(null)
const history = ref<(string | null)[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const failed = ref(false)
const busy = ref(false)
const status = ref<FirstBallOperationResult>('blocked')
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

let controller: GameScreenFirstBallController | null = null
let generation = 0
let request: AbortController | null = null
const identity = () => ({
  tenantId: auth.teamId,
  epoch: auth.authEpoch,
  verified: auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null,
})
const message = computed(() => {
  if (status.value === 'recorded')
    return 'サーバーに初球が保存されています。2球目の入力は接続準備中です'
  if (busy.value) return '初球の保存結果を確認しています'
  if (status.value === 'saved')
    return '保存応答を受け取りました。サーバーの状態を再取得しています'
  if (status.value === 'pending')
    return '端末に初球の要求が残っています。同じ要求の結果を確認してください'
  if (status.value === 'blocked')
    return 'この端末の開始資格・保存領域を確認できないため確定できません'
  return '初球のボールを入力できます'
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
    status.value !== 'ready' ||
    props.game.read_kind !== 'initial' ||
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
        resultId: 'batting-result.ball',
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
    if (result === 'saved') emit('saved')
  } finally {
    if (controller === current) busy.value = false
  }
}
watch(
  () =>
    [
      props.game.id,
      props.game.current_d4,
      props.game.read_kind,
      auth.authEpoch,
      auth.teamId,
      auth.isAuthenticated,
      auth.hasHydrated,
    ] as const,
  async () => {
    controller?.dispose()
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
      // APIで閉DTO検証された値からVueの観測Proxyだけを外す。
      // controllerは独立した固定snapshotへcloneし、元のreactive値を保持しない。
      const current = new GameScreenFirstBallController(
        toRaw(props.game),
        identity,
        writer,
      )
      controller = current
      const result = await current.inspect()
      if (controller !== current) return
      status.value = result
      if (result === 'ready') await load(null)
    } catch {
      controller?.dispose()
      controller = null
      status.value = 'blocked'
    }
  },
  { immediate: true },
)
onScopeDispose(() => {
  generation++
  request?.abort()
  controller?.dispose()
  controller = null
})
</script>
<template>
  <section
    aria-label="初球のボールを記録"
    class="space-y-3 rounded-xl border p-4"
  >
    <h2 class="text-lg font-bold">初球のボールを記録</h2>
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
    <p>現在は初球のボールを記録できます。2球目・取消・訂正は接続準備中です。</p>
    <template v-if="status === 'ready' && props.game.read_kind === 'initial'">
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
          selected === '' ||
          point === null
        "
        @click="save"
      >
        ボールを確定・保存
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
      同じ初球の保存結果を確認
    </button>
  </section>
</template>
