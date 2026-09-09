---
feature: pg-authz-verification-g2
type: research
date: 2026-09-09
---

# 調査メモ: PostgreSQL 認可構成の実機検証 第 2 群・第 3 群(TSK-317)

調査サブエージェント 3 本(要件突合 / 決定経緯 / 資産実測)+ Claude による原典の直接確認。
**すべての事実に典拠を付ける。典拠のないものは「不明」と書く。**

## 問い

1. 第 1 群で凍結した oracle は、TSK-342 が新設した `docs/design/data-model.md`(approved v0.1)と整合するか。
2. `NFR-019`(b) の越境テストの要求の全数と、本タスクが担う範囲・残す範囲の境界。
3. 12-4 節の越境テスト再実行ゲートにおける TSK-317 と TSK-344 の責務境界。
4. 第 2 群・第 3 群で新設が必要な資産と、既存資産のうち書き換え禁止のもの。
5. 実機検証を実行できる環境が揃っているか。

## 結論(要約)

1. **approved 正本に P0 級の欠陥が 1 件ある** — `data-model.md:240` が `search_path` の契約として
   「一時スキーマを `search_path` から外す」と定めるが、**第 1 群がこれを実 PostgreSQL 17.11 で
   「誤り」と実測して凍結している**(`REJ-003`)。**正本の改訂が第 2 群の前提**になる(下記 1-1)。
2. **裁定を先に取らないと高くつく** — 凍結資産自身が**人間の裁定待ち 2 件**を記録し、
   いずれも `oracle_change_action: return_to_step_5_and_re_review` を持つ。封印は 6 資産の
   digest 全体なので**ロール 1 件の追加でも発火する**(下記 2)。
3. **本タスクは `NFR-019`(b) の 13 クラスのうち 1 クラス分にしか届かない**。`NFR-010` は
   測定方法が「API 直叩き含む」なので DB 層だけでは満たせない。**「NFR-010 適合」と主張してはならない**(下記 3-1・3-2)。
4. **実機検証の実施主体が未確定** — 開発 DB は環境変数の実値なしに起動せず、`psql` も未導入。
   委任先のサンドボックスはネットワーク遮断・シークレット非コピーである(下記 0・5-U-11)。
5. **`core-areas.json` への登録はほぼ済んでいる** — 前計画書 `plan.md:124` の「登録は第 2 群の射程」は陳腐化。
   残るのは第 2 群で新設する `backend/src/**` 配下のみ(下記 4-4)。

## 詳細と典拠

### 0. 実行環境の実測(2026-09-09・Claude が直接実測)

| 事実 | 実測値 | 計画への影響 |
| --- | --- | --- |
| Docker | **29.1.3**・稼働中コンテナ **0 件** | 開発 DB は起動していない |
| `docker compose config` | **失敗** — `services.db.environment.POSTGRES_USER: required variable POSTGRES_USER is missing a value` | **開発 DB は環境変数の実値が無いと起動しない**。実値の用意は人間の作業(`NFR-014` — 設計書 12.1) |
| `psql` クライアント | **未導入** | 実機検証は **psycopg 3 経由**に限る。`psql` 前提の手順を計画に書けない |
| `secret_guard` の挙動 | 設定テンプレートを含むコマンドも遮断する(**台帳の既知の誤検知が再現**) | 設定変数名は `backend/tests/db/conftest.py` 側から取った(実測: `PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN`) |
| `codex_guard` の挙動 | 本 research.md の本文に委任先の名を含めた heredoc を**生実行と誤検知して遮断**した(同型の誤検知) | 文書作成は Write 経由で行う。台帳の候補になり得る観測 |

### 1. 正本と凍結資産の食い違い(Claude が原典で確認)

#### 1-1. **【P0】`search_path` の契約が、実測で「誤り」と判定された記述のまま正本に残っている**

**正本の側**(`docs/design/data-model.md:240` — 3-2 節の契約表の 1 行):

```
| **一時スキーマ** | 書き込み可能スキーマ・一時スキーマを `search_path` から外す |
```

**凍結資産の側**(`contracts/authz/rejected-configs.json` の `REJ-003` — 実測値):

| フィールド | 実値 |
| --- | --- |
| `configuration_id` | `SEARCH_PATH_WITHOUT_EXPLICIT_TRAILING_PG_TEMP` |
| `verification_environment` | `postgresql_17_11_real_instance` |
| `candidate_statement` | **`remove_temporary_schema_from_search_path`** |
| `candidate_statement_status` | **`incorrect`** |
| `corrected_expectation` | **`place_pg_temp_explicitly_last`** |
| `observed_result` | **`temporary_relation_hijack_returned_attacker_rows`** |
| `rejection_reason_id` | `IMPLICIT_PG_TEMP_PRECEDES_LISTED_SCHEMAS` |

