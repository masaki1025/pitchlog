<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  sameDisplayValue,
  snapshotDisplayValue,
} from './GameScreenDisplayValue'
import GameScreenObservationField from './GameScreenObservationField.vue'
import type {
  ObservationAnswer,
  PlayObservationCase,
  PlayObservationQuestion,
  PlayObservationRequest,
  RawPlayObservation,
  SingleObservationQuestion,
} from './GameScreenPlayObservationTypes'

const props = defineProps<{
  request?: PlayObservationRequest | null
  /** 試合・プレイ文脈の識別子。要求側のキーと一致しなければ入力を閉じる。 */
  activeContextKey?: string | null
  /** 旧投球下書きと同じ試合・プレイ識別子。変更時は観測も破棄する。 */
  eventIdentity?: unknown
}>()

const actionId = ref<string | null>(null)
const ballX = ref('')
const ballY = ref('')
const fielderId = ref<string | null>(null)
const answers = ref(new Map<string, Map<string, ObservationAnswer>>())
const draftClearedNotice = ref(false)

function hasDraft(): boolean {
  return (
    actionId.value !== null ||
    ballX.value !== '' ||
    ballY.value !== '' ||
    fielderId.value !== null ||
    [...answers.value.values()].some((fields) =>
      [...fields.values()].some((value) => value !== null),
    )
  )
}

function reset() {
  actionId.value = null
  ballX.value = ''
  ballY.value = ''
  fielderId.value = null
  answers.value = new Map()
}

function clearObservation() {
  reset()
  draftClearedNotice.value = false
}

function discardChangedDraft() {
  const discarded = hasDraft()
  reset()
  draftClearedNotice.value = discarded
}

let previousInputs = snapshotDisplayValue([
  props.request,
  props.activeContextKey,
  props.eventIdentity,
])

// 表示契約の内容または試合文脈が変わった場合だけ旧下書きを破棄する。
watch(
  () => [props.request, props.activeContextKey, props.eventIdentity],
  (current) => {
    if (sameDisplayValue(previousInputs, current)) return
    discardChangedDraft()
    previousInputs = snapshotDisplayValue(current)
  },
  {
    deep: true,
    flush: 'sync',
  },
)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function uniqueOptions(question: unknown): question is PlayObservationQuestion {
  if (!isRecord(question) || !Array.isArray(question.options)) return false
  return (
    typeof question.key === 'string' &&
    question.key.length > 0 &&
    typeof question.label === 'string' &&
    typeof question.required === 'boolean' &&
    (question.multiple === undefined ||
      typeof question.multiple === 'boolean') &&
    question.options.every(
      (option) =>
        isRecord(option) &&
        typeof option.id === 'string' &&
        option.id.length > 0 &&
        typeof option.label === 'string',
    ) &&
    new Set(question.options.map((option: { id: string }) => option.id))
      .size === question.options.length
  )
}

function validSingleQuestion(
  question: unknown,
): question is SingleObservationQuestion {
  return (
    uniqueOptions(question) &&
    (question.multiple === undefined || question.multiple === false)
  )
}

function validQuestions(questions: unknown): boolean {
  if (questions === undefined) return true
  if (!Array.isArray(questions) || !questions.every(uniqueOptions)) return false
  return (
    new Set(questions.map((question) => question.key)).size === questions.length
  )
}

