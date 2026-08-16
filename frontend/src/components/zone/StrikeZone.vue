<script setup lang="ts">
import { computed, ref } from 'vue'
import batterFrontSilhouette from '../../assets/batter-silhouette-front.png'
import batterSilhouette from '../../assets/batter-silhouette-right.png'
import {
  COURSE_STRIKE_ZONE,
  DISPLAY_COORD_SIZE,
} from '../../lib/displayGeometry'
import {
  courseInputViewLabel,
  courseScreenXToStoredX,
  courseStoredXToScreenX,
  type CourseInputView,
} from '../../lib/courseInputView'
import { cx } from '../../lib/format'
import { moveSpatialPoint } from '../../lib/spatialInput'

interface Props {
  /** タップ済みコース（0〜263 float、従来の捕手側保存座標） */
  point: { x: number; y: number } | null
  /** 打席左右（右打者=三塁側=左にシルエット） */
  plateSide: string
  /** 画面の視点。保存座標は常に従来の捕手側視点へ正規化する。 */
  viewpoint: CourseInputView
  highlight?: boolean
  disabled?: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  tap: [x: number, y: number]
}>()

// ストライクゾーン矩形（表示用。保存座標は viewBox 全域 0〜263 のタップ値そのまま）
const Z = COURSE_STRIKE_ZONE
const svgRef = ref<SVGSVGElement | null>(null)

function handlePointer(e: PointerEvent) {
  if (props.disabled) return
  const svg = svgRef.value
  if (!svg) return
  const rect = svg.getBoundingClientRect()
  const screenX = ((e.clientX - rect.left) / rect.width) * DISPLAY_COORD_SIZE
  const y = ((e.clientY - rect.top) / rect.height) * DISPLAY_COORD_SIZE
  const clampedScreenX = Math.max(
    0.1,
    Math.min(DISPLAY_COORD_SIZE - 0.1, screenX),
  )
  emit(
    'tap',
    courseScreenXToStoredX(clampedScreenX, props.viewpoint),
    Math.max(0.1, Math.min(DISPLAY_COORD_SIZE - 0.1, y)),
  )
}

function handleKeyDown(e: KeyboardEvent) {
  if (props.disabled) return
  const screenPoint = props.point
    ? {
        x: courseStoredXToScreenX(props.point.x, props.viewpoint),
        y: props.point.y,
      }
    : null
  const next = moveSpatialPoint(screenPoint, e.key, {
    defaultPoint: { x: (Z.left + Z.right) / 2, y: (Z.top + Z.bottom) / 2 },
    fine: e.shiftKey,
  })
  if (!next) return
  e.preventDefault()
  emit('tap', courseScreenXToStoredX(next.x, props.viewpoint), next.y)
}

const thirdW = (Z.right - Z.left) / 3
const thirdH = (Z.bottom - Z.top) / 3
const isPitcherView = computed(() => props.viewpoint === 'pitcher')
// 捕手側画像は透明余白を含む正方形PNG。`slice`で細長く切り抜かず、
// 透過領域ごと拡大して実画部分だけを左右の打席領域（各80px）へ収める。
const batterX = computed(() => (isPitcherView.value ? 2 : -53))
const batterY = computed(() => (isPitcherView.value ? 37 : 23))
const batterWidth = computed(() => (isPitcherView.value ? 70 : 210))
const batterHeight = computed(() => (isPitcherView.value ? 178 : 210))
const batterOnLeft = computed(() =>
  isPitcherView.value ? props.plateSide === '左' : props.plateSide !== '左',
)
const batterPlacementX = computed(() =>
  batterOnLeft.value ? 0 : 263 - (batterX.value * 2 + batterWidth.value),
)
// 両画像は右打者を基準にし、打席位置と画像反転を独立して扱う。
const batterMirrored = computed(() => props.plateSide === '左')
const batterMirrorTransform = computed(() =>
  batterMirrored.value
    ? `translate(${batterX.value * 2 + batterWidth.value} 0) scale(-1 1)`
    : undefined,
)
const batterImage = computed(() =>
  isPitcherView.value ? batterFrontSilhouette : batterSilhouette,
)
const homePlatePath = computed(() =>
  // 投手側から見たホームベースは、先端が捕手側（画面上）を向く。
  isPitcherView.value
    ? 'M 106 252 L 157 252 L 157 240 L 131.5 226 L 106 240 Z'
    : 'M 106 226 L 157 226 L 157 238 L 131.5 252 L 106 238 Z',
)
const markerX = computed(() =>
  props.point ? courseStoredXToScreenX(props.point.x, props.viewpoint) : null,
)
const viewpointBadgeLabel = computed(() =>
  courseInputViewLabel(props.viewpoint),
)
const viewpointLabel = computed(() => `${viewpointBadgeLabel.value}視点`)
const leftFieldSide = computed(() =>
  props.viewpoint === 'pitcher' ? '1塁側' : '3塁側',
)
const rightFieldSide = computed(() =>
  props.viewpoint === 'pitcher' ? '3塁側' : '1塁側',
)
const ariaLabel = computed(
  () =>
    `ストライクゾーン（${viewpointLabel.value}。画面左は${leftFieldSide.value}、画面右は${rightFieldSide.value}。タップまたは矢印キーでコース入力。Shift+矢印で微調整）${
      props.point && markerX.value !== null
        ? `。現在位置 X${Math.round(markerX.value)} Y${Math.round(props.point.y)}`
        : '。現在は未入力'
    }`,
)
</script>

