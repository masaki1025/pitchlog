<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  denseEvery,
  isLabel,
  sameDisplayValue,
  snapshotDisplayValue,
} from './GameScreenDisplayValue'
import type {
  CorrectionDraft,
  CorrectionDraftIdentity,
  CorrectionOperation,
  CorrectionPrerequisites,
  CorrectionPreview,
  CorrectionQuestion,
  CorrectionRequest,
} from './GameScreenCorrectionTypes'

const props = defineProps<{
  request?: CorrectionRequest | null
  activeContextKey?: string | null
  prerequisites?: CorrectionPrerequisites | null
  preview?: CorrectionPreview | null
}>()
const emit = defineEmits<{
  draftChange: [draft: CorrectionDraft | null]
}>()

const operationLabels: Record<CorrectionOperation, string> = {
  modify: '修正',
  insert: '挿入',
  delete: '削除（履歴は残ります）',
}
const operations: readonly CorrectionOperation[] = [
  'modify',
  'insert',
  'delete',
]

// 再表示後の旧応答を区別するための画面内識別子。生成できなければ照合を閉じる。
function createUiInstanceId(): string | null {
  try {
    const random = globalThis.crypto
    if (typeof random?.randomUUID === 'function') {
      return random.randomUUID() || null
    }
    if (typeof random?.getRandomValues === 'function') {
      const bytes = random.getRandomValues(new Uint8Array(16))
      return Array.from(bytes, (byte) =>
        byte.toString(16).padStart(2, '0'),
      ).join('')
    }
  } catch {
    // ブラウザが乱数を提供しない場合、古い応答を受け入れない。
  }
  return null
}

const uiInstanceId = createUiInstanceId()

// 下書きを戻しても旧応答を再表示しないよう、変更ごとに世代を進める。
let nextDraftId = 0
const draftId = ref(++nextDraftId)
const targetId = ref<string | null>(null)
const operation = ref<CorrectionOperation | null>(null)
const answers = ref(new Map<string, string>())
const screen = ref<'edit' | 'confirm'>('edit')
const draftClearedNotice = ref(false)

function reset() {
  targetId.value = null
  operation.value = null
  answers.value = new Map()
  screen.value = 'edit'
  draftId.value = ++nextDraftId
  publishDraft()
}

// 比較は既存の画面表示値ヘルパーと同一。参照の再供給では下書きを消さない。
let previousConditions = snapshotDisplayValue([
  props.request,
  props.activeContextKey,
])
watch(
  () => [props.request, props.activeContextKey],
  () => {
    const next = [props.request, props.activeContextKey]
    if (!sameDisplayValue(previousConditions, next)) {
      const hadDraft =
        targetId.value !== null ||
        operation.value !== null ||
        answers.value.size > 0 ||
        screen.value === 'confirm'
      reset()
      draftClearedNotice.value = hadDraft
    }
    previousConditions = snapshotDisplayValue(next)
  },
  { deep: true, flush: 'sync' },
)

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

const requestReady = computed(() => {
  const request: unknown = props.request
  if (
    !isRecord(request) ||
    !isLabel(request.contextKey) ||
    !props.activeContextKey ||
    request.contextKey !== props.activeContextKey ||
    !isRecord(request.page) ||
    !isLabel(request.page.label) ||
    typeof request.page.hasPrevious !== 'boolean' ||
    typeof request.page.hasNext !== 'boolean' ||
    !Array.isArray(request.page.targets) ||
    !isRecord(request.questions)
  )
    return false
  const targets: unknown[] = request.page.targets
  if (
    !denseEvery(
      targets,
      (target) =>
        isRecord(target) &&
        isLabel(target.id) &&
        isLabel(target.label) &&
        typeof target.detail === 'string',
    ) ||
    new Set(targets.map((target) => (target as Record<string, unknown>).id))
      .size !== targets.length
  )
    return false
  const questionGroups = request.questions
  return operations.every((item) => {
    const questions = questionGroups[item]
    if (!Array.isArray(questions)) return false
    const entries: unknown[] = questions
    if (
      !denseEvery(entries, (question) => {
        if (
          !isRecord(question) ||
          !isLabel(question.key) ||
          !isLabel(question.label) ||
          (question.input !== 'text' && question.input !== 'choice')
        )
          return false
        if (question.options === undefined) return question.input === 'text'
        if (!Array.isArray(question.options)) return false
        const options: unknown[] = question.options
        return (
          denseEvery(
            options,
            (option) =>
              isRecord(option) && isLabel(option.id) && isLabel(option.label),
          ) &&
          new Set(
            options.map((option) => (option as Record<string, unknown>).id),
          ).size === options.length
        )
      }) ||
      new Set(
        entries.map((question) => (question as Record<string, unknown>).key),
      ).size !== entries.length
    )
      return false
    return true
  })
})

