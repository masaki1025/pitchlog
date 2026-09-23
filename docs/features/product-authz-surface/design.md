---
feature: product-authz-surface
type: design
date: 2026-09-24
---

# 詳細設計: TSK-424 製品認可面の確定

本書は [plan.md](./plan.md) 4 節から参照される詳細設計である。調査の典拠は [research.md](./research.md)。
入力は U-T1 の詳細設計 `../tenant-boundary-enforcement/design.md` の 2〜4 節・7 節・9 節で、
**それを正本と実測で検証し直したうえで、本単位の設計として確定する**。U-T1 の記述を是正した箇所は、各節で明記する。

## 1. 許可プロファイル

### 1-1. 物理プロファイルは 4 種、到達経路は属性で分ける

U-T1 は P1〜P5 の 5 種を置き、Notion カードは「親表経由のテナント所属」と「認証前グローバル可変」の追加を求めた。
**本単位は、プロファイルの軸を 2 つに分ける**:

- **物理プロファイル**: DB に何を置くか(RLS・ポリシー・アプリ用ロールの ACL)。**4 種**
- **到達経路**: アプリがその表に**どこから**到達するか。**`direct`(アプリ用ロールが直接読み書きする)か、関数経由か**。関数経由なら、その関数の**所有単位**を持つ

| 物理プロファイル | RLS | ポリシー(アプリ用ロール向け) | アプリ用ロールの ACL |
| --- | --- | --- | --- |
| **`tenant_owned`** | `ENABLE` + `FORCE` | `USING` / `WITH CHECK` とも `COALESCE(tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::UUID, FALSE)` | `SELECT` / `INSERT` / `UPDATE` |
| **`self_tenant_row`** | `ENABLE` + `FORCE` | `USING` のみ `COALESCE(id = ...::UUID, FALSE)`。書き込みポリシーは置かない | `SELECT` のみ |
| **`global_read_only`** | `ENABLE` + `FORCE` | `FOR SELECT USING (true)` のみ | `SELECT` のみ |
| **`function_only`** | `ENABLE` + `FORCE` | **置かない** | **与えない**(期待は `42501`) |

**全 45 表を `ENABLE` + `FORCE` にする**(`data-model.md:202`・`:272`・SP-06 `:2698`)。
プロファイル間で違うのは、ポリシーと ACL だけである。

### 1-2. カードが求めた 2 プロファイルを、独立の物理プロファイルにしない理由

| カードの求め | 対象 | 直接アクセス用のポリシーを置いた場合の問題 | 本単位の処分 |
| --- | --- | --- | --- |
| **親表経由のテナント所属** | `tenant_credentials`(`tenant_id` を持たず、`tenant_auth_subjects` 経由でテナントに属する) | **ログインは TenantContext の束縛前に走る**。親表経由の `EXISTS` 述語は `app.tenant_id` を読むので、**認証の時点では常に 0 行**になり、使い道が無い。束縛後に使えるようにすると、**パスワードハッシュをアプリ用ロールが直接読める経路**が残る | **`function_only`**。到達経路 = 認証関数(所有単位 **U-A1**) |
| **認証前グローバル可変** | `rate_limit_counters` | 行を絞らない書き込みポリシーを置くと、**アプリ用ロールが全テナントのカウンタを書き換えられる**(他チームのロックアウトを起こせる)。正本も「同じアクセス経路に混ぜない」と書く(`data-model.md:1710`) | **`function_only`**。到達経路 = レート制限関数(所有単位 **U-A1**) |

→ どちらも、**直接アクセスの許可を置かず、関数経由に倒す**(fail-closed)。
**「親表経由」と「認証前」は到達経路の性質として記録する**(`access_path.reason`)。
関数を持つ単位が経路を開くときに、**本資産の表分類を改訂する**(表の分類を緩める変更は、コア領域の敵対レビューの対象になる)。

**この処分は Notion カードの DoD「許可プロファイル種別の確定(少なくとも 2 種を追加)」と字面が違う**。
計画の承認をもってカードの DoD を書き換える(plan.md 5 節)。

### 1-3. 制御資源(P3)は `function_only` にする — U-T1 design の記述を是正する

