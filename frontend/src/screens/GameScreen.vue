<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import StrikeZone from '../components/zone/StrikeZone.vue'
import type { CourseInputView } from '../lib/courseInputView'
import {
  SYNC_NOTICE_CATALOG,
  type SyncNoticeDescriptor,
} from '../lib/sync/syncNotices'
import { resolvePitchCommitGate } from './GameScreenCommitGate'
import {
  judgePitchInputEligibility,
  PITCH_INPUT_INELIGIBILITY_MESSAGE,
  type PitchInputObservation,
} from './GameScreenPitchEligibility'
import { buildPitchEventDraft } from './GameScreenPitchEvent'
import {
  deriveQueueStatus,
  type ActionRequiredSummary,
} from './GameScreenQueueStatus'

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

const props = withDefaults(
  defineProps<{
    state?: Partial<GameDisplayState> | null
    pitchTypes?: readonly InputCandidate[]
    results?: readonly InputCandidate[]
    courseView?: CourseView | null
    /** 未送信の件数。索引集計の結果を渡す(画面では数えない)。 */
    unsentCount?: number
    actionRequired?: ActionRequiredSummary
    evacuatedCount?: number
    syncedCount?: number
    /** 同期境界から受け取る通知。区分の判定は通信・キュー側が持つ。 */
    receivedNotices?: readonly SyncNoticeDescriptor[]
    /** 未送信が警告の閾値へ達したか。clientDiscipline の判定を渡す。 */
    unsentWarning?: boolean
    // boolean の prop は未指定が false へキャストされ「拒否」と区別できないため、
    // 未確定を表せる文字列で受け取る。
    storagePersistence?: 'granted' | 'denied'
    /** 1 球の入力に対する記録者の観測。可否の判定にだけ使う。 */
    inputObservation?: PitchInputObservation
    /** 確定値のうち、画面の下書き欄の外から来るもの。 */
    eventIdentity?: { d5: string; d4: string; gameId: string; d2: unknown }
  }>(),
  {
    state: undefined,
    pitchTypes: undefined,
    results: undefined,
    courseView: undefined,
    unsentCount: undefined,
    actionRequired: undefined,
    evacuatedCount: undefined,
    syncedCount: undefined,
    receivedNotices: undefined,
    unsentWarning: undefined,
    storagePersistence: undefined,
    inputObservation: undefined,
    eventIdentity: undefined,
  },
)

// 未同期の判定を画面で作り直さず、単一の導出から読む。
const queueStatus = computed(() =>
  deriveQueueStatus({
    unsentCount: props.unsentCount,
    actionRequired: props.actionRequired,
    evacuatedCount: props.evacuatedCount,
    syncedCount: props.syncedCount,
    unsentWarning: props.unsentWarning,
    receivedNotices: props.receivedNotices,
    storagePersistenceGranted:
      props.storagePersistence === undefined
        ? undefined
        : props.storagePersistence === 'granted',
  }),
)

// 第 1 期で許す入力かどうか。結果は入力欄の活性と理由の表示にだけ使う。
const eligibility = computed(() =>
  props.inputObservation
    ? judgePitchInputEligibility(props.inputObservation)
    : undefined,
)

// 観測が渡されていなければ判定の対象外として活性のままにする(判定を求めた
// のに観測が欠けている場合は、判定側が不可へ倒す)。方針は design.md 6-3。
const inputEnabled = computed(() => eligibility.value?.eligible !== false)

function noticeMessage(noticeId: keyof typeof SYNC_NOTICE_CATALOG): string {
  return SYNC_NOTICE_CATALOG[noticeId]
}

// 確定の可否は単一のゲートから読む。画面側で封鎖の判断を複製しない。
const commitGate = resolvePitchCommitGate()

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

// 確定値が揃ったときだけ下書きを組み立てる。確定はしない(封鎖はゲートが持つ)。
const draftAssembly = computed(() => {
  if (eligibility.value?.eligible === false) {
    return undefined
  }
  const identity = props.eventIdentity
  if (!identity || !pitchTypeId.value || !resultId.value) {
    return undefined
  }
  return buildPitchEventDraft({
    d5: identity.d5,
    d4: identity.d4,
    gameId: identity.gameId,
    d2: identity.d2,
    payload: {
      pitchTypeId: pitchTypeId.value,
      resultId: resultId.value,
      speed: speed.value,
      course: course.value,
    },
  })
})