**判定 = P0**(7.3-3「挙動・データ・安全が壊れる」)。**正本の記述に従うと一時リレーションによる乗っ取りが成立する**
(実測結果が `temporary_relation_hijack_returned_attacker_rows`)。`pg_temp` を列挙から外すと**暗黙の
`pg_temp` が列挙スキーマより前に来る**のが原因で、正しい対処は**末尾に明示すること**である。

**なぜ TSK-342 の確定ゲート 13 周が捕まえなかったか**(推測): 反証は `contracts/authz/` にあり、
**同ゲートのレビュー射程は正本本文だった**。正本側は `pg_temp` を 1 度も書いていない
(`grep -n "pg_temp" docs/design/data-model.md` の一致 = **0 件**。`:240` は「一時スキーマ」という別名)。
**台帳 `H-79`(同種の欠陥を全経路へ適用せず字面で検索して取りこぼす)の型**である。

**実装側は正しい**: `ddl-elements.json` の関数 3 件の `search_path` 実値は
`["pg_catalog","authz_private","pg_temp"]`(2 件)/ `["pg_catalog","management_private","pg_temp"]`(1 件)で
**いずれも末尾 `pg_temp`**。`scripts/check_authz_catalog.py:2910-2911` も
「`search_path` の末尾が `pg_temp` で、かつ `pg_temp` の出現回数が 1」を検査している。
**食い違っているのは正本の 1 行だけ**である。

→ **`docs/design/data-model.md` の改訂が必要**。ゲート区分は 7.6 の決定表で判定する(下記 5-U-12)。

#### 1-2. **アプリ用ロールの `DELETE` が正本で扱われていない**

| 側 | 実測 |
| --- | --- |
| 正本 `data-model.md:204` | 「**業務表への `SELECT` / `INSERT` / `UPDATE` を持つ**…**`TRUNCATE` と `REFERENCES` は与えない**」— **`DELETE` に言及がない** |
| 凍結資産 `ddl-elements.json` の `acl_expectations` | `ACL:probe_business_rows:app_role` = **`["SELECT","INSERT","UPDATE","DELETE"]`** / `ACL:probe_management_effects:app_role` = 同じ 4 権限。他 4 表は `["SELECT"]` のみ |

要件書は **`4.0-2`「物理削除しない」**(削除はすべて論理削除 — AGENTS.md のコーディング規約が引く)を課している。
**probe 表は製品スキーマではない**(`ddl-elements.json:10` `product_schema: false`)ので現時点の矛盾ではないが、
**第 3 群が「通った構成」を製品へ渡すときに `DELETE` が付いてくる**。
**正本の役割表が `DELETE` の可否を決めていない**ため、渡す側で決めるか正本へ送るかの判断が要る(下記 5-U-13)。

#### 1-3. 「4 ロール」と「5 ロール」は差ではなく**軸違い**(当初の仮説は誤り)

正本の 5 分類(`data-model.md:201-207`)と、前計画書の実行行列 4 本(`plan.md:354-356`)は**別の軸**である。
後者は「**`LOGIN` できるロール**」で切っており、`NOLOGIN` の関数所有ロールは原理的に実接続の行列に入らない
(同 `:354`「**`NOLOGIN` の関数所有ロールは実接続できない**ため実行行列に入れられない。
関数所有ロールは**カタログ検査の対象**とする」)。

凍結資産 `ddl-elements.json` の `roles` は **7 件**(Claude 実測):

| `role_id` | `role_kind` | login | bypass_rls | 正本 3-2 の 5 分類との対応 |
| --- | --- | --- | --- | --- |
| `provisioner` | `external_provisioner` | true | **true** | 5 分類に無い(構築主体) |
| `table_owner` | `object_owner` | true | false | マイグレーション用 |
| `app_role` | `tested_caller` | true | false | アプリ用 |
| `shared_fn_owner` | `function_owner` | **false** | **true** | 共有関数所有用 |
| `management_fn_owner` | `function_owner` | **false** | **true** | 管理関数所有用 |
| `outsider_role` | `negative_test_caller` | true | false | 5 分類に無い(負例) |
| `management_caller` | `management_caller` | true | false | 5 分類に無い(管理関数の呼び出し元) |

