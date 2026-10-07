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
- **PO 裁定(2026-10-08・徳光 尋弥)= 包括続行指示「P0 限定・最大 N = 2 回」**(設計書 6.3 (3) の 1 対 1 原則の唯一の例外。範囲 = 直前周の P0 反映差分〔P0 限定〕。計上は周ごとに通常どおり。2 回で P0 が残れば再び裁定)**+ P0 ゼロ(判定 = 可決)になった時点で承認扱い**(`承認: 済(2026-10-08・徳光 尋弥)` を記入し、採否記録を worklog に残して /implement へ進む — 最終反映は Codex の再レビューを受けないため、可決周の反映差分がないことをもって承認者の差分確認に代える)

### /plan — 計画レビュー 4 回目(2026-10-08・`review normal`・**P0 限定**〔PO 包括続行指示 1/2 回目〕・対象 = 3 回目の P0 反映差分・**99,106 tok**・判定 = **可決 P0 0 / P1 0 / P2 0**)

- 指摘なし → 反映差分なし。`計画レビュー周回` は 3 のまま(収束確認周は数えない)
- **PO 裁定(2026-10-08)に基づき承認扱い**: `承認: 済(2026-10-08・徳光 尋弥)` を記入。計画レビュー合計 4 回(全文 1・差分 1・P0 限定 2)。残指摘 0・不採用 0。/implement へ

### /implement — ステップ 1(1 回目の委任・2026-10-08・Codex `implement`・114,194 tok・22 分)— **差し戻し(方式変更)**

- 依存追加(`pytest-xdist>=3` → 3.8.0・`execnet` 2.1.2)は Codex サンドボックスがネットワーク不可・`~/.cache/uv` 書込不可のため **Claude が `uv add --dev` で実施**(uv 生成の差分のみ。Codex が内容を確認)。Codex は `ci.yml` の harness pytest に `-n auto`・`tests/test_ci_wiring.py` の `HARNESS_PYTEST_COMMAND` 同期・`/check` を `-n 8` に変更
- **実測**: `-n 8` でハーネス全件 **400.96 秒 / 393.96 秒**(直列 974 秒 → 約 41%)。ただし失敗を含む参考値
- **失敗の内訳**(既知 5 件はいずれも非該当): ① `tests/test_check_tenant_boundary_bypass.py::test_repository_is_green` × 2 回 — 「射影が動いた資産は識別値の更新が必要: base-allowlist.json」(`ci.yml` が `external_files`)② `tests/test_frozen_archive*.py` 33 件 × 2 回 — corpus digest 不一致(`manifest.json` の `corpus_inputs.files` に `ci.yml`)③ `tests/domain/gen/test_backends.py::test_generation_writes_neither_product_paths_nor_contracts` 1 回目のみ — 別 worker の import が書く `__pycache__` を `_tree_snapshot` が拾う(並列の揺れ)④ `tests/test_packaging.py` 2 件 — サンドボックスのネットワーク不可(手元では green を確認)⑤ `tests/test_doc_check_profile.py::test_propagation_checker_and_claude_files_are_unchanged` — 未コミットの `.claude` 差分(コミット後に解消する既知の型)
- **発見**: `ci.yml` はテナント分離の凍結資産 7 件を束ねる `base-allowlist.json` の `frozen_projection.external_files`(`tenant-boundary-baseline/design.md:114` の設計)と比較 corpus の入力。変更 = 7.7-2 の受理記録(識別値繰り上げ・PR 番号・PO 受理)+ digest 再 pin = コア領域 paths の変更 → PR が敵対レビュー経路に。計画レビュー 4 回(全文 1・差分 1・P0 限定 2)はこれを拾えなかった(凍結点の一覧がリポジトリに無い — 運用評価台帳 2026-10-05 候補の再演)
- **PO 判断(2026-10-08・徳光 尋弥)**: **B = `ci.yml` に触れない方式へ計画修正**(`-n auto` はルート `pyproject.toml` の addopts・ローカルは `PYTEST_XDIST_AUTO_NUM_WORKERS=8`・ステップ 4 は `backend/pyproject.toml` の addopts と `[tool.coverage.run] core`)/ **pycache の揺れはスナップショットから `__pycache__` を除外**(計画外 1 ファイルをステップ 1 に含める)/ **修正は P0 限定の差分レビュー 1 回**(可決なら承認扱いで続行)。Codex の `ci.yml`・`test_ci_wiring.py`・`SKILL.md` 変更は取り消し(`git checkout`)、`pyproject.toml`・`uv.lock` の依存追加は保持
- 事前確認(Claude): root / backend の `pyproject.toml` の `addopts`・`[tool.coverage.run]` を固定する検査は無い(`tests/test_ci_wiring.py` は `markers` のみ参照 `:1915,3386`)/ xdist 3.8.0 は `PYTEST_XDIST_AUTO_NUM_WORKERS` に対応(実測)/ coverage 7.15.4 は `core` 設定に対応(`coverage debug config` → `core: sysmon`)/ backend の非 DB テストは 943 件(手元で実行可)

