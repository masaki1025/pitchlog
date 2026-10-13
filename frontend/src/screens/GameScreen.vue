<script setup lang="ts">
import { ref, watch } from 'vue'
import StrikeZone from '../components/zone/StrikeZone.vue'
import type { CourseInputView } from '../lib/courseInputView'

interface GameDisplayState {
  gameName: string | null
  inning: string | null
  half: string | null
  awayScore: string | null
  homeScore: string | null
  outs: string | null
  runners: string | null
  count: string | null
  batter: string | null
  pitcher: string | null
}

interface InputCandidate {
  id: string
  displayName: string
  enabled: boolean
}

interface CourseView {
  plateSide: string
  viewpoint: CourseInputView
}

const props = defineProps<{
  state?: Partial<GameDisplayState> | null
  pitchTypes?: readonly InputCandidate[]
  results?: readonly InputCandidate[]
  courseView?: CourseView | null
}>()

const pitchTypeId = ref<string | null>(null)
const speed = ref('')
const course = ref<{ x: number; y: number } | null>(null)
const resultId = ref<string | null>(null)

// 呼出元が表示用に整形した文字列だけを描画する。
function display(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value : '未取得'
}

function isEnabled(
  candidates: readonly InputCandidate[] | undefined,
  id: string,
) {
  return (
    candidates?.some((candidate) => candidate.enabled && candidate.id === id) ??
    false
  )
}

function selectedId(
  event: Event,
  candidates: readonly InputCandidate[] | undefined,
): string | null {
  const id = (event.target as HTMLSelectElement).value
  return isEnabled(candidates, id) ? id : null
}

watch(
  () => props.pitchTypes,
  (candidates) => {
    if (
      pitchTypeId.value !== null &&
      !isEnabled(candidates, pitchTypeId.value)
    ) {
      pitchTypeId.value = null
    }
  },
  { deep: true, flush: 'sync' },
)

watch(
  () => props.results,
  (candidates) => {
    if (resultId.value !== null && !isEnabled(candidates, resultId.value)) {
      resultId.value = null
    }
  },
  { deep: true, flush: 'sync' },
)

function clearDraft() {
  pitchTypeId.value = null
  speed.value = ''
  course.value = null
  resultId.value = null
}
</script>

