---
date: 2026-10-10
topic: TSK-447 在籍区分の入口とキャッシュ無効化の発火点(無効化意図の ID 導出規則と原子性の錨)
branch: feature/roster-status-invalidation
---

# 作業ログ: 2026-10-10 TSK-447 在籍区分の入口とキャッシュ無効化の発火点(無効化意図の ID 導出規則と原子性の錨)

## やったこと

### /task-start

- 既存 Notion タスク TSK-447(2026-09-24 起票・U-M1 から分離)に着手: https://app.notion.com/p/3e593b75e6878116ab33fc7eaadd64d9
- ブランチ `feature/roster-status-invalidation` / worktree `../pitchlog-worktrees/feature-roster-status-invalidation`(origin/develop `f79c14e0` 起点 = PR #95 マージ直後)
- 射程: TSK-447(イベント由来でないトリガーの意図 ID 導出規則と原子性の錨・正本 11-2 節の改訂・契約 `cache-invalidation-contract.json` の追随)+ U-M1 第 10 改訂で #95 から外した旧ステップ 11(在籍区分の入口〔プレビュー・適用〕と発火点 — FR-017・トリガー 14)。選手の削除(FR-018)は TSK-459 待ちで射程外
- 位置づけ: FR-017 はリハーサル最小集合 26 件に入り、#95 では判定対象外(U-M1 plan.md:650)なので本 PR でしか着地しない(master 2026-10-10)
- コア領域(テナント分離)

### /investigate

- 調査サブエージェント 6 本(下調べ 3 本 + 追加 3 本)の結果を [research.md](../features/roster-status-invalidation/research.md) に統合した
- 原典で確認した要点: 11-2 節の意図の永続化(`B03`・`B04`)は `I5`(P3)の永続化先として書かれている(`data-model.md:2232`)。発火条件の正である sync-protocol 8-5 の行は D1 付き経路と I5 の 2 つだけで(`sync-protocol.md:1356-1361`)、**同期を通らないトリガーの発火条件の正はどこにも無い**。契約の `durable_intent` は P3 の規則を 14 トリガーすべてに分岐なしで掛けている
- イベント由来でないトリガーは 9 件(5・7〜14)。U-M1 計画書の「7」と Notion の「少なくとも 6」はどちらも数え漏れ
- キャッシュ本体・配信先・意図表へ書くコードは無い。契約と DDL の語彙が食い違っている(既存の記録なし)
- 旧システムに在籍区分は無い(FR-017 はすべて新規)

## 決定

## 未決・次の一歩

- /investigate(着手前の下調べは 2026-10-10 に 3 並列で実施済み — 結果を research.md へ起こす)→ /plan
