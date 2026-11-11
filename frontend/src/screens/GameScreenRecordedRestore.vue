<script setup lang="ts">
import { computed, toRaw, ref, watch } from 'vue'
import GameScreenFirstBall from './GameScreenFirstBall.vue'
import GameScreenOrdinaryPitch from './GameScreenOrdinaryPitch.vue'
import GameScreenUndoProduct from './GameScreenUndoProduct.vue'
import GameScreenLifecycleProduct from './GameScreenLifecycleProduct.vue'
import GameScreenSubstitutionProduct from './GameScreenSubstitutionProduct.vue'
import GameScreenPastCorrectionProduct from './GameScreenPastCorrectionProduct.vue'
import { ordinaryContextFromRead } from '../api/recordedPrefixGame'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  playContextFromRead,
  lineupContextFromRead,
  type RecordingContext,
} from './GameScreenOrdinaryPitchProvider'
import { useAuthStore } from '../stores/authStore'
import { useRoute, useRouter } from 'vue-router'
import {
  beforeState,
  currentState,
  firstHistory,
  historyCount,
  playCount,
  useRecordedRestore,
  type RecordingGameRead,
} from './GameScreenRecordedRestore'

const props = withDefaults(defineProps<{ auto?: boolean }>(), {
  auto: undefined,
})
const emit = defineEmits<{ fullscreen: [value: boolean] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const gameId = computed(() =>
  typeof route.params.gameId === 'string' ? route.params.gameId : undefined,
)
const undoNative = ref(false)
const undoProduct = ref<{ reload: () => Promise<void> } | null>(null)
const auto = computed(() => props.auto)
// 旧版で保存した要求の復旧入口だけを閉じた内部queryで保持する。
const legacy = computed(() => route.query.recording === 'ordinary-prefix-v1')
const projection = computed(() => {
  const value = route.query.recording
  if (value === 'play-prefix-v3') return 'play-prefix-v3' as const
  if (
    value === undefined ||
    value === 'ordinary-prefix-v1' ||
    value === 'play-prefix-v2'
  )
    return null
  return 'invalid' as const
})
const restore = useRecordedRestore(gameId, auto, legacy, projection)
async function enterLineup() {
  await router.replace({
    query: { ...route.query, recording: 'play-prefix-v3' },
  })
  await restore.reload()
}
async function enterPreviousRecording() {
  const query = { ...route.query }
  delete query.recording
  await router.replace({ query })
  await restore.reload()
}
const current = computed(() =>
  restore.game.value ? currentState(restore.game.value) : null,
)
const before = computed(() =>
  restore.game.value ? beforeState(restore.game.value) : null,
)
const recorded = computed(
  () =>
    restore.game.value?.read_kind === 'recorded' ||
    ((restore.game.value?.read_kind === 'recorded-prefix' ||
      restore.game.value?.read_kind === 'play-prefix' ||
      restore.game.value?.read_kind === 'lineup-prefix') &&
      BigInt(restore.game.value.prefix_ref.length) > 0n),
)
const prefixContext = ref<RecordingContext | null>(null)
watch(prefixContext, (value) => emit('fullscreen', value !== null), {
  immediate: true,
})
const contextRefreshing = ref(false)
let contextScope: {
  gameId: string
  tenant: string
  epoch: number
  d4: string
} | null = null
let retainConfirmedInput = false
async function pitchSaved() {
  const sourceScope = [gameId.value, auth.teamId, auth.authEpoch] as const
  let ready = false
  retainConfirmedInput = true
  try {
    await restore.reload()
    ready =
      restore.status.value === 'ready' &&
      gameId.value === sourceScope[0] &&
      auth.teamId === sourceScope[1] &&
      auth.authEpoch === sourceScope[2]
  } finally {
    retainConfirmedInput = false
  }
  if (ready) await undoProduct.value?.reload?.()
}
const inputSuspended = computed(
  () =>
    contextRefreshing.value ||
    (restore.status.value !== 'ready' &&
      restore.status.value !== 'offline-ready'),
)
let contextSequence = 0
// pending/確認済みの同値入力だけを保持し、失敗値を再利用しない。
let watchedContextInput: unknown = null
watch(
  [
    () => restore.game.value,
    () => restore.status.value,
    () => auth.teamId,
    () => auth.authEpoch,
    () => auth.hasHydrated,
    () => auth.isAuthenticated,
  ],
  async () => {
    let input: {
      game: RecordingGameRead | null
      tenant: typeof auth.teamId
      epoch: number
      hydrated: boolean
      authenticated: boolean
      readFailed: boolean
    }
    try {
      input = {
        game:
          restore.game.value === null
            ? null
            : structuredClone(toRaw(restore.game.value)),
        tenant: auth.teamId,
        epoch: auth.authEpoch,
        hydrated: auth.hasHydrated,
        authenticated: auth.isAuthenticated,
        readFailed: ['failed', 'not-found', 'unavailable'].includes(
          restore.status.value,
        ),
      }
    } catch {
      contextSequence++
      watchedContextInput = null
      prefixContext.value = null
      contextScope = null
      contextRefreshing.value = false
      return
    }
    // 全受信値と認証scopeが同じなら、進行中のasync/子の入力を失効させない。
    if (
      watchedContextInput !== null &&
      sameOrdinaryWire(watchedContextInput, input)
    )
      return
    const own = ++contextSequence
    watchedContextInput = null
    // 同じ記録端末scopeの新GET解析中だけ子を保持し、入力は明示的に止める。
    // 確認値を別試合・別認証世代へ持ち越さない。
    const keep =
      retainConfirmedInput &&
      prefixContext.value !== null &&
      contextScope !== null &&
      input.game?.id === contextScope.gameId &&
      'current_d4' in input.game &&
      input.game.current_d4 === contextScope.d4 &&
      input.tenant === contextScope.tenant &&
      input.epoch === contextScope.epoch &&
      input.hydrated &&
      input.authenticated &&
      !input.readFailed
    if (!keep) {
      prefixContext.value = null
      contextScope = null
    }
    contextRefreshing.value = true
    if (
      (restore.status.value !== 'ready' &&
        restore.status.value !== 'offline-ready') ||
      input.readFailed ||
      !input.game ||
      !input.tenant ||
      !input.hydrated ||
      !input.authenticated
    ) {
      contextRefreshing.value = false
      return
    }
    watchedContextInput = input
    try {
      const source = input.game
      if (source.read_kind === 'lineup-prefix') {
        const context = await lineupContextFromRead(source, input.tenant)
        if (own === contextSequence) prefixContext.value = context
      } else if (source.read_kind === 'play-prefix') {
        const context = await playContextFromRead(source, input.tenant)
        if (own === contextSequence) prefixContext.value = context
      } else if (source.read_kind === 'recorded-prefix') {
        prefixContext.value = {
          ...ordinaryContextFromRead(source, input.tenant),
          serverStamp: {
            recoveryGeneration: source.recovery_generation,
            checkpointAnchor: source.checkpoint_anchor,
            lastSavedAt: source.last_saved_at,
          },
        }
      }
      if (own === contextSequence && prefixContext.value) {
        contextScope = {
          gameId: source.id,
          tenant: input.tenant,
          epoch: input.epoch,
          d4: 'current_d4' in source ? source.current_d4 : '',
        }
      }
    } catch {
      if (own === contextSequence) {
        contextScope = null
        prefixContext.value = null
        // 同値再取得でも再試行できる。pending同値の二重開始とは区別する。
        watchedContextInput = null
      }
    } finally {
      if (own === contextSequence) contextRefreshing.value = false
    }
  },
  { immediate: true },
)
const history = computed(() =>
  restore.game.value ? firstHistory(restore.game.value) : null,
)
const lineupGame = computed(() =>
  restore.game.value?.read_kind === 'lineup-prefix' ? restore.game.value : null,
)
</script>

<template>
  <GameScreenOrdinaryPitch
    v-if="prefixContext && !undoNative"
    :suspended="inputSuspended"
    :context="prefixContext"
    :game-read="lineupGame"
    @saved="pitchSaved"
    @reload="restore.reload()"
  />
  <section
    v-show="!undoNative && !prefixContext"
    aria-label="サーバーから復元した状態"
    class="space-y-2 rounded-xl border p-4"
  >
    <h2 class="text-lg font-bold">
      {{
        restore.status.value === 'offline-ready'
          ? '端末の未同期記録'
          : 'サーバーから復元した状態'
      }}
    </h2>
    <p role="status">{{ restore.message.value }}</p>
    <GameScreenFirstBall
      v-if="
        restore.game.value &&
        restore.game.value.read_kind !== 'recorded-prefix' &&
        restore.game.value.read_kind !== 'play-prefix' &&
        restore.game.value.read_kind !== 'lineup-prefix'
      "
      :key="restore.game.value.id"
      :game="restore.game.value"
      @saved="restore.reload()"
    />
    <GameScreenPastCorrectionProduct
      v-if="
        !prefixContext &&
        auto !== false &&
        restore.game.value?.read_kind === 'lineup-prefix' &&
        (restore.status.value === 'ready' || restore.status.value === 'loading')
      "
      :game="restore.game.value"
      :suspended="restore.status.value !== 'ready'"
      @saved="restore.reload()"
    />
    <button
      v-if="restore.game.value?.read_kind === 'initial'"
      type="button"
      :disabled="restore.status.value === 'loading'"
      @click="restore.loadOrdinary()"
    >
      通常投球（ボール・ストライク・ファウル）の入力へ
    </button>
    <button
      type="button"
      class="min-h-11 rounded-lg border px-3 py-2"
      :disabled="restore.status.value === 'loading'"
      @click="restore.reload()"
    >
      {{ restore.game.value ? 'サーバーから再取得' : 'サーバーから復元' }}
    </button>
    <dl v-if="restore.game.value && current" class="grid gap-2">
      <div>
        <dt>取得種別</dt>
        <dd>
          {{
            restore.game.value.read_kind === 'recorded-prefix' ||
            restore.game.value.read_kind === 'play-prefix' ||
            restore.game.value.read_kind === 'lineup-prefix'
              ? recorded
                ? '保存済みの記録（表示履歴は有限ページ）'
                : '開始済み（記録前）'
              : recorded
                ? '記録済み（保存初球1件）'
                : '開始済み（記録前）'
          }}
        </dd>
      </div>
      <div
        v-if="
          restore.game.value.read_kind === 'recorded-prefix' ||
          restore.game.value.read_kind === 'play-prefix' ||
          restore.game.value.read_kind === 'lineup-prefix'
        "
      >
        <dt>サーバーの最終保存日時</dt>
        <dd data-testid="restore-last-saved-at">
          {{ restore.game.value.last_saved_at }}
        </dd>
      </div>
      <div>
        <dt>現在のボール</dt>
        <dd data-testid="restore-balls">
          {{ current.stateFields['state.count.balls'] }}
        </dd>
      </div>
      <div>
        <dt>現在のストライク</dt>
        <dd data-testid="restore-strikes">
          {{ current.stateFields['state.count.strikes'] }}
        </dd>
      </div>
      <div>
        <dt>アウト</dt>
        <dd data-testid="restore-outs">
          {{ current.stateFields['state.outs'] }}
        </dd>
      </div>
      <div>
        <dt>イニング</dt>
        <dd>
          {{ current.stateFields['state.inning'] }}回
          {{ current.stateFields['state.half'] === 'top' ? '表' : '裏' }}
        </dd>
      </div>
      <div>
        <dt>走者</dt>
        <dd data-testid="restore-runners">
          {{ current.stateFields['state.runners'] }}
        </dd>
      </div>
      <div>
        <dt>打順</dt>
        <dd>{{ current.stateFields['state.battingOrder'] }}</dd>
      </div>
      <div>
        <dt>得点</dt>
        <dd>
          {{ current.stateFields['state.score'].home }} -
          {{ current.stateFields['state.score'].away }}
        </dd>
      </div>
      <div v-if="recorded && before">
        <dt>開始前（before）のボール</dt>
        <dd data-testid="restore-before-balls">
          {{ before.stateFields['state.count.balls'] }}
        </dd>
      </div>
      <div>
        <dt>
          {{
            restore.game.value.read_kind === 'recorded-prefix' ||
            restore.game.value.read_kind === 'play-prefix' ||
            restore.game.value.read_kind === 'lineup-prefix'
              ? restore.game.value.read_kind === 'recorded-prefix'
                ? '通常投球の確定水位（一般履歴長とは別）'
                : '保存済みの履歴'
              : '履歴'
          }}
        </dt>
        <dd data-testid="restore-history">
          {{ restore.game.value ? historyCount(restore.game.value) : 0 }}件
        </dd>
      </div>
      <div>
        <dt>
          {{
            restore.game.value.read_kind === 'recorded-prefix' ||
            restore.game.value.read_kind === 'play-prefix' ||
            restore.game.value.read_kind === 'lineup-prefix'
              ? restore.game.value.read_kind === 'lineup-prefix'
                ? '表示中のプレイ数'
                : '表示ページのPlayRow件数'
              : '保存初球'
          }}
        </dt>
        <dd data-testid="restore-plays">
          {{ restore.game.value ? playCount(restore.game.value) : 0 }}件
        </dd>
      </div>
      <div v-if="history">
        <dt>
          {{
            restore.game.value.read_kind === 'recorded-prefix' ||
            restore.game.value.read_kind === 'play-prefix' ||
            restore.game.value.read_kind === 'lineup-prefix'
              ? '最後の記録1件の差分（全履歴ではありません）'
              : '履歴1件の差分'
          }}
        </dt>
        <dd>
          {{
            Object.entries(history.difference.stateFields)
              .map(([key, value]) => `${key}: ${value.before}→${value.after}`)
              .join(', ')
          }}
        </dd>
      </div>
    </dl>
    <button
      v-if="projection === 'play-prefix-v3'"
      type="button"
      :disabled="restore.status.value === 'loading'"
      @click="enterPreviousRecording"
    >
      従来の投球記録を表示
    </button>
    <button
      v-if="projection === null"
      type="button"
      :disabled="restore.status.value === 'loading'"
      @click="enterLineup"
    >
      三振・攻守交代を含む投球の記録へ
    </button>
  </section>
  <div v-show="!prefixContext">
    <GameScreenUndoProduct
      v-if="gameId && auto !== false"
      ref="undoProduct"
      :key="gameId"
      :game-id="gameId"
      @state="undoNative = $event"
      @saved="restore.reload()"
    />
  </div>
  <GameScreenLifecycleProduct
    v-if="gameId && auto !== false && !prefixContext"
    :key="gameId"
    :game-id="gameId"
    @resume-recording="restore.reload()"
  />
  <GameScreenSubstitutionProduct
    v-if="gameId && auto !== false && !prefixContext"
    :key="gameId"
    :game-id="gameId"
    @saved="restore.reload()"
  />
</template>
