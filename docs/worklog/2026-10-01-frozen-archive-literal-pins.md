---
date: 2026-10-01
topic: TSK-466 frozen_archive のテストのリテラル固定を外す
branch: fix/frozen-archive-literal-pins
---

# 作業ログ: 2026-10-01 TSK-466 frozen_archive のテストのリテラル固定を外す

## ステップ 1: 現況と受理記録 +1 の全件実測

- 測定元: `fix/frozen-archive-literal-pins`、`HEAD=9ee4c1784f4934084623ce937616fa9b31645027`。測定開始時の `git status --short` は空。計画書の基準 `origin/develop=f527cddf` 相当のコードに、計画書等の作業ブランチコミットが載った状態。
- 現況: `uv run pytest tests/ -q` は **2113 passed**、終了コード 0。
- 合成: **48 failed、2065 passed**、終了コード 1。全 2113 件を実行。失敗の内訳は **固定 assertion の直接失敗 17 件・corpus digest 31 件（直接 1 件、連鎖 30 件）**。固定 assertion の 17 件は履歴長 7、参照数 7、metrics 2、版列 1。

### 合成の作り方と適法性

`/tmp/tsk466-make-synthetic.py` で測定元を `/tmp/tsk466-synthetic` にローカル clone し、仮想環境を `/tmp` 側へ複製した。`base-allowlist.json` の `contract_revision` と `current_identifiers` を 19→20 にし、現況の 8 資産と宣言済み外部ファイルから `frozen_history.py` の射影・snapshot 導出関数を使って受理前後を作った。`baseline_control.history` の既存 6 件を byte ではなく JSON 値として prefix 不変に保ち、`masaki1025/pitchlog#90` の v2 記録 1 件を追記した。`#90` は既存の `#78/#80/#86/#84/#83` と、テスト内の `#79/#81` のいずれにも衝突しない。追記記録のキー集合は既存末尾の **9 キーと exact-set 一致**し、`change.before`/`after` は両方とも `declaration`、`movement_policy`、`external_snapshots`、`asset_snapshots` の 4 側面を持つ。実差分の `aspect` は `asset_snapshots` と `declaration`。

`history-snapshots/` には SHA-256 をファイル名とする `6004e72706b96fa4d3ac573f5b76753d609e0db17e4ba54b2ff7c5a00598e05f` を 1 件追加し、内容ハッシュとの一致を検査した。合成側の `git status --short` は authority JSON の変更とこの snapshot の追加だけだった。`frozen_history.validate_repository_histories` を PR 受理モードで比較元・合成後の 8 資産と snapshot ディレクトリへ直接適用し、例外なしで通過した。`frozen_archive.validate_snapshot_archive` も通過した。したがって、以下は不正な追記の副作用を測ったものではない。

直接値の補助測定では、履歴版列は `[1,2,2,2,2,2,2]`、一意参照は 51 件、archive metrics は `SnapshotArchiveMetrics(84, 2_965_310, 33, 1_214_665)` だった。corpus digest は manifest の `199bac414260249591e84d0ccfc7cd559cf06c32c3d6a552f7a309e1f1822aaf` に対し合成側 `78ffe6b41fd1fc4416acd675e80146edf6568dd70fb0eedff02a10f8c27ef41c`。版列テストの後続 `:131` と metrics テストの期待値 `:332-336` は先行の assertion に隠れるため、この直接測定で個別に差を確認した。

### 失敗テスト ID → 根因の固定箇所

以下は JUnit XML の全 48 failure を 1 行ずつ写像したもの。`連鎖` は `runner.py:735 prepare_case` が最初に `validate_corpus_inputs` を呼び、manifest の digest 不一致で後続処理へ進まないことを指す。

