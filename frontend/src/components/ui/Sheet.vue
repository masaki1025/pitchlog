<script lang="ts">
type Entry = {
  panel: HTMLElement
  close: () => void
  returnFocus: HTMLElement | null
  listener: (event: KeyboardEvent) => void
}
const stack: Entry[] = []
const history: Entry[] = []
let backgroundLock: (() => void) | null = null
</script>

<script setup lang="ts">
import { nextTick, onScopeDispose, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    side?: 'right' | 'bottom'
    wide?: boolean
  }>(),
  { side: 'right', wide: false },
)
const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)

let currentEntry: Entry | null = null

function lockBackground(): () => void {
  const app = document.getElementById('app')
  const targets = app
    ? [app]
    : Array.from(document.body.children).filter(
        (element): element is HTMLElement =>
          element instanceof HTMLElement &&
          !element.hasAttribute('data-sheet-layer'),
      )
  const snapshots = targets.map((element) => ({
    element,
    inert: element.getAttribute('inert'),
    ariaHidden: element.getAttribute('aria-hidden'),
  }))
  const overflow = document.body.style.getPropertyValue('overflow')
  const priority = document.body.style.getPropertyPriority('overflow')
  document.body.style.setProperty('overflow', 'hidden')
  for (const { element } of snapshots) {
    element.setAttribute('inert', '')
    element.setAttribute('aria-hidden', 'true')
  }
  return () => {
    if (overflow)
      document.body.style.setProperty('overflow', overflow, priority)
    else document.body.style.removeProperty('overflow')
    for (const { element, inert, ariaHidden } of snapshots) {
      if (inert === null) element.removeAttribute('inert')
      else element.setAttribute('inert', inert)
      if (ariaHidden === null) element.removeAttribute('aria-hidden')
      else element.setAttribute('aria-hidden', ariaHidden)
    }
  }
}

function topEntry(): Entry | null {
  return stack[stack.length - 1] ?? null
}

function focusables(entry: Entry): HTMLElement[] {
  return Array.from(
    entry.panel.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    ),
  )
}

function handleKey(event: KeyboardEvent, current: Entry) {
  if (event.key === 'Escape') {
    event.stopPropagation()
    current.close()
    return
  }
  if (event.key !== 'Tab') return
  const items = focusables(current)
  if (items.length === 0) return
  const first = items[0]!
  const last = items[items.length - 1]!
  if (!current.panel.contains(document.activeElement)) {
    event.preventDefault()
    ;(event.shiftKey ? last : first).focus()
    return
  }
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

/** 閉じたパネル内の戻り先は、そのパネルを開く前の戻り先へ引き継ぐ。 */
function resolveReturnFocus(entry: Entry): HTMLElement | null {
  let target = entry.returnFocus
  const seen = new Set<Entry>()
  while (target && !target.isConnected && !seen.has(entry)) {
    const owner = history.find((candidate) => candidate.panel.contains(target!))
    if (!owner) return null
    seen.add(owner)
    target = owner.returnFocus
  }
  return target && target.isConnected ? target : null
}

function openSheet() {
  if (!panel.value) {
    void nextTick(openSheet)
    return
  }
  if (stack.some((entry) => entry.panel === panel.value)) return
  const close = () => emit('close')
  const entry: Entry = {
    panel: panel.value,
    close,
    returnFocus:
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null,
    listener: () => undefined,
  }
  entry.listener = (event) => {
    if (topEntry() !== entry) return
    handleKey(event, entry)
  }
  stack.push(entry)
  history.push(entry)
  currentEntry = entry
  if (stack.length === 1) backgroundLock = lockBackground()
  window.addEventListener('keydown', entry.listener, true)
  closeButton.value?.focus()
}

function closeSheet() {
  const entry = currentEntry
  if (!entry) return
  const index = stack.indexOf(entry)
  if (index === -1) return
  const wasTop = index === stack.length - 1
  stack.splice(index, 1)
  currentEntry = null
  window.removeEventListener('keydown', entry.listener, true)
  if (stack.length === 0) {
    backgroundLock?.()
    backgroundLock = null
    resolveReturnFocus(entry)?.focus()
    return
  }
  if (!wasTop) return
  const target =
    resolveReturnFocus(entry) ??
    stack[stack.length - 1]?.panel.querySelector<HTMLElement>(
      'button[aria-label="閉じる"]',
    ) ??
    null
  target?.focus()
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) openSheet()
    else closeSheet()
  },
  { immediate: true, flush: 'post' },
)

onScopeDispose(() => {
  if (props.open || (currentEntry !== null && stack.includes(currentEntry)))
    closeSheet()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50" data-sheet-layer="">
      <div class="absolute inset-0 bg-black/40" @click="emit('close')" />
      <div
        ref="panel"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        :class="[
          'absolute flex flex-col bg-white shadow-2xl dark:bg-slate-900',
          side === 'right'
            ? `inset-y-0 right-0 w-full ${wide ? 'max-w-3xl' : 'max-w-md'}`
            : 'inset-x-0 bottom-0 max-h-[85dvh] rounded-t-2xl',
        ]"
      >
        <div
          class="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700"
        >
          <h2 class="text-lg font-bold">{{ title }}</h2>
          <button
            ref="closeButton"
            type="button"
            class="grid min-h-11 min-w-11 place-items-center rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="閉じる"
            @click="emit('close')"
          >
            <X :size="22" />
          </button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto p-4"><slot /></div>
      </div>
    </div>
  </Teleport>
</template>
