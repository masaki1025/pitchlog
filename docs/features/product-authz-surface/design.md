---
feature: product-authz-surface
type: design
date: 2026-09-24
---

# 詳細設計: TSK-424 製品認可面の確定

本書は [plan.md](./plan.md) 4 節から参照される詳細設計である。調査の典拠は [research.md](./research.md)。
入力は U-T1 の詳細設計 `../tenant-boundary-enforcement/design.md` の 2〜4 節・7 節・9 節である。
**本書はそれを正本と実測で検証し直し、本単位の設計として確定する**。U-T1 の記述を是正した箇所は、各節に明記する。

**改訂履歴**: 計画レビュー 1 周目(P0 7 / P1 8 / P2 2)と 2 周目(P0 6 / P1 7 / P2 2)の反映。各節末の【1 周目】【2 周目】が、その周で直した点である。2 周目の後、移行バッチ用ロールの実行側を TSK-349 へ切り出した(人間の判断 2026-09-24 — 8 節)。

## 1. 許可プロファイル

### 1-1. 物理プロファイルは 5 種、到達経路は属性で分ける

軸を 2 つに分ける:

- **物理プロファイル**: DB に何を置くか(RLS・ポリシー・アプリ用ロールの ACL)
- **到達経路**: アプリがその表に**どこから**到達するか。`direct`(アプリ用ロールが読み書きする)か、関数経由か。関数経由なら、その関数の**所有単位**を持つ

述語 `TENANT(c)` = `COALESCE(c = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::UUID, FALSE)`。

| 物理プロファイル | RLS | アプリ用ロール向けのポリシー | アプリ用ロールの ACL |
| --- | --- | --- | --- |
| **`tenant_owned`** | `ENABLE` + `FORCE` | `FOR ALL`。`USING` と `WITH CHECK` の両方に `TENANT(tenant_id)` | `SELECT` / `INSERT` / `UPDATE` |
| **`self_tenant_row`** | `ENABLE` + `FORCE` | `FOR SELECT USING TENANT(id)` のみ | `SELECT` のみ |
| **`effective_group_control`** | `ENABLE` + `FORCE` | `FOR SELECT`。述語は正本 3-0 節の「実効グループ ∧ 実効参加」(1-3) | `SELECT` のみ(書き込みは U-C1 の管理関数) |
| **`global_read_only`** | `ENABLE` + `FORCE` | `FOR SELECT USING (true)` のみ | `SELECT` のみ |
| **`function_only`** | `ENABLE` + `FORCE` | **置かない** | **与えない**(期待は `42501`) |

**全 45 表を `ENABLE` + `FORCE` にする**(`data-model.md:202`・`:272`・SP-06 `:2698`)。

### 1-2. カードが求めた 2 プロファイルを、独立の物理プロファイルにしない理由

| カードの求め | 対象 | 直接アクセスのポリシーを置いた場合の問題 | 処分 |
| --- | --- | --- | --- |
| **親表経由のテナント所属** | `tenant_credentials` | **ログインは TenantContext の束縛前に走る**ので、`app.tenant_id` を読む述語は認証の時点で常に 0 行になる。束縛後に使えるようにすると、**パスワードハッシュをアプリ用ロールが直接読める経路**が残る | **`function_only`**。到達経路 = 認証関数(所有単位 **U-A1**) |
| **認証前グローバル可変** | `rate_limit_counters` | 行を絞らない書き込みポリシーを置くと、**アプリ用ロールが全テナントのカウンタを書き換えられる**(他チームのロックアウトを起こせる)。正本も「同じアクセス経路に混ぜない」と書く(`data-model.md:1710`) | **`function_only`**。到達経路 = レート制限関数(所有単位 **U-A1**) |

**正本はこの 2 表の RLS を定めていない**(research.md 1-5)。したがって `function_only` は正本の契約の変更ではなく、正本が実装に委ねた範囲の中での fail-closed な選択である。
「親表経由」と「認証前」は、到達経路の理由(`access_path.reason`)として記録する。
関数を持つ単位が経路を開くときに、本資産の表分類を改訂する。表分類を緩める変更は、コア領域の敵対レビューの対象になる。

**この処分は、Notion カードの DoD「許可プロファイル種別の確定(少なくとも 2 種を追加)」と字面が違う**。計画の承認をもって、カードの DoD を書き換える(plan.md 5 節)。

### 1-3. 制御資源 4 表は正本どおり RLS ポリシーで守る — 補助関数で再帰を避ける

**U-T1 design `:141` の P3 は、「終了済みグループも RLS 上は見え続ける」と書いていた。これは正本と矛盾する**。
正本 3-5 節(`data-model.md:447-449`)と 3-0 節(`:101-133`)は、制御資源の RLS 述語を **「実効グループ ∧ 実効参加」** と定めている。
「見え続ける」と書かれているのは、「参加行が `active`」だけにした場合に起きる**欠陥**のほうである。

正本どおりの述語を素朴にポリシーへ書くと、成立しない点が 2 つある:

1. **自己参照による再帰**: `group_memberships` のポリシーが `group_memberships` を読むと、無限再帰のエラー(`42P17`)になる
2. **他テナントの有効状態が見えない**: 「実効参加」は「参加テナントが有効」を含む。一方で `tenants` は `self_tenant_row` なので、他テナントの行は見えない

→ **述語の判定を補助関数に切り出す**。

| 事項 | 内容 |
| --- | --- |
| 関数 | `authz_private.tenant_has_effective_membership(p_group_id uuid, p_require_admin boolean) RETURNS boolean`。**真偽値だけを返す**(行も列も返さない) |
| 判定 | 呼び出し元テナント(`app.tenant_id`)が、グループ `p_group_id` に**実効参加**している(参加行が `active` ∧ 参加テナントが有効)∧ そのグループが**実効グループ**(`active`)。`p_require_admin` が真なら、さらに役割が `admin` |
| 所有者 | `pitchlog_shared_fn_owner`(`NOLOGIN` + `BYPASSRLS`)。関数の中の読み取りは RLS を迂回するので、再帰しない |
| 所有者の表権限 | **`BYPASSRLS` は RLS を迂回するだけで、表の権限は与えない**。所有者に次だけを与え、exact-set で検査する: `public` の `USAGE` / `tenants`・`analysis_groups`・`group_memberships` の `SELECT`(列は判定に使う列に限る)。**過剰な表・過剰な権限・1 件の欠落を、それぞれ変異で red にする**【2 周目 2-P1-1】 |
| 属性 | `SECURITY DEFINER` / `STABLE` / `SET search_path = pg_catalog, pg_temp`(`pg_temp` を末尾に明示 — REJ-003)/ 本文の表参照はすべてスキーマ修飾 |
| ACL | 作成と同じトランザクションで `REVOKE ALL ... FROM PUBLIC` → `GRANT EXECUTE ... TO pitchlog_app`(`data-model.md:242`) |
| スキーマ | `authz_private`(所有者 `pitchlog_shared_fn_owner`。`pitchlog_app` には `USAGE` のみ・`CREATE` は誰にも与えない) |
| 存在の秘匿 | 参加していないグループと、存在しないグループは、どちらも `false` を返す。**戻り値から存在を推測できない**(FR-034 の 404 と同じ性質) |

