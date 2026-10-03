---
feature: product-rls-boundary-tests
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d593b75e687811f8ad5f5da4a8af046
branch: feature/product-rls-boundary-tests
created: 2026-09-24
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 製品テーブルの RLS 適用と越境テスト(TSK-344)

> **【2026-10-03 全面改訂】** 本書は **7 周の計画レビューで収束しなかった旧版(544 行)を破棄して書き直した**ものである。
> 周回を 0 へリセットした理由と、旧版から引き継いだもの・落としたものは **11 節**に全部書いた。
> **旧版の P0 を生み続けた 2 つの原因**(「実スキーマ」の未定義を自前で埋めようとしたこと /
> 存在しない 4 単位の代表を必須依存へ格上げしたこと)も同節に記録してある。

## 1. 背景・目的

- Notion タスク: [TSK-344 越境テスト再実行ゲートの実行 — 実スキーマ適用後の再実行](https://app.notion.com/p/3d593b75e687811f8ad5f5da4a8af046)(優先度 **高**)
- 前タスク: TSK-342(データモデル設計の正本化)。**裁定 `A-2`(2026-09-08・山田正輝)= 「定義は TSK-342・実行は本タスク」**
- 計画段階の調査: [research.md](research.md) / [research-dod-revision.md](research-dod-revision.md) / [decision-sheet-minimum-four.md](decision-sheet-minimum-four.md)
- 正本: `docs/design/data-model.md` **12-4 節**(ゲートの定義・non-serving 宣言・マージ停止条件)/ **12-8 節**(射程宣言)/ 3-2・3-6・8-2-B 節

### 本タスクの実体

**TSK-424 が使い捨てクラスタで作成・初回実行した製品 authz 資産と越境テストを、実スキーマで再実行し、12-4 の判定を記録する。**

切り分けの逐語(`../tenant-boundary-enforcement/design.md:362-366`):

> **TSK-344 との切り分け**: `docs/design/data-model.md:2846` は TSK-344 の射程を
> 「越境テスト再実行ゲートの実行(**実スキーマに対する再実行**)」と書いている。
> **「再実行」である以上、作成と初回実行はこちら側にある** … →
> **本単位: 使い捨てクラスタで作成・実行 / TSK-344: 実スキーマで再実行。** 矛盾しない。

> **【引用の行ずれを是正した】** 旧版は同ファイルを `:335-345` として引いていたが、
> 3-5-a 節が後から挿入されて **21 行ずれており、現在位置は `:356-366`** である。本書は全件を現在位置へ直した。

### 12-4 の通過条件(逐語 — `../../design/data-model.md:2531`)

> **① RLS のポリシーとロールの DDL が実スキーマへ適用されている ② その実スキーマに対して越境テストが green である**
> ([NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md)(b) の越境テスト)。**②の green は本表の「適用単位」の範囲で判定する**

## 2. スコープ

### やること

1. **専用の Postgres インスタンスを立てる** — `docker-compose.yml` へ別サービス・別ポート・別ボリュームで 1 つ足す(4-1 節)
2. **運用手順書(最小版)を新設する** — `docs/ops/product-rls-real-schema.md`。**4 節だけ**: ① 適用主体 ② 対象の識別と撤去・作り直しの手順 ③ 既存接続 0 件の確かめ方 ④ 失敗時に serving へ戻さない扱い
3. **`scripts/` の runner とプラグインを置く** — 対象を検査して作り直し、製品コードの `apply_product_authz_ddl` で適用し、**既存 17 本をそのまま実行する**
4. **12-4 通過条件①②を満たす**
5. **12-4 の判定を PR へ記録する** — 正本由来 4 項目 + 同一対象 5 項目(4-5 節)。**入口を 1 つも開かないので「対象入口なし」と書く(項目を省かない)**
6. **DoD を現行化する** — [research-dod-revision.md](research-dod-revision.md) の成果(**DoD 1・3 が不変、2・4・5・6 が変わる**)。PO 裁定により本タスクの PR の中で行う

### やらないこと

| 項目 | 行き先 | 典拠 |
| --- | --- | --- |
| **12-4 の「実スキーマ」の正本上の意味の確定** | **TSK-382** | **人間の決定 2026-10-03**。正本は意味を定義しないと明記している(`../product-authz-surface/design.md:652`「「実スキーマ」の意味も定義しない(**TSK-382 の判断を先取りしない**)」)。**本書は運用対象の特定にとどめ、条文の意味を定めない** |
| **越境関数そのものの実装**(`shared_read` / `control_read` / `representative_management_operation` / 管理関数) | **U-C3 / U-C2 / U-C1 / U-A2** | **関数を書くのは「再実行」ではなく「作成」**であり、1 節の切り分けで TSK-424 側。**ただし最低要求 4 件は本タスクで判定する**(4-4 節 — 正本は「**4 件は HTTP 経路を開かない PR でも判定できる**」「**測定経路の充足条件は 4 件に足す別の要求であって、4 件を置き換えも縮小もしない**」と明記している。`../../design/data-model.md:2533`) |
| **新規の変異試験の設計・追加** | **TSK-442 の隔離環境** | 射程縮小 2026-10-03。正本 12-4 は「変異させて red になることを確かめよ」と書いていない。**既存試験の再実行は射程内**(4-1-b 節 — 2 周目 P2 の是正) |
| **`maintenance latch`** | **落とした** | 変異をやめた以上、弱化状態を跨いで保持する latch の役目が無い |
| **製品 authz DDL 資産の作成**・表分類・capability カタログ | **TSK-424 PR A1** | `../tenant-boundary-enforcement/design.md:315-322` |
| **適用器の一般化・probe↔製品写像・使い捨てクラスタでの初回試験** | **TSK-424 PR A2 = TSK-442** | 同 `:356-366` |
| **最終パスへの切替**(staged → final) | **TSK-443** | `ddl-elements.staged.json` の `pending_switch: "TSK-443"`(**機械で強制** — `backend/tests/test_authz_product_staging.py:150-155`) |
| **認証・レート制限テーブルの RLS と表分類** | **TSK-424**(`function_only` と分類済み。関数側は **U-A1**) | `../product-authz-surface/design.md:35-45` |
| **`backend/tests/` の編集・新設** | **1 ファイルも置かない** | 裁定 2026-09-28。**実スキーマ不在の無関係な PR が既定 pytest で赤になる経路を作らない** |
| **`backend/migrations/` への RLS / ロール DDL の追加** | **しない**(差分 0 行) | `../tenant-boundary-enforcement/design.md:347-354` の `D7` |
| **`contracts/authz/product/` 配下の変更** | **読むだけ** | 9 節 |
| **既存データを持つ DB への適用の検証** | **しない** | 4 節の設計上の限界。**判定記録へ明記する** |
| **HTTP の入口を開くこと** | **開かない** | 判定記録は「対象入口なし」 |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PR レビュー / finalize-doc) |
| --- | --- | --- |
| **`docs/ops/product-rls-real-schema.md`** | **新設(最小版・4 節)**。適用主体 / 専用 DB の識別と作り直し / 既存接続 0 件の確かめ方 / 失敗時に serving へ戻さない扱い | **`/finalize-doc`**(7.6 の決定表 — **新設は敵対レビュー + 人間承認**。**確定前に実運用へ使わない**) |
| **`.claude/core-areas.json`** | **3 件**を `tenant-isolation` の `paths` へ追加する — ① 上記の運用正本 ② **`scripts/` に新設する runner とプラグイン** ③ **その設定資産**。**1 周目 P0-7 の是正**: 既存 `paths` は `scripts/` 全体を覆っておらず(`scripts/check_tenant_boundary_bypass.py` など個別列挙)、**新 runner は DROP 先と越境判定の両方を変えうる**ので、保護外のままだと後続 PR がコアレビューなしで対象を差し替えられる | PR レビュー |
| **`docs/README.md`** | 索引へ上記を追加する | PR レビュー |
| `docs/design/data-model.md` | **反映なし**。12-4 の定義は変えない。**最低要求 4 件の文言も変えない**(`:2533` が「**4 件の文言は変えない** — 12-7 (1) が同じ 4 件を列挙しているため」と明記)。12-8 節の実装追随は TSK-424 の射程 | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/adr/` | **新設なし**(既決の制約の実行であり、新しい決定を持たない) | — |
| `contracts/authz/product/*` | **変更しない**(TSK-424 / TSK-443 の資産を**読むだけ**) | — |
| **Notion カード TSK-344 の DoD** | **現行化する**(PO 裁定 — カードは正本ではない) | — |

## 4. 実装方針

**重さ分類 = コア領域**。根拠は `contracts/authz/*`(`.claude/core-areas.json:307` = `tenant-isolation`)を読み、
**新設する `docs/ops/` の文書を同じ `paths` へ登録する**こと。**`backend/migrations/*` には触れない**(差分 0 行)。

### 4-1. 採る設計 — 専用の Postgres インスタンスを立てる

**調査で判明した障害**: **既存 17 本は使い捨てクラスタ専用に書かれており、他が使う環境へ当てると破壊的である。**

| # | 事象 | 典拠 |
| --- | --- | --- |
| 1 | seed が **commit** され、ID は `uuid5` で決定的、`ON CONFLICT` 無し → **同じ DB で 2 回目は重複キーで落ちる** | `backend/tests/db/test_product_authz_tenant_owned.py:46` / `test_product_authz_cross_cutting.py:82` / `backend/tests/product_authz_tenant_owned_cases.py:938-950` |
| 2 | `ALTER ROLE pitchlog_app PASSWORD <random>` を **commit** → アプリロールの資格情報を壊す | `test_product_authz_tenant_owned.py:56-62` / `test_product_authz_cross_cutting.py:182-188` |
| 3 | `DROP POLICY` / `NO FORCE ROW LEVEL SECURITY` を **commit**。復元は `finally` のみ → **プロセス死で RLS が無効のまま残る** | `test_product_authz_tenant_owned.py:426-433` / `:480` |
| 4 | fixture が `CREATE ROLE pitchlog_owner`(**`IF NOT EXISTS` 無し**)・`CREATE DATABASE pitchlog_product`・`alembic upgrade head` を実行 | `backend/tests/db_fixtures.py:966-980` / `:992-996` |
| 5 | `verify_connection_identities` が **autouse**(`db_fixtures.py:403`)で、`requires_db` のとき `tested_role_connection` を引く。同 fixture は **`CREATE ROLE` → 事前存在なら `pytest.fail` → `DROP ROLE`** | `db_fixtures.py:327-344` / `:403-436` |
| 6 | 1 本が **manifest 全表の `count(*) == 0`** を要求 | `test_product_authz_cross_cutting.py:336-353` |
| 7 | 一時ロール名が固定(`pitchlog_step9_temp_role`)で `DROP OWNED BY` を打つ | `test_product_authz_cross_cutting.py:34` / `:259` |

> **【1 周目 P0-3 の是正】** 当初案は「共有インスタンス上に専用 DB を作り、毎回作り直す」だった。
> **これは成立しない** — **ロールは DB 単位ではなくクラスタ単位**なので、
> **2・5・7(`pitchlog_app` のパスワード変更 / 被検査ロールの事前存在 / 固定名の一時ロール)は DB を作り直しても残る**。
> 「7 事象がすべて消える」と書いたのは誤りだった。

**したがって、専用の Postgres インスタンスを `docker-compose.yml` へ 1 つ足す**(人間の決定 2026-10-03)。

| 性質 | 内容 |
| --- | --- |
| **分離の粒度** | **クラスタ**。別サービス・別ポート・**別の名前付きボリューム**。共有開発 DB(`${POSTGRES_DB}`)とロール空間を共有しない |
| **永続性** | **インスタンスは永続する**(名前付きボリューム)。**使い捨てコンテナではない** — 通過条件①の「実スキーマへ適用されている」はこの形で満たす |
| **DB の作り直し** | **実行のたびに対象 DB を作り直す**(事象 1 が残るため)。**インスタンスは消さない。ボリュームも消さない** |
| **ロールの後始末** | 作り直しの前に **`DROP OWNED BY` → `DROP ROLE`** で製品 authz ロールと被検査ロールを撤去する(事象 2・5・7 の解消) |
| **中断時** | **弱化したまま次回へ持ち越さない** — runner は起動時に必ず撤去から入る(**復元ではなく再構築で閉じる**) |

**明示する限界**: **既存データを持つ DB に対する適用は検証しない。** 判定記録へ書く(変異感度を TSK-442 へ委ねたのと同じ扱い)。

### 4-1-b. 変異を含む試験の扱い

既存 17 本のうち 4 本は変異を伴う(`test_policy_force_and_with_check_mutations_change_production_behavior` /
`test_each_removed_helper_condition_changes_its_matrix_cell_and_rolls_back` /
`test_function_only_tables_are_permission_denied_and_grant_mutation_changes_it` /
`test_all_trigger_functions_fire_without_app_execute_privilege`)。

**17 本すべてをそのまま再実行する。部分集合を採らない。**

- 専用インスタンスは他が使わないので、変異が外へ波及しない
- **「どれを除くか」という判断を持ち込まないことが、4-3 節の同一性の担保そのもの**である
- **射程外なのは「変異試験を設計すること」**であって、既存試験の再実行ではない。**変異による感度の確認は TSK-442 の試験 ID へ委ねる**という申し送りは維持する

### 4-2. 適用の入口と前提(実測)

| 事実 | 典拠 |
| --- | --- |
| 適用の入口は **`apply_product_authz_ddl(connection)` ただ 1 つ**。製品コード・`scripts/` からの既存呼び出しは **0 件** | `backend/src/pitchlog/authz/product_provisioning.py:63` |
| 公開面は `__all__` ではなく**テストで固定**(`ProductOperation` / `apply_product_authz_ddl` / `unapply_product_authz_ddl` の 3 つ) | `backend/tests/test_product_authz_provisioning.py:38-43` |
| 適用主体は **superuser かつ `pitchlog_app` でない**ことを、SQL を打たずに接続通知で検査する | `product_provisioning.py:497-511` |
| 接続は **closed 不可・autocommit 不可・トランザクション IDLE 必須** | `product_provisioning.py:513-` |
| 適用手順は資産で定義済み(**apply 7 + unapply 7・単一トランザクション**) | `contracts/authz/product/application-steps.json`(`PRODUCT-APPLY-01-ROLES` 〜 `-07-TRIGGER-FUNCTION-ACLS`) |
| ロール資産は `IF NOT EXISTS` 付きだが **`pitchlog_owner` だけ `ALTER ROLE` のみ** → **事前に存在していないと失敗する** | `contracts/authz/product/function-bodies/roles/pitchlog_owner.sql` |
| `current_database.sql` が **繋いだ DB の所有者を書き換える** | `contracts/authz/product/function-bodies/databases/current_database.sql` |
| compose が作るのは DB 1 つと superuser 1 つだけ。**authz ロールは作らない**(initdb スクリプトのマウント無し) | `docker-compose.yml:2-15` |
| 製品表 45・ポリシーを持つ 32・`function_only` 13 | `contracts/authz/product/table-classification.json` |
| migration 26 本・`op.create_table` 45 件・**RLS 系 DDL は 0 件** | `backend/migrations/versions/`(全数) |
| migration の接続先は `PITCHLOG_MIGRATION_DATABASE_URL` | `backend/migrations/env.py:23` |

### 4-3. 「同一性」を宣言ではなく構造で担保する

旧版の依存 9(シナリオ ID と digest)が塞ごうとしていたのは「**コピーした別試験を『同一』と記録できる穴**」である。
**これは本タスクが新規にテストを書く前提だから生じていた。書かない。既存の test 本体 17 本をそのまま実行する。**

- **コピーが存在しないので、「別物を同一と記録する」経路が構造的に無い**
- 同一性の記録 = **test ファイルの commit + 実行した node ID の exact-set**
- 期待値側の cases 3 本(`backend/tests/product_authz_{tenant_owned,cross_cutting,other_profiles}_cases.py`)は**接続先に依存しない純粋な資産読み取り**なので障害にならない

#### 接続先の差し替え方(**1 周目 P0-2 の是正 — 計画段階で確定する**)

**問題**: `provisioned_product_catalog` は**必ず `disposable_postgres_cluster()` を呼び、Docker で別クラスタを起動して
その上に DB を作る**(`backend/tests/db_fixtures.py:949-1005`)。**差し替えずに node ID が green でも、専用インスタンスの証拠にならない。**

**採る手段**: **`scripts/` 配下に pytest プラグインを置き、`pytest -p <plugin>` で既存の test ファイルを実行する。**
プラグインは `db_fixtures` の**クラスタ起動関数を、専用インスタンスへのハンドルを返す実装へ差し替える**。

| 制約 | 守り方 |
| --- | --- |
| `backend/tests/` を編集しない | プラグインは `scripts/` に置く。test ファイルも conftest も触らない |
| 既定 pytest の収集集合を変えない | **`parametrize` を足さない**。プラグインは `-p` で明示指定したときだけ読まれる |
| fixture の優先順位 | **fixture を再定義して上書きしない**(conftest がプラグインより強いため成立しない)。**モジュール関数の差し替えで行う** |
| 2 つの DSN(`PITCHLOG_TEST_ADMIN_DSN` / `PITCHLOG_TEST_ROLE_DSN`) | **変数名は資産で凍結**(`backend/tests/db/environment-expectations.json:195-211`)。**資産を変えず、runner が専用インスタンスを指す値を与える** |

**差し替えが効いたことの証明**(ステップ 4 の合格条件 — **green だけでは証拠にならない**):

1. **実行中に Docker コンテナが 1 つも作られていない**(実行前後でコンテナ一覧が一致)
2. **試験が使った接続の host・port が専用インスタンスのものと一致する**(接続パラメータから観測。**DSN の実値は記録せず、識別子だけを残す**)
3. **適用・試験・判定記録の 3 者が同じ生成回を指す**(4-5 節)

> **先例**: 接続元を実行時に切り替える唯一の先例は `request.fixturenames` による供給源の差し替え
> (`db_fixtures.py:1190-1200`)。**`indirect=True` はリポジトリに 0 件**で、接続先軸の `parametrize` の先例も無い(実測)。

### 4-4. 最低要求 4 件と既存 17 本の対応(**①②③ は充足・④ は未決 A 待ち**)

**①②③ は現在の資産で判定できる。④ は判定できない**(**2 周目 P0-1** — 1 周目に出した反証は成立しなかった)。
正本は「**4 件は HTTP 経路を開かない PR でも判定できる**」と明記するが(`../../design/data-model.md:2533`)、
**④ は「対象側は非共有・要求元だけ付与」の組の越境テストを明示的に要求しており**(同 `:555`)、
**`SECURITY DEFINER` 0 件の表明では代替できない**(0 件試験は付与の正負を作らない)。**7 節の未決 A を要する。**

| 最低要求 | 対応する既存試験 | 根拠 |
| --- | --- | --- |
| **① 関数を経由せず他テナント行を読めない** | `test_tenant_id_table_enforces_product_boundary`(**`tenant_id` 列を持つ 28 表**)/ `test_guarded_tenant_reassignment_is_also_rejected_by_rls_with_check` / `test_self_tenant_row_filters_and_rejects_update` / `test_force_rls_applies_to_owner_with_unbound_context` | `../product-authz-surface/design.md:444` |
| **② `PUBLIC` が越境関数を実行できない** | `test_untrusted_logins_and_public_lack_effective_helper_execute` | 同 `:480`(`PUBLIC` と信頼しない `LOGIN` ロールが補助関数の実効 `EXECUTE` を持たない) |
| **③ `search_path` の乗っ取りが効かない** | `test_app_cannot_create_temporary_table` / `test_temp_schema_shadowing_does_not_change_helper_result` | 同 `:481` |
| **④ 対象側が非共有なら要求元が付与していても返らない** | **該当なし(未決 A)** | 対象の**共有集計の越境関数が 0 件**で、所有は **U-C3**(帯 3 の最後)。表レベルでも代替できない — `POLICY:sharing_grants:effective_group_control.sql` は**自分の実効メンバーシップ**で絞るだけで相互性を表現せず、seed の `grant_flags` は**全件空**。`test_app_can_execute_no_security_definer_function` は「0 件の表明」であって**付与の正負を作らない** |

**④ の扱いは未決 A の結論に従う**。現時点で書けるのは「**越境関数が 0 件である**」という事実までで、それを ④ の充足と数えてよいかは正本の判断である。
**U-C1 / U-C2 / U-C3 / U-A2 が関数を足した時点でこの試験が red になり、各単位が ④ の試験を足す**という設計である
(`../product-authz-surface/design.md:639` が残件を「越境関数と最低要求 ②③④ の残り = U-C1 / U-C3 / U-A2」と記録)。
**本タスクは「0 件の表明」で ④ を満たしたと記録し、関数が増えた後の ④ は各単位の責務であることを併記する。**

### 4-5. 対象の識別と生成回の拘束(**1 周目 P0-5 の是正**)

**DB 識別タプルの構成要素と取得元を定める。**

| 要素 | 取得元 | 記録の形 |
| --- | --- | --- |
| インスタンス識別 | compose のサービス名とボリューム名(**リポジトリ内の定義**) | そのまま記録 |
| 接続先 | `scripts/` の設定資産から読む | **ホスト・ポート・DB 名の識別子のみ**。**資格情報は記録しない**(絶対規則 2 / NFR-014) |
| **生成回** | runner が作り直しのたびに採番する **生成 ID**(時刻 + 乱数) | 適用・試験・判定記録の 3 者に同じ値を書く |
| migration head | `alembic` の head リビジョン | そのまま記録 |
| DDL 資産 | `contracts/authz/product/` の digest | そのまま記録 |

**DROP の前に対象検査を置き、拒否側へ倒す**(ステップ 3 の合格条件):

- 接続先が **専用インスタンスであること**(ホスト・ポートが設定資産の値と一致)
- 対象 DB 名が **承認された名前と exact 一致**すること
- **共有開発 DB の名前・ポートと一致しないこと**
- **いずれか 1 つでも判定できなければ中止する**(判定不能を成功にしない)

**同名 DB を作り直す前後は生成 ID で区別する** — 生成 ID が一致しない適用・試験・記録の組を不整合として扱う。

### 4-6. non-serving 区間(引き継ぎ — 本文へ明記する)

**区間の始期**: **取り外しを始める前に、新しい接続を止め、対象へアクセス可能な既存接続が 0 件であることを確かめた時点。**
**区間の終期**: **再適用の commit の後に、カタログ検査と越境の試験が green になった時点。**

- **途中で失敗したら serving に戻さない**(撤去・作り直し・適用・試験のどれで失敗しても同じ)
- **既存接続の排出対象は「アプリ接続」だけでなく、対象へアクセス可能な全主体**とする
- **配備環境・DB 識別タプル・接続遮断を同じ生成 ID へ拘束する**(4-5 節)— 環境 A を停止して環境 B を操作する取り違えを拒否側へ倒すため
- **中断後の再開は復元ではなく再構築で行う**(4-1 節)— 弱化した状態を次回へ持ち越さない
- **`maintenance latch` は置かない**。latch は「変異で弱化した状態のまま serving へ戻さない」ための機構であり、**再構築で閉じる以上その役目が無い**

> 専用インスタンスは製品トラフィックを受けないので、実務上の「serving」は**他の作業が同インスタンスを使う状態**を指す。
> **本タスクの時点では利用者が本タスクだけ**であり、区間の規律は**手順として定めるが、外部影響は無い**。この非対称を運用手順書へ明記する。

### 4-7. 依存(exact-set = 2 件)

| # | 要るもの | 所有 | 状態(2026-10-03 実測) |
| --- | --- | --- | --- |
| 1 | **staged → final の切替** — staged のままだと適用した DDL とランタイム契約(`PROVISIONAL = True`)が食い違う | **TSK-443**(PR #87) | **ステップ 7 まで済・draft。残るのはステップ 8 のみ**(`git mv` + `pending_switch`/`provisional_contract_additions` の除去 + `asset_spec.py` 1 行)。**人間の受理(S・H・D の明記)とマージ順 `#74 → #87` 待ち**(`../runtime-contract-switch/plan.md:80`) |
| 2 | **既存 17 本と cases 3 本が develop にあること** | **TSK-442**(PR #84) | **✅ 充足**(2026-10-03 実測) |

**着地済みで依存から外れたもの**: 製品 authz 静的資産(PR #79)/ 適用器・実 DB 試験・写像(PR #84)/ Session の供給(PR #82・2026-10-03 マージ)。

### 着手前のゲート(**ステップ表の外** — 1 周目 P0-6 の是正)

**次の 2 つはステップ表に入れない。**ステップ 1 に「ステップ記法を付けない」と書くと、
以降が `(ステップ 2)` から始まり **1 からの連続集合にならず、`scripts/feature_status.py` が「不整合」と判定する**
(設計書 6.1 の厳密文法)。

| ゲート | 内容 | 通過条件 |
| --- | --- | --- |
| **G1** | 本計画書の確定 | 人間の承認(`承認: 済`)。**計画系コミットなのでステップ記法を付けない** |
| **G2** | `docs/ops/product-rls-real-schema.md`(最小版 4 節)の確定 | **`/finalize-doc`** で承認。`.claude/core-areas.json` と `docs/README.md` の更新を**同一コミット**で行う。**計画系コミットなのでステップ記法を付けない** |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**総数が変わりうるためステップ記法に `/<N>` を書かない**(設計書 6.1 の厳密文法③)。**番号は 1 から連続する。**
**着手は TSK-443(#87)のステップ 8 着地後。** ただし **G1・G2 は並行して進められる**。

| # | ステップ | 合格条件(**人間の判断を含まない。実行者によらず同じ結果になること**) |
| --- | --- | --- |
| 1 | **専用 Postgres インスタンスを `docker-compose.yml` へ足す** — 別サービス・別ポート・別の名前付きボリューム | `docker compose up -d` で起動し `pg_isready` が通る。**共有開発 DB のサービス定義の差分 0 行**。`.env.example` にキーを追加(**値は書かない**) |
| 2 | **`scripts/` の runner に対象検査と撤去・作り直しを置く** | ① 4-5 節の対象検査 4 項目が**すべて通ったときだけ** DROP へ進む ② 判定不能・不一致なら**終了コード非 0 で中止し、DROP を実行しない** ③ 撤去 → 作り直し → `alembic upgrade head` を 2 回連続実行して、**2 回目の終了コードと migration head が 1 回目と一致** ④ **`backend/tests/` の差分 0 行** |
| 3 | **`scripts/` の pytest プラグインを置く(接続先の差し替え)** | ① `pytest -p <plugin>` で既存 17 本を収集でき、**node ID の集合が `backend/tests/db/test_product_authz_{tenant_owned,cross_cutting,other_profiles}.py` の 17 件と exact 一致** ② **プラグインを付けない既定実行の収集集合が本 PR の前後で exact 一致** ③ **fixture を再定義していない**(`backend/tests/` と同名 fixture の定義が 0 件) |
| 4 | **製品 authz DDL を専用インスタンスへ適用する**(通過条件①) | ① `apply_product_authz_ddl` が終了コード 0 ② **実行中に Docker コンテナが 1 つも作られていない**(実行前後のコンテナ一覧が一致) ③ **接続の host・port が専用インスタンスの設定値と一致** ④ カタログ検査が 0 件の差分 ⑤ **非 superuser と `pitchlog_app` での適用が拒否される**(故障系 2 本) |
| 5 | **既存 17 本を専用インスタンスに対して実行する**(通過条件②) | ① **17 本すべて green**(skip を成功に数えない) ② 実行した **node ID の exact-set** と test ファイルの commit を記録 ③ 4-5 節の**生成 ID が適用時と一致** |
| 6 | **12-4 の判定を PR へ記録する** | 正本由来 4 項目(`../../design/data-model.md:2536`)+ 同一対象 5 項目(4-5 節の表)。**入口は「対象入口なし」と書く(項目を省かない)**。**限界 2 件を明記**。**ステップ 4・5 の実測が揃うまで記録しない** |
| 7 | **DoD の現行化と worklog** | [research-dod-revision.md](research-dod-revision.md) の DoD 2・4・5・6 を反映。`docs/README.md` の索引が現行 |

## 5. DoD(受け入れ基準)

> 変わるのは **DoD 2・4・5・6**、**DoD 1 と 3 は不変**([research-dod-revision.md](research-dod-revision.md)`:50`〜`:57`)。

- [ ] **【DoD 1・不変】RLS のポリシーとロールの DDL が実スキーマへ適用されている**(通過条件① — `../../design/data-model.md:2531`)
- [ ] **【DoD 2・変わる】その実スキーマに対して越境テストが green である**。**②の green は「適用単位」の範囲で判定する** — **判定の対象は当該 PR が開く入口の集合に限り、当該 PR が開いていない入口を理由に不合格と判定しない**(同 `:2530`)
- [ ] **【DoD 3・不変】最低要求 4 件を覆っている**(同 `:2532`)— ① アプリ用ロールが関数を経由せず他テナント行を読めない ② `PUBLIC` が越境関数を実行できない ③ `search_path` の乗っ取りが効かない ④ 対象側が非共有なら要求元が付与していても返らない
- [ ] **【DoD 4・変わる】測定経路の要求は空であることを確認した** — **本タスクの PR は入口を 1 つも開かない**。**空であることは要求の免除ではなく、要求を当てる対象が無いこと**(同 `:2534`)
- [ ] **【DoD 5・変わる】通過判定を PR に記録した** — 誰が・いつ・どの対象に対して green を確認したか・**どの入口について判定したか**。**入口を 1 つも開かないので「対象入口なし」と書く(項目を省かない)**(同 `:2536`)
- [ ] **【DoD 6・変わる】12-4 の越境テスト再実行ゲートを通ったことを記録した**。**「non-serving 宣言の解除」ではない** — 新版の第 2 項は **PR ごとの継続的条件**へ変わり、一回性の契機が消えた。**「non-serving 宣言の解除」という語は正本に 1 件も無い**(全数確認 — [research-dod-revision.md](research-dod-revision.md)`:131`〜`:152`)。**第 1 項に終期を与える作業は TSK-382 の所有**
- [ ] **判定記録が同一対象 5 項目を満たす**(4-5 節の表)— インスタンス識別 / 接続先の識別子(**資格情報は記録しない**)/ **生成 ID** / migration head / DDL 資産の digest。あわせて**実行した test の commit と node ID の exact-set**・実行コードの commit
- [ ] **④ の満たし方を判定記録に明記した** — 現時点の ④ は「**越境関数が 0 件であることの表明**」で満たしており、**U-C1 / U-C2 / U-C3 / U-A2 が関数を足した時点で ④ の試験は各単位の責務になる**(4-4 節)
- [ ] **限界 2 件を判定記録に明記した** — ① **変異による感度の確認は TSK-442 の試験 ID に委ねた** ② **既存データを持つ DB への適用は検証していない**
- [ ] **既存ジョブの配線と backend pytest の収集集合を変えていない**、かつ**増えた検査対象が green**(6 節の 4 項目)
- [ ] **`.claude/core-areas.json` の `tenant-isolation` の `paths` に 3 件が登録されている** — 運用正本 / `scripts/` の runner とプラグイン / その設定資産
- [ ] **DoD 自体の現行化**(TSK-381 の成果を反映)

## 6. テスト計画

**NFR-019 の「越境」に当たる。** ただし**本タスクは HTTP 入口を持たない**ので、判定は **DB 層(ロール・関数 ACL・`search_path`)**で行う。
**最低要求 4 件は HTTP 経路への要求を 1 件も含まない**(`../../design/data-model.md:2533` の逐語)。

### 試験の置き場と実行

**すべて `scripts/` の手動 runner に置く。`backend/tests/` へは 1 ファイルも置かない**(裁定 2026-09-28)。

| 対象 | 種別 | 置き場 | 確認すること |
| --- | --- | --- | --- |
| 対象検査と撤去・作り直し | 正例 + 故障系 | `scripts/` の runner | 4-5 節の 4 項目が通ったときだけ DROP。**判定不能なら中止**。2 回連続で終了コードと migration head が一致 |
| 製品 authz DDL の適用 | 正例 + 故障系 | 同上 | 終了コード 0・カタログ検査の差分 0 件・**Docker コンテナが作られていない**・接続先が専用インスタンス・**非 superuser と `pitchlog_app` での適用が拒否される** |
| **既存 17 本の実行** | 越境 | **既存ファイルをそのまま実行**(新設しない。部分集合も採らない) | **17 本すべて green**(skip を成功に数えない)。node ID の exact-set と commit を記録 |

**17 本の内訳**(`backend/tests/db/`):`test_product_authz_tenant_owned.py` 3 本 / `test_product_authz_cross_cutting.py` 7 本 / `test_product_authz_other_profiles.py` 7 本。
**最低要求 4 件との対応は 4-4 節の表**が正。**1 周目 P1 の是正** — 旧版は `other_profiles` の 7 本を数え漏らして「10 本」と書いていた。

### CI の実行内容を変えないことの確認

> **【1 周目 P1 の是正】** 旧文は「CI の実行内容を変えない」と書いていたが**実際より広い約束**だった。
> **新設する `scripts/` のファイルは harness ジョブの `ruff` と `ty` の検査対象に入り**(`.github/workflows/ci.yml:85-90`・ルート `pyproject.toml` の検査対象が `scripts/`)、
> **`docs/ops/` は `docs-lint` の母集団を増やす**。**約束するのは次の 2 つに限る。**

**保証する 2 つ**:

1. **既存ジョブの配線を変えない** — `.github/workflows/` の差分 0 行 / DB の外部依存を増やさない / 既存ジョブの選択条件を変えない
2. **backend pytest の収集集合を変えない** — `backend/` で `uv run pytest -c pyproject.toml --collect-only -q` を実行し、**`::` を含む行を集合として比較して exact 一致**。**基準線 = 792 件**(うち `tests/db/` 配下が 203 件)。**終了コードは見ない** — `--collect-only` でも `backend/tests/db/conftest.py` の DB ガードが働いて `exit=1` になる(実測)

**増える検査対象については「変えない」ではなく「green であること」を条件にする**:

3. **新設した `scripts/` のファイルが `ruff check` と `ty check` を通る**
4. **新設した `docs/ops/` の文書が `docs-lint` を通る**(frontmatter・索引・変更履歴)

> **参考(実測)**: 「DB 必須テストが 0 件なら赤」は **`backend/tests/db/` の収集時にしか読まれない**
> (`backend/tests/db/conftest.py:60-125`)。また **「pytest 呼び出しは 1 回」を強制する機構はコード上に無く**、
> CI が 1 本しか呼ばない事実(`.github/workflows/ci.yml:258`)と、session スコープの `CREATE ROLE`
> (`db_fixtures.py:327-329`)が並行を許さないことの重なりである。

## 7. 人間の裁定が要る事項

### 未決 — **この 2 件が無いと本タスクは完了できない**(2 周目の敵対レビューで確定)

> **人間の意思(2026-10-03)**: 「**344 は終わらせたい**」。**普通に終わらせる道は帯 3 を丸ごと通すことだが、
> 帯 3 は直列(`U-A1 → U-A2 → U-C1 → U-C2 → U-C3` — `../product-impl-unit-split/plan.md:385`)で、
> **先頭の U-A1 は計画書が白紙**である。**短く終わらせる道は下の裁定 2 件しかない。**

| # | 未決 | なぜ要るか(実測) | 性質 |
| --- | --- | --- | --- |
| **A** | **最低要求 ④ の現時点での満たし方**を確定する — 「**越境関数が 0 件の間は、0 件であることの表明をもって ④ を満たしたと記録する**」を 12-4 の運用解釈として置けるか | ④「対象側が非共有なら要求元が付与していても返らない」は**共有集計の越境関数**を要する。関数は 0 件で、**所有は U-C3**(帯 3 の最後)。表レベルでは代替できない — `sharing_grants` のポリシーは**自分の実効メンバーシップ**で絞るだけで相互性を表現しない(`contracts/authz/product/function-bodies/policies/POLICY:sharing_grants:effective_group_control.sql`)。既存 seed の `grant_flags` は**全件空**(`backend/tests/product_authz_other_profiles_cases.py:247`) | **正本の改訂**。`data-model.md:2533` が「**4 件の文言は変えない**」と定めるので、**文言を変えず「現時点の満たし方」を注記する**形になる。**`/finalize-doc`**。TSK-382 と同じ性質 |
| **B** | **既存 17 本が外部供給のカタログを受け取れる経路**を `backend/tests/` へ 1 つ足すことを許すか(**裁定 2026-09-28 の緩和**) | 既存 17 本は **function スコープ**の `provisioned_product_catalog` で**テストごとに使い捨てクラスタを立て、DB を作り、DDL を適用する**(`backend/tests/db_fixtures.py:949`・`:615`)。**自分で作った対象しか検査しない**ので、「ステップ 4 で適用した実スキーマに対して再実行する」が原理的に成立しない | **コア領域の編集**。緩和の正当性は「裁定の趣旨は**実スキーマ不在の無関係な PR が既定 pytest で赤になるのを防ぐ**ことであり、**opt-in で既定の挙動が不変なら趣旨に反しない**」。**既定の収集集合と既定実行の挙動が不変であることを実測で示す**ことを条件にできる |

**A が無いと DoD 3 を満たせず、B が無いと DoD 2 を満たせない。** どちらか一方でも欠けると 12-4 のゲートは通らない。

### 決定済み(2026-10-03)

| # | 事項 | 決定(2026-10-03・山田正輝) |
| --- | --- | --- |
| 1 | **「実スキーマ」を何と数えるか** | **当初は「専用の永続 DB」**。**1 周目 P0-3 で前提が壊れ(ロールはクラスタ単位)、同日に「専用の Postgres インスタンスを立てる」へ改めた。** 共有開発 DB(compose の `${POSTGRES_DB}`)は対象にしない — 他セッションの backend pytest を壊す実績があるため |
| 2 | **TSK-382 との線引き** | **運用対象だけ決める。** 12-4 の「実スキーマ」の**正本上の意味は定義しない**(TSK-382 の射程を先取りしない) |
| 3 | **運用手順書の範囲** | **最小版**(4 節)を本タスクで確定する。本番運用・災害復旧・複数環境は後継タスクへ |
| 4 | **隔離の粒度**(1 周目 P0-3・P0-4 を受けて) | **専用の Postgres インスタンスを `docker-compose.yml` へ足す。** インスタンスは永続(名前付きボリューム)、**対象 DB は実行のたびに作り直す**。ロールがクラスタ単位である以上、DB 分離では既存試験の破壊的操作を隔離できないため |

## 8. 旧版からの差分(依存 9 件 → 2 件)

| 旧依存 | 旧状態 | 本改訂での扱い |
| --- | --- | --- |
| 1 表分類・製品 authz DDL 資産・capability カタログ | TSK-424 PR A1 | **着地済み**(PR #79)→ 依存から外す |
| 2 適用器・実 DB 試験・写像・`provisioned_product_catalog` | TSK-442 PR A2 | **着地済み**(PR #84)→ **依存 2 として残す**(既存 17 本と cases 3 本の存在) |
| 3 ランタイム契約の切り替え | TSK-443 PR B | **依存 1 として残す**(唯一のブロッカー) |
| 4 Session の供給 | TSK-444 PR C | **着地済み**(PR #82・2026-10-03)→ 依存から外す |
| 5 `shared_read` の代表 | U-C3 | **射程外へ**(2 節) |
| 6 `control_read` の代表 | U-C2 | **射程外へ** |
| 7 `representative_management_operation` の代表 | U-C1 | **射程外へ** |
| 8 管理関数の代表 | U-A2 | **射程外へ** |
| 9 シナリオ ID と digest を持つ不変な試験ベクタ | TSK-442 | **構造で代替**(4-3 節)。**#84 には入らなかった**ことを実測で確認済み(`contracts/` に `scenario_id` 0 件) |

## 9. 踏んではいけない他タスクの射程

| 範囲 | 所有 | 典拠 |
| --- | --- | --- |
| **12-4 の「実スキーマ」の意味の確定**・**`SP-06` と 12-4 の字面衝突**・**non-serving 第 1 項に終期を与える作業** | **TSK-382** | `../../adr/ADR-004-merge-gate-scope.md:44` / `../product-authz-surface/design.md:652` |
| **`data-model.md` 12-8 節の実装追随** | **TSK-424** | `../tenant-boundary-enforcement/plan.md:79`・`:125` |
| 表分類・プロファイル割り当て | **TSK-424** | `../product-authz-surface/design.md:595` |
| **移行バッチ用ロールの退役・接続終了・ACL 剥奪・孤児回収** | **TSK-349** | **8-3 検査が落ちても本タスクでは実行しない** — **観測して不合格にするだけ** |
| **`product_provisioning` / `product_catalog` / `provisioned_product_catalog` の書き換え** | **TSK-442** | **実スキーマ向けに書き換えない**。必要なら**本タスク所有の別アダプタを `scripts/` 側に定義する** |
| **最終パスへの切替・生成ランタイム契約・凍結基準** | **TSK-443** | **変更しない** |
| **Session 供給機構**(`repositories/transaction.py`) | **TSK-444**(完了) | **変更しない** |
| **`contracts/authz/product/` 配下の全体** | **TSK-424** | **読み取り専用** — DDL・分類・capability・適用手順・故障注入点・移行ロール・写像のいずれも変更しない |
| **関数本体・ACL・所有者・`search_path`** | **U-C1 / U-C2 / U-C3 / U-A1 / U-A2** | **再実行の都合で補修しない** |

**DoD 6 は「12-4 のゲートを通ったことを PR に記録した」という条文への写像に留める**(PO 裁定)。
**ただしステップ 6 を「DoD 1・2・最低要求 4 件の実測完了後にのみ記録可能」と拘束する** — 記録だけ先に作れてしまう経路を塞ぐ。

## 10. 本タスクが開けるもの

**帯 2 の葉 6 本 + 帯 3 の 6 本 = 12 単位のマージ路**(`../product-impl-unit-split/plan.md`)。
これらは「入口を開く単位」なので 12-4 ゲートの対象で、**実装はできるがマージできない**状態にある。

**ただし単独では開かない** — 入口を開くには製品 CRUD 経路を表す `route_kind` も要る。
**2026-09-24 に TSK-446 として起票し、`record_and_aggregate` を実装した**
(`scripts/check_authz_catalog.py:92` の `ROUTE_KINDS`)。

## 11. 本改訂の経緯(周回リセットの根拠)

**旧版は計画レビュー 7 周で収束しなかった。** P0 件数は 3 → 6 → 6 → 5 → 5 → 5 と減らず、
6 周目に人間が承認した射程縮小(変異試験の TSK-442 への委譲)は**新しい P0 を 2 件生んだ**。

### 収束しなかった 2 つの原因(実測で特定)

1. **「実スキーマ」が未定義のまま、それに依存する契約を書き続けた。**
   正本は意味を**明文で定義しない**と宣言している(`../product-authz-surface/design.md:652`)。
   旧版はその穴を自前で埋めようとし、「識別タプルと権威ある取得元と適格性述語」を書く作業に 5 周を使った。
   **本改訂は人間の決定により、運用対象の特定にとどめ、条文の意味は TSK-382 へ残す。**
2. **5〜6 周目に、存在しない 4 単位の「代表」を必須依存へ格上げした。**
   代表が存在しない以上それは「再実行」ではなく「作成」であり、1 節の切り分けに反する。
   **書けない契約を書こうとしたので、周ごとに P0 が湧いた。**

### 引き継いだもの

2 節のやること骨子 / 3 節の正本影響(`docs/ops/` 新設・`core-areas.json` への paths 追加・読み取り専用の宣言)/
DoD 現行化の内容 / `--collect-only` の測り方と基準線 792 件 / 判定記録の同一対象の考え方(**4 項目 → 5 項目へ拡張**)/
non-serving 区間の定義と「途中で失敗したら serving に戻さない」/ 9 節の射程表。

### 落としたもの

旧 8 節「代表の選択規則」(5 周目 P0-2)と「上流試験の移植」(5 周目 P0-3)/ 依存 5〜9 /
`maintenance latch` / 変異試験 / **旧ステップ 1 の「許可された危険ロール集合」4 項目**
— **適用主体の検査が製品コード側にある**ことが判明したため(`product_provisioning.py:497-511`)。

### 直した誤り

`../tenant-boundary-enforcement/design.md` への引用を **`:335-345` → `:356-366`** へ全件是正した(3-5-a 節の挿入で 21 行ずれていた)。

### 1 周目の敵対レビュー(2026-10-03)で直したこと

**P0 7 件・P1 4 件・P2 1 件。うち 1 件は反証し、残りを反映した。**

| 指摘 | 扱い |
| --- | --- |
| **P0-1** 最低要求 ④ を検証できず DoD 3 を満たせない | **反証した。** `../product-authz-surface/design.md:482` が「**越境関数が本単位に無い場合は `pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件であることを表明する**」と既に解いており、その試験(`test_app_can_execute_no_security_definer_function`)が実在する。**4-4 節に 4 件 ↔ 17 本の対応表を追加**し、④ の性質(関数が増えたら各単位の責務へ移る)を判定記録の必須項目にした |
| **P0-2** 接続先の差し替え経路が未設計 | **4-3 節で確定した。** `scripts/` の pytest プラグインでモジュール関数を差し替える。**fixture の再定義では成立しない**(conftest が勝つ)ことも明記。**green だけを証拠にしない**ため、Docker コンテナ 0・接続先一致・生成 ID 一致の 3 点を合格条件にした |
| **P0-3** DB の作り直しでは 7 事象が消えない(ロールはクラスタ共通) | **設計を変えた。** 専用 DB → **専用インスタンス**(4-1 節)。「7 事象がすべて消える」という誤りを本文に記録した |
| **P0-4** 承認された「専用の永続 DB」を計画が読み替えている | **人間へ戻して再裁定を得た**(7 節 #4)。インスタンスは永続・対象 DB は作り直し、という形で確定 |
| **P0-5** 破壊的操作の対象判定と証跡の同一性が未定義 | **4-5 節を新設。** DB 識別タプルの構成要素と取得元、**生成 ID による 3 者の拘束**、DROP 前の対象検査 4 項目(**判定不能なら中止**)を定めた |
| **P0-6** ステップ番号とコミット規約が衝突する | **G1・G2 をステップ表の外へ出し、実装ステップを 1 から連続させた** |
| **P0-7** 新 runner がコア保護から漏れる | **`core-areas.json` への追加を 1 件 → 3 件**(運用正本・runner とプラグイン・設定資産)にした |
| **P1** 「既存 10 本」が閉じた集合でない | **17 本へ是正**(`other_profiles` の 7 本を数え漏らしていた)。内訳と 4 件との対応を固定した |
| **P1** non-serving 区間の定義が本文に無い | **4-6 節を新設**して始期・終期・排出対象・中断時の扱いを本文へ書いた |
| **P1** ステップの判定語が不足 | **合格条件を実行者によらない形へ全面的に書き直した**(終了コード・exact-set・差分 0 件・前後一致) |
| **P1** 「CI の実行内容を変えない」が実際より広い | **保証を 2 つに狭め、増える検査対象は「green であること」を条件にした**(6 節) |
| **P2** NFR-019(b) の引用が `:930` | **`:933` へ是正** |

### 2 周目の敵対レビュー(2026-10-03)で分かったこと

**P0 4 件・P1 3 件・P2 1 件。うち 2 件は「計画の書き方では閉じない」ことを示した。**

| 指摘 | 扱い |
| --- | --- |
| **P0-1(再)** ④ は「0 件の表明」では実測できない | **反証に失敗した。** 正本 `:555` が「**とくに『対象側は非共有・要求元だけ付与』の組み合わせ**」の越境テストを明示的に要求している。**7 節の未決 A へ上げた** |
| **P0-2(新)** 既存 17 本は**自己完結型**で、適用済みの対象を検査できない | **決定的。** `provisioned_product_catalog` も `disposable_postgres_cluster` も **function スコープ**(`backend/tests/db_fixtures.py:949`・`:615`)で、**テストごとに使い捨てクラスタを立てて DB を作り DDL を適用する**。ステップ 4 で適用済みなら 1 本目で衝突し、適用しなければ「適用した対象を試した」ことにならない。**7 節の未決 B へ上げた** |
| **P0-3(新)** DROP 前の対象検査が設定値の自己照合で、真正性を示せない | 未決 B の結論後に設計へ反映する。**接続したサーバーの識別値を compose の実コンテナへ独立に突合する**条件が要る |
| **P0-4(新)** 「Docker コンテナ 0」は偽陽性になる | 同上。元 fixture は `docker run --rm` の後に `docker rm` するので、**途中で作って消しても前後の一覧は一致する**(`db_fixtures.py:639-674`)。**作成呼び出しかイベントを観測する**形へ改める |
| **P1** プラグインの差し替え時点が未指定 | `conftest.py:6-29` が `db_fixtures` から**直接 import** するため、後から名前を差し替えても効かない。未決 B の結論後に確定する |
| **P1** G2 の無記法コミットが `feature_status.py` と整合しない | `.claude/core-areas.json` を含む無記法コミットは**実装扱い**になり進捗が「不明」に落ちる(`scripts/feature_status.py:797-820`・`:867-891`)。**G2 を分割するか記法を付けるかを、着手時に決める** |
| **P1** ステップ 1・2 の合格条件が実行者間で一致しない | 「2 回の終了コードが一致」は**両方失敗でも満たす**。**両回の成功**へ改める。専用ポート占有時・キー未設定時の期待結果も定める |
| **P2** 変異の射程の表現が食い違う | 2 節 66 行目を「**新規の変異試験の設計・追加**が射程外」へ言い換える(既存試験の再実行は射程内) |

**本改訂の到達点**: **計画の書き方で閉じる指摘はすべて閉じた。残るのは正本と裁定の問題 2 件**(7 節の未決 A・B)である。
**この 2 件が決まるまで `承認: 済` にできない。**

