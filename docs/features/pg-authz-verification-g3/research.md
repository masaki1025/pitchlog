---
feature: pg-authz-verification-g3
type: research
date: 2026-09-14
---

# 調査メモ: TSK-317 改訂 4(PR #3)— 引き渡しの ID 完全性と受取契約

**ブランチ**: `feature/pg-authz-verification-g3` / **計画書**: `docs/features/pg-authz-verification-g3/plan.md`(**改訂 4** — 同じ文書の続き。**2026-09-14 に `pg-authz-verification-g2/` から移した** — `feature_status.py:1589` が `docs/features/<ブランチslug>/plan.md` を要求し、不一致だと `plan 重複` へ縮退するため)。
**基準**: develop `569954d`。**調査 4 本を並列で実施**(数値の再導出 / spec-checker / decision-tracer / 資産と検査器の実測)。

## 問い

改訂 4 の射程 7 項目(`S-2` `S-3` `S-4` `S-6` `S-9` `S-10` と `S-8` の一部)について、
**他タスクから受け取った数値と主張を、資産とコードから独立に検証する**。
**受け取った値を 1 つも定数として持ち込まない**(台帳の候補「母集団を人が列挙する検査は、
射程が動くたびに黙って古くなる」— TSK-367 自身が同型の取りこぼしを 2 件出している)。

## 結論(要約)

1. **数値は全件再現できた** — `152` / `158` / `178` / `198` / `187` / 共有 8 組 / 非 FR-* `46` / 保留 0。
   ただし **`B_SET` 10 と `A_SET` 142 は資産に符号化されていない**(計画書の手作業分類)。
2. **2 段コミットは機構的に強制される** — **実機で再現した**。`--reseal-oracle` は `oracle_commit` を
   触らないので、`git rev-parse <oracle_commit>:<path>` の検査が必ず落ちる。**単独では絶対に閉じない。**
3. **`U-T1`(TSK-363)の依存に TSK-317 が抜けている** — `data-model.md` が `U-T1` の構成要素 4 つを
   明示的に TSK-317 へ送っている。**未裁定の穴。**
4. **文書側の壊れが 6 件**(TSK-367 の plan.md)。**資産の再導出では検出できない層**であり、
   **数値の再導出と文書の内部整合は別の検査**である。
5. **計画書の記述が 5 件陳腐化**(訂正 4 の 2 値 / `S-10`(7) の `fetch-depth` / `design.md:302` / `S-2` の母集団)。

---

## 1. 数値の再導出(**資産が正**)

### 1-1. 出所の資産名

**`auth-catalog.json` に `claims` キーは無い**(トップは `entries` 187 件)。
**`execution_class` / `runtime_test_owner` / `receiving_task_id` / `contract_only_reason_code` の
出現は 0 件。** 実体は **`contracts/authz/claim-mutant-map.json:55` の `claims`(198 件)**。

**TSK-367 の計画書は正しく `claim-mutant-map.json` と書いている**(`contract-only-runtime-handoff/plan.md:26` `:64` `:317`)。
**誤っているのは同タスクの Notion カード本文と申し送りの文面だけ**で、規則の正には影響しない。
**本計画書が `auth-catalog.json` を入力資産と呼ぶのは `S-2` の 187 件 enforcement の話**であり別物。

### 1-2. 母集団の定義(**すり替えに注意**)

| 集合 | 定義 | 実測 |
| --- | --- | --- |
| `claims` 全体 | `claim-mutant-map.json` の `claims[]` | **198 行 / owner 一意 187 / 共有 8 組・余剰 11** |
| `contract_only` **全体** | `execution_class == "contract_only"` | **165 行 / owner 一意 159 / 重複 6 組** |
| **`U`(本タスクの対象)** | `contract_only` **かつ** `receiving_task_id == "TSK-270-GROUP-2"` | **158 行 / owner 一意 152** |
| 残余 | `contract_only` かつ `receiving_task_id == "TSK-217"` | **7 行 / 7 owner** |

**`158 / 152` は `contract_only` 全体ではなく `U` の値である。**
**計画書は母集団の定義を逐語で書くこと** — **`165` と `158` がすり替わる。**

**`grep` で `execution_class` を数えると 168 / 36 になる罠がある**
(`classification_rules` 6 件が同名キーで宣言しているため)。**構造走査の 165 / 33 が正。**

