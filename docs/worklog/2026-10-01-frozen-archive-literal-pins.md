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

## ステップ 2: 参照集合の独立オラクルとの照合

`tests/test_frozen_archive.py` に `_expected_references()` を追加した。生の `baseline_control.history` の v2 記録だけから、`external_snapshots` と `asset_snapshots` の before/after にある `snapshot_ref` を読み、`SNAPSHOT_REF_PREFIX` を取り除いて集合化する。共有するのは prefix 定数だけで、`frozen_archive.py` の抽出関数・分類表・抽出器・検証関数は呼ばない。被検査実装の結果との集合一致と、独立に求めた期待集合の非空をそれぞれ assert する。

| 旧箇所 | 変更前 | 変更後 |
| --- | --- | --- |
| `:131` | `assert len(references) == 50` | `expected = _expected_references()`、`assert references == expected`、`assert expected`。テスト名と docstring の「50件」も現況非依存へ変更。 |
| `:139` | `assert len(_current_references()) == 50` | `assert _current_references() == expected` と `assert expected`。 |
| `:164` | 同上 | 同上。分類反転の 4 パラメータへ適用。 |
| `:198-200` | `assert len(archive.extract_referenced_snapshot_names(history, SNAPSHOT_ROOT)) == 50` | 抽出結果と `expected` の集合一致、`assert expected`。 |
| `:210-212` | 同上 | 同上。 |

### 合成状態と変異の実測

ステップ 1 で適法性を確認した `/tmp/tsk466-synthetic` に変更後のテストファイルだけをコピーし、対象 5 test node（分類反転は 4 instance）を個別に指定して実行した。**7 passed / 1 failed**。唯一の failure は `test_current_mixed_history_matches_independent_snapshot_references` が未変更の版列 assert で `7 != 6` となったもので、ステップ 3 の対象。`/tmp/tsk466-step2-oracle-probe.py` でこの後続の対象 assertion だけを直接実行すると、抽出結果と独立オラクルは **51 件で集合一致**し、期待集合は非空だった。したがって本ステップの 5 箇所の対象 assertion は合成状態で通過した。corpus digest の変更はしていない。

`/tmp/test_tsk466_step2_mutations.py` から元の参照集合テストを 2 通りの変異実装で実行した結果、**2 failed**。

| 変異 | 期待表照合 | red の原因 |
| --- | --- | --- |
| 抽出関数を常に `frozenset()` 返しにする | 抽出関数自体を monkeypatch | `tests/test_frozen_archive.py:146` の `assert references == expected`。期待集合が非空のため空集合と不一致。 |
| `external_snapshots` の after 側だけを抽出しない | `_validate_extraction_tables()` は例外なく通過 | 同じ `:146` の集合一致。分類表は正しいままなので、期待表照合による red ではない。 |

既存の変異テストは測定元で **7 instance 全部 passed**（変異先が期待どおり red になることを `pytest.raises` で確認）。`/tmp/tsk466-step2-mutation-diagnostics.py` でも拒否理由を直接捕捉した。

| 既存の変異 | red の原因 |
| --- | --- |
| 第 5 キー追加 | `ASPECT_NAMES` と抽出表のキー集合不一致。 |
| 分類反転（4 パラメータ） | `ASPECT_REFERENCE_KINDS` と独立の期待表の分類値不一致。独立オラクルへ到達する前に拒否。 |
| v1 記録を v2 として走査 | `change.before` の 4 側面のキー集合不一致。 |
| v2 の `snapshot_ref` 欠落 | `change.before.external_snapshots[0]` のキー集合不一致。 |

### 実行コマンドと終了コード

