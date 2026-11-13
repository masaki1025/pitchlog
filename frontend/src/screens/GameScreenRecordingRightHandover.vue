<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/authStore'
import {
  GameStartPersistence,
  type StoredGameStart,
} from '../lib/gameStartPersistence'
import { openDurableQueue } from '../lib/sync/durableQueue'
import {
  acquireRecordingRightHandover,
  releaseRecordingRightHandover,
} from '../api/recordingRightHandover'
import {
  enrollInitialDevice,
  type InitialDeviceEnrollmentResponse,
} from '../api/gameStart'
import { readStartedGame, type StartedGameMetadata } from '../api/startedGame'
import { readLineupPrefixGame } from '../api/lineupPrefixGame'
import {
  readPlayPrefixGame,
  readRecordedPrefixGame,
} from '../api/recordedPrefixGame'

type HandoverGame = StartedGameMetadata
type LoadState = 'loading' | 'ready' | 'failed'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const gameId = computed(() =>
  typeof route.params.gameId === 'string' ? route.params.gameId : '',
)
const state = ref<LoadState>('loading')
const game = ref<HandoverGame | null>(null)
const device = ref<InitialDeviceEnrollmentResponse | null>(null)
const start = ref<StoredGameStart | null>(null)
const message = ref('')
const busy = ref(false)
const released = ref(false)
const acquired = ref(false)
const toDeviceId = ref('')
const requestIdInput = ref('')
const confirmed = ref(false)
const lastD1 = ref<number | null>(null)
const handoverRequestId = ref('')

const holder = computed(() => {
  const g = game.value
  const d = device.value
  const s = start.value
  return Boolean(
    g &&
    d &&
    s?.status === 'received' &&
    s.grant !== null &&
    s.grant.device_id === d.device_id &&
    s.grant.d4 === g.current_d4,
  )
})

function storageKey(tenant: string): string {
  return `pitchlog-handover:${tenant}:${gameId.value}:${device.value?.device_id ?? ''}`
}

function requestId(): string {
  let value = handoverRequestId.value
  const tenant = auth.teamId
  if (value === '' && tenant !== null && device.value !== null) {
    try {
      const key = storageKey(tenant)
      const saved = globalThis.sessionStorage?.getItem(key)
      value =
        saved && /^[0-9a-f-]{36}$/.test(saved) ? saved : crypto.randomUUID()
      globalThis.sessionStorage?.setItem(key, value)
    } catch {
      // sessionStorage 不在でも同一画面内のIDで継続する。
      value = crypto.randomUUID()
    }
  }
  if (value === '') value = crypto.randomUUID()
  handoverRequestId.value = value
  return value
}

async function loadGame(id: string): Promise<HandoverGame> {
  const direct = await readStartedGame(id)
  if (direct.kind === 'found') return direct.game
  const lineup = await readLineupPrefixGame(id)
  if (lineup.kind === 'found') return lineup.game
  const play = await readPlayPrefixGame(id)
  if (play.kind === 'found') return play.game
  const recorded = await readRecordedPrefixGame(id)
  if (recorded.kind === 'found') return recorded.game
  throw new Error('試合の記録状態を取得できません')
}

async function lastAssignedD1(
  tenant: string,
  id: string,
  d4: string,
): Promise<number> {
  const queue = await openDurableQueue({
    databaseName: 'pitchlog-first-ball-queue-' + tenant,
  })
  try {
    const next = await queue.readNextD1({ game: id, d4 })
    return Math.max(0, next - 1)
  } finally {
    queue.close()
  }
}