U-T1 design `:141` の P3 は、「**終了済みグループも RLS 上は見え続ける。終了後を 404 にするのは FR-034 の責務**」と書いていた。
**これは正本と矛盾する**。正本 3-5 節(`data-model.md:447-449`)と 3-0 節(`:101-133`)は、
制御資源の RLS 述語を **「実効グループ ∧ 実効参加」** と定めている。
「見え続ける」と書いているのは**「参加行が `active`」だけにした場合に起きる欠陥**のほうであって、許してよい状態ではない。

正本どおりの述語を**直接アクセスの RLS ポリシー**として書くと、成立しない点が 3 つある:

1. **自己参照による再帰**: `group_memberships` のポリシーが `group_memberships` を読む。PostgreSQL では無限再帰のエラー(`42P17`)になる
2. **他テナントの有効状態が見えない**: 「実効参加」は「参加テナントが有効」を含む(`:101-133`)。ところが `tenants` は `self_tenant_row` で、**他テナントの行は見えない**
3. **列の粒度を表せない**: メンバー一覧はテナント名だけ、参加日時と役割は `admin` だけが見る(`:463-471`)。**行ポリシーでは列を絞れない**

→ **制御資源 4 表は `function_only`**。到達経路は、読み取りが **U-C2**(制御情報の読み取り 4 経路)、
操作が **U-C1**(グループ管理 8 経路)の関数である(`../product-impl-unit-split/plan.md:225-226`)。
probe の制御資源ポリシーは `membership.status = 'active'` だけを見ている(`contracts/authz/function-bodies/policies/POLICY:probe_groups:tenant_boundary.sql`)。
これは機構の検証用であり、製品の述語にはならない(正本 `:537`「probe と製品は別の層」)。

### 1-4. 全 45 表の割り当て(母集合 = `contracts/db/schema-manifest.json`)

**`tenant_owned`(24 表)** — 到達経路は `direct`:

`team_records` / `players` / `games` / `lineup_memories` / `game_lineups` / `participation_intervals` /
`tournament_rule_assignments` / `event_slots` / `operation_events` / `play_rows` / `play_runners` /
`temporary_player_id_mappings` / `idempotency_ledger` / `rejected_event_originals` / `evacuated_event_originals` /
`recording_generations` / `medical_notes` / `medical_note_versions` / `pdf_export_records` / `tenant_vocabularies` /
`player_merge_events` / `player_move_records` / `invalidation_intents` / `migrated_final_lineups`

- 追記専用の表(`operation_events` など)も、ACL は正本どおり `SELECT` / `INSERT` / `UPDATE` にする(`data-model.md:209`)。
  変更の禁止は既存のトリガ(migration)が担う。**ACL を表ごとに削る最小権限化は、本単位ではしない**
  (正本の一律規定を変えることになるので。未解決 4)
- `invalidation_intents` は、`T7` と同じトランザクションで要求元テナントの文脈から書く(`data-model.md:2147`)。
  配信側(他テナントへ波及する処理)の到達経路は本単位の射程外(未解決 5)

**`self_tenant_row`(1 表)**: `tenants` — `direct`(`SELECT` のみ)。
テナントの作成・無効化・名称変更の書き込みは、管理経路(**U-A2**)の関数が行う。

**`global_read_only`(5 表)**: `rule_sets` / `game_type_rule_defaults` / `system_vocabularies` / `admin_vocabularies` / `system_settings` — `direct`(`SELECT` のみ)。
書き込みは管理経路(**U-A2**)の関数が行う。**`function_only` にすると通常の入力と設定参照が止まる**(U-T1 design `:145-146`)。

**`function_only`(15 表)**:

| 表 | `access_path.reason` | 所有単位 |
| --- | --- | --- |
| `analysis_groups` / `group_memberships` / `sharing_grants` / `group_invitations` | `control_resource`(1-3) | U-C1(操作)/ U-C2(読み取り) |
| `tenant_auth_subjects` / `tenant_credentials` / `tenant_tokens` | `pre_context_authentication`(1-2) | U-A1 |
| `rate_limit_counters` | `pre_context_global_mutable`(1-2) | U-A1 |
| `admin_credentials` / `admin_sessions` / `admin_operation_logs` | `admin_path`(`data-model.md:1543`) | U-A2 |
| `migration_runs` / `migration_quarantine` / `migration_resolution_reports` / `migration_warning_reports` | `migration_batch_only`(8 節) | 移行バッチ用ロール(FR-038 の移行タスク) |

