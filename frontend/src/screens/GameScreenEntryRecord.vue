<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { isPreparingGame } from '../api/games'
import { canonicalUuid } from '../api/authIntent'
import { useAuthStore } from '../stores/authStore'
import GameScreen from './GameScreen.vue'
import GameScreenRecordedRestore from './GameScreenRecordedRestore.vue'
import GameScreenEntryPremises from './GameScreenEntryPremises.vue'
import {
  currentEntrySupply,
  datumLabel,
  entryStatusLabel,
  existingStateLabel,
  isEntryEnvironment,
  isRecordDetail,
  type EntryEnvironment,
  type EntrySupply,
  type RecordDetail,
  type PreparingReadDetail,
} from './GameScreenEntryTypes'

const props = withDefaults(
  defineProps<{
    mode?: 'preparing-read'
    preparing?: EntrySupply<PreparingReadDetail> | null
    detail?: EntrySupply<RecordDetail> | null
    environment?: EntrySupply<EntryEnvironment> | null
    restoreAuto?: boolean
  }>(),
  {
    mode: undefined,
    preparing: undefined,
    detail: undefined,
    environment: undefined,
    restoreAuto: undefined,
  },
)
const emit = defineEmits<{ retry: [] }>()
const route = useRoute()
const auth = useAuthStore()
const gameId = computed(() => route.params.gameId)
// 未保存下書きは画面内にだけあるため、試合・認証の実scopeごとに画面を作り直す。
const recordScopeKey = computed(() =>
  JSON.stringify([auth.authEpoch, auth.teamId, route.path, gameId.value]),
)
const validId = computed(
  () => typeof gameId.value === 'string' && canonicalUuid.test(gameId.value),
)
const source = computed(() =>
  validId.value ? currentEntrySupply(props.detail, auth, route) : null,
)
const environment = computed(() => {
  const received = currentEntrySupply(props.environment, auth, route, null)
  return received?.status === 'ready' && isEntryEnvironment(received.data)
    ? received.data
    : null
})
const visibleDetail = computed(() => {
  const received = source.value
  return received?.status === 'ready' &&
    received.data &&
    auth.teamId !== null &&
    received.data.gameId === gameId.value &&
    isRecordDetail(received.data, auth.teamId)
    ? received.data
    : null
})
const recordEntryDenied = computed(
  () =>
    source.value?.status === 'denied' ||
    visibleDetail.value?.recordingRight === 'denied',
)
const preparingSource = computed(() =>
  validId.value
    ? currentEntrySupply(props.preparing, auth, route, gameId.value as string)
    : null,
)
const savedDetail = computed(() => {
  const source = preparingSource.value
  const data = source?.data
  return source?.status === 'ready' &&
    data &&
    data.tenantId === auth.teamId &&
    data.gameId === gameId.value &&
    typeof data.label === 'string' &&
    isPreparingGame(data.saved) &&
    data.saved.id === gameId.value
    ? data
    : null
})
const showDraftForm = computed(
  () =>
    props.mode !== 'preparing-read' &&
    validId.value &&
    auth.hasHydrated &&
    auth.isAuthenticated &&
    auth.teamId !== null &&
    canonicalUuid.test(auth.teamId) &&
    !recordEntryDenied.value,
)
</script>