**表ごとのポリシー**(すべて `FOR SELECT TO pitchlog_app`):

| 表 | `USING` |
| --- | --- |
| `analysis_groups` | `tenant_has_effective_membership(id, false)` |
| `group_memberships` | `tenant_has_effective_membership(group_id, false)` |
| `sharing_grants` | `EXISTS (参加行 m WHERE m.id = membership_id AND tenant_has_effective_membership(m.group_id, false))` — 参加行の読み取りも同じポリシーに従う |
| `group_invitations` | `tenant_has_effective_membership(group_id, true)`(招待は `admin` のみ — `data-model.md:470`) |

- **列の粒度**(メンバー一覧はテナント名のみ、参加日時と役割は `admin` のみ — `:463-471`)は、行ポリシーでは表せない。**これは正本の二重構成(`:137`)どおり、アプリ層(U-C2 の読み取り経路)の責務**とし、本単位は行の可視性までを持つ
- **この関数は越境関数(記録・集計を返す経路)ではなく、ポリシーの述語の一部**である。U-T1 plan `:86` が「製品 RLS の述語構造は TSK-424」と定めた範囲に入る
- 本関数を置くので、**最低要求 ②(`PUBLIC` が実行できない)と ③(`search_path` の乗っ取りが効かない)が本単位にも掛かる**。6 節で試験する

【1 周目 1-P0-1】旧案は制御資源を `function_only` にしていた。これは正本 3-5 の契約の変更で、確定ゲートの対象だった。**正本を変えずに済むこの形へ改めた**。

### 1-4. 全 45 表の割り当て(母集合 = `contracts/db/schema-manifest.json`)

**`tenant_owned`(24 表)** — `direct`:

`team_records` / `players` / `games` / `lineup_memories` / `game_lineups` / `participation_intervals` /
`tournament_rule_assignments` / `event_slots` / `operation_events` / `play_rows` / `play_runners` /
`temporary_player_id_mappings` / `idempotency_ledger` / `rejected_event_originals` / `evacuated_event_originals` /
`recording_generations` / `medical_notes` / `medical_note_versions` / `pdf_export_records` / `tenant_vocabularies` /
`player_merge_events` / `player_move_records` / `invalidation_intents` / `migrated_final_lineups`

- 追記専用の表(`operation_events` など)も、ACL は正本どおり `SELECT` / `INSERT` / `UPDATE` にする(`data-model.md:209`)。変更の禁止は migration のトリガが担う
- `invalidation_intents` は、`T7` と同じトランザクションで要求元テナントの文脈から書く(`data-model.md:2147`)

**`self_tenant_row`(1 表)**: `tenants` — `direct`(`SELECT` のみ)。書き込みは管理経路(**U-A2**)の関数。

**`effective_group_control`(4 表)**: `analysis_groups` / `group_memberships` / `sharing_grants` / `group_invitations` — 読み取りは `direct`(`SELECT` のみ)、書き込みは **U-C1** の管理関数。

**`global_read_only`(5 表)**: `rule_sets` / `game_type_rule_defaults` / `system_vocabularies` / `admin_vocabularies` / `system_settings` — `direct`(`SELECT` のみ)。書き込みは **U-A2** の関数。

**`function_only`(11 表)**:

| 表 | `access_path.reason` | 所有単位 |
| --- | --- | --- |
| `tenant_auth_subjects` / `tenant_credentials` / `tenant_tokens` | `pre_context_authentication`(1-2) | U-A1 |
| `rate_limit_counters` | `pre_context_global_mutable`(1-2) | U-A1 |
| `admin_credentials` / `admin_sessions` / `admin_operation_logs` | `admin_path`(`data-model.md:1543`) | U-A2 |
| `migration_runs` / `migration_quarantine` / `migration_resolution_reports` / `migration_warning_reports` | `migration_batch_only`(8 節) | 移行バッチ用ロール(TSK-349) |

合計は 24 + 1 + 4 + 5 + 11 = **45**。

### 1-5. 表分類の合格述語 — 分類資産から期待値を導かない

**分類資産そのものを正解にすると、誤った割り当てで自己充足する**。例: `admin_credentials` を `global_read_only` に移すと、DDL も実 DB 試験もその分類から期待値を導くので、全部 green になる。

→ 期待値を**分類資産の外**に 2 系統置く。

1. **固定 oracle**: 1-4 の割り当て表を、**検査器から独立した機械可読の凍結資産** `contracts/authz/product/table-classification.oracle.json` に置く。分類資産はこの oracle と exact-map で一致しなければ red。
   - **設計書 7.7 に従う**: oracle は凍結基準である。**検査器のソースには値を直書きしない**(7.7-1)。oracle を動かすときは、**追記のみの履歴**(新旧の識別値・変えた表とその前後のプロファイル・事実・理由・承認者・承認日 — 7.7-2)を oracle 自身に残す。履歴を確かめられないときは不合格(7.7-3)
   - **履歴なしの変更を、比較元の ref を使わずに検出する**: 履歴の各項目は、その変更の後の割り当て全体の digest と、**直前の項目の digest**(鎖)を持つ。**現在の割り当ての digest が、履歴の最後の項目の digest と一致しなければ red**。比較元を資産や CI の引数に頼らないので、TSK-431 の 7A(比較元の自己申告)の形の穴を作らない
   - 検査: 分類資産だけを変える変異で red(oracle と不一致)/ **oracle だけを履歴なしで変える変異で red**(digest 不一致)/ oracle と分類資産を両方変え、履歴を足さない変異で red / 履歴の途中の項目を消す・書き換える変異で red(鎖が切れる)。**末尾の項目を消して割り当ても戻す操作は、比較元なしでは検出できない**(直前の承認済み状態へ戻るだけで、誤分類は通せない)。この限界を残余として記録する
   - これで、誤分類を通すには「oracle の履歴に承認者と理由を書く」ことが必要になり、レビューで必ず見える(7.7-4 のとおり、承認の真正性そのものは保証しない)
   - 【2 周目 2-P0-1】旧案は oracle を試験モジュールの定数として持ち、7.7-1 の直書き禁止に反していた
