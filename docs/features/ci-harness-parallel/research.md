---
feature: ci-harness-parallel
type: research
date: 2026-10-08
---

# 調査メモ: CI 所要時間の内訳と harness pytest の律速要因

調査基点: develop = `1fdf1eec`(2026-10-08)。調査サブエージェントは起動せず(軽い単発確認・設計書 8.5「作業の重さで増減」)、GitHub Actions の実測(`gh run view --json jobs`)と手元の pytest 計測で代替した。CI の実測は 2026-10-07 の直近 3 run、手元計測は develop `27ff94eb` 時点。

## 問い

1. CI の壁時計(25〜28 分)はどのジョブ・どのステップが決めているか
2. harness の pytest はなぜ長いか(件数か、少数の重いテストか)
3. 並列化(pytest-xdist)の障害になる共有状態はあるか
4. backend ジョブ(16 分)は何で決まり、手元で計測できるか
5. 変更の射程 — 正本・guard_paths・機構(テストが固定しているもの)

## 結論(要約)

- 壁時計はほぼ **`harness` ジョブの pytest ステップ**(23.7 / 26.6 / 26.4 分)で決まる。`backend` は 15.2 分の pytest(backend/contracts 変更時のみ)、他 10 ジョブは 1.2 分以下
- harness の 2,620 件・974 秒(手元)のうち **上位 40 件 ≈ 800 秒(約 82%)**。律速は少数の全数変異テスト: `tests/test_check_authz_catalog.py`(≈400 秒・最長 111.5 秒と 98.8 秒の 2 件はプロセス内 CPU 律速)と `tests/test_census_baseline_check.py`(≈310 秒・アンカーの実体化と現行センサスの全文走査をテストごとに再計算)
- pytest は 1 プロセス直列(xdist 未導入)で、4 vCPU のランナーの 1 コアしか使っていない。共有状態は少なく(`tmp_path` 1,932 箇所・chdir 2・固定 `/tmp` は文字列のみ)、並列化の障害は小さい
- backend は `pytest --cov`(閾値なし・行カバレッジのみ)。Python 3.12 + coverage 7.15.4 なので `COVERAGE_CORE=sysmon` が使える。手元に Docker がなく内訳は未計測 → CI で `--durations=25` を取る
- 射程: `ci.yml`(guard_paths)・`tests/test_ci_wiring.py`(harness の pytest コマンド文字列を固定)・ルート `pyproject.toml`/`uv.lock`(xdist 追加)・設計書 10.1 の harness/backend 行(節更新・版は上げない)・`/check` スキル

## 詳細と典拠

### §1 CI の実測(run 37635969114 / 37631745853 / 37570351073 — 2026-10-07)

| ジョブ | 所要(3 run) | 内訳 |
| --- | --- | --- |
| harness | 24.5 / 27.6 / 27.2 分 | `uv run pytest -c pyproject.toml tests/ --ignore=...` = 23.7 / 26.6 / 26.4 分、`tests/test_census_baseline_check.py` の直接実行 0.6〜0.7 分、ruff/ty/sync は合計 0.5 分未満(`.github/workflows/ci.yml:72-98`) |
| backend | 15.9 / 15.8 / 15.7 分 | `uv run pytest -c pyproject.toml --cov` = 15.2 分(`ci.yml:305-`。paths filter: backend/ contracts/ ci.yml) |
| frontend | 1.0〜1.2 分(変更時のみ) | — |
| mutation / consistency / tenant-boundary-bypass / nfr021 / core-guard / docs-lint / secrets / *-changes | 各 0.1〜0.9 分 | — |

- 壁時計 = 24.6 / 27.8 / 27.2 分 ≒ harness の所要。`concurrency: cancel-in-progress`(`ci.yml:13-15`)・`setup-uv` の `enable-cache`(各ジョブ)は有効
- ランナー = `ubuntu-latest`(public リポの標準ランナー = 4 vCPU / 16 GB)
- 必須チェック(Ruleset 23694095・strict): secrets / docs-lint / core-guard / harness / nfr021-append-only / frontend-changes / backend-changes / frontend / backend / tenant-boundary-bypass の 10 コンテキスト — 本タスクはコンテキストを変えない

### §2 harness pytest の律速要因(手元計測 — develop `27ff94eb`・24 コア機・`--durations=40`)

- 対象 = CI と同じ(`tests/` から `tests/domain/boot`・`tests/domain/mut`・`tests/test_plan_generation.py`・`tests/test_step_history_audit.py` を除外)。**2,620 件・974.26 秒**(5 failed は手元環境固有 — §6)
- 上位 40 件の合計 ≈ 800 秒。ファイル別:

