<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    balls: number
    strikes: number
    outs: number
    compact?: boolean
  }>(),
  { compact: false },
)
const items = computed(() => [
  {
    label: 'B',
    name: 'ボール',
    count: props.balls,
    max: 3,
    labelClass: 'text-emerald-700 dark:text-emerald-300',
    activeBarClass: 'bg-emerald-600 dark:bg-emerald-500',
    limitClass:
      'bg-emerald-50 ring-1 ring-inset ring-emerald-300 dark:bg-emerald-950/40 dark:ring-emerald-700',
  },
  {
    label: 'S',
    name: 'ストライク',
    count: props.strikes,
    max: 2,
    labelClass: 'text-amber-700 dark:text-amber-300',
    activeBarClass: 'bg-amber-500',
    limitClass:
      'bg-amber-50 ring-1 ring-inset ring-amber-300 dark:bg-amber-950/40 dark:ring-amber-700',
  },
  {
    label: 'O',
    name: 'アウト',
    count: props.outs,
    max: 2,
    labelClass: 'text-red-700 dark:text-red-300',
    activeBarClass: 'bg-red-600 dark:bg-red-500',
    limitClass:
      'bg-red-50 ring-1 ring-inset ring-red-300 dark:bg-red-950/40 dark:ring-red-700',
  },
])
</script>

<template>
  <div
    v-if="compact"
    class="flex min-w-[130px] items-center justify-center"
    role="group"
    :aria-label="`カウント ボール${balls}、ストライク${strikes}、アウト${outs}`"
  >
    <div
      class="grid h-8 w-full max-w-44 grid-cols-3 overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm dark:border-slate-600 dark:bg-slate-900"
    >
      <div
        v-for="item in items"
        :key="item.label"
        class="grid min-w-0 grid-rows-[1fr_3px] gap-0.5 border-l border-slate-200 px-1 py-1 first:border-l-0 dark:border-slate-700"
        :class="item.count === item.max ? item.limitClass : ''"
        role="img"
        :aria-label="`${item.name} ${item.count}`"
        :title="`${item.label}：${item.name} ${item.count}`"
      >
        <span
          class="flex min-w-0 items-center justify-center gap-1 leading-none"
          aria-hidden="true"
        >
          <span :class="['text-[10px] font-black', item.labelClass]">{{
            item.label
          }}</span>
          <span
            class="text-base font-black leading-none text-slate-950 tabular-nums dark:text-white"
            >{{ item.count }}</span
          >
        </span>
        <span
          :class="[
            'grid gap-0.5',
            item.max === 3 ? 'grid-cols-3' : 'grid-cols-2',
          ]"
          aria-hidden="true"
        >
          <span
            v-for="index in item.max"
            :key="index"
            :class="[
              'rounded-full',
              index <= item.count
                ? item.activeBarClass
                : 'bg-slate-200 dark:bg-slate-700',
            ]"
          />
        </span>
      </div>
    </div>
  </div>
  <div
    v-else
    class="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
  >
    <div class="flex flex-col gap-1">
      <div
        v-for="item in items"
        :key="item.label"
        class="flex items-center gap-1.5"
        role="img"
        :aria-label="`${item.name} ${item.count}`"
      >
        <span
          class="w-4 text-sm font-bold text-slate-500 dark:text-slate-400"
          >{{ item.label }}</span
        >
        <span
          v-for="index in item.max"
          :key="index"
          :class="[
            'h-4 w-4 rounded-full border',
            index <= item.count
              ? item.activeBarClass
              : 'border-slate-300 bg-slate-100 dark:border-slate-600 dark:bg-slate-800',
          ]"
        />
      </div>
    </div>
    <slot />
  </div>
</template>