**凍結資産に無い正本のロールは「移行バッチ用」(`LOGIN` + `BYPASSRLS`・期間限定)の 1 件だけ**。
Claude 実測: `ddl-elements.json` に `migration` / `移行` / `batch` / `FR-038` が**各 0 件**。
かつ `data-model.md` の TSK-317 宛の送り先の列挙(`:2631`・`:2750`)は
「`BYPASSRLS` / `NOLOGIN` / 関数 ACL / `search_path` / `FORCE RLS` の組合せ」であり、
**`LOGIN` + `BYPASSRLS` の期間限定ロールは列挙に入っていない**。
→ `data-model.md:289`「**移行完了後に属性が残っていないことを検査する**」の**所有者が空**(下記 5-U-1)。

### 2. 凍結資産が記録している「人間の裁定待ち」(Claude が原典で確認)

`contracts/authz/boundary-proposal.json` の `pending_human_reviews`:

| `review_id` | `status` | `frozen_value` | 代替 | 影響 |
| --- | --- | --- | --- | --- |
| `PENDING-MANAGEMENT-COMMAND-COUNT` | `pending_human_decision` | **8** | **7** | 影響 ID **9 件**(`issue_invitation`・`revoke_invitation` と対応する `ROUTE:MANAGEMENT:*`・`HTTP:ROUTE:MANAGEMENT:*`・`FR-041/list_item-006#*` 3 件) |
| `PENDING-ALL-LOGICAL-SCOPE` | `pending_human_review` | **29** | — | `SCOPE:ALL_LOGICAL` の claim 帰属 |

**両方に `oracle_change_action: return_to_step_5_and_re_review`。**

`contracts/authz/oracle-seal.lock.json`(Claude 実測):

```
oracle_commit: dd2cb92cf48d5b1a58431ce1b65e64b4c91e8ba0
review_policy: ORACLE_STEP5_REREVIEW
  trigger: oracle_change_in_revision_2_or_later
  required_action: return_to_step_5_and_re_review
reseal_policy: normal_validation_reseals=false / --reseal-oracle / human_review_required=true
sealed assets: 6
```

**封印は 6 資産の canonical digest 全体**なので、**追加でも発火する**(「追加は自由」ではない)。
`scripts/check_authz_catalog.py:4592`・`:4645` が `canonical_sha256 != _table_digest(asset)` で fail。

**帰結**: **裁定を第 2 群の実装より前に取るのが安い。** あとから取ると、そのたびにステップ 5 へ戻る。
前例では差分敵対レビュー **4 周 + PO 打ち切り裁定**を要した(`docs/worklog/2026-09-03-authz-claims-corpus.md:183-186`)。

**`PENDING-MANAGEMENT-COMMAND-COUNT` は要件書と食い違っている** — 要件書は「**7 つ**の制御資源操作」を
**3 箇所で逐語的に**書く(`REQ:613`・`:680`・`:845`。招待の発行・失効を 1 操作として数える)。
一方 oracle の `operation_ids` は **8**(発行と失効を分ける)。

### 3. 要件突合の帰結

#### 3-1. `NFR-019`(b) の要求は **13 組合せクラス**。本タスクが届くのは 1 クラス分

`REQ:928` が「網羅すべき組合せ」として列挙するクラス:
付与粒度 3 種 × 相互性 / グループ終了後・離脱後・付与撤回後・無効化後 / 複数グループ同時参加 /
資源種別ごと / 制御資源の読み取り / 制御資源への操作 / 再有効化後 / 既定拒否 /
単一テナント名指し直接アクセス / 参加上限の同時受諾 / 同時比較上限超えの 400 拒否 /
自テナントを含む集合 / 在籍区分変更後のキャッシュ失効 — **13 クラス**。

**認可行列の行数は要件で確定している**(`REQ:630-639` の 9 行。うち常に 404 = 4 行)が、
**越境テストの件数は要件に記載がない**(`REQ:928` にも 8 章 DoD `REQ:1035` にも数値なし)。

本タスクの「拒否例 4 件」が対応するのは **資源種別クラスの「常に 404 の 4 資源」だけ**。
「4 ロール × 関数群の実行行列」は **`NFR-019`(b) の要求項目に対応する行が無い** —
要件の軸は「テナント × 付与 × グループ状態 × 資源種別 × 役割」であり、**DB ロールという軸は要件に存在しない**
(要件書の `ロール` 6 件はいずれも利用者ロール。`RLS` / `BYPASSRLS` / `search_path` / `ACL` は**各 0 件**)。
→ **計画書に「これは要件の写像ではなく設計判断である」と明記する**。前計画書は第 1 群について
同じ注記を既に行っている(`plan.md:36-38`)。

