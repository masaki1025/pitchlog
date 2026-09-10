---
feature: pg-authz-verification-g2
type: design
date: 2026-09-09
---

# 詳細設計: PostgreSQL 認可構成の実機検証 第 2 群・第 3 群

[plan.md](plan.md) 4 節から参照される詳細設計。

> **本計画の承認範囲は第 2 群前半(ステップ 1〜20)である**(裁定 `D-8` — **裁定 `D-9`(2026-09-10)で旧ステップ 17〔`contract_only` の runtime テスト〕を撤去し、旧 18〜21 を 17〜20 へ連番で振り直したため 21 → 20**)。
> 本書のうち **8 節(引き渡し 3 資産)・8-2(7→8 写像)・9 節(`R-4` の受取契約)は改訂 3 第 2 弾の射程**であり、承認範囲には入らない。
> **改訂 3 第 2 弾が満たすべき要件は plan.md 4 節の `S-1`〜`S-10` が正**(**裁定 `D-10`(2026-09-10)で改訂 3 を 2 弾に分けた** — 第 1 弾は機械的な作業のみ、`S-1`〜`S-10` の機械条件の確定は**ステップ 17〜20 の完了後**)。
> **`S-10` は旧ステップ 17 の置き換えで、`contract_only` 158 行の runtime テストは受取タスクの所有である**(`R-7`)— **本タスクは実テストを書かない**。
**機構が読む状態と実装ステップ表は plan.md のみに置く**
(設計書 7.1-1)。前計画書の内容・凍結資産の中身・要件の逐語は**ここへ複製せず**、
[../pg-authz-verification/plan.md](../pg-authz-verification/plan.md) と [research.md](research.md) を参照する。

## 1. 配置

| 対象 | 配置 | 理由 |
| --- | --- | --- |
| DDL 生成器 | `backend/src/pitchlog/authz/ddl.py` | 製品コード側。**生成器そのものは本計画のステップ 3 で実装する**。**第 2 弾(`S-8`)へ送るのは `core-areas.json` への paths 登録だけ**である(現在このパスは `tenant-isolation.paths` へ未登録)|
| 適用器 | `backend/src/pitchlog/authz/provisioning.py` | 同上。psycopg 直書き(`D-3`) |
| カタログ検査 | `backend/src/pitchlog/authz/catalog.py` | 同上。**問い合わせだけを持ち、期待値は資産から読む** |
| 変異の適用 | `backend/tests/db/authz/mutation.py` | **テスト側**に置く。製品コードに変異機構を入れない |
| 越境テスト・行列 | `backend/tests/db/authz/test_*.py` | `backend/tests/db/*` は既に `tenant-isolation.paths` に登録済み |
| 4 ロール fixture | `backend/tests/db/conftest.py` の拡張 | 既存の `tested_role_connection` の形を踏襲(`backend/*conftest.py` は登録済み) |
| **関数 body と DDL の SQL 実体** | **`contracts/authz/function-bodies/**`** | **封印 6 資産に含まれない**ため oracle の再封印を発火させない。ステップ 1 の先行コミットで置く |
| **MC/DC の写像** | **`contracts/authz/mcdc-map.json`** | 凍結資産には判定形の名前しかない(下記 6-2)。**ステップ 18**(裁定 `D-9` の連番振り直しで旧 19 → 18)|
| **7 単位 → 8 ID の写像** | **`contracts/authz/operation-count-mapping.json`** | 裁定 `D-4`。**改訂 3 第 2 弾の射程**(`S-3`) |
| **共有関数の 6 前提の母集合** | **`contracts/authz/shared-preconditions.json`** | 資産の `precondition_ids` は管理操作用の別概念。ステップ 9 |
| **失敗注入点** | **`contracts/authz/failure-injection-points.json`** | `R-5` の 5 種。ステップ 14。**閉じた `injection_point_id` 5 個 + ステップ 4 の適用器が発行する `checkpoint_id`(step 内の序数)+ 相互重複禁止 + 実行ログへの実在**(3 周目 `P1-4`)。**実行ログ全体との exact-set ではない** — 凍結 DDL は 7 ロール・3 スキーマ・6 表・6 ポリシー・3 関数・17 ACL で 5 文を大きく超えるため両立しない(4 周目 `P1-3`)。5 種の位置への対応は `operation_kind` で機械判定する |
| **引き渡しマニフェスト** | **`contracts/authz/handoff-manifest.json`** | **改訂 3 第 2 弾の射程**(`S-4`・下記 8 節) |