### 1-3. `receiving_task_id` の分布(全 198 件)

```
TSK-270-GROUP-2  178   (= contract_only 158 + probe_executable 20)
TSK-250           13   (全件が素の TSK-250。サフィックス付きは 0)
TSK-217            7
PENDING:*          0   ← 「PENDING:」というコロン付き文字列はファイル内に 0 件
```

**`TSK-270-GROUP-2` の出現パスは `claims/[]/receiving_task_id` のみ**(部分一致 0)。

> **`grep -c PENDING claim-mutant-map.json` は 158 を返すが、全部
> `classification_rule_id: CONTRACT_ONLY_RUNTIME_TARGET_PENDING`(157)+ 規則宣言 1 であって受取先ではない。**

### 1-4. `contract_only_reason_code`

```
route_universe_pending   157
no_db_decision_point       8   ← 7 が TSK-217 / 1 が TSK-270-GROUP-2
ddl_target_pending         0   ← 定数と expected_reasons にはあるがデータ 0 件
```

**裁定 `D-15` の本文(`plan.md:90`)が「158 行は `route_universe_pending`」と書いているのは不正確**
(実測 157 / 1)。**`S-9` ① が既にこの混在を記録している。**

### 1-5. **不変条件と、報告に無かった残滓**

**同一 `runtime_test_owner.id` を共有する 8 組すべてで `receiving_task_id` は単一値**(破れ 0)。
`execution_class` も `runtime_test_owner.status` も組内で単一。

**ただし 1 組だけ別の軸で割れる**(報告に無い・**本調査で発見**):

**`TSK-270.group2.runtime.FR-041/list_item-014`**(`#request-validation` / `#participant-authorization`)は
**`contract_only_reason_code` が `no_db_decision_point` 1 / `route_universe_pending` 1 に割れる。**
**これが「`no_db_decision_point` 8 件のうち 1 件だけ受取先が `TSK-270-GROUP-2`」の正体である。**

**`receiving_task_id` の不変条件は保たれているが、owner 単位で `reason_code` を畳むと衝突する唯一の owner**。
TSK-367 の計画書 `:87`「行ごとの判定が割れたら即エラー」を `reason_code` にも当てると引っかかる。
**改訂 4 の設計判断が 1 つ増えた。**

### 1-6. `B_SET` / `A_SET` は資産に無い

**受取先の値域は `TSK-217` / `TSK-250` / `TSK-270-GROUP-2` の 3 値のみ。**
**`B_SET` 10 は計画書の手作業分類**で、**資産の `TSK-217` 7 行とは共通要素 0 の別母集団**。

- **`B_SET` 10** = 「`U` のうち将来 TSK-217 へ回す予定の 10」(10 owner とも `U` に実在・claim 行 1:1)
- **資産の 7** = 「既に TSK-217 に付いている 7」

**`10 ≠ 7` は矛盾ではない。** ただし「TSK-217 10」と書くと 7 と衝突して見える。
**置換後は 7 + 10 = 17**(互いに素なので加算が成立 — `S-10`(4) の是正は正しい)。

---

## 2. 封印手順(**コードから導く。計画書の記述は使わない**)

### 2-1. reseal フラグは 3 つだけ

**`--skip-derived`(`:5014`)と `--skip-oracle`(`:5019`)は実在する**(**2026-09-14 に是正** —
**`argparse.SUPPRESS` でヘルプに出ないため、2 セッションが独立に「存在しない」と誤認した**)。
**ただし reseal ではなく検査のスキップ**であり、**`--reseal-*` と同時指定不可**(`:5097-5100`)、
**`--skip-derived` は `--skip-oracle` を要求する**(`:5101`「oracle 検査にはステップ4資産の検査が必要」)。

| フラグ | 定義 | 再計算するもの | 書き出すファイル |
| --- | --- | --- | --- |
| `--reseal` | `:5000` | `requirement-claims.json` の全 `decision_digest` + decision lock | `requirement-claims.json` と `.lock.json` の **2 本** |
| `--reseal-derived` | `:5005` | 導出 3 資産の `asset_digest` / `entry_count` / `entries[]` | `route-registry.lock` / `auth-catalog.lock` / `http-route-matrix.lock` の **3 本**(元資産は書き換えない) |
| `--reseal-oracle` | `:5010` | `input_assets[].git_blob_digest` 8 件 + `sealed_assets[]` 6 行を全面再構築。**`oracle_commit` は既存値をコピー** | `oracle-seal.lock.json` **1 本** |