#### 3-2. `NFR-010` は DB 層だけでは満たせない — 線引きは要件と整合

`REQ:846`「**測定方法**: 越境アクセスの自動テスト(**API直叩き含む**。CIに常設 → NFR-019)」。
加えて `REQ:844`「**内容・存在を含め参照できない**」・`REQ:599`「**URL直叩き・API直叩きで指定 /
Then 404または拒否となり、内容・存在が応答から判別できない**」。
DB 層は「0 行」と「権限拒否」を区別してしまうため、**存在秘匿の同値性を DB 単体では判定できない**。

→ 「HTTP 経路の判定は対象外 — TSK-217」(`plan.md:115-117`)という線引きは**要件と整合する**。
**条件は 1 つ**: 本タスクの成果を「`NFR-010` を満たした」と主張しないこと。

#### 3-3. mutation test は `NFR-019` のどの種別でもない

要件が定義する CI のテストは **4 種**((a) 一致性 /(b) 越境 /(c) E2E 主要分岐 /(d) 同期故障系
— `REQ:920`・`REQ:1035`・`REQ:956`)。**「単体」という種別は要件に存在しない**。
要件が定義する変異テストは **`NFR-018`(b)②** で、**対象は `REQ:888` の列挙**
(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定)に限定され、
**認可構成は入っていない**。`REQ:891` は「実装判断で対象から外せない」と定めるが、
**実装判断で対象に加える規定は無い**。

→ **認可構成の mutation test は設計判断として宣言する**。`NFR-018`(b)② を根拠に引かない。
「3 変異で必ず red」という件数にも要件典拠がない(要件の閾値は `REQ:902`「**非等価変異の生存 0**」)。

**前計画書 6 節のラベルが誤帰属している**(`plan.md:459-464`): 「単体(a)」「一致性(c)」と書くが、
正しくは (a) = 一致性 /(c) = E2E。**改訂 2 で是正する**。
なお `docs/development/templates/plan-template.md:60` が「単体・一致性・越境・E2E・故障系」と
**5 種で要約している**のが誤帰属の伝播源(要件は 4 種)。

### 4. 既存資産の実測(要点)

#### 4-1. `contracts/authz/` = **15 ファイル**。`contracts/` の領域ディレクトリは `authz/` のみ

主要件数(実測): `requirement-claims.json` claims **1078** / `auth-catalog.json` entries **187** /
`route-registry.json` routes **37**(legacy 13 + shared_data 12 + control_read 4 + management 8)/
`http-route-matrix.json` cells **12**(allow 6 / deny 6)/ `claim-mutant-map.json` claims 198・mutants 231・
two_factor_interactions 276 / `attack-tree.json` goals 14・cut sets 24 / `rejected-configs.json` rejections **3** /
`ddl-elements.json` roles 7・schemas 3・tables 6(全件 `rls_enabled` かつ `force_rls`)・policies 6・
functions 3・acl_expectations 17。

`ddl-elements.json:9-12` の `scope`: `status: candidate_probe_only` / `product_schema: false` /
`contains_sql_body: false` / `second_group_approval_required: true`。
**候補 probe であり、通った構成の確定ではない。**

`auth-catalog.json` の 187 entries は **`enforcement_test_owner.status` が全件 `planned`**、
末尾は全件 `.db`。`catalog_test_owner` は全件 `implemented`。
**つまり「DB での強制を実証するテスト」は 187 件すべて未実装**であり、これが第 2 群の中身。

#### 4-2. 検査スクリプトは **JSON 資産の検査のみで DB へ接続しない**

`scripts/check_authz_catalog.py` = **5019 行**。終了コードは **0 / 1 の 2 値**(`--root` + 資産パス 15 個 +
フラグ 5 個 `--reseal` / `--reseal-derived` / `--reseal-oracle` / 隠し `--skip-derived` / `--skip-oracle`)。
再利用可能な digest 系は **`git_blob_digest`(`:327-338`)のみ公開**で、
`canonical_digest` / `file_digest` は**未存在**(相当物は private の `_canonical_json` `:593` / `_table_digest` `:597`)。

