---
date: 2026-10-03
topic: TSK-405 U-X1 状況計算核 — 計画段階
branch: feature/ux1-game-state-core
---

# 作業ログ: 2026-10-03 TSK-405 U-X1 状況計算核 — 計画段階

## やったこと

**`/investigate` を 4 本(spec-checker / legacy-analyst / decision-tracer / Explore)。**
**結果は「実装計画の下調べ」ではなく「`ADR-003` 見直しトリガー 1 への反例集」として
[research.md](../features/ux1-game-state-core/research.md) に統合した。**

### 当方が原典・資産で直接実測したもの(2026-10-03)

| 対象 | 測り方 | 結果 |
| --- | --- | --- |
| `model.schema.json`(`origin/feature/domain-calc-dsl`) | JSON として読み `$defs` 35 件の `required` / `properties` / `additionalProperties` を機械列挙 | `Expression` は 8 分岐・条件ノードなし / `GuardRule.expression` は `ComparisonExpression` 固定 / `OutputField` 7 キーに `expression` なし / `ReferenceExpression` は `fieldRef` 1 個のみ / `ExtremumExpression` は値を返す / `ReducerRule.initial` は定数 |
| `pregen_checks.py` | 該当箇所を読む | 同一イベントの遷移 2 本は `count > 1` で「複数の遷移が成立し決定的でない」 |
| `guardRefs` の結合規則 | `git grep guardRefs -- backend/src` | **0 件**(連言か選言かを読む実装が無い) |
| `domaingen/core.py` | `rules` / `outputs` / `states` / `events` を grep | 中間表現に入るのは `displayRules` のみ |
| `backends/{python,typescript}.py` | 同上 | **0 件**(固定スタブ)。`sql.py` は `COALESCE(SUM(...))` の固定文字列 |
| `TSK-235` のステップ 53〜57 | ステップ表を読む | CI 配線 / lock / 文書同期 / `core-guard` 基線 / `core-areas.json` 登録。**生成を作るステップは無い** |
| トリガー 1 の裁定記録 | `review-trigger-evidence.json` の `manualDecisions` | `fired: false` / `2026-09-19` / 証拠は `model.schema.json` / 記録は 1 件のみ |

## 決定

**本タスクの成果物を「実装計画書」から「トリガー 1 への反例集」へ切り替える**(人間の承認 2026-10-03)。
`U-X1` は `../features/product-impl-unit-split/plan.md:396` により**条文上まだ着手できない**ため、
コードを 1 行も追加しない。**提出時期(`TSK-235` のマージ前か後か)は人間の判断事項として残す。**

## 自己是正

| 件 | 内容 |
| --- | --- |
| **行番号の取り違え** | `ADR-003` の「この段階では対象計算のコードを追加しない」を `:388` と書いた。**実在行は `:377` と `:441`** で、`:388` は経過規定の行。`plan.md:396` が与える `:388` が行ずれしており、それを検算せずに引いた |
| **条項の取り違え** | `design.md:1863-1881` の「`U-X1` で必ず再浮上する」を、トリガー 1 の予告として引こうとした。**同節はトリガー 2(結果表示名)についてのもの**で別条項。研究メモ側で明示的に分離した |

## 未決・次の一歩

| # | 事項 | 送り先 |
| --- | --- | --- |
| 1 | **ステップ 30 でトリガー 1 を再評価したか** | `TSK-235` 担当へ照会中 |
| 2 | **トリガー 1 を発火させるか** | **判定者は山田正輝**。本書は材料のみ |
| 3 | **段階 2 の生成経路の所有者が不在** | 起票が要る |
| 4 | **FR-040 / FR-007 / FR-011 の受け皿**・**旧システムの 6 形態** | いずれもエージェントの報告のみで当方未確認。反例の成立には不要 |

## 再開(2026-10-09 — 担当セッション交代)

- 計画承認(2026-10-03)から 6 日空いた。ブランチは `origin/develop` より 565 コミット遅れていたため、`origin/develop` = `0bbf3be6d90b5f0d2aae55946e919290ba0c7d2a` を取り込んだ(衝突なし。本ブランチの差分は `docs/features/ux1-game-state-core/**` と本 worklog だけ)
- **前提の再測**(証拠の基準 `0492b9af` → `0bbf3be6`、`git diff --stat 0492b9af 0bbf3be6 -- <path>`):

  | 資産 | 結果 |
  | --- | --- |
  | `backend/domain/**`(`model.schema.json`・`review-triggers.json` を含む) | **差分なし** |
  | `backend/src/pitchlog/domaingen/**`(`pregen_checks.py` を含む) | **差分なし** |
  | `docs/features/domain-calc-dsl/design.md` | **差分なし** |
  | `docs/adr/ADR-003-domain-calc-method.md` | **差分なし**(`:377` / `:441` の凍結条項・見直しトリガー第 1 項はそのまま) |
  | `docs/requirements/requirements-pitchlog-2026-07-22.md` | **差分なし**(`FR-004:224`・`NFR-019:930`・付録B-6 `:1208` はそのまま) |
  | `docs/features/product-impl-unit-split/{plan,design}.md` | **差分なし**(`plan.md:396` の凍結はそのまま) |
  | `contracts/**` | 43 ファイル変更。**内訳は `authz/`・`tenant_boundary/`・`db/schema-manifest.json`・`migrations/seed-allowlist.json`・`seeds/roster-status.json`(在籍区分)だけ**。DSL・付録 E のゴールデンベクタ・付録B-6 の領域シードには触れていない |

  → **計画の前提はすべて成立している。** 証拠の基準 `0492b9af` を据え置き、ステップ 1 へ進む(PO 了承 2026-10-09)
- **DoD の検査コマンドの読み替え**: DoD・6 節の `git diff 0492b9af...HEAD -- backend/ frontend/ contracts/` は、develop を取り込んだ後は develop 側の変更(127 ファイル)まで拾い、「本ブランチが製品コードに触れていない」ことを測れなくなった。**本ブランチの差分は `git diff origin/develop...HEAD -- backend/ frontend/ contracts/` で測る**(取り込み直後の実測 = 空)。計画書の文言の是正はステップ 8 の敵対レビューで扱う
- **U-S1(TSK-391)からの申し送り**(Notion 2026-10-08 — `ProjectionPort`・`ContentValidationPort` の本物の実装と、投影の表への DB トリガの検討): **U-X1 を実装する段階の事項で、本タスク(製品コードを書かない)の射程外**。U-X1 の実装計画へ引き継ぐ(カードのコメントが残っている)
- 未決 1(ステップ 30 でトリガー 1 を再評価したか)は計画レビュー 1 周目で解消済み(`design.md:1532-1544` に PO 裁定が実在)
