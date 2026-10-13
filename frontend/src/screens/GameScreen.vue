<script setup lang="ts">
interface GameDisplayState {
  gameName: string | null
  inning: string | null
  half: string | null
  awayScore: string | null
  homeScore: string | null
  outs: string | null
  runners: string | null
  count: string | null
  batter: string | null
  pitcher: string | null
}

const props = defineProps<{
  state?: Partial<GameDisplayState> | null
}>()

// 呼出元が表示用に整形した文字列だけを描画する。
function display(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value : '未取得'
}
</script>

<template>
  <main class="mx-auto max-w-5xl space-y-5 p-4 pb-12">
    <header class="space-y-2">
      <p class="text-sm font-semibold text-sky-700 dark:text-sky-300">
        試合状態 · 表示のみ
      </p>
      <h1 class="text-2xl font-extrabold" data-testid="game-name">
        {{ display(props.state?.gameName) }}
      </h1>
      <p class="text-sm text-slate-600 dark:text-slate-300">
        この画面は表示データの接続前です。ここから記録はできません。
      </p>
    </header>

    <section
      aria-label="試合状況"
      class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
    >
      <div class="mb-5 flex flex-wrap items-center gap-2 text-sm font-bold">
        <span
          class="rounded-full bg-sky-100 px-3 py-1 text-sky-800 dark:bg-sky-950 dark:text-sky-200"
          data-testid="inning"
        >
          {{ display(props.state?.inning) }}
        </span>
        <span
          class="rounded-full bg-slate-100 px-3 py-1 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
          data-testid="half"
        >
          {{ display(props.state?.half) }}
        </span>
      </div>

      <dl class="grid grid-cols-2 gap-3">
        <div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
          <dt class="text-sm text-slate-500 dark:text-slate-400">先攻</dt>
          <dd
            class="mt-1 text-3xl font-extrabold tabular-nums"
            data-testid="away-score"
          >
            {{ display(props.state?.awayScore) }}
          </dd>
        </div>
        <div class="rounded-xl bg-slate-50 p-4 dark:bg-slate-800">
          <dt class="text-sm text-slate-500 dark:text-slate-400">後攻</dt>
          <dd
            class="mt-1 text-3xl font-extrabold tabular-nums"
            data-testid="home-score"
          >
            {{ display(props.state?.homeScore) }}
          </dd>
        </div>
      </dl>

      <dl class="mt-4 grid gap-3 sm:grid-cols-3">
        <div
          class="rounded-xl border border-slate-200 p-3 dark:border-slate-700"
        >
          <dt class="text-sm text-slate-500 dark:text-slate-400">アウト</dt>
          <dd class="mt-1 font-bold" data-testid="outs">
            {{ display(props.state?.outs) }}
          </dd>
        </div>
        <div
          class="rounded-xl border border-slate-200 p-3 dark:border-slate-700"
        >
          <dt class="text-sm text-slate-500 dark:text-slate-400">走者</dt>
          <dd class="mt-1 font-bold" data-testid="runners">
            {{ display(props.state?.runners) }}
          </dd>
        </div>
        <div
          class="rounded-xl border border-slate-200 p-3 dark:border-slate-700"
        >
          <dt class="text-sm text-slate-500 dark:text-slate-400">カウント</dt>
          <dd class="mt-1 font-bold" data-testid="count">
            {{ display(props.state?.count) }}
          </dd>
        </div>
      </dl>
    </section>

    <section aria-label="対戦中の選手" class="grid gap-3 sm:grid-cols-2">
      <dl
        class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
      >
        <dt class="text-sm text-slate-500 dark:text-slate-400">打者</dt>
        <dd class="mt-1 text-lg font-bold" data-testid="batter">
          {{ display(props.state?.batter) }}
        </dd>
      </dl>
      <dl
        class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
      >
        <dt class="text-sm text-slate-500 dark:text-slate-400">投手</dt>
        <dd class="mt-1 text-lg font-bold" data-testid="pitcher">
          {{ display(props.state?.pitcher) }}
        </dd>
      </dl>
    </section>
  </main>
</template>
