<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  endPayload,
  postGameLifecycle,
  reopenPayload,
  type GameLifecycleRead,
} from '../api/gameLifecycleSpike'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { useAuthStore } from '../stores/authStore'

const props = defineProps<{
  gameId: string
  lifecycle: GameLifecycleRead | null
  loading: boolean
  message: string
}>()
const emit = defineEmits<{ refresh: []; changed: [] }>()
const auth = useAuthStore()
const busy = ref(false)
const actionMessage = ref('')

const score = computed(() => {
  const value = props.lifecycle?.currentState.stateFields['state.score']
  return typeof value === 'object' && value !== null
    ? (value as Record<string, unknown>)
    : null
})
const active = computed(() => props.lifecycle?.activeFinalization ?? null)
const finalizations = computed(() => props.lifecycle?.finalizations ?? [])

function digest(value: string): string {
  return value.length > 20 ? `${value.slice(0, 18)}…` : value
}

async function submit(action: 'end' | 'reopen') {
  if (busy.value) return
  const lifecycle = props.lifecycle
  if (lifecycle === null || auth.teamId === null) {
    actionMessage.value = 'ログイン状態と試合状態を確認できません'
    return
  }
  busy.value = true
  actionMessage.value = ''
  let store: GameStartPersistence | null = null
  try {
    actionMessage.value = '端末の開始資格を確認しています'
    store = await GameStartPersistence.open()
    actionMessage.value = '登録端末を確認しています'
    const device = await store.readDevice(auth.teamId)
    actionMessage.value = '開始応答を確認しています'
    const start = await store.readStart(auth.teamId, props.gameId)
    if (
      device === null ||
      start === null ||
      start.grant === null ||
      start.status !== 'received' ||
      start.grant.d4 !== lifecycle.d4
    ) {
      actionMessage.value = '開始資格と現在の記録世代を確認できません'
      return
    }
    const payload =
      action === 'end' ? endPayload(lifecycle) : reopenPayload(lifecycle)
    if (payload === null) {
      actionMessage.value =
        action === 'end'
          ? '終了できる状態または次の版を確認できません'
          : '再開できる終了確定版を確認できません'
      return
    }
    const result = await postGameLifecycle(props.gameId, {
      d4: lifecycle.d4,
      d1: lifecycle.nextD1,
      d2: lifecycle.nextD2,
      recordingRightProof: start.grant.recording_right_proof,
      payload,
      syncCredentials: {
        deviceId: device.device_id,
        deviceCredential: device.device_credential,
        attempt: crypto.randomUUID(),
      },
    })
    if (!result.sent) {
      actionMessage.value = `同期要求を送信できませんでした (${result.reason})`
      return
    }
    if (result.a5Result !== '受理' && result.a5Result !== '重複') {
      actionMessage.value = `サーバーが受理しませんでした: ${result.a5Result}`
      return
    }
    actionMessage.value =
      result.a5Result === '重複'
        ? '同じ要求は重複として処理されました。サーバーから再取得します'
        : action === 'end'
          ? '終了を宣言しました。サーバーから再取得します'
          : '試合を追記再開しました。サーバーから再取得します'
    emit('changed')
  } catch {
    actionMessage.value = '終了・再開を保存できませんでした'
  } finally {
    store?.close()
    busy.value = false
  }
}
</script>

<template>
  <section
    aria-label="試合の終了と再開"
    class="space-y-3 rounded-2xl border border-amber-300 bg-amber-50 p-4"
  >
    <header class="space-y-1">
      <h2 class="text-lg font-extrabold">試合の終了・再開（接続spike）</h2>
      <p class="text-sm">
        既存の正式同期入口へ終了宣言・再開を送り、保存済みイベントから確定版を読みます。
      </p>
      <p data-testid="lifecycle-status" role="status" class="font-bold">
        {{
          loading
            ? 'サーバーの終了状態を取得中です'
            : lifecycle === null
              ? message
              : lifecycle.status === 'finished'
                ? '終了確定'
                : '進行中'
        }}
      </p>
      <p data-testid="lifecycle-message" role="status" class="text-sm">
        {{ actionMessage || message }}
      </p>
      <button
        v-if="lifecycle === null && !loading"
        type="button"
        data-testid="lifecycle-refresh"
        class="min-h-11 rounded-lg border px-3 py-2"
        @click="emit('refresh')"
      >
        サーバーから再取得
      </button>
    </header>
    <template v-if="lifecycle !== null">
      <dl class="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <div>
          <dt>スコア</dt>
          <dd data-testid="lifecycle-score">
            {{ score?.away ?? '—' }} - {{ score?.home ?? '—' }}
          </dd>
        </div>
        <div>
          <dt>確定版</dt>
          <dd data-testid="lifecycle-version">
            {{ active === null ? 'なし' : `v${active.version}` }}
          </dd>
        </div>
        <div>
          <dt>次の D1 / D2</dt>
          <dd data-testid="lifecycle-next">
            {{ lifecycle.nextD1 }} / {{ lifecycle.nextD2 }}
          </dd>
        </div>
        <div>
          <dt>水位</dt>
          <dd data-testid="lifecycle-watermark">{{ lifecycle.watermark }}</dd>
        </div>
      </dl>
      <p v-if="active" data-testid="lifecycle-active" class="text-sm">
        有効な終了確定版: v{{ active.version }} / D1 {{ active.d1 }} /
        {{ digest(active.finalizationDigest) }}
      </p>
      <ul
        v-if="finalizations.length"
        data-testid="lifecycle-finalizations"
        class="space-y-1 text-sm"
      >
        <li v-for="item in finalizations" :key="`${item.version}:${item.d1}`">
          v{{ item.version }}（D1 {{ item.d1 }}）:
          {{
            item.invalidatedBy === null
              ? '有効'
              : `再開 D1 ${item.invalidatedBy.d1} で失効`
          }}
        </li>
      </ul>
      <p v-if="lifecycle.truncated" class="text-sm font-bold">
        イベント履歴がspikeの走査上限を超えています
      </p>
      <div class="grid gap-2 sm:grid-cols-3">
        <button
          type="button"
          data-testid="lifecycle-end"
          class="min-h-11 rounded-lg border border-amber-700 bg-white px-3 py-2 font-bold disabled:opacity-60"
          :disabled="busy || lifecycle.status !== 'in_progress'"
          @click="submit('end')"
        >
          終了を宣言する
        </button>
        <button
          type="button"
          data-testid="lifecycle-reopen"
          class="min-h-11 rounded-lg border border-amber-700 bg-white px-3 py-2 font-bold disabled:opacity-60"
          :disabled="busy || lifecycle.status !== 'finished'"
          @click="submit('reopen')"
        >
          試合を追記再開する
        </button>
        <button
          type="button"
          data-testid="lifecycle-refresh"
          class="min-h-11 rounded-lg border px-3 py-2"
          :disabled="busy || loading"
          @click="emit('refresh')"
        >
          サーバーから再取得
        </button>
      </div>
      <p
        v-if="lifecycle.status === 'finished'"
        data-testid="lifecycle-finished-note"
        class="text-sm"
      >
        終了確定版を保存しました。再開するとこの版は失効し、再終了で新しい版になります。
      </p>
    </template>
  </section>
</template>
