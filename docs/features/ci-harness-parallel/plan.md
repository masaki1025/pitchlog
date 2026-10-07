---
feature: ci-harness-parallel
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-08・徳光 尋弥) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3f293b75e6878195a980c5cf8ca32e4a
branch: feature/ci-harness-parallel
created: 2026-10-08
計画レビュー周回: 3        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: CI 短縮① — harness pytest の並列化(xdist)と巨大変異テストの分割、backend の計測

## 1. 背景・目的

- Notion: [TSK-501](https://app.notion.com/p/3f293b75e6878195a980c5cf8ca32e4a)。PO 指示(2026-10-07〜08): 「CI の長さを短縮したい。ローカルでできるテストはローカルで。並列も実施したい。ローカルは 8 上限で」
- 実測([research.md](research.md) §1〜§2): CI の壁時計 25〜28 分のうち **harness ジョブの pytest が 24〜27 分**。手元計測では 2,620 件・974 秒のうち上位 40 件が約 82% を占め、`tests/test_check_authz_catalog.py` の全数変異テスト 2 件(111.5 秒・98.8 秒 — プロセス内ループ)と `tests/test_census_baseline_check.py`(約 310 秒 — アンカーの実体化と現行センサスの全文走査をテストごとに再計算)が大半。pytest は 1 プロセス直列で 4 vCPU の 1 コアしか使っていない
- 関連要件: NFR-019 柱書(PR ごとに CI を実行し全グリーン必須)は維持する。レビュー・テストの網羅性を落とさずに所要時間だけを下げる。直接該当する FR はない
- 関連正本・決定: 設計書 10.1(CI ジョブ表 — harness/backend 行は実装追随の節更新)/ 10.2(必須チェック 10 コンテキスト — 不変)/ 台帳候補「検査が無関係な PR を巻き込んで赤にする」(所要時間とは別問題 — 後続タスク B の入力選択で扱う)
- 後続タスク B(PR #99 マージ後): 入力に基づくテスト選択 + develop/nightly 全件実行(10.1 の構造変更 → v1.20)。本タスクはその前段で、構造を変えずに時間を削る

## 2. スコープ

### やること

1. **pytest-xdist の導入**: ルート `pyproject.toml` の dev 依存に `pytest-xdist` を追加(`uv.lock` 更新)し、同ファイルの `[tool.pytest.ini_options]` に **`addopts = "-n auto"`** を置く(CI の harness ジョブは `-c pyproject.toml` で設定を読むため、**`ci.yml` を変えずに**ランナー 4 vCPU → 4 ワーカーで走る。`tests/test_ci_wiring.py` の `HARNESS_PYTEST_COMMAND` も不変)。`.claude/skills/check/SKILL.md` の harness pytest を **`PYTEST_XDIST_AUTO_NUM_WORKERS=8 uv run pytest tests/`**(ローカル上限 8 — PO 決定 2026-10-08。xdist の `auto` を環境変数で上書き)に。並列の揺れ 1 件(`tests/domain/gen/test_backends.py::_tree_snapshot` が、別 worker の import が書く `backend/src/pitchlog/__pycache__` を拾う — 2026-10-08 実測)は、スナップショットから `__pycache__` を除外して対処する(PO 判断 2026-10-08)
2. **巨大 2 テストのパラメトライズ分割**(`tests/test_check_authz_catalog.py:4983` `test_recursive_derivers_cover_generated_container_sequences_and_siblings`・`:5141` `test_all_recursively_enumerated_oracle_leaves_reject_change_and_deletion`): 容器列 / (資産, 葉, 変異) を収集時に列挙して `parametrize` に展開し、xdist で分散できる粒度にする。**全数性は維持**する(展開件数が旧ループの試行数と一致することを別テストで固定し、各資産の葉数 > 0 の検査も残す)
3. **census 系の重複準備の共有**(`tests/test_census_baseline_check.py`): 宣言アンカーの実体化(`_declared_anchor_checker`・9 箇所)と現行センサス(`_checker_census`・15 箇所)のうち**入力が同一のもの**を module スコープの fixture またはメモ化で共有する。変異ごとの計算と、宣言と実装の対応監査(`_audit_declaration_implementation` の母集団)は変えない
4. **backend の coverage を sysmon へ**: backend の pytest **コマンドは変えない**(期待値資産 `backend/tests/db/environment-expectations.json:164` が `uv run pytest -c pyproject.toml --cov` を完全一致で固定し、同資産はコア領域 paths)。**`ci.yml` も `backend/pyproject.toml`(コア領域 paths — `.claude/core-areas.json` の 5 領域すべて)も変えない**。代わりに **`backend/.coveragerc`(新規・非コア)** に `[run] core = sysmon`(Python 3.12 + coverage 7.15.4。CI の backend ジョブは `working-directory: backend` なので読み込まれる — `coverage debug config` で `config_files_read: backend/.coveragerc`・`core: sysmon` を実測済み)を置く。**`--durations=25` の内訳計測は本タスクから外す**(非コア・非 `ci.yml` の置き場が無い — PO 判断 2026-10-08。後続タスク B で取る)。backend の効果は PR 作成後の CI run のジョブ所要時間(導入前 15.7〜15.9 分)との前後比較で worklog に記録
5. **文書の追随**(Claude): 設計書 10.1 の harness 行(pytest は `-n auto` 並列 — ルート `pyproject.toml` の addopts・ローカルは `/check` が環境変数で 8 上限)と backend 行(coverage `core = sysmon` — `backend/.coveragerc`)を節更新し変更履歴に 1 行(版は上げない — 7.6-3 前段)、`docs/README.md` を現行化

### やらないこと

- **ジョブ構成・必須チェック・path filter の変更**(10.1 の構造 — 後続タスク B。10.1 が fail-closed の理由で filter を付けない nfr021 / tenant-boundary には触れない)
- **`.github/workflows/ci.yml`・`tests/test_ci_wiring.py`・`contracts/**`・`tests/fixtures/frozen-archive-cases/**` の変更**(`ci.yml` は凍結の外部入力 — 4 節「凍結点への注意」。2026-10-08 計画修正)
- **backend テストの並列化・`--cov` の省略・DB テストの worker 分離・`--durations` の内訳計測**(内訳の置き場〔`backend/pyproject.toml`・conftest〕がコア領域 paths、環境変数は `ci.yml` のため — 後続タスク B で取ってから判断)
- **テストの網羅性の削減**(葉・変異・述語の母集団は不変)、**検査器(`scripts/*.py`)本体の変更**(テスト側の呼び方だけを変える)
- 手元環境固有の赤(research.md §6)の是正
- GitHub の larger runner(有料)の採用

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` | 10.1 ジョブ表の harness 行に「pytest は `-n auto` で並列(ルート `pyproject.toml` の addopts。ランナー 4 vCPU → 4 ワーカー)。ローカルは `/check` が `PYTEST_XDIST_AUTO_NUM_WORKERS=8` で上限 8」、backend 行に「coverage は `backend/.coveragerc` の `[run] core = sysmon`」を追記。変更履歴 1 行(**版は上げない** — 実装追随の節更新・7.6-3 前段) | PR レビュー |
| `docs/README.md` | 設計書行の最終更新日を現行化 | PR レビュー |
| `docs/development/harness-evaluation.md` | `/pr` クローズ処理で判断(該当すれば候補へ: xdist 導入前後の実測・backend 内訳) | PR レビュー |
| 要件書・ADR-001〜004・github-setup.md・onboarding.md・`docs/ops/**` | **反映なし** | — |

**正本体系外だが同一 PR で更新するもの**: `pyproject.toml`・`uv.lock`(いずれも **guard_paths** — 人間の逐行確認・実施記録行)・`backend/.coveragerc`(新規)・`tests/test_check_authz_catalog.py`(guard_paths)・`tests/test_census_baseline_check.py`・`tests/domain/gen/test_backends.py`・`.claude/skills/check/SKILL.md`・`docs/features/ci-harness-parallel/{plan,research}.md`・`docs/worklog/2026-10-08-ci-harness-parallel.md`。**触れないもの**: `.github/workflows/ci.yml`・`tests/test_ci_wiring.py`・`contracts/**`・`tests/fixtures/frozen-archive-cases/**`・`backend/pyproject.toml`・`backend/*conftest.py`(4 節「凍結点への注意」「コア領域 paths への注意」)

## 4. 実装方針

- **重さ分類 = 通常** の根拠: 変更対象はルートの pytest 設定(`pyproject.toml`)・`backend/.coveragerc`(新規)・ハーネスのテスト・依存・スキル本文・設計書の節更新で、コア領域 5 領域の `paths` には該当しない(`pyproject.toml`・`uv.lock`・`tests/test_check_authz_catalog.py` は guard_paths だが ADR-001 の重さ分類上のコア領域ではない。`ci.yml`・`contracts/**`・`tests/fixtures/frozen-archive-cases/**`・`backend/pyproject.toml`・`backend/*conftest.py` には触れない — 「凍結点への注意」「コア領域 paths への注意」)。軽微でもない(CI の実行形態と 50 行超の差分)。機械的軽作業でもない(テストの分割・共有の設計判断を伴う)。**コードとテスト(ステップ 1〜4)は Codex へ委任**、文書(ステップ 5)は Claude が編集する(設計書 3 章)
- **ワーカー数**: CI = `-n auto`(ランナーの 4 vCPU に追随。`-n 4` 固定にしない — ランナー変更時に自動で追随)/ ローカル = 8 上限(PO 決定。24 コア機でも子プロセスを多数起動するテストのため過負荷を避ける)。**指定場所はルート `pyproject.toml` の `[tool.pytest.ini_options] addopts = "-n auto"`**(2026-10-08 計画修正 — 当初は `ci.yml` のコマンド側に置く案だったが、`ci.yml` は凍結の外部入力のため触れない。下記「凍結点への注意」)。ローカルの上限は `/check` が **`PYTEST_XDIST_AUTO_NUM_WORKERS=8`** で `auto` を上書きする(xdist 3.8.0 が対応 — 実測済み)。**副作用(明示)**: ルートの `pytest` は常に並列既定になる — mutation ジョブ(`uv run pytest -c pyproject.toml tests/domain/mut/`)も 4 ワーカーで走る(結果は不変・所要時間は短縮方向)/ 単体デバッグは `-n 0` で直列に戻す / `uv run python tests/test_census_baseline_check.py` の直接実行経路は pytest を経由しないので無関係
- **凍結点への注意(2026-10-08 ステップ 1 で実測)**: `.github/workflows/ci.yml` は **テナント分離の凍結資産 `contracts/tenant_boundary/base-allowlist.json` の `baseline_control.identity.frozen_projection.external_files`**(`:19-24` — 検査器・helper・`frozen_archive.py`・`ci.yml`。`docs/features/tenant-boundary-baseline/design.md:114` の設計)と、**比較 corpus `tests/fixtures/frozen-archive-cases/manifest.json` の `corpus_inputs.files`** に含まれる。1 行でも変えると (a) `tests/test_check_tenant_boundary_bypass.py::test_repository_is_green` が「射影が動いた資産は識別値の更新が必要」(`scripts/frozen_history.py:1481`)で red → 設計書 7.7-2 の受理(識別値 `contract_revision` の繰り上げ + PR 番号付き v2 受理記録 + PO の受理)が要る (b) `tests/test_frozen_archive.py`・`tests/test_frozen_archive_case_runner.py` の 33 件が corpus digest 不一致で red → digest の再 pin が要る。いずれも **コア領域 paths**(`contracts/tenant_boundary/*`・`tests/fixtures/frozen-archive-cases/*`)の変更になり PR が敵対レビュー経路になるため、**本タスクは `ci.yml`・`tests/test_ci_wiring.py`・`contracts/**`・`tests/fixtures/frozen-archive-cases/**` に触れない**(PO 判断 2026-10-08)。各ステップの合格条件に `git status` でこれらが現れないことを含める。凍結点の一覧はリポジトリに無い(運用評価台帳 2026-10-05 の候補)ため、この 2 点を本計画に記録しておく
- **コア領域 paths への注意(計画レビュー 5 回目・2026-10-08)**: `backend/pyproject.toml`・`backend/uv.lock`・`backend/*conftest.py` は `.claude/core-areas.json` の **5 領域すべてのコア領域 paths**。backend の pytest / coverage の挙動を非コアで変えられる置き場は **`backend/.coveragerc`**(coverage が `working-directory: backend` で既定で読む — 新規・どの領域の glob にも該当しない・backend 直下を列挙するテストは無い)だけ。pytest 側の `--durations` は置き場が無い(`addopts` = コア、conftest = コア、`PYTEST_ADDOPTS` = `ci.yml`)ため本タスクから外した(PO 判断 2026-10-08)
- **分割の方針(ステップ 2)**: 収集時の列挙はリポジトリ資産を読む(`_repository_oracle_assets()`)。収集コストは数十 ms 級で許容。ID は `資産名-葉パス-変異` の形で可読にし、xdist の `load` 分配に任せる。「全数」の保証(分割で母集団が黙って減る・重複する経路を閉じる)は独立のテストで固定する: ① 葉側 — 旧ループと同じ走査(`_iter_leaf_paths` × 6 資産 + seal × 改変/削除)で**独立に導出した期待キー集合**と、パラメータ列のキー集合が**完全一致**し、かつキーが**一意**であること(件数一致だけでは 1 件の重複と 1 件の欠落を見分けられない)② 容器列側(`test_recursive_derivers_cover_generated_container_sequences_and_siblings` には `attempts` が無い)— 旧ループと同じ走査(深さ 1..d の `("dict","list")` の直積 × 各 `widened_index`)で**独立に導出した期待キー集合 {(sequence, widened_index)}** と、パラメータ列のキー集合が**完全一致**し、かつ一意であること(件数一致だけでは 1 組の重複と 1 組の欠落を見分けられない — 葉側と同じ規律)。あわせて件数が Σ_{depth=1..d} 2^depth × depth と一致すること ③ 各資産の葉数 > 0
- **共有の方針(ステップ 3)**: 通常の census 検査は**毎回、監査(`_audit_declaration_implementation`)の内側で実行され**(`tests/test_census_baseline_check.py:1982`)、アンカーもテストごとの一時 `reference_root` へ実体化される(`:1993`・パス照合 `:592`)。さらに実体化には**来歴検査**があり(`_assert_declared_anchor_materialization_provenance` `:340` — `git show` 応答の観測世代がその回の `monitor` と同一・書込みが観測した応答そのもの・revision と内容の一致を要求。監視開始前に捕捉した bytes を後から使う退行は `:3354` の回帰テストが拒否する)、**取得結果をテスト間で持ち回ることはできない**。したがって共有・削減の経路は次の 2 つに限定し、監査の宣言読取り(実行ごとに記録)・テストごとの `reference_root`・パス照合・来歴検査の不変条件は**変えない**: ① **現行センサス走査(`_checker_census` `:630`)のメモ化** — 同関数は `checker_module.load_contract(repository_root)` で契約を読んでから `scan_directory(source_root, contract=...)` を走らせるため、キーは **検査器(モジュール `__file__` の内容 digest)× 契約入力(`repository_root` の解決済みパス + `load_contract` が読む資産〔`scripts/check_tenant_boundary_bypass.py:1335-1353` の `DEFAULT_*`・`FROZEN_BASELINE_ASSETS`〕の内容 digest)× `source_root`(解決済みパス + ツリー digest)** とし、かつ **`checker_module.load_contract`・`scan_directory` が import 時の関数オブジェクトと同一(差し替えられていない)場合に限って共有**する。別の契約ツリーを渡す呼び出し(`:2665,2709` の `current_root`)・`load_contract` の差し替え(`:2346-2349`)・`_checker_census` 自体のラップ(`:2764-2769`)はキー不一致または条件不成立で自動的に再計算になる ② **アンカー実体化(`_materialize_declared_anchor` `:381`)の取得のバッチ化** — 各実体化の `monitor` 生成後に 129 ファイル(`materialized_tree.file_count`)分の `git show` を 1 ファイル 1 プロセスで回す現行(`:424`)を、**その回の取得として 1 回の `git cat-file --batch`(stdin に `<anchor_commit>:<relative_path>` を列挙。同等の 1 プロセス取得でも可)でまとめて取得**し、応答を従来どおり `_ObservedGitBlob(monitor, anchor_commit, content)` として観測してから書き込む(観測世代・書込み元の同一性・revision・内容一致の不変条件は不変。**テスト間のキャッシュは置かない**)。子プロセス起動は 129 × 9 → 1 × 9 回。**削減可能量はステップ 3 の冒頭でプロファイル(`-n 1` の総経過時間と `--durations=0` の setup/call 内訳)を取って定め**、目標 = 総経過時間の半減、**下限 = 25% 短縮**(下限に届かない場合は手法を変えずに止め、実測と理由を worklog に記録して PO へ報告する)。既存テストが red/green で示すこと(監査が検出する「結線が外れた」型・来歴検査が拒否する「監視開始前キャッシュ」型 — いずれも既存の回帰テスト — を再生産しない)
- **xdist の揺れへの備え**: ステップ 1 の合格条件で 8 ワーカーを 2 回連続・新規失敗ゼロとし、順序依存が出たファイルは当該ファイルだけ同一 worker にまとめる(`pytest-xdist` の `--dist loadfile` 相当・`xdist_group`)。原因不明のまま `-n 1` へ戻さない。**実測した揺れ(2026-10-08・1 回目のみ 1 件)**: `tests/domain/gen/test_backends.py::test_generation_writes_neither_product_paths_nor_contracts` — `_tree_snapshot` が `backend/src/pitchlog` 配下を `rglob` で全列挙するため、別 worker の import が書く `__pycache__/*.pyc` を拾って before/after が食い違う。対処 = スナップショットから `__pycache__` 配下を除外する(テストの主張「生成が製品パス・contracts に何も書かない」は不変。PO 判断 2026-10-08・計画外 1 ファイルをステップ 1 に含める)。サンドボックス固有の赤(`tests/test_packaging.py` の 2 件 = ネットワーク不可、`tests/test_doc_check_profile.py::test_propagation_checker_and_claude_files_are_unchanged` = 未コミット差分)は Claude 側の手元実行で確認する
- **手元の既知失敗(固定集合 — research.md §6)**: `tests/domain/gen/test_formatter.py::test_alpha_python_typescript_and_reference_return_same_display`・`tests/domain/test_review_triggers_complete.py::{test_as_of_fifty_accepts_all_due_evaluations, test_nine_po_evidence_locations_are_allowed_and_exist, test_recorded_evaluations_match_machine_measurements_and_po_evidence, test_machine_trigger_cannot_be_marked_without_measured_condition}` の 5 件(develop でも同じく失敗・CI では green)。手元の合格条件は「この 5 件以外の失敗がゼロ」、CI では全件 green
- **計測の定義**: 手元の所要時間は同じワーカー数で前後を比べる。census の「ファイル合計時間」= **`-n 1`(直列)で `uv run pytest tests/test_census_baseline_check.py` を実行したときの総経過時間(pytest の報告する `in N s`)**。module fixture へ移した計算は `call` から `setup` へ移るだけで総時間は減らないため、`call` だけで判定しない(内訳の確認には `--durations=0` の setup/call/teardown を併記する)。並列化の効果と共有の効果を混ぜないため、必ず `-n 1` 同士で比べる。CI の実測(harness / backend ジョブの所要時間)は **PR 作成後の DoD 検証**として run から取得し worklog に記録する(正本の順序 = ステップ検証 → コミット → 文書反映 → PR → CI。ステップの合格条件には置かない)。backend ジョブは `backend/**` の変更で走る(本 PR は `backend/.coveragerc` を足すので走る)
- **ステップの担当**: ステップ 1〜4 = Codex(`/implement` でステップ単位)。ステップ 5 = Claude(文書)。Codex はコミットしない(Claude が 1 ステップ 1 コミット)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **xdist 導入**(Codex): ルート `pyproject.toml` dev 依存に `pytest-xdist` + `uv.lock` 更新(Claude が `uv add` で実施済み — サンドボックスはネットワーク不可)/ 同ファイル `[tool.pytest.ini_options]` に `addopts = "-n auto"` / `.claude/skills/check/SKILL.md` の harness pytest を `PYTEST_XDIST_AUTO_NUM_WORKERS=8 uv run pytest tests/` に / `tests/domain/gen/test_backends.py::_tree_snapshot` から `__pycache__` を除外。**`ci.yml`・`tests/test_ci_wiring.py` は不変** | `PYTEST_XDIST_AUTO_NUM_WORKERS=8 uv run pytest -c pyproject.toml tests/ --ignore=tests/domain/boot --ignore=tests/domain/mut --ignore=tests/test_plan_generation.py --ignore=tests/test_step_history_audit.py` を **2 回連続**実行し、いずれも **4 節「手元の既知失敗(固定集合)」5 件以外の失敗がゼロ**(出力に `8 workers`)/ `uv run pytest tests/test_ci_wiring.py` green(変更なし)/ `uv run ruff check .`・`uv run ty check` green / `git status --short` に `.github/workflows/ci.yml`・`tests/test_ci_wiring.py`・`contracts/`・`tests/fixtures/frozen-archive-cases/` が現れない / 導入前(直列 974 秒)と 8 ワーカーの所要時間を worklog に記録 |
| 2 | **巨大 2 テストのパラメトライズ分割**(Codex): `tests/test_check_authz_catalog.py:4983,5141` を収集時列挙の `parametrize` へ展開し、4 節「分割の方針」①〜③(葉側・容器列側とも、旧ループと同じ走査で独立導出した期待キー集合との完全一致・一意性〔容器列は幅・深さからの期待件数も併記〕/ 葉数 > 0)を固定する独立テストを追加 | `uv run pytest tests/test_check_authz_catalog.py -n 8 --durations=0` で 5 件の既知失敗以外ゼロ・**分割で生じたパラメータケース(2 テスト由来の node ID)の最長 call 時間 < 30 秒**(変更対象外の `test_g_*` 3 件〔40〜42 秒〕は対象外)/ 期待キー集合との完全一致・一意性・容器列の件数のテストが green / `-n 1` でも同じ結果(順序非依存) |
| 3 | **census 系の重複計算の共有**(Codex): まず `-n 1` の総経過時間と `--durations=0` の内訳でプロファイルを取り、4 節「共有の方針」の 2 経路(① 現行センサス走査のメモ化〔キー = 検査器 digest × 契約入力 × `source_root`・`load_contract`/`scan_directory` が未差し替えの場合のみ〕② アンカー実体化の取得を各回 1 プロセスへバッチ化〔来歴検査の不変条件は不変・テスト間キャッシュなし〕)を実装する。監査の宣言読取り・テストごとの `reference_root`・パス照合・来歴検査は不変 | `-n 1` で測った `tests/test_census_baseline_check.py` の**総経過時間**が、同条件の導入前(同じ機械で直前に計測)の **50% 以下(目標)・少なくとも 75% 以下(下限)**。下限未達なら手法を変えずに止め PO へ報告 / 同ファイルが `-n 8` と `-n 1` の両方で green / `uv run python tests/test_census_baseline_check.py`(CI の直接実行経路)が従来どおり `census-baseline: OK` / 監査 wiring のテスト(結線が外れた型を red にするもの)・来歴検査の回帰テスト(`:3354`)・契約差し替えの変異テスト(`:2346,2665,2709`)が不変で green / 前後の総経過時間と setup/call 内訳を worklog に記録 |
| 4 | **backend の coverage を sysmon へ**(Codex): `backend/.coveragerc` を新規作成し `[run]` に `core = sysmon` を置く(2 行)。**`ci.yml`・`backend/pyproject.toml`・pytest コマンド・期待値資産・`tests/test_ci_wiring.py` は不変** | `backend/` で `uv run coverage debug config` の出力に `config_files_read: .../backend/.coveragerc` と `core: sysmon` / `backend/` で `uv run pytest -c pyproject.toml -m "not requires_db" --cov`(手元に DB が無いため非 DB の約 940 件)が green でカバレッジ表が出る / `git status --short` の `backend/` 配下の変更が `backend/.coveragerc` の追加だけ / ルートで `uv run pytest tests/test_ci_wiring.py` green |
| 5 | **文書の追随**(Claude): 設計書 10.1 の harness/backend 行・変更履歴 1 行(版は上げない)・`docs/README.md`・worklog に手元の実測(8 ワーカーの前後・census の `-n 1` 総経過時間の前後) | `uv run python scripts/check_docs_status.py` 0 違反 / `uv run python scripts/check_plan_docs_sync.py --plan docs/features/ci-harness-parallel/plan.md --base origin/develop` exit 0 / 設計書 10.1 の harness 行に `-n auto`(addopts)と `PYTEST_XDIST_AUTO_NUM_WORKERS`、backend 行に `backend/.coveragerc` の `core = sysmon` の記述がある |

**PR 作成後の DoD 検証(ステップではない — 正本の順序どおり PR → CI の後に行う)**: PR の run から harness ジョブの所要時間と backend ジョブの所要時間(sysmon 導入前 15.7〜15.9 分との比較)を取得し、worklog に記録する。**harness が 8 分を超えた場合は DoD 不合格として差し戻す**(/pr の差し戻し手順: plan を `active` へ戻し、原因〔最長ケース・ワーカー数・揺れ〕を是正して再計測)。8 分以内を満たすまで PR を「確認待ち」にしない

## 5. DoD(受け入れ基準)

- [ ] harness ジョブの pytest が `-n auto`(ルート `pyproject.toml` の addopts — `ci.yml` 不変)で並列実行され、**PR 作成後の CI run で** harness 所要時間が **8 分以内**(実測を worklog に記録 — PR 後の DoD 検証)。ローカル `/check` は `PYTEST_XDIST_AUTO_NUM_WORKERS=8`
- [ ] `test_check_authz_catalog` の全数変異 2 テストがパラメトライズで分割され、網羅性(独立導出した期待キー集合との完全一致・一意性・容器列の期待件数・葉数 > 0)をテストで固定したまま、分割由来のケースの最長 call 時間が 30 秒未満
- [ ] census 系テストの重複計算(現行センサス走査のメモ化・アンカー実体化の取得バッチ化)が削減され、`-n 1` の総経過時間が導入前の 75% 以下(目標 50%)。CI の直接実行経路・監査の宣言読取り・テストごとの `reference_root`・来歴検査の不変条件は不変
- [ ] backend の coverage が `backend/.coveragerc` の `[run] core = sysmon` で動き、**PR 作成後の CI run で** backend ジョブの所要時間(導入前 15.7〜15.9 分)との前後比較が worklog に記録されている。期待値資産・pytest コマンド・`ci.yml`・`backend/pyproject.toml` は不変。`--durations` の内訳は後続タスク B へ
- [ ] 設計書 10.1 の harness/backend 行と `/check` スキルが追随し、docs-lint・plan/docs 突合が green。PR は guard_paths(`pyproject.toml`・`uv.lock`・`tests/test_check_authz_catalog.py`)の逐行確認を経る。`ci.yml`・`contracts/**`・`tests/fixtures/frozen-archive-cases/**` に差分が無い

## 6. テスト計画

- 本タスクの変更はテスト基盤そのものなので、検証 = ハーネステスト全件(`-n 8` と `-n 1` の両方で green — 順序非依存の確認)+ `tests/test_ci_wiring.py`(CI 配線の固定)+ 分割テストの件数一致テスト(新設)。NFR-019 の種別追加はない(製品コードの変更なし)
- 計測: 手元 8 ワーカーの所要時間(導入前 974 秒・直列)/ CI の harness と backend ジョブの所要時間(PR の run)を worklog に記録し、DoD の判定に使う
