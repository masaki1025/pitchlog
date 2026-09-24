---
feature: product-authz-surface
type: design
date: 2026-09-24
---

# 詳細設計: TSK-424 製品認可面の確定

本書は [plan.md](./plan.md) 4 節から参照される詳細設計である。調査の典拠は [research.md](./research.md)。
入力は U-T1 の詳細設計 `../tenant-boundary-enforcement/design.md` の 2〜4 節・7 節・9 節である。
**本書はそれを正本と実測で検証し直し、本単位の設計として確定する**。U-T1 の記述を是正した箇所は、各節に明記する。

**改訂履歴**: 計画レビュー 1 周目(P0 7 / P1 8 / P2 2)と 2 周目(P0 6 / P1 7 / P2 2)の反映。各節末の【1 周目】【2 周目】が、その周で直した点である。2 周目の後、移行バッチ用ロールの実行側を TSK-349 へ切り出した(人間の判断 2026-09-24 — 8 節)。3 周目(P0 3 / P1 8)の反映は【3 周目】。4 周目(P0 3 / P1 6 / P2 3)の反映は【4 周目】。6 周目(P0 3 / P1 4 / P2 2)の反映は【6 周目】。7 周目(P0 3 / P1 2 / P2 2)の反映は【7 周目】。10 周目の後、11 周目(P0 1 / P1 4 / P2 2)の反映は【11 周目】、12 周目(P0 2 / P1 2 / P2 3)の反映は【12 周目】(製品の SQL 本体は凍結しない方針に改めた — 3-2-a)。8 周目は「条件付き可」(P0 0 / P1 3 / P2 2)で、その条件の反映は【8 周目】。9 周目(P0 0 / P1 5 / P2 1)の反映は【9 周目】。10 周目(P0 1 / P1 5 / P2 2)の反映は【10 周目】で、**plan.md を PR A1 だけの計画書にし、A2 を別の計画書へ切り出した**(本書は TSK-424 全体の設計の正として共有する)。9 周目では、あわせて PR A を A1 / A2 に分けた(人間の判断 2026-09-24 — 迂回検査の `allowed_symbols` が凍結基準で、TSK-431 の 7C を待つため)。5 周目(P0 4 / P1 4 / P2 2)の後、人間の判断(2026-09-24)で、表分類の自己充足の残余を受容し、露出の事実を正本の文言に結び付ける形で確定した(1-5)。

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
| **`effective_group_control`** | `ENABLE` + `FORCE` | `FOR SELECT`。述語は正本 3-0 節の「実効グループ ∧ 実効参加」(1-3) | **与えない**。読み取りは U-C2 の制限関数、書き込みは U-C1 の管理関数だけ(1-3)【7 周目 7-P0-1】 |
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
| 所有者の表権限 | **`BYPASSRLS` は RLS を迂回するだけで、表の権限は与えない**。所有者に与える権限を **`{表, 列, 権限}` の機械可読な exact-set** として資産に置き、`pg_attribute.attacl` まで検査する: `public` の `USAGE` / `tenants`(`id`・`enabled`)・`analysis_groups`(`id`・`status`)・`group_memberships`(`group_id`・`tenant_id`・`role`・`status`)の**列単位の `SELECT`**。**表単位の `SELECT` を与える・使わない列を 1 つ足す・必要な列を 1 つ欠く変異を、それぞれ red にする**【2 周目 2-P1-1・3 周目 3-P1-4】 |
| 属性 | `SECURITY DEFINER` / `STABLE` / `SET search_path = pg_catalog, pg_temp`(`pg_temp` を末尾に明示 — REJ-003)/ 本文の表参照はすべてスキーマ修飾 |
| ACL | 作成と同じトランザクションで `REVOKE ALL ... FROM PUBLIC`(`data-model.md:242`)。**`pitchlog_app` にも `EXECUTE` を与えない**(アプリ用ロールは制御資源の表に直接触れないので、ポリシーを評価する場面が無い) |
| スキーマ | `authz_private`(所有者 `pitchlog_shared_fn_owner`。`pitchlog_app` にも何も与えない。`CREATE` は誰にも与えない) |
| 存在の秘匿 | 参加していないグループと、存在しないグループは、どちらも `false` を返す。**戻り値から存在を推測できない**(FR-034 の 404 と同じ性質) |

**なぜアプリ用ロールに直接の `SELECT` を与えないか**【7 周目 7-P0-1】: 正本の読み取りの粒度(`data-model.md:463-471`)は、行だけでなく**列と、対象の行の状態**にも及ぶ。

- 一般のメンバーには、他のメンバーの**テナント名だけ**を見せる。参加日時と役割は `admin` だけに見せる
- 離脱したメンバーの参加行と付与は見せない

ポリシーが判定できるのは「要求元が実効参加しているか」だけで、この 2 つは表せない。**直接の `SELECT` を残すと、U-C2 の制限関数を作っても、アプリ用ロールが表を直接読んで列の制限を迂回できる**。
→ **4 表とも、アプリ用ロールには表の権限を与えない**。読み取りは U-C2 の制限関数(`BYPASSRLS` の所有者で動く)に一本化する。

**それでもポリシーを置く理由**: 正本 3-5 節は、制御資源の RLS を「実効グループ ∧ 実効参加」の形と定めている。将来、直接の読み取りを開く単位が現れたときに、**行の制限が最初から効いている**ようにするためである。
直接の読み取りを開くには、表分類の改訂(コア領域の逐行確認)と、列と対象の行の制限の設計が要る。capability カタログにも載せない(10 節)。

**表ごとのポリシー**(すべて `FOR SELECT TO pitchlog_app`。**アプリ用ロールに表の権限が無い間は評価されない**。試験では、rollback するトランザクションの中で `pitchlog_app` に一時的に権限を与えて述語を確かめる — 6-2):

| 表 | `USING` |
| --- | --- |
| `analysis_groups` | `tenant_has_effective_membership(id, false)` |
| `group_memberships` | `tenant_has_effective_membership(group_id, false)` |
| `sharing_grants` | `EXISTS (参加行 m WHERE m.id = membership_id AND tenant_has_effective_membership(m.group_id, false))` — 参加行の読み取りも同じポリシーに従う |
| `group_invitations` | `tenant_has_effective_membership(group_id, true)`(招待は `admin` のみ — `data-model.md:470`) |

- **列の粒度**(メンバー一覧はテナント名のみ、参加日時と役割は `admin` のみ — `:463-471`)は、行ポリシーでは表せない。さらに、**他の参加テナントの名前は `tenants`(`self_tenant_row`)からは読めない**。→ **制御情報の読み取りは、U-C2 が持つ制限関数**(probe の `read_control_resources` に当たる)が、要求元の実効参加を確かめたうえで、テナント名と `admin` だけに見せる列を返す。本単位は、アプリ用ロールが 4 表に直接触れないことと、ポリシーの述語までを持つ
- **スキーマの欠落**: 正本はグループの名称を求める(`:453`)が、`analysis_groups` に名称の列が無い(`contracts/db/schema-manifest.json:945-963`)。グループ作成を持つ **U-C1** へ申し送る【6 周目 6-P0-2】
- **この関数は越境関数(記録・集計を返す経路)ではなく、ポリシーの述語の一部**である。U-T1 plan `:86` が「製品 RLS の述語構造は TSK-424」と定めた範囲に入る
- 本関数を置くので、**最低要求 ②(`PUBLIC` が実行できない)と ③(`search_path` の乗っ取りが効かない)が本単位にも掛かる**。6 節で試験する

【1 周目 1-P0-1】旧案は制御資源を `function_only` にしていた。これは正本 3-5 の契約の変更で、確定ゲートの対象だった。**正本を変えずに済むこの形へ改めた**。

### 1-4. 全 45 表の割り当て(母集合 = `contracts/db/schema-manifest.json`)

**`tenant_owned`(23 表)** — `direct`:

`team_records` / `players` / `games` / `lineup_memories` / `game_lineups` / `participation_intervals` /
`event_slots` / `operation_events` / `play_rows` / `play_runners` /
`temporary_player_id_mappings` / `idempotency_ledger` / `rejected_event_originals` / `evacuated_event_originals` /
`recording_generations` / `medical_notes` / `medical_note_versions` / `pdf_export_records` / `tenant_vocabularies` /
`player_merge_events` / `player_move_records` / `invalidation_intents` / `migrated_final_lineups`

- 追記専用の表(`operation_events` など)も、ACL は正本どおり `SELECT` / `INSERT` / `UPDATE` にする(`data-model.md:209`)。変更の禁止は migration のトリガが担う
- `invalidation_intents` は、`T7` と同じトランザクションで要求元テナントの文脈から書く(`data-model.md:2147`)

