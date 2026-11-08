<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { InterferenceConfirmation } from './GameScreenOrdinaryPitchProvider'

type Base = '1' | '2' | '3'
type ResultId = InterferenceConfirmation['resultId']
type Person =
  | { kind: 'batter'; batter_id: { kind: 'official'; player_id: string } }
  | { kind: 'runner'; runner_id: { kind: 'official'; player_id: string } }
const props = defineProps<{
  contextKey: string
  resultId: ResultId
  batterId: string
  runners: readonly { base: Base; runnerId: string; label: string }[]
  disabled?: boolean
}>()
const emit = defineEmits<{ change: [value: InterferenceConfirmation | null] }>()
const confirmed = ref(false)
const thirdAttempt = ref('')
const playKind = ref('')
const obstructedKey = ref('')
const beforeFirst = ref('')
const awards = ref<Record<string, string>>({})
const returns = ref<Record<string, string>>({})
const outs = ref<Record<string, boolean>>({})
watch(obstructedKey, () => {
  beforeFirst.value = ''
})
watch(playKind, () => {
  outs.value = {}
})
const persons = computed(() => [
  { key: 'batter', label: '打者走者' },
  ...props.runners.map((runner) => ({
    key: runner.base,
    label: runner.label,
  })),
])
function person(key: string): Person | null {
  if (key === 'batter')
    return {
      kind: 'batter',
      batter_id: { kind: 'official', player_id: props.batterId },
    }
  const found = props.runners.find((runner) => runner.base === key)
  return found
    ? {
        kind: 'runner',
        runner_id: { kind: 'official', player_id: found.runnerId },
      }
    : null
}
function destination(value: string) {
  return ['first', 'second', 'third', 'home'].includes(value)
}
const observation = computed<InterferenceConfirmation | null>(() => {
  if (props.disabled || !confirmed.value) return null
  if (props.resultId === 'secondary-result.batting-interference') {
    const third = props.runners.some((runner) => runner.base === '3')
    if (
      third &&
      !['none', 'squeeze', 'steal-home'].includes(thirdAttempt.value)
    )
      return null
    return {
      resultId: props.resultId,
      interferenceRuling: {
        kind: 'batting-interference',
        adopted: { kind: 'penalty-award' },
        third_base_scoring_attempt: third
          ? { kind: 'observed', value: thirdAttempt.value }
          : { kind: 'not-required' },
      },
    }
  }
  if (props.resultId === 'secondary-result.obstruction') {
    if (
      !['play-on-obstructed-runner', 'no-play-on-obstructed-runner'].includes(
        playKind.value,
      ) ||
      !persons.value.some((item) => item.key === obstructedKey.value) ||
      persons.value.some(
        (item) =>
          awards.value[item.key] === undefined ||
          (awards.value[item.key] !== 'none' &&
            !destination(awards.value[item.key]!)),
      ) ||
      (obstructedKey.value === 'batter' &&
        !['yes', 'no'].includes(beforeFirst.value)) ||
      (obstructedKey.value !== 'batter' && beforeFirst.value !== '')
    )
      return null
    const obstructed = person(obstructedKey.value)
    if (obstructed === null) return null
    const placements = persons.value.flatMap((item) => {
      const actual = person(item.key)
      const awarded = awards.value[item.key]
      return actual && awarded && awarded !== 'none' && destination(awarded)
        ? [{ person: actual, destination: awarded }]
        : []
    })
    const outTargets = persons.value.flatMap((item) => {
      const actual = person(item.key)
      return actual && outs.value[item.key] ? [actual] : []
    })
    if (
      (playKind.value === 'play-on-obstructed-runner' && outTargets.length) ||
      persons.value.some(
        (item) => outs.value[item.key] && awards.value[item.key] !== 'none',
      ) ||
      (obstructedKey.value === 'batter' && awards.value.batter === 'none')
    )
      return null
    return {
      resultId: props.resultId,
      interferenceRuling: {
        kind: 'obstruction',
        play_kind: playKind.value,
        obstructed,
        awarded_destinations: placements,
        out_targets: outTargets,
        batter_before_first:
          obstructedKey.value === 'batter'
            ? beforeFirst.value === 'yes'
            : 'not-required',
      },
    }
  }
  if (props.resultId === 'secondary-result.offensive-interference') {
    const outTargets = persons.value.flatMap((item) => {
      const actual = person(item.key)
      return actual && outs.value[item.key] ? [actual] : []
    })
    if (
      outTargets.length === 0 ||
      props.runners.some(
        (runner) =>
          !outs.value[runner.base] &&
          !destination(returns.value[runner.base] ?? ''),
      )
    )
      return null
    const returnBases = props.runners.flatMap((runner) => {
      const actual = person(runner.base)
      return actual && !outs.value[runner.base]
        ? [{ person: actual, destination: returns.value[runner.base]! }]
        : []
    })
    return {
      resultId: props.resultId,
      interferenceRuling: {
        kind: 'offensive-interference',
        out_targets: outTargets,
        return_bases: returnBases,
      },
    }
  }
  return null
})
watch(observation, (value) => emit('change', value), { immediate: true })
watch(
  () => [props.contextKey, props.resultId, props.batterId, props.runners],
  () => {
    confirmed.value = false
    thirdAttempt.value = ''
    playKind.value = ''
    obstructedKey.value = ''
    beforeFirst.value = ''
    awards.value = {}
    returns.value = {}
    outs.value = {}
    emit('change', null)
  },
  { deep: true },
)
</script>

