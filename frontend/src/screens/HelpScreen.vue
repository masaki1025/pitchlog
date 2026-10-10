<script setup lang="ts">
import { ArrowLeft, CircleHelp } from 'lucide-vue-next'
import Button from '../components/ui/Button.vue'

const STEPS = [
  [
    '1',
    'チーム・選手を準備',
    '初回のチーム登録はシステム管理者が行います。ログイン後、ホームの「チーム・選手」から名簿を登録します。',
  ],
  [
    '2',
    '試合を作成',
    'ホームの「新しい試合」から試合情報、先攻・後攻、スタメンを設定します。',
  ],
  [
    '3',
    '1球ずつ入力',
    '構え・コース・球種・球速・結果を1画面で選びます。インプレーだけ追加確認して確定します。',
  ],
  [
    '4',
    '保存・再開',
    '入力は毎球保存されます。直近4試合はホーム、それ以前は「試合一覧」から検索して再開できます。',
  ],
  [
    '5',
    '確認・分析',
    'スコア表・プレイ一覧で記録を確認し、「データ分析」からスタッツ・カルテ・各種出力へ進みます。',
  ],
] as const

const emit = defineEmits<{ back: [] }>()
</script>

<template>
  <div class="mx-auto max-w-5xl p-4 pb-12">
    <header class="mb-6 flex items-center gap-3">
      <Button variant="ghost" aria-label="戻る" @click="emit('back')">
        <ArrowLeft :size="18" />
      </Button>
      <div>
        <h1 class="flex items-center gap-2 text-xl font-extrabold">
          <CircleHelp :size="21" class="text-sky-600" /> 使い方
        </h1>
        <p class="text-sm text-slate-400">
          現在のホーム・試合入力画面に合わせた操作ガイド
        </p>
      </div>
    </header>

    <section class="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <article
        v-for="step in STEPS"
        :key="step[0]"
        class="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
      >
        <span
          class="mb-3 grid size-8 place-items-center rounded-full bg-sky-600 text-sm font-black text-white"
          >{{ step[0] }}</span
        >
        <h2 class="font-extrabold">{{ step[1] }}</h2>
        <p
          class="mt-1 text-sm leading-relaxed text-slate-500 dark:text-slate-400"
        >
          {{ step[2] }}
        </p>
      </article>
    </section>
  </div>
</template>