function validCase(observation: unknown): observation is PlayObservationCase {
  if (!isRecord(observation)) return false
  const runners = observation.runners
  if (
    !Array.isArray(runners) ||
    runners.some(
      (runner) =>
        !isRecord(runner) ||
        typeof runner.runnerKey !== 'string' ||
        runner.runnerKey.length === 0 ||
        typeof runner.displayName !== 'string',
    ) ||
    new Set(runners.map((runner: { runnerKey: string }) => runner.runnerKey))
      .size !== runners.length
  )
    return false
  if (observation.battedBall !== undefined) {
    const ball = observation.battedBall
    if (
      !isRecord(ball) ||
      !Array.isArray(ball.fielderCandidates) ||
      ball.fielderCandidates.some(
        (item) =>
          !isRecord(item) ||
          typeof item.id !== 'string' ||
          item.id.length === 0 ||
          typeof item.label !== 'string',
      ) ||
      new Set(ball.fielderCandidates.map((item: { id: string }) => item.id))
        .size !== ball.fielderCandidates.length ||
      (ball.suggestedFielderId !== undefined &&
        ball.suggestedFielderId !== null &&
        typeof ball.suggestedFielderId !== 'string')
    ) {
      return false
    }
  }
  if (
    (observation.playResult !== undefined &&
      !validSingleQuestion(observation.playResult)) ||
    (observation.rbiRuling !== undefined &&
      !validSingleQuestion(observation.rbiRuling)) ||
    !validQuestions(observation.interferenceQuestions) ||
    !validQuestions(observation.officialScoringQuestions)
  )
    return false
  return runners.every(
    (runner: Record<string, unknown>) =>
      [
        runner.advanceResult,
        runner.destinationBase,
        runner.attemptedBase,
        runner.thirdOutTiming,
        runner.rbiRuling,
      ].every(
        (question) => question === undefined || validSingleQuestion(question),
      ) &&
      validQuestions(runner.interferenceQuestions) &&
      validQuestions(runner.officialScoringQuestions),
  )
}

const requestReady = computed(() => {
  const request = props.request
  if (
    !request ||
    !request.contextKey ||
    !props.activeContextKey ||
    request.contextKey !== props.activeContextKey
  )
    return false
  if (request.mode === 'pitch') return validCase(request.observation)
  if (request.mode !== 'non-pitch') return false
  return (
    Array.isArray(request.actions) &&
    request.actions.every(
      (action) =>
        isRecord(action) &&
        typeof action.id === 'string' &&
        action.id.length > 0 &&
        typeof action.label === 'string' &&
        isRecord(action.observation) &&
        action.observation.playResult === undefined &&
        action.observation.battedBall === undefined &&
        validCase(action.observation),
    ) &&
    new Set(request.actions.map((action) => action.id)).size ===
      request.actions.length
  )
})

const observationCase = computed(() => {
  if (!requestReady.value || !props.request) return null
  if (props.request.mode === 'pitch') return props.request.observation
  return (
    props.request.actions.find((action) => action.id === actionId.value)
      ?.observation ?? null
  )
})

const suggestedFielder = computed(() => {
  const ball = observationCase.value?.battedBall
  return (
    ball?.fielderCandidates.find(
      (candidate) => candidate.id === ball.suggestedFielderId,
    )?.label ?? '未取得'
  )
})

const suggestedFielderId = computed(() => {
  const ball = observationCase.value?.battedBall
  return (
    ball?.fielderCandidates.find(
      (candidate) => candidate.id === ball.suggestedFielderId,
    )?.id ?? null
  )
})

function chooseSuggestedFielder() {
  if (suggestedFielderId.value !== null) {
    fielderId.value = suggestedFielderId.value
  }
}

function selectAction(event: Event) {
  discardChangedDraft()
  const id = (event.target as HTMLSelectElement).value
  if (
    props.request?.mode === 'non-pitch' &&
    props.request.actions.some((action) => action.id === id)
  ) {
    actionId.value = id
  }
}

function selectFielder(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  fielderId.value = observationCase.value?.battedBall?.fielderCandidates.some(
    (candidate) => candidate.id === id,
  )
    ? id
    : null
}

function scope(category: string, runnerKey?: string): string {
  return JSON.stringify([category, runnerKey ?? null])
}

function answer(
  category: string,
  question: PlayObservationQuestion,
  runnerKey?: string,
): ObservationAnswer {
  return (
    answers.value.get(scope(category, runnerKey))?.get(question.key) ?? null
  )
}

function setAnswer(
  category: string,
  question: PlayObservationQuestion,
  value: ObservationAnswer,
  runnerKey?: string,
) {
  const key = scope(category, runnerKey)
  const current = new Map(answers.value.get(key) ?? [])
  current.set(question.key, value)
  answers.value = new Map(answers.value).set(key, current)
}

function single(
  category: string,
  question?: SingleObservationQuestion,
  runnerKey?: string,
): string | null {
  if (!question) return null
  const value = answer(category, question, runnerKey)
  if (typeof value === 'string' || value === null) return value
  throw new Error('単一選択の観測に複数値が含まれています')
}