合計は 24 + 1 + 5 + 15 = **45**。

### 1-5. 表分類の合格述語

U-T1 design の 2-4-b(`:173-180`)を引き継ぎ、次を加える:

- **母集合 = `Base.metadata` の全表 = manifest の全表**。割り当て資産と**両方向 exact-set**(未割り当て 0・重複 0・存在しない表 0)
- **既定のプロファイルを持たない**。モデルを 1 つ足すと red になる負例を置く
- `tenant_id` 列を持たない表に `tenant_owned` を割り当てると red(`tenants` / `analysis_groups` ほか)
- `TenantMixin` を継承している表を `function_only` にするときは、`access_path.reason` が必須(`group_memberships` / `tenant_auth_subjects` / `tenant_tokens` / `admin_operation_logs`)
- **`function_only` 表の所有単位は閉じた列挙**(`U-A1` / `U-A2` / `U-C1` / `U-C2` / `migration_batch`)

## 2. 製品ロール

正本の 5 ロール(`data-model.md:206-212`)を、次の形で資産に置く。**パスワードは資産に書かない**(NFR-014)。

| ロール | 資産上の ID | 属性 | 本単位で作るか |
| --- | --- | --- | --- |
| マイグレーション用(表の所有者) | `product_table_owner` | `NOLOGIN` を既定とし、migration 実行時だけ外部の手順で接続する | **作らない**(外部の前提。移行と同じく外で用意する)。資産には**期待属性として宣言**し、カタログ検査の対象にする |
| アプリ用 | `pitchlog_app`(U-T1 の暫定名 `runtime_contract.py:26` を踏襲) | `LOGIN` / `NOSUPERUSER` / `NOBYPASSRLS` / `NOCREATEROLE` / `NOCREATEDB` / `NOREPLICATION` / `NOINHERIT` | 作る |
| 共有関数所有用 | `pitchlog_shared_fn_owner` | `NOLOGIN` / `BYPASSRLS` | **作る。所有する関数は 0 件**(3-4) |
| 管理関数所有用 | `pitchlog_management_fn_owner` | `NOLOGIN` / `BYPASSRLS` | **作る。所有する関数は 0 件** |
| 移行バッチ用 | `pitchlog_migration_batch` | `LOGIN` / `BYPASSRLS`・**期間限定** | **定常の資産には含めない**。ライフサイクル資産(8 節)だけが有効化する |

- 関数所有ロールを「関数 0 件」で先に作るのは、**U-C1 / U-C2 / U-C3 / U-A1 / U-A2 が関数を足すときに、ロールの属性を後から決め直さなくて済む**ようにするためである。
  関数を持たない `BYPASSRLS` ロールは `NOLOGIN` で、どのロールからも `SET` で到達できない。これをカタログ検査で表明する(R-2 の危険終点の検査)
- probe の `outsider_role` / `management_caller` / `provisioner` に相当するものは、**試験専用の要素**として試験側の fixture で作る。**製品資産には含めない**(写像の理由コードは `test_only_role` / `external_provisioner`)

## 3. 製品 authz DDL 資産の形と置き場

### 3-1. 置き場

```
contracts/authz/product/ddl-elements.json              製品 DDL 要素(roles / schemas / tables / policies / acl / runtime_contract)
contracts/authz/product/table-classification.json      全 45 表の物理プロファイルと到達経路(1 節)
contracts/authz/product/probe-product-map.json         probe 原子要素 ↔ 製品原子要素(7 節)
contracts/authz/product/migration-batch-lifecycle.json 移行バッチ用ロールのライフサイクル(8 節)
contracts/authz/product/function-bodies/               製品側の SQL 本体と manifest.json
```

- **probe 資産(`contracts/authz/` 直下)は 1 バイトも触らない**(封印 — `contracts/authz/oracle-seal.lock.json:40-88`)
- 上記はすべて `contracts/authz/*` に一致し、コア領域に入る(`.claude/core-areas.json:295`)。paths の追加は不要
- `ddl-elements.json` の scope は `{"status": "product_configuration", "product_schema": true, ...}`。**probe の scope 値と重ならない閉じた値**にする

### 3-2. ポリシーの本体

- 述語は `COALESCE(<列> = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)`。
  **`COALESCE` と `NULLIF` の骨格は probe と同じにし、型だけを `UUID` にする**(U-T1 design 2-2)
