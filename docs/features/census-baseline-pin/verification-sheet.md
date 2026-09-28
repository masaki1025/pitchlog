<!-- このファイルは generate_verification_sheet.py が機械生成する。手編集しない。 -->
# census baseline pin 人間逐行確認シート

生成コマンド: `uv run python docs/features/census-baseline-pin/generate_verification_sheet.py`

## 見る順序

1. **A** で基準を新設する裁定と 7.7 の適用を判断する。
2. **C** で件数を捨てて述語にした合否写像の十分性を判断する。
3. **B** で宣言アンカーから比較元が一意に組み上がる実測を突合する。
4. **D** で fail-closed・退行・両方向結線の変異がすべて赤になる証跡を確認する。

## 機械と人間の境界

- **機械**: 宣言値の再計算と、壊した入力が赤・復元後がgreenになる pytest を実行する。
- **人間**: AとCを中心に、基準の新設・NO_BASELINE・述語の選択が設計として妥当かを判断する。
- Cの変異テストは実装どおり動くことを機械確認するが、述語が必要十分かの最終判断は人間に残す。

## 集計

- 判定項目総数: **30**
- 機械が担保する項目: **17**
- 人間が判断する項目: **13**
- 生成時に実行して全件PASSEDを要求した pytest node: **23**

## A. 基準を新設する判断と 7.7 の手続

### A-1 [人間] 可変参照を census の基準にしない判断

