---
date: 2026-10-05
topic: 12-4 の「実スキーマ」の意味と SP-06 の字面衝突を裁定する(TSK-382)
branch: feature/real-schema-meaning
---

# 作業ログ: 2026-10-05 12-4 の「実スキーマ」の意味と SP-06 の字面衝突を裁定する(TSK-382)

## やったこと

### /task-start(2026-10-05・UM01 タブ)

- Notion TSK-382 を 進行中 へ。ブランチ `feature/real-schema-meaning`(起点 develop `f2dc9f9b`)
- カード(09-12 起票)の射程は 3 者の字面衝突の裁定: 12-9 `SP-06`「RLS を初日から全テーブルに掛ける」/ 12-4 の non-serving 宣言 / 12-6 の受け取り先表
- 後から積まれた射程: **12-4 の「実スキーマ」の正本上の意味の確定**(人間の決定 2026-10-03)。カード本文には無く、正本と計画書の側に残っている

### 入力: TSK-344(344 タブ)が求める受け入れ条件 — **344 タブの申告・原典は /investigate で確認する(未検証)**

- 要るのは**可否 1 つ**: 次の性質を持つ対象が 12-4 の「実スキーマ」に当たるか否かが、条文から一意に決まること
  - compose の**専用 Postgres インスタンス**(共有開発 DB とはクラスタ実体が別)の上の、名前の付いた 1 データベース
  - 実行のたびに DROP → CREATE → `alembic upgrade head` → 製品コードの `apply_product_authz_ddl` で作り直す
  - **既存データを持たない**
  - 適用は製品コードの入口 1 つだけを通る。試験は既存 17 本(node 48 件)をそのまま実行する
- 「本番相当」の語を入れるなら、上の 4 性質のどれが必須でどれが任意かが分かる形にする(曖昧だと TSK-344 側で再び判断が割れる)
- 典拠として挙がったもの:
  - `docs/ops/product-rls-real-schema.md:18-28`(実測の記録とゲート通過の判定は別)
  - `docs/features/product-authz-surface/design.md:652`(「実スキーマ」の意味を定義しない — TSK-382 の判断を先取りしない。**意味の確定を送った根の典拠**)
  - `docs/features/product-rls-boundary-tests/plan.md:64`・`:435`・`:567`・`:589`
  - `docs/adr/ADR-004-merge-gate-scope.md:44`
  - worklog: `2026-09-24-product-rls-boundary-tests.md`・`2026-09-13-merge-gate-clause.md`
- 版の順序: TSK-344 は `data-model.md` に触れない。#93(確定ゲート 7 周で先行)と TSK-382 はどちらも `data-model.md` の版を上げる見込み → **#93 → TSK-382 の順が安い見込み(裁定は人間)**
- TSK-344 の現況(申告): ステップ 6 まで完了(コミット前)。専用インスタンスで通過条件①②相当を実測済み(適用の違反 0 件・node 48 件 passed)。残りはステップ 7・8

## 決定

## 未決・次の一歩
