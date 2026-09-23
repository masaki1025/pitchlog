---
feature: tenant-boundary-enforcement
type: research
date: 2026-09-17
---

# 調査メモ: U-T1 テナント境界の強制点 — 実装入力の確定

## 問い

TSK-418「U-T1 の入力を確定する」が「U-T1 の実装入力が未確定である」と指摘している。
この指摘が**今も成立しているか**を原典で裁定し、成立するなら**何がどこまで揃っていて、何を
U-T1 の計画書が決めなければならないか**を、資産のパスとキーで名指しできる形にする。

調査体制: spec-checker(要件突合)/ decision-tracer(TSK-317 の成果と裁定)/ Explore(authz 実資産の棚卸し)
の 3 並列。legacy-analyst は外した(テナント分離は旧システムに対応面のない新規要求 — U-00 と同じ判断)。
**エージェント間で判断が分かれた点・計画を左右する点は、すべて原典で再確認した**(下記「裁定した点」)。

## 結論(要約)

1. **TSK-418 の指摘は実質的に成立する。** ただし「`data-model.md` が構成要素 4 つを TSK-317 へ送っている」は
   **一部成立**(12-8 節の表で TSK-317 を名指しているのは 2 行のみ)。**結論は変わらない** —
   その 2 行は **probe 層では実体が landed しているが、製品スキーマへの写像が欠けている**ため、
   U-T1 が直接消費できる形になっていない。**「確定済み」と言える行は 0**。
2. **U-T1 は 12-4 のマージゲートの対象ではなく、TSK-344 を待たずにマージできる。**
   Notion カードの「マージの条件」節は ADR-004 approved 前の理解が残った**古い記述**であり、
   分割計画書が【承認後の是正】として明示的に訂正している。→ **カード側の追随が要る**。
3. **U-T1 のスコープ 5 要素は、いずれも FR-034 に直接の根拠がない。** FR-034 が定めるのは越境の*結果*
   (404・存在秘匿・認可行列)であり、*機構*は `docs/design/data-model.md` 3 章が正。
   要件書には `RLS` / `set_config` / `search_path` / `DDL` の語が 1 件もない。
4. **「未設定時 fail-closed」の DB 層での意味は「`set_config` を出さなければ 0 行」まで**である。
   **「他テナントの値を騙れない」ことは DB 層では保証できない** — 既存テストがこれを**残余リスクとして
   期待値に固定**しており、値の真正性は API 層(TSK-217)の責務と宣言されている。**U-T1 の射程の核心的な限界**。
5. **実装入力の 3/4 は既に probe 層の実資産として存在する**(ロール属性・`search_path`・関数 ACL・RLS ポリシー)。
   **欠けているのは probe → 製品の写像**と、**製品スキーマの物理 DDL 書式**の 2 点である。

## 詳細と典拠

### 1. TSK-418 の各主張の裁定

| TSK-418 の主張 | 判定 | 典拠 |
| --- | --- | --- |
| `data-model.md` が U-T1 の構成要素 **4 つ**を TSK-317 へ送っている | **一部成立** | 12-8 節の表で受け取り先が TSK-317 と明記されているのは **2 行のみ**(`docs/design/data-model.md:2844` 名前解決経路の非注入 / `:2845` RLS ポリシー・ロール DDL の実機確定)。「物理 DDL の書式」(`:238` 付近)は「実機確定時でよい」の括弧書きのみで **TSK-317 を名指ししていない**。「4 つ」の数え方の出所は `docs/features/pg-authz-verification-g3/research.md:247-256` の表 |
| `ddl-elements.json` の `scope.product_schema` が `false` | **成立** | `contracts/authz/ddl-elements.json:10` = `"product_schema": false`、`:9` = `"status": "verified_probe_configuration"`。`scope` キーを持つのは `contracts/authz/` 内でこの 1 ファイルのみ |
| `product-ddl-map-data-model.json` は予告のみで**資産が未作成** | **成立** | `scripts/design_relations/` に存在しない。**全ブランチ・全履歴を当たっても一度も追加されていない**(`git log --all --diff-filter=A`)。同名で存在するのは**テスト fixture のみ** = `tests/fixtures/profile-sample/assets/product-ddl-map.json`(合成サンプル)。予告は `docs/features/data-model-canonical/plan.md:253`(条件付き必須)・`:135` `:143`(申し送り 15・23) |
| U-T1 と TSK-317 を結び付けた記述が `product-impl-unit-split/` の 3 文書に **0 件** | **成立** | `TSK-317` の出現は 6 件(research 3・plan 2・design 1)で、いずれも U-T1 と結び付いていない。U-T1 の依存列は `docs/features/product-impl-unit-split/plan.md:204` で **`U-00` のみ** |