**`backend/src/pitchlog/authz/` の 3 モジュールは責務で分ける** — 生成(資産 → SQL 文字列)/
適用(SQL → クラスタ・順序と原子性)/ 検査(クラスタ → 観測値)。
**検査モジュールに期待値を持たせない**(自己 oracle 化を防ぐ — 前計画書のステップ 5 の趣旨)。

## 2. DDL 生成器の入力契約

**入力は 2 つ** — `contracts/authz/ddl-elements.json`(構造)と
`contracts/authz/function-bodies/**`(関数 body と DDL の SQL 実体)。生成器は**この 2 つ以外の定数を持たない**。

**なぜ body を資産の外に置くか(計画レビュー 1 周目 `P0-2` の訂正)**: `ddl-elements.json` には
**body・引数型・戻り列が無い**(`contains_sql_body: false` は `scripts/check_authz_catalog.py:2680` が
**ハード要求する値**なので、そこへ body を入れることはできない)。構造だけを入力にして SQL を生成し、
その生成結果の `pg_get_functiondef` digest を検査すると、**誤った認可関数を生成しても同じ digest で green になる**
(自己 oracle 化)。したがって **body はステップ 1 の先行コミットで固定し、manifest と静的照合をステップ 2、カタログ検査をステップ 6 に置く**。
`function-bodies/**` は**封印 6 資産に含まれない**ので oracle の再封印を発火させない。

**「先にコミットした」という履歴だけでは閉じない(計画レビュー 2 周目 `P1-3` の訂正)** —
後続コミットで body を変えれば期待 digest も一緒に動く。したがって manifest に
**`source_commit`(ステップ 1 のコミット SHA)と各ファイルの `blob_digest`** を持たせ、
ステップ 2 の検査は **`git rev-parse <source_commit>:<path>` の blob が manifest の digest と一致すること**
まで確認する(oracle seal が `input_assets` に対して行っているのと同じ 2 段の縛り)。
これで**後続コミットでの body 差し替えが red になる**。

| 資産の節 | 生成物 | 落としてはいけない属性 |
| --- | --- | --- |
| `roles`(7) | `CREATE ROLE` | `login` / `bypass_rls` / `create_role`(`shared_fn_owner` と `management_fn_owner` は **`NOLOGIN` + `BYPASSRLS`**) |
| `schemas`(3) | `CREATE SCHEMA` + owner | 所有ロール |
| `tables`(6) | `CREATE TABLE` + `ENABLE ROW LEVEL SECURITY` + **`FORCE ROW LEVEL SECURITY`** | **6 表すべてが `rls_enabled` かつ `force_rls`** |
| `predicates`(1) / `policies`(6) | `CREATE POLICY` | `polcmd` / `polroles` / `polpermissive` / `polqual` / `polwithcheck` に対応する 5 属性 |
| `functions`(3) | `CREATE FUNCTION` + `SECURITY DEFINER` + `SET search_path` | **`search_path` は末尾 `pg_temp`**(`REJ-003`)/ `public_execute: false` |
| `acl_expectations`(17) / `column_acl_expectations`(1) | `REVOKE` + `GRANT` | **関数作成と `REVOKE ALL ... FROM PUBLIC` を同一トランザクション**に置く |

**生成の検証方法**(ステップ 3 の合格条件の実装形):

1. 資産の全要素 ID(`role_id` / `schema_id` / `table_id` / `policy_id` / `function_id` / `acl_id`)を
   集合として取り、**sha256 を取って生成物側の被覆集合と exact-set 突合**する
2. **資産を参照しない SQL リテラルの検出** — 生成器のソースから SQL 断片を抽出し、
   識別子部分が資産のキー由来であることを検査する(手打ちの識別子を許さない)
3. **負例** — 資産から 1 要素を削って生成物が変わることを全要素で確認する(`_iter_leaf_paths` 同型)

## 3. 適用器の順序契約と原子性

**`provisioning_claim.ordered_steps`(5 件)を資産から読み、その順序で実行する。**
順序を**コード上の並びで表現しない**(定数の並べ替えは検出できない)。