| ファイル | 上位 40 件内の合計 | 代表 |
| --- | --- | --- |
| `tests/test_check_authz_catalog.py` | ≈ 400 秒 | `test_all_recursively_enumerated_oracle_leaves_reject_change_and_deletion` **111.5 秒**(`:5141` — 6 資産 + seal の全葉 × 改変/削除をプロセス内でループ)/ `test_recursive_derivers_cover_generated_container_sequences_and_siblings` **98.8 秒**(`:4983` — 深さ d の全容器列 × 幅 w をプロセス内で列挙)/ `test_g_*` 3 件 40〜42 秒 / 他 10 件 3.7〜23.7 秒 |
| `tests/test_census_baseline_check.py` | ≈ 310 秒 | 45.3 / 44.7 / 36.6 / 21.6 秒ほか 10〜17 秒級 10 件以上。`_declared_anchor_checker`(`:601` — 宣言アンカーを `git show` で実体化し検査器を隔離ロード)が 9 箇所、`_checker_census`(`:630` — `backend/src` 全文走査)が 15 箇所から呼ばれ、テストごとに再計算している |
| `tests/test_check_tenant_boundary_bypass.py` | ≈ 27 秒 | 実コミット差分を作って検査(6〜8 秒 × 4) |
| `tests/test_feature_status.py` / `tests/test_frozen_archive_case_runner.py` | 20 / 14 秒 | 一時リポで git 操作 |

- 2 つの巨大テストはいずれも**プロセス内の全数ループ**で、1 テストのまま xdist に載せても分割されない(最長単体テストが並列化の下限になる)。パラメトライズに展開すれば分散でき、失敗 ID も葉単位で読める

### §3 並列化(xdist)の障害見積

- 隔離: `tmp_path` / `TemporaryDirectory` 1,932 箇所。子プロセス呼び出し 119 箇所(`uv run`/`sys.executable` 67・git 69)は一時リポか読み取り専用(実リポに対する `git diff`/`log`/`show`)
- 共有状態の兆候: `monkeypatch.chdir` 2 箇所(`tests/test_codex_run.py:499`・`tests/test_packaging.py:242` — worker プロセス内で完結)/ 固定 `/tmp` は `tests/test_product_rls_real_schema_runner.py:540,708,779`(偽オブジェクトの Path 値のみ・書き込みなし)と `tests/test_ci_wiring.py:133`(文字列定数)
- `git checkout` 等の状態変更はすべて一時リポ(`tests/test_core_guard.py:1536`・`tests/frozen_negatives/*`・`tests/test_nfr021_append_only.py:1141-1161` など)
- `tests/test_ci_wiring.py:119-123` が `HARNESS_PYTEST_COMMAND` を文字列で固定(`:1123-1124`「harness の pytest は 1 回」)— `-n auto` 追加時に同時更新

### §4 backend ジョブ

- `uv run pytest -c pyproject.toml --cov`(`ci.yml` backend ジョブ)。`backend/pyproject.toml` に `[tool.coverage]` 節なし(行カバレッジ既定・閾値なし)、`requires-python = ">=3.12,<3.13"`、`uv.lock` の coverage = 7.15.4 → `COVERAGE_CORE=sysmon`(sys.monitoring 方式)が利用可能
- テスト 738 件(`def test_` 計測)、うち `backend/tests/db/` 189 件・`requires_db` 39 ファイル。手元に Docker がない(WSL の Docker Desktop 統合無効)ため内訳は未計測

### §5 射程(正本・guard_paths・機構)

- 設計書 10.1 の表(`docs/development/dev-harness-design-2026-08-07.md` 10.1)— harness 行「ruff / ty / pytest(`-c pyproject.toml` で設定固定)」・backend 行「`pytest -c pyproject.toml --cov`」。本タスクは **ジョブ構成・必須チェック・path filter を変えない**ので実装追随の節更新(7.6-3 前段・版は上げない)
- `ci.yml` は `.claude/core-areas.json` の guard_paths → PR で人間の逐行確認・実施記録行(6.3)
- `.claude/skills/check/SKILL.md`(正本体系外・guard_paths ではない)— ローカル `-n 8`
- 後続タスク B(入力に基づく選択 + develop/nightly 全件)は 10.1 の構造変更(path filter を付けない方針 `ci.yml:189-192,208-211` との整合を含む)で v1.20 の確定ゲート

### §6 手元環境固有の赤(本タスクの対象外)

- 手元計測で failed となった `tests/domain/gen/test_formatter.py`・`tests/domain/test_review_triggers_complete.py`(4 件)は develop `27ff94eb` の main tree でも同じく失敗し、同日の CI harness(run 37635969114)は success。手元環境(ツール・日付依存)の差で、本タスクの変更対象外

## 未解決・申し送り

- backend の内訳は CI の `--durations=25` 出力を待つ(次の打ち手: 非 DB テストの xdist / DB テストの worker 別スキーマ / PR での `--cov` 省略)
- xdist 導入後に順序依存の揺れが出た場合は、当該ファイルだけ `--dist loadfile` 相当にまとめる(ステップ 1 の合格条件で 2 回連続 green を要求する)