**発火条件は今も成立している**: `product-ddl-map` の条件付き必須は
「`ddl-elements.json` の `scope.product_schema` が `false` である限り必須」(`docs/features/data-model-canonical/plan.md:253`)。
現在値は `false`(`contracts/authz/ddl-elements.json:10`)。
**未マージの `fix/oracle-input-baseline`(develop より 41 コミット先行)でも `false` のまま**で、
同ブランチの `ddl-elements.json` 差分は `oracle_commit` の digest 更新 1 行のみ
→ **U-T1 の入力としての実質は動かない。この並行タスクの完了を待つ理由はない。**

なお写像の**形式**は自明で、fixture が示すとおり `entries[].{ddl_id, product_id}` の素朴な ID 対応である
(`tests/fixtures/profile-sample/assets/product-ddl-map.json`)。**難所は形式ではなく製品側 ID を何にするかの決定。**

### 2. 12-8 節で TSK-317 が受け取り先の 2 行 — 現在の充足状態

| 行 | 充足状態 | 典拠 |
| --- | --- | --- |
| **名前解決経路の非注入の検査対象集合と合格述語** | **部分確定**(probe 構成のみ確定・製品構成は未確定) | 確定側: `contracts/authz/ddl-elements.json:102-127` が 3 スキーマ(`probe_data`/`authz_private`/`management_private`)について `create_role_ids: []` を宣言。合格述語は `docs/features/pg-authz-verification-g3/catalog-check-map.md:39`(`CATALOG:SEARCH-PATH:<function_id>` = `proconfig`、**末尾 `pg_temp` かつ出現 1 回**)。実装は `backend/src/pitchlog/authz/catalog.py`。**未確定側**: 対象集合は probe スキーマの集合であり、製品スキーマへの写像が無い。**合格述語の記述が正本でも `contracts/` でもなく feature 文書にある** |
| **RLS ポリシー・ロール DDL の実機確定と越境テストの作成・実行** | **部分確定**(probe クラスタ上で実機確定・越境テストは実在。製品スキーマへの適用は未) | 確定側: `contracts/authz/function-bodies/roles/`(7)・`policies/`(6)・`predicates/`(1)。越境テストは `backend/tests/db/test_authz_runtime_{positive,negative}.py` ほか。**未確定側**: `docs/features/pg-authz-verification-g3/design.md:382-384` が「本タスクは probe クラスタ上での作成・実行まで」と明記。実スキーマへの適用と再実行は **TSK-344**(`docs/design/data-model.md:2846`・裁定 `A-2`) |

### 3. マージゲート(12-4)は U-T1 に掛からない — Notion カードの記述が古い

`docs/features/product-impl-unit-split/plan.md:433-436`(逐語):

> **「DB を利用する単位はマージできない」は不正確だった**(本書の承認後に ADR-004 が approved になり、
> 適用単位が「当該 PR が開く入口ごと」へ精密化された)。**`U-T1` は入口を 1 つも開かないので、
> ゲートの要求は空である** — **`U-T1` 自体は TSK-344 を待たずにマージできる。**

同 `:440-443`【承認後の是正】も同旨。根拠条項は `docs/design/data-model.md:2528`(適用単位)・`:2532`(測定経路 —
「入口を 1 つも開かない PR に対しては、この要求は空である…空であることは要求の免除ではなく、
要求を当てる対象が無いことである」)。経緯は `docs/adr/ADR-004-merge-gate-scope.md`(approved 2026-09-13)。

→ **Notion カード TSK-390 の「マージの条件(着手とは別)」節は、この是正前の理解である。**
**カードの記述を追随させる必要がある**(U-T1 の DoD の変更ではなく、カードの記述の是正)。

**越境テストの最低要求 4 件の帰属**(`docs/design/data-model.md:2530`。**計画レビュー 2 周目で是正**):
① アプリ用ロールが関数を経由せず他テナント行を読めない ② `PUBLIC` が越境関数を実行できない
③ `search_path` の乗っ取りが効かない ④ 対象側が非共有なら要求元が付与していても返らない。