| `step_id` | `operation_kind` |
| --- | --- |
| `PROVISION-01-CREATE-OWNER` | `create_no_login_bypass_owner` |
| `PROVISION-02-OPEN-SET-PATH` | `temporarily_grant_set_membership` |
| `PROVISION-03-ASSIGN-OBJECTS` | `create_and_assign_owned_objects` |
| `PROVISION-04-CLOSE-FUNCTION-ACL` | `revoke_public_and_grant_named_execute` |
| `PROVISION-05-CLOSE-SET-PATH` | `revoke_temporary_membership` |

**なぜ手順 2 が要るか**: `BYPASSRLS` ロールに何かを所有させる操作は**実行者の `SET ROLE` 可能性を要求する**
(Supabase 実機検証 `RES-01`)。したがって「一時的に開く → 所有させる → 閉じる」が契約になる。
**検査対象は「適用完了時点で閉じていること」に限る** — `admin_option = true` により経路は再度開けるため、
DB 層では塞げない(同 `RES-01`)。

**完了時の検査**(`completion_catalog_expectations`):
`pg_has_role(<provisioner>, <fn_owner>, 'SET') = false` / `pg_has_role(<provisioner>, <fn_owner>, 'USAGE') = false`

**原子性 — 適用は非原子である(計画レビュー 1 周目 `P0-5` の訂正)**: `ddl-elements.json` の
`transaction_boundaries` は `TX:PROVISIONING` を **`atomic: false`** の `ordered_application` と定める。
したがって**失敗時の回復手段は rollback ではなく「冪等な再適用による収束」**である。

| `boundary_id` | `boundary_kind` | `atomic` | 本タスクでの扱い |
| --- | --- | --- | --- |
| `TX:PROVISIONING` | `ordered_application` | **`false`** | ステップ 4・15。順序を守り、失敗後は**再適用で収束**する |
| `TX:REPRESENTATIVE_MANAGEMENT` | `authorization_and_side_effect` | **`true`** | ステップ 12。**認可と副作用が同一トランザクション**。認可失敗時に副作用行が増えない |
| `TX:GLOBAL_MUTATION_ISOLATION` | `disposable_cluster` | **`false`** | **ステップ 17**(裁定 `D-9` の連番振り直しで旧 18 → 17)。起動〜破棄は原子でない |

`R-5` の失敗点 5 種は**注入位置を資産由来の列で持つ**(ロール作成後 / policy 変更後 / body 置換後 /
owner 変更後 / ACL 正規化途中)。比較対象は**全対象 catalog・membership・default ACL・fixture data** で、
**注入 → 再適用 → 正常適用時と一致**を要求する。**注入後に再適用しない場合の状態も記録する**(隠さない)。

**冪等性**: `CREATE OR REPLACE` + `ALTER ... OWNER TO` + **ACL の全正規化**。
「古い直接 `GRANT` が 1 回目と 2 回目の双方で消えている」ことを要求する(差分適用にしない)。

## 4. カタログ検査の検査 ID 体系

**`CATALOG:<対象>:<観点>`** の形で ID を与え、**資産の要素 ID と 1:N で結ぶ**。
期待値は資産から読み、検査モジュールは**観測クエリと正規化だけ**を持つ。

| 検査 ID の系列 | 観測対象 | 由来 |
| --- | --- | --- |
| `CATALOG:POLICY:*` | `pg_policy` の `polcmd` / `polroles` / `polpermissive` / `polqual` / `polwithcheck` を正規化して exact 比較 | 前計画書 4 節「読み取りだけでなく書き込み」 |
| `CATALOG:FUNCTION-DIGEST:*` | `pg_get_functiondef` / owner / language / security / volatility / leakproof / strict / parallel / `proconfig` / ACL の **10 属性の digest**。**期待値はステップ 1 で先行コミットした `function-bodies/**` から取る**(観測値を後から期待値にしない) | **`R-1`** |
| `CATALOG:FUNCTION-STRUCTURE:*` | **読み取り関数が `LANGUAGE SQL BEGIN ATOMIC`** であること / **動的 SQL(`EXECUTE`・`format(`・文字列連結)が 0 件** / **body が `dependency_table_ids` 以外の relation を参照しない** | **`R-1`**(digest だけでは「後から足された参照」を型として捕まえられないため、構造検査を併置する) |
| `CATALOG:REACHABILITY:*` | 危険終点 = **`rolsuper OR rolbypassrls OR 保護 relation/schema/routine の owner`** と、アプリ・管理呼び出し・outsider からの `SET` 到達集合の**交差が空** | **`R-2`** |
| `CATALOG:ACL:*` | 表 ACL・**列 ACL**・**schema ACL**・**default ACL**。`PUBLIC` が含まれないこと | 前計画書 4 節「カタログ検査」 |
| `CATALOG:SEARCH-PATH:*` | **末尾が `pg_temp` で、かつ `pg_temp` の出現回数が 1** | `REJ-003` / 既存 `scripts/check_authz_catalog.py:2910-2911` と同じ述語 |
| `CATALOG:PROVISIONER-*` | 上記 `completion_catalog_expectations` の 2 件 | **`R-8`** |
| `CATALOG:OWNED-OBJECTS:*` | **`BYPASSRLS` ロールが所有する全 object** と **全 `SECURITY DEFINER` routine** が exact-set(採用構成外の関数が 1 件増えると red) | 前計画書 4 節 |