- **アンカー**: [`docs/features/census-baseline-pin/plan.md:32`](plan.md#L32) / [`tests/test_census_baseline_check.py:302`](../../../tests/test_census_baseline_check.py#L302)
- **実測値**: 現行 materialize 内の可変参照出現数={'origin/develop': 0, 'merge-base': 0}; 宣言 resolution=direct_full_commit_sha; 正例 pytest=PASSED
- **判定観点**: 比較元と HEAD が合流後に自己比較になる問題を、固定宣言へ移す判断が妥当か。
- **判定**: ☐ 適合 / ☐ 要修正

### A-2 [人間] 固定 SHA を Python ソースへ戻せない三経路の遮断

- **アンカー**: [`docs/development/dev-harness-design-2026-08-07.md:530`](../../development/dev-harness-design-2026-08-07.md#L530) / [`scripts/check_frozen_baselines.py:1621`](../../../scripts/check_frozen_baselines.py#L1621) / [`tests/test_census_baseline_check.py:225`](../../../tests/test_census_baseline_check.py#L225) / [`tests/test_check_tenant_boundary_bypass.py:2950`](../../../tests/test_check_tenant_boundary_bypass.py#L2950)
- **実測値**: (1) scan roots=['scripts', 'tests', 'backend/tests'], census source hex hits=0; (2) 結線変異=pytest=1/1 PASSED; nodes=['test_implementation_to_declaration_rejects_undeclared_input_and_recovers']; states=['PASSED']; (3) frozen external_files に census module=True, movement mutation=PASSED
- **判定観点**: 走査・宣言外入力拒否・凍結 movement の三経路で直書きへの回帰を十分に防げるか。
- **判定**: ☐ 適合 / ☐ 要修正

### A-3 [人間] 直前値を NO_BASELINE とする第8周再裁定

- **アンカー**: [`docs/worklog/2026-09-26-census-baseline-pin.md:121`](../../worklog/2026-09-26-census-baseline-pin.md#L121) / [`docs/features/census-baseline-pin/plan.md:288`](plan.md#L288) / [`scripts/frozen_history.py:538`](../../../scripts/frozen_history.py#L538)
- **実測値**: 分岐点で census 資産存在=False; 旧テスト内の固定40/64 hex=0; 可変参照出現=1; 機構の基準不在 marker=NO_BASELINE
- **判定観点**: 識別値が置かれていない相対比較を、既存の凍結基準と数えない裁定が7.7-2に適合するか。
- **判定**: ☐ 適合 / ☐ 要修正

### A-4 [人間] 7.7-1 宣言の外出し

- **アンカー**: [`docs/development/dev-harness-design-2026-08-07.md:525`](../../development/dev-harness-design-2026-08-07.md#L525) / [`contracts/tenant_boundary/census-baseline.json:46`](../../../contracts/tenant_boundary/census-baseline.json#L46) / [`tests/test_census_baseline_check.py:186`](../../../tests/test_census_baseline_check.py#L186)
- **実測値**: 宣言 anchor/resolution={'commit': 'b4ae7394a6ca038c8ea90ad9ddea40e00165ba7b', 'resolution': 'direct_full_commit_sha'}; Python source の40/64 hex=0
- **判定観点**: 基準値を資産宣言だけに置き、実装はロケータとschema keyだけを持つ境界が妥当か。
- **判定**: ☐ 適合 / ☐ 要修正

### A-5 [人間] 7.7-2 更新記録を最終ステップへ送る手続

- **アンカー**: [`docs/development/dev-harness-design-2026-08-07.md:581`](../../development/dev-harness-design-2026-08-07.md#L581) / [`contracts/tenant_boundary/census-baseline.json:43`](../../../contracts/tenant_boundary/census-baseline.json#L43) / [`docs/features/census-baseline-pin/plan.md:483`](plan.md#L483)
- **実測値**: census history件数=0; history_authority=False; authority assets=['contracts/tenant_boundary/base-allowlist.json']; acceptance_unit=single_review_acceptance
- **判定観点**: 凍結対象が確定するステップ10でauthorityへ1記録を書く順序と受理単位が妥当か。
- **判定**: ☐ 適合 / ☐ 要修正

### A-6 [人間] 7.7-3 fail-closed の満たし方

- **アンカー**: [`docs/development/dev-harness-design-2026-08-07.md:607`](../../development/dev-harness-design-2026-08-07.md#L607) / [`tests/test_census_baseline_check.py:1919`](../../../tests/test_census_baseline_check.py#L1919)
- **実測値**: fail-closed 8分類=8/8 PASSED; pytest nodes=9
- **判定観点**: 確認不能をskip・中立・合格にせず不合格にする境界が十分か。
- **判定**: ☐ 適合 / ☐ 要修正

## B. 比較元の組み立て

### B-1 [機械] 宣言アンカーからの tree materialize と digest 突合

- **アンカー**: [`contracts/tenant_boundary/census-baseline.json:50`](../../../contracts/tenant_boundary/census-baseline.json#L50) / [`tests/test_census_baseline_check.py:302`](../../../tests/test_census_baseline_check.py#L302)
- **実測値**: anchor=b4ae7394a6ca038c8ea90ad9ddea40e00165ba7b; paths=['contracts/tenant_boundary', 'tests/fixtures/tenant_boundary', 'scripts/check_tenant_boundary_bypass.py', 'scripts/frozen_history.py']; files declared/actual=129/129; digest declared/actual=214a708144881fede3ec914a9cbcb767cbfae0fe030a5197c6f47bc83b9c895a/214a708144881fede3ec914a9cbcb767cbfae0fe030a5197c6f47bc83b9c895a; mutations=pytest=3/3 PASSED; nodes=['test_fail_closed_rejects_declaration_mutation_and_recovers[unresolved-anchor]', 'test_fail_closed_rejects_declaration_mutation_and_recovers[tree-digest-mismatch]', 'test_fail_closed_rejects_declaration_mutation_and_recovers[file-count-mismatch]']; states=['PASSED', 'PASSED', 'PASSED']
- **判定観点**: 宣言値とGit由来の実測値が一致し、3変異が赤から復元greenになっているか。
- **判定**: ☐ 適合 / ☐ 要修正

### B-2 [機械] 受理記録の checker・helper snapshot との相互検査

- **アンカー**: [`contracts/tenant_boundary/census-baseline.json:64`](../../../contracts/tenant_boundary/census-baseline.json#L64) / [`tests/test_census_baseline_check.py:381`](../../../tests/test_census_baseline_check.py#L381)
- **実測値**: acceptance_id=masaki1025/pitchlog#80; matching_records=1; verified_sha256={'scripts/check_tenant_boundary_bypass.py': '4e4c22633db5765fc8c5bf0ae7e4969dc1d9742c8035e0ced8bbb61940aed878', 'scripts/frozen_history.py': '0bd319d2118948d288d338bc80dcb3885d0ee5834f7dea6d9d0ef33ecb5d40e8'}; mutations=pytest=3/3 PASSED; nodes=['test_fail_closed_rejects_declaration_mutation_and_recovers[acceptance-record-not-found]', 'test_fail_closed_rejects_nonunique_acceptance_record_and_recovers', 'test_fail_closed_rejects_acceptance_digest_mismatch_and_recovers']; states=['PASSED', 'PASSED', 'PASSED']
- **判定観点**: 受理記録が一意で、別経路の2ファイルdigestが一致し、不在・重複・不一致を拒否するか。
- **判定**: ☐ 適合 / ☐ 要修正

### B-3 [機械] 旧 checker と旧 helper の隔離ロード

- **アンカー**: [`tests/test_census_baseline_check.py:449`](../../../tests/test_census_baseline_check.py#L449) / [`tests/test_census_baseline_check.py:2051`](../../../tests/test_census_baseline_check.py#L2051)
- **実測値**: checker=<materialized-root>/scripts/check_tenant_boundary_bypass.py; helper=<materialized-root>/scripts/frozen_history.py; current scripts 使用=False; mutation=pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_module_cache_contamination_and_recovers']; states=['PASSED']
- **判定観点**: 両moduleがmaterialize先配下だけからロードされ、cache混入を拒否するか。
- **判定**: ☐ 適合 / ☐ 要修正

## C. 合否写像を述語にした判断

### C-1 [人間] 製品コードで動く件数を基準値にしない判断

- **アンカー**: [`docs/features/census-baseline-pin/plan.md:171`](plan.md#L171) / [`contracts/tenant_boundary/census-baseline.json:83`](../../../contracts/tenant_boundary/census-baseline.json#L83)
- **実測値**: declared predicates=5; pass_fail_mapping の count 系 key=[]
- **判定観点**: 現行backend/srcの変化で動く件数を捨て、安定した述語へ置き換える判断が妥当か。
- **判定**: ☐ 適合 / ☐ 要修正

### C-2 [人間] 述語 `difference_codes_within_allowed_set` の拘束

- **アンカー**: [`contracts/tenant_boundary/census-baseline.json:86`](../../../contracts/tenant_boundary/census-baseline.json#L86) / [`tests/test_census_baseline_check.py:1242`](../../../tests/test_census_baseline_check.py#L1242) / [`tests/test_census_baseline_check.py:1746`](../../../tests/test_census_baseline_check.py#L1746)
- **実測値**: 宣言=sets=['added', 'removed'] の code を allowed_codes=['TB002', 'TB007'] に包含; mutation=PASSED→正入力復元PASSED
- **判定観点**: 宣言された拘束が必要十分で、将来の製品コード変更を件数で縛らないか。
- **判定**: ☐ 適合 / ☐ 要修正

### C-3 [人間] 述語 `removed_tb007_matches_declared_relaxations` の拘束

- **アンカー**: [`contracts/tenant_boundary/census-baseline.json:97`](../../../contracts/tenant_boundary/census-baseline.json#L97) / [`tests/test_census_baseline_check.py:1269`](../../../tests/test_census_baseline_check.py#L1269) / [`tests/test_census_baseline_check.py:1746`](../../../tests/test_census_baseline_check.py#L1746)
- **実測値**: 宣言=removed の TB007 を quantifier=every で matches_declared_relaxation; mutation=PASSED→正入力復元PASSED
- **判定観点**: 宣言された拘束が必要十分で、将来の製品コード変更を件数で縛らないか。
- **判定**: ☐ 適合 / ☐ 要修正

### C-4 [人間] 述語 `unadjudicated_removed_tb002_remains_in_current_census` の拘束

- **アンカー**: [`contracts/tenant_boundary/census-baseline.json:104`](../../../contracts/tenant_boundary/census-baseline.json#L104) / [`tests/test_census_baseline_check.py:1298`](../../../tests/test_census_baseline_check.py#L1298) / [`tests/test_census_baseline_check.py:1746`](../../../tests/test_census_baseline_check.py#L1746)
- **実測値**: 宣言=removed の TB002 の非裁定要素を current_census の TB002 と match_fields=['path', 'line', 'code'] で照合; mutation=PASSED→正入力復元PASSED
- **判定観点**: 宣言された拘束が必要十分で、将来の製品コード変更を件数で縛らないか。
- **判定**: ☐ 適合 / ☐ 要修正

### C-5 [人間] 述語 `added_equals_independently_derived_condition_2_candidates` の拘束

- **アンカー**: [`contracts/tenant_boundary/census-baseline.json:120`](../../../contracts/tenant_boundary/census-baseline.json#L120) / [`tests/test_census_baseline_check.py:1392`](../../../tests/test_census_baseline_check.py#L1392) / [`tests/test_census_baseline_check.py:1746`](../../../tests/test_census_baseline_check.py#L1746)
- **実測値**: 宣言=added を relation=exact_set_equality、source=current_backend_src_ast、AST=Name、filters=['matches_current_condition_2_contract', 'does_not_match_anchor_condition_2_contract'] で拘束し、derivation=candidate_checker_census を禁止; mutation=PASSED→正入力復元PASSED
- **判定観点**: 宣言された拘束が必要十分で、将来の製品コード変更を件数で縛らないか。
- **判定**: ☐ 適合 / ☐ 要修正

### C-6 [人間] 述語 `difference_sets_are_nonempty` の拘束

- **アンカー**: [`contracts/tenant_boundary/census-baseline.json:141`](../../../contracts/tenant_boundary/census-baseline.json#L141) / [`tests/test_census_baseline_check.py:1432`](../../../tests/test_census_baseline_check.py#L1432) / [`tests/test_census_baseline_check.py:1746`](../../../tests/test_census_baseline_check.py#L1746)
- **実測値**: 宣言=nonempty_sets=['added', 'removed'] を要求; mutation=PASSED→正入力復元PASSED
- **判定観点**: 宣言された拘束が必要十分で、将来の製品コード変更を件数で縛らないか。
- **判定**: ☐ 適合 / ☐ 要修正

### C-7 [人間] 述語4の右辺を candidate checker から独立させる判断

- **アンカー**: [`docs/features/census-baseline-pin/plan.md:202`](plan.md#L202) / [`tests/test_census_baseline_check.py:1014`](../../../tests/test_census_baseline_check.py#L1014) / [`tests/test_census_baseline_check.py:1781`](../../../tests/test_census_baseline_check.py#L1781)
- **実測値**: candidate_source=current_backend_src_ast; forbidden_source=candidate_checker_census; candidate omission mutation=PASSED
- **判定観点**: 候補checkerの取りこぼしと同時に期待集合まで縮む循環を断てているか。
- **判定**: ☐ 適合 / ☐ 要修正

## D. fail-closed と退行の実測

### D-01 [機械] fail-closed ① 宣言不在・JSON不正

- **アンカー**: [`tests/test_census_baseline_check.py:1919`](../../../tests/test_census_baseline_check.py#L1919)
- **実測値**: pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_unreadable_declaration_and_recovers']; states=['PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-02 [機械] fail-closed ② 宣言の必須フィールド欠落

- **アンカー**: [`tests/test_census_baseline_check.py:1957`](../../../tests/test_census_baseline_check.py#L1957)
- **実測値**: pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_declaration_mutation_and_recovers[missing-required-field]']; states=['PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-03 [機械] fail-closed ③ アンカー解決不能

- **アンカー**: [`tests/test_census_baseline_check.py:1957`](../../../tests/test_census_baseline_check.py#L1957)
- **実測値**: pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_declaration_mutation_and_recovers[unresolved-anchor]']; states=['PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-04 [機械] fail-closed ④ tree digest 不一致

- **アンカー**: [`tests/test_census_baseline_check.py:1957`](../../../tests/test_census_baseline_check.py#L1957)
- **実測値**: pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_declaration_mutation_and_recovers[tree-digest-mismatch]']; states=['PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-05 [機械] fail-closed ⑤ materialize ファイル数不一致

- **アンカー**: [`tests/test_census_baseline_check.py:1957`](../../../tests/test_census_baseline_check.py#L1957)
- **実測値**: pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_declaration_mutation_and_recovers[file-count-mismatch]']; states=['PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-06 [機械] fail-closed ⑥ 受理記録不在・非一意

- **アンカー**: [`tests/test_census_baseline_check.py:1957`](../../../tests/test_census_baseline_check.py#L1957) / [`tests/test_census_baseline_check.py:1977`](../../../tests/test_census_baseline_check.py#L1977)
- **実測値**: pytest=2/2 PASSED; nodes=['test_fail_closed_rejects_declaration_mutation_and_recovers[acceptance-record-not-found]', 'test_fail_closed_rejects_nonunique_acceptance_record_and_recovers']; states=['PASSED', 'PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-07 [機械] fail-closed ⑦ 受理 snapshot digest 不一致

- **アンカー**: [`tests/test_census_baseline_check.py:2028`](../../../tests/test_census_baseline_check.py#L2028)
- **実測値**: pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_acceptance_digest_mismatch_and_recovers']; states=['PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-08 [機械] fail-closed ⑧ module-cache 混入

- **アンカー**: [`tests/test_census_baseline_check.py:2051`](../../../tests/test_census_baseline_check.py#L2051)
- **実測値**: pytest=1/1 PASSED; nodes=['test_fail_closed_rejects_module_cache_contamination_and_recovers']; states=['PASSED']
- **判定観点**: 変異が赤として捕捉され、復元後greenまで到達しているか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-09 [機械] 退行(a) origin/develop loader

- **アンカー**: [`tests/test_census_baseline_check.py:2088`](../../../tests/test_census_baseline_check.py#L2088)
- **実測値**: pytest=1/1 PASSED; nodes=['test_reference_checker_regressions_are_rejected[origin-develop-loader]']; states=['PASSED']
- **判定観点**: 宣言アンカー以外の比較元へ戻す退行が赤になり、正経路へ戻すとgreenか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-10 [機械] 退行(b) merge-base loader

- **アンカー**: [`tests/test_census_baseline_check.py:2088`](../../../tests/test_census_baseline_check.py#L2088)
- **実測値**: pytest=1/1 PASSED; nodes=['test_reference_checker_regressions_are_rejected[merge-base-loader]']; states=['PASSED']
- **判定観点**: 宣言アンカー以外の比較元へ戻す退行が赤になり、正経路へ戻すとgreenか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-11 [機械] 退行(c) 現行worktree checker

- **アンカー**: [`tests/test_census_baseline_check.py:2088`](../../../tests/test_census_baseline_check.py#L2088)
- **実測値**: pytest=1/1 PASSED; nodes=['test_reference_checker_regressions_are_rejected[current-worktree-checker]']; states=['PASSED']
- **判定観点**: 宣言アンカー以外の比較元へ戻す退行が赤になり、正経路へ戻すとgreenか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-12 [機械] 退行(d) collection時点のGit bytes cache

- **アンカー**: [`tests/test_census_baseline_check.py:2133`](../../../tests/test_census_baseline_check.py#L2133)
- **実測値**: pytest=1/1 PASSED; nodes=['test_reference_regression_rejects_git_bytes_cached_before_monitoring']; states=['PASSED']
- **判定観点**: 宣言アンカー以外の比較元へ戻す退行が赤になり、正経路へ戻すとgreenか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-13 [機械] 結線① 宣言の未使用フィールド

- **アンカー**: [`tests/test_census_baseline_check.py:2197`](../../../tests/test_census_baseline_check.py#L2197)
- **実測値**: pytest=1/1 PASSED; nodes=['test_declaration_to_implementation_rejects_unused_field_and_recovers']; states=['PASSED']
- **判定観点**: 宣言と実装の片方向だけを外す変異が赤になり、復元後greenか。
- **判定**: ☐ 適合 / ☐ 要修正

### D-14 [機械] 結線② 宣言外の実装入力

- **アンカー**: [`tests/test_census_baseline_check.py:2226`](../../../tests/test_census_baseline_check.py#L2226)
- **実測値**: pytest=1/1 PASSED; nodes=['test_implementation_to_declaration_rejects_undeclared_input_and_recovers']; states=['PASSED']
- **判定観点**: 宣言と実装の片方向だけを外す変異が赤になり、復元後greenか。
- **判定**: ☐ 適合 / ☐ 要修正
