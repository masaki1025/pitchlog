<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

type Panel = 'inplay' | 'strikeout' | 'walk' | null
type SimpleResult =
  | 'batting-result.called-pitch'
  | 'batting-result.swinging-strike'
  | 'batting-result.foul'
  | 'batting-result.ball'
type InPlayResult =
  | 'batting-result.single'
  | 'batting-result.batted-out'
  | 'batting-result.double'
  | 'batting-result.error'
  | 'batting-result.sacrifice-bunt'
  | 'batting-result.triple'
  | 'batting-result.home-run'
  | 'batting-result.batted-reach'
  | 'batting-result.fielders-choice'
  | 'batting-result.sacrifice-fly'
  | 'batting-result.sacrifice-bunt-error'
  | 'batting-result.double-play'
type StrikeoutResult =
  | 'batting-result.called-strikeout'
  | 'batting-result.swinging-strikeout'
  | 'batting-result.k3'
  | 'batting-result.strikeout-double-play'
type WalkResult = 'batting-result.walk' | 'batting-result.hit-by-pitch'

const props = withDefaults(
  defineProps<{
    balls: number
    strikes: number
    outs: number
    disabled?: boolean
    busy?: boolean
    selectedResult?: string | null
    missingCourse?: boolean
    missingPitchType?: boolean
    missingResult?: boolean
    hitAvailable?: boolean
    hasRunners?: boolean
    hasFirst?: boolean
    hasThird?: boolean
    strikeoutDoublePlayAvailable?: boolean
    intentionalWalkAvailable?: boolean
    strikeoutDetailAvailable?: boolean
    secondaryPending?: string
  }>(),
  {
    disabled: false,
    busy: false,
    selectedResult: null,
    missingCourse: false,
    missingPitchType: false,
    missingResult: false,
    hitAvailable: true,
    hasRunners: false,
    hasFirst: false,
    hasThird: false,
    strikeoutDoublePlayAvailable: false,
    intentionalWalkAvailable: false,
    strikeoutDetailAvailable: true,
    secondaryPending: undefined,
  },
)
const emit = defineEmits<{
  simple: [result: SimpleResult]
  'select-in-play': [result: InPlayResult]
  direct: [result: StrikeoutResult | WalkResult]
  intentional: []
  secondary: [resultId: string]
  interference: [resultId: string]
  balk: [resultId: string]
  clearSecondary: []
  panel: [panel: Panel]
}>()
const panel = defineModel<Panel>('panel', { default: null })
const simple = computed(() => [
  {
    result: 'batting-result.called-pitch' as const,
    label: props.strikes >= 2 ? '見逃し三振' : '見逃し',
  },
  {
    result: 'batting-result.swinging-strike' as const,
    label: props.strikes >= 2 ? '空振り三振' : '空振り',
  },
  { result: 'batting-result.foul' as const, label: 'ファール' },
  {
    result: 'batting-result.ball' as const,
    label: props.balls >= 3 ? '四球' : 'ボール',
  },
])
const strikeoutDisabled = computed(
  () =>
    props.disabled ||
    props.busy ||
    Boolean(props.secondaryPending) ||
    !props.strikeoutDetailAvailable ||
    props.strikes < 2,
)
function simpleDisabled(result: string): boolean {
  if (props.disabled || props.busy) return true
  if (!props.secondaryPending) return false
  return (
    (result === 'batting-result.ball' && props.balls >= 3) ||
    (result === 'batting-result.called-pitch' && props.strikes >= 2) ||
    (result === 'batting-result.swinging-strike' && props.strikes >= 2)
  )
}
const quickInPlay: readonly { result: InPlayResult; label: string }[] = [
  { result: 'batting-result.single', label: '単打' },
  { result: 'batting-result.batted-out', label: '凡打死' },
  { result: 'batting-result.double', label: '二塁打' },
  { result: 'batting-result.error', label: 'エラー' },
  { result: 'batting-result.sacrifice-bunt', label: '犠打' },
]
const allInPlay: readonly { result: InPlayResult; label: string }[] = [
  { result: 'batting-result.single', label: '単打' },
  { result: 'batting-result.double', label: '二塁打' },
  { result: 'batting-result.triple', label: '三塁打' },
  { result: 'batting-result.home-run', label: '本塁打' },
  { result: 'batting-result.batted-out', label: '凡打死' },
  { result: 'batting-result.double-play', label: '併殺打' },
  { result: 'batting-result.batted-reach', label: '凡打出塁' },
  { result: 'batting-result.error', label: 'エラー' },
  { result: 'batting-result.fielders-choice', label: '野手選択' },
  { result: 'batting-result.sacrifice-bunt', label: '犠打' },
  { result: 'batting-result.sacrifice-fly', label: '犠飛' },
  { result: 'batting-result.sacrifice-bunt-error', label: '犠打失策' },
]
const strikeouts: readonly {
  result: StrikeoutResult
  label: string
  disabled?: boolean
}[] = [
  { result: 'batting-result.called-strikeout', label: '見逃し三振' },
  { result: 'batting-result.swinging-strikeout', label: '空振り三振' },
  { result: 'batting-result.k3', label: 'K3（スリーバント失敗）' },
  { result: 'batting-result.strikeout-double-play', label: '三振ゲッツー' },
]
const walks: readonly { result: WalkResult; label: string }[] = [
  { result: 'batting-result.walk', label: '四球' },
  { result: 'batting-result.hit-by-pitch', label: '死球' },
]
function back() {
  panel.value = null
  emit('panel', null)
}
function inPlayDisabled(result: string): boolean {
  if (props.disabled || props.busy || !props.hitAvailable) return true
  if (props.secondaryPending) return true
  if (result === 'batting-result.double-play')
    return !props.hasFirst || props.outs !== 0
  if (result === 'batting-result.sacrifice-fly')
    return !props.hasThird || props.outs >= 2
  if (
    result === 'batting-result.sacrifice-bunt' ||
    result === 'batting-result.sacrifice-bunt-error'
  )
    return props.outs >= 2
  if (
    result === 'batting-result.batted-reach' ||
    result === 'batting-result.fielders-choice'
  )
    return !props.hasRunners
  return false
}
</script>

