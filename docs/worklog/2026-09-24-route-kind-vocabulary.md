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
('disposition_by_kind', "KeyError: 'unmapped_route_kind'")
```

**6 本目は `failures` が 2 件**である(**4 周目 P1-3 の是正** — 当初は `--tb=line` の
要約が先頭 1 件しか出さないのに気づかず、`expected_keys_by_kind` だけを写していた。
`-vv -o addopts=` で全文を出して確認した)。

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
(`scripts/check_frozen_baselines.py:973-983`)。**`value` には fold 先の状態が無い。**

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

## 結果サマリ(/pr クローズ処理・2026-09-25)

**実装したもの**: `route_kind` に **`record_and_aggregate`** を足した。**語彙だけで、経路は 1 本も足していない**
(`routes` は 37 件のまま・`entries` と `aggregate_decision_digest` は merge-base と完全一致)。

既存 4 種と同じ **「値域 + 種別別検査 + exact-set」の 3 点セット**を持たせた:

| 検査 | 内容 |
| --- | --- |
| 値域 | `ROUTE_KINDS` へ 1 値追加(4 → 5) |
| 必須キー | `expected_keys_by_kind` = 共通 4 + `provenance_ids` + `operation` |
| `origin` | **`design` を強制**(`legacy_route` が `requirement` を強制するのと同型) |
| `route_id` | **導出規則 `ROUTE:RECORD:<資源>:<操作>`** と一致すること |
| provenance | **専用 ID `PLAN-TSK446-RECORD-AND-AGGREGATE`** を含むこと |
| `operation` | **`{read, insert, update}` に閉じる**(`delete` を外して物理削除経路を構造的に塞ぐ) |
| 対応表 | `ROUTE_KINDS` / `expected_keys_by_kind` / `disposition_by_kind` の不整合が **`CatalogError`** |

**正本への反映**: `contracts/authz/route-registry.json`(+ lock)/ `auth-catalog.json`(+ lock)/
`oracle-seal.lock.json` と oracle 資産 6 本の `oracle_commit` / `frozen-baselines.json` の `history`(2 件目)/
`frozen-baselines.schema.json`(`changes.minItems` 1 → 0)/ ハーネス運用評価台帳(候補 4 件)/ `docs/README.md`。
**要件書・`data-model.md`・ADR への反映はなし**(いずれにも `route_kind` の語が 0 件)。

**副産物**: **凍結基準台帳の初回の「値の移動」**になり、台帳が値の移動を表現できない欠陥が露見した(ステップ 8 で是正)。
`tests/frozen_negatives/` の 4 本が「履歴 1 件」を前提に直書きされていたことも露見した(ステップ 7 で一般化)。

**テスト**: 全件実行 **1631 passed / red 0**。`ruff check` / `ty check` green。
`check_authz_catalog.py` ok(`routes=37 cells=12` — **判定不変**)。`check_frozen_baselines.py --invariants-only` OK。

**敵対レビュー 3 周**(計画 1 周・実装 2 周)。3 周目の P0 2 件 / P1 4 件はすべて反映済み。
**4 周目(最終確認)は PR 作成後に回す。**

**申し送り**: **台帳が「宣言そのものとしての値の移動」を記録できない一般の欠陥は TSK-421 へ**。
`changes` は台帳文書の replay ログなので、値の移動に対応する `aspect` を足すと fold 先の状態が無い。
本タスクは `changes` の空を許す形で回避したが、**設計としての整理は台帳所有者の判断**である。

## 敵対レビュー 5 周目(2026-09-26)

**判定: 否決(P0 2 件 / P1 2 件 / P2 1 件)。** 指摘はすべて当方で裏を取った。

### P0-1 は本タスクの射程外 — TSK-421 へ申し送る

レビュアーは **`implementation_bindings.registry` の記録が、実際に使われる registry object と
一致することを機械検査していない**ことを示した。合成 PR で `registry` を
`scripts/frozen_baselines.py:COMPARISON_STRATEGIES` から
`scripts/check_frozen_baselines.py:CODE_ASSET_PATHS` へ差し替え、その before/after を
非空 `changes` として追記したところ、**`--acceptance` が exit 0** になった。

原因は **symbol の存在検査が字面だけ**(`_module_defines_symbol`)で、
**実際の strategy key 検査と識別値導出は import 済みの `COMPARISON_STRATEGIES` を直接使う**こと。

**当方の実測**: **本 PR は `_check_implementation_bindings` と registry symbol の検査に 1 行も触れていない**
(`git diff bf8ba5b..HEAD -- scripts/check_frozen_baselines.py` を `registry` / `implementation_bindings` /
`COMPARISON` で絞ると **0 行**)。**merge-base から存在する穴**である。

→ **射程外として TSK-421(台帳所有者)へ申し送る。**
ただし**ステップ 8・9 が掲げた「レコードが必ず何かを主張する」という約束は、この穴がある限り完全には果たせない**。
**本 PR が保証するのは「`changes` が空なら識別値か配置が動いていること」と
「change entry の before / after が意味上異なること」までである。**

### P1-1 はステップ 10 で是正

**ステップ 9 の正規化が広すぎた。** `placement_change` の locator 配列まで正規化したため、
**同じ台帳の同じ配列を検査器が 2 つの規則で比べる**状態になっていた。

| 場所 | 比較規則 |
| --- | --- |
| 履歴導出(`moved` の決定・`:841`) | **raw equality** |
| 不変条件 A(`:440-441`) | **正規化してから比較** |

`[A, B] → [B, A]` の配置変更で、**導出側は `moved: true`・不変条件 A は「配置も動いていない」**となり、
**4 周目 P1-1 の再発**になる。ステップ 10 で**配置と識別値の比較を raw equality へ戻した**。

### P1-2 は 3 件を是正

| 旧 | 新 | 理由 |
| --- | --- | --- |
| `check_frozen_baselines.py:795-816` | **`:818-825`** | 旧は値を取り出す途中まで。現在値との比較はここ |
| 同 `:1009-1023`・`:1304-1342`・`:1395-1412` | **`:1413-1433`** | 旧は event 値の読取・受理 batch の fold・関数冒頭。`base.ref == develop` と親照合はここ |
| 同 `:975-983` | **`:973-983`** | 規範状態 5 件のうち `acceptance`(`:974`)が範囲外だった |

### P2-1 は当方の記述の誤り

台帳の候補①に「**負例テストは red になったことしか見ない**」と書いたが**事実と違った**。
共通 helper `_assert_red` は **returncode だけでなく stdout が空であることと stderr の完全一致**まで
検査する(`tests/frozen_negatives/test_frozen_baseline_acceptance.py:471-481`)。
したがって sha256 エラーが先に出れば、**対象の負例は「誤った理由で通る」のではなくテスト失敗になる**。
**正確には「変異が対象の検査へ一度も届かず、変異試験そのものが未成立になる」**である。台帳と索引を訂正した。

### P0-2 は 3 周連続で同じ判定

**3 周目・4 周目・5 周目のすべてで P0**。5 周目は満たす条件を具体的に挙げた:

- **PR #77 の `APPROVED` review の `user.login` と `submitted_at` を機械可読な出所として転記する**
- 実名を使うなら、login と実名の対応も一次資料で示す
- または、発話者の認証済み identity とイベント timestamp を含むセッション記録を出所にする
- **取得できなければ規律どおり停止する**

**当方は 4 度目の推奨として、PR #77 への Approve を求める。**