**3 フラグは同時指定不可**(`:5090-5096`)。**実行して確認済み。**

### 2-2. **2 段コミットが機構的に強制される理由**(実機で再現)

`auth-catalog.json` の `enforcement_test_owner.id` を 1 文字変えて順に回した実測:

| 段 | コマンド | 結果 |
| --- | --- | --- |
| 1 | フラグ無し | `decision lock と不一致: catalog:CATALOG:SECTION-1.1/paragraph-002` |
| 2 | `--reseal-derived` | **`auth-catalog.lock.json` は書き換わる**が、**同じ実行の oracle 段で落ちる**(`oracle input blob が不一致`) |
| 3 | `--reseal-oracle` | `oracle commit 上の blob が不一致`。**`oracle-seal.lock.json` は 1 バイトも書かれない** |

**原因**: `auth-catalog.json` は **oracle の入力 8 資産の 1 つ**(`:4800-4810` の `required_input_paths` に exact-set)。
`validate_oracle_seal` の入力検査(`:4776-4799`)は **2 段** — ① worktree の blob == seal の digest
② **`git rev-parse <oracle_commit>:<path>` の blob == seal の digest**。
**`_build_oracle_seal` は ① を打ち直すが `oracle_commit` を触らないので ② が必ず落ちる。**

**`oracle_commit` に「これから作るコミット」を指定できない。**
これが 2 段コミットの機構的な理由であり、**`oracle_commit_semantics: "last_committed_step_4_input_baseline"`
がその意味を持っている。**

### 2-3. 最小手順(コードから導出)

```
コミット A: auth-catalog.json を変更
            → check_authz_catalog.py --reseal-derived
              (auth-catalog.lock.json が更新される。同実行は oracle 段で exit 1 だが副作用は残る)
            → 2 ファイルを A としてコミット        ← ここまで CI は red

コミット B: check_authz_catalog.py:107 の ORACLE_INPUT_BASELINE_COMMIT を SHA(A) へ
            oracle-seal.lock.json の oracle_commit を SHA(A) へ
            oracle 6 資産の oracle_context.oracle_commit を SHA(A) へ
            → check_authz_catalog.py --reseal-oracle
            → コミット B
```

**`--reseal` は不要**(`requirement-claims.json` を変えない限り無関係)。

**段 B は 6 資産の `oracle_context` を書き換えるので `sealed_assets` 6 行が全更新される。**
**`S-10`(1) の「差分が `receiving_task_id` だけ、では成立しない」はこの挙動を指していた**(裏が取れた)。

### 2-4. `ORACLE_INPUT_BASELINE_COMMIT` と fail-open

**値**: `0cf994f4aa6ca51331a62c05fcd6e0756c4492d2`(`:107`)。**コード内の参照は `:4525` の 1 箇所だけ**で、
`boundary-proposal.json` の `oracle_commit` としか突き合わせていない。
**ただし `validate_oracle_seal` が「oracle 6 資産の `oracle_context.oracle_commit` が
すべて `seal.oracle_commit` と一致」を要求するので、推移的に seal と 6 資産全部がこの定数に釘付けされる。**

**影響**: ① 基準点を動かすたびに `check_authz_catalog.py` の変更が必須 →
**同ファイルは `guard_paths` と `tenant-isolation.paths` の両方にあるので毎回コア領域が発火**
② **部分的な修正が一切できない** ③ 2 段コミットが強制される。

#### **fail-open**(**改訂 4 の合格条件に効く**)

`:4796-4799` の逐語:

```python
if result.returncode == 0 and result.stdout.strip() != digest:
    raise CatalogError(f"{path_text}: oracle commit 上の blob が不一致")
```

