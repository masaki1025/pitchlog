---
date: 2026-09-13
topic: contract_only 158 行の runtime テスト受取先を決める(TSK-367)
branch: feature/contract-only-runtime-handoff
---

# 作業ログ: 2026-09-13 contract_only 158 行の runtime テスト受取先を決める

## やったこと

### 着手前の実測(develop `478a026`・2026-09-13)

**資産の所在**: `claims` / `execution_class` / `runtime_test_owner` / `receiving_task_id` は
**`contracts/authz/claim-mutant-map.json`**。**Notion カードと TSK-317 の申し送りが書く `auth-catalog.json` は誤り**
(後者は `catalog_entry_id` と `catalog_test_owner` / `enforcement_test_owner` を持つ別資産)。

**母集団**:

| 区分 | 行数 |
| --- | --- |
| `claims` 全体 | 198 |
| `execution_class: contract_only` | **165** |
| うち `receiving_task_id: TSK-270-GROUP-2`(プレースホルダ = 未確定)| **158** ← 本タスクの対象 |
| うち `receiving_task_id: TSK-217`(確定済み)| 7 |

→ **「contract_only が 158 行」は不正確**。正しくは「**`contract_only` 165 行のうち受取先が未確定の 158 行**」。

**158 行の内訳**:

- 一意 `runtime_test_owner.id` = **152**(共有 **6 組 × 2 行** = 余剰 6 参照)
  ※ 申し送りの「8 組 / 重複 11」は**全 198 行**での数字。**158 行の中は 6 組 / 6**
  (計画書の `S-10` 論点 (5) も「6 組の共有」と書いており、そちらが整合する)
- `contract_only_reason_code`: `route_universe_pending` **157** / `no_db_decision_point` **1**
- `classification_rule_id`: `CONTRACT_ONLY_RUNTIME_TARGET_PENDING` 157 / `CONTRACT_ONLY_NO_DB_DECISION_POINT` 1
- `runtime_test_owner.status`: 全 158 が `planned`
- `runtime_evidence_kind`: 全 158 が `handoff_runtime_test`
- `auth-catalog.json` 突合の `route_scope_id`: `SCOPE:DATA_READ` 79 / `SCOPE:CONTROL` 50 /
  `SCOPE:ALL_LOGICAL` 28(計 157)+ **突合不能 1**

**不変条件の再確認**: 同一 `runtime_test_owner.id` を共有する行の `receiving_task_id` は一致 — **全 8 組で成立**。

### 唯一の構造的な係争点 — 1 行

**`FR-041/list_item-014#request-validation`** が**3 軸すべてで外れる**:

1. 理由コードが `no_db_decision_point` — **158 内で唯一**。既定 `TSK-217` の 7 行と同じ分類
2. `auth-catalog.json` に entry が無い — **158 内で唯一**。したがって `route_scope_id` を持たない
3. `runtime_test_owner.id` = `TSK-270.group2.runtime.FR-041/list_item-014` を
   `FR-041/list_item-014#participant-authorization`(`route_universe_pending`)と**共有している**

**分類上は `TSK-217` へ行く顔をしているのに、不変条件が受取先の分離を禁じ、ID 共有の解消も禁じられている。**
既定 `TSK-217` の 7 行はすべて `TSK-217.runtime.*` の専用 owner を 1 対 1 で持ち**共有が無い**ので、
**この 1 行だけが構造的に浮いている**。**PO 裁定に上げる候補**。

### 裁定 A・B の帰結(有力仮説 — 要検証)

**原典**: `feature/merge-gate-clause`(`96d0f86`・PO 承認済み未マージ)の
`docs/design/data-model.md` 12-4「経路と入口の定義」。

- **判定・測定・記録の単位は「入口」**(HTTP なら **method と path の組**)。
  「経路」は同じ `route_id` を持つ入口の集合で、**`route_id` と入口は 1 対 1 に対応しない**
- **裁定 B**: **入口を開く PR は同一 PR にその入口を外から直接叩くテストを含む**
- HTTP 以外の入口について明文で「**別タスクへ送らない — 送ると、識別子が無いまま入口だけが開く**」

→ **仮説**: `route_universe_pending` **157 行**の受取先は **`TSK-217` でも `TSK-344` でもなく、
その入口を開く製品機能の実装タスク**(カードの候補 3)。
理由コードの字面(経路の母集合が未確定)と裁定 B が同じ方向を指す。
**`TSK-344` は「実スキーマでの越境テスト再実行」であって入口を開く PR ではない**ため、
現時点で `TSK-344` が受けるべき行は **0 件**と見ている。

**未検証**: `http-route-matrix.json` の `routes` **37 件**と 157 行の解像度が合うか
(`route_scope_id` は 3 値しかなく、入口単位の受取先を決めるには粗い)。

### 不変条件は**機械検査されていない**(master タブの主張を実測で否定)

master タブから「不変条件は TSK-317 の計画書ステップ 1 の合格条件として機械検査されており、
負例も入っている」と申し送られたが、**原典で不成立**。

- `scripts/check_authz_catalog.py` の `receiving_task_id` は **2 箇所だけ** —
  **3757 行**(必須キーの列挙)と **3867 行**(`contract_only` 行について `_expect_string` = **非空文字列判定のみ**)。
  **同一 `runtime_test_owner.id` でグルーピングして一致を見る処理は無い**
- `tests/test_check_authz_catalog.py:3374/3384` の `TSK-217` / `TSK-270-GROUP-2` は
  `test_all_claim_execution_classes_reject_the_opposite_class`(**probe/contract 反転の負例**)の随伴データであり、
  **不変条件の負例ではない**。`tests/` 全体でも `receiving_task_id` の出現はこの 2 行とフィクスチャ 1 件のみ
- TSK-317 改訂 3 第 2 弾(PR #2)のステップ 1 は `core-areas.json` への登録で、**不変条件に触れていない**
- **計画書 711 行の `S-10` が、この検査を「第 2 弾で確定すべき論点」として列挙している** —
  **論点 (2)**「現行検査器 `check_authz_catalog.py:3803` は**非空文字列しか見ない**」/
  **論点 (3)**「同一 `runtime_test_owner.id` の行が同一受取先を持つことの**検査**」(`S-9` ① の不変条件)

→ **不変条件は現時点では「データが満たしている観測された性質」であって「機械が強制している制約」ではない。**
**強制するのは PR #3 がこれから書く検査。**

**PO へ上げるときの含意**: 3 択(不変条件に例外を作る / 共有 ID の側を動かす / 分類を `TSK-217` 以外にする)は
維持されるが、**どれを選んでも既存検査の変更は発生しない**(検査がまだ無いため)。
**PR #3 が論点 (3) の検査を書くときに、例外を持つ形で書くかを選ぶだけ**であり、
**コア領域の既存検査を弱める重さはかからない**。

## 決定

## 未決・次の一歩

- **上記仮説の検証**(`/investigate`)— `route_scope_id` → `route_id` → 入口の解像度
- **master タブ `TSK-381`**(`TSK-344` の DoD を裁定 A・B に合わせて見直す)の結論待ち。**仮説を共有済み**
- **`TSK-217` の前提訂正タスク**(「実装が先」→「実装 PR と同一変更」)の結論 — 上記仮説と整合するはず
- **係争点 1 行**の扱い(PO 裁定に上げるか)