### /plan — 計画レビュー 5 回目(2026-10-08・`review normal`・**P0 限定**〔PO 裁定: 計画修正差分の追加レビュー 1 回〕・対象 = 計画修正差分 243dd3fa..31cbdb75・**129,574 tok**・判定 = **否決 P0 1 / P1 0 / P2 0**)— **採用(修正案とは別の形)**

| # | 重大度 | 起因 | 受理範囲 | 要旨 | 採否と反映 |
| --- | --- | --- | --- | --- | --- |
| 1 | P0 | 起因 | 正本違反 | ステップ 4 の移し先 `backend/pyproject.toml` は `.claude/core-areas.json` のコア領域 paths(5 領域すべて)。`重さ分類: 通常` のままでは 6.3 の敵対レビュー・逐行確認を欠く | 採用 — レビューの修正案(コア領域へ再分類)ではなく、`--durations=25` を本タスクから外し(非コア・非 `ci.yml` の置き場が無い: `addopts`/conftest はコア、`PYTEST_ADDOPTS` は `ci.yml`)、coverage の `core = sysmon` だけを **`backend/.coveragerc`(新規・非コア — 5 領域の backend 配下 glob に該当せず、backend 直下を列挙するテストも無い。`coverage debug config` で `config_files_read` と `core: sysmon` を実測)** に置く。重さ分類は通常のまま。4 節「コア領域 paths への注意」新設 |

- **PO 判断(2026-10-08・徳光 尋弥)**: ステップ 4 は `.coveragerc` の sysmon だけに縮小(内訳計測は後続タスク B へ)/ この修正は **PO 直接承認**(追加レビューなし — 変更は新規 2 行のファイルで、コア paths・凍結入力・backend 直下の列挙テストの不在を Claude が確認済み)。`承認: 済` は維持。計画レビュー合計 5 回(全文 1・差分 1・P0 限定 3)・Codex 約 654K tok

### /implement — ステップ 1(2 回目の委任・修正版・2026-10-08・Codex `implement --resume`・164,334 tok・15 分)— **合格・コミット `7bb4610f`**

- 変更 3 ファイル(+ 依存 2 ファイル): ルート `pyproject.toml` の `[tool.pytest.ini_options]` に `addopts = "-n auto"`(dev 依存 `pytest-xdist>=3` と `uv.lock` は Claude の `uv add`)/ `.claude/skills/check/SKILL.md` の harness pytest を `PYTEST_XDIST_AUTO_NUM_WORKERS=8 uv run pytest tests/` に / `tests/domain/gen/test_backends.py::_tree_snapshot` から `__pycache__` 配下と `*.pyc` を除外。**`ci.yml`・`tests/test_ci_wiring.py`・`contracts/`・`tests/fixtures/frozen-archive-cases/` は不変**(`git status` で確認)
- **実測(8 ワーカー・2 回連続・全件 2,677 件)**: **358.60 秒 / 380.75 秒**(直列 974 秒 → 約 37〜39%)。失敗は両回とも `tests/test_doc_check_profile.py::test_propagation_checker_and_claude_files_are_unchanged` 1 件のみ(未コミットの `.claude` 差分由来 — コミット後に green を確認)。手元の既知失敗 5 件はサンドボックスでは出なかった(環境依存)
- `uv run pytest tests/test_ci_wiring.py` 86 件 green(変更なし)/ ruff・ty green
- サンドボックス固有: `~/.cache/uv` が読み取り専用のため Codex は `UV_CACHE_DIR=/tmp/... UV_NO_SYNC=1` を付けて実行(手元では不要)
- 残り時間の律速は `tests/test_check_authz_catalog.py` の 2 テスト(111 / 99 秒)→ ステップ 2 で分割