| コマンド | 終了コード・結果 |
| --- | --- |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive.py::test_current_mixed_history_matches_independent_snapshot_references tests/test_frozen_archive.py::test_added_aspect_is_red_after_current_table_is_green tests/test_frozen_archive.py::test_reversed_aspect_classification_is_red_after_current_table_is_green tests/test_frozen_archive.py::test_v1_record_forced_through_v2_shape_is_red_after_mixed_history_is_green tests/test_frozen_archive.py::test_missing_v2_snapshot_ref_is_red_after_current_history_is_green -q`（測定元） | **0**。8 passed。 |
| 同じコマンドの末尾を `-q --tb=short` にしたもの（`/tmp/tsk466-synthetic`） | **1**。未変更の版列で 1 failed、7 passed。 |
| `/tmp/tsk466-synthetic/.venv/bin/python /tmp/tsk466-step2-oracle-probe.py` | **0**。対象の集合一致と非空を通過。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest /tmp/test_tsk466_step2_mutations.py -q --tb=short` | **1**。意図した 2 failed、いずれも集合一致 assert。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run python /tmp/tsk466-step2-mutation-diagnostics.py` | **0**。既存 4 種、計 7 instance の拒否理由を確認。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ruff check tests/test_frozen_archive.py` | **0**。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ty check` | **0**。 |
| `git diff --exit-code -- scripts/ contracts/` | **0**。両ディレクトリの追跡ファイル差分なし。 |

ステップ 3 以降の版列・metrics・digest は変更していない。コミット・push はしていない。

## ステップ 3: 版列と authority 履歴長の構造条件

測定元 `HEAD=fa04355c11bbfb2569a32c5659c8f6475fa59e5e`、開始時の作業ツリーは clean。`tests/test_frozen_archive.py` の版列固定 `[1,2,2,2,2,2]` を `len(versions) >= 2`、`versions[0] == 1`、`set(versions[1:]) == {2}` に置換した。`tests/test_check_tenant_boundary_bypass.py:3346` の `len(authority_history) == 6` は `>= 2` に置換した。版列と履歴長のどちらも現在の記録数を期待値にしていない。

対象 test node は現況・受理記録 +1 の合成状態の双方で **9 passed / 終了コード 0**。合成状態では変更後の 2 テストファイルが測定元と `cmp` で一致することを確認してから実行した。版列は現況 `[1,2,2,2,2,2]`、合成 `[1,2,2,2,2,2,2]` の両方で構造条件を通過した。

### `FROZEN_BASELINE_ASSETS` 8 インスタンスの内訳

`/tmp/tsk466-step3-branches.py` で `_validate_baseline_control` の返却履歴と実際の分岐を両状態で読んだ。以下の authority 履歴長は現況 / 合成の順。

| パラメータ | 資産 | 到達結果 | authority 履歴長 |
| --- | --- | --- | --- |
| `relative_path0` | `base-allowlist.json` | `>= 2` 通過 | 6 / 7 |
| `relative_path1` | `cache-invalidation-contract.json` | `>= 2` 通過 | 6 / 7 |
| `relative_path2` | `census-baseline.json` | 履歴 0 件のため `if not history: return` | assertion に到達せず |
| `relative_path3` | `db-api-inventory.json` | `>= 2` 通過 | 6 / 7 |
| `relative_path4` | `negative-fixtures.json` | `>= 2` 通過 | 6 / 7 |
| `relative_path5` | `repository-contract.json` | `>= 2` 通過 | 6 / 7 |
| `relative_path6` | `runtime-authz-contract.json` | `>= 2` 通過 | 6 / 7 |
| `relative_path7` | `tenant-context-allowlist.json` | `>= 2` 通過 | 6 / 7 |

### 3 変異の red と原因

`/tmp/test_tsk466_step3_mutations.py` で、各状態の生履歴を変異して変更後の元テスト関数を呼んだ。差し戻しで長さ条件を先頭へ移した後、現況・合成状態ともに **3 failed / 終了コード 1**。以下は再測定で確認した失敗行。

| 変異 | 現況 / 合成の red 原因 |
| --- | --- |
| bootstrap（先頭）を v2 にする | `tests/test_frozen_archive.py:136` の `versions[0] == 1` で失敗。 |
| 末尾付近の v2 を v1 にする | 同 `:137` の `set(versions[1:]) == {2}` で失敗。 |
| 履歴を先頭 1 件だけにする | 同 `:135` の `len(versions) >= 2` で失敗。 |

最初の測定では、1 件への短縮変異が長さ条件より前にある集合条件で止まった。差し戻しで assertion の順序を入れ替え、3 条件を各変異で個別に発火させた。`design.md` 1-2 の順序は旧順のため、この作業では編集せず委任元へ報告する。`tests/test_check_tenant_boundary_bypass.py:3346` は差し戻し時に変更していない。

### 実行コマンドと終了コード

| コマンド | 終了コード・結果 |
| --- | --- |
| `cp /home/ymdms/projects/pitchlog-worktrees/fix-frozen-archive-literal-pins/tests/test_frozen_archive.py /tmp/tsk466-synthetic/tests/test_frozen_archive.py`、`cmp`（両状態の 2 テストファイル） | **0**。両ファイル一致。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive.py::test_current_mixed_history_matches_independent_snapshot_references tests/test_check_tenant_boundary_bypass.py::test_every_frozen_baseline_asset_has_a_valid_chained_history -q`（測定元） | **0**。9 passed。 |
| 同じ pytest コマンド（`/tmp/tsk466-synthetic`、絶対パスから 2 テストファイルをコピーし `cmp` で一致確認後） | **0**。9 passed。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run python /tmp/tsk466-step3-branches.py <root>`（現況・合成の各 root） | **0 / 0**。各々 7 件到達・1 件早期 return。 |
| `TSK466_MUTATION_ROOT=<root> UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest /tmp/test_tsk466_step3_mutations.py -q --tb=short`（現況・合成の各 root） | **1 / 1**。両方とも意図した 3 failed。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ruff check tests/test_frozen_archive.py tests/test_check_tenant_boundary_bypass.py` | **0**。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ty check` | **0**。 |
| `git diff --check` | **0**。 |
| `git diff --exit-code -- scripts/ contracts/` | **0**。両ディレクトリの追跡ファイル差分なし。 |
| `rg -n 'versions\[0\]|versions\[1:|len\(versions\)' docs/features/frozen-archive-literal-pins/design.md` | **0**。1-2 の記載順が旧順のままと確認。 |

初回の合成側試行では作業ディレクトリを `/tmp/tsk466-synthetic` にしたまま相対パスで同じファイルへ `cp` したため、コピー 2 件は終了コード 1、旧テストでの pytest は 8 failed / 1 passed（終了コード 1）となった。**この試行は測定から除外**し、測定元の絶対パスからコピーし直して再実行した。ステップ 4 以降には進んでいない。コミット・push はしていない。

## ステップ 4: metrics の独立計数との照合

測定元 `HEAD=6151c18c`。`tests/test_frozen_archive.py` に `_expected_current_archive_totals()` を追加した。`SNAPSHOT_ROOT` の実ファイルから総件数・総バイト数を数え、ファイル名集合とステップ 2 の `_expected_references()` の差から孤児件数・孤児バイト数を数える。被検査の抽出器は期待値側で呼ばない。

- 群 A: 固定の `SnapshotArchiveMetrics(83, 2_958_228, 33, 1_214_665)` を、上記実測値から組み立てる形へ置換した。
- 群 B: `comparison.base` と `comparison.head` の双方を、その実測由来 `expected` と照合する。`head` の件数・総バイト数が予算内であることと、孤児件数が比較元以下であることも明示した。
- 群 C: `comparison.head` の 4 個の固定値比較を、実測した 4 値との個別比較へ置換した。
- docstring の「現況83件と既存孤児33件」を現況非依存の文言へ改めた。

独立計数と被検査実装の出力は、現況でともに `(83, 2_958_228, 33, 1_214_665)`、受理記録 +1 の合成状態でともに `(84, 2_965_310, 33, 1_214_665)`。孤児の期待値は履歴から抽出した参照集合を経由するため、ここで主張する範囲は**件数・バイト数の実測一致と、比較元から孤児件数が増えていないこと**まで。

対象 2 件、件数・バイト数の閾値ちょうど受理 2 件、比較元と同数の孤児受理、および孤児バイト数の境界 1 件の合計 6 件は、現況・合成状態ともに **6 passed / 終了コード 0**。`git diff --unified=0 -- tests/test_frozen_archive.py` では差分が追加 helper、群 A/B/C、docstring のみに限られ、閾値境界テスト・孤児境界テスト・`_install_metric_mutation` は無変更。

`/tmp/test_tsk466_step4_metrics_mutations.py` で `_measure_snapshot_archive` を monkeypatch した。孤児見逃しは実際の未参照ファイルを 1 件選び、孤児件数とそのファイルのバイト数を計数から除いた。各変異を群 A/B と群 C の両方へ当て、現況・合成状態ともに **6 failed / 終了コード 1**。

| 変異 | 群 A/B で落ちた assertion | 群 C で落ちた assertion |
| --- | --- | --- |
| snapshot 件数を +1 | `tests/test_frozen_archive.py:375` の `comparison.base == expected` | 同 `:557` の `comparison.head.snapshot_count == count` |
| snapshot バイト数を +1 | 同 `:375` の `comparison.base == expected` | 同 `:558` の `comparison.head.snapshot_bytes == total_bytes` |
| 未参照ファイルを 1 件見逃す | 同 `:375` の `comparison.base == expected` | 同 `:559` の `comparison.head.orphan_count == orphan_count` |

`_install_metric_mutation` を使う F3/F4 の統合 test node は、現況でも `runner.py:735` の corpus digest 検査が先に落ちるため **2 failed / 終了コード 1**。この gate はステップ 5 の対象なので変更していない。`/tmp/tsk466-step4-old-metric-mutation-probe.py` で同 helper と本番の `validate_snapshot_archive_limits` を単独接続し、F3/F4 がそれぞれ予定の `ContractError` 分岐へ入ることを現況・合成状態で確認した（各 **終了コード 0**）。統合 test node の green は主張しない。

### 実行コマンドと終了コード

| コマンド | 終了コード・結果 |
| --- | --- |
| `cp <worktree>/tests/test_frozen_archive.py /tmp/tsk466-synthetic/tests/test_frozen_archive.py`、`cmp <worktree>/tests/test_frozen_archive.py /tmp/tsk466-synthetic/tests/test_frozen_archive.py` | **0**。変更後テストファイルの一致。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive.py::test_current_archive_metrics_are_within_limits tests/test_frozen_archive.py::test_current_archive_has_no_unreferenced_new_snapshot tests/test_frozen_archive.py::test_snapshot_count_over_limit_is_red_after_exact_limit_is_green tests/test_frozen_archive.py::test_snapshot_bytes_over_limit_is_red_after_exact_limit_is_green tests/test_frozen_archive.py::test_orphan_count_increase_is_red_after_29_orphans_are_green tests/test_frozen_archive.py::test_orphan_bytes_increase_is_red_after_equal_bytes_are_green -q`（現況・合成の各 root） | **0 / 0**。各 6 passed。 |
| `TSK466_METRIC_ROOT=<root> UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest /tmp/test_tsk466_step4_metrics_mutations.py -q --tb=short`（現況・合成の各 root） | **1 / 1**。各 6 failed、すべて上記 assertion で停止。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run python /tmp/tsk466-step4-metrics-probe.py <root>`（現況・合成の各 root） | **0 / 0**。上記 4 値を実測。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest 'tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f3]' 'tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure[f4]' -q`（現況） | **1**。2 failed、両方 corpus digest gate で停止。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run python /tmp/tsk466-step4-old-metric-mutation-probe.py <root>`（現況・合成の各 root） | **0 / 0**。F3/F4 の既存分岐を確認。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ruff check tests/test_frozen_archive.py` / `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ty check` | **0 / 0**。 |
| `git diff --unified=0 -- tests/test_frozen_archive.py` | **0**。変更範囲を確認。 |