**`R-1` の負例は SELECT と DML の双方**を要求する — 既存関数の body へ禁止 relation の
`SELECT` を追加する変異と、`INSERT`/`UPDATE`/`DELETE` を追加する変異を別に持ち、**両方で red** にする。
あわせて **body に動的 SQL を導入する変異**でも red にする(構造検査の実効性の確認)。

**到達閉包は 2 種を分ける** — `pg_auth_members` の推移閉包について、
**`SET` 権限による到達**と**`USAGE`(継承)による到達**を別に取る(`R-2` の負例 3 種が両方に掛かる)。

**再利用**: `scripts/check_authz_catalog.py` の **`git_blob_digest`(`:327-338`)は公開**なので import する。
**`canonical_digest` / `file_digest` は未存在**で、相当物は private の `_canonical_json`(`:593`)/
`_table_digest`(`:597`)。**private を import しない** — 正規化 JSON の digest が必要なら
`scripts/doc_check_profile.py` の公開関数を `importlib` ローダ方式(`scripts/check_doc_profiles.py:26-33` の形)で
読むか、本タスク側に 1 実装だけ置いて**両方から使う**(`NFR-018` のコピー実装禁止に留意)。

## 5. 4 ロール実接続 fixture の構造

既存 `backend/tests/db/conftest.py` の `tested_role_connection`(`:88-122`)を**一般化**する。
既存は「管理接続で `CREATE ROLE ... LOGIN PASSWORD` → そのロール自身の DSN で新規接続 → teardown で `DROP ROLE`」。

| fixture | ロール | 用途 |
| --- | --- | --- |
| `table_owner_connection` | `table_owner` | 所有者でも `FORCE RLS` によりポリシーに従うことの確認 |
| `app_role_connection` | `app_role` | 通常経路。**関数を経由しない他テナント行の読み取りが不可**であることの確認 |
| `management_caller_connection` | `management_caller` | 管理経路。**基表 DML を持たない**ことの確認 |
| `outsider_connection` | `outsider_role` | 負例。無所属からの越境関数実行が不可であることの確認 |

**制約**:

- **`SET ROLE` を使わない** — `tests/test_ci_wiring.py:1237` が `assert "SET ROLE" not in conftest` を検査する。
  理由は「`SET ROLE` の可否は**セッションの認証ユーザー**で判定されるため模擬では検証にならない」
- **各テストの冒頭で `session_user` / `current_user` を照合する**(既存 `verify_connection_identities` の
  autouse fixture を 4 本へ拡張。**ソースの grep を合格根拠にしない**)
- **`NOLOGIN` の関数所有ロール 2 本は実行行列に入らない** — 実接続できないため。
  これらは**カタログ検査の対象**とし、実行は `SECURITY DEFINER` 経由だけ
- **新しい DSN 環境変数を増やさない(計画レビュー 2 周目 `P1-13` の訂正)** — 実資産の
  `dsn_environment_variables` は `admin_connection` と `tested_role_connection` の **2 本だけ**。
  4 ロールに 4 変数を割り当てると CI と compose の両方へ配線が要る。
  代わりに **既存 `PITCHLOG_TEST_ROLE_DSN` をテンプレートとして使い、user とパスワードを差し替える**。
  `tests/test_ci_wiring.py` が既に「**ロール DSN はユーザーだけ異なり host/db は同一**」を検査しており、
  この形が想定されている。パスワードは管理接続の `CREATE ROLE ... LOGIN PASSWORD` で設定する。
  **`environment-expectations.json` は変更しない。**

