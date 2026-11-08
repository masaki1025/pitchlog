<script setup lang="ts">
import { computed, onScopeDispose, ref, toRaw, watch } from 'vue'
import {
  isPlayRecordingContext,
  isLineupRecordingContext,
  type RecordingContext,
  type PlayScreenObservation,
  type RecordingScreenObservation,
} from './GameScreenOrdinaryPitchProvider'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  readPitchTypeOptions,
  type PitchTypeOption,
} from '../api/pitchTypeOptions'
import { captureLocalPitchPage } from '../lib/localRecordingPermissionPersistence'
import {
  isLocalRecordingSession,
  type LocalRecordingSession,
} from '../lib/localRecordingSession'
import GameScreenBattedHitObservation from './GameScreenBattedHitObservation.vue'
import GameScreenRunnerEventObservation from './GameScreenRunnerEventObservation.vue'
import type { RunnerObservationWire } from '../api/runnerEventWire'
import type { BattedHitResult } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1.d.ts'
import type { BattedOtherResult } from '../api/lineupPrefixWire'
type CandidateBattedResult =
  | BattedHitResult
  | 'batting-result.batted-out'
  | 'batting-result.double-play'
  | BattedOtherResult
import StrikeZone from '../components/zone/StrikeZone.vue'
import { useAuthStore } from '../stores/authStore'
import {
  GameScreenOrdinaryPitchController,
  type OrdinaryOperationResult,
  type LocalOrdinaryResult,
} from './GameScreenOrdinaryPitchController'
const props = defineProps<{
  context: RecordingContext
  localSession?: LocalRecordingSession | null
  suspended?: boolean
}>()
const emit = defineEmits<{ saved: [] }>()
const auth = useAuthStore()
const point = ref<{ x: number; y: number } | null>(null)
const viewpoint = ref<'catcher' | 'pitcher'>('catcher')
const selected = ref('')
const resultId = ref<PlayScreenObservation['resultId']>('batting-result.ball')
const nextBatterId = ref('')
const runnerMode = ref(false)
const runnerObservation = ref<RunnerObservationWire | null>(null)
const runnerNonpitch = computed(
  () =>
    runnerMode.value &&
    runnerObservation.value?.perPitch.pitchEventKind === 'non-pitch-event',
)
const hitResults: readonly string[] = [
  'batting-result.single',
  'batting-result.double',
  'batting-result.triple',
  'batting-result.home-run',
  'batting-result.batted-out',
  'batting-result.batted-reach',
  'batting-result.error',
  'batting-result.fielders-choice',
  'batting-result.sacrifice-bunt',
  'batting-result.sacrifice-bunt-error',
  'batting-result.sacrifice-fly',
  'batting-result.double-play',
]
const batted = computed(() => hitResults.includes(resultId.value))
const battedOutAvailable = computed(() =>
  isLineupRecordingContext(displayed.value),
)
const runnerBattedAvailable = computed(
  () =>
    isLineupRecordingContext(displayed.value) &&
    displayed.value.after.stateFields['state.runners'] !== 'empty',
)
const sacrificeBuntAvailable = computed(
  () =>
    runnerBattedAvailable.value &&
    displayed.value.after.stateFields['state.outs'] !== '2',
)
const sacrificeFlyAvailable = computed(
  () =>
    isLineupRecordingContext(displayed.value) &&
    ['third', 'first-third', 'second-third', 'first-second-third'].includes(
      displayed.value.after.stateFields['state.runners'],
    ) &&
    displayed.value.after.stateFields['state.outs'] !== '2',
)
const doublePlayAvailable = computed(
  () =>
    isLineupRecordingContext(displayed.value) &&
    displayed.value.after.stateFields['state.runners'] === 'first' &&
    displayed.value.after.stateFields['state.outs'] === '0',
)
/** 原典で成立した一三塁0-0だけを画面に提示する。遷移値は唯一核が決める。 */
const intentionalWalkAvailable = computed(() => {
  const c = displayed.value
  if (!isLineupRecordingContext(c) || localRequested.value) return false
  const state = c.after.stateFields
  return (
    state['state.runners'] === 'first-third' &&
    state['state.outs'] === '0' &&
    state['state.count.strikes'] === '0' &&
    state['state.count.balls'] === '0' &&
    !state['state.gameEnded']
  )
})
const battedHit = ref<PlayScreenObservation['battedHit']>(null)
const hitAvailable = computed(() => {
  if (!isLineupRecordingContext(displayed.value)) return false
  return (
    !displayed.value.after.stateFields['state.tiebreakActive'] &&
    !displayed.value.after.stateFields['state.gameEnded']
  )
})
const battedRunners = computed(() => {
  const runners = displayed.value.after.stateFields['state.runners']
  const source = isLineupRecordingContext(displayed.value)
    ? displayed.value.lineupSource.runners
    : []
  const result: Array<{
    base: '1' | '2' | '3'
    label: string
    runnerId?: string
  }> = []
  if (
    runners === 'first' ||
    runners === 'first-second' ||
    runners === 'first-third' ||
    runners === 'first-second-third'
  )
    result.push({
      base: '1',
      label: '一塁走者',
      runnerId: source.find((r) => r.base === '1')?.runnerId,
    })
  if (
    runners === 'second' ||
    runners === 'first-second' ||
    runners === 'second-third' ||
    runners === 'first-second-third'
  )
    result.push({
      base: '2',
      label: '二塁走者',
      runnerId: source.find((r) => r.base === '2')?.runnerId,
    })
  if (
    runners === 'third' ||
    runners === 'first-third' ||
    runners === 'second-third' ||
    runners === 'first-second-third'
  )
    result.push({
      base: '3',
      label: '三塁走者',
      runnerId: source.find((r) => r.base === '3')?.runnerId,
    })
  return result
})
const battedContextKey = computed(() => {
  const c = displayed.value
  return isLineupRecordingContext(c)
    ? c.game.id +
        ':' +
        c.prefixRef.checkpoint.id +
        ':' +
        c.prefixRef.checkpoint.revision +
        ':' +
        resultId.value
    : ''
})
const runnerPeople = computed(() => {
  const c = displayed.value
  return isLineupRecordingContext(c)
    ? c.lineupSource.runners.map((r) => ({
        base: r.base,
        runnerId: r.runnerId,
        responsiblePitcherId: r.responsiblePitcherId,
      }))
    : []
})

