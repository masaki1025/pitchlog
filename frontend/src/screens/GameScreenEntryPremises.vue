<script setup lang="ts">
import { computed } from 'vue'
import type {
  EntryConnectivity,
  EntryEnvironment,
  PremiseStatus,
} from './GameScreenEntryTypes'

const props = defineProps<{ environment?: EntryEnvironment | null }>()
const premises = [
  { number: 1, content: 'トップレベルの HTTPS 表示' },
  { number: 5, content: 'サイトストレージが利用可能' },
  { number: 6, content: 'Lockdown Mode 非適用' },
] as const

function status(number: 1 | 5 | 6): PremiseStatus {
  const received = props.environment?.premises?.[number]
  return received === 'met' || received === 'unmet' ? received : 'unknown'
}

const outstanding = computed(() =>
  premises.filter(({ number }) => status(number) !== 'met'),
)
const count = computed(() => {
  const value = props.environment?.queuedCount
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? String(value)
    : '未取得'
})
const persistenceDenied = computed(
  () => props.environment?.persistence === 'denied' && status(5) === 'met',
)
const connectivity = computed<EntryConnectivity>(() => {
  const received = props.environment?.connectivity
  return received === 'online' || received === 'offline' ? received : 'unknown'
})
</script>

<template>
  <section
    aria-label="記録開始前提"
    class="min-w-0 space-y-3 rounded-2xl border border-slate-300 p-4 wrap-anywhere"
  >
    <h2 class="text-lg font-bold">記録開始前提</h2>
    <p v-if="connectivity === 'online'">
      通信状態：オンライン（提供された状態）
    </p>
    <p v-else-if="connectivity === 'offline'" role="status">
      通信状態：オフライン。通信が切れているため、試合を開始・再開できません。
    </p>
    <p v-else role="status">
      通信状態：未取得。通信状態を確認できないため、試合を開始・再開できません。
    </p>
    <p v-if="outstanding.length === 0">
      前提1・5・6は成立と提供されています。記録開始の接続は未提供です。
    </p>
    <template v-else>
      <p>次の前提を確認できないため、記録を開始できません。</p>
      <ul class="list-inside list-disc space-y-1">
        <li v-for="item in outstanding" :key="item.number">
          前提{{ item.number }} {{ item.content }}：{{
            status(item.number) === 'unmet' ? '不成立' : '不明'
          }}
        </li>
      </ul>
    </template>
    <p v-if="persistenceDenied" role="status">
      永続化保証の要求が拒否されました。未送信キューが消える可能性があります。サイトストレージは利用可能なため、この警告だけでは開始前提5の不成立ではありません。通信状態とほかの前提が成立している場合に限り、記録を継続できます。実際の開始は接続前のためできません。
    </p>
    <p>
      既存の未送信キューは保持します。未送信件数：{{
        count
      }}。試合の閲覧はできます。
    </p>
  </section>
</template>