## 6. 変異の軸と kill 判定の写像

**変異集合は `contracts/authz/claim-mutant-map.json` から読む。件数を定数で持たない**(`H-53`)。

| 軸(`mutant_axes`) | 件数(実測) | 適用先 |
| --- | --- | --- |
| `authorization_predicate` | **205** | ポリシー述語・関数本体の認可条件 |
| `configuration` | **24** | ロール属性・ACL・`search_path`・`FORCE RLS` |
| `r8_provisioning` | **2** | 手順 5 の `REVOKE` 省略 / 手順 2 を手順 3 の後ろへ移す |

**実行クラス**(`execution_classes`): `probe_executable`(**33**)/ `contract_only`(**165**)。
**`contract_only` に runtime kill を要求しない** — 代わりに **schema-drift kill + 受取タスクの runtime テスト ID** を
必須にする(`R-7`。契約 lint を実副作用 kill として数える抜け道を塞ぐ)。

**kill 判定の 5 条件**(`kill_contract.conditions`):

| `condition_id` | `requirement` | 実装上の意味 |
| --- | --- | --- |
| `KILL-01-TARGETED-CATALOG-DELTA` | `only_declared_target_attributes_changed` | 変異が**宣言した属性以外を変えていない**ことをカタログ差分で確認する |
| `KILL-02-TEST-EXECUTED` | `not_skip_not_xfail_not_error` | skip / xfail / error を kill に数えない |
| `KILL-03-EXPECTED-FAILURE` | `expected_assertion_or_sqlstate_only` | **期待した assertion か SQLSTATE でのみ** red を kill とする |
| `KILL-04-NO-FIXTURE-FAILURE` | `setup_and_teardown_failure_never_counts` | setup/teardown 失敗は kill にならない |
| `KILL-05-GLOBAL-STATE-ISOLATION` | `role_attribute_membership_default_acl_use_disposable_cluster` | **ロール属性・所属・default ACL の変異は使い捨てクラスタで**。ロールはクラスタ全域に存在するため別 DB では他の変異へ漏れる |

**使い捨てクラスタ**は既存 `disposable_postgres_cluster` fixture(`conftest.py:168-269`)を使う。
方式は Docker CLI を `subprocess` で叩く(`docker run --detach --pull=never --publish 127.0.0.1::5432`・
イメージと initdb 引数は期待値資産から読む・`_wait_for_postgres` は 60 秒デッドライン・
teardown は `docker rm --force`)。**変異ごとに新しい DB を作る** — 製品適用器を巻き戻し装置にしない。

**2 因子相互作用(276)と最小 cut set(24)**: `attack-tree.json` の `minimal_cut_sets` と
`two_factor_interactions` から読む。

### 6-2. MC/DC の写像を新設する(計画レビュー 1 周目 `P1-9` の訂正)

**凍結資産にあるのは `mcdc_decision_forms`(`AND` / `OR` / `NOT` / `CASE` の**判定形の名前**)だけ**で、
**判定・個別条件・独立影響を示すテスト対の写像が無い**。「各判定形で MC/DC を満たす」という条件は
**4 つの literal を置くだけで green にできる**。そこで `contracts/authz/mcdc-map.json` を新設する。

| フィールド | 内容 |
| --- | --- |
| `decision_id` | 判定の安定 ID(関数本体・ポリシー述語のどの判定か) |
| `decision_form` | `mcdc_decision_forms` のいずれか(exact-set で全判定形を覆う) |
| `conditions[]` | その判定の**個別条件**の一覧(安定 ID つき) |
| `independence_pairs[]` | 各条件について**独立影響を示すテスト対**(2 つのテスト ID と、変えた条件・期待結果の差) |

**合格条件の形(計画レビュー 2 周目 `P1-9` の訂正)** — 「参照が存在する」「片方を消すと red」だけでは
**4 形式に自明な 1 条件ずつと同一テストを割り当てても green にできる**。次の 4 条件を**すべて機械で検査する**:

