---
feature: tenant-session-supply
type: research
date: 2026-09-26
---

# 調査メモ: Session の供給 + 複数 operation の 1 トランザクション単位(TSK-444 / TSK-424 PR C)

> **行番号の基準**: 断りのない限り **`origin/develop` = `b4ae7394`** 時点。
> 確認は `git show b4ae7394:<path>` で行う。

## 問い

1. **「複数 operation を 1 トランザクション」は U-T1 の確定事項に反しないか**
2. **FR-018 / FR-039 / FR-017 が原子性について何を要求しているか**(要求と、要求していないこと)
3. **何を触ることになるか**(公開面・契約資産・凍結基準・既存テスト)

**調査方法**: 調査サブエージェント 3 本(spec-checker / decision-tracer / Explore)を並列委任し、
**結論に効く事実は当方が原典で再実測した**。`legacy-analyst` は使っていない(旧システムに対応物が無い)。

## 結論(要約)

1. **「1 束縛 = 1 文」という条文も検査も存在しない。** 既存の**合格テスト**が **1 束縛 2 文**を正例として固定している。
   **矛盾しているのは条文ではなく現行の実装形**であり、**禁止ではなく未実装**
2. **必要性は正本が 4 箇所で既に要求している**。現行の「1 呼び出し = 1 トランザクション」ではどれも満たせない
3. **カードの主張 2 件が原典と食い違う** — 「同一トランザクションの規定は `T7` だけ」「FR-039 が同一トランザクションを要求」
4. **最初にぶつかる壁は `Session` の使い捨て制約**。束縛の印を消すコードが**リポジトリ全体に存在しない**
5. **`base.py` / `binding.py` の当該行を書き換えると、迂回検査の変異テストが壊れる**(literal アンカー)

## 詳細と典拠

### 1. 「複数 operation を 1 トランザクション」は条文に反しない(最重要)

#### 1-1. 条文は「先頭」しか縛っていない

| 典拠 | 逐語 | 何を縛るか |
| --- | --- | --- |
| `docs/features/tenant-boundary-enforcement/plan.md:173` ① | 業務トランザクション内の**発行 SQL 列の先頭が束縛文**(観測窓は `Session.begin()` 以降) | **列**と書いている = 2 件以上を前提。件数の上限を課す語が無い |
| `docs/features/tenant-boundary-enforcement/design.md:403` | **束縛より前に他の SQL が出ない**こと | 制約は**前**だけ |
| `docs/design/data-model.md:320` | **1 トランザクションの最初**に `SELECT set_config('app.tenant_id', :tenant_id, true)` を発行する | 「最初」は順序であって排他ではない |

#### 1-2. 既存の合格テストが 1 束縛 2 文を正例として固定している(**当方の実測**)

`backend/tests/test_authz_tenant_binding.py:1174` のテスト名は
**`test_tenant_binding_is_first_and_local_guc_clears_after_commit`** — **`is_first` であって `is_only` ではない**。

```python
with _tenant_transaction(session, context):
    marker = session.execute(text(_PROBE_STATEMENT), {...}).scalar_one()
...
assert observed_statements == [_BINDING_STATEMENT, _PROBE_STATEMENT]   # :1226
```

**→ 1 回の束縛の中で束縛文 + 業務文の 2 文を発行するのが現行の正例である。**

#### 1-3. 矛盾しているのは実装形

- `backend/src/pitchlog/repositories/base.py:194` — `with _tenant_transaction(self._session, context):` が
  **`_execute_operation` の内側**にある。**トランザクション境界 = operation の境界**
- `backend/src/pitchlog/repositories/binding.py:60-61` — `if _BOUND_TENANT_INFO_KEY in session.info: raise TenantBindingError(...)`

**→ `execute` を 2 回呼ぶと 2 回目が落ちる。** これは U-T1 が射程を絞った結果(公開面は
「文脈束縛・実行器の token 入口・空の越境関数 registry」まで — `plan.md:174`)であり、**禁止ではなく未実装**。

### 2. 必要性は正本が既に要求している

| 典拠 | 要求 |
| --- | --- |
| 要件書 `:303`(FR-012) | べき等キー記録・イベント保存・prefix 更新・状態遷移が**単一の DB トランザクションで確定する** |
| 要件書 `:391`(FR-018) | **紐づけ判定と削除が同一トランザクション**で行われ、**判定後に紐づいた場合は失敗する** |
| `docs/design/data-model.md:1757-1759`(**FR-041 — 9-1 節**) | **上限検査の前にグループ行を排他ロックし、挿入まで保持**(`SELECT ... FOR UPDATE` 相当)**または `SERIALIZABLE` + 再試行**。**この二択は FR-041 のものであり、FR-018(11-1 節)へ転用してはならない**(**1 周目 P0-1** — 初稿の計画書が転用していた) |
| `docs/design/sync-protocol.md:1258-1264` | **P2 = T1・T2・T3・T4・T5・T6 の 6 要素**を 1 トランザクション |