### /implement — ステップ 2(2026-10-08・Codex `implement --resume`・236,512 tok・16 分)— **合格・コミット `51deefca`**

- 変更 1 ファイル(`tests/test_check_authz_catalog.py` +132/-56): 容器列テストを **3,586 ケース**(深さ 1〜8 の Σ 2^depth × depth)、葉の変異テストを **21,826 ケース**(6 資産 + seal の全 10,913 葉 × 改変・削除)の収集時 `parametrize` へ展開(旧ループの試行数と一致)。全数性の独立テスト 2 件を新設(`test_recursive_deriver_cases_cover_every_container_sequence_and_width`・`test_oracle_leaf_mutation_cases_cover_every_source_leaf` — 旧走査で独立導出した期待キー集合との完全一致・一意性・各資産の葉数 > 0)。検査器本体は不変
- **実測**: 同ファイル 25,571 件 — 8 ワーカー **206.09 秒** / `-n 1` **358.88 秒**(分割前の直列 ≈ 400 秒)。**分割由来ケースの最長 call = 容器列 0.13 秒・葉 0.12 秒**(< 30 秒)。残る上位は対象外の `test_g_*` 38.86 / 38.64 / 37.48 秒。収集 0.75 秒(Claude 実測)。失敗ゼロ・ruff・ty green・`git status` は対象ファイルのみ
- 直列の総時間がほぼ変わらない(400 → 359 秒)のは想定どおり — 分割の目的は xdist で分散できる粒度にすること(最長単体テスト 111 秒 → 0.13 秒)

### /implement — ステップ 3(2026-10-08・Codex `implement --resume`・360,440 tok・20 分)— **合格(下限達成・目標未達)・コミット `58b9e7ba`**

- 変更 1 ファイル(`tests/test_census_baseline_check.py`): ① 現行センサス走査 `_checker_census` を、検査器 digest × 契約入力(`repository_root` + `load_contract` が読む資産の digest)× `source_root`(パス + ツリー digest)をキーに、`load_contract`・`scan_directory` が import 時の関数のままの場合だけプロセス内でメモ化 ② アンカー実体化の blob 取得を実体化ごとに **`git cat-file --batch` 1 回**へ(子プロセス 129 → 1 回 / 計画書の 9 回換算で 1,161 → 9 回)。監査の宣言読取り・テストごとの `reference_root`・パス照合・来歴検査は不変。テスト間キャッシュなし
- **実測(`-n 1 --durations=0`・同一機械・直前)**: 総経過時間 **279.44 秒 → 190.12 秒(68.0%)** — **下限 75% は達成、目標 50% は未達**。上位 call: 宣言・実装の相互回帰テスト 40.22 → 24.02 秒・40.10 → 24.12 秒 / 非許可 API の変異テスト 28.70 → 28.18 秒(契約差し替えのため再計算 — 設計どおり)。上位 setup 10.28 → 2.21 秒。8 ワーカー: **48 件 53.72 秒**
- CI の直接実行経路 `uv run python tests/test_census_baseline_check.py` → `census-baseline: OK`(Claude も再確認)/ 監査・来歴・契約差し替えの回帰テストは変更なしで green / ruff・ty green / `git status` は対象ファイルのみ
- 目標未達の理由(実測から): 残りの大半は変異テストが契約を差し替えるため設計上共有できない再計算(28 秒級)と、監査内で毎回走るアンカーの実体化・隔離ロード(書き出しは不変条件のため削減対象外)。計画書どおり「下限達成なら手法を変えずに進む」

