<script setup lang="ts">
import { computed } from 'vue'
import { safeLiveSources } from './GameScreenLiveDisplayShape'
import type {
  BatterDay,
  BatterSeason,
  DisplaySupply,
  GameFlow,
  InningCell,
  LiveDisplaySources,
  LiveIdentity,
} from './GameScreenLiveDisplayTypes'

const props = defineProps<{
  identity?: LiveIdentity | null
  sources?: LiveDisplaySources | null
}>()
const sources = computed(() => safeLiveSources(props.sources))

function matches<T>(supply: DisplaySupply<T> | undefined, playerId?: string) {
  const identity = props.identity
  return !!(
    identity &&
    supply &&
    typeof identity.scopeKey === 'string' &&
    identity.scopeKey !== '' &&
    typeof identity.contextKey === 'string' &&
    identity.contextKey !== '' &&
    supply.scopeKey === identity.scopeKey &&
    supply.contextKey === identity.contextKey &&
    ((supply.playerId === undefined && playerId === undefined) ||
      (typeof playerId === 'string' &&
        !!playerId &&
        supply.playerId === playerId))
  )
}

function ready<T>(
  supply: DisplaySupply<T> | undefined,
  playerId?: string,
): T | null {
  return matches(supply, playerId) &&
    supply?.status === 'ready' &&
    supply.value !== undefined &&
    supply.value !== null
    ? supply.value
    : null
}

function status<T>(
  supply: DisplaySupply<T> | undefined,
  playerId?: string,
): string {
  if (!matches(supply, playerId)) return '未取得'
  if (supply?.status === 'read-failed') return '読取失敗'
  if (supply?.status === 'empty') return 'データなし'
  if (
    supply?.status === 'ready' &&
    supply.value !== undefined &&
    supply.value !== null
  )
    return ''
  return '未取得'
}

function shown(value: string | null | undefined): string {
  return typeof value === 'string' ? value : '未取得'
}

function cell(value: InningCell | undefined): string {
  if (value?.kind === 'blank') return ''
  if (value?.kind === 'text') return value.text
  return '未取得'
}

function provisional<T>(
  supply: DisplaySupply<T> | undefined,
  playerId?: string,
): boolean {
  return ready(supply, playerId) !== null && supply?.provisional === true
}

function seasonNote<T>(
  supply: DisplaySupply<T> | undefined,
  playerId?: string,
): string {
  if (!matches(supply, playerId)) return '最終取得: 未取得 / オフライン: 未取得'
  const fetched =
    typeof supply?.fetchedAt === 'string' && supply.fetchedAt !== ''
      ? supply.fetchedAt
      : '未取得'
  const offline =
    supply?.offline === true
      ? 'オフライン'
      : supply?.offline === false
        ? 'オンライン'
        : '未取得'
  return `最終取得: ${fetched} / ${offline}`
}

const score = computed(() => ready(sources.value.scoreboard))
const pitcherId = computed(() => props.identity?.pitcherId ?? '')
const pitcherDay = computed(() =>
  ready(sources.value.pitcherDay, pitcherId.value),
)
const pitcherSeason = computed(() =>
  ready(sources.value.pitcherSeason, pitcherId.value),
)
const pitcherDayFields = computed(() => {
  const day = pitcherDay.value
  return [
    ['当日投球数', day?.pitchCount],
    ['投球回', day?.inningsPitched],
    ['最速球速', day?.fastestSpeed],
    ['平均球速', day?.averageSpeed],
    ['被安打', day?.hitsAllowed],
    ['奪三振', day?.strikeouts],
    ['与四球', day?.walks],
    ['失点', day?.runsAllowed],
  ] as const satisfies readonly (readonly [string, string | null | undefined])[]
})
const pitcherSeasonFields = computed(() => {
  const season = pitcherSeason.value
  return [
    ['対左被打率', season?.vsLeftAverage],
    ['対右被打率', season?.vsRightAverage],
    ['投球回', season?.inningsPitched],
    ['WHIP', season?.whip],
    ['FIP', season?.fip],
  ] as const satisfies readonly (readonly [string, string | null | undefined])[]
})

