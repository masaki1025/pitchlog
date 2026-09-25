---
feature: route-kind-vocabulary
type: research
date: 2026-09-24
---

# 調査メモ: 製品 CRUD 経路の route_kind 値域を決める(TSK-446)

> **【行番号の基準 — 4 周目 P1-2 の是正】**
> **本書がコードへ与える行番号は、断りのない限り merge-base `bf8ba5b` 時点のものである。**
> 本書は**着手時点のコードを記述した調査メモ**であり、**本 PR 自身がこれらの行を動かす**。
> **確認は `git show bf8ba5b:<path>` で行う。**

## 問い

1. **4 値をこう切った理由**は何か。**「製品 CRUD を含めない」と決めた記録**はあるか
2. **新種別の名前と必須キー体系を、条文のどこから引けるか**
3. **検査器を広げるとき、何が壊れるか**(参照点・lock・封印・凍結基準)

**調査方法**: 調査サブエージェント 3 本(decision-tracer / spec-checker / Explore)を並列委任し、
**結論に効く事実は当方が原典で再実測した**。`legacy-analyst` は使っていない(旧システムに対応物が無いため)。

## 結論(要約)

1. **4 値は分類学ではなく「当時列挙した論理経路の母集団」をそのまま種別化したもの**。
   **「製品 CRUD を含めない」と決めた記録は存在しない**。**「4 値を変えるな」という条文も存在しない**
2. **新種別の名前を要件から引くことはできない**。「業務」「CRUD」は要件書に **0 hits**。
   既存 4 値も要件書に逐語が無く、**正は検査器の定数 `ROUTE_KINDS` だけ**。**名前は設計判断**
3. **最大の壁は凍結基準**。`route-registry.json` を 1 バイト変えると `--reseal-oracle` **自体が失敗**し、
   **`oracle_commit` の移動 → `frozen-baselines.json` への承認付き履歴追記**が要る。**台帳上の初回**になる
4. **検査器の参照点は 4 ではなく 6**。うち 2 つは dict の直参照で、**`CatalogError` ではなく素の `KeyError`** が飛ぶ
5. **当方の計画書に事実誤認が 2 件**(`route_scopes` の所在・参照点の数)。本メモで訂正する

## 詳細と典拠

### 1. 4 値の由来(decision-tracer)

**一次記録は `docs/features/pg-authz-verification/plan.md`**(TSK-270・承認 2026-08-31)。
3 周目のレビュー P1-7 で構造の不足が判明し、軸が分けられた。逐語(`:187-193`):

> `route_kind` の許可値が 2 種しかないのに、**FR-020〜032 を同じ直積の拒否行として表現するスキーマが無い**。したがって:
> - **`route_id` の閉じたレジストリを別に置く** — **FR-020〜032・制御資源の読み取り・7 操作を含む全論理経路**を列挙する
> - **`route_class`** で許可 2 種(`shared_screen` / `shared_aggregate_export`)を表す
> - **経路レジストリと HTTP 行列を exact-set で結ぶ**

**→ 4 値は「レジストリが列挙すると決めた 3 群 + 許可 2 種の直積セル」に 1:1 対応する**:

| `route_kind` | 母集団のどの群か | 件数 |
| --- | --- | --- |
| `legacy_route` | FR-020〜032(明示的拒否行) | 13 |
| `shared_data` | 許可される共有経路(`route_class` 2 × `resource_kind` 3 × `channel` 2 の直積) | 12 |
| `control_read` | 制御資源の読み取り | 4 |
| `management_operation` | 7 操作(資産側は 8 ID) | 8 |

#### 「製品 CRUD を含めない」— **決定なし**

- `route_kind` に言及する文書は **5 本のみ**で、製品 CRUD の除外に触れるものは **0 件**
- **当時は製品の HTTP 入口が 1 本も存在しなかった**(`/health` のみ)
- **「registry の閉世界は製品 CRUD を覆っていない」と読める根拠が 2 つある**:
  - 要件書 `:608`「**本原則の射程は「FR-041 が新設する権限・経路」に限られ、それ以外の権限源による既存のアクセスは本要件の射程外である**」
  - PO 前提確認(2026-09-17)「**FR-034 の「既定拒否の原則」を fail-closed の根拠に使わない**」

