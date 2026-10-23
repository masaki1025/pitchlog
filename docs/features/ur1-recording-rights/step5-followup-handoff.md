# U-R1 新5 後続PRの引継ぎ（番号取得段階）

## 基線と保全

- 基線は `origin/develop` の `7717b98686395b2c0db9d545a5effa06888885ff`。#170 は同SHAで計画・作業ログの2ファイルだけを統合した。製品実装の完了とは扱わない。
- #172 の統合SHA `8a43d044052b6a343b3b90b0120d149898ac8f6c` は基線の祖先。`base-allowlist.json` の既受理履歴は25件で、末尾は `masaki1025/pitchlog#172`。後続候補は25件とそのbefore値を保持して再導出する。
- 旧#156の公開ブランチ `feature/ur1-initial-rights`（公開HEAD `73ebf8ee`）、正式受理記録、承認・レビュー資料、ローカル是正HEAD `92c5b9ec` を保全する。旧PRは引継ぎ公開まで開いたままにする。
- 旧#170の公開ブランチは `b3efd492` の番号取得用文書のみ。旧承認値を新PRの受理に流用しない。旧ローカル候補は `feature/ur1-initial-rights-replacement` のworktreeに保全し、最後に確認したローカルHEADは `d41c8b8b`、未コミット全体のtreeは `d9e511736c40a8c566aa1a1922582df9b925cf6a`。候補の7.7資料は同worktreeの `step5-pr170-7.7-fixture-*` に残す。

## 移植する未統合差分

番号取得時点では、以下を**まだ公開しない**。基線の差分から再導出し、正式受理・必要レビューのゲートを満たしてから公開する。

| 区分 | 対象 | 残条件 |
| --- | --- | --- |
| 製品候補 | `backend/src/pitchlog/recording_rights/`、`authz/runtime_contract.py`、`repositories/repository_contract.py`、`repositories/tenant_context_contract.py` | 実台帳・端末資格・鍵・実Portは未接続。隔離候補を完成証跡にしない |
| 試験候補 | `backend/tests/test_initial_recording_right_candidate.py`、`tests/test_census_baseline_check.py`、`tests/fixtures/tenant_boundary/census-scoped-digests.json` と直接影響試験 | digest 2値のexact照合、欠損・改変・余剰・不正形式の拒否、旧checker43件・独立AST18件と範囲外負例を保持 |
| 認可・凍結候補 | U-R1に必要なtenant-boundary 9資産、`scripts/check_tenant_boundary_bypass.py`、corpus宣言・snapshot・単一受理記録 | #172の25件目を保持。新PR番号の正式7.7完全値を再導出して人間受理まで正式履歴へ書かない |
| コア経路 | `scripts/core_guard.py` → `.claude/core-areas.json` の宣言・登録と試験 | 宣言→登録のコミット順と人間逐行確認を維持 |
| 設計・説明 | U-R1新5の計画、接続契約、候補差分、作業ログ | 担当未受理事項、旧レビュー対象と後発未再レビュー差分を区別 |

## #162 との共有パス

#162 は `760c04d540b22190cab076165f1b4e35ae473a1f` で統合され、後続枝は `6af8c801` で取り込んだ。`docs/design/data-model.md`、`contracts/db/schema-manifest.json`、`contracts/authz/shared-preconditions.json`、ORM受理シート、`tests/test_orm_acceptance_sheets.py` の #162 内容を保持する。旧worktree値を上書きせず、U-R1分は実統合後のdevelopから必要な変更だけを再導出する。U-R1専有の製品・census候補は独立して進める。

## 公開・受理の境界

この文書と番号取得用のPR本文だけでは引継ぎ完了でも製品実装完了でもない。新番号確定後、#172を含む基線からfixture是正込みの9資産の完全な前後値、snapshot、corpus、単一記録案と各SHAを提示する。旧#156/#170承認の自動延長はしない。必要な独立レビューと正式7.7受理後に製品・試験・正式資産を公開し、全CIと本人逐行確認の対象を確認する。旧#156は必要な差分と未決事項の公開引継ぎを確認してから閉じる。
