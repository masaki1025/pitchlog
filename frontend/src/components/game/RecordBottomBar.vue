<script setup lang="ts">
import { Menu, Pencil, Undo2, UserRoundCog } from 'lucide-vue-next'

withDefaults(
  defineProps<{
    hasRunners?: boolean
    inputLocked?: boolean
    gameFinished?: boolean
    pendingCount?: number
    actionRequiredCount?: number
    elapsed?: string
    syncLabel?: string
    editLastAvailable?: boolean
    pickoffAvailable?: boolean
    strategyAvailable?: boolean
  }>(),
  {
    hasRunners: false,
    inputLocked: false,
    gameFinished: false,
    pendingCount: 0,
    actionRequiredCount: 0,
    elapsed: '0:00',
    syncLabel: '',
    editLastAvailable: true,
    pickoffAvailable: true,
    strategyAvailable: true,
  },
)
const emit = defineEmits<{
  undo: []
  editLast: []
  pickoff: []
  strategy: []
  substitution: []
  menu: []
  sync: []
}>()
const button =
  'flex h-11 shrink-0 items-center gap-1 rounded-xl border border-slate-300 bg-white px-3 text-sm font-bold hover:bg-slate-50 active:bg-slate-200 disabled:pointer-events-none disabled:opacity-40 dark:border-slate-600 dark:bg-slate-800 dark:hover:bg-slate-700'
</script>

<template>
  <div
    class="flex h-14 shrink-0 items-center gap-2 border-t border-slate-200 bg-white px-2 dark:border-slate-700 dark:bg-slate-900"
    aria-label="記録操作"
  >
    <button
      type="button"
      :class="button"
      :disabled="inputLocked"
      title="未同期プレイの送信完了後に操作できます"
      @click="emit('undo')"
    >
      <Undo2 :size="18" />
      1球戻す
    </button>
    <button
      type="button"
      :class="button"
      :disabled="inputLocked || !editLastAvailable"
      :title="editLastAvailable ? undefined : 'このMVPでは未接続です'"
      @click="emit('editLast')"
    >
      <Pencil :size="16" />
      直前修正
    </button>
    <button
      type="button"
      :class="[button, !hasRunners && 'opacity-40']"
      :disabled="
        !hasRunners || !pickoffAvailable || inputLocked || gameFinished
      "
      :title="pickoffAvailable ? undefined : 'このMVPでは未接続です'"
      @click="emit('pickoff')"
    >
      牽制 ▸
    </button>
    <button
      type="button"
      :class="button"
      :disabled="!strategyAvailable || inputLocked || gameFinished"
      :title="strategyAvailable ? undefined : 'このMVPでは未接続です'"
      @click="emit('strategy')"
    >
      作戦 ▸
    </button>
    <button
      type="button"
      :class="button"
      :disabled="inputLocked || gameFinished"
      @click="emit('substitution')"
    >
      <UserRoundCog :size="16" />
      交代
    </button>
    <button type="button" :class="button" @click="emit('menu')">
      <Menu :size="16" />
      メニュー
    </button>
    <div
      class="ml-auto flex items-center gap-2 pr-1 text-xs font-semibold text-slate-500 lg:shrink-0 lg:flex-nowrap dark:text-slate-400"
    >
      <div
        class="flex items-center gap-3 lg:shrink-0 lg:border-l lg:border-slate-200 lg:pl-2 dark:lg:border-slate-700"
      >
        <button
          type="button"
          data-testid="record-sync"
          :class="[
            'min-h-11 rounded-full px-2 py-1 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 lg:shrink-0 lg:whitespace-nowrap',
            actionRequiredCount > 0
              ? 'animate-pulse bg-red-100 font-bold text-red-700 hover:bg-red-200 dark:bg-red-900/60 dark:text-red-300'
              : pendingCount > 0
                ? 'bg-amber-100 font-bold text-amber-800 hover:bg-amber-200 dark:bg-amber-900/60 dark:text-amber-200'
                : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700',
          ]"
          :aria-label="`未同期センターを開く。未同期${pendingCount}件`"
          @click="emit('sync')"
        >
          {{
            syncLabel ||
            (pendingCount === 0
              ? '同期済み'
              : [
                  pendingCount - actionRequiredCount > 0
                    ? `送信待ち ${pendingCount - actionRequiredCount}`
                    : '',
                  actionRequiredCount > 0
                    ? `要確認 ${actionRequiredCount}`
                    : '',
                ]
                  .filter(Boolean)
                  .join('・'))
          }}
        </button>
        <span class="tabular-nums lg:shrink-0 lg:whitespace-nowrap"
          >経過 {{ elapsed }}</span
        >
      </div>
    </div>
  </div>
</template>