ステップ 5 以降の corpus digest と `scripts/`・`contracts/` は変更していない。コミット・push はしていない。

## ステップ 5: corpus digest の追記不感応と改竄検知

測定元 `HEAD=5d0fe5f3`。`design.md` 2-3 の 2026-10-01・山田正輝承認を再読して再開した。**7.7 の分岐 A**であり、7.7-2 の記録は作っていない。先の中断では、適法な受理記録 +1 に `contract_revision` と `baseline_control.identity.current_identifiers` の 19→20 が伴うため、履歴だけの正規化では現況・合成の digest が一致しなかった。承認後はこの 2 値も除外した。

`corpus_inputs.pinned_prefixes` は `{history_record_count: 正整数（2 以上）, snapshot_names: 昇順・一意の非空 64 桁小文字 hex 名配列}` の exact-set。実ファイルから **`k=6` / `m=83`** を測り、manifest へ固定した。`_normalized_manifest_input` に両値を入れ、除外範囲を後で広げる変更自体も digest に拘束した。生成時点の先頭 `k` 件の履歴と `m` 件の snapshot の名前・内容は hash 対象に残し、それ以降の追記だけを無視する。`base-allowlist.json` の識別値の除外先は、資産内の `baseline_control.identity.field` と `current_identifiers` から導出する。その他の原文は byte 単位で digest に残す。識別値宣言は object・scheme・field・正整数 revision・`current_identifiers` の整合を検査し、不正なら ValueError で止める。