**`self_tenant_row`(1 表)**: `tenants` — `direct`(`SELECT` のみ)。書き込みは管理経路(**U-A2**)の関数。

**`effective_group_control`(4 表)**: `analysis_groups` / `group_memberships` / `sharing_grants` / `group_invitations` — **アプリ用ロールには表の権限を与えない**。読み取りは **U-C2** の制限関数、書き込みは **U-C1** の管理関数。正本 3-5 節の RLS ポリシーは置く(1-3)。

**`global_read_only`(4 表)**: `game_type_rule_defaults` / `system_vocabularies` / `admin_vocabularies` / `system_settings` — `direct`(`SELECT` のみ)。書き込みは **U-A2** の関数。`game_type_rule_defaults` から読めるのは規則セットの ID までで、規則の中身は `rule_sets` の関数経由で読む

**`function_only`(13 表)**:

| 表 | `access_path.reason` | 所有単位 |
| --- | --- | --- |
| `tenant_auth_subjects` / `tenant_credentials` / `tenant_tokens` | `pre_context_authentication`(1-2) | U-A1 |
| `rate_limit_counters` | `pre_context_global_mutable`(1-2) | U-A1 |
| `admin_credentials` / `admin_sessions` / `admin_operation_logs` | `admin_path`(`data-model.md:1543`) | U-A2 |
| `migration_runs` / `migration_quarantine` / `migration_resolution_reports` / `migration_warning_reports` | `migration_batch_only`(8 節) | 移行バッチ用ロール(TSK-349) |
| `rule_sets` / `tournament_rule_assignments` | `mixed_ownership_rules`(1-6) | **U-X1(凍結中)**(FR-014 の主所有 — `../product-impl-unit-split/plan.md:234`。PO 決定 2026-09-24) |

合計は 23 + 1 + 4 + 4 + 13 = **45**。

### 1-6. 規則セットは所有者の列を持たないので、直接読ませない

正本は、規則を 3 層に分けている。**試合区分のデフォルトはシステム管理者が管理してテナントに属さない**。一方、**大会名に紐づく規則はチームが設定する**(`data-model.md:1280-1289`・`:1963`)。
ところが物理表 `rule_sets` は、**所有者の列(`tenant_id` や帰属の区分)を持たない**。全体既定の規則も、チームごとの大会規則も、同じ表に入る(`contracts/db/schema-manifest.json:225-245`)。どちらの規則かは、参照する側(`game_type_rule_defaults` か `tournament_rule_assignments`)でしか分からない。

- **`rule_sets` を `global_read_only` にすると、全テナントが他チームの大会規則を読める**(越境)。`tenant_owned` にもできない(`tenant_id` が無い)
- **`tournament_rule_assignments` を `tenant_owned` にすると、自テナントの割り当てに他テナントの規則セットの ID を結べる**。これで他チームの規則を自分の大会に使えてしまう
- → 2 表とも **`function_only`**。規則を読む・大会へ結ぶ経路は、FR-014 を持つ単位の関数が「全体既定か、要求元テナントが割り当てた規則だけ」を返す形で用意する
- **スキーマの欠落**(`rule_sets` に帰属の列が無い)は、FR-014 の主所有の U-X1 へ申し送る。帰属の列が入れば、`rule_sets` を「全体既定は全員が読め、大会規則は自テナントだけが読める」ポリシーへ改訂できる
- **FR-014 の主所有は U-X1(状況計算核・帯 4 で凍結中)**(`../product-impl-unit-split/plan.md:234`。表は `FR-014` ではなく裸の番号 `014` で列挙している)。**PO 決定(2026-09-24)で U-X1 のままとし、単位の再定義はしない**。したがって、規則を読む・大会へ結ぶ関数と帰属の列は、**帯 4 の解凍後に U-X1 が足す**。それまでは、規則セットへはどの経路からも直接届かない(function_only なので安全側)。U-X1 のカードに申し送りを記録した。【訂正 2026-09-24】旧版は「単位分割計画に載っていない・候補は U-G1」と書いていたが、`FR-014` の文字列だけで検索した誤りだった
- **実 DB 試験**: テナント A と B がそれぞれ大会規則を作る。`pitchlog_app` は `rule_sets` と `tournament_rule_assignments` をどちらも読めない(`42501`)
- 露出の事実(1-5-a)では、`rule_sets` を「非テナント」にしない。**正本の文言が「テナントに属さない」としているのは試合区分デフォルトだけ**である

【6 周目 6-P0-1】5 周目までの案は `rule_sets` を全体共有にしており、他チームの大会規則を読めた。

### 1-5. 表分類の合格述語 — 露出の事実を正本の文言に結び付け、残余は人間の逐行確認が持つ

**分類資産そのものを正解にすると、誤った割り当てで自己充足する**(1 周目 1-P0-2)。
例: `admin_credentials` を `global_read_only` に移すと、DDL も実 DB 試験もその分類から期待値を導くので、全部 green になる。

**方針(人間の判断 2026-09-24)**: どんな機械検査でも、**同じ PR の中で分類と判定基準を両方弱める変更**は止められない。
→ 機械検査は「**分類だけ・判定基準だけの単独の変更を検出する多重防御**」と位置づける。**複数の決定元を同時に弱める変更は、コア領域の人間の逐行確認が止める**(残余リスクとして受容 — 本節末)。

#### 1-5-a. 露出の事実の資産

**`contracts/authz/product/exposure-facts.json`** に、表と列の「露出の事実」を置く。分類資産とは別の決定元である。
**各事実は、正本 `docs/design/data-model.md` の文言を典拠として引用する**。検査器は、**引用した文言が正本に一字一句そのまま存在すること**を確かめる。
正本は approved で、改訂には確定ゲート(7.3)が要る。したがって、**正本を変えずに事実だけを弱めることはできない**。

| 事実の種類 | 対象 | 典拠にする正本の文言(例) |
| --- | --- | --- |
| **非テナント(全体共有)** | `game_type_rule_defaults` / `system_vocabularies` / `admin_vocabularies` / `system_settings` | 3-4 節の全数表の `➖` の行と、10-3・10-4・10-5 節の「テナントに属さない」(`:386`・`:394`・`:1941`・`:1954`・`:1963`)。**`rule_sets` は入れない**(1-6) |
| **制御資源** | `analysis_groups` / `group_memberships` / `sharing_grants` / `group_invitations` | 3-5 節のエンティティ表(グループ / 参加 / 付与 / 招待 — `:451-461`) |
| **所有が混在する規則資源** | `rule_sets` / `tournament_rule_assignments` | 6-5 節の規則の表(`:1280-1289` — 「試合区分デフォルト」と「大会名に紐づく規則」) |
| **管理者専用** | `admin_credentials` / `admin_sessions` / `admin_operation_logs` | 8-2-A 節の管理者資格情報・管理者セッション(`:1534-1543` — 「テナント参照を持たないことが要点」「管理者経路はテナント文脈を持たない」)と、8-4 節の管理者操作ログ(`:1643`)【11 周目 11-P0-1】 |
| **認証前専用** | `tenant_auth_subjects` / `tenant_credentials` / `tenant_tokens` / `rate_limit_counters` | 8-2・8-3 節の認証主体・認証情報・トークンと、8-6 節のレート制限(`:1704-1720`)【11 周目 11-P0-1】 |
| **移行専用** | `migration_runs` / `migration_quarantine` / `migration_resolution_reports` / `migration_warning_reports` | 12-3 節の移行バッチと隔離領域(`:1969-1981`・`:2361-2373`)【11 周目 11-P0-1】 |
| **秘密の列** | `tenant_credentials.password_hash` / `admin_credentials.password_hash` / `group_invitations.code_hash`(**実装後の敵対レビュー 1 周目 P2 で訂正**: 当初は「認証トークン・セッションの識別子」〔`tenant_tokens.id`・`admin_sessions.id`〕も挙げていたが、**正本はトークンの提示形式を定めておらず**〔8-2-A・8-3 節〕、ID が提示される秘密だという典拠が無いので**取り除いた**。2 表は「管理者専用」「認証前専用」の事実で `function_only` のままで、アプリ用ロールの ACL も無い。**トークンの提示形式と秘密性の確定は U-A1**) | 8-2・8-3 節の認証情報と、3-5 節の「コードのハッシュ」(`:456`)・「コード本体は発行時に一度だけ表示」(`:470`)【6 周目 6-P2-1】 |

