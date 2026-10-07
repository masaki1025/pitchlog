---
date: 2026-10-08
topic: CI 短縮① — harness pytest の並列化(xdist)と巨大変異テストの分割、backend の計測
branch: feature/ci-harness-parallel
---

# 作業ログ: 2026-10-08 CI 短縮①(harness の並列化・巨大テスト分割・backend 計測)

## やったこと

### /task-start

- PO 指示(2026-10-07〜08): 「現在の CI の長さを短縮したい。ローカルでできるテストはローカルで。並列も実施したい。ローカルは 8 上限で」。CI 上での Claude レビュー案は不採用(Codex は CI を見ておらず、CI は機械検査のみという前提の確認後)
- 2 タスクに分割(PO 合意): **A = 本タスク**(xdist 並列化・巨大 2 テストの分割・census 系の `uv run` 起動削減・backend の `--durations`/`COVERAGE_CORE=sysmon` — 設計書 10.1 は節更新のみ)/ **B = 後続**(入力に基づくテスト選択 + develop/nightly 全件実行 — 10.1 の構造変更 → v1.20。PR #99 マージ後)
- Notion タスクを起票(担当 = 徳光・優先度 高・DoD 5 項目・`進行中`): https://app.notion.com/p/3f293b75e6878195a980c5cf8ca32e4a
- develop を現行化(27ff94eb → `1fdf1eec` = PR #98 マージ)。ブランチ `feature/ci-harness-parallel`・worktree `../pitchlog-worktrees/feature-ci-harness-parallel`(origin/develop = `1fdf1eec` 起点)

### 実測(/investigate の代替 — 軽い単発確認のため調査サブエージェントは起動せず、CI と手元の実測で代替)

- **CI の所要時間**(`gh run view --json jobs`・直近 3 run: 37635969114 / 37631745853 / 37570351073): 壁時計 24.6 / 27.8 / 27.2 分。**`harness` ジョブ 24.5 / 27.6 / 27.2 分で、うち `uv run pytest ... tests/` ステップが 23.7 / 26.6 / 26.4 分**。`backend` 15.9 / 15.8 / 15.7 分(`pytest --cov` 15.2 分・backend/contracts 変更時のみ)。他 10 ジョブは各 1.2 分以下。`concurrency` の cancel-in-progress・`setup-uv` のキャッシュは有効
- **ランナー**: `ubuntu-latest`(public リポの標準 = 4 vCPU / 16 GB)。pytest は 1 プロセス直列(xdist 未導入 — ルート `pyproject.toml` の dev 依存は pytest / pyyaml / ruff / ty)
- **手元計測**(develop `27ff94eb`・CI harness と同じ対象: `tests/` から `domain/boot`・`domain/mut`・`test_plan_generation.py`・`test_step_history_audit.py` を除外・`--durations=40`): **2,620 件・974 秒(16 分 14 秒)**。上位 40 件の合計 ≈ 800 秒(約 82%)。内訳:
  - `tests/test_check_authz_catalog.py` ≈ 400 秒 — `test_all_recursively_enumerated_oracle_leaves_reject_change_and_deletion` **111.5 秒**・`test_recursive_derivers_cover_generated_container_sequences_and_siblings` **98.8 秒**(1 テスト内で資産 × 葉 × 変異を全数ループ・プロセス内 CPU 律速)、`test_g_*` 3 件 40 秒台、他 10 件 3〜24 秒
  - `tests/test_census_baseline_check.py` ≈ 310 秒 — 45.3 / 44.7 / 36.6 / 21.6 秒ほか 10〜17 秒級が 10 件以上(センサス検査を**子プロセス**で変異ごとに再実行)
  - `tests/test_check_tenant_boundary_bypass.py`(実コミット差分を作って検査・6〜8 秒 × 4)・`tests/test_feature_status.py`(10 秒 × 2)・`tests/test_frozen_archive_case_runner.py`(14 秒)
- **xdist の障害見積**: `tmp_path`/`TemporaryDirectory` 1,932 箇所で隔離・`os.chdir`/`monkeypatch.chdir` 2 箇所・固定 `/tmp` 2 箇所・実リポに対する git は読み取り(diff/log)。`tests/test_ci_wiring.py:119-123` が harness の pytest コマンド文字列を固定しており、`-n auto` 追加時に同時更新が要る(「harness の pytest は 1 回」の assert は維持)
- **backend**: 738 件(DB 189 件・39 ファイル)。`pyproject` に `[tool.coverage]` なし(行カバレッジのみ)・Python 3.12・coverage 7.15.4 → `COVERAGE_CORE=sysmon` が使える。手元に Docker がなく(WSL の Docker Desktop 統合無効)内訳は未計測 → CI で `--durations=25` を取る
- **ワーカー数の決定(PO 2026-10-08)**: CI = `-n auto`(4)/ ローカル = **8 上限**(24 コア機だが子プロセスを多数起動するテストのため過負荷を避ける)

## 決定

- タスク分割(A/B)とワーカー数(上記)

## 未決・次の一歩

- /plan → `review normal`(設計書 6.3 の上限: 全文 1 + 差分 1 + P0 例外)→ 人間承認 → /implement(ステップ単位・Codex)
