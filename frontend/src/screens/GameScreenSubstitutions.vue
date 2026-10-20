<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { UndoOffer } from './GameScreenCorrectionTypes'
import {
  sameDisplayValue,
  snapshotDisplayValue,
} from './GameScreenDisplayValue'
import type {
  PastSubstitutionPreview,
  PastSubstitutionRequest,
  RawSubstitutionDraft,
  SubstitutionDraftsSnapshot,
  SubstitutionChoice,
  SubstitutionDraftIdentity,
  SubstitutionKind,
  SubstitutionLockState,
  SubstitutionOperationSupply,
  SubstitutionQuestion,
  SubstitutionRequest,
  SubstitutionValidation,
  TiebreakRequest,
} from './GameScreenSubstitutionTypes'

const props = defineProps<{
  request?: SubstitutionRequest | null
  tiebreakRequest?: TiebreakRequest | null
  pastRequest?: PastSubstitutionRequest | null
  activeContextKey?: string | null
  lockState?: SubstitutionLockState | null
  undoOffer?: UndoOffer | null
  validation?: SubstitutionValidation | null
  preview?: PastSubstitutionPreview | null
}>()
const emit = defineEmits<{
  'draft-change': [snapshot: SubstitutionDraftsSnapshot]
}>()

const kindLabels: Record<SubstitutionKind, string> = {
  pitcher: '投手交代',
  'pinch-hitter': '代打',
  'pinch-runner': '代走',
  defense: '守備変更',
}
const kinds: readonly SubstitutionKind[] = [
  'pitcher',
  'pinch-hitter',
  'pinch-runner',
  'defense',
]

function createUiInstanceId(): string | null {
  try {
    const random = globalThis.crypto
    if (typeof random?.getRandomValues === 'function') {
      return Array.from(random.getRandomValues(new Uint8Array(16)), (byte) =>
        byte.toString(16).padStart(2, '0'),
      ).join('')
    }
  } catch {
    // 識別子が得られない場合、提供結果の照合だけを閉じる。
  }
  return null
}
const uiInstanceId = createUiInstanceId()

function choicesReady(value: unknown): value is readonly SubstitutionChoice[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        item &&
        typeof item.id === 'string' &&
        !!item.id &&
        typeof item.label === 'string' &&
        !!item.label,
    ) &&
    new Set(value.map((item) => item.id)).size === value.length
  )
}

function questionsReady(
  value: unknown,
): value is readonly SubstitutionQuestion[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        item &&
        typeof item.key === 'string' &&
        !!item.key &&
        typeof item.label === 'string' &&
        !!item.label &&
        typeof item.required === 'boolean' &&
        (item.input === 'text' ||
          (item.input === 'choice' &&
            choicesReady(item.options) &&
            item.options.length > 0)),
    ) &&
    new Set(value.map((item) => item.key)).size === value.length
  )
}

function distinctQuestions(
  groups: readonly (readonly SubstitutionQuestion[])[],
) {
  const keys = groups.flat().map((item) => item.key)
  return new Set(keys).size === keys.length
}