**要件書で「同一トランザクション」の語が現れるのは `:391` の 1 行だけ**(spec-checker の全文検索)。

### 3. カードの主張の訂正(**当方が原典で実測**)

#### 3-1. 「同一トランザクションの規定は `T7` だけ」は**正本全体としては誤り**

`docs/design/data-model.md` の「同一トランザクション」は **20 行**存在する(**1 周目の典拠監査で 18 → 20 へ訂正**)。
とくに **TSK-444 の直接の対象である FR-018 の不変条件が `:2030` に明記**されている(逐語):

> | **同一トランザクション** | **紐づけ判定と削除を同一トランザクションで行い、判定後に紐づいた場合は失敗**する(FR-018) | **本書で決める** |

カードの主張が真なのは **11-2 節(キャッシュ無効化契約)の範囲内だけ**(同節では `:2148` の `T7` 行のみ)。
**「`T7` だけ」を正本全体の事実として計画書に書くと矛盾になる。**

#### 3-2. 「FR-039 が判定と削除の同一トランザクションを要求」は**典拠が存在しない**

要件書 `:412` の逐語(**当方が実測**):

> Given 誤登録のチーム / When 削除 / Then 論理削除の共通原則(4.0-2)に従う。**試合・選手が紐づくチームは削除不可でリネームへ誘導される**

**同一トランザクションの文言は無い。** 設計正本側にも FR-039 削除の原子性規定は無い。
→ **TSK-444 で FR-039 に原子性を約束するなら、要件・設計の裏付けが無い追加**であると明記する。

#### 3-3. FR-017 は「推奨」であって要求ではない(カードの記載と整合)

要件書 `:383` / `:996`、`data-model.md:2070` のいずれも**同一トランザクションを要求していない**。
`data-model.md:2148` の同一トランザクション規定は **`T7`(同期プロトコル `P3` の無効化発火)に紐づく**もので、
FR-017 経路に適用する条文ではない。**FR-017 を要求として扱うと過剰実装になる。**

### 4. 最初にぶつかる壁 — `Session` は生涯 1 回しか束縛できない(**当方の実測**)

`_BOUND_TENANT_INFO_KEY` の全出現は **3 行だけ**:

```
backend/src/pitchlog/repositories/binding.py:14   定数定義
backend/src/pitchlog/repositories/binding.py:60   存在チェック(拒否)
backend/src/pitchlog/repositories/binding.py:65   書き込み
```

**`pop` / `del` / クリアする箇所は `backend/` `tests/` のいずれにも存在しない。**
しかも `:60` は **tenant_id を比較せずキーの存在だけ**で拒否するので、**同一テナントでの再入も拒否される**。

**→ 「複数 operation を 1 トランザクション」は、束縛を 2 回行う形では作れない。
1 回の `_tenant_transaction` の内側で複数の登録済み operation を実行する形にしかできない。**

### 5. Session を作る手段が存在せず、作る権利も無い

- `backend/src` に `sessionmaker` / `async_sessionmaker` / `AsyncSession` / `Session(` は **0 件**
  (`db/tenant_isolation/models.py:519` の `class AdminSession` は ORM モデル名の偶然一致)
- `create_database_engine()` は **`Engine` を返すだけ**(`backend/src/pitchlog/db/engine.py:426`・`:447`)
- `contracts/tenant_boundary/base-allowlist.json:804-848` の **`allowed_symbols` は 5 件**で、
  **Session を「作る」シンボルは 0 件**
- `sqlalchemy.orm.Session` のコンストラクタは `db-api-inventory.json` の **`receiver_factories`**(`:121-124`)にあり
  **`apis` には無い** → **呼び出し自体は TB005 にならない**が、返り値は provenance `db` になり、
  以後の `.begin()` / `.execute()` / `.commit()` は**許可シンボル外なら TB005**
- **製品コードに `TenantRepositoryBase` のサブクラスは 0 件**。`_session` を実装しているのは**テスト内だけ**

### 6. 公開面は必ず動く(**当方の実測**)

```python
# backend/tests/test_authz_repository_contract.py:250
assert public_methods == {"execute"}
```

**公開メソッドを 1 つ足せば red。** ただし判定は `not name.startswith("_") and inspect.isfunction(value)` なので、
**`_session` は `_` 始まりの property であり exact-set の対象外**(`base.py:155-158`)。

### 7. 【要注意】`base.py` / `binding.py` の当該行を書き換えると変異テストが壊れる(**当方の実測**)

`tests/test_check_tenant_boundary_bypass.py:644-652` は、**`backend/src` の実ソースを literal 文字列で置換**して変異を作る:

```python
source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
mutated = source.replace(
    "from sqlalchemy.orm import Session", ...
).replace(
    "            execution_result = self._session.execute(\n", ...
```

