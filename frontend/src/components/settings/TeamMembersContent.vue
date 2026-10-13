<script setup lang="ts">
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { storeToRefs } from 'pinia'
import { computed, ref, watch } from 'vue'
import { ApiError, ApiNetworkError, ApiStaleAuthError } from '../../api/client'
import {
  createPlayer,
  createTeamRecord,
  updatePlayer,
  updateTeamRecord,
  type PlayerCreate,
  type PlayerRead,
  type PlayerUpdate,
  type TeamRecordRead,
} from '../../api/roster'
import { rosterQueryKeys } from '../../lib/rosterQueryKeys'
import { useAuthStore } from '../../stores/authStore'
import Button from '../ui/Button.vue'

const props = defineProps<{
  players: readonly PlayerRead[]
  selectedTeam: TeamRecordRead | null
  teamRecords: readonly TeamRecordRead[]
}>()

type TenantScope = {
  authEpoch: number
  teamId: string
}

type PlayerMutationScope = TenantScope & {
  teamRecordId: string
}

const auth = useAuthStore()
const { authEpoch, teamId } = storeToRefs(auth)
const queryClient = useQueryClient()

const opponentName = ref('')
const opponentError = ref<string | null>(null)
const opponentSuccess = ref<string | null>(null)
const similarNames = ref<string[]>([])
const lastCreatedOpponent = ref<TeamRecordRead | null>(null)
const editingOpponentId = ref('')
const editingOpponentName = ref('')

const playerName = ref('')
const playerThrows = ref<PlayerRead['throws'] | ''>('')
const playerBats = ref<PlayerRead['bats'] | ''>('')
const playerUniformNumber = ref('')
const playerError = ref<string | null>(null)
const playerSuccess = ref<string | null>(null)
const sameNumberPlayers = ref<PlayerRead[]>([])
const editingPlayerId = ref('')
const editingPlayerName = ref('')
const editingPlayerThrows = ref<PlayerRead['throws'] | ''>('')
const editingPlayerBats = ref<PlayerRead['bats'] | ''>('')
const editingPlayerUniformNumber = ref('')

const opponents = computed(() =>
  props.teamRecords.filter((record) => record.kind === 'opponent'),
)

function currentTenantScope(): TenantScope | null {
  if (teamId.value === null) return null
  return { authEpoch: authEpoch.value, teamId: teamId.value }
}

function currentPlayerScope(): PlayerMutationScope | null {
  const tenantScope = currentTenantScope()
  if (tenantScope === null || props.selectedTeam === null) return null
  return { ...tenantScope, teamRecordId: props.selectedTeam.id }
}

function isCurrentTenant(scope: TenantScope): boolean {
  return teamId.value === scope.teamId && authEpoch.value === scope.authEpoch
}

function isCurrentPlayer(scope: PlayerMutationScope): boolean {
  return isCurrentTenant(scope) && props.selectedTeam?.id === scope.teamRecordId
}

function normalizeUniformNumber(value: string): string | null {
  const normalized = value.trim()
  return normalized === '' ? null : normalized
}

function mutationErrorMessage(error: unknown, target: string): string {
  if (error instanceof ApiStaleAuthError) {
    return '認証が切り替わったため結果は未確認です。自動再送せず、送信元チームへ戻って一覧を再読込してください。'
  }
  if (error instanceof ApiNetworkError) {
    return `${target}の通信結果を確認できませんでした。自動再送はしていません。一覧を再読込して確認してください。`
  }
  if (error instanceof ApiError) {
    if (error.status === 401) return '認証の有効期限が切れました。'
    if (error.status === 404) return `${target}の対象が見つかりません。`
    if (error.status === 422) return '入力内容を確認してください。'
  }
  return `${target}に失敗しました。時間をおいて再試行してください。`
}

function resetPlayerCreateForm(): void {
  playerName.value = ''
  playerThrows.value = ''
  playerBats.value = ''
  playerUniformNumber.value = ''
}

function clearPlayerEdit(): void {
  editingPlayerId.value = ''
  editingPlayerName.value = ''
  editingPlayerThrows.value = ''
  editingPlayerBats.value = ''
  editingPlayerUniformNumber.value = ''
}