- 事実の表と列が manifest に実在することも検査する
- 典拠の引用が 1 件でも正本に見つからなければ不合格(fail-closed)

#### 1-5-b. 割り当ての条件

| プロファイル | 割り当ててよい条件 |
| --- | --- |
| `tenant_owned` | manifest で `tenant_id` 列を持つ ∧ 秘密の列を持たない ∧ 露出の事実で「非テナント」「制御資源」「所有が混在する規則資源」「管理者専用」「認証前専用」「移行専用」の**どれでもない** |
| `self_tenant_row` | `tenants` のみ |
| `effective_group_control` | **露出の事実で「制御資源」とされた 4 表だけ** |
| (共通) | **露出の事実で「所有が混在する規則資源」「管理者専用」「認証前専用」「移行専用」のどれかとされた表は `function_only` だけ**(11 周目 11-P0-1)。**`function_only` の表は、このどれかの事実を持つことを必須にする**(事実の無い表を `function_only` にすると red — 分類の入れ替えで件数を保つ抜け道を塞ぐ)。「所有が混在する規則資源」の典拠は(`rule_sets`・`tournament_rule_assignments`。典拠: 6-5 節の「試合区分デフォルト — システム管理者が管理」と「大会名に紐づく規則 — チームが設定可能」が同じ規則セットの表を参照すること — 1-6)【7 周目 7-P0-2】 |
| `global_read_only` | **露出の事実で「非テナント」とされた表だけ** ∧ manifest で `tenant_id` 列を持たない ∧ 秘密の列を持たない |
| `function_only` | **下の共通の条件を満たすこと**(追加の条件は無い)。共通の条件はすべてのプロファイルに論理積で掛かる【12 周目 12-P0-1】 |

- **秘密の列に対して、アプリ用ロールは表単位の `SELECT` も、その列の列単位の `SELECT` も持たない**(10 節の ACL と照合する。ACL の変異は plan.md のステップ 11 で試す)
- 母集合 = `Base.metadata` の全表 = manifest の全表。割り当て資産と**両方向 exact-set**(未割り当て 0・重複 0・存在しない表 0)。**既定のプロファイルを持たない**
- `function_only` の表は `access_path.reason` と所有単位(閉じた列挙: `U-A1` / `U-A2` / `U-X1` / `migration_batch`)が必須
- **正例**: 1-4 の 45 表の割り当てがすべての条件を満たす(plan.md のステップ 1 の合格条件)

【5 周目 5-P0-1・5-P0-3・5-P0-4】4 周目の案は manifest の構造(列と FK)だけで判定していた。そのため、`cross_tenant` の FK を持つ `admin_operation_logs` を制御資源として扱えた。生の行を持つ `migration_quarantine` も全体共有として扱えた。逆に、テナントの表から参照される語彙を全体共有にできなかった。

#### 1-5-c. 変異(分類資産だけで完結するもの — plan.md のステップ 1)

すべて red:

- `admin_credentials → global_read_only`
- `tenant_credentials → tenant_owned`
- `analysis_groups → tenant_owned`
- `admin_operation_logs → effective_group_control`
- `migration_quarantine → global_read_only`
- `rate_limit_counters → global_read_only`
- `rule_sets → global_read_only`(露出の事実に「非テナント」が無い)
- `tournament_rule_assignments → tenant_owned`
- `admin_operation_logs → tenant_owned` / `admin_operation_logs → global_read_only`(「管理者専用」)
- `tenant_auth_subjects → tenant_owned` / `tenant_tokens → tenant_owned`(「認証前専用」)
- **件数を保つ入れ替え**: `tenant_owned` の表を 1 つ `function_only` に移し、`admin_operation_logs` を `tenant_owned` にする(`function_only` の表が露出の事実を持たないので red)
- 表を 1 つ未割り当てにする
- モデルを 1 つ足す
- `function_only` の `access_path.reason` を消す
- **露出の事実の典拠の引用を、正本に無い文言に書き換える**
- **露出の事実から `password_hash` を消し、同時に `admin_credentials` を `global_read_only` にする**(`global_read_only` は「非テナント」の事実を要求するが、`admin_credentials` にはその事実が無い)

【5 周目 5-P0-2・5-P1-2】

#### 1-5-d. 受容した残余リスク

**分類資産・露出の事実・ACL の 3 つを同じ PR で整合的に弱める変更**は、機械検査では止められない。例: 正本にある無関係な文言を引用して「非テナント」の事実を捏造し、分類と ACL も合わせて変える。

→ **止めるのは、コア領域の人間の逐行確認**である(`contracts/authz/*` はコア領域の paths — `.claude/core-areas.json:295`)。
**人間の判断(2026-09-24)でこの残余を受容した**。PR の本文には、3 つの資産のどれかを変えたときに、逐行確認で見る観点(露出の事実の典拠が、その表の意味を本当に述べているか)を明記する。

【1 周目 1-P0-2 ほか、2〜5 周目の関連指摘】2〜4 周目は、固定 oracle を 7.7 の凍結基準として扱った。4 周目は、manifest の構造だけで判定した。どちらも自己充足を機械だけで閉じようとして、新しい欠陥を生んだ。

### 2-0. ロールの属性はすべて肯否で固定し、適用のたびに正規化する

PostgreSQL の `ALTER ROLE` は、指定しなかった属性を前の値のまま残す。**再適用で危険な属性が残らないように**、製品ロールの 7 属性(`SUPERUSER` / `BYPASSRLS` / `LOGIN` / `CREATEROLE` / `CREATEDB` / `REPLICATION` / `INHERIT`)を**すべて肯否で資産に宣言し、適用器は毎回 7 属性すべてを明示して正規化する**。

