<script setup lang="ts">
import type { UndoOffer } from './GameScreenCorrectionTypes'

defineProps<{ offer?: UndoOffer | null }>()
</script>

<template>
  <section
    aria-label="直前の操作を取り消す"
    class="min-w-0 space-y-3 rounded-2xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/30"
  >
    <h2 class="text-lg font-extrabold">直前の操作を取り消す</h2>
    <p
      v-if="!offer || offer.kind === 'unknown'"
      data-testid="undo-target-status"
    >
      取消対象は未取得です。
    </p>
    <p v-else-if="offer.kind === 'none'" data-testid="undo-target-status">
      取り消せる直前の操作はありません。
    </p>
    <dl v-else class="min-w-0 space-y-2" data-testid="undo-target-status">
      <div class="min-w-0">
        <dt class="text-sm">操作</dt>
        <dd class="font-bold wrap-anywhere">{{ offer.operationLabel }}</dd>
      </div>
      <div class="min-w-0">
        <dt class="text-sm">対象</dt>
        <dd class="font-bold wrap-anywhere">{{ offer.targetLabel }}</dd>
      </div>
    </dl>
    <p id="undo-blocked-reason" class="text-sm">
      この画面ではまだ取消できません。記録は変更されず、そのまま保持されています。
    </p>
    <button
      type="button"
      disabled
      aria-describedby="undo-blocked-reason"
      data-testid="undo-action"
      class="min-w-0 rounded-lg border border-amber-600 px-3 py-2 font-bold disabled:cursor-not-allowed disabled:opacity-60"
      @click.stop.prevent
    >
      直前の操作を取り消す
    </button>
  </section>
</template>