const selectedTarget = computed(() =>
  requestReady.value
    ? (props.request?.page.targets.find((item) => item.id === targetId.value) ??
      null)
    : null,
)
const selectedQuestions = computed<readonly CorrectionQuestion[]>(() =>
  requestReady.value && operation.value
    ? (props.request?.questions[operation.value] ?? [])
    : [],
)
const canReview = computed(
  () =>
    requestReady.value &&
    !!selectedTarget.value &&
    !!operation.value &&
    selectedQuestions.value.length > 0,
)

function selectTarget(event: Event) {
  if (!requestReady.value) return
  const id = (event.target as HTMLSelectElement).value
  targetId.value = props.request?.page.targets.some((item) => item.id === id)
    ? id
    : null
  answers.value = new Map()
  screen.value = 'edit'
  draftId.value = ++nextDraftId
  draftClearedNotice.value = false
  publishDraft()
}

function selectOperation(event: Event) {
  if (!requestReady.value) return
  const value = (event.target as HTMLSelectElement).value
  operation.value = operations.find((item) => item === value) ?? null
  answers.value = new Map()
  screen.value = 'edit'
  draftId.value = ++nextDraftId
  draftClearedNotice.value = false
  publishDraft()
}

function setAnswer(question: CorrectionQuestion, event: Event) {
  if (!selectedQuestions.value.includes(question)) return
  const value = (event.target as HTMLInputElement | HTMLSelectElement).value
  if (
    question.input === 'choice' &&
    value !== '' &&
    !question.options?.some((option) => option.id === value)
  )
    return
  const updated = new Map(answers.value)
  if (value === '') updated.delete(question.key)
  else updated.set(question.key, value)
  answers.value = updated
  draftId.value = ++nextDraftId
  draftClearedNotice.value = false
  publishDraft()
}

const identity = computed<CorrectionDraftIdentity | null>(() => {
  if (
    !uiInstanceId ||
    !canReview.value ||
    !selectedTarget.value ||
    !operation.value
  )
    return null
  return {
    contextKey: props.request!.contextKey,
    uiInstanceId,
    draftId: draftId.value,
    targetId: selectedTarget.value.id,
    operation: operation.value,
  }
})

/** 表示下書きのコピー。正式な修正要求やプレビュー通信は行わない。 */
function getDraft(): CorrectionDraft | null {
  if (!identity.value) return null
  return {
    identity: { ...identity.value },
    answers: Object.fromEntries(
      selectedQuestions.value.map((question) => [
        question.key,
        answers.value.get(question.key) ?? null,
      ]),
    ),
  }
}

function publishDraft() {
  emit('draftChange', getDraft())
}

onMounted(() => {
  if (props.request) publishDraft()
})
onBeforeUnmount(() => {
  if (props.request) emit('draftChange', null)
})

const currentPreview = computed<CorrectionPreview | null>(() => {
  const expected = identity.value
  const received = props.preview
  if (!expected || !isRecord(received) || !isRecord(received.identity))
    return null
  const actual = received.identity
  if (!(
    actual.contextKey === expected.contextKey &&
    actual.uiInstanceId === expected.uiInstanceId &&
    actual.draftId === expected.draftId &&
    actual.targetId === expected.targetId &&
    actual.operation === expected.operation
  ))
    return null
  if (
    received.kind === 'pending' ||
    received.kind === 'failed' ||
    received.kind === 'conflict'
  )
    return received
  if (
    received.kind === 'ready' &&
    Array.isArray(received.rows) &&
    received.rows.length > 0 &&
    denseEvery(
      received.rows,
      (row) =>
        isRecord(row) &&
        isLabel(row.label) &&
        typeof row.before === 'string' &&
        typeof row.after === 'string',
    )
  )
    return received
  return null
})

const prerequisites = computed<CorrectionPrerequisites>(
  () =>
    props.prerequisites ?? {
      writer: 'unknown',
      queue: 'unknown',
      connection: 'unknown',
    },
)

