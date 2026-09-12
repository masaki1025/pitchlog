---
feature: core-area-population-base
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 軽微            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)
notion: https://app.notion.com/p/3d993b75e687812d8335d1906e3ea7b3
branch: fix/core-area-population-base
created: 2026-09-12
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: fast             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: core-areas 全件登録検査の母集団がブランチに依存する欠陥の修正(fast path)

**fast path で実行する**(設計書 6.1)。**人間の事前 OK を 2026-09-12 に取得**(山田正輝)。
短縮計画は PR 本文に記載する。本書はメタデータとして保持する。

## fast path の適用判断

| 条件 | 判定 |
| --- | --- |
| **非コア** | **`tests/test_core_guard.py` は `core-areas.json` の `guard_paths`(検査経路)に含まれるが、`areas`(コア領域)ではない**。PR テンプレートも両者を区別する。**人間が「検査経路だが fast で可」と判断した** |
| **小差分** | **1 ファイル・約 60 行**(目安 50 行以下をわずかに超えるが、うち大半は docstring と負例 2 本) |
| **正本影響なし** | **`docs/` 配下に変更なし** |

## 背景

TSK-343(PR #55)のマージ後、**develop の `harness` ジョブが red** になった。

`tests/test_core_guard.py` の `schema_contract_asset_paths()` が `backend/tests/` の母集団を
`core_guard.changed_paths(REPO, "origin/develop", "HEAD")` で導出していたため、
**マージ後の develop では差分が空になり母集団が空洞化**する。

| | 母集団 | うち `backend/tests/` |
| --- | --- | --- |
| feature ブランチ上 | 66 件 | **20 件** |
| develop 上(マージ後) | 46 件 | **0 件** |

負例 `test_unregistered_task_test_is_rejected_from_version_control_population` が
`DID NOT RAISE` で落ちた。**負例は正しく仕事をしており、母集団が空になったことを検出した。**
落ちなければ検査が空洞化したまま誰も気づけなかった。

**この欠陥は PR #55 のレビュー時に見落とした** — 母集団の切り方を 3 候補から選ばせ、
「版管理の差分から導出」が選ばれたが、**フィーチャーブランチ上でしか検証しなかった**。
マージ後に基準が自分自身になることを確認していない。

## 直したもの

**母集団をブランチの状態に依存しない規則へ変えた。**

```
backend/tests/ 配下で pitchlog.db / schema-manifest / migrations を参照するファイル
  + それらが import する補助モジュール(推移閉包)
```

- **マージ前の 20 件をすべて含む**(取りこぼし 0)
- 余分は `backend/tests/db/conftest.py` と `environment_contract.py` の 2 件で、
  **DB テストの共通基盤なのでコア領域に属すべきもの**。既存の `backend/tests/db/*` glob が覆う
- **認可検証(TSK-317 の資産)を巻き込まない**ことを検査で固定した

**負例を 2 本へ整理した**:

| テスト | 検査すること |
| --- | --- |
| `test_schema_contract_test_population_does_not_depend_on_branch` | 母集団が空でない / 対象のテストを含む / authz を巻き込まない |
| `test_unregistered_schema_contract_test_is_rejected` | 1 本を登録から外すと red になる |

## 確認方法

- **`origin/develop` と同一の HEAD で母集団を数え、`backend/tests/` が 22 件**になること
  (旧規則では 0 件)。**前回はこの確認が抜けていた**
- ルートで `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/` が **全 green**

## 影響する正本

| 正本・資産 | 変更内容 | ゲート |
| --- | --- | --- |
| [ハーネス運用評価台帳](../../development/harness-evaluation.md) | **`## 候補` へ 1 件追記**(`/pr` のクローズ処理で判断 — **母集団を版管理の差分で導出すると、マージ後に基準が自分自身になって空洞化する**)。**`H-*` の新規採番はしない・版は上げない**(7.6-3 前段) | **PR レビューで可**(7.6-3 前段) |
| [ドキュメントマップ](../../README.md) | 台帳行の最終更新を現行化 | **PR レビューで可** |
| その他の正本 | **反映なし** | — |

**正本体系外だが同一 PR で運ぶもの**: `tests/test_core_guard.py`(検査経路 — `guard_paths`)。

## DoD

- develop の `harness` ジョブが green に戻る
- 母集団がブランチによって変わらない
- TSK-343 が新設したテストを 1 つ未登録にすると red になる
- 認可検証(TSK-317 の資産)を巻き込まない
