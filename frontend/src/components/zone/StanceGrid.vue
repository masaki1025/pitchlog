<script setup lang="ts">
import { computed } from 'vue'
import {
  courseInputViewLabel,
  stanceScreenZoneToStoredZone,
  type CourseInputView,
} from '../../lib/courseInputView'

const props = withDefaults(
  defineProps<{
    value: number
    viewpoint: CourseInputView
    highlight?: boolean
    disabled?: boolean
  }>(),
  { highlight: false, disabled: false },
)
const emit = defineEmits<{ change: [zone: number] }>()
const viewpointLabel = computed(() => courseInputViewLabel(props.viewpoint))
const leftFieldSide = computed(() =>
  props.viewpoint === 'pitcher' ? '1塁側' : '3塁側',
)
const rightFieldSide = computed(() =>
  props.viewpoint === 'pitcher' ? '3塁側' : '1塁側',
)
const zones = Array.from({ length: 25 }, (_, index) => index + 1)
function storedZone(screenZone: number): number {
  return stanceScreenZoneToStoredZone(screenZone, props.viewpoint)
}
function zoneClass(screenZone: number): string {
  const row = Math.floor((screenZone - 1) / 5)
  const column = (screenZone - 1) % 5
  const core = row >= 1 && row <= 3 && column >= 1 && column <= 3
  return props.value === storedZone(screenZone)
    ? 'bg-sky-600 text-white shadow-sm ring-2 ring-sky-700/20'
    : core
      ? 'bg-white text-slate-600 hover:bg-sky-100 active:bg-sky-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-sky-900'
      : 'bg-slate-50 text-slate-500 hover:bg-sky-100 active:bg-sky-200 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-sky-900'
}
</script>

<template>
  <div
    class="w-[244px] shrink-0 [@media(min-width:1120px)_and_(min-height:961px)]:w-[260px]"
    :class="{ 'missing-highlight': highlight }"
    :data-viewpoint="viewpoint"
  >
    <div
      class="mb-1 flex min-h-6 items-center justify-between px-1 text-xs font-semibold text-slate-500 dark:text-slate-400"
    >
      <span>構え（5×5）</span>
      <span
        class="font-mono font-bold tabular-nums text-slate-700 dark:text-slate-200"
      >
        {{ viewpointLabel }}・{{ value > 0 ? `Zone ${value}` : '未入力' }}
      </span>
    </div>
    <div
      class="relative grid grid-cols-5 gap-1 rounded-xl border border-slate-300 bg-slate-200 p-1 dark:border-slate-600 dark:bg-slate-700"
    >
      <button
        v-for="screenZone in zones"
        :key="screenZone"
        type="button"
        :disabled="disabled"
        :aria-label="`構えゾーン${storedZone(screenZone)}（${viewpointLabel}視点）`"
        :aria-pressed="value === storedZone(screenZone)"
        :data-screen-zone="screenZone"
        :data-stored-zone="storedZone(screenZone)"
        :class="[
          'h-11 w-11 rounded-lg text-xs font-bold tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-1 [@media(min-width:1120px)_and_(min-height:961px)]:h-[46px] [@media(min-width:1120px)_and_(min-height:961px)]:w-[46px]',
          zoneClass(screenZone),
        ]"
        @click="emit('change', storedZone(screenZone))"
      >
        {{ storedZone(screenZone) }}
      </button>
      <div
        class="pointer-events-none absolute inset-0 z-10 col-start-2 col-end-5 row-start-2 row-end-5 rounded-[3px] border-2 border-red-500 shadow-[0_0_0_1px_rgba(255,255,255,0.75)] dark:border-red-400 dark:shadow-[0_0_0_1px_rgba(15,23,42,0.8)]"
        aria-hidden="true"
      />
    </div>
    <div
      class="mt-1 flex justify-between px-1 text-[10px] font-medium text-slate-400"
    >
      <span>{{ leftFieldSide }}</span>
      <span>{{ rightFieldSide }}</span>
    </div>
  </div>
</template>
