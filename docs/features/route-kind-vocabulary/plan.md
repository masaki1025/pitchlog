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

### やること

### やらないこと

| 項目 | 行き先 |
| --- | --- |
| **実際の経路の登録**(選手・チームの `route_id` 付与) | **各単位が自 PR で行う**(U-M1 ほか) |
| **既存 37 経路の `test_owner` 再割り当て** | **TSK-380** |
| **API 契約の正本化** | **TSK-346** |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |

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

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
|   |   |   |

## 5. DoD(受け入れ基準)

- [ ] 製品 CRUD 経路の `route_kind` の**値と必須キー体系**を決め、根拠を本計画書に書いた
- [ ] `ROUTE_KINDS` の **4 箇所の参照点すべて**を更新した
- [ ] `disposition` の導出規則に新種別の行を足した
- [ ] **既存 37 経路の判定が変わらない**ことをテストで確認した
- [ ] **負例**(新種別に必須キーを欠いた行)が red になることを確認した
- [ ] lock を再封印し、`tests/test_check_authz_catalog.py` が green
- [ ] pytest / ruff / ty green
- [ ] 横断要求: 物理削除しない / テナント分離を全機能に適用 / 自動エスケープ

## 6. テスト計画

## 7. 依存・前提

**外部依存は無い。**`TSK-424` とも `TSK-344` とも**独立に進められる**
— 424 が触るのは `contracts/authz/product/`(新規サブディレクトリ)と capability であり、`route-registry.json` には触らない
(**典拠**: `feature/product-authz-surface` ブランチの `docs/features/product-authz-surface/plan.md` 2 節「やること(PR A1)」と「やらないこと」。
**リポジトリの develop 側には典拠が無い**ので、本書は当該ブランチを典拠として明記する)。

### ⚠ 最大の壁 — 凍結基準(research.md 4 節)

`contracts/authz/oracle-seal.lock.json` の `input_assets` **8 資産**に **`route-registry.json` と `route-registry.lock.json` が含まれる**(実測)。
`validate_oracle_seal` は **作業ツリーの blob digest** と **`git rev-parse <oracle_commit>:<path>` の blob** を二重照合し、
`--reseal-oracle` は再計算後にそのまま同検査を呼ぶ(`scripts/check_authz_catalog.py:5842-5844`)。

> **したがって `route-registry.json` を 1 バイトでも変えたら、`oracle_commit` を「新しい内容を含むコミット」へ進めない限り `--reseal-oracle` 自体が失敗する。**

`oracle_commit` は `contracts/authz/frozen-baselines.json` の **`oracle_input` 系列**が凍結しており、
`scripts/check_frozen_baselines.py:795-816` が現在値と `history` 末尾の一致を検査するため、
**`history` へ承認付きの 1 レコード追記が必須**になる。**既存の履歴は 1 件のみ**(`masaki1025/pitchlog#73`・山田正輝・2026-09-21)で、
それは**値の移設であって値の変更ではない**。→ **「`oracle_commit` の値そのものを動かす」のは本タスクが台帳上の初回。**

**マージ順序**: 本タスク → 入口を開く各単位(U-M1 ほか)。どちらも `route-registry.json` を触るため。