2. **意味の不変条件**(manifest の事実から導く。分類資産を見ない):
   - `tenant_id` 列を持たない表は `tenant_owned` にできない
   - **秘密の列を持つ表は `function_only` でなければならない**。秘密の列は閉じた列挙で持つ(`password_hash` / `code_hash` など — manifest を走査して列挙を確定する)
   - `global_read_only` にできるのは、`tenant_id` 列を持たず、かつ秘密の列を持たない表だけ
   - `effective_group_control` にできるのは、manifest で `cross_tenant: true` の FK を持つか、その参照先である表だけ
   - `function_only` の表は `access_path.reason` と所有単位(閉じた列挙: `U-A1` / `U-A2` / `U-C1` / `U-C2` / `migration_batch`)が必須

**変異**(すべて red): `admin_credentials → global_read_only` / `tenant_auth_subjects → tenant_owned` / 制御資源の表 → `tenant_owned` / 表を 1 つ未割り当てにする / モデルを 1 つ足す / 秘密の列の列挙から 1 つ消す。

【1 周目 1-P0-2】旧案は分類資産だけを正解にしていた。

## 2. 製品ロール

正本の 5 ロール(`data-model.md:206-212`)を、次の形で資産に置く。**パスワードは資産に書かない**(NFR-014)。

| ロール | 資産上の名前 | 属性 | 作る主体 |
| --- | --- | --- | --- |
| マイグレーション用(表の所有者・**DB の所有者**) | `pitchlog_owner` | `LOGIN` / `NOSUPERUSER` / `NOBYPASSRLS` / `NOCREATEROLE` / `NOCREATEDB` | **外部の手順**(試験では fixture)。資産には期待属性を宣言し、カタログ検査の対象にする |
| アプリ用 | `pitchlog_app`(U-T1 の暫定名 `runtime_contract.py:26` を踏襲) | `LOGIN` / `NOSUPERUSER` / `NOBYPASSRLS` / `NOCREATEROLE` / `NOCREATEDB` / `NOREPLICATION` / `NOINHERIT` | 製品 DDL |
| 共有関数所有用 | `pitchlog_shared_fn_owner` | `NOLOGIN` / `BYPASSRLS` | 製品 DDL。**所有する関数は補助関数 1 つ**(1-3) |
| 管理関数所有用 | `pitchlog_management_fn_owner` | `NOLOGIN` / `BYPASSRLS` | 製品 DDL。**所有する関数は 0 件** |
| 移行バッチ用 | `pitchlog_migration_batch` | `LOGIN` / `BYPASSRLS`・**期間限定・`VALID UNTIL`** | **定常の資産には含めない**。ライフサイクル資産(8 節)だけが有効化する |

### 2-1. DB と `public` スキーマの所有

PostgreSQL 17 では、`public` スキーマは `pg_database_owner` が所有し、DB の所有者がそれを管理する。

→ **DB の所有者を `pitchlog_owner` にする**(`CREATE DATABASE ... OWNER pitchlog_owner` — 外部の手順)。
`pitchlog_owner` は `public` に表と関数を作れる(migration)。
製品 DDL は、`public` の `CREATE` を `PUBLIC` から明示的に剥奪し、`pitchlog_app` に `USAGE` だけを与える。
**DB・スキーマの所有者と、スキーマの ACL の最終状態を exact-set で検査する**。

【1 周目 1-P1-2】旧案は DB とスキーマの所有者が未定義で、マイグレーション用ロールを `NOLOGIN` としながら「その権限で接続する」と書いていた。

### 2-2. ロールの membership — `ADMIN OPTION` まで検査する

`pg_auth_members` の 3 つの option(`admin_option` / `set_option` / `inherit_option`)を、**辺ごとに exact-set で検査する**。

- **製品ロール(`pitchlog_app`・関数所有ロール・`pitchlog_owner`)から出る辺は 0 本**。`SET` / `INHERIT` / `ADMIN` の**どの option も持たない**。`ADMIN OPTION` だけの辺でも、自分へ membership を付け直せば `SET ROLE` できるので、**`ADMIN` だけを残す変異で red** にする
- **provisioner は外部の特権主体として宣言する**(probe の `external_provisioner` と同じ位置づけ)。ロールを作り、再適用し、退役させるのが provisioner の仕事なので、**製品ロールへの `ADMIN OPTION` の辺を持つ**。これを隠さず、**資産に「恒久の特権主体と、その辺の集合」として宣言し、exact-set で検査する**:
  - provisioner から各製品ロールへの辺は **`ADMIN` のみ(`SET` と `INHERIT` は偽)**
  - **provisioner へ入る辺は 0 本**(どの製品ロールからも provisioner に到達できない)
  - `SET` / `INHERIT` の辺は、適用のトランザクションの中だけに存在する一時の辺で、commit 後に残れば red
- 危険ロールの定義は `rolsuper` ∨ `rolbypassrls` ∨ 保護対象の所有者。**「恒久の特権主体」の許可集合を資産に宣言し、LOGIN できる危険ロールの集合がこの許可集合と exact-set で一致すること**を検査する(使い捨てクラスタでは bootstrap の superuser と provisioner)
- probe の適用器は `SET` と `INHERIT` だけを剥奪し、`ADMIN` を残している(`backend/src/pitchlog/authz/provisioning.py:627`)。製品では、その `ADMIN` の辺を**宣言された恒久の辺**として扱い、宣言に無い `ADMIN` の辺を red にする

【2 周目 2-P1-5 の一部】旧案の「provisioner からの辺も 0 本」は、再適用(4-3)と両立しなかった。

【1 周目 1-P0-4】

## 3. 製品 authz DDL 資産の形と置き場

### 3-1. 置き場と段階

```
contracts/authz/product/table-classification.json        全 45 表の物理プロファイルと到達経路(1 節)
contracts/authz/product/ddl-elements.staged.json          製品 DDL 要素(PR A の間の置き場。3-2)
contracts/authz/product/function-bodies/                  製品側の SQL 本体と manifest.json
contracts/authz/product/probe-product-map.json            probe 原子要素 ↔ 製品原子要素(7 節)
contracts/authz/product/migration-batch-lifecycle.json    移行バッチ用ロールのライフサイクル(8 節)
```

