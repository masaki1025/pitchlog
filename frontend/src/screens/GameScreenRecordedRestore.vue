<script setup lang="ts">
import { computed, toRaw, ref, watch } from 'vue'
import GameScreenFirstBall from './GameScreenFirstBall.vue'
import GameScreenOrdinaryPitch from './GameScreenOrdinaryPitch.vue'
import { ordinaryContextFromRead } from '../api/recordedPrefixGame'
import { sameOrdinaryWire } from '../api/ordinaryPitchWire'
import {
  playContextFromRead,
  type RecordingContext,
} from './GameScreenOrdinaryPitchProvider'
import { useAuthStore } from '../stores/authStore'
import { useRoute } from 'vue-router'
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
const route = useRoute()
const auth = useAuthStore()
const gameId = computed(() =>
  typeof route.params.gameId === 'string' ? route.params.gameId : undefined,
)
const auto = computed(() => props.auto)
// 旧版で保存した要求の復旧入口だけを閉じた内部queryで保持する。
const legacy = computed(() => route.query.recording === 'ordinary-prefix-v1')
const restore = useRecordedRestore(gameId, auto, legacy)
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
      restore.game.value?.read_kind === 'play-prefix') &&
      BigInt(restore.game.value.prefix_ref.length) > 0n),
)
const prefixContext = ref<RecordingContext | null>(null)
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
    prefixContext.value = null
    if (
      restore.status.value !== 'ready' ||
      input.readFailed ||
      !input.game ||
      !input.tenant ||
      !input.hydrated ||
      !input.authenticated
    )
      return
    watchedContextInput = input
    try {
      const source = input.game
      if (source.read_kind === 'play-prefix') {
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
    } catch {
      if (own === contextSequence) {
        prefixContext.value = null
        // 同値再取得でも再試行できる。pending同値の二重開始とは区別する。
        watchedContextInput = null
      }
    }
  },
  { immediate: true },
)
const history = computed(() =>
  restore.game.value ? firstHistory(restore.game.value) : null,
)
</script>

<template>
  <section
    aria-label="サーバーから復元した状態"
    class="space-y-2 rounded-xl border p-4"
  >
    <h2 class="text-lg font-bold">サーバーから復元した状態</h2>
    <p role="status">{{ restore.message.value }}</p>
    <GameScreenOrdinaryPitch
      v-if="prefixContext"
      :context="prefixContext"
      @saved="restore.reload()"
    />
    <GameScreenFirstBall
      v-else-if="
        restore.game.value &&
        restore.game.value.read_kind !== 'recorded-prefix' &&
        restore.game.value.read_kind !== 'play-prefix'
      "
      :key="restore.game.value.id"
      :game="restore.game.value"
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
            restore.game.value.read_kind === 'play-prefix'
              ? '保存済みの記録（表示履歴は有限ページ）'
              : recorded
                ? '記録済み（保存初球1件）'
                : '開始済み（記録前）'
          }}
        </dd>
      </div>
      <div
        v-if="
          restore.game.value.read_kind === 'recorded-prefix' ||
          restore.game.value.read_kind === 'play-prefix'
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
            restore.game.value.read_kind === 'play-prefix'
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
            restore.game.value.read_kind === 'play-prefix'
              ? '表示ページのPlayRow件数'
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
            restore.game.value.read_kind === 'play-prefix'
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
  </section>
</template>