1. **判定 ID の全体が exact-set で固定**されている(後から判定を減らせない)
2. 各テスト対の **2 つのテスト ID が相異**する
3. **対象条件以外の入力が同一**で、**対象条件だけが反転**している
4. **実測した判定結果が反転する**(期待値の宣言ではなく実行結果で確認する)

**判定 ID の母集合は body から取る(3 周目 `P1-5` の訂正)** — `mcdc-map.json` が判定 ID を
自分で宣言すると、**架空の 4 判定を 1 条件ずつ置いても機械 green にできる**。したがって
**ステップ 1 で body の各認可判定へ `-- DECISION: <id>` の注記を置き、その注記の集合を母集合とする**。
body は**ステップ 1 の先行コミットで凍結され、manifest の `source_commit` 照合で改変が捕まる**ので、
**後から判定を減らすことも、body に無い判定 ID を書くこともできない**。

**ただし「最初から注記を漏らす」ことは機械では捕まえられない(4 周目 `P1-2`)** —
body と注記を同じステップ 1 で作るため、実際の認可判定から注記を省いた縮んだ集合と
`mcdc-map.json` を一致させれば機械 green になる。**注記の網羅性は `[手動・外部]` で担保する**
(SQL の AST から認可判定を自動識別するのは別種の実装であり、本タスクの射程を超える)。
**「機械的に自己申告でない」とは主張しない** — 機械が閉じるのは上の 2 点だけである。
**ステップ 18**(裁定 `D-9` の連番振り直しで旧 19 → 18)の合格条件は「**`mcdc-map.json` の判定 ID 集合が body 由来の集合と exact-set 一致**」。

**注記が実際の認可判定を漏れなく覆っていること**は `[手動・外部]` で確認する(自動抽出できない)。
**この資産は封印 6 資産に含まれない**ので oracle の再封印を発火させない。

## 7. 越境テストの構造

**正例**(`positive_cases.cases` 6 件)と**拒否例**を、`http-route-matrix.json` の `cells`(12・allow 6 / deny 6)と
**テスト ID で 1:1 に結ぶ**(ID 集合の sha256 で exact-set)。

**関数が返す形の要求 — 凍結資産の読みを採る(計画レビュー 1 周目 `P0-3` の訂正)**

正本 3-6 節は「**返す列を集計値に限定**すれば」と「**集計は関数に書かない**」を併記しており、
**関数が集計後の値を返すのに集計を書かない**という読みになって矛盾する。凍結資産は
`return_contract: "typed_authorized_business_rows"` / **`aggregation_contract: "none"`** で、
**認可済みの業務行を返し、集計は呼び出し側**という読みを取っている。

→ **本タスクは凍結資産の読みに従う**(`contract_only` の claim も同じ前提で書かれている)。
**正本の表現との差の解消は [TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5) が持つ**(裁定 `D-5`)。
**本タスクは正本の当該表現を変更しない。**

- **越境関数は「認可済みの業務行」を返す**形にし、**許可された行だけが返る**ことを試験する
- **集計は関数に書かない**(`aggregation_contract: none`)
- **下段 4 行(常に 404)は「返す経路を持たない」形**にする。付与の値で分岐させない
  → **テストは「返らない」ではなく「そのシグネチャが存在しない」ことも確認する**
- 関数は **`group_id` を必須引数に取り、内部で当該グループに紐づく付与だけを見る**

**第 2 層(認可行列)の検査 — 機械条件にする(計画レビュー 1 周目 `P1-8` の訂正)**

6 前提を満たした要素それぞれについて、要求粒度の行を認可行列から引き、
**`相手の付与 ∧ 要求元の付与` の双方**を検査する。**とくに「対象側は非共有・要求元だけ付与」の組み合わせ**。

**当初は `[手動・外部]` の概念名確認に落としていたが、それではテストを実装せず worklog に語を置くだけで
合格できてしまう**(`H-79` を閉じていない)。したがって**母集合を資産から導出する**:

**母集合はテストと同じステップで作らない(計画レビュー 2 周目 `P1-10` の訂正)** — 同時に作ると
**1 つ落としたときに前提集合とテスト集合の両方が縮んで green のまま**になり、`H-79` / `H-53` を閉じない。
また **資産の `precondition_ids`(6 個: `tenant_active` / `group_active` / `active_membership` /
`participant_capacity` / `invitation_active` / `preserve_active_admin`)は管理操作用の別概念**であり、
共有関数の 6 前提とは違う(正本 3-6 節の別の列挙)。