runner で機械再計算した manifest digest は **`b3a1df017e4bbaf19a2c6fc927a7cef91f14ed5bfc0503c137fd8d7e331367d7`**。現況と `/tmp/tsk466-synthetic` の両方で actual = manifest と実測した。後者はステップ 1 の適法な受理記録 +1、snapshot +1 の合成状態で、変更後の runner・manifest をコピーし `cmp` で一致確認した。`identity.field` を検証用に `schema_version` へ替えた別入力では、その欄の繰り上げだけを除外し、`contract_revision` は固定対象へ残ることも直接確認した（終了コード 0）。**欄名 `contract_revision` を除外リストへハードコードしていない。**

現況の `test_production_check_repository_fails_closed_for_each_design_failure` は **F1〜F11 の 11 passed / 終了コード 0**。`test_frozen_archive_case_runner.py` の既存 drift 4 本（runner・manifest case action・契約資産・検査器の変更）はそれぞれ入力変異を拒否して **4 passed / 終了コード 0**。ファイル全体では **25 passed / 1 failed / 終了コード 1**。失敗 1 件はステップ 6 で反転予定の `test_prepare_case_rejects_appended_history_record` で、`ValueError` が発生しなくなったための期待どおりの red。今回この試験は変更していない。

`/tmp/tsk466-step5-mutation-probe.py` は `/tmp` に corpus 入力をコピーし、次の変異を 1 件ずつ当てた。**全件で期待する red を確認し、スクリプトの終了コードは 0**。

