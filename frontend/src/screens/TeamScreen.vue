<script setup lang="ts">
import { useInfiniteQuery } from '@tanstack/vue-query'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { ApiNetworkError, ApiStaleAuthError } from '../api/client'
import {
  listPlayers,
  listTeamRecords,
  type PlayerRead,
  type TeamRecordRead,
} from '../api/roster'
import TeamMembersContent from '../components/settings/TeamMembersContent.vue'
import Button from '../components/ui/Button.vue'
import { rosterQueryKeys } from '../lib/rosterQueryKeys'
import { useAuthStore } from '../stores/authStore'

const PAGE_LIMIT = 25

const auth = useAuthStore()
const { authEpoch, teamId, teamName } = storeToRefs(auth)
const selectedTeamRecordId = ref<string | null>(null)

const teamRecordsQuery = useInfiniteQuery({
  queryKey: computed(() =>
    rosterQueryKeys.teamRecords.pages(
      teamId.value,
      authEpoch.value,
      PAGE_LIMIT,
    ),
  ),
  enabled: computed(() => teamId.value !== null),
  initialPageParam: null as string | null,
  queryFn: async ({ pageParam, signal }) => {
    const requestEpoch = authEpoch.value
    const page = await listTeamRecords(
      { cursor: pageParam, include_hidden: false, limit: PAGE_LIMIT },
      { signal },
    )
    if (authEpoch.value !== requestEpoch) {
      throw new ApiStaleAuthError('GET', '/team-records')
    }
    return page
  },
  getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
})

const teamRecords = computed<TeamRecordRead[]>(
  () => teamRecordsQuery.data.value?.pages.flatMap((page) => page.items) ?? [],
)

watch(
  [teamId, authEpoch],
  () => {
    selectedTeamRecordId.value = null
  },
  { flush: 'sync' },
)

watch(
  teamRecords,
  (records) => {
    if (records.length === 0) {
      selectedTeamRecordId.value = null
      return
    }
    if (
      selectedTeamRecordId.value !== null &&
      records.some((record) => record.id === selectedTeamRecordId.value)
    ) {
      return
    }
    selectedTeamRecordId.value =
      records.find((record) => record.kind === 'self')?.id ??
      records[0]?.id ??
      null
  },
  { flush: 'sync' },
)

const selectedTeamRecord = computed(
  () =>
    teamRecords.value.find(
      (record) => record.id === selectedTeamRecordId.value,
    ) ?? null,
)

const playersQuery = useInfiniteQuery({
  queryKey: computed(() =>
    rosterQueryKeys.players.pages(
      teamId.value,
      authEpoch.value,
      selectedTeamRecordId.value,
      PAGE_LIMIT,
    ),
  ),
  enabled: computed(
    () => teamId.value !== null && selectedTeamRecordId.value !== null,
  ),
  initialPageParam: null as string | null,
  queryFn: async ({ pageParam, signal }) => {
    const requestEpoch = authEpoch.value
    const teamRecordId = selectedTeamRecordId.value
    if (teamRecordId === null) {
      throw new Error('選択中のチームがありません')
    }
    const page = await listPlayers(
      {
        cursor: pageParam,
        include_hidden: false,
        limit: PAGE_LIMIT,
        team_record_id: teamRecordId,
      },
      { signal },
    )
    if (authEpoch.value !== requestEpoch) {
      throw new ApiStaleAuthError('GET', '/players')
    }
    return page
  },
  getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
})

const players = computed<PlayerRead[]>(
  () => playersQuery.data.value?.pages.flatMap((page) => page.items) ?? [],
)

function selectTeam(recordId: string): void {
  selectedTeamRecordId.value = recordId
}

function loadMoreTeamRecords(): void {
  void teamRecordsQuery.fetchNextPage()
}

function retryTeamRecords(): void {
  if (teamRecordsQuery.isFetchNextPageError.value) {
    void teamRecordsQuery.fetchNextPage()
    return
  }
  void teamRecordsQuery.refetch()
}

function loadMorePlayers(): void {
  void playersQuery.fetchNextPage()
}

function retryPlayers(): void {
  if (playersQuery.isFetchNextPageError.value) {
    void playersQuery.fetchNextPage()
    return
  }
  void playersQuery.refetch()
}

function listErrorMessage(error: unknown, target: string): string {
  if (error instanceof ApiStaleAuthError) {
    return '認証が切り替わったため、古い一覧の応答を破棄しました。'
  }
  if (error instanceof ApiNetworkError) {
    return `${target}を取得できませんでした。通信状態を確認してください。`
  }
  return `${target}を取得できませんでした。時間をおいて再試行してください。`
}

function throwingLabel(value: PlayerRead['throws']): string {
  if (value === 'right') return '右投'
  if (value === 'left') return '左投'
  return '投球未設定'
}

function battingLabel(value: PlayerRead['bats']): string {
  if (value === 'right') return '右打'
  if (value === 'left') return '左打'
  if (value === 'both') return '両打'
  return '打席未設定'
}
</script>

