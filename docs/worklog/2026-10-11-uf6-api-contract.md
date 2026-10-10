---
date: 2026-10-11
topic: U-F6 共通 API・形式契約
branch: feature/uf6-api-contract
---

# 作業ログ: 2026-10-11 U-F6 共通 API・形式契約

## やったこと

### /task-start

- 既存 Notion タスク TSK-521 に着手(master の依頼 — U-F2 の後続。画面 8 単位の結節点): https://app.notion.com/p/3f493b75e6878145aa82d873e8cb65f3
- ブランチ `feature/uf6-api-contract` / worktree `../pitchlog-worktrees/feature-uf6-api-contract`(`origin/develop` = `8060b8d0` — #116 マージ後)

### /investigate

- 4 並列(legacy-analyst / spec-checker / decision-tracer / Explore)。legacy-analyst へは `dd03160` の api・lib の 26 ファイルと import 一覧を主セッションが書き出して渡した
- 結果は [research.md](../features/uf6-api-contract/research.md)。要点: 旧 `endpoints.ts`・`types.ts`(74 関数・147 型)は develop の backend(業務 8 経路・カーソル・別のエラー封筒・`/api` 接頭辞なし)とほぼ噛み合わない / 旧 `mock.ts` はドメイン計算を自前で持つ(NFR-018)・モックの移植は未決 / 同期の通信層は TSK-506 の担当 / `format.ts` は移植済み / 2026-08-16 の「API 契約を踏襲」裁定と U-M1 の新しい形をすり合わせた記録がない

## 決定

## 未決・次の一歩

### /plan

- /plan 前に PO へ分岐 4 点を確認(2026-10-10・山田): Q1 いまの backend に合わせる / Q2 モックは移植しない / Q3 U-F6 は土台だけ(同期は TSK-506)/ Q4 `/api` を付けて送り proxy で外す。すべて推奨案
- 5 領域判定を当て直し: T のみ該当(S・G・R・D は持つ範囲から外れた)。`vite.config.ts` が機械判定に当たるため PR 全体はコア領域