**→ 4 値に製品 CRUD が無いのは、当時の母集団に製品 CRUD が無かったからであり、排除の決定があったからではない。**

#### 「4 値を変えるな」— **条文なし**

`docs/adr/` / `docs/requirements/` / `docs/design/data-model.md` のいずれにも
`route_kind` / `route-registry` / `ROUTE_KINDS` の語が **0 件**。
**値域の正は `scripts/check_authz_catalog.py:92` の定数だけ**で、正本レベルの拘束は無い。

※ `data-model.md:2531` の「**4 件の文言は変えない**」は**越境テストの最低要求 4 件**の話で、`route_kind` とは無関係。

### 2. 名前と必須キーを条文から引けるか(spec-checker)

#### 引けない

- 要件書に「**業務**」「**CRUD**」は **0 hits**。`route_kind` の 4 値も `disposition` の 3 値も**要件書に逐語では存在しない**
- **FR-034 の認可行列 9 行に、製品 CRUD に当たる行は 1 行も無い**。行列の射程は要件書 `:608` が
  「FR-041 が新設する権限・経路」に明文で限定している

#### 引ける語(候補・すべて逐語)

| 語 | 出典 |
| --- | --- |
| **自チームのデータ** | 要件書 `:594`(FR-033)「操作は自チームのデータのみ、参照は自チームのデータおよび FR-041 で付与された範囲に限られる」 |
| **自チームが記録したデータ** | 同 `:848`(NFR-010) |
| **データ資源** | 同 `:848` / `:730` |
| **記録・集計** | 同 `:849`「**制御資源は記録・集計とは別のクラスである**」← **制御資源と対置してクラス名として使っている唯一の語** |
| **業務表 / 業務データ / 通常の読み書き** | `data-model.md:209` / `:229` / `:1544-1548` |
| **〈主体 × 資源 × 操作〉** | 同 `:2468-2474`「**入口の到達性は〈主体 × 資源 × 操作〉の 3 軸で比べる**」。操作の値域は「**読取 / 追加 / 更新 / 削除**」 |

**必須キー体系の根拠として最も強いのは `data-model.md:2468-2474` の 3 軸**。ただしこれは
**「到達性の比較軸」として定義されたもの**であって、**レジストリの必須キーとして指定されてはいない**。

#### `disposition` も要件から導出できない

3 値(`product_cell` / `conditional` / `deny_404`)は要件書にも設計正本にも**逐語で存在しない**。
要件から出せる判断材料は 2 点だけ:

- **`deny_404` は不適** — `legacy_route` の `deny_404` は「その経路は**共有グループ経由では開かない**」の表明。
  製品 CRUD は**自テナントからは通る**ので意味が合わない
- **`product_cell` は認可行列のセルを指す語**で、製品 CRUD に当たるセルが行列に存在しない

### 3. 検査器の具体形(Explore)— **参照点は 6 箇所**

| # | 行 | 何が起きるか |
| --- | --- | --- |
| 1 | `scripts/check_authz_catalog.py:92` | `ROUTE_KINDS` の定義。**唯一の正** |
| 2 | 同 `:1967`(`:1973-1976`) | `enums.route_kinds` と **frozenset 完全一致**。資産側にも同じ値を追記しないと red。**逆も同じ** |
| 3 | 同 `:2066` | 各 route の `route_kind` を閉じた値域へ落とす |
| 4 | 同 `:2068-2075` | **`expected_keys_by_kind` — dict の直参照**。新種別の行が無いと **`KeyError`(非 `CatalogError`)** |
| 5 | 同 `:2411-2416` | **`disposition_by_kind` — dict の直参照**。同上 |
| 6 | 同 `:2254` | `route_scopes[].route_kinds ⊆ ROUTE_KINDS` の**部分集合判定**。何もしなくても green |

**さらに検査器の外にも 2 箇所ある**(2 本目の調査 — 実測で裏取り):

| # | 場所 | 挙動 |
| --- | --- | --- |
| 7 | `backend/tests/db/authz/mutation_execution.py:897-909` の **`class_by_route_kind`** | 未知 kind は **`MutationContractError`**(「probe 関数へ写像できない route kind」)。**値域を足すだけなら発火しない**が、新種別の route が `claim-mutant-map` の `runtime_target` に現れた瞬間に red |
| 8 | `scripts/check_authz_catalog.py:5026-5031` の `boundary-proposal.json` の責務 **exact-set**(`{SHARED-AUTHORIZED-ROWS, CONTROL-READS, REPRESENTATIVE-MANAGEMENT}`) | route_kind 2〜4 の鏡像。**第 4 の責務を足すと oracle 資産の変更**になり `ORACLE_STEP5_REREVIEW` が発火する |