const contextReady = computed(
  () => typeof props.activeContextKey === 'string' && !!props.activeContextKey,
)
const requestReady = computed(() => {
  const request = props.request
  if (!request) return false
  return (
    contextReady.value &&
    request?.contextKey === props.activeContextKey &&
    Array.isArray(request.operations) &&
    request.operations.length > 0 &&
    request.operations.every(
      (item) =>
        kinds.includes(item.kind) &&
        choicesReady(item.outgoing) &&
        item.outgoing.length > 0 &&
        choicesReady(item.incoming) &&
        questionsReady(item.registrationQuestions) &&
        questionsReady(item.placementQuestions) &&
        questionsReady(item.questions) &&
        distinctQuestions([
          item.registrationQuestions,
          item.placementQuestions,
          item.questions,
        ]),
    ) &&
    new Set(request.operations.map((item) => item.kind)).size ===
      request.operations.length
  )
})
const tiebreakReady = computed(() => {
  const request = props.tiebreakRequest
  if (!request) return false
  return (
    contextReady.value &&
    request?.contextKey === props.activeContextKey &&
    questionsReady(request.placementQuestions) &&
    request.placementQuestions.length > 0 &&
    questionsReady(request.leadBatterQuestions) &&
    request.leadBatterQuestions.length > 0 &&
    questionsReady(request.inningQuestions) &&
    request.inningQuestions.length > 0 &&
    distinctQuestions([
      request.placementQuestions,
      request.leadBatterQuestions,
      request.inningQuestions,
    ])
  )
})
const pastReady = computed(() => {
  const request = props.pastRequest
  if (!request) return false
  return (
    contextReady.value &&
    request?.contextKey === props.activeContextKey &&
    !!request.page &&
    typeof request.page.label === 'string' &&
    !!request.page.label &&
    choicesReady(request.page.targets) &&
    request.page.targets.every((item) => typeof item.detail === 'string') &&
    typeof request.page.hasPrevious === 'boolean' &&
    typeof request.page.hasNext === 'boolean' &&
    questionsReady(request.personQuestions) &&
    request.personQuestions.length > 0 &&
    questionsReady(request.inningQuestions) &&
    request.inningQuestions.length > 0 &&
    questionsReady(request.timingQuestions) &&
    request.timingQuestions.length > 0 &&
    distinctQuestions([
      request.personQuestions,
      request.inningQuestions,
      request.timingQuestions,
    ])
  )
})

let nextDraftId = 0
const normalDraftId = ref(++nextDraftId)
const tiebreakDraftId = ref(++nextDraftId)
const pastDraftId = ref(++nextDraftId)
const kind = ref<SubstitutionKind | null>(null)
const outgoingId = ref<string | null>(null)
const incomingMode = ref<'existing' | 'new' | null>(null)
const incomingId = ref<string | null>(null)
const normalAnswers = ref(new Map<string, string>())
const tiebreakAnswers = ref(new Map<string, string>())
const pastTargetId = ref<string | null>(null)
const pastAnswers = ref(new Map<string, string>())
const normalCleared = ref(false)
const tiebreakCleared = ref(false)
const pastCleared = ref(false)

function resetNormal() {
  const hadDraft =
    kind.value !== null ||
    outgoingId.value !== null ||
    incomingMode.value !== null ||
    incomingId.value !== null ||
    normalAnswers.value.size > 0
  kind.value = null
  outgoingId.value = null
  incomingMode.value = null
  incomingId.value = null
  normalAnswers.value = new Map()
  normalDraftId.value = ++nextDraftId
  normalCleared.value = hadDraft
}
function resetTiebreak() {
  const hadDraft = tiebreakAnswers.value.size > 0
  tiebreakAnswers.value = new Map()
  tiebreakDraftId.value = ++nextDraftId
  tiebreakCleared.value = hadDraft
}
function resetPast() {
  const hadDraft = pastTargetId.value !== null || pastAnswers.value.size > 0
  pastTargetId.value = null
  pastAnswers.value = new Map()
  pastDraftId.value = ++nextDraftId
  pastCleared.value = hadDraft
}

// 同内容の新参照では保持し、実文脈・供給質問の変更時だけ破棄する。
let previousNormal = snapshotDisplayValue([
  props.activeContextKey,
  props.request,
])
let previousTiebreak = snapshotDisplayValue([
  props.activeContextKey,
  props.tiebreakRequest,
])
let previousPast = snapshotDisplayValue([
  props.activeContextKey,
  props.pastRequest,
])
watch(
  () => [
    props.activeContextKey,
    props.request,
    props.tiebreakRequest,
    props.pastRequest,
  ],
  () => {
    const normal = [props.activeContextKey, props.request]
    const tiebreak = [props.activeContextKey, props.tiebreakRequest]
    const past = [props.activeContextKey, props.pastRequest]
    const normalChanged = !sameDisplayValue(previousNormal, normal)
    const tiebreakChanged = !sameDisplayValue(previousTiebreak, tiebreak)
    const pastChanged = !sameDisplayValue(previousPast, past)
    if (normalChanged) resetNormal()
    if (tiebreakChanged) resetTiebreak()
    if (pastChanged) resetPast()
    previousNormal = snapshotDisplayValue(normal)
    previousTiebreak = snapshotDisplayValue(tiebreak)
    previousPast = snapshotDisplayValue(past)
    if (normalChanged || tiebreakChanged || pastChanged) emitDraftChange()
  },
  { deep: true, flush: 'sync' },
)

