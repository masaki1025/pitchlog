---
feature: product-authz-surface
type: research
date: 2026-09-24
---

# 調査メモ: TSK-424 製品認可面の確定

**表記**: 本書で `design.md` とだけ書いた典拠は、U-T1 の `../tenant-boundary-enforcement/design.md` を指す(本調査は TSK-424 の design.md より前に書いた)。TSK-424 の設計は [design.md](./design.md) が正。

調査方法: /investigate で 4 本を並列に実施した(spec-checker / decision-tracer / Explore〔コード実測〕/ legacy-analyst〔移行制約〕)。エージェント間の食い違いと主要な主張は、原典を直接読んで裁定した(本文の「**原典確認済み**」)。対象は develop `e6bc0cc`。

## 問い

1. 正本と要件は、製品の認可面(全表の RLS・ロール・ACL)に何を要求しているか。Notion カードの DoD と食い違いはないか
2. 本タスクを縛る過去の裁定と、U-T1(PR #72)から TSK-424 へ引き継がれた未解決事項は何か
3. 実装の現状: 45 表の所属経路はどうなっているか。probe 資産の封印とツールチェーンのどこを差し替えるか。U-T1 の暫定定義はどこにあるか
4. 移行バッチ用ロール(裁定 A-3)の書き込み先・実行形態・所有者は何か

## 結論(要約)

- **全 45 表の所属は 6 通りに分かれる**。`tenant_id` を持つ表は 28、持たない表は 17(manifest の列から数え直した値。Explore の報告は 29 で誤り)。U-T1 の案 P1〜P5 では覆えない表が実在する(`tenant_credentials`・`rate_limit_counters`・`tenants`・`migration_*` 系など)。表ごとの所属を列挙した記述は正本に無い。したがって**表の固定は本タスクの計画で行い、正本に反しない形にする**(4-1)
- **製品資産は `contracts/authz/product/` へ新設し、probe 資産は 1 バイトも触らない**。ツールチェーンは 5 箇所以上で probe のパスと scope を固定している。特に `_validate_ddl_scope` が `product_schema: False` 以外を拒否するので、**一般化しないと製品資産は検査を通らない**(4-3)
- **U-T1 との往復契約は、テストの形で既に固まっている**。製品資産を置いた時点で、次の 3 つを同時に満たさないと red になる。① 製品資産に `runtime_contract` オブジェクト(8 フィールド)がある ② 生成モジュールが `PROVISIONAL=False` で、`SUPERSEDED_BY` が `None` ③ 暫定資産 `contracts/tenant_boundary/runtime-authz-contract.json` を削除した。③は、TSK-431 が持つ既知欠陥 7D(削除した資産の履歴を検査できない)にぶつかる(4-4)
- **人間の裁定が要る論点が 4 つある**: ① 移行ロールの所有が TSK-349 と TSK-424 に二重で、方式も正反対 ② SP-06 と 12-4 の字面衝突(所有は TSK-382)を踏まない線引き ③ 移行ロールの書き込み先 exact-set の閉じ方 ④ 正本 3-2 節の監査根拠(NFR-012)を直すかどうか(6 節)
- 適用経路は migration ではない(裁定 A-2・`D7`)。**TSK-424 は使い捨てクラスタで適用と検査を行う。実スキーマでの再実行は TSK-344 が行う**。TSK-424 は入口を開かないので、12-4 の判定記録には「対象入口なし」を必ず書く

## 詳細と典拠

### 1. 正本・要件の要求

#### 1-1. data-model.md 3 章(機構の正)

| 項目 | 要求 | 典拠 |
| --- | --- | --- |
| RLS の位置づけ | 要件から導いたものではなく、本書の設計判断。要件書・決定記録・改善台帳のいずれにも `RLS` は 0 件 | `docs/design/data-model.md:139-149` |
| 二重構成 | アプリ層の明示 `tenant_id` 条件を省かない | `:137`・`:181-188` |
| default-deny | ポリシーが無ければ拒否。既存行には USING、新規・更新後の行には WITH CHECK を適用 | `:178-179` |
| ロール | 5 つ: マイグレーション用(表所有者)/ アプリ用 / 共有関数所有用(NOLOGIN+BYPASSRLS)/ 管理関数所有用(NOLOGIN+BYPASSRLS)/ 移行バッチ用(LOGIN+BYPASSRLS・期間限定) | `:206-212` |
| アプリ用ロールの表権限 | **SELECT / INSERT / UPDATE のみ**。TRUNCATE と REFERENCES は与えない。DELETE は列挙されていない | `:209`(残余リスクの本文は `:438-439`) |
| 行の絞り込み | 権限ではなくポリシーで行う。共有集計用の越境 RLS ポリシーは作らない | `:229`・`:204` |
| 関数 ACL | 作成と同じトランザクションで PUBLIC から剥奪し、GRANT する。分割しない | `:242` |
| search_path | 設定は必須。`pg_temp` は末尾に 1 回だけ明示する(REJ-003) | `:243`・`:245` |
| FORCE RLS | **表現が揃っていない**。`:202` と `:272` は「全テーブルへ FORCE を掛けると**定める**」、`:263` は「掛けることを**推奨する**」(**原典確認済み**)。DoD は強い読み(全表必須)を採っており、SP-06(`:2698`)とも整合する | `:202`・`:263`・`:272` |
| テナント ID の受け渡し | トランザクション先頭で `set_config('app.tenant_id', :tenant_id, true)`。ポリシーは `current_setting('app.tenant_id', true)` を読む | `:319-323` |
| 制御資源 | テナントに属さない。ポリシーは「自テナントが実効参加を持つ実効グループの行だけ見える」形。述語の正は 3-0 節 | `:447-449`・`:101-133`・`:463-471` |
| 共有集計 | SECURITY DEFINER の制限関数が唯一の越境経路。バイパスの実体は、所有ロールが持つ BYPASSRLS | `:477-491` |
| probe と製品 | **別の層として扱う** | `:537` |

#### 1-2. 12 章(ゲートと射程)

- 12-4 の通過条件は 2 つ。① RLS ポリシーとロールの DDL が実スキーマへ適用されている ② その実スキーマに対して越境テストが green。最低要求は 4 件で、どれも HTTP に依らない。**4 件の文言は変えない** — `data-model.md:2529-2531`
- 適用単位は入口。入口を開かない PR では測定経路の要求が空になる。**判定の記録では「対象入口なし」を省けない** — `:2528`・`:2532`・`:2534`。バッチは入口を開かないが、4 件は掛かる — `:2492`
- 12-8 の受け取り先は TSK-317(`:2844`・`:2845`)と TSK-344(`:2846`)。**TSK-424 は data-model.md 内に 0 件**で、分離が正本へ未反映 — `:2842-2862`
- 最低要求 ① の所有は TSK-424、②③④ は U-C1/U-C2/U-C3/U-A2 — `docs/features/tenant-boundary-enforcement/design.md:577-581`。**所有の割り当てであって、条文の書き換えではない**(`:2531`)

#### 1-3. 要件書

- NFR-010: 他チームのデータは内容も存在も参照できない。**初日から全機能に適用する**。測定方法は越境の自動テスト(API 直叩きを含む)。実現層(RLS など)の指定は無い — `docs/requirements/requirements-pitchlog-2026-07-22.md:846-850`
- NFR-019(b): 合否は「FR-034 の認可行列どおりに通り、行列外はすべて 404」。発効条項により、**発効前の経路を理由に不合格としない**。ただし未発効は網羅の免除ではない — `:923-933`
- NFR-014: DB 接続情報はリポジトリに含めない。→ **DDL 資産にロールのパスワードを書かない** — `:867-870`
- FR-033(レート制限): カウンタの読み書き主体と認証前のアクセスは**定めていない**。制限の具体設計は未決事項 — `:590-597`
- Won't(個人アカウント・セルフサインアップ)・P-20・P-21 との衝突: 提案中の 2 プロファイル(親表経由・認証前グローバル)は主体を増やさないので、**衝突しない** — 要件書 `:96-110`、`data-model.md:1513`・`:1727`

#### 1-4. Notion DoD との突合

| DoD | 判定 | 典拠 |
| --- | --- | --- |
| 全表 ENABLE+FORCE | 適合(正本の語の揺れは 1-1 のとおり) | `data-model.md:202`・`:2698` |
| 全表で {プロファイル, ACL, コマンド, roles, USING, WITH CHECK} が exact-set | 正本は「検査対象集合と合格述語は実装が確定する」としている。**実装に送られた範囲の内側で、矛盾しない** | `:244`・`:2423-2425`・`:2845` |
| probe↔製品写像 | 正本は「別の層」とだけ書く。写像そのものの記載は無く、矛盾もしない | `:537` |
| 移行ロールの「5 条件」 | 正本の表は **6 行**(期間限定 / アプリから到達しない / DDL を持たない / 書き込み先の限定 / 監査 / 検査対象)。**実質の条件が 5 つ、6 行目は検査の手続き**と読む(**原典確認済み**)。計画では 6 行すべてを対応づける | `:288-297` |
| 使い捨てクラスタで green | 12-4 の「実スキーマ」の定義は正本に無い。「再実行」は TSK-344 なので、**作成と初回実行は TSK-424 の側**(4-5) | `:2846`・`design.md:335-345` |
| 12-8 の記録 | 追随が必要。**TSK-317 行を「解消済み」にせず**、残件・所有者・発効条件を明記する | `../tenant-boundary-enforcement/design.md:583-586` |
| probe 差分 0 行 / pyproject・uv.lock・conftest 差分 0 行 | 矛盾しない(どちらもコア領域の paths に含まれる) | `.claude/core-areas.json:295`・`:312-314` |

#### 1-5. tenant_id を持たない表について正本が定めていること

| 表 | 正本 | 判定 |
| --- | --- | --- |
| 分析グループ・参加・付与・招待 | 制御資源。3-0 節の述語 | 定めあり(`:447-471`) |
| `tenant_credentials` | 別表(認証主体 1 : 認証情報 1)。認証主体がテナントに属する | 所属のみ(`:385`・`:1516-1518`)。**RLS・認証前の読み取りは記載なし** |
| `tenants` | 有効/無効。**RLS ポリシーにテナントの有効性を含めない** | `:1490-1503`・`:1499`。**表自体のポリシーは記載なし** |
| `rate_limit_counters` | プロセス外の専用表。同じアクセス経路に混ぜない。物理削除しない | `:1704-1720`。**アクセス主体・認証前アクセス・RLS は記載なし** |
| 管理者資格情報・管理者セッション | 別表。テナント参照を持たない。管理関数所有用として扱う | `:1534-1543`。**アプリ用ロールの権限は記載なし** |
| 語彙(システム層・管理者層)・システム設定 | テナントに属さない | `:394-395`・`:1941-1954` |

**帰結(導出)**: default-deny(`:178`)と「全表に RLS」(`:2698`)を合わせると、ポリシーを持たない非テナント表にはアプリ用ロールが到達できなくなる。`rate_limit_counters` は認証前に読み書きするので、この帰結とぶつかる。正本にこの衝突を扱う記述は無い。

### 2. 過去の裁定と制約

| 裁定・決定 | 本タスクへの制約 | 典拠 |
| --- | --- | --- |
| 12-7 打ち切り(2026-08-22) | 最低要求 4 件。① が TSK-424 | `data-model.md:2749-2765` |
| TSK-317 第 1 群の oracle 凍結(2026-08-31) | **probe 資産を書き換えない**。変更すると `ORACLE_STEP5_REREVIEW` と `--reseal-oracle`(人手レビュー)が必要になる | `docs/features/pg-authz-verification/plan.md:375-376`・`:390`、`contracts/authz/oracle-seal.lock.json:40-88` |
| TSK-317 改訂 2 の R-1〜R-8 | 製品 DDL 資産の形に効くのは次の 5 つ。R-1(body digest)/ R-2(危険終点の exact-set)/ R-5(適用原子性の失敗点)/ R-6(PG17 の 8 権限を単一集合から生成)/ R-8(手順の順序) | `pg-authz-verification/plan.md:407-414` |
| 裁定 A-3(2026-09-08) | 移行ロールの 6 行の条件(1-4) | `data-model.md:268-306` |
| 裁定 A-2 → `D7` | migration の `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` を 0 件に保つ。**製品 DDL は migration の外で適用する** | `data-model.md:2846`、`docs/features/orm-schema-migration/plan.md:848` |
| ADR-004(2026-09-13) | 入口単位で判定する。入口を開かない PR には空の要求が掛かる。判定の記録は省けない | `docs/adr/ADR-004-merge-gate-scope.md:79-82` |
| 単位分割(2026-09-13) | 越境関数の本体・ACL・search_path は U-C1/U-C2/U-C3/U-A2 が持つ。本タスクは「空であること」を宣言として持つ | `docs/features/product-impl-unit-split/plan.md:224-227`、`../tenant-boundary-enforcement/design.md:286-294` |
| TSK-418 の取り込みと撤回・TSK-424 の分離(2026-09-17) | TSK-418 の「やること 1・2」(実装入力の名指し・写像規則)は TSK-424 が引き受ける | `docs/worklog/2026-09-17-tenant-boundary-enforcement.md:27-31`・`:70-73` |
| U-T1 計画レビュー 5・6 周目 | 製品 RLS の述語構造・未束縛 SQL が 0 行・不正 UUID の `22P02` は TSK-424 の受入条件。**物理識別子(schema, table, function identity_args)で出す**。capability も出力契約に含める | `tenant-boundary-enforcement/plan.md:86`、`design.md:310-325` |

(注: 調査の依頼文で挙げた「R-9」は authz 系の裁定ではなかった。TSK-335 系の「88 列写像の値は TSK-250 が決める」という別系列の記号で、本タスクには関係しない — `docs/worklog/2026-09-08-data-model-handoff-revision.md:304`)

#### 2-1. 再提案しない却下案

- **正本が却下したもの**(`data-model.md:190-196`・`:254-258`・`:299-306`): アプリ層だけで強制する / RLS だけで強制する / Supabase に寄せる / 関数所有ロールを表所有者にする / 越境 RLS ポリシーを置く / 移行バッチを表所有者で投入する / 移行中だけ FORCE を外す / 移行バッチも set_config で切り替えながら投入する / superuser で投入する
- **U-T1 のレビューで却下されたもの**(`tenant-boundary-enforcement/design.md`):
  - 分類を `TenantMixin` から導く(`GroupMembership` が反例)— `:163-171`
  - 一部の表を RLS 対象外にする — `:152-161`
  - P5 の期待を「0 行」にする(SELECT 付与を誘発するので、正しくは `42501`)— `:148-150`
  - 語彙と設定を P5 にする(通常機能が止まる)— `:145-146`
  - USING だけを検査する — `:182-192`
  - probe 述語を流用する / 製品述語をテスト内にコピーする — `:44`
  - 写像を片方向だけ検査する / 1 対多を 0 件にする / 「probe 側の未写像 0」を条件にする(充足できない)— `:78-87`
  - `ddl.py` だけを一般化する — `:263-281`
  - 製品 JSON を package data に含める / 作業ディレクトリ依存の相対参照 — `:307-308`
  - 移行ロールを「定常状態に存在しない」ことだけで済ませる — `:217-221`
- **封印済みの却下構成**(`contracts/authz/rejected-configs.json:14-46`): REJ-001(SECURITY DEFINER だけでは RLS をバイパスしない)/ REJ-002(関数の既定 PUBLIC EXECUTE)/ REJ-003(`pg_temp` の暗黙位置)

### 3. U-T1 から引き継いだ未解決事項

`tenant-boundary-enforcement/design.md` の 2〜4 節と 7 節は、TSK-424 の計画の入力になる(`:25-31`)。9 節の未解決は 7 件ある(`:588-601`):

| # | 種別 | 内容 |
| --- | --- | --- |
| 1 | P0 | プロファイル 5 種では 45 表を覆えない。**「親表経由のテナント所属」と「認証前グローバル可変」を追加し、45 表を計画段階で表として固定する** |
| 2 | P0 | `read_control_resources` 相当の受け取り先は U-C2。写像の `owner_unit` に U-C2 を含める |
| 3 | P0 | U-T1 との往復契約(4-4) |
| 4 | P1 | P2/P3 の実 DB 正負行列(P3 の 4 表 × member/admin/nonmember/terminated)と、P4 の書き込み `42501` |
| 5 | P1 | 移行ロールの監査の実効性。失敗したトランザクションでは監査行もロールバックされるので、**トランザクション境界を分け、失敗注入点を固定する** |
| 6 | P1 | 非写像の理由コードを全列挙する(適用できる原子要素種別・`owner_unit` つき) |
| 7 | P1 | ランタイム定数の生成手段(生成器・入力・出力・決定的整形・`--check`) |

設計の要点(design.md から):
- 原子要素は `role` / `schema` / `table` / `policy` / `function` / `acl_privilege`。写像の合格条件は `probe 全要素 = mapped ∪ explicit_non_mapping` の両方向 exact-set — `:76-95`
- 製品述語は `::UUID`。`COALESCE(..., FALSE)` と `NULLIF(...,'')` の骨格は変えない — `:97-110`
- **`app_role` に DELETE を与えない**。probe 資産は DELETE を持つ(`contracts/authz/ddl-elements.json:454`)が、正本(`data-model.md:209`)に従う。これは `acl_privilege` 粒の意図的な非写像として記録する — `:111-120`
- 分類は明示メタデータ `contracts/authz/product/table-classification.json` に置き、母集合は `Base.metadata` から導く。合格述語は 6 本 — `:163-181`
- 期待 SQLSTATE: WITH CHECK 違反 = `42501` / P5 = `42501` / 不正 UUID = `22P02` / USING で不可視 = 0 行 — `:182-202`
- 写像資産の二重正本: `scripts/design_relations/product-ddl-map-data-model.json`(TSK-250 が予告したが未作成)に対し、**本資産を正とし、TSK-250 側を導出にする**。TSK-250 の文書には未反映 — `:93-95`、`docs/features/data-model-canonical/plan.md:253`

### 4. 実装の実測

#### 4-1. 全 45 表の所属

母集合の正は `contracts/db/schema-manifest.json`。`backend/tests/test_schema_manifest.py:579-610` が manifest = models = `Base.metadata` の 45 表一致を検査している。`backend/src/pitchlog/authz/runtime_contract.py:38-84` にも 45 表が並ぶ。

| 所属の型 | 表 |
| --- | --- |
| **テナントの根(自身が tenant)** | `tenants` |
| **直接所属**(`tenant_id → tenants` の単列 FK) | `team_records`、`tenant_vocabularies`、`tenant_auth_subjects`、`tenant_tokens` |
| **親表経由の複合 FK**(`(tenant_id, x) → 親`) | `players`、`games`、`lineup_memories`、`game_lineups`、`participation_intervals`、`tournament_rule_assignments`、`event_slots`、`operation_events`、`play_rows`、`play_runners`、`temporary_player_id_mappings`、`rejected_event_originals`、`evacuated_event_originals`、`recording_generations`、`medical_notes`、`medical_note_versions`、`pdf_export_records`、`player_merge_events`、`player_move_records`、`migrated_final_lineups` |
| **`tenant_id` はあるが FK なし** | `idempotency_ledger`、`invalidation_intents` |
| **`tenant_id` を持たず、親経由でテナントに属する** | `tenant_credentials`(→ `tenant_auth_subjects`) |
| **制御資源**(テナント横断・cross_tenant FK) | `analysis_groups`、`group_memberships`(`tenant_id` あり・TenantMixin あり)、`sharing_grants`、`group_invitations` |
| **全体共有(読み取り)** | `game_type_rule_defaults`、`system_vocabularies`、`admin_vocabularies`、`system_settings` |
| **所有が混在する規則資源(直接アクセス不可)** | `rule_sets`(全体既定とチームの大会規則が同じ表に入り、所有者の列が無い)・`tournament_rule_assignments`(任意の規則セットを結べる)— 計画レビュー 6 周目で訂正。design.md 1-6 |
| **管理者経路** | `admin_credentials`、`admin_sessions`、`admin_operation_logs`(`tenant_id` は NULL 可。mixin は使わず直接宣言 — `tenant_isolation/models.py:673`) |
| **認証前グローバル可変** | `rate_limit_counters` |
| **移行専用(テナントなし)** | `migration_runs`、`migration_quarantine`、`migration_resolution_reports`、`migration_warning_reports` |

(各表の model の行・PK・mixin・論理削除列は、Explore の実測表による。manifest の表定義の開始行: `tenants` :27 〜 `migration_warning_reports` :1150)

- `tenant_id` が PK の先頭に来ない表: `tenant_auth_subjects`、`tenant_tokens`、`admin_operation_logs`、`group_memberships`
- **未決の分類が要る表**: `tenants`(自テナント行だけ見せるか)/ `rate_limit_counters` / `migration_*` 4 表(アプリから完全に拒否するか)/ `admin_operation_logs`(`tenant_id` が NULL 可の二面性)/ `idempotency_ledger`・`invalidation_intents`(FK が無い)。どれも正本に記載が無い(1-5)

#### 4-2. probe 資産と封印

- `contracts/authz/ddl-elements.json`: scope は `verified_probe_configuration` / `product_schema: false`(:9-12)。要素の内訳は roles 7、schemas 3、tables 6、predicates 1、policies 6、functions 3、acl_expectations 17、transaction_boundaries 3(:37-662)
- `oracle-seal.lock.json`: input_assets を git_blob_digest で、sealed_assets 6 件を canonical_sha256 で封印する。**function-bodies/ は封印に入らず**、`function-bodies/manifest.json` の blob_digest と source_commit で別途照合する
- probe の `tenant_id` と述語は BIGINT(`function-bodies/predicates/PREDICATE:CURRENT_TENANT_OWNS_ROW.sql:7`)。製品は UUID(`backend/src/pitchlog/db/mixins.py:18`)

#### 4-3. ツールチェーンの差し替え点

| 部品 | ファイル | 固定点 |
| --- | --- | --- |
| DDL 生成器 | `backend/src/pitchlog/authz/ddl.py` | `DDL_ELEMENTS_PATH` / `BODY_MANIFEST_PATH` / `BODY_CHECKER_PATH`(:12-14)。`generate_authz_ddl(root)`(:212)は root 以外の引数を持たない。**SQL 断片も資産識別子のリテラルも書けない**(`backend/tests/test_authz_ddl.py:181` の AST 検査) |
| body 検査器 | `scripts/check_authz_function_bodies.py` | `BODY_DIRECTORY`(:21)/ `DDL_ELEMENTS_PATH`(:23)/ `ELEMENT_SECTIONS`(:29-41)。CLI は `--root` だけ |
| 適用器 | `backend/src/pitchlog/authz/provisioning.py` | `apply_authz_ddl(connection, root)`(:685)。**手順ごとに commit しており、1 トランザクションではない**(:491・:527・:606・:625・:647、**原典確認済み**)。同じトランザクションで閉じるのは、関数の PUBLIC 剥奪と ACL 正規化だけ(:612-625) |
| DB カタログ検査 | `backend/src/pitchlog/authz/catalog.py` | `inspect_authz_catalog`(:1399)。危険ロールの導出 `_dangerous_role_ids`(:808-885)は資産の schema/table/function ID から危険所有者を導く → **製品資産は物理識別子を出す義務がある** |
| 静的検査 | `scripts/check_authz_catalog.py`(5854 行) | `DEFAULT_*` 定数(:30-46)。**`_validate_ddl_scope` は `product_schema: False` 以外を拒否する**(:2786-2806、**原典確認済み**)。probe の表名を直書き(:271・:303-332 ほか) |
| DB fixture | `backend/tests/db_fixtures.py` | `_load_ddl_asset`(:104)/ `disposable_postgres_cluster`(:555-615。`docker run --pull=never postgres:17.11-bookworm`)/ `provisioned_catalog`(:618-677) |
| 呼び出し元 | `backend/tests/db/` の authz 系 10 ファイル・`mutation_*.py` | probe 名の直書きは `mutation_execution.py` に 25 箇所、`test_authz_precondition_matrix.py` に 15 箇所 |
| 写像の射影 | `scripts/check_design_propagation.py:1109-1150` | `product_schema` が false のとき `product_ddl_map` を必須にする。本番の対応資産は無い |

**方針(U-T1 の design.md 3-3 の申し送り。TSK-424 では design.md 5 節)**: 資産指定オブジェクトで一般化する。既定値を probe 構成にし、既存テストは無改変で green を保つ。

#### 4-4. U-T1 の暫定定義と往復契約(テストが強制する形)

- 暫定資産: `contracts/tenant_boundary/runtime-authz-contract.json`。`provisional: true`(:67)/ `superseded_by: contracts/authz/product/ddl-elements.json`(:68)/ `application_role.rolname = pitchlog_app`(:71-82)/ `protected_objects`(schema 1・表 45・関数 33)
- 生成モジュール: `backend/src/pitchlog/authz/runtime_contract.py`(`PROVISIONAL = True`、`SUPERSEDED_BY` — :7-8、**原典確認済み**)
- **二状態テスト** `backend/tests/test_authz_runtime_contract.py:127-156`(**原典確認済み**): 製品資産が存在すると、次の場合に red になる。暫定資産が残っている(`PROVISIONAL_ASSET_REMAINS`)/ 生成物が provisional のまま / `SOURCE_ASSET` が製品資産ではない / `SUPERSEDED_BY` が `None` ではない。製品資産は `runtime_contract` オブジェクト(8 フィールド)を持つ必要がある(:79-84・:113-124)
- capability と越境関数 registry は空集合: `backend/src/pitchlog/repositories/repository_contract.py:57-59`(強制テストは `backend/tests/test_authz_repository_contract.py:261-266`)
- **暫定資産を削除すると `FROZEN_BASELINE_ASSETS` に当たる**: `scripts/check_tenant_boundary_bypass.py:37-45`(**原典確認済み**)。既知欠陥 7D(削除・移動で旧パスの履歴を検査できない — 所有は TSK-431、`tenant-boundary-enforcement/plan.md:106`)と、設計書 7.7-1「基準の削除も『動かす』に含む」(`docs/development/dev-harness-design-2026-08-07.md:553-577`)が掛かる
- **観測事実**: 暫定資産の履歴は `source_commit: PENDING_ACCEPTANCE`(:41)、`approved_by/on` は「未承認(PR #72 のレビュー待ち)」(:61-62)のままで、PR #72 のマージ後も更新されていない(**原典確認済み**)。検査器はこの値を定数として許容している(`check_tenant_boundary_bypass.py:49-50`)。更新する責任が誰にあるかは**不明**

#### 4-5. 適用経路・CI・コア領域

- `backend/migrations` に RLS・ROLE・GRANT・`set_config` は 0 件(Explore の全文検索)
- 分担: **TSK-424 = 使い捨てクラスタで製品 migration と製品 authz DDL を適用し、実 DB で検査する / TSK-344 = 実スキーマで再実行する** — `tenant-boundary-enforcement/design.md:335-345`、`data-model.md:2845-2846`
- CI: backend ジョブ(`.github/workflows/ci.yml:210-260`)は、`contracts/**` の変更でも走る。PostgreSQL 17.11 の service container を使い、使い捨てクラスタは pytest 中に `docker run` する
- コア領域: `contracts/authz/*`(`.claude/core-areas.json:295`)は `fnmatch` の `*` が `/` にも一致する(`scripts/core_guard.py:226`)。したがって **`contracts/authz/product/**` は paths を追加しなくてもコア領域に入る**。`backend/src/pitchlog/authz/*`(:306)・`backend/tests/db/*`(:311)・`contracts/tenant_boundary/*`(:352)も同じ area に属する

### 5. 移行バッチ用ロール

- **書き込み先の正**は 12-3 節の不変条件 1「そのバッチが作った行のすべて」(`data-model.md:295`・`:2367`)。**閉じた表集合ではないので、そのままでは exact-set にできない**。U-T1 の design.md は「機械可読資産で閉じ、正本記述との対応を検査する」と申し送っている(`../tenant-boundary-enforcement/design.md:233-236`)
- 物理的な材料: `import_batch_id` を持つ 18 表と `migration_runs`。ただし、**この集合から次の 2 表が漏れる**:
  - `event_slots`: `import_batch_id` を持たない(`schema-manifest.json:287-298`、`migration_retirement: 持たない`、**原典確認済み**)。それでも `operation_events` が FK で参照する(:340)ので、**バッチはスロット行も INSERT する必要がある**。これは正本 12-3 の不変条件 1(移行が作る行はすべて取り込みバッチ識別子を持つ — `data-model.md:2367`)とスキーマの食い違いである。`medical_note_versions` も識別子を持たないが、`medical_notes` を参照する子表であり `event_slots` と同じ形ではない。移行がこの表に行を作るかどうかは正本から読み取れない(計画レビュー 1 周目 1-P0-7 で訂正)
  - `admin_operation_logs`: 監査先だが `import_batch_id` を持たない(:849)
- **テナント横断**: バッチは `tenants` 行そのものを作る(ファンアウト 5 手順 — `data-model.md:1376-1384`、`tenants.import_batch_id` — manifest :36)。書き込み先には、`tenant_id` を持たない表(隔離・レポート・バッチ)も含まれる
- **繰り返し有効化できる形が要る**: 何度でもやり直せる(要件書 `:788`)。やり直しは退役し、新しいバッチ識別子で再投入する(`data-model.md:2361-2372`)。段階移行も否定していない(`:304`)。`migration_runs` は `completed_at` と `retired_at` を別に持つ
- 実運用の移行実行(FR-038)は本タスクの射程外(`../tenant-boundary-enforcement/design.md:237`)。旧 DB は読むだけ(要件書 `:788`)

## 未解決・申し送り(/plan で扱う。★ は人間の裁定が要る)

1. ★ **移行ロールの所有が二重で、方式が正反対** — TSK-349(Notion「未着手」)の DoD は「**凍結 probe 資産へ移行ロールを追加し、`--reseal-oracle` を回す**」。TSK-424 の DoD は「**probe 資産の差分 0 行**」。TSK-349 の開始条件「移行バッチの実装が存在する」は満たされていない。U-T1 / TSK-424 側の文書に TSK-349 への言及は 0 件(`docs/features/pg-authz-verification-g3/design.md:376-378`、TSK-349 カード)。→ 案: TSK-424 が製品資産側で持ち、TSK-349 を取り下げるか吸収する。または TSK-424 から外して TSK-349 に残す
2. ★ **SP-06 と 12-4 の字面衝突(所有は TSK-382)を踏まない線引き** — 全表 ENABLE+FORCE を製品資産として確定すると、SP-06 の実体が先に立つ(`docs/adr/ADR-004-merge-gate-scope.md:44`)。本タスクは「資産と使い捨てクラスタでの検査」にとどまり、実スキーマへは適用しない。それで射程を踏まないと言えるかを計画で明記し、踏むなら PO の裁定を取る
3. ★ **移行ロールの書き込み先 exact-set の閉じ方** — `import_batch_id` を持つ表から導出するなら、`event_slots`・`medical_note_versions`・`admin_operation_logs` の扱いを決める必要がある(5 節)。→ **決着(計画レビュー 1 周目)**: 導出集合と完全一致・例外なし。監査は手順の側が書く。食い違いは申し送る(design.md 8-1・8-2)
4. ★ **正本 3-2 節 `:296` の監査根拠** — 正本は NFR-012 を引くが、U-T1 design は根拠を裁定 A-3 に是正済み(`design.md:215`・`:535`)。正本の引用を直すなら、7.6 の決定表でゲートを判定する
5. **認可が未決の表の分類** — `tenants` / `rate_limit_counters` / `migration_*` 4 表 / `admin_operation_logs` / FK なしの 2 表。正本に記載が無いので、計画の 45 表の表で決めて敵対レビューにかける(4-1・1-5)。`rate_limit_counters` の認証前アクセスは、default-deny とぶつかる
6. **暫定資産の削除と 7D** — 二状態テストのせいで削除は避けられない。7D(TSK-431)が閉じる前に削除する場合、履歴の検査をどう担保するか、TSK-431 との順序を決める(4-4)
7. **暫定資産の `PENDING_ACCEPTANCE` / 「未承認」** — PR #72 のマージ後も残っている。本タスクが資産を削除すれば消えるが、削除の履歴(7.7-2)にどの値で記録するかを決める
8. **12-8 の追随** — TSK-317 行を分割し、TSK-424 / U-C1 / U-C2 / U-C3 / U-A2 / TSK-344 へ割り当てる。「解消済み」にはしない
9. **写像資産の二重正本** — TSK-250 の予告資産 `product-ddl-map-data-model.json` を導出側にすることを、TSK-250(`data-model-canonical/plan.md:253`)へ申し送る
10. **適用器は 1 トランザクションではない** — 製品適用の原子性(R-5 の失敗点)を、既存の手順ごと commit の構造のまま満たすのか、変えるのかを決める
11. **ツールチェーン一般化の規模** — `check_authz_catalog.py`(5854 行)の probe 固有の閉じた検査と、mutation 系の直書き 40 箇所。既存テストを無改変で green に保つ方針のもとで、ステップ分割の粒度を決める