| 失敗テスト node ID | 根因の固定箇所（ファイル:行） | 直接/連鎖 | エラー要旨 |
| --- | --- | --- | --- |
| `tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path0]` | `tests/test_check_tenant_boundary_bypass.py:3346` | 直接 | authority_history 7 件≠6 件 |
| `tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path1]` | `tests/test_check_tenant_boundary_bypass.py:3346` | 直接 | authority_history 7 件≠6 件 |
| `tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path3]` | `tests/test_check_tenant_boundary_bypass.py:3346` | 直接 | authority_history 7 件≠6 件 |
| `tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path4]` | `tests/test_check_tenant_boundary_bypass.py:3346` | 直接 | authority_history 7 件≠6 件 |
| `tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path5]` | `tests/test_check_tenant_boundary_bypass.py:3346` | 直接 | authority_history 7 件≠6 件 |
| `tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path6]` | `tests/test_check_tenant_boundary_bypass.py:3346` | 直接 | authority_history 7 件≠6 件 |
| `tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history[relative_path7]` | `tests/test_check_tenant_boundary_bypass.py:3346` | 直接 | authority_history 7 件≠6 件 |
| `tests/test_frozen_archive.py::test_current_mixed_history_has_50_unique_snapshot_references` | `tests/test_frozen_archive.py:120-127`, `tests/test_frozen_archive.py:131` | 直接（:131 は先行 assert に遮蔽） | 版列が 7 件≠6 件。独立測定では参照も 51 件≠50 件 |
| `tests/test_frozen_archive.py::test_added_aspect_is_red_after_current_table_is_green` | `tests/test_frozen_archive.py:139` | 直接 | 一意参照 51 件≠50 件 |
| `tests/test_frozen_archive.py::test_reversed_aspect_classification_is_red_after_current_table_is_green[declaration]` | `tests/test_frozen_archive.py:164` | 直接 | 一意参照 51 件≠50 件（変異前 assert） |
| `tests/test_frozen_archive.py::test_reversed_aspect_classification_is_red_after_current_table_is_green[movement_policy]` | `tests/test_frozen_archive.py:164` | 直接 | 一意参照 51 件≠50 件（変異前 assert） |
| `tests/test_frozen_archive.py::test_reversed_aspect_classification_is_red_after_current_table_is_green[external_snapshots]` | `tests/test_frozen_archive.py:164` | 直接 | 一意参照 51 件≠50 件（変異前 assert） |
| `tests/test_frozen_archive.py::test_reversed_aspect_classification_is_red_after_current_table_is_green[asset_snapshots]` | `tests/test_frozen_archive.py:164` | 直接 | 一意参照 51 件≠50 件（変異前 assert） |
| `tests/test_frozen_archive.py::test_v1_record_forced_through_v2_shape_is_red_after_mixed_history_is_green` | `tests/test_frozen_archive.py:198-200` | 直接 | 一意参照 51 件≠50 件（変異前 assert） |
| `tests/test_frozen_archive.py::test_missing_v2_snapshot_ref_is_red_after_current_history_is_green` | `tests/test_frozen_archive.py:210-212` | 直接 | 一意参照 51 件≠50 件（変異前 assert） |
| `tests/test_frozen_archive.py::test_current_archive_metrics_are_within_limits` | `tests/test_frozen_archive.py:332-336`, `tests/test_frozen_archive.py:339-340` | 直接（:332-336 は期待値構築） | 実測 84 件/2,965,310 B、固定期待 83 件/2,958,228 B と不一致 |
| `tests/test_frozen_archive.py::test_current_archive_has_no_unreferenced_new_snapshot` | `tests/test_frozen_archive.py:514-517` | 直接 | snapshot_count 84 件≠83 件（bytes も独立測定で不一致） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f1]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f2]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f3]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f4]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f5]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f6]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f7]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f8]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f9]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f10]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f11]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_corpus_inputs_match_manifest_digest` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 直接 | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[unchanged-acceptance]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[recorded-movement]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[unchanged-identifier]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[new-orphan-snapshot]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[snapshot-count-over-limit]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[snapshot-bytes-over-limit]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[noncanonical-existing-reference]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[noncanonical-appended-reference]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[grandfathered-orphans]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[mixed-v1-v2-history]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_each_case_builds_matching_two_parent_merge_and_event[missing-existing-v2-reference]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_runner_calls_real_cli_in_pull_request_mode` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_checker_rejects_stale_record_after_accepting_single_transition` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_checker_accepts_distinct_referenced_snapshot_sets` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_checker_rejects_archive_mutations_through_production_path[4]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_checker_rejects_archive_mutations_through_production_path[5]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_checker_rejects_archive_mutations_through_production_path[6]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_checker_rejects_archive_mutations_through_production_path[7]` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |
| `tests/test_frozen_archive_case_runner.py::test_current_checker_grandfathers_base_orphans` | `tests/fixtures/frozen-archive-cases/manifest.json:7` | 連鎖（prepare_case 入口） | corpus digest 不一致（manifest 199bac… / 実測 78ffe6…） |

### 根因の exact-set 照合

対応表から得た根因の集合は、`research.md` 1 節の **11 箇所と exact-set 一致**した。過不足は 0。`manifest.json:7` だけを根因とする 31 failure を別々の固定箇所として数えていない。`tests/test_frozen_archive.py:120-127` と `:131`、同 `:332-336` と `:339-340` はそれぞれ同じ test node ID に現れるが、直接値の補助測定により両固定箇所を確認した。

なお `research.md` 1 節は `tests/test_check_tenant_boundary_bypass.py:3346` が「8 インスタンス同時に落ちる」と書くが、実測は **7 failed / 1 passed**。`relative_path2` は `census-baseline.json` で `history=[]` のため `if not history: return` を通り、当該 assertion に到達しない。**根因集合の不一致ではないが、調査メモの件数記述とは食い違う。** `research.md` は変更していない。

### 条件付き 4 件の実測

| 条件付き箇所 | 実測結果 |
| --- | --- |
| `#79`/`#81` の `acceptance_id` literal 11 箇所 | 合成 ID は `#90`。該当 11 箇所が現れる 12 test node は JUnit XML 上で **12 passed / 0 failed**。`#79`/`#81` を使った合成は本測定の対象外。 |
| `test_frozen_archive_case_runner.py:47-58` の `files`/`trees` exact-set | 合成前後の集合がそれぞれ一致。`test_manifest_matches_design_case_set_and_transitions` は **passed**。 |
| `manifest.json` の `cases[9]`/`cases[10]` の description | 合成前後で全 case の description が一致し、当該 2 件も一致。case 試験の failure は両方とも同一の corpus digest 不一致で、文言差による failure は 0。 |
| `frozen-baseline-scan-allowlist.json` と `test_frozen_baseline_declarations.py:287-293` | `.py` 走査は両状態とも 40 桁 13 出現・64 桁 1 出現、pair 集合と allowlist も同一。`test_repository_scan_has_the_declared_terminal_population` は **passed**。 |