const selectedOperation = computed<SubstitutionOperationSupply | null>(() =>
  requestReady.value
    ? (props.request?.operations.find((item) => item.kind === kind.value) ??
      null)
    : null,
)
const normalQuestions = computed(() => [
  ...(selectedOperation.value?.questions ?? []),
  ...(selectedOperation.value?.placementQuestions ?? []),
  ...(incomingMode.value === 'new'
    ? (selectedOperation.value?.registrationQuestions ?? [])
    : []),
])
// 必須性は供給値だけを読む。9位置・打順・交代可否の意味判定は行わない。
const normalFieldsSelected = computed(
  () =>
    !!selectedOperation.value &&
    normalQuestions.value.length > 0 &&
    outgoingId.value !== null &&
    (incomingMode.value === 'existing'
      ? incomingId.value !== null
      : incomingMode.value === 'new' &&
        selectedOperation.value.registrationQuestions.length > 0) &&
    normalQuestions.value.every(
      (question) =>
        !question.required || !!normalAnswers.value.get(question.key)?.trim(),
    ),
)
const tiebreakQuestions = computed(() => [
  ...(tiebreakReady.value ? props.tiebreakRequest!.placementQuestions : []),
  ...(tiebreakReady.value ? props.tiebreakRequest!.leadBatterQuestions : []),
  ...(tiebreakReady.value ? props.tiebreakRequest!.inningQuestions : []),
])
const pastQuestions = computed(() => [
  ...(pastReady.value ? props.pastRequest!.personQuestions : []),
  ...(pastReady.value ? props.pastRequest!.inningQuestions : []),
  ...(pastReady.value ? props.pastRequest!.timingQuestions : []),
])
const pastFieldsSelected = computed(
  () =>
    pastTargetId.value !== null &&
    pastQuestions.value.every(
      (question) =>
        !question.required || !!pastAnswers.value.get(question.key)?.trim(),
    ),
)

function choose(
  value: string,
  choices: readonly SubstitutionChoice[],
): string | null {
  return choices.some((item) => item.id === value) ? value : null
}
function selectKind(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  kind.value =
    props.request?.operations.find((item) => item.kind === value)?.kind ?? null
  outgoingId.value = null
  incomingMode.value = null
  incomingId.value = null
  normalAnswers.value = new Map()
  normalDraftId.value = ++nextDraftId
  normalCleared.value = false
  emitDraftChange()
}
function selectOutgoing(event: Event) {
  outgoingId.value = choose(
    (event.target as HTMLSelectElement).value,
    selectedOperation.value?.outgoing ?? [],
  )
  normalDraftId.value = ++nextDraftId
  emitDraftChange()
}
function selectIncomingMode(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  incomingMode.value =
    value === 'existing'
      ? 'existing'
      : value === 'new' &&
          !!selectedOperation.value?.registrationQuestions.length
        ? 'new'
        : null
  incomingId.value = null
  normalAnswers.value = new Map()
  normalDraftId.value = ++nextDraftId
  emitDraftChange()
}
function selectIncoming(event: Event) {
  incomingId.value = choose(
    (event.target as HTMLSelectElement).value,
    selectedOperation.value?.incoming ?? [],
  )
  normalDraftId.value = ++nextDraftId
  emitDraftChange()
}
function selectPastTarget(event: Event) {
  pastTargetId.value = choose(
    (event.target as HTMLSelectElement).value,
    props.pastRequest?.page.targets ?? [],
  )
  pastAnswers.value = new Map()
  pastDraftId.value = ++nextDraftId
  pastCleared.value = false
  emitDraftChange()
}
function setAnswer(
  area: 'normal' | 'tiebreak' | 'past',
  question: SubstitutionQuestion,
  event: Event,
) {
  const questions =
    area === 'normal'
      ? normalQuestions.value
      : area === 'tiebreak'
        ? tiebreakQuestions.value
        : pastQuestions.value
  if (!questions.includes(question)) return
  const value = (event.target as HTMLInputElement | HTMLSelectElement).value
  if (
    question.input === 'choice' &&
    value !== '' &&
    !question.options?.some((item) => item.id === value)
  )
    return
  const current =
    area === 'normal'
      ? normalAnswers.value
      : area === 'tiebreak'
        ? tiebreakAnswers.value
        : pastAnswers.value
  const updated = new Map(current)
  if (value === '') updated.delete(question.key)
  else updated.set(question.key, value)
  if (area === 'normal') {
    normalAnswers.value = updated
    normalDraftId.value = ++nextDraftId
  } else if (area === 'tiebreak') {
    tiebreakAnswers.value = updated
    tiebreakDraftId.value = ++nextDraftId
  } else {
    pastAnswers.value = updated
    pastDraftId.value = ++nextDraftId
  }
  emitDraftChange()
}