**`git rev-parse` が失敗すると(`returncode != 0`)黙って通る。**
**CI の浅いクローンで落ちれば、blob 不一致を検出せず green になる。**
**台帳に同型の前例がある**(`harness` と `backend` に `fetch-depth: 0` が無く fixture が死に、
**PR #52 が red のままマージされた** — 台帳 `:2469`)。

**→ 改訂 4 は「`oracle_commit` 上の blob 一致」を合格条件の根拠にしない。**
**恒久解は TSK-386 が持つ**(`:4798` を fail-closed へ)。

**現状の CI は穴を踏んでいない**: `harness`(`ci.yml:78`)と `backend`(`:214`)は
どちらも `fetch-depth: 0` を持つ(TSK-386 の実測・本調査でも確認)。
**ただし「現状は持っている」だけなので、外れたときに黙って戻る。**

---

## 3. 文書側の壊れ(**資産の再導出では検出できない層**)

### 3-1. TSK-367 の `plan.md` に 6 件(**当人が是正 PR を用意中**)

| # | 箇所 | 内容 |
| --- | --- | --- |
| 1 | `:134` | **`NFR-012/list_item-003` → `TSK-217` は改訂 2 の取り消し漏れ。** `:150` が `B_SET` から外したと書き、`:165` が `FR-037` 側に置き、`:144` の合計 10(4+2+3+1)も数えていない。**正しくは `PENDING:FR-037`** |
| 2 | `:399` | 「`TSK-217-B` 9 owner」が古い(**10**) |
| 3 | `:446` | 「7 + 9 = 16」が古い(**7 + 10 = 17**) |
| 4 | `:156` | **「全件」宣言が成立していない** — 非 FR-* は資産で **46**、override 表は **44**(`(+1)` 行 2 本を含む) |
| 5 | `:164` | `FR-041` ラベル **17** / 実数 **15 + `(+1)` 1 = 16** |
| 6 | `:165` | `FR-037` ラベル **6** / 実数 **7** |

**孤児 owner は 0 件。** 表に無い 2 件は別の場所に宛先がある:
`NFR-019/paragraph-001` → `TSK-217`(`:135` `:144`)/ `SECTION-8/list_item-002` → `TSK-217`(`:136` `:144`)。

### 3-2. **検査を 2 層に分ける**(本調査で得た一般則)

**資産から取れるのは「いま資産に何が書かれているか」だけで、
「文書が資産に対して何を約束しているか」は資産からは出てこない。**

| 層 | 何を検査するか | 今回の検出 |
| --- | --- | --- |
| **① 資産からの再導出** | 母集団の件数・分布・不変条件 | `152` / `158` / `46` などを全件再現。**`:134` の取り消し漏れは出てこない**(資産に `NFR-012/list_item-003` の宛先は書かれていない) |
| **② 文書の内部整合** | **その文書が名乗る母数・合計・ラベルが、自分の中身と合うか** | **ラベル件数の不一致 2 件と「全件」の不成立 1 件を機械で検出**。**取り消し漏れ 1 件は人の指摘でしか出なかった** |

**② の機械化は改訂 4 では行わない**(**裁定 `D-24`(2026-09-14)で別タスクへ送った** —
[文書の内部整合を検査する](https://app.notion.com/p/3db93b75e68781d694b2cf53a8b3d119))。
**改訂 4 は一回限りの検証に留める。** 「ラベル件数 vs 行の実数」の突合は今回のスクリプトがそのまま雛形になる。

---

## 4. `U-T1`(TSK-363)の依存 — **未裁定の穴**

### 4-1. TSK-363 は依存を書いていない

`product-impl-unit-split/plan.md:204` の `U-T1` 行の**依存列は `U-00` のみ**。
同タスクの 3 文書で `TSK-317` の出現は 6 件あるが、**`U-T1` と結び付けた記述は 0 件**
(いずれも「周回コストの実測」「裁定 `D-19` と同じ手」という手続き面の参照)。

### 4-2. しかし `data-model.md` は `U-T1` の構成要素を TSK-317 へ送っている

| `U-T1` の要素 | `data-model.md` の扱い | 典拠 |
| --- | --- | --- |
| app ロールの属性 | **定めている** | `:206-212` |
| `set_config` の規律 5 項 | **定めている** | `:308-332` |
| 越境関数経由のリポジトリ基底 | **定めている** | `:223-230` `:477` |
| **物理 DDL の書式** | **定めていない — 実機確定へ** | `:238` |
| **スキーマ検査の対象集合と合格述語** | **定めていない — TSK-317 へ** | `:244` `:2844` |
| **名前解決経路の非注入の検査対象集合** | **定めていない — TSK-317 へ** | `:246` `:2844` |
| **RLS ポリシー・ロール DDL の実機確定と越境テスト** | **定めていない — TSK-317 へ** | `:2845` |
| `pg_temp` 末尾明示 | **定めている**(`rejected-configs.json` の `REJ-003` を規範として引用) | `:245` |

**→ `data-model.md` 3-1〜3-6 だけでは `U-T1` の物理 DDL と迂回検査は書けない。**

### 4-3. さらに 3 資産は製品構成ではない

**`ddl-elements.json:8-13` の `scope` は `product_schema: false`** を自己宣言している
(`status` は **`verified_probe_configuration`** — PR #2 で `candidate_probe_only` から反転済み)。
**probe 構成であって製品構成ではない。**
**probe → 製品の写像規則(`product-ddl-map-data-model.json`)は予告だけで資産が未作成。**

### 4-4. 判定

**「`U-T1` が引き渡し 3 資産に依存する」と書いた文書は存在しない。**
**「どの資産のどの部分が入力か」を名指しした記録も無い。**
**未裁定である。** 最も近い候補は `ddl-elements.json` の `roles[]`(`:37-101`)・
`search_path`(`:305` `:358` `:411`)・関数 ACL。

---

## 5. 射程 7 項目の現状

### `S-2`(論理 ID → node ID・187 + 310 参照・status 更新)

- **`catalog_entry_id` は 187 件・重複 0・全件 `CATALOG:` 接頭辞。`AUTH-*` は 0 件**(訂正 10 は正しい)
- enforcement 側は **187 件すべて `planned`**・`::` を含むものは 0 件・接頭辞は `TSK-270` 169 / `TSK-312` 18
- catalog 側は **187 件すべて `implemented`** だが **ID は全件同一の 1 つ**
  (`tests/test_check_authz_catalog.py::test_repository_derived_assets_are_valid`)。**網羅の証拠にならない**
- **`310` の出所を特定した**: `310 = 468 − 158`。`468 = 460 + 8`。
  `460` = `claims` の `TSK-270-GROUP-2` 178 + `two_factor_interactions` 276 + `positive_cases.cases` 6。
  `8` = `ddl-elements.json` の **`table_privilege_probe_matrix[].test_owner`**(`privilege_groups` 12 ではない)
- **`planned` → `implemented` へ上げた瞬間に「実在する node ID であること」が機械で効く**
  (`:1656-1671` の `_validate_test_owner` → `collect_pytest_node_ids`)。
  **ID を node ID へ書き換えるだけなら `TEST_ID_RE`(`:74`)は `:` を許すので通る**

#### **射程の穴**(本調査で発見)

**`requirement-claims.json` に `test_owner` が 402 参照**(全件ユニーク)あり、
**うち 187 は auth-catalog の enforcement と同一、残り 215 は別 ID**(接尾辞 `.http` 195 / `.cache` 20)。
**そのうち 193 が `TSK-270` 所有。**

**→ `187 + 310` は TSK-270 所有の planned 論理 ID の全部ではない。**
**射程外と判断する根拠は資産にも計画書にも無い。** **`S-2` の射程宣言で明示的に扱う。**

### `S-3`(要件側 7 単位の source)

- **`req-universe.json` に `list_item` は 0 件**(訂正 17 は正しい)。カテゴリは
  `requirements` 65 / `sections` 28 / `blocks` 8 / `appendix_items` 23 ほかで `total: 212`
- **「要件側 7 単位」の列挙はどの資産・文書にも存在しない。** `operation-count-mapping.json` は未作成
- **代替の安定 ID 源は 2 つ**: (a) `requirement-claims.json` の `source_id`(要件書の全 list_item **603 件**)
  (b) `route-registry.json` の `management_operations[].source_claim_ids`(FR-041 由来の相異なる base ID が **7 個**)
- **ただし 1:1 に写せない** — **`FR-041/list_item-016` の `source_text` は「役割変更・グループ終了」の
  2 操作を 1 行に含み、`atomic_claims` による分割が無い**(`FR-041/list_item-014` には分割があるのと対照的)。
  **資産側の `operation_ids` は 8。** **どちらを `stable_id` に採るかは未確定**

### `S-4`(引き渡しマニフェストの ID 完全性)

- **マニフェストは存在しない。** `contracts/authz/handoff-manifest.json` は無い。**丸ごと新設**
- **雛形は 3 つある**: `oracle-seal.lock.json` / `shared-preconditions.json` / `function-bodies/manifest.json`

| 要求項目 | 取れるか |
| --- | --- |
| スキーマ版 | **取れる**(3 資産とも `schema_version: 1`) |
| 安定 ID | **取れる**(`auth-catalog` = `catalog_entry_id` 187 / `ddl-elements` = roles 7・schemas 3・tables 6 ほか / `rejected-configs` = `rejection_id` 3) |
| 共通正規化 ID | **計算関数はあるが、ID 集合の digest を持つフィールドは全資産に 0 件** |
| 元 commit | **2/3** — `auth-catalog.json` は `oracle_context` を持たない |
| blob digest | **1/3 しか記録が無い** — `auth-catalog` は `input_assets` 側(`git_blob_digest`)、他 2 本は `sealed_assets` 側(`canonical_sha256`)。**種類が違う** |

**「3 資産を 1 箇所に同じ形で」記録する場所は無い。**
**seal は `_expect_keys` でキー exact なので「版」を足すと検査器も同時に変わる**
→ **別ファイル(引き渡しマニフェスト)で持つのが素直。**

**`S-4` の「13 行 / 8 ID」は現物と完全一致**(`FR-041/list_item-007` が 4 行・`-006` が 3 行で ID 共有)。

### `S-6`(受取契約・read-back・製品 adapter)

- **`read-back` は正本に 1 件も無い。** 定義は計画書系のみ(`design.md:332-357` が 3 段で定義)
- **「製品 adapter」はどこにも定義されていない。** 出現 4 箇所すべてが語の反復。
  識別子はコード・資産に 0 件。**`S-6` を書くならまずこれを定義する**
- **`TSK-250` は `data-model.md` ではない** — `closure-handoff-data-model.json` が
  `source_task: TSK-342` / `destination_task: TSK-250` / `canon: docs/design/data-model.md` と記録。
  **`data-model.md` は TSK-342 の成果物で、TSK-250 はその引き渡し先。**
  **v0.3 approved は TSK-250 の完了を意味しない**
- **TSK-250 / TSK-217 とも未着手で DoD が存在しない** → **`read-back` の突合先が空**
- **→ 前提は生きているが、`[機械]` 部分は実行不能。** `S-10` と同じ書き分けが要る

### `S-8` の一部(引き渡し 3 資産の記録 + `test_ci_wiring.py`)

- **`tests/test_ci_wiring.py` は存在する**(1,820 行・`test_*` 23 本)。
  **`authz` の文字列は 0 件** → **追記は完全に未着手**
- **`ci.yml` は `check_authz_catalog.py` を直接呼んでいない。**
  `harness` ジョブの `pytest tests/` 経由で `tests/test_check_authz_catalog.py`(92 本)が走る。
  **配線を固定するテストが無い** = **pytest のパスを絞れば authz 検査が黙って消える**
- **3 資産の記録場所は `oracle-seal.lock.json` に部分的にあるだけ** —
  **2 つの別セクションに分かれ、digest の種類も違う。「版」はどこにも記録されていない**
- **`core-areas.json`**: `paths` は **登録済み**(`tenant-isolation.paths` の glob `contracts/authz/*`)。
  **`guard_paths` は未登録**(42 件に `contracts/` で始まる要素は 0 件)。
  **`guard_paths` は完全一致専用なので glob を置けず、個別列挙しても `matched_paths` は OR なので判定は変わらない**
  → **「両方に登録」は達成不可能かつ不要**

### `S-9` / `S-10`

**§1 と §3 が正。** `S-9` の 178 件(158 + 20)は再現済み。
**`S-10` の 9 論点のうち (4)(8)(9) の是正内容は §6 に記す。**

---

## 6. 改訂 4 で是正する項目

### 6-1. TSK-367 からの申し送り(**検証済み**)

| # | 是正 | 検証結果 |
| --- | --- | --- |
| 1 | **`S-10` (8)(9) を `PENDING:` 行について書き換える** | **一部一致。** 「全 152 で不成立」ではない — **`B_SET` 10 + 起票済み 3 = 13 owner には課せる**。不成立なのは **`PENDING:FR-nnn` の 139** |
| 2 | **`plan.md:231` の「受取タスクは起票済み」は誤り** | **典拠が不十分。** `merge-gate-api-cycle/research.md:362`(「製品 HTTP 経路(API)の実装 = なし」)は単独では反証にならない。**二層に分けて書けば両立する** — 「受取**先を決める**タスクは起票済み(TSK-367・完了)/ runtime テストの**受取タスク本体**は `PENDING:FR-nnn` 139 owner について未起票」 |
| 3 | **`S-10`(4) の「TSK-217 の 7 件」→ 7 + 10 = 17** | **一致。** 10 owner は全件実在し既存 7 と互いに素 |
| 4 | **`contract_only_reason_code` は定数追加では足りない** | **実証で一致。** 定数(`:118-120`)だけ足した実験は `:3838` で落ち、`expected_reasons` の導出(`:3833`)も直して初めて通った。**改修はちょうど 2 箇所** |

### 6-2. 改訂 4 で明示が要る 2 件

1. **`no_db_decision_point` → TSK-217 の写像を定めた文書は存在しない**(**2 系統の独立走査で追認**)。
   **検査器は受取先について「非空文字列であること」しか見ていない**(`:3867-3868`)。
   最も近いのは第 1 群の計画書 `:115`「HTTP 404/400 の判定は TSK-217 へ」だが、
   **理由コードを名指ししておらず規則にもなっていない**
2. **既定 7 行の根拠がカード本文の説明と実データで合っていない** — **TSK-367 の分類は全件正しい**:
   **存在秘匿 1**(`FR-033/list_item-005`・要件書 `:593`)/ **レート制限 2**(`FR-033/list_item-006` `:594`・
   `FR-035/list_item-016` `:746`)/ **認証構成の補足 1**(`FR-033/list_item-007` `:595`)/
   **トークン失効 1**(`FR-036/list_item-005` `:753`)/ **PW ポリシー 1**(`-006` `:754`)/
   **人手の復旧経路 1**(`-007` `:755`)。**7 行の `source_text` に `404` も `400` も 0 件**

   > **「既定 7 行(`no_db_decision_point`)」という呼び方も厳密には不正確** —
   > **`no_db_decision_point` を持つ行は 8 行**で、そのうち TSK-217 を指すのが 7 行。

### 6-3. 計画書の陳腐化 5 件

| 記述 | 実測 |
| --- | --- |
| 訂正 4「`scope.status == candidate_probe_only`」 | **`verified_probe_configuration`**(PR #2 で消化済み) |
| 訂正 4「`PENDING-MANAGEMENT-COMMAND-COUNT.status == pending_human_decision`」 | 検査器の要求値は **`human_decided`**(`:4442`) |
| `S-10`(7)「`harness` は `fetch-depth` 未指定で浅い履歴」 | **`ci.yml:78` に `fetch-depth: 0` がある**。**履歴を要する検査は CI で実行可能** |
| `design.md:302`「`REJ-001`〜`003` + 第 2 群で追加した分」 | **現物は 3 件のまま**(追加ゼロ) |
| `S-2`「468 参照」 | 468 は再現できたが**全部ではない**(§5 の射程の穴) |

---

## 7. 順序と干渉

### 7-1. マージ順序(**PO 裁定 2026-09-12 — 変更なし**)

```
TSK-348(済)→ TSK-317 PR #1(済)→ TSK-343(済)→ TSK-317 PR #2(済)
  → TSK-355 → **本タスク(PR #3)** → TSK-235
```

**裁定以降に順序を変える新しい裁定は無い**(worklog 全件・`docs/features/**/plan.md` を走査)。
**待つのはマージだけで、計画・実装は先行できる。**

**TSK-355 の状態**(2026-09-14 に当人から受領): **確定ゲート 6 周目で 6 周警告(7.3-6)に到達。**
**PO の判断は「続行」で、射程の再縮小も打ち切りも無い。**
**要件書 `NFR-018` の達成条件 (e) 新設は射程に残る** → **要件書の blob は動き、
`requirement-claims.json` の digest も動く** → **本タスクを後に置いた根拠はそのまま生きている。**
`P0` は 6 周連続ゼロ・`P2` が初めて 0 件だが、**起因比がほぼ 100% で 5 周続いている**。
**同型の前例 TSK-278 は 27 周。マージ時期は読めない。**

### 7-2. TSK-386(`fix/oracle-input-baseline`)— **順序が決まった**

**担当は TSK-379 と同じセッション**(コミットの `Claude-Session` 突合で判別 — **`ListAgents` のタブ名と担当はずれる**)。
**計画レビュー 6 周で可決(`P0` 0 / `P1` 0 / `P2` 2)、人間の計画承認待ち。**

**順序は「PR #3 が先、TSK-386 が後」**(2026-09-14 に合意)。**根拠は作り直しの非対称性**:

- **TSK-386 が先** → PR #3 は新しいキー構成へ**合わせ直し**
- **PR #3 が先** → TSK-386 は **rebase して reseal をやり直すだけ**(その手順をステップ 9・10 として既に持つ)

**TSK-386 の射程は `:107` だけではない** — `:4525` の参照先・**`:4798` の fail-open の是正**・
`mutation_composition.py:36` / `test_check_authz_catalog.py:38` / `test_core_guard.py:47` の base 値・
`frozen-baselines.json` の新設・**派生 3 資産の `input_manifest` から
`requirement_claims_blob_digest` と `..._lock_blob_digest` を落として `corpus_version` へ**・
**ハーネス設計書 v1.15 の新設**(確定ゲート)。

#### **改訂 4 が守る制約**

1. **派生資産の `input_manifest` のキー名を直接アサートしない**
   (`requirement_claims_blob_digest` / `..._lock_blob_digest` は TSK-386 で消える)。
   **`_validate_derived_input_manifest`(`:1627` — 派生 3 資産が `:1838` `:2135` `:2284` で共用)経由で見る**
2. **`oracle_commit` 上の blob 一致を合格条件の根拠にしない**(§2-4 の fail-open)

**未解明**: **`--reseal-derived` は decision lock だけを書き、派生資産自身の `input_manifest` の
digest は再生成しない**(`:1627` は検証のみ)。**誰が更新しているかは双方とも未特定。**
**改訂 4 の reseal 手順を組むときに判明したら TSK-386 へ共有する。**

### 7-3. TSK-386 は 2026-09-12 の総順序に席が無い

**PR #3 が `D-14`/`D-15` で新設されたとき席が無かったのと同型。**
**台帳 `:2276-2278` が構造原因として記録した「計画書テンプレートにマージ順序を書く節が存在しない」型の再発に見える。**
**ただし再発と裁定した記録は無い。**

---

## 未解決・申し送り

1. ~~**`U-T1` が引き渡し 3 資産に依存するか**~~ → **裁定済み**(`D-25`・2026-09-14・山田正輝)。
   **別タスクとして起票した** — [U-T1 の入力を確定する](https://app.notion.com/p/3db93b75e687813a9386f3b1f1e682ed)。
   **受取範囲**: 実装入力の名指し + probe → 製品の写像 + TSK-363 側への追記。
2. **`S-2` の射程の穴** — `requirement-claims.json` に TSK-270 所有の planned ID が **193 参照**残る。
   **射程外と判断する根拠が無い。** 改訂 4 の射程宣言で明示的に扱う。
3. **`FR-041/list_item-014` の `reason_code` 分裂** — owner 単位で畳むと衝突する唯一の owner(§1-5)。
   **設計判断が要る。**
4. **「製品 adapter」の定義が無い** — `S-6` を書く前に定義が要る(§5)。
5. **`S-3` の 7 単位が 1:1 に写せない** — `FR-041/list_item-016` が 2 操作を 1 行に含む(§5)。
6. **引き渡し 3 資産の受け手が食い違う** — `design.md:305` は **TSK-343 / TSK-344**、
   TSK-250 の計画書は**自分**。**裁定が無い。しかも TSK-343 は既に完了**していて、
   名指しされた受け手の片方は資産が固まる前に閉じている。
7. **`D-14`・`D-15`・`D-16` に裁定者名の記録が無い**(`D-11`〜`D-13` は worklog に「山田正輝」と明記)。
8. **TSK-367 の是正 PR(`feature/tsk217-scope-alignment`)待ち** — 6 件を直し
   **override 表の母数を 44 → 46 にする**とのこと。**マージ前に同計画書を引くときは commit を明記する。**
   **和を取る実装は防御として残す。**
9. **調査の限界**: decision-tracer は **Bash が無効で `git log` のコミットメッセージを見ていない**。
   §6-2 の「写像を定めた文書は無い」は**作業ツリー上のファイルに対する結論**である。
10. **`BOOT-ACTIVATION` の「CI の必須経路へ接続された」はツリー基準**(TSK-355 の実測 —
    `required_status_checks` は存在せず、運用は「PR の最新 HEAD SHA に対して全ジョブ green」)。
    **改訂 4 も同じ前提で動く。**