<template>
  <main class="mx-auto max-w-5xl space-y-5 p-4 pb-12 wrap-anywhere">
    <header class="space-y-2">
      <RouterLink
        :to="{ name: 'games' }"
        class="inline-block min-h-11 underline"
      >
        試合一覧へ
      </RouterLink>
      <h1 class="text-2xl font-extrabold">記録画面の入口</h1>
      <p v-if="!validId" role="status">試合IDが正しくありません。</p>
      <template v-else-if="mode === 'preparing-read'">
        <h2 class="text-lg font-bold">準備中試合の保存情報</h2>
        <dl v-if="savedDetail" class="grid gap-2 rounded-xl border p-4">
          <div>
            <dt>試合</dt>
            <dd>{{ savedDetail.label }}</dd>
          </div>
          <div>
            <dt>状態</dt>
            <dd>準備中</dd>
          </div>
          <div>
            <dt>種別</dt>
            <dd>{{ savedDetail.saved.game_type_key }}</dd>
          </div>
          <div>
            <dt>大会</dt>
            <dd>{{ savedDetail.saved.tournament_key }}</dd>
          </div>
          <div>
            <dt>ビジターチームID</dt>
            <dd>{{ savedDetail.saved.away_team_record_id }}</dd>
          </div>
          <div>
            <dt>ホームチームID</dt>
            <dd>{{ savedDetail.saved.home_team_record_id }}</dd>
          </div>
          <div>
            <dt>球審</dt>
            <dd>{{ savedDetail.saved.plate_umpire ?? '未設定' }}</dd>
          </div>
          <div>
            <dt>保存された適用規則</dt>
            <dd>
              <pre class="whitespace-pre-wrap wrap-anywhere">{{
                JSON.stringify(savedDetail.saved.applied_rules, null, 2)
              }}</pre>
            </dd>
          </div>
        </dl>
        <p v-else role="status">
          準備中試合の保存情報：{{ entryStatusLabel(preparingSource?.status) }}
        </p>
        <button
          v-if="
            preparingSource?.status === 'failed' ||
            preparingSource?.status === 'denied'
          "
          type="button"
          class="min-h-11 rounded-lg border px-3 py-2"
          @click="emit('retry')"
        >
          この試合を再試行
        </button>
        <p>スタメン・記録権・下書き復元：未取得</p>
      </template>
      <p v-else-if="visibleDetail === null" role="status">
        試合詳細・記録権・下書き復元：{{ entryStatusLabel(source?.status) }}
      </p>
      <dl v-else class="grid min-w-0 gap-2 rounded-xl border p-4">
        <div>
          <dt>試合</dt>
          <dd>{{ visibleDetail.label }}</dd>
        </div>
        <div>
          <dt>スタメン</dt>
          <dd>{{ datumLabel(visibleDetail.lineup) }}</dd>
        </div>
        <div>
          <dt>適用規則</dt>
          <dd>{{ datumLabel(visibleDetail.rules) }}</dd>
        </div>
        <div>
          <dt>記録権</dt>
          <dd>
            {{
              visibleDetail.recordingRight === 'held'
                ? '保持'
                : visibleDetail.recordingRight === 'denied'
                  ? '非保持'
                  : '未取得'
            }}
          </dd>
        </div>
        <div>
          <dt>既存状態</dt>
          <dd>
            {{ existingStateLabel(visibleDetail.existingState) }}
          </dd>
        </div>
        <div>
          <dt>下書き復元</dt>
          <dd>{{ datumLabel(visibleDetail.draftRestoration) }}</dd>
        </div>
      </dl>
      <p v-if="visibleDetail?.recordingRight === 'denied'">
        記録権を保持していません。記録を再開できません。
      </p>
      <p v-if="visibleDetail?.existingState === 'suspended'">
        中断中の試合です。再開状態の正式提供を待っています。
      </p>
      <button
        type="button"
        disabled
        class="min-h-11 rounded-lg border px-3 py-2"
      >
        記録を再開（未提供）
      </button>
    </header>
    <GameScreenRecordedRestore
      v-if="savedDetail === null && preparingSource?.status === 'denied'"
      :auto="props.restoreAuto"
    />
    <GameScreenEntryPremises :environment="environment" />
    <section aria-label="試合の閲覧" class="space-y-2">
      <h2 class="text-lg font-bold">試合の閲覧</h2>
      <p>記録内容は未取得です。記録の確定・保存・送信はできません。</p>
      <p v-if="!validId">
        正しい試合IDで開くと、閲覧を続けられます。未送信キューは変更しません。
      </p>
      <p v-else-if="visibleDetail?.recordingRight === 'denied'">
        記録権がないため入力欄は表示しません。閲覧と未送信キューの保持は続けられます。
      </p>
      <p v-else-if="recordEntryDenied">
        この試合の情報を確認できないため入力欄は表示しません。閲覧と未送信キューの保持は続けられます。
      </p>
      <GameScreen v-if="showDraftForm" :key="recordScopeKey" />
    </section>
  </main>
</template>