- **probe 資産(`contracts/authz/` 直下)は 1 バイトも触らない**(封印 — `contracts/authz/oracle-seal.lock.json:40-88`)
- すべて `contracts/authz/*` に一致し、コア領域に入る(`.claude/core-areas.json:295`)
- `ddl-elements.staged.json` の scope は `{"status": "product_configuration", "product_schema": true, ...}`。**probe の scope 値と重ならない閉じた値**にする

### 3-2. PR A の間は「未発効」の第三状態として置き、その状態自体を検査する

U-T1 の二状態テストは、**`contracts/authz/product/ddl-elements.json` が存在するかどうかだけ**で状態を切り替える(`backend/tests/test_authz_runtime_contract.py:65-84`)。
存在すると、暫定資産が残っていること・生成物が暫定のままであることが即座に違反になる(同 `:127-156`)。
暫定資産の削除は TSK-431 を待つ(9 節)ので、PR A の間に最終パスへ置くと、既存テストが red になる。

→ PR A では `ddl-elements.staged.json` に置く。**ただし、名前を変えて検査を避けるだけにはしない**。
「製品資産はあるが、まだ発効していない」という第三状態を**明示し、新しい試験で検査する**(既存の `test_authz_runtime_contract.py` は変えない):

| 状態 | 条件 | 検査(新設 `backend/tests/test_authz_product_staging.py`) |
| --- | --- | --- |
| 暫定 | staged 無し ∧ 最終無し | 既存の二状態テストのとおり |
| **未発効(PR A の後)** | **staged 有り ∧ 最終無し** | ランタイムは暫定のまま(`PROVISIONAL = True`)。**staged 資産の宣言 `pending_switch` が、切り替えを行うタスクの ID を持つ**。staged 資産から導いた保護対象が、**暫定資産の保護対象 ∪ 宣言済みの追加分**(`authz_private` スキーマと補助関数 1 個)と exact-set で一致する(切り替え時に保護対象が黙って変わらない) |
| 製品 | staged 無し ∧ 最終有り | 既存の二状態テストのとおり(PR B の後) |
| **不正** | **staged 有り ∧ 最終有り** | **red**(二重の正本) |

- **正本 12-8 には、PR A の段階を「資産は確定・未発効(ランタイム契約の切り替えは PR B のタスク)」と書く。「landed」とは書かない**。TSK-424 の Notion カードも、PR B のマージまで完了にしない
- **PR B で `git mv` により最終パスへ移し、`runtime_contract` を足し、暫定資産を削除する**。資産指定オブジェクト(5 節)がパスを持つので、移動は spec の 1 行の変更で済む

【1 周目 1-P1-1・2 周目 2-P0-2】

### 3-3. ポリシーの本体

- **表ごとにポリシーを 1 本の SQL ファイルで持つ**(`function-bodies/policies/POLICY:<table>:<profile>.sql`)
- `tenant_owned` 24 表ぶんの同じ述語は、**1 つの述語要素から生成器が展開する**(probe の `predicates/` と同じ仕組み)。**展開結果を資産として固定**し、生成器が壊れたら digest の差分で red にする
- `tenant_owned` のポリシーは `FOR ALL TO pitchlog_app`。`DELETE` は ACL が無いので `42501` になる

### 3-4. migration が作る関数の ACL

migration は `public` にトリガ関数を 33 個作る(`runtime_contract.py:85-119`)。PostgreSQL は関数の既定の `EXECUTE` を `PUBLIC` に与える。

- **33 個すべてから `PUBLIC` の `EXECUTE` を剥奪する**。`CREATE TRIGGER` の時点では関数の `EXECUTE` が要るが、**発火時には見ない**。migration は `pitchlog_owner` で作るので、所有者の `EXECUTE` は残り、再作成(downgrade → upgrade)にも支障が無い
- **剥奪後もトリガが発火すること**を実 DB 試験で表明する(アプリ用ロールの書き込みで、追記専用表のトリガが拒否を返す)
- **33 個が `SECURITY INVOKER` であること**をカタログ検査で表明する。`SECURITY DEFINER` の関数が migration に紛れたら red
- 関数 ACL の exact-set = 33 個 + 補助関数 1 個(1-3)

## 4. 適用経路

### 4-1. 順序

**migration の外で、migration の後に適用する**(裁定 A-2・`D7`)。

1. 使い捨てクラスタを作る(`backend/tests/db_fixtures.py:555-615` と同じ形)。クラスタの初期管理ユーザー(superuser)は **bootstrap にだけ使う**
2. bootstrap: superuser が **provisioner**(`LOGIN` + `CREATEROLE`・superuser ではない)を作る。provisioner が `pitchlog_owner` を作る。superuser が DB を `OWNER pitchlog_owner` で作る(2-1)。**以後、superuser は使わない**
3. `pitchlog_owner` で接続して `alembic upgrade head`
4. provisioner で接続して**製品 authz DDL を適用する**(4-2)
5. カタログ検査と実 DB 試験(6 節)

### 4-2. 1 トランザクションで適用する

probe の適用器は、手順ごとに commit している(`backend/src/pitchlog/authz/provisioning.py:491` ほか 4 箇所)。
これは probe が表そのものを作るためだった。**製品の適用対象は migration が作った既存の表**なので、この制約が無い。

→ **製品の適用は、ロールの作成を含めて全体を 1 トランザクションで行う**。

- provisioner は **superuser ではない**(probe の provisioner と同じ `LOGIN` + `CREATEROLE` — `contracts/authz/ddl-elements.json:39`)。superuser で試すと、権限の欠落が隠れるため
- 表の所有者でないと `ALTER TABLE` も `CREATE POLICY` もできない。provisioner は**トランザクションの中で `SET LOCAL ROLE`** を使う。**`SET LOCAL` は commit / rollback で必ず戻る**。通常の `SET ROLE` は commit 後もセッションに残るので使わない
- **1 トランザクションの中の順序を固定する**(`pitchlog_owner` は `NOCREATEROLE` なので、その権限のままでは membership を回収できない):
  1. ロールを作る。**PostgreSQL 16 以降、superuser でない作成者には、作ったロールへの `ADMIN OPTION` つき membership が自動で付く**。これが 2-2 で宣言する恒久の `ADMIN` の辺になる
  2. 一時の辺を張る: `GRANT pitchlog_owner TO provisioner WITH SET TRUE, INHERIT FALSE, ADMIN FALSE`。補助関数とスキーマの所有者を移すため、`pitchlog_shared_fn_owner` にも同じ形の辺を張る(**一時の辺は資産に列挙した 2 本だけ**)
  3. `SET LOCAL ROLE pitchlog_owner` → 表の `ENABLE` / `FORCE`・ポリシー・表 ACL・トリガ関数の `PUBLIC` 剥奪
  4. `RESET ROLE`
  5. 補助関数とスキーマの作成と所有者の移動(`pitchlog_shared_fn_owner` へ)・関数 ACL
  6. **一時の辺の `SET` を外す**(`REVOKE SET OPTION FOR ...`)。provisioner に残るのは、2-2 で宣言した `ADMIN` のみの辺だけ
