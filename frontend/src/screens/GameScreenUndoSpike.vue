<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  postUndoSpike,
  readUndoSpikeState,
  type UndoSpikeResult,
  type UndoSpikeState,
} from '../api/undoSpike'
import { GameStartPersistence } from '../lib/gameStartPersistence'
import { invokeFirstBallDomain } from '../lib/generated/wrappers/domainArtifact'
import { useAuthStore } from '../stores/authStore'

const route = useRoute()
const auth = useAuthStore()
const gameId = computed(() =>
  typeof route.params.gameId === 'string' ? route.params.gameId : '',
)
const state = ref<UndoSpikeState | null>(null)
const loading = ref(true)
const busy = ref(false)
const message = ref('取消spikeの状態を読み込み中です')
const target = computed(() => state.value?.undoTarget ?? null)
const fields = computed(() => state.value?.state?.stateFields ?? {})
const historyCount = computed(() => state.value?.history.length ?? 0)
const eventsCount = computed(() => state.value?.events.length ?? 0)

function text(key: string): string {
  const value = fields.value[key]
  return typeof value === 'string' ? value : '—'
}

async function load() {
  if (!auth.isAuthenticated || auth.teamId === null || gameId.value === '') {
    message.value = 'ログイン状態と試合IDを確認できません'
    loading.value = false
    return
  }
  loading.value = true
  try {
    state.value = await readUndoSpikeState(gameId.value)
    message.value =
      state.value.undoTarget === null
        ? '取り消せる直前の操作はありません'
        : '取消対象を確認しました'
  } catch {
    state.value = null
    message.value = '取消spikeの状態を取得できません'
  } finally {
    loading.value = false
  }
}

async function undo() {
  const currentState = state.value
  const currentTarget = target.value
  if (
    busy.value ||
    currentState === null ||
    currentState.state === null ||
    currentTarget === null ||
    auth.teamId === null
  )
    return
  busy.value = true
  let store: GameStartPersistence | null = null
  try {
    store = await GameStartPersistence.open()
    const device = await store.readDevice(auth.teamId)
    const start = await store.readStart(auth.teamId, gameId.value)
    if (
      device === null ||
      start === null ||
      start.grant === null ||
      start.status !== 'received' ||
      start.grant.d4 !== currentState.d4
    ) {
      message.value = '開始資格と取消対象の世代を確認できません'
      return
    }
    const current: Record<string, unknown> = {
      stateFields: currentState.state.stateFields,
      scoreboard: currentState.state.scoreboard,
    }
    if (currentState.state.battingOrderBySide !== undefined)
      current.battingOrderBySide = currentState.state.battingOrderBySide
    const result = invokeFirstBallDomain('applyUndo', {
      current,
      history: {
        stack: currentState.history.map((item) => item.entry),
      },
    }) as UndoSpikeResult
    if (
      result.operationResult !== 'applied' ||
      result.historyEffect.pops !== '1'
    ) {
      message.value = '取消の正式計算が適用になりません'
      return
    }
    const reference = {
      game: currentTarget.game,
      d4: currentTarget.d4,
      d1: currentTarget.d1,
    }
    const d5 = crypto.randomUUID()
    await postUndoSpike(
      gameId.value,
      {
        recording_right_proof: start.grant.recording_right_proof,
        d5,
        d1: currentState.nextD1,
        target: reference,
        payload: {
          formatVersion: 'undo-connection-spike-v1',
          target: reference,
          result,
        },
      },
      {
        deviceId: device.device_id,
        deviceCredential: device.device_credential,
        attempt: crypto.randomUUID(),
      },
    )
    message.value = '取消を保存しました。サーバーから再取得します'
    await load()
  } catch {
    message.value = '取消を保存できませんでした。状態を再取得してください'
  } finally {
    store?.close()
    busy.value = false
  }
}

onMounted(load)
</script>

<template>
  <main class="mx-auto max-w-3xl space-y-5 p-4 pb-12 wrap-anywhere">
    <header class="space-y-2">
      <p class="text-sm">取消の接続spike（正式統合前の候補）</p>
      <h1 class="text-2xl font-extrabold">直前の操作を取り消す</h1>
      <p data-testid="undo-spike-status" role="status">{{ message }}</p>
    </header>
    <section
      aria-label="サーバー由来の現在状態"
      class="space-y-3 rounded-xl border p-4"
    >
      <h2 class="text-lg font-bold">サーバー由来の現在状態</h2>
      <p v-if="loading" role="status">読み込み中です</p>
      <template v-else-if="state !== null">
        <dl class="grid grid-cols-2 gap-2">
          <div>
            <dt>ボール</dt>
            <dd data-testid="undo-spike-balls">
              {{ text('state.count.balls') }}
            </dd>
          </div>
          <div>
            <dt>ストライク</dt>
            <dd data-testid="undo-spike-strikes">
              {{ text('state.count.strikes') }}
            </dd>
          </div>
          <div>
            <dt>アウト</dt>
            <dd data-testid="undo-spike-outs">{{ text('state.outs') }}</dd>
          </div>
          <div>
            <dt>走者</dt>
            <dd data-testid="undo-spike-runners">
              {{ text('state.runners') }}
            </dd>
          </div>
          <div>
            <dt>打順</dt>
            <dd data-testid="undo-spike-order">
              {{ text('state.battingOrder') }}
            </dd>
          </div>
          <div>
            <dt>履歴</dt>
            <dd data-testid="undo-spike-history">{{ historyCount }}件</dd>
          </div>
          <div>
            <dt>保存イベント</dt>
            <dd data-testid="undo-spike-events">{{ eventsCount }}件</dd>
          </div>
          <div>
            <dt>水位</dt>
            <dd data-testid="undo-spike-watermark">{{ state.watermark }}</dd>
          </div>
        </dl>
        <p data-testid="undo-spike-target">
          取消対象: {{ target === null ? 'なし' : `D1 ${target.d1}` }}
        </p>
      </template>
    </section>
    <section
      aria-label="取消操作"
      class="space-y-3 rounded-2xl border border-amber-300 bg-amber-50 p-4"
    >
      <h2 class="text-lg font-extrabold">取消を保存する</h2>
      <p class="text-sm">
        正式artifactの取消計算を同じ要求へ載せ、実認証・実記録権・同期核・実DBで保存します。
      </p>
      <button
        type="button"
        data-testid="undo-spike-undo"
        class="min-h-11 rounded-lg border border-amber-600 px-3 py-2 font-bold disabled:opacity-60"
        :disabled="busy || target === null"
        @click="undo"
      >
        直前の操作を取り消す
      </button>
      <button
        type="button"
        data-testid="undo-spike-reload"
        class="min-h-11 rounded-lg border px-3 py-2"
        :disabled="busy"
        @click="load"
      >
        サーバーから再取得
      </button>
    </section>
  </main>
</template>