1. **ステップ 9 で `contracts/authz/shared-preconditions.json` を新設**する — 正本 3-6 節の 6 前提を
   **逐語で抽出**し、**抽出規則と正本の blob digest** を持たせる(正本が変わると red)。
   **`route-registry.json` の `precondition_ids` との重複が 0 件**であることを機械で示す
2. **ステップ 10 で認可行列の許可行**を `http-route-matrix.json` の allow セルから導出する
3. **直積のすべてにテスト ID を割り当て、ID 集合の sha256 で exact-set 突合**する
4. **1 行落とすと red**。**前提 ⑤ の例外**(自テナントは付与・相互性を適用しないが同時比較上限には数える)は
   ステップ 9 の資産に**独立の行**として持つ

**選手個別の行フィルタ**: **`kind = 'self'` かつ在籍区分が現役(`active`)の選手だけ**。
**チーム集計には在籍フィルタを掛けない**(OB が出場した過去試合も含めるのが正)。

## 8. 引き渡し 3 資産の形(第 3 群)

**対象の 3 資産を明示する(計画レビュー 1 周目 `P1-12` の訂正)** — 当初は seal 風の構造だけを指定しており、
**任意の 3 ファイルに版と digest を置けば条件を満たせた**。対象は次の 3 つに固定する:

| # | 資産 | 役割 |
| --- | --- | --- |
| 1 | `contracts/authz/ddl-elements.json` | **通った構成** — **`scope` の消化は改訂 3 第 2 弾の `S-7` の射程**(裁定 `D-10`。**現在のステップ表 1〜20 に `scope` 消化のステップは無い**)|
| 2 | `contracts/authz/auth-catalog.json` | **`CATALOG:*` の母集合**(187 entries・`enforcement_test_owner` が `implemented`)。**`AUTH-*` は実在しない** |
| 3 | `contracts/authz/rejected-configs.json` | **不採用構成**(`REJ-001`〜`REJ-003` + 第 2 群で追加した分) |

**この 3 パスを資産側(引き渡しマニフェスト)に明記する** — 受け手(TSK-343 / TSK-344)が
パスを推測しないで済むようにする。

**受け手が exact-set で突合できる形にする** — **実在する `catalog_entry_id`(= `CATALOG:*`。`AUTH-*` は 0 件 — 計画レビュー 2 周目 `P1-8` の訂正)**を
**成果 ID + blob digest** で特定できるようにし、
**ID 集合の sha256 を資産に持たせる**(受け手が件数を数え直さずに照合できる)。

`oracle-seal.lock.json` の構造を踏襲: `input_assets[]`(`path` + `git_blob_digest`)/
`sealed_assets[]`(`path` + `asset_role`(`expectation`/`evidence`)+ `asset_kind` + `canonical_sha256`)。
**期待値資産と証跡資産を別ファイルに保つ**(第 1 群の規律)。

### 8-2. `D-4` の 1:N 写像 — 要件側を自己申告にしない(計画レビュー 2 周目 `P1-11` の訂正)

要件書の 7 単位と資産の `operation_ids`(8)の対応を機械可読に持つ。**資産側 8 ID は凍結資産から導出**できるが、
**要件側 7 単位を新資産が自分で宣言すると、任意の 7 単位を書いて差集合 0 を作れる**。したがって:

| フィールド | 内容 |
| --- | --- |
| `requirement_source_digest` | **要件書の blob digest**(要件書が変わると red) |
| `requirement_units[].stable_id` | **`scripts/design_relations/req-universe.json` の安定 ID**(例 `FR-041/list_item-006`)。自由文の宣言を許さない |
| `requirement_units[].extraction_rule` | 抽出規則の ID(閉じた値域)。「どの列挙のどの項目を 1 単位と数えたか」 |
| `operation_ids[]` | 資産側の 8 ID(`route-registry.json` から導出) |
| `mapping[]` | 1:N の対応 + **前提条件の差**(`issue_invitation` = `participant_capacity` / `revoke_invitation` = `invitation_active`) |

**「7 操作」「8 操作」という件数の主張を資産に書かない** — 書くと実体と食い違う。
件数は双方を導出して**差集合 0** で示す。