**4 件は 2 つの契約に現れ、帰属が違う**:
- **12-4 のマージゲートの通過条件②**としての 4 件 → **ゲートの対象は入口を開く PR** (`:2528`)。
  **U-T1 は入口を開かないので対象外**
- **12-7 (1) の実機確定タスクへの要求**としての 4 件 (`:2762-2765`) → **こちらはゲートとは別契約**で、
  **U-T1 が 12-8 の TSK-317 行 (`:2845`) を部分的に引き受ける以上、無所有にできない**

→ **責務分割**(**2026-09-17 の射程縮小で更新** — 計画レビュー 5・6 周目):
**U-T1 = アプリ層の強制点のみ**(接続ロールの真正性 / `TenantContext` / 文脈束縛 / リポジトリ基底 / 迂回検査 /
キャッシュ無効化契約)/ **TSK-424 = ロール・RLS・許可プロファイル・最低要求 ①** /
**U-C1・U-C3 = 共有経路の越境関数・関数 ACL・`search_path` / U-C2 = 制御情報読み取り / U-A2 = システム管理経路**(②〜④)/
**TSK-344 = 揃った 4 件の実スキーマ再実行**。**12-8 の TSK-317 行は U-T1 完了時点でも「解消済み」にしない** —
残件・所有者・発効条件を明記して残す。
同 `:2531` が「**4 件はすべて DB ロール・関数 ACL・`search_path` に対する要求**であり、HTTP 経路に対する要求を
1 件も含まない。したがって **4 件は HTTP 経路を開かない PR でも判定できる**」と明示 — **まさに U-T1 の主題**。

### 4. 要件との対応 — スコープ 5 要素の根拠は要件書に無い

| U-T1 スコープ要素 | FR-034 の対応 | 機構の正本 |
| --- | --- | --- |
| app ロール接続 | **根拠なし** | `docs/design/data-model.md:198-233`(ロールを 5 つに分ける) |
| `set_config` による文脈束縛 | **根拠なし**(要件書に `set_config` の語は 0 件) | 同 `:308-332`(規律 5 項) |
| 未設定時 fail-closed | **根拠なし(誤対応に注意)** | 同 `:178`(ポリシーがなければ default-deny)・`:331`(`set_config` を発行せずにクエリすると 0 行) |
| 越境関数経由のリポジトリ基底 | **根拠なし** | 同 `:477-490`(`SECURITY DEFINER` の制限関数を唯一の越境経路に) |
| 迂回検査 | **根拠なし** | `docs/features/product-impl-unit-split/plan.md:267-277`(5 条件)・`:568` |

**重要な誤読の回避**: FR-034 の「**既定拒否の原則**」を DB の fail-closed の根拠に使えない。
要件書 `docs/requirements/requirements-pitchlog-2026-07-22.md:608` が
「本原則の射程は『FR-041 が新設する権限・経路』に限られ、**それ以外の権限源による既存のアクセスは本要件の射程外**」
と**明文で限定**している(原典で確認済み)。fail-closed の根拠は `data-model.md:178` / `:331` に置く。

**要件側が定める測定方法**(逐語):
- **NFR-010**(REQ:850): 「越境アクセスの自動テスト(**API直叩き含む**。CIに常設 → NFR-019)」
- **NFR-019(b)**(REQ:933): 合否は「FR-034 の認可行列どおりに通り、行列外はすべて404」。
  **発効条項**「対象となる経路が実装され…その時点をもって、**その経路について発効する**」
  → **U-T1 は入口を開かないので (b) の経路ごとの発効は無い**。要件と設計(`data-model.md:2530-2532`)は整合。
- **NFR-014**(REQ:869-870): DB 接続情報はリポジトリに含めず環境変数。測定は「リポジトリの走査・コードレビュー」
- **NFR-005**(REQ:818): 「要求で選択されていないテナントのデータを走査しない」← リポジトリ基底に効く

**DoD 6 項目のうち要件に根拠があるのは「NFR-019 の越境テスト」1 件のみ。** 残り 5 件は設計書・計画書由来
(集約 = `data-model.md:204` `:487` `:490` / 迂回検査 = `product-impl-unit-split/plan.md:568` /
テスト命名 = 同 `:466` / fail-closed 故障系 = `data-model.md:331-332` / conftest 0 行 = 同 `:465` `:482`)。

### 5. 【最重要】DB 層では塞げない — テナント文脈の**真正性**は U-T1 の射程外