<template>
  <div class="mx-auto max-w-6xl p-4 pb-12">
    <header class="mb-6">
      <p class="text-sm font-bold text-sky-700 dark:text-sky-300">
        {{ teamName ?? 'チーム未選択' }}
      </p>
      <h1 class="text-2xl font-extrabold">チーム・選手</h1>
    </header>

    <p
      v-if="teamId === null"
      class="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-semibold text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-100"
      role="status"
    >
      認証済みチーム情報の確認待ちです。
    </p>

    <div v-else class="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <section
        class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
        aria-labelledby="team-records-heading"
      >
        <h2 id="team-records-heading" class="font-extrabold">チーム</h2>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          自チームと登録済みの対戦相手
        </p>

        <p
          v-if="teamRecordsQuery.isPending.value"
          class="mt-4 text-sm text-slate-500"
          role="status"
        >
          チームを読み込んでいます。
        </p>
        <div
          v-else-if="teamRecordsQuery.isError.value && teamRecords.length === 0"
          class="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200"
          role="alert"
        >
          <p>
            {{ listErrorMessage(teamRecordsQuery.error.value, 'チーム一覧') }}
          </p>
          <Button class="mt-3" @click="retryTeamRecords">再試行</Button>
        </div>
        <p
          v-else-if="teamRecords.length === 0"
          class="mt-4 text-sm text-slate-500"
          role="status"
        >
          表示できるチームがありません。
        </p>
        <ul v-else class="mt-4 space-y-2" data-testid="team-record-list">
          <li v-for="record in teamRecords" :key="record.id">
            <button
              type="button"
              class="w-full rounded-xl border px-3 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
              :class="
                record.id === selectedTeamRecordId
                  ? 'border-sky-500 bg-sky-50 text-sky-950 dark:bg-sky-950/50 dark:text-sky-100'
                  : 'border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800'
              "
              :aria-pressed="record.id === selectedTeamRecordId"
              @click="selectTeam(record.id)"
            >
              <span class="block font-bold">{{ record.name }}</span>
              <span class="text-xs text-slate-500 dark:text-slate-400">
                {{ record.kind === 'self' ? '自チーム' : '対戦相手' }}
              </span>
            </button>
          </li>
        </ul>

        <div
          v-if="teamRecordsQuery.isFetchNextPageError.value"
          class="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200"
          role="alert"
        >
          <p>
            {{ listErrorMessage(teamRecordsQuery.error.value, '次のチーム') }}
          </p>
          <Button class="mt-2" @click="retryTeamRecords">再試行</Button>
        </div>
        <Button
          v-else-if="teamRecordsQuery.hasNextPage.value"
          class="mt-3 w-full"
          aria-label="チームをさらに読み込む"
          :disabled="teamRecordsQuery.isFetchingNextPage.value"
          @click="loadMoreTeamRecords"
        >
          {{
            teamRecordsQuery.isFetchingNextPage.value
              ? '読み込み中'
              : 'さらに表示'
          }}
        </Button>
      </section>

      <section
        class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
        aria-labelledby="players-heading"
      >
        <h2 id="players-heading" class="font-extrabold">
          {{ selectedTeamRecord?.name ?? '選手' }}
        </h2>
        <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
          登録済み選手
        </p>

        <p
          v-if="selectedTeamRecordId === null"
          class="mt-4 text-sm text-slate-500"
          role="status"
        >
          チームを選択してください。
        </p>
        <p
          v-else-if="playersQuery.isPending.value"
          class="mt-4 text-sm text-slate-500"
          role="status"
        >
          選手を読み込んでいます。
        </p>
        <div
          v-else-if="playersQuery.isError.value && players.length === 0"
          class="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200"
          role="alert"
        >
          <p>{{ listErrorMessage(playersQuery.error.value, '選手一覧') }}</p>
          <Button class="mt-3" @click="retryPlayers">再試行</Button>
        </div>
        <p
          v-else-if="players.length === 0"
          class="mt-4 text-sm text-slate-500"
          role="status"
        >
          登録済みの選手はいません。
        </p>
        <div v-else class="mt-4 overflow-x-auto">
          <table class="w-full min-w-[32rem] text-left text-sm">
            <thead class="border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th class="px-3 py-2">背番号</th>
                <th class="px-3 py-2">選手名</th>
                <th class="px-3 py-2">投打</th>
                <th class="px-3 py-2">在籍</th>
              </tr>
            </thead>
            <tbody data-testid="player-list">
              <tr
                v-for="player in players"
                :key="player.id"
                class="border-b border-slate-100 dark:border-slate-800"
              >
                <td class="px-3 py-3">{{ player.uniform_number ?? '—' }}</td>
                <td class="px-3 py-3 font-bold">{{ player.name }}</td>
                <td class="px-3 py-3">
                  {{ throwingLabel(player.throws) }}・{{
                    battingLabel(player.bats)
                  }}
                </td>
                <td class="px-3 py-3">
                  {{ player.roster_label_key ?? player.roster_status_key }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          v-if="playersQuery.isFetchNextPageError.value"
          class="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200"
          role="alert"
        >
          <p>{{ listErrorMessage(playersQuery.error.value, '次の選手') }}</p>
          <Button class="mt-2" @click="retryPlayers">再試行</Button>
        </div>
        <Button
          v-else-if="playersQuery.hasNextPage.value"
          class="mt-3 w-full"
          aria-label="選手をさらに読み込む"
          :disabled="playersQuery.isFetchingNextPage.value"
          @click="loadMorePlayers"
        >
          {{
            playersQuery.isFetchingNextPage.value ? '読み込み中' : 'さらに表示'
          }}
        </Button>
      </section>
    </div>

    <TeamMembersContent
      v-if="teamId !== null"
      :players="players"
      :selected-team="selectedTeamRecord"
      :team-records="teamRecords"
    />
  </div>
</template>