async function load(): Promise<void> {
  state.value = 'loading'
  message.value = ''
  released.value = false
  acquired.value = false
  const id = gameId.value
  const tenant = auth.teamId
  if (!id || tenant === null || !auth.isAuthenticated) {
    state.value = 'failed'
    message.value = 'ログイン状態と試合を確認してください'
    return
  }
  let store: GameStartPersistence | null = null
  try {
    store = await GameStartPersistence.open()
    const [openedDevice, savedStart, receivedGame] = await Promise.all([
      store.readDevice(tenant),
      store.readStart(tenant, id),
      loadGame(id),
    ])
    device.value = openedDevice
    start.value = savedStart
    game.value = receivedGame
    if (savedStart?.status === 'released') released.value = true
    if (openedDevice && savedStart?.status === 'received') {
      lastD1.value = await lastAssignedD1(
        tenant,
        id,
        savedStart.grant?.d4 ?? receivedGame.current_d4,
      )
    }
    handoverRequestId.value = requestId()
    state.value = 'ready'
  } catch {
    state.value = 'failed'
    message.value = '引き継ぎの前提を確認できません'
  } finally {
    store?.close()
  }
}

async function enroll(): Promise<void> {
  const tenant = auth.teamId
  if (tenant === null || busy.value) return
  busy.value = true
  message.value = ''
  let store: GameStartPersistence | null = null
  try {
    store = await GameStartPersistence.open()
    const enrolled = await enrollInitialDevice(tenant)
    await store.rememberDevice(enrolled, tenant)
    device.value = enrolled
    handoverRequestId.value = requestId()
    message.value = 'この端末を登録しました'
  } catch {
    message.value = '端末登録の結果を確認できません'
  } finally {
    store?.close()
    busy.value = false
  }
}

async function release(): Promise<void> {
  const tenant = auth.teamId
  const saved = start.value
  if (
    tenant === null ||
    !device.value ||
    !holder.value ||
    !saved?.grant ||
    !confirmed.value ||
    busy.value
  )
    return
  busy.value = true
  message.value = ''
  let store: GameStartPersistence | null = null
  try {
    await releaseRecordingRightHandover(
      gameId.value,
      {
        handoverRequestId: requestIdInput.value,
        toDeviceId: toDeviceId.value,
        fromD4: saved.grant.d4,
        lastD1: lastD1.value ?? 0,
        recordingRightProof: saved.grant.recording_right_proof,
      },
      {
        deviceId: device.value.device_id,
        deviceCredential: device.value.device_credential,
      },
    )
    store = await GameStartPersistence.open()
    start.value = await store.markReleased(saved.owner)
    released.value = true
    confirmed.value = false
    message.value = '記録権を解放しました。この端末は読み取り専用になりました。'
  } catch {
    message.value =
      '解放を確認できません。未送信記録を確認し、同じ操作を再試行してください。'
  } finally {
    store?.close()
    busy.value = false
  }
}

async function acquire(): Promise<void> {
  const tenant = auth.teamId
  const receivedGame = game.value
  if (
    tenant === null ||
    !device.value ||
    !receivedGame ||
    holder.value ||
    busy.value
  )
    return
  busy.value = true
  message.value = ''
  let store: GameStartPersistence | null = null
  try {
    const grant = await acquireRecordingRightHandover(
      gameId.value,
      handoverRequestId.value,
      {
        deviceId: device.value.device_id,
        deviceCredential: device.value.device_credential,
      },
    )
    store = await GameStartPersistence.open()
    start.value = await store.rememberHandoverGrant(
      tenant,
      gameId.value,
      grant,
      { started_at: receivedGame.started_at, lineups: receivedGame.lineups },
    )
    acquired.value = true
    message.value = '引き継ぎを受け、この端末で記録を再開できます。'
  } catch {
    message.value =
      '旧端末の解放がまだ確認できません。旧端末の操作完了後に再試行してください。'
  } finally {
    store?.close()
    busy.value = false
  }
}

async function goRecord(): Promise<void> {
  await router.replace({
    name: 'game-record',
    params: { gameId: gameId.value },
    query: { recording: 'play-prefix-v3' },
  })
}

onMounted(load)
</script>