**RLS / `search_path` を実 SQL で検査するスクリプト・テストは `scripts/` にも `backend/tests/` にも未存在。**
現状の検査は JSON 資産のセマンティクス(`:2740` 関数所有者は `NOLOGIN` + `BYPASSRLS` /
`:2802` RLS と FORCE RLS 必須 / `:2910-2911` `search_path` 末尾 `pg_temp` 1 回 ほか)。

`tests/test_check_authz_catalog.py` = 2699 行・`def test_` **72 件**。
**期待件数のハードコードが 20 箇所**(`:350` `total=1078 auth_claim=184 out_of_scope=894` /
`:1576` `db_claim_count == 187` / `:2186-2188` `contract_only: 165, probe_executable: 33` /
`:2193` cut_set 24 / `:2196` all_logical 29 ほか)。**台帳 `H-85` の連鎖点**。

#### 4-3. DB テスト基盤は「管理 1 本 + 被検査ロール 1 本」の 2 接続のみ。使い捨てクラスタの仕組みはある

`backend/tests/db/conftest.py`(333 行)の fixture: `admin_connection`(session)/
`tested_role_connection`(session — **管理接続で `CREATE ROLE ... LOGIN PASSWORD` してから
そのロール自身の DSN で新規接続**。teardown で `DROP ROLE`)/ `verify_connection_identities`(autouse)/
`disposable_postgres_cluster`(function)。

**`SET ROLE` による模擬は禁止されている** — `tests/test_ci_wiring.py:1237` が
`assert "SET ROLE" not in conftest` を実際に検査する。**ロールごとに実接続を張り替えるのが契約**。

前計画書 4 節が要求する **4 本の行列**(`table_owner` / `app_role` / `management_caller` / `outsider_role`)は
**未存在** — 現状 2 本なので**拡張が必要**。

使い捨てクラスタ(`:168-269`)は **Docker CLI を `subprocess` で直接叩く**方式
(`docker run --detach --pull=never --publish 127.0.0.1::5432`・イメージと initdb 引数は期待値資産から読む・
`_wait_for_postgres` は 60 秒デッドライン・teardown は `docker rm --force`)。
**利用箇所は現在 1 件のみ**。第 2 群のロール属性変異(クラスタ全域に及ぶ変異)はこれを使う。

**ローカル実行の要求条件**(コードから読み取り): `PITCHLOG_TEST_ADMIN_DSN` と `PITCHLOG_TEST_ROLE_DSN` の
**両方が非空**(未設定は **skip ではなく `pytest.fail`**)/ 被検査ロール DSN に `user` と `password` の両方 /
被検査ロールが開始前に `pg_roles` に**存在しない** / 管理接続に `CREATE ROLE` `DROP ROLE` 権限 /
接続先が `postgres:17.11-bookworm` を所定の initdb 引数で作ったもの(`server_version_num == 170011` ほか 5 値が exact 一致)/
Docker CLI と `postgres:17.11-bookworm` イメージがローカルに存在(`--pull=never`)。
さらに `pytest_sessionfinish` が **`requires_db` の 0 件収集・0 件実行を `TESTS_FAILED` に落とす**ので、
**「DSN が無いから DB テストを飛ばす」運用は構造上できない**。

#### 4-4. `.claude/core-areas.json` — 登録はほぼ済んでいる

`tenant-isolation.paths` は **22 件**(Claude 実測)。`contracts/authz/*` / `scripts/check_authz_catalog.py` /
`tests/test_check_authz_catalog.py` / `tests/fixtures/authz_claims/*` / `backend/tests/db/*` /
`backend/pyproject.toml` / `backend/uv.lock` / `backend/*conftest.py` / `docker-compose.yml` を含む。
導入コミットは **`d4373ec`(2026-09-02)「feat: コア領域 paths へコード資産を充填しオラクルを追随(ステップ 3/4)」**
(Claude 実測 — `git log -S'contracts/authz/*' -- .claude/core-areas.json`)。

`scripts/core_guard.py` の突合方式(Claude 実測 `:222-227`):
**`guard_paths` は `frozenset` の完全一致**(glob 展開も前方一致もしない)/
**`areas[].paths` は `fnmatch.fnmatchcase`** で、`*` が `/` を跨ぐ。
→ **`contracts/authz/*` は実効的に配下全階層を覆う。**

**未登録は `backend/src/**`**(製品コード。実在は `__init__.py` と `main.py` のみ)。
第 2 群の DDL 適用器・カタログ検査モジュールをここに置くなら **6.3 規則⑤で登録する**
(しないと台帳 `H-12` の再発 — PR #33 で「認可構成の初コード群に対し core-guard が構造的に非発火・
逐行確認チェックなしでマージされた」と記録されている)。

