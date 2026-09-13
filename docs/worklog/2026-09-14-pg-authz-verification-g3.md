---
date: 2026-09-14
topic: TSK-317 改訂 4(PR #3)— 引き渡しの ID 完全性と受取契約
branch: feature/pg-authz-verification-g3
---

# 作業ログ: 2026-09-14 TSK-317 改訂 4(PR #3)

Notion: [TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)(**進行中**)。
計画書: `docs/features/pg-authz-verification-g2/plan.md`(**改訂 4** — 同じ文書の続き)。

## ブランチ名と計画書ディレクトリが一致しない(**意図的**)

| | |
| --- | --- |
| ブランチ | `feature/pg-authz-verification-g3` |
| 計画書 | `docs/features/pg-authz-verification-g2/plan.md` |

**`feature/pg-authz-verification-g2` は origin に残っている**(PR #52・#59 でマージ済み)ため
同名で切れない。**計画書は改訂 4 として同じ文書を継ぐ**ので、ディレクトリは分割しない(7.1-1)。

**機構への影響**: `codex_run.py` が検証するのは **worktree の実ブランチと frontmatter `branch` の一致だけ**
(`:414`)で、**ディレクトリ名とは突合しない**。**`feature_status.py` も frontmatter の `branch` で照合する。**
**ただし `/pr` の `check_plan_docs_sync.py` は `--plan` 省略時にブランチ名から導出するので、
本タスクでは `--plan docs/features/pg-authz-verification-g2/plan.md` を明示する。**

## 改訂 4 の射程(**前改訂が送ったもの** — `D-14` `D-15`)

| 項目 | 内容 |
| --- | --- |
| **`S-2`** | 論理 ID → node ID(187 + 310 参照)・status 更新 |
| **`S-3`** | 要件側 7 単位の source |
| **`S-4`** | 引き渡しマニフェストの ID 完全性 |
| **`S-6`** | 受取契約・read-back・製品 adapter の事前凍結 |
| **`S-9`** | `claim-mutant-map.json` の受取先 178 件(裁定 `D-15`) |
| **`S-10`** | `contract_only` 158 行の受取契約・9 論点 |
| **`S-8` の一部** | 引き渡し 3 資産のパスと版・digest + `test_ci_wiring.py` の追記 |

## 着手時点で分かっている入力(**すべて develop `569954d` で確認済み**)

### TSK-367 が確定した規則(**正は `docs/features/contract-only-runtime-handoff/plan.md` 2 節**)

- **152 owner / 158 claim 行**・**`B_SET`(TSK-217)10 / `A_SET` 142**・**保留 0・未解決 0**
- **規則 3 本**: `R-A′`(認可判定が執行される入口を開く FR。`claim_id` の接頭辞は既定値にすぎず、
  その FR が入口を開かない場合は執行先へ寄せる)/ `R-B`(対象横断の判定とハーネスは TSK-217)/
  `R-C`(**注記**であって振り分けではない — `C-ABSENCE` / `C-ACCEPTED-RISK` / `C-PRECONDITION`)
- **override 表 46 owner**(FR 接頭辞が宛先を返さない owner の全件)を逐行で確定

**数値はそのまま使わない** — **資産から再導出して一致を確認してから書く**。
**TSK-367 自身が列挙型の取りこぼしを 2 件出している**(override 表を 32 と書いて実数 46 /
`B_SET` を 9 と書いて実数 11)。台帳の候補「母集団を人が列挙する検査は、射程が動くたびに黙って古くなる」。

### 実装で要る仕様

- **文法**: `TASK_ID ::= "TSK-" [0-9]{3}` / `PENDING_REF ::= "PENDING:" (("FR"|"NFR") "-" [0-9]{3} | "TASK-" [A-Z-]+)`。
  **`TSK-270-GROUP-2` は文法から外れるので、置換後に残っていたら red**
- **参照整合は要件書の `FR`/`NFR` 条見出しから導出**し、**件数を定数で持たない**。
  **母集団は `^#### (FR|NFR)-[0-9]{3}` にマッチする見出し = 65 件**(FR-001〜042 の 42 + NFR-001〜023 の 23)。
  **「見出し 65 件」と縮約して書いてはいけない** — **要件書の見出し総数は 125 件**
  (`#` 1 / `##` 17 / `###` 34 / `####` 69 / `#####` 4。`requirement-claims.json:141` の
  `item_counts_by_kind.heading` も 125)。**限定を落とすと母集団が 2 倍になる**(2026-09-14 に是正)。
  **なお 65 は既に 2 箇所に定数として存在する**(`scripts/design_relations/req-universe.json:10` の
  `categories.requirements.count` と `tests/test_check_doc_coverage.py:176`)が、
  **これは `contracts/authz/` とは別系統の oracle 定数**であり、**両者を突合した記述は見つかっていない**
- **対象集合は `contract_only` のみ**。**`probe_executable` に `PENDING:` があったら red**(`S-9` ② で受取先が TSK-317 に確定)
- **置換義務は 2 方向**: 入口を開く PR が**自分の開いた入口に対応する owner だけ**を実 ID へ置換し `--reseal-oracle`。
  **過少(残したままマージ)も過剰(開いていない入口の owner を置換)も red**
- **文法検査の導入と 158 行の置換は同一コミット**(資産に `TSK-270-GROUP-2` が 178 件ある以上、
  検査だけ先に入れると即 red)

### `PENDING:` の 2 種類を混同しない(**2026-09-14 に訂正を受けた**)

**区別は「起票済みか」であって「着手済みか」ではない。**

| 種別 | 件数 | PR #3 での扱い |
| --- | --- | --- |
| **`PENDING:FR-nnn`** | 139 owner | **`PENDING:` のまま残す**。FR 実装タスクは**1 件も起票されていない**(裁定 C により起票は各 FR の着手時)。置換は**入口を開く PR** が行う |
| **`PENDING:TASK-RECOVERY` / `PENDING:TASK-REQ-LABEL`** | **3 owner** | **実タスク ID へ解決する**。**TSK-367 が 2026-09-13 に起票済み**(カード実在) |

**解決先**: `SECTION-8/list_item-006` と `NFR-009/list_item-004` →
[バックアップ復元の復旧手順](https://app.notion.com/p/3da93b75e687818da3aac516470d8c40) /
`SECTION-4.0-3/table_row-003` →
[ラベル語彙の FR 新設](https://app.notion.com/p/3da93b75e68781fb978fedba7ef499e0)。
**TSK 番号が未採番なら Notion UUID を値にしてよい**(前例: `boundary-proposal.json:14` の
`aggregation_owner_task_id` = `3d993b75-e687-818d-8cb8-ec57508e73e0`)。

**typo の層を分けて記録する**: **`receiving_task_id` の解決**は起票済みなので PR #3 でできる /
**runtime テストの実装**は着手済みが要るのでまだできない。**前者が PR #3 の射程、後者は受取タスクの射程。**

### 封印手順のコマンド(**2026-09-14 に実測で是正**)

**`--skip-derived` / `--skip-oracle` というオプションは存在しない。**
`check_authz_catalog.py` にあるのは **`--reseal`(`:5000`)/ `--reseal-derived`(`:5005`)/
`--reseal-oracle`(`:5010`)の 3 つだけ**(`:4851` の `dedicated_flag` も `--reseal-oracle`)。

**段 2 = `--reseal` のみ / 段 4 = `--reseal-derived` のみ / 段 7 = `--reseal-oracle` のみ。**

**`input_assets` の重複拒否は PR #2 で塞がれている** — `_validate_object_path_uniqueness` が
`:556` に実在し `:4775` で `oracle seal.input_assets` に対して呼ばれる。
**前改訂が「既知の穴」としていた件は解消済み。**

## 是正が要る 4 件(**TSK-367 からの申し送り**)

1. **`S-10` の (8)(9) は `PENDING:` 行について成立しない**(read-back の相手も受取側の DoD も存在しない)。
   → **「`PENDING:` でない行の集合への exact-set 突合」+「入口を開く PR が同一 PR で自分の owner を置換する義務の検査」へ置き換える**
2. **`plan.md:231` の「受取タスクは起票済み」は `S-10` については誤り**
   (典拠: `merge-gate-api-cycle/research.md:362`「製品 HTTP 経路(API)の実装 = なし」)
3. **`S-10`(4) の「TSK-217 の 7 件」→ 7 + 10 = 17**(既存 7 件〔`no_db_decision_point`〕と本タスクが足す 10 件は互いに素)
4. **`contract_only_reason_code` の新設は定数追加では足りない** — 値集合は閉じた 3 値(`:118`)だが、
   **検査器は期待値を導出する**(`:3818` の `_has_db_decision` → `expected_reasons`)。
   **対象 owner の明示集合を入力にして導出ロジックまで変える必要がある**

## 改訂 4 で明示が要る 2 件(**TSK-367 が意図的に崩したもの**)

1. **`no_db_decision_point` → TSK-217 の 100% 一致を崩した**
   (`FR-041/list_item-014#request-validation` を FR-041 へ回すため)。
   **`_has_db_decision` を見た実装者が矛盾と誤認しないよう明示する。**
   **そもそもこの写像を定めた文書は見つかっていない。**
2. **既定 7 行が TSK-217 である根拠がカード本文の説明と実データで合っていない** —
   カードは「404/400/存在秘匿の同値性」とするが、**`source_text` を読むと存在秘匿は 1 行だけ**で、
   残りは**レート制限 2・認証構成の補足 1・トークン失効 1・PW ポリシー 1・人手の復旧経路 1**

## 射程宣言へ入れる 3 点(**TSK-367 からの依頼**)

1. `contract_only` 158 行(152 owner)の**受取先の規則は TSK-367 が確定済み**
2. **PR #3 はその規則を消費して `claim-mutant-map.json` へ書き写す側**
3. **規則の正は `docs/features/contract-only-runtime-handoff/plan.md` の 2 節**(develop にマージ済み)

**TSK-367 は依頼を残したまま PO 判断で閉じた**(2026-09-13)。
**台帳の候補「送り先が空手形になる」に TSK-367 が反例として名指しされている**ので、
**書かないと反例の位置づけが弱まる。**

## 順序の制約

```
TSK-348(済)→ TSK-317 PR #1(済)→ TSK-343(済)→ TSK-317 PR #2(済)
  → TSK-355 → **本タスク(PR #3)** → TSK-235
```

**PO 裁定 2026-09-12。** **待つのはマージだけで、計画・実装は先行できる。**

### TSK-355(`adr003-bootstrap-transition`)の状態(**2026-09-14 に当人から受領**)

**確定ゲート 4 周目・未マージ。`P0` は 4 周連続ゼロ、件数 9 → 7。**
**射程縮小したのは条文の内容であって対象文書ではない** — **要件書 `NFR-018` の達成条件 (e) 新設は射程に残る**。
**したがって要件書の blob は動き、`requirement-claims.json` の digest も動く。**
**本タスクを TSK-355 の後に置いた根拠はそのまま生きている。**

**`確定ゲート周回` が 6 に達したら PO へ提示する規定**(7.3-6)で、そのとき共有が来る。

### TSK-386(`fix/oracle-input-baseline`)との干渉 — **未決**

**本タスクは `auth-catalog.json`(入力資産)を変えて `--reseal-oracle` を回す。**
**TSK-386 は `ORACLE_INPUT_BASELINE_COMMIT` の直書き(`check_authz_catalog.py:107`)の恒久解**で、
**封印の基準点の決め方そのものを変える。** **どちらが先かで、もう片方が作り直しになりうる。**

**担当セッションは `session_01VuxQorz5FMmci7J6mB3UnF`**(TSK-379 と同一 — **PO 指示で続けて持っている**)。
**`ListAgents` のタブ名と担当はずれているので、`git log -1 --format=%b <branch>` の
`Claude-Session` を突き合わせて判別した。** **`tsk343-orm` へ問い合わせ中。**

## やったこと

1. ブランチ `feature/pg-authz-verification-g3` と worktree を作成
2. 計画書 frontmatter を改訂 4 用へ(`status: active` / `承認: 未` / `branch` 更新)
3. 本作業ログを作成
4. **`/investigate` を 4 本並列で実施**(数値の再導出 / spec-checker / decision-tracer / 資産と検査器の実測)。
   **結果は `docs/features/pg-authz-verification-g2/research.md`(470 行)に統合した**

## 調査の主な結果(**詳細は research.md が正**)

| # | 結果 |
| --- | --- |
| 1 | **数値は全件再現**(`152` / `158` / `178` / `198` / `187` / 共有 8 組 / 非 FR-* `46` / 保留 0)。**ただし `B_SET` 10 / `A_SET` 142 は資産に符号化されていない** |
| 2 | **2 段コミットは機構的に強制される** — **実機で再現**。`--reseal-oracle` は `oracle_commit` を触らないので単独では絶対に閉じない |
| 3 | **`:4798` に fail-open**(`git rev-parse` 失敗時に黙って通る)。**改訂 4 はこの上に合格条件を組まない** |
| 4 | **`U-T1`(TSK-363)の依存に TSK-317 が抜けている** — **未裁定の穴** |
| 5 | **TSK-367 の `plan.md` に 6 件の壊れ**(当人が是正 PR を用意中)。**資産の再導出では検出できない層** |
| 6 | **本計画書の記述が 5 件陳腐化** |
| 7 | **`S-2` の射程の穴** — TSK-270 所有の planned ID が別に **193 参照**残る |
| 8 | **`FR-041/list_item-014` の `reason_code` 分裂**(本調査で発見) |

## 検査を 2 層に分ける(**本調査で得た一般則**)

**資産から取れるのは「いま資産に何が書かれているか」だけで、
「文書が資産に対して何を約束しているか」は資産からは出てこない。**

| 層 | 今回の検出 |
| --- | --- |
| **① 資産からの再導出** | 母集団の件数・分布・不変条件を全件再現。**取り消し漏れは出てこない** |
| **② 文書の内部整合** | **名乗る母数・合計・ラベルが自分の中身と合うか**。**3 件中 2 件を機械で検出**。残り 1 件は人の指摘でしか出なかった |

**改訂 4 は ② を機械化する。**

## 決定

## 未決・次の一歩

1. **`/investigate`** — 資産からの再導出(152 / 158 / `B_SET` 10 / `A_SET` 142 / override 46 / 178)・
   **`U-T1` が引き渡し 3 資産に依存するかの確認**・`S-2`〜`S-8` の実測
2. **`/plan`** — 改訂 4 の射程宣言とステップ表
3. **TSK-386 との順序** — 返事待ち