既存テスト `backend/tests/db/test_authz_trust_boundary.py:1-5`(docstring 逐語):

> テナント GUC に残る信頼境界の残余リスクを実 PostgreSQL で示す。
> **アプリ用ロールが任意のテナント文脈を設定できてしまうことを期待値にする。**

同 `:87` `test_app_role_can_spoof_tenant_context_only_with_matching_grants`
(docstring「**app_role が他テナントを設定でき、その付与を利用できてしまう**」)。

契約側の宣言 `contracts/authz/boundary-proposal.json:43-47`(逐語):
```
"trust_boundary": {
  "app_tenant_context": "trusted_input_set_only_by_authenticated_api",
  "db_connection_to_attacker": false,
  "verification_owner_task_id": "TSK-217"
}
```

残余リスク `contracts/authz/verification-evidence.json:17-38`: `RES-01` / `RES-03` はいずれも
`db_layer_verifiability: "not_verifiable"`、典拠の逐語は「**DB 層では塞げない**」「DB 層のカタログ検査では検出できない」。

→ **U-T1 が DB 層で保証できるのは「`set_config` を出さなければ 0 行」(fail-closed)まで。**
**「`app.tenant_id` に入る値が認証済みの主体のものであること」は API 層の責務**であり、
検証の所有者は **TSK-217** と宣言されている。**U-T1 の計画書はこの境界を明示し、**
**「越境の強制点を 1 本に集約する」の意味を「値の真正性」ではなく「経路の一本化」に限定して書く必要がある。**

### 6. 実装入力として使える既存資産(パスとキー)

| U-T1 の要素 | 使える既存資産 | 状態 |
| --- | --- | --- |
| **app ロール接続** | `contracts/authz/ddl-elements.json:37-101`(`roles[]` 7 件)。`app_role` は `:56-64`(`login:true` / `bypass_rls:false` / `inherit:false`)。SQL は `contracts/authz/function-bodies/roles/app_role.sql:4-5` | **probe 構成として確定** |
| **`set_config` 文脈束縛** | `contracts/authz/function-bodies/predicates/PREDICATE:CURRENT_TENANT_OWNS_ROW.sql:4-11`。**fail-closed の既存規範形** = `:7` `COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::BIGINT, FALSE)` | **規範形が確定** |
| **RLS ポリシー** | `ddl-elements.json:230-297`(6 件・全て `command: ALL` / `role_ids: [app_role]` / USING・WITH CHECK ともに上記述語)。`tables[]` `:130-223` は全件 `rls_enabled: true` / `force_rls: true` | **probe 構成として確定** |
| **`search_path`** | `ddl-elements.json:305-309` / `:358-362` / `:411-415`(3 関数とも `["pg_catalog", <private schema>, "pg_temp"]`)。規範は `:713-717`(`PLAN-PG-TEMP-LAST`)・否認例は `contracts/authz/rejected-configs.json:34-46`(`REJ-003`) | **確定** |
| **関数 ACL** | `ddl-elements.json:452-629`(`acl_expectations[]` 17 件)。関数 3 件は `:600` `:610` `:620`。`public_execute: false` は `:350` ほか。SQL は `contracts/authz/function-bodies/acl-expectations/*.sql`(17 件) | **確定** |
| **越境関数(唯一の越境経路)** | `ddl-elements.json:298-451`(`functions[]` 3 件)。SQL は `function-bodies/functions/`(3 件) | **確定** |
| **ロール別接続の実装** | `backend/tests/db/conftest.py` に既存。`_authz_login_role_ids()`(:134)・名前付き fixture `app_role_connection`(:717) ほか。**identity guard** `verify_connection_identities`(:263-298、autouse)が `SET ROLE` 偽装を封じる | **テスト側は実装済み** |
| **製品側の物理 DDL 書式** | **無い** | **未確定** |
| **probe → 製品の写像** | **無い**(fixture のみ) | **未確定** |

### 7. 製品コード側の現状 — 受け皿がまだ無い

- `backend/src/pitchlog/authz/` の 3 ファイル(`ddl.py` 229 行 / `provisioning.py` 701 行 / `catalog.py` 1456 行)は
  すべて **probe 側の道具**(DDL を生成・適用・検査する)。**ランタイムの認可実装は無い。**
