<script setup lang="ts">
import { ref } from 'vue'
import StrikeZone from './StrikeZone.vue'

type PlateSide = '右' | '左'
type Status = '通常' | 'disabled' | 'highlight'

interface ComparisonCell {
  id: string
  point: { x: number; y: number } | null
  plateSide: PlateSide
  status: Status
  disabled: boolean
  highlight: boolean
}

const comparisonCells: ComparisonCell[] = [
  {
    id: 'point-right-normal',
    point: { x: 131.5, y: 124 },
    plateSide: '右',
    status: '通常',
    disabled: false,
    highlight: false,
  },
  {
    id: 'point-right-disabled',
    point: { x: 131.5, y: 124 },
    plateSide: '右',
    status: 'disabled',
    disabled: true,
    highlight: false,
  },
  {
    id: 'point-right-highlight',
    point: { x: 131.5, y: 124 },
    plateSide: '右',
    status: 'highlight',
    disabled: false,
    highlight: true,
  },
  {
    id: 'point-left-normal',
    point: { x: 131.5, y: 124 },
    plateSide: '左',
    status: '通常',
    disabled: false,
    highlight: false,
  },
  {
    id: 'point-left-disabled',
    point: { x: 131.5, y: 124 },
    plateSide: '左',
    status: 'disabled',
    disabled: true,
    highlight: false,
  },
  {
    id: 'point-left-highlight',
    point: { x: 131.5, y: 124 },
    plateSide: '左',
    status: 'highlight',
    disabled: false,
    highlight: true,
  },
  {
    id: 'empty-right-normal',
    point: null,
    plateSide: '右',
    status: '通常',
    disabled: false,
    highlight: false,
  },
  {
    id: 'empty-right-disabled',
    point: null,
    plateSide: '右',
    status: 'disabled',
    disabled: true,
    highlight: false,
  },
  {
    id: 'empty-right-highlight',
    point: null,
    plateSide: '右',
    status: 'highlight',
    disabled: false,
    highlight: true,
  },
  {
    id: 'empty-left-normal',
    point: null,
    plateSide: '左',
    status: '通常',
    disabled: false,
    highlight: false,
  },
  {
    id: 'empty-left-disabled',
    point: null,
    plateSide: '左',
    status: 'disabled',
    disabled: true,
    highlight: false,
  },
  {
    id: 'empty-left-highlight',
    point: null,
    plateSide: '左',
    status: 'highlight',
    disabled: false,
    highlight: true,
  },
]

const colorSchemes = [
  {
    id: 'light',
    label: 'light',
    className: 'border-slate-300 bg-slate-100 text-slate-900',
  },
  {
    id: 'dark',
    label: 'dark',
    className: 'dark border-slate-700 bg-slate-950 text-slate-100',
  },
] as const

const lastTap = ref('まだタップしていません')

function cellLabel(cell: ComparisonCell): string {
  const point = cell.point ? 'point: あり' : 'point: なし'
  return `${point} / plateSide: ${cell.plateSide}打者 / 状態: ${cell.status}`
}

function handleTap(label: string, x: number, y: number): void {
  lastTap.value = `${label}: X${Math.round(x)} Y${Math.round(y)}`
}
</script>

<template>
  <!-- 開発時の目視比較専用。製品画面のルーティングには使用しない。 -->
  <section class="space-y-6 p-6">
    <p class="text-sm text-slate-600 dark:text-slate-300">
      タップ結果: {{ lastTap }}（全セルは捕手側視点）
    </p>

    <section
      v-for="scheme in colorSchemes"
      :key="scheme.id"
      :class="['space-y-4 rounded-2xl border p-4', scheme.className]"
      :style="{ colorScheme: scheme.id }"
    >
      <h2 class="text-lg font-bold">カラースキーム: {{ scheme.label }}</h2>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <article
          v-for="cell in comparisonCells"
          :key="cell.id"
          class="space-y-2 rounded-xl border border-slate-300 bg-white p-3 dark:border-slate-600 dark:bg-slate-900"
        >
          <p class="text-sm font-medium">{{ cellLabel(cell) }}</p>
          <StrikeZone
            :point="cell.point"
            :plate-side="cell.plateSide"
            viewpoint="catcher"
            :highlight="cell.highlight"
            :disabled="cell.disabled"
            @tap="
              (x, y) => handleTap(`${scheme.label} / ${cellLabel(cell)}`, x, y)
            "
          />
        </article>
      </div>
    </section>
  </section>
</template>
