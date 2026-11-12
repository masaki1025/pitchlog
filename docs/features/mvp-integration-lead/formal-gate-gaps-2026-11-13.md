# 正式ゲートの未達（2026-11-13）

この文書は、統合候補 `feature/mvp-integration-20261109` の**機能証拠**と**正式受理**を混同しないための台帳である。ここに挙げた赤は、機能の不具合と限らず、7.7 の凍結基準・受理履歴が統合ブランチの変更へ追随していないことを含む。

## 1. tenant-boundary 7.7

- `contracts/tenant_boundary/base-allowlist.json` は `contract_revision:54` のまま。
- `tests/test_check_tenant_boundary_bypass.py` は単一ファイルで **570 failed / 1237 passed / 2 errors**（2026-11-13 03:00 JST 時点）。
- 代表的な赤:
  - `test_fixed_function_surface_matches_empty_product_registry`: `native5固定原典を取得/検証できない`。`stats_native_registry` / `stats_native_operations` / `stats_function_codec` の現行byteが固定原典 `b5669d3f...` の射影と一致しない。
  - `test_tenant_repository_product_definition_passes_bypass_scan`
  - `test_census_implementation_movement_requires_record_and_identifier_bump`
  - `test_repository_always_supplies_reexport_maps_to_source_change`
- 必要な作業（未実施）:
  1. 7.7-1 に従い、動かした基準の集合を機械可読に宣言する。
  2. 7.7-2 に従い、`baseline_control.history` へ前後識別値・変更内容・理由・承認者・承認日を追記する（追記のみ）。
  3. `frozen-inputs.json` の固定原典・射影・external_files の digest を再 pin する。
  4. 非作者レビューと承認を得る。**自己承認・受理済み扱いはしない。**

## 2. repository-contract

- `contracts/tenant_boundary/repository-contract.json` の `contract_revision:39` と、統合ブランチの関数操作registryの間に差分がある。
- 7.7 の受理単位（単一レビュー受理）に合わせ、前後状態・snapshot・承認を揃える必要がある。**未受理。**

## 3. 歴史的射影テスト

- `tests/test_sync_apply_product_supply.py` の3件:
  - `test_batted_extension_rejects_every_other_old_statement[4]`
  - `test_batted_extension_rejects_every_other_old_statement[5]`
  - `test_reapply_keeps_all_other_generated_statements_exact`
- 原因: `catalog_before_revision` / `catalog_after_revision` が現在の `contracts/authz/product/ddl-elements.json` と一致しない。非play通常保存（`f43d88a7`）で `prepare_play_prefix_projection` / `finish_play_prefix_projection` のSQL本文が意図的に変わったが、旧batted参照fixture（`batted_source_extension_reference_v1.json`）はその変更を含まない。
- 必要な作業（未実施）: 新しい受理点の before/after と batted参照fixtureを同時に固定し、非作者レビューで承認する。**既存期待値を現在値へ緩めるだけの修正はしない。**

## 4. 解消済み（この候補内）

- `test_batted_hit_product_declarations.py`: 意図的SQL変更へ `PRESERVED_FUNCTION_BODIES` と `adopted_prepare_body_sha256` を追随して通過。
- `test_batted_hit_storage_boundaries.py`: `finish` / `guard` / `old_v2_prepare` の固定値を追随して通過。
- `test_sync_apply_product_supply.py`: native5/guard/count/volatility/result-type の固定値を追随し、上記3件を除いて通過。
- ACK喪失E2E・55プレイE2E・終了再開の機能assertは通過。同期1回7920msの5秒性能assertは未達。

## 5. 未実施の受入

- 実機操作、本番TLS、バックアップ復旧、運用公開。
- 3試合×記録1端末＋閲覧10端末の実測（別担当）。
- 最終HEADの独立レビュー再実行（今回は `88652997` をレビューし、P1/P2を是正した。是正後HEAD `dd2a999f` 以降の再レビューは未実施）。
