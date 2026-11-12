# 7.7 失敗の共通原因（2026-11-13 実測）

対象: `feature/mvp-integration-20261109` HEAD `90c1def4`
実測: `uv run --offline pytest tests/test_check_tenant_boundary_bypass.py -q` → **563 failed / 272 passed / 2 errors**（837 collected）。
`scripts/rederive_tenant_generated_modules.py --check` は exit 0（生成モジュール自体は資産と一致）。

## 最大の原因（550/563）

`pr197_generated_facts_sha256` の pin 不一致。

- 現行 `backend/src/pitchlog/stats/generated/facts.py` SHA-256: `d39e5caf86a44bd8a52bc9b7cdb61f4707376aac9b797de36530abd5fb3e9e9f`
- `contracts/tenant_boundary/frozen-inputs.json` の pin: `7673b5969d6ce3104b48d4f94f217c6b4a44ef1b9b08d06ebaeee935648497d4`
- 固定 Git `a59c654e...:backend/src/pitchlog/stats/generated/facts.py` は `7673b596...`。差分は 27 番目 `batters_faced` の追加と `SOURCE_MODEL_HASH` 更新（生成 commit `ca7564e4`）。
- `checker.load_contract()` → `_load_pr197_source_owners` がほぼ全テストの前提のため、544 件が同じ例外で落ち、残り 6 件が別エラーに化ける。
- **SHA だけの書き換えは不可**。`scripts/frozen_history.py:2215-2229` の `read_original_pr197_pin` が origin commit `2fa42d65` の旧 source 行と照合して拒否する。

## 次の原因

1. **7.7-2 履歴・snapshot drift**（2直接 + 次ゲート）
   - 最新受理 `masaki1025/pitchlog#197` は base-allowlist **53** / runtime-authz **33**。現在は **54** / **35**。
   - 不一致 4 資産: `base-allowlist.json`（`4e4f913e...` → `7d6ed18d...`）、`frozen-inputs.json`（`d81604c6...` → `5a71f2f1...`）、`repository-contract.json`（`f9d13ca7...` → `e4198f2d...`）、`runtime-authz-contract.json`（`2525a304...` → `95010dd4...`）。
   - 原因 commit: `19b2e5da`（base 53→54、履歴なし）、`f1386d4a`（runtime 34→35、履歴なし）、`7a30f8c9`（repository 60件化、revision 39 のまま）、`2d2db963`（frozen-inputs external_files 変更、revision 18 のまま）、`9cac3b8a`（allowed_symbols 変更、bump なし）。
2. **native5 固定原典／registry 60件化**（7件）
   - pin `stats_native_registry_reference_revision=b5669d3f...`。現行 `operation_registry.py` / `stats_native_operations.py` / `stats_function_codec.py` が pin と不一致。
   - `repository-contract.json` の `product_function_operation_ids` は 60件で現行と一致。テストは旧 22/27 前提のまま（`test_registry_native_tuple_current_exact27` など）。
3. **initial population proof / census 固定原典**（3件）
   - `product_function_acl.py` の `_GENERATION_GUARD_SQL` が `_INITIAL_POPULATION_POLICY` の固定行 177/2614 と一致せず、`_initial_population_evidence` が空集合を返す。
4. **テスト側メタデータ drift**（1失敗 + 2 errors）
   - `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/games_archive.py` が `current_only` に無い（`19b2e5da` で追加済み）。1行追加で解消。
   - `function_name in {"check_current_right", "check_ordinary_right"}` の literal が現行 `function_operations.py:1083-1084` と不一致。
5. **未顕在の次ゲート**
   - deployment asset digest stale（ledger manifest、writer-binding 4/4）。
   - checker の `ast.Delete` flow 解析 bug（`stats_native_flush.py:467:31` の `del _UNDO_STATS_ISSUED[id(state)]`）。

## 最小修復順序

1. **PR197 facts pin の決着**（最大レバレッジ）。`batters_faced` を正式採用するなら新固定 Git revision・fixture・`pr197_source_revision` / `pr197_expectation_revision` / `pr197_expectation_fixture_sha256` / `pr197_generated_facts_sha256` を再固定し、`frozen_history` の trust root を更新する 7.7 受理を行う。採用しないなら固定 source の公式 generator で `facts.py` を再生成して `7673b596...` へ戻す（BF 指標は消える）。
2. **source・checker・テスト候補の修正**（native5 60件 profile、initial population proof、fixture 1行、builder literal、`ast.Delete` flow、deployment digest 再pin）。
3. **7.7 受理を1回に集約**。base-allowlist / runtime / repository / frozen-inputs の現在射影を再計算し、`history-snapshots` へ追加、authority history へ v2 record を1件追記。非作者レビュー・承認を受ける。
4. **検証**: `test_check_tenant_boundary_bypass.py`、`test_census_baseline_check.py`、`test_frozen_archive*.py`、`check_frozen_baselines.py --ci`、`check_tenant_boundary_bypass.py --base-ref origin/develop`、`rederive_tenant_generated_modules.py --check`。

## 機械的再生成でよいもの / 7.7 新規受理が必要なもの

- 機械的: `rederive_tenant_generated_modules.py`、`frozen_projection_content` の再計算、`history-snapshots` 追加、deployment asset SHA 再pin、fixture/literal 追随。
- 7.7 新規受理: PR197 facts pin・fixture・trust root、4 資産の history/revision/snapshot/承認、native5 profile の checker 適合、initial population proof、checker の `ast.Delete` 修正、旧 22/27 テストの再構成。
- 設計判断: `batters_faced` の正式採用、旧 4 hash pin の扱い、旧 22件 profile を固定歴史 snapshot で維持するか現行 60件へ置き換えるか。
