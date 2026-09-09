---
feature: pg-authz-verification-g2
type: design
date: 2026-09-09
---

# 詳細設計: PostgreSQL 認可構成の実機検証 第 2 群・第 3 群

[plan.md](plan.md) 4 節から参照される詳細設計。**機構が読む状態と実装ステップ表は plan.md のみに置く**
(設計書 7.1-1)。前計画書の内容・凍結資産の中身・要件の逐語は**ここへ複製せず**、
[../pg-authz-verification/plan.md](../pg-authz-verification/plan.md) と [research.md](research.md) を参照する。

## 1. 配置

| 対象 | 配置 | 理由 |
| --- | --- | --- |
| DDL 生成器 | `backend/src/pitchlog/authz/ddl.py` | 製品コード側。**`core-areas.json` へ未登録**なのでステップ 20 で登録する(6.3 規則⑤) |
| 適用器 | `backend/src/pitchlog/authz/provisioning.py` | 同上。psycopg 直書き(`D-3`) |
| カタログ検査 | `backend/src/pitchlog/authz/catalog.py` | 同上。**問い合わせだけを持ち、期待値は資産から読む** |
| 変異の適用 | `backend/tests/db/authz/mutation.py` | **テスト側**に置く。製品コードに変異機構を入れない |
| 越境テスト・行列 | `backend/tests/db/authz/test_*.py` | `backend/tests/db/*` は既に `tenant-isolation.paths` に登録済み |
| 4 ロール fixture | `backend/tests/db/conftest.py` の拡張 | 既存の `tested_role_connection` の形を踏襲(`backend/*conftest.py` は登録済み) |

**`backend/src/pitchlog/authz/` の 3 モジュールは責務で分ける** — 生成(資産 → SQL 文字列)/
適用(SQL → クラスタ・順序と原子性)/ 検査(クラスタ → 観測値)。
**検査モジュールに期待値を持たせない**(自己 oracle 化を防ぐ — 前計画書のステップ 5 の趣旨)。

## 2. DDL 生成器の入力契約

**入力は `contracts/authz/ddl-elements.json` のみ。** 生成器は資産以外の定数を持たない。

| 資産の節 | 生成物 | 落としてはいけない属性 |
| --- | --- | --- |
| `roles`(7) | `CREATE ROLE` | `login` / `bypass_rls` / `create_role`(`shared_fn_owner` と `management_fn_owner` は **`NOLOGIN` + `BYPASSRLS`**) |
| `schemas`(3) | `CREATE SCHEMA` + owner | 所有ロール |
| `tables`(6) | `CREATE TABLE` + `ENABLE ROW LEVEL SECURITY` + **`FORCE ROW LEVEL SECURITY`** | **6 表すべてが `rls_enabled` かつ `force_rls`** |
| `predicates`(1) / `policies`(6) | `CREATE POLICY` | `polcmd` / `polroles` / `polpermissive` / `polqual` / `polwithcheck` に対応する 5 属性 |
| `functions`(3) | `CREATE FUNCTION` + `SECURITY DEFINER` + `SET search_path` | **`search_path` は末尾 `pg_temp`**(`REJ-003`)/ `public_execute: false` |
| `acl_expectations`(17) / `column_acl_expectations`(1) | `REVOKE` + `GRANT` | **関数作成と `REVOKE ALL ... FROM PUBLIC` を同一トランザクション**に置く |

**生成の検証方法**(ステップ 2 の合格条件の実装形):

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

**原子性**: 全体を 1 トランザクションで実行する。`R-5` の失敗点 5 種は**注入位置を資産由来の列で持つ**
(ロール作成後 / policy 変更後 / body 置換後 / owner 変更後 / ACL 正規化途中)。
比較対象は**全対象 catalog・membership・default ACL・fixture data**。

**冪等性**: `CREATE OR REPLACE` + `ALTER ... OWNER TO` + **ACL の全正規化**。
「古い直接 `GRANT` が 1 回目と 2 回目の双方で消えている」ことを要求する(差分適用にしない)。

## 4. カタログ検査の検査 ID 体系

**`CATALOG:<対象>:<観点>`** の形で ID を与え、**資産の要素 ID と 1:N で結ぶ**。
期待値は資産から読み、検査モジュールは**観測クエリと正規化だけ**を持つ。

