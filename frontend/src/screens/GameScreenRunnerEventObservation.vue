<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { isRunnerObservation } from '../api/runnerEventWire'
import type {
  LiveRunnerIdentity,
  RunnerDestination,
  RunnerOutcomeMap,
  RunnerOutKind,
} from '../domain/runnerEvent'
import type {
  RunnerObservationWire,
  RunnerPerPitch,
} from '../api/runnerEventWire'
const props = defineProps<{
  runners: readonly LiveRunnerIdentity[]
  primaryResultId: string
  sourceKey: string
  disabled?: boolean
}>()
const emit = defineEmits<{ confirmed: [observation: RunnerObservationWire] }>()
const operation = ref('')
const third = ref('')
const thirdRunner = ref('')
const noError = ref(false)
const error = ref('')
const outcomes = reactive<
  Record<
    string,
    { kind: string; destination: string; cause: string; timing: string }
  >
>({})
const modes = [
  ['steal-pitch', '盗塁（投球あり）'],
  ['steal-nonpitch', '盗塁（投球なし）'],
  ['secondary-result.wild-pitch', '暴投'],
  ['secondary-result.passed-ball', '捕逸'],
  ['secondary-result.balk', 'ボーク'],
  ['pitcher-pickoff-destination.first', '投手の一塁牽制'],
  ['pitcher-pickoff-destination.second', '投手の二塁牽制'],
  ['pitcher-pickoff-destination.third', '投手の三塁牽制'],
  ['catcher-pickoff-destination.first', '捕手の一塁牽制'],
  ['catcher-pickoff-destination.second', '捕手の二塁牽制'],
  ['catcher-pickoff-destination.third', '捕手の三塁牽制'],
  ['batting-result.strikeout-double-play', '三振と走者アウト'],
]
const bases = [
  ['first', '一塁'],
  ['second', '二塁'],
  ['third', '三塁'],
  ['home', '本塁'],
]
const causes = [
  ['caught-stealing', '盗塁死'],
  ['pitcher-pickoff-out', '投手牽制死'],
  ['catcher-pickoff-out', '捕手牽制死'],
  ['running-out', '走塁死'],
]
const contextKey = computed(
  () =>
    props.sourceKey +
    '|' +
    props.runners
      .map((r) => r.base + ':' + r.runnerId + ':' + r.responsiblePitcherId)
      .join('|'),
)
watch(
  contextKey,
  () => {
    for (const key of Object.keys(outcomes)) delete outcomes[key]
    for (const r of props.runners)
      outcomes[r.base] = { kind: '', destination: '', cause: '', timing: '' }
    noError.value = false
    third.value = ''
    thirdRunner.value = ''
    error.value = ''
  },
  { immediate: true },
)
function confirm() {
  error.value = ''
  if (
    !modes.some(([value]) => value === operation.value) ||
    !noError.value ||
    !third.value ||
    props.runners.length === 0
  ) {
    error.value =
      '操作・走者結果・第3アウト・失策と妨害の有無を確認してください'
    return
  }
  const byRunner: RunnerOutcomeMap = {}
  const timing: Partial<
    Record<
      'first' | 'second' | 'third',
      'home-before-third-out' | 'not-before-third-out'
    >
  > = {}
  for (const runner of props.runners) {
    const o = outcomes[runner.base]
    if (!o || !['hold', 'safe-advance', 'out'].includes(o.kind)) {
      error.value = '各走者の実結果を選択してください'
      return
    }
    const slot =
      runner.base === '1' ? 'first' : runner.base === '2' ? 'second' : 'third'
    const player = { kind: 'official' as const, player_id: runner.runnerId }
    if (o.kind === 'hold') byRunner[slot] = { kind: 'hold', runner: player }
    else {
      if (!bases.some(([value]) => value === o.destination)) {
        error.value = '到達または企図した塁を選択してください'
        return
      }
      if (o.kind === 'safe-advance')
        byRunner[slot] = {
          kind: 'safe-advance',
          runner: player,
          destination: o.destination as RunnerDestination,
        }
      else {
        if (!causes.some(([value]) => value === o.cause)) {
          error.value = 'アウトの原因を選択してください'
          return
        }
        byRunner[slot] = {
          kind: 'out',
          runner: player,
          attempted_base: o.destination as RunnerDestination,
          out_kind: o.cause as RunnerOutKind,
        }
      }
    }
    if (
      o.timing === 'home-before-third-out' ||
      o.timing === 'not-before-third-out'
    )
      timing[slot] = o.timing
  }
  let thirdOut: RunnerPerPitch['thirdOutObservation']
  if (third.value === 'none') thirdOut = { kind: 'none' }
  else if (third.value === 'not-required') thirdOut = { kind: 'not-required' }
  else {
    const person = props.runners.find((r) => r.runnerId === thirdRunner.value)
    if (!person) {
      error.value = '第3アウトの対象走者を選択してください'
      return
    }
    const runner = { kind: 'official' as const, player_id: person.runnerId }
    if (third.value === 'other-third-out')
      thirdOut = { kind: 'other-third-out', out_person: runner }
    else if (third.value === 'missed-base-appeal')
      thirdOut = { kind: 'missed-base-appeal', runner }
    else {
      error.value = '第3アウトの種類を確認してください'
      return
    }
  }
  const primary =
    operation.value === 'steal-pitch' ||
    operation.value === 'secondary-result.wild-pitch' ||
    operation.value === 'secondary-result.passed-ball'
  const steal = operation.value.startsWith('steal-')
  const so = operation.value === 'batting-result.strikeout-double-play'
  const eventKind: RunnerPerPitch['kind'] =
    operation.value === 'steal-pitch' || so
      ? 'batting-result'
      : operation.value.startsWith('secondary-result.')
        ? 'secondary-result'
        : 'runner-event'
  const id = steal ? 'strategy-category.steal' : operation.value
  const payload = {
    primaryResultId: primary ? props.primaryResultId : null,
    perPitch: {
      kind: eventKind,
      pitchEventKind: primary || so ? 'pitch-event' : 'non-pitch-event',
      resultId: operation.value === 'steal-pitch' ? props.primaryResultId : id,
      runnerEventPayload:
        steal || eventKind === 'runner-event'
          ? { kind: 'runner-event', event_kind: id, by_runner: byRunner }
          : { kind: 'not-applicable' },
      runnerAdvanceOverridesByRunner:
        steal || eventKind === 'runner-event'
          ? { kind: 'not-applied' }
          : { kind: 'overridden', by_runner: byRunner },
      thirdOutObservation: thirdOut,
      thirdOutTimingByRunner: timing,
      officialScoringPayload: { kind: 'no-error' },
      interferenceRuling: { kind: 'not-required' },
      rbi: {
        doublePlayRelayError: 'not-required',
        runnerContinuityByRunner: { kind: 'not-required' },
        wouldScoreWithoutErrorByRunner: { kind: 'not-required' },
        cause_by_runner: { kind: 'not-required' },
        restart_by_runner: { kind: 'not-required' },
      },
      homeTouchOrder: { kind: 'not-required' },
    },
  }
  if (!isRunnerObservation(payload)) {
    error.value = '実結果の正式入力形式を確認できません'
    return
  }
  emit('confirmed', payload)
}
</script>
<template>
  <fieldset :disabled="disabled" data-testid="runner-operation-observation">
    <legend>走者の実結果</legend>
    <label
      >操作<select v-model="operation" data-testid="runner-operation-kind">
        <option value="">選択してください</option>
        <option v-for="[value, label] in modes" :key="value" :value="value">
          {{ label }}
        </option>
      </select></label
    >
    <div v-for="runner in runners" :key="runner.runnerId">
      <p>{{ runner.base }}塁走者</p>
      <template v-if="outcomes[runner.base]">
        <label
          >実結果<select
            v-model="outcomes[runner.base]!.kind"
            :data-testid="`runner-${runner.base}-outcome`"
          >
            <option value="">未確認</option>
            <option value="hold">停止</option>
            <option value="safe-advance">セーフ進塁</option>
            <option value="out">アウト</option>
          </select></label
        >
        <label v-if="outcomes[runner.base]!.kind !== 'hold'"
          >到達・企図塁<select
            v-model="outcomes[runner.base]!.destination"
            :data-testid="`runner-${runner.base}-destination`"
          >
            <option value="">未確認</option>
            <option v-for="[value, label] in bases" :key="value" :value="value">
              {{ label }}
            </option>
          </select></label
        >
        <label v-if="outcomes[runner.base]!.kind === 'out'"
          >アウト原因<select
            v-model="outcomes[runner.base]!.cause"
            :data-testid="`runner-${runner.base}-cause`"
          >
            <option value="">未確認</option>
            <option
              v-for="[value, label] in causes"
              :key="value"
              :value="value"
            >
              {{ label }}
            </option>
          </select></label
        >
        <label v-if="outcomes[runner.base]!.destination === 'home'"
          >第3アウトとの時機<select
            v-model="outcomes[runner.base]!.timing"
            :data-testid="`runner-${runner.base}-timing`"
          >
            <option value="">非該当・未確認</option>
            <option value="home-before-third-out">
              第3アウトより前に本塁到達
            </option>
            <option value="not-before-third-out">
              第3アウトより前ではない
            </option>
          </select></label
        >
      </template>
    </div>
    <label
      >第3アウト<select v-model="third" data-testid="runner-third-out">
        <option value="">選択してください</option>
        <option value="none">第3アウトなし</option>
        <option value="not-required">得点判定に非該当</option>
        <option value="other-third-out">その他の第3アウト</option>
        <option value="missed-base-appeal">踏み忘れアピール</option>
      </select></label
    >
    <label v-if="third === 'other-third-out' || third === 'missed-base-appeal'"
      >対象走者<select
        v-model="thirdRunner"
        data-testid="runner-third-out-person"
      >
        <option value="">未確認</option>
        <option
          v-for="runner in runners"
          :key="runner.runnerId"
          :value="runner.runnerId"
        >
          {{ runner.base }}塁走者
        </option>
      </select></label
    >
    <label
      ><input
        v-model="noError"
        type="checkbox"
        data-testid="runner-no-error"
      />失策・妨害を含まないことを確認した</label
    >
    <p>
      未確認の結果は補いません。通常ファウルの進塁や、現在未対応の複合操作は記録できません。
    </p>
    <p v-if="error" role="alert">{{ error }}</p>
    <button
      type="button"
      data-testid="runner-observation-confirm"
      @click="confirm"
    >
      この実結果を確認
    </button>
  </fieldset>
</template>