<template>
  <main class="mx-auto max-w-3xl space-y-5 p-4 pb-12 wrap-anywhere">
    <header class="space-y-2">
      <RouterLink
        :to="{ name: 'games' }"
        class="inline-block min-h-11 underline"
      >
        試合一覧へ
      </RouterLink>
      <h1 class="text-2xl font-extrabold">記録担当の引き継ぎ</h1>
      <p class="text-sm">
        元の記録端末がオンラインで解放を確定し、新しい端末が同じ引き継ぎ要求を受け取ります。
        未送信の記録が残っている間は解放できません。
      </p>
    </header>

    <p v-if="state === 'loading'" role="status">
      引き継ぎの前提を確認しています
    </p>
    <p v-else-if="state === 'failed'" role="alert">{{ message }}</p>

    <template v-else>
      <section v-if="!device" class="space-y-2 rounded-xl border p-4">
        <h2 class="text-lg font-bold">この端末を登録する</h2>
        <p>引き継ぎを受ける前に、この端末をチームへ登録します。</p>
        <button
          type="button"
          class="min-h-11 rounded-lg border px-3 py-2"
          :disabled="busy"
          @click="enroll"
        >
          この端末を登録
        </button>
      </section>

      <section
        v-else-if="holder"
        class="space-y-3 rounded-xl border p-4"
        aria-label="記録権の解放"
      >
        <h2 class="text-lg font-bold">この端末は現在の記録端末です</h2>
        <dl class="grid gap-1 text-sm">
          <div>
            <dt class="inline font-bold">現在の世代:</dt>
            <dd class="inline">{{ game?.current_d4 }}</dd>
          </div>
          <div>
            <dt class="inline font-bold">同期済みの最終連番:</dt>
            <dd class="inline">{{ lastD1 ?? 0 }}</dd>
          </div>
        </dl>
        <label class="block text-sm">
          新しい記録端末のID
          <input
            v-model.trim="toDeviceId"
            class="mt-1 block min-h-11 w-full rounded border px-3 py-2"
            autocomplete="off"
          />
        </label>
        <label class="block text-sm">
          引き継ぎ要求ID（新端末に表示された値）
          <input
            v-model.trim="requestIdInput"
            class="mt-1 block min-h-11 w-full rounded border px-3 py-2"
            autocomplete="off"
          />
        </label>
        <label class="flex items-start gap-2 text-sm">
          <input v-model="confirmed" type="checkbox" class="mt-1" />
          <span>
            記録入力を停止し、表示中の最終連番まで同期済みであることを確認しました。
          </span>
        </label>
        <button
          type="button"
          class="min-h-11 rounded-lg border px-3 py-2"
          :disabled="busy || !confirmed || !toDeviceId || !requestIdInput"
          @click="release"
        >
          記録権を解放する
        </button>
        <p v-if="released" role="status" class="font-bold">
          この端末は読み取り専用です。新しい端末で記録を再開してください。
        </p>
      </section>

      <section
        v-else
        class="space-y-3 rounded-xl border p-4"
        aria-label="引き継ぎの取得"
      >
        <h2 class="text-lg font-bold">この端末で引き継ぎを受ける</h2>
        <p class="text-sm">
          次の2つを、現在の記録端末の「記録権を解放する」欄へ入力してください。
        </p>
        <label class="block text-sm">
          この端末のID
          <input
            :value="device.device_id"
            readonly
            class="mt-1 block min-h-11 w-full rounded border bg-gray-50 px-3 py-2"
          />
        </label>
        <label class="block text-sm">
          引き継ぎ要求ID
          <input
            :value="handoverRequestId"
            readonly
            class="mt-1 block min-h-11 w-full rounded border bg-gray-50 px-3 py-2"
          />
        </label>
        <button
          type="button"
          class="min-h-11 rounded-lg border px-3 py-2"
          :disabled="busy"
          @click="acquire"
        >
          旧端末の解放後に引き継ぎを受ける
        </button>
        <p v-if="acquired" role="status" class="font-bold">
          引き継ぎを受けました。この端末で記録を再開できます。
        </p>
        <button
          v-if="acquired"
          type="button"
          class="min-h-11 rounded-lg border px-3 py-2"
          @click="goRecord"
        >
          記録画面へ
        </button>
      </section>

      <p v-if="message" role="status" class="rounded border p-3 text-sm">
        {{ message }}
      </p>
    </template>
  </main>
</template>