| 検査 ID の系列 | 観測対象 | 由来 |
| --- | --- | --- |
| `CATALOG:POLICY:*` | `pg_policy` の `polcmd` / `polroles` / `polpermissive` / `polqual` / `polwithcheck` を正規化して exact 比較 | 前計画書 4 節「読み取りだけでなく書き込み」 |
| `CATALOG:FUNCTION-DIGEST:*` | `pg_get_functiondef` / owner / language / security / volatility / leakproof / strict / parallel / `proconfig` / ACL の **10 属性の digest** | **`R-1`** |
| `CATALOG:REACHABILITY:*` | 危険終点 = **`rolsuper OR rolbypassrls OR 保護 relation/schema/routine の owner`** と、アプリ・管理呼び出し・outsider からの `SET` 到達集合の**交差が空** | **`R-2`** |
| `CATALOG:ACL:*` | 表 ACL・**列 ACL**・**schema ACL**・**default ACL**。`PUBLIC` が含まれないこと | 前計画書 4 節「カタログ検査」 |
| `CATALOG:SEARCH-PATH:*` | **末尾が `pg_temp` で、かつ `pg_temp` の出現回数が 1** | `REJ-003` / 既存 `scripts/check_authz_catalog.py:2910-2911` と同じ述語 |
| `CATALOG:PROVISIONER-*` | 上記 `completion_catalog_expectations` の 2 件 | **`R-8`** |
| `CATALOG:OWNED-OBJECTS:*` | **`BYPASSRLS` ロールが所有する全 object** と **全 `SECURITY DEFINER` routine** が exact-set(採用構成外の関数が 1 件増えると red) | 前計画書 4 節 |

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
- **DSN は期待値資産から名前を引く**(既存 `_dsn_names`・`:40-53` の形)。新規 2 本の DSN 名も
  `environment-expectations.json` の `dsn_environment_variables` へ**先に固定**してから配線する
  (`oracle_policy.expectations_must_precede_observation_code: true`)

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
`two_factor_interactions` から読む。**MC/DC は `mcdc_decision_forms` の各判定形**について満たす。

## 7. 越境テストの構造

**正例**(`positive_cases.cases` 6 件)と**拒否例**を、`http-route-matrix.json` の `cells`(12・allow 6 / deny 6)と
**テスト ID で 1:1 に結ぶ**(ID 集合の sha256 で exact-set)。

**関数が返す形の要求**(`data-model.md` 3-6 節):

- **越境関数は「許可された業務行」を返す**形にし、**許可された行だけが返る**ことを試験する
- **集計は関数に書かない**
- **下段 4 行(常に 404)は「返す経路を持たない」形**にする。付与の値で分岐させない
  → **テストは「返らない」ではなく「そのシグネチャが存在しない」ことも確認する**
- 関数は **`group_id` を必須引数に取り、内部で当該グループに紐づく付与だけを見る**

**第 2 層(認可行列)の検査**(同 3-6 節・敵対レビュー P0-2 の是正):
6 前提を満たした要素それぞれについて、要求粒度の行を認可行列から引き、
**`相手の付与 ∧ 要求元の付与` の双方**を検査する。**とくに「対象側は非共有・要求元だけ付与」の組み合わせ**。

**選手個別の行フィルタ**: **`kind = 'self'` かつ在籍区分が現役(`active`)の選手だけ**。
**チーム集計には在籍フィルタを掛けない**(OB が出場した過去試合も含めるのが正)。

## 8. 引き渡し 3 資産の形(第 3 群)

**受け手が exact-set で突合できる形にする** — `AUTH-*` を**成果 ID + blob digest** で特定できるようにし、
**ID 集合の sha256 を資産に持たせる**(受け手が件数を数え直さずに照合できる)。

`oracle-seal.lock.json` の構造を踏襲: `input_assets[]`(`path` + `git_blob_digest`)/
`sealed_assets[]`(`path` + `asset_role`(`expectation`/`evidence`)+ `asset_kind` + `canonical_sha256`)。
**期待値資産と証跡資産を別ファイルに保つ**(第 1 群の規律)。

**`D-4` の 1:N 写像**: 要件書の「7 操作」と資産の `operation_ids`(8)の対応を、
**前提条件の差つきで**機械可読に持つ(`issue_invitation` = `participant_capacity` /
`revoke_invitation` = `invitation_active`)。**「7 操作」という件数の主張を資産に書かない** —
書くと 8 件の実体と食い違う。

## 未解決・検討メモ

- **`R-4` の受取先** — 前計画書は「TSK-250 の DoD へ登録して read-back」と書くが、TSK-250 は分割された
  (正本化 = TSK-342 完了 / `models`・`migration` = TSK-343 / ゲート再実行 = TSK-344)。
  **本タスクは資産の `test_owner.id` 文字列(`TSK-250.management.*` / `TSK-250.runtime.*`)を維持し、
  read-back は「文字列が資産と一致すること」の機械検査に留める**。受け手のタスク再編は射程外(research.md 5-U-7)
- **`closure-handoff-data-model.json` の「作成」と正本 `:2750` の「作成・実行」の差** — どちらを正とする条項が
  見つからない。本タスクは**probe クラスタ上での作成・実行まで**と読む(実スキーマは TSK-343 の成果)。
  差の解消は申し送り(research.md 5-U-8)
- **`ddl-elements.json` の `app_role` に `DELETE` がある**(`probe_business_rows` / `probe_management_effects`)一方、
  正本 3-2 節のアプリ用ロールは `SELECT`/`INSERT`/`UPDATE` で **`DELETE` に言及がない**。
  probe は製品スキーマではないので本タスクは資産どおり検証するが、**製品への引き渡し時に判断が要る**(申し送り)
- **`contracts/authz/` の ADR-003 `D-12` 適合** — 領域列挙に `authz` が無く、命名も `"version"` フィールドも規約と
  乖離している。**本タスクでは触らない**(`H-68` 対策)。申し送りで別起票