function clearOpponentEdit(): void {
  editingOpponentId.value = ''
  editingOpponentName.value = ''
}

function clearTenantUi(): void {
  opponentName.value = ''
  opponentError.value = null
  opponentSuccess.value = null
  similarNames.value = []
  lastCreatedOpponent.value = null
  clearOpponentEdit()
  resetPlayerCreateForm()
  playerError.value = null
  playerSuccess.value = null
  sameNumberPlayers.value = []
  clearPlayerEdit()
}

watch([teamId, authEpoch], clearTenantUi, { flush: 'sync' })

watch(
  () => props.selectedTeam?.id ?? null,
  () => {
    resetPlayerCreateForm()
    playerError.value = null
    playerSuccess.value = null
    sameNumberPlayers.value = []
    clearPlayerEdit()
  },
  { flush: 'sync' },
)

const createOpponentMutation = useMutation({
  retry: false,
  mutationFn: async (variables: { name: string; scope: TenantScope }) => {
    const created = await createTeamRecord({ name: variables.name })
    if (!isCurrentTenant(variables.scope)) {
      throw new ApiStaleAuthError('POST', '/team-records')
    }
    return created
  },
  onSuccess: async (created, variables) => {
    if (!isCurrentTenant(variables.scope)) return
    await queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.teamRecords.all(variables.scope.teamId),
    })
    if (!isCurrentTenant(variables.scope)) return
    opponentName.value = ''
    opponentError.value = null
    opponentSuccess.value = `対戦相手「${created.name}」を登録しました。`
    similarNames.value = [...created.similar_names]
    lastCreatedOpponent.value = created
  },
  onError: (error, variables) => {
    if (!isCurrentTenant(variables.scope)) return
    opponentSuccess.value = null
    similarNames.value = []
    lastCreatedOpponent.value = null
    opponentError.value = mutationErrorMessage(error, '対戦相手の登録')
  },
})

const updateOpponentMutation = useMutation({
  retry: false,
  mutationFn: async (variables: {
    id: string
    name: string
    scope: TenantScope
  }) => {
    const updated = await updateTeamRecord(variables.id, {
      name: variables.name,
    })
    if (!isCurrentTenant(variables.scope)) {
      throw new ApiStaleAuthError('PATCH', `/team-records/${variables.id}`)
    }
    return updated
  },
  onSuccess: async (updated, variables) => {
    if (!isCurrentTenant(variables.scope)) return
    await queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.teamRecords.all(variables.scope.teamId),
    })
    if (!isCurrentTenant(variables.scope)) return
    opponentError.value = null
    opponentSuccess.value = `対戦相手名を「${updated.name}」へ更新しました。`
    similarNames.value = []
    lastCreatedOpponent.value = null
    clearOpponentEdit()
  },
  onError: (error, variables) => {
    if (!isCurrentTenant(variables.scope)) return
    opponentSuccess.value = null
    opponentError.value = mutationErrorMessage(error, '対戦相手名の更新')
  },
})

const createPlayerMutation = useMutation({
  retry: false,
  mutationFn: async (variables: {
    body: PlayerCreate
    scope: PlayerMutationScope
  }) => {
    const created = await createPlayer(variables.body)
    if (!isCurrentPlayer(variables.scope)) {
      throw new ApiStaleAuthError('POST', '/players')
    }
    return created
  },
  onSuccess: async (created, variables) => {
    if (!isCurrentTenant(variables.scope)) return
    await queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.players.all(variables.scope.teamId),
    })
    if (!isCurrentPlayer(variables.scope)) return
    resetPlayerCreateForm()
    playerError.value = null
    playerSuccess.value = `選手「${created.name}」を登録しました。`
    sameNumberPlayers.value = [...created.same_number_players]
  },
  onError: (error, variables) => {
    if (!isCurrentPlayer(variables.scope)) return
    playerSuccess.value = null
    sameNumberPlayers.value = []
    playerError.value = mutationErrorMessage(error, '選手の登録')
  },
})