- `backend/src/pitchlog/db/tenant_isolation/` は `models.py`(ORM のみ)と docstring 1 行の `__init__.py` のみ。
- **製品コードに `set_config` / `current_setting` / `SET ROLE` は 1 件も無い**(`backend/src/pitchlog/` 全体)。
- **`Session` / `sessionmaker` / リクエストスコープ依存も無い。** engine 生成は
  `backend/src/pitchlog/db/engine.py:75-91` の `create_database_engine()` が唯一の点
  (`:91` `return create_engine(normalized_url, connect_args=connect_args)` — ロール別 DSN や
  `event.listen` を差し込むならここ)。
- 「未設定時 fail-closed」の既存パターンの雛形は `backend/src/pitchlog/db/config.py:8-25`
  (`require_database_configuration` — 未設定/空で例外)。
- alembic は**別変数**を使う前例あり: `backend/migrations/env.py:23`
  `_MIGRATION_DATABASE_URL_VARIABLE = "PITCHLOG_MIGRATION_DATABASE_URL"`。

### 8. U-T1 に掛かる既決の制約(`docs/features/product-impl-unit-split/plan.md:460-468`)

- `backend/pyproject.toml` / `uv.lock`: **依存追加禁止**(要るなら単独 PR)
- `backend/src/pitchlog/db/`: **1 ファイルも足さない**。新規は `api/` `services/` `repositories/` `sync/` `domain/` のみ
- `backend/tests/conftest.py`: 1 行でも編集したらコア。**現状 9 行・DB 記述ゼロ**(実測)なので 0 行差分は無理なく満たせる。
  DB 側 fixture は `backend/tests/db/conftest.py` に完全分離済み
- `test_authz*`: **U-T1 は意図的に `test_authz_tenant_binding.py` と命名**して機械判定を効かせる(同 `:466`)
- `contracts/authz/*` の `test_owner` 既存行は書き換えない(再割り当ては TSK-380 待ち)

**コア判定の機構**(実測): `.claude/core-areas.json` の `tenant-isolation` は `:288-348`。
照合は `scripts/core_guard.py:222-227` の `fnmatch.fnmatchcase` で、**`*` が `/` も食う**ため
`backend/*conftest.py` は `backend/tests/conftest.py` と `backend/tests/db/conftest.py` の**両方**に、
`contracts/authz/*` は `function-bodies/**` 全部にマッチする。
→ **U-T1 が触る箇所はパス判定でも意味判定でも無条件にコア領域。**

**注意**: `backend/src/pitchlog/db/` 配下の paths は**個別ファイル列挙**なので、
仮に新規ファイルを置いても tenant-isolation のコア判定には**自動では入らない**
(`.claude/core-areas.json` 自体が `guard_paths` にあり、paths 追加は設計書 6.3-⑤ の敵対レビュー + 人間承認の対象)。
ただし上記のとおり `db/` には 1 ファイルも足さない制約があるため、置き場は `repositories/` になる。

### 9. 封印資産に触れるときの追随(実測)

`contracts/authz/ddl-elements.json` は `contracts/authz/oracle-seal.lock.json:40-77` の
`sealed_assets`(6 件)に `canonical_sha256` で封印されている。変更すると
`backend/tests/test_authz_mutation_composition_full.py:51` `:91` `:122` が赤になり、
`--reseal-oracle` + **人間レビュー必須**(`oracle-seal.lock.json:84-88`)。
`contracts/authz/failure-injection-points.json:4-7` も `ddl-elements.json` の `git_blob_digest` を固定しており追随が要る。
また `backend/src/pitchlog/authz/ddl.py` には **SQL 断片・資産識別子リテラルを書けない**
(`backend/tests/test_authz_ddl.py:181` の AST 検査)。SQL は `contracts/authz/function-bodies/` 側に置く運用。

### 裁定した点(エージェント報告の突き合わせ)

1. **「構成要素 4 つを TSK-317 へ送っている」** — decision-tracer が「一部成立」と報告。12-8 節の表を自分で確認し、
   TSK-317 名指しは 2 行のみであることを追認。**TSK-418 の記述は数え方が緩い**が、結論は変わらない。
2. **U-T1 のマージ可否** — 調査の途中で「TSK-344 に依存する」と見立てたが、`product-impl-unit-split/plan.md:433-443`
   の【承認後の是正】を原典で読み、**誤りと確定**(対象外・TSK-344 を待たずマージ可)。Notion カードのほうが古い。
