---
date: 2026-09-04
topic: TSK-250 計画書の再レビュー — 先行タスク A(TSK-269)の申し送り 24 項目の反映
branch: feature/data-model-canonical
---

# 作業ログ: 2026-09-04 TSK-250 計画書の再レビュー(A の申し送り 24 項目の反映)

## やったこと

先行タスク **A = TSK-269 文書検査機構の多文書対応** が **PR #42 / merge commit `fdda374`** で develop へマージされた。
その `docs/features/doc-check-multi-doc/design.md` **11 節の申し送り 24 項目**を、TSK-250 の実装計画書
`docs/features/data-model-canonical/plan.md` へ反映した。**射程は 24 項目に限定**し、計画全体の再レビューはしていない。

反映先の対応は計画書 1 節「A の申し送り 24 項目の反映先」の表が正(24 行・全件)。主な変更は次の 6 点。

### 1. 契約 5 の文言変更(PO 裁定 (b)・申し送り 24)

1 節の受け渡し契約を「契約 1〜4 = A のマージで充足」「契約 5 = 改訂」の形へ書き換えた。
**A は機構(評価器・構造抽出器・集合一致・資産ローダー・pins)と合成サンプルまでを保証し、
データモデル正本に対する実入力契約(資産形状・必須抽出器・集合宣言・pin 対象と実値)は TSK-250 が固定する。**
「人間確認へ回して契約を満たす」逃げ道の禁止は維持し、**4 保証を check ID で名指しして DoD(5 節)へ移した**
(`forbidden-structure` / `attribution-direct` / `baseline-digest` / `cross-consistency`)。

### 2. ステップ表 26 → 28(2 本追加・全番号を +2)

| 新 # | 追加したステップ | 由来 |
| --- | --- | --- |
| **1** | **A の新資産の `guard_paths` 登録**(最初の独立コミット) | 申し送り 3 |
| **3** | **staging の木の原子的作成**(文書骨格の直後) | 申し送り 14・12 |

旧 1〜26 は新 2・4〜28 へ繰り下げ。**4 節の所有ステップ表(78 件の割り当て)・本文中の全ステップ参照・
確定ゲートの見出し・DoD も同じ写像で更新した**(残存参照の grep 確認済み)。旧ステップ 22(CI 配線)は
**新 24「本番移設と登録(= CI 配線)」**になり、申し送り 14 の「移設 + 登録を同一コミット」を吸収した。

### 3. CI は引数なし列挙(申し送り 1・2)

旧ステップ 22 の「**明示引数で CI に追加**」を撤回した。`ci.yml` は無変更で、**本番 `profiles/registry.json` へ
`data-model` entry を登録すれば検査対象になる**。これに伴い **4 節の検証コマンド集合を 9 件へ差し替え**、
旧 5〜8 の明示引数 4 本を「引数なしの `check_design_propagation.py` / `check_doc_coverage.py`」+
「`check_doc_profiles.py --profile` 2 本」に置いた。**4 周目 P1-1 の宿題(同期側プロファイル名が暫定)は
これで解消**(暫定パスの置換自体が不要になった)。

### 4. 資産の追加と実パス化(申し送り 5・7・8・10・15・22)

- プロファイル → `scripts/design_relations/profiles/data-model.json`、宣言資産 → `invariants/data-model.json`、
  レジストリは**既存ファイルの変更**(`data-model` entry の追加)として 3 節に立てた
- **独立資産 4 本を新設**: `auth-ddl-map-` / `product-ddl-map-` / `direct-requirements-` / `expected-ids-data-model.json`
- `verify_handoff_digest.py` は **A のランナーに載せない**と確定し、本タスクの**専用スクリプト**として 3 節と
  `guard_paths` へ入れた(旧計画の「載らない場合は…」という条件分岐を除去)
- 欠陥台帳の項目を **immutable / mutable** で確定(A の `baseline-digest` の digest 対象と一致させた)。
  機械欠陥は `check` と `invariant` を必ず持つ
- claims の分類に **`direct_requirement` を採る**(排他 4 分類)。`attribution-direct` が必須 22 に入るため必要

### 5. レジストリ entry の `must_require` + `pins`(申し送り 21)