| 変異 | red にした検査 |
| --- | --- |
| 先頭 `k` 件の bootstrap `reason` を変更 | `validate_corpus_inputs` の digest 不一致。 |
| 固定済み snapshot を 1 件削除 | `corpus_input_digest` の固定済み snapshot 存在確認。 |
| 検査器 1 本を変更 | `validate_corpus_inputs` の digest 不一致。 |
| 識別値以外の宣言 `movement_policy.acceptance_unit` を変更 | `validate_corpus_inputs` の digest 不一致。 |
| 資産ファイルを 1 本追加 | `validate_corpus_inputs` の digest 不一致（tree のメンバシップを維持）。 |
| `runner.py` を変更 | `validate_corpus_inputs` の digest 不一致。 |
| `pinned_prefixes.snapshot_names` を 1 件減らす | 正規化 manifest の変化を直接確認し、`validate_corpus_inputs` の digest 不一致。 |
| `k` を履歴長より大きくする | `_pinned_authority_content` の固定履歴 prefix 不足。 |
| `m` の固定済み snapshot を 1 件削除 | `corpus_input_digest` の固定済み snapshot 存在確認。 |
| `baseline_control.identity` を欠落させる / `field` を配列へ壊す | `_object` / `_string` の宣言形状検査。 |
| `k=1` / `m=0` | `load_manifest` の下限・非空検査。 |

### 実行コマンドと終了コード

