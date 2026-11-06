<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import {
  ApiError,
  ApiNetworkError,
  ApiSessionUnverifiedError,
  ApiStaleAuthError,
  ApiTenantVerificationError,
} from '../../api/client'
import {
  downloadGamePlayCsv,
  GameExportVerificationError,
  verifyGamePlayArchive,
} from '../../api/gameExports'
import { useAuthStore } from '../../stores/authStore'

const props = defineProps<{
  gameId: string
  /** 端末に残る未送信件数。ZIPには含まれないことを示す。 */
  unsentCount?: number
}>()

type ExportPhase = 'idle' | 'downloading' | 'saved' | 'canceled' | 'failed'

const auth = useAuthStore()
const phase = ref<ExportPhase>('idle')
const errorMessage = ref('')
const canRetry = ref(false)
const validGameId =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
    props.gameId,
  )

let controller: AbortController | null = null
const objectUrls = new Set<string>()

const statusText = computed(() => {
  if (!validGameId) return '試合IDが正しくありません。'
  switch (phase.value) {
    case 'downloading':
      return 'ZIPを作成しています。完了するまでこの画面を閉じないでください。'
    case 'saved':
      return 'ZIPを保存しました。'
    case 'canceled':
      return 'ダウンロードを取り消しました。'
    case 'failed':
      return 'ZIPを保存できませんでした。'
    default:
      return '記録済みの全プレイとサイドカーをZIPで保存できます。'
  }
})

function revoke(url: string) {
  if (objectUrls.delete(url)) URL.revokeObjectURL(url)
}

function scheduleRevoke(url: string) {
  window.setTimeout(() => revoke(url), 0)
}

function isAbort(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    error.name === 'AbortError'
  )
}

function failureMessage(error: unknown): string {
  if (error instanceof ApiStaleAuthError) {
    return '認証が切り替わったため保存しません。ログイン状態を確認して再試行してください。'
  }
  if (error instanceof ApiTenantVerificationError) {
    return 'テナントの照合を確認できないため保存しません。ログイン状態を確認してください。'
  }
  if (error instanceof ApiSessionUnverifiedError) {
    return 'ログイン状態を確認できないため保存しません。'
  }
  if (error instanceof GameExportVerificationError) {
    return `${error.message}。保存していません。`
  }
  if (error instanceof ApiNetworkError) {
    return '通信に失敗しました。保存できたか確認できないため再試行してください。'
  }
  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        return 'ログイン状態を確認してください。'
      case 404:
        return 'この試合は出力できません。削除・非表示・別テナントの可能性があります。'
      case 409:
        return `供給不足または版の変更によりZIPを作成できません（不足列 ${error.fields.length} 件）。`
      case 503:
        return 'サーバーを一時的に利用できません。時間をおいて再試行してください。'
      default:
        return 'ZIPの作成に失敗しました。'
    }
  }
  return 'ZIPを保存できませんでした。'
}

async function start() {
  if (!validGameId || phase.value === 'downloading') return
  const p = auth.authEpoch
  const team = auth.teamId
  controller = new AbortController()
  phase.value = 'downloading'
  errorMessage.value = ''
  canRetry.value = false
  try {
    const downloaded = await downloadGamePlayCsv(props.gameId, {
      signal: controller.signal,
    })
    if (auth.authEpoch !== p || auth.teamId !== team) {
      throw new ApiStaleAuthError(
        'GET',
        `/games/${props.gameId}/exports/plays.zip`,
      )
    }
    const verified = await verifyGamePlayArchive(downloaded)
    const url = URL.createObjectURL(verified.blob)
    objectUrls.add(url)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = verified.filename ?? `pitchlog-plays-${props.gameId}.zip`
    anchor.rel = 'noopener'
    anchor.click()
    scheduleRevoke(url)
    phase.value = 'saved'
  } catch (error) {
    if (isAbort(error)) {
      phase.value = 'canceled'
      return
    }
    phase.value = 'failed'
    errorMessage.value = failureMessage(error)
    canRetry.value =
      error instanceof ApiNetworkError ||
      error instanceof GameExportVerificationError ||
      (error instanceof ApiError &&
        error.status !== 404 &&
        error.status !== 401)
  } finally {
    controller = null
  }
}

function cancel() {
  controller?.abort()
}

onBeforeUnmount(() => {
  controller?.abort()
  for (const url of [...objectUrls]) revoke(url)
})
</script>

<template>
  <section
    aria-label="毎球CSVのダウンロード"
    class="space-y-2 rounded-xl border p-4"
  >
    <h2 class="text-lg font-bold">毎球CSV（ZIP）</h2>
    <p>
      確定済みの全プレイとサイドカーを1つのZIPで保存します。未送信の記録は含まれません。
    </p>
    <p v-if="props.unsentCount && props.unsentCount > 0" role="status">
      未送信が{{
        props.unsentCount
      }}件あります。送信完了後に再取得してください。
    </p>
    <div class="flex flex-wrap gap-2">
      <button
        type="button"
        class="min-h-11 rounded-lg border px-3 py-2"
        :disabled="!validGameId || phase === 'downloading'"
        @click="start"
      >
        毎球CSVをダウンロード
      </button>
      <button
        v-if="phase === 'downloading'"
        type="button"
        class="min-h-11 rounded-lg border px-3 py-2"
        @click="cancel"
      >
        取り消す
      </button>
      <button
        v-if="canRetry"
        type="button"
        class="min-h-11 rounded-lg border px-3 py-2"
        @click="start"
      >
        再試行
      </button>
    </div>
    <p role="status">{{ statusText }}</p>
    <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
  </section>
</template>