function questionAnswers(
  category: string,
  questions: readonly PlayObservationQuestion[] = [],
  runnerKey?: string,
): Record<string, ObservationAnswer> {
  return Object.fromEntries(
    questions.map((question) => {
      const value = answer(category, question, runnerKey)
      return [question.key, Array.isArray(value) ? [...value] : value]
    }),
  )
}

function rawText(value: string): string | null {
  return value === '' ? null : value
}

/** 表示専用 raw 観測のコピー。未提供・文脈不一致では取得できない。 */
function getRawObservation(): RawPlayObservation | null {
  const request = props.request
  const current = observationCase.value
  if (!requestReady.value || !request || !current) return null
  const runnerAdvanceOverridesByRunner: RawPlayObservation['runnerAdvanceOverridesByRunner'] =
    Object.create(null)
  const runnerEventsByRunner: RawPlayObservation['runnerEventsByRunner'] =
    Object.create(null)
  const thirdOutTimingByRunner: RawPlayObservation['thirdOutTimingByRunner'] =
    Object.create(null)
  const rbiByRunner: Record<string, string | null> = Object.create(null)
  const interferenceByRunner: Record<
    string,
    Record<string, ObservationAnswer>
  > = Object.create(null)
  const officialByRunner: Record<
    string,
    Record<string, ObservationAnswer>
  > = Object.create(null)

  for (const runner of current.runners) {
    const resultId = single(
      'advanceResult',
      runner.advanceResult,
      runner.runnerKey,
    )
    const destinationBaseId = single(
      'destinationBase',
      runner.destinationBase,
      runner.runnerKey,
    )
    const attemptedBaseId = single(
      'attemptedBase',
      runner.attemptedBase,
      runner.runnerKey,
    )
    if (request.mode === 'non-pitch') {
      runnerEventsByRunner[runner.runnerKey] = {
        resultId,
        destinationBaseId,
        attemptedBaseId,
      }
    } else if (
      resultId !== null ||
      destinationBaseId !== null ||
      attemptedBaseId !== null
    ) {
      runnerAdvanceOverridesByRunner[runner.runnerKey] = {
        resultId,
        destinationBaseId,
        attemptedBaseId,
      }
    }
    if (runner.thirdOutTiming) {
      thirdOutTimingByRunner[runner.runnerKey] = single(
        'thirdOutTiming',
        runner.thirdOutTiming,
        runner.runnerKey,
      )
    }
    if (runner.rbiRuling) {
      rbiByRunner[runner.runnerKey] = single(
        'rbiRuling',
        runner.rbiRuling,
        runner.runnerKey,
      )
    }
    if (runner.interferenceQuestions?.length) {
      interferenceByRunner[runner.runnerKey] = questionAnswers(
        'interference',
        runner.interferenceQuestions,
        runner.runnerKey,
      )
    }
    if (runner.officialScoringQuestions?.length) {
      officialByRunner[runner.runnerKey] = questionAnswers(
        'official',
        runner.officialScoringQuestions,
        runner.runnerKey,
      )
    }
  }

  return {
    contextKey: request.contextKey,
    mode: request.mode,
    actionId: request.mode === 'non-pitch' ? actionId.value : null,
    playResultId: single('playResult', current.playResult),
    battedBall: current.battedBall
      ? {
          x: rawText(ballX.value),
          y: rawText(ballY.value),
          fielderId: fielderId.value,
        }
      : null,
    runnerAdvanceOverridesByRunner,
    runnerEventsByRunner,
    thirdOutTimingByRunner,
    rbiRuling: {
      play: single('rbiRuling', current.rbiRuling),
      byRunner: rbiByRunner,
    },
    interferenceRuling: {
      play: questionAnswers('interference', current.interferenceQuestions),
      byRunner: interferenceByRunner,
    },
    officialScoringPayload: {
      play: questionAnswers('official', current.officialScoringQuestions),
      byRunner: officialByRunner,
    },
  }
}

defineExpose({ getRawObservation })
</script>

