# 全harness初回10失敗の原因・担当・受理条件

初回: `/tmp/t2-reserved-full-harness.log`、29,709 passed/10 failed/2 skipped、514.88秒。
比較元origin/develop=`156dd139`。承認済みdevelopを`76037523`で通常mergeし、先行の受理履歴を保持した。検査基準の弱化や履歴の削除/置換はしていない。

| 失敗したtest（ファイル/関数） | 原因 | 修正/対応担当 | 正式受理待ちか・再検証 |
| --- | --- | --- | --- |
| test_core_guard.py / test_actual_core_area_paths_follow_merge_base_layers | 旧枝のpathsと最新develop基線の二層契約不一致 | 本Codexが承認済みdevelopを取り込む | この失敗のための新規受理は不要。既存承認/受理を継承し影響試験合格 |
| 同 / test_product_rls_paths_remain_in_develop_baseline | 同上 | 同上 | 同上 |
| 同 / test_uf8_game_screen_paths_are_registered_in_all_areas | 同上 | 同上 | 同上 |
| 同 / test_us1_sync_apply_paths_are_registered_in_both_areas | 同上。RG1等の追加9pathsが旧枝に欠落 | 同上 | 同上 |
| 同 / test_uf5_team_paths_are_registered_for_tenant_and_migration | 二層paths不一致 | 同上 | 同上 |
| 同 / test_area_registration | paths集合と宣言済み追加層の不一致 | 同上 | 同上 |
| test_check_tenant_boundary_bypass.py / test_repository_is_green | 最新developのbase-allowlist先行受理履歴が旧枝に無く、prefix保持検査に失敗 | 本Codexが先行履歴を保持してdevelop取り込み | 新規受理を捏造しない。取り込み後の履歴検査合格 |
| tests/domain/mut/test_lang_operators.py / test_each_language_mutants_are_actually_killed[sql] | 127.0.0.1:5432のDB接続拒否 | 本Codexが専用一時DBで検証 | 受理待ちではなく検証環境の問題。SQL変異を実PostgreSQLで再実行して合格 |
| tests/domain/mut/test_cost_record.py / test_actual_measurement_is_generated_and_passes_both_budgets | 子測定スイートexit=1。初回の捕捉出力だけではSQLへの帰属を断定できなかった | 本Codexが同一スイートを専用DBで再実行 | ソース/予算を変えず再実行合格。新しい測定結果を正式な過去資産へ追記したわけではない |
| test_human_review_signature.py / test_repository_gate6_signature_records_match_current_contracts | provenance追加後のT2 digestと旧署名が不一致 | 実際の人間確認者が対象版を確認・明示再署名し、契約所有側が内容を記録 | **明示再署名待ち**。自分やP-6検証者の実施を推定転記しない。予定失敗を隠さない |

影響試験:

- core-guardの上記6件+tenant履歴1件 = **7 passed**（3.44秒）。
- 専用DBは既存ローカルimage `postgres:17.11-bookworm`、container `pitchlog-t2-p8-harness-ca1c5df4`、一時DB `t2_harness`、localhost割当port36411、データは専用tmpfs。共有DB/ロール/秘密情報は使わない。SQL変異+費用測定 = **2 passed**（4.53秒）、ログ `/tmp/t2-p8-sql-cost-impact.log`。
- DSNは専用の認証不要テストDBだけを指し、子測定スイートにも引き継ぐ。実スイートが両予算内に入ることを既存testが検査し、上限・失敗条件は変更しない。

残る正式受理は、今回候補を正式契約へ反映する7.7、正本の確定、P-6、担当受理、署名で別管理する。これらを上の9件の環境/取込み是正と混同しない。