`must_require` = 全 22、`pins` = `profile_gating_digest` / `invariants_digest` / `asset_digests` を 3 節に明記し、
4 節へ **「pins の更新規律」**を新設した(**ゲート宣言・宣言資産・oracle 資産を触るステップは同一コミットで pins を再計算**。
更新漏れは終了 2 で落ちる)。確定ゲートの手順 5・6 にも `pins` を入れた(反映周コミットでは触れない / 人間の逐行確認の対象)。

### 6. 二段階射影と交差検査(申し送り 23)

4 節の交差検査を **段階 A(raw DDL ID)/ 段階 B(製品 ID への射影)** の形へ書き直した。
現物 `contracts/authz/ddl-elements.json` の `scope` は **`candidate_probe_only`・`product_schema: false`** なので
**`product_ddl_map` は必須**。ただし B(TSK-270)完了時に `product_schema` が真になっていれば恒等写像で省略可のため、
**開始条件(DoD)でどちらかを確定する**とした。

## 決定

- **frontmatter の `承認` を `済` → `未` へ戻した。** 契約 5 の文言変更とステップ +2 は射程変更であり、
  確定ゲート手順 8 と A の design 11 節ヘッダ(「TSK-250 は着手前に再レビューが必要」)が人間承認を要求する。
  `codex_run.py implement` は `承認: 済` でないと実行を拒否するので、**再承認までは着手できない**状態になっている。
  `計画レビュー周回` は 4 → **5**
- **`guard_paths` へ登録するのは B 集合の未登録 33 パスのみ**とし、C 集合(`.claude/scripts/codex_run.py`・
  `tests/test_codex_run.py`)は対象外と明記した。裁定 2026-09-04 が TSK-250 に委ねたのは B 集合であり、
  ラッパーは元から `guard_paths` 外(hooks 側の統制対象)。統制範囲を本タスクで広げない
- **登録対象は A の design 3 節 B 表(38 件)ではなく `fdda374` の実 diff を正とする。**
  照合したところ **`scripts/doc_check_invariants.py` が B 表から漏れている**(実在する新設ファイル)。
  表を信じると 1 本取りこぼすため、ステップ 1 の合格条件を「実 diff から導出した集合と突合」にした
- staging の木は `scripts/design_relations/staging/data-model/` に置き、**`guard_paths` へは登録しない**
  (一時物。最終パスは新ステップ 26 で登録し、新ステップ 24 で staging を削除する)
- `absent-section`(申し送り 13)の使い道は**候補案 13 節の再混入の禁止**とした。欠陥 ID は追記分の
  **`DM-MT-01`**(`baseline: false`)で、**ベースライン 78 件の集合は変えない**

## 確認したこと(事実)

| 事実 | 典拠 |
| --- | --- |
| A の実体は共通ローダー `doc_check_profile.py`・評価器 `doc_check_invariants.py`・ランナー `check_doc_profiles.py` | `fdda374` の diff |
| 未登録の B 集合は **33 件**(既登録 6 件・C 集合 2 件を除く) | `.claude/core-areas.json` の `guard_paths` と実 diff の差分 |
| 欠陥 ID の名前空間は**ハイフン前**。`DM-SY-C01` → `DM` | `scripts/doc_check_profile.py` `_defect_namespace` |
| データモデル型プロファイルの雛形が A のサンプルにある | `tests/fixtures/profile-sample/profiles/data-model-like.json`(全 22 ID・`assets` 10 本・抽出器 4 本・`collection_sets` 4 本) |
| `ddl-elements.json` は probe-only | `contracts/authz/ddl-elements.json` の `scope` |
| 設計書 10.1 の `docs-lint` 行は「伝播突合 12 検査(引数なし)」のまま | `docs/development/dev-harness-design-2026-08-07.md` 10.1 |

## 再承認の記録(2026-09-04)

**人間(山田正輝)が本改訂を再承認した。** frontmatter を `承認: 済(2026-09-04・山田正輝)` へ、
DoD 開始条件のチェックを `[x]` へ更新した。計画書 1 節「承認時に記録すること」のうち、
**先行タスク A の分**を以下に確定する(B・C は未マージのため、開始条件成立時に追記する)。