const updatePlayerMutation = useMutation({
  retry: false,
  mutationFn: async (variables: {
    body: PlayerUpdate
    id: string
    scope: PlayerMutationScope
  }) => {
    const updated = await updatePlayer(variables.id, variables.body)
    if (!isCurrentPlayer(variables.scope)) {
      throw new ApiStaleAuthError('PATCH', `/players/${variables.id}`)
    }
    return updated
  },
  onSuccess: async (updated, variables) => {
    if (!isCurrentTenant(variables.scope)) return
    await queryClient.invalidateQueries({
      queryKey: rosterQueryKeys.players.all(variables.scope.teamId),
    })
    if (!isCurrentPlayer(variables.scope)) return
    playerError.value = null
    playerSuccess.value = `選手「${updated.name}」を更新しました。`
    sameNumberPlayers.value = []
    clearPlayerEdit()
  },
  onError: (error, variables) => {
    if (!isCurrentPlayer(variables.scope)) return
    playerSuccess.value = null
    playerError.value = mutationErrorMessage(error, '選手の更新')
  },
})

const isCreatingOpponent = computed(
  () =>
    createOpponentMutation.isPending.value &&
    createOpponentMutation.variables.value !== undefined &&
    isCurrentTenant(createOpponentMutation.variables.value.scope),
)

const isUpdatingOpponent = computed(
  () =>
    updateOpponentMutation.isPending.value &&
    updateOpponentMutation.variables.value !== undefined &&
    isCurrentTenant(updateOpponentMutation.variables.value.scope),
)

const isCreatingPlayer = computed(
  () =>
    createPlayerMutation.isPending.value &&
    createPlayerMutation.variables.value !== undefined &&
    isCurrentPlayer(createPlayerMutation.variables.value.scope),
)

const isUpdatingPlayer = computed(
  () =>
    updatePlayerMutation.isPending.value &&
    updatePlayerMutation.variables.value !== undefined &&
    isCurrentPlayer(updatePlayerMutation.variables.value.scope),
)

function submitOpponent(): void {
  const scope = currentTenantScope()
  const name = opponentName.value.trim()
  opponentError.value = null
  opponentSuccess.value = null
  similarNames.value = []
  lastCreatedOpponent.value = null
  if (scope === null) return
  if (name === '') {
    opponentError.value = '対戦相手名を入力してください。'
    return
  }
  createOpponentMutation.mutate({ name, scope })
}

function selectOpponentForEdit(id: string): void {
  editingOpponentId.value = id
  const opponent = opponents.value.find((record) => record.id === id)
  editingOpponentName.value = opponent?.name ?? ''
  opponentError.value = null
}

function editLastCreatedOpponent(): void {
  const opponent = lastCreatedOpponent.value
  if (opponent === null) return
  editingOpponentId.value = opponent.id
  editingOpponentName.value = opponent.name
}

function submitOpponentEdit(): void {
  const scope = currentTenantScope()
  const name = editingOpponentName.value.trim()
  opponentError.value = null
  opponentSuccess.value = null
  if (scope === null || editingOpponentId.value === '') return
  const target = opponents.value.find(
    (record) => record.id === editingOpponentId.value,
  )
  const isCreatedWarningTarget =
    lastCreatedOpponent.value?.id === editingOpponentId.value
  if (target?.kind !== 'opponent' && !isCreatedWarningTarget) {
    opponentError.value = '編集できる対戦相手を選択してください。'
    return
  }
  if (name === '') {
    opponentError.value = '対戦相手名を入力してください。'
    return
  }
  updateOpponentMutation.mutate({
    id: editingOpponentId.value,
    name,
    scope,
  })
}

function submitPlayer(): void {
  const scope = currentPlayerScope()
  const name = playerName.value.trim()
  playerError.value = null
  playerSuccess.value = null
  sameNumberPlayers.value = []
  if (scope === null) return
  if (name === '' || playerThrows.value === '' || playerBats.value === '') {
    playerError.value = '選手名、投、打を入力してください。'
    return
  }
  createPlayerMutation.mutate({
    body: {
      bats: playerBats.value,
      name,
      roster_label_key: null,
      roster_status_key: 'active',
      team_record_id: scope.teamRecordId,
      throws: playerThrows.value,
      uniform_number: normalizeUniformNumber(playerUniformNumber.value),
    },
    scope,
  })
}

