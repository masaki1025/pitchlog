<script setup lang="ts">
import { useRouter } from 'vue-router'
import {
  BarChart3,
  BookOpen,
  CalendarRange,
  ChevronRight,
  FileUp,
  LogOut,
  Network,
  Play,
  Settings,
  Users,
} from 'lucide-vue-next'
import { useAuthStore } from '../stores/authStore'

const router = useRouter()
const auth = useAuthStore()

async function logout(): Promise<void> {
  auth.signOut()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="mx-auto max-w-6xl p-4 pb-10">
    <header class="mb-5 flex items-center justify-between gap-3">
      <div class="min-w-0">
        <p class="text-xs font-bold uppercase tracking-widest text-sky-600">
          Baseball scoring
        </p>
        <h1 class="truncate text-2xl font-extrabold">
          {{ auth.teamName ?? 'チーム未選択' }}
        </h1>
      </div>
      <div class="flex items-center gap-1">
        <RouterLink
          :to="{ name: 'team' }"
          aria-label="設定を開く"
          class="inline-flex min-h-12 items-center gap-1.5 rounded-xl px-3 text-sm font-bold text-slate-700 hover:bg-slate-200 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <Settings :size="16" />
          <span class="hidden sm:inline">設定</span>
        </RouterLink>
        <RouterLink
          :to="{ name: 'help' }"
          class="inline-flex min-h-12 items-center gap-1.5 rounded-xl px-3 text-sm font-bold text-slate-700 hover:bg-slate-200 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <BookOpen :size="16" />
          <span class="hidden sm:inline">使い方</span>
        </RouterLink>
        <button
          type="button"
          class="inline-flex min-h-12 items-center gap-1.5 rounded-xl px-3 text-sm font-bold text-slate-700 hover:bg-slate-200 dark:text-slate-200 dark:hover:bg-slate-800"
          @click="logout"
        >
          <LogOut :size="16" />
          <span class="hidden sm:inline">ログアウト</span>
        </button>
      </div>
    </header>

    <section
      class="mb-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(440px,456px)]"
    >
      <RouterLink
        :to="{ name: 'games', query: { create: '1' } }"
        class="group flex min-h-40 items-center justify-between overflow-hidden rounded-3xl bg-gradient-to-br from-sky-600 to-blue-700 p-6 text-left text-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg"
      >
        <div>
          <p class="mb-2 text-sm font-bold text-sky-100">
            今日の記録をはじめる
          </p>
          <h2 class="text-2xl font-black sm:text-3xl">新しい試合</h2>
          <p class="mt-2 text-sm text-sky-100">試合情報とスタメン入力へ</p>
        </div>
        <span
          class="grid size-14 shrink-0 place-items-center rounded-2xl bg-white/15 transition group-hover:bg-white/25"
        >
          <Play :size="28" fill="currentColor" />
        </span>
      </RouterLink>

      <div class="grid grid-cols-2 gap-3">
        <RouterLink
          :to="{ name: 'team' }"
          class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-emerald-400 hover:bg-emerald-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-emerald-950/30"
        >
          <span
            class="grid size-10 shrink-0 place-items-center rounded-xl bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
          >
            <Users :size="20" />
          </span>
          <span class="min-w-0">
            <span class="block font-extrabold lg:whitespace-nowrap"
              >チーム・選手</span
            >
            <span class="block truncate text-xs text-slate-400"
              >自チーム・相手名簿を管理</span
            >
          </span>
          <ChevronRight :size="17" class="ml-auto shrink-0 text-slate-300" />
        </RouterLink>

        <RouterLink
          :to="{ name: 'season-stats' }"
          class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-violet-400 hover:bg-violet-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-violet-950/30"
        >
          <span
            class="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300"
          >
            <BarChart3 :size="20" />
          </span>
          <span class="min-w-0">
            <span class="block font-extrabold lg:whitespace-nowrap"
              >データ分析</span
            >
            <span class="block truncate text-xs text-slate-400"
              >シーズン成績・個人成績を確認</span
            >
          </span>
          <ChevronRight :size="17" class="ml-auto shrink-0 text-slate-300" />
        </RouterLink>

        <RouterLink
          :to="{ name: 'games' }"
          class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-sky-400 hover:bg-sky-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-sky-950/30"
        >
          <span
            class="grid size-10 shrink-0 place-items-center rounded-xl bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300"
          >
            <CalendarRange :size="20" />
          </span>
          <span class="min-w-0">
            <span class="block font-extrabold lg:whitespace-nowrap"
              >試合一覧</span
            >
            <span class="block truncate text-xs text-slate-400"
              >検索・入力再開・スコア表</span
            >
          </span>
          <ChevronRight :size="17" class="ml-auto shrink-0 text-slate-300" />
        </RouterLink>

        <RouterLink
          :to="{ name: 'games' }"
          class="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-amber-400 hover:bg-amber-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-amber-950/30"
        >
          <span
            class="grid size-10 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
          >
            <FileUp :size="20" />
          </span>
          <span class="min-w-0">
            <span class="block font-extrabold lg:whitespace-nowrap"
              >データ入出力</span
            >
            <span class="block truncate text-xs text-slate-400"
              >試合ごとのCSV出力</span
            >
          </span>
          <ChevronRight :size="17" class="ml-auto shrink-0 text-slate-300" />
        </RouterLink>

        <div
          class="col-span-2 flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left dark:border-slate-700 dark:bg-slate-900"
        >
          <span
            class="grid size-10 shrink-0 place-items-center rounded-xl bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300"
          >
            <Network :size="20" />
          </span>
          <span class="min-w-0">
            <span class="block font-extrabold">比較グループ</span>
            <span class="block truncate text-xs text-slate-400"
              >共有分析は未提供です</span
            >
          </span>
        </div>
      </div>
    </section>

    <RouterLink
      :to="{ name: 'games' }"
      class="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-sky-400 hover:bg-sky-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-sky-950/30"
    >
      <span>
        <span class="block font-extrabold">最近の試合</span>
        <span class="block text-xs text-slate-400"
          >試合一覧で準備中・保存済みの試合を確認</span
        >
      </span>
      <ChevronRight :size="17" class="shrink-0 text-slate-300" />
    </RouterLink>
  </div>
</template>
