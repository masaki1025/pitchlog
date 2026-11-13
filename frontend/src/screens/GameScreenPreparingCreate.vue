<script setup lang="ts">
import { computed, reactive, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { GameChoice, GameTypeKey, PreparingGameCreate } from '../api/games'
import type { TeamRecordRead } from '../api/roster'
import { pinia } from '../appProviders'
import { useAuthStore } from '../stores/authStore'
import { usePreparingCreateProvider } from './GameScreenPreparingCreateProvider'

const emit = defineEmits<{ close: []; inspect: [] }>()
const auth = useAuthStore(pinia),
  route = useRoute()
const provider = usePreparingCreateProvider()
const {
  status,
  choices,
  created,
  message,
  online,
  canPreviousOptions,
  canPreviousTeams,
} = provider
const initial = () => ({
  scheduled_at: '',
  game_type_key: '' as GameTypeKey | '',
  away_team_record_id: '',
  home_team_record_id: '',
  tournament_kind: 'existing' as 'existing' | 'new',
  tournament_key: '',
  display_name: '',
  rule_mode: 'default' as 'default' | 'custom',
  regulation_innings: 9,
  extension_limit: 9,
  plate_umpire: '',
  section_label: '',
  week_label: '',
  day_label: '',
  game_number_label: '',
})
const draft = reactive(initial())
const selectedAway = shallowRef<TeamRecordRead | null>(null)
const selectedHome = shallowRef<TeamRecordRead | null>(null)
const selectedTournament = shallowRef<GameChoice | null>(null)
const teams = computed(() => {
  const page = choices.value
  if (!page) return []
  return [
    ...new Map(
      [
        page.self,
        ...page.opponents.items,
        selectedAway.value,
        selectedHome.value,
      ]
        .filter((team): team is TeamRecordRead => team !== null)
        .map((team) => [team.id, team]),
    ).values(),
  ]
})
const extensionOptions = computed(() =>
  draft.regulation_innings === 7
    ? ([
        { value: 7, label: '延長なし（7回で引き分け）' },
        { value: 9, label: '9回まで' },
        { value: 12, label: '12回まで' },
      ] as const)
    : ([
        { value: 9, label: '延長なし（9回で引き分け）' },
        { value: 12, label: '12回まで' },
      ] as const),
)
const tournaments = computed(() => [
  ...new Map(
    [
      ...(choices.value?.options.tournaments.items ?? []),
      selectedTournament.value,
    ]
      .filter((item): item is GameChoice => item !== null)
      .map((item) => [item.key, item]),
  ).values(),
])
watch(
  () => draft.away_team_record_id,
  (id) => {
    selectedAway.value = teams.value.find((team) => team.id === id) ?? null
  },
)
watch(
  () => draft.home_team_record_id,
  (id) => {
    selectedHome.value = teams.value.find((team) => team.id === id) ?? null
  },
)
watch(
  () => draft.tournament_key,
  (key) => {
    selectedTournament.value =
      tournaments.value.find((item) => item.key === key) ?? null
  },
)
watch(
  () => draft.regulation_innings,
  () => {
    if (
      !extensionOptions.value.some(
        (item) => item.value === draft.extension_limit,
      )
    )
      draft.extension_limit = draft.regulation_innings
  },
)
watch(
  () => [auth.teamId, auth.authEpoch, route.path],
  () => {
    Object.assign(draft, initial())
    selectedAway.value = selectedHome.value = null
    selectedTournament.value = null
  },
  { flush: 'sync' },
)
const valid = computed(
  () =>
    status.value === 'ready' &&
    online.value &&
    choices.value !== null &&
    /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(draft.scheduled_at) &&
    Number.isFinite(Date.parse(`${draft.scheduled_at}:00+09:00`)) &&
    choices.value.options.game_types.some(
      (item) => item.key === draft.game_type_key,
    ) &&
    teams.value.some((team) => team.id === draft.away_team_record_id) &&
    teams.value.some((team) => team.id === draft.home_team_record_id) &&
    (draft.tournament_kind === 'new'
      ? draft.display_name.trim().length > 0
      : tournaments.value.some((item) => item.key === draft.tournament_key)) &&
    (draft.rule_mode === 'default' ||
      extensionOptions.value.some(
        (item) => item.value === draft.extension_limit,
      )),
)
function ruleChoice(): PreparingGameCreate['rule_choice'] {
  if (draft.rule_mode !== 'custom') return undefined
  const regulation = draft.regulation_innings
  const extension = draft.extension_limit
  if (regulation !== 7 && regulation !== 9) return undefined
  if (extension !== 7 && extension !== 9 && extension !== 12) return undefined
  return {
    regulation_innings: regulation,
    extension_limit: extension,
  }
}
function submit() {
  if (!valid.value) return
  const choice = ruleChoice()
  const body: PreparingGameCreate = {
    scheduled_at: `${draft.scheduled_at}:00+09:00`,
    game_type_key: draft.game_type_key as GameTypeKey,
    away_team_record_id: draft.away_team_record_id,
    home_team_record_id: draft.home_team_record_id,
    tournament:
      draft.tournament_kind === 'new'
        ? { kind: 'new', display_name: draft.display_name }
        : { kind: 'existing', key: draft.tournament_key },
    plate_umpire: draft.plate_umpire,
    section_label: draft.section_label,
    week_label: draft.week_label,
    day_label: draft.day_label,
    game_number_label: draft.game_number_label,
  }
  if (choice !== undefined) body.rule_choice = choice
  void provider.submit(body)
}
</script>

<template>
  <section
    aria-label="試合の新規作成"
    class="mx-auto max-w-4xl space-y-3 rounded-2xl border p-4"
  >
    <h2 class="text-lg font-bold">試合の新規作成</h2>
    <p>日時は日本時間です。作成後も準備中のままで、試合は開始しません。</p>
    <p v-if="!online" role="status">新規作成にはオンライン接続が必要です。</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="status === 'loading'" role="status">選択肢を取得しています</p>
    <button v-if="status === 'failed'" type="button" @click="provider.load">
      選択肢を再取得
    </button>
    <form @submit.prevent="submit">
      <fieldset :disabled="status !== 'ready' || !online" class="grid gap-3">
        <label
          >日時（日本時間）<input
            v-model="draft.scheduled_at"
            data-testid="scheduled"
            type="datetime-local"
            required
        /></label>
        <label
          >試合区分<select
            v-model="draft.game_type_key"
            data-testid="game-type"
            required
          >
            <option value="" disabled>選択してください</option>
            <option
              v-for="item in choices?.options.game_types ?? []"
              :key="item.key"
              :value="item.key"
            >
              {{ item.display_name }}
            </option>
          </select></label
        >
        <label
          >適用する規則<select
            v-model="draft.rule_mode"
            data-testid="rule-mode"
          >
            <option value="default">試合区分の既定規則を使う</option>
            <option value="custom">規定回と延長上限を選ぶ</option>
          </select></label
        >
        <template v-if="draft.rule_mode === 'custom'">
          <label
            >規定回<select
              v-model.number="draft.regulation_innings"
              data-testid="regulation-innings"
            >
              <option :value="7">7回</option>
              <option :value="9">9回</option>
            </select></label
          >
          <label
            >延長<select
              v-model.number="draft.extension_limit"
              data-testid="extension-limit"
            >
              <option
                v-for="item in extensionOptions"
                :key="item.value"
                :value="item.value"
              >
                {{ item.label }}
              </option>
            </select></label
          >
        </template>
        <label
          >先攻チーム<select
            v-model="draft.away_team_record_id"
            data-testid="away"
            required
          >
            <option value="" disabled>選択してください</option>
            <option v-for="team in teams" :key="team.id" :value="team.id">
              {{ team.name }}（{{
                team.kind === 'self' ? '自チーム' : '対戦相手'
              }}・{{ team.id }}）
            </option>
          </select></label
        >
        <label
          >後攻チーム<select
            v-model="draft.home_team_record_id"
            data-testid="home"
            required
          >
            <option value="" disabled>選択してください</option>
            <option v-for="team in teams" :key="team.id" :value="team.id">
              {{ team.name }}（{{
                team.kind === 'self' ? '自チーム' : '対戦相手'
              }}・{{ team.id }}）
            </option>
          </select></label
        >
        <div>
          <button
            type="button"
            :disabled="!canPreviousTeams"
            @click="provider.page('teams', 'previous')"
          >
            前の対戦相手
          </button>
          <button
            type="button"
            :disabled="!choices?.opponents.next_cursor"
            @click="provider.page('teams', 'next')"
          >
            次の対戦相手
          </button>
        </div>
        <label
          >大会の指定<select
            v-model="draft.tournament_kind"
            data-testid="tournament-kind"
          >
            <option value="existing">登録済みの大会を選ぶ</option>
            <option value="new">新しい大会名を登録する</option>
          </select></label
        >
        <template v-if="draft.tournament_kind === 'existing'">
          <label
            >大会<select
              v-model="draft.tournament_key"
              data-testid="tournament"
              required
            >
              <option value="" disabled>選択してください</option>
              <option
                v-for="item in tournaments"
                :key="item.key"
                :value="item.key"
              >
                {{ item.display_name }}（{{ item.key }}）
              </option>
            </select></label
          >
          <div>
            <button
              type="button"
              :disabled="!canPreviousOptions"
              @click="provider.page('options', 'previous')"
            >
              前の大会
            </button>
            <button
              type="button"
              :disabled="!choices?.options.tournaments.next_cursor"
              @click="provider.page('options', 'next')"
            >
              次の大会
            </button>
          </div>
        </template>
        <label v-else
          >新しい大会名<input
            v-model="draft.display_name"
            data-testid="tournament-name"
            type="text"
            required
        /></label>
        <label
          >主審（任意）<input
            v-model="draft.plate_umpire"
            data-testid="umpire"
            type="text"
        /></label>
        <label
          >節（任意）<input
            v-model="draft.section_label"
            data-testid="section"
            type="text"
        /></label>
        <label
          >週（任意）<input
            v-model="draft.week_label"
            data-testid="week"
            type="text"
        /></label>
        <label
          >日（任意）<input
            v-model="draft.day_label"
            data-testid="day"
            type="text"
        /></label>
        <label
          >試合番号（任意）<input
            v-model="draft.game_number_label"
            data-testid="number"
            type="text"
        /></label>
        <button type="submit" data-testid="create-submit" :disabled="!valid">
          準備中の試合を作成
        </button>
      </fieldset>
    </form>
    <p v-if="created">作成応答の試合ID：{{ created.id }}</p>
    <button
      v-if="status === 'created' || status === 'confirming'"
      type="button"
      :disabled="status !== 'created' || !online"
      @click="provider.confirmCreated"
    >
      作成した試合IDの保存値を確認
    </button>
    <button v-if="status === 'unknown'" type="button" @click="emit('inspect')">
      一覧で保存結果を確認
    </button>
    <button
      type="button"
      :disabled="
        status === 'sending' || status === 'confirming' || status === 'unknown'
      "
      @click="emit('close')"
    >
      作成入力を閉じる
    </button>
  </section>
</template>