function batterDayFields(day: BatterDay | null) {
  return [
    ['打席数', day?.plateAppearances],
    ['打数', day?.atBats],
    ['安打', day?.hits],
    ['打点', day?.rbi],
    ['四球', day?.walks],
    ['死球', day?.hitByPitch],
    ['三振', day?.strikeouts],
    ['犠打', day?.sacrificeBunts],
    ['犠飛', day?.sacrificeFlies],
  ] as const satisfies readonly (readonly [string, string | null | undefined])[]
}
function batterSeasonFields(season: BatterSeason | null) {
  return [
    ['対左打率', season?.vsLeftAverage],
    ['対右打率', season?.vsRightAverage],
    ['本塁打', season?.homeRuns],
  ] as const satisfies readonly (readonly [string, string | null | undefined])[]
}
const batters = computed(() => {
  const supplied = sources.value
  const identity = props.identity
  return [
    {
      slot: 'current',
      title: '現在打者',
      id: identity?.currentBatterId ?? '',
      name: identity?.currentBatterName,
      day: supplied.currentBatterDay,
      season: supplied.currentBatterSeason,
      history: supplied.currentBatterHistory,
    },
    {
      slot: 'next',
      title: '次打者',
      id: identity?.nextBatterId ?? '',
      name: identity?.nextBatterName,
      day: supplied.nextBatterDay,
      season: supplied.nextBatterSeason,
      history: supplied.nextBatterHistory,
    },
  ] as const
})

const flow = computed(() => ready(sources.value.flow))
const endLabels: Record<GameFlow['endState'], string> = {
  undetected: '終了未検知',
  detected: '終了候補を検知（未宣言）',
  'declared-unsynced': '終了宣言済み・未同期',
  'declared-synced': '終了宣言済み・同期確認済み',
  reopened: '試合追記再開中',
  'reclosed-unsynced': '再終了宣言済み・未同期',
  'reclosed-synced': '再終了宣言済み・同期確認済み',
}
function endText(value: GameFlow | null): string {
  const state: unknown = value?.endState
  return typeof state === 'string' && Object.hasOwn(endLabels, state)
    ? endLabels[state as GameFlow['endState']]
    : '未取得'
}
function offered(value: boolean | null | undefined): string {
  return value === true ? 'あり' : value === false ? 'なし' : '未取得'
}
const inputOfflineText = computed(() => {
  const supplied = sources.value.inputOffline
  const value = ready(supplied)
  return value === true
    ? 'オフライン'
    : value === false
      ? 'オンライン'
      : status(supplied)
})
</script>