function identity(
  operation: SubstitutionDraftIdentity['operation'],
  targetId: string | null,
  draftId: number,
  ready: boolean,
): SubstitutionDraftIdentity | null {
  if (!ready || !uiInstanceId || !props.activeContextKey) return null
  return {
    contextKey: props.activeContextKey,
    uiInstanceId,
    draftId,
    operation,
    targetId,
  }
}
const normalIdentity = computed(() =>
  kind.value
    ? identity(
        kind.value,
        outgoingId.value,
        normalDraftId.value,
        !!selectedOperation.value,
      )
    : null,
)
const tiebreakIdentity = computed(() =>
  identity('tiebreak', null, tiebreakDraftId.value, tiebreakReady.value),
)
const pastIdentity = computed(() =>
  identity(
    'past-correction',
    pastTargetId.value,
    pastDraftId.value,
    pastReady.value && pastTargetId.value !== null,
  ),
)
function sameIdentity(
  left: SubstitutionDraftIdentity | null,
  right: SubstitutionDraftIdentity | null | undefined,
) {
  return (
    !!left &&
    !!right &&
    left.contextKey === right.contextKey &&
    left.uiInstanceId === right.uiInstanceId &&
    left.draftId === right.draftId &&
    left.operation === right.operation &&
    left.targetId === right.targetId
  )
}
const currentValidation = computed(() =>
  sameIdentity(normalIdentity.value, props.validation?.identity) &&
  ['pending', 'failed', 'invalid', 'valid'].includes(props.validation!.kind) &&
  (props.validation!.messages === undefined ||
    (Array.isArray(props.validation!.messages) &&
      props.validation!.messages.every((item) => typeof item === 'string')))
    ? props.validation
    : null,
)
const currentPreview = computed(() =>
  sameIdentity(pastIdentity.value, props.preview?.identity) &&
  ['pending', 'failed', 'conflict', 'ready'].includes(props.preview!.kind) &&
  (props.preview!.kind !== 'ready' || pastFieldsSelected.value) &&
  (props.preview!.kind !== 'ready' ||
    (Array.isArray(props.preview!.rows) &&
      props.preview!.rows.length > 0 &&
      props.preview!.rows.every(
        (row) =>
          !!row &&
          typeof row.label === 'string' &&
          !!row.label &&
          typeof row.before === 'string' &&
          typeof row.after === 'string',
      )))
    ? props.preview
    : null,
)

// 親のUndoOffer文脈付き型が取り込まれるまで、実行時に存在を確かめて安全側へ倒す。
const matchedUndoOffer = computed(() => {
  const offer = props.undoOffer
  const active = props.activeContextKey
  return offer &&
    typeof active === 'string' &&
    !!active &&
    'contextKey' in offer &&
    typeof offer.contextKey === 'string' &&
    offer.contextKey === active
    ? offer
    : null
})
const lockExplanation = computed(() => {
  switch (props.lockState) {
    case 'open':
      return '終了条件による交代の制限はありません。この画面ではまだ交代を記録できません。'
    case 'ending-locked-undo-available':
      return matchedUndoOffer.value?.kind === 'available'
        ? '終了条件により交代できません。直前取消の対象は上の欄にありますが、この画面ではまだ取り消せません。'
        : '終了条件により交代できません。直前取消の対象は確認できていません。上の欄を確認してください。'
    case 'ending-locked-undo-unavailable':
      return matchedUndoOffer.value?.kind === 'none'
        ? '終了条件により交代できません。直前取消の対象もありません。'
        : '終了条件により交代できません。直前取消の対象は確認できていません。上の欄を確認してください。'
    default:
      return '終了条件の状態は未取得です。交代できるか確認できません。取消の対象は上の直前取消欄で確認してください。'
  }
})

