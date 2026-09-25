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

## ステップ 8 — P0-1 の是正(2026-09-25)

**当初の推奨(`changes` に `value` aspect を足す)は実測で覆した。**
`changes` は**台帳文書そのものの replay ログ**であり、`_check_replay` が `changes[]` と
`placement_change` を fold して**規範状態 5 つ**(`acceptance` / `movement_rules` /
`implementation_bindings` / `placements` / `declarations`)と一致するかを検査する
(`scripts/check_frozen_baselines.py:975-983`)。**`value` には fold 先の状態が無い。**

そこで **`changes` の空を許し**(schema `minItems: 1` → `0`)、
**レコードが必ず何かを主張すること**を補償不変条件 2 つで強制した:

- **A**: `changes` が空なら `prior_identity != new_identity`
- **B**: change entry は `before != after`(**no-op entry を塞ぐ** — 今回の虚偽記録の形そのもの)

`history[1].changes` は、検査器を編集したことで動いた `implementation_bindings` の
**実変更 1 件**になった(虚偽の `frozen_targets` 同値 entry は除去)。

### 検査器の自己保護に気づいた点(申し送り)

**台帳は `implementation_bindings.code_assets` で検査器の sha256 を固定している。**
そのため `check_frozen_baselines.py` に欠落変異を入れると、**目的の検査ではなく
sha256 検査が先に鳴る**。欠落変異の確認をするときは、**台帳の sha256 も変異後の値へ
揃えてから実行する**必要がある。この手順で `_check_history_append_only` を無効化し、
ステップ 7 で直した削除検査・同数置換検査の負例 2 本が**期待する red を得られなくなる**ことを確認した
(= ステップ 7・8 の fixture 変更は保護を緩めていない)。

**全件実行 1631 passed / red 0。**

## 未決(人間の手が要る 2 点)

1. ~~**ステップ 8 の射程拡大を認めた記録**~~ → **記録済み(下記)。**
   `scripts/check_frozen_baselines.py` は `guard_paths` であり、本計画書が「やらないこと」に入れていた。
   ~~**凍結基準台帳が「値の移動」を表現できない**(3 周目 P0-1)。~~ **ステップ 8 で是正済み。**
   以下は経緯の記録:
   台帳自身は `movement_rules.triggers` に **`value_change`** を挙げ、
   `universal_lower_bound` に **`value`** を必須軸として挙げているが、
   `CHANGE_ASPECTS`(`scripts/check_frozen_baselines.py:77`)の 8 種は
   **`declarations` の 4 フィールド + 台帳自体の 4 事項**であり、**値の移動に対応する `aspect` が無い**。
   schema は `changes` に最低 1 件を要求するため、現状は `frozen_targets` の before/after 同値という
   **変わっていないものを変更として書いた**記録になっている。
   **このとき出した「`changes` に `value` aspect を足す」という推奨は誤りだった** —
   `changes` の実体が replay ログであることを後から実測して判明した(上のステップ 8 を見ること)。
   **一般の欠陥(値の移動を宣言そのものとして記録できない件)は TSK-421 へ申し送る。**
2. ~~**`approved_by` / `approved_at` の出所**(3 周目 P0-2)~~ → **記録済み(下の「承認の取得元」)。**
   値は変えず(`山田正輝` / `2026-09-25`)、`reason` へ取得元を逐語で追記した。

   **当方は 2 度、PR #77 の Approve レビューを出所にすることを推奨した**
   (`acceptance_id` が同じ受理単位を指すので `gh api` から機械的に引ける)。
   **人間がセッションの発話で入れることを選んだ**ので、その選択と取得元が後から読み取れる形で記録した。
   **台帳は追記のみで書き換え不可**であり、この記録は残り続ける。

## 射程拡大の記録(ステップ 8)

**逐語**:

> ステップ 8 の射程拡大を認める

- **取得元**: 本セッション(Claude Code)での人間の発話
- **日付**: 2026-09-25
- **対象**: ステップ 8 が `scripts/check_frozen_baselines.py`(`guard_paths`)と
  `contracts/authz/frozen-baselines.schema.json` を触ること。
  本計画書が「やらないこと」に入れていた範囲の拡大
- **記録者**: Claude(発話の逐語転記。**言い換えていない**)

> **これは凍結基準台帳の `approved_by` / `approved_at` の出所には使わない。**
> 台帳が求めるのは**値の移動そのものの受理**であり、射程拡大の許諾とは別の事柄である。
> **P0-2 の出所は別に記録した**(下の「承認の取得元(凍結基準 history[1])」)。

## 承認の取得元(凍結基準 history[1])

**逐語**:

> 承認するから入れてくれない?

- **取得元**: 2026-09-25 の Claude Code セッションでの発話
- **台帳へ入れた値**: `approved_by: 山田正輝` / `approved_at: 2026-09-25`(**推定時の値から変えていない**)
- **`reason` へ書いた内容**: 上の取得元と、**PR #77 に review・comment がいずれも 0 件**である事実
- **当方が推奨していた案**: PR #77 の Approve レビューを出所にする
  (`gh api repos/masaki1025/pitchlog/pulls/77/reviews` の `user.login` と `submitted_at`)。
  **2 度提案した**。人間はセッションの発話で入れることを選んだ

> **申し送り**: 台帳は追記のみで書き換え不可なので、この記録は残る。
> **次に凍結基準を動かすときは、PR の Approve を先に取ってから台帳へ入れるほうが、
> 第三者が後から検証できる**。
