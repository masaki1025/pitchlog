---
feature: route-kind-vocabulary
status: active
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3e593b75e68781c9b811e86543960c6d
branch: feature/route-kind-vocabulary
created: 2026-09-24
計画レビュー周回: 1        # 敵対レビュー 1 周目(判定 否決・P0 6 / P1 4 / P2 1)の反映を含む
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: 製品 CRUD 経路の route_kind 値域を決める(TSK-446)

## 1. 背景・目的

**Notion**: [TSK-446](https://app.notion.com/p/3e593b75e68781c9b811e86543960c6d)(優先度 **高**)
**計画段階の調査**: [research.md](research.md)(調査サブエージェント 3 本 + 当方の原典実測)。**本書が事実を述べるときは正本・資産を直接引く**

[`../../design/data-model.md`](../../design/data-model.md)`:2454` が
「同ファイル(`contracts/authz/http-route-matrix.json`)に `route_id` を持たない HTTP の入口を開く PR は、
**同一 PR でその入口へ `route_id` を与える**」と要求する。ところが実測で:

| 事実 | 典拠 |
| --- | --- |
| `route-registry.json` と `http-route-matrix.json` は **exact-set**。片側だけの追加は必ず red | `scripts/check_authz_catalog.py:2437-2442` |
| `route_kind` は **4 値**に固定。**正は検査器の定数 `ROUTE_KINDS`** | 同 `:92` |
| **製品 CRUD を表す種別が存在しない** | 実測(`legacy_route` 13 / `shared_data` 12 / `management_operation` 8 / `control_read` 4) |
| **所有者を定めた記録が存在しない** | 全文探索 0 件。`TSK-380` の射程は既存 37 経路の `test_owner` 再割り当て([`../../adr/ADR-004-merge-gate-scope.md`](../../adr/ADR-004-merge-gate-scope.md)`:46`) |
| **拡張を禁じた条文も存在しない** | `docs/adr/` / `docs/requirements/` / `data-model.md` に `route_kind` の語が **0 件** |

### 本タスクが開けるもの(**1 周目で訂正** — 初稿は過大だった)

**新種別を要するのは「製品 CRUD の入口を開く単位」**である。
[`../product-impl-unit-split/plan.md`](../product-impl-unit-split/plan.md)`:502` の逐語:

> **FR-041 の経路所有**: **U-C1 = `management_operation` 8 / U-C2 = `control_read` 4 / U-C3 = `shared_data` 12**。
> **`route-registry.json` の `route_kind` で機械的に分かれる**(実測)

→ **U-C1 / U-C2 / U-C3 は既存 4 値で入口を開ける。**
初稿が書いた「**帯 2 の葉 6 本 + 帯 3 の 6 本 = 12 単位**」は誤りで、**製品 CRUD を開く単位に限られる**。
**該当単位の確定は本タスクの射程外**(各単位の経路表が正)だが、**帯 2 の葉 6 本は確実に該当する**。

### 種別ごとに必須キーが違う(実測 — 設計の中心)

| `route_kind` | 必須キー | 種別別の追加検査 |
| --- | --- | --- |
| `legacy_route` | `route_class` / `channel` / `expected_default` / `provenance_ids` | `origin == requirement` 強制(`:2131-2132`)/ `expected_default == deny_404`(`:2102-2103`)/ `legacy_route_ids` と exact-set(`:2122-2128`) |
| `shared_data` | `route_class` / `resource_kind` / `channel` | 3 軸直積 12 と exact-set + `route_id` を 3 軸から導出して照合(`:2140-2166`) |
| `control_read` | `control_read_id` / `access_requirement` | `control_read_ids` と exact-set(`:2168-2176`)/ `access_requirement ∈ {participant, admin}`(`:2107-2111`) |
| `management_operation` | `operation_id` | `operation_ids` と exact-set(`:2177-2185`)/ `management_operations` との相互一致(`:2112-2117`) |

**→ 既存 4 種はすべて「値域 + 種別別検査 + exact-set」の 3 点セットを持つ。新種別も同じ形を持たせる。**

## 2. スコープ

**本タスクは語彙だけを決める。経路は 1 本も足さない。**
検査器上これは成立する — 「全 `route_kind` が 1 件以上の route を持つ」制約は存在せず、
種別ごとの exact-set 照合は**その種別の route だけ**を抽出して行う(research.md 3 節)。
**1 周目の敵対レビューが実測で確認済み** — 値域だけ広げた状態で、
route registry / auth catalog / HTTP matrix の **entries と `aggregate_decision_digest` がいずれも不変**のまま
派生資産検査と oracle 意味検査を通過した。

### やること

1. **製品 CRUD 経路を表す `route_kind` の値・必須キー・種別別検査を決め、根拠を本計画書に書く**
2. **検査器を更新する**(4 節 — `ROUTE_KINDS` の直接参照に加え、種別別分岐と exact-set を新設)
3. **資産側の `enums.route_kinds`** を `contracts/authz/route-registry.json` と
   `tests/fixtures/authz_claims/route-registry.json` の**両方**で更新する
4. **負例テストを追加する**
5. **lock の再封印と凍結基準の移動**(4 節 — 本タスクの律速)
6. **`SCOPE:ALL_LOGICAL` / `SCOPE:DATA_READ` / `SCOPE:CONTROL` への対応を裁定し、記録する**

### やらないこと

| 項目 | 行き先 | 典拠 |
| --- | --- | --- |
| **実際の経路の登録**(選手・チームの `route_id` 付与) | **各単位が自 PR で行う** | `../../design/data-model.md:2454` |
| **既存 37 経路の `test_owner` 再割り当て** | **TSK-380** | `../../adr/ADR-004-merge-gate-scope.md:46`。**「付与と再割り当ては別の操作」**(`../product-impl-unit-split/plan.md:519`) |
| **path / method / 404 vs 403 の決着** | **TSK-346** | 同 `:45`。**新種別の必須キーに `http_method` / `path` / `expected_status` を含めない** |
| **`contracts/authz/product/` と capability** | **TSK-424** | 同タスクの射程に「authz ツールチェーンの一般化」が含まれる。**本タスクは `ROUTE_KINDS` の語彙だけ**と宣言する |
| **`claim` の到達経路種別の機械判定** | **TSK-383** | 本タスクは「**route の種別**」であって「**claim の到達経路種別**」ではない |
| **`boundary-proposal.json` への裁定の追記** | **しない**(下記) | `scripts/check_authz_catalog.py:4918` が `pending_human_reviews` を**既存 2 ID の exact-set**で固定しており、**3 件目を足すと `CatalogError`**(1 周目の敵対レビューが実測で確認)。**裁定は本計画書と PR 本文に残す** |
| **`mutation_execution.py` の `class_by_route_kind` への追加** | **しない**(発火させない) | 新種別の route が `claim-mutant-map` の `runtime_target` に現れない限り発火しない |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/` / `docs/design/data-model.md` / `docs/adr/` | **反映なし**。いずれにも `route_kind` の語が **0 件**(実測)で、**値域の正は検査器の定数だけ** | — |
| **`contracts/authz/route-registry.json`**(+ `.lock.json`) | `enums.route_kinds` へ 1 値追加。**`routes` は 37 件のまま** | PR レビュー(`contracts/authz/*` = `tenant-isolation` のコア) |
| **`contracts/authz/auth-catalog.json`**(+ `.lock.json`) | `route_scopes` の裁定次第 | 同上 |
| **`contracts/authz/oracle-seal.lock.json`** | `input_assets` の digest と `oracle_commit` | **人間レビュー必須**(`reseal_policy.human_review_required: true`) |
| **oracle 資産 6 本の `oracle_context.oracle_commit`** | 新しいコミット SHA へ差し替え | 同上 |
| **`contracts/authz/frozen-baselines.json`** | `history` へ 1 レコード(**10 キー必須** — 4 節) | **人間承認が schema レベルで強制** |

## 4. 実装方針

**重さ分類 = コア領域**。`scripts/check_authz_catalog.py` と `tests/test_check_authz_catalog.py` は
**`guard_paths`**(`.claude/core-areas.json:21`・`:32`)かつ **`tenant-isolation` のコア paths**(同 `:308`・`:309`)。
`contracts/authz/*` も同 `:307`。**`.claude/core-areas.json` への paths 登録は不要**(すべて既に一致している)。

### 4-1. 新種別の設計(**1 周目 P0-1 の是正** — 最小形は成立しなかった)

**1 周目の敵対レビューが実測で示した欠陥**: 共通 4 キー + `provenance_ids` だけでは、
`route_id: "garbage"` + `origin: design` + **既存 legacy 用 provenance の流用**が検査を通過する。
`origin == design` のときだけ provenance を見る現行構造(`:2085-2092`)に、
**「この種別なら design でなければならない」という制約が無い**ため。

**→ 既存 4 種と同じ「値域 + 種別別検査 + exact-set」の 3 点セットを持たせる。**

| 事項 | 提案 | 根拠 |
| --- | --- | --- |
| **必須キー** | 共通 4(`route_id` / `route_kind` / `origin` / `source_claim_ids`)+ **`provenance_ids`** + **`operation`** | `operation` の値域は**正本に根拠がある** — `../../design/data-model.md:2468-2474`「入口の到達性は〈主体 × 資源 × 操作〉の 3 軸で比べる」で、**操作の値域は逐語で「読取 / 追加 / 更新 / 削除」** |
| **`operation` の値域** | **`{read, insert, update}`**(閉じた集合) | **削除は論理削除**(要件書 4.0-2)なので `update` に含まれる。**`delete` を値域に置かない**ことで物理削除の経路を構造的に作れなくする |
| **`origin`** | **`design` を強制**(`legacy_route` が `requirement` を強制するのと同型 — `:2131-2132`) | 要件書に製品 CRUD 経路の条項が無い(research.md 2 節)。**強制することで「design のときだけ provenance を見る」現行構造の穴が塞がる** |
| **`route_id` の導出規則** | **`ROUTE:TENANT:<資源>:<OPERATION>`**。末尾が `operation` と**大文字小文字を無視して一致**すること | `shared_data` が 3 軸から `route_id` を導出して照合する形(`:2140-2166`)と同型 |
| **`provenance_ids`** | **専用 ID `PLAN-TSK446-TENANT-OWNED-DATA` を含むこと**を強制 | 既存 provenance(`PLAN-STEP4-LEGACY-DENY`)の流用を塞ぐ。**`design_provenance` の `path` に本計画書を指す前例がある**(`route-registry.json:78-84` の唯一の行が `docs/features/pg-authz-verification/plan.md`) |
| **`disposition`** | **既存の `conditional` へ写す** | **新値を作らない**。ただし理由は「404/403 を決めるから」ではない(**1 周目 P1-2 の是正** — `disposition` は HTTP status を決めていない。`:2395` の閉じた値域と `route_kind` の対応しか検査しない)。**新値は `http-route-matrix.json` の `route_dispositions` の exact-set(`:2397-2400`)も動かす**ため、**変更面を最小に保つ**のが理由 |
| **名前** | **`tenant_owned_data`**(代替: `record_and_aggregate`) | 「**自テナント所有**」は要件書 `:130` の用語定義の語。**⚠ 1 周目 P1-1**: 424 の表分類のプロファイル名 `tenant_owned` と語彙が揃う一方、**表の RLS プロファイルと経路分類を混同しうる**。代替の `record_and_aggregate` は要件書 `:849`「**制御資源は記録・集計とは別のクラスである**」から引ける。**裁定事項 1**(8 節) |

### 4-2. 検査器の変更箇所(**1 周目 P1-3 の是正** — 初稿の「6 箇所」は不正確)

**`ROUTE_KINDS` の直接参照は 4 箇所**だが、**種別別の分岐と exact-set を含めると変更面はもっと広い**。
初稿が「外 2 箇所」とした `boundary-proposal.json` の責務 exact-set は**同じ検査器内**であり、
**`route_kind` の直接参照ではない**。代わりに **`pending_human_reviews` の exact-set(`:4918`)が漏れていた**(2 節で「触らない」と決めた)。

| # | 場所 | 変更内容 |
| --- | --- | --- |
| 1 | `scripts/check_authz_catalog.py:92` | `ROUTE_KINDS` へ 1 値追加 |
| 2 | 同 `:1973-1976` | `enums.route_kinds` との **frozenset 完全一致**(資産側と対で更新) |
| 3 | 同 `:2068-2075` | **`expected_keys_by_kind` へ行を追加**(足し忘れると素の `KeyError`) |
| 4 | 同 `:2085-2092` の直後 | **新設**: `route_kind == "tenant_owned_data"` なら `origin == "design"` 強制 |
| 5 | 同 `:2112-2117` の直後 | **新設**: `operation` の値域検査・`route_id` の導出照合・専用 provenance の包含検査 |
| 6 | 同 `:2177-2185` の直後 | **新設**: 新種別の exact-set(**経路 0 件なので空集合と照合**) |
| 7 | 同 `:2411-2416` | **`disposition_by_kind` へ行を追加**(足し忘れると素の `KeyError`) |
| 8 | 同 `:2254` | `route_scopes` は**部分集合判定**なので機械上は不要。**裁定 5 次第**で `auth-catalog.json` を更新 |
| 9 | `ROUTE_KINDS` / `expected_keys_by_kind` / `disposition_by_kind` の**整合検査を新設** | **素の `KeyError` ではなく `CatalogError`** にする |

### 4-3. 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**TSK-312 の前例に倣い「テスト先行」で進める**。**総数が変わりうるため `/<N>` を書かない**。
**各ステップ終了時の期待失敗集合を明示する**(**1 周目 P0-4 の是正** — 途中のステップで全件 green は時系列上ありえない)。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **draft PR を先に作り、番号を確定する** — 凍結基準の `acceptance_id` は `<repo>#<PR番号>` から機械導出するため(`docs/worklog/2026-09-20-frozen-baseline-ledger.md:152`「**ステップ 1 で draft PR を先に作って番号を確定する**」) | PR 番号が確定している。**ステップ記法を付けない**(実装コミットではない) |
| 2 | **負例テストを先に置く** — ① 必須キー欠落 ② 未登録の `route_kind` 値 ③ `origin != design` ④ `route_id` が導出規則に合わない ⑤ 専用 provenance を含まない ⑥ `ROUTE_KINDS` と `expected_keys_by_kind` の不整合 | **6 種すべてが red**。red の出力を worklog へ実出力つきで残す。**期待失敗集合を先に完全列挙して固定**する |
| 3 | **検査器と資産を対で更新する** — 4-2 の 1〜7・9 と、`route-registry.json` + `tests/fixtures/authz_claims/route-registry.json` の `enums.route_kinds` | ステップ 2 の 6 種が **green**。**期待失敗**: `test_repository_derived_assets_are_valid`(lock 未更新のため)と `test_repository_oracle_assets_are_valid`(seal 未更新のため)は **red のまま**。**これ以外に red が無いこと**を全件実行で確認する |
| 4 | **派生 lock を再封印する** — `--reseal-derived --skip-oracle`。**fixture の lock は CLI が触らないので手で作り直す** | `route-registry.lock.json` の **`entries` と `aggregate_decision_digest` が変更前と完全一致**し、**`asset_digest` だけが変わる**(**1 周目 P1-4 の是正** — 件数だけでは判定不変を証明しない)。**期待失敗**: `test_repository_oracle_assets_are_valid` は red のまま |
| 5 | **oracle の内容を追随させ、人間の確認を受ける** — 前段コミットの SHA を **7 箇所の `oracle_commit`**(seal 1 + oracle 資産 6)へ差し替える。**この時点で敵対レビューと人間確認を受ける**(前例の順序は「**内容追随 → commit 差し替え → レビュー → reseal**」— `docs/worklog/2026-09-03-authz-claims-corpus.md:67`) | 差分が人間に確認されている。**まだ reseal しない** |
| 6 | **凍結基準の履歴を追記し、oracle を再封印する** — `frozen-baselines.json` の `history` へ **10 キーすべて**を持つ 1 レコード(`acceptance_id` / `series` / `new_identity` / `prior_identity` / `changes` / `placement_change` / `moved` / `reason` / `approved_by` / `approved_at`。**純粋な SHA 移動でも `changes` は最低 1 件・`placement_change` は no-op・`moved: false` が要る**)→ `--reseal-oracle` | `uv run python scripts/check_authz_catalog.py` が green。**`uv run python scripts/check_frozen_baselines.py --invariants-only`** が green(**mode 指定が必須** — 無指定は argparse error)。**全件 green はここで初めて成立する** |

## 5. DoD(受け入れ基準)

- [ ] 製品 CRUD 経路の `route_kind` の**値・必須キー・種別別検査**を決め、根拠を本計画書に書いた
- [ ] **既存 4 種と同じ「値域 + 種別別検査 + exact-set」の 3 点セット**を新種別も持つ
- [ ] **`origin == design` を強制**した(`legacy_route` が `requirement` を強制するのと同型)
- [ ] **`route_id` の導出規則**を検査した
- [ ] **専用 provenance ID の包含**を検査した(既存 provenance の流用を塞ぐ)
- [ ] `ROUTE_KINDS` / `expected_keys_by_kind` / `disposition_by_kind` の**不整合が `CatalogError` になる**(素の `KeyError` にしない)
- [ ] **`contracts/authz/route-registry.json` と `tests/fixtures/authz_claims/route-registry.json` の両方**を更新した
- [ ] **fixture の lock** を手で作り直した
- [ ] **`routes` を 1 件も増やしていない**
- [ ] **既存の判定が変わらない** — route registry / auth catalog / HTTP matrix の **`entries` と `aggregate_decision_digest` が変更前と完全一致**する(件数だけで済ませない)
- [ ] **`boundary-proposal.json` に触れていない**(`pending_human_reviews` は既存 2 ID の exact-set)
- [ ] **`mutation_execution.py` の `class_by_route_kind` を発火させていない**
- [ ] **凍結基準の履歴が 10 キーすべてを持つ**
- [ ] **oracle 差分の敵対レビュー + 人間確認**を **reseal の前**に受けた
- [ ] pytest / ruff / ty green
- [ ] 横断要求: 物理削除しない / テナント分離を全機能に適用 / 自動エスケープ

## 6. テスト計画

**DB を使わない**。ハーネス側の `tests/` のみ。

| 対象 | 種別 | 確認すること |
| --- | --- | --- |
| 必須キー欠落 | 負例 | `"キー不一致: 不足=[...]"` で red |
| 未登録の `route_kind` 値 | 負例 | `"route_kindが閉じた値域にない"` で red(**型 C** — `:2369-2411` の `route_class` 版を読み替え) |
| `origin != design` | 負例 | 新設の `CatalogError` で red |
| `route_id` が導出規則に合わない | 負例 | 同上 |
| 専用 provenance を含まない | 負例 | 同上 |
| `ROUTE_KINDS` と `expected_keys_by_kind` / `disposition_by_kind` の不整合 | 負例 | **素の `KeyError` ではなく `CatalogError`** |
| 既存 37 経路・187 catalog entries・12 cells | 回帰 | **`entries` と `aggregate_decision_digest` が完全一致** |

**負例の型**(**1 周目 P0-6 の是正** — 初稿は型 B の説明を誤っていた):
`:1686-1730` の `test_legacy_routes_require_requirement_origin_and_source_claims` は
**`origin` と `source_claim_ids` の「値」を差し替える**テストであって、**キー削除のテストではない**。
キー削除の負例は新規に作る。

**`-x` を使わず全件実行する**(期待失敗集合の完全列挙 — `docs/features/authz-claims-corpus/plan.md:70`)。

## 7. 依存・前提

**外部依存は無い。**`TSK-424` とも `TSK-344` とも `TSK-431` とも**独立に進められる**。

**⚠ ただし名前を `tenant_owned_data` にする場合**(裁定 1)、**424 の表分類のプロファイル名と語彙が結びつく**。
**424 側の分類変更で意味が変わりうる**(1 周目 P1-1)。**独立を優先するなら代替名を採る。**

**マージ順序**: **本タスク → 製品 CRUD の入口を開く各単位**。どちらも `route-registry.json` を触り、
`route-registry.json` と `http-route-matrix.json` は exact-set のため。

## 8. 人間の裁定が要る事項(**1 周目 P0-2 の是正** — 4 件では足りず 5 件に分けた)

| # | 事項 | 本書の提案 | 代替 |
| --- | --- | --- | --- |
| **1** | **新種別の名前** | **`tenant_owned_data`** | **`record_and_aggregate`**(要件書 `:849` が制御資源と対置する唯一のクラス名。**424 との語彙の結びつきを避けられる**) |
| **2** | **必須キー体系** | 共通 4 + `provenance_ids` + **`operation`**(値域 `{read, insert, update}`) | `operation` を持たせず `route_id` の導出規則だけで識別する |
| **3** | **`origin`** | **`design` を強制** | `requirement` を許し、要件主張との結線を要求する |
| **4** | **`disposition`** | **既存の `conditional` へ写す** | 新値を作る(**`route_dispositions` の exact-set も動く**) |
| **5** | **3 scope への対応** | **`SCOPE:ALL_LOGICAL` に入れる**(「論理経路の全体」の意味を保つ)。`SCOPE:DATA_READ` と `SCOPE:CONTROL` は**触らない** | `DATA_READ` にも入れる(製品 CRUD は読み取りを含むため)/ どこにも入れない |

**裁定の残し方**: **`boundary-proposal.json` には書けない**(`pending_human_reviews` は既存 2 ID の exact-set)。
**本計画書の承認そのものが裁定の記録**とし、PR 本文へも転記する。