const fielders = computed(
  () =>
    displayed.value.game.roster.teams
      .find(
        (t) =>
          t.side ===
          (displayed.value.after.stateFields['state.half'] === 'top'
            ? 'home'
            : 'away'),
      )
      ?.participants.filter((p) => p.roles.some((r) => r.kind === 'fielding'))
      .map((p) => ({
        id: p.player.player_id,
        label:
          '守備位置 ' +
          p.roles
            .filter((r) => r.kind === 'fielding')
            .map((r) => r.position)
            .join('/') +
          ' の選手',
      })) ?? [],
)

const terminal = computed(
  () =>
    !isLineupRecordingContext(displayed.value) &&
    (resultId.value === 'batting-result.walk' ||
      resultId.value === 'batting-result.hit-by-pitch'),
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
watch([runnerMode, battedContextKey], () => {
  runnerObservation.value = null
  if (batted.value) runnerMode.value = false
})
watch([resultId, battedContextKey], () => {
  battedHit.value = null
})

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
const status = ref<OrdinaryOperationResult | LocalOrdinaryResult>('blocked')
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
function activeLocalSession(): LocalRecordingSession | null {
  if (props.localSession == null) return null
  const raw = toRaw(props.localSession)
  return isLocalRecordingSession(raw) && raw.current ? raw : null
}
const localRequested = computed(() => props.localSession != null)
const isLocalMode = computed(() => localRequested.value)
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
const localWriter = {
  resolvePreconditions: writer.resolvePreconditions,
  revalidateSingleWriter: () =>
    !props.suspended &&
    confirmed.value &&
    activeLocalSession()?.current === true,
}

let controller: GameScreenOrdinaryPitchController | null = null
let generation = 0
let request: AbortController | null = null
const baseIdentity = () =>
  localRequested.value
    ? (activeLocalSession()?.identity() ?? {
        tenantId: null,
        epoch: 0,
        verified: false,
      })
    : {
        tenantId: auth.teamId,
        epoch: auth.authEpoch,
        verified:
          auth.hasHydrated && auth.isAuthenticated && auth.teamId !== null,
      }
const identity = () =>
  props.suspended
    ? { ...baseIdentity(), tenantId: null, verified: false }
    : baseIdentity()
const message = computed(() => {
  if (props.suspended)
    return 'サーバーの最新記録を確認しています。入力と再送を一時停止します'
  if (retryEvidenceUnavailable.value)
    return '再送に必要な元要求の送信記録を確認できません。新しい要求に置き換えず、運用責任者に確認してください'
  if (busy.value)
    return isLocalMode.value
      ? '端末の未送信記録を確認しています'
      : '記録要求の保存・送信結果を確認しています'
  if (isLocalMode.value) {
    if (status.value === 'queued-local')
      return '投球を端末の未送信キューに記録しました。サーバー確認前の暫定状態です'
    if (status.value === 'pending')
      return '端末の未送信記録を復元しました。通信復帰後に同じ要求を順序どおり送信します'
    if (status.value === 'blocked')
      return '端末内記録の資格または保存原本を確認できません'
    return '端末内の未送信記録として投球できます'
  }
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
  if (props.suspended) return
  const own = ++generation
  request?.abort()
  request = new AbortController()
  loading.value = true
  failed.value = false
  items.value = []
  selected.value = ''
  const captured = identity()
  const local = activeLocalSession()
  try {
    const result = localRequested.value
      ? local?.page(page)
      : await readPitchTypeOptions(page, 25, request.signal)
    if (!result) throw new Error('保存済み球種ページがありません')
    if (
      props.suspended ||
      own !== generation ||
      !sameOrdinaryWire(captured, identity())
    )
      return
    if (!localRequested.value && isLineupRecordingContext(displayed.value)) {
      try {
        await captureLocalPitchPage(
          displayed.value.game.id,
          displayed.value.game.current_d4,
          page,
          result,
          captured.epoch,
        )
      } catch {
        // onlineの実ページは使用可能。端末内資格としては採用しない。
      }
    }
    if (
      props.suspended ||
      own !== generation ||
      !sameOrdinaryWire(captured, identity())
    )
      return
    items.value = result.items
    cursor.value = page
    nextCursor.value = result.next_cursor
  } catch {
    if (own === generation && !props.suspended) {
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
    props.suspended ||
    busy.value ||
    !canAppend.value ||
    !confirmed.value ||
    (localRequested.value && (!activeLocalSession() || batted.value)) ||
    (runnerMode.value && runnerObservation.value === null) ||
    (!runnerNonpitch.value && !point.value) ||
    (batted.value && (!hitAvailable.value || !battedHit.value)) ||
    (!runnerNonpitch.value &&
      !items.value.some((i) => i.key === selected.value))
  )
    return
  const current = controller
  busy.value = true
  try {
    let observation: RecordingScreenObservation
    if (runnerNonpitch.value && runnerObservation.value) {
      observation = {
        kind: 'non-pitch-event',
        runnerEvent: structuredClone(toRaw(runnerObservation.value)),
      }
    } else {
      if (!point.value) return
      observation = {
        resultId: resultId.value,
        runnerEvent: runnerMode.value
          ? structuredClone(toRaw(runnerObservation.value))
          : null,
        battedHit: batted.value
          ? structuredClone(toRaw(battedHit.value))
          : null,
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
      }
    }
    const tenantId = identity().tenantId
    if (!tenantId) return
    const vocabulary = {
      tenantId,
      pitchTypeKeys: items.value.map((i) => i.key),
    }
    const result = localRequested.value
      ? await current.localEnqueue(observation, vocabulary)
      : await current.submit(observation, vocabulary)
    if (controller !== current || props.suspended) return
    status.value = result
    displayed.value = current.context
    canAppend.value = localRequested.value
      ? current.canAppendLocal
      : current.canAppend
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    if (result === 'saved' || result === 'pending' || result === 'queued-local')
      point.value = null
    if (result === 'saved' && !localRequested.value) emit('saved')
  } finally {
    if (controller === current) busy.value = false
  }
}
async function saveIntentionalWalk() {
  if (
    !controller ||
    props.suspended ||
    busy.value ||
    !canAppend.value ||
    !confirmed.value ||
    !intentionalWalkAvailable.value
  )
    return
  const current = controller
  const tenantId = identity().tenantId
  if (!tenantId) return
  busy.value = true
  try {
    const result = await current.submit('intentional-walk', {
      tenantId,
      pitchTypeKeys: [],
    })
    if (controller !== current || props.suspended) return
    status.value = result
    displayed.value = current.context
    canAppend.value = current.canAppend
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    if (result === 'saved') emit('saved')
  } finally {
    if (controller === current) busy.value = false
  }
}
async function retry(): Promise<OrdinaryOperationResult | null> {
  if (
    localRequested.value ||
    props.suspended ||
    !controller ||
    busy.value ||
    !confirmed.value ||
    !identity().verified
  )
    return null
  const current = controller
  busy.value = true
  try {
    const result = await current.retry()
    if (controller !== current || props.suspended) return null
    status.value = result
    displayed.value = current.context
    canAppend.value = current.canAppend
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    if (result === 'saved' || result === 'pending') point.value = null
    if (result === 'saved') emit('saved')
    return result
  } finally {
    if (controller === current) busy.value = false
  }
}
watch(confirmed, async (ready) => {
  if (!ready || props.suspended || !controller || busy.value) return
  const current = controller
  if (localRequested.value) {
    if (!activeLocalSession()) return
    const result = await current.inspectLocal()
    if (controller !== current || props.suspended) return
    status.value = result
    displayed.value = current.context
    canAppend.value = current.canAppendLocal
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    if (result === 'ready' || result === 'pending') await load(null)
  } else if (status.value === 'pending' && identity().verified) {
    await retry()
  }
})
let watchedInput: {
  context: RecordingContext
  identity: ReturnType<typeof identity>
  hydrated: boolean
  local: boolean
} | null = null
let observedSuspended = false
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
      props.localSession,
      props.suspended,
    ] as const,
  async () => {
    const wasSuspended = observedSuspended
    observedSuspended = props.suspended === true
    const input = {
      context: toRaw(props.context),
      identity: baseIdentity(),
      hydrated: auth.hasHydrated,
      local: localRequested.value,
    }
    // 親の同値DTO再供給では送信中の所有者を失効させない。
    // anchor/世代/状態/位置を含む全値と認証scopeが変われば必ず失効する。
    if (watchedInput !== null && sameOrdinaryWire(watchedInput, input)) {
      if (props.suspended) {
        generation++
        request?.abort()
        loading.value = false
        return
      }
      if (wasSuspended && controller) {
        const current = controller
        const result = localRequested.value
          ? await current.inspectLocal()
          : await current.inspect()
        if (controller !== current || props.suspended) return
        status.value = result
        displayed.value = current.context
        canAppend.value = localRequested.value
          ? current.canAppendLocal
          : current.canAppend
        retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
        if (result === 'pending' && !localRequested.value && confirmed.value) {
          if ((await retry()) === 'saved' || controller !== current) return
        }
        if (
          items.value.length === 0 &&
          (result === 'ready' || result === 'pending')
        )
          await load(null)
      }
      return
    }
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
    if (localRequested.value) resultId.value = 'batting-result.ball'
    if (props.suspended) return
    if (localRequested.value ? !activeLocalSession() : !identity().verified)
      return
    try {
      watchedInput = structuredClone(input)
      // APIで閉DTO検証された値からVueの観測Proxyだけを外す。
      // controllerは独立した固定snapshotへcloneし、元のreactive値を保持しない。
      const current = new GameScreenOrdinaryPitchController(
        watchedInput.context,
        identity,
        localRequested.value ? localWriter : writer,
        localRequested.value ? activeLocalSession() : null,
      )
      controller = current
      // 最終チェック前のlocal inspectは開始しない。最後のチェックで一度だけ再評価する。
      if (localRequested.value && !confirmed.value) return
      const result = localRequested.value
        ? await current.inspectLocal()
        : await current.inspect()
      if (controller !== current || props.suspended) return
      status.value = result
      displayed.value = current.context
      canAppend.value = localRequested.value
        ? current.canAppendLocal
        : current.canAppend
      retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
      if (result === 'pending' && !localRequested.value && confirmed.value) {
        if ((await retry()) === 'saved' || controller !== current) return
      }
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
    <fieldset
      class="space-y-1 rounded border p-2"
      :disabled="busy || suspended"
    >
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
    <p v-if="isLocalMode" data-testid="ordinary-local-notice">
      通信断中は端末へ未送信の投球だけを記録します。安打の詳細観測はこの入口で確定できません。
    </p>
    <p>
      {{
        isLocalMode
          ? 'ボール・ストライク・ファウル、四球・死球、三振を端末の未送信記録として入力できます。'
          : isLineupRecordingContext(displayed)
            ? 'ボール・ストライク・ファウル、四球・死球、三振、単打・二塁打・三塁打・本塁打を記録できます。走者あり安打では走者ごとの到達塁を確認します。次の打者と攻守は保存された打順から引き継ぎます。'
            : 'ボール・見逃し・空振り・通常のファウル、無走者の四球・死球を記録できます。四球・死球では次の打者を確認してください。'
      }}
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
    <p
      v-if="isLineupRecordingContext(displayed)"
      data-testid="lineup-local-state"
    >
      {{ displayed.after.stateFields['state.inning'] }}回{{
        displayed.after.stateFields['state.half'] === 'top' ? '表' : '裏'
      }}・{{ displayed.after.stateFields['state.outs'] }}アウト・{{
        displayed.lineupSource.participants.battingOrder
      }}番
    </p>
    <template v-if="canAppend && !suspended">
      <label v-if="!runnerNonpitch" class="block"
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
            v-if="
              isPlayRecordingContext(displayed) ||
              isLineupRecordingContext(displayed)
            "
            value="batting-result.walk"
          >
            四球
          </option>
          <option
            v-if="
              isPlayRecordingContext(displayed) ||
              isLineupRecordingContext(displayed)
            "
            value="batting-result.hit-by-pitch"
          >
            死球
          </option>
          <option
            v-if="isLineupRecordingContext(displayed)"
            value="batting-result.called-strikeout"
          >
            見逃し三振
          </option>
          <option
            v-if="isLineupRecordingContext(displayed)"
            value="batting-result.swinging-strikeout"
          >
            空振り三振
          </option>
          <option
            v-if="isLineupRecordingContext(displayed)"
            value="batting-result.k3"
          >
            K3（スリーバント失敗）
          </option>
          <option
            v-if="
              isLineupRecordingContext(displayed) &&
              displayed.after.stateFields['state.outs'] === '1' &&
              displayed.after.stateFields['state.runners'] === 'first' &&
              displayed.after.stateFields['state.count.strikes'] === '2' &&
              displayed.after.stateFields['state.count.balls'] === '0'
            "
            value="batting-result.strikeout-double-play"
          >
            三振ゲッツー（一死一塁・一塁走者アウト）
          </option>
          <template v-if="hitAvailable && !isLocalMode">
            <option value="batting-result.single">単打</option>
            <option value="batting-result.double">二塁打</option>
            <option value="batting-result.triple">三塁打</option>
            <option value="batting-result.home-run">本塁打</option>
            <option v-if="battedOutAvailable" value="batting-result.batted-out">
              打球アウト
            </option>
            <option
              v-if="runnerBattedAvailable"
              value="batting-result.batted-reach"
            >
              打球による出塁
            </option>
            <option
              v-if="runnerBattedAvailable"
              value="batting-result.fielders-choice"
            >
              野手選択
            </option>
            <option value="batting-result.error">失策による出塁</option>
            <option
              v-if="sacrificeBuntAvailable"
              value="batting-result.sacrifice-bunt"
            >
              犠打
            </option>
            <option
              v-if="sacrificeBuntAvailable"
              value="batting-result.sacrifice-bunt-error"
            >
              犠打失策
            </option>
            <option
              v-if="sacrificeFlyAvailable"
              value="batting-result.sacrifice-fly"
            >
              犠飛
            </option>
            <option
              v-if="doublePlayAvailable"
              value="batting-result.double-play"
            >
              併殺打（一塁走者の封殺）
            </option>
          </template>
          <option value="batting-result.foul">
            ファウル（通常・非バント）
          </option>
        </select></label
      >
      <label v-if="isLineupRecordingContext(displayed) && !batted" class="block"
        ><input
          v-model="runnerMode"
          type="checkbox"
          data-testid="runner-operation-enable"
          :disabled="busy"
        />走者操作を記録する</label
      >
      <GameScreenRunnerEventObservation
        v-if="runnerMode && isLineupRecordingContext(displayed) && !batted"
        :runners="runnerPeople"
        :primary-result-id="resultId"
        :source-key="battedContextKey"
        :disabled="busy"
        @select-primary-result="(value) => (resultId = value)"
        @confirmed="(value) => (runnerObservation = value)"
      />
      <p
        v-if="runnerMode && runnerObservation"
        data-testid="runner-observation-ready"
      >
        走者の実結果を確認しました。確定・保存はこれからです。
      </p>
      <GameScreenBattedHitObservation
        v-if="
          batted &&
          hitAvailable &&
          !isLocalMode &&
          isLineupRecordingContext(displayed)
        "
        :context-key="battedContextKey"
        :result-id="resultId as CandidateBattedResult"
        :before-outs="displayed.after.stateFields['state.outs']"
        :batter-id="displayed.lineupSource.participants.batterId"
        :fielders="fielders"
        :runners="battedRunners"
        :disabled="busy"
        @change="(value) => (battedHit = value)"
      />
      <p v-else-if="batted" role="alert">
        この安打入力は試合継続中・タイブレークなしの状態だけに対応しています。
      </p>
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
        {{
          isLocalMode
            ? '保存済みの球種ページを確認できません。'
            : '球種を取得できません。再取得してください。'
        }}
      </p>
      <button
        v-if="failed"
        type="button"
        :disabled="loading"
        @click="load(cursor)"
      >
        {{ isLocalMode ? '保存済み球種を再確認' : '球種を再取得' }}
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
      <div
        v-if="!runnerNonpitch"
        class="max-w-sm"
        data-testid="first-ball-course"
      >
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
          (!runnerNonpitch && (loading || failed)) ||
          (terminal && nextBatterId === '') ||
          (batted && (!hitAvailable || battedHit == null)) ||
          (runnerMode && runnerObservation === null) ||
          (!runnerNonpitch && (selected === '' || point === null))
        "
        @click="save"
      >
        {{
          runnerNonpitch
            ? isLocalMode
              ? '走者操作を端末に記録'
              : '走者操作を確定・保存'
            : isLocalMode
              ? '投球を端末に記録'
              : '投球を確定・保存'
        }}
      </button>
      <button
        v-if="intentionalWalkAvailable"
        type="button"
        data-testid="nonpitch-intentional-walk"
        class="min-h-11 rounded border px-4 py-2"
        :disabled="busy || !confirmed"
        @click="saveIntentionalWalk"
      >
        申告敬遠を記録
      </button>
    </template>
    <button
      v-if="status === 'pending' && !isLocalMode && !suspended"
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