| 項目 | 実値 |
| --- | --- |
| A のタスク | TSK-269 文書検査機構の多文書対応(Notion ステータス **完了**・完了日 2026-09-04) |
| A の計画書 | `docs/features/doc-check-multi-doc/plan.md`(38 ステップ) |
| A の PR / merge commit | **PR #42** / **`fdda374842636d98fe6dd989c2a9c8d532510e85`** |
| A からの受け渡し資産 | `scripts/doc_check_profile.py` / `scripts/doc_check_invariants.py` / `scripts/check_doc_profiles.py` / `scripts/design_relations/{profiles,invariants,schemas}/` / `tests/fixtures/profile-sample/` |
| 資産の digest | **ステップ 6 の `handoff-digest-data-model.json` で固定する**(A は写像対象ではなく機構の提供元であり、同一性は `fdda374` の tree で取れる) |
| TSK-250 の DoD 更新 | 2026-09-04 の計画承認時に Notion 側を更新済み。**本改訂の要点(契約 5・ステップ 28 本・再承認日)をタスクへコメントした** |

## 再承認後の人間の判断(2026-09-04)

| 論点 | 判断 |
| --- | --- |
| **ステップ 1(`guard_paths` 登録)を開始条件より先行させるか** | **先行させない — B・C のマージまで待つ。** 計画は変更しない。A の新資産 33 件が core-guard の対象外である期間は、design 14-2 の受容済みリスクの延長として引き受ける(裁定 2026-09-04 が想定した「マージ後〜TSK-250 の最初のコミットまで」より長くなることを承知のうえ) |
| **`feature_status.py:999` の `merge_allowed` 漏れ** | **今は対応しない**(Notion 起票も台帳追記もしない)。ステップ 1 のコミットで自然に解消する表示上の問題であり、記録は本ログに残すにとどめる |
| **TSK-269 の B 表の漏れ** | **TSK-269 へコメントで記録した**(B 集合は実際には 39 件・未登録 33 件) |

**`feature_status.py` の不具合の詳細**(対応しないが記録): `classify_unmarked_commit` は develop 取り込みマージを
`merge_allowed` と正しく判定するのに、**ステップコミットが 0 件のときの経路**(`:999` の
`any(kind not in {"planning", "documentation"} ...)`)がその値を許容しないため、`kind="unknown"`・note なしで
「実装状況: 不明」になる。ステップコミットが 1 件でも入れば `if completed:` 側へ移り `merge_allowed` は無視されるので、
**「承認直後に develop を取り込んだ状態」でしか発火しない**。`empty` も同じ経路で落ちる。

## 開始条件 B の精密化(2026-09-04)

**B は「マージ済み」に見えて実は満たしていなかった。** TSK-270 は Notion 上「完了」・PR #33 マージ済みだが、
計画書 `docs/features/pg-authz-verification/plan.md` が**第 1 群(契約と前提の凍結・ステップ 1〜5)だけを承認範囲**とし、
**第 2 群・第 3 群を「計画改訂 2 で確定する」として承認範囲外のまま**マージしていた(人間の裁定 2026-08-31 — 台帳 H-68 の型を避けるため)。

実測: `contracts/authz/ddl-elements.json` は **`status: candidate_probe_only` / `product_schema: false` /
`second_group_approval_required: true`**。**候補 probe 資産であり「通った構成」ではない。**

→ **続きを [TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2)(第 2 群・第 3 群)として起票**し、TSK-270 へ相互リンクのコメントを残した。
本計画書の開始条件を **「B がマージ済み」→「TSK-317 の完了」** へ精密化した(1 節の表・4 節の開始条件・5 節の DoD)。
**射程は変わらない**(本タスクがやることは同じ)ため、`承認: 済` は維持する。

**この精密化をしなかった場合の事故**: 開始条件を字面どおり読むと B は充足済みに見え、
**候補 probe 資産の上にデータモデル正本を建てられてしまう**(ステップ 19 の `AUTH-*` exact-set が候補値で green になる)。

## 未決・次にやること

- 開始条件のうち **B(TSK-317)・C(TSK-271)は未完了**。人間の裁定 4 件も未。
  **上の判断により、ステップ 1 を含む全ステップが B・C 待ち**
- **主軸は TSK-280(同期プロトコル イベント契約の骨格 — 製品コードの 1 本目)へ移す**(人間の判断 2026-09-04)。
  approved 設計・DB スキーマ不要・ベクタ非依存で、本タスクにも B・C にも依存しない
- 計画書 3 節・4 節は A の機構に合わせて実パス化したが、**実値(pins・digest・資産の中身)はステップ 3 以降で確定する**
