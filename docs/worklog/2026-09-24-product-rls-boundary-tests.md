---
date: 2026-09-24
topic: 製品テーブルの RLS 適用と越境テスト(TSK-344)
branch: feature/product-rls-boundary-tests
---

# 作業ログ: 2026-09-24 製品テーブルの RLS 適用と越境テスト(TSK-344)

## やったこと

- **着手**(/task-start)。`origin/develop` = `bf8ba5b` 起点で worktree を作成。TSK-344 は担当者・プロジェクトが揃っていたため起票せず、進行中への遷移とブランチ名のコメント記録のみ
- **TSK-381 の調査成果 274 行を持ち込んだ**([research-dod-revision.md](../features/product-rls-boundary-tests/research-dod-revision.md))。
  出所はブランチ `feature/tsk344-dod-revision` のコミット `cb889a8`。**同ブランチは origin に存在せず消失の危険があったため、着手前に push して保全した**

## 決定

- **slug をカード名ではなく実体に合わせた**(`product-rls-boundary-tests`)。カードは「越境テスト**再実行**」だが、
  実測では `backend/migrations` に `ROW LEVEL SECURITY` が **0 件**・既存の越境テストは全部 probe テーブル向けで、
  実体は「**RLS を製品テーブル 20 数枚へ展開 + 製品テーブルの越境テストを新規作成**」である

## 追記: 計画段階の調査(/investigate)

調査サブエージェント 3 本(spec-checker / decision-tracer / Explore)を並列委任し、**結論に効く事実は当方が原典で再実測**して
[research.md](../features/product-rls-boundary-tests/research.md)(236 行)へ統合した。
`legacy-analyst` は使っていない — RLS とロール設計は旧システムに対応物が無く、旧資料から引ける事実が無いため。

### ⚠ 着手時に書いた射程が誤りだった

**「実体 = RLS を製品テーブル 20 数枚へ展開 + 製品越境テストを新規作成」は誤り。** 既決は:

- **作成と初回実行 = TSK-424**(使い捨てクラスタ)/ **TSK-344 = 実スキーマで再実行**
  (`tenant-boundary-enforcement/design.md:341-345` の逐語「**『再実行』である以上、作成と初回実行はこちら側にある**」)
- **適用経路は migration ではない**(同 `:327-333`)。適用器は `apply_authz_ddl`。
  → **`backend/migrations/` の差分 0 行**を不変条件に置く。足すと TSK-343 の `D7` と U-T1 の設計判断に逆行する

**誤りの原因**: 着手時に `docs/worklog/2026-09-19-post-public-doc-sync.md` の申し送り (5) だけを読み、
**U-T1 設計書の切り分け(`design.md:335-345`)と TSK-424 の計画書を当たらなかった**。
申し送りは「TSK-317 の成果に製品展開が含まれない」という事実としては正しいが、
**その先を誰が持つか**については 424 への移管を反映していなかった。

### 実装に直結する実測

- **本番適用経路が存在しない** — `apply_authz_ddl` の呼び出しは**すべて `backend/tests/` から**(製品コードからは 0 件)
- **probe の述語を製品へコピーできない** — probe は `::BIGINT`(DDL に「probe fixture で決定的な値を簡潔に扱える BIGINT とする」と
  TYPE-DESIGN が明記)、製品は `Uuid(as_uuid=True)`。**製品述語は `::UUID`**
- **`provisioned_catalog` は probe 専用**。製品表とロールを同居させる fixture は新設が要る
- **テスト基盤の制約が資産で固定**: `backend/tests/db/` 配下・`requires_db` マーカー・**pytest 呼び出しは 1 回**

## 未決・次の一歩

- **人間の裁定が要る 3 件**(plan.md 7 節): ① **本タスクの実体をどう確定するか**(条文に矛盾が埋まっている)
  ② **認証テーブルの RLS の帰属**(決定が存在しない) ③ **最低要求 4 件の線引き**(②③④の所有は U-C1 / U-C3 / U-A2)
- **本タスクは TSK-424 の完全な下流**(PR A + PR A2)。**計画段階は並行して完走できる**
- 上記が決まってから /plan で計画書を起草する
