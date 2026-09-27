---
feature: product-rls-boundary-tests
type: research
date: 2026-09-24
---

# 調査メモ: 製品テーブルの RLS 適用と越境テスト(TSK-344)

先行調査: [research-dod-revision.md](research-dod-revision.md)(274 行 — TSK-381 の成果を持ち込んだもの)

## 問い

1. **条文**: 12-4 ゲートの通過条件・`non-serving` 宣言と解除・最低要求 4 件・NFR-010/019 の測定方法。**DoD 現行化の結論は今も成り立つか**
2. **決定経緯**: TSK-317 が確定させた範囲・TSK-424 が出す資産の形・RLS プロファイルの既決・**U-A1 との境界**・migration への DDL 追加の可否
3. **既存資産**: probe の RLS ポリシー・適用器・越境テストの構造・fixture・CI の DB ジョブ

**調査方法**: 調査サブエージェント 3 本(spec-checker / decision-tracer / Explore)を並列委任し、**結論に効く事実は当方が原典で再実測した**。
`legacy-analyst` は使っていない — RLS とロール設計は旧システム(SQLite / Supabase)に対応物が無く、旧資料から引ける事実が無いため。

> **【失効の明示 — 2026-09-27・敵対レビュー 2 周目 P1-8】**
> **本書は初回調査時点の結論であり、下記 4 点は計画書の 1 周目是正で失効している。**
> **現況は `plan.md` が正である。**
>
> | 本書の記述 | 現況 |
> | --- | --- |
> | 認証テーブルの帰属は未決(`:26`) | **解消** — **TSK-424 が所有**し `function_only` と分類済み。関数側は U-A1(1 周目 P0-3) |
> | `contracts/authz/product/` は develop に無い(`:161`) | **develop へ着地済み**(2026-09-27 実測) |
> | 射程・認証帰属が人間裁定待ち(`:217`) | **解消**(1 周目 P0-2・P0-3・P0-6)。**最低要求 4 件の線引きも 2026-09-28 の裁定で解消**(`plan.md` 7 節 #3)。**本書に残る「人間裁定待ち」はすべて失効している**(**4 周目 P2-11 の是正**) |
> | 表分類と `route_kind` の所有者が未確定(`:228`) | **route_kind は解消** — TSK-446 として起票し `record_and_aggregate` を実装済み。**表分類は TSK-424 が所有** |

## 結論(要約)

1. **⚠ 着手時に本計画書へ書いた射程は誤りだった。** 既決は「**作成と初回実行 = TSK-424(使い捨てクラスタ)/ TSK-344 = 実スキーマで再実行**」である
2. **TSK-344 は migration に RLS を足す側ではない。** 既決は「**適用経路は migration ではない**」で、適用器は `apply_authz_ddl`
3. **TSK-344 は TSK-424 の完全な下流**。424 が資産(PR A)と適用器・実 DB 試験(PR A2)を出さないと何も実行できない
4. **`non-serving` の「解除」は正本に対応条文が無い**(全数確認)。DoD 6 は**条文への写像**に留める(PO 裁定)
5. **認証テーブルの RLS の帰属は決定が存在しない**(全文探索で 0 件)。**人間の裁定が要る**

## 詳細と典拠

### 1. 射程 — 作成は TSK-424・再実行が TSK-344(当方の裁定)

[`../tenant-boundary-enforcement/design.md`](../tenant-boundary-enforcement/design.md)`:335-345` の逐語:

> ### 4-1. 使い捨てクラスタへ適用して試験する(**所有は TSK-424** — 5・6 周目の裁定で移管)
> **TSK-344 との切り分け**: `docs/design/data-model.md:2846` は TSK-344 の射程を
> 「越境テスト再実行ゲートの実行(**実スキーマに対する再実行**)」と書いている。
> **「再実行」である以上、作成と初回実行はこちら側にある** — 同 `:2845` が TSK-317 へ送った範囲も
> 「RLS ポリシー・ロール DDL の実機確定**と越境テストの作成・実行**」である。
> → **本単位: 使い捨てクラスタで作成・実行 / TSK-344: 実スキーマで再実行。** 矛盾しない。

正本側も同じ切り方である:

| 範囲 | 受け取り先 | 典拠 |
| --- | --- | --- |
| RLS ポリシー・ロールの DDL の実機確定**と越境テストの作成・実行** | **TSK-317**(→ 5・6 周目の裁定で **TSK-424** へ移管) | `../../design/data-model.md:2845` |
| 越境テスト再実行ゲートの**実行**(実スキーマに対する再実行) | **TSK-344** | 同 `:2846` |

**TSK-424 の計画書も同じ**: 「やらないこと」に「**実スキーマへの適用と、越境テストの再実行** → TSK-344(`data-model.md:2846`・裁定 A-2)」
(`feature/product-authz-surface` ブランチの `docs/features/product-authz-surface/plan.md`)。

**→ 本タスクの実体は「TSK-424 が作った資産と試験を、実スキーマに対して適用・再実行し、ゲートの判定を記録する」。**
着手時に書いた「RLS を製品テーブル 20 数枚へ展開する + 製品テーブルの越境テストを新規に書く」は**誤り**である。

**ただし条文に矛盾が埋まっている**: `data-model.md:2846` 自身が「**越境テスト自体がまだ存在しない**」と書いており、
**誰かが書かねばならない**。この矛盾の解消には裁定が要る(§7 #2)。

### 2. 適用経路は migration ではない(当方の裁定)

同 `design.md:327-333` の逐語:

> ## 4. 適用経路 — migration ではない
> 裁定 `A-2` により alembic migration は `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` を **0 件**に保つ
> (`docs/features/orm-schema-migration/plan.md:848` の `D7`。実測でも該当 0 件)。
> → 製品の RLS・ロール DDL は migration の外で適用する。適用器は既存の
> `backend/src/pitchlog/authz/provisioning.py`(`apply_authz_ddl`)を 3-3 の一般化を経て使う。

**実測**: `backend/migrations` 配下に `ROW LEVEL SECURITY` / `CREATE POLICY` / `CREATE ROLE` / `GRANT` / `REVOKE` が **0 件**
(生 SQL 167 箇所はすべて不変性強制の plpgsql トリガと列型是正)。

**→ 本タスクは `backend/migrations/` の差分 0 行を不変条件に置く。**足すと `D7` と U-T1 の設計判断の双方に逆行する。

**注意**: この 4 節は正本ではなく feature 設計書で、**所有は TSK-424 へ移っている**。
**424 の PR A が別の適用経路を選べば変わりうる**ので、PR A の着地時に再確認する。

### 3. 本番適用経路が存在しない(実測)

`apply_authz_ddl` の呼び出しは**すべて `backend/tests/` から**である(実測 — `db_fixtures.py:665,667` /
`test_authz_provisioning.py` / `test_authz_failure_injection_points.py` / `db/authz/mutation_execution.py`)。
**製品コードからの呼び出しは 0 件。**

→ 「実スキーマへ適用されている」(通過条件①)を**どの経路で満たすか**が未設計。
**424 PR A2 が「適用器」を持つ**ので、本タスクはそれを実スキーマへ当てる側になる。

### 4. probe の述語は製品へコピーできない(実測)

probe の 6 ポリシーは全部この形で、**型が `BIGINT`** である:

```sql
COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::BIGINT, FALSE)
```

probe 表の DDL に**設計意図がコメントで明記**されている:

```sql
-- TYPE-DESIGN: tenant_id は probe fixture で決定的な値を簡潔に扱える BIGINT とする。
    tenant_id BIGINT NOT NULL,
```

対して製品は **`TenantMixin.tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)`**
(`backend/src/pitchlog/db/mixins.py:18`)。

**→ 製品述語は `::UUID`。`COALESCE(...)` と `NULLIF(...,'')` の骨格は維持する**
(`../tenant-boundary-enforcement/design.md:97-109`)。**probe の述語をそのまま写さない。**
なお `probe_groups` だけは `EXISTS` 相関サブクエリ形(`tenant_id` 列を持たない表の扱い)。

### 5. 12-4 ゲートの条文(spec-checker — 逐語)

| 行 | 内容 | 典拠 |
| --- | --- | --- |
| **適用単位** | **当該 PR が開く入口ごとに判定する**(裁定 A)。**当該 PR が開いていない入口を理由に不合格と判定しない** | `../../design/data-model.md:2528` |
| **通過条件** | **① RLS のポリシーとロールの DDL が実スキーマへ適用されている ② その実スキーマに対して越境テストが green** | 同 `:2529` |
| **最低要求 4 件** | ① アプリ用ロールが関数を経由せず他テナント行を読めない ② `PUBLIC` が越境関数を実行できない ③ `search_path` の乗っ取りが効かない ④ 対象側が非共有なら要求元が付与していても返らない | 同 `:2530` |
| **4 件と測定経路の関係** | **4 件はすべて DB ロール・関数 ACL・`search_path` に対する要求**で **HTTP 経路に対する要求を 1 件も含まない**。**4 件は HTTP 経路を開かない PR でも判定できる**。**4 件の文言は変えない** | 同 `:2531` |
| **測定経路** | **入口を 1 つも開かない PR に対しては、この要求は空である**。**空であることは要求の免除ではなく、要求を当てる対象が無いこと** | 同 `:2532` |
| **本書の責務** | ゲートの定義まで。**再実行の契機は「実スキーマの適用」「本書の改訂」「入口を開く PR」の 3 つ** | 同 `:2533` |
| **判定の記録** | 誰が・いつ・どの実スキーマに対して green を確認したか・**どの入口について判定したか**(経路識別子と入口を一意に指す値の**両方**)。**入口を 1 つも開かない PR は「対象入口なし」と書く — 項目を省かない** | 同 `:2534` |

**入口の定義**(同 `:2438`): **製品の外からの要求を受け取り、DB のデータへ到達する 1 本の口**(HTTP なら method と path の組)。
**本タスクの PR は入口を開かない** — 現在の HTTP 入口は `/health` と `/version` の 2 本だけで、いずれも DB へ到達しない(同 `:2494` により「開かない」)。

**→ DoD 4(API 直叩き)は空。DoD 5 は「対象入口なし」の記録義務が残る。**

### 6. `non-serving` の解除は正本に条文が無い(spec-checker・全数確認)

- `data-model.md` 全文で「解除」は **1 件のみ**で `:1173` の「DH 解除」(無関係)
- non-serving 第 1 項「**利用経路を開かない**」に**終期を与える条文は無い**
- 第 2 項は一回性の条件ではなく **PR ごとの継続的条件への参照**(同 `:2528`「本ゲートは PR ごとに判定する」)
- **`SP-06`「RLS を初日から全テーブルに掛ける」(`:2698`)と 12-4 の射程外宣言(`:2505`)の字面衝突は TSK-382(着手可)の所有**([`../../adr/ADR-004-merge-gate-scope.md`](../../adr/ADR-004-merge-gate-scope.md)`:44`)

**→ 本タスクが踏んではいけないのは「`SP-06` と 12-4 の整合をとる作業」と「non-serving 第 1 項に終期を与える作業」。**
書けるのは「12-4 のゲートを通ったことを PR に記録した」という**条文への写像**まで(PO 裁定)。
先例: TSK-343 も同じ衝突に当たり「本計画は 12-4 の non-serving 宣言を優先根拠に置く。字面の差は申し送る」で回避した
(`../orm-schema-migration/plan.md:250-251`)。

### 7. RLS プロファイルは定義済み・割り当ては未確定(decision-tracer)

**所有は TSK-424**(2026-09-17・山田正輝の裁定で U-T1 から分離)。定義は
[`../tenant-boundary-enforcement/design.md`](../tenant-boundary-enforcement/design.md)`:137-143`:

| プロファイル | 対象の例 | RLS | 述語 | アプリ用ロールの ACL |
| --- | --- | --- | --- | --- |
| **P1 `tenant_owned`** | `TenantMixin` 継承表(実測 27 クラス) | ENABLE+FORCE | `COALESCE(tenant_id = ...::UUID, FALSE)` | `SELECT`/`INSERT`/`UPDATE` |
| **P2 `self_tenant_row`** | `Tenant` | ENABLE+FORCE | `COALESCE(id = ...::UUID, FALSE)` | `SELECT`/`UPDATE` |
| **P3 `effective_group_control`** | `AnalysisGroup` / `SharingGrant` / `GroupInvitation` / **`GroupMembership`** | ENABLE+FORCE | 自テナントが実効参加を持つ実効グループの行だけ(正は `data-model.md` 3-0 節) | `SELECT` |
| **P4 `global_read_only`** | `SystemVocabulary` / `AdminVocabulary` / `SystemSetting` | ENABLE+FORCE | 行を絞らない読み取り専用 | **`SELECT` のみ** |
| **P5 `app_denied`** | `AdminCredential` / `AdminSession` / `AdminOperationLog` | ENABLE+FORCE | **ポリシーを置かない** | **ACL を与えない** |

- **全プロファイルで `ENABLE` + `FORCE`**。「RLS を掛けない」ではなく「掛けたうえで許可を与えない」
- **P5 の期待は「0 行」ではなく `42501` 権限拒否**
- **分類は `TenantMixin` からは導けない**(`GroupMembership` が `TenantMixin` 継承の制御資源)。
  母集合は `Base.metadata` から自動導出、意味分類は **`contracts/authz/product/table-classification.json`**
- **合格述語**: 表ごとに `{許可プロファイル, ACL, 対象コマンド, roles, USING, WITH CHECK}` が exact-set。**`WITH CHECK` も必須**
- **期待 SQLSTATE**: `WITH CHECK` 違反 = `42501` / P5 アクセス = `42501` / 不正 UUID = `22P02` / `USING` で見えない = 0 行

**⚠ 5 種では 45 表を覆えない** — TSK-424 への P0 引き継ぎに明記(同 `:595`):
`TenantCredential` は `tenant_id` を持たず `TenantAuthSubject` 経由 / `RateLimitCounter` は認証主体の確定前に読み書きするグローバル可変表
→ **「親表経由のテナント所属」「認証前グローバル可変」のプロファイル追加が要る**。

### 8. TSK-424 が出す資産の形(受け取る入力)

**`contracts/authz/product/` は develop に未存在**(実測)。入力仕様の典拠は U-T1 の設計書(`:253-258`・`:315-323`):

```
contracts/authz/product/ddl-elements.json          製品側の DDL 要素(roles/schemas/tables/policies/acl)
contracts/authz/product/probe-product-map.json     probe 原子要素 ID ↔ 製品原子要素 ID(両方向 exact-set)
contracts/authz/product/table-classification.json  全 ORM 表の分類
contracts/authz/product/function-bodies/           製品側 SQL 本体 + manifest.json
```

- **生成先モジュール = `pitchlog.authz.runtime_contract`**(U-T1 はこのモジュールだけを import)
- **二状態契約**: `contracts/authz/product/ddl-elements.json` の**存在そのものが暫定→本番の切替条件**。
  存在する場合、`provisional: true` と旧暫定値への参照は red
- `contracts/authz/*` は `fnmatch` の `*` が `/` を食うため**この配下も自動でコア判定**に入る

**現状の暫定値**: `backend/src/pitchlog/authz/runtime_contract.py` が `PROVISIONAL = True` /
`SUPERSEDED_BY = "contracts/authz/product/ddl-elements.json"` / `APPLICATION_ROLE_NAME = "pitchlog_app"` /
**`PROTECTED_TABLES` = 45 タプル**(`contracts/db/schema-manifest.json` の 45 表と同順・同名)。

### 9. テスト基盤の制約(Explore・実測)

- **ロール切り替えは `SET ROLE` を使わない** — ロールごとに**独立した接続をそのロール自身のパスワードで新規認証**し、
  autouse fixture `verify_connection_identities` が `session_user` / `current_user` を照合
- `backend/tests/db/environment-expectations.json:146-194` が固定するもの:
  **`required_marker = requires_db`** / **`required_path = backend/tests/db/`** /
  **`single_command = uv run pytest -c pyproject.toml --cov`**(`marker_selection_argument_allowed: false`・
  `additional_db_test_invocation_allowed: false`・`expected_backend_pytest_invocation_count: 1`)/
  **`missing_dsn_policy = fail`**(`skip_allowed: false`)
- `backend/tests/db/conftest.py:100-119` が **DB 必須テストの 0 件収集・0 件実行を `TESTS_FAILED` にする**(skip 逃げの禁止)
- **`provisioned_catalog` は probe 資産適用専用**。**製品表とロールを同居させる fixture は新設が要る**。
  製品表を実 DB に出す前例は `test_schema_audit.py:770-775` の `disposable_postgres_cluster` + `alembic upgrade head`
- **CI の `backend` ジョブ**は `postgres:17.11-bookworm` の service container + 3 つの DSN 環境変数。
  **`fetch-depth: 0` が必須**(`manifest.json` の `source_commit` 解決のため)。**runner 上で `docker` が使える必要がある**
- `ddl-elements.json` は `oracle-seal.lock.json` で**封印済み**(`--reseal-oracle` + 人手レビューが必要)。
  `scope.product_schema: false` と明示 → **製品側は別ファイル**

### 10. 最低要求 4 件の帰属(decision-tracer)

`../tenant-boundary-enforcement/design.md:575-581`:
**① = TSK-424 / ②③④ のうち共有関数分 = U-C1・U-C3 / 管理関数分 = U-A2 / 揃った 4 件の実スキーマ再実行 = TSK-344**。

**→ 本タスクの DoD「最低要求 4 件を覆っている」を単独で閉じると U-C1 / U-C3 / U-A2 の射程を踏む。**
「TSK-424 が出した ① と、②③④のうち製品へ写せる分」の線引きが要る。

### 11. 踏んではいけない他タスクの射程

| 範囲 | 所有 | 典拠 |
| --- | --- | --- |
| `SP-06` と 12-4 の字面衝突 | **TSK-382**(着手可) | `ADR-004:44` |
| **`data-model.md` 12-8 節の実装追随** | **TSK-424** | `../tenant-boundary-enforcement/plan.md:79`・`:125` |
| 12-8 の TSK-317 行 | **「解消済み」にしない。残件・所有者(U-C1/U-C3/U-A2)・発効条件を明記して残す** | 同 `design.md:583-586` |
| 表分類・プロファイル割り当て | **TSK-424** | 同 `design.md:595` |

## 未解決・申し送り

### 人間の裁定が要るもの

1. **【射程】本タスクの実体をどう確定するか** — 既決は「作成 = TSK-424 / 再実行 = TSK-344」だが、
   `data-model.md:2846` 自身が「**越境テスト自体がまだ存在しない**」と書いており**誰かが書かねばならない**。
   (a) TSK-424 が作った試験を実スキーマで回す形にする / (b) 踏む範囲を PO 裁定で明示的に取り込む のいずれか
2. **【帰属】認証テーブルの RLS を誰が持つか** — **決定が存在しない**(全文探索 0 件)。
   `tenants` / `tenant_auth_subjects` / `tenant_credentials` / `tenant_tokens` / `admin_credentials` / `admin_sessions` / `rate_limit_counters`。
   隣接する既決は「**プロファイル確定 = TSK-424 / 適用と越境テスト = TSK-344**」で、**U-A1 の名は一度も出てこない**。
   U-A1 側の計画書も雛形のままで同じ穴を開けている
3. **【DoD】最低要求 4 件の線引き** — ②③④の所有が U-C1 / U-C3 / U-A2 にある(§10)

### 決定が存在しない(原典で確認できなかった)

- **45 表の表単位プロファイル割り当て表** — 未作成(TSK-424 の射程)
- **`route_kind` の値域決定の所有者** — 記録なし(`scripts/check_authz_catalog.py:92` の `ROUTE_KINDS` は 4 値固定で製品 CRUD を表す種別が無い)
- **TSK-382 の計画書・現在の状態** — リポジトリ内に feature dir なし

### 状態表記の古さ(着手前に PR 状態で確認する)

- `../pg-authz-verification-g3/plan.md:3` の frontmatter が `status: active` のまま。
  ただし `contracts/authz/claim-mutant-map.json` の placeholder `TSK-270-GROUP-2` は **0 件**(実測)なので PR #66 はマージ済みと読める
- `data-model.md:2846`「越境テスト自体がまだ存在しない」・`:2505`「RLS のポリシーとロールの DDL は本書の射程外」は v0.3(2026-09-13)時点の記述
