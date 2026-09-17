---
feature: tenant-boundary-enforcement
type: design
date: 2026-09-17
---

# 詳細設計: U-T1 テナント境界の強制点

調査は [research.md](./research.md) が正。本書は**詳細設計と検討**を持つ(契約と実装ステップ表は
[plan.md](./plan.md) — 複製しない)。

**改訂**: 計画レビュー 1〜4 周目(敵対・sol xhigh)の指摘を反映(いずれも 2026-09-17)。
反映の一覧は本書 8 節。**2 周目では自分の裁定 1 件を是正した**(8-1)。

## 0. 本書の射程と TSK-424 への分離(**2026-09-17・山田正輝の裁定**)

計画レビュー 4 周で **P0 が 5 → 5 → 3 → 3 と収束しなかった**。残った P0 はいずれも
**製品の認可面ぜんたい(45 表 × 許可プロファイル × 所有単位)を確定する作業**で、
**U-C1 / U-C2 / U-C3 / U-A1 / U-A2 にまたがる**。
→ 当該範囲を **[TSK-424 製品認可面の確定](https://app.notion.com/p/3de93b75e6878172a4b4d2f6edd663fc)** へ分離した。

| 本書の節 | 所属 |
| --- | --- |
| **1. 射程の境界** | **U-T1**(本単位) |
| **2. probe → 製品の写像 / 許可プロファイル / 移行ロール** | **TSK-424**(**本書に残し、TSK-424 の計画の入力として引き継ぐ**) |
| **3-1〜3-4. 製品 authz DDL 資産・ツールチェーンの一般化** | **TSK-424**(同上) |
| **3-5. ランタイムが資産を参照する経路** | **U-T1** |
| **4. 適用経路** | **TSK-424** |
| **5. ランタイム設計** | **U-T1** |
| **6. 迂回検査** | **U-T1** |
| **7. 合格述語の置き場** | **TSK-424** |
| **8. レビュー反映一覧** | 共通(履歴) |

**TSK-424 側の未解決(4 周目 P0)は本書では閉じない** — 引き継ぎ事項として 9 節に列挙する。

## 1. 射程の境界 — 何を守り、何を守らないか

**この節が本単位の最重要の設計判断である。** 「越境の強制点を 1 本に集約する」は
**経路の一本化**であって、**テナント文脈の値の真正性ではない**。

| 主張 | 本単位で守るか | 根拠 |
| --- | --- | --- |
| **`TenantContext` が無ければ業務 SQL を 1 文も発行しない**(アプリ層 fail-closed) | **守る** | 本単位の契約。**SQL observer で発行 0 件を観測**する(「0 行が返る」ではない) |
| `set_config` を発行しなければ 1 行も見えない(**DB 層 fail-closed**) | **TSK-424**(5 周目 P0 の是正) | `docs/design/data-model.md:331`。**製品 RLS ポリシーが無いと成立しない**。probe の流用も製品述語のテスト内コピーも製品契約を検証しない |
| アプリ用ロールが業務表を直接読んでも他テナント行は返らない | **TSK-424** | 同 `:198-233` |
| 制御資源が「自テナントが実効参加を持つ実効グループ」に限って見える | **TSK-424** | 同 `:447`(3-5 節) |
| 越境は `SECURITY DEFINER` 関数の 1 点だけを通る | **枠を守る**(基底が関数以外の越境手段を公開しない) | 同 `:487` `:490` |
| **`app.tenant_id` に入る値が認証済み主体のものである** | **守らない(守れない)** | `contracts/authz/boundary-proposal.json:43-47` が `trusted_input_set_only_by_authenticated_api` と宣言し、検証所有者を **TSK-217** としている。既存テスト `backend/tests/db/test_authz_trust_boundary.py:87` が「アプリ用ロールが任意のテナント文脈を設定できてしまう」ことを**期待値に固定** |

### 1-1. 真正性の引き渡しを**機械化する**(レビュー 1-3 の反映)

docstring だけを防壁にしない。下流の `U-M1` 等は `U-A1`(認証)を待たず **`U-T1` に直接依存する**
(`docs/features/product-impl-unit-split/plan.md:212` ほか)ため、文章の申し送りでは漏れる。

| 機構 | 内容 |
| --- | --- |
| **`TenantContext` 型** | 基底は生の `UUID` を受け取らない。**`TenantContext` 値オブジェクトだけ**を受ける |
| **生成箇所の allowlist** | `TenantContext` を構築できるモジュールを**機械可読の allowlist** に限る。allowlist 外からの構築は検査で red |
| **未検証の明示** | allowlist の初期値は「認証を実装する単位(**U-A1** / **TSK-217**)が入るまで、テスト専用の構築経路のみ」。**製品の入口が開く前に allowlist へ製品モジュールが入ることを禁じる** |

## 2. probe → 製品の写像

`contracts/authz/ddl-elements.json` は `scope.product_schema: false` の **probe 構成**である
(`:10`)。製品へ写すとき**恒等写像は成立しない**。

### 2-1. 写像の domain / codomain を**原子要素まで閉じて定義する**(レビュー 7-1 の反映)

probe 6 表 → 製品 27+ 表なので、**要素どうしの 1 対 1 は最初から成立しない**。
旧案の合格条件「1 対多 0 件」は誤りだった。**改める**:

| 事項 | 定義 |
| --- | --- |
| **原子要素** | `role` / `schema` / `table` / `policy` / `function` / **`acl_privilege`**(表 × ロール × 権限の 1 粒)まで分解した ID |
| **写像の形** | **集合写像**(1 対多を許す)。ただし**意図した 1 対多だけを許可集合として明示宣言**する |
| **「曖昧」の定義** | **許可集合の外にある多重対応**。これは終了 2(不合格) |
| **検査の向き** | **両方向の exact-set**。probe 側の未写像・製品側の余分の**両方**を検出する(片方向だと製品専用の移行バッチロールや製品表の欠落を見逃す) |
| **充足可能な形**(2 周目 P1 の是正) | 「probe 側未写像 0」は**そのままでは成立しない** — 製品側の越境関数は空(3-4)なのに probe には 3 関数と関数 ACL があり(`ddl-elements.json:298` `:600`)、ロールも probe 7 対 製品 5 で一致しない。→ **`probe の全原子要素 = mapped ∪ explicit_non_mapping`** を exact-set にする。**`explicit_non_mapping` の理由コードは閉じた列挙**とし(`test_only_role` / `external_provisioner` / `deferred_to_owning_unit` / `forbidden_by_canon` ほか)、**関数・関数 ACL・テスト専用ロール・`DELETE` のすべてに処分を与える** |

**`app_role` の `DELETE` は独立要素ではない** — `acl_privilege` 粒で複数箇所に現れる
(`contracts/authz/ddl-elements.json:454` `:507` ほか)。原子要素を `acl_privilege` まで下げて初めて
「`DELETE` を落とす」が機械的に表明できる。

**二重正本の回避**: `scripts/design_relations/product-ddl-map-data-model.json`(TSK-250 の予告資産)も
同じ「probe ID → 製品 ID」を扱う。**片方を生成物にして一致検査を置く**か**所有を一本化する**。
本単位は**自分の写像資産を正とし、TSK-250 側は本資産からの導出とする**ことを申し送る(未解決欄)。

### 2-2. 述語の型 — **`BIGINT` ではなく `UUID`**

probe の述語(`contracts/authz/function-bodies/predicates/PREDICATE:CURRENT_TENANT_OWNS_ROW.sql:7`):

```
COALESCE(tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::BIGINT, FALSE)
```

製品の `tenant_id` は **UUID**(`backend/src/pitchlog/db/mixins.py` の `TenantMixin`)。
→ 製品側は **`::UUID`**。**`COALESCE(..., FALSE)` と `NULLIF(...,'')` の骨格は変えない**
(未設定・空文字のいずれでも `FALSE` に落ちる = fail-closed の要)。
**不正な UUID 文字列はキャスト例外**になる(`FALSE` ではない)。行は返らないので fail-closed は破れないが、
**例外の形が変わる**ので故障系で表明する。

### 2-3. アプリ用ロールの表権限 — probe と正本が食い違う

| 出所 | `app_role` の業務表権限 |
| --- | --- |
| probe 資産 `contracts/authz/ddl-elements.json:454` | `SELECT, INSERT, UPDATE, **DELETE**` |
| 正本 `docs/design/data-model.md:209` | **`SELECT` / `INSERT` / `UPDATE`** のみ(`TRUNCATE`・`REFERENCES` は与えない) |

**製品側は正本に従い `DELETE` を与えない**(要件はすべて論理削除)。
写像資産に `acl_privilege` 粒の「意図的な非写像」として理由つきで記録する。
(`docs/features/pg-authz-verification-g3/design.md:385-387` が送っていた判断。**本単位が決める**。)

### 2-4. 対象表の**3 分類**(レビュー 1-1 の反映 — 旧案の重大な誤り)

**旧案は「`TenantMixin` 継承表だけを対象にし、それ以外は意図的除外」としていた。これは誤りだった。**
正本 3-5 節(`docs/design/data-model.md:447`)は**制御資源にも RLS を要求**している:

> したがって**制御資源のテーブルはテナントに属さない**。RLS ポリシーは `app.tenant_id` 単独では書けず、
> 「**自テナントが実効参加を持つ実効グループの行だけ見える**」という形になる(**述語は 3-0 節が正**)。

実モデルでも `AnalysisGroup`(`models.py:897`)・`SharingGrant`(`:1008`)・`GroupInvitation`(`:1045`)は
**`TenantMixin` 非継承**である(`GroupMembership`(`:934`)だけは `TenantMixin` を持つ)。
旧案のままだと **NFR-019(b) の「制御資源の読み取り・操作」を構造的に漏らす**。

**3 分類では実モデルのアクセス形を表現できない**(計画レビュー 3 周目 P0 の是正)。
**所有分類と許可プロファイルを分ける。** 表ごとに**許可プロファイルを 1 つ**割り当てる。

| プロファイル | 対象の例 | RLS | ポリシーの述語 | アプリ用ロールの ACL |
| --- | --- | --- | --- | --- |
| **P1. `tenant_owned`** | `TenantMixin` 継承表(実測 27 クラス) | `ENABLE`+`FORCE` | `COALESCE(tenant_id = ...::UUID, FALSE)`(2-2) | `SELECT`/`INSERT`/`UPDATE` |
| **P2. `self_tenant_row`** | **`Tenant`**(`models.py:41`) | `ENABLE`+`FORCE` | **`tenant_id` 列を持たず主キーが `id`** なので `COALESCE(id = ...::UUID, FALSE)` | `SELECT`/`UPDATE`(`INSERT` はテナント作成経路の所有単位へ) |
| **P3. `effective_group_control`** | `AnalysisGroup`(`:897`)/ `SharingGrant`(`:1008`)/ `GroupInvitation`(`:1045`)/ **`GroupMembership`**(`:934`) | `ENABLE`+`FORCE` | **「自テナントが実効参加を持つ実効グループの行だけ」**。**述語の正は `data-model.md` 3-0 節**。**「参加行が `active`」だけにしてはならない**(終了済みグループも RLS 上は見え続ける — 同 `:447`)。**終了後を 404 にするのは FR-034 の責務**であり RLS では表現しない。**`AnalysisGroup`/`SharingGrant`/`GroupInvitation` は `tenant_id` 列を持たない**ので、述語は**グループ経由**で書く | 経路に応じて `SELECT`(書き込みは U-C1 の管理関数経由) |
| **P4. `global_read_only`** | `SystemVocabulary`(`:1114`)/ `AdminVocabulary`(`:1146`)/ `SystemSetting`(`:1227`) | `ENABLE`+`FORCE` | **テナント非所属だが通常機能が読む**(`data-model.md:1925`)。**行を絞らない読み取り専用ポリシー** | **`SELECT` のみ**。書き込みは管理関数経由 |
| **P5. `app_denied`** | `AdminCredential`(`:481`)/ `AdminSession`(`:519`)/ `AdminOperationLog`(`:634`) | `ENABLE`+`FORCE` | **ポリシーを置かない** | **ACL を与えない**。管理経路は 8-2-B の管理関数(所有ロールが `BYPASSRLS`)を通る |

**P4 を P5 に入れてはならない**(3 周目 P0): `SystemVocabulary` / `AdminVocabulary` / `SystemSetting` は
**通常の入力・設定参照が読む**。アプリ完全拒否にすると**通常機能が止まる**。

**P5 の期待は「0 行」ではなく「権限拒否」**(3 周目 P0): ACL を与えないので
`SELECT` は **`42501` insufficient_privilege** で落ちる。**「0 行」を合格条件にすると
`SELECT` 権限の付与を誘発する**(付与したうえでポリシー 0 件にすれば 0 行になってしまうため)。

#### 2-4-a. 全プロファイルで `FORCE RLS` を掛ける(計画レビュー 2 周目 P0 の是正)

**旧案は一部の表を「RLS 対象外」としていた。これは正本の変更にあたり、誤りだった。**
正本は **`ALTER TABLE ... FORCE ROW LEVEL SECURITY` を全テーブルへ掛ける**と定めている
(`docs/design/data-model.md:202` — 「本書は本節末で**全テーブルへ FORCE を掛ける**と定める」、同 `:263`)。
本計画は 3 章を**変更しない**と宣言しているので、対象外にすると**承認されていない例外**になる。
しかも P5 には**管理者資格情報・セッション・操作ログ**という機微表が含まれる。

→ **P1〜P5 のすべてで `ENABLE` + `FORCE` する。** 差が出るのは**ポリシーと ACL** であって
RLS の有無ではない。**「RLS を掛けない」ではなく「掛けたうえで許可を与えない」**が正本に沿う形である。

#### 2-4-b. 分類は `TenantMixin` からは導けない(計画レビュー 2 周目 P0 の是正)

**旧案は A を「`TenantMixin` 継承表」と定義していた。これも誤りだった。**
**`GroupMembership` は `TenantMixin` を継承する制御資源**である(`models.py:934`)。
A に入れると単純な `tenant_id` 述語になり、**同じ実効グループの他メンバーを見る**という正本契約
(`docs/design/data-model.md:447` `:468`)を満たせない。B に入れると「A = `TenantMixin` 継承」と矛盾する。

→ **`Base.metadata` から自動導出するのは「表の母集合」だけ**にする。
**各表の意味分類は機械可読な明示メタデータ**(`contracts/authz/product/table-classification.json`)で与える。

**合格述語**:
- **母集合 = `Base.metadata` の全表**。プロファイル割り当て資産と**両方向 exact-set**(未割り当て 0・重複 0・存在しない表 0)
- **P1〜P5 すべてが `rls_enabled` かつ `force_rls`**
- **表ごとに `{許可プロファイル, アプリ用ロールの ACL, 対象コマンド, roles, USING, WITH CHECK}` が exact-set**
  (2-4-c。**ポリシーだけでなく ACL も**検査対象 — 3 周目 P0)
- **既定のプロファイルを持たない** — 新しい表は**未割り当て = red**(「モデルを 1 つ足すと red」の負例で検証)
- **`TenantMixin` 継承かつ P3** の負例(`GroupMembership`)を置き、**P1 の述語を適用すると red** になること
- **`tenant_id` 列を持たない表に P1 を割り当てると red**(`Tenant` / `AnalysisGroup` ほか)

#### 2-4-c. ポリシーは `USING` と `WITH CHECK` を**両方**検査する(計画レビュー 2 周目 P0 の是正)

**旧案は読み取り側しか見ていなかった。** アプリ用ロールは **`INSERT` 権限を持つ**(`data-model.md:209`)。
RLS は既存行を `USING`、**新規行と更新後の行を `WITH CHECK`** で拘束する(同 `:178`)。
`WITH CHECK` を検査しないと、**他テナントの `tenant_id` での `INSERT` や、`UPDATE` による `tenant_id` の
書き換え(越境)を許すポリシー**でも合格してしまう。

→ **全表**について **`{許可プロファイル, ACL, 対象コマンド, roles, USING, WITH CHECK}` を exact-set 検査**する。
実 DB 試験に **自テナント `INSERT`/`UPDATE` の成功・他テナント `INSERT` の拒否(`42501` または 0 行更新ではなく
`WITH CHECK` 違反の `42501`)・`UPDATE` による `tenant_id` 越境の拒否**を足す。
基底の明示条件(5-4)も **`INSERT` まで広げる**。

**プロファイルごとの期待 SQLSTATE**(実装前に固定する — 3 周目 P1 の是正):

| 事象 | 期待 |
| --- | --- |
| `WITH CHECK` 違反(他テナント `INSERT` / `tenant_id` 越境 `UPDATE`) | **`42501`**(`new row violates row-level security policy`) |
| P5 の表へのアクセス(ACL 不存在) | **`42501`** insufficient_privilege |
| 不正 UUID のテナント文脈 | **`22P02`** invalid_text_representation(トランザクションは中断状態になる) |
| `USING` で行が見えない(自テナント外の読み取り) | **例外ではなく 0 行** |

### 2-5. 移行バッチ用ロールの**ライフサイクル契約**(レビュー 7-2 の反映)

正本 5 ロールの 1 つ「移行バッチ用」(`LOGIN` + `BYPASSRLS`・期間限定)は、
**静的に作るだけでは常設の `LOGIN`+`BYPASSRLS` 経路を生む**。正本 `docs/design/data-model.md:283-296`
(裁定 `A-3`)が 5 条件を課している:

| 条件 | 内容 |
| --- | --- |
| **期間限定** | 移行完了で `NOBYPASSRLS` へ戻すかロールを落とす。**残置しない** |
| **アプリから到達しない** | アプリ用ロール・越境関数所有ロールへ `GRANT` しない。**アプリの接続文字列で使わない** |
| **DDL を持たない** | テーブル所有者にしない |
| **書き込み先の限定** | 移行が書く表へのみ `GRANT`。**対象集合の正は 12-3 節「移行バッチの退役」の不変条件 1** |
| **監査** | このロールでの接続と一括投入を操作ログに残す(**根拠は裁定 `A-3`**。計画レビュー 2 周目 P2 の是正 — 旧案は NFR-012 を引いていたが、同条は「**管理者操作の分離**」であって移行バッチ監査の一般要件ではない) |

**本単位はライフサイクル 5 条件を「全部」持つ**(計画レビュー 2 周目 P0 の是正)。
旧案は「定常状態に存在しないこと」だけを実装対象にしていたが、それでは
**有効化中の権限限定・監査・成功/失敗いずれの場合の退役**が誰のものでもなくなる
(除外先のタスク ID も無かった)。**移行バッチ用ロールは 3-2 節の 5 ロールの 1 つであり、
ロール定義を持つ本単位が契約ごと持つのが筋である。**

→ 設計:

| 事項 | 内容 |
| --- | --- |
| **資産** | 定常 authz DDL から**分離した**ライフサイクル資産(有効化 → 投入 → 退役の順序ステップと各段の期待カタログ状態) |
| **使い捨てクラスタ試験** | **有効化 → 投入 → 退役**を通し、**成功時と失敗時の両方で退役する**ことを検査する |
| **定常の不変条件** | 定常の適用結果に **`BYPASSRLS` を持つ `LOGIN` ロールが 0 件**(負例つき) |
| **有効化中の不変条件** | **書き込み先が機械可読資産の表 ID 集合と exact-set**(下記)/ アプリ用ロール・越境関数所有ロールへ `GRANT` されていない / **テーブル所有者でない**(`pg_class.relowner` で確認 — 3 周目 P1 の是正) |
| **監査**(3 周目 P1 の是正) | **このロールでの接続と一括投入が操作ログに記録される**ことを、**成功系と失敗系の両方**で検査する |

**書き込み先の集合は資産で閉じる**(3 周目 P1 の是正): 旧案は「12-3 節の不変条件 1 の集合」と書いたが、
**同節の不変条件 1 は閉じた表集合ではなく「そのバッチが作った全行」という普遍条件**である
(`docs/design/data-model.md:2365`)。そのままでは exact-set を構成できない。
→ **移行書き込み対象のテーブル ID を機械可読資産として閉じ、正本の記述との対応を検査する。**
| **本単位が持たないもの** | **実運用での移行の実行そのもの**(FR-038 の移行タスクの射程)。本単位が持つのは**ロールのライフサイクル契約とその検査**である |

## 3. 製品 authz DDL 資産の形と置き場

### 3-1. 既存の probe 資産は触らない

`contracts/authz/ddl-elements.json` は `contracts/authz/oracle-seal.lock.json:40-77` の
`sealed_assets` に `canonical_sha256` で封印。変更すると
`backend/tests/test_authz_mutation_composition_full.py` の 3 テストが red、
`--reseal-oracle` + **人間レビュー必須**(`oracle-seal.lock.json:84-88`)。
`contracts/authz/failure-injection-points.json:4-7` も同資産の `git_blob_digest` を固定。

→ **製品資産は別ファイルとして新設し、probe 資産は 1 バイトも触らない。**

### 3-2. 置き場

```
contracts/authz/product/ddl-elements.json          製品側の DDL 要素(roles/schemas/tables/policies/acl)
contracts/authz/product/probe-product-map.json     probe 原子要素 ID ↔ 製品原子要素 ID(両方向 exact-set)
contracts/authz/product/table-classification.json  全 ORM 表の A/B/C 分類(2-4)
contracts/authz/product/function-bodies/           製品側 SQL 本体 + manifest.json
```

`contracts/authz/*` は `fnmatch` の `*` が `/` を食うため、**この配下も自動的にコア判定に入る**
(`.claude/core-areas.json:295` + `scripts/core_guard.py:226`)。paths 追加は不要。

### 3-3. ツールチェーン全体を**資産指定オブジェクト**で一般化する(レビュー 2-1 の反映)

**旧案は `ddl.py` だけを一般化すれば足りると書いていた。これは誤りだった。**
probe パスを固定しているのは生成器だけではない:

| 箇所 | 固定している内容 |
| --- | --- |
| `backend/src/pitchlog/authz/ddl.py:12-13` | `DDL_ELEMENTS_PATH` / `BODY_MANIFEST_PATH` |
| `backend/src/pitchlog/authz/ddl.py:66` | body 検査の呼び出し |
| `scripts/check_authz_function_bodies.py:21` | body 検査器側のパス |
| `backend/src/pitchlog/authz/provisioning.py:668` | 適用器の順序ステップ |
| `backend/tests/db/conftest.py:39` | DB fixture の資産読み込み |

→ **1 つの「資産指定オブジェクト」**(資産ルート・要素ファイル・manifest・検査器パスを束ねた値)を導入し、
**生成器・body 検査器・適用器・カタログ検査・DB fixture がすべてそれを受け取る**形にする。
既定値を現行の probe 構成にして**既存テストを無改変で green に保つ**(後方互換)。

**これをやらないと**、製品資産は適用も実 DB 検査もできず、
**「probe で再試験して green にする」抜け道**が残る。

**制約**: `ddl.py` には SQL 断片も資産識別子リテラルも書けない
(`backend/tests/test_authz_ddl.py:181` の AST 検査)。SQL は `function-bodies/` 側に置く。

### 3-4. 本単位が持つ製品 DDL の範囲 — **越境関数は持たない**

製品の**越境関数の本体は本単位のものではない**。FR-041 の主所有は **U-C1**
(`docs/features/product-impl-unit-split/plan.md:225`)、共有出力の認可面は **U-C3**(同 `:227`)。

→ 本単位の製品 DDL 資産が持つのは **ロール・スキーマ・表 / RLS / ポリシー**まで。
**越境関数とその ACL・`search_path` は U-C1 / U-C3 が足す**(理由は**射程の重複の回避**であって
NFR-018 ではない — 8-1)。資産の構造は関数を受け取れる形にしておき、**空であることを宣言として持つ**
(「まだ無い」と「書き忘れ」を区別する)。**あわせて 12-8 に残件として記録する**(8-1)。

### 3-5. ランタイムが製品資産を参照する経路(3 周目 P1 の反映)

5-2 は「接続時に期待アプリロール名を**製品資産から解決する**」としているが、
**そのままでは実行時に資産へ到達できない**。`backend/pyproject.toml` の
`[tool.setuptools.packages.find] where = ["src"]` により、**配布物に入るのは `backend/src` 配下のパッケージだけ**で、
リポジトリ直下の `contracts/` は**インストール成果物に入らない**。
既存の資産読み込み(`backend/src/pitchlog/authz/ddl.py:212`)は**リポジトリルートを受け取る検証ツール向け**である。

| 案 | 評価 |
| --- | --- |
| **(採用) 製品資産から生成したランタイム定数モジュールをパッケージ内に置く** | 置き場は `backend/src/pitchlog/authz/`(**`db/` ではない**ので「1 ファイルも足さない」制約に触れない)。**資産との一致検査をテストで持つ**(生成物が古いと red)。**`backend/pyproject.toml` の差分 0 行**を保てる |
| (不採用) 製品 JSON を package data に含める | **`backend/pyproject.toml` の差分禁止**と衝突する(`../product-impl-unit-split/plan.md:462`)。必要なら依存追加と同様に**単独 PR** へ切る |
| (不採用) 作業ディレクトリ依存の相対参照 | 実行場所に依存するので採らない |

### 3-5-a. TSK-424 との往復契約(計画レビュー 5 周目 P0 の反映)

本単位のロール真正性検査(5-2)が要るのは**期待アプリロール名だけではない**。
既存の `_dangerous_role_ids`(`backend/src/pitchlog/authz/catalog.py:808-812`)は
**資産の schema / table / function ID から危険所有者を導出**している。
→ **TSK-424 の出力契約を名指しで固定する**:

| 事項 | 内容 |
| --- | --- |
| **TSK-424 が出す値** | ① **期待アプリロールの全属性**(`rolname` / `rolsuper` / `rolbypassrls` / `rolcanlogin` / `rolcreaterole` / `rolcreatedb` / `rolreplication` / `rolinherit`)② **保護対象の物理識別子**(6 周目 P0 の是正 — **抽象 ID だけでは足りない**。現行検査は `nspname` / `relname` / `proname` として扱うため、**schema 名・`(schema, table)`・`(schema, function, identity_args)` の形で出す**)③ `schema_version` ④ **正規化方式を定めた digest** ⑤ `provisional` |
| **受け渡しの場所** | 資産 = `contracts/authz/product/ddl-elements.json` / **生成先モジュール = `pitchlog.authz.runtime_contract`**(6 周目 P0 の是正 — ディレクトリではなくモジュール名・公開シンボル・型まで固定する)/ U-T1 は**このモジュールだけ**を import する |
| **capability の扱い** | ステップ 9 の製品 capability も **TSK-424 の出力契約に含める**(含めないなら「順序依存は 1 点だけ」が成り立たない — 同 P0)。**依存表に明示する** |
| **二状態契約** | **`contracts/authz/product/ddl-elements.json` が存在しない間**だけ暫定値を許す。**存在する場合は `provisional: true` と旧暫定値への参照が必ず red** になる。`provisional: true` と書くだけでは CI は TSK-424 の完了を知れないので、**資産の存在そのものを切替条件にする**。**暫定資産あり / 製品資産あり の双方について、生成物一致と旧暫定資産の不在を検査する** |
| **旧暫定資産の除去** | 切替後に暫定資産が残っていると red |

**差し替え漏れを検出できない設計にしない。** この往復契約は 9 節にも引き継ぐ。

## 4. 適用経路 — migration ではない

裁定 `A-2` により alembic migration は `CREATE POLICY` / `CREATE ROLE` / `ALTER ROLE` を **0 件**に保つ
(`docs/features/orm-schema-migration/plan.md:848` の `D7`。実測でも該当 0 件)。

→ 製品の RLS・ロール DDL は migration の外で適用する。適用器は既存の
`backend/src/pitchlog/authz/provisioning.py`(`apply_authz_ddl`)を 3-3 の一般化を経て使う。

### 4-1. 使い捨てクラスタへ適用して試験する(**所有は TSK-424** — 5・6 周目の裁定で移管)

**「生成できるところまで」では抜け道が残る**ので、本単位は
既存の `disposable_postgres_cluster` / `provisioned_catalog` fixture(`backend/tests/db/conftest.py:442` `:505`)と
同じ形で、**使い捨て PostgreSQL へ製品 migration + 製品 authz DDL を適用し、実 DB で検査する**。

**TSK-344 との切り分け**: `docs/design/data-model.md:2846` は TSK-344 の射程を
「越境テスト再実行ゲートの実行(**実スキーマに対する再実行**)」と書いている。
**「再実行」である以上、作成と初回実行はこちら側にある** — 同 `:2845` が TSK-317 へ送った範囲も
「RLS ポリシー・ロール DDL の実機確定**と越境テストの作成・実行**」である。
→ **本単位: 使い捨てクラスタで作成・実行 / TSK-344: 実スキーマで再実行。** 矛盾しない。

## 5. ランタイム設計

### 5-1. 置き場の制約

`backend/src/pitchlog/db/` には **1 ファイルも足せない**
(`docs/features/product-impl-unit-split/plan.md:466`。新規は `api/` `services/` `repositories/` `sync/` `domain/` のみ)。
→ 新規コードは **`backend/src/pitchlog/repositories/`**。`db/engine.py` の変更は既存ファイルなので制約外。

`repositories/` は `.claude/core-areas.json` の `tenant-isolation` の `paths` に**無い**。
テナント境界の強制点がコア判定の外に出るのは筋が通らないため **`paths` への追加が要る** —
`.claude/core-areas.json` は `guard_paths` にあり、**追加は設計書 6.3-⑤ の敵対レビュー + 人間承認の対象**。
**独立したステップとして積む**(黙って足さない)。

### 5-2. アプリ用ロール接続 — **経路を増やさず、ロールの真正性を検査する**(レビュー 1-2 の反映)

**旧案は新しい DSN 変数を足す形だった。これは誤りだった** — 既存経路を残したまま任意経路を足すと
**強制点が二本になる**。

| 事項 | 設計 |
| --- | --- |
| **変数** | **既存のアプリ用 DSN 変数をアプリ用ロール専用として強化する**(新変数を足さない)。alembic は既に別変数 `PITCHLOG_MIGRATION_DATABASE_URL` を持つ(`backend/migrations/env.py:23`)ので経路の分離は既に成立している |
| **接続時の検査** | **期待するアプリ用ロール名を製品資産から解決し**、`session_user` と `current_user` の**両方がそれと完全一致**することを検査する。あわせて **`rolcanlogin` = true / `rolsuper` = false / `rolbypassrls` = false**、および **`pg_auth_members` の `SET`/`USAGE` 推移閉包で危険ロール(`BYPASSRLS` 保持ロール・テーブル所有ロール)へ到達できない**ことを検査する |
| **拒否の時点** | **最初の物理接続の確立時に拒否する**(計画レビュー 2 周目 P1 の是正 — 旧案は「起動を拒否」と書いていたが、現在のアプリ生成は engine を作らず接続もしない〔`backend/src/pitchlog/api/app.py` / `main.py`〕ので、「起動拒否」は実装できない主張だった) |
| **負例(名前で落ちるもの)** | **`table_owner`(属性検査だけでは通ってしまう — `contracts/authz/ddl-elements.json:48`)** / 任意の通常 `LOGIN` ロール / 共有関数所有ロール / **管理関数所有ロール** / 移行バッチロール / superuser の DSN で**拒否される**。`SET ROLE` 偽装が `session_user ≠ current_user` で弾かれる |
| **負例(推移閉包でしか落ちないもの)** | **期待アプリロール名を保ったまま**、`app_role → 中間ロール → 危険ロール` の **① 直接所属 ② 多段所属**を作り、**いずれも拒否される**こと。**`set_option` と `inherit_option` を別 fixture** にして両方を検査する |
| **危険終点の集合** | **既存のカタログ検査と同じ exact-set** にする(`backend/src/pitchlog/authz/catalog.py:808` の `_dangerous_role_ids`)。**`BYPASSRLS` 保持ロールとテーブル所有者だけでは足りない** — superuser・スキーマ所有者・テーブル所有者・関数所有者を含む |

**属性検査だけでは真正性にならない**(計画レビュー 2 周目 P0 の是正): 旧案の
`rolcanlogin=true / rolsuper=false / rolbypassrls=false` は**テーブル所有ロールでも任意の通常ロールでも成立する**。
実際 probe の `table_owner` は 3 条件すべてを通る。

**負例の設計も要る**(3 周目 P0 の是正): 上の「名前で落ちるもの」だけを並べると、
**`pg_auth_members` の推移閉包を実装しなくても全負例が green になる**。
**期待ロール名を保ったまま危険ロールへ到達できる負例**を置いて初めて、推移閉包の検査が意味を持つ。
| **先例** | `backend/tests/db/conftest.py:263-298` の autouse fixture `verify_connection_identities` が同じ形の identity guard を既に持つ。**製品側へ同じ規律を持ち込む** |
| **未設定時** | 既存の `require_database_configuration`(`backend/src/pitchlog/db/config.py:8-25`)の fail-closed 形を踏襲 |

**接続方式**: 正本は「アプリは session pooler を第 1 候補、transaction pooler を許容」(`data-model.md:308-315`)。
**規律は transaction pooler でも成立する形に統一**するので、実装は pooler の別を前提にしない。

**設定テンプレートの扱い**(3 周目 P1 の是正 — **旧案の事実誤認を訂正**):
旧案は「ハーネスのフックが設定テンプレートを遮断するので人間作業」と書いたが、**誤りだった**。
`.claude/hooks/secret_guard.py` は「**許可する例外は basename が exact `.env.example`(大小無視)のトークンのみ**」と
明記し、`.claude/hooks/protect_paths.py:40` も `.env.example` を除外している。
実際に遮断されたのは、**`.env` を含む解析不能な長大コマンドが安全側でブロックされた**ためである。
→ **`.env.example` の更新は通常の実装ステップでよい**。人間作業にしない。
`PITCHLOG_DATABASE_URL` のコメント(「未設定なら起動失敗」相当の記述)も
**「最初の物理接続時に失敗」へ同期する**。

### 5-3. テナント文脈の束縛 — 規律 5 項を**すべて**検査する(レビュー 2-3 の反映)

正本の規律(`docs/design/data-model.md:317-329`)を実装契約にする。
**旧案は `set_config(..., true)` の字面検査だけで、5 項のうち 3 項が検査されていなかった。**

| # | 規律 | 検査の形 |
| --- | --- | --- |
| 1 | 明示した 1 トランザクションの**最初**に `SELECT set_config('app.tenant_id', :tenant_id, true)` | **SQL 発行順**を観測し、束縛より前に他の SQL が出ないこと |
| 2 | ポリシー側は `current_setting('app.tenant_id', true)` を読む | 述語の構造検査(2-2) |
| 3 | **`SET app.tenant_id` と `set_config(…, false)` を使わない** | 字面検査 + **commit 後に GUC が消えている**ことの実 DB 観測 |
| 4 | **autocommit で別トランザクションにしない** | autocommit 接続で基底を使うと**拒否される**負例 |
| 5 | リクエストごとに `Session` を作り `begin()` の中で最初に発行。**テナント横断・リクエスト横断で共有しない** | **同一 Session の再束縛が拒否される**負例 + **並行する 2 Session 間で GUC が漏れない**こと |

### 5-4. 越境関数経由のリポジトリ基底 — **二重構成を守る**(レビュー 4-1 の反映)

**旧案は自テナント経路を「RLS の絞り込みだけ」と書いていた。これは正本と食い違う。**
正本 3-1 節(`docs/design/data-model.md:181-188`)は **RLS に加えてアプリ層でも `tenant_id` 条件を省かない**
二重構成を定める(索引選択・意図の明示・RLS のバイパス経路が実在するため)。
NFR-005(要件書 `:818`「選択されていないテナントのデータを走査しない」)にも効く。

| 経路 | 設計 |
| --- | --- |
| **自テナント経路** | 基底は**生の `Session` も任意クエリも公開しない**。テナント所有表への `SELECT` / `UPDATE` は**明示的な `tenant_id = :tenant_id` を必須**にする(API の形で強制し、書き忘れを起こせなくする) |
| **越境経路** | `SECURITY DEFINER` 関数の呼び出しのみ。**基底は関数呼び出し以外の越境手段を公開しない**。関数そのものは U-C1 / U-C3 が足す(3-4) |
| **公開メソッドの戻り値**(5 周目 P0 の是正) | **完全実体化済みの immutable な値 / DTO のみ**。**接続中の ORM instance・SQLAlchemy `Result` / `ScalarResult`・query・遅延 generator は公開 exact-set から除外**する。これらを返すと**呼び出し元の属性参照・反復・expire 後の再読込で SQL が発行され**、呼び出し元の AST に `Session.execute` が現れないため**迂回検査では捕捉できない**(6 節が挙げた遅延ロードの穴を閉じるのはここ) |
| **製品表向けの汎用 CRUD**(同) | **本単位では公開しない**。`TenantMixin` から公開操作を導くと **`GroupMembership`(制御資源)を一般テナント表として開いてしまう**。公開面は**文脈束縛・封印された実行器・空の越境関数 registry**まで。製品表操作は **TSK-424 の表分類から生成する capability** を受けて有効化する |
| **負例** | 接続中 ORM instance を返す / `Result` を外側で反復する / 無条件 `SELECT` / 全件取得 / 選択外テナントの走査 |

## 6. 迂回検査 — **実装前に検査契約を確定する**(レビュー 6-1 の反映)

**旧案は「実装後に検索式を確定する」「基底ファイルをパスで丸ごと除外する」だった。いずれも誤りだった。**

- 分割計画は**各計画書が 5 条件それぞれの検索式を確定する**と定めている
  (`docs/features/product-impl-unit-split/plan.md:275-277`)。「検討する」では未決のままになる
- 行 grep の `session\.execute` は **`conn.execute` / `cursor.execute` / `session.get|add|delete` /
  `exec_driver_sql` / alias / 改行またぎ / 遅延ロード**を捕捉しない
- **基底ファイルを丸ごと除外すると、後からそのファイルへ直接 SQL や認可迂回を足しても永久に検査対象外**になる

**改める**:

| 事項 | 設計 |
| --- | --- |
| **検査の形** | 行 grep ではなく **AST / import 境界**。**DB へ到達できる API を閉じた集合として列挙**する(`Session.execute|get|add|delete|scalars` / `Connection.execute|exec_driver_sql` / psycopg の `cursor.execute` / `engine.*` / `raw_connection` ほか。**集合は資産として持ち、追加は明示的な改訂**とする) |
| **許可の粒度** | **ファイルではなく、基底の特定シンボル・特定関数の内側**に限る |
| **基底自身** | **除外しない**。基底は**構造検査と変異検査の対象**にする(基底に直接 SQL を足したら red) |
| **正例**(2 周目 P1 の是正) | **負例だけでは、全呼び出しを拒否する検査器でも合格してしまう**。許可されるべき**完全修飾シンボルと署名**を**正例 fixture** として置き、**正例が通ること**も合格条件にする。実装前の段階では**将来のシンボル契約**(完全修飾名と署名)として書き、実装ステップがそれに合わせる |
| **負例** | **条件ごとに変異軸が違う**(3 周目 P1 の是正 — 旧案の「5 条件 × 各 5 種」は意味のある 25 組を作れない。alias / 複数行 / psycopg / ORM / async は**条件 5 の構文変異軸**であって条件 1〜4 には対応しない)。下表のとおり条件ごとに分類と ID を持ち、**負例 fixture の ID 集合を exact-set で固定**する |

**条件ごとの負例分類**(`docs/features/product-impl-unit-split/plan.md:267-273` の 5 条件に対応):

| 条件 | 変異軸 |
| --- | --- |
| **1. 新たな認可判定を追加しない** | **禁止シンボル名**の変異(`can_*` / `may_*` / `is_allowed` / `has_permission` / `check_*_access` / `require_role` / `assert_*_owner`)+ デコレータ形・メソッド形・モジュール関数形 |
| **2. 同期セマンティクスを扱わない** | **契約名**の変異(べき等キー / 連番 / 墓標 / 改訂 / 世代)+ それらを import する形 |
| **3. NFR-018 の対象計算を含まない** | **ADR-003 D-1〜D-6 の契約名**の変異 + 当該モジュールからの import |
| **4. キャッシュ無効化契約に触れない** | **無効化 API 名**の変異 + 6.2 のトリガー語彙 |
| **5. テナントデータは越境関数経由だけ** | **DB 到達 API の構文変異**(alias / 複数行 / psycopg 直呼び / SQLAlchemy ORM / async)+ 基底シンボル以外からの呼び出し |
| **常時実行** | 検査器は**全後続 PR で常時実行**する。**現行 CI の backend フィルタは `backend/**` と `contracts/**` しか拾わない**(`.github/workflows/ci.yml:176`)ので、**検査器だけを変更した PR でも必ず走るジョブ**を明記して配線する |
| **検査器自身の保護** | **検査器・allowlist・正負 fixture・検査テストも**コア領域 paths へ入れる。**強制点を変え得るファイルを paths へ含める**規則(`docs/development/dev-harness-design-2026-08-07.md:393`)に従う — `repositories/*` だけでは足りない |
| **確定の時期** | **実装前**(ステップの先頭側)に検査契約を確定し、実装はそれに従う |

5-3 の禁止事項(`set_config(..., false)` / `SET app.tenant_id`)も同じ検査に載せる
(枠は分割計画書が 5 条件で拘束しているので、**条件 5 の内側**に置く)。

**迂回検査の目的の言い直し**(レビュー 6-2 の反映): 旧案は「葉 6 本の非コア判定の根拠」と書いていたが、
**現行の分割計画では非コアで通せる対象は器 3 本(`U-00`/`U-01`/`U-02`)だけで、葉 6 本は既にコア確定**
(`docs/features/product-impl-unit-split/plan.md:254-257`)。
→ 目的は「**後続実装が強制点を経由することの継続保証**」である。

## 7. スキーマ検査の合格述語の置き場

現在、合格述語は**正本でも `contracts/` でもなく feature 文書**にある
(`docs/features/pg-authz-verification-g3/catalog-check-map.md:24-43`)。実装は `authz/catalog.py`。
→ 製品側の述語は **`contracts/authz/product/` の資産として持つ**(再発させない)。
probe 側の `catalog-check-map.md` は移さない(TSK-317 の成果物・本単位の射程外)。

## 8. レビューの反映一覧

### 8-00. 計画レビュー 3 周目の反映

| 指摘 | 深刻度 | 反映 |
| --- | --- | --- |
| 12-8 の残件所有者に **U-A2**(管理経路)が抜けている | P0 | **8-1**。共有・グループ経路(U-C1/U-C3)と**システム管理経路(U-A2)**に分割 |
| ロール到達可能性の負例が推移閉包を実際には検査しない | P0 | **5-2**。**期待ロール名を保ったまま危険ロールへ到達する負例**(直接・多段・`set_option`/`inherit_option` 別 fixture)。危険終点を `catalog.py:808` と同じ exact-set へ |
| A/B/C では実モデルのアクセス形を表現できない | P0 | **2-4 を許可プロファイル 5 種へ作り直し**(`Tenant` は `id` 述語 / 制御資源は `tenant_id` を持たない / 語彙・設定は `global_read_only` / `app_denied` は**権限拒否**を期待) |
| 移行ロールの「テーブル所有者でない」「監査」が実装条件にない / 12-3 不変条件 1 は閉じた集合ではない | P1 | **2-5**。`pg_class.relowner` による非所有確認・成功系/失敗系の監査・**書き込み先を機械可読資産で閉じる** |
| ステップ 7・8・16 の依存順が逆 | P1 | **plan のステップを組み替え**(fixture 抽出をツールチェーン一般化の直後へ / 製品 DDL 適用を移行ロール試験より前へ) |
| ステップ 10 を人間作業にする根拠が事実誤認 | P1 | **5-2**。`.env.example` はフックが明示的に許可している。**通常の実装ステップへ戻す** |
| ステップ 1 の負例マトリクスが 5 条件の構造と一致しない | P1 | **6 節**。**条件ごとに異なる変異軸**の表を追加 |
| 期待値を「実装時に固定」しており計画の合否基準になっていない | P1 | **2-4-c に期待 SQLSTATE 表**。plan に fixture ID・例外型を列挙。**ページ上限は U-01 の所有へ戻す**。fixture 共有先のパスを固定 |
| ランタイムが製品資産を取得する方法がない | P1 | **3-5**(新設) |

### 8-0. 計画レビュー 2 周目の反映

| 指摘 | 深刻度 | 反映 |
| --- | --- | --- |
| 1 12-4 対象外と 12-7/12-8 の実機確定責務の混同 | P0 | **8-1 を書き直し**。責務分割(U-T1 / U-C1・U-C3 / TSK-344)と「12-8 を解消済みにしない」を明記。research.md も同期 |
| 3 `GroupMembership` が A/B 境界を破る | P0 | **2-4-b**。分類を `TenantMixin` から導くのをやめ、**明示メタデータ**へ。`GroupMembership` は **B** |
| 4 C 分類が「全テーブル FORCE」を変更している | P0 | **2-4-a**。**C も `ENABLE`+`FORCE` し、ポリシーを置かない**(default-deny)形へ |
| 5 属性検査だけではロール真正性にならない | P0 | **5-2**。**ロール名の完全一致** + `pg_auth_members` の推移閉包で危険ロールへ到達不能 |
| 6 `INSERT` と `WITH CHECK` が落ちている | P0 | **2-4-c**。`{コマンド, roles, USING, WITH CHECK}` の exact-set + 越境 `INSERT`/`UPDATE` の拒否試験 |
| 2 NFR-018 を不採用理由に使うのは誤り | P1 | **8-1 で是正**。理由を「主所有が U-C1 / U-C3」へ差し替え |
| 7 移行ロールの 5 条件のうち 1 つしか実装されない | P1(実質 P0) | **2-5**。**ライフサイクル 5 条件を全部持つ**(有効化→投入→退役の使い捨てクラスタ試験) |
| 8 ステップ 4 はステップ 6 より先に実行できない | P1 | **plan のステップ順を組み替え**(ツールチェーン一般化 → 製品 body 作成 → 封印) |
| 9 写像の exact-set が充足不能 | P1 | **2-1**。`probe 全要素 = mapped ∪ explicit_non_mapping` の形へ。**非写像理由コードを閉じた列挙**にし、関数・関数 ACL・テスト専用ロールの処分も明記 |
| 10 ステップ 1 が負例だけでは確定できない / 検査器がコア保護外 | P1 | **6 節**。**正例 fixture と将来シンボル契約**・**閉じた DB API 集合**・**検査器/allowlist/fixture もコア paths へ**・**CI ジョブの明記** |
| 11 「起動拒否」と設定テンプレート更新にステップがない | P1 | **5-2**。「**最初の物理接続の確立時に拒否**」へ。設定テンプレートは **plan で独立ステップ**にする |
| 12 合格条件に機械判定不能な語が残る | P1 | **plan のステップ表と DoD を fixture ID・期待例外/SQLSTATE・件数・観測対象まで具体化** |
| 13 NFR-012 を移行バッチ監査の根拠に引用 | P2 | **2-5**。根拠を**裁定 `A-3`** へ差し替え |

### 8-1 以前. 計画レビュー 1 周目の反映一覧

| 指摘 | 深刻度 | 反映 |
| --- | --- | --- |
| 1-1 対象集合が制御資源を漏らす | P0 | **2-4 で 3 分類へ作り直し**。未分類は red |
| 1-2 アプリ DSN のロール真正性が未検査 | P0 | **5-2 で新変数を足さず既存を強化 + 接続時のロール属性検査**へ |
| 2-1 製品 DDL の検証・適用ステップ欠落 | P0 | **3-3 でツールチェーン全体を資産指定オブジェクトで一般化 / 4-1 で使い捨てクラスタ試験**を射程に入れた |
| 6-1 迂回検査が実装後送り + パス除外 | P0 | **6 節で AST / シンボル粒度・基底も検査対象・実装前確定**へ |
| 7-2 移行バッチロールのライフサイクル欠落 | P0 | **2-5 で 5 条件の契約と「定常に残らない」負例**を追加 |
| 1-3 真正性の引き渡しが機械化されていない | P1 | **1-1 で `TenantContext` + 生成箇所 allowlist** |
| 2-2 写像を写像先より先に作ると検証不能 | P1 | **plan のステップ順を「製品要素 → manifest 封印 → 写像」へ組み替え** |
| 2-3 規律 5 項のうち 3 項が未検査 | P1 | **5-3 で 5 項すべてに検査の形を割り当て** |
| 3-1 依存追加禁止が差分不変条件から抜け | P1 | **plan の「やらないこと」と DoD へ `backend/pyproject.toml` / `uv.lock` 差分 0 を追加** |
| 3-2 12-8 節を実質閉じるのに「反映なし」 | P1 | **plan 3 節で `data-model.md` 12-8 を実装追随として更新対象に変更** |
| 4-1 二重構成と NFR-005 が落ちている | P1 | **5-4 で明示的 `tenant_id` 条件を必須化** |
| 5-1 最低要求 4 件を 3 件へ縮小している | P1 | **一部採らない**(8-1)。plan 5 節で「12-4 の 4 件」と「本単位の DB 試験」を分離 |
| 5-2 「節ごと削除」は過剰 | P1 | **plan 5 節で「対象入口なし」+ PR へ判定記録を残す**形へ |
| 6-2 非コア判定の要という前提が食い違う | P2 | **6 節末で目的を言い直し / plan 1 節の当該記述を削除** |
| 8-1 NFR-019(d) と一般の故障系の混同 | P2 | **plan 6 節で (a)(b)(c)(d) の割当と、単体・DB 統合・構成検査・故障注入の別表へ** |

### 8-1. 越境テスト最低要求 4 件の帰属(**計画レビュー 2 周目で自分の裁定を是正**)

1 周目のレビュー 5-1 に対し、**2 つの理由を挙げて不採用としたが、どちらも不正確だった**。
2 周目のレビューがそれを指摘し、**原典で確認して是正する**。

| 1 周目に書いたこと | 2 周目の是正 |
| --- | --- |
| 「12-4 のゲート対象外だから 4 件は U-T1 の義務ではない」 | **ゲートの話としては正しい**(`docs/design/data-model.md:2528`)。**しかし 4 件は 12-7 (1) にも別契約として現れる**(同 `:2762-2765`「実機確定タスクへの要求」)。**U-T1 が 12-8 の TSK-317 行(`:2845`)を部分的に引き受ける以上、4 件を無所有にはできない** |
| 「代表関数を実装すると **NFR-018 の単一実装**に反する」 | **誤り。** NFR-018 の**対象は閉じた列挙**(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定 — 要件書 `:887` `:892`)であり、**認可関数は対象外**。正しい理由は「**製品の越境関数の主所有が U-C1 / U-C3 だから**」という**射程の重複**である |

**是正後の帰属**(責務分割):

**越境関数は 1 種類ではない**(3 周目 P0 の是正)。正本は**共有関数**(FR-041 の共有集計 — 3-6 節)と
**管理関数**(FR-035/037 の管理経路 — 8-2-B 節)を**別ロール・別関数群**に分けており
(`docs/design/data-model.md:210`)、12-7 の未確定範囲には**管理経路の 7 操作**も入る(同 `:2755`)。
分割計画では**管理経路の主所有は U-A2**(`docs/features/product-impl-unit-split/plan.md:223`)。
→ 残件を**共有・グループ経路**と**システム管理経路**に分ける。

| 主体 | 持つもの |
| --- | --- |
| **U-T1**(本単位) | **アプリ層の強制点のみ** — 接続ロールの真正性 / `TenantContext` / 文脈束縛 / リポジトリ基底 / 迂回検査 / キャッシュ無効化契約。**RLS・許可プロファイル・最低要求 ① は TSK-424 へ移管**(5・6 周目の裁定) |
| **TSK-424** | **ロール / RLS / 許可プロファイル / 最低要求 ①** / 製品 DDL 資産 / 写像 / 移行ロール |
| **U-C1 / U-C3** | **共有・グループ経路**の越境関数・関数 ACL・`search_path` / **最低要求 ②③④のうち共有関数に係る分** |
| **U-A2** | **システム管理経路**の管理関数・関数 ACL・`search_path` / **7 操作の操作別契約**(8-2-B)/ 同じく ②③④のうち管理関数に係る分 |
| **TSK-344** | **揃った 4 件の実スキーマ再実行** |

**12-8 の TSK-317 行は U-T1 完了時点でも「解消済み」にしない。**
**残件・所有者(U-C1 / U-C3 / U-A2)・発効条件を明記して残す。**
これを怠ると、`PUBLIC` の `EXECUTE`・`search_path` の乗っ取り・非共有対象の確認・管理経路の 7 操作が
**無所有になる**。

## 9. TSK-424 への引き継ぎ(計画レビュー 4 周目で閉じ切らなかった P0/P1)

**本書 2・3-1〜3-4・4・7 節を入力として引き継ぐ。** そのうえで、4 周目の敵対レビューが挙げた
**未閉鎖の論点**を TSK-424 の計画で閉じる:

| 論点 | 内容 |
| --- | --- |
| **許可プロファイル 5 種では 45 表を覆えない**(P0) | `TenantCredential` は `tenant_id` を持たず **`TenantAuthSubject` 経由**でテナントに属する / `RateLimitCounter` は**認証主体の確定前**に読み書きするグローバル可変表。**「親表経由のテナント所属」「認証前グローバル可変」のプロファイル追加**が要る。**全 45 表の期待プロファイルを計画段階で表として固定**する(`backend/tests/test_schema_manifest.py` が 45 表を固定) |
| **`read_control_resources` 相当の受け取り先**(P0) | 制御情報読み取り 4 経路の主所有は **U-C2**(`../product-impl-unit-split/plan.md:226`)。probe には専用関数が実在(`contracts/authz/ddl-elements.json:353`)。**写像の `owner_unit` に U-C2 を含める** |
| **P2/P3 の実 DB 挙動試験**(P1) | P2 の自己行許可/他行 0 件、**P3 の 4 表について member / admin / nonmember / terminated の正負行列**、P4 の書き込み `42501` |
| **移行ロールの監査の実効性**(P1) | 試験ドライバ自身が監査行を書けば green になる。**失敗した投入トランザクションでは同一トランザクションの監査行もロールバックされる**ため、**別トランザクション境界**と失敗注入点を固定する。書き込み先は `contracts/db/schema-manifest.json` の `import_batch_id` 等から**導出する規則**を置く |
| **非写像の理由コード**(P1) | 「ほか」で開いている。**全列挙し、各コードを適用できる原子要素種別と `owner_unit` も固定**する |
| **ランタイム定数の生成手段**(P1) | 生成器のパス・入力資産・出力ファイル・決定的な整形・`--check` 相当の CI コマンドを固定(本書 3-5 は置き場の方針まで) |
| **U-T1 への往復契約**(P0) | **本書 3-5-a が定める出力契約を満たすこと** — ① 期待アプリロール名 ② **保護対象の schema / table / function の ID 集合**(`catalog.py:808-812` の危険所有者導出が要る)③ `schema_version` と digest。**`contracts/authz/product/ddl-elements.json` の存在が U-T1 側の暫定→本番の切替条件**になるので、**資産を置いた時点で U-T1 の暫定値が red になる**ことを両者で確認する |

## 未解決・検討メモ(**U-T1 の射程**)

- **`repositories/` をコア領域 paths へ追加する件**(5-1)は敵対レビュー + 人間の逐行確認が要る
  (**PR レビューのゲート**であって、コミット単位の合格条件ではない)。
- **期待アプリロール名の暫定定義**(3-5)。TSK-424 完了後の差し替え漏れを検出できる形にする。
- **`backend/tests/test_authz_tenant_binding.py` は平場**に置くため、
  **`backend/tests/db/conftest.py` の fixture を自動では使えない**(pytest の conftest 有効範囲)。
  **`backend/tests/db_fixtures.py` へ抽出**して明示 import で共有する
  (`backend/tests/conftest.py` は触らない — 差分 0 行が DoD)。
- **Notion カード TSK-390 の DoD・「マージの条件」節・射程の縮小**の 3 件の是正
  ([plan.md](./plan.md) 5 節)。