function answerRecord(
  questions: readonly SubstitutionQuestion[],
  answers: Map<string, string>,
) {
  return Object.fromEntries(
    questions.map((item) => [item.key, answers.get(item.key) ?? null]),
  )
}
/** UI専用raw下書き。正式な登録・交代・回切替要求は組み立てない。 */
function getDrafts(): SubstitutionDraftsSnapshot {
  const snapshot: {
    normal: RawSubstitutionDraft | null
    tiebreak: RawSubstitutionDraft | null
    past: RawSubstitutionDraft | null
  } = {
    normal: normalIdentity.value
      ? {
          identity: { ...normalIdentity.value },
          outgoingId: outgoingId.value,
          incomingMode: incomingMode.value,
          incomingId: incomingId.value,
          answers: answerRecord(normalQuestions.value, normalAnswers.value),
        }
      : null,
    tiebreak: tiebreakIdentity.value
      ? {
          identity: { ...tiebreakIdentity.value },
          outgoingId: null,
          incomingMode: null,
          incomingId: null,
          answers: answerRecord(tiebreakQuestions.value, tiebreakAnswers.value),
        }
      : null,
    past: pastIdentity.value
      ? {
          identity: { ...pastIdentity.value },
          outgoingId: null,
          incomingMode: null,
          incomingId: null,
          answers: answerRecord(pastQuestions.value, pastAnswers.value),
        }
      : null,
  }
  for (const draft of Object.values(snapshot)) {
    if (!draft) continue
    Object.freeze(draft.identity)
    Object.freeze(draft.answers)
    Object.freeze(draft)
  }
  return Object.freeze(snapshot)
}
function emitDraftChange() {
  emit('draft-change', getDrafts())
}
onMounted(() => {
  if (requestReady.value || tiebreakReady.value || pastReady.value) {
    emitDraftChange()
  }
})
</script>