<template>
  <div
    class="flex h-full min-h-0 flex-col gap-1.5"
    :class="{ 'missing-highlight p-1': missingResult }"
  >
    <template v-if="panel === null">
      <div class="grid grid-cols-2 gap-1.5">
        <button
          v-for="item in simple"
          :key="item.result"
          type="button"
          :data-result-id="item.result"
          :disabled="simpleDisabled(item.result)"
          :title="
            secondaryPending && simpleDisabled(item.result)
              ? '付加結果を解除してから選んでください'
              : undefined
          "
          :class="[
            'relative min-h-16 select-none rounded-xl border-2 bg-white px-3 text-xl font-bold text-slate-900 transition-colors hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:bg-slate-800 dark:text-slate-100',
            selectedResult === item.result
              ? 'border-sky-500 bg-sky-100 text-sky-900'
              : 'border-slate-300 dark:border-slate-600 dark:hover:bg-slate-700',
          ]"
          @click="emit('simple', item.result)"
        >
          {{ item.label }}
        </button>
      </div>

      <div
        v-if="secondaryPending"
        class="flex items-center gap-2 rounded-lg border border-purple-300 bg-purple-50 px-2 py-1.5 text-[11px] font-bold text-purple-900 dark:border-purple-700 dark:bg-purple-950/40 dark:text-purple-100"
      >
        <span class="rounded-full bg-purple-600 px-1.5 py-0.5 text-white">{{
          secondaryPending
        }}</span>
        <span class="min-w-0 flex-1"
          >を選択済み。次にボール・見逃し・空振り・ファウルを選んでください。</span
        >
        <button
          type="button"
          class="min-h-8 rounded border border-purple-300 bg-white px-1.5 text-purple-800"
          @click="emit('clearSecondary')"
        >
          解除
        </button>
      </div>
      <section>
        <div
          class="mb-1 flex items-center justify-between text-[11px] font-bold text-slate-500 dark:text-slate-400"
        >
          <span>打球結果</span>
          <span class="font-normal">頻出5件</span>
        </div>
        <div class="grid grid-cols-3 gap-1.5">
          <button
            v-for="item in quickInPlay"
            :key="item.result"
            type="button"
            :data-result-id="item.result"
            :disabled="inPlayDisabled(item.result)"
            :class="[
              'min-h-12 rounded-xl border bg-white px-1 text-sm font-bold text-slate-800 transition-colors hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:bg-slate-800 dark:text-slate-100',
              selectedResult === item.result
                ? 'border-sky-500 bg-sky-100 text-sky-900'
                : 'border-slate-300 dark:border-slate-600 dark:hover:bg-slate-700',
            ]"
            @click="emit('select-in-play', item.result)"
          >
            {{ item.label }}
          </button>
          <button
            type="button"
            class="min-h-12 rounded-xl border border-slate-300 bg-white px-1 text-sm font-bold text-slate-800 hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            :disabled="disabled || busy"
            @click="panel = 'inplay'"
          >
            <span class="inline-flex items-center gap-0.5">
              全打球 <ChevronRight :size="15" />
            </span>
          </button>
        </div>
      </section>

      <div class="grid grid-cols-2 gap-1.5">
        <button
          type="button"
          class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold text-slate-800 hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
          :disabled="strikeoutDisabled"
          :title="strikes < 2 ? '2ストライクから選択できます' : undefined"
          @click="panel = 'strikeout'"
        >
          <span class="inline-flex items-center"
            >三振詳細 <ChevronRight :size="14"
          /></span>
        </button>
        <button
          type="button"
          class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold text-slate-800 hover:bg-slate-50 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
          :disabled="disabled || busy || Boolean(secondaryPending)"
          @click="panel = 'walk'"
        >
          <span class="inline-flex items-center"
            >四死球 <ChevronRight :size="14"
          /></span>
        </button>
      </div>

      <section>
        <div
          class="mb-1 flex items-center justify-between gap-2 text-[11px] font-bold text-slate-500 dark:text-slate-400"
        >
          <span>付加結果</span>
          <span class="font-normal">PB＝捕逸 / WP＝暴投</span>
        </div>
        <div class="grid grid-cols-4 gap-1">
          <button
            type="button"
            :disabled="disabled || busy"
            :class="[
              'min-h-10 rounded-lg border px-1 text-[11px] font-bold disabled:pointer-events-none disabled:opacity-40',
              secondaryPending
                ? 'border-slate-300 bg-white text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200'
                : 'border-purple-300 bg-purple-50 text-purple-800 dark:border-purple-700 dark:bg-purple-950/50 dark:text-purple-200',
            ]"
            @click="emit('clearSecondary')"
          >
            なし
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-700 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="disabled || busy || !hitAvailable"
            title="走者の実結果を確認して付加結果を記録します"
            @click="emit('secondary', 'secondary-result.passed-ball')"
          >
            PB
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-700 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="disabled || busy || !hitAvailable"
            title="走者の実結果を確認して付加結果を記録します"
            @click="emit('secondary', 'secondary-result.wild-pitch')"
          >
            WP
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-700 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="disabled || busy || !hitAvailable"
            @click="emit('interference', 'secondary-result.obstruction')"
          >
            守備妨害
          </button>
        </div>
        <div class="mt-1 grid grid-cols-4 gap-1">
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-700 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="disabled || busy || !hitAvailable"
            @click="
              emit('interference', 'secondary-result.batting-interference')
            "
          >
            打撃妨害
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-700 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="disabled || busy || !hitAvailable"
            @click="
              emit('interference', 'secondary-result.offensive-interference')
            "
          >
            走塁妨害
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-700 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="disabled || busy || !hitAvailable"
            @click="emit('balk', 'secondary-result.balk')"
          >
            ボーク
          </button>
          <button
            type="button"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-700 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            :disabled="disabled || busy || !hitAvailable"
            @click="emit('balk', 'secondary-result.pitch-clock-violation')"
          >
            時計違反
          </button>
        </div>
      </section>

      <section>
        <div
          class="mb-1 text-[11px] font-bold text-slate-500 dark:text-slate-400"
        >
          プレス
        </div>
        <div class="grid grid-cols-4 gap-1">
          <button
            v-for="label in ['なし', '3', '1', '両']"
            :key="label"
            type="button"
            disabled
            title="このMVPでは未接続です"
            class="min-h-10 rounded-lg border border-slate-300 bg-white px-1 text-[11px] font-bold text-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-500"
          >
            {{ label }}
          </button>
        </div>
      </section>

      <button
        type="button"
        disabled
        title="このMVPでは未接続です"
        class="min-h-11 rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold text-slate-400 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-500"
      >
        <span class="inline-flex items-center"
          >その他詳細 <ChevronRight :size="14"
        /></span>
      </button>
    </template>

    <template v-else-if="panel === 'inplay'">
      <button
        type="button"
        class="mb-1 flex min-h-11 w-full items-center gap-1 rounded-lg px-2 text-left text-sm font-bold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
        @click="back"
      >
        <ChevronLeft :size="18" />
        インプレー
        <span class="ml-auto text-xs font-normal">Esc で戻る</span>
      </button>
      <div class="grid grid-cols-2 gap-2">
        <button
          v-for="item in allInPlay"
          :key="item.result"
          type="button"
          :data-result-id="item.result"
          :disabled="inPlayDisabled(item.result)"
          :class="[
            'min-h-16 rounded-xl border-2 bg-white px-3 text-base font-bold text-slate-900 transition-colors hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:bg-slate-800 dark:text-slate-100',
            selectedResult === item.result
              ? 'border-sky-500 bg-sky-100 text-sky-900'
              : 'border-slate-300 dark:border-slate-600 dark:hover:bg-slate-700',
          ]"
          @click="emit('select-in-play', item.result)"
        >
          {{ item.label }}
        </button>
      </div>
    </template>

    <template v-else-if="panel === 'strikeout'">
      <button
        type="button"
        class="mb-1 flex min-h-11 w-full items-center gap-1 rounded-lg px-2 text-left text-sm font-bold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
        @click="back"
      >
        <ChevronLeft :size="18" />
        三振
        <span class="ml-auto text-xs font-normal">Esc で戻る</span>
      </button>
      <div class="grid grid-cols-1 gap-2">
        <button
          v-for="item in strikeouts"
          :key="item.result"
          type="button"
          :data-result-id="item.result"
          :disabled="
            strikeoutDisabled ||
            (item.result === 'batting-result.strikeout-double-play' &&
              !strikeoutDoublePlayAvailable)
          "
          :class="[
            'min-h-16 rounded-xl border-2 bg-white px-3 text-xl font-bold text-slate-900 transition-colors hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:bg-slate-800 dark:text-slate-100',
            selectedResult === item.result
              ? 'border-sky-500 bg-sky-100 text-sky-900'
              : 'border-slate-300 dark:border-slate-600 dark:hover:bg-slate-700',
          ]"
          @click="emit('direct', item.result)"
        >
          {{ item.label }}
        </button>
      </div>
    </template>

    <template v-else-if="panel === 'walk'">
      <button
        type="button"
        class="mb-1 flex min-h-11 w-full items-center gap-1 rounded-lg px-2 text-left text-sm font-bold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
        @click="back"
      >
        <ChevronLeft :size="18" />
        四死球
        <span class="ml-auto text-xs font-normal">Esc で戻る</span>
      </button>
      <div class="grid grid-cols-1 gap-2">
        <button
          v-for="item in walks"
          :key="item.result"
          type="button"
          :data-result-id="item.result"
          :disabled="disabled || busy"
          class="min-h-16 rounded-xl border-2 border-slate-300 bg-white px-3 text-xl font-bold text-slate-900 transition-colors hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
          @click="emit('direct', item.result)"
        >
          {{ item.label }}
        </button>
        <button
          type="button"
          :disabled="disabled || busy || !intentionalWalkAvailable"
          :title="
            intentionalWalkAvailable
              ? undefined
              : 'この状況では申告敬遠を記録できません'
          "
          class="min-h-16 rounded-xl border-2 border-slate-300 bg-white px-3 text-xl font-bold text-slate-900 transition-colors hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
          @click="emit('intentional')"
        >
          申告敬遠
          <span class="ml-1 text-xs font-normal text-slate-400"
            >（無投球）</span
          >
        </button>
      </div>
    </template>
  </div>
</template>