- **commit 後と rollback 後の両方**で、同じ接続の `current_user = session_user = provisioner` を検査する(`backend/src/pitchlog/db/engine.py:138` と同じ観点)。**適用後の `pg_auth_members` が、2-2 の宣言と exact-set で一致する**
- 【2 周目 2-P1-6】旧案は `RESET ROLE` の位置と一時の辺の列挙が無かった
- **commit 後と rollback 後の両方**で、同じ接続の `current_user = session_user = provisioner` を検査する(`backend/src/pitchlog/db/engine.py:138` と同じ観点)
- **失敗点**(R-5 と、ロール切り替えの前後): ロール作成の直後 / `SET LOCAL ROLE` の直後 / ポリシー作成の直後 / ACL 正規化の途中 / `RESET ROLE` の直後 / membership の `REVOKE` の直前。**どこで失敗しても、カタログが適用前と 1 要素も変わらない**
- **変異**: `SET LOCAL ROLE` を `SET ROLE` に変えると red(commit 後の `current_user` 検査で落ちる)/ `RESET ROLE` を省くと red / 一時の辺の `SET` を 1 本残すと red / 宣言に無い `ADMIN` の辺を 1 本足すと red / 製品ロールから出る辺を 1 本足すと red

【1 周目 1-P0-3】

### 4-3. 再適用と migration の往復

- **二重適用**: 製品 DDL を 2 回適用しても、2 回目の後のカタログが 1 回目と同じになる(収束する)
- **往復**: 製品 DDL の適用 → `alembic downgrade base` → `alembic upgrade head` → 製品 DDL の再適用。**再適用後のカタログが、初回の適用後と一致する**
- **往復の途中(再 upgrade の直後)は、表に RLS もポリシーも無い**。この区間を non-serving として扱う運用契約(authz の適用が済むまで、アプリ用ロールの接続を受けない)は、**実環境の手順を持つ TSK-344 へ申し送る**
- 既存の往復試験(`backend/tests/db/test_migration_round_trip.py:53`)は変えない。製品 DDL を含む往復は別の試験として足す

【1 周目 1-P1-3】

### 4-4. 適用器の操作種別

probe の適用器は、操作種別を閉じた 5 種で振り分けている(`provisioning.py:19-29`)。
**製品の操作種別は別の閉じた集合**として、資産指定オブジェクト(5 節)に持たせる。
**probe の 5 種に製品の種別を足して 1 つの集合にはしない**(probe の資産で製品の操作が通る経路を作らないため)。

## 5. ツールチェーンの一般化

U-T1 design 3-3(`:263-284`)の方針を引き継ぐ。**資産指定オブジェクト**(`AuthzAssetSpec`)を導入し、次の値を束ねる:

- 資産ルート・要素ファイル・body manifest・body ディレクトリ
- **許可する scope の値**(probe = `verified_probe_configuration` / 製品 = `product_configuration`)
- **操作種別の閉じた集合**と、その処理関数の対応(4-4)
- 資産の種類(`probe` / `product`)

| 部品 | 差し替え点(research.md 4-3) | 方針 |
| --- | --- | --- |
| 生成器 `ddl.py` | `DDL_ELEMENTS_PATH` ほか 3 定数・`generate_authz_ddl(root)` | `generate_authz_ddl(root, spec=PROBE_SPEC)`。**`ddl.py` に SQL 断片も資産識別子のリテラルも書かない**(`backend/tests/test_authz_ddl.py:181`) |
| body 検査器 | `BODY_DIRECTORY` / `DDL_ELEMENTS_PATH` / `ELEMENT_SECTIONS` | CLI に `--asset-spec probe\|product` を足す。既定は `probe` |
| 適用器 | `apply_authz_ddl(connection, root)` | `apply_authz_ddl(connection, root, spec=PROBE_SPEC)`。製品は 4-2 の形 |
| DB カタログ検査 | `inspect_authz_catalog` が `DDL_ELEMENTS_PATH` を import | spec を受け取る |
| 静的検査 `check_authz_catalog.py` | `_validate_ddl_scope` が probe の scope 以外を拒否(`:2786-2806`) | **scope の許可値を spec から受け取る**。probe 固有の閉じた検査は **probe spec のときだけ**走らせる |
| DB fixture | `_load_ddl_asset` / `provisioned_catalog` | 製品用の `provisioned_product_catalog` を**新設**。既存の fixture の振る舞いは変えない |

**許容する既存ファイルの差分**(1 周目 1-P1-4 の是正 — 旧案の「既存テストのファイル差分 0 行」は、fixture を変える計画と両立しなかった):

- **既存の `test_*.py` は差分 0 行**
- 変えてよい既存ファイルは、上表の 6 部品と `backend/tests/db_fixtures.py`・`backend/tests/db/conftest.py`(再エクスポートを足すだけ)に限る。**各ステップの合格条件に、そのステップで変える既存ファイルを列挙する**
- **既定値を probe にして、既存テストを無改変で green に保つ**
- **spec の取り違えを red にする**負例: 製品資産を probe spec で読むと scope 不一致で拒否、その逆も同じ。**「probe で試験して green にする」抜け道**を塞ぐ(U-T1 design `:280-281`)

## 6. 実 DB 試験

使い捨てクラスタに migration と製品 DDL を適用し、**2 テナント分の行**を置いて試験する。
**試験の期待値は、1-5 の固定 oracle から導く**(分類資産から導かない)。表名は試験側に直書きせず、oracle からパラメタ化して生成する。

### 6-1. `tenant_owned`(24 表すべて。代表の表だけで済ませない)

| 観点 | 期待 |
| --- | --- |
| **最低要求 ①**(`data-model.md:2530`)— 関数を経由せず他テナントの行を読む | 0 行 |
| `WITH CHECK` — 他テナントの `tenant_id` で `INSERT` / `tenant_id` を書き換える `UPDATE` | `42501` |
| 未束縛で読む | 0 行 |
| 不正 UUID の束縛 | `22P02` |
| `DELETE` | `42501` |

