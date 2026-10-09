<script setup lang="ts">
import { computed } from 'vue'
import { cx } from '../../lib/format'

type Variant = 'primary' | 'result' | 'secondary' | 'ghost' | 'danger' | 'chip'

const props = withDefaults(
  defineProps<{
    variant?: Variant
    keyHint?: string
    active?: boolean
  }>(),
  { variant: 'secondary', keyHint: undefined, active: false },
)

const base =
  'relative select-none rounded-xl font-bold transition-colors disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500'

const variants: Record<Variant, string> = {
  // 主要ボタンは高さ 60px 以上にする。
  primary:
    'min-h-[60px] px-4 text-lg bg-sky-600 text-white hover:bg-sky-700 active:bg-sky-800',
  result:
    'min-h-[60px] px-3 text-xl bg-white text-slate-900 border-2 border-slate-300 hover:bg-slate-50 active:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700',
  secondary:
    'min-h-12 px-3 text-base bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 active:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700',
  ghost:
    'min-h-12 px-3 text-base text-slate-700 hover:bg-slate-200 active:bg-slate-300 dark:text-slate-200 dark:hover:bg-slate-800',
  danger:
    'min-h-12 px-3 text-base bg-red-600 text-white hover:bg-red-700 active:bg-red-800',
  chip: 'min-h-11 px-3 text-sm bg-white text-slate-800 border border-slate-300 hover:bg-slate-50 active:bg-slate-200 dark:bg-slate-800 dark:text-slate-100 dark:border-slate-600 dark:hover:bg-slate-700',
}

const activeCls =
  'bg-sky-100 border-sky-500 text-sky-900 dark:bg-sky-900/60 dark:border-sky-400 dark:text-sky-100'

// 旧は active の sky 系クラスが variant 側に負け、見た目が効かなかった。
// active 時は競合する色クラスだけを外す（計画書 決定 L）。
const activeColorRemovals: Record<Variant, readonly string[]> = {
  primary: ['bg-sky-600', 'text-white'],
  result: [
    'bg-white',
    'text-slate-900',
    'border-slate-300',
    'dark:bg-slate-800',
    'dark:text-slate-100',
    'dark:border-slate-600',
  ],
  secondary: [
    'bg-white',
    'text-slate-800',
    'border-slate-300',
    'dark:bg-slate-800',
    'dark:text-slate-100',
    'dark:border-slate-600',
  ],
  ghost: ['text-slate-700', 'dark:text-slate-200'],
  danger: ['bg-red-600', 'text-white'],
  chip: [
    'bg-white',
    'text-slate-800',
    'border-slate-300',
    'dark:bg-slate-800',
    'dark:text-slate-100',
    'dark:border-slate-600',
  ],
}

const variantClass = computed(() => {
  const variant = props.variant
  if (!props.active) return variants[variant]

  return variants[variant]
    .split(' ')
    .filter((classToken) => !activeColorRemovals[variant].includes(classToken))
    .join(' ')
})

const buttonClass = computed(() =>
  cx(base, variantClass.value, props.active && activeCls),
)
</script>

<template>
  <button type="button" :class="buttonClass">
    <slot />
    <span
      v-if="keyHint"
      class="pointer-events-none absolute right-1.5 top-1 hidden rounded border border-slate-300 bg-slate-100 px-1 text-[10px] font-mono font-normal leading-4 text-slate-500 lg:inline dark:border-slate-600 dark:bg-slate-900 dark:text-slate-400"
    >
      {{ keyHint }}
    </span>
  </button>
</template>
