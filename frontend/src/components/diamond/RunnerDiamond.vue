<script setup lang="ts">
import { computed } from 'vue'

interface RunnerView {
  name: string
  temporary?: string | null
}
const props = withDefaults(
  defineProps<{
    first?: RunnerView | null
    second?: RunnerView | null
    third?: RunnerView | null
    batter?: string | null
    compact?: boolean
  }>(),
  {
    first: null,
    second: null,
    third: null,
    batter: null,
    compact: false,
  },
)
const pos = {
  second: { x: 110, y: 25 },
  first: { x: 185, y: 90 },
  third: { x: 35, y: 90 },
  batter: { x: 110, y: 155 },
} as const
type BaseKey = keyof typeof pos
const bases = computed(() => [
  { key: 'second' as const, runner: props.second, label: '2塁走者' },
  { key: 'third' as const, runner: props.third, label: '3塁走者' },
  { key: 'first' as const, runner: props.first, label: '1塁走者' },
  { key: 'batter' as const, runner: null, label: '打者' },
])
function left(base: BaseKey): string {
  return `${(pos[base].x / 220) * 100}%`
}
function top(base: BaseKey): string {
  return `${(pos[base].y / 170) * 100}%`
}
function runnerName(base: BaseKey): string | null {
  if (base === 'batter') return props.batter || null
  return props[base]?.name || null
}
</script>

<template>
  <div
    :class="[
      'relative mx-auto aspect-[220/170] w-full select-none',
      compact ? 'max-w-60' : 'max-w-72',
    ]"
  >
    <svg viewBox="0 0 220 170" class="absolute inset-0 h-full w-full">
      <path
        :d="`M ${pos.batter.x} ${pos.batter.y} L ${pos.first.x} ${pos.first.y} L ${pos.second.x} ${pos.second.y} L ${pos.third.x} ${pos.third.y} Z`"
        class="fill-emerald-50 stroke-slate-300 dark:fill-emerald-950/30 dark:stroke-slate-600"
        stroke-width="2"
      />
    </svg>
    <div
      v-for="base in bases"
      :key="base.key"
      class="absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-lg px-1.5 py-0.5 text-center"
      :style="{ left: left(base.key), top: top(base.key) }"
    >
      <span
        :class="[
          'mx-auto block h-5 w-5 rotate-45 rounded-[3px] border-2',
          base.key === 'batter' || runnerName(base.key)
            ? 'border-red-600 bg-red-500'
            : 'border-slate-400 bg-white dark:border-slate-500 dark:bg-slate-800',
        ]"
      />
      <span
        v-if="runnerName(base.key)"
        class="mt-0.5 block max-w-20 truncate text-xs font-semibold"
      >
        <span
          v-if="base.key !== 'batter' && props[base.key]?.temporary"
          class="mr-1 rounded bg-violet-600 px-1 py-0.5 text-[9px] font-extrabold text-white"
          >臨走</span
        >
        {{ runnerName(base.key) }}
      </span>
    </div>
    <div
      v-if="!compact"
      class="absolute inset-x-0 bottom-0 flex justify-between text-[10px] font-semibold text-slate-400"
    >
      <span>3塁側</span>
      <span>1塁側</span>
    </div>
  </div>
</template>
