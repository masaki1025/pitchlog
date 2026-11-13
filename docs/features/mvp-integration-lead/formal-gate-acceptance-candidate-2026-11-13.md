# 7.7 正式受理候補（2026-11-13）

**状態: 独立レビュー待ち。自己承認・受理済み扱いはしない。**

対象: `feature/mvp-formal-repin-20261113` HEAD `446ff9dad73e141474232e31a5829d6d879a05eb`。
根拠: `docs/features/mvp-integration-lead/formal-gate-root-cause-2026-11-13.md`（`12047cad` 時点の実測）
および本ブランチでの再実測。機械可読な候補は
`docs/features/mvp-integration-lead/formal-gate-acceptance-candidate-2026-11-13.json`。

## 1. 残っている赤の原因

`tests/test_check_tenant_boundary_bypass.py` の大量赤は
`pr197_generated_facts_sha256` の pin 不一致を共通原因とする。

| 項目 | 旧固定値 | 現行値 |
| --- | --- | --- |
| `pr197_generated_facts_sha256` | `7673b5969d6ce3104b48d4f94f217c6b4a44ef1b9b08d06ebaeee935648497d4` | `d39e5caf86a44bd8a52bc9b7cdb61f4707376aac9b797de36530abd5fb3e9e9f` |
| 固定 facts 原典 | `a59c654e... : backend/src/pitchlog/stats/generated/facts.py` | 現木（`batters_faced` 追加済み） |
| `pr197_source_revision` | `a59c654e3366d2be9c6456e47b07118e1674bce2` | 現木と 14/15 owner path が不一致 |

**SHA だけの差し替えは不可。** `scripts/frozen_history.py:read_original_pr197_pin` が
origin commit `2fa42d653e44bba8586c0afe831421402247fd30` の旧 source 行と照合して拒否する。
旧 trust root・旧 fixture・旧 history を書き換えず、後継の独立再導出を 1 件の受理として置く。

本ブランチで再測定した 15 owner path のうち、`a59c654e` と現木が一致しないもの:

```
backend/src/pitchlog/db/current_product_startup.py
backend/src/pitchlog/db/game_state/stats.py
backend/src/pitchlog/domaincheck/runners/stats_native.py
backend/src/pitchlog/exports/generated/play_primitives.sql
backend/src/pitchlog/repositories/stats_function_codec.py
backend/src/pitchlog/repositories/stats_native_operations.py
backend/src/pitchlog/repositories/transaction.py
backend/src/pitchlog/stats/facts.py
backend/src/pitchlog/stats/generated/stats.sql
backend/src/pitchlog/stats/generated/stats_rates.sql
backend/src/pitchlog/sync/native_ledger_insert.py
backend/src/pitchlog/sync/ordinary_pitch_execution.py
backend/src/pitchlog/sync/stats_native_flush.py
backend/src/pitchlog/sync/stats_native_hook.py
```

`446ff9da` の tree は上記 15 path すべてで現木と byte 一致する（測定済み）。
したがって **target source revision は `446ff9da`** とし、`pr197_source_revision` の後継値にする。
最終受理時は、受理対象 HEAD が動いた場合に同じ 15 path の全 byte 一致を再確認する。

## 2. 受理候補の固定値

### 2.1 PR197

- `pr197_source_revision`: `446ff9dad73e141474232e31a5829d6d879a05eb`
- `pr197_generated_facts_sha256`: `d39e5caf86a44bd8a52bc9b7cdb61f4707376aac9b797de36530abd5fb3e9e9f`
- `pr197_expectation_revision`: **未確定**。fixture を独立再導出した commit を受理時に固定する。
- `pr197_expectation_fixture_sha256`: **未確定**。現行 fixture は
  `tests/fixtures/pr197_tenant_source_expected_v1.json`
  （現 revision `42bda907cb54355552f4022ccf948cca7995617c`、SHA-256
  `a14381644954dc8bf918c574810e49656f8e01ee3e21ef64c13955984a037ab4`）。
  後継 fixture では次を更新し、非作者が独立再導出する。
  - `facts_generated_sha256` → `d39e5caf...`
  - `owners[*].source_sha256` → `446ff9da` tree の実 byte
  - `independent_sites_sha256` / `preexec_review_sha256` → 再導出値
