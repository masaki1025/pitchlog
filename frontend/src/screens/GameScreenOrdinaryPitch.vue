<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, toRaw, watch } from 'vue'
import { useRouter } from 'vue-router'
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
import GameScreenInterferenceObservation from './GameScreenInterferenceObservation.vue'
import GameScreenRunnerEventObservation from './GameScreenRunnerEventObservation.vue'
import type { RunnerObservationWire } from '../api/runnerEventWire'
import StrikeZone from '../components/zone/StrikeZone.vue'
import StanceGrid from '../components/zone/StanceGrid.vue'
import SpeedPad from '../components/pads/SpeedPad.vue'
import LegacyResultPad from '../components/pads/LegacyResultPad.vue'
import RunnerDiamond from '../components/diamond/RunnerDiamond.vue'
import CountDisplay from '../components/scoreboard/CountDisplay.vue'
import RecordBottomBar from '../components/game/RecordBottomBar.vue'
import Sheet from '../components/ui/Sheet.vue'
import GameScreenUndoProduct from './GameScreenUndoProduct.vue'
import GameScreenPastCorrectionProduct from './GameScreenPastCorrectionProduct.vue'
import GameScreenLifecycleProduct from './GameScreenLifecycleProduct.vue'
import { useRecordDisplay } from './GameScreenRecordDisplayProvider'
import { ordinaryPitchLockReason } from './ordinaryPitchLock'
import { useAuthStore } from '../stores/authStore'
import {
  GameScreenOrdinaryPitchController,
  type AttemptInspection,
  type OrdinaryOperationResult,
  type LocalOrdinaryResult,
} from './GameScreenOrdinaryPitchController'
const props = defineProps<{
  context: RecordingContext
  localSession?: LocalRecordingSession | null
  suspended?: boolean
  gameRead?: import('../api/lineupPrefixGame').LineupPrefixGame | null
}>()
const emit = defineEmits<{ saved: []; reload: [] }>()
const auth = useAuthStore()
const router = useRouter()
const stance = ref(0)
const speed = ref('')
const lastSpeed = ref('')
const battingSideOverride = ref<'右' | '左' | null>(null)
const activeSheet = ref<
  | null
  | 'safety'
  | 'undo'
  | 'past-correction'
  | 'menu'
  | 'lifecycle'
  | 'sync'
  | 'runner'
  | 'next-batter'