| ロール | `SUPERUSER` | `BYPASSRLS` | `LOGIN` | `CREATEROLE` | `CREATEDB` | `REPLICATION` | `INHERIT` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pitchlog_owner` | 否 | 否 | 可 | 否 | 否 | 否 | 否 |
| `pitchlog_app` | 否 | 否 | 可 | 否 | 否 | 否 | 否 |
| `pitchlog_shared_fn_owner` | 否 | **可** | 否 | 否 | 否 | 否 | 否 |
| `pitchlog_management_fn_owner` | 否 | **可** | 否 | 否 | 否 | 否 | 否 |
| 移行バッチ用(有効な間) | 否 | **可** | 可 | 否 | 否 | 否 | 否 |

- 変異(すべて red): 各ロールに `CREATEROLE` / `CREATEDB` / `REPLICATION` / `INHERIT` を 1 つずつ足した状態から再適用すると、正規化で消える(消えなければ red)。資産の宣言から属性を 1 つ消すと red(宣言が 7 属性そろっていない)
- `pitchlog_owner` は外部の適用主体が作る(2-3)が、属性の正規化は製品 DDL が毎回行う

【4 周目 4-P1-2】

### 2-1. DB と `public` スキーマの所有

PostgreSQL 17 では、`public` スキーマは `pg_database_owner` が所有し、DB の所有者がそれを管理する。

→ **DB の所有者を `pitchlog_owner` にする**(`CREATE DATABASE ... OWNER pitchlog_owner` — 外部の適用主体)。
`pitchlog_owner` は `public` に表と関数を作れる(migration)。
製品 DDL は、`public` の `CREATE` を `PUBLIC` から明示的に剥奪し、`pitchlog_app` に `USAGE` だけを与える。
**DB・スキーマの所有者と、DB とスキーマの ACL の最終状態を、次の期待集合と exact-set で検査する**(`{grantee, privilege, grantable}`。所有者の暗黙の権限は所有者の欄で検査する)【4 周目 4-P1-3】:

| 対象 | 所有者 | 期待する ACL(これ以外は 0 件) |
| --- | --- | --- |
| DB | `pitchlog_owner` | `pitchlog_app`: `CONNECT`。**`PUBLIC` の `CONNECT` と `TEMPORARY` は剥奪する**(PostgreSQL の既定では付いている)。移行バッチ用ロールの `CONNECT` は有効な間だけ(8-2) |
| `public` スキーマ | `pitchlog_owner`(`pg_database_owner` 経由) | `pitchlog_app`: `USAGE` / `pitchlog_shared_fn_owner`: `USAGE`。**`PUBLIC` の `USAGE` と `CREATE` は剥奪する** |
| `authz_private` スキーマ | `pitchlog_shared_fn_owner` | **何も与えない**(`pitchlog_app` にも `PUBLIC` にも。アプリ用ロールは補助関数を呼ばない — 1-3)【8 周目 8-P1-1】 |

- **所有者以外への `TEMPORARY` は、明示の付与も実効の権限も 0 件**(DB の所有者 `pitchlog_owner` の暗黙の権限と superuser は除く)。したがってアプリ用ロールは一時表を作れない【5 周目 5-P2-2】。一時スキーマを使う `search_path` の乗っ取り(REJ-003)は、補助関数の `search_path` の固定に加えて、ここでも閉じる
- 変異(すべて red): DB に `PUBLIC` の `CONNECT` を戻す / `pitchlog_app` に DB の `CREATE` か `TEMPORARY` を与える / `public` に `PUBLIC` の `USAGE` を戻す / `authz_private` に `CREATE` を与える / **`pitchlog_app` に `authz_private` の `USAGE` を与える** / `pitchlog_app` から DB の `CONNECT` を外す(接続できなくなることで検出)

【1 周目 1-P1-2】

### 2-2. ロールの membership — 製品ロールに接する辺は 0 本

**正本は、関数所有ロールについて「`NOLOGIN` + 誰にも `GRANT` しない」を唯一の経路と定める**(`data-model.md:223-233`)。
これをすべての製品ロールに広げる:

- **`pg_auth_members` のうち、製品ロール(`pitchlog_owner`・`pitchlog_app`・関数所有ロール 2 つ)を `roleid` か `member` に含む行が 0 件**。`admin_option` / `set_option` / `inherit_option` の**どの option の辺も**持たない
- **`ADMIN OPTION` だけの辺も 0 本**。`ADMIN` があれば、別の `LOGIN` ロールを作って `SET` 付きで付与し直せる。**`ADMIN` だけを足す変異で red**
- **恒久の特権主体の許可集合**を検査する。**LOGIN できる危険ロール**(`rolsuper` ∨ `rolbypassrls` ∨ 保護対象の所有者)**の集合が、許可集合と exact-set で一致すること**を検査する
  - 許可集合 = **製品が固定する部分**(`pitchlog_owner` — DB と表の所有者なので危険ロールに当たる。LOGIN するのは migration のときだけで、アプリ用の接続経路では U-T1 の真正性検査が拒否する — `backend/src/pitchlog/db/engine.py:159`)**∪ 環境が与える部分**(外部の適用主体と、その環境に正当に存在する管理用の superuser の OID)
  - **環境が与える部分は、製品資産に書かない**。検査の入力として渡す(使い捨てクラスタの試験では bootstrap の superuser の OID)。実環境での値と、その値の管理方法は TSK-344 が決める【4 周目 4-P1-4】
  - 検査の対象はクラスタ全体の LOGIN できるロールである。**環境が与える部分に入っていない superuser があれば不合格**(未知の特権主体を見逃さないため)
  - 移行バッチ用ロールは、定常では許可集合に入らない(8-3)

【2 周目 2-P1-5・3 周目 3-P0-3】2 周目の案(provisioner に恒久の `ADMIN` 辺を持たせる)は、正本の「誰にも `GRANT` しない」に反し、`CREATEROLE` と `ADMIN` の組み合わせで関数所有ロールへ到達する経路を作っていた。

### 2-3. 外部の適用主体

**製品 DDL は、外部の適用主体(superuser)が 1 トランザクションで適用する**。

- 理由: 関数所有ロールに `BYPASSRLS` を付けられるのは、superuser か、自分が `BYPASSRLS` を持つロールだけである(PostgreSQL 17 `ALTER ROLE`)。superuser でない provisioner を使うと、provisioner 自身に `BYPASSRLS` を持たせるか、製品ロールへの恒久の辺を残すことになる(2 周目の案の欠陥)。**どちらも製品ロールの外に危険な到達経路を増やす**
- superuser は表の所有者でなくても `ALTER TABLE`・`CREATE POLICY` を実行でき、スキーマと関数の所有者も移せる。**membership の辺を 1 本も作らずに適用できる**
- **superuser で試験すると権限の欠落が隠れる**、という懸念(2 周目 2-P1-2)への答え: superuser は DDL を適用するだけで、**製品の振る舞いの試験はすべて `pitchlog_app` と `pitchlog_owner`(superuser ではない)の接続で行う**。補助関数は実行時に所有者 `pitchlog_shared_fn_owner` の権限で動くので、所有者の権限の欠落は `pitchlog_app` からの試験で表に出る
- 実環境で誰が適用主体になるかは、TSK-344(実スキーマへの適用)の射程である。本単位は「superuser 相当の外部主体が、1 トランザクションで適用する」ことを契約として固定する
- probe の適用器は、superuser でない provisioner を使っている(`contracts/authz/ddl-elements.json:39-45`)。**probe は provisioner の到達性そのものを検証する目的だった**(TSK-317)。製品は検証済みの構成を置く層なので、この形を踏襲しない

【3 周目 3-P0-3・3-P1-1・3-P1-2】

## 3. 製品 authz DDL 資産の形と置き場

### 3-1. 置き場と段階

```
contracts/authz/product/table-classification.json        全 45 表の物理プロファイルと到達経路(1 節)
contracts/authz/product/exposure-facts.json              露出の事実 7 種(非テナント・制御資源・所有が混在する規則資源・管理者専用・認証前専用・移行専用・秘密の列)。正本の文言を典拠に引く(1-5-a)
contracts/authz/product/capability-catalog.json          capability の記述(10 節)
contracts/authz/product/ddl-elements.staged.json          製品 DDL 要素(PR A1 から PR B までの置き場。3-2)
contracts/authz/product/function-bodies/                  製品側の SQL 本体と manifest.json(要素とパスの対応表。**凍結しない** — 3-2-a)
contracts/authz/product/probe-product-map.json            probe 原子要素 ↔ 製品原子要素(7 節)
contracts/authz/product/migration-batch-role.json         移行バッチ用ロールの書き込み先と、有効な間の形(8 節)
```

- **probe 資産(`contracts/authz/` 直下)は 1 バイトも触らない**(封印 — `contracts/authz/oracle-seal.lock.json:40-88`)
- すべて `contracts/authz/*` に一致し、コア領域に入る(`.claude/core-areas.json:295`)
- `ddl-elements.staged.json` の scope は `{"status": "product_configuration", "product_schema": true, ...}`。**probe の scope 値と重ならない閉じた値**にする

### 3-2. PR A1 から PR B までの間は「未発効」の第三状態として置き、その状態自体を検査する

U-T1 の二状態テストは、**`contracts/authz/product/ddl-elements.json` が存在するかどうかだけ**で状態を切り替える(`backend/tests/test_authz_runtime_contract.py:65-84`)。
存在すると、暫定資産が残っていること・生成物が暫定のままであることが即座に違反になる(同 `:127-156`)。
暫定資産の削除は TSK-431 を待つ(9 節)ので、PR B より前に最終パスへ置くと、既存テストが red になる。

→ PR A1・A2 の間は `ddl-elements.staged.json` に置く。**ただし、名前を変えて検査を避けるだけにはしない**。
「製品資産はあるが、まだ発効していない」という第三状態を**明示し、新しい試験で検査する**(既存の `test_authz_runtime_contract.py` は変えない):

| 状態 | 条件 | 検査(新設 `backend/tests/test_authz_product_staging.py`) |
| --- | --- | --- |
| 暫定 | staged 無し ∧ 最終無し | 既存の二状態テストのとおり |
| **未発効(PR A1 の後、PR B の前)** | **staged 有り ∧ 最終無し** | ランタイムは暫定のまま(`PROVISIONAL = True`)。**staged 資産の宣言 `pending_switch` が、切り替えを行うタスクの ID を持つ**。**staged 資産から導いた保護対象が、暫定資産の保護対象 ∪ 宣言済みの追加分(`authz_private` スキーマと補助関数 1 個)と exact-set で一致する**(切り替え時に保護対象が黙って変わらない)。**この照合は、すべての DDL 要素がそろった後(plan.md のステップ 13)で初めて要求する**。それより前の未発効状態の検査は、状態・パス・`pending_switch` だけを見る【12 周目 12-P1-1】 |
| 製品 | staged 無し ∧ 最終有り | 既存の二状態テストのとおり(PR B の後) |
| **不正** | **staged 有り ∧ 最終有り** | **red**(二重の正本) |

- **正本 12-8 には、PR A1 の段階を「A1 の静的資産は確定・未発効(ランタイム契約の切り替えは PR B のタスク)」と書く。「landed」とは書かない**。TSK-424 の Notion カードも、PR B のマージまで完了にしない
- **PR B で `git mv` により最終パスへ移し、`runtime_contract` を足し、暫定資産を削除する**。資産指定オブジェクト(5 節)がパスを持つので、移動は spec の 1 行の変更で済む

【1 周目 1-P1-1・2 周目 2-P0-2】

### 3-2-a. 製品の SQL 本体は凍結しない — manifest は要素とパスの対応表にとどめる【11 周目 11-P1-1・12 周目 12-P0-2】

probe の `function-bodies/manifest.json` は、各 body の `source_commit` と blob digest を持ち、**oracle の凍結**(TSK-317 の第 1 群)のために本体を封印している(`scripts/check_authz_function_bodies.py:130-177`・`:258-335`)。
製品の SQL 本体に同じ封印を掛けると、**新しい凍結基準**を置くことになり、設計書 7.7 の宣言・追記のみの履歴・受理の単位が要る(11 周目の案は、この扱いを定めないまま封印のステップを置いていた)。

→ **製品の SQL 本体は凍結しない**。製品の DDL は、所有単位が関数を足すたびに改訂される資産であり、「変わらない」ことを主張する理由が無い。**正しさは意味の検査で担保する**: 表分類・露出の事実との exact-set(静的検査)と、PR A2 の実 DB 試験。

- **製品の manifest** は、`{要素の種別, 要素 ID, パス}` の対応表だけを持つ(`source_commit`・blob digest を持たない)。`PRODUCT_SPEC` の body 検査器は、**manifest と body ファイルと DDL 要素資産の 3 者が exact-set で対応すること**だけを検査する
- **probe の manifest の形は変えない**(`PROBE_SPEC` のときは従来どおり `source_commit` と digest を検査する)
- **述語の展開結果**(3-3)は、生成器の出力と資産の一致で検査する(digest は「生成物が古い」ことの検出に使い、凍結の基準にはしない)
- **変異**(すべて red): manifest に無い body ファイルを足す / body の無い要素を manifest に載せる / 要素 ID とパスの対応を入れ替える / `PRODUCT_SPEC` の manifest に `source_commit` を書く(凍結の基準を黙って持ち込ませない)

### 3-3. ポリシーの本体

- **表ごとにポリシーを 1 本の SQL ファイルで持つ**(`function-bodies/policies/POLICY:<table>:<profile>.sql`)
- `tenant_owned` 23 表ぶんの同じ述語は、**1 つの述語要素から生成器が展開する**(probe の `predicates/` と同じ仕組み)。**展開結果を資産として固定**し、生成器が壊れたら digest の差分で red にする
- `tenant_owned` のポリシーは `FOR ALL TO pitchlog_app`。`DELETE` は ACL が無いので `42501` になる

### 3-4. migration が作る関数の ACL

**【実装時の訂正 2026-09-24 — PR A1 ステップ 12】** 本節と 6 節の「33 個」は、暫定資産 `runtime_contract.py` の `PROTECTED_FUNCTIONS` の件数を写したもので、**migration が作る実物は 37 個**だった(0015・0016・0017・0024 の 4 関数が暫定資産から漏れている)。**製品資産は migration の実物 37 個を正とする**。暫定資産との差の 4 個は `provisional_contract_gap` の理由付きの追加分として宣言する(3-2 の未発効状態の照合の「宣言済みの追加分」に入る)。暫定資産(凍結基準)は PR A1 では変えず、漏れは PR B(TSK-443)へ申し送った

migration は `public` にトリガ関数を 33 個作る(`runtime_contract.py:85-119`)。PostgreSQL は関数の既定の `EXECUTE` を `PUBLIC` に与える。

- **33 個すべてから `PUBLIC` の `EXECUTE` を剥奪する**。`CREATE TRIGGER` の時点では関数の `EXECUTE` が要るが、**発火時には見ない**。migration は `pitchlog_owner` で作るので、所有者の `EXECUTE` は残り、再作成(downgrade → upgrade)にも支障が無い
- **剥奪後もトリガが発火すること**を実 DB 試験で表明する(アプリ用ロールの書き込みで、追記専用表のトリガが拒否を返す)
- **33 個が `SECURITY INVOKER` であること**をカタログ検査で表明する。`SECURITY DEFINER` の関数が migration に紛れたら red
- 関数 ACL の exact-set = 33 個 + 補助関数 1 個(1-3)

## 4. 適用経路

### 4-1. 順序

**migration の外で、migration の後に適用する**(裁定 A-2・`D7`)。

1. 使い捨てクラスタを作る(`backend/tests/db_fixtures.py:555-615` と同じ形)。クラスタの初期管理ユーザー(superuser)を **外部の適用主体**とする(2-3)
2. 適用主体が `pitchlog_owner` を作り、DB を `OWNER pitchlog_owner` で作る(2-1)
3. `pitchlog_owner` で接続して `alembic upgrade head`
4. 適用主体で接続して**製品 authz DDL を 1 トランザクションで適用する**(4-2)
5. カタログ検査と実 DB 試験(6 節)。**振る舞いの試験は `pitchlog_app` と `pitchlog_owner` の接続で行う**

### 4-2. 1 トランザクションで適用する

probe の適用器は、手順ごとに commit している(`backend/src/pitchlog/authz/provisioning.py:491` ほか 4 箇所)。
これは probe が表そのものを作り、superuser でない provisioner の到達性を段階的に確かめるためだった。
**製品の適用対象は migration が作った既存の表で、適用主体は superuser**(2-3)なので、この制約が無い。

→ **製品の適用は、ロールの作成を含めて全体を 1 トランザクションで行う**。手順は次の順に固定する:

1. ロールを作り、7 属性を正規化する(`pitchlog_app`・関数所有ロール 2 つ。`pitchlog_owner` は属性の正規化だけ)
2. DB とスキーマの ACL(`PUBLIC` の `CONNECT`・`TEMPORARY`・`public` の `USAGE`・`CREATE` の剥奪と、期待集合の付与)。`authz_private` スキーマを作り、所有者を `pitchlog_shared_fn_owner` にする
3. **補助関数**を作り、所有者を移し、所有者の列単位の権限を与え、関数 ACL(`PUBLIC` から剥奪)を整える。**ポリシーより先に作る**(ポリシーが補助関数を参照するため)
4. 全 45 表の `ENABLE` / `FORCE`
5. ポリシー
6. 表 ACL と列 ACL
7. トリガ関数 33 個の `PUBLIC` 剥奪

【7 周目 7-P0-3】6 周目までの手順は、ポリシーを補助関数より先に作っていたため、初回の適用が失敗した。

- **適用主体は `SET ROLE` を使わない**。**commit 後と rollback 後の両方**で、同じ接続の `current_user = session_user` を検査する
- **適用後の `pg_auth_members` に、製品ロールに接する辺が 0 本**(2-2)
- **失敗点**(R-5): 手順 1 の直後 / **手順 3 の補助関数の作成の直後** / 手順 4 の直後 / **手順 5 のポリシーの作成の直後** / 手順 6 の途中。**どこで失敗しても、カタログが適用前と 1 要素も変わらない**
- **変異**: 手順を 2 つのトランザクションに分ける(途中の commit)と red / 製品ロールへの辺を 1 本足すと red

【1 周目 1-P0-3・2 周目 2-P1-6・3 周目 3-P1-2】2 周目までの案(superuser でない provisioner が `SET LOCAL ROLE` と一時の辺で所有者の権限を借りる)は、`BYPASSRLS` を付ける権限と、スキーマ作成の権限が成立していなかった。

### 4-3. 再適用と migration の往復

- **二重適用**: 製品 DDL を 2 回適用しても、2 回目の後のカタログが 1 回目と同じになる(収束する)
- **往復**: 製品 DDL の適用 → **製品 DDL の取り外し(unapply)** → `alembic downgrade base` → `alembic upgrade head` → 製品 DDL の再適用。**取り外しを先に行うのは、補助関数などの製品のオブジェクトが migration の表に依存しているため**である(SQL 標準の本文の関数は参照先の表への依存を記録するので、そのままでは migration の `DROP TABLE` が失敗する)【6 周目 6-P1-2】
- **適用前の状態の前提**: fixture は、`pitchlog_owner` を **2-0 の 7 属性どおりに作ってから**、適用前のカタログを記録する。危険な属性からの正規化の試験は**別のケース**とし、そのケースでは取り外しの前後の一致を求めない(取り外しで危険な属性を戻すことはしない)【8 周目 8-P2-2】
- **取り外し**: 適用の逆順(トリガ関数の `PUBLIC` の `EXECUTE` を戻す → 表 ACL と列 ACL → **ポリシー** → `FORCE` / `ENABLE` → **補助関数** → `authz_private` → DB とスキーマの ACL を適用前へ戻す → ロールの削除〔`pitchlog_app`・関数所有ロール 2 つ。**`pitchlog_owner` は削除しない**〕)を、適用と同じく 1 トランザクションで行う。**ポリシーを補助関数より先に落とす**(依存の向き)。失敗点は、ポリシーの削除の直後と、補助関数の削除の直後に置く【7 周目 7-P0-3】。**取り外しの後のカタログが、製品 DDL の適用前と一致する**ことと、途中の失敗で何も変わらないことを検査する**再適用後のカタログが、初回の適用後と一致する**
- **non-serving 区間**(TSK-344 へ申し送る運用契約)【10 周目 10-P1-4】: 取り外しの commit の時点で、ポリシー・`FORCE`・ACL・ロールが適用前の状態に戻る。したがって区間は、**取り外しを始める前に、新しい接続を止め、既存のアプリの接続が 0 件であることを確かめた時点**から、**再適用の commit の後に、カタログ検査と越境の試験が green になった時点**までとする。**途中で失敗したら serving に戻さない**(downgrade や upgrade の失敗・再適用の失敗のどれでも)。実環境の手順は TSK-344 が持つ
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
- **既定値を probe にして、既存テストを無改変で green に保つ**。これが保証するのは**既存の回帰試験が観測する範囲の維持**であって、変更前との完全な一致ではない。**spec で分岐させた probe 固有の検査を一覧にし、各分岐を誤って無効にした変異(probe spec でその検査が走らなくなる)を新しい試験で red にする**【8 周目 8-P2-1】
- plan.md のステップ 5・6 の spec の汎化は、**試験の中で組み立てた、probe ではない試験用の spec** で確かめる。**本物の `PRODUCT_SPEC` を使う双方向の負例**(製品資産を probe spec で読むと拒否・その逆)は、`PRODUCT_SPEC` を作るステップで置く【8 周目 8-P1-3】
- **spec の取り違えを red にする**負例: 製品資産を probe spec で読むと scope 不一致で拒否、その逆も同じ。**「probe で試験して green にする」抜け道**を塞ぐ(U-T1 design `:280-281`)

## 6. 実 DB 試験

使い捨てクラスタに migration と製品 DDL を適用し、**2 テナント分の行**を置いて試験する。
**安全性の試験の期待値は、manifest の事実から導く**(分類資産から導かない — 1-5)。例: 最低要求 ① は「`tenant_id` 列を持つ 28 表すべてで、アプリ用ロールが他テナントの行を 0 行しか読めないか、`42501` で読めない」とし、表の集合を manifest から取る。表名は試験側に直書きしない。

### 6-1. `tenant_owned`(23 表すべて。代表の表だけで済ませない)

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
| `function_only` 13 表: `SELECT` | **`42501`(0 行ではない** — U-T1 design `:148-150`) |
| `effective_group_control`: `pitchlog_app` で 4 表を `SELECT` | **`42501`**(表の権限が無い — 7 周目 7-P0-1) |
| `effective_group_control`: `pitchlog_app` で補助関数を呼ぶ | **`42501`**(`EXECUTE` が無い) |
| `effective_group_control`: ポリシーの述語の正負行列(U-T1 design 9 節 #4) | 下表。ポリシーは `TO pitchlog_app` なので、**rollback する試験のトランザクションの中で、`pitchlog_app` 自身に 4 表の `SELECT`・`authz_private` の `USAGE`・補助関数の `EXECUTE` を一時的に与えて**確かめる。**rollback の後に、カタログが exact-set に戻っていること**(与えた権限が残っていないこと)を検査する【8 周目 8-P1-2】 |

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
| **最低要求 ②** | `PUBLIC` と、信頼しない `LOGIN` ロール(`pitchlog_app` を含む)が補助関数の実効の `EXECUTE` を持たない。**例外は関数所有者と環境入力の superuser**(負例の母集合から除く)【5 周目 5-P1-1・7 周目 7-P0-1】 |
| **最低要求 ③** | ① `pitchlog_app` は一時表を作れない(DB の `TEMPORARY` が無い — 2-1。`42501`)② `TEMPORARY` を持つ試験専用のロールで、一時スキーマに補助関数の参照先と同名の表を作り、そのロールの接続で補助関数を呼んでも結果が変わらない(`search_path` の固定の検査。試験専用のロールには試験の中だけで `EXECUTE` を与える) |
| 最低要求 ④ | 対象(共有集計の越境関数)が本単位に無い。**`pitchlog_app` が `EXECUTE` できる `SECURITY DEFINER` 関数が 0 件**であることを表明する。各単位が関数を足すと red になり、④ の試験を足すよう促す |

**変異**(すべて red): 1 表のポリシーを外す / `FORCE` を外す / `WITH CHECK` を `true` にする / `function_only` の表に `SELECT` を与える / 補助関数から「実効グループ」の条件を外す / 補助関数から「参加テナントが有効」の条件を外す / 補助関数の `search_path` から `pg_temp` の明示を外す / 補助関数を `PUBLIC` に `EXECUTE` させる。

## 7. probe ↔ 製品の写像

U-T1 design 2-1(`:76-95`)を引き継ぐ。

- **製品側の原子要素の母集合は `ddl-elements.staged.json` だけから取る**。移行バッチ用ロールは定常の DDL 資産に含まれない(2 節)ので、写像の codomain に入らない。`migration-batch-role.json` を写像の検査は読まない【4 周目 4-P2-1】
- 原子要素は `role` / `schema` / `table` / `policy` / `function` / `acl_privilege`
- 合格条件: **`probe の全原子要素 = mapped ∪ explicit_non_mapping`**、かつ **`製品の全原子要素 = mapped の像 ∪ product_only`**。両方向とも exact-set
- **理由コードは閉じた列挙**。種別ごとに使えるコードを固定する:

| コード | 使える原子要素の種別 | 意味 |
| --- | --- | --- |
| `test_only_role` | role | 試験専用(`outsider_role` / `management_caller`) |
| `external_provisioner` | role | 外部の手順が用意する(`provisioner`)。製品では外部の適用主体(2-3)に相当する |
| (廃止)`superseded_by_product_design` | — | **6 周目で廃止**。`read_control_resources` は `deferred_to_owning_unit`(U-C2)へ戻した【6 周目 6-P0-2】 |
| `deferred_to_owning_unit` | function / acl_privilege | 所有単位が足す(`owner_unit` 必須: U-C1 / U-C2 / U-C3 / U-A2) |
| `forbidden_by_canon` | acl_privilege | 正本が禁じる(`app_role` の `DELETE` — `data-model.md:209`) |
| `probe_schema_only` | schema / table / policy | probe 専用の器(`probe_data` / `probe_business_rows` など) |
| `product_only` | 製品側の全種別 | probe に対応物が無い製品要素(45 表・トリガ関数 33 個・補助関数など) |

- `read_control_resources`(`contracts/authz/ddl-elements.json:353`)は **`deferred_to_owning_unit` / `owner_unit: U-C2`**。U-C2 が、要求元の実効参加を確かめてテナント名と `admin` だけに見せる列を返す制限関数を持つ(1-3)。U-T1 の引き継ぎ(`../tenant-boundary-enforcement/design.md:596`)と一致する【6 周目 6-P0-2 — 4・5 周目の「置き換え」は、他テナント名を読む経路を失わせていた】
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
- **必要な権限の行列を、manifest から導いて固定する**(上限だけでなく下限も閉じる — 6 周目 6-P0-3):
  - 19 表すべてに `INSERT`(移行が行を作る — 正本 12-3 の不変条件 1)と `SELECT`(冪等性と検証のため)
  - **`UPDATE` は列単位**にする(`{表, 列, 権限}` の行列)。`retired_at` 列を持つ表は **`UPDATE(retired_at)` だけ**。`migration_runs` は、manifest の `immutability.allowed_update_columns` に挙がった列だけ(バッチの状態の更新 — 不変条件 2・3)。**表単位の `UPDATE` は与えない**(`BYPASSRLS` の移行ロールが、他バッチ・他テナントの行の中身〔`lineup_memories.lineup`・`medical_notes.content` など〕を書き換えられるため)【7 周目 7-P1-1】
  - これ以外の権限は持たない。**`DELETE` / `TRUNCATE` / `REFERENCES` / `TRIGGER` を足す変異で red**。**必要な権限を 1 つ外す変異でも red**
  - **正例**: 使い捨てクラスタで、資産どおりに作ったロールが、19 表それぞれへの最小の `INSERT` と `SELECT` と、`UPDATE` を要する表の `retired_at` の更新を実際に通す
  - **負例**: `lineup_memories.lineup`・`medical_notes.content` など、`retired_at` 以外の列の `UPDATE` が `42501`
  - TSK-349 の実行器の契約で必要な権限が増えたら、本資産を改訂する(改訂はコア領域の逐行確認の対象)
- **監査の表(`admin_operation_logs`)は含めない**。監査を書くのは移行実行器の管理接続であり、その設計は TSK-349 が持つ

**正本とスキーマの食い違い**(本単位では直さない — TSK-349 へ申し送る):
正本 12-3 の不変条件 1 は「**移行が作る行はすべて取り込みバッチ識別子を持つ**」と定める(`data-model.md:2367`)。
ところが `event_slots` は取り込みバッチ識別子を持たない(`contracts/db/schema-manifest.json:287-298`)。それなのに `operation_events` は `event_slots` を FK で参照する(`:340`)。
**移行が `operation_events` を作るなら `event_slots` の行も作る必要があり、そうすると不変条件 1 を破る**。
`medical_note_versions` も識別子を持たないが、移行がこの表に行を作るかどうかは正本から読み取れない。
→ 本単位は正本どおりの導出集合で閉じる。**この食い違いが解けるまで、実際の移行は `operation_events` を書けない**。書き込み先を広げるのは、食い違いが解けた後に、本資産の改訂として行う。

### 8-2. 有効化したときの形

資産 `migration-batch-role.json` に、有効な間のロールの形を宣言する。**名前は固定しない**(同時実行の制御は TSK-349 の射程なので、名前の付け方も TSK-349 が決める)。
**形の検査は、呼び出し元が渡したロールの OID を対象にし、名前に依存しない**(TSK-349 がどんな名前を採っても検査が効く)【3 周目 3-P1-8】。
本単位は、**資産どおりに作ったロールが次を満たすこと**を使い捨てクラスタで検査する:

| 正本の条件(`data-model.md:290-297`) | 有効な間の形 |
| --- | --- |
| アプリから到達しない | **このロールに接する `pg_auth_members` の辺(入る辺も出る辺も)が 0 本**。どのロールからも、`SET` / `INHERIT` / `ADMIN` のどの option でも到達しない。**無関係な `LOGIN` ロールから辺を足す変異・外部の適用主体から辺を足す変異で、それぞれ red**【3 周目 3-P1-3】 |
| DDL を持たない | `pg_class.relowner` / `pg_proc.proowner` / `pg_namespace.nspowner` / `pg_database.datdba` のどれにも現れない |
| 書き込み先の限定 | 表 ACL が `write_targets` と exact-set。スキーマの ACL は `public` の `USAGE` のみ。DB の ACL は `CONNECT` のみ。**製品スキーマ(`public`・`authz_private`)の利用者定義の関数を、1 つも実行できない**(直接の `GRANT`・`PUBLIC` 経由・既定の権限経由のどれでも。`has_function_privilege` で実効の `EXECUTE` を検査する)。`SECURITY DEFINER` の関数を実行できると、その所有者の権限で `write_targets` の外へ書けるため【4 周目 4-P0-3】 |
| (属性) | 7 属性の exact-set(2-0 の表): `LOGIN` / `BYPASSRLS` / `NOSUPERUSER` / `NOCREATEROLE` / `NOCREATEDB` / `NOREPLICATION` / **`NOINHERIT`**【5 周目 5-P2-1】 |

**関数の実行の変異**(すべて red): 移行バッチ用ロールに、`write_targets` の外の表へ書く試験用の `SECURITY DEFINER` 関数の `EXECUTE` を直接与える / `PUBLIC` に `EXECUTE` を戻す / 既定の権限(`ALTER DEFAULT PRIVILEGES`)で `EXECUTE` が付くようにする【4 周目 4-P0-3】。

**本単位が検査しないもの**(TSK-349 へ): 期間限定(退役の手順・資格情報の寿命)/ 監査(接続単位の記録と、投入結果との一対一対応)/ 孤児の回収 / 同時実行 / 投入の途中で止まったときの状態の収束。

### 8-3. 定常の不変条件

**移行を行っていない定常状態**では、次が成り立つ。**カタログ検査に入れ、成り立たなければ不合格**(fail-closed):

- 資産の形(8-2)をもつロール — **`BYPASSRLS` を持つ `LOGIN` のロールのうち、恒久の特権主体として宣言されていないもの** — が **0 件**
- 恒久の特権主体の許可集合(2-2)は資産に宣言する。**大域の「`LOGIN` + `BYPASSRLS` が 0 件」とはしない**(正当な外部の適用主体を誤検出するため)

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
| **旧カルテの移行で `medical_note_versions` に行を作るかの確定**。作るなら、取り込みバッチ識別子の不変条件と本資産の `write_targets` を先に改訂する。作らないなら、移行実行器の試験で 0 件を保証する | 3-P1-5 |
| **FR-038 の移行実行器が、本単位の `migration-batch-role.json` を読んで書き込み先と形を決めること**を、TSK-349 の合格条件にする | 1-P1-6 |

TSK-349 の旧 DoD のうち「凍結 probe 資産への追加と `--reseal-oracle`」は採らない(probe と製品は別の層 — `data-model.md:537`)。

【1 周目 1-P0-5〜7・1-P1-6・2 周目 2-P0-4〜6・2-P1-2〜5】

## 9. ランタイム契約の切り替え(PR B — 本計画の外)

**PR A1・A2 はランタイム契約を切り替えない**。切り替えは、TSK-431 のマージ後に**別のタスク・別のブランチ・別の計画書**で行う(plan.md 2 節)。PR B が行う内容を、ここに契約として固定する:

1. `contracts/authz/product/ddl-elements.staged.json` を `git mv` で `contracts/authz/product/ddl-elements.json` へ移し、`runtime_contract` オブジェクト(8 フィールド)を足す。値は製品資産から導出する
2. 生成器で `backend/src/pitchlog/authz/runtime_contract.py` を作り直す(`PROVISIONAL = False` / `SOURCE_ASSET` = 製品資産 / `SUPERSEDED_BY = None`)
3. 暫定資産 `contracts/tenant_boundary/runtime-authz-contract.json` を削除する。設計書 7.7-1(値をソースに残さない)・7.7-2(削除の記録を追記のみで残す)に従う
4. **履歴の生存先**: 暫定資産が持つ凍結基準(`baseline_control` の `identity`・`movement_policy`・`history` の組 — `contracts/tenant_boundary/runtime-authz-contract.json:4-64`)を、次のどちらかで扱う。**どちらを採るかは PR B の計画で確定し、その計画の敵対レビューにかける**:
   - **(a) 継承**: 製品資産の中に、**完全な `baseline_control`**(移した後の射影の範囲・現在の識別値・旧パスと旧射影から新パスと新射影への遷移の記録 1 件)を置く
   - **(b) 廃止**: 基準そのものを廃止する。現在の宣言は残さず、**専用の tombstone 資産に履歴だけを保持**し、廃止の記録を 1 件追記する
   - どちらでも、**旧履歴の `source_commit: PENDING_ACCEPTANCE` と、新しい記録の `source_commit` の識別の規則**を固定する。**TSK-431 が直した検査器が、base の旧資産と HEAD の生存先を exact に突き合わせること**を、PR B の合格条件にする【5 周目 5-P1-4・6 周目 6-P1-3】
5. 削除記録では、暫定資産の履歴にある `PENDING_ACCEPTANCE` と「未承認(PR #72 のレビュー待ち)」を**変更前の値としてそのまま**記録する。事実として「PR #72 のマージ後も受理値へ更新されていなかった」と書く。**値を書き換えてから削除することはしない**

**TSK-431 を待つ理由**: 暫定資産の削除は、凍結基準を動かす行為である(7.7-1)。削除記録を検査する機構が無い(既知欠陥 **7D**)。**7D を開けたまま削除はしない**。

【1 周目 1-P1-5】


## 10. capability — 「記述」は本単位が出し、「登録」は各単位が行う

U-T1 は、**製品の capability を TSK-424 の出力契約に含める**と定めている(`../tenant-boundary-enforcement/design.md:321`・`:421`)。

→ capability を 2 つに分ける:

| | 内容 | 持ち主 |
| --- | --- | --- |
| **capability の記述**(カタログ) | 表分類から導いた、**開けてよい操作の閉じた一覧**。`contracts/authz/product/capability-catalog.json` に置く。1 行 = (capability ID, 表 ID, 操作種別 `read` / `insert` / `update`)。**capability ID と `(表 ID, 操作種別)` は 1 対 1**(全単射)。**1 つの capability は 1 つの表の 1 つの操作だけを表す**。登録された文が参照する表の集合(FROM・JOIN・サブクエリのすべて)は、その 1 表とちょうど一致しなければならない【10 周目 10-P1-2】。**文の中でユーザー定義関数を呼ばない**(SELECT 句・WHERE 句・表を返す関数のどれでも。`pg_catalog` の組み込み関数だけを許す)。越境は `SECURITY DEFINER` の関数だけに分けてあるので(U-T1 design `:416-421`)、直接の capability の文に関数を混ぜると、その経路を迂回できるため【11 周目 11-P1-2】。**文の検査は、許す SQLAlchemy のノードの型を閉じた集合で持つ**(表・列・比較・論理演算・束縛パラメタ・`pg_catalog` の組み込み関数・並べ替え・件数の制限など)。**`text()`・`literal_column()` などの不透明な SQL 断片は拒否する**。**CTE は再帰的にたどり、読み取りの capability の中の DML の CTE(`add_cte()` を含む)を拒否する**。変異: 正しい表に `literal_column('authz_private.evil()')` を足す / 参照されない INSERT・UPDATE・DELETE の CTE を足す【12 周目 12-P1-2】。**`direct` の表だけ**が載る。`effective_group_control` と `function_only` の表は 1 つも載らない(アプリ用ロールが直接触れないので) | **本単位** |
| **capability の登録**(公開 registry) | `PRODUCT_CAPABILITY_IDS` などへ登録して、実際に操作を開くこと(`backend/src/pitchlog/repositories/repository_contract.py:57-59`) | **経路を持つ単位**(U-01・U-M1・U-D1 ほか)。本単位は空のまま残す |

- カタログは表分類から**生成器で導出**し、導出結果と資産の一致を検査する(手で書かない)
- **登録できるのは、カタログに載っている capability だけ**にする検査を本単位で置く。**ID の存在だけでなく、登録された operation token の文(`statement`)を解析し、その対象の表とコマンドが、ID に結び付いたカタログの行と一致すること**を確かめる(現物の registry は `{capability_id, statement, tenant_column}` を持つ — `backend/src/pitchlog/repositories/base.py:41-62`・`tokens.py:21-29`)。カタログに無い ID・**正しい ID を別の表や別の操作の文へ付け替える**・ID の重複を、変異で red にする。現物の registry は `Select` だけを扱うので、`insert` / `update` の登録の形式は、それを開く単位が registry と一緒に定める(本単位はカタログの行を用意するだけ)【9 周目 9-P1-1】
- 検査は**試験の中だけで仮の登録を作って確かめる**。製品のパッケージには登録しない
- U-T1 の「順序依存は 1 点だけ」(`../tenant-boundary-enforcement/plan.md:113-118`)とは矛盾しない。U-T1 が待っていたのは期待ロール名と保護対象(9 節)である

【2 周目 2-P0-3】旧案は capability を一切出さず、U-T1 の出力契約と矛盾していた。

**登録の検査の保証範囲(脅威モデル — 人間の判断 2026-09-24・山田正輝)**: 実装後の敵対レビューで、この検査への指摘が 3 周続いた(P1: 3 → 1 → 1)。周を追うごとに SQLAlchemy の内部状態を 1 段ずつ深く掘る形だったため、保証の範囲を次のとおり宣言して打ち切る。

| 範囲 | 扱い |
| --- | --- |
| **SQLAlchemy の公開 API で組み立てた文**(別の表の参照・`text()` / `literal_column()` などの不透明な SQL 断片・UDF・DML の CTE・prefix / suffix・hint・`execution_options`・方言オプション・任意の演算子) | **検査で閉じる**(fail-closed) |
| **その文のインスタンスの状態**(許可したノード型ごとの `__dict__` のキーの exact-set・キャッシュ属性と正規の導出値の一致) | **検査で閉じる** |
| **型(クラス)の書き換え・SQLAlchemy 自体の改変**・監査した版(2.0.52)以外の SQLAlchemy | **保証の外**。版が違えば検査は拒否する側に倒れる(再監査まで登録できない)。型や依存の改変はコア領域の人間の逐行確認が止める |

- 目的は、各単位が書く**登録の誤り**を止めることである。私的属性を意図して書き換える登録は、この検査の対象ではない(登録はコア領域として逐行確認を通る)

## 11. 正本の追随(PR A1 に含める。A2 は A2 の PR で追記する)

| 箇所 | 変更 | ゲート |
| --- | --- | --- |
| `data-model.md` 12-8(`:2844-2846`) | TSK-317 行を**分割**する。**PR A1 の段階では、A1 が置いた範囲だけを「確定・未発効」と書く** = 表分類・露出の事実・capability カタログ・製品 DDL の静的資産(TSK-424 PR A1)。**適用・実 DB 検査・移行ロールの資産・写像は確定と書かない** = TSK-424 PR A2(残件 — 7C の後)。A2 のマージで追記する【10 周目 10-P0-1】。ほかの残件: 移行ロールのライフサイクルの実行 = TSK-349 / 越境関数と最低要求 ②③④ の残り = U-C1 / U-C3 / U-A2 / 認証・レート制限の関数(`function_only` の 4 表への到達経路)= U-A1 / 制御情報の読み取りの制限関数と列の粒度の制限 = U-C2 / 規則セットの関数と `rule_sets` の帰属の列 = U-X1(凍結中 — FR-014 の主所有) / `analysis_groups` の名称の列 = U-C1 / 実スキーマでの再実行 = TSK-344 / ランタイム契約の切り替え = PR B のタスク / Session の供給 = PR C のタスク。**タスクは Notion の ID で記録する**。**「解消済み」にしない** | 7.6-3 前段(実装追随の節更新)→ PR レビュー |
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
| **TSK-431** | **PR A1** は TSK-431 と衝突しない(`scripts/check_tenant_boundary_bypass.py` と `contracts/tenant_boundary/*.json` に触れず、`backend/src` の DB 呼び出しの違反も増やさない)。**PR A2** は `base-allowlist.json` の `allowed_symbols` を足すので 7C の後、**PR B** は 7D の後、**PR C** は `allowed_symbols` を足すので 7C の後(人間の判断 2026-09-24) |
| **TSK-349** | 移行バッチ用ロールのライフサイクルの**実行**(退役・接続監査・孤児回収・同時実行・状態の収束)と、`event_slots` の食い違いの解消の窓口。本単位の資産(8-1・8-2)を入力として使う。申し送りは 8-4 |
| **U-A1 / U-A2 / U-C1 / U-C3** | 越境関数と、その ACL・`search_path`・関数所有ロールへの所有の付与は各単位が持つ(U-A1 = 認証・レート制限、U-A2 = 管理経路、U-C1 = グループ管理、U-C3 = 共有出力)。本単位は補助関数 1 個だけを持ち、「それ以外の `SECURITY DEFINER` 関数は 0 件」を試験で表明する(6-3) |
| **U-C2** | **制御情報の読み取り 4 経路の制限関数を持つ**(`read_control_resources` に当たる — 7 節)。テナント名と `admin` だけに見せる列を返し、列の粒度の制限もここで持つ(1-3) |
| **U-M1 / U-D1 ほか帯 2** | capability カタログ(PR A1)に載っている capability だけを登録できる(10 節)。アプリ層の実装は先に着手できる |
| **TSK-250** | 写像資産は本単位が正。TSK-250 の予告資産は導出側(7 節) |
| **スキーマを持つ単位** | 8-1 の `event_slots` の取り込みバッチ識別子の欠落(窓口は TSK-349) |

## 未解決・検討メモ

1. **`tenants` の名称変更の経路** — 本単位は `SELECT` のみを与える。チーム自身が名称を変える要件があれば、U-A1 か U-A2 の関数経由になる。要件の確認は各単位へ送る
2. **追記専用表の ACL の最小権限化** — 正本は一律に `SELECT` / `INSERT` / `UPDATE`(`data-model.md:209`)。追記専用の表から `UPDATE` を外すと防御は一段深くなるが、正本の変更になる。本単位ではしない
3. **`invalidation_intents` の配信側** — 波及先テナントへの配信を誰がどの権限で行うかは、11-2 節を持つ単位の射程
4. **補助関数の性能** — ポリシーごとに関数を呼ぶ。制御資源の表は小さいので問題にならない見込みだが、計測はしていない(推測)。NFR-005 の対象になる集計経路ではない