- **表ごとにポリシーを 1 本の SQL ファイルで持つ**(`function-bodies/policies/POLICY:<table>:<profile>.sql`)。
  **24 表ぶんの同じ述語を手で書き写すことはしない**。1 つの述語要素から生成器が展開する(probe の `predicates/` と同じ仕組み)。
  **展開された結果の SQL を資産として固定**し、生成器が壊れたら digest の差分で red にする
- `tenant_owned` のポリシーは `FOR ALL TO pitchlog_app` で、`USING` と `WITH CHECK` に同じ述語を置く。`DELETE` は ACL が無いので `42501` になる

### 3-3. migration が作る関数の ACL

migration は `public` スキーマにトリガ関数を 33 個作る(`runtime_contract.py:85-119`)。
PostgreSQL は関数の既定の `EXECUTE` を `PUBLIC` に与える(REJ-002 と同じ性質)。

- **33 個すべてから `PUBLIC` の `EXECUTE` を剥奪する**。トリガの発火時には `EXECUTE` 権限を見ないので、剥奪してもトリガは動く。**これを実 DB 試験で表明する**(剥奪後に、アプリ用ロールの書き込みで該当トリガが発火すること)
- **33 個が `SECURITY INVOKER` であること**をカタログ検査で表明する。`SECURITY DEFINER` の関数が migration に紛れ込んだら red にする
- 関数 ACL の exact-set に 33 個を入れる。**越境関数は 0 件**という宣言(`cross_tenant_functions: []`)と一緒に持つ

### 3-4. スキーマの ACL

- `public` スキーマ: `pitchlog_app` に `USAGE` だけを与える。`CREATE` は誰にも与えない(PostgreSQL 15 以降の既定。**明示の `REVOKE` で表明**する)
- 関数所有ロールは、関数を持つようになった時点でスキーマ権限を追加する。本単位では与えない

## 4. 適用経路

### 4-1. 順序

**migration の外で、migration の後に適用する**(裁定 A-2・`D7`)。

1. 使い捨てクラスタを作る(`backend/tests/db_fixtures.py:555-615` と同じ形)
2. 外部の手順で `product_table_owner` を作り、その権限で **`alembic upgrade head`** を流す
3. **製品 authz DDL を適用する**(ロールの作成 → スキーマ ACL → 全表の `ENABLE` / `FORCE` → ポリシー → 表 ACL → トリガ関数の `PUBLIC` 剥奪)
4. カタログ検査と実 DB 試験(6 節)

### 4-2. 1 トランザクションで適用する

probe の適用器は手順ごとに commit している(`backend/src/pitchlog/authz/provisioning.py:491` ほか 4 箇所)。
これは probe が「表そのものを作る」ためで、ロール作成と所有者の切り替えを段階的に行う必要があった。
**製品の適用対象は、migration が作った既存の表**なので、この制約は無い。

→ **製品の適用は、ロールの作成を含めて全体を 1 トランザクションで行う**
(PostgreSQL では `CREATE ROLE` / `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` / `CREATE POLICY` / `GRANT` / `REVOKE` をどれもトランザクション内で実行できる)。
**R-5 の失敗点**(ロール作成後 / ポリシー作成後 / ACL 正規化の途中)で失敗を注入し、**カタログが適用前の状態から 1 要素も変わっていないこと**を検査する。

- 表の所有者でないと `ALTER TABLE` も `CREATE POLICY` もできない。
  適用を行う外部の provisioner は、**トランザクション内で `product_table_owner` の権限を一時的に借り、同じトランザクション内で返す**。
  完了後に「provisioner が `product_table_owner` へ `SET` できない」ことをカタログ検査で表明する(probe の `CATALOG:PROVISIONER-CANNOT-SET-OWNER` と同じ性質)

### 4-3. 適用器の操作種別

probe の適用器は、操作種別を閉じた 5 種で振り分けている(`provisioning.py:19-29`)。
**製品の操作種別は別の閉じた集合**として資産指定オブジェクト(5 節)に持たせる。
**probe の 5 種に製品の種別を足して 1 つの集合にしない**(probe の資産で製品の操作が通る経路を作らないため)。

## 5. ツールチェーンの一般化