>(null)
const leftOpen = ref(false)
const resultPanel = ref<'inplay' | 'strikeout' | 'walk' | null>(null)
const resultPicked = ref(false)
const pendingNextBatter = ref<string | null>(null)
const missingCourse = ref(false)
const missingPitchType = ref(false)
const runnerNotice = ref('')
const pendingSecondary = ref<string | null>(null)
const pendingSecondaryLabel = computed(() => {
  if (pendingSecondary.value === 'secondary-result.passed-ball') return 'PB'
  if (pendingSecondary.value === 'secondary-result.wild-pitch') return 'WP'
  if (pendingSecondary.value === 'secondary-result.balk') return 'ボーク'
  if (pendingSecondary.value === 'secondary-result.pitch-clock-violation')
    return '時計違反'
  return ''
})
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
const interference = computed(() =>
  [
    'secondary-result.batting-interference',
    'secondary-result.obstruction',
    'secondary-result.offensive-interference',
  ].includes(resultId.value),
)
const battedHit = ref<PlayScreenObservation['battedHit']>(null)
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
const adoptInterference = ref(false)
const interferenceObservation = ref<PlayScreenObservation['interference']>(null)
const strikeoutDetailAvailable = computed(() =>
  isLineupRecordingContext(displayed.value),
)
const hitAvailable = computed(() => {
  if (!isLineupRecordingContext(displayed.value)) return false
  return !displayed.value.after.stateFields['state.gameEnded']
})
const runnersState = computed(
  () => displayed.value.after.stateFields['state.runners'],
)
const outsState = computed(
  () => displayed.value.after.stateFields['state.outs'],
)
const runnerBattedAvailable = computed(
  () =>
    isLineupRecordingContext(displayed.value) && runnersState.value !== 'empty',
)
const sacrificeBuntAvailable = computed(
  () => hitAvailable.value && outsState.value !== '2',
)
const sacrificeFlyAvailable = computed(
  () =>
    isLineupRecordingContext(displayed.value) &&
    ['third', 'first-third', 'second-third', 'first-second-third'].includes(
      runnersState.value,
    ) &&
    outsState.value !== '2' &&
    hitAvailable.value,
)
const doublePlayAvailable = computed(
  () =>
    isLineupRecordingContext(displayed.value) &&
    runnersState.value === 'first' &&
    outsState.value === '0' &&
    hitAvailable.value,
)
const strikeoutDoublePlayAvailable = computed(
  () =>
    isLineupRecordingContext(displayed.value) &&
    runnersState.value === 'first' &&
    outsState.value === '0' &&
    displayed.value.after.stateFields['state.count.strikes'] === '2' &&
    displayed.value.after.stateFields['state.count.balls'] === '0',
)
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
const interferenceRunners = computed(() =>
  battedRunners.value.every((runner) => typeof runner.runnerId === 'string')
    ? battedRunners.value.map((runner) => ({
        base: runner.base,
        label: runner.label,
        runnerId: runner.runnerId!,
      }))
    : null,
)
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
const runnerSourceKey = computed(
  () => game.value.id + ':' + displayed.value.nextPosition.d1,
)
const runnerPeople = computed(() => {
  const c = displayed.value
  if (isLineupRecordingContext(c))
    return c.lineupSource.runners.map((r) => ({
      base: r.base,
      runnerId: r.runnerId,
      responsiblePitcherId: r.responsiblePitcherId,
    }))
  if (isPlayRecordingContext(c))
    return c.playSource.runners.map((r) => ({
      base: r.base,
      runnerId: r.runnerId,
      responsiblePitcherId: r.responsiblePitcherId,
    }))
  return []
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
      .map((p) => {
        const positions = p.roles
          .filter((r) => r.kind === 'fielding')
          .map((r) => r.position)
          .join('/')
        return {
          id: p.player.player_id,
          label: `${positions} ${display.playerName(
            p.player.player_id,
            'の選手',
          )}`,
        }
      }) ?? [],
)

const terminal = computed(
  () =>
    resultId.value === 'batting-result.walk' ||
    resultId.value === 'batting-result.hit-by-pitch',
)
const nextBatters = computed(() => {
  const c = displayed.value,
    side = c.after.stateFields['state.half'] === 'top' ? 'away' : 'home'
  // 四球・死球の次打者は現打順の直後枠だけ。全打順からの自由選択にしない。
  const current = Number(c.after.stateFields['state.battingOrder'])
  if (!Number.isInteger(current) || current < 1 || current > 9) return []
  const next = current === 9 ? 1 : current + 1
  return (
    c.game.roster.teams
      .find((t) => t.side === side)
      ?.participants.filter(
        (p) =>
          p.batting_slot.kind === 'slot' &&
          Number(p.batting_slot.slot) === next,
      ) ?? []
  )
})
const tiebreakFirst = ref('')
const tiebreakSecond = ref('')
const tiebreakRule = computed(() => displayed.value.rules.tiebreak)
const tiebreakInning = computed(() => Number(inning.value))
const tiebreakCandidates = computed(() => {
  const c = displayed.value
  const side = c.after.stateFields['state.half'] === 'top' ? 'away' : 'home'
  const currentBatter = participants.value.batterId
  return c.game.lineups[side].entries
    .filter(
      (entry) =>
        entry.batting_order !== null && entry.player_id !== currentBatter,
    )
    .map((entry) => ({
      id: entry.player_id,
      label: `${display.playerName(entry.player_id, '選手')}（${entry.batting_order}番）`,
    }))
})
const tiebreakReady = computed(() => {
  const rule = tiebreakRule.value
  if (
    rule === null ||
    (rule.runnerPlacement !== 'no_out_first_second' &&
      rule.runnerPlacement !== 'first-second') ||
    rule.leadoffRule !== 'continue_lineup' ||
    Number(rule.startInning) > tiebreakInning.value ||
    stateFields.value['state.runners'] !== 'empty' ||
    Number(stateFields.value['state.outs']) !== 0 ||
    Number(stateFields.value['state.count.strikes']) !== 0 ||
    Number(stateFields.value['state.count.balls']) !== 0
  )
    return false
  const ids = new Set(tiebreakCandidates.value.map((item) => item.id))
  return (
    tiebreakFirst.value !== '' &&
    tiebreakSecond.value !== '' &&
    tiebreakFirst.value !== tiebreakSecond.value &&
    ids.has(tiebreakFirst.value) &&
    ids.has(tiebreakSecond.value)
  )
})
const canAppend = ref(false)
const retryEvidenceUnavailable = ref(false)
const displayed = ref<RecordingContext>(structuredClone(toRaw(props.context)))
const display = useRecordDisplay(computed(() => displayed.value.game))
const game = computed(() => displayed.value.game)
const stateFields = computed(() => displayed.value.after.stateFields)
const inning = computed(() => stateFields.value['state.inning'])
const half = computed(() => stateFields.value['state.half'])
const halfLabel = computed(() => (half.value === 'top' ? '表' : '裏'))
const outs = computed(() => Number(stateFields.value['state.outs']))
const balls = computed(() => Number(stateFields.value['state.count.balls']))
const strikes = computed(() => Number(stateFields.value['state.count.strikes']))
const battingOrder = computed(() =>
  Number(stateFields.value['state.battingOrder']),
)
const score = computed(() => stateFields.value['state.score'])
const awayTeamName = computed(() =>
  display.teamName(game.value.away_team_record_id, 'ビジター'),
)
const homeTeamName = computed(() =>
  display.teamName(game.value.home_team_record_id, 'ホーム'),
)
function derivedParticipants(c: RecordingContext): {
  batterId: string
  pitcherId: string
  catcherId: string
  battingOrder: string
} {
  if (isLineupRecordingContext(c)) return { ...c.lineupSource.participants }
  if (isPlayRecordingContext(c)) {
    const defend = c.after.stateFields['state.half'] === 'top' ? 'home' : 'away'
    const catching = c.game.lineups[defend].entries.find(
      (entry) =>
        entry.fielding_position.kind === 'fielding' &&
        entry.fielding_position.position === '2',
    )
    return {
      ...c.playSource.participants,
      catcherId: catching?.player_id ?? '',
    }
  }
  const order = c.after.stateFields['state.battingOrder']
  const attack = c.after.stateFields['state.half'] === 'top' ? 'away' : 'home'
  const defend = attack === 'away' ? 'home' : 'away'
  const batter = c.game.lineups[attack].entries.find(
    (entry) => entry.batting_order === order,
  )
  const fielding = c.game.lineups[defend].entries.find(
    (entry) =>
      entry.fielding_position.kind === 'fielding' &&
      entry.fielding_position.position === '1',
  )
  const catching = c.game.lineups[defend].entries.find(
    (entry) =>
      entry.fielding_position.kind === 'fielding' &&
      entry.fielding_position.position === '2',
  )
  return {
    batterId: batter?.player_id ?? '',
    pitcherId: fielding?.player_id ?? '',
    catcherId: catching?.player_id ?? '',
    battingOrder: order,
  }
}
const participants = computed(() => derivedParticipants(displayed.value))
const batterId = computed(() => participants.value.batterId)
const pitcherId = computed(() => participants.value.pitcherId)
const catcherId = computed(() => participants.value.catcherId)
const batterName = computed(() =>
  display.playerName(batterId.value, `${battingOrder.value}番の打者`),
)
const batterNumber = computed(() => display.playerNumber(batterId.value))
const pitcherName = computed(() => display.playerName(pitcherId.value, '投手'))
const pitcherNumber = computed(() => display.playerNumber(pitcherId.value))
const catcherName = computed(() => display.playerName(catcherId.value, '捕手'))
const batterProfile = computed(() =>
  batterId.value ? display.player(batterId.value) : null,
)
const battingSide = computed<'右' | '左'>(() => {
  if (battingSideOverride.value !== null) return battingSideOverride.value
  const bats = batterProfile.value?.bats
  if (bats === 'left') return '左'
  return '右'
})
const canToggleBattingSide = computed(
  () => batterProfile.value?.bats === 'both',
)
function toggleBattingSide() {
  battingSideOverride.value = battingSide.value === '右' ? '左' : '右'
}
function occupied(base: 'first' | 'second' | 'third'): boolean {
  const value = stateFields.value['state.runners']
  if (value === 'empty') return false
  const map: Record<string, readonly string[]> = {
    first: ['first', 'first-second', 'first-third', 'loaded'],
    second: ['second', 'first-second', 'second-third', 'loaded'],
    third: ['third', 'first-third', 'second-third', 'loaded'],
  }
  return map[base].includes(value)
}
function runnerView(base: 'first' | 'second' | 'third') {
  if (!occupied(base)) return null
  const slot = base === 'first' ? '1' : base === 'second' ? '2' : '3'
  const person = runnerPeople.value.find((runner) => runner.base === slot)
  if (!person) return { name: '走者' }
  return { name: display.playerName(person.runnerId, '走者') }
}
const runnerFirst = computed(() => runnerView('first'))
const runnerSecond = computed(() => runnerView('second'))
const runnerThird = computed(() => runnerView('third'))
const hasRunners = computed(
  () =>
    runnerFirst.value !== null ||
    runnerSecond.value !== null ||
    runnerThird.value !== null,
)
const runnerChips = computed(() => [
  { base: '1塁', runner: runnerFirst.value },
  { base: '2塁', runner: runnerSecond.value },
  { base: '3塁', runner: runnerThird.value },
])
const nextBatterName = computed(() => {
  const candidate = nextBatters.value[0]
  return candidate
    ? display.playerName(
        candidate.player.player_id,
        `${candidate.batting_slot.kind === 'slot' ? candidate.batting_slot.slot : ''}番の打者`,
      )
    : '—'
})
const highlightedResult = computed(() =>
  resultPicked.value ? resultId.value : null,
)
const pitchTypeCodes: readonly { pattern: RegExp; code: string }[] = [
  { pattern: /直球|ストレート/, code: 'FB' },
  { pattern: /カーブ/, code: 'CB' },
  { pattern: /スライダー/, code: 'SL' },
  { pattern: /カット/, code: 'CT' },
  { pattern: /シュート/, code: 'ST' },
  { pattern: /ツーシーム/, code: '2S' },
  { pattern: /チェンジ/, code: 'CH' },
  { pattern: /フォーク/, code: 'SP' },
  { pattern: /シンカー/, code: 'SK' },
  { pattern: /特殊|その他/, code: 'OT' },
]
function pitchTypeChipLabel(item: PitchTypeOption): string {
  return (
    pitchTypeCodes.find((entry) => entry.pattern.test(item.display_name))
      ?.code ?? item.display_name
  )
}
const currentPitchTypeLabel = computed(
  () =>
    items.value.find((item) => item.key === selected.value)?.display_name ??
    '未',
)
const courseEntered = computed(() => point.value !== null)
function selectPitchType(key: string) {
  selected.value = key
  missingPitchType.value = false
}
function selectStance(zone: number) {
  stance.value = zone
}
function changeSpeed(value: string) {
  speed.value = value
}
async function openSafety() {
  activeSheet.value = 'safety'
}
function openUndo() {
  if (!canAppend.value) return
  activeSheet.value = 'undo'
}
async function openSubstitution() {
  if (!canAppend.value) return
  await router.push({
    name: 'game-lineup',
    params: { gameId: game.value.id },
  })
}
async function openViewer() {
  await router.push({ name: 'game-viewer', params: { gameId: game.value.id } })
}
async function openStats() {
  await router.push({ name: 'game-stats', params: { gameId: game.value.id } })
}
async function openExport() {
  await router.push({ name: 'game-export', params: { gameId: game.value.id } })
}
function openMenu() {
  activeSheet.value = 'menu'
}
function openRunner() {
  if (!hasRunners.value) return
  runnerNotice.value = ''
  activeSheet.value = 'runner'
}
function openSecondary(resultId: string) {
  if (!isLineupRecordingContext(displayed.value)) return
  pendingSecondary.value = resultId
  runnerNotice.value = ''
  activeSheet.value = 'runner'
}
function clearSecondary() {
  pendingSecondary.value = null
  runnerMode.value = false
  runnerObservation.value = null
}
function openBalk(resultId: string) {
  if (!isLineupRecordingContext(displayed.value)) return
  pendingSecondary.value = resultId
  runnerNotice.value = ''
  activeSheet.value = 'runner'
}
function selectInterference(value: string) {
  if (!isLineupRecordingContext(displayed.value) || !hitAvailable.value) return
  resultPicked.value = true
  resultId.value = value as PlayScreenObservation['resultId']
  battedHit.value = null
  interferenceObservation.value = null
  resultPanel.value = null
}
async function runnerConfirmed(value: RunnerObservationWire) {
  if (value.perPitch.pitchEventKind !== 'non-pitch-event') {
    if (
      pendingSecondary.value !== 'secondary-result.passed-ball' &&
      pendingSecondary.value !== 'secondary-result.wild-pitch'
    ) {
      runnerNotice.value =
        '投球を伴う盗塁は、通常投球の結果と合わせて記録します。ここでは暴投・捕逸・牽制・ボークを選んでください。'
      return
    }
  }
  runnerMode.value = true
  runnerObservation.value = value
  activeSheet.value = null
  if (value.perPitch.pitchEventKind === 'non-pitch-event') {
    await nextTick()
    await save()
  }
}
async function undoDone() {
  activeSheet.value = null
  emit('saved')
}
async function pastCorrectionSaved() {
  activeSheet.value = null
  emit('saved')
}
async function lifecycleResumed() {
  activeSheet.value = null
  emit('saved')
}
function chooseDirect(
  result:
    | 'batting-result.called-strikeout'
    | 'batting-result.swinging-strikeout'
    | 'batting-result.k3'
    | 'batting-result.strikeout-double-play'
    | 'batting-result.walk'
    | 'batting-result.hit-by-pitch',
) {
  if (!ensureConfirmed()) return
  if (
    (result === 'batting-result.called-strikeout' ||
      result === 'batting-result.swinging-strikeout' ||
      result === 'batting-result.k3' ||
      result === 'batting-result.strikeout-double-play') &&
    (strikes.value < 2 || !strikeoutDetailAvailable.value)
  )
    return
  resultPicked.value = true
  resultId.value = result
  if (
    result === 'batting-result.walk' ||
    result === 'batting-result.hit-by-pitch'
  ) {
    pendingNextBatter.value = result
    nextBatterId.value = ''
    activeSheet.value = 'next-batter'
    return
  }
  void nextTick().then(() => save())
}
function ensureConfirmed(): boolean {
  if (!confirmed.value) {
    activeSheet.value = 'safety'
    return false
  }
  return true
}
function selectSimple(
  result:
    | 'batting-result.called-pitch'
    | 'batting-result.swinging-strike'
    | 'batting-result.foul'
    | 'batting-result.ball',
) {
  if (!ensureConfirmed()) return
  resultPicked.value = true
  if (result === 'batting-result.ball' && balls.value >= 3) {
    chooseDirect('batting-result.walk')
    return
  }
  if (
    result === 'batting-result.called-pitch' &&
    strikes.value >= 2 &&
    strikeoutDetailAvailable.value
  ) {
    chooseDirect('batting-result.called-strikeout')
    return
  }
  if (
    result === 'batting-result.swinging-strike' &&
    strikes.value >= 2 &&
    strikeoutDetailAvailable.value
  ) {
    chooseDirect('batting-result.swinging-strikeout')
    return
  }
  resultId.value = result
  void save()
}
function selectInPlay(result: string) {
  if (!ensureConfirmed()) return
  resultPicked.value = true
  resultId.value = result as PlayScreenObservation['resultId']
  resultPanel.value = null
  battedHit.value = null
  interferenceObservation.value = null
}
const resultLabels: Readonly<Record<string, string>> = {
  'batting-result.single': '単打',
  'batting-result.double': '二塁打',
  'batting-result.triple': '三塁打',
  'batting-result.home-run': '本塁打',
  'batting-result.batted-out': '凡打死',
  'batting-result.double-play': '併殺打',
  'batting-result.batted-reach': '凡打出塁',
  'batting-result.error': 'エラー',
  'batting-result.fielders-choice': '野手選択',
  'batting-result.sacrifice-bunt': '犠打',
  'batting-result.sacrifice-fly': '犠飛',
  'batting-result.sacrifice-bunt-error': '犠打失策',
  'secondary-result.batting-interference': '打撃妨害',
  'secondary-result.obstruction': '走塁妨害',
  'secondary-result.offensive-interference': '守備妨害',
}
const resultLabel = computed(
  () => resultLabels[resultId.value] ?? resultId.value,
)
function clearComplex() {
  resultId.value = 'batting-result.ball'
  battedHit.value = null
  interferenceObservation.value = null
  adoptInterference.value = false
  resultPanel.value = null
}
async function confirmNextBatter() {
  if (!nextBatterId.value) return
  activeSheet.value = null
  await nextTick()
  await save()
}
watch(battedContextKey, () => {
  runnerObservation.value = null
  if (batted.value || interference.value) runnerMode.value = false
})
watch(runnerMode, (value) => {
  if (!value) runnerObservation.value = null
})
watch([resultId, battedContextKey], () => {
  battedHit.value = null
  adoptInterference.value = false
  interferenceObservation.value = null
  if (batted.value || interference.value) {
    runnerMode.value = false
    runnerObservation.value = null
  }
})
watch(adoptInterference, () => {
  battedHit.value = null
})

watch(
  [resultId, () => displayed.value.after.stateFields['state.battingOrder']],
  () => {
    nextBatterId.value = ''
  },
)
watch(resultId, (value) => {
  if (
    value === 'batting-result.walk' ||
    value === 'batting-result.hit-by-pitch'
  ) {
    pendingNextBatter.value = value
    activeSheet.value = 'next-batter'
  }
})
const items = ref<readonly PitchTypeOption[]>([])
const cursor = ref<string | null>(null)
const history = ref<(string | null)[]>([])
const nextCursor = ref<string | null>(null)
const loading = ref(false)
const failed = ref(false)
const busy = ref(false)
const inspecting = ref(false)
const inspectState = ref<AttemptInspection | 'idle'>('idle')
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
const locked = computed(() =>
  canAppend.value ? null : ordinaryPitchLockReason(displayed.value.t2),
)
const lockMessage = computed(() => {
  if (props.suspended || locked.value === null) return null
  return locked.value === 'tiebreak'
    ? 'タイブレーク開始の配置・先頭打者・回を記録するまで、通常球は入力できません。'
    : '終了条件を検知しました。試合終了を宣言するまで、通常球は入力できません。'
})
const message = computed(() => {
  if (lockMessage.value) return '通常球の入力は停止しています'
  if (props.suspended)
    return 'サーバーの最新記録を確認しています。入力と再送を一時停止します'
  if (retryEvidenceUnavailable.value)
    return '再送に必要な元要求の送信記録を確認できません。新しい要求に置き換えず、運用責任者に確認してください'
  if (inspectState.value === 'unresolved')
    return '保存済みか未確定かを断定できません。結果確認中です'
  if (inspectState.value === 'retry_allowed' && status.value === 'pending')
    return '元の要求を照会し、後着を遮断して再送できることを確認しました'
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
async function save(override?: PlayScreenObservation['resultId']) {
  if (override !== undefined) resultId.value = override
  const diagnostic = globalThis as {
    __pitchlogE2eDiagnostics?: boolean
    __pitchlogSaveEnteredAt?: number
    __pitchlogSaveEnteredStatus?: Record<string, unknown>
  }
  if (diagnostic.__pitchlogE2eDiagnostics === true) {
    diagnostic.__pitchlogSaveEnteredAt = Date.now()
    diagnostic.__pitchlogSaveEnteredStatus = {
      status: status.value,
      busy: busy.value,
      canAppend: canAppend.value,
      confirmed: confirmed.value,
      point: point.value,
      selected: selected.value,
      loading: loading.value,
      failed: failed.value,
      tenantId: identity().tenantId,
      verified: identity().verified,
      hydrated: auth.hasHydrated,
      authenticated: auth.isAuthenticated,
      controller: controller !== null,
      runnerMode: runnerMode.value,
      runnerObservation: runnerObservation.value !== null,
    }
  }
  missingCourse.value = !runnerNonpitch.value && point.value === null
  missingPitchType.value =
    !runnerNonpitch.value &&
    !items.value.some((item) => item.key === selected.value)
  if (missingPitchType.value || missingCourse.value) {
    if (missingCourse.value) activeSheet.value = null
    return
  }
  if (
    !controller ||
    props.suspended ||
    busy.value ||
    !canAppend.value ||
    !confirmed.value ||
    (localRequested.value &&
      (!activeLocalSession() || batted.value || interference.value)) ||
    (runnerMode.value && runnerObservation.value === null) ||
    (!runnerNonpitch.value && !point.value) ||
    (batted.value && (!hitAvailable.value || !battedHit.value)) ||
    (interference.value &&
      (!hitAvailable.value ||
        interferenceRunners.value === null ||
        !interferenceObservation.value)) ||
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
        runnerEvent:
          runnerMode.value && runnerObservation.value
            ? (() => {
                const value = structuredClone(toRaw(runnerObservation.value))
                return value.perPitch.pitchEventKind === 'pitch-event'
                  ? { ...value, primaryResultId: resultId.value }
                  : value
              })()
            : null,
        battedHit: batted.value
          ? structuredClone(toRaw(battedHit.value))
          : null,
        interference: interference.value
          ? structuredClone(toRaw(interferenceObservation.value))
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
        pitchSpeed:
          speed.value === ''
            ? { kmh: null, outsideRangeConfirmed: false }
            : { kmh: speed.value, outsideRangeConfirmed: false },
        stance: stance.value > 0 ? String(stance.value) : null,
        battingSide: battingSide.value,
      }
    }
    const diagnostic = globalThis as {
      __pitchlogE2eDiagnostics?: boolean
      __pitchlogLastObservation?: string
    }
    if (diagnostic.__pitchlogE2eDiagnostics === true)
      diagnostic.__pitchlogLastObservation = JSON.stringify(observation)
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
    if (result === 'saved') inspectState.value = 'idle'
    if (
      result === 'saved' ||
      result === 'pending' ||
      result === 'queued-local'
    ) {
      if (speed.value !== '') lastSpeed.value = speed.value
      point.value = null
      speed.value = ''
      battedHit.value = null
      interferenceObservation.value = null
      resultPanel.value = null
      nextBatterId.value = ''
      if (!batted.value && !interference.value) {
        resultPicked.value = false
        resultId.value = 'batting-result.ball'
      }
      runnerObservation.value = null
      runnerMode.value = false
      pendingSecondary.value = null
      missingCourse.value = false
      missingPitchType.value = false
    }
    if (result === 'saved' && !localRequested.value) emit('saved')
  } finally {
    if (controller === current) busy.value = false
  }
}
async function saveTiebreakStart() {
  if (
    !controller ||
    props.suspended ||
    busy.value ||
    !confirmed.value ||
    !tiebreakReady.value
  )
    return
  const current = controller
  busy.value = true
  try {
    const result = await current.submitTiebreakStart({
      firstRunnerId: tiebreakFirst.value,
      secondRunnerId: tiebreakSecond.value,
      leadoffBatter: battingOrder.value,
      inning: Number(inning.value),
    })
    if (controller !== current || props.suspended) return
    status.value = result
    displayed.value = current.context
    canAppend.value = current.canAppend
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    if (result === 'saved') {
      tiebreakFirst.value = ''
      tiebreakSecond.value = ''
      emit('reload')
    }
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
    resultId.value = 'batting-result.ball'
    if (result === 'saved') emit('saved')
  } finally {
    if (controller === current) busy.value = false
  }
}
async function inspect(): Promise<AttemptInspection> {
  if (
    localRequested.value ||
    props.suspended ||
    !controller ||
    !confirmed.value ||
    !identity().verified ||
    inspecting.value
  )
    return 'blocked'
  const current = controller
  inspecting.value = true
  try {
    const resolution = await current.inspectAttempt()
    if (controller !== current || props.suspended) return 'blocked'
    inspectState.value = resolution
    retryEvidenceUnavailable.value = current.retryEvidenceUnavailable
    return resolution
  } finally {
    if (controller === current) inspecting.value = false
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
    if (result === 'saved') inspectState.value = 'idle'
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
  }
  // 未確認要求は自動送信しない。利用者が「結果を照会」で終結を確認してから再送する。
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
        // 停止解除では状態の再読取までに留める。照会・再送は利用者操作から始める。
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
        (error, detail) => {
          // E2Eが初期化時にだけ立てる観測フラグ。通常の製品操作では何もしない。
          const scope = globalThis as {
            __pitchlogE2eDiagnostics?: boolean
            __pitchlogSubmitError?: string
            __pitchlogSubmitDetail?: string
          }
          if (scope.__pitchlogE2eDiagnostics !== true) return
          scope.__pitchlogSubmitError =
            error instanceof Error
              ? `${error.name}: ${error.message}\n${error.stack ?? ''}`
              : String(error)
          scope.__pitchlogSubmitDetail = JSON.stringify(detail)
        },
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
      // reload直後は自動送信せず、利用者の照会から再開する。
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
  <section
    aria-label="通常投球を記録"
    class="flex h-dvh min-w-0 flex-col overflow-y-auto bg-slate-100 dark:bg-slate-950"
  >
    <div
      v-if="stateFields['state.gameEnded']"
      class="bg-red-600 px-4 py-1.5 text-center text-sm font-bold text-white lg:hidden"
    >
      試合終了 — 入力は無効です（メニュー→終了・再開で確認）
    </div>
    <p
      v-if="lockMessage"
      role="alert"
      data-testid="ordinary-pitch-locked"
      class="border-b border-amber-300 bg-amber-100 px-3 py-1.5 text-center text-xs font-extrabold text-amber-950 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-100"
    >
      {{ lockMessage }}
    </p>
    <section
      v-if="locked === 'tiebreak'"
      data-testid="tiebreak-start-panel"
      aria-label="タイブレーク開始"
      class="shrink-0 space-y-2 border-b border-violet-300 bg-violet-50 px-3 py-2 text-xs text-violet-950 dark:border-violet-800 dark:bg-violet-950/60 dark:text-violet-100"
    >
      <h3 class="font-extrabold">
        タイブレーク開始 — {{ tiebreakInning }}回・一塁/二塁・0アウト
      </h3>
      <p data-testid="tiebreak-leadoff">
        先頭打者（打順継続）: {{ battingOrder }}番 {{ batterName }}
      </p>
      <p v-if="tiebreakRule === null" data-testid="tiebreak-rule-missing">
        この試合にはタイブレーク規則がありません。試合設定を確認してください。
      </p>
      <template v-else>
        <div class="flex flex-wrap items-end gap-3">
          <label class="font-bold">
            一塁走者
            <select
              v-model="tiebreakFirst"
              data-testid="tiebreak-first-runner"
              class="mt-1 min-h-9 min-w-48 rounded border bg-white p-1 dark:bg-slate-900"
            >
              <option value="">未選択</option>
              <option
                v-for="item in tiebreakCandidates"
                :key="item.id"
                :value="item.id"
              >
                {{ item.label }}
              </option>
            </select>
          </label>
          <label class="font-bold">
            二塁走者
            <select
              v-model="tiebreakSecond"
              data-testid="tiebreak-second-runner"
              class="mt-1 min-h-9 min-w-48 rounded border bg-white p-1 dark:bg-slate-900"
            >
              <option value="">未選択</option>
              <option
                v-for="item in tiebreakCandidates"
                :key="item.id"
                :value="item.id"
              >
                {{ item.label }}
              </option>
            </select>
          </label>
          <button
            type="button"
            data-testid="tiebreak-start-apply"
            class="min-h-9 rounded border border-violet-400 bg-white px-3 py-1 font-extrabold text-violet-900 disabled:opacity-40 dark:border-violet-700 dark:bg-slate-900 dark:text-violet-100"
            :disabled="!tiebreakReady || busy || !confirmed"
            @click="saveTiebreakStart"
          >
            配置と回を記録
          </button>
        </div>
        <p v-if="!tiebreakReady" data-testid="tiebreak-start-blocked">
          規則に適合する二人の実選手を、重複しないように選択してください。
        </p>
      </template>
    </section>
    <p
      v-if="isLocalMode"
      data-testid="ordinary-local-notice"
      class="pointer-events-none border-b border-sky-300 bg-sky-50 px-3 py-1.5 text-center text-xs font-extrabold text-sky-800 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-200"
    >
      通信断中は端末へ未送信の投球だけを記録します。安打の詳細観測はこの入口で確定できません。
    </p>
    <div
      v-if="status === 'pending' && !isLocalMode && !suspended"
      class="flex shrink-0 items-center justify-center gap-2 border-b border-red-300 bg-red-50 px-3 py-1.5 text-center text-xs font-extrabold text-red-800 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
    >
      <span
        >未確認の要求が端末に残っています。同じ要求を順序どおり再送します。</span
      >
      <button
        type="button"
        data-testid="first-ball-inspect"
        class="min-h-9 rounded-lg border border-red-300 bg-white px-2 font-bold text-red-800 disabled:opacity-40 dark:border-red-700 dark:bg-slate-900 dark:text-red-200"
        :disabled="inspecting || !confirmed"
        @click="inspect"
      >
        結果を照会
      </button>
      <button
        type="button"
        data-testid="first-ball-retry"
        class="min-h-9 rounded-lg border border-red-300 bg-white px-2 font-bold text-red-800 disabled:opacity-40 dark:border-red-700 dark:bg-slate-900 dark:text-red-200"
        :disabled="
          busy || !confirmed || inspecting || inspectState === 'unresolved'
        "
        @click="retry"
      >
        再送
      </button>
    </div>
    <button
      v-if="!confirmed"
      type="button"
      class="flex shrink-0 items-center justify-center gap-2 border-b border-amber-300 bg-amber-50 px-3 py-1.5 text-center text-xs font-extrabold text-amber-900 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-100"
      @click="openSafety"
    >
      記録端末の安全確認が必要です — タップして確認
    </button>

    <header
      class="relative z-30 hidden h-16 shrink-0 overflow-visible border-b border-slate-200 bg-white lg:flex lg:flex-col [@media(max-height:960px)]:h-14 dark:border-slate-700 dark:bg-slate-900"
    >
      <div
        class="grid h-9 grid-cols-[minmax(190px,1.2fr)_120px_minmax(130px,1fr)_minmax(150px,1fr)_146px_minmax(220px,236px)] items-center gap-2 px-3 text-xs [@media(max-height:960px)]:h-8 [@media(max-height:960px)]:px-2"
      >
        <div class="truncate font-extrabold">
          <span class="text-slate-600 dark:text-slate-300">{{
            awayTeamName
          }}</span>
          <span class="mx-1 text-lg tabular-nums">{{ score.away }}</span>
          <span class="text-slate-400">–</span>
          <span class="mx-1 text-lg tabular-nums">{{ score.home }}</span>
          <span class="text-slate-600 dark:text-slate-300">{{
            homeTeamName
          }}</span>
        </div>
        <div
          class="flex min-w-0 items-center justify-center font-extrabold tabular-nums"
        >
          {{ inning }}回{{ halfLabel }}　{{ outs }}アウト
        </div>
        <CountDisplay compact :balls="balls" :strikes="strikes" :outs="outs" />
        <div
          class="relative flex min-w-0 items-center gap-1 rounded-lg border border-sky-100 bg-sky-50/50 px-1 dark:border-sky-900/60 dark:bg-sky-950/20"
          role="group"
          aria-label="打者情報と打席左右"
        >
          <span class="min-w-0 flex-1 truncate px-1 text-left">
            <span class="mr-1 text-slate-400">打</span>
            <span class="font-bold">{{ battingOrder }}番 {{ batterName }}</span>
            <span v-if="batterNumber" class="ml-1 text-slate-400"
              >#{{ batterNumber }}</span
            >
          </span>
          <button
            type="button"
            class="inline-flex h-8 min-w-12 shrink-0 items-center justify-center gap-0.5 whitespace-nowrap rounded-md border border-sky-200 bg-white px-1.5 text-[10px] font-extrabold text-sky-700 shadow-sm transition hover:border-sky-400 hover:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-sky-800 dark:bg-slate-900 dark:text-sky-300 dark:hover:bg-sky-950/70"
            :disabled="!canToggleBattingSide"
            :title="
              canToggleBattingSide
                ? '打席左右を切り替える'
                : '打席左右は登録された打者情報に従います'
            "
            :aria-label="`現在は${battingSide}打席`"
            @click="toggleBattingSide"
          >
            {{ battingSide }}打
            <span v-if="canToggleBattingSide" aria-hidden="true">⇄</span>
          </button>
        </div>
        <div
          class="relative min-w-0 rounded-lg border border-violet-100 bg-violet-50/50 px-1 dark:border-violet-900/60 dark:bg-violet-950/20"
        >
          <div class="flex min-h-8 min-w-0 items-center gap-1 rounded-lg px-1">
            <span class="shrink-0 text-slate-400">投</span>
            <span class="min-w-0 truncate font-bold">{{ pitcherName }}</span>
            <span
              v-if="pitcherNumber"
              class="shrink-0 rounded bg-violet-100 px-1 py-0.5 text-[10px] font-extrabold text-violet-700 dark:bg-violet-900/60 dark:text-violet-300"
            >
              #{{ pitcherNumber }}
            </span>
          </div>
        </div>
        <div
          class="relative flex min-w-0 items-center gap-1"
          role="group"
          aria-label="走者状況"
        >
          <span
            v-for="chip in runnerChips"
            :key="chip.base"
            :class="[
              'flex h-8 min-w-0 flex-1 flex-col items-center justify-center rounded-md border px-1 leading-none',
              chip.runner
                ? 'border-red-500 bg-red-50 text-red-800 dark:bg-red-950/50 dark:text-red-200'
                : 'border-slate-200 bg-slate-50 text-slate-400 dark:border-slate-700 dark:bg-slate-800',
            ]"
          >
            <span class="text-[9px] font-extrabold">{{ chip.base }}</span>
            <span
              class="mt-0.5 w-full truncate text-center text-[10px] font-bold"
            >
              {{ chip.runner ? chip.runner.name : '—' }}
            </span>
          </span>
        </div>
      </div>
      <div
        class="flex h-7 min-w-0 items-center gap-1.5 overflow-hidden border-t border-slate-100 bg-slate-50 px-3 [@media(max-height:960px)]:h-6 [@media(max-height:960px)]:px-2 dark:border-slate-800 dark:bg-slate-950/50"
      >
        <span
          class="mr-0.5 text-[10px] font-extrabold uppercase tracking-wider text-slate-400"
        >
          #{{ displayed.nextPosition.d1 }}
        </span>
        <span
          :class="[
            'rounded-full px-2 py-1 text-[10px] font-extrabold',
            stance > 0
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200'
              : 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
          ]"
        >
          構え {{ stance > 0 ? stance : '未' }}
        </span>
        <span
          :class="[
            'rounded-full px-2 py-1 text-[10px] font-extrabold',
            courseEntered
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200'
              : 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
          ]"
        >
          コース {{ courseEntered ? '入力済' : '未入力' }}
        </span>
        <span
          :class="[
            'rounded-full px-2 py-1 text-[10px] font-extrabold',
            selected
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200'
              : 'bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
          ]"
        >
          球種 {{ selected ? currentPitchTypeLabel : '未' }}
        </span>
        <span
          class="rounded-full bg-slate-200 px-2 py-1 text-[10px] font-extrabold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
        >
          球速 {{ speed || '---' }}km/h
        </span>
        <span
          class="rounded-full bg-slate-200 px-2 py-1 text-[10px] font-extrabold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
        >
          結果 {{ resultLabels[resultId] ?? '未選択' }}
        </span>
        <span
          data-testid="ordinary-state-source"
          class="rounded-full bg-slate-200 px-2 py-1 text-[10px] font-extrabold text-slate-500 dark:bg-slate-800 dark:text-slate-400"
        >
          {{
            displayed.source === 'local-provisional'
              ? '端末の暫定状態'
              : 'サーバー確認済み'
          }}
        </span>
        <button
          v-if="!confirmed"
          type="button"
          class="ml-auto rounded-full bg-amber-400 px-2 py-1 text-[10px] font-extrabold text-amber-950"
          @click="openSafety"
        >
          端末確認が必要
        </button>
        <button
          v-else
          type="button"
          class="ml-auto rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-extrabold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200"
          @click="openSafety"
        >
          端末確認済み
        </button>
      </div>
    </header>

    <div
      class="shrink-0 border-b border-slate-200 bg-white px-2 py-1 lg:hidden dark:border-slate-700 dark:bg-slate-900"
    >
      <button
        type="button"
        class="flex w-full items-center justify-between gap-2 text-sm font-bold"
        @click="leftOpen = !leftOpen"
      >
        <span>
          {{ inning }}回{{ halfLabel }} {{ outs }}アウト B{{ balls }}-S{{
            strikes
          }}
          ／ {{ battingOrder }}番 {{ batterName }}
        </span>
        <span class="tabular-nums">{{ score.away }}-{{ score.home }}</span>
      </button>
      <p data-testid="ordinary-local-balls" class="sr-only">{{ balls }}</p>
      <p data-testid="ordinary-local-strikes" class="sr-only">
        {{ strikes }}
      </p>
      <div v-if="leftOpen" class="mt-2 flex flex-col gap-2 pb-1">
        <div class="grid grid-cols-2 gap-2">
          <CountDisplay :balls="balls" :strikes="strikes" :outs="outs" />
          <div
            class="rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-900"
          >
            <p class="font-extrabold">{{ battingOrder }}番 {{ batterName }}</p>
            <p class="mt-1 text-slate-500">
              投手 {{ pitcherName }}・捕手 {{ catcherName }}
            </p>
            <p class="mt-1 text-slate-500">次打者 {{ nextBatterName }}</p>
          </div>
        </div>
        <div
          class="rounded-xl border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900"
        >
          <RunnerDiamond
            :first="runnerFirst"
            :second="runnerSecond"
            :third="runnerThird"
            :batter="batterName"
            compact
          />
        </div>
      </div>
      <p
        v-if="isLineupRecordingContext(displayed)"
        data-testid="lineup-local-state"
        class="mt-1 text-xs text-slate-500"
      >
        {{ inning }}回{{ halfLabel }}・{{ outs }}アウト・{{ battingOrder }}番
      </p>
    </div>

    <div
      class="grid grid-cols-1 gap-2 p-2 lg:min-h-0 lg:flex-1 lg:grid-cols-[264px_368px_360px] lg:justify-center [@media(min-width:1120px)]:grid-cols-[280px_368px_360px] xl:grid-cols-[280px_minmax(440px,520px)_400px] [@media(max-height:960px)]:gap-1 [@media(max-height:960px)]:p-1"
    >
      <div
        class="hidden min-h-0 flex-col gap-2 overflow-hidden lg:flex [@media(max-height:960px)]:gap-1"
      >
        <section
          aria-label="構え入力"
          class="flex min-h-0 items-start justify-center overflow-y-auto overscroll-contain rounded-xl border border-slate-200 bg-white p-1 [@media(max-height:960px)]:p-0 dark:border-slate-700 dark:bg-slate-900"
        >
          <div class="my-auto">
            <StanceGrid
              :value="stance"
              :viewpoint="viewpoint"
              @change="selectStance"
            />
          </div>
        </section>
        <section
          aria-label="球速入力"
          class="flex min-h-0 items-start justify-center overflow-y-auto overscroll-contain rounded-xl border border-slate-200 bg-white p-1 [@media(max-height:960px)]:p-0 dark:border-slate-700 dark:bg-slate-900"
        >
          <div class="my-auto">
            <SpeedPad
              :value="speed"
              :last-speed="lastSpeed"
              :disabled="busy"
              @change="changeSpeed"
            />
          </div>
        </section>
        <section
          class="rounded-xl border border-slate-200 bg-white p-2 text-xs dark:border-slate-700 dark:bg-slate-900"
        >
          <p
            role="status"
            data-testid="first-ball-status"
            class="font-semibold text-slate-600 dark:text-slate-300"
          >
            {{ message }}
          </p>
          <p
            v-if="displayed.source === 'local-provisional'"
            class="mt-1 text-slate-500"
          >
            端末の未確認分を含む暫定状態
          </p>
          <p v-else class="mt-1 text-slate-500">サーバー確認済みの状態</p>
          <button
            type="button"
            class="mt-2 min-h-10 w-full rounded-lg border border-slate-300 bg-white px-2 font-bold text-slate-700 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="busy"
            @click="openSafety"
          >
            記録端末の確認
          </button>
        </section>
      </div>

      <div
        class="flex flex-col gap-2 lg:min-h-0 [@media(max-height:960px)]:gap-1"
      >
        <div v-show="!batted && !interference" class="contents">
          <div class="flex items-center justify-center lg:min-h-0 lg:flex-1">
            <div
              class="aspect-square w-full max-w-sm lg:h-full lg:max-h-full lg:max-w-full"
              data-testid="first-ball-course"
            >
              <StrikeZone
                :point="point"
                :plate-side="battingSide"
                :viewpoint="viewpoint"
                :highlight="missingCourse"
                :disabled="busy"
                @tap="
                  (x, y) => {
                    point = { x, y }
                    missingCourse = false
                  }
                "
              />
            </div>
          </div>
          <div
            class="flex flex-wrap justify-center gap-1.5"
            :class="{ 'missing-highlight p-1': missingPitchType }"
          >
            <button
              v-for="item in items"
              :key="item.key"
              type="button"
              :data-testid="'pitch-type-' + item.key"
              :data-pitch-type="item.key"
              :aria-pressed="selected === item.key"
              :disabled="busy"
              :class="[
                'relative min-h-11 min-w-12 rounded-lg border px-1.5 text-sm font-bold transition-colors disabled:opacity-40',
                selected === item.key
                  ? 'border-sky-600 bg-sky-600 text-white'
                  : 'border-slate-300 bg-white text-slate-700 hover:bg-sky-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-sky-900/40',
              ]"
              :title="item.display_name"
              @click="selectPitchType(item.key)"
            >
              {{ pitchTypeChipLabel(item) }}
            </button>
            <button
              v-if="nextCursor !== null"
              type="button"
              class="min-h-11 rounded-lg border border-slate-300 bg-white px-2 text-xs font-bold text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
              :disabled="loading || busy"
              @click="next"
            >
              次の球種
            </button>
            <button
              v-if="history.length > 0"
              type="button"
              class="min-h-11 rounded-lg border border-slate-300 bg-white px-2 text-xs font-bold text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
              :disabled="loading || busy"
              @click="previous"
            >
              前の球種
            </button>
          </div>
          <p v-if="loading" class="text-center text-xs text-slate-500">
            球種を取得しています…
          </p>
          <p
            v-if="failed"
            role="alert"
            class="text-center text-xs font-bold text-red-700"
          >
            {{
              isLocalMode
                ? '保存済みの球種ページを確認できません。'
                : '球種を取得できません。'
            }}
          </p>
          <button
            v-if="failed"
            type="button"
            class="mx-auto min-h-10 rounded-lg border border-slate-300 bg-white px-2 text-xs font-bold dark:border-slate-600 dark:bg-slate-800"
            :disabled="loading"
            @click="load(cursor)"
          >
            {{ isLocalMode ? '保存済み球種を再確認' : '球種を再取得' }}
          </button>
        </div>
        <div
          v-if="batted || interference"
          class="rounded-xl border border-sky-300 bg-sky-50 p-3 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100"
        >
          <p class="font-extrabold">{{ resultLabel }} を選択中</p>
          <p class="mt-1 text-xs font-semibold">
            右の確認欄で打球位置・打球種・捕球選手・走者の実結果を確認し、「確定・保存」を押してください。
          </p>
        </div>
        <div class="flex flex-wrap items-center justify-center gap-2 pb-1">
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-3 text-xs font-bold text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
            :disabled="busy"
            @click="viewpoint = viewpoint === 'catcher' ? 'pitcher' : 'catcher'"
          >
            視点: {{ viewpoint === 'catcher' ? '捕手側' : '投手後方' }}
          </button>
          <button
            v-if="canToggleBattingSide"
            type="button"
            class="min-h-10 rounded-lg border border-sky-300 bg-white px-3 text-xs font-bold text-sky-700 dark:border-sky-700 dark:bg-slate-800 dark:text-sky-200"
            :disabled="busy"
            @click="toggleBattingSide"
          >
            打席 {{ battingSide }}打 ⇄
          </button>
        </div>
        <div
          class="flex flex-col items-center justify-center gap-2 sm:flex-row sm:items-start lg:hidden"
        >
          <SpeedPad
            :value="speed"
            :last-speed="lastSpeed"
            :disabled="busy"
            @change="changeSpeed"
          />
          <StanceGrid
            :value="stance"
            :viewpoint="viewpoint"
            @change="selectStance"
          />
        </div>
      </div>

      <div
        class="min-h-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-50 p-2 [@media(max-height:960px)]:p-1 dark:border-slate-700 dark:bg-slate-900/60"
      >
        <div
          v-if="batted || interference"
          class="flex h-full min-h-0 flex-col gap-2 overflow-y-auto"
        >
          <button
            type="button"
            class="flex min-h-11 w-full items-center gap-1 rounded-lg px-2 text-left text-sm font-bold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            @click="clearComplex"
          >
            ← 結果選択に戻る
          </button>
          <div
            class="rounded-xl border-2 border-sky-500 bg-sky-50 p-2 dark:bg-sky-950/40"
          >
            <p class="text-xs font-bold text-sky-600 dark:text-sky-300">
              {{ batted ? 'インプレー' : '妨害' }}
            </p>
            <p class="text-2xl font-extrabold">{{ resultLabel }}</p>
          </div>
          <p
            v-if="batted && !hitAvailable"
            role="alert"
            class="text-xs font-bold text-red-700"
          >
            この入力は試合継続中・タイブレークなしの状態だけに対応しています。
          </p>
          <GameScreenBattedHitObservation
            v-if="batted && hitAvailable"
            :context-key="battedContextKey"
            :result-id="
              resultId as NonNullable<
                PlayScreenObservation['battedHit']
              >['resultId']
            "
            :before-outs="stateFields['state.outs']"
            :batter-id="batterId"
            :fielders="fielders"
            :runners="battedRunners"
            :adopt-interference="adoptInterference"
            :disabled="busy"
            @change="
              (value) =>
                (battedHit = value as PlayScreenObservation['battedHit'])
            "
          />
          <GameScreenInterferenceObservation
            v-if="
              interference &&
              hitAvailable &&
              interferenceRunners !== null &&
              isLineupRecordingContext(displayed)
            "
            :context-key="battedContextKey"
            :result-id="
              resultId as NonNullable<
                PlayScreenObservation['interference']
              >['resultId']
            "
            :batter-id="batterId"
            :runners="interferenceRunners"
            :disabled="busy"
            @change="(value) => (interferenceObservation = value)"
          />
          <p
            v-else-if="interference"
            role="alert"
            class="text-xs font-bold text-red-700"
          >
            この妨害入力は試合継続中・タイブレークなし・走者ID確認済みの状態だけに対応しています。
          </p>
          <button
            type="button"
            data-testid="first-ball-save"
            class="mt-auto min-h-16 rounded-xl bg-sky-600 px-4 text-lg font-bold text-white hover:bg-sky-700 disabled:pointer-events-none disabled:opacity-40"
            :disabled="
              busy ||
              !canAppend ||
              (batted && (!hitAvailable || battedHit == null)) ||
              (interference &&
                (!hitAvailable || interferenceObservation == null))
            "
            @click="save()"
          >
            確定・保存
          </button>
        </div>
        <LegacyResultPad
          v-else
          v-model:panel="resultPanel"
          :balls="balls"
          :strikes="strikes"
          :outs="outs"
          :disabled="busy || !canAppend"
          :busy="busy"
          :selected-result="highlightedResult"
          :missing-course="missingCourse"
          :missing-pitch-type="missingPitchType"
          :hit-available="hitAvailable"
          :has-runners="runnersState !== 'empty'"
          :has-first="
            runnersState === 'first' ||
            runnersState === 'first-second' ||
            runnersState === 'first-third' ||
            runnersState === 'loaded'
          "
          :has-third="
            runnersState === 'third' ||
            runnersState === 'first-third' ||
            runnersState === 'second-third' ||
            runnersState === 'loaded'
          "
          :strikeout-double-play-available="strikeoutDoublePlayAvailable"
          :strikeout-detail-available="strikeoutDetailAvailable"
          :secondary-pending="pendingSecondaryLabel"
          :intentional-walk-available="intentionalWalkAvailable"
          @simple="selectSimple"
          @select-in-play="selectInPlay"
          @direct="chooseDirect"
          @intentional="saveIntentionalWalk"
          @secondary="openSecondary"
          @interference="selectInterference"
          @balk="openBalk"
          @clear-secondary="clearSecondary"
        />
      </div>
    </div>

    <RecordBottomBar
      :has-runners="hasRunners"
      :input-locked="busy || !canAppend"
      :game-finished="stateFields['state.gameEnded']"
      :edit-last-available="false"
      :pickoff-available="true"
      :strategy-available="false"
      sync-label="同期状態"
      elapsed="—"
      @undo="openUndo"
      @pickoff="openRunner"
      @substitution="openSubstitution"
      @menu="openMenu"
      @sync="activeSheet = 'sync'"
    />

    <Sheet
      :open="activeSheet === 'safety'"
      title="記録端末の安全確認"
      side="right"
      @close="activeSheet = null"
    >
      <div class="space-y-3 text-sm">
        <p>
          記録の二重書き込みを防ぐため、開始時と同じ端末・ブラウザで操作していることを確認します。
        </p>
        <p
          v-if="!httpsTopLevel()"
          role="alert"
          class="rounded-lg border border-red-300 bg-red-50 p-2 font-bold text-red-800"
        >
          記録にはHTTPSで直接開いた画面が必要です。
        </p>
        <label
          class="flex items-start gap-2 rounded-lg border border-slate-200 p-2"
        >
          <input
            v-model="sameProfile"
            type="checkbox"
            data-testid="first-ball-env-profile"
            class="mt-1"
          />
          <span>ほかの記録タブと同じブラウザプロファイルを使います</span>
        </label>
        <label
          class="flex items-start gap-2 rounded-lg border border-slate-200 p-2"
        >
          <input
            v-model="sameMode"
            type="checkbox"
            data-testid="first-ball-env-mode"
            class="mt-1"
          />
          <span>通常・プライベートなどの閲覧モードを統一します</span>
        </label>
        <label
          class="flex items-start gap-2 rounded-lg border border-slate-200 p-2"
        >
          <input
            v-model="sameBucket"
            type="checkbox"
            data-testid="first-ball-env-bucket"
            class="mt-1"
          />
          <span>同じサイトの保存領域を使うタブだけで記録します</span>
        </label>
        <label
          class="flex items-start gap-2 rounded-lg border border-slate-200 p-2"
        >
          <input
            v-model="noLockdown"
            type="checkbox"
            data-testid="first-ball-env-lockdown"
            class="mt-1"
          />
          <span>この端末でLockdownモードを適用していません</span>
        </label>
        <p class="text-xs text-slate-500">
          4項目を確認すると投球を確定できます。確認はこの画面を開いている間だけ保持します。
        </p>
        <button
          type="button"
          class="min-h-12 w-full rounded-xl bg-sky-600 px-4 font-bold text-white disabled:opacity-40"
          :disabled="!confirmed"
          @click="activeSheet = null"
        >
          確認して記録へ戻る
        </button>
      </div>
    </Sheet>

    <Sheet
      :open="activeSheet === 'undo'"
      title="直前の記録を取り消す"
      side="right"
      wide
      @close="activeSheet = null"
    >
      <GameScreenUndoProduct :game-id="game.id" @saved="undoDone" />
    </Sheet>

    <Sheet
      :open="activeSheet === 'past-correction'"
      title="過去の訂正"
      side="right"
      wide
      @close="activeSheet = null"
    >
      <GameScreenPastCorrectionProduct
        v-if="gameRead"
        :game="gameRead"
        :suspended="busy || suspended"
        @saved="pastCorrectionSaved"
      />
      <p v-else role="status">この試合状態では過去訂正を開けません。</p>
    </Sheet>

    <Sheet
      :open="activeSheet === 'menu'"
      title="メニュー"
      side="right"
      @close="activeSheet = null"
    >
      <div v-if="activeSheet === 'menu'" class="space-y-2">
        <button
          type="button"
          class="flex min-h-14 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-left font-bold dark:border-slate-700 dark:bg-slate-800"
          @click="activeSheet = 'lifecycle'"
        >
          <span>試合の終了・再開</span>
          <span class="text-xs text-slate-400">終了宣言 / 再開</span>
        </button>
        <button
          type="button"
          class="flex min-h-14 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-left font-bold dark:border-slate-700 dark:bg-slate-800"
          @click="activeSheet = 'sync'"
        >
          <span>同期センター</span>
          <span class="text-xs text-slate-400">未送信・結果不明</span>
        </button>
        <button
          type="button"
          disabled
          class="flex min-h-14 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-left font-bold text-slate-400 dark:border-slate-700 dark:bg-slate-800"
          title="このMVPでは未接続です"
        >
          <span>タイブレーク開始</span>
          <span class="text-xs">未接続</span>
        </button>
        <button
          type="button"
          class="flex min-h-14 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-left font-bold dark:border-slate-700 dark:bg-slate-800"
          @click="openViewer"
        >
          <span>記録を見る</span>
          <span class="text-xs text-slate-400">閲覧画面</span>
        </button>
        <button
          type="button"
          class="flex min-h-14 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-left font-bold dark:border-slate-700 dark:bg-slate-800"
          @click="openStats"
        >
          <span>成績</span>
          <span class="text-xs text-slate-400">打撃・投手</span>
        </button>
        <button
          type="button"
          class="flex min-h-14 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-left font-bold dark:border-slate-700 dark:bg-slate-800"
          @click="openExport"
        >
          <span>毎球CSV</span>
          <span class="text-xs text-slate-400">保存済みのみ</span>
        </button>
        <button
          type="button"
          :disabled="!gameRead"
          class="flex min-h-14 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 text-left font-bold disabled:text-slate-400 dark:border-slate-700 dark:bg-slate-800"
          :title="gameRead ? undefined : 'この試合状態では過去訂正を開けません'"
          @click="activeSheet = 'past-correction'"
        >
          <span>過去の訂正</span>
          <span class="text-xs">{{ gameRead ? '開く' : '未提供' }}</span>
        </button>
      </div>
    </Sheet>

    <Sheet
      :open="activeSheet === 'lifecycle'"
      title="試合の終了・再開"
      side="right"
      wide
      @close="activeSheet = 'menu'"
    >
      <GameScreenLifecycleProduct
        :game-id="game.id"
        @resume-recording="lifecycleResumed"
      />
    </Sheet>

    <Sheet
      :open="activeSheet === 'sync'"
      title="同期センター"
      side="right"
      @close="activeSheet = null"
    >
      <div class="space-y-3 text-sm">
        <p role="status" class="font-semibold">{{ message }}</p>
        <p
          v-if="status === 'pending'"
          class="rounded-lg border border-amber-300 bg-amber-50 p-2 font-bold text-amber-900"
        >
          未確認の要求が端末に残っています。同じ要求を再送し、サーバーの受理結果を確認してください。
        </p>
        <div v-if="status === 'pending' && !isLocalMode" class="space-y-2">
          <button
            type="button"
            data-testid="sync-inspect"
            class="min-h-12 w-full rounded-xl border border-sky-300 bg-white px-4 font-bold text-sky-800 disabled:opacity-40 dark:border-sky-700 dark:bg-slate-900 dark:text-sky-200"
            :disabled="inspecting || !confirmed"
            @click="inspect"
          >
            結果を照会（保存要求は送りません）
          </button>
          <button
            type="button"
            data-testid="sync-retry"
            class="min-h-12 w-full rounded-xl bg-sky-600 px-4 font-bold text-white disabled:opacity-40"
            :disabled="
              busy || !confirmed || inspecting || inspectState === 'unresolved'
            "
            @click="retry"
          >
            同じ要求を再送
          </button>
          <p
            v-if="inspectState === 'unresolved'"
            role="status"
            class="rounded-lg border border-amber-300 bg-amber-50 p-2 text-xs font-bold text-amber-900"
          >
            照会では保存済み・未保存を確定できませんでした。結果確認中のまま、再送しません。
          </p>
          <p
            v-else-if="inspectState === 'retry_allowed'"
            role="status"
            class="rounded-lg border border-emerald-300 bg-emerald-50 p-2 text-xs font-bold text-emerald-900"
          >
            旧要求を終結し、後着を遮断しました。同じ本文のまま再送できます。
          </p>
        </div>
        <p v-else class="text-slate-500">
          現在のこの画面からの未確認要求はありません。
        </p>
        <button
          type="button"
          class="min-h-12 w-full rounded-xl border border-slate-300 bg-white px-4 font-bold text-slate-700 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          :disabled="busy"
          @click="emit('reload')"
        >
          サーバーから再取得
        </button>
      </div>
    </Sheet>

    <Sheet
      :open="activeSheet === 'runner'"
      title="牽制・走者操作"
      side="right"
      wide
      @close="activeSheet = null"
    >
      <div class="space-y-3">
        <p
          class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-900"
        >
          ここでは牽制・ボークなど無投球の操作を記録します。投球を伴う盗塁・暴投・捕逸は、通常投球の結果と合わせて記録します。
        </p>
        <p
          v-if="runnerNotice"
          role="alert"
          class="rounded-lg border border-red-300 bg-red-50 p-2 text-sm font-bold text-red-800"
        >
          {{ runnerNotice }}
        </p>
        <GameScreenRunnerEventObservation
          :runners="runnerPeople"
          :primary-result-id="resultId"
          :source-key="runnerSourceKey"
          :initial-operation="pendingSecondary ?? undefined"
          :disabled="busy"
          @confirmed="runnerConfirmed"
          @select-primary-result="(value) => (resultId = value)"
        />
      </div>
    </Sheet>

    <Sheet
      :open="activeSheet === 'next-batter'"
      title="次の打者を確認"
      side="right"
      @close="activeSheet = null"
    >
      <div class="space-y-3 text-sm">
        <p>
          四球・死球で打席が終了します。打順どおりの次の打者を確認してください。
        </p>
        <label class="block font-bold">
          次の打者
          <select
            v-model="nextBatterId"
            data-testid="terminal-next-batter-dialog"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-base dark:border-slate-600 dark:bg-slate-800"
          >
            <option value="">次の打者を選択</option>
            <option
              v-for="candidate in nextBatters"
              :key="candidate.player.player_id"
              :value="candidate.player.player_id"
            >
              {{
                candidate.batting_slot.kind === 'slot'
                  ? candidate.batting_slot.slot
                  : ''
              }}番
              {{ display.playerName(candidate.player.player_id, 'の打者') }}
            </option>
          </select>
        </label>
        <p
          v-if="nextBatters.length === 0"
          role="alert"
          class="font-bold text-red-700"
        >
          次の打者候補を確認できません。打順とスタメンを確認してください。
        </p>
        <button
          type="button"
          class="min-h-12 w-full rounded-xl bg-sky-600 px-4 font-bold text-white disabled:opacity-40"
          :disabled="nextBatterId === '' || busy"
          @click="confirmNextBatter"
        >
          この打者で確定
        </button>
      </div>
    </Sheet>

    <div class="sr-only" aria-label="キーボード・読み上げ用の結果入力">
      <label
        ><input
          v-model="sameProfile"
          type="checkbox"
          data-testid="first-ball-env-profile"
        />同じブラウザプロファイルを使います</label
      >
      <label
        ><input
          v-model="sameMode"
          type="checkbox"
          data-testid="first-ball-env-mode"
        />同じ閲覧モードを使います</label
      >
      <label
        ><input
          v-model="sameBucket"
          type="checkbox"
          data-testid="first-ball-env-bucket"
        />同じ保存領域を使います</label
      >
      <label
        ><input
          v-model="noLockdown"
          type="checkbox"
          data-testid="first-ball-env-lockdown"
        />Lockdownモードではありません</label
      >
      <p class="sr-only">次の打者を確認</p>
      <label v-if="terminal"
        >次の打者
        <select v-model="nextBatterId" data-testid="terminal-next-batter">
          <option value="">次の打者を選択</option>
          <option
            v-for="candidate in nextBatters"
            :key="candidate.player.player_id"
            :value="candidate.player.player_id"
          >
            {{
              candidate.batting_slot.kind === 'slot'
                ? candidate.batting_slot.slot
                : ''
            }}番
          </option>
        </select>
      </label>
      <label v-if="items.length > 0"
        >球種
        <select v-model="selected" data-testid="first-ball-pitch-type">
          <option value="">球種を選択</option>
          <option v-for="item in items" :key="item.key" :value="item.key">
            {{ item.display_name }}
          </option>
        </select>
      </label>
      <label v-if="items.length > 0"
        >結果
        <select v-model="resultId" data-testid="ordinary-pitch-result">
          <option value="batting-result.ball">ボール</option>
          <option value="batting-result.called-pitch">見逃し</option>
          <option value="batting-result.swinging-strike">空振り</option>
          <option value="batting-result.foul">ファール</option>
          <template
            v-if="
              isPlayRecordingContext(displayed) ||
              isLineupRecordingContext(displayed)
            "
          >
            <option value="batting-result.walk">四球</option>
            <option value="batting-result.hit-by-pitch">死球</option>
          </template>
          <template v-if="isLineupRecordingContext(displayed)">
            <template v-if="strikes >= 2">
              <option value="batting-result.called-strikeout">
                見逃し三振
              </option>
              <option value="batting-result.swinging-strikeout">
                空振り三振
              </option>
              <option value="batting-result.k3">K3</option>
              <option
                v-if="strikeoutDoublePlayAvailable"
                value="batting-result.strikeout-double-play"
              >
                三振ゲッツー
              </option>
            </template>
            <template v-if="hitAvailable && !isLocalMode">
              <option value="batting-result.single">単打</option>
              <option value="batting-result.double">二塁打</option>
              <option value="batting-result.triple">三塁打</option>
              <option value="batting-result.home-run">本塁打</option>
              <option value="batting-result.batted-out">打球アウト</option>
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
                併殺打
              </option>
              <option value="secondary-result.batting-interference">
                打撃妨害
              </option>
              <option value="secondary-result.obstruction">走塁妨害</option>
              <option value="secondary-result.offensive-interference">
                守備妨害
              </option>
            </template>
          </template>
        </select>
      </label>
      <button
        v-if="
          items.length > 0 &&
          !suspended &&
          canAppend &&
          !batted &&
          !interference
        "
        type="button"
        data-testid="first-ball-save"
        class="sticky bottom-0 z-20 min-h-16 w-full rounded-xl bg-sky-600 px-4 text-lg font-bold text-white shadow-lg hover:bg-sky-700 disabled:pointer-events-none disabled:opacity-40"
        :disabled="
          busy ||
          !canAppend ||
          !confirmed ||
          (!runnerNonpitch && (!point || !selected)) ||
          (terminal && nextBatterId === '')
        "
        @click="save()"
      >
        投球を確定・保存
      </button>
    </div>
  </section>
</template>
