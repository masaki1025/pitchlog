<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import type {
  BattedHitObservations,
  BattedHitResult,
} from '../../../contracts/state-transition/lineup_play_prefix_payload_v1.d.ts'
import {
  readBattedBallOptions,
  type BattedBallOption,
} from '../api/battedBallOptions'
import GameScreenObservationField from './GameScreenObservationField.vue'
import { useAuthStore } from '../stores/authStore'

type Confirmation = Omit<
  BattedHitObservations,
  'pitchTypeKey' | 'course' | 'pitchSpeed' | 'stance' | 'battingSide'
>
const props = defineProps<{
  contextKey: string
  resultId: BattedHitResult
  fielders: readonly { id: string; label: string }[]
  disabled?: boolean
}>()
const emit = defineEmits<{ change: [value: Confirmation | null] }>()
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
const questions = [
  {
    key: 'scoring',
    label: '公式記録：失策なし・失策数0を確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
  {
    key: 'interference',
    label: '妨害裁定を要しないことを確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
  {
    key: 'overrides',
    label: '走者進塁の手動上書きなしを確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
  {
    key: 'thirdOut',
    label: '第3アウトなし（追加タイミング観測なし）を確認',
    required: true,
    options: [{ id: 'confirmed', label: '確認した' }],
  },
]
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
  () => [props.contextKey, props.resultId, auth.teamId, auth.authEpoch],
  () => {
    previousPages.value = []
    reset()
    void load(null)
  },
  { immediate: true },
)
watch(() => props.fielders, reset, { deep: true })
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
const observation = computed<Confirmation | null>(() => {
  if (
    props.disabled ||
    questions.some((q) => confirmations.value[q.key] !== 'confirmed')
  )
    return null
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
  return {
    resultId: props.resultId,
    battedBall: {
      typeKey: ball.typeKey!,
      strengthKey: ball.strengthKey!,
      hitX: ball.hitX!,
      hitY: ball.hitY!,
      rawFielderPosition: ball.rawFielderPosition!,
      resolvedFielderId: ball.resolvedFielderId!,
    },
    officialScoringPayload: { kind: 'no-error', errorCount: '0', fielders: [] },
    interferenceRuling: { kind: 'not-required' },
    runnerAdvanceOverridesByRunner: { kind: 'not-applied', overrides: [] },
    thirdOutObservation: { kind: 'none' },
    thirdOutTimingByRunner: {},
  }
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
      無走者の単打・二塁打・三塁打・本塁打に対応します。未観測は各欄で明示してください。
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
    <GameScreenObservationField
      v-for="q in questions"
      :key="q.key"
      :question="q"
      :value="confirmations[q.key] ?? null"
      @change="(v) => (confirmations[q.key] = typeof v === 'string' ? v : '')"
    />
    <p v-if="observation === null">
      観測と裁定の確認が揃うまで確定できません。
    </p>
  </fieldset>
</template>
