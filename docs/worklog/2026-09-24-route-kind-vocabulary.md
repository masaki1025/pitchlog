---
date: 2026-09-24
topic: 製品 CRUD 経路の route_kind 値域を決める(TSK-446)
branch: feature/route-kind-vocabulary
---

# 作業ログ: 2026-09-24 製品 CRUD 経路の route_kind 値域を決める(TSK-446)

## やったこと

- **起票と着手**(/task-start)。`origin/develop` = `bf8ba5b` 起点で worktree を作成。
  **所有者が空席**であることが TSK-393(U-M1)と TSK-344 の計画段階の調査で判明したため、新規に起票した

## 決定

- **射程を「値域と必須キー体系の決定 + 検査器の拡張」に限る**。実際の経路登録は各単位が自 PR で行う
  (`../product-impl-unit-split/plan.md:61` が「`.claude/core-areas.json` への paths 登録は各核単位が自 PR で行う」と定めるのと同じ構え)

## 未決・次の一歩

- /investigate でリポ内調査(**新種別の名前と必須キー体系の根拠をどこから引くか**が中心)→ /plan
- 本タスクは **TSK-424 とも TSK-344 とも独立**。**マージ順序は 本タスク → 入口を開く各単位**

## 実装の経過(2026-09-24 〜 2026-09-25)

### ステップ 2 の期待失敗集合(実出力)

計画書 4 節ステップ 2 が「red の出力を worklog へ実出力つきで残す」ことを求めているが、
着手時に記録を落としていた(**3 周目の敵対レビュー P1-4 の是正**)。
`6b9023e` を detached worktree へ取り出して**再実行した実出力**を以下に残す。

```
$ uv run pytest -c pyproject.toml tests/ -q --no-header
FAILED tests/test_check_authz_catalog.py::test_record_and_aggregate_route_requires_operation_key
FAILED tests/test_check_authz_catalog.py::test_all_route_kind_values_reject_an_unregistered_value
FAILED tests/test_check_authz_catalog.py::test_record_and_aggregate_route_requires_design_origin
FAILED tests/test_check_authz_catalog.py::test_record_and_aggregate_route_id_must_match_operation
FAILED tests/test_check_authz_catalog.py::test_record_and_aggregate_route_requires_dedicated_provenance
FAILED tests/test_check_authz_catalog.py::test_route_kind_tables_reject_missing_mapping_rows
6 failed, 1621 passed in 674.23s (0:11:14)
```

**失敗内容(`--tb=line`)— 6 本すべてが素の `KeyError`**:

```
('operation', "KeyError: 'record_and_aggregate'")
('正常なrecord_and_aggregate', "KeyError: 'record_and_aggregate'")
('requirement_origin', "KeyError: 'record_and_aggregate'")
('operation_mismatch', "KeyError: 'record_and_aggregate'")
('legacy_provenance', "KeyError: 'record_and_aggregate'")
('expected_keys_by_kind', "KeyError: 'unmapped_route_kind'")
```

`expected_keys_by_kind` と `disposition_by_kind` に新種別の行が無いため素の `KeyError` になる。
**ステップ 3 でこれを `CatalogError` へ変える**のが実装の主眼。
**既存テストへの red 増加は 0**(6 failed / 1621 passed)。

### ステップの実施順と、記法の乱れ

コミットは `(ステップ <k>)` トークンで追える。**ただしステップ 1 のコミット `7637afe` は
ステップ 2〜7 の後ろに置かれている**。当初ステップ 1 を「draft PR を作るだけ・コミットを作らない」
としたため `feature_status.py` が番号 1 を欠番と判定し、**後から成果物(PR 番号の記録)を
リポジトリへ残して是正**した経緯による。**設計書 6.1 は番号列を 1 からの連番と定めており、
コミットを伴わないステップを表へ置いたのが計画の誤り**だった。

`(ステップ 3 再)` / `(ステップ 4 再)` / `(ステップ 5 追補)` / `(ステップ 2 再)` は
敵対レビューの反映周である。

### 敵対レビュー 3 周

| 周 | 結果 | 主な指摘 |
| --- | --- | --- |
| 1 周目(計画) | 否決 | 期待失敗集合の明示・判定不変の証明方法・`pending_human_reviews` の exact-set |
| 2 周目(実装) | 否決 | `SCOPE:ALL_LOGICAL` の取りこぼし(P0)・絞り込み実行で 34 本の red を見落とし・oracle 外の digest 連鎖 |
| 3 周目(実装・最終) | **否決(P0 2 件)** | 凍結基準の `changes` の表現・承認記録の出所 |

**全件実行 1627 passed / red 0**。ステップ 7 の一般化が保護を弱めていないことは
**欠落変異の確認**(`_check_history_append_only` / `_check_bootstrap` / `_check_basis_correspondence` を
それぞれ無効化すると対応する負例が期待する red を得られない)で実証済み。

## 未決(人間の手が要る 2 点)

1. **凍結基準台帳が「値の移動」を表現できない**(3 周目 P0-1)。
   台帳自身は `movement_rules.triggers` に **`value_change`** を挙げ、
   `universal_lower_bound` に **`value`** を必須軸として挙げているが、
   `CHANGE_ASPECTS`(`scripts/check_frozen_baselines.py:77`)の 8 種は
   **`declarations` の 4 フィールド + 台帳自体の 4 事項**であり、**値の移動に対応する `aspect` が無い**。
   schema は `changes` に最低 1 件を要求するため、現状は `frozen_targets` の before/after 同値という
   **変わっていないものを変更として書いた**記録になっている。
   → **推奨**: TSK-421(台帳所有者)へ起票したうえで、`changes` に `value` aspect を足す。
   **`check_frozen_baselines.py` は `guard_paths` かつ本計画書の「やらないこと」に入っているため、
   射程拡大には人間の明示承認が要る**
2. **`approved_by` / `approved_at` の出所**(3 周目 P0-2)。現在の値は当方の推定であり、
   「**承認者・承認日は取得元を明記して逐語転記する。取得不能なら停止する**」
   (`docs/worklog/2026-09-20-frozen-baseline-ledger.md:63`)に反する。
   → **推奨**: PR #77 の Approve レビューを出所にし、`gh api` の結果から逐語転記する
   (`acceptance_id` が既に `masaki1025/pitchlog#77` で、同じ受理単位から機械的に引ける)
