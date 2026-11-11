<script setup lang="ts">
import { computed, ref } from 'vue'
import { DISPLAY_COORD_SIZE, FIELD_HOME } from '../../lib/displayGeometry'
import { FIELDER_ANCHORS, POSITION_SHORT } from '../../lib/fielderAnchors'
import { moveSpatialPoint } from '../../lib/spatialInput'
import FieldGeometrySvg from './FieldGeometrySvg.vue'

const props = withDefaults(
  defineProps<{
    point: { x: number; y: number } | null
    defense?: Readonly<Record<string, string>>
    fielder?: number | null
    runners?: { first: boolean; second: boolean; third: boolean }
    highlight?: boolean
    disabled?: boolean
  }>(),
  {
    defense: () => ({}),
    fielder: null,
    runners: () => ({ first: false, second: false, third: false }),
    highlight: false,
    disabled: false,
  },
)
const emit = defineEmits<{ tap: [x: number, y: number] }>()
const svg = ref<SVGSVGElement | null>(null)
const marker = computed(() => props.point)
function handlePointer(event: PointerEvent) {
  if (props.disabled) return
  const node = svg.value
  if (!node) return
  const rect = node.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * DISPLAY_COORD_SIZE
  const y = ((event.clientY - rect.top) / rect.height) * DISPLAY_COORD_SIZE
  emit(
    'tap',
    Math.max(0.1, Math.min(DISPLAY_COORD_SIZE - 0.1, x)),
    Math.max(0.1, Math.min(DISPLAY_COORD_SIZE - 0.1, y)),
  )
}
function handleKeyDown(event: KeyboardEvent) {
  if (props.disabled) return
  const next = moveSpatialPoint(props.point, event.key, {
    defaultPoint: { x: FIELD_HOME.x, y: 150 },
    fine: event.shiftKey,
  })
  if (!next) return
  event.preventDefault()
  emit('tap', next.x, next.y)
}
</script>

<template>
  <div class="relative aspect-square w-full">
    <svg
      ref="svg"
      :viewBox="`0 0 ${DISPLAY_COORD_SIZE} ${DISPLAY_COORD_SIZE}`"
      :class="[
        'aspect-square w-full cursor-crosshair touch-none select-none rounded-xl border border-slate-300 bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:border-slate-600 dark:bg-emerald-950/30 dark:focus-visible:ring-offset-slate-950',
        highlight && 'missing-highlight',
        disabled && 'opacity-60',
      ]"
      :tabindex="disabled ? -1 : 0"
      role="img"
      :aria-label="`フィールド（タップまたは矢印キーで打球位置入力。Shift+矢印で微調整）${
        point
          ? `。現在位置 X${Math.round(point.x)} Y${Math.round(point.y)}`
          : '。現在は未入力'
      }`"
      @pointerdown="handlePointer"
      @keydown="handleKeyDown"
    >
      <FieldGeometrySvg :runners="runners" />
      <g
        v-for="[num, ax, ay] in FIELDER_ANCHORS"
        :key="num"
        class="pointer-events-none"
      >
        <circle
          :cx="ax"
          :cy="ay - 4"
          r="8"
          :class="
            fielder === num
              ? 'fill-sky-600 stroke-sky-700'
              : 'fill-white/90 stroke-slate-400 dark:fill-slate-800/90 dark:stroke-slate-500'
          "
          stroke-width="1"
        />
        <text
          :x="ax"
          :y="ay - 1"
          text-anchor="middle"
          font-size="9"
          font-weight="700"
          :class="
            fielder === num
              ? 'fill-white'
              : 'fill-slate-600 dark:fill-slate-300'
          "
        >
          {{ POSITION_SHORT[num] }}
        </text>
        <text
          v-if="defense[String(num)]"
          :x="ax"
          :y="ay + 13"
          text-anchor="middle"
          font-size="8.5"
          class="fill-slate-500 dark:fill-slate-400"
        >
          {{
            (defense[String(num)] ?? '').length > 5
              ? (defense[String(num)] ?? '').slice(0, 5)
              : defense[String(num)]
          }}
        </text>
      </g>
      <g v-if="marker">
        <circle
          :cx="marker.x"
          :cy="marker.y"
          r="8"
          class="fill-red-500/25 stroke-red-500"
          stroke-width="2"
        />
        <circle :cx="marker.x" :cy="marker.y" r="3" class="fill-red-600" />
      </g>
    </svg>
  </div>
</template>