**→ 当方の計画書 4 節「参照点 4 箇所」は過少。検査器内で 6・外を含めて 8 箇所。**
**7 と 8 は「発火させない」ことを DoD に書いて境界を明示する。**

#### 必須キーは exact-set の裏返し

`_expect_keys`(`:605-612`)が `actual != expected` の**完全一致**を要求するため、
**必須キーの不足も未知キーの混入も同じ 1 箇所で red** になる。「禁止キー」という独立の判定は無い。

#### `origin: design` を新種別で使うと現状 `KeyError`

`origin == "design"` の分岐(`:2085-2092`)は `route["provenance_ids"]` を読むが、
**`provenance_ids` が許可キーに入るのは `legacy_route` だけ**(`:2068-2075`)。
→ **新種別を design origin で設計するなら、必須キー表に `provenance_ids` を含める必要がある。**

#### 既存 37 経路は壊れない

種別ごとの exact-set 照合は 4 種別それぞれに個別に書かれており(`:2122-2128` / `:2140-2166` / `:2168-2176` / `:2177-2185`)、
**新値を足すだけでは壊れない**。壊れるのは **`enums.route_kinds` の完全一致(`:1973-1976`)だけ**。

**「全 route_kind が 1 件以上の route を持つ」制約は無い**ので、
**値域だけ先に広げて経路は各単位の PR で足す、という分割は検査器上は成立する。**

### 4. 【最大の壁】凍結基準と oracle seal

**当方の実測**:

- `contracts/authz/oracle-seal.lock.json` の `input_assets` は **8 資産**で、
  **`route-registry.json` と `route-registry.lock.json` が含まれる**。`oracle_commit` = `24ef4fcc682b42b504edc1d6264d380760c54929`
- `contracts/authz/frozen-baselines.json` の `declarations` に **`oracle_input`** 系列があり、**`history` は 1 件のみ**
  (`acceptance_id: masaki1025/pitchlog#73` / `approved_by: 山田正輝` / `approved_at: 2026-09-21`)

`validate_oracle_seal` は `route-registry.json` について **2 つの digest 検査**を行う:

- `:5284` — **作業ツリー**の blob digest が seal の記載と一致
- `:5292-5306` — **`git rev-parse <oracle_commit>:contracts/authz/route-registry.json`** の blob が同じ digest

`--reseal-oracle` は作業ツリーから digest を再計算する(`:5216`)が、**再計算後にそのまま `validate_oracle_seal` を呼ぶ**(`:5842-5844`)。

> **したがって `route-registry.json` を変えたら、`oracle_commit` を「新しい内容を含むコミット」へ進めない限り、`--reseal-oracle` 自体が失敗する。**

そして `oracle_commit` は `frozen-baselines.json` の `oracle_input` が凍結しており、
`scripts/check_frozen_baselines.py:795-816` が**現在値と `history` 末尾の `new_identity` の一致**を検査するため、
**`history` へ 1 レコード追記(`acceptance_id` = `<repo>#<PR番号>` / `approved_by` / `approved_at`)が必須**。