U-T1 design 3-3(`:263-284`)の方針を引き継ぐ。**資産指定オブジェクト**(`AuthzAssetSpec`)を導入し、
次の値を束ねて、生成器・body 検査器・適用器・カタログ検査・静的検査・DB fixture へ渡す:

- 資産ルート・要素ファイル・body manifest・body ディレクトリ
- **許可する scope の値**(probe = `verified_probe_configuration` / 製品 = `product_configuration`)
- **操作種別の閉じた集合**と、その処理関数の対応(4-3)
- 資産の種類(`probe` / `product`)

| 部品 | 差し替え点(research.md 4-3) | 方針 |
| --- | --- | --- |
| 生成器 `ddl.py` | `DDL_ELEMENTS_PATH` ほか 3 定数・`generate_authz_ddl(root)` | `generate_authz_ddl(root, spec=PROBE_SPEC)`。**`ddl.py` に SQL 断片も資産識別子のリテラルも書かない**(`backend/tests/test_authz_ddl.py:181`) |
| body 検査器 | `BODY_DIRECTORY` / `DDL_ELEMENTS_PATH` / `ELEMENT_SECTIONS` | CLI に `--asset-spec probe\|product` を足す。既定は `probe` |
| 適用器 | `apply_authz_ddl(connection, root)` | `apply_authz_ddl(connection, root, spec=PROBE_SPEC)`。製品は 4-2 の 1 トランザクション形 |
| DB カタログ検査 | `inspect_authz_catalog` が `DDL_ELEMENTS_PATH` を import | spec を受け取る |
| 静的検査 `check_authz_catalog.py` | `_validate_ddl_scope` が probe の scope 以外を拒否(`:2786-2806`) | **scope の許可値を spec から受け取る**。probe 固有の閉じた検査(probe の表名の直書きなど)は **probe spec のときだけ**走らせる |
| DB fixture | `_load_ddl_asset` / `provisioned_catalog` | 製品用の `provisioned_product_catalog` を**新設**する。既存の fixture は変えない |

- **既定値を probe にして、既存テストを無改変で green に保つ**。「既存テストのファイルを 1 行も変えずに green」をステップの合格条件にする
- **probe spec と product spec の取り違えを red にする**負例を置く(製品資産を probe spec で読むと scope 不一致で拒否、その逆も同じ)。
  **「probe で試験して green にする」抜け道**を塞ぐため(U-T1 design `:280-281`)
- `backend/tests/db/conftest.py` は**再エクスポートを 1 行足すだけ**にする(U-T1 との衝突面。`backend/tests/conftest.py` は変えない)

## 6. 実 DB 試験(最低要求 ① と各プロファイルの挙動)

使い捨てクラスタに migration と製品 DDL を適用し、**2 テナント分の行**を置いて試験する。

| 観点 | 試験 | 期待 |
| --- | --- | --- |
| 最低要求 ①(`data-model.md:2530`) | `pitchlog_app` が、関数を経由せず他テナントの行を読めない | `tenant_owned` 24 表**すべて**で、他テナントの行が 0 行 |
| `USING` | 自テナントの束縛で他テナントの行を読む | 0 行(例外ではない) |
| `WITH CHECK` | 他テナントの `tenant_id` で `INSERT` / `tenant_id` を書き換える `UPDATE` | `42501`(`new row violates row-level security policy`) |
| 未束縛 | `app.tenant_id` を設定せずに読む | 0 行(`NULLIF` → `NULL` → `FALSE`) |
| 不正 UUID | `app.tenant_id` に UUID でない文字列 | `22P02` |
| `DELETE` | `tenant_owned` の行を消す | `42501`(ACL が無い) |
| `self_tenant_row` | `tenants` の自テナントの行 / 他テナントの行 / `UPDATE` | 1 行 / 0 行 / `42501` |
| `global_read_only` | 5 表の `SELECT` / `INSERT` | 読める / `42501` |
| `function_only` | 15 表の `SELECT` | `42501`(**0 行ではない** — U-T1 design `:148-150`) |
| トリガ関数 | `PUBLIC` 剥奪後も、アプリ用ロールの書き込みでトリガが発火する | 追記専用表への `UPDATE` がトリガで拒否される |
| FORCE | `product_table_owner` で接続しても、ポリシーに従う | 未束縛で 0 行 |
| 危険終点(R-2) | `pitchlog_app` から `SET` で到達できるロール集合と、`rolsuper` / `rolbypassrls` / 保護対象の所有者の集合 | 交差が空 |

