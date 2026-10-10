<script lang="ts">
interface AttributeSnapshot {
  element: HTMLElement
  inert: string | null
  ariaHidden: string | null
}

interface OverflowSnapshot {
  value: string
  priority: string
}

let openSheetCount = 0
let overflowSnapshot: OverflowSnapshot | null = null
let backgroundSnapshots: AttributeSnapshot[] = []
const openSheetStack: symbol[] = []

function restoreAttribute(
  element: HTMLElement,
  name: 'inert' | 'aria-hidden',
  value: string | null,
): void {
  if (value === null) element.removeAttribute(name)
  else element.setAttribute(name, value)
}

function lockBackground(): () => void {
  if (openSheetCount === 0) {
    overflowSnapshot = {
      value: document.body.style.getPropertyValue('overflow'),
      priority: document.body.style.getPropertyPriority('overflow'),
    }
    document.body.style.setProperty('overflow', 'hidden')

    // 旧の #root は現行 Vue のマウント先 #app に替える（決定 A）。
    const app = document.getElementById('app')
    const backgrounds = app
      ? [app]
      : Array.from(document.body.children).filter(
          (element): element is HTMLElement =>
            element instanceof HTMLElement &&
            !element.hasAttribute('data-sheet-layer'),
        )
    backgroundSnapshots = backgrounds.map((element) => ({
      element,
      inert: element.getAttribute('inert'),
      ariaHidden: element.getAttribute('aria-hidden'),
    }))
    for (const { element } of backgroundSnapshots) {
      element.setAttribute('inert', '')
      element.setAttribute('aria-hidden', 'true')
    }
  }

  openSheetCount += 1
  let released = false
  return () => {
    if (released) return
    released = true
    openSheetCount = Math.max(0, openSheetCount - 1)
    if (openSheetCount !== 0) return

    if (overflowSnapshot) {
      const { value, priority } = overflowSnapshot
      if (value || priority) {
        document.body.style.setProperty('overflow', value, priority)
      } else {
        document.body.style.removeProperty('overflow')
      }
    }
    overflowSnapshot = null
    for (const { element, inert, ariaHidden } of backgroundSnapshots) {
      restoreAttribute(element, 'inert', inert)
      restoreAttribute(element, 'aria-hidden', ariaHidden)
    }
    backgroundSnapshots = []
  }
}
</script>

<script setup lang="ts">
import { X } from 'lucide-vue-next'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { cx } from '../../lib/format'

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
const sheetToken = Symbol('sheet')

const panel = ref<HTMLDivElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const panelClass = computed(() =>
  cx(
    'absolute flex flex-col bg-white shadow-2xl dark:bg-slate-900',
    props.side === 'right'
      ? cx('inset-y-0 right-0 w-full', props.wide ? 'max-w-3xl' : 'max-w-md')
      : 'inset-x-0 bottom-0 max-h-[85dvh] rounded-t-2xl',
  ),
)

function handleKeydown(event: KeyboardEvent): void {
  // stopPropagation は同じ window の後続リスナーを止めないため、最前面だけが処理する（決定 M）。
  if (openSheetStack[openSheetStack.length - 1] !== sheetToken) return

  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('close')
    return
  }
  if (event.key !== 'Tab') return

  const focusable = panel.value?.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
  )
  if (!focusable?.length) return
  const first = focusable.item(0)
  const last = focusable.item(focusable.length - 1)
  if (!first || !last) return

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

let cleanup: (() => void) | undefined

function activate(): void {
  if (cleanup) return
  const previousFocus =
    document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
  closeButton.value?.focus()
  const unlockBackground = lockBackground()
  openSheetStack.push(sheetToken)
  window.addEventListener('keydown', handleKeydown, true)
  cleanup = () => {
    window.removeEventListener('keydown', handleKeydown, true)
    const index = openSheetStack.indexOf(sheetToken)
    if (index !== -1) openSheetStack.splice(index, 1)
    unlockBackground()
    previousFocus?.focus()
  }
}

function deactivate(): void {
  const release = cleanup
  cleanup = undefined
  release?.()
}

// watch は DOM 更新後に走らせ、初期 open は onMounted で処理する（決定 C）。
watch(
  () => props.open,
  (open) => {
    if (open) activate()
    else deactivate()
  },
  { flush: 'post' },
)
onMounted(() => {
  if (props.open) activate()
})
onBeforeUnmount(deactivate)
</script>

<template>
  <Teleport v-if="open" to="body">
    <div class="fixed inset-0 z-50" data-sheet-layer="">
      <div class="absolute inset-0 bg-black/40" @click="emit('close')" />
      <div
        ref="panel"
        :class="panelClass"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
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