### /implement — ステップ 4(2026-10-08・Codex `implement --resume`・398,595 tok・3 分)— **合格・コミット `ff515e1a`**

- 変更 1 ファイル(新規 `backend/.coveragerc` — `[run] core = sysmon` の 2 行)。`backend/` で `uv run coverage debug config` → `config_files_read: backend/.coveragerc`・`core: sysmon`(Claude も再確認)。`ci.yml`・`backend/pyproject.toml`・期待値資産・`tests/test_ci_wiring.py` は不変
- 非 DB 実行 `uv run pytest -c pyproject.toml -m "not requires_db" --cov`: カバレッジ表 TOTAL 60%・**939 passed, 4 skipped**。終了コードは 1 — `backend/tests/db/conftest.py` の「DB テスト 0 件実行は fail」ガード(10.1 の fail-closed)によるもので、`-m "not requires_db"` とは両立しない。合格条件の文言を「failed 0」に改めた(計画修正 3)

### /implement — ステップ 1 付記(2026-10-08・Codex `implement --resume`・429,436 tok・2 分)— **コミット `c327e336`** — addopts の副作用の実測と対処

- **実測(ステップ 4 の検証で発覚)**: `backend/tests/test_authz_product_roles.py::test_product_role_assets_match_design_and_all_readers_accept_them` が `scripts/check_authz_catalog.py` を backend の venv の Python で起動し、同検査器の `collect_pytest_node_ids`(`:2960`)が `python -m pytest --collect-only -q tests/` を**ルート**で走らせる → ルート `pyproject.toml` の `addopts = "-n auto"` が xdist の無い backend 環境で `unrecognized arguments: -n` → **CI の backend ジョブが赤になる経路**。計画修正 2 の P0 限定レビュー(5 回目)はこの経路を拾っていない(依頼文で「`-n auto` 既定が他経路と衝突しないか」を問うていたが、別 venv からのルート起動は反例に挙がらなかった)
- **採れない対処**: backend に xdist(`backend/pyproject.toml` = コア領域 paths)/ 検査器の変更(guard_paths・digest 固定)/ `ci.yml` の env(凍結の外部入力)
- **採った対処**: ルートに `conftest.py` を新設し、`importlib.util.find_spec("xdist") is None` のときだけダミーの `-n`/`--numprocesses` を `pytest_addoption` で登録(xdist がある環境では何も登録しない)。`conftest.py` は guard_paths(逐行確認)だがコア領域 paths ではない。**PO への報告事項**(計画外の新規ファイル 1 件・計画修正 3 として plan.md に記録)

## 決定

- タスク分割(A/B)とワーカー数(上記)
- 計画レビューの PO 裁定(2026-10-08): 上限到達後は包括続行指示(P0 限定・最大 2 回)。P0 ゼロで承認扱い(`承認: 済` を記入して /implement へ)
- 2026-10-08(ステップ 1 の実測後): `ci.yml`・`tests/test_ci_wiring.py`・`contracts/**`・`tests/fixtures/frozen-archive-cases/**` に触れない(凍結の外部入力)。xdist はルート pyproject の addopts、ローカル上限は環境変数。pycache はスナップショットから除外。計画修正は P0 限定レビュー 1 回(可決で承認扱い)
- 2026-10-08(5 回目レビュー後): ステップ 4 = `backend/.coveragerc` の `core = sysmon` のみ(`--durations` の内訳は後続タスク B)。`backend/pyproject.toml`・`backend/*conftest.py` はコア領域 paths で触れない。この修正は PO 直接承認

## 未決・次の一歩

- /implement(ステップ 1〜4 = Codex・ステップ単位、5 = Claude)→ /check → /sync-docs → /pr(ci.yml は guard_paths → 人間の逐行確認)→ PR 後の DoD 検証(harness ≤ 8 分・backend durations)
