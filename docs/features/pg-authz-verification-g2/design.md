---
feature: pg-authz-verification-g2
type: design
date: 2026-09-09
---

# 詳細設計: PostgreSQL 認可構成の実機検証 第 2 群・第 3 群

[plan.md](plan.md) 4 節から参照される詳細設計。

> **本改訂(計画改訂 3 第 2 弾)の承認範囲は 2 ステップである**(`core-areas.json` 登録 / 封印資産の確定と reseal — 裁定 `D-14`・`D-16`・`D-18`・2026-09-12)。
> **`S-9` は裁定 `D-15` で PR #3 へ、期待件数のハードコード撤去は裁定 `D-16` で別タスクへ送った。**
> **本書のうち 8 節(引き渡し 3 資産)・8-2(7→8 写像)・9 節(`R-4` の受取契約)は PR #3 の射程**であり、
> **本改訂の承認範囲には入らない。**
> **以下の記述は第 1 弾(PR #52 でマージ済み)についての記録である** — **ただし本書末尾の「試験設計」A〜F 節は現行 PR(改訂 3 第 2 弾)のためのもの**(裁定 `D-19`・2026-09-12)。
>
> **第 1 弾の承認範囲は第 2 群前半(ステップ 1〜20)だった**(裁定 `D-8` — **裁定 `D-9`(2026-09-10)で旧ステップ 17〔`contract_only` の runtime テスト〕を撤去し、旧 18〜21 を 17〜20 へ連番で振り直したため 21 → 20**)。
> **【2026-09-12 現在】本改訂(PR #2)の射程は `S-1`・`S-5`・`S-7` と `S-8` の一部(`core-areas.json` 登録)だけである**(裁定 `D-14`・`D-15`・`D-16`・`D-18`)。
> **`scope` の消化(`S-7`)は本改訂のステップ 2 に含まれる。**
> **改訂 3 第 2 弾が満たすべき要件の一覧は plan.md 4 節の `S-1`〜`S-10` が正**(**うち本改訂の射程は上記のとおり**)(**裁定 `D-10`(2026-09-10)で改訂 3 を 2 弾に分けた** — 第 1 弾は機械的な作業のみ、`S-1`〜`S-10` の機械条件の確定は**ステップ 17〜20 の完了後**)。
> **`S-10` は旧ステップ 17 の置き換えで、`contract_only` 158 行の runtime テストは受取タスクの所有である**(`R-7`)— **本タスクは実テストを書かない**。
**機構が読む状態と実装ステップ表は plan.md のみに置く**
(設計書 7.1-1)。前計画書の内容・凍結資産の中身・要件の逐語は**ここへ複製せず**、
[../pg-authz-verification/plan.md](../pg-authz-verification/plan.md) と [research.md](research.md) を参照する。

## 1. 配置

| 対象 | 配置 | 理由 |
| --- | --- | --- |
| DDL 生成器 | `backend/src/pitchlog/authz/ddl.py` | 製品コード側。**生成器そのものは第 1 弾のステップ 3 で実装済み**。**第 2 弾(`S-8`)へ送るのは `core-areas.json` への paths 登録だけ**である(現在このパスは `tenant-isolation.paths` へ未登録)|
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

**生成の検証方法**(第 1 弾ステップ 3 の合格条件の実装形):

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
| 1 | `contracts/authz/ddl-elements.json` | **通った構成** — **`scope` の消化(`S-7`)は本改訂(PR #2)のステップ 2 に含まれる**(**裁定 `D-10` 当時は「現在のステップ表 1〜20 に無い」と書いたが、その後 `D-14`・`D-18` で本改訂の射程に入った**) |
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

---

# 試験設計(**裁定 `D-19`・2026-09-12 で plan 4 節から移した**)

## A. 母集団の導出と探針の設計(**裁定 `D-19` で plan 4 節から移した**)

4. **母集団は列挙せず「導出元 + 導出器の全数性」で書く**(**型 A の是正**)。
   **「X・Y・Z を拾う」と書かない。** **「母集団 = 外部の閉じた集合 `S` から導出器 `f` で得る集合。
   `f` が `S` を取りこぼさないことを `S` 自身で示す」**の形に固定する。
   **全数性試験は述語の分岐ごとに割る**(19 周目 `P1-1`)— **`f` が OR や複合条件なら、分岐 1 つだけを満たす探針を分岐の数だけ作る**。
   **合成した探針が複数の分岐を同時に満たすと、片方しか実装しない導出器も通る**(**実証**: **`*_owner_task_id` は `owner` と `task_id` の両方を含むので、
   どちらか片方しか見ない導出器も `+1` になる**。**`owner` だけ / `task_id` だけの 2 本なら、欠けた分岐が `+0` で落ちる**)。

   **探針の生成** — **探針の置き場所も容器の型の並びから生成する**(20 周目 `P1-2` — **`g` と同じ機構**)。
   **並びは再帰の「遷移」しか覆わない**ので、**次の 2 軸を直積で足す**(21 周目):
   **① 兄弟要素の全数反復** — **系列の各段について、その段の容器を要素 2 個以上にし、2 個目以降に探針を置く**(23 周目 — **末端だけでは中間 `list` の 2 個目以降や `dict` の 2 番目以降の値を降りない走査が通る**)。
   **`dict` の段では 2 番目以降のキー、`list` の段では添字 1 以降**へ置く。
   **② leaf の型** — **`str` / `int` / `bool` / `null` / 空 `dict` / 空 `list`** を**それぞれ leaf に置く**(**型で leaf を取りこぼす走査を落とす**)。
   **「`dict` の中 / `list` の中 / 新しい `list`」の 3 種では、`dict→dict` や `list→list` のような系列を識別しない**。
   **深さ `d` までの並び(`2^1 + ... + 2^d` 通り、`d` はテストが実資産から計算する)それぞれの末端へ leaf を置いた探針を作り、すべてで `+1` になることを示す**。
   **実測(2026-09-12)**: **`dict→dict` / `dict→list` / `list→dict` / `list→list` を降りない 4 種の欠陥走査は、対応する系列の探針で `+0` になって落ちる**。

   **`S` の適格性は主観で判定しない。次の 3 問すべてが yes でなければ `S` にしない**
   (**「自分が作っていない」は主観語で、13・14 周目とも甘く判定していた**):

   | # | 問い | 落ちる例 |
   | --- | --- | --- |
   | 1 | **`S` をコマンド 1 本で再生成でき、その入力が本ステップの diff の外にあるか** | **本ステップで改変する資産・コードを入力にしている**(**版を `origin/develop` の blob へ固定すれば yes になる**)|
   | 2 | **計画書だけを書き換えたら `S` が変わるか。変わるなら no** | **確定値表・「5 配列」・「4 箇所」**|
   | 3 | **`f` は実行可能なコードで、`S` に対する全数性テストを持つか** | **日本語の規則のまま書いた述語**|

   **自分で列挙した集合を `S` にすると、列挙の縁が無検査になる。**
   **観測層で潰れる欠陥は、観測層を下げる**
   (例: **重複 JSON キーは解析後には消えるので `object_pairs_hook` か生テキストで見る**)。
5. **封印資産の値を変える負例は、semantic validator を直接呼ぶ**(**型 B の是正**)。
   **封印資産の変異は `seal` の digest 不一致だけでも必ず red になる**ので、
   **`check_authz_catalog.py` 全体を回して red を確認しても、目的の検査が効いている証拠にならない**
   (**検査を 1 行も書かなくても red になる** — 5・8・10・11・12 周目の `P1`)。
   **負例は当該 validator の関数を直接呼び、その関数が投げることを確かめる**
   (**「直接呼ぶか seal を追随させるか」の二択にしない** — 17 周目 `P1-4`)。

   **本規律が掛かるのは「封印資産の値を変える負例」だけである。**
   **検査コードを変異させる負例**(走査の無効化・深さ制限・対象集合の縮小)と、
   **CLI の副作用を見る負例**(通常検証で reseal されないこと)は**別の型**で、
   **それぞれ「当該コードを壊すと負例が red でなくなる」「seal と資産が食い違う状態で通常検証を回して seal がバイト不変」で確かめる**
   (**整合済みの seal でバイト不変を見るだけでは実効がない** — **reseal しても同じバイトになるので差が出ない**。21 周目)。
   **負例の形**: **semantic validation を通る変更を資産へ入れ、seal を古いままにし、通常検証を回す** → **seal が書き換わったら red**(**`--reseal-oracle` でだけ書き換わること**)。
   **「semantic を通る変更」が条件である**(23 周目)— **不正な変更を選ぶと検査器が reseal 処理へ達する前に終了し、負例が意味を持たない**。
   **具体形**: **`provenance[].extracted_text` の末尾へ空白を足す**など、**どの validator も拒否しないが canonical digest は変わる変更**(**実装時に semantic green であることを実測して worklog へ記録する**)。

> **条件 ID・3 点組ハーネス・母集団の導出器を機構として作ることは、
> 裁定 `D-18`(2026-09-12)で別タスクへ送った**
> — [合格条件の検査基盤を作る](https://app.notion.com/p/3d993b75e687810f8265fc44999fb9c2)。
> **`D-17` で本改訂の先行ステップへ切り出したが、基盤自体が新しい `P0` を 3 件生んだ。**
> **本改訂は規律 4・5 を「書き方の指針」として使い、機構化はしない。**

> **なぜ「測ったのに閉じたと書く」のか**(**規律 4 の根拠** — 2026-09-12 の相談で言語化した)。
> **変異実験には人が選ぶ自由度が 2 つある** — **① 変異を置く場所の母集団**
> (走査の入口・配列の選択・AST のノード種)と **② 変異の操作**。
> **「全変異が検出された」は ①② を固定した条件付きの主張**であり、
> **① の外にある欠陥については何も言わない**(**標本誤差ではなくカバレッジ誤差**)。
> **測定は検査器の性能を測るが、枠の妥当性は測らない** —
> **枠を選んだのが自分なら、測定結果は自分の選択を反射しているだけである。**

## B. 多重度の是正 — 2 層の試験設計(**plan 4 節から移した**)

**2-d 多重度の是正 — 2 層で書く**(**層ごとに射程が違う**)

**検査器は配列を `set` / `dict` へ畳んでから exact-set を比べる**ので、
**同じ行を複製しても多重度が潰れて green になる**。

**この PR が封印する形は正しい**(**実測 2026-09-12**: 凍結 15 資産の**全配列ノード 2341 本**
〔うち非空 2290 本・空 51 本〕を走査して**重複要素 0 件・重複 JSON キー 0 件**)。
**したがって本改訂の封印が壊れる危険はない。**

**多重度の是正は 2 層に分かれる。層ごとに射程が違うので、混ぜて書かない**(9 周目 `P1-1`):

| 層 | 何を守るか | 本改訂の射程 |
| --- | --- | --- |
| **① 検査器**(`check_authz_catalog.py`) | **検査器が配列を畳んで多重度を潰す**こと自体 | **`g` の出力すべて**。**残るのは重複 JSON キーだけ** |
| **② 資産の恒久検査**(`tests/`) | **凍結資産に重複が入る**こと | **base の seal が挙げる凍結 15 パスを恒久的に閉じる**(**全配列 + 全 JSON キー対の汎用走査**) |

**② は一回限りの実測ではなく恒久的なテストとして置く**(`tests/` 配下 —**実行証跡が CI に残り、将来の混入も止まる**)。

**② の走査自体を壊せないようにする**(10 周目 `P1-1`)— **正常な資産で「重複 0 件」を確かめるだけでは、走査を壊しても green になる**。
**次の 6 つの壊し方それぞれについて、負例で red を示す**:

| 壊し方 | 負例の形 |
| --- | --- |
| **走査が再帰しない**(最上位の配列しか見ない) | **入れ子の深さ 2 以上に重複要素を置いた資産**で red |
| **重複キーを `json.loads` の last-wins で潰す** | **重複 JSON キーを持つ資産**で red |
| **検査そのものが無効化されている** | **重複を 1 件入れた資産で必ず red**(**skip・空走査で通らない**) |
| **対象資産の集合を狭める**(凍結 15 のうち 1 つを外す) | **15 パスそれぞれに重複を入れた 15 の負例で red**(**1 資産ぶんを外すと 1 件が通ってしまう**) |
| **深さ制限つきの走査で通す** | **凍結 15 パスの最大容器深さは 8**(**実測 — `requirement-claims.json`**)。**その最深部に重複を置いた負例で red** |
| **分岐単位で例外を握り潰す** | **走査が実際に到達した配列パスの集合を assert する**(**到達しなかった配列があれば red** — 正常時の集合を固定する) |

**負例の資産は本物の凍結資産を変異させず、一時ディレクトリの写しで作る**(**本物を壊さない** — 第 1 弾の `_make_repository(tmp_path)` と同じ形)。

**同じ入口へ通す**(**資産ごとに別の呼び出しを書くと、1 つを外しても気づけない**)。
**対象資産の集合も列挙しない**(13 周目 `P1-5`)。

**層 ① と層 ② は `S` が違う**(23 周目 `P1-1` の是正 — **以前は「同じ `S`」と書いていた**):

| 層 | `S` | 理由 |
| --- | --- | --- |
| **① 検査器の多重度検査** | **base の seal の `sealed_assets[].path` 6 本 + seal 自身 = 7 パス** | **`input_assets` の 8 資産は別の入口で検査され、本改訂は触らない** |
| **② 資産の恒久検査** | **凍結 15 パス**(`sealed` 6 + `input` 8 + seal 自身) | **汎用走査なので validator の入口に依存しない** |

**`seal` 自身をどちらにも足すのを忘れない** — **`oracle-seal.lock.json` はどちらの配列にも登録されていない**(14 周目 `P1-5` の実測)。
**差分を `S` にしてはいけない** — **検証・コミットの時点でまだ変更が `HEAD` に無い**(17 周目 `P1-2`)。
**全数性**: **入口の分岐と容器の並びを直積で割る**(21 周目 — **別試験では「入口 A では深い配列を読むが入口 B では読まない」導出器が通る**)。**入口の分岐**は次のとおり — **① `sealed_assets[]` だけへ資産を 1 本足す ② `input_assets[]` だけへ 1 本足す ③ seal 自身を対象から外す**。**① ② はそれぞれ +1、③ は母集団が 1 減る**。
**「seal へ資産を 1 本足す」だけでは追加先を選べるので、片方の配列しか読まない導出器も、seal 自身を落とす欠陥も通る。**

**層 ① の対象配列も同じ形で導く** — **導出元 `S` = `git show origin/develop:contracts/authz/oracle-seal.lock.json` が挙げる
`sealed_assets[].path` と `input_assets[].path`、および seal 自身**(= **凍結 15 パス**)**の base 版の全コンテナ**、
**`g` の `S` は凍結 15 パスではなく 7 パスである**(22 周目 `P1-1` の是正)— 
**base の seal が `sealed_assets[].path` に挙げる 6 資産 + seal 自身**。
**`input_assets` の 8 資産は別の入口**(`validate_catalog` / `validate_derived_assets`)**で検査され、本改訂は触らない**ので**層 ① の射程外**である(**層 ② の汎用走査が凍結 15 パス全部を覆う**)。

**導出器 `g` = 「*いずれかの* 要素を複製しても、その資産の semantic validator が green のまま通る配列」。**
**先頭要素だけを複製する形にしない**(24 周目 `P1-4`)— **検査器が先頭だけを特別扱いする場合、先頭の複製は red でも 2 個目以降の複製は通る**。
**判定は「その配列の全要素について、それぞれ複製したときの結果」を取り、1 つでも green があれば母集団に入れる。**
**入口は資産の区分ごとに 1 つずつ固定する**(**選ぶ余地を残さない**):

| 対象 | 入口 |
| --- | --- |
| **`sealed_assets` の 6 資産** | `validate_oracle_assets(..., verify_seal=False)` |
| **seal 自身** | `validate_oracle_seal` |

**`verify_seal=False` は digest 検査だけを外すのではない**(22 周目 `P1-2` の実測)— 
**`check_authz_catalog.py:4693` は `validate_oracle_seal` の呼び出しごと省略する**。
**だから 6 資産については semantic だけを見る正しい入口になるが、seal 自身はこの経路では一切検査されない。**
**seal の配列は `validate_oracle_seal` を直接呼んで測る。**

**対象資産を「本改訂が変更する 3 資産」に絞らない**(17 周目 `P1-2`)— **それは私が列挙した集合で、規律 4 の問 2 に落ちる**。
**また `origin/develop...HEAD` の差分を入力にすると、検証・コミットの時点ではまだ変更が `HEAD` に無く成立しない**。
**実測は下記の表が正**(**過去の値と誤りの原因は worklog へ記録した**)。

**`g` は入力・検査器の両方を base へ固定する**(16 周目 `P0-1`):

| 固定するもの | 版 |
| --- | --- |
| 資産 | `git show origin/develop:contracts/authz/<name>` |
| 検査器 | `git show origin/develop:scripts/check_authz_catalog.py` |

**検査器だけを固定すると `g = ∅` になる** — **ステップ 2 後の `boundary-proposal` と `ddl-elements` は base 検査器が要求する旧 `status`/`scope` と意図的に異なるので、複製する前から red になる**(16 周目 `P0-1` の実測)。
**作業コピーの検査器で導出しても `g = ∅` になる** — **本ステップがその検査器を直すため**(15 周目 `P0-3`)。
**両方を base に揃えた状態は「本改訂が何も変えていない時点」であり、本ステップの diff の外にある**(規律 4 の問 1)。

**`g` の全数性**(規律 4 の問 3): **合成資産を列挙せず、容器の型の並びから生成する**。
**JSON の容器は `dict` と `list` の 2 種しかない**ので、
**深さ `d` までの容器の並びは `2^1 + ... + 2^d` 通りで閉じる**(**言語の仕様から来る集合で、私が選んでいない**)。
**`d` も私が選ばない** — **`d` = base の凍結 15 パスの最大容器深さ**(**テストが実資産から計算する**。18 周目 `P1-1`)。
**実測(2026-09-12): `d = 8`**(`requirement-claims.json`)→ **510 通り**。
**`d` を定数で持たない** — **資産が深くなれば試験も自動で深くなる。**
**510 通りそれぞれの末端へ配列を置いた合成資産を作り、走査が全部を訪れることを示す。**

**3 種を選ぶ形では足りない**(17 周目 `P1-3`)— **`dict→list` / `list→list` / `list→dict→list` を訪れながら `dict→dict→list` を省く走査器が作れ、実資産(`ddl-elements.json:665`)にその形がある**。
**実測: `dict→dict` を降りない欠陥走査は、14 通りのうち 5 件で検出される。**
**要素の型で入口を絞らない**(**7 周目に `dict` 限定で 10 本取りこぼした**)。

**`g` の出力を人が絞らない**(14 周目 `P1-6`)— **以前は「5 配列」と書いて
残り 10 配列を別タスクへ延期したが、`g` は 10 配列も返すので述語と延期が両立しなかった**。
**本改訂は `g` の出力すべてに検査を置く。**
**別タスクへ送るのは、`g` では捕まらない多重度の軸**である —
**① 重複 JSON キー**(**解析後には消えるので観測層を下げる必要がある**)・
**② (本改訂で解消 — 層 ② を凍結 15 パスへ広げた)**。
**下表は現時点の `g` の出力であって定義ではない。**
**① を `g` の出力に絞るのは、`g` では捕まらない軸(重複キー)が観測層を下げる作業を伴い、別タスクの射程だからである**
(**重複キーの検出には `_read_json` の `object_pairs_hook` が要る** — `:491`)。

> **【撤回】下表は 7 周目〜18 周目の測定で、入口が誤っていた。**
> **現行の実測は後述の 18 本の表が正**(22 周目に入口を是正)。

| 資産 | 配列 | 要素の型 |
| --- | --- | --- |
| `oracle-seal.lock.json` | `input_assets` | dict |
| `boundary-proposal.json` | `boundaries` | dict |
| `boundary-proposal.json` | `pending_human_reviews` | dict |
| `boundary-proposal.json` | `pending_human_reviews[0].affected_ids_if_changed` | **str** |
| `ddl-elements.json` | `transaction_boundaries` | dict |
| `ddl-elements.json` | `transaction_boundaries[0..2].step_ids`(3 本) | **str** |
| `ddl-elements.json` | `provisioning_claim.completion_catalog_expectations` | dict |
| `ddl-elements.json` | `tables[0..5].row_shape_ids`(6 本) | **str** |

**実測(2026-09-12・資産の区分ごとの入口)**: **7 パスの非空配列 1676 本のうち `g` の出力は 18 本。**

| 資産 | 配列 |
| --- | --- |
| `ddl-elements` | `tables[0..5].row_shape_ids`(6)/ `transaction_boundaries` / `transaction_boundaries[0..2].step_ids`(3)/ `provisioning_claim.completion_catalog_expectations` |
| `claim-mutant-map` | `kill_contract.conditions` |
| `attack-tree` | `attack_goals` |
| `boundary-proposal` | `boundaries` / `pending_human_reviews` / `pending_human_reviews[0].affected_ids_if_changed` |
| `verification-evidence` | `residual_risks` |
| `oracle-seal.lock` | **`input_assets` のみ** |

**`sealed_assets` は `g` に出ない** — **`validate_oracle_seal:4582` が `if path_text in sealed_by_path: raise` で既に重複を拒否している**(5 周目に確認済み)。
**前周の「19 本」に `sealed_assets` が入っていたのは、`verify_seal=False` で seal がまったく検査されていなかったためである。**

**過去の実測は 3 回とも誤っていた**:

| 周 | 値 | 誤りの原因 |
| --- | --- | --- |
| 7 | 5 本 | **走査の入口を `dict` 限定にしていた** |
| 17 | 16 本 | **資産ごとに別の validator を呼び 5 資産しか測れていなかった** |
| 21 | 19 本 | **`verify_seal=False` で seal が一切検査されず `sealed_assets` が偽陽性で入った** |

**上表は実装時に測り直して worklog へ記録する**(**数を計画書から取らない**)。

> **【撤回】7 周目に「変異で測ったので母集団は閉じた」と書いたが誤りである。**
> **走査の入口を「`dict` を要素に持つ配列」と私が選んだ**ため、
> **文字列の配列が漏れていた**(`pending_human_reviews[0].affected_ids_if_changed` /
> `tables[0..5].row_shape_ids` / `transaction_boundaries[0..2].step_ids` — **計 10 配列**)。
> **さらに JSON オブジェクトの重複キーは、解析後のオブジェクトを走っても観測できない**
> (`_read_json` が `json.loads` の last-wins で潰す — `:491`)。
> **「閉じる対象を人が選んだ」という、本 PR で 4 度目の同じ失敗である。**

**別タスクへ送ったもの** —**[authz 凍結資産の多重度を検査器で閉じる(重複行・重複キー)](https://app.notion.com/p/3d993b75e68781b59bd3c55024f9ffea)**:

- **層 ①**: **重複 JSON キー**(`_read_json` の読み取り経路を変える — **観測層を下げる**)

**本改訂は「層 ① を `g` の出力」+「層 ② を凍結 15 パス」である。**
**どちらも base の seal から導き、私が列挙した集合を使わない。**
**実測値は実装時に取って worklog へ記録する。**

`[機械]` **`g` が出力する全配列に行数と要素一意性の検査がある**・
**負例: `g` の出力それぞれで先頭要素を 1 件複製すると、多重度検査が red を出す**
(**seal の digest 不一致では判定しない** — `ddl-elements` と `boundary-proposal` は
**digest 不一致だけでも必ず red になる**ため、**それでは検査を 1 行も書かなくても負例が通る**
〔8 周目 `P1-3`〕。**規律 5 のとおり semantic validator を直接呼ぶ**)・
**負例: 多重度検査を外すと上記の負例が red でなくなる**・
**既に red だった配列の検査は変えない**。

## C. `core-areas.json` の登録先の導出(**plan 4 節から移した**)

**負例の母集団**(規律 4): **導出元 `S` = `scripts/*.py` と `tests/test_*.py` の実在ファイル**。**導出器 `f` = 機械判定できる述語**(**日本語の規則をそのまま条件にしない** — 13 周目 `P1-2`)。
**「ファイルを開く」の判定方法も固定する**(21 周目)— **検査器を子プロセスで実行し、`sys.addaudithook` の `open` イベントで実測する**。
**関数を差し替える形にしない**(23 周目 — **実測で確認**)— **`Path.open()` と `Path.read_text()` は `builtins.open` ではなく `io.open` を呼ぶ**ので、**`builtins.open` だけを差し替えても捕捉できない**。**`io.open` / `os.open` も要る。**
**監査フックは言語仕様の機構で、経路を列挙しなくてよい** — **実測で `builtins.open` / `io.open` / `Path.open` / `Path.read_text` / `os.open` の5 経路すべてを捕捉した。**
**静的な文字列検索にもしない** — **`Path` 定数・別名・helper 経由・動的結合を取りこぼす**。
**述語の本体**:**「`contracts/authz/` 配下のファイルを開く、または `git show origin/develop:.claude/core-areas.json` の `areas[].paths` にマッチするファイルを開く `scripts/check_*.py` と、その**名前の対** `tests/test_<検査器のファイル名>`」**。
**「対」は名前の規約で決める**(17 周目 `P1-1` の実測)— **`import` を条件にすると 0 本になる**(**実測: `check_*` 系 4 本はすべて `subprocess` 実行で import していない**)。**`subprocess` を条件にすると別の検査器が入る。**
**名前の対応 `scripts/check_X.py` ↔ `tests/test_check_X.py` は実測で全 8 本に存在する**(**対の無い検査器 0 件**)。
**`core-areas.json` の版も base へ固定する**(**自己監査 2026-09-12**)— **ステップ 1 がその `core-areas.json` を変更するので、作業コピーを参照すると `g` と同じ循環になる**(**登録したパスが述語の入力へ戻り、母集団が自分の出力で膨らむ**)。**全数性**: **述語の分岐ごとに探針を作る**(19 周目 `P1-1`)— **① `contracts/authz/` 配下だけを開く検査器**と**② `areas[].paths` にマッチするファイルだけを開く検査器**を**それぞれ 1 本足した合成ツリーで、母集団が 2 ずつ増える**。
**両方を満たす検査器 1 本だけでは、片方しか実装しない導出器も通る。**
**対の有無も分岐である** — **対の無い検査器を 1 本足すと母集団が 1 しか増えない**ことも示す。**`f` の出力は既登録分を含む**(**実測 2026-09-12: 検査器 8 本 = 16 パス。うち `check_design_propagation` / `check_doc_coverage` / `check_processing_stages` の 6 パスは既登録**)。**本改訂が追加するのはその差分 10 パスである。****合格条件は「`f` の出力すべてが `guard_paths` に登録されている」を本改訂のテスト内で 1 度確かめるところまで**である。**これを恒久テストとして常時発火させると、未登録の 11 本目を検出する導出型検査そのものになり、裁定 `D-13` の送り先と衝突する**(15 周目 `P1-7`)。**恒久化は別タスクの射程**([core-areas.json の登録を導出型の検査で閉じる](https://app.notion.com/p/3d993b75e68781e6bcb4e42c79ddd789))。**本改訂は `f` の出力を「実装時点で 1 度測り、その結果を worklog へ記録する」** —**`f` を呼ぶ恒久テストを `tests/` へコミットしない**(**コミットすれば常時発火する導出型検査そのものになる** —16 周目 `P1-3`)。**`tests/` へ入れるのは「4 節の表が列挙する 19 件が登録されている」という固定の検査だけ**で、**11 本目の検出は別タスクが恒久化する。****下表は差分の内訳であって母集団の定義ではない。****母集団の各要素を 1 件ずつ外すと red**(**「いずれか 1 件」ではなく全件**)。**`guard_paths` は完全一致なので、パスの大小文字を変えるだけでも red**。**規律 5 により、当該検査を外すと 19 件の負例が red でなくなることを示す**。`[手動・外部]` **6.3 規則⑤の敵対レビュー + 人間承認**

**`guard_paths`(完全一致・`frozenset`)へ 10 本** — 規則「**凍結資産またはコア領域の成果物を検査する検査器とその対**」:

| 検査器 | 対(テスト) |
| --- | --- |
| `scripts/check_authz_catalog.py` | `tests/test_check_authz_catalog.py` |
| `scripts/check_authz_function_bodies.py` | `tests/test_check_authz_function_bodies.py` |
| `scripts/check_mcdc_map.py` | `tests/test_check_mcdc_map.py` |
| `scripts/check_failure_injection_points.py` | `tests/test_check_failure_injection_points.py` |
| `scripts/check_shared_preconditions.py` | `tests/test_check_shared_preconditions.py` |

**`areas[].paths`(`tenant-isolation`・`fnmatch` で `*` が `/` を跨ぐ)へ 9 パターン** —
**既登録との差分だけを足す**(`scripts/check_authz_catalog.py` と `tests/test_check_authz_catalog.py` と
`contracts/authz/*` は**既に登録済み**であり、**再登録しない**):

`scripts/check_authz_function_bodies.py` / `scripts/check_mcdc_map.py` /
`scripts/check_failure_injection_points.py` / `scripts/check_shared_preconditions.py` /
`tests/test_check_authz_function_bodies.py` / `tests/test_check_mcdc_map.py` /
`tests/test_check_failure_injection_points.py` / `tests/test_check_shared_preconditions.py` /
`backend/src/pitchlog/authz/*`

**「9 パターン」はパターンの数であって、ファイルの数ではない**(実測 2026-09-12)— **検査器 4 + テスト 4 = 8 本のパターンが 8 ファイルを、`backend/src/pitchlog/authz/*` の 1 本が 4 ファイルを覆い、合計 12 ファイル**。
**`fnmatch` の `*` が `/` を跨ぐ**ので、1 パターンが階層をまたいで覆う。

**本改訂は `f` を負例の母集団の導出にだけ使い、「規則に合致するのに未登録の 11 本目」を本番検査として常時発火させることはしない**(裁定 `D-13`)。
**この 2 つは別物である**(13 周目 `P1-2` の自己矛盾の解消) — **前者は本改訂のテストが負例を作るために `f` を呼ぶだけ**で、**後者は `core_guard.py` の本番経路へ導出型の判定を組み込むこと**を指す。**後者が別タスクの射程である。**
**導出型の一般化は別タスクの射程**であり、**`PR #56` の `schema_contract_asset_paths()`
(`tests/test_core_guard.py:778`)が同型の先例である** — **同じ形をここで作ると、
別タスクへ送った範囲を二重に持つことになる**(4 周目 `P1-6`)。
**本改訂の合格条件は「`f` の出力すべてが登録されており、1 件外すと red」である**(**`f` の出力 = 既登録 6 パス + 本改訂が足す 10 パス**。**下表はその差分 10 パスの内訳であって、合格条件の母集団ではない**)。

## D. owner の母集団と全数性(**plan 4 節から移した**)

**全数性**: **2 つの軸を直積で割る**(21 周目 — **別々に試すと `task_id` はトップレベルだけ・`owner` は全深度を読む導出器が通る**):
**① 述語の分岐**(19 周目 `P1-1`)— **`owner` だけを含むキー**と**`task_id` だけを含むキー**を**それぞれ 1 つ足すと母集団が 1 増える**。**`*_owner_task_id` のような両方を含むキーだけでは、片方しか見ない導出器も通る**(実測)。
**② 再帰の分岐**(20 周目 `P1-1`)— **探針の置き場所を容器の型の並びから生成する**(規律 4 の「探針の生成」)。**トップレベルの `dict` へ足すだけでは、配列の中を降りない導出器も通る**。
**削除する leaf(`CONTROL-READS` の owner)は base 側にあるので母集団に残る。**

## E. seal の全 leaf の母集団(**plan 4 節から移した**)

**負例の母集団**(規律 4): **導出元 `S` = `git show origin/develop:contracts/authz/oracle-seal.lock.json` の全 leaf**
(**トップレベルキーではなく leaf** — **配列行の `path` / `asset_role` / `asset_kind` まで含める**。
**「全フィールド」と書いて digest だけ変異させていた** — 15 周目 `P1-8`)。
**導出器 `f` = 資産を再帰的に走り、全 leaf のパスを返す**。
**全数性**: **探針の置き場所を容器の型の並びから生成する**(規律 4 の「探針の生成」)。

## F. `S-5` の leaf の母集団(**plan 4 節から移した**)

**負例の母集団**(規律 4 —**自分で列挙しない**):

| 導出元 `S` | 導出器 `f` | 全数性の示し方 |
| --- | --- | --- |
| **`git show origin/develop:contracts/authz/boundary-proposal.json` の全 leaf**(**base のみ** — **変更後を入れると本ステップの diff が入力になり規律 4 の問 1 に no**。16 周目 `P1-2`) | **base を再帰的に走り、全 leaf のパスを返す** | **探針の置き場所を容器の型の並びから生成する**(規律 4 の「探針の生成」)。**`dict` の中だけへ足す探針では `list` を降りない走査器も +1 になる**(**実測: 完全な走査 88 leaf に対し `list` を降りない走査は 11 leaf しか見ない**) |