<template>
  <section
    aria-label="選手交代とタイブレーク"
    class="min-w-0 space-y-5 rounded-2xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30"
  >
    <h2 class="text-lg font-extrabold">選手交代とタイブレーク</h2>
    <p class="wrap-anywhere text-sm">
      この入力は保存・送信されず、画面を離れると消えます。候補と検証結果は提供された内容だけを表示します。
    </p>
    <p
      data-testid="substitution-lock-status"
      class="wrap-anywhere text-sm font-bold"
    >
      {{ lockExplanation }}
    </p>

    <section
      aria-label="通常の選手交代"
      class="min-w-0 space-y-3 rounded-lg border p-3"
    >
      <h3 class="font-bold">通常の選手交代</h3>
      <p
        v-if="normalCleared"
        data-testid="substitution-draft-cleared"
        role="status"
        class="text-sm"
      >
        試合または入力項目が変わったため、未保存の交代下書きを消去しました。
      </p>
      <p v-if="!requestReady" data-testid="substitution-unavailable">
        交代の候補と入力項目は未取得です。確認できるまで操作できません。
      </p>
      <template v-else>
        <label class="block min-w-0 font-bold">
          交代の種類
          <select
            data-testid="substitution-kind"
            :value="kind ?? ''"
            class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
            @change="selectKind"
          >
            <option value="">未選択</option>
            <option
              v-for="item in request!.operations"
              :key="item.kind"
              :value="item.kind"
            >
              {{ kindLabels[item.kind] }}
            </option>
          </select>
        </label>
        <template v-if="selectedOperation">
          <label class="block min-w-0 font-bold">
            交代する選手
            <select
              data-testid="substitution-outgoing"
              :value="outgoingId ?? ''"
              class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
              @change="selectOutgoing"
            >
              <option value="">未選択</option>
              <option
                v-for="item in selectedOperation.outgoing"
                :key="item.id"
                :value="item.id"
              >
                {{ item.label }}
              </option>
            </select>
          </label>
          <label class="block min-w-0 font-bold">
            入る選手の指定方法
            <select
              data-testid="substitution-incoming-mode"
              :value="incomingMode ?? ''"
              class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
              @change="selectIncomingMode"
            >
              <option value="">未選択</option>
              <option value="existing">登録済み選手から選ぶ</option>
              <option
                v-if="selectedOperation.registrationQuestions.length"
                value="new"
              >
                その場で選手を登録
              </option>
            </select>
          </label>
          <label
            v-if="incomingMode === 'existing'"
            class="block min-w-0 font-bold"
          >
            入る選手
            <select
              data-testid="substitution-incoming"
              :value="incomingId ?? ''"
              class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
              @change="selectIncoming"
            >
              <option value="">未選択</option>
              <option
                v-for="item in selectedOperation.incoming"
                :key="item.id"
                :value="item.id"
              >
                {{ item.label }}
              </option>
            </select>
          </label>
          <p v-if="incomingMode === 'new'" class="text-sm">
            その場登録は下の提供項目を入力してください。登録はまだ行われません。
          </p>
          <fieldset
            v-for="group in [
              {
                label: '交代の追加項目',
                questions: selectedOperation.questions,
              },
              {
                label: '配置・守備位置',
                questions: selectedOperation.placementQuestions,
              },
              {
                label: 'その場登録',
                questions:
                  incomingMode === 'new'
                    ? selectedOperation.registrationQuestions
                    : [],
              },
            ]"
            :key="group.label"
            class="min-w-0 space-y-2 rounded border p-2"
          >
            <legend class="font-bold">{{ group.label }}</legend>
            <p v-if="!group.questions.length" class="text-sm">
              入力項目を確認できません。
            </p>
            <label
              v-for="question in group.questions"
              :key="question.key"
              class="block min-w-0 font-bold"
            >
              {{ question.label }}
              <input
                v-if="question.input === 'text'"
                type="text"
                autocomplete="off"
                :value="normalAnswers.get(question.key) ?? ''"
                :data-normal-question="question.key"
                class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
                @input="setAnswer('normal', question, $event)"
              />
              <select
                v-else
                :value="normalAnswers.get(question.key) ?? ''"
                :data-normal-question="question.key"
                class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
                @change="setAnswer('normal', question, $event)"
              >
                <option value="">未選択</option>
                <option
                  v-for="item in question.options"
                  :key="item.id"
                  :value="item.id"
                >
                  {{ item.label }}
                </option>
              </select>
            </label>
          </fieldset>
          <div
            data-testid="substitution-validation"
            class="min-w-0 space-y-1 text-sm"
          >
            <p v-if="!currentValidation">
              この下書きに対応する検証結果は未取得です。
            </p>
            <p v-else-if="currentValidation.kind === 'pending'">
              この下書きの検証を待っています。
            </p>
            <p v-else-if="currentValidation.kind === 'failed'">
              検証結果を取得できませんでした。
            </p>
            <p v-else-if="currentValidation.kind === 'invalid'">
              入力内容を確認できませんでした。
            </p>
            <p v-else-if="!normalQuestions.length">
              入力項目を確認できないため、検証済みとして扱えません。
            </p>
            <p v-else-if="!normalFieldsSelected">
              必要な選択または入力が未完了です。検証済みとして扱えません。
            </p>
            <p v-else>
              入力内容の確認が終わりました。変更はまだ行われていません。
            </p>
            <ul
              v-if="
                currentValidation?.messages?.length &&
                (currentValidation.kind !== 'valid' || normalFieldsSelected)
              "
              class="list-disc pl-5"
            >
              <li
                v-for="(message, index) in currentValidation.messages"
                :key="index"
                class="wrap-anywhere"
              >
                {{ message }}
              </li>
            </ul>
          </div>
        </template>
      </template>
      <p id="substitution-blocked-reason" class="text-sm">
        この画面ではまだ交代を記録できません。入力内容にかかわらず保存・送信されません。
      </p>
      <button
        type="button"
        disabled
        aria-describedby="substitution-blocked-reason"
        data-testid="substitution-apply"
        class="rounded border px-3 py-2 disabled:opacity-60"
        @click.stop.prevent
      >
        交代を記録
      </button>
    </section>

    <section
      aria-label="タイブレークと回"
      class="min-w-0 space-y-3 rounded-lg border p-3"
    >
      <h3 class="font-bold">タイブレークと回</h3>
      <p
        v-if="tiebreakCleared"
        data-testid="tiebreak-draft-cleared"
        role="status"
        class="text-sm"
      >
        試合または入力項目が変わったため、未保存のタイブレーク下書きを消去しました。
      </p>
      <p v-if="!tiebreakReady" data-testid="tiebreak-unavailable">
        配置・先頭打者・回の入力項目は未取得です。
      </p>
      <template v-else>
        <fieldset
          v-for="group in [
            {
              label: '走者の配置',
              questions: tiebreakRequest!.placementQuestions,
            },
            {
              label: '先頭打者',
              questions: tiebreakRequest!.leadBatterQuestions,
            },
            { label: '回の指定', questions: tiebreakRequest!.inningQuestions },
          ]"
          :key="group.label"
          class="min-w-0 space-y-2 rounded border p-2"
        >
          <legend class="font-bold">{{ group.label }}</legend>
          <label
            v-for="question in group.questions"
            :key="question.key"
            class="block min-w-0 font-bold"
          >
            {{ question.label }}
            <input
              v-if="question.input === 'text'"
              type="text"
              autocomplete="off"
              :value="tiebreakAnswers.get(question.key) ?? ''"
              :data-tiebreak-question="question.key"
              class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
              @input="setAnswer('tiebreak', question, $event)"
            />
            <select
              v-else
              :value="tiebreakAnswers.get(question.key) ?? ''"
              :data-tiebreak-question="question.key"
              class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
              @change="setAnswer('tiebreak', question, $event)"
            >
              <option value="">未選択</option>
              <option
                v-for="item in question.options"
                :key="item.id"
                :value="item.id"
              >
                {{ item.label }}
              </option>
            </select>
          </label>
        </fieldset>
      </template>
      <p id="tiebreak-blocked-reason" class="text-sm">
        この画面ではまだ配置・先頭打者・回を記録できません。入力は保存されません。
      </p>
      <button
        type="button"
        disabled
        aria-describedby="tiebreak-blocked-reason"
        data-testid="tiebreak-apply"
        class="rounded border px-3 py-2 disabled:opacity-60"
        @click.stop.prevent
      >
        配置と回を記録
      </button>
    </section>

    <section
      aria-label="過去の選手交代を訂正"
      class="min-w-0 space-y-3 rounded-lg border p-3"
    >
      <h3 class="font-bold">過去の選手交代を訂正</h3>
      <p class="text-sm">
        通常の交代とは別の下書きです。訂正後に誰の記録になるかは、確認できた変更前後の内容だけを表示します。
      </p>
      <p
        v-if="pastCleared"
        data-testid="past-substitution-draft-cleared"
        role="status"
        class="text-sm"
      >
        試合または対象・入力項目が変わったため、未保存の訂正下書きを消去しました。
      </p>
      <p v-if="!pastReady" data-testid="past-substitution-unavailable">
        交代履歴と訂正項目は未取得です。
      </p>
      <template v-else>
        <p class="wrap-anywhere font-bold">
          対象一覧: {{ pastRequest!.page.label }}
        </p>
        <label class="block min-w-0 font-bold">
          訂正する交代
          <select
            data-testid="past-substitution-target"
            :value="pastTargetId ?? ''"
            class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
            @change="selectPastTarget"
          >
            <option value="">未選択</option>
            <option
              v-for="item in pastRequest!.page.targets"
              :key="item.id"
              :value="item.id"
            >
              {{ item.label }}
            </option>
          </select>
        </label>
        <p
          v-if="pastTargetId"
          data-testid="past-substitution-detail"
          class="wrap-anywhere text-sm"
        >
          {{
            pastRequest!.page.targets.find((item) => item.id === pastTargetId)
              ?.detail
          }}
        </p>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            type="button"
            disabled
            data-testid="past-substitution-previous"
            class="rounded border p-2 disabled:opacity-60"
            @click.stop.prevent
          >
            前のページ{{
              pastRequest!.page.hasPrevious ? '（準備中）' : 'なし'
            }}
          </button>
          <button
            type="button"
            disabled
            data-testid="past-substitution-next"
            class="rounded border p-2 disabled:opacity-60"
            @click.stop.prevent
          >
            次のページ{{ pastRequest!.page.hasNext ? '（準備中）' : 'なし' }}
          </button>
        </div>
        <fieldset
          v-for="group in [
            { label: '選手の訂正', questions: pastRequest!.personQuestions },
            { label: '回の訂正', questions: pastRequest!.inningQuestions },
            { label: '時点の訂正', questions: pastRequest!.timingQuestions },
          ]"
          :key="group.label"
          class="min-w-0 space-y-2 rounded border p-2"
        >
          <legend class="font-bold">{{ group.label }}</legend>
          <label
            v-for="question in group.questions"
            :key="question.key"
            class="block min-w-0 font-bold"
          >
            {{ question.label }}
            <input
              v-if="question.input === 'text'"
              type="text"
              autocomplete="off"
              :value="pastAnswers.get(question.key) ?? ''"
              :data-past-question="question.key"
              class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
              @input="setAnswer('past', question, $event)"
            />
            <select
              v-else
              :value="pastAnswers.get(question.key) ?? ''"
              :data-past-question="question.key"
              class="mt-1 w-full min-w-0 rounded border bg-white p-2 dark:bg-slate-900"
              @change="setAnswer('past', question, $event)"
            >
              <option value="">未選択</option>
              <option
                v-for="item in question.options"
                :key="item.id"
                :value="item.id"
              >
                {{ item.label }}
              </option>
            </select>
          </label>
        </fieldset>
        <div
          v-if="pastIdentity"
          data-testid="past-substitution-preview"
          class="min-w-0 space-y-2 rounded border p-3"
        >
          <h4 class="font-bold">訂正後に変わる記録の確認</h4>
          <p
            v-if="!currentPreview"
            data-testid="past-substitution-preview-status"
          >
            この下書きに対応するプレビューは未取得です。
          </p>
          <p
            v-else-if="currentPreview.kind === 'pending'"
            data-testid="past-substitution-preview-status"
          >
            この下書きに対応するプレビューは準備中です。
          </p>
          <p
            v-else-if="currentPreview.kind === 'failed'"
            data-testid="past-substitution-preview-status"
          >
            プレビューを取得できませんでした。変更は行われていません。
          </p>
          <p
            v-else-if="currentPreview.kind === 'conflict'"
            data-testid="past-substitution-preview-status"
          >
            別の変更と競合しました。対象の再確認が必要です。
          </p>
          <template v-else-if="currentPreview.kind === 'ready'">
            <p data-testid="past-substitution-preview-status">
              変更前後の記録を確認できます。変更はまだ行われていません。
            </p>
            <dl data-testid="past-substitution-preview-rows" class="space-y-2">
              <div
                v-for="(row, index) in currentPreview.rows"
                :key="index"
                class="min-w-0 rounded border p-2"
              >
                <dt class="wrap-anywhere font-bold">{{ row.label }}</dt>
                <dd class="wrap-anywhere">変更前: {{ row.before }}</dd>
                <dd class="wrap-anywhere">変更後: {{ row.after }}</dd>
              </div>
            </dl>
          </template>
        </div>
        <p
          v-else
          data-testid="past-substitution-preview-unavailable"
          class="text-sm"
        >
          プレビューを確認できません。入力内容は保存されていません。
        </p>
      </template>
      <p id="past-substitution-blocked-reason" class="text-sm">
        この画面ではまだ過去の交代を訂正できません。履歴と試合の終了状態は変わりません。
      </p>
      <button
        type="button"
        disabled
        aria-describedby="past-substitution-blocked-reason"
        data-testid="past-substitution-apply"
        class="rounded border px-3 py-2 disabled:opacity-60"
        @click.stop.prevent
      >
        訂正を確定
      </button>
    </section>
  </section>
</template>