**既存の履歴 1 件(PR #73)は値の移設であって値の変更ではない**(`prior` と `new` が同一 commit)。
**→ 「`oracle_commit` の値そのものを動かす」のは本タスクが台帳上の初回になる。**

さらに `check_authz_catalog.py:5022-5023` が `boundary-proposal.json` の `oracle_commit` を
台帳の `oracle_input` 系列と一致させることを要求する → **台帳を先に動かさないと checker が通らない順序依存**がある。

#### 連鎖(`route-registry.json` を変えたとき)

1. `route-registry.lock.json`(`--reseal-derived` — 3 資産の lock を**同時に**書き直す)
2. `http-route-matrix.json` + `.lock`(route を足すなら exact-set のため必須)
3. `auth-catalog.json` + `.lock`(`route_scopes` を触る場合のみ)
4. **`oracle-seal.lock.json` の `input_assets` 4 エントリ**(`--reseal-oracle`)
5. **oracle 資産 6 本の `oracle_context.oracle_commit`**
6. **`frozen-baselines.json` の `history` へ 1 レコード(人間承認つき)**

**`input_manifest` は変わらない** — 3 資産の `input_manifest` は `requirement-claims.json` とその lock しか指しておらず、
**派生資産どうしは繋がっていない**。派生資産を縛るのは `route_id` の exact-set と lock の digest と oracle seal。

**経路を 1 本も足さなくても lock は変わる** — `enums.route_kinds` に 1 要素足すだけで canonical digest が動く。
ただし `entries` は行テーブル由来なので **230 件のまま**(差分は `asset_digest` のみ)。

### 4-2. 【前例あり】`design_provenance` に行を足す形

**新種別を `origin: design` にすれば、要件主張との結線が不要**になる(`claim_dispositions` の 165 件にも触らずに済む)。
機械規則(`scripts/check_authz_catalog.py`):

| 規則 | 行 |
| --- | --- |
| `design` → `source_claim_ids` は**空必須**(「design origin は要件主張を名乗れない」) | `:2085-2087` |
| `design` → `provenance_ids` が `design_provenance` の閉集合の部分集合かつ空でない | `:2088-2092` |
| `legacy_route` は **`requirement` origin 必須**(design 不可) | `:2131-2132` |

**`design_provenance` の行の要件**(`:1794-1817`): `{provenance_id, path, extracted_text}` の exact キー /
`path` はリポジトリ内 / **`extracted_text` が `path` の原文と空白無視で逐語一致**(`:1811-1813`)/ `provenance_id` 重複禁止。

**既存行は 1 件だけ**で、その `path` は **`docs/features/pg-authz-verification/plan.md`**(= **正本ではなく feature 計画書**)。

> **→ 本タスクの `docs/features/route-kind-vocabulary/plan.md` に決定文を逐語で書き、それを `extracted_text` として引く形が前例どおりになる。正本の改訂は要らない。**

**⚠ ただし `origin: "design"` は現行スキーマでは「デッドな値域」である**(2 本目の調査 — 実測で裏取り):

- `:2089` が `route["provenance_ids"]` を読むが、**そのキーが許可されるのは `legacy_route` だけ**(`:2068-2075`)
- 一方 **`legacy_route` は `origin: requirement` 強制**(`:2129-2132`)
- **→ 現行のどの種別でも `design` origin は成立しない。**実在も 0 件

**したがって新種別で design origin を使うなら、必須キー表に `provenance_ids` を含める設計が前提**になる。
これは「デッドだった値域を初めて生かす」変更であり、**計画書で明示的に扱う**。

### 4-3. 凍結基準を動かす承認手順(記録されている逐語)

| # | 手順 | 典拠 |
| --- | --- | --- |
| 1 | **draft PR を先に作って番号を確定する** — 「`repository` + PR number へ一本化し、ステップ 1 で draft PR を先に作って番号を確定する」 | `docs/worklog/2026-09-20-frozen-baseline-ledger.md:152`(5 周目 P0-1) |
| 2 | registry の変更をコミットする | — |
| 3 | **その SHA を 7 箇所の `oracle_commit` へ差し替える**(seal 1 + oracle 資産 6) | `contracts/authz/frozen-baselines.json:69-84` |
| 4 | **台帳 `history` へ 1 レコード** — `acceptance_id`(`^[^/]+/[^#]+#[1-9][0-9]*$`)/ **`approved_by` / `approved_at`(`^\d{4}-\d{2}-\d{2}$`)は schema 必須** = **人間の承認が schema レベルで強制される** | `contracts/authz/frozen-baselines.schema.json:789-845` |
| 5 | **oracle 差分の敵対レビュー + 人間確認** — `review_policy: ORACLE_STEP5_REREVIEW` / `reseal_policy.human_review_required: true` | `contracts/authz/oracle-seal.lock.json:78-88` |
| 6 | `--reseal-oracle` | — |

**承認者・承認日は取得元を明記して逐語転記する。取得不能なら停止する**(`docs/worklog/2026-09-20-frozen-baseline-ledger.md:63`)。
CI が受理遷移を機械検査する(`base.ref == develop` の限定・`base.sha`/`head.sha` の親照合 —
`scripts/check_frozen_baselines.py:1009-1023`・`:1304-1342`・`:1395-1412`)。

**reseal の実行順**(TSK-312 の前例 — `docs/worklog/2026-09-03-authz-claims-corpus.md:51`・`:67`):
①`--reseal --skip-derived --skip-oracle` ②派生更新 ③`--reseal-derived --skip-oracle` →
oracle は「**内容追随 → commit 差し替え(最終形確定)→ レビュー → reseal**」。

### 5. 前例 — TSK-312 ステップ 6(2026-09-03)

**`route_kind` 自体の拡張前例は無い**が、**閉じた値域を広げた前例は実在する**(2 本目の調査で判明 — 当方の初稿の「前例なし」は誤り)。

#### 前例 A: `operation_ids` を 7 → 8 に広げた(人間裁定 D-4・2026-09-09)

**資産の形**(実測 — `contracts/authz/boundary-proposal.json` の `pending_human_reviews[]`):

```json
{ "review_id": "PENDING-MANAGEMENT-COMMAND-COUNT",
  "status": "human_decided",
  "frozen_value": 8,
  "alternative_value": 7,
  "affected_ids_if_changed": ["issue_invitation", "revoke_invitation",
    "ROUTE:MANAGEMENT:ISSUE_INVITATION", "HTTP:ROUTE:MANAGEMENT:ISSUE_INVITATION",
    "FR-041/list_item-006#issue-permission", "..."],
  "oracle_change_action": "return_to_step_5_and_re_review" }
```

**運用の型**: ① 起票時に**保留中の裁定**として oracle へ明記し、**変わる場合の影響 ID を先に列挙**する
② 人間裁定で `frozen_value` を確定(`status: human_decided`)
③ **要件の数え方と実装の数え方がずれるなら「1:N 写像」を明示**して両立させる
(要件書は「7 操作」・資産は 8 ID。裁定 D-4 =「frozen 値を確定として承認(8 と 29)+ 要件の『7 操作』との 1:N 写像を明示」)

**⚠ ただし本タスクでは同じ形を使えない**(1 周目の敵対レビューが実測で確認):
`scripts/check_authz_catalog.py:4919-4923` が `pending_human_reviews` を**既存 2 ID の exact-set**で固定しており、
**3 件目を足すと `CatalogError: 保留中の人間裁定2件が exact-set 不一致`** になる。
**→ 裁定は計画書の承認そのものと PR 本文に残す。**

#### 前例 B: `claim_dispositions` の新設(`docs/worklog/2026-09-03-authz-claims-corpus.md:146-147`)。
**なぞるべき手順の型**:

1. **テスト先行** — 負例フィクスチャを先に置き red を実出力つきで確認 → 実装 → green
2. **期待失敗集合を委任前に完全列挙して固定**
3. **実資産への追随は別ステップ**(任意フィールドなら実資産を動かさずに済む — 設計上の逃げ道)
4. **reseal 3 段の実行順を固定**: ①`--reseal --skip-derived --skip-oracle` ②派生更新 ③`--reseal-derived --skip-oracle`。
   oracle は「**内容追随 → commit 差し替え → レビュー → reseal**」(同 `:51`・`:67`)
5. **oracle 差分の敵対レビュー + 人間確認**(`oracle-seal.lock.json` の `review_policy: ORACLE_STEP5_REREVIEW`・
   `reseal_policy.human_review_required: true`)

#### 負例テストの型(Explore)

`tests/test_check_authz_catalog.py` に **`route_kind` の値域を対象にした負例テストは現存しない**(`route_kind` の語は `:1711` の 1 箇所のみ)。
新規に作ることになる。雛形は **型 C**(`:2369-2411` の `test_all_route_class_values_reject_an_unregistered_value`)で、
`path[-1] == "route_kind"` / `path[-2] == "route_kinds"` に読み替える。
必須キー欠落の負例は**型 B**(`:1686-1730`)が型。スタイルは `assert failures == []` / `assert escaped == []` の集約 assert。

### 6. 射程の境界

| タスク | 判定 | 典拠 |
| --- | --- | --- |
| **TSK-346**(API 契約の正本) | **踏まない。ただし条件つき** — `route_kind` は path / method を持たない**論理経路の種別**(`data-model.md:2441-2443`)。**必須キーに `http_method` / `path` / `expected_status`(404 か 403 か)を含めると射程を踏む** | `ADR-004:45`・`:154`(射程侵犯の判定)/ `product-impl-unit-split/plan.md:499-500` |
| **TSK-380**(`test_owner` 再割り当て) | **踏まない**。「付与と再割り当ては別の操作」が明文化済み。**条件: 既存 37 行の `test_owner` に 1 文字も触れないこと** | `ADR-004:46` / `product-impl-unit-split/plan.md:519` |
| **TSK-424** | **⚠ 射程に「authz ツールチェーンの一般化」が含まれる**(`tenant-boundary-enforcement/plan.md:75`)。`check_authz_catalog.py` の値域拡張は**広義にはこれに触れうる**。→ 計画書で「**本タスクは `ROUTE_KINDS` の語彙だけ。`contracts/authz/product/` にも capability にも触れない**」と明示宣言する。なお同 `:87`「製品表向けの汎用 CRUD の公開は TSK-424 の表分類が確定するまで公開しない」は、**語彙を決めることは「公開」ではない**ので抵触しない。あわせて**独立性の根拠がリポ内に無い** — 当方の計画書 7 節「424 は `route-registry.json` に触らない」は、**リポ内に典拠が存在しない**(Notion カードと 424 のブランチが出所)。**典拠として 424 の計画書か Notion カードを明記する必要がある** | `docs/worklog/2026-09-17-tenant-boundary-enforcement.md:70-73` が唯一の言及 |
| **TSK-383**(「入口を開く」の機械判定) | **表裏になりうる**。本タスクは「**route の種別**」であって「**claim の到達経路種別**」ではない、という線を計画書で引く | `ADR-004:43` / `contract-only-runtime-handoff/research.md:255-258` |

### 7. 当方の計画書の事実誤認(本メモで訂正)

| 計画書の記述 | 判定 | 正 |
| --- | --- | --- |
| 「`route_scopes`(`route-registry.json` のトップレベルキー)」 | **誤り** | **`auth-catalog.json` のトップレベルキー**(実測 — `route-registry.json` のトップレベルキーは 8 つで `route_scopes` を含まない) |
| 「`ROUTE_KINDS` の参照点 4 箇所」 | **過少** | **6 箇所**(§3) |
| 「lock を再封印し」 | **不足** | **oracle seal の `oracle_commit` 移動と凍結基準台帳への承認付き履歴追記**が要る(§4) |

## 未解決・申し送り

### 人間の裁定が要るもの

1. **新種別の名前** — 要件から引けない。**設計判断**。候補は §2 の表(「記録・集計」が要件書で制御資源と対置される唯一のクラス名)
2. **必須キー体系** — 要件から引けない。最も強い根拠は `data-model.md:2468-2474` の**〈主体 × 資源 × 操作〉**
   だが、これは到達性の比較軸であってレジストリのキーとして指定されたものではない
3. **`disposition` の当て先** — 要件から導出できない。**`deny_404` は意味が合わず、`product_cell` は行列にセルが無い**。
   `conditional` に写すか新値を作るかの判断
4. **`SCOPE:ALL_LOGICAL` に新種別を入れるか** — **機械は強制しない**(部分集合判定)が、
   同スコープは「論理経路の全体」の意味で使われており、**入れないと読みが黙って壊れる**
5. **凍結基準 `oracle_input` の `oracle_commit` を動かす承認** — **台帳上の初回**。人間承認が必須

### 決定が存在しない(原典で確認できなかった)

- **「製品 CRUD を含めない」と決めた記録**(§1)
- **「4 値を変えるな」という条文**(§1)
- **要件から route を導出する規則**(存在するのは逆向きの網羅検査だけ)

### 実装上の罠(計画書の合格条件に入れる)

- `ROUTE_KINDS` / `expected_keys_by_kind` / `disposition_by_kind` は**対で更新**。片方だけだと**素の `KeyError`**
- `contracts/authz/route-registry.json` **と** `tests/fixtures/authz_claims/route-registry.json` の
  `enums.route_kinds` を**両方**同時更新
- **fixture の lock** は CLI の `--reseal-derived` では更新されない。手で作り直す
- `--reseal-derived` は内部で `pytest --collect-only` を走らせる。`status: "implemented"` の test id は**実在必須**
- `route-registry.json` の `routes[]` には `test_owner` が無い。**新経路の owner は matrix 側**で付ける
