<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Delete } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    value: string
    lastSpeed?: string
    disabled?: boolean
  }>(),
  { lastSpeed: '', disabled: false },
)
const emit = defineEmits<{ change: [value: string] }>()
const DEFAULT_SPEED = 140
const CANDIDATE_COUNT = 20
const RANGE_STEP = 10
const MIN_SPEED = 1
const MAX_SPEED = 999
const rangeOffset = ref(0)
const directInput = ref(false)
const digits = ref('')

function toSpeed(value: string | undefined): number | null {
  if (!value || !/^\d{1,3}$/.test(value)) return null
  const speed = Number(value)
  return speed >= MIN_SPEED && speed <= MAX_SPEED ? speed : null
}
const lastSpeed = computed(() => toSpeed(props.lastSpeed))
const anchorSpeed = computed(() => lastSpeed.value ?? DEFAULT_SPEED)
watch(anchorSpeed, () => {
  rangeOffset.value = 0
})
const candidates = computed(() => {
  const unclampedStart = anchorSpeed.value - RANGE_STEP + rangeOffset.value
  const start = Math.min(
    MAX_SPEED - CANDIDATE_COUNT + 1,
    Math.max(MIN_SPEED, unclampedStart),
  )
  return Array.from({ length: CANDIDATE_COUNT }, (_, index) => start + index)
})
const rangeLabel = computed(
  () =>
    `${candidates.value[0]}–${candidates.value[candidates.value.length - 1]}`,
)
const displayValue = computed(() =>
  directInput.value ? digits.value : props.value,
)
function digit(value: string) {
  if (digits.value.length >= 3) return
  digits.value += value
  emit('change', digits.value)
}
function removeDigit() {
  digits.value = digits.value.slice(0, -1)
  emit('change', digits.value)
}
function select(value: string) {
  directInput.value = false
  digits.value = ''
  emit('change', value)
}
watch(
  () => props.value,
  (value) => {
    if (!directInput.value) digits.value = ''
    if (value === '') digits.value = ''
  },
)
</script>

<template>
  <div
    class="w-[244px] shrink-0 [@media(min-width:1120px)_and_(min-height:961px)]:w-[260px]"
  >
    <div class="mb-1 flex min-h-6 shrink-0 items-center justify-between px-1">
      <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">
        球速{{ lastSpeed !== null ? `（直前 ${lastSpeed}）` : '' }}
      </span>
      <span
        class="font-mono text-lg font-bold leading-6 tabular-nums text-slate-800 dark:text-slate-100"
      >
        {{ displayValue || '未計測'
        }}<span
          v-if="displayValue"
          class="ml-0.5 text-xs font-normal text-slate-400"
          >km/h</span
        >
      </span>
    </div>

    <div
      v-if="directInput"
      class="grid grid-cols-3 gap-1 rounded-xl border border-slate-300 bg-slate-100 p-1 dark:border-slate-600 dark:bg-slate-900"
    >
      <button
        v-for="d in ['1', '2', '3', '4', '5', '6', '7', '8', '9']"
        :key="d"
        type="button"
        :disabled="disabled"
        class="min-h-11 rounded-lg border border-slate-300 bg-white text-base font-bold hover:bg-sky-50 active:bg-sky-100 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-sky-900/40"
        @click="digit(d)"
      >
        {{ d }}
      </button>
      <button
        type="button"
        class="min-h-11 rounded-lg border border-slate-300 bg-slate-50 text-xs font-bold text-slate-500 hover:bg-slate-200 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-400"
        title="球速入力をクリア"
        aria-label="球速入力をクリア"
        :disabled="disabled"
        @click="select('')"
      >
        C
      </button>
      <button
        type="button"
        class="min-h-11 rounded-lg border border-slate-300 bg-white text-base font-bold hover:bg-sky-50 active:bg-sky-100 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-sky-900/40"
        :disabled="disabled"
        @click="digit('0')"
      >
        0
      </button>
      <button
        type="button"
        class="flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-slate-50 text-slate-500 hover:bg-slate-200 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-400"
        aria-label="1文字削除"
        :disabled="disabled"
        @click="removeDigit"
      >
        <Delete :size="18" />
      </button>
    </div>
    <template v-else>
      <div class="mb-1 grid grid-cols-[44px_1fr_44px] gap-1">
        <button
          type="button"
          class="flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-slate-50 text-xs font-bold text-slate-600 hover:bg-slate-200 active:bg-slate-300 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
          aria-label="球速候補を10キロ下げる"
          :disabled="disabled"
          @click="rangeOffset -= RANGE_STEP"
        >
          −10
        </button>
        <div
          class="flex min-h-11 items-center justify-center rounded-lg bg-slate-100 px-2 font-mono text-sm font-bold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300"
        >
          {{ rangeLabel }} km/h
        </div>
        <button
          type="button"
          class="flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-slate-50 text-xs font-bold text-slate-600 hover:bg-slate-200 active:bg-slate-300 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300"
          aria-label="球速候補を10キロ上げる"
          :disabled="disabled"
          @click="rangeOffset += RANGE_STEP"
        >
          +10
        </button>
      </div>
      <div
        class="grid grid-cols-5 gap-1 rounded-xl border border-slate-300 bg-slate-100 p-1 dark:border-slate-600 dark:bg-slate-900"
      >
        <button
          v-for="speed in candidates"
          :key="speed"
          type="button"
          :disabled="disabled"
          :aria-label="`球速${speed}キロ`"
          :aria-pressed="value === String(speed)"
          :class="[
            'min-h-11 min-w-0 rounded-lg font-mono text-sm font-bold tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-1 disabled:opacity-40',
            value === String(speed)
              ? 'bg-sky-600 text-white shadow-sm'
              : lastSpeed === speed
                ? 'bg-sky-100 text-sky-800 ring-1 ring-inset ring-sky-400 dark:bg-sky-950 dark:text-sky-200'
                : 'bg-white text-slate-700 hover:bg-sky-50 active:bg-sky-100 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-sky-900/40',
          ]"
          @click="select(String(speed))"
        >
          {{ speed }}
        </button>
      </div>
    </template>

    <div class="mt-1 grid grid-cols-2 gap-1">
      <button
        type="button"
        :disabled="disabled"
        :class="[
          'min-h-11 rounded-lg border text-xs font-bold transition-colors disabled:opacity-40',
          value === ''
            ? 'border-slate-500 bg-slate-600 text-white dark:border-slate-400 dark:bg-slate-300 dark:text-slate-950'
            : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300',
        ]"
        @click="select('')"
      >
        未計測
      </button>
      <button
        type="button"
        class="min-h-11 rounded-lg border border-slate-300 bg-white text-xs font-bold text-slate-600 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300"
        :aria-expanded="directInput"
        :disabled="disabled"
        @click="directInput = !directInput"
      >
        {{ directInput ? '候補に戻る' : '3桁テンキー' }}
      </button>
    </div>
  </div>
</template>