3. **FR-034 の既定拒否の射程** — spec-checker の指摘を REQ:608 で逐語確認。**射程限定は明文**。
4. **`fnmatch` の `*` が `/` を食う** — `scripts/core_guard.py:226` で確認。
5. **`app_role` のテナント文脈偽装** — `test_authz_trust_boundary.py` の docstring と
   `boundary-proposal.json:43-47` を直接確認。**残余リスクとして期待値に固定済み**。

## 未解決・申し送り

### U-T1 の計画書が決めなければならないこと

1. ~~**probe → 製品の写像をどうするか。**~~ → **決定 2 度目(2026-09-17・山田正輝): TSK-424 へ分離した。**
   最初は「U-T1 に取り込む」と決めたが、**計画レビュー 4 周で P0 が 5 → 5 → 3 → 3 と収束せず**、
   残った P0 が**製品の認可面ぜんたい(45 表 × 許可プロファイル × 所有単位)**で
   **U-C1 / U-C2 / U-C3 / U-A1 / U-A2 にまたがる**ことが判明したため、
   [TSK-424 製品認可面の確定](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc) へ分離した。
   **以下は最初の決定の記録(参考)**: U-T1 に取り込む。
   TSK-418 の「やること 1・2」(実装入力の名指し・写像規則)を**本タスクの先頭ステップ**に置き、
   TSK-418 には「カードへの依存追記」(やること 3)だけを残す。
   **恒等写像は成立しない** — probe 側は `probe_business_rows` 等、製品側の ORM は
   `Tenant` / `TeamRecord` / `Player` 等(`backend/src/pitchlog/db/tenant_isolation/models.py`)で
   名前も粒度も違う(`docs/worklog/2026-09-04-data-model-canonical.md:65` の「製品スキーマ化されれば
   写像資産は不要になり得る」という条件は、現時点では満たされていない)。**U-T1 の見積は膨らむ。**
2. **製品スキーマの物理 DDL 書式**(probe の `probe_business_rows` 等に対応する製品テーブルは何か)。
   `ddl-elements.json` の `app_role` に `DELETE` があるが正本 3-2 節のアプリ用ロールは `SELECT/INSERT/UPDATE` のみ
   → **引き渡し時に判断が要る**(`docs/features/pg-authz-verification-g3/design.md:385-387`)。
3. **迂回検査の検索式の確定。** `docs/features/product-impl-unit-split/plan.md:275-277` が
   「検索式は『候補』であり、**確定は各単位の計画書が行う**(語彙は実装が生まれるまで固定できない —
   現在 `backend/src` に製品コードが 0 行)」と明記。**U-T1 の計画書の責任**。
4. **スキーマ検査の合格述語の置き場。** 現在の記述は正本でも `contracts/` でもなく
   feature 文書(`docs/features/pg-authz-verification-g3/catalog-check-map.md`)にある。
   U-T1 が製品側の検査を書くとき、述語の正本をどこに置くか。
5. **Notion カード TSK-390 の「マージの条件」節の是正**(上記 3 節)。TSK-418 の DoD にも
   「`U-T1` のカードへ依存を追記した」がある — **TSK-418 の射程と重なる**。

### 本タスクの射程外と確認できたこと

- **テナント文脈の値の真正性**(`app.tenant_id` に入る値が認証済み主体のものか)= **TSK-217**
  (`contracts/authz/boundary-proposal.json:46`)
- **実スキーマへの RLS 適用と越境テスト再実行** = **TSK-344**(裁定 `A-2`・`docs/design/data-model.md:2846`)
- **`contracts/authz/` の `test_owner` 再割り当て** = **TSK-380**(`docs/adr/ADR-004-merge-gate-scope.md:43-47`)
- **「入口を開く」の機械判定** = **TSK-383**(同)

### 不明(典拠を確認できなかったもの)

- **製品スキーマの物理 DDL 書式を定めた資産・記述**は、リポジトリ内に確認できない。
- **「U-T1 が引き渡し 3 資産のどの部分を入力とするか」を名指しした記録**は存在しない
  (`docs/features/pg-authz-verification-g3/research.md:269-272` が「未裁定である」と結論)。
- **TSK-317 全体(カード)の完了判定** — `docs/features/pg-authz-verification-g3/plan.md:35` は「進行中」と書くが、
  改訂 4 の成果は develop に landed している(PR #66)。**Notion 側の状態は未確認。**