### 実行コマンドと終了コード

| コマンド・作業ディレクトリ | 終了コード・結果 |
| --- | --- |
| `uv run pytest tests/ -q`（測定元。初回） | **2**。既定の `~/.cache/uv` が読み取り専用でロック作成に失敗。テストは未開始。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/ -q`（測定元） | **0**。2113 passed。ログ `/tmp/tsk466-baseline.log`。 |
| `python /tmp/tsk466-make-synthetic.py`（測定元） | **0**。PR 受理モードの直接検査と archive 検査を通過。 |
| `/tmp/tsk466-synthetic/.venv/bin/python /tmp/tsk466-probe.py` | **0**。版列、参照数、metrics、digest、条件付き入力差を直接測定。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache PYTEST_ADDOPTS='--junitxml=/tmp/tsk466-synthetic.xml --tb=short' uv run pytest tests/ -q`（`/tmp/tsk466-synthetic`） | **1**。48 failed / 2065 passed。ログ `/tmp/tsk466-synthetic.log`。 |
| `python /tmp/tsk466-map.py > /tmp/tsk466-table.md` | **0**。48 failure と 11 根因の exact-set を assertion で確認。 |
| `git diff --exit-code -- scripts/ contracts/ tests/`（測定元） | **0**。これらの追跡ファイルに差分なし。 |

## 決定

ステップ 1 の測定と記録のみ実施。ステップ 2 以降の assertion・digest・製品経路は変更していない。コミット・push はしていない。

## 未決・次の一歩

`research.md` の「8 インスタンス同時失敗」と実測の 7 件の差は委任元へ報告する。作業中に `docs/features/frozen-archive-literal-pins/design.md` に本作業の操作によらない差分が現れた。こちらからは編集・復元せず保持した。測定元の `scripts/`、`contracts/`、`tests/` には差分なし。