<template>
  <svg
    ref="svgRef"
    :viewBox="`0 0 ${DISPLAY_COORD_SIZE} ${DISPLAY_COORD_SIZE}`"
    :class="
      cx(
        'aspect-square w-full touch-none select-none rounded-xl border border-slate-300 bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2 dark:border-slate-600 dark:bg-slate-900 dark:focus-visible:ring-offset-slate-950',
        props.highlight && 'missing-highlight',
        !props.disabled && 'cursor-crosshair',
      )
    "
    :tabindex="props.disabled ? -1 : 0"
    :aria-disabled="props.disabled || undefined"
    :aria-label="ariaLabel"
    :data-viewpoint="props.viewpoint"
    role="img"
    @pointerdown="handlePointer"
    @keydown="handleKeyDown"
  >
    <!-- 視点ごとの打席位置へ配置し、左打者のときだけ画像をフレーム内で反転する。 -->
    <g
      aria-hidden="true"
      pointer-events="none"
      :transform="
        batterPlacementX === 0 ? undefined : `translate(${batterPlacementX} 0)`
      "
    >
      <g :transform="batterMirrorTransform">
        <image
          :href="batterImage"
          :x="batterX"
          :y="batterY"
          :width="batterWidth"
          :height="batterHeight"
          preserve-aspect-ratio="xMidYMid meet"
          pointer-events="none"
          class="brightness-0 opacity-[0.18] dark:invert dark:opacity-[0.24]"
        />
      </g>
    </g>

    <!-- 画像で視点を判別できるため、名称だけを控えめに常時表示する。 -->
    <g aria-hidden="true" pointer-events="none">
      <rect
        :x="183"
        :y="8"
        :width="70"
        :height="20"
        :rx="10"
        class="fill-slate-100/95 stroke-slate-300 dark:fill-slate-800/95 dark:stroke-slate-600"
        :stroke-width="1"
      />
      <text
        :x="218"
        :y="21.5"
        text-anchor="middle"
        class="fill-slate-600 text-[9px] font-bold dark:fill-slate-200"
      >
        {{ viewpointBadgeLabel }}
      </text>
    </g>

    <!-- ホームベース -->
    <path
      :d="homePlatePath"
      :data-viewpoint="props.viewpoint"
      class="fill-slate-200 stroke-slate-400 dark:fill-slate-800 dark:stroke-slate-500"
      :stroke-width="1.5"
    />

    <!-- 外周ガイド（ボールゾーン） -->
    <rect
      :x="Z.left - thirdW"
      :y="Z.top - thirdH"
      :width="Z.right - Z.left + thirdW * 2"
      :height="Z.bottom - Z.top + thirdH * 2"
      class="fill-none stroke-slate-200 dark:stroke-slate-700"
      :stroke-width="1"
      stroke-dasharray="4 4"
    />

    <!-- ストライクゾーン本体 3x3 -->
    <rect
      :x="Z.left"
      :y="Z.top"
      :width="Z.right - Z.left"
      :height="Z.bottom - Z.top"
      class="fill-sky-50 stroke-slate-500 dark:fill-sky-950/40 dark:stroke-slate-400"
      :stroke-width="2"
    />
    <g
      v-for="i in [1, 2]"
      :key="i"
      class="stroke-slate-300 dark:stroke-slate-600"
    >
      <line
        :x1="Z.left + thirdW * i"
        :y1="Z.top"
        :x2="Z.left + thirdW * i"
        :y2="Z.bottom"
        :stroke-width="1"
      />
      <line
        :x1="Z.left"
        :y1="Z.top + thirdH * i"
        :x2="Z.right"
        :y2="Z.top + thirdH * i"
        :stroke-width="1"
      />
    </g>

    <!-- コースマーカー（即時表示） -->
    <g v-if="props.point">
      <circle
        :cx="markerX ?? props.point.x"
        :cy="props.point.y"
        :r="9"
        class="fill-red-500/25 stroke-red-500"
        :stroke-width="2"
      />
      <circle
        :cx="markerX ?? props.point.x"
        :cy="props.point.y"
        :r="3.5"
        class="fill-red-600"
      />
    </g>
  </svg>
</template>
