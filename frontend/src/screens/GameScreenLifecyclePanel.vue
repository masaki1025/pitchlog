<script setup lang="ts">
import { computed } from 'vue'
import type {
  GameLifecycleHandoff,
  GameLifecycleReason,
  GameLifecycleView,
} from './gameLifecycleController'

const props = defineProps<{
  view: GameLifecycleView | null
}>()
const emit = defineEmits<{
  refresh: []
  end: []
  reopen: []
  retry: []
  'resume-recording': [handoff: GameLifecycleHandoff]
  back: []
}>()

const REASON_TEXT: Record<GameLifecycleReason, string> = {
  busy: '他の操作を処理中です。',
  'identity-changed':
    'ログイン状態が変わったため操作していません。再読込してください。',
  'storage-unavailable':
    '端末の保存領域を確認できません。記録は変更していません。',
  'grant-unavailable': 'この試合の開始資格を確認できません。',
  'grant-changed':
    '記録権または世代が変わったため、元の要求をそのまま送れません。再読込してください。',
  'lock-unavailable': '別のタブが記録中です。このタブからは操作していません。',
  'read-not-found':
    '試合または終了状態を取得できません（権限・存在・確定証拠のいずれか）。',
  'read-unavailable': '試合がこの読取では閉じません。再読込してください。',
  'read-unsupported': 'このサーバーは終了再開の読取に対応していません。',
  'read-failed': '状態を取得できません。通信を確認してください。',
  'status-mismatch':
    '表示とサーバーの状態が食い違うため操作していません。再読込してください。',
  'reopen-kind-unavailable':
    '追記再開のイベント種別が正式裁定されるまで実行できません（接合待ち）。',
  'pending-predecessor': '先に同期すべき未送信の操作があります。',
  'queued-awaiting-predecessor':
    '終了/再開は端末に保存しました。先行する未送信操作の同期後に送信します。',
  'prepared-envelope':
    '送信準備済みで未受理の要求があります。再送で確認してください。',
  'foreign-prepared-envelope':
    '別の操作の送信準備が残っています。先にそちらを完了してください。',
  'queue-append-rejected':
    '端末キューへ追記できませんでした。記録は変更していません。',
  'queue-append-undetermined':
    '端末キューへの追記結果を確認できません。再読込してください。',
  'durability-unavailable':
    '送信内容を端末へ確定できませんでした。送信していません。',
  'request-body-mismatch':
    '保存した要求とキューが一致しないため送信していません。',
  'prepared-envelope-unavailable':
    '元の送信内容を復元できません。新しい要求で置き換えません。',
  'send-not-accepted':
    '送信できなかったか、応答を確認できません。結果は未確定です。',
  'ack-not-applied':
    '受理を確認できないため同期済みにしていません。結果は未確定です。',
  'requires-operator': '要操作の未確定操作が残っています。自動再送しません。',
  'nothing-pending': '再送する操作はありません。',
  'operation-failed': '操作を完了できませんでした。記録は変更していません。',
  'scan-truncated': '未送信の確認が上限に達しました。先頭のみ表示しています。',
}

const STATUS_TEXT = {
  in_progress: '進行中',
  finished: '終了',
} as const

const REFRESH_TEXT = {
  idle: '未取得',
  done: '取得済み',
  failed: '再取得失敗',
} as const

const view = computed(() => props.view)
const statusText = computed(() =>
  view.value?.status ? STATUS_TEXT[view.value.status] : '未取得',
)
const refreshText = computed(() =>
  view.value ? REFRESH_TEXT[view.value.refresh] : REFRESH_TEXT.idle,
)
const failureText = computed(() =>
  view.value?.lastFailure ? REASON_TEXT[view.value.lastFailure] : null,
)
const ackText = computed(() => {
  const ack = view.value?.saveAck
  if (ack === 'accepted') return '受理を確認しました'
  if (ack === 'duplicate') return '重複として確認しました（増分なし）'
  return null
})
const canRefresh = computed(() => !view.value?.busy)
const hasUnknown = computed(() => (view.value?.unknownCount ?? 0) > 0)
const retryLabel = computed(() =>
  hasUnknown.value ? '結果不明の要求を再送' : '未確定の要求を再送',
)

function resume(): void {
  const handoff = view.value?.resumeHandoff
  if (handoff) emit('resume-recording', handoff)
}
</script>