- `pr197_pin_origin_commit`: 旧 `2fa42d65...` を**書き換えない**。後継 origin を別 record として追加する。

### 2.2 4 資産の snapshot

`asset_snapshots` の SHA は `frozen_projection_content()` の正規化 JSON byte の SHA-256。
`before` は本ブランチの現行値、`after` は revision 繰り上げと PR197 後継 pin だけを適用した機械的候補。
fixture 後継値の確定後に `after` を再計算する。

| 資産 | 現 revision | 現 snapshot | 候補 revision | 候補 snapshot |
| --- | --- | --- | --- | --- |
| `base-allowlist.json` | 54 | `1c8253d785a52bb9795bbcb56aa172234b98d2d35e786a7ed65ad49d8ea4d10b` | 55 | `61c0a7294b339d6217c9b41637f467af2106c22b0940432698db5d6ff9817405` |
| `runtime-authz-contract.json` | 35 | `d892a3f506b183e1f2573187f247d43ba0f4100bab29a82a94ab6ab5c18a4a82` | 36 | `6311e8041c40b1e1d1d45f6ac819feb6f3b7ccebf7ce795c1146190901d4993c` |
| `repository-contract.json` | 39 | `2f2b463770a265cafb445a3399270d50eee1c5e7383077f923572709b85a4b7b` | 40 | `e9a7a8196d5d5c36075b0507a43bed506f57f5ec12bec4ee8cb1980cab1d4d78` |
| `frozen-inputs.json` | 18 | `ab85a0f734d41f90af54cc2389f3b163c5a6e960519cf6b2282e944f61c97a04` | 19 | `1f18a5f55f66600912d943ee8dd7771b1db97665d0c695631de514ca3da5ce4b` |

受理時は上記 `after` の各 snapshot を
`contracts/tenant_boundary/history-snapshots/<sha256>` へ追加し（追記のみ）、
`change.after.asset_snapshots` の `snapshot_ref` を同じ値へ向ける。
`before` 側の snapshot は既存履歴に存在しない場合だけ追加する。

## 3. 正確な history record

`base-allowlist.json` の `baseline_control.history` へ **1 件だけ追記**する。
record の完全な `change.before` / `change.after`（全 9 資産の declaration・movement_policy・
asset_snapshots・external_snapshots）は候補 JSON の `history_record` に固定した。
非導出値は次のとおり。

```json
{
  "record_schema_version": 2,
  "acceptance_id": "受理時に採番（owner/repository#number）",
  "new_baseline_identifiers": {
    "contracts/tenant_boundary/base-allowlist.json": "contract_revision:55",
    "contracts/tenant_boundary/runtime-authz-contract.json": "runtime_contract_revision:36",
    "contracts/tenant_boundary/repository-contract.json": "contract_revision:40",
    "contracts/tenant_boundary/frozen-inputs.json": "contract_revision:19"
  },
  "previous_baseline_identifiers": {
    "contracts/tenant_boundary/base-allowlist.json": "contract_revision:54",
    "contracts/tenant_boundary/runtime-authz-contract.json": "runtime_contract_revision:35",
    "contracts/tenant_boundary/repository-contract.json": "contract_revision:39",
    "contracts/tenant_boundary/frozen-inputs.json": "contract_revision:18"
  },
  "change": {
    "subject": "PR197 facts/source successorと4資産の正式再pin",
    "aspect": ["asset_snapshots"],
    "before": "候補JSONの history_record.change.before（現行9資産の完全射影）",
    "after": "候補JSONの history_record.change.after（候補9資産の完全射影）"
  },
  "movement_fact": "PR197固定source a59cと現行15 owner pathのうち14 pathが不一致で、facts.pyもbatters_faced追加により7673b596からd39e5cafへ移動した。旧trust rootを書き換えず、独立再導出したfixtureと4資産の単一受理で新しい基線を置く。",
  "reason": "現行artifact/製品sourceをPR197の旧固定値へ戻すと採用済みbatters_facedとstats sourceが失われるため、後継受理を一件に集約する。",
  "approved_by": "非作者レビュー承認者（受理時に記入）",
  "approved_on": "受理日（YYYY-MM-DD、受理時に記入）"
}
```

