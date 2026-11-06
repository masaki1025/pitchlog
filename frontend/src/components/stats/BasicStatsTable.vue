<script setup lang="ts">
import type { BasicStatItem, PlayerBasicStats } from '../../api/stats'

defineProps<{
  players: PlayerBasicStats[]
  periodLabel: string
}>()

const reasonLabels: Record<string, string> = {
  D03_SOURCE_PENDING: '登板: 正式な投手出場sourceが未接続',
  D04_SOURCE_PENDING: '打者数: 責任帰属sourceが未接続',
  MISSING_OBSERVATION: '観測が未取得',
  MISSING_ATTRIBUTION: '責任帰属が未取得',
}

function display(item: BasicStatItem | undefined): string {
  if (item === undefined) return '—'
  if (item.state === 'available' && item.display !== null) return item.display
  return item.reason === null
    ? '未取得'
    : (reasonLabels[item.reason] ?? '未取得')
}

function onlyPitchers(players: PlayerBasicStats[]): PlayerBasicStats[] {
  return players.filter((player) => player.is_pitcher)
}
</script>

<template>
  <section class="space-y-6">
    <p v-if="players.length === 0" class="text-sm">データなし</p>
    <template v-else>
      <div>
        <h2 class="mb-2 text-lg font-semibold">{{ periodLabel }} 打撃</h2>
        <div class="overflow-x-auto">
          <table class="min-w-full border-collapse text-sm">
            <thead>
              <tr>
                <th class="border px-2 py-1 text-left">選手</th>
                <th class="border px-2 py-1 text-left">チーム</th>
                <th
                  v-for="item in players[0]?.batting ?? []"
                  :key="item.metric_id"
                  class="border px-2 py-1 text-right"
                >
                  {{ item.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="player in players" :key="player.player_id">
                <td class="border px-2 py-1">
                  {{ player.uniform_number }} {{ player.player_name }}
                </td>
                <td class="border px-2 py-1">{{ player.team_name }}</td>
                <td
                  v-for="item in player.batting"
                  :key="item.metric_id"
                  class="border px-2 py-1 text-right"
                  :title="item.reason ?? undefined"
                >
                  {{ display(item) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <h2 class="mb-2 text-lg font-semibold">{{ periodLabel }} 投手</h2>
        <p v-if="onlyPitchers(players).length === 0" class="text-sm">
          投手成績なし
        </p>
        <div v-else class="overflow-x-auto">
          <table class="min-w-full border-collapse text-sm">
            <thead>
              <tr>
                <th class="border px-2 py-1 text-left">選手</th>
                <th class="border px-2 py-1 text-left">チーム</th>
                <th
                  v-for="item in onlyPitchers(players)[0]?.pitching ?? []"
                  :key="item.metric_id"
                  class="border px-2 py-1 text-right"
                >
                  {{ item.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="player in onlyPitchers(players)"
                :key="player.player_id"
              >
                <td class="border px-2 py-1">
                  {{ player.uniform_number }} {{ player.player_name }}
                </td>
                <td class="border px-2 py-1">{{ player.team_name }}</td>
                <td
                  v-for="item in player.pitching"
                  :key="item.metric_id"
                  class="border px-2 py-1 text-right"
                  :title="item.reason ?? undefined"
                >
                  {{ display(item) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>