| コマンド | 結果 |
| --- | --- |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run python /tmp/tsk466-step5-digest-probe.py <root>`（現況・合成） | **0 / 0**。同じ actual / manifest digest。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive.py::test_production_check_repository_fails_closed_for_each_design_failure -q` | **0**。11 passed。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive_case_runner.py::test_prepare_case_rejects_changed_runner tests/test_frozen_archive_case_runner.py::test_prepare_case_rejects_changed_manifest_case_action tests/test_frozen_archive_case_runner.py::test_prepare_case_rejects_changed_contract_asset tests/test_frozen_archive_case_runner.py::test_prepare_case_rejects_changed_checker -q` | **0**。4 passed、各変異は red。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive_case_runner.py -q --tb=short` | **1**。25 passed / 1 failed（追記拒否試験のみ）。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive_case_runner.py::test_prepare_case_rejects_appended_history_record -q --tb=short` | **1**。`DID NOT RAISE ValueError`。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run python /tmp/tsk466-step5-mutation-probe.py <root>` | **0**。全 13 変異が上記の箇所で red。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ruff check tests/fixtures/frozen-archive-cases/runner.py tests/test_frozen_archive_case_runner.py` / `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ty check` | **0 / 0**。 |
| `git diff --check` / `git diff --exit-code -- scripts/ contracts/` | **0 / 0**。 |

変更は `runner.py`・`manifest.json`・`test_frozen_archive_case_runner.py` と本 worklog のみ。ステップ 6 以降には進んでいない。コミット・push はしていない。

## ステップ 6: 適法な追記の正例、固定 prefix の負例、11 ケースの不感応

測定元 `HEAD=3a23bb1e`。`test_prepare_case_rejects_appended_history_record`（不正な `{"synthetic_corpus_drift": true}` を追記して digest 拒否を期待）を `test_prepare_case_accepts_appended_history_record` へ反転した。共通ヘルパ `_source_with_appended_acceptance` は `/tmp` の corpus 入力コピーから一時 Git リポジトリを作り、既存の `_bump_asset_revision` と `_append_current_repository_transition_record` を使って実遷移に沿う v2 記録と内容アドレス付き snapshot を追加する。固定済み prefix の不変、末尾と同じ **9 キー exact-set**、`change.before` / `after` の **4 側面 exact-set**、既存 ID との非衝突、新 snapshot の SHA-256 ファイル名一致を assert する。今回の生成 ID は実測で `masaki1025/pitchlog#85`。正例では元の base からこの遷移を PR event・二親 merge に封入して現版の本番検査器へ当て、**終了コード 0** を確認した。その後、追記済み source の corpus digest 不変と `prepare_case` の成功も確認した。

新設の負例 2 本は、いずれも `prepare_case` から `_assert_prepare_rejects_corpus_drift` を経由して拒否理由を確認する。固定した先頭 `k` 件の bootstrap `reason` を書き換えると、`validate_corpus_inputs` が **「比較 corpus の入力が動いた。期待値の導き直しが要る」**で拒否。`pinned_prefixes.snapshot_names` の先頭 1 件を削除すると、`corpus_input_digest` が **「固定済み snapshot が存在しない」**で拒否した。両試験とも green。

`test_appended_history_record_does_not_change_case_outcomes` は**この合成追記 1 件についてのみ**現版検査器の 11 ケースを追記前・追記後に実行し、全件が manifest の green/red 期待値にも一致したうえで `after == before` を要求する。実測した終了コードは前後とも次のとおりで、試験は green。

| ケース ID | 追記前 | 追記後 |
| --- | --- | --- |
| 1, 2, 9, 10 | 0 | 0 |
| 3, 4, 5, 6, 7, 8, 11 | 2 | 2 |

`/tmp/tsk466-step6-outcomes-probe.py` は本試験を呼んで上の 11 件ずつを表示した。ケース 1 の**追記後終了コードだけを 0→1**にすると `assert after == before` で red。さらにケース 1 の**期待値だけを green→red**にすると `assert all(result.matches for result in results)` で red。比較・期待値検査のどちらも恒真ではない。`test_frozen_archive_case_runner.py` 全体は **29 passed / 終了コード 0**。既存の runner 変更、manifest case action 変更、契約資産変更、検査器変更の 4 本もそれぞれ変異の拒否を要求して green（対象 7 件の個別実行も **7 passed / 終了コード 0**）。

### 実行コマンドと終了コード

| コマンド | 結果 |
| --- | --- |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive_case_runner.py::test_prepare_case_accepts_appended_history_record tests/test_frozen_archive_case_runner.py::test_prepare_case_rejects_changed_pinned_history_record tests/test_frozen_archive_case_runner.py::test_prepare_case_rejects_missing_pinned_snapshot -q --tb=short` | **0**。3 passed。 |
| 上記 3 件と既存 drift 4 件の計 7 test node を `uv run pytest … -q --tb=short` で実行 | **0**。7 passed。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive_case_runner.py::test_appended_history_record_does_not_change_case_outcomes -q --tb=short` | **0**。1 passed。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run python /tmp/tsk466-step6-outcomes-probe.py <root>` | **0**。11 件の前後値と、1 件の終了コード変異・期待値変異の red を確認。初回は検証スクリプト側の `sys.path` 不足で終了コード 1、修正して再実行した。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run pytest tests/test_frozen_archive_case_runner.py -q --tb=short` | **0**。29 passed。 |
| `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ruff check tests/test_frozen_archive_case_runner.py` / `UV_CACHE_DIR=/tmp/tsk466-uv-cache uv run ty check` | **0 / 0**。 |