→ **前計画書 `plan.md:124`「本 PR では反映なし — 登録は第 2 群の射程」は陳腐化している。改訂 2 で現況化する。**

#### 4-5. **第 2 群の DDL 適用器は Alembic を使えない**

`tests/test_ci_wiring.py:1272` が **`assert {"sqlalchemy","alembic"}.isdisjoint(locked_versions)`** を
実際に検査している(`backend/uv.lock` に両者が 1 件も無いこと)。
ORM 導入と同テストの更新は **TSK-343 の射程**(`data-model.md:2752`)。
→ **第 2 群の適用器は psycopg 直書きで書く**か、**TSK-343 の完了を待つ**かの選択になる(下記 5-U-14)。

#### 4-6. 第 2 群・第 3 群で新設が必要なもの(いずれも現時点で未存在)

DDL 適用器(`ddl-elements.provisioning_claim.ordered_steps` 5 件 + `R-5` の失敗点 5 種 + `R-8` の順序契約)/
**候補 DDL の SQL 実体**(`contains_sql_body: false` なので表 6・ポリシー 6・関数 3・ロール 7・スキーマ 3・ACL 17 の
実 DDL がどこにも無い。`docs/features/pg-authz-verification/probe/*.sql` 13 件は
**手実行の証跡であって適用器の入力ではない**)/
カタログ検査モジュール(`pg_policy` の 5 属性・`pg_auth_members` の 2 種到達閉包・列 ACL・schema ACL・
default ACL・`pg_get_functiondef` digest)/ 越境テスト(`planned` な `TSK-270.group2.*` が **468 参照**:
interaction 276 / runtime 178 / runtime-positive 6 / table-privilege 8)/ mutation ランナーと kill 判定 5 条件 /
4 ロール実接続 fixture の拡張 / `test_ci_wiring.py`・`test_core_guard.py` の追記 / 設計書 10.1 の追随。

#### 4-7. 「第 1 群で凍結した oracle を書き換えない」の射程

出典は **① 前計画書 `plan.md:375-376`**(「第 1 群で oracle をすべて凍結し、**第 3 群はそれを書き換えない**」)
**② 同 `:390`**(ステップ 5 の合格条件)**③ 機械可読な正 = `oracle-seal.lock.json:78-88`**。

**射程の判定**: 書き換え禁止の対象は「**第 3 群**」であって「改訂 2」ではない。
改訂 2 以降の変更は**禁止ではなく手続き付き**(ステップ 5 へ戻る + 差分敵対レビュー + 人間確認 +
専用フラグ `--reseal-oracle`)。**前例が 3 回ある**(`oracle_commit` は `e10f2b1` → `dfd523a` → 現在の `dd2cb92`。
TSK-312 では内容自体も変えた — `docs/worklog/2026-09-03-authz-claims-corpus.md:182-186`)。

#### 4-8. 12-4 節のゲートにおける TSK-317 / TSK-344 の境界

正本に明記されている部分(`data-model.md`):

| 項目 | 所有 | 典拠 |
| --- | --- | --- |
| 越境テストの**作成・実行**(実機確定) | **TSK-317** | `:2750` |
| ゲートの**実行**(実スキーマに対する**再**実行) | **TSK-344** | `:2751`(裁定 `A-2`「定義は本書・実行は後」) |
| ゲートの**定義** | TSK-342 で完了 | `:2439`「本書の責務 = ゲートの定義まで」 |
| 実スキーマの実体化 | **TSK-343** | `:2752` |

**明記されていない部分**: **通過条件①「実スキーマへ適用されている」を TSK-317 単独では満たせない**
(実スキーマは TSK-343 の成果であり、前計画は DDL を「**probe 構成の検証**とし製品資産として確定しない」と
定めている — `plan.md:98`)。**TSK-317 が満たせるのは probe クラスタ上での構成成立まで**という読みは
2 つの正本記述からの**推測**で、この繋ぎを述べた条項は見つからない(下記 5-U-8)。

**「最低要求 4 件」は下限である** — 正本は別の節でより多くを要求している:
`:239`(スキーマ検査 = 関数所有者 / ACL に `PUBLIC` を含まない / `search_path` / 所有ロールの
`NOLOGIN`・`BYPASSRLS` / ロール所属。**越境テストとは別に構成そのものを検査する**)/
`:544`(**6 前提と認可行列の各行それぞれに越境テストを持つ** — とくに「対象側は非共有・要求元だけ付与」)/
`:289`(移行完了後に属性が残っていないことを検査する)。
**「4 件で足りる」と読むと 3-2 / 3-6 の要求を落とす**(台帳 `H-79` の型)。