**アンカー文字列がソースから消えると `assert mutated != source` が red になる。**
`base.py:194` 付近を触る本タスクは、**この変異テストの更新が不可避**。

### 8. 凍結基準の記録は機械が強制する(前回 TSK-446 との差)

TSK-431 の 7C(**PR #78・マージ済み**)が入れた機構:

```
scripts/frozen_history.py:39-41    予約 marker を拒否 {"PENDING","TODO","TBD","未承認","未定","レビュー待ち"}
scripts/frozen_history.py:1521     approved_by は非空・approved_on は実在する ISO 日付
```

- 記録は **v2 形式・9 キー exact-set**(`record_schema_version` / `acceptance_id` / `new_baseline_identifiers` /
  `previous_baseline_identifiers` / `change` / `movement_fact` / `reason` / `approved_by` / `approved_on`)
- **authority は `base-allowlist.json` のみ**。**同一受理で 2 件追記は red**
  (`docs/features/tenant-boundary-baseline/plan.md:115`)
- `change.aspect` は**実差分から機械導出し申告値と exact-set 照合**(同 `:94` の D3)
- 雛形は **`contracts/tenant_boundary/base-allowlist.json:70-782` の 1 件だけ**

> **TSK-446 の教訓**: 承認記録の出所が取れず**敵対レビューが 3 周連続で P0**。
> **今回はプレースホルダを機械が拒否する**ので、**着手前に出所を決めておく**。

### 9. 「1 operation = 1 表」は本タスクと直交する

`backend/src/pitchlog/authz/capability_registration.py:1256-1257` が
**カタログ行の `table_id` 1 個から作った frozenset と exact-set 比較**している。
これは **1 つの capability(= 1 つの token)が参照できる表の数**への制約であって、
**1 トランザクションに載せられる operation の数への制約ではない**。
`design.md` / `plan.md` に **1 トランザクションあたりの operation 数に触れた条文は無い**。

**→ 複数 capability を 1 トランザクションで並べるだけなら capability 側の変更は不要。**

## まだ決まっていないこと(本タスクで決める)

| # | 事項 | 「決まっていない」の典拠 |
| --- | --- | --- |
| U-1 | **`_session` を満たす具体的な供給形** | 所有だけが決まっている(`docs/worklog/2026-09-24-product-authz-surface.md:19`)。**方式を定めた条文は無い** |
| U-2 | **複数 operation を束ねる公開 API の形** | U-T1 は「公開面が exact-set」「token だけを受ける署名」を要求するが、**メソッドの個数・形は定めていない** |
| U-3 | **行ロックか `SERIALIZABLE` か** | `docs/design/data-model.md:1760`「**どちらを採るかは実装の判断**」 |
| U-4 | **分離レベルの既定値・リトライ方針** | **言及なし**(ADR・設計正本・D-* のいずれにも無い) |
| U-5 | **savepoint / `begin_nested` の採否** | **言及なし**(`db-api-inventory.json:883` に API 登録があるだけ) |
| U-6 | **FR-018 の述語 SQL とロックを誰が決めるか** | `data-model.md:2033`「**具体的なロック方式・SQL は実装計画へ送る**」— **委譲先が U-M1 か本タスクかは正本に無い** |

## 触ることになるもの

**必ず触る**: `repositories/base.py` / `repositories/binding.py` / **新規の Session 供給モジュール**

**契約資産**: `base-allowlist.json`(`allowed_symbols` + `contract_revision` + 履歴)/
`repository-contract.json`(`public_surface` + `source_digest` + `contract_revision`)/
`repository_contract.py`(生成モジュール・JSON と 1:1)/
`db-api-inventory.json`(触ると allowlist の `inventory.sha256` も更新必須)/
`tests/fixtures/tenant_boundary/positive/**`(許可シンボル 1 つにつき fixture 1 本)

**red になる既存テスト**(**1 周目の典拠監査で訂正** — 初稿は「確実に red」と書いたが、
**空集合系は計画どおり空のままなら green で通る**):

| テスト | red になる条件 |
| --- | --- |
| `test_authz_repository_contract.py:242-245`・`:250` | **公開面を増やしたとき**(本タスクは増やすので red) |
| `tests/test_check_tenant_boundary_bypass.py:644-682` | **`base.py` の literal アンカーが消えたとき**(本タスクは消すので red) |
| `tests/test_check_tenant_boundary_bypass.py:2965-3012` | **許可シンボルの署名が契約と食い違うとき** |
| `test_authz_repository_contract.py:269-271` / `test_authz_capability_registration.py:1022-1027` | **`PRODUCT_*` を空でなくしたとき**。本タスクは**空のまま残すので green のまま** |
| `tests/test_check_tenant_boundary_bypass.py:23-33`(`PRODUCT_APPLICATION_PATHS`) | **新規ファイルとの exact-set 検査ではない**。新規許可シンボルを導入した PR で**全要素が差分に含まれること**を要求する形 |