function clearDraft() {
  pitchTypeId.value = null
  speed.value = ''
  course.value = null
  resultId.value = null
}
</script>

<template>
  <main class="mx-auto max-w-5xl space-y-5 p-4 pb-12 wrap-anywhere">
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
      aria-label="同期の状態"
      class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="mb-3 text-lg font-extrabold">同期の状態</h2>
      <dl class="grid gap-3 sm:grid-cols-2">
        <div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
          <dt class="text-sm text-slate-500 dark:text-slate-400">未送信</dt>
          <dd
            class="mt-1 text-2xl font-extrabold tabular-nums"
            data-testid="unsent-count"
          >
            {{ queueStatus.unsentCount ?? '未取得' }}
          </dd>
        </div>
        <div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
          <dt class="text-sm text-slate-500 dark:text-slate-400">要操作</dt>
          <dd
            class="mt-1 text-2xl font-extrabold tabular-nums"
            data-testid="action-required-count"
          >
            {{ queueStatus.actionRequiredCount ?? '未取得' }}
          </dd>
        </div>
        <div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
          <dt class="text-sm text-slate-500 dark:text-slate-400">退避済み</dt>
          <dd
            class="mt-1 text-2xl font-extrabold tabular-nums"
            data-testid="evacuated-count"
          >
            {{ queueStatus.evacuatedCount ?? '未取得' }}
          </dd>
        </div>
      </dl>

      <p
        v-if="queueStatus.unsentWarning"
        class="mt-3 rounded-lg border border-amber-500 p-3 text-sm font-bold text-amber-900 dark:text-amber-200"
        data-testid="unsent-warning"
      >
        未送信が多くたまっています。同期できる状態か確認してください。
      </p>

      <ul
        v-if="queueStatus.actionRequiredLabels.length"
        class="mt-3 list-disc space-y-1 pl-5 text-sm"
        data-testid="action-required-labels"
      >
        <li
          v-for="(label, index) in queueStatus.actionRequiredLabels"
          :key="`${label}-${index}`"
        >
          {{ label }}
        </li>
      </ul>

      <ul class="mt-3 space-y-2 text-sm" data-testid="sync-notices">
        <li
          v-for="(notice, index) in queueStatus.notices.filter(
            (item) => item.noticeId !== 'Q4',
          )"
          :key="`${notice.noticeId}-${index}`"
          :data-notice-id="notice.noticeId"
        >
          {{ noticeMessage(notice.noticeId) }}
        </li>
      </ul>
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

      <div
        class="mb-5 rounded-xl border border-slate-300 bg-white p-4 dark:border-slate-600 dark:bg-slate-900"
      >
        <button
          type="button"
          class="rounded-lg border border-slate-400 px-4 py-2 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-500"
          data-testid="commit-pitch"
          :disabled="!commitGate.committable"
          :aria-describedby="
            commitGate.committable ? undefined : 'commit-blocked-reason'
          "
        >
          1球を確定
        </button>
        <p
          v-if="!commitGate.committable"
          id="commit-blocked-reason"
          class="mt-2 text-sm text-slate-700 dark:text-slate-300"
          data-testid="commit-blocked-reason"
        >
          {{ commitGate.reason }}
        </p>
      </div>

      <ul
        v-if="eligibility && !eligibility.eligible"
        class="mb-4 list-disc space-y-1 rounded-lg border border-amber-500 p-3 pl-8 text-sm"
        data-testid="input-ineligible-reasons"
      >
        <li v-for="reason in eligibility.reasons" :key="reason">
          {{ PITCH_INPUT_INELIGIBILITY_MESSAGE[reason] }}
        </li>
      </ul>

      <p
        v-if="draftAssembly"
        class="mb-4 text-sm"
        data-testid="draft-assembly-status"
      >
        {{
          draftAssembly.ok
            ? '下書きを組み立てました（保存も送信もしていません）'
            : `下書きを組み立てられません: ${draftAssembly.reason.target}`
        }}
      </p>

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
                :disabled="!inputEnabled"
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
                :disabled="!inputEnabled"
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
                :disabled="!inputEnabled"
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
