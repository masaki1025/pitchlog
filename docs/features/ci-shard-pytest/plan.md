---
feature: ci-shard-pytest
status: in-review
承認: 済（ユーザー指示 2026-10-31・CI短縮の5条件を反映）
重さ分類: 通常
branch: feature/ci-shard-pytest
created: 2026-10-31
計画レビュー周回: 0
確定ゲート周回: 0
---

# CI の pytest 分割と本文検査の分離

## 1. 背景

backend 59分31秒・harness 43分20秒で、クリティカルパスのほぼ全てが pytest である
(backend は単一プロセス 58分32秒、harness は 4 並列で 40分35秒)。検査範囲を変えずに
壁時計を短縮する。加えて、PR 本文の編集で同じ検査が再実行・キャンセルされていた。

## 2. スコープ

やること:

- pytest の分割実行(backend 4 / harness 4)と、収集したテスト ID による全件被覆検査
- 必須チェック名を維持する集約ジョブ(失敗・キャンセル・skip の拒否)
- PR 本文を読む検査の別ワークフロー化と concurrency の分離
- 凍結資産(tenant v2 受理record・比較 corpus digest・生成モジュール)の追随

やらないこと:

- テストの削除・skip・marker 選択による検査範囲の縮小
- カバレッジ測定範囲の縮小、`fetch-depth` の削減
- GitHub Ruleset(必須 context)の変更

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` | 10.1 のジョブ表と変更履歴へ分割配線を追随 | 7.6-3 前段(節更新) |
| `docs/development/github-setup.md` | 必須 context・ジョブ分類の現行化 | PR レビュー |
| `.github/workflows/ci.yml` | 分割ジョブ・集約・`edited` 除去 | 凍結資産(受理record) |
| `.github/workflows/pr-body.yml` | `core-guard` の移設 | PR レビュー |
| `tests/test_ci_wiring.py` | 配線契約の分割追随 | 凍結資産(受理record) |
| `contracts/tenant_boundary/*` | v2 受理record と snapshot | 7.7-2 |

## 4. 実装方針

- 重さ分類: **通常**。コア領域(状況計算・同期・記録権・テナント分離・移行)の意味は変えない。
- 分割は node id ではなく**収集順の剰余**で決定的に行う(乱数 UUID を含む parametrize があるため)。
- 必須チェック名は集約ジョブが維持し、`toJSON(needs)` で success 以外を拒否する。

## 5. 実装ステップ

| # | 内容 | 合格条件 |
| --- | --- | --- |
| 1 | 分割機構(プラグイン・被覆検査・定義)と CI 配線、本文検査の分離 | 被覆検査が全件一致・0件/欠落/重複を拒否し、`core-guard` が別ワークフローで動く |
| 2 | 配線契約の追随と凍結資産の再導出 | `tests/test_ci_wiring.py` 全件成功、tenant 検査 `ok`、corpus digest 一致 |

## 6. テスト計画

- `tests/test_ci_wiring.py`: ジョブ順・fetch-depth・条件式・集約ゲート・分割定義と CI コマンドの結線
- `tests/test_frozen_archive.py` / `tests/test_check_tenant_boundary_bypass.py`: 凍結資産の整合
- `scripts/pytest_shards.py verify`: 収集したテスト ID による全件被覆(harness / backend + `--require-db`)
- 実 CI: ジョブ所要時間の計測

## 7. 完了条件(DoD)

- [ ] 必須チェック名 `backend` / `harness` / `core-guard` が維持され、集約が success 以外を拒否する
- [ ] 分割の全件被覆が収集テスト ID で検証され、DB 0 件拒否とカバレッジ測定範囲が維持される
- [ ] 凍結資産(受理record・corpus digest・生成モジュール)が実 byte と一致する
- [ ] 実 CI で全ジョブ green となり、所要時間を記録する

## 8. 未了

- 実 CI のジョブ所要計測と目標値の確定(17〜20 分は実測前の目標値)。
- 最終HEADの非作者レビューと PO 委任証拠の掲載。
