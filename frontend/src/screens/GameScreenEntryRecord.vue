<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { canonicalUuid } from '../api/authIntent'
import { useAuthStore } from '../stores/authStore'
import GameScreen from './GameScreen.vue'
import GameScreenEntryPremises from './GameScreenEntryPremises.vue'
import {
  currentEntrySupply,
  datumLabel,
  entryStatusLabel,
  existingStateLabel,
  isRecordDetail,
  type EntryEnvironment,
  type EntrySupply,
  type RecordDetail,
} from './GameScreenEntryTypes'

const props = defineProps<{
  detail?: EntrySupply<RecordDetail> | null
  environment?: EntrySupply<EntryEnvironment> | null
}>()
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
  const received = currentEntrySupply(props.environment, auth, route)
  return received?.status === 'ready' ? received.data : null
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
        記録権を確認できないため、記録を再開できません。
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
    <GameScreenEntryPremises :environment="environment" />
    <section aria-label="試合の閲覧" class="space-y-2">
      <h2 class="text-lg font-bold">試合の閲覧</h2>
      <p>記録内容は未取得です。記録の確定・保存・送信はできません。</p>
      <GameScreen :key="recordScopeKey" />
    </section>
  </main>
</template>