<template>
  <section
    aria-label="打球・走者観測の下書き"
    class="min-w-0 space-y-4 rounded-2xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30"
  >
    <h2 class="text-lg font-extrabold">打球・走者観測の下書き</h2>
    <p class="text-sm">
      この入力は保存・送信されません。画面を離れると消えます。
    </p>
    <p
      v-if="draftClearedNotice"
      role="status"
      data-testid="observation-draft-cleared"
      class="text-sm font-bold"
    >
      入力対象または試合文脈が変わったため、未保存の観測下書きを消去しました。
    </p>
    <p
      v-if="!requestReady"
      data-testid="observation-unavailable"
      class="text-sm"
    >
      入力対象と試合文脈の提供待ちです。観測入力はできません。
    </p>
    <template v-else-if="request">
      <p data-testid="observation-mode" class="text-sm font-bold">
        {{ request.mode === 'pitch' ? '投球時の観測' : '非投球プレイの観測' }}
      </p>
      <div v-if="request.mode === 'non-pitch'" class="min-w-0 space-y-1">
        <label for="non-pitch-action" class="block text-sm font-bold"
          >非投球の種別（入力対象）</label
        >
        <select
          id="non-pitch-action"
          data-testid="non-pitch-action"
          :value="actionId ?? ''"
          class="w-full min-w-0 rounded border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-900"
          @change="selectAction"
        >
          <option value="">未選択</option>
          <option
            v-for="action in request.actions"
            :key="action.id"
            :value="action.id"
          >
            {{ action.label }}
          </option>
        </select>
      </div>
      <p
        v-if="request.mode === 'non-pitch' && !observationCase"
        class="text-sm"
      >
        種別を選ぶと、提供された対象走者と質問を表示します。
      </p>
      <div v-if="observationCase" class="min-w-0 space-y-5">
        <GameScreenObservationField
          v-if="observationCase.playResult"
          :question="observationCase.playResult"
          :value="answer('playResult', observationCase.playResult)"
          @change="setAnswer('playResult', observationCase.playResult!, $event)"
        />
        <div
          v-if="observationCase.battedBall"
          class="min-w-0 space-y-3 rounded-xl border border-slate-300 p-3 dark:border-slate-600"
          data-testid="batted-ball"
        >
          <h3 class="font-bold">打球観測</h3>
          <p class="text-sm">
            打球座標は X/Y とも 0〜1
            の値を入力してください。画面上のタップ入力は準備中です。
          </p>
          <div class="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
            <label class="min-w-0 text-sm"
              >打球座標 X<input
                v-model="ballX"
                data-testid="ball-x"
                type="text"
                inputmode="decimal"
                autocomplete="off"
                class="mt-1 w-full min-w-0 rounded border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-900"
            /></label>
            <label class="min-w-0 text-sm"
              >打球座標 Y<input
                v-model="ballY"
                data-testid="ball-y"
                type="text"
                inputmode="decimal"
                autocomplete="off"
                class="mt-1 w-full min-w-0 rounded border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-900"
            /></label>
          </div>
          <button
            type="button"
            disabled
            data-testid="ball-tap"
            class="min-w-0 rounded border border-slate-400 p-2 text-sm disabled:opacity-60"
            @click.stop.prevent
          >
            フィールドをタップして入力（接続待ち）
          </button>
          <p class="text-sm" data-testid="suggested-fielder">
            提供された捕球候補: {{ suggestedFielder }}
          </p>
          <button
            v-if="suggestedFielderId"
            type="button"
            data-testid="choose-suggested-fielder"
            class="min-w-0 rounded border border-slate-400 p-2 text-sm"
            @click="chooseSuggestedFielder"
          >
            この候補を選ぶ
          </button>
          <label class="block min-w-0 text-sm font-bold"
            >捕球選手を手動選択
            <select
              :value="fielderId ?? ''"
              data-testid="fielder"
              class="mt-1 w-full min-w-0 rounded border border-slate-300 bg-white p-2 dark:border-slate-600 dark:bg-slate-900"
              @change="selectFielder"
            >
              <option value="">未選択</option>
              <option
                v-for="candidate in observationCase.battedBall
                  .fielderCandidates"
                :key="candidate.id"
                :value="candidate.id"
              >
                {{ candidate.label }}
              </option>
            </select>
          </label>
        </div>
        <div
          v-for="runner in observationCase.runners"
          :key="runner.runnerKey"
          class="min-w-0 space-y-3 rounded-xl border border-slate-300 p-3 dark:border-slate-600"
          data-testid="runner-observation"
          :data-runner-key="runner.runnerKey"
        >
          <h3 class="font-bold wrap-anywhere">{{ runner.displayName }}</h3>
          <GameScreenObservationField
            v-if="runner.advanceResult"
            :question="runner.advanceResult"
            :value="
              answer('advanceResult', runner.advanceResult, runner.runnerKey)
            "
            @change="
              setAnswer(
                'advanceResult',
                runner.advanceResult!,
                $event,
                runner.runnerKey,
              )
            "
          />
          <GameScreenObservationField
            v-if="runner.destinationBase"
            :question="runner.destinationBase"
            :value="
              answer(
                'destinationBase',
                runner.destinationBase,
                runner.runnerKey,
              )
            "
            @change="
              setAnswer(
                'destinationBase',
                runner.destinationBase!,
                $event,
                runner.runnerKey,
              )
            "
          />
          <GameScreenObservationField
            v-if="runner.attemptedBase"
            :question="runner.attemptedBase"
            :value="
              answer('attemptedBase', runner.attemptedBase, runner.runnerKey)
            "
            @change="
              setAnswer(
                'attemptedBase',
                runner.attemptedBase!,
                $event,
                runner.runnerKey,
              )
            "
          />
          <GameScreenObservationField
            v-if="runner.thirdOutTiming"
            :question="runner.thirdOutTiming"
            :value="
              answer('thirdOutTiming', runner.thirdOutTiming, runner.runnerKey)
            "
            @change="
              setAnswer(
                'thirdOutTiming',
                runner.thirdOutTiming!,
                $event,
                runner.runnerKey,
              )
            "
          />
          <GameScreenObservationField
            v-if="runner.rbiRuling"
            :question="runner.rbiRuling"
            :value="answer('rbiRuling', runner.rbiRuling, runner.runnerKey)"
            @change="
              setAnswer(
                'rbiRuling',
                runner.rbiRuling!,
                $event,
                runner.runnerKey,
              )
            "
          />
          <GameScreenObservationField
            v-for="question in runner.interferenceQuestions ?? []"
            :key="`interference-${question.key}`"
            :question="question"
            :value="answer('interference', question, runner.runnerKey)"
            @change="
              setAnswer('interference', question, $event, runner.runnerKey)
            "
          />
          <GameScreenObservationField
            v-for="question in runner.officialScoringQuestions ?? []"
            :key="`official-${question.key}`"
            :question="question"
            :value="answer('official', question, runner.runnerKey)"
            @change="setAnswer('official', question, $event, runner.runnerKey)"
          />
        </div>
        <GameScreenObservationField
          v-if="observationCase.rbiRuling"
          :question="observationCase.rbiRuling"
          :value="answer('rbiRuling', observationCase.rbiRuling)"
          @change="setAnswer('rbiRuling', observationCase.rbiRuling!, $event)"
        />
        <GameScreenObservationField
          v-for="question in observationCase.interferenceQuestions ?? []"
          :key="`interference-${question.key}`"
          :question="question"
          :value="answer('interference', question)"
          @change="setAnswer('interference', question, $event)"
        />
        <GameScreenObservationField
          v-for="question in observationCase.officialScoringQuestions ?? []"
          :key="`official-${question.key}`"
          :question="question"
          :value="answer('official', question)"
          @change="setAnswer('official', question, $event)"
        />
        <button
          type="button"
          data-testid="clear-observation"
          class="min-w-0 rounded border border-amber-600 p-2 text-sm font-bold"
          @click="clearObservation"
        >
          観測下書きを消去
        </button>
      </div>
      <div
        class="min-w-0 rounded-xl border border-slate-300 p-3 dark:border-slate-600"
      >
        <button
          type="button"
          disabled
          data-testid="commit-observation"
          class="min-w-0 rounded border border-slate-400 p-2 text-sm font-bold disabled:opacity-60"
          @click.stop.prevent
        >
          観測を確定
        </button>
        <p class="mt-2 text-sm" data-testid="observation-blocked">
          入力要求・単一計算・保存経路の正式接続待ちです。実確定はできません。
        </p>
      </div>
    </template>
  </section>
</template>