## 9. 受取契約(`R-4`)— 弱めず、実在するタスクへ登録して read-back する

**計画レビュー 1 周目 `P0-6` の訂正。** 当初は「資産内の `test_owner.id` 文字列が一致すること」に縮めていたが、
**それは read-back ではなく自己照合**であり、`contract_only` の runtime テスト ID が
**実在する受取ゲートへ接続されない**。`R-4` が要求するのは受取タスクの DoD への登録・相互リンク・
**受取側からの exact read-back**・製品 adapter / manifest の事前凍結である。

**受取先の割り当て**(TSK-250 が分割されたため実 ID へ振り直す):

| 資産側の `test_owner.id` の系列 | 受取先 | 根拠 |
| --- | --- | --- |
| `TSK-250.runtime.*`(7 操作の状態遷移・招待の一回消費・同時受諾・最後の `admin` の離脱/降格・無効化時の終了・再有効化) | **TSK-250**(現存 — 残りの正本化を持つ) | `closure-handoff-data-model.json` が TSK-250 の受け取りを維持している |
| `TSK-250.management.*`(管理経路 8 操作) | **TSK-250** | 同上 |
| cache / 通知・操作ログ | **TSK-217**(HTTP 経路) | `NFR-010` の測定方法が API 直叩きを含む |

**read-back の形**(`[手動・外部]` を含む 3 段):

1. **登録** — 上表のテスト ID を**受取タスクの Notion DoD へ書き込む**(安定テスト ID つき)
2. **相互リンク** — 本タスクと受取タスクをコメントで相互に記録する(`URL` プロパティは `/pr` 専用)
3. **read-back** — **受取タスクの DoD を取得し、資産のテスト ID 集合と exact-set 突合する**
   (差集合 0 を機械で示す。取得結果を worklog に貼る)

**ステップの割り当て**: **改訂 3 第 2 弾の射程**(4 節 `S-6`)。本計画の承認範囲には入らない。

> **旧設計の残滓についての申し送り(5 周目 `P2-4`・`(B)` で第 2 弾へ)**: **本書 8-2 節が 7 単位の安定 ID を `req-universe.json` から取るよう指示している**が、**同ファイルに `list_item` は 0 件**であり、**source を決め直すことは plan.md 4 節の `S-3` の射程**である。**8-2 節は第 2 弾と明示済みで plan 側が正**なので第 1 弾の委任は阻害しないが、**第 2 弾で `S-3` を確定する際に本書 8-2 節も同時に是正する**。
**登録と相互リンクは外部手続きなので `[手動・外部]`、read-back の突合は `[機械]`** に書き分ける。

## 未解決・検討メモ

- **移行バッチ用ロールの検査は [TSK-349](https://app.notion.com/p/3d693b75e68781cdaa22f364955f9fab) が持つ** —
  計画レビュー 1 周目 `P0-4` が「検査責務の所有者が空」と判定したため、**実 ID で起票して受取先を閉じた**
  (プレースホルダの「新規起票」では閉じない)
- **正本側の 3 件は [TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5) が持つ**(裁定 `D-5`)—
  `search_path` の P0 / 返却契約の不一致 / 定義の言い換えによる重複。**本タスクは正本を変更しない**
- **設計書 10.1 の追随は TSK-343 が持つ**(`P1-14`)— `data-model.md` の受け取り先表がそう割り当てている
- **`closure-handoff-data-model.json` の「作成」と正本 `:2750` の「作成・実行」の差** — どちらを正とする条項が
  見つからない。本タスクは**probe クラスタ上での作成・実行まで**と読む(実スキーマは TSK-343 の成果)。
  差の解消は申し送り(research.md 5-U-8)
- **`ddl-elements.json` の `app_role` に `DELETE` がある**(`probe_business_rows` / `probe_management_effects`)一方、
  正本 3-2 節のアプリ用ロールは `SELECT`/`INSERT`/`UPDATE` で **`DELETE` に言及がない**。
  probe は製品スキーマではないので本タスクは資産どおり検証するが、**製品への引き渡し時に判断が要る**(申し送り)
- **`contracts/authz/` の ADR-003 `D-12` 適合** — 領域列挙に `authz` が無く、命名も `"version"` フィールドも規約と
  乖離している。**本タスクでは触らない**(`H-68` 対策)。申し送りで別起票
