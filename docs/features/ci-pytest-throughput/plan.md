---
feature: ci-pytest-throughput
status: active
承認: 済（ユーザー指示 2026-11-07・CI短縮候補）
重さ分類: 通常
branch: feature/ci-pytest-throughput
created: 2026-11-07
計画レビュー周回: 0
確定ゲート周回: 0
---

# pytest 分割の 8 分割化と実行時間重み付き割当

## 1. 背景

固定 HEAD `12cc636dfaaea2ef6ecba2985492d3acb3f1dc30` の CI は、harness と backend を
それぞれ 4 シャードで実行している。実 CI のログでは収集順の剰余による割当が実行時間を
均しておらず、backend は 23〜35 分、harness は 8〜23 分の幅で、遅いシャードが
クリティカルパスになっている。検査内容と拒否条件を変えずに、シャード数と割当だけを
見直して待ち時間を短縮する。

## 2. スコープ

やること:

- backend を 4 から 8 シャードへ増やす。
- harness も 8 シャードへ増やす。backend の短縮後も harness がクリティカルパスに
  残らないことを、実 CI ログのシャード所要から確認する。
- 既存の実行時間ログ（CI run の pytest `--durations=25`）からテスト単位の重みを作り、
  重いテストから最も空いているシャードへ置く決定的な割当へ変える。
- 収集したテスト ID の和集合が全件と一致すること、新規テストが重みに無くても
  ちょうど 1 回だけ割り当てられることを `scripts/pytest_shards.py verify` で検査する。
- シャードごとの PostgreSQL service、必須チェック名、集約ジョブの失敗・キャンセル・
  未実行の拒否、カバレッジ計測と artifact を維持する。

やらないこと:

- テストの削除・skip・marker 選択・`--ignore` の追加による検査範囲の縮小。
- カバレッジ計測（`--cov`）や `fetch-depth` の削減。
- 必須チェック名・集約ジョブ名・GitHub Ruleset の変更。
- 有料 runner、main / develop への直接変更。
- 製品コード、共有台帳、正式な凍結資産、受理 record、seal の変更。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| `.github/workflows/ci.yml` | シャード数・表示・コメントの 8 分割化 | PR レビュー |
| `ci/pytest-shards.json` | 8 分割と実行時間重みの定義 | PR レビュー |
| `scripts/pytest_shard_plugin.py` | 重み付き決定的割当 | PR レビュー |
| `scripts/pytest_shards.py` | 重みの検証と全件被覆検査の強化 | PR レビュー |
| `tests/test_ci_wiring.py` | 配線契約の 8 分割追随 | 凍結資産（主担当が再導出） |
| `scripts/pytest_shard_plan.py` | 割当計算の単一実装（新規） | PR レビュー |
| `tests/test_pytest_shards.py` | 割当・新規テスト・拒否条件の単体検査（新規） | PR レビュー |

## 4. 実装方針

- 重さ分類: **通常**。コア領域（同期・状況計算・記録権・テナント分離・移行）の
  意味は変えない。
- 割当は `ci/pytest-shards.json` の重み（秒）を使う LPT（longest processing time）で
  決定的に行う。重みに無いテストは `default_weight_seconds` で必ず割り当てる。
- 乱数 UUID を含む node id は UUID を `<uuid>` に伏せて重みを引き、収集順を
  タイブレーカーに使う。同一プロセス内で全シャードが同じ全件集合から同じ割当を計算する。
- 被覆検査は分割前の全件収集と各シャードの収集結果を多重集合で比較し、欠落・重複・
  0 件シャード・重み定義の陳腐化を拒否する。
- シャードは従来どおり 1 ジョブ 1 PostgreSQL service とし、DB を共有しない。

## 5. 実装ステップ

| # | 内容 | 合格条件 |
| --- | --- | --- |
| 1 | 8 分割の CI 配線と、実行時間重み付きの決定的割当を実装する | CI の matrix と `ci/pytest-shards.json` が 8 で一致し、重み付き割当が全件を各 1 回だけ返す |
| 2 | 全件被覆・新規テスト取りこぼし・重み陳腐化・集約拒否・カバレッジ維持の検査を追加して実行する | `pytest_shards.py verify` が harness / backend で成功し、追加テストと配線テストが成功する |
| 3 | 変更前後の構成、短縮見込み、未検証点、主担当が必要な正式追随を記録する | `docs/features/ci-pytest-throughput/report.md` に実測値と推定値が区別して記録される |

## 6. テスト計画

- `tests/test_pytest_shards.py`: 重み付き割当の全件 1 回性、新規テストの既定重み、
  重いテストの分散、UUID 正規化、重みの不正値拒否。
- `tests/test_ci_wiring.py`: matrix 数・pytest コマンド・集約ゲート・カバレッジ
  artifact の 8 分割追随。
- `scripts/pytest_shards.py verify --suite harness` /
  `--suite backend --require-db`: 実収集 ID による全件被覆。
- `uv run ruff check .` / `uv run ty check` / 対象 pytest。

## 7. 完了条件（DoD）

- [ ] backend / harness の matrix と設定が 8 分割で一致する。
- [ ] 全テストが分割後もちょうど 1 回ずつ実行され、新規テストも取りこぼさない。
- [ ] 必須チェック名 `backend` / `harness` が維持され、集約が success 以外を拒否する。
- [ ] シャードごとに独立した PostgreSQL service があり、カバレッジ計測が維持される。
- [ ] 変更前後の構成・短縮見込み・未検証点が記録される。

## 8. 未了

- 8 分割の実 CI 所要時間は未実測（PR を作成しないため）。実測できるまでは推定と明記する。
- `tests/test_ci_wiring.py` の変更に伴う凍結資産（受理 record・hash・snapshot）の
  再導出は主担当が直列で行う。