const writerText = computed(() => {
  switch (prerequisites.value.writer) {
    case 'held':
      return '保持を確認済み'
    case 'not-held':
      return '記録権を保持していません'
    default:
      return '未取得（記録権を確認できません）'
  }
})
const queueText = computed(() => {
  switch (prerequisites.value.queue) {
    case 'empty':
      return '処理待ちの記録はありません'
    case 'not-empty':
      return '処理待ちの記録があります'
    default:
      return '未取得（処理待ちの記録を確認できません）'
  }
})
const connectionText = computed(() => {
  switch (prerequisites.value.connection) {
    case 'online':
      return 'オンラインを確認済み'
    case 'offline':
      return '通信が切れています'
    default:
      return '未取得（接続を確認できません）'
  }
})
</script>

<template>
  <section
    aria-label="オンラインの過去プレイ修正"
    class="min-w-0 space-y-4 rounded-2xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30"
  >
    <h2 class="text-lg font-extrabold">オンラインの過去プレイ修正</h2>
    <p class="text-sm">
      修正・挿入・削除は直前の取消とは別の操作です。削除した記録も履歴に残ります。この下書きは保存・送信されず、画面を離れると消えます。
    </p>
    <p
      v-if="draftClearedNotice"
      data-testid="correction-draft-cleared"
      role="status"
      class="text-sm"
    >
      対象または入力項目が変わったため、前の下書きを消去しました。変更は保存されていません。
    </p>
    <dl class="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-3">
      <div class="min-w-0 rounded-lg bg-white p-3 dark:bg-slate-900">
        <dt>記録権</dt>
        <dd data-testid="correction-writer" class="wrap-anywhere font-bold">
          {{ writerText }}
        </dd>
      </div>
      <div class="min-w-0 rounded-lg bg-white p-3 dark:bg-slate-900">
        <dt>処理待ちの記録</dt>
        <dd data-testid="correction-queue" class="wrap-anywhere font-bold">
          {{ queueText }}
        </dd>
      </div>
      <div class="min-w-0 rounded-lg bg-white p-3 dark:bg-slate-900">
        <dt>接続</dt>
        <dd data-testid="correction-connection" class="wrap-anywhere font-bold">
          {{ connectionText }}
        </dd>
      </div>
    </dl>
    <p v-if="!requestReady" data-testid="correction-request-unavailable">
      対象プレイと入力項目は未取得です。確認できるまで操作できません。
    </p>
    <template v-else-if="request">
      <div
        v-if="screen === 'edit'"
        class="min-w-0 space-y-4"
        data-testid="correction-edit"
      >
        <div class="min-w-0 space-y-2">
          <p class="text-sm font-bold">対象一覧: {{ request.page.label }}</p>
          <label class="block min-w-0 font-bold">
            対象プレイ
            <select
              data-testid="correction-target"
              :value="targetId ?? ''"
              class="mt-1 w-full min-w-0 rounded border border-slate-400 bg-white p-2 dark:bg-slate-900"
              @change="selectTarget"
            >
              <option value="">未選択</option>
              <option
                v-for="target in request.page.targets"
                :key="target.id"
                :value="target.id"
              >
                {{ target.label }}
              </option>
            </select>
          </label>
          <p
            v-if="selectedTarget"
            data-testid="correction-target-detail"
            class="wrap-anywhere text-sm"
          >
            {{ selectedTarget.detail }}
          </p>
          <div class="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
            <button
              type="button"
              disabled
              data-testid="correction-previous-page"
              class="min-w-0 rounded border p-2 disabled:opacity-60"
              @click.stop.prevent
            >
              前のページ{{ request.page.hasPrevious ? '（準備中）' : 'なし' }}
            </button>
            <button
              type="button"
              disabled
              data-testid="correction-next-page"
              class="min-w-0 rounded border p-2 disabled:opacity-60"
              @click.stop.prevent
            >
              次のページ{{ request.page.hasNext ? '（準備中）' : 'なし' }}
            </button>
          </div>
        </div>
        <label class="block min-w-0 font-bold">
          操作
          <select
            data-testid="correction-operation"
            :value="operation ?? ''"
            class="mt-1 w-full min-w-0 rounded border border-slate-400 bg-white p-2 dark:bg-slate-900"
            @change="selectOperation"
          >
            <option value="">未選択</option>
            <option v-for="item in operations" :key="item" :value="item">
              {{ operationLabels[item] }}
            </option>
          </select>
        </label>
        <div
          v-if="operation"
          class="min-w-0 space-y-3"
          data-testid="correction-questions"
        >
          <p
            v-if="!selectedQuestions.length"
            class="text-sm"
            data-testid="correction-questions-unavailable"
          >
            この操作の入力項目を確認できません。
          </p>
          <label
            v-for="question in selectedQuestions"
            :key="question.key"
            class="block min-w-0 font-bold"
          >
            {{ question.label }}
            <input
              v-if="question.input === 'text'"
              :value="answers.get(question.key) ?? ''"
              :data-question-key="question.key"
              type="text"
              autocomplete="off"
              class="mt-1 w-full min-w-0 rounded border border-slate-400 bg-white p-2 dark:bg-slate-900"
              @input="setAnswer(question, $event)"
            />
            <select
              v-else
              :value="answers.get(question.key) ?? ''"
              :data-question-key="question.key"
              class="mt-1 w-full min-w-0 rounded border border-slate-400 bg-white p-2 dark:bg-slate-900"
              @change="setAnswer(question, $event)"
            >
              <option value="">未選択</option>
              <option
                v-for="option in question.options ?? []"
                :key="option.id"
                :value="option.id"
              >
                {{ option.label }}
              </option>
            </select>
          </label>
        </div>
        <button
          type="button"
          data-testid="correction-review"
          :disabled="!canReview"
          class="min-w-0 rounded-lg border border-amber-600 px-3 py-2 font-bold disabled:opacity-60"
          @click="screen = 'confirm'"
        >
          下書きを確認
        </button>
      </div>
      <div
        v-else
        class="min-w-0 space-y-3"
        data-testid="correction-confirmation"
      >
        <h3 class="font-bold">下書きの確認</h3>
        <p class="wrap-anywhere">対象: {{ selectedTarget?.label }}</p>
        <p>操作: {{ operation ? operationLabels[operation] : '未選択' }}</p>
        <dl class="space-y-2">
          <div
            v-for="question in selectedQuestions"
            :key="question.key"
            class="min-w-0"
          >
            <dt>{{ question.label }}</dt>
            <dd class="wrap-anywhere font-bold">
              {{
                question.input === 'choice'
                  ? (question.options?.find(
                      (option) => option.id === answers.get(question.key),
                    )?.label ?? '未選択')
                  : (answers.get(question.key) ?? '未入力')
              }}
            </dd>
          </div>
        </dl>
        <button
          type="button"
          data-testid="correction-back"
          class="rounded border p-2"
          @click="screen = 'edit'"
        >
          入力に戻る
        </button>
        <p id="correction-blocked-reason" class="text-sm">
          この画面ではまだ確定できません。下書きは保存されません。交代時点と試合の終了状態は変わらず、終了後の追記再開も行いません。
        </p>
        <button
          type="button"
          disabled
          aria-describedby="correction-blocked-reason"
          data-testid="correction-apply"
          class="min-w-0 rounded-lg border border-amber-600 px-3 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-60"
          @click.stop.prevent
        >
          この内容で確定
        </button>
      </div>
      <p
        v-if="canReview && !identity"
        data-testid="correction-preview-unavailable"
        class="text-sm"
      >
        プレビューを確認できません。入力内容は保存されていません。
      </p>
      <div
        v-if="identity"
        class="min-w-0 space-y-2 rounded-lg border border-slate-300 p-3 dark:border-slate-600"
        data-testid="correction-preview"
      >
        <h3 class="font-bold">差分プレビュー</h3>
        <p v-if="!currentPreview" data-testid="correction-preview-status">
          現在の下書きに対応するプレビューは未取得です。
        </p>
        <p
          v-else-if="currentPreview.kind === 'pending'"
          data-testid="correction-preview-status"
        >
          現在の下書きに対応するプレビューは準備中です。
        </p>
        <p
          v-else-if="currentPreview.kind === 'failed'"
          data-testid="correction-preview-status"
        >
          プレビューを取得できませんでした。変更は行われていません。
        </p>
        <p
          v-else-if="currentPreview.kind === 'conflict'"
          data-testid="correction-preview-status"
        >
          別の変更と競合しました。対象の再確認が必要です。変更は行われていません。
        </p>
        <template v-else-if="currentPreview.kind === 'ready'">
          <p data-testid="correction-preview-status">
            変更前後の内容を確認できます。変更はまだ行われていません。
          </p>
          <dl class="space-y-2" data-testid="correction-diff-rows">
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
    </template>
  </section>
</template>