`runner.py`・`manifest.json`・`scripts/`・`contracts/` は変更していない。ステップ 7 には進んでいない。コミット・push はしていない。

---

## 結果サマリ(`/pr` のクローズ処理)

### 実装したもの

**受理記録を足す PR をすべて落としていた 11 箇所のリテラル固定を外した。** 製品経路(`scripts/frozen_archive.py` / `scripts/check_tenant_boundary_bypass.py`)は**差分 0 バイト**で、変更はテストと fixture だけ。

| クラス | 置換の形 |
| --- | --- |
| 参照集合(5 箇所) | **独立オラクルとの集合一致**(生 JSON から導出。被検査実装の抽出関数・分類表・抽出器・検証関数を呼ばず、共有は `SNAPSHOT_REF_PREFIX` 定数のみ) |
| 版列・authority 履歴長(2 箇所) | **構造条件**(長さ 2 以上 → 先頭が v1 → 以降すべて v2。**この順序でないと長さ条件が死ぬ**) |
| metrics(3 箇所) | **独立計数との照合**(ディレクトリを直接数える)+ 予算上限 + 孤児の非増加 |
| corpus digest(1 箇所) | **「生成時点の prefix と集合」の固定**(`pinned_prefixes` = `history_record_count` `k=6` / `snapshot_names` `m=83`)。**追記は通し、改竄・削除は red** |

### 検出力を壊していないことの実証

| 機構 | 実証 |
| --- | --- |
| 参照集合のオラクル | **期待表照合を通過する誤抽出**(`external_snapshots` の after 側欠落)を捕まえる。既存の期待表照合では捕まらない変異 |
| 版列の 3 条件 | **3 つの変異がそれぞれ別の assertion で発火**(差し戻し 1 周で是正) |
| metrics | 変異 3 種(件数 +1 / バイト +1 / 孤児の見逃し)が各 6 件 red |
| corpus digest | **変異 13 件がすべて意図した箇所で red**。既存 drift 4 本も恒真化していない |
| 追記不感応 | 11 ケースの終了コードが追記前後で一致。**ケース 1 の値を変えると red**(恒真でない) |

### 安全の守り 3 つ(2026-10-01・山田正輝承認の条件)

1. **除外先を資産の `baseline_control.identity.field` 宣言から導出**(ハードコードした列挙にしない)
2. **`pinned_prefixes` 自体を digest に拘束**(`runner.py:406` — 除外範囲の拡大自体が検出される)
3. **fail-closed** — **`k > len(history)`(記録の削除)で red**(`runner.py:498`)/ 固定 snapshot の不在 / `identity` 宣言の欠落・不正 / `k < 2`(`:283`)/ `m < 1`(`:262`)。**保留・skip・中立を認めない**(設計書 7.7-3 `:609-612`)

### 人間の判断 2 件

| 判断 | 内容 |
| --- | --- |
| **設計書 7.7 の射程**(2026-10-01) | **分岐 A「対象外」。** 決め手は **7.7-2 の記録形式がテストの期待値を書く枠を持たない**こと(`scripts/frozen_history.py:20-27` の 4 側面)。**補強 3 つはいずれも当てはめで条文の裏付けではない** |
| **除外範囲の拡大**(2026-10-01) | **識別値を除外へ加える。** 適法な受理記録の追記は `contract_revision` と `current_identifiers` も 19→20 へ繰り上げるため(実測)。**守り 3 つを条件とした** |

### 正本への反映

- `docs/development/harness-evaluation.md` — **`## 候補` へ新規 2 件**(7.7 の射程の両義性 / リテラル固定を外す是正の危険)+ 変更履歴表に 1 行。**版は上げない**(7.6-3 前段)・**`H-*` の採番なし**
- `docs/README.md` — 台帳行を **候補 87 件・2026-10-01** へ現行化

**TSK-444 の候補「検査が、そのタスクに無関係な PR を巻き込んで赤にする」は本記述の時点で develop へ未着地**(`feature/tenant-session-supply`)のため追記できず、**新規候補②から相互参照を張る旨だけ記した。**