#### 4-9. `R-1`〜`R-8`(前計画書 4 節)— 番号の不整合

前計画書は 2 箇所で「満たすべき要件は 4 節の `R-1`〜`R-7`」と書く(`plan.md:90`・`:452`)が、
**表には `R-8` が存在し**(`:414`・プロビジョニング手順の順序と解除漏れの検査)、
**本文 2 箇所が `R-8` を参照している**(`:313`・`:390`)。**改訂 2 で `R-8` を落とさない。**

`R-6` / `R-7` は**第 1 群で部分履行済み**(実測): `ddl-elements.json` が表権限 8 種を単一集合で持つ /
`claim-mutant-map.json` が `execution_classes` = `probe_executable` / `contract_only` を持つ。

4 節の小見出し 13 件のうち、**第 2/3 群の実装を直接縛らないのは「母集合は全数採取→分類」の 1 件のみ**
(第 1 群で完了)。残り 12 件はすべて実装物に直接効く。

#### 4-10. ADR-003 D-12 と `contracts/authz/` の関係 — **規約側が追随していない**

ADR-003 D-12(`docs/adr/ADR-003-domain-calc-method.md:293-301`)は
`contracts/<領域>/` の 1 階層・`<対象>_v<N>.json`(英小文字とアンダースコア)・
ファイル内に `"version"`(ファイル名と一致)・「**本 ADR の承認後に新設する契約から適用**」と定める。
領域の列挙は `state-transition` / `field-regions` / `display-geometry` / `stat-vectors` の **4 つで、`authz` は無い**
(`contracts/README.md:12` の列挙も同じ。ADR-003 全文に `authz` は 0 件)。

実測の乖離: ファイル名はハイフン区切りで版接尾なし(`auth-catalog.json` ほか)/
`"version"` キーは無く `"schema_version": 1` を持つ。
**`contracts/authz/**` を D-12 の射程から外す決定はリポジトリ内に見つからない**(不明)。
第 1 群の計画書 3 節も `docs/adr/**` を「反映なし」としている(`plan.md:127`)。→ 下記 5-U-3。

### 5. 未解決・申し送り(人間の裁定が必要な論点)

**優先度は「第 2 群の実装に着手する前に決めないと後戻りが発生するか」で並べた。**

