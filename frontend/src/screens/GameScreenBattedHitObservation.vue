<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import type { BattedHitResult } from '../../../contracts/state-transition/lineup_play_prefix_payload_v1.d.ts'
import type { RunnerAdvanceOverridesByRunner } from '../api/runnerAdvanceWire'
import type {
  BattedHitWireObservations,
  BattedOtherResult,
} from '../api/lineupPrefixWire'
import {
  readBattedBallOptions,
  type BattedBallOption,
} from '../api/battedBallOptions'
import GameScreenObservationField from './GameScreenObservationField.vue'
import { useAuthStore } from '../stores/authStore'

type Confirmation = Omit<
  BattedHitWireObservations,
  | 'pitchTypeKey'
  | 'course'
  | 'pitchSpeed'
  | 'stance'
  | 'battingSide'
  | 'runnerAdvanceOverridesByRunner'
> & {
  runnerAdvanceOverridesByRunner: RunnerAdvanceOverridesByRunner
  rbiRulingByRunner?: Partial<
    Record<
      '1' | '2' | '3',
      'ordinary-play' | 'kept-running' | 'stopped-and-restarted'
    >
  >
}
type BattedOutConfirmation = Omit<
  Confirmation,
  'resultId' | 'thirdOutObservation'
> & {
  resultId: 'batting-result.batted-out'
  thirdOutObservation:
    | { kind: 'none' }
    | {
        kind: 'batter-before-first'
        batter: { kind: 'official'; player_id: string }
      }
}
type BattedOtherConfirmation = Omit<Confirmation, 'resultId'> & {
  resultId: BattedOtherResult
}
type BattedDoublePlayConfirmation = Omit<Confirmation, 'resultId'> & {
  resultId: 'batting-result.double-play'
  outRunner: { base: '1'; runnerId: string; outKind: 'force-out' }
}
type Base = '1' | '2' | '3'
const props = withDefaults(
  defineProps<{
    contextKey: string
    resultId:
      | BattedHitResult
      | 'batting-result.batted-out'
      | BattedOtherResult
      | 'batting-result.double-play'
    beforeOuts: string
    batterId: string
    fielders: readonly { id: string; label: string }[]
    runners?: readonly { base: Base; label: string; runnerId?: string }[]
    adoptInterference?: boolean
    disabled?: boolean
  }>(),
  { runners: () => [] },
)
const emit = defineEmits<{
  change: [
    value:
      | Confirmation
      | BattedOutConfirmation
      | BattedOtherConfirmation
      | BattedDoublePlayConfirmation
      | null,
  ]
}>()
const auth = useAuthStore()
const fields = [
  'typeKey',
  'strengthKey',
  'hitX',
  'hitY',
  'rawFielderPosition',
  'resolvedFielderId',
] as const
const labels = {
  typeKey: '打球種',
  strengthKey: '打球の強さ',
  hitX: '打球座標 X（0〜1）',
  hitY: '打球座標 Y（0〜1）',
  rawFielderPosition: '観測した守備位置',
  resolvedFielderId: '観測した守備者',
}
const modes = ref<Record<string, string>>({})
const values = ref<Record<string, string>>({})
const confirmations = ref<Record<string, string>>({})
const runnerDestinations = ref<Record<string, string>>({})
const runnerRbiRulings = ref<Record<string, string>>({})
const runnerConfirmed = ref(false)
const thirdAttempt = ref('')
const errorFielderId = ref('')
const questions = computed(() => [
  {
    key: 'scoring',
    label:
      props.resultId === 'batting-result.error' ||
      props.resultId === 'batting-result.sacrifice-bunt-error'
        ? '公式記録：守備側の失策1件を確認'
        : '公式記録：失策なし・失策数0を確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
  {
    key: 'interference',
    label: props.adoptInterference
      ? '打撃妨害で実プレイ結果を採用したことを確認'
      : '妨害裁定を要しないことを確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
  {
    key: 'overrides',
    label:
      props.runners.length === 0
        ? '走者なし（進塁上書きなし）を確認'
        : '走者の実結果を確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
  {
    key: 'thirdOut',
    label:
      props.resultId === 'batting-result.batted-out' && props.beforeOuts === '2'
        ? '第3アウトは打者走者の一塁到達前と確認'
        : props.resultId === 'batting-result.double-play'
          ? '打者アウトと一塁走者の二塁封殺を確認'
          : '第3アウトなし（追加タイミング観測なし）を確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
])
function destinations(base: Base): ReadonlyArray<'2' | '3' | '4'> {
  if (props.resultId === 'batting-result.home-run') return ['4']
  if (base === '1') return ['2', '3', '4']
  if (base === '2') return ['3', '4']
  return ['4']
}
const items = ref<readonly BattedBallOption[]>([])
// 実ページから選んだ2欄の値だけを保持し、未取得ページを蓄積しない。
const retained = ref<
  Partial<Record<'typeKey' | 'strengthKey', BattedBallOption>>
>({})
function choices(key: 'typeKey' | 'strengthKey') {
  const selected = retained.value[key]
  return selected && !items.value.some((item) => item.key === selected.key)
    ? [selected, ...items.value]
    : items.value
}
function remember(key: 'typeKey' | 'strengthKey') {
  const selected = items.value.find((item) => item.key === values.value[key])
  if (selected) retained.value[key] = selected
  else if (retained.value[key]?.key !== values.value[key])
    delete retained.value[key]
}
const cursor = ref<string | null>(null),
  nextCursor = ref<string | null>(null)
const previousPages = ref<(string | null)[]>([])
const loading = ref(false),
  failed = ref(false)
let sequence = 0,
  request: AbortController | null = null
function reset() {
  retained.value = {}
  modes.value = {}
  values.value = {}
  confirmations.value = {}
  runnerDestinations.value = {}
  runnerRbiRulings.value = {}
  runnerConfirmed.value = false
  thirdAttempt.value = ''
  errorFielderId.value = ''
  emit('change', null)
}
async function load(page: string | null) {
  const own = ++sequence,
    tenant = auth.teamId,
    epoch = auth.authEpoch
  request?.abort()
  request = new AbortController()
  items.value = []
  loading.value = true
  failed.value = false
  confirmations.value = {}
  try {
    const result = await readBattedBallOptions(page, 25, request.signal)
    if (own !== sequence || auth.teamId !== tenant || auth.authEpoch !== epoch)
      return
    items.value = result.items
    cursor.value = page
    nextCursor.value = result.next_cursor
  } catch {
    if (own === sequence) {
      failed.value = true
      nextCursor.value = null
    }
  } finally {
    if (own === sequence) loading.value = false
  }
}
watch(
  () => [
    props.contextKey,
    props.resultId,
    props.adoptInterference,
    auth.teamId,
    auth.authEpoch,
  ],
  () => {
    previousPages.value = []
    reset()
    void load(null)
  },
  { immediate: true },
)
watch(() => props.fielders, reset, { deep: true })
watch(() => props.runners, reset, { deep: true })
watch(
  [runnerDestinations, runnerRbiRulings],
  () => {
    runnerConfirmed.value = false
  },
  { deep: true, flush: 'sync' },
)
watch(
  values,
  () => {
    confirmations.value = {}
    for (const key of ['typeKey', 'strengthKey'] as const)
      if (retained.value[key]?.key !== values.value[key])
        delete retained.value[key]
  },
  { deep: true, flush: 'sync' },
)
onScopeDispose(() => {
  ++sequence
  request?.abort()
  emit('change', null)
})
function changeMode(key: string) {
  values.value[key] = ''
  confirmations.value = {}
}
const observation = computed<
  | Confirmation
  | BattedOutConfirmation
  | BattedOtherConfirmation
  | BattedDoublePlayConfirmation
  | null
>(() => {
  if (
    props.disabled ||
    (props.resultId === 'batting-result.batted-out' &&
      !['0', '1', '2'].includes(props.beforeOuts)) ||
    questions.value.some((q) => confirmations.value[q.key] !== 'confirmed')
  )
    return null
  let runnerOverrides: RunnerAdvanceOverridesByRunner
  const rbiRulingByRunner: Record<string, string> = {}
  if (props.runners.length === 0) {
    runnerOverrides = { kind: 'not-applied', overrides: [] }
  } else if (props.resultId === 'batting-result.double-play') {
    if (
      !runnerConfirmed.value ||
      props.runners.length !== 1 ||
      props.runners[0]?.base !== '1' ||
      !props.runners[0].runnerId
    )
      return null
    runnerOverrides = { kind: 'not-applied', overrides: [] }
  } else {
    if (!runnerConfirmed.value) return null
    const overrides: Array<{
      runnerBase: Base
      destination: '1' | '2' | '3' | '4'
    }> = []
    for (const runner of props.runners) {
      const destination = runnerDestinations.value[runner.base]
      if (destination === undefined || destination === '') return null
      if (
        destination !== 'hold' &&
        !destinations(runner.base).includes(destination as '2' | '3' | '4')
      )
        return null
      if (
        destination === '4' &&
        props.resultId !== 'batting-result.home-run' &&
        !(
          props.resultId === 'batting-result.batted-out' &&
          props.beforeOuts === '2'
        )
      ) {
        const cause = runnerRbiRulings.value[runner.base]
        if (
          cause !== 'ordinary-play' &&
          cause !== 'kept-running' &&
          cause !== 'stopped-and-restarted'
        )
          return null
        rbiRulingByRunner[runner.base] = cause
      }
      overrides.push({
        runnerBase: runner.base,
        destination: (destination === 'hold' ? runner.base : destination) as
          '1' | '2' | '3' | '4',
      })
    }
    if (overrides.length === 0) return null
    runnerOverrides = { kind: 'applied', overrides }
  }
  const ball: Record<string, string | null> = {}
  for (const key of fields) {
    if (modes.value[key] === 'unobserved') {
      ball[key] = null
      continue
    }
    if (modes.value[key] !== 'observed') return null
    const value = values.value[key]
    if (typeof value !== 'string' || !value || value.trim() !== value)
      return null
    if (
      (key === 'typeKey' || key === 'strengthKey') &&
      (loading.value ||
        failed.value ||
        !choices(key).some((i) => i.key === value))
    )
      return null
    if (
      (key === 'hitX' || key === 'hitY') &&
      !/^(?:0(?:\.[0-9]+)?|1(?:\.0+)?|-0(?:\.0+)?)$/.test(value)
    )
      return null
    if (
      key === 'resolvedFielderId' &&
      !props.fielders.some((p) => p.id === value)
    )
      return null
    ball[key] = value
  }
  if (
    (props.resultId === 'batting-result.error' ||
      props.resultId === 'batting-result.sacrifice-bunt-error') &&
    !props.fielders.some((p) => p.id === errorFielderId.value)
  )
    return null
  const officialScoringPayload =
    props.resultId === 'batting-result.error' ||
    props.resultId === 'batting-result.sacrifice-bunt-error'
      ? {
          kind: 'error-recorded' as const,
          errors: [
            {
              fielder: {
                kind: 'official' as const,
                player_id: errorFielderId.value,
              },
              count: 1 as const,
            },
          ] as [{ fielder: { kind: 'official'; player_id: string }; count: 1 }],
        }
      : {
          kind: 'no-error' as const,
          errorCount: '0' as const,
          fielders: [] as [],
        }
  const thirdOccupied = props.runners.some((runner) => runner.base === '3')
  if (
    props.adoptInterference &&
    thirdOccupied &&
    !['none', 'squeeze', 'steal-home'].includes(thirdAttempt.value)
  )
    return null
  const interferenceRuling = props.adoptInterference
    ? {
        kind: 'batting-interference' as const,
        adopted: { kind: 'play-result' as const, resultId: props.resultId },
        third_base_scoring_attempt: thirdOccupied
          ? {
              kind: 'observed' as const,
              value: thirdAttempt.value as 'none' | 'squeeze' | 'steal-home',
            }
          : { kind: 'not-required' as const },
      }
    : { kind: 'not-required' as const }
  const common = {
    battedBall: {
      typeKey: ball.typeKey!,
      strengthKey: ball.strengthKey!,
      hitX: ball.hitX!,
      hitY: ball.hitY!,
      rawFielderPosition: ball.rawFielderPosition!,
      resolvedFielderId: ball.resolvedFielderId!,
    },
    officialScoringPayload,
    interferenceRuling,
    runnerAdvanceOverridesByRunner: runnerOverrides,
    thirdOutTimingByRunner: {},
    ...(Object.keys(rbiRulingByRunner).length ? { rbiRulingByRunner } : {}),
  }
  if (props.resultId === 'batting-result.batted-out')
    return {
      ...common,
      resultId: props.resultId,
      thirdOutObservation:
        props.beforeOuts === '2'
          ? {
              kind: 'batter-before-first',
              batter: { kind: 'official', player_id: props.batterId },
            }
          : { kind: 'none' },
    } as BattedOutConfirmation
  if (props.resultId === 'batting-result.double-play')
    return {
      ...common,
      resultId: props.resultId,
      thirdOutObservation: { kind: 'none' },
      outRunner: {
        base: '1',
        runnerId: props.runners[0]!.runnerId!,
        outKind: 'force-out',
      },
    } as BattedDoublePlayConfirmation
  return {
    ...common,
    resultId: props.resultId,
    thirdOutObservation: { kind: 'none' },
  } as Confirmation | BattedOtherConfirmation
})
watch(observation, (value) => emit('change', value), {
  deep: true,
  immediate: true,
})
async function next() {
  if (nextCursor.value !== null) {
    previousPages.value.push(cursor.value)
    await load(nextCursor.value)
  }
}
async function previous() {
  if (previousPages.value.length) await load(previousPages.value.pop() ?? null)
}
</script>
<template>
  <fieldset
    :disabled="disabled"
    class="space-y-3 rounded border p-3"
    data-testid="batted-hit-observation"
  >
    <legend>安打の実観測・裁定を確認</legend>
    <p>
      打球と走者の実結果を確認してください。未観測の打球欄は明示してください。
    </p>
    <p v-if="failed" role="alert">
      打球語彙を取得できません。観測値の選択はできません。未観測とは別です。
    </p>
    <button v-if="failed" type="button" @click="load(cursor)">
      打球語彙を再取得
    </button>
    <button
      type="button"
      :disabled="loading || !previousPages.length"
      @click="previous"
    >
      前の打球語彙
    </button>
    <button
      type="button"
      :disabled="loading || nextCursor === null"
      @click="next"
    >
      次の打球語彙
    </button>
    <div v-for="key in fields" :key="key">
      <label
        >{{ labels[key] }}
        <select
          v-model="modes[key]"
          :data-testid="'batted-mode-' + key"
          @change="changeMode(key)"
        >
          <option value="">観測の有無を選択</option>
          <option value="unobserved">未観測として記録</option>
          <option value="observed">観測値を記録</option>
        </select>
      </label>
      <select
        v-if="
          modes[key] === 'observed' &&
          (key === 'typeKey' || key === 'strengthKey')
        "
        v-model="values[key]"
        :disabled="loading || failed"
        :aria-label="labels[key] + 'の値'"
        :data-testid="'batted-value-' + key"
        @change="remember(key)"
      >
        <option value="">実語彙から選択</option>
        <option v-for="item in choices(key)" :key="item.key" :value="item.key">
          {{ item.display_name }}
        </option>
      </select>
      <select
        v-else-if="modes[key] === 'observed' && key === 'resolvedFielderId'"
        v-model="values[key]"
        :aria-label="labels[key] + 'の値'"
        :data-testid="'batted-value-' + key"
      >
        <option value="">守備者を選択</option>
        <option v-for="p in fielders" :key="p.id" :value="p.id">
          {{ p.label }}
        </option>
      </select>
      <input
        v-else-if="modes[key] === 'observed'"
        v-model="values[key]"
        type="text"
        :aria-label="labels[key] + 'の値'"
        :data-testid="'batted-value-' + key"
      />
    </div>
    <label
      v-if="
        resultId === 'batting-result.error' ||
        resultId === 'batting-result.sacrifice-bunt-error'
      "
      class="block"
    >
      公式失策の野手
      <select v-model="errorFielderId" data-testid="batted-error-fielder">
        <option value="">守備側の実野手を選択</option>
        <option v-for="p in fielders" :key="p.id" :value="p.id">
          {{ p.label }}
        </option>
      </select>
    </label>
    <fieldset
      v-if="runners.length"
      class="space-y-2 rounded border p-2"
      data-testid="batted-runner-advances"
    >
      <legend>走者の実結果</legend>
      <p v-if="resultId === 'batting-result.double-play'">
        一塁走者の二塁封殺を実際の記録と照合して確認してください。
      </p>
      <p v-else>
        既定進塁は適用しません。各走者の実際の到達塁を選択してください。
      </p>
      <template v-if="resultId !== 'batting-result.double-play'">
        <label v-for="runner in runners" :key="runner.base" class="block">
          {{ runner.label }}
          <select
            v-model="runnerDestinations[runner.base]"
            :data-testid="`batted-runner-${runner.base}-destination`"
            class="min-h-11 rounded border p-2"
          >
            <option value="">到達塁を選択</option>
            <option v-if="resultId !== 'batting-result.home-run'" value="hold">
              その塁に停止
            </option>
            <option
              v-for="dest in destinations(runner.base)"
              :key="dest"
              :value="dest"
            >
              {{
                dest === '4'
                  ? '本塁（生還）'
                  : ['', '一', '二', '三'][Number(dest)] + '塁'
              }}
            </option>
          </select>
          <select
            v-if="
              runnerDestinations[runner.base] === '4' &&
              resultId !== 'batting-result.home-run' &&
              !(resultId === 'batting-result.batted-out' && beforeOuts === '2')
            "
            v-model="runnerRbiRulings[runner.base]"
            :data-testid="`batted-runner-${runner.base}-rbi-cause`"
            class="min-h-11 rounded border p-2"
            :aria-label="runner.label + 'の打点因果'"
          >
            <option value="">打点の因果を確認</option>
            <option value="ordinary-play">守備の持ち過ぎ・無用送球なし</option>
            <option value="kept-running">
              持ち過ぎ・無用送球中も走り続けた
            </option>
            <option value="stopped-and-restarted">
              一旦停止後、持ち過ぎ・無用送球を見て再発進
            </option>
          </select>
        </label>
      </template>
      <label class="block">
        <input
          v-model="runnerConfirmed"
          type="checkbox"
          data-testid="batted-runner-confirmed"
        />
        {{
          resultId === 'batting-result.double-play'
            ? '一塁走者の封殺を確認した'
            : '上記の走者結果を確認した'
        }}
      </label>
    </fieldset>
    <GameScreenObservationField
      v-for="q in questions"
      :key="q.key"
      :question="q"
      :value="confirmations[q.key] ?? null"
      @change="(v) => (confirmations[q.key] = typeof v === 'string' ? v : '')"
    />
    <label
      v-if="adoptInterference && runners.some((runner) => runner.base === '3')"
      class="block"
    >
      三塁走者の打撃妨害時点の得点企図
      <select
        v-model="thirdAttempt"
        data-testid="batted-interference-third-attempt"
      >
        <option value="">選択してください</option>
        <option value="none">企図なし</option>
        <option value="squeeze">スクイズ</option>
        <option value="steal-home">本盗</option>
      </select>
    </label>
    <p v-if="observation === null">
      観測と裁定の確認が揃うまで確定できません。
    </p>
  </fieldset>
</template>