<template>
  <fieldset class="space-y-2 rounded border p-3" :disabled="disabled">
    <legend>審判の妨害裁定を記録</legend>
    <template v-if="resultId === 'secondary-result.batting-interference'">
      <p>打撃妨害の罰則採用を明示します。</p>
      <label v-if="runners.some((runner) => runner.base === '3')" class="block"
        >三塁走者の得点企図
        <select v-model="thirdAttempt" data-testid="interference-third-attempt">
          <option value="">選択してください</option>
          <option value="none">企図なし</option>
          <option value="squeeze">スクイズ</option>
          <option value="steal-home">本盗</option>
        </select>
      </label>
    </template>
    <template v-else-if="resultId === 'secondary-result.obstruction'">
      <label class="block"
        >妨害走者へのプレイ
        <select v-model="playKind" data-testid="obstruction-play-kind">
          <option value="">選択してください</option>
          <option value="play-on-obstructed-runner">プレイあり</option>
          <option value="no-play-on-obstructed-runner">プレイなし</option>
        </select>
      </label>
      <label class="block"
        >妨害された対象
        <select v-model="obstructedKey" data-testid="obstruction-person">
          <option value="">選択してください</option>
          <option v-for="item in persons" :key="item.key" :value="item.key">
            {{ item.label }}
          </option>
        </select>
      </label>
      <label v-if="obstructedKey === 'batter'" class="block"
        >打者走者の一塁到達前
        <select v-model="beforeFirst" data-testid="obstruction-before-first">
          <option value="">選択してください</option>
          <option value="yes">はい</option>
          <option value="no">いいえ</option>
        </select>
      </label>
      <div v-for="item in persons" :key="item.key">
        <label class="block"
          >{{ item.label }}への授与塁
          <select
            v-model="awards[item.key]"
            :data-testid="`obstruction-award-${item.key}`"
          >
            <option value="">選択してください</option>
            <option value="none">授与なしと確認</option>
            <option value="first">一塁</option>
            <option value="second">二塁</option>
            <option value="third">三塁</option>
            <option value="home">本塁</option>
          </select>
        </label>
        <label v-if="playKind === 'no-play-on-obstructed-runner'" class="block"
          ><input v-model="outs[item.key]" type="checkbox" />
          {{ item.label }}を最終裁定でアウト
        </label>
      </div>
    </template>
    <template v-else>
      <div v-for="item in persons" :key="item.key">
        <label class="block"
          ><input v-model="outs[item.key]" type="checkbox" />
          {{ item.label }}をアウトと宣告
        </label>
        <label v-if="item.key !== 'batter' && !outs[item.key]" class="block"
          >{{ item.label }}の帰塁先
          <select
            v-model="returns[item.key]"
            :data-testid="`offensive-return-${item.key}`"
          >
            <option value="">選択してください</option>
            <option value="first">一塁</option>
            <option value="second">二塁</option>
            <option value="third">三塁</option>
            <option value="home">本塁</option>
          </select>
        </label>
      </div>
    </template>
    <label class="block"
      ><input
        v-model="confirmed"
        type="checkbox"
        data-testid="interference-confirm"
      />
      上記の裁定対象と到達先を記録員が確認
    </label>
    <p v-if="observation !== null" data-testid="interference-observation-ready">
      裁定の原入力を確認しました。保存はこれからです。
    </p>
  </fieldset>
</template>
