<script lang="ts">
import { inject, type InjectionKey } from 'vue'

export type ToastTone = 'info' | 'success' | 'error' | 'warning'

export interface ToastApi {
  push(message: string, tone?: ToastTone, durationMs?: number): void
}

export const toastKey: InjectionKey<ToastApi> = Symbol('toast')

export function useToast(): ToastApi {
  const api = inject(toastKey)
  if (!api) {
    throw new Error('ToastProvider の外では useToast() を使用できません')
  }
  return api
}
</script>

<script setup lang="ts">
import { provide, ref } from 'vue'
import { cx } from '../../lib/format'

interface ToastItem {
  id: number
  message: string
  tone: ToastTone
}

const toneCls: Record<ToastTone, string> = {
  info: 'bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900',
  success: 'bg-emerald-600 text-white',
  error: 'bg-red-600 text-white',
  warning: 'bg-amber-500 text-slate-900',
}

const toastBaseClass = 'rounded-xl px-4 py-3 text-sm font-semibold shadow-lg'
const items = ref<ToastItem[]>([])
let nextId = 1

function push(
  message: string,
  tone: ToastTone = 'info',
  durationMs?: number,
): void {
  const id = nextId
  nextId += 1
  items.value = [...items.value.slice(-4), { id, message, tone }]

  const ttl = durationMs ?? (tone === 'error' ? 6000 : 4000)
  window.setTimeout(() => {
    items.value = items.value.filter((item) => item.id !== id)
  }, ttl)
}

provide(toastKey, { push })
</script>

<template>
  <slot />
  <div
    class="pointer-events-none fixed bottom-20 right-4 z-[60] flex w-80 flex-col gap-2"
  >
    <div
      v-for="item in items"
      :key="item.id"
      :class="cx(toastBaseClass, toneCls[item.tone])"
      role="status"
    >
      {{ item.message }}
    </div>
  </div>
</template>