<template>
  <div class="min-w-0 space-y-5 wrap-anywhere" data-testid="live-display">
    <section
      aria-label="イニング別得点"
      class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="text-lg font-extrabold">イニング別得点</h2>
      <p v-if="!score" data-testid="score-status">
        {{ status(sources.scoreboard) }}
      </p>
      <template v-else>
        <div
          class="mt-3 flex min-w-0 flex-wrap gap-2"
          data-testid="inning-list"
        >
          <div
            v-for="inning in score.innings"
            :key="inning.key"
            class="min-w-0 w-full rounded-lg border p-3 sm:w-32"
            data-testid="inning-card"
          >
            <h3 class="font-bold">{{ shown(inning.label) }}</h3>
            <dl class="grid min-w-0 grid-cols-2 gap-2 text-sm">
              <div
                v-for="(team, index) in score.teams"
                :key="index"
                class="min-w-0"
              >
                <dt>{{ shown(team.name) }}</dt>
                <dd
                  class="font-bold"
                  :data-testid="`inning-${inning.key}-${index}`"
                  :aria-label="
                    inning.cells[index]?.kind === 'blank' ? '空欄' : undefined
                  "
                >
                  {{ cell(inning.cells[index]) }}
                </dd>
              </div>
            </dl>
          </div>
        </div>
        <div class="mt-3 grid min-w-0 gap-2 sm:grid-cols-2">
          <div
            v-for="(team, index) in score.teams"
            :key="index"
            class="min-w-0 rounded-lg bg-slate-50 p-3 dark:bg-slate-800"
            :data-testid="`team-${index}`"
          >
            <h3 class="font-bold">{{ shown(team.name) }}</h3>
            <dl class="grid min-w-0 grid-cols-5 gap-1 text-center text-sm">
              <div
                v-for="item in [
                  ['合計', team.total],
                  ['H', team.h],
                  ['E', team.e],
                  ['K', team.k],
                  ['B', team.b],
                ]"
                :key="item[0]"
                class="min-w-0"
              >
                <dt>{{ item[0] }}</dt>
                <dd class="font-bold">{{ shown(item[1]) }}</dd>
              </div>
            </dl>
          </div>
        </div>
        <p
          v-if="provisional(sources.scoreboard)"
          class="mt-2 text-amber-800"
          data-testid="score-provisional"
        >
          当日表示は暫定
        </p>
      </template>
    </section>

    <section
      aria-label="現投手の成績"
      class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="text-lg font-extrabold">
        現投手: {{ shown(props.identity?.pitcherName) }}
      </h2>
      <h3 class="mt-3 font-bold">当日</h3>
      <p data-testid="pitcher-day-status">
        {{ status(sources.pitcherDay, pitcherId) }}
      </p>
      <p
        v-if="provisional(sources.pitcherDay, pitcherId)"
        data-testid="pitcher-day-provisional"
      >
        当日表示は暫定
      </p>
      <dl class="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-4">
        <div
          v-for="[label, value] in pitcherDayFields"
          :key="label"
          class="min-w-0 rounded-lg bg-slate-50 p-2 dark:bg-slate-800"
        >
          <dt class="text-sm">{{ label }}</dt>
          <dd class="font-bold">{{ shown(value) }}</dd>
        </div>
      </dl>
      <h3 class="mt-3 font-bold">シーズン</h3>
      <p data-testid="pitcher-season-status">
        {{ status(sources.pitcherSeason, pitcherId) }}
      </p>
      <p data-testid="pitcher-season-note">
        {{ seasonNote(sources.pitcherSeason, pitcherId) }}
      </p>
      <dl class="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-5">
        <div
          v-for="[label, value] in pitcherSeasonFields"
          :key="label"
          class="min-w-0 rounded-lg bg-slate-50 p-2 dark:bg-slate-800"
        >
          <dt class="text-sm">{{ label }}</dt>
          <dd class="font-bold">{{ shown(value) }}</dd>
        </div>
      </dl>
    </section>

    <section
      v-for="batter in batters"
      :key="batter.slot"
      :aria-label="`${batter.title}の成績`"
      class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
      :data-testid="`${batter.slot}-batter`"
    >
      <h2 class="text-lg font-extrabold">
        {{ batter.title }}: {{ shown(batter.name) }}
      </h2>
      <h3 class="mt-3 font-bold">当日</h3>
      <p :data-testid="`${batter.slot}-day-status`">
        {{ status(batter.day, batter.id) }}
      </p>
      <p v-if="provisional(batter.day, batter.id)">当日表示は暫定</p>
      <dl class="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3">
        <div
          v-for="[label, value] in batterDayFields(
            ready(batter.day, batter.id),
          )"
          :key="label"
          class="min-w-0 rounded-lg bg-slate-50 p-2 dark:bg-slate-800"
        >
          <dt class="text-sm">{{ label }}</dt>
          <dd class="font-bold">{{ shown(value) }}</dd>
        </div>
      </dl>
      <h3 class="mt-3 font-bold">シーズン</h3>
      <p :data-testid="`${batter.slot}-season-status`">
        {{ status(batter.season, batter.id) }}
      </p>
      <p :data-testid="`${batter.slot}-season-note`">
        {{ seasonNote(batter.season, batter.id) }}
      </p>
      <dl class="grid min-w-0 grid-cols-2 gap-2 sm:grid-cols-3">
        <div
          v-for="[label, value] in batterSeasonFields(
            ready(batter.season, batter.id),
          )"
          :key="label"
          class="min-w-0 rounded-lg bg-slate-50 p-2 dark:bg-slate-800"
        >
          <dt class="text-sm">{{ label }}</dt>
          <dd class="font-bold">{{ shown(value) }}</dd>
        </div>
      </dl>
      <h3 class="mt-3 font-bold">打席ごとの記録</h3>
      <p :data-testid="`${batter.slot}-history-status`">
        {{ status(batter.history, batter.id) }}
      </p>
      <div
        class="mt-2 grid min-w-0 gap-2"
        :data-testid="`${batter.slot}-history`"
      >
        <dl
          v-for="row in ready(batter.history, batter.id) ?? []"
          :key="row.key"
          class="grid min-w-0 grid-cols-2 gap-2 rounded-lg border p-2 sm:grid-cols-4"
          data-testid="plate-row"
        >
          <div
            v-for="[label, value] in [
              ['番号', row.number],
              ['イニング', row.inning],
              ['結果表示名', row.resultName],
              ['打数算入', row.atBat],
              ['安打種別', row.hitType],
              ['打点', row.rbi],
              ['出塁別', row.onBaseType],
            ]"
            :key="label"
            class="min-w-0"
          >
            <dt class="text-sm">{{ label }}</dt>
            <dd class="font-bold">{{ shown(value) }}</dd>
          </div>
        </dl>
      </div>
    </section>

    <section
      aria-label="当日の球種"
      class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="text-lg font-extrabold">当日の球種</h2>
      <p data-testid="pitch-types-status">
        {{ status(sources.pitchTypes) }}
      </p>
      <p
        v-if="provisional(sources.pitchTypes)"
        data-testid="pitch-types-provisional"
      >
        当日表示は暫定
      </p>
      <dl class="grid min-w-0 gap-2 sm:grid-cols-2">
        <div
          v-for="pitch in ready(sources.pitchTypes) ?? []"
          :key="pitch.key"
          class="min-w-0 rounded-lg bg-slate-50 p-2 dark:bg-slate-800"
          data-testid="pitch-type-share"
        >
          <dt class="font-bold">{{ shown(pitch.name) }}</dt>
          <dd>割合 {{ shown(pitch.share) }} / 球数 {{ shown(pitch.count) }}</dd>
        </div>
      </dl>
    </section>

    <section
      aria-label="回・打順・終了と鮮度"
      class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="text-lg font-extrabold">回・打順・終了と鮮度</h2>
      <p data-testid="flow-status">{{ status(sources.flow) }}</p>
      <dl class="grid min-w-0 grid-cols-2 gap-2">
        <div>
          <dt>回</dt>
          <dd data-testid="flow-inning">{{ shown(flow?.inning) }}</dd>
        </div>
        <div>
          <dt>打順</dt>
          <dd data-testid="flow-order">{{ shown(flow?.battingOrder) }}</dd>
        </div>
        <div>
          <dt>終了状態</dt>
          <dd data-testid="end-state">
            {{ endText(flow) }}
          </dd>
        </div>
        <div>
          <dt>終了確認の案内</dt>
          <dd data-testid="end-prompt">{{ offered(flow?.promptRequired) }}</dd>
        </div>
        <div>
          <dt>取消の提供可否</dt>
          <dd data-testid="flow-undo">{{ offered(flow?.undoAllowed) }}</dd>
        </div>
        <div>
          <dt>交代の提供可否</dt>
          <dd data-testid="flow-substitution">
            {{ offered(flow?.substitutionAllowed) }}
          </dd>
        </div>
        <div>
          <dt>閲覧端末の最終反映</dt>
          <dd data-testid="viewer-applied-at">
            {{ shown(ready(sources.viewerAppliedAt)) }}
          </dd>
        </div>
        <div>
          <dt>入力端末の接続</dt>
          <dd data-testid="input-offline">{{ inputOfflineText }}</dd>
        </div>
      </dl>
      <div class="mt-3 grid min-w-0 gap-2 sm:grid-cols-3">
        <button
          type="button"
          disabled
          class="rounded-lg border p-2 disabled:opacity-60"
          data-testid="switch-inning"
        >
          回を切り替える
        </button>
        <button
          type="button"
          disabled
          class="rounded-lg border p-2 disabled:opacity-60"
          data-testid="declare-end"
        >
          終了を宣言する
        </button>
        <button
          type="button"
          disabled
          class="rounded-lg border p-2 disabled:opacity-60"
          data-testid="reopen-game"
        >
          試合を追記再開する
        </button>
      </div>
      <p class="mt-2 text-sm">
        送信停止から同内容で再開する操作は、試合の追記再開とは別です。
      </p>
    </section>
  </div>
</template>
