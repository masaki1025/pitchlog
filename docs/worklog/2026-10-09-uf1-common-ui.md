---
date: 2026-10-09
topic: TSK-516 U-F1 共通表示(汎用部品・起動補助)
branch: feature/uf1-common-ui
---

# 作業ログ: 2026-10-09 TSK-516 U-F1 共通表示(汎用部品・起動補助)

## やったこと

### /task-start

- 既存 Notion タスク TSK-516(2026-10-09 起票・TSK-508 #110 のステップ 5)に着手: https://app.notion.com/p/3f493b75e687810aafaaf6ba6d7a34a8
- ブランチ `feature/uf1-common-ui` / worktree `../pitchlog-worktrees/feature-uf1-common-ui`(origin/develop `ed4025bd` 起点)
- 経緯: TSK-510 は TSK-509 の確定ゲート通過まで待機(PO 判断)。その間に U-X1 を待たない単位として U-F1 → U-F4 を取る(master セッション経由の割り当てを本セッションで PO が確認)
- 単位定義の典拠 `docs/features/frontend-impl-units/design.md:308`(U-F1)・`:311`(U-F4)。#110 が develop へマージ済み(`62fc5bfc`・2026-10-09)のため、着手直後に本ブランチを `62fc5bfc` へ早送りした(自コミット 0 件の時点)
- 着手時の注意(原典で確認済み): 依存追加の 6 ファイル(`frontend/package.json`・`pnpm-lock.yaml`・`vite.config.ts`・`vitest.config.ts`・`tsconfig.json`・`tsconfig.app.json`)はコア領域の paths に当たる。`components/ui/**`・`index.css`・`lib/queryClient.ts` は当たらない。移植元 `dd03160` は React(`.tsx`)、現行 frontend は Vue 3 — 変換は porting-rules に従う

### /investigate(2026-10-10)

- 3 並列(spec-checker / legacy-analyst / decision-tracer)→ `docs/features/uf1-common-ui/research.md` に統合
- 照合基準の注意: ローカル `~/projects/Baseball_Scoring` の作業ツリーは dd03160 より古い。固定リビジョンを `git show` でスクラッチパッドへ書き出して渡した
- エージェントの「不明」2 件を主セッションが git で解消: teamSearch の呼び出し元(AnalysisScreen・TeamScreen)、authStore の `queryClient.clear()`(認証変化 → U-F2 側の責務)
- 食い違いの裁定: 「依存追加は別 PR」— 既決ではないが、U-F1(sync・zone に触れない)では成り立つ。否定側の資料は同期・ゾーンに触れる画面についての記述
- PO に上げる分岐 3 つ(依存 2 件の承認と PR の切り方 / registerServiceWorker + sw.js の扱い / .test.mjs の書き換え)を research.md の末尾に整理

### /plan(2026-10-10)

- PO 決定(本セッション): 依存 2 件(`@tanstack/vue-query` 5.101.4・`lucide-vue-next` 1.0.0)は **U-F1 の PR に含める**(→ 重さ分類 = コア領域)/ `registerServiceWorker.ts` + `public/sw.js` は **U-F1 から外し別単位へ** → TSK-533 を起票(https://app.notion.com/p/3f493b75e68781db829cfa994b45a9e0)
- 計画段階の実測: `vue/multi-word-component-names` が `Button.vue` で error(eslint 実行)/ lucide `X` の照合(npm pack — パスと svg 属性は一致、class に `lucide-x-icon` が増えるだけ)/ dd03160 の lock 解決版 = lucide-react 0.525.0・react-query 5.101.2・tailwindcss 4.3.2

#### 計画レビュー 1 回目(adversarial・全文 — 判定: 否決 P0 2 / P1 2 / P2 0)

| # | 重大度 | 要旨 | 採否 | 理由・反映 |
| --- | --- | --- | --- | --- |
| 1 | P0 | 逐語複製(teamSearch.ts・queryClient.ts)は ADR-002:34「コード再利用はしない」と衝突 | **採用(PO 決定 2026-10-10)** | 作成者は不採用を提案(8/16 裁定 2 項・I-28・逐語 .ts 4 件の前例)したが、PO は採用し「Vue で問題なく作れればいい」と指示。→ 旧コードは複製せず Vue / TS で書き起こす。見た目・挙動の同等性はクラス一致と試験で確かめる。`.prettierignore` 追加・逐語比較コマンドを削除、決定 I・K、ステップ 2・3、DoD 1 項目目、1 節を改訂 |
| 2 | P0 | `watch(open, …, flush post)` は初期 open=true で走らない | 採用 | 決定 C を「変化 = watch(flush post)/ 初期 = onMounted / 後始末 = 閉じたとき + onBeforeUnmount」へ。`immediate` を使わない理由も記載。ステップ 6 に初期 open=true と開いたままのアンマウントの試験を追加 |
| 3 | P1 | ステップ 7 の追記対象から決定 B・D が漏れ | 採用 | 載せる 9 件(A・B・C・D・E・F・H・J・K)と載せない 2 件(G・I)の理由を明記 |
| 4 | P1 | 下流申し送りの DoD に担当ステップが無い | 採用 | ステップ 7 ③ に宛先 6 単位の Notion コメント + worklog 記録を割り当て |

#### 計画レビュー 2 回目(adversarial・反映差分 + 影響節 — 判定: 否決 P0 0 / P1 1 / P2 0)

| # | 重大度 | 要旨 | 採否 | 理由・反映 |
| --- | --- | --- | --- | --- |
| 1 | P1 | DoD は見た目の同等性を求めるが、`Button` active 時の bg クラス競合の確認を合否から外している | 採用 | ステップ 4 の合格条件に、ビルド CSS の規則順序で勝敗を確かめてコミット本文へ記録する項を追加。DoD の文言を揃えた |

P0 ゼロのため P0 例外(3 回目)は発生しない。基本枠 2 回を使い切り、最終反映(上の 1 件)は再レビューを受けていない — 承認時に差分を確認してもらう(設計書 6.3 (4))。

### /implement(2026-10-10)

- ステップ 1(ネットワーク有効 — 人間了承済み): Codex が package.json(2 行)と lock を更新したが、sandbox で別の pnpm ストアを使ったため `--frozen-lockfile` が TTY 確認で停止(環境起因)。主セッションで検証したところ **`ERR_PNPM_IGNORED_BUILDS: vue-demi@0.14.10`** で install と以後の `pnpm exec` がすべて失敗
- **計画変更(PO 決定 2026-10-10)**: `frontend/pnpm-workspace.yaml` を新設し `allowBuilds: { vue-demi: false }`。理由: postinstall は Vue 2/3 のファイル差し替えだけで同梱の既定が Vue 3 用 / 第三者スクリプトを install で走らせない。`pnpm-workspace.yaml` はコア paths に当たらない(実測)。計画書ステップ 1 の内容と合格条件を更新

## 決定

## 未決・次の一歩