| # | 論点 | 決めないと何が止まるか | 典拠 |
| --- | --- | --- | --- |
| **U-12** | **`data-model.md:240` の `search_path` 契約(P0)をどう直すか** — 改訂のゲート区分(7.6 決定表)と、TSK-317 で直すか別タスクにするか | **正本の契約に従うと乗っ取りが成立する**。第 2 群のカタログ検査は正本と食い違ったまま書くことになる | 1-1 節 |
| **U-4** | **管理コマンドは 7 か 8 か**(`PENDING-MANAGEMENT-COMMAND-COUNT`) | 変更すると route-registry / HTTP 行列 / claim 3 件が動き **oracle 再レビュー**。放置すると**正本(7)と oracle(8)が食い違ったまま**第 2 群のテストを書く | 2 節・`REQ:613`/`:680`/`:845` |
| **U-5** | **`SCOPE:ALL_LOGICAL` の 29 claim の帰属**(`PENDING-ALL-LOGICAL-SCOPE`) | 未裁定のまま第 2 群のテスト ID を割ると、裁定時に再割り当て + oracle 再レビュー | 2 節 |
| **U-11** | **実機検証を誰がどの環境で回すか** — 開発 DB は環境変数の実値なしに起動せず、`psql` 未導入。委任先はネットワーク遮断・シークレット非コピー | 第 2 群の合格条件を `[機械]` と `[手動・外部]` に書き分けられない | 0 節・台帳 `H-79` 対応案 (b) |
| **U-14** | **第 2 群の DDL 適用器を psycopg 直書きにするか、TSK-343 を待つか** | `test_ci_wiring.py:1272` が `uv.lock` に `sqlalchemy`/`alembic` が無いことを検査している | 4-5 節 |
| **U-1** | **移行バッチ用ロールを TSK-317 の射程に入れるか** | 入れるなら oracle 変更 → 再レビュー + 母集合の `FR-038` 判定(全 18 行 `out_of_scope`)の見直し = `H-85` 連鎖。入れないと `data-model.md:289` の検査の所有者が空 | 1-3 節 |
| **U-8** | **越境テストは「作成」までか「作成・実行」までか**。probe 上か実スキーマ上か | **矛盾**: `data-model.md:2750`「作成・**実行**」vs `closure-handoff-data-model.json` の当該行「作成」(後者は `guard_paths` 収載) | 4-8 節 |
| **U-13** | **アプリ用ロールに `DELETE` を与えるか** — 正本が扱っておらず、probe は与えている。`4.0-2`「物理削除しない」との関係 | 第 3 群が「通った構成」を渡すときに `DELETE` が付いてくる | 1-2 節 |
| **U-2** | **oracle 再レビューの周回上限・打ち切り基準** | policy は「ステップ 5 へ戻る」までしか定めない。前例は差分敵対レビュー 4 周 + PO 打ち切り。**改訂 2 の見積もりが立たない** | 4-7 節 |
| **U-3** | **`contracts/authz/` を ADR-003 D-12 にどう位置づけるか**(領域列挙・命名・`"version"`) | 第 3 群の「引き渡し 3 資産の確定」が規約適合を主張できない。ADR 改訂なら確定ゲートが 1 本増える | 4-10 節 |
| **U-6** | **`H-85` 対応案②③ の所有者** | **矛盾**: 台帳「②③ は TSK-270 の計画改訂 2 の射程」vs TSK-312 計画「PO 裁定 2026-09-03 で見送り・別起票」。改訂 2 の射程が大きく変わる | 台帳 vs `docs/features/authz-claims-corpus/plan.md` |
| **U-7** | **`R-4` の受取先** — 「TSK-250 の DoD へ登録して read-back」と書かれているが TSK-250 は分割された | read-back 相手が存在しないまま DoD を書くと機械条件が満たせない | 4-9 節・`data-model.md:2750-2752` |
| **U-9** | **`H-57`(10.1 へ `NFR-019`(b)(d) のジョブ行を追記)と TSK-270 の「新ジョブを起こさない」の字面衝突** | 10.1 の追随の書き方が決まらない。**新ジョブ行を新設すると `H-19` 型で確定ゲートへ覆るリスク** | 台帳 `H-57` vs `plan.md:125`・設計書 `:695` |
| **U-10** | **`R-1`〜`R-7` か `R-1`〜`R-8` か** | `R-8`(プロビジョニング手順の順序・解除漏れ検査)が改訂 2 の要件から落ちる | 4-9 節 |

**機械的に是正すればよく裁定が不要なもの**(改訂 2 で直す):

- 前計画書 `plan.md:459-464` の `NFR-019` 種別ラベルの誤帰属((a) = 一致性 /(c) = E2E。「単体」は存在しない)
- 同 `plan.md:124` の `core-areas.json` 登録状況の陳腐化(4-4 節)
- `docs/development/templates/plan-template.md:60` が `NFR-019` を 5 種と要約している(要件は 4 種)
- 台帳 `H-12` の再発「5 件」に対応する 5 件目の補記が本文に不在

**本タスクで踏みやすい台帳の型**:

- **`H-68`**(実体のない段階の設計が輪に入る): 実体は oracle・テスト基盤・実機実測については**ある**が、
  **DDL 適用器と実クエリはまだ 1 行も無い**。「適用器の内部設計の細部」「実スキーマ前提の具体値」を
  改訂 2 で確定させようとすると再度踏む。**隣接規範を引き込む要求を 1 つも書かない**のが避け方
  (台帳 `:1193`「『細部設計をしない』という自己申告では避けられない」)。引き込みやすいのは
  ADR-003 D-12 / `core-areas.json` の paths / 設計書 10.1 の 3 つ
- **`H-79`**(同種の欠陥を全経路へ適用しない): **1-1 節の `search_path` がまさにこの型**。
  「越境テスト 4 件」で検索して足りたと判断すると 4-8 節の追加要求 3 箇所を落とす
- **`H-85`**(oracle の入力凍結が追随を 8 資産 + テストへ拡大): 期待件数のハードコードが
  `tests/test_check_authz_catalog.py` に **20 箇所**。**追随を独立ステップとして 2 コミットで持つ**
- **`H-53`**(委任の指示に列挙した挙動だけを検証する): 変異集合を扱うので
  **件数を定数で持たない・ID 集合の sha256 で exact-set 突合する**
- **`H-12`**(core-guard が構造的に非発火): `backend/src/**` を登録しないと PR #33 と同じ型
