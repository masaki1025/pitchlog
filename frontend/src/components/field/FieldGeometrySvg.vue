<script setup lang="ts">
import {
  FIELD_FENCE_LEFT,
  FIELD_FENCE_RADIUS,
  FIELD_FENCE_RIGHT,
  FIELD_FIRST,
  FIELD_HOME,
  FIELD_HOME_PLATE_POINTS,
  FIELD_SECOND,
  FIELD_THIRD,
  svgPoints,
  type DisplayPoint,
} from '../../lib/displayGeometry'

withDefaults(
  defineProps<{
    runners?: { first: boolean; second: boolean; third: boolean }
  }>(),
  { runners: () => ({ first: false, second: false, third: false }) },
)
function marker(point: DisplayPoint, occupied: boolean) {
  return {
    x: point.x - 5,
    y: point.y - 5,
    occupied,
  }
}
</script>

<template>
  <path
    :d="`M ${FIELD_HOME.x} ${FIELD_HOME.y} L ${FIELD_FENCE_LEFT.x} ${FIELD_FENCE_LEFT.y} A ${FIELD_FENCE_RADIUS} ${FIELD_FENCE_RADIUS} 0 0 1 ${FIELD_FENCE_RIGHT.x} ${FIELD_FENCE_RIGHT.y} Z`"
    class="fill-emerald-100 stroke-emerald-400 dark:fill-emerald-900/40 dark:stroke-emerald-700"
    stroke-width="1.5"
  />
  <path
    :d="`M ${FIELD_HOME.x} ${FIELD_HOME.y} L ${FIELD_FIRST.x} ${FIELD_FIRST.y} L ${FIELD_SECOND.x} ${FIELD_SECOND.y} L ${FIELD_THIRD.x} ${FIELD_THIRD.y} Z`"
    class="fill-amber-100/80 stroke-amber-500 dark:fill-amber-900/30 dark:stroke-amber-700"
    stroke-width="1.5"
  />
  <rect
    v-for="item in [
      marker(FIELD_FIRST, runners.first),
      marker(FIELD_SECOND, runners.second),
      marker(FIELD_THIRD, runners.third),
    ]"
    :key="`${item.x}-${item.y}`"
    :x="item.x"
    :y="item.y"
    width="10"
    height="10"
    :transform="`rotate(45 ${item.x + 5} ${item.y + 5})`"
    :class="
      item.occupied
        ? 'fill-red-500 stroke-red-600'
        : 'fill-white stroke-slate-400 dark:fill-slate-800 dark:stroke-slate-500'
    "
    stroke-width="1.5"
  />
  <polygon
    :points="svgPoints(FIELD_HOME_PLATE_POINTS)"
    class="fill-white stroke-slate-400 dark:fill-slate-800 dark:stroke-slate-500"
    stroke-width="1.2"
  />
</template>
