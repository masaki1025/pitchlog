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

### /plan — 計画レビュー 1 回目(2026-10-08・`review normal` = gpt-6-sol max・全文・**165,993 tok**・判定 = **否決 P0 3 / P1 5 / P2 0**)— **全件採用・不採用 0**(全件非起因・受理範囲 = 緑にできない)

| # | 重大度 | 要旨 | 採否と反映 |
| --- | --- | --- | --- |
| 1 | P0 | backend の pytest に `--durations=25` を足すと、期待値資産 `backend/tests/db/environment-expectations.json`(完全一致コマンド・**コア領域 paths**)と `tests/test_ci_wiring.py` の固定に衝突。資産を変えるとコア領域のレビュー経路になる | 採用 — コマンドは変えず、計測は **`PYTEST_ADDOPTS` 環境変数**(`--durations=25`)で行う方式へ。backend と mutation の両ジョブに同じ env を置き、資産は触らない |
| 2 | P0 | ステップ 4・5 の合格条件に「PR の CI 実測」を置いているが、正本の順序はステップ検証 → コミット → 文書反映 → PR → CI | 採用 — ステップの合格条件は PR 前に検証できる内容(YAML 検証・配線テスト・手元計測)に限定し、CI 実測は PR 作成後の DoD 検証へ移す |
| 3 | P0 | 分割後の全数性を「件数一致 + 葉数 > 0」で固定しても、1 件の重複と 1 件の欠落を見分けられない。容器列側の旧テストには `attempts` がない | 採用 — 旧ループと同じ走査で**独立に導出した期待キー集合**との完全一致と一意性を検査し、容器列側は幅・深さから期待件数を定義する |
| 4 | P1 | backend だけに `COVERAGE_CORE` を足すと mutation ジョブとの env 一致(`test_ci_wiring.py:1593`)が崩れ、固定された葉数 130(`:140,3352`)も変わる。「該当固定があれば同期」は一意でない | 採用 — env は backend・mutation の両方へ同値で追加し、葉数の固定値更新と env 検査の更新をステップに明記 |
| 5 | P1 | 「2 回連続 green」と「手元固有の赤を除く」が両立していない(手元の既知失敗 5 件) | 採用 — 既知失敗の固定集合(node ID)を明示し、手元条件 = 2 回とも新規失敗ゼロ、CI 条件 = 全件 green |
| 6 | P1 | 「最長単体テスト < 30 秒」をファイル全体に読むと `test_g_*` 3 件(40〜42 秒)で達成不能 | 採用 — 閾値の対象を分割した 2 テスト由来のパラメータケースに限定 |
| 7 | P1 | census の「半分以下」が直列の事前値と `-n 8` の事後値の比較になっており、並列化だけで達成し得る。`--durations=10` は合計を示さない | 採用 — 共有前後を同じ `-n 1` で測り、`--durations=0` の call 時間の合計で比較 |
| 8 | P1 | 共有してよい「同一入力」に `reference_root` が無い。アンカーは指定先へ書き出され検査器のパス照合もある。監査は実行ごとに宣言読取りを記録 | 採用 — 共有対象の呼び出しを特定し、`reference_root` ごと・監査中・変異中は再計算する条件を明記 |

- plan frontmatter `計画レビュー周回` = 1。次 = 2 回目(反映差分 + 影響節)

### /plan — 計画レビュー 2 回目(2026-10-08・`review normal`・反映差分 + 影響節・**153,266 tok**・判定 = **否決 P0 3 / P1 1 / P2 0**)— **全件採用・不採用 0**(P0 1 件非起因・他 3 件は 1 回目の反映に起因)

