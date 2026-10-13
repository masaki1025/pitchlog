<script setup lang="ts">
import {
  ArrowLeft,
  BarChart3,
  CalendarRange,
  CircleHelp,
  Cloud,
  Download,
  FileUp,
  Keyboard,
  Pencil,
  Play,
  RotateCcw,
  Table2,
  Users,
} from 'lucide-vue-next'
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

    <div class="grid gap-4 lg:grid-cols-2">
      <section
        class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
      >
        <h2 class="mb-3 flex items-center gap-2 font-extrabold">
          <Play :size="18" class="text-sky-600" />1球入力の流れ
        </h2>
        <ol class="space-y-3 text-sm">
          <li>
            <b>① 左：</b>構えを選び、直前球速の候補またはテンキーで球速を入力
          </li>
          <li>
            <b>② 中央：</b
            >投球コースと球種を選択。打球時はフィールドへ自動で切り替わります
          </li>
          <li>
            <b>③ 右：</b
            >結果を選択。ボール・見逃し・空振り・ファールなどはその場で保存
          </li>
          <li>
            <b>④ インプレー：</b
            >打球位置・打球タイプ・捕球選手・走者進塁を確認して確定
          </li>
        </ol>
        <p
          class="mt-4 rounded-xl bg-sky-50 p-3 text-sm font-semibold text-sky-800 dark:bg-sky-950/40 dark:text-sky-200"
        >
          構えと球種は前回値を保持し、球速は直前値の周辺候補が並びます。上部の打者・投手名を押すと、基本情報と共有カルテ所見も確認できます。
        </p>
        <p
          class="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400"
        >
          球速は「設定 →
          球速入力」で方式を選べます。下2桁クイックは35を135km/h、89を89km/hとして入力し、1桁途中では登録を止めます。従来どおり実速度を入力する場合は「通常3桁」を選びます。
        </p>
      </section>

      <section
        class="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
      >
        <h2 class="mb-3 flex items-center gap-2 font-extrabold">
          <RotateCcw :size="18" class="text-amber-600" />修正・同期
        </h2>
        <div class="space-y-3 text-sm">
          <div class="flex gap-3">
            <RotateCcw :size="18" class="mt-0.5 shrink-0 text-amber-600" />
            <p><b>1球戻す：</b>直前に確定した1球を取り消します。</p>
          </div>
          <div class="flex gap-3">
            <Pencil :size="18" class="mt-0.5 shrink-0 text-violet-600" />
            <p>
              <b>直前修正：</b
              >直前球を入力画面に再現します。内容を変えたあと「修正を保存」で反映します。
            </p>
          </div>
          <div class="flex gap-3">
            <Users :size="18" class="mt-0.5 shrink-0 text-emerald-600" />
            <p><b>交代：</b>試合下部の「交代」からメンバー表を更新します。</p>
          </div>
          <div class="flex gap-3">
            <Cloud :size="18" class="mt-0.5 shrink-0 text-sky-600" />
            <p>
              <b>未同期：</b
              >送れなかった入力はこの端末に保持され、接続回復後に自動再送されます。確認が必要な場合は画面下の「未同期」を押して未同期センターを開きます。
            </p>
          </div>
          <div class="flex gap-3">
            <Download :size="18" class="mt-0.5 shrink-0 text-emerald-600" />
            <p>
              <b>記録確認・CSV：</b
              >スコア表・プレイ一覧・ホームの「データ入出力」から確認や出力ができます。
            </p>
          </div>
          <div class="flex gap-3">
            <BarChart3 :size="18" class="mt-0.5 shrink-0 text-violet-600" />
            <p>
              <b>データ分析：</b
              >チーム・期間・対戦相手を絞り、左右別・球種別・コース別の分析、個人レポート、試合用カルテ、チーム攻撃分析を出力できます。
            </p>
          </div>
        </div>
        <p
          class="mt-4 rounded-xl bg-amber-50 p-3 text-xs font-semibold leading-5 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
        >
          未同期データが残っている間は、ブラウザの閲覧データを削除しないでください。別端末が記録権を持っている試合は、明示的な引き継ぎ操作をしない限り記録できません。引き継ぎ前に取った未送信の記録は適用されず、退避されたうえで管理コンソールで内容を確認・書き出しできます。
        </p>
      </section>
    </div>

    <section
      class="mt-4 rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
    >
      <h2 class="mb-3 flex items-center gap-2 font-extrabold">
        <CalendarRange
          :size="18"
          class="text-sky-600"
        />試合を探す・記録を確認する
      </h2>
      <div class="grid gap-3 md:grid-cols-3">
        <article class="rounded-2xl bg-slate-50 p-4 dark:bg-slate-800/70">
          <CalendarRange :size="20" class="mb-2 text-sky-600" />
          <h3 class="font-extrabold">試合一覧</h3>
          <p class="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">
            対象チーム・対戦相手・試合ID・期間・シーズン・試合種別で検索できます。各試合から入力再開、スコア表、プレイ一覧、削除へ進めます。
          </p>
        </article>
        <article class="rounded-2xl bg-slate-50 p-4 dark:bg-slate-800/70">
          <Table2 :size="20" class="mb-2 text-emerald-600" />
          <h3 class="font-extrabold">スコア表・プレイ一覧</h3>
          <p class="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">
            スコア表は印刷・PDF保存に対応します。1球ごとの記録確認は「プレイ一覧」から、試合データCSVはホームの「データ入出力」から利用できます。複数試合を選ぶと1つのZIPにまとまります。
          </p>
        </article>
        <article class="rounded-2xl bg-slate-50 p-4 dark:bg-slate-800/70">
          <FileUp :size="20" class="mb-2 text-amber-600" />
          <h3 class="font-extrabold">データ入出力</h3>
          <p class="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">
            「試合データCSV出力」は所有する試合を複数選択できます。取り込みでは旧データ変換／現システムCSV復元を選び、プレビュー確認後に新しい試合として保存します。投手・打者・チーム集計CSVは取り込み対象外です。
          </p>
        </article>
      </div>
    </section>

    <section class="mt-4 grid gap-4 md:grid-cols-2">
      <article
        class="rounded-2xl border border-violet-200 bg-violet-50/70 p-5 dark:border-violet-900 dark:bg-violet-950/30"
      >
        <h2 class="flex items-center gap-2 font-extrabold">
          <BarChart3 :size="18" class="text-violet-600" />データ分析・カルテ
        </h2>
        <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
          チーム・期間・対戦相手で絞り、投手・打者・チーム攻撃を確認します。個人分析から所見編集、分析PDF、試合用カルテへ進め、一覧の「出力」からスタッツCSVやチーム一括カルテも保存できます。
        </p>
      </article>
      <article
        class="rounded-2xl border border-sky-200 bg-sky-50/70 p-5 dark:border-sky-900 dark:bg-sky-950/30"
      >
        <h2 class="flex items-center gap-2 font-extrabold">
          <Keyboard :size="18" class="text-sky-600" />キーボード設定
        </h2>
        <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
          現在の割り当て確認・変更はホーム右上の「設定 →
          キーボード」から行います。試合中は「メニュー →
          キーボードショートカット設定」からも開けます。設定はこの端末のブラウザに保存されます。
        </p>
        <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
          球速テンキーの「下2桁クイック／通常3桁」は、同じ設定内の「球速入力」から切り替えます。
        </p>
        <p class="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
          ログインパスワードは、同じ設定内の「アカウント」から変更できます。変更後は安全のためログアウトし、新しいパスワードで再ログインします。
        </p>
        <p class="mt-2 text-xs font-semibold text-sky-800 dark:text-sky-200">
          詳細なキー一覧と固定操作は、設定画面または試合中のショートカット一覧で確認してください。
        </p>
      </article>
    </section>
  </div>
</template>