### ゲート

| | 結果 |
| --- | --- |
| `uv run pytest tests/` | **2,116 passed**(終了コード 0) |
| `uv run ruff check .` / `uv run ty check` | All checks passed |
| `uv run python scripts/check_tenant_boundary_bypass.py` | 終了コード 0 |
| `uv run python scripts/check_docs_status.py` | 終了コード 0 |
| 台帳追記後の docs 系再実行 | 311 passed |

### 射程外(送り出し)

| 事項 | 送り先 |
| --- | --- |
| `acceptance_id` の `#79` / `#81` literal 11 箇所 — いまは落ちないが、将来その番号を名乗る受理記録が出たら一斉に red | **起票が必要**([design.md](../features/frozen-archive-literal-pins/design.md) 4 節) |
| `tests/test_frozen_archive.py` の無力な assertion(`clean_history` も期待も空集合で退化実装が素通りする) | 同上 |
| TSK-448 の `design.md:120` の「一意参照 18 件」が未更新 | 同上 |
| TSK-448 の `research.md` の典拠の行ずれ(`:605`→`:607` / `:900`→`:895`) | 同上 |

### 未解決

**TSK-444 の 48 件の内訳の合計(11 + 7 + 1 + 1 + 1 = 21)が 48 にならない点は未解明。** 本タスクの実測では 48 = 固定 assertion の直接失敗 17 + corpus digest 31(直接 1・連鎖 30)で、**444 は「種類」を数えている可能性が高いが確認していない。**

---

## 敵対レビュー 1 周目 P1 是正(2026-10-02)

`tests/test_frozen_archive.py` に `test_current_unpinned_snapshots_are_referenced` を追加した。既に読み込まれている `CASE_MANIFEST = case_runner.load_manifest()` の `corpus_inputs.pinned_prefixes.snapshot_names` を固定名集合とし、実ディレクトリの通常ファイル名との差集合を `_expected_references()` に包含させる。新しい件数リテラルは追加していない。固定時点の孤児は固定名集合に含まれる。

| 検証 | 実測 | 落とした検査 |
| --- | --- | --- |
| 現況の対象ファイル全件 | 36 passed、終了コード 0 | — |
| 適法な受理記録 +1 の `/tmp/tsk466-synthetic` の対象ファイル全件 | 36 passed、終了コード 0 | — |
| `/tmp` の snapshot ディレクトリに、有効な SHA-256 名を持つ未参照ファイルを 1 件追加 | 1 failed、終了コード 1 | 新設テストの `assert unpinned <= _expected_references()` |
| `/tmp` の corpus コピーから、固定済み孤児を 1 件削除 | 1 failed、終了コード 1 | 既存の `runner.validate_corpus_inputs` → `corpus_input_digest` が「固定済み snapshot が存在しない」と拒否 |

合成はステップ 1 の `/tmp/tsk466-make-synthetic.py` が作ったもので、履歴記録と content-addressed snapshot を追記し、`frozen_history.validate_repository_histories` と `frozen_archive.validate_snapshot_archive` に通している。今回の検査前に `runner.py`・`manifest.json`・両検査器が現況と合成で一致することも `cmp` で確認した。

実行コマンドと終了コード: `uv run pytest tests/test_frozen_archive.py::test_current_unpinned_snapshots_are_referenced -q` は現況・合成とも 0(各 1 passed)。`uv run pytest tests/test_frozen_archive.py -q` は現況・合成とも 0(各 36 passed)。`uv run pytest /tmp/test_tsk466_p1_mutations.py::<変異テスト名> -q` は 2 種を個別に実行し、それぞれ 1(意図した red)。`uv run ruff check tests/test_frozen_archive.py`、`uv run ty check`、`git diff --check`、`git diff --exit-code -- scripts/ contracts/ tests/fixtures/frozen-archive-cases/runner.py tests/fixtures/frozen-archive-cases/manifest.json` はすべて 0。`uv run pytest tests/ -q` は対象外へ広がるため進行中に中断し、終了コード 130(全件の結果は主張しない)。

変更したリポジトリファイルは本テストファイルとこの worklog だけ。`scripts/`・`contracts/`・fixture の `runner.py`・`manifest.json` は差分 0。コミット・push はしていない。