- **24 表すべてを 1 つずつ試す**。代表の表だけで済ませない(24 表のどれか 1 つでポリシーが欠けると越境になるので)。
  試験は表分類資産から**パラメタ化して生成**し、試験側に表名を直書きしない
- 最低要求 ②③④ は越境関数への要求で、関数が 0 件の本単位では**対象が空**である。
  **空であることを試験で表明する**(`pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件)。
  各単位が関数を足すと、この試験が red になり、②③④ の試験を足すよう促す

## 7. probe ↔ 製品の写像

U-T1 design 2-1(`:76-95`)を引き継ぐ。

- 原子要素は `role` / `schema` / `table` / `policy` / `function` / `acl_privilege`
- 合格条件: **`probe の全原子要素 = mapped ∪ explicit_non_mapping`**、かつ **`製品の全原子要素 = mapped の像 ∪ product_only`**。両方向とも exact-set
- **理由コードは閉じた列挙**:

| コード | 使える原子要素の種別 | 意味 |
| --- | --- | --- |
| `test_only_role` | role | 試験専用(`outsider_role` / `management_caller`) |
| `external_provisioner` | role | 外部の手順が用意する(`provisioner`) |
| `deferred_to_owning_unit` | function / acl_privilege | 所有単位が足す(`owner_unit` 必須: U-C1 / U-C2 / U-C3 / U-A2) |
| `forbidden_by_canon` | acl_privilege | 正本が禁じる(`app_role` の `DELETE` — `data-model.md:209`) |
| `probe_schema_only` | schema / table / policy | probe 専用の器(`probe_data` / `probe_business_rows` など) |
| `product_only` | 製品側の全種別 | probe に対応物が無い製品要素(45 表・トリガ関数 33 個など) |

- `read_control_resources`(`contracts/authz/ddl-elements.json:353`)は `deferred_to_owning_unit` / `owner_unit: U-C2`(U-T1 design 9 節 #2)
- **写像資産を正とし、TSK-250 の予告資産 `scripts/design_relations/product-ddl-map-data-model.json` は本資産から導出する**。
  TSK-250 の計画書(`../data-model-canonical/plan.md:253`)への申し送りを、PR 本文と Notion に記録する

## 8. 移行バッチ用ロールのライフサイクル

U-T1 design 2-5(`:203-237`)を引き継ぐ。**正本の 6 行の条件**(`data-model.md:290-297`)を、次のように対応させる:

| 正本の条件 | 検査 |
| --- | --- |
| 期間限定 | 退役後、`pitchlog_migration_batch` が存在しないか、`NOBYPASSRLS` かつ `NOLOGIN`。**成功時と失敗時の両方**で |
| アプリから到達しない | `pitchlog_app` と関数所有ロールから、`SET` / `INHERIT` で到達できない |
| DDL を持たない | `pg_class.relowner` / `pg_proc.proowner` / `pg_namespace.nspowner` のどれにも現れない |
| 書き込み先の限定 | 表 ACL が、下記の書き込み先資産と **exact-set** |
| 監査 | 接続と一括投入の開始・終了が監査行として残る。**投入が失敗しても残る** |
| 検査対象 | 本資産はコア領域(逐行確認の対象)。定常の適用結果に `BYPASSRLS` を持つ `LOGIN` ロールが 0 件 |

### 8-1. 書き込み先の閉じ方

- **導出の規則**: `contracts/db/schema-manifest.json` で `import_batch_id` 列を持つ表 ∪ `migration_runs`
- **資産**: `migration-batch-lifecycle.json` の `write_targets` に、表 ID と権限(`INSERT` / `UPDATE`)を列挙する
- **合格述語**: `write_targets ⊇ 導出集合`。かつ、`write_targets − 導出集合` の各表には、閉じた理由コードが付いている
  - `fk_parent_without_batch_column`: `event_slots`(`operation_events` が FK で参照する — manifest `:340`)/ `medical_note_versions`
  - `audit_sink`: `admin_operation_logs`(`INSERT` のみ)
- **`admin_operation_logs` へ移行バッチ用ロールが直接書くこと**は、正本に明記が無い(research.md 未解決 3)。**計画レビューで最初に叩く点**として plan.md に明記する

### 8-2. 監査を失敗時にも残す

投入のトランザクションが失敗すると、同じトランザクションで書いた監査行もロールバックされる(U-T1 design 9 節 #5)。

→ 監査行は**投入とは別のトランザクション**で書く。**投入前に「開始」を commit、投入後に「成功」または「失敗」を別トランザクションで commit** する。
試験ドライバは、投入トランザクションの途中で故障を注入する。そのうえで、「開始」と「失敗」の 2 行が残り、投入した行が 0 件であることを検査する。
**試験ドライバ自身が監査行を書く形にはしない**(自分で書けば必ず green になるので)。監査行を書くのは、ライフサイクル資産が定める手順の側である。

### 8-3. 射程

- 本単位が持つのは**ロールのライフサイクル契約と、使い捨てクラスタでの検査**まで
- **実運用の移行実行**(FR-038)は持たない
- **TSK-349 との関係**: TSK-349 の DoD のうち、ロールの追加・退役の検査・監査の検査は本単位が持つ。
  TSK-349 の「凍結 probe 資産への追加と `--reseal-oracle`」は**採らない**(probe と製品は別の層 — `data-model.md:537`)。
  TSK-349 を取り下げる。「本番の移行実行の中で確かめること」は FR-038 の移行タスクへ移す(plan.md 2 節)

## 9. ランタイム契約の切り替え

U-T1 との往復契約(U-T1 design 3-5-a・`backend/tests/test_authz_runtime_contract.py:127-156`)を満たす。

1. `contracts/authz/product/ddl-elements.json` に `runtime_contract` オブジェクト(8 フィールド)を置く。
   値は製品資産から**導出**する(`application_role` = 2 節の `pitchlog_app` / `protected_objects` = 45 表・`public`・トリガ関数 33 個 / `provisional: false` / `superseded_by: null`)
2. 生成器で `backend/src/pitchlog/authz/runtime_contract.py` を作り直す(`PROVISIONAL = False` / `SOURCE_ASSET` = 製品資産 / `SUPERSEDED_BY = None`)
3. **暫定資産 `contracts/tenant_boundary/runtime-authz-contract.json` を削除する**

### 9-1. 設計書 7.7 と TSK-431 との順序

暫定資産の削除は、**凍結基準を動かす行為**である(7.7-1「基準の削除も『動かす』に含む」)。

- 7.7-1: 削除後に凍結対象が 1 つも残らなければ、宣言は置かない。ただし**値をソースに残さない**(`scripts/check_tenant_boundary_bypass.py:37-45` の `FROZEN_BASELINE_ASSETS` から取り除く)
- 7.7-2: 削除の記録(新旧の識別値・何を変えたか・事実・理由・承認者・承認日)を**追記のみ**で残す
- **ところが、削除記録を検査する機構が無い** — 既知欠陥 **7D**(HEAD 側の一覧しか走査しないので、削除した資産の旧パスの履歴を検査できない)。これを直すのは **TSK-431(着手可)**

→ **切り替えは本計画の最後のステップにし、TSK-431 のマージ後に行う**。
それまでのステップは TSK-431 と並行して進められる(衝突面は `contracts/tenant_boundary/` と `scripts/check_tenant_boundary_bypass.py` で、切り替えステップ以外では触らない)。

**TSK-431 が遅れた場合**: 切り替えより前のステップだけで PR を分けることを、その時点で人間に諮る。
**7D を開けたまま削除を強行することはしない**。

### 9-2. 暫定資産の「未承認」表記

暫定資産の履歴は、PR #72 のマージ後も `source_commit: PENDING_ACCEPTANCE` と「未承認(PR #72 のレビュー待ち)」のままである(research.md 4-4)。
削除記録(7.7-2)では、**変更前の値をこのまま記録し、事実として「PR #72 のマージ後も受理値へ更新されていなかった」と書く**。本単位で値を書き換えてから削除することはしない(記録の改ざんになるので)。

## 10. capability の扱い

U-T1 design 3-5-a は「製品 capability も TSK-424 の出力契約に含める」と書いている。

→ **本単位が出すのは、capability を導くための入力(表分類資産)まで**である。
**`PRODUCT_CAPABILITY_IDS` などは空のまま残す**(`backend/src/pitchlog/repositories/repository_contract.py:57-59`)。

- 理由: capability を 1 つでも入れると、**製品表への操作が開く**。操作を開くのは、その経路を持つ単位(U-01 ほか)の射程である。本単位は経路を開かない
- 出力契約として固定する事項: 表分類資産のパスとスキーマ(表 ID → 物理プロファイル → 到達経路 → 所有単位)。
  **`direct` の表だけが capability の候補**で、`function_only` の表から capability を作ると red になる検査を**本単位で置く**(capability を作る側が誤って `function_only` の表を開けないように)
- U-T1 の「順序依存は 1 点だけ」(`../tenant-boundary-enforcement/plan.md:113-118`)とは矛盾しない。U-T1 が待っていたのは期待ロール名と保護対象(9 節)で、capability の中身ではない

## 11. 正本の追随

| 箇所 | 変更 | ゲート |
| --- | --- | --- |
| `data-model.md` 12-8(`:2844-2846`) | TSK-317 行を**分割**する。製品の RLS・ロール DDL・表分類・移行ロールのライフサイクル = TSK-424(本 PR で landed)/ 越境関数と ②③④ = U-C1 / U-C2 / U-C3 / U-A2(残件)/ 実スキーマでの再実行 = TSK-344(残件)。**「解消済み」にしない** | 7.6-3 前段(実装追随の節更新)→ PR レビュー |
| `data-model.md` 3-2(`:296`) | 監査の根拠を `NFR-012` → **裁定 `A-3`** に直す(契約は変えず、引用だけを直す) | 同上。**PR レビューで「契約を変えていない」ことを確認する** |
| `data-model.md` 変更履歴 | 上の 2 件を 1 行で追記する。版は上げない | 同上 |
| `docs/README.md` | 索引の現行化 | 同上 |

- **12-6 の受け取り先表(`:2719`・`:2725`)は変えない**。TSK-382 が扱う 3 箇所の 1 つだからである(12 節)
- **3-5 節の述語は変えない**。本単位は述語を `function_only` に倒すだけで、「実効グループ ∧ 実効参加」という契約はそのまま U-C1 / U-C2 の関数が満たす

## 12. 他タスクとの境界

| タスク | 境界 |
| --- | --- |
| **TSK-344** | 本単位 = 使い捨てクラスタで作成・初回実行 / TSK-344 = 実スキーマで再実行(`data-model.md:2846`) |
| **TSK-382** | 本単位は**実スキーマへ適用しない**。SP-06(12-9)・12-4 の non-serving 宣言・12-6 の受け取り先表の**どれも変えない**。資産の中身(全表に FORCE)は SP-06 の方針どおりで、衝突しない |
| **TSK-431** | 9-1 のとおり。切り替えステップだけが TSK-431 のマージを待つ |
| **TSK-349** | 8-3 のとおり。取り下げて吸収する |
| **U-A1 / U-A2 / U-C1 / U-C2 / U-C3** | 関数と、その ACL・`search_path`・関数所有ロールへの所有の付与は各単位が持つ。本単位は「関数 0 件」を宣言し、関数が足されたら red になる試験を置く(6 節) |
| **TSK-250** | 写像資産は本単位が正。TSK-250 の予告資産は導出側(7 節) |

## 未解決・検討メモ

1. **`admin_operation_logs` への移行バッチの直接書き込み**(8-1)— 正本に明記が無い。代わりの案は「監査行は管理関数(U-A2)経由で書く」。ただしその場合、移行バッチ用ロールが管理関数を `EXECUTE` することになり、「アプリから到達しない」とは別の到達経路が生まれる
2. **`tenants` の名称変更の経路** — 本単位は `SELECT` のみを与える。チーム自身が名称を変える要件があるなら、U-A1 か U-A2 の関数経由になる。**要件の確認は各単位へ送る**
3. **`product_table_owner` の作成主体** — 本単位の試験では fixture が作る。実環境で誰が作るかは TSK-344(実スキーマ適用)の射程
4. **追記専用表の ACL の最小権限化** — 正本は一律に `SELECT` / `INSERT` / `UPDATE`(`data-model.md:209`)。追記専用の表から `UPDATE` を外すと防御は一段深くなるが、正本の変更になる。本単位ではしない
5. **`invalidation_intents` の配信側** — 波及先テナントへの配信を誰がどの権限で行うかは、11-2 節を持つ単位の射程。本単位は、要求元テナントの文脈で書けることまでを保証する