<template>
  <section
    aria-label="試合の終了と追記再開"
    class="min-w-0 space-y-3 rounded-2xl border border-slate-300 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    data-testid="lifecycle-panel"
  >
    <div class="flex min-w-0 flex-wrap items-center justify-between gap-2">
      <h2 class="text-lg font-extrabold">試合の終了と追記再開</h2>
      <p class="text-sm" data-testid="lifecycle-refresh-state">
        表示: {{ refreshText }}
      </p>
    </div>

    <p v-if="!view" class="text-sm" data-testid="lifecycle-unavailable">
      終了状態をまだ取得していません。再読込してください。
    </p>

    <template v-else>
      <p
        v-if="view.stale"
        class="rounded-lg border border-amber-500 bg-amber-50 p-2 text-sm font-bold dark:bg-amber-950/40"
        data-testid="lifecycle-stale"
      >
        表示は最終取得時点のままです。保存の有無と最新状態は再読込で確認してください。
      </p>

      <dl class="grid min-w-0 gap-2 sm:grid-cols-2">
        <div class="min-w-0">
          <dt class="text-sm">試合状態</dt>
          <dd class="font-bold wrap-anywhere" data-testid="lifecycle-status">
            {{ statusText }}
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-sm">確定版</dt>
          <dd
            class="font-bold wrap-anywhere"
            data-testid="lifecycle-last-version"
          >
            {{ view.lastVersion === null ? '未取得' : `v${view.lastVersion}` }}
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-sm">終了確定版</dt>
          <dd class="font-bold wrap-anywhere" data-testid="lifecycle-active">
            {{
              view.active === null
                ? 'なし（進行中）'
                : `v${view.active.version}`
            }}
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-sm">最終更新</dt>
          <dd class="font-bold wrap-anywhere">
            <time
              v-if="view.lastSavedAt"
              :datetime="view.lastSavedAt"
              data-testid="lifecycle-last-saved"
            >
              {{ view.lastSavedAt }}
            </time>
            <span v-else data-testid="lifecycle-last-saved">未取得</span>
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-sm">結果不明</dt>
          <dd
            class="font-bold wrap-anywhere"
            data-testid="lifecycle-unknown-count"
          >
            {{ view.unknownCount }}件
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-sm">未送信</dt>
          <dd
            class="font-bold wrap-anywhere"
            data-testid="lifecycle-unsent-count"
          >
            {{ view.preparedCount }}件
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-sm">他の未終結操作</dt>
          <dd
            class="font-bold wrap-anywhere"
            data-testid="lifecycle-other-unsettled"
          >
            {{ view.otherUnsettledCount }}件
          </dd>
        </div>
        <div class="min-w-0">
          <dt class="text-sm">保存の確認</dt>
          <dd class="font-bold wrap-anywhere" data-testid="lifecycle-save-ack">
            {{ ackText ?? '未確認' }}
          </dd>
        </div>
      </dl>

      <p
        v-if="view.unpreparedCount > 0"
        class="rounded-lg border border-rose-400 bg-rose-50 p-2 text-sm font-bold dark:bg-rose-950/40"
        data-testid="lifecycle-unprepared"
      >
        送信内容を復元できない操作が{{
          view.unpreparedCount
        }}件あります。新しい要求で置き換えません。
      </p>

      <p
        v-if="view.scanTruncated"
        class="text-sm"
        data-testid="lifecycle-scan-truncated"
      >
        未送信の確認が上限（1000件）に達しました。表示は先頭のみです。
      </p>

      <p
        v-if="failureText"
        class="rounded-lg border border-rose-400 bg-rose-50 p-2 text-sm font-bold dark:bg-rose-950/40"
        role="status"
        data-testid="lifecycle-failure"
      >
        {{ failureText }}
      </p>

      <p
        v-if="view.reopenBlocked"
        class="text-sm"
        data-testid="lifecycle-reopen-blocked"
      >
        追記再開は、再開イベント種別の正式裁定とroot接合が済むまで実行できません。
      </p>

      <div class="flex min-w-0 flex-wrap gap-2">
        <button
          type="button"
          :disabled="!view.canEnd"
          data-testid="lifecycle-end"
          class="rounded-lg border border-slate-500 px-3 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-60"
          @click="emit('end')"
        >
          試合終了を宣言
        </button>
        <button
          type="button"
          :disabled="!view.canReopen"
          data-testid="lifecycle-reopen"
          class="rounded-lg border border-emerald-600 px-3 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-60"
          @click="emit('reopen')"
        >
          追記のために再開
        </button>
        <button
          v-if="view.canRetry"
          type="button"
          data-testid="lifecycle-retry"
          class="rounded-lg border border-amber-600 px-3 py-2 font-bold"
          @click="emit('retry')"
        >
          {{ retryLabel }}
        </button>
        <button
          type="button"
          :disabled="!canRefresh"
          data-testid="lifecycle-refresh"
          class="rounded-lg border border-slate-500 px-3 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-60"
          @click="emit('refresh')"
        >
          再読込
        </button>
        <button
          v-if="view.resumeHandoff"
          type="button"
          data-testid="lifecycle-resume"
          class="rounded-lg border border-sky-600 px-3 py-2 font-bold"
          @click="resume"
        >
          記録を続ける
        </button>
        <button
          type="button"
          data-testid="lifecycle-back"
          class="rounded-lg border border-slate-400 px-3 py-2 font-bold"
          @click="emit('back')"
        >
          記録画面へ戻る
        </button>
      </div>

      <p class="text-xs" data-testid="lifecycle-next-position">
        次の記録位置: D1={{ view.nextPosition?.d1 ?? '未取得' }} / D2={{
          view.nextPosition?.d2 ?? '未取得'
        }}
      </p>
    </template>
  </section>
</template>
