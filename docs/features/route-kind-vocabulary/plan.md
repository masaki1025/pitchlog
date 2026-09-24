---
feature: route-kind-vocabulary
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e593b75e68781c9b811e86543960c6d
branch: feature/route-kind-vocabulary
created: 2026-09-24
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書: 製品 CRUD 経路の route_kind 値域を決める(TSK-446)

<!-- 本文は /plan で起草する。以下は /task-start が記入した着手時点の与件 -->

## 1. 背景・目的

**Notion**: [TSK-446](https://app.notion.com/p/3e593b75e68781c9b811e86543960c6d)(優先度 **高**)
**計画段階の調査**: [research.md](research.md)(調査サブエージェント 3 本 + 当方の原典実測)。**本書が事実を述べるときは正本・資産を直接引く**

**帯 2 の葉 6 本と帯 3 の 6 本 = 12 単位が、これが無いと HTTP 入口を 1 本も開けない。**

[`../../design/data-model.md`](../../design/data-model.md)`:2454` が
「同ファイル(`contracts/authz/http-route-matrix.json`)に `route_id` を持たない HTTP の入口を開く PR は、
**同一 PR でその入口へ `route_id` を与える**」と要求する。ところが実測で:

| 事実 | 典拠 |
| --- | --- |
| `route-registry.json` と `http-route-matrix.json` は **exact-set**。片側だけの追加は必ず red | `scripts/check_authz_catalog.py:2437-2442` |
| `route_kind` は **`{legacy_route, shared_data, control_read, management_operation}` の 4 値**に固定。**正は検査器の定数 `ROUTE_KINDS`** | 同 `:92` |
| **選手・チーム等の製品 CRUD を表す種別が存在しない** | 実測(`route_kind` 分布 = legacy_route 13 / shared_data 12 / management_operation 8 / control_read 4) |
| **所有者を定めた記録が存在しない** | 全文探索 0 件。**`TSK-380` の射程は既存 37 経路の `test_owner` 再割り当て**であって値域拡張ではない |

### 種別ごとに必須キーが違う(実測 — 設計の中心)

| `route_kind` | 必須キー |
| --- | --- |
| `legacy_route` | `route_class` / `channel` / `expected_default` / `provenance_ids` |
| `shared_data` | `route_class` / `resource_kind` / `channel` |
| `control_read` | `control_read_id` / `access_requirement` |
| `management_operation` | `operation_id` |

**→ 新しい種別にも独自のキー体系を決める必要がある。**

## 2. スコープ

**本タスクは語彙だけを決める。経路は 1 本も足さない。**
検査器上これは成立する — 「全 `route_kind` が 1 件以上の route を持つ」制約は存在せず、
種別ごとの exact-set 照合は**その種別の route だけ**を抽出して行う(research.md 3 節)。

### やること

1. **製品 CRUD 経路を表す `route_kind` の値と必須キー体系を決め、根拠を本計画書に書く**
2. **検査器の 6 箇所**(`ROUTE_KINDS` / `enums` 突合 / route 検査 / `expected_keys_by_kind` / `disposition_by_kind` / `route_scopes`)を更新する
3. **資産側の `enums.route_kinds`** を `contracts/authz/route-registry.json` と
   `tests/fixtures/authz_claims/route-registry.json` の**両方**で更新する
4. **負例テストを追加する**(新種別に必須キーを欠いた行 / 未登録値 / 対で更新し忘れた場合)
5. **lock の再封印と凍結基準の移動**(4 節 — 本タスクの律速)
6. **`SCOPE:ALL_LOGICAL` に新種別を入れるかを裁定し、記録する**

### やらないこと

| 項目 | 行き先 | 典拠 |
| --- | --- | --- |
| **実際の経路の登録**(選手・チームの `route_id` 付与) | **各単位が自 PR で行う**(U-M1 ほか) | `../../design/data-model.md:2454` |
| **既存 37 経路の `test_owner` 再割り当て** | **TSK-380** | `../../adr/ADR-004-merge-gate-scope.md:46`。**「付与と再割り当ては別の操作」**(`../product-impl-unit-split/plan.md:519`) |
| **API 契約の正本化**(path / method / 404 vs 403) | **TSK-346** | 同 `:45`。**⚠ 新種別の必須キーに `http_method` / `path` / `expected_status` を含めると射程を踏む**(同 `:154` が逆向きの畳み込みを「射程侵犯」と却下) |
| **`contracts/authz/product/` と capability** | **TSK-424** | 同タスクの射程に「**authz ツールチェーンの一般化**」が含まれるため、**本タスクは `ROUTE_KINDS` の語彙だけ**と明示宣言する |
| **`claim` の到達経路種別の機械判定** | **TSK-383** | 本タスクは「**route の種別**」であって「**claim の到達経路種別**」ではない |
| **`disposition` の新値の追加** | **しない**(既存 3 値へ写す) | 新値は「その経路の既定 HTTP 応答」を決めることになり **TSK-346 の射程**に触れる |
| **`mutation_execution.py` の `class_by_route_kind` への追加** | **しない**(発火させない) | 新種別の route が `claim-mutant-map` の `runtime_target` に現れない限り発火しない |
| **`boundary-proposal.json` の責務への第 4 の追加** | **しない** | 足すと oracle 資産の変更になり `ORACLE_STEP5_REREVIEW` が発火する |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/requirements/` / `docs/design/data-model.md` / `docs/adr/` | **反映なし**。いずれにも `route_kind` / `route-registry` の語が **0 件**(実測)で、**値域の正は検査器の定数だけ** | — |
| **`contracts/authz/route-registry.json`**(+ `.lock.json`) | `enums.route_kinds` へ 1 値追加。**`routes` は増やさない** | PR レビュー(`contracts/authz/*` = `tenant-isolation` のコア) |
| **`contracts/authz/auth-catalog.json`**(+ `.lock.json`) | `SCOPE:ALL_LOGICAL.route_kinds` へ追加する場合のみ(6 節の裁定次第) | 同上 |
| **`contracts/authz/oracle-seal.lock.json`** | `input_assets` の `git_blob_digest` と `oracle_commit` | **人間レビュー必須**(`reseal_policy.human_review_required: true`) |
| **oracle 資産 6 本の `oracle_context.oracle_commit`** | 新しいコミット SHA へ差し替え | 同上 |
| **`contracts/authz/frozen-baselines.json`** | `history` へ 1 レコード(`acceptance_id` / `approved_by` / `approved_at`) | **人間承認が schema レベルで強制** |
| **`docs/features/route-kind-vocabulary/plan.md`** | **`design_provenance` の `extracted_text` の典拠元になる**(4 節) | 本 PR |

## 4. 実装方針

**重さ分類 = コア領域**。`scripts/check_authz_catalog.py` と `tests/test_check_authz_catalog.py` は
**`guard_paths`**(`.claude/core-areas.json:21`・`:32`)かつ **`tenant-isolation` のコア paths**(同 `:308`・`:309`)。
`contracts/authz/*` も同 `:307`。→ **敵対レビュー + 人間の逐行確認が必須。**

### `ROUTE_KINDS` の参照点(実測 — 4 箇所すべてを更新する)

**着手時に「4 箇所」と書いたが、実測では 6 箇所**(research.md 3 節)。

| # | 行 | 用途 | 足し忘れたときの挙動 |
| --- | --- | --- | --- |
| 1 | `scripts/check_authz_catalog.py:92` | `ROUTE_KINDS` の定義(**唯一の正**) | — |
| 2 | 同 `:1973-1976` | `enums.route_kinds` と **frozenset 完全一致** | `CatalogError` |
| 3 | 同 `:2066` | 各 route の `route_kind` を閉じた値域へ落とす | `CatalogError` |
| 4 | 同 `:2068-2075` | **`expected_keys_by_kind` — dict 直参照** | **素の `KeyError`** |
| 5 | 同 `:2411-2416` | **`disposition_by_kind` — dict 直参照** | **素の `KeyError`** |
| 6 | 同 `:2254` | `route_scopes[].route_kinds ⊆ ROUTE_KINDS` の**部分集合判定** | **何もしなくても green**(意味の穴) |

**`route_scopes` は `auth-catalog.json` のトップレベルキー**である(着手時に `route-registry.json` と書いたのは誤り — 実測で訂正)。

あわせて **`disposition` の導出規則**(同 `:2411-2429` — `legacy_route → deny_404` / `shared_data → product_cell` /
`control_read → conditional` / `management_operation → conditional`)へ新種別の行が要る。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

### 提案する値と必須キー(**人間の裁定を要する** — 8 節)

| 事項 | 提案 | 代替 | 根拠 |
| --- | --- | --- | --- |
| **値の名前** | **`tenant_owned_data`** | `record_and_aggregate` / `business_data` | 「**自テナント所有**」は要件書 `:130` の用語定義の語。**424 の表分類のプロファイル名 `tenant_owned`(23 表)と語彙が揃う**。`shared_data` と対になる形 |
| **必須キー** | **`{route_id, route_kind, origin, source_claim_ids, provenance_ids}`**(共通 4 + `provenance_ids`) | 〈主体 × 資源 × 操作〉を列にする案 | **最小限に留める**。`table_id` / `operation` を持たせると TSK-424 の capability と二重になり、`path` / `http_method` / `expected_status` を持たせると **TSK-346 の射程を踏む**(`ADR-004:154`) |
| **`origin`** | **`design`** | `requirement` | 要件書に製品 CRUD 経路の条項が無い(research.md 2 節)。`design` にすれば**要件主張との結線が不要**で `claim_dispositions` 165 件にも触らない。**`provenance_ids` を必須キーに含めるのはこのため**(現状 `design` はどの種別でも成立しない「デッドな値域」— research.md 4-2) |
| **`disposition`** | **`conditional`**(既存値へ写す) | 新値 `tenant_cell` | **新値を作ると「その経路の既定 HTTP 応答」を決めることになり TSK-346 の射程に触れる**。`deny_404` は「共有グループ経由では開かない」の意味で不適、`product_cell` は認可行列にセルが無い |
| **`SCOPE:ALL_LOGICAL`** | **入れる** | 入れない | 機械は強制しない(部分集合判定)が、**同スコープは「論理経路の全体」の意味で使われており、入れないと名前が嘘になる**。`frozen_value: 29` は entry 件数なので**動かない**(実測) |

**裁定の残し方は前例 A に倣う** — `contracts/authz/boundary-proposal.json` の `pending_human_reviews[]` に
`frozen_value` / `alternative_value` / `affected_ids_if_changed` / `oracle_change_action` の形で残す(research.md 5 節)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**TSK-312 の前例に倣い「テスト先行」で進める**(research.md 5 節)。**総数が変わりうるため `/<N>` を書かない**。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **負例テストを先に置く** — `tests/test_check_authz_catalog.py` へ ① 新種別に必須キーを欠いた行 ② 未登録の `route_kind` 値 ③ `ROUTE_KINDS` だけ足して `expected_keys_by_kind` を足し忘れた場合 の 3 種を追加する。**型 C**(`:2369-2411` の `route_class` 版)を `route_kind` に読み替える | **3 種すべてが red**。red の出力を worklog へ実出力つきで残す。**期待失敗集合を先に完全列挙して固定**する |
| 2 | **検査器と資産を対で更新する** — `scripts/check_authz_catalog.py` の **6 箇所**(`:92` / `:1973-1976` / `:2066` / `:2068-2075` / `:2411-2416` / `:2254`)と、`contracts/authz/route-registry.json` + `tests/fixtures/authz_claims/route-registry.json` の `enums.route_kinds` | ステップ 1 の 3 種が **green**。**既存 37 経路の判定が変わらない**(`uv run pytest -c pyproject.toml tests/` 全件 green)。**`routes` は 37 件のまま**(経路を足していない) |
| 3 | **派生 lock を再封印する** — `--reseal-derived --skip-oracle`。fixture の lock は CLI が触らないので**手で作り直す** | `route-registry.lock.json` の `asset_digest` だけが変わり **`entry_count` は 230 のまま**(`enums` は entries に写らない)。`tests/test_check_authz_catalog.py` が green |
| 4 | **凍結基準を移動し oracle を再封印する** — draft PR の番号を確定 → 前段コミットの SHA を **7 箇所の `oracle_commit`** へ差し替え → `frozen-baselines.json` の `history` へ 1 レコード → `--reseal-oracle` | `uv run python scripts/check_authz_catalog.py` と `scripts/check_frozen_baselines.py` が green。**`history` に `acceptance_id` / `approved_by` / `approved_at` が揃っている**(schema 必須) |

## 5. DoD(受け入れ基準)

- [ ] 製品 CRUD 経路の `route_kind` の**値と必須キー体系**を決め、根拠を本計画書に書いた
- [ ] `ROUTE_KINDS` の **検査器内 6 箇所の参照点すべて**を更新した(`:92` / `:1973-1976` / `:2066` / `:2068-2075` / `:2411-2416` / `:2254`)
- [ ] **検査器の外の 2 箇所を発火させていない** — `backend/tests/db/authz/mutation_execution.py:897-909` の `class_by_route_kind`(新種別の route を `claim-mutant-map` の `runtime_target` に出さない)/ `scripts/check_authz_catalog.py:5026-5031` の `boundary-proposal.json` の責務 exact-set(第 4 の責務を足さない)
- [ ] **`ROUTE_KINDS` と `expected_keys_by_kind` / `disposition_by_kind` の不整合が `CatalogError` になる**(素の `KeyError` にしない)明示検査を足した
- [ ] **`contracts/authz/route-registry.json` と `tests/fixtures/authz_claims/route-registry.json` の両方**の `enums.route_kinds` を更新した
- [ ] **fixture の lock** を手で作り直した(CLI の `--reseal-derived` は触らない)
- [ ] **`routes` を 1 件も増やしていない**(経路の登録は各単位の PR)
- [ ] **裁定を `boundary-proposal.json` の `pending_human_reviews[]` に残した**(前例 A の形)
- [ ] `disposition` の導出規則に新種別の行を足した
- [ ] **既存 37 経路の判定が変わらない**ことをテストで確認した
- [ ] **負例**(新種別に必須キーを欠いた行)が red になることを確認した
- [ ] **派生 lock を再封印**し、`tests/test_check_authz_catalog.py` が green
- [ ] **凍結基準を移動した** — draft PR の番号確定 → 7 箇所の `oracle_commit` 差し替え → `frozen-baselines.json` の `history` へ 1 レコード(`acceptance_id` / `approved_by` / `approved_at`)→ `--reseal-oracle`
- [ ] **oracle 差分の敵対レビュー + 人間確認**を受けた(`review_policy: ORACLE_STEP5_REREVIEW` / `reseal_policy.human_review_required: true`)
- [ ] pytest / ruff / ty green
- [ ] 横断要求: 物理削除しない / テナント分離を全機能に適用 / 自動エスケープ

## 6. テスト計画

**DB を使わない**。ハーネス側の `tests/` のみ(`uv run pytest -c pyproject.toml tests/`)。

| 対象 | 種別 | ファイル | 確認すること |
| --- | --- | --- | --- |
| 新種別に必須キーを欠いた行 | 負例 | `tests/test_check_authz_catalog.py` | `"キー不一致: 不足=[...]"` で red(**型 B** — `:1686-1730`) |
| 未登録の `route_kind` 値 | 負例 | 同上 | `"route_kindが閉じた値域にない"` で red(**型 C** — `:2369-2411` を読み替え) |
| `ROUTE_KINDS` と `expected_keys_by_kind` の不整合 | 負例 | 同上 | **素の `KeyError` ではなく `CatalogError`** になること(**検査器側に明示検査を足す**) |
| 既存 37 経路 | 回帰 | 同上 | **判定が 1 件も変わらない** |
| `disposition_by_kind` の不整合 | 負例 | 同上 | 同じく `CatalogError` |

**ステップ 1 の注意**: 現在 `route_kind` を対象にした負例テストは**存在しない**(`route_kind` の語は `:1711` の 1 箇所のみ)。**新規に型を作る。**

**`-x` を使わず全件実行する**(期待失敗集合の完全列挙 — TSK-312 の前例 `docs/features/authz-claims-corpus/plan.md:70`)。

## 7. 依存・前提

**外部依存は無い。**`TSK-424` とも `TSK-344` とも `TSK-431` とも**独立に進められる**。

**マージ順序**: **本タスク → 入口を開く各単位**(U-M1 ほか)。どちらも `route-registry.json` を触り、
`route-registry.json` と `http-route-matrix.json` は exact-set(`scripts/check_authz_catalog.py:2437-2442`)のため。

**本タスクが開けるもの**: **帯 2 の葉 6 本 + 帯 3 の 6 本 = 12 単位**が入口を開けるようになる。
**ただし単独では開かない** — 12-4 の通過条件(RLS の実スキーマ適用 = TSK-344)と capability(TSK-424)も要る。

## 8. 人間の裁定が要る事項

| # | 事項 | 本書の提案 |
| --- | --- | --- |
| **1** | **新種別の名前** — 要件書から引けない(「業務」「CRUD」は 0 hits)。**既存 4 値も要件書に逐語が無く、正は検査器の定数だけ** | **`tenant_owned_data`**(4 節) |
| **2** | **必須キー体系** — 要件から引けない。最も強い根拠は `data-model.md:2468-2474` の〈主体 × 資源 × 操作〉だが、**到達性の比較軸であってレジストリのキーとして指定されたものではない** | **共通 4 + `provenance_ids` の最小形**(4 節) |
| **3** | **`SCOPE:ALL_LOGICAL` に入れるか** — 機械は強制しないが、入れないと「全体」の読みが黙って壊れる | **入れる**(4 節) |
| **4** | **凍結基準 `oracle_input` の `oracle_commit` を動かす承認** — **台帳上の初回**(既存履歴 1 件は値の移設であって値の変更ではない)。`approved_by` / `approved_at` が schema 必須 | ステップ 4 で人間の承認を得る |