### 6-2. その他のプロファイル

| 観点 | 期待 |
| --- | --- |
| `self_tenant_row`: 自テナントの行 / 他テナントの行 / `UPDATE` | 1 行 / 0 行 / `42501` |
| `global_read_only`: `SELECT` / `INSERT` | 読める / `42501` |
| `function_only` 11 表: `SELECT` | **`42501`(0 行ではない** — U-T1 design `:148-150`) |
| `effective_group_control`: 正負行列(U-T1 design 9 節 #4) | 下表 |

**`effective_group_control` の正負行列**(4 表 × 状態):

| 要求元テナントの状態 | `analysis_groups` / `group_memberships` / `sharing_grants` | `group_invitations` |
| --- | --- | --- |
| 実効参加・`member` | 見える | 見えない |
| 実効参加・`admin` | 見える | 見える |
| 非参加 | 見えない | 見えない |
| 参加行が離脱 | 見えない | 見えない |
| **グループが終了** | **見えない**(1-3 の是正点) | 見えない |
| **参加テナントが無効化**(参加行は `active` のまま) | **見えない**(`data-model.md:111-118`) | 見えない |
| 存在しないグループ ID を補助関数に渡す | `false`(非参加と区別できない) | — |

### 6-3. 横断の観点

| 観点 | 期待 |
| --- | --- |
| トリガ関数 | `PUBLIC` 剥奪後も、アプリ用ロールの書き込みでトリガが発火する |
| FORCE | `pitchlog_owner` で接続しても、ポリシーに従う(未束縛で 0 行) |
| 危険終点(R-2・2-2) | `pitchlog_app` から `SET` / `INHERIT` / `ADMIN` で到達できるロールと、危険ロールの交差が空 |
| **最低要求 ②** | `PUBLIC`(と、`pitchlog_app` 以外のロール)が補助関数を `EXECUTE` できない |
| **最低要求 ③** | `pitchlog_app` の一時スキーマに補助関数の参照先と同名の表を作っても、補助関数の結果が変わらない |
| 最低要求 ④ | 対象(共有集計の越境関数)が本単位に無い。**`pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が、補助関数 1 個だけ**であることを表明する。各単位が関数を足すと red になり、④ の試験を足すよう促す |

**変異**(すべて red): 1 表のポリシーを外す / `FORCE` を外す / `WITH CHECK` を `true` にする / `function_only` の表に `SELECT` を与える / 補助関数から「実効グループ」の条件を外す / 補助関数から「参加テナントが有効」の条件を外す / 補助関数の `search_path` から `pg_temp` の明示を外す / 補助関数を `PUBLIC` に `EXECUTE` させる。

## 7. probe ↔ 製品の写像

U-T1 design 2-1(`:76-95`)を引き継ぐ。

- 原子要素は `role` / `schema` / `table` / `policy` / `function` / `acl_privilege`
- 合格条件: **`probe の全原子要素 = mapped ∪ explicit_non_mapping`**、かつ **`製品の全原子要素 = mapped の像 ∪ product_only`**。両方向とも exact-set
- **理由コードは閉じた列挙**。種別ごとに使えるコードを固定する:

| コード | 使える原子要素の種別 | 意味 |
| --- | --- | --- |
| `test_only_role` | role | 試験専用(`outsider_role` / `management_caller`) |
| `external_provisioner` | role | 外部の手順が用意する(`provisioner`) |
| `deferred_to_owning_unit` | function / acl_privilege | 所有単位が足す(`owner_unit` 必須: U-C1 / U-C2 / U-C3 / U-A2) |
| `forbidden_by_canon` | acl_privilege | 正本が禁じる(`app_role` の `DELETE` — `data-model.md:209`) |
| `probe_schema_only` | schema / table / policy | probe 専用の器(`probe_data` / `probe_business_rows` など) |
| `product_only` | 製品側の全種別 | probe に対応物が無い製品要素(45 表・トリガ関数 33 個・補助関数など) |

- `read_control_resources`(`contracts/authz/ddl-elements.json:353`)は `deferred_to_owning_unit` / `owner_unit: U-C2`
- **写像資産を正とし、TSK-250 の予告資産 `scripts/design_relations/product-ddl-map-data-model.json` は本資産から導出する**。TSK-250 の計画書(`../data-model-canonical/plan.md:253`)への申し送りを、PR 本文と Notion に記録する

## 8. 移行バッチ用ロール — 本単位は「形」と「定常の不変条件」まで

**人間の判断(2026-09-24)**: ライフサイクルの**実行**(有効化・投入・退役の手順、接続の監査、孤児の回収、同時実行の制御)は、**移行実行器と一体の設計なので TSK-349 が持つ**。
U-T1 design 2-5 が「持ち主がいない」として本単位へ引き取った経緯(`../tenant-boundary-enforcement/design.md:217-221`)は、TSK-349 が実在する持ち主になったことで解消した。

本単位が持つのは次の 3 つで、**TSK-349 はこれを入力として使う**:

| 本単位が持つもの | 内容 |
| --- | --- |
| **(a) 書き込み先の資産** | `contracts/authz/product/migration-batch-role.json` の `write_targets`(8-1) |
| **(b) 有効化したときの形** | ロールが有効な間に満たすべきカタログ状態(8-2)。使い捨てクラスタで、資産どおりに作ったロールがその形を満たすことを検査する |
| **(c) 定常の不変条件** | 移行を行っていない定常状態の条件(8-3)。カタログ検査に入れ、TSK-344 の実スキーマの再実行でも同じ検査が走る |

### 8-1. 書き込み先は導出集合と完全に一致させる

- **書き込み先 = `contracts/db/schema-manifest.json` で `import_batch_id` 列を持つ表 ∪ `migration_runs`**(実測で 19 表 — research.md 5 節)
- **例外は置かない**。`write_targets` は、この導出集合と **exact-set**(表 ID と権限の組)で一致しなければ red
- 権限は `SELECT` / `INSERT` / `UPDATE` に限る。**`DELETE` / `TRUNCATE` / `REFERENCES` / `TRIGGER` を足す変異で red**
- **監査の表(`admin_operation_logs`)は含めない**。監査を書くのは移行実行器の管理接続であり、その設計は TSK-349 が持つ

**正本とスキーマの食い違い**(本単位では直さない — TSK-349 へ申し送る):
正本 12-3 の不変条件 1 は「**移行が作る行はすべて取り込みバッチ識別子を持つ**」と定める(`data-model.md:2367`)。
ところが `event_slots` は取り込みバッチ識別子を持たない(`contracts/db/schema-manifest.json:287-298`)。それなのに `operation_events` は `event_slots` を FK で参照する(`:340`)。
**移行が `operation_events` を作るなら `event_slots` の行も作る必要があり、そうすると不変条件 1 を破る**。
`medical_note_versions` も識別子を持たないが、移行がこの表に行を作るかどうかは正本から読み取れない。
→ 本単位は正本どおりの導出集合で閉じる。**この食い違いが解けるまで、実際の移行は `operation_events` を書けない**。書き込み先を広げるのは、食い違いが解けた後に、本資産の改訂として行う。

### 8-2. 有効化したときの形

資産 `migration-batch-role.json` に、有効な間のロールの形を宣言する。**名前は固定しない**(同時実行の制御は TSK-349 の射程なので、名前の付け方も TSK-349 が決める)。
本単位は、**資産どおりに作ったロールが次を満たすこと**を使い捨てクラスタで検査する:

| 正本の条件(`data-model.md:290-297`) | 有効な間の形 |
| --- | --- |
| アプリから到達しない | `pitchlog_app`・関数所有ロール・`pitchlog_owner` から、`SET` / `INHERIT` / `ADMIN` のどの辺でも到達しない。**このロールから出る辺も 0 本** |
| DDL を持たない | `pg_class.relowner` / `pg_proc.proowner` / `pg_namespace.nspowner` / `pg_database.datdba` のどれにも現れない |
| 書き込み先の限定 | 表 ACL が `write_targets` と exact-set。スキーマの ACL は `public` の `USAGE` のみ |
| (属性) | `LOGIN` / `BYPASSRLS` / `NOSUPERUSER` / `NOCREATEROLE` / `NOCREATEDB` / `NOREPLICATION` |

**本単位が検査しないもの**(TSK-349 へ): 期間限定(退役の手順・資格情報の寿命)/ 監査(接続単位の記録と、投入結果との一対一対応)/ 孤児の回収 / 同時実行 / 投入の途中で止まったときの状態の収束。

### 8-3. 定常の不変条件

**移行を行っていない定常状態**では、次が成り立つ。**カタログ検査に入れ、成り立たなければ不合格**(fail-closed):

- 資産の形(8-2)をもつロール — **`BYPASSRLS` を持つ `LOGIN` のロールのうち、恒久の特権主体として宣言されていないもの** — が **0 件**
- 恒久の特権主体の許可集合(2-2)は資産に宣言する。**大域の「`LOGIN` + `BYPASSRLS` が 0 件」とはしない**(正当な provisioner を誤検出するため)

TSK-349 は、移行の区間の前後でこの検査が合格すること(区間の外にロールが残っていないこと)を、自分の合格条件に使う。

### 8-4. TSK-349 への申し送り(契約の要求事項)

2 周目のレビューで出た次の要求を、**TSK-349 の設計の入力**として渡す(Notion と PR 本文に記録する):

| 要求 | 出所 |
| --- | --- |
| 退役は、`NOLOGIN NOBYPASSRLS` への硬化と commit → 対象ロールの全 backend の終了と `pg_stat_activity` での 0 件の確認 → `write_targets` とスキーマの `REVOKE` → `DROP ROLE` の順。**ACL の依存が残ると `DROP ROLE` は失敗する** | 2-P0-4・2-P0-5 |
| `VALID UNTIL` はパスワード認証の期限にすぎず、成立済みの接続を切らない。資格情報の生成・引き渡し・破棄を NFR-014 に沿って定める | 2-P0-5 |
| 接続の監査は、run ID・バッチ ID・ロール名・`pg_backend_pid()`・`backend_start`・接続の開始と終了・投入の開始と commit と失敗を固定の形で記録し、実行器が作った接続と一対一で対応させる | 2-P0-6 |
| 監査を書く管理主体の属性と権限を宣言する。**superuser でない属性で試験する** | 2-P1-2 |
| 投入の commit 後に止まったときは、`migration_runs` の永続状態から、成功の補完・バッチの論理退役・公開禁止のいずれかへ一意に収束させる | 2-P1-3 |
| 同時実行: run ID ごとの一意なロール名か、クラスタの advisory lock と一意な active-run 制約 | 2-P1-4 |
| 孤児の検出は、run ID から作ったロールの OID を記録し、そのロールの不存在または完全な硬化を直接検査する(本単位の 8-3 は、その外側の網) | 2-P1-5 |
| `event_slots` の取り込みバッチ識別子の欠落(8-1) | 1-P0-7 |
| **FR-038 の移行実行器が、本単位の `migration-batch-role.json` を読んで書き込み先と形を決めること**を、TSK-349 の合格条件にする | 1-P1-6 |

TSK-349 の旧 DoD のうち「凍結 probe 資産への追加と `--reseal-oracle`」は採らない(probe と製品は別の層 — `data-model.md:537`)。

【1 周目 1-P0-5〜7・1-P1-6・2 周目 2-P0-4〜6・2-P1-2〜5】

## 9. ランタイム契約の切り替え(PR B — 本計画の外)

**PR A(本計画)はランタイム契約を切り替えない**。切り替えは、TSK-431 のマージ後に**別のタスク・別のブランチ・別の計画書**で行う(plan.md 2 節)。PR B が行う内容を、ここに契約として固定する:

1. `contracts/authz/product/ddl-elements.staged.json` を `git mv` で `contracts/authz/product/ddl-elements.json` へ移し、`runtime_contract` オブジェクト(8 フィールド)を足す。値は製品資産から導出する
2. 生成器で `backend/src/pitchlog/authz/runtime_contract.py` を作り直す(`PROVISIONAL = False` / `SOURCE_ASSET` = 製品資産 / `SUPERSEDED_BY = None`)
3. 暫定資産 `contracts/tenant_boundary/runtime-authz-contract.json` を削除する。設計書 7.7-1(値をソースに残さない)・7.7-2(削除の記録を追記のみで残す)に従う
4. 削除記録では、暫定資産の履歴にある `PENDING_ACCEPTANCE` と「未承認(PR #72 のレビュー待ち)」を**変更前の値としてそのまま**記録する。事実として「PR #72 のマージ後も受理値へ更新されていなかった」と書く。**値を書き換えてから削除することはしない**

**TSK-431 を待つ理由**: 暫定資産の削除は、凍結基準を動かす行為である(7.7-1)。削除記録を検査する機構が無い(既知欠陥 **7D**)。**7D を開けたまま削除はしない**。

【1 周目 1-P1-5】


## 10. capability — 「記述」は本単位が出し、「登録」は各単位が行う

U-T1 は、**製品の capability を TSK-424 の出力契約に含める**と定めている(`../tenant-boundary-enforcement/design.md:321`・`:421`)。

→ capability を 2 つに分ける:

| | 内容 | 持ち主 |
| --- | --- | --- |
| **capability の記述**(カタログ) | 表分類から導いた、**開けてよい操作の閉じた一覧**。`contracts/authz/product/capability-catalog.json` に置く。1 行 = (capability ID, 表 ID, 操作種別 `read` / `insert` / `update`)。**`direct` の表だけ**が載る。`effective_group_control` の表は `read` だけ。`function_only` の表は 1 つも載らない | **本単位** |
| **capability の登録**(公開 registry) | `PRODUCT_CAPABILITY_IDS` などへ登録して、実際に操作を開くこと(`backend/src/pitchlog/repositories/repository_contract.py:57-59`) | **経路を持つ単位**(U-01・U-M1・U-D1 ほか)。本単位は空のまま残す |

- カタログは表分類から**生成器で導出**し、導出結果と資産の一致を検査する(手で書かない)
- **登録できるのは、カタログに載っている capability だけ**にする検査を本単位で置く。カタログに無い capability を登録する変異で red(`function_only` の表を対象にしたもの・`effective_group_control` の表への書き込みを含む)
- 検査は**試験の中だけで仮の登録を作って確かめる**。製品のパッケージには登録しない
- U-T1 の「順序依存は 1 点だけ」(`../tenant-boundary-enforcement/plan.md:113-118`)とは矛盾しない。U-T1 が待っていたのは期待ロール名と保護対象(9 節)である

【2 周目 2-P0-3】旧案は capability を一切出さず、U-T1 の出力契約と矛盾していた。

## 11. 正本の追随(PR A に含める)

| 箇所 | 変更 | ゲート |
| --- | --- | --- |
| `data-model.md` 12-8(`:2844-2846`) | TSK-317 行を**分割**する。製品の RLS・ロール DDL・表分類・capability カタログ・移行ロールの形と定常の不変条件 = TSK-424(**PR A で資産は確定・未発効**。「landed」とは書かない — 3-2)/ 移行ロールのライフサイクルの実行 = TSK-349(残件)/ 越境関数と最低要求 ②③④ の残り = U-C1 / U-C2 / U-C3 / U-A2(残件)/ 実スキーマでの再実行 = TSK-344(残件)/ ランタイム契約の切り替え = PR B のタスク(残件)。**「解消済み」にしない** | 7.6-3 前段(実装追随の節更新)→ PR レビュー |
| `data-model.md` 変更履歴 | 上を 1 行で追記する。版は上げない | 同上 |
| `docs/README.md` | 索引の現行化 | 同上 |

- **3-2 節 `:296` の監査根拠(NFR-012)は直さない**。これは実装追随ではなく、approved の正本に既にある典拠の誤りである。直すには確定ゲートか、人間による省略の判断が要る。**本単位では直さず、専用の Notion タスクを承認後に起票して申し送る**(起票したタスク ID を 12-8 の残件と plan.md の DoD に記録する。確定ゲートの要否はそのタスクで判定する)【1 周目 1-P1-7・2 周目 2-P2-2】
- **12-6 の受け取り先表(`:2719`・`:2725`)は変えない**。TSK-382 が扱う 3 箇所の 1 つだからである
- **3-5 節の述語は変えない**。本単位はその述語を、補助関数を使ったポリシーとして実装する(1-3)

## 12. 他タスクとの境界

| タスク | 境界 |
| --- | --- |
| **TSK-344** | 本単位 = 使い捨てクラスタで作成・初回実行 / TSK-344 = 実スキーマで再実行(`data-model.md:2846`)。4-3 の non-serving 区間の運用契約と、8-3 の定常の不変条件(カタログ検査に含まれる)を申し送る |
| **TSK-382** | 本単位は、**製品トラフィックを受ける配備先には適用しない**。SP-06(12-9)・12-4 の non-serving 宣言・12-6 の受け取り先表の**どれも変えない**。「実スキーマ」の意味も定義しない(TSK-382 の判断を先取りしない)【1 周目 1-P2-1】 |
| **TSK-431** | 本計画(PR A)は TSK-431 と衝突しない(`scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*.json` に触れない)。PR B が TSK-431 のマージを待つ |
| **TSK-349** | 移行バッチ用ロールのライフサイクルの**実行**(退役・接続監査・孤児回収・同時実行・状態の収束)と、`event_slots` の食い違いの解消の窓口。本単位の資産(8-1・8-2)を入力として使う。申し送りは 8-4 |
| **U-A1 / U-A2 / U-C1 / U-C2 / U-C3** | 越境関数と、その ACL・`search_path`・関数所有ロールへの所有の付与は各単位が持つ。本単位は補助関数 1 個だけを持ち、「それ以外の `SECURITY DEFINER` 関数は 0 件」を試験で表明する(6-3) |
| **U-M1 / U-D1 ほか帯 2** | capability カタログ(PR A)に載っている capability だけを登録できる(10 節)。アプリ層の実装は先に着手できる |
| **TSK-250** | 写像資産は本単位が正。TSK-250 の予告資産は導出側(7 節) |
| **スキーマを持つ単位** | 8-1 の `event_slots` の取り込みバッチ識別子の欠落(窓口は TSK-349) |

## 未解決・検討メモ

1. **`tenants` の名称変更の経路** — 本単位は `SELECT` のみを与える。チーム自身が名称を変える要件があれば、U-A1 か U-A2 の関数経由になる。要件の確認は各単位へ送る
2. **追記専用表の ACL の最小権限化** — 正本は一律に `SELECT` / `INSERT` / `UPDATE`(`data-model.md:209`)。追記専用の表から `UPDATE` を外すと防御は一段深くなるが、正本の変更になる。本単位ではしない
3. **`invalidation_intents` の配信側** — 波及先テナントへの配信を誰がどの権限で行うかは、11-2 節を持つ単位の射程
4. **補助関数の性能** — ポリシーごとに関数を呼ぶ。制御資源の表は小さいので問題にならない見込みだが、計測はしていない(推測)。NFR-005 の対象になる集計経路ではない