<template>
  <main class="mx-auto max-w-5xl space-y-5 p-4 pb-12">
    <header class="space-y-2">
      <p class="text-sm font-semibold text-sky-700 dark:text-sky-300">
        試合状態 · 表示のみ
      </p>
      <h1 class="text-2xl font-extrabold" data-testid="game-name">
        {{ display(props.state?.gameName) }}
      </h1>
      <p class="text-sm text-slate-600 dark:text-slate-300">
        この画面は表示データの接続前です。ここから記録はできません。
      </p>
    </header>

    <section
      aria-label="試合状況"
      class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
    >
      <dl class="mb-5 flex flex-wrap items-center gap-2 text-sm font-bold">
        <div
          class="rounded-full bg-sky-100 px-3 py-1 text-sky-800 dark:bg-sky-950 dark:text-sky-200"
        >
          <dt>回</dt>
          <dd data-testid="inning">{{ display(props.state?.inning) }}</dd>
        </div>
        <div
          class="rounded-full bg-slate-100 px-3 py-1 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
        >
          <dt>表裏</dt>
          <dd data-testid="half">{{ display(props.state?.half) }}</dd>
        </div>
      </dl>

      <dl class="grid grid-cols-2 gap-3">
        <div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
          <dt class="text-sm text-slate-500 dark:text-slate-400">先攻</dt>
          <dd
            class="mt-1 text-3xl font-extrabold tabular-nums"
            data-testid="away-score"
          >
            {{ display(props.state?.awayScore) }}
          </dd>
        </div>
        <div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
          <dt class="text-sm text-slate-500 dark:text-slate-400">後攻</dt>
          <dd
            class="mt-1 text-3xl font-extrabold tabular-nums"
            data-testid="home-score"
          >
            {{ display(props.state?.homeScore) }}
          </dd>
        </div>
      </dl>

      <dl class="mt-4 grid gap-3 sm:grid-cols-3">
        <div
          class="rounded-xl border border-slate-200 p-3 dark:border-slate-700"
        >
          <dt class="text-sm text-slate-500 dark:text-slate-400">アウト</dt>
          <dd class="mt-1 font-bold" data-testid="outs">
            {{ display(props.state?.outs) }}
          </dd>
        </div>
        <div
          class="rounded-xl border border-slate-200 p-3 dark:border-slate-700"
        >
          <dt class="text-sm text-slate-500 dark:text-slate-400">走者</dt>
          <dd class="mt-1 font-bold" data-testid="runners">
            {{ display(props.state?.runners) }}
          </dd>
        </div>
        <div
          class="rounded-xl border border-slate-200 p-3 dark:border-slate-700"
        >
          <dt class="text-sm text-slate-500 dark:text-slate-400">カウント</dt>
          <dd class="mt-1 font-bold" data-testid="count">
            {{ display(props.state?.count) }}
          </dd>
        </div>
      </dl>
    </section>

    <section aria-label="対戦中の選手" class="grid gap-3 sm:grid-cols-2">
      <dl
        class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
      >
        <dt class="text-sm text-slate-500 dark:text-slate-400">打者</dt>
        <dd class="mt-1 text-lg font-bold" data-testid="batter">
          {{ display(props.state?.batter) }}
        </dd>
      </dl>
      <dl
        class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
      >
        <dt class="text-sm text-slate-500 dark:text-slate-400">投手</dt>
        <dd class="mt-1 text-lg font-bold" data-testid="pitcher">
          {{ display(props.state?.pitcher) }}
        </dd>
      </dl>
    </section>

    <section
      aria-label="投球入力の下書き"
      class="rounded-2xl border border-amber-300 bg-amber-50 p-5 dark:border-amber-800 dark:bg-amber-950/30"
    >
      <div class="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="text-lg font-extrabold">投球入力の下書き</h2>
          <p
            id="draft-unsaved-note"
            class="mt-1 text-sm text-amber-900 dark:text-amber-200"
          >
            この入力は保存・送信されません。画面を離れると消えます。
          </p>
        </div>
        <button
          type="button"
          class="rounded-lg border border-amber-500 px-3 py-2 text-sm font-bold text-amber-900 hover:bg-amber-100 dark:text-amber-200 dark:hover:bg-amber-900"
          data-testid="clear-draft"
          @click="clearDraft"
        >
          下書きをすべて消去
        </button>
      </div>

      <div class="grid gap-5 lg:grid-cols-2">
        <div class="space-y-4">
          <div>
            <label for="pitch-type" class="mb-1 block text-sm font-bold"
              >球種</label
            >
            <div class="flex gap-2">
              <select
                id="pitch-type"
                aria-describedby="draft-unsaved-note"
                :value="pitchTypeId ?? ''"
                class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                data-testid="pitch-type"
                @change="pitchTypeId = selectedId($event, props.pitchTypes)"
              >
                <option value="">未選択</option>
                <option
                  v-for="candidate in props.pitchTypes?.filter(
                    (item) => item.enabled,
                  ) ?? []"
                  :key="candidate.id"
                  :value="candidate.id"
                >
                  {{ candidate.displayName }}
                </option>
              </select>
              <button
                type="button"
                class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600"
                @click="pitchTypeId = null"
              >
                球種を消去
              </button>
            </div>
          </div>

          <div>
            <label for="pitch-speed" class="mb-1 block text-sm font-bold"
              >球速</label
            >
            <div class="flex gap-2">
              <input
                id="pitch-speed"
                v-model="speed"
                aria-describedby="draft-unsaved-note"
                type="text"
                inputmode="decimal"
                autocomplete="off"
                class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                data-testid="pitch-speed"
                placeholder="km/h"
              />
              <button
                type="button"
                class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600"
                @click="speed = ''"
              >
                球速を消去
              </button>
            </div>
          </div>

          <div>
            <label for="pitch-result" class="mb-1 block text-sm font-bold"
              >結果</label
            >
            <div class="flex gap-2">
              <select
                id="pitch-result"
                aria-describedby="draft-unsaved-note"
                :value="resultId ?? ''"
                class="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                data-testid="pitch-result"
                @change="resultId = selectedId($event, props.results)"
              >
                <option value="">未選択</option>
                <option
                  v-for="candidate in props.results?.filter(
                    (item) => item.enabled,
                  ) ?? []"
                  :key="candidate.id"
                  :value="candidate.id"
                >
                  {{ candidate.displayName }}
                </option>
              </select>
              <button
                type="button"
                class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600"
                @click="resultId = null"
              >
                結果を消去
              </button>
            </div>
          </div>
        </div>

        <div>
          <div class="mb-2 flex items-center justify-between gap-2">
            <h3 class="text-sm font-bold">コース</h3>
            <button
              type="button"
              class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600"
              data-testid="clear-course"
              @click="course = null"
            >
              コースを消去
            </button>
          </div>
          <StrikeZone
            v-if="props.courseView"
            aria-describedby="draft-unsaved-note"
            :plate-side="props.courseView.plateSide"
            :viewpoint="props.courseView.viewpoint"
            :point="course"
            class="max-w-80"
            @tap="(x, y) => (course = { x, y })"
          />
          <p
            v-else
            class="rounded-lg border border-dashed border-slate-400 p-5 text-sm text-slate-600 dark:text-slate-300"
          >
            コース入力には打席と視点の設定が必要です。
          </p>
          <p class="mt-2 text-sm" data-testid="course-status">
            {{ course ? 'コース選択済み（未保存）' : 'コース未選択' }}
          </p>
        </div>
      </div>
    </section>
  </main>
</template>