function selectPlayerForEdit(id: string): void {
  editingPlayerId.value = id
  const selected = props.players.find((player) => player.id === id)
  editingPlayerName.value = selected?.name ?? ''
  editingPlayerThrows.value = selected?.throws ?? ''
  editingPlayerBats.value = selected?.bats ?? ''
  editingPlayerUniformNumber.value = selected?.uniform_number ?? ''
  playerError.value = null
}

function submitPlayerEdit(): void {
  const scope = currentPlayerScope()
  const name = editingPlayerName.value.trim()
  playerError.value = null
  playerSuccess.value = null
  if (scope === null || editingPlayerId.value === '') return
  if (
    !props.players.some((player) => player.id === editingPlayerId.value) ||
    name === '' ||
    editingPlayerThrows.value === '' ||
    editingPlayerBats.value === ''
  ) {
    playerError.value = '編集する選手と、選手名、投、打を確認してください。'
    return
  }
  updatePlayerMutation.mutate({
    body: {
      bats: editingPlayerBats.value,
      name,
      throws: editingPlayerThrows.value,
      uniform_number: normalizeUniformNumber(editingPlayerUniformNumber.value),
    },
    id: editingPlayerId.value,
    scope,
  })
}
</script>

<template>
  <section class="mt-4 grid gap-4 xl:grid-cols-2" aria-label="登録と編集">
    <div
      class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="font-extrabold">対戦相手の管理</h2>
      <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
        現在のチーム内で使う対戦相手を登録します。
      </p>

      <form class="mt-4 space-y-3" @submit.prevent="submitOpponent">
        <label class="block text-sm font-bold">
          対戦相手名
          <input
            v-model="opponentName"
            name="opponent-name"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
            autocomplete="off"
            maxlength="200"
          />
        </label>
        <Button
          variant="primary"
          :disabled="isCreatingOpponent"
          @click="submitOpponent"
        >
          {{ isCreatingOpponent ? '登録中' : '対戦相手を登録' }}
        </Button>
      </form>

      <div class="mt-5 border-t border-slate-200 pt-4 dark:border-slate-700">
        <label class="block text-sm font-bold">
          編集する対戦相手
          <select
            :value="editingOpponentId"
            name="opponent-edit-target"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
            @change="
              selectOpponentForEdit(($event.target as HTMLSelectElement).value)
            "
          >
            <option value="">選択してください</option>
            <option
              v-for="opponent in opponents"
              :key="opponent.id"
              :value="opponent.id"
            >
              {{ opponent.name }}
            </option>
          </select>
        </label>
        <form
          v-if="editingOpponentId !== ''"
          class="mt-3 space-y-3"
          @submit.prevent="submitOpponentEdit"
        >
          <label class="block text-sm font-bold">
            新しい名称
            <input
              v-model="editingOpponentName"
              name="opponent-edit-name"
              class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
              autocomplete="off"
              maxlength="200"
            />
          </label>
          <div class="flex gap-2">
            <Button :disabled="isUpdatingOpponent" @click="submitOpponentEdit">
              名称を保存
            </Button>
            <Button variant="ghost" @click="clearOpponentEdit">取消</Button>
          </div>
        </form>
      </div>

      <p
        v-if="opponentError"
        class="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200"
        role="alert"
      >
        {{ opponentError }}
      </p>
      <div
        v-if="opponentSuccess"
        class="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100"
        role="status"
      >
        <p>{{ opponentSuccess }}</p>
        <div v-if="similarNames.length > 0" class="mt-2">
          <p class="font-bold">類似する登録済み名称があります。</p>
          <ul class="list-disc pl-5">
            <li v-for="name in similarNames" :key="name">{{ name }}</li>
          </ul>
          <Button class="mt-2" variant="ghost" @click="editLastCreatedOpponent">
            登録した対戦相手名を編集
          </Button>
        </div>
      </div>
    </div>

    <div
      class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="font-extrabold">
        {{ selectedTeam?.name ?? 'チーム未選択' }}の選手管理
      </h2>
      <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
        在籍区分とラベルはこの画面では変更しません。
      </p>

      <form
        class="mt-4 grid gap-3 sm:grid-cols-2"
        @submit.prevent="submitPlayer"
      >
        <label class="block text-sm font-bold sm:col-span-2">
          選手名
          <input
            v-model="playerName"
            name="player-name"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
            autocomplete="off"
            maxlength="200"
          />
        </label>
        <label class="block text-sm font-bold">
          投
          <select
            v-model="playerThrows"
            name="player-throws"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
          >
            <option value="">選択してください</option>
            <option value="right">右投</option>
            <option value="left">左投</option>
          </select>
        </label>
        <label class="block text-sm font-bold">
          打
          <select
            v-model="playerBats"
            name="player-bats"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
          >
            <option value="">選択してください</option>
            <option value="right">右打</option>
            <option value="left">左打</option>
            <option value="both">両打</option>
          </select>
        </label>
        <label class="block text-sm font-bold sm:col-span-2">
          背番号（任意）
          <input
            v-model="playerUniformNumber"
            name="player-uniform-number"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
            autocomplete="off"
            maxlength="20"
          />
        </label>
        <Button
          class="sm:col-span-2"
          variant="primary"
          :disabled="selectedTeam === null || isCreatingPlayer"
          @click="submitPlayer"
        >
          {{ isCreatingPlayer ? '登録中' : '選手を登録' }}
        </Button>
      </form>

      <div class="mt-5 border-t border-slate-200 pt-4 dark:border-slate-700">
        <label class="block text-sm font-bold">
          編集する選手
          <select
            :value="editingPlayerId"
            name="player-edit-target"
            class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
            @change="
              selectPlayerForEdit(($event.target as HTMLSelectElement).value)
            "
          >
            <option value="">選択してください</option>
            <option
              v-for="player in players"
              :key="player.id"
              :value="player.id"
            >
              {{ player.uniform_number ?? '—' }} {{ player.name }}
            </option>
          </select>
        </label>
        <form
          v-if="editingPlayerId !== ''"
          class="mt-3 grid gap-3 sm:grid-cols-2"
          @submit.prevent="submitPlayerEdit"
        >
          <label class="block text-sm font-bold sm:col-span-2">
            選手名
            <input
              v-model="editingPlayerName"
              name="player-edit-name"
              class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
              autocomplete="off"
              maxlength="200"
            />
          </label>
          <label class="block text-sm font-bold">
            投
            <select
              v-model="editingPlayerThrows"
              name="player-edit-throws"
              class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
            >
              <option value="">選択してください</option>
              <option value="right">右投</option>
              <option value="left">左投</option>
            </select>
          </label>
          <label class="block text-sm font-bold">
            打
            <select
              v-model="editingPlayerBats"
              name="player-edit-bats"
              class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
            >
              <option value="">選択してください</option>
              <option value="right">右打</option>
              <option value="left">左打</option>
              <option value="both">両打</option>
            </select>
          </label>
          <label class="block text-sm font-bold sm:col-span-2">
            背番号（任意）
            <input
              v-model="editingPlayerUniformNumber"
              name="player-edit-uniform-number"
              class="mt-1 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-600 dark:bg-slate-800"
              autocomplete="off"
              maxlength="20"
            />
          </label>
          <div class="flex gap-2 sm:col-span-2">
            <Button :disabled="isUpdatingPlayer" @click="submitPlayerEdit">
              選手情報を保存
            </Button>
            <Button variant="ghost" @click="clearPlayerEdit">取消</Button>
          </div>
        </form>
      </div>

      <p
        v-if="playerError"
        class="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200"
        role="alert"
      >
        {{ playerError }}
      </p>
      <div
        v-if="playerSuccess"
        class="mt-3 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-100"
        role="status"
      >
        <p>{{ playerSuccess }}</p>
        <div v-if="sameNumberPlayers.length > 0" class="mt-2">
          <p class="font-bold">同じ背番号の在籍選手がいます。</p>
          <ul class="list-disc pl-5">
            <li v-for="player in sameNumberPlayers" :key="player.id">
              {{ player.uniform_number ?? '—' }} {{ player.name }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>