`approved_by` / `approved_on` は**空欄のまま受理済みにしない**。
候補 JSON では `PENDING_INDEPENDENT_REVIEW` と明示している。

## 4. 受理前に必要な独立作業

1. 後継 fixture の独立再導出（`facts_generated_sha256`、15 owner path の `source_sha256`、
   `independent_sites_sha256`、`preexec_review_sha256`）。作者の現木値で自己生成しない。
2. 後継 `pr197_expectation_revision` / `pr197_expectation_fixture_sha256` の固定。
3. 4 資産の revision 繰り上げ、`history-snapshots` 追記、history record 1 件追記。
4. `approved_by` / `approved_on` を非作者レビューで記入。
5. 受理後に `test_check_tenant_boundary_bypass.py`、`test_census_baseline_check.py`、
   `test_frozen_archive*.py`、`check_frozen_baselines.py --ci`、
   `check_tenant_boundary_bypass.py --base-ref origin/develop` を再実行する。

旧 PR197 trust root・旧 fixture・旧 history・旧 snapshot は変更しない。
SHA だけの差し替え、期待値の緩和、自己承認は行わない。

## 5. 本ブランチで行った機械的修正（受理不要）

- `tests/test_check_tenant_boundary_bypass.py`: 正例 tree の `current_only` へ
  `tests/fixtures/tenant_boundary/positive/pitchlog/repositories/games_archive.py` を追加。
- `scripts/check_tenant_boundary_bypass.py`:
  - `_FIXED_PLAY_PREFIX_BUILDER_BODY` を現行 `function_operations.py` の
    `check_p3_right` / `_VIEWER_FUNCTION_TYPES` / `read_p3_current` を含む完全形へ追随。
  - `ast.Delete` の Attribute/Subscript 対象式も評価し、`del mapping[id(state)]` の
    Call 被覆欠落を修正（`stats_native_flush.py:467`）。
- これらは受理値を緩めず、現行 source との機械的突合を回復するだけである。
  正式 7.7 の再 pin は本候補の独立レビュー後に別途行う。

## 6. 製品資産の追随結果（2026-11-13 追補）

- `contracts/authz/product/ddl-elements.json` へ `first_ball_product.ADDITIONS` の
  完全行 5 件（table 1、policy 2、function 1、ACL 1）を追加した。手書き SQL の重複はない。
- 公式 renderer の本文を `contracts/authz/product/function-bodies/functions|tables|policies|acl_expectations`
  と `manifest.json` へ追加し、既存 4 関数の本文も現行 `nonplay_prefix_read_sql.py` /
  `first_ball_product.BODIES` へ追随した。`check_authz_function_bodies.validate_repository(PRODUCT_SPEC)`
  は 0 findings。
- `repository-contract.json` と生成 `repository_contract.py` は
  `SYNC_NONPLAY:consume_nonplay_tiebreak_start` を 1 件追加した（60→61）。
  revision/history/snapshot は本 7.7 受理候補側で再導出し、自己承認しない。
- migration の revision id は `alembic_version.version_num varchar(32)` 制約に収めるため
  `0051_tiebreak_start_receipt` とした（ファイル名は `0051_tiebreak_start_write_receipt.py` のまま）。
  `0050_play_export_p3_snapshots` の子として migration chain に含まれる。
- `tests/db/test_substitution_vertical_http.py` は setup を含め **1 passed**（2026-11-13 実測）。
  製品資産・migration・function body の exact 集合が揃ったことを確認した。
- 残る `test_sync_apply_product_supply.py` の 5 件は、追加 5 行を含む
  generated statement の件数/reference fixture を新しい受理点へ再固定するまで赤。
  検査条件を緩めず、`batted_source_extension_reference_v1.json` の後継受理で解消する。
- A branch の新 artifact `961844ed...` に合わせ、v7（`bb6768ea...`）は保持したまま
  v8 witness/registry を追加した。v7 を書き換えず、v8 が `bb6768ea...` と
  `961844ed...` の有限 pair を閉登録する。