| # | 重大度 | 起因 | 受理範囲 | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P0 | 非起因 | DoD不対応 | 容器列側は件数しか検証せず、`(sequence, widened_index)` の 1 組の重複と 1 組の欠落を見分けられない | 採用 — 容器列も独立導出した期待キー集合との完全一致・一意性を検証(件数一致は併記) |
| 2 | P0 | 起因 | 緑にできない | 「監査中・変異中・別 `reference_root` は再計算」とすると、通常の census 検査は毎回監査内で別の一時 root へ実体化されるため共有できるものがなく、半減に達する経路が示されていない | 採用 — 共有経路を ① 現行センサス走査のメモ化(`reference_root` 非依存)② アンカー実体化の `git show` blob 内容の module スコープ保持(書き出し・パス照合・監査は不変)の 2 つに限定し、削減量はプロファイルで定める(目標 50%・下限 25% 短縮。下限未達は止めて PO へ報告) |
| 3 | P0 | 起因 | DoD不対応 | 半減判定を `call` 時間だけにすると module fixture へ移した費用が `setup` に移り、総時間が減らなくても通る | 採用 — 判定を `-n 1` の総経過時間(pytest の `in N s`)に変更、内訳は `--durations=0` の setup/call を併記 |
| 4 | P1 | 起因 | DoD不対応 | harness 8 分未達時の扱いが「後続へ送る」で、8 分以内を必須とする DoD と一致しない | 採用 — 未達は DoD 不合格として差し戻し(plan を `active` へ戻して是正・再計測)、満たすまで「確認待ち」にしないと明記 |

- plan frontmatter `計画レビュー周回` = 2。**2 回目に P0 が残り採用したため、設計書 6.3 の P0 例外を適用 → 3 回目 = P0 限定の差分レビュー**(P1/P2 は報告させない)

### /plan — 計画レビュー 3 回目(2026-10-08・`review normal`・**P0 限定**〔6.3 (2) の P0 例外〕・対象 = 2 回目の P0 反映差分・**106,126 tok**・判定 = **否決 P0 2 / P1 0 / P2 0**)— **全件採用・不採用 0**(2 件とも 2 回目の反映に起因)

| # | 重大度 | 起因 | 受理範囲 | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P0 | 起因 | 緑にできない | 共有経路①のメモ化キーに契約入力(`repository_root`)が無い。`_checker_census` は `load_contract(repository_root)` を読み(`tests/test_census_baseline_check.py:630`)、同じ検査器・ソースに別の契約ツリーを渡して結果の変化を要求するテストがある(`:2665,2709`。`load_contract` の差し替え `:2346`・関数のラップ `:2764` も)ため、計画どおりのキーでは誤ったキャッシュが返る | 採用 — キーを検査器 digest × 契約入力(`repository_root` + `load_contract` が読む資産の内容 digest)× `source_root`(パス + ツリー digest)とし、`load_contract`/`scan_directory` が import 時の関数と同一の場合に限って共有(それ以外は再計算)と明記 |
| 2 | P0 | 起因 | 正本違反 | 共有経路②(blob の module スコープ保持)は、来歴検査(`:340` — 観測世代 = その回の `monitor`・書込み = 観測した応答そのもの)と「監視開始前キャッシュ」を拒否する回帰テスト(`:3354`)に反する。キャッシュを現世代の応答に包み直せばゲートの証明が壊れる(旧 P0-2 未解消) | 採用 — ②を「各実体化の `monitor` 生成後に、その回の取得として 1 回の `git cat-file --batch`(同等の 1 プロセス取得可)でまとめて取得し、従来どおり観測してから書き込む(テスト間キャッシュなし)」へ置換。子プロセス起動 129 × 9 → 1 × 9 回。来歴検査・回帰テストを合格条件へ追加 |

- plan frontmatter `計画レビュー周回` = 3。**基本枠 2 回 + P0 例外 1 回を使い切り、P0 が残った(2 件とも採用・反映済み)→ 設計書 6.3 (3)/(4): 追加レビューは PO 裁定 1 回につき 1 回(または「P0 限定・最大 N 回」の包括続行指示)、または上限到達の終端として採否記録 + 人間承認へ(承認者が最終反映の差分を確認)。PO 裁定を仰ぐ**

## 決定

- タスク分割(A/B)とワーカー数(上記)

## 未決・次の一歩

- /plan → `review normal`(設計書 6.3 の上限: 全文 1 + 差分 1 + P0 例外)→ 人間承認 → /implement(ステップ単位・Codex)
