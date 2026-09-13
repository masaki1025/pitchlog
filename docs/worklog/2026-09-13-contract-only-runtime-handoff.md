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

---

## 裁定結果表(終着区分つき)— ステップ 2(2026-09-13)

**前例**: `2026-09-02-decision-sheet-ruling.md` の裁定結果表。
**終着区分**: **(a)** 既存正本アンカー / **(b)** 本 PR で正本へ反映 / **(c)** 正本パス・節・ゲートを DoD に持つ後続タスク。

### 群ごとの裁定(**152 owner / 158 claim 行・保留 0・未解決 0**)

| 群 | owner | 受取先 | 終着区分 | 送り先の実 ID / 射程行 |
| --- | --- | --- | --- | --- |
| `A_SET`(製品機能の実装タスク)| **139** | `PENDING:FR-nnn` 12 種 | **(c)** | **未起票**(裁定 `C` により各 FR の実装タスクが持つ。`../features/course-coordinate-contract/plan.md:350` の前例に従い相互リンクを求めない)|
| `B_SET`(対象横断の判定とハーネス)| **10** | `TSK-217` | **(c)** | [TSK-217](https://app.notion.com/p/3bc93b75e68781f2a613d791db2231ab) |
| 復旧手順 | **2** | `PENDING:TASK-RECOVERY` | **(c)** | [復旧手順タスク](https://app.notion.com/p/3da93b75e687818da3aac516470d8c40)(**本タスクで起票**)|
| 要件書の穴 | **1** | `PENDING:TASK-REQ-LABEL` | **(c)** | [要件書改訂タスク](https://app.notion.com/p/3da93b75e68781fb978fedba7ef499e0)(**本タスクで起票**)|
| **合計** | **152** | — | — | — |

### 引き渡しの実値(**射程確認の結果を含む**)

**台帳 `../development/harness-evaluation.md:2365-2410` の「送り先が空手形になる」型を踏まないため、
送り先ごとに「その射程が当該項目を受け取れるか」を確認した。結果は 1 件が不十分だった。**

| # | 送り先 | 追記した URL | 射程確認の結果 | 確認者 |
| --- | --- | --- | --- | --- |
| 1 | **TSK-367**(自カード)| `discussion://…3da93b75-e687-817b-b400-001ce950214d` | — | Claude |
| 2 | **TSK-217** | `discussion://…3da93b75-e687-81bc-9a3b-001cfe867eb6` | **不十分** — カードの「スコープ」節が明記するのは **10 件中 4 件**。カードは 2026-08-14 作成で**裁定 `C`(2026-09-12)より前**のため、裁定 C が与えた「対象横断の判定とハーネスの所有者」という役割に追随していない。**射程の拡張を依頼した** | Claude |
| 3 | **TSK-317**(PR #3)| `discussion://…3da93b75-e687-8163-94f3-001cc24c8fee` | **射程内**(`S-9` / `S-10` が PR #3 — `../features/pg-authz-verification-g2/plan.md:226, :231`)。**ただし分担の明文化は先方が未記載**(同書に `TSK-367` の出現 0 件)→ **完了の前提として残す** | Claude |
| 4 | **TSK-380** | `discussion://…3da93b75-e687-815c-9407-001c71a5ae72` | **射程内**(`ADR-004:46` = 37 経路の `test_owner` 再割り当て方式)。**行の衝突 0 件**を実測して伝達 | Claude |

### PO 裁定(2026-09-13・山田正輝)— 保留 5 owner を全件解消

| owner | 裁定 | 根拠 |
| --- | --- | --- |
| `SECTION-4.0-2/list_item-001` | **`TSK-217`** | 横断不変条件。`NFR-010`「全機能に適用」と同性格で、それらを `TSK-217` へ入れて本件だけ外すのは不整合 |
| `SECTION-6.2/list_item-003` | **`FR-041`** | 本文が「うち後半 6 件は共同分析グループ(`FR-041`)に伴うもの」と明記。在籍区分変更を含める理由も `FR-041` 基準で説明 |
| `SECTION-8/list_item-006` | **復旧手順タスク**(新規)| 12-4 の定義上「入口を開く」に当たらず裁定 `C` の規則が当たらない。越境行列でも横断ハーネスでもない |
| `NFR-009/list_item-004` | 同上 | **同じ復旧ライフサイクル**(記録権世代の失効と新世代発行 + `FR-012` の端末イベント回収)を記述 |
| `SECTION-4.0-3/table_row-003` | **要件書改訂タスク**(新規)| 対応する FR 条項が要件書に存在しない(`grep "ラベル語彙"` のヒットは `:100` Won't と `:169` 4.0-3 のみ)|

### 再現手順(**数値を定数で持たない**)

```python
import json, re, collections
cm = json.load(open('contracts/authz/claim-mutant-map.json'))
g  = [c for c in cm['claims']
      if c['execution_class'] == 'contract_only'
      and c['receiving_task_id'] == 'TSK-270-GROUP-2']
own  = {c['runtime_test_owner']['id'] for c in g}
base = [o[len('TSK-270.group2.runtime.'):] for o in own]
sh   = collections.Counter(c['runtime_test_owner']['id'] for c in g)
# claim 158 / owner 152 / 共有 6 組 / override 母数 46
```

**2026-09-13 の実測**: claim 行 **158** / owner **152** / 共有 **6 組** /
FR 接頭辞で宛先を返さない owner **46** / `TSK-270-GROUP-2` 全体 **178**(= `contract_only` 158 + `probe_executable` 20)。

## 決定

- **射程 A(縮小)** — 実装・検査・資産置換をすべて TSK-317 の PR #3 へ送る。
  **資産に `TSK-270-GROUP-2` が 178 件ある以上、`PENDING:` の文法検査の導入と 158 行の置換は
  同一コミットでしか成立しない**(敵対レビュー 2 周目 `P1-6`)
- **規則の主キーは FR/NFR 接頭辞ではなく「認可判定が執行される入口を開く FR」** —
  接頭辞は既定値にすぎず、`FR-034` の 51 owner のうち 48 が `FR-041` へ寄る
- **`R-C` は振り分け規則ではなく注記** — 契約上「runtime テストを持たない終着」は存在しない
  (`execution_classes` は閉じた 2 値 / `contract_only_runtime_rule` = `runtime_kill_forbidden_handoff_test_required`)

## 未決・次の一歩

- **`TSK-217` の射程拡張**(10 件中 6 件がカードの射程に明記なし)— 先方の対応待ち
- **`TSK-317` との分担の明文化** — **本タスク完了の前提**。PR #3 の改訂 4 で受け取り形が書かれるのを待つ
- 次は `/pr`(クローズ処理 → 突合 → push → PR 作成)。**コア領域なので PR 本文の人間逐行確認チェックが要る**
