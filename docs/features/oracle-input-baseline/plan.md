---
feature: oracle-input-baseline
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3da93b75e68781308abac4ecfe162251
branch: fix/oracle-input-baseline
created: 2026-09-13
計画レビュー周回: 5        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 凍結資産の更新経路を条文化し、検査器から SHA を落とす(TSK-386)

## 1. 背景・目的

Notion: [TSK-386](https://app.notion.com/p/3da93b75e68781308abac4ecfe162251)。
調査: [research.md](research.md)。詳細設計: [design.md](design.md)。

**送り元は TSK-379(PR #60・マージ済み `0bc05b8`)。** 同タスクは要件書を v2.8 へ改訂する際に、
**「入力ベースラインは永久に動かない」を前提にした検査が 5 箇所ある**ことに突き当たった。
**うち 4 箇所は PR #60 内で解消したが、`scripts/check_authz_catalog.py:107` の
`ORACLE_INPUT_BASELINE_COMMIT`(コミット SHA 直書き)は応急処置のまま残っている。**

**放置すると、要件書を改訂するたびに検査器のソースを編集する運用が続く。**

**要件の根拠**: [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010)(測定方法)+
[NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)(b)。
構成検査の位置づけは **`data-model.md:244` の明示委任**(「各項目の検査対象集合と合格述語は実装が確定する」
— 範囲確定・PO 裁定 2026-09-09)。
**`NFR-018` は根拠にしない** — 同項の対象列挙に認可構成は入っておらず、
承認済み計画書が明文で禁じている(`docs/features/pg-authz-verification-g2/plan.md:854`)。

**台帳の受け取り先**: `docs/development/harness-evaluation.md:2708` が本タスクを名指ししている。
**上位型は `H-85`(採番済み・未対応)**(同 `:745`)。

## 2. スコープ

**計画レビュー 5 周**(`P1` 7 / 6 / 6 / 6 / **3**)。**全周の誤り 36 件は [design.md](design.md) 8 節が持つ。**
**5 周目で初めて件数が落ち、残った指摘に設計の方向を変えるものは 1 件も無い。**
**5 周目の要点**: **① version 型は `supersedes` を持たない**(`G-4` が同じ役目 — 同 3-3)
**② `pending_removal` は「台帳が base に無いとき」にだけ許す**(機械の期限 — 同 2-4)。

### やること

1. **ハーネス設計書へ `7.7 凍結基準の更新経路` を新設**(`v1.14 → v1.15`・**7.6-3 後段**)
2. **`contracts/authz/frozen-baselines.json` を新設** — **追記のみの基準台帳**
   (`oracle_input` / `oracle_meaning` / **`core_areas_guard`** / `corpus_versions` の **4 系列**)
3. **凍結基準の直書き 4 箇所をすべて台帳へ移す**(`P1-3` — **条文の適用範囲と実装を一致させる**)。
   **台帳は 4 系列**(`oracle_input` / `oracle_meaning` / **`core_areas_guard`** / `corpus_versions`)
   - `scripts/check_authz_catalog.py:107` `ORACLE_INPUT_BASELINE_COMMIT` → `oracle_input`
   - `backend/tests/db/authz/mutation_composition.py:36` `STEP2_BASE_REVISION` → `oracle_meaning`
   - `tests/test_check_authz_catalog.py:38` `AUTHZ_STEP2_BASE_REVISION` → 同上(**これだけが重複**)
   - **`tests/test_core_guard.py:47` `AUTHZ_GUARD_BASE_REVISION` → `core_areas_guard`(独立系列)**
     — **値は同じだが対象が違う**(`core-areas.json` を読む固定基準。**3 周目 `P1-2`**。
     統合すると **oracle 意味基準の更新が core-guard の基準まで暗黙にリベースする**)
4. **`:4798` の fail-open を fail-closed へ**
5. **`H-85` 対応案②** — 母集合へ `corpus_version`、**派生 3 資産の digest 辺 6 本を 0 本へ**
   (**台帳側で 1 本増えるので純減 5 本** — 2 周目 `P1-1`)
6. **負例 12 件を固定**(N1〜N12 — design.md 6 節。**`N9` 初期値すり替え / `N10` `F-7` の比較元 /
   `N11` allow-list の識別単位 / `N12` 古くなった登録**)
7. **allow-list 方式の走査を作る**(design.md 2-4)— **ソース本文の部分一致**で走査し
   (**AST 完全一致だと埋め込みを見落とす** — 4 周目 `P1-5`)、**識別単位は `(パス, 値)` の組**、
   置き場は `scripts/frozen-baseline-scan-allowlist.json`、**未登録の出現も、消えた登録も red**。
   **`pending_removal` 枠を持つ**(ステップ 5 の時点では除去前の基準が残るため — 4 周目 `P1-3`)
8. **`ci.yml` へ新設検査のステップを足す**(**3 周目 `P1-4`**)— **`fetch-depth: 0` のジョブへ**。
   **base/HEAD を要る検査は `pytest tests/` の経路では走らない**(先例 `ci.yml:108`)

### やらないこと(**無宛先の申し送りを作らない** — `P2-8`)

| 対象 | 判定 |
| --- | --- |
| `.github/workflows/ci.yml` へ **既存** authz 系の実行ステップを足す | **不採用(閉じる)**。**harness ジョブが `pytest tests/` を無条件実行し、`test_repository_catalog_covers_the_entire_requirements_file` が実スクリプトを subprocess 実行している**ため**検査の実効に差が無い**。**ただし新設 `check_frozen_baselines.py` は別**(やること 8 — base/HEAD を要るため `pytest` 経路では走らない。**3 周目 `P1-4` で判定を部分的に取り消した**) |
| harness 側 `test_oracle_reseal_preserves_inputs_and_changes_only_two_asset_digests` の整理 | **不採用(閉じる)**。**無条件実行 vs パスフィルタ依存の差**があり、**消すと弱くなる場合がある** |
| `contracts/authz/function-bodies/manifest.json` の `source_commit` | **射程外。台帳の候補へ記録する**(受け取り先を持たせる) |
| 要件書 → 母集合の 1 段目 / oracle → 下流 2 の 3 段目 | `H-85` の射程外 / 封印の性質そのもの |
| `review_policy` / `reseal_policy` の変更 | **一次記録が無く**、変える理由も無い |

**製品コードは 1 行も書かない。**

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| [ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) | **`7.7 凍結基準の更新経路` を新設**(`v1.14 → v1.15`)。基準の外出し・更新経路の必置・**追記のみ**・更新の記録・fail-closed・委任の境界 | **finalize-doc**(7.6-3 **後段** — 合否条件の新設。先例は `:720`・裁定 `Q-1`) |
| [ドキュメント索引](../../README.md) | ハーネス設計書の版・要約・最終更新を現行化 | PR レビュー(機械強制) |
| [ハーネス運用評価台帳](../../development/harness-evaluation.md) | **`H-85` へ対応の追記** + **候補「2 つの機械検査が正面から矛盾し…」へ解消の追記** + **候補 5 件を新規**(**完了コミットを持たないステップで現在地導出が壊れる** / `function-bodies` の `source_commit` / **一度きりの移行検査(`F-7`)がマージ後に到達不能な分岐として残る問題** / **レビュー指摘の訂正を 1 箇所だけ直して「反映した」と数える型**〔3・4 周目の非起因がこれ〕/ **新設した要素を既存の要件文・述語表・ステップ順序・負例の向きと突き合わせない型**〔4 周目 `P1` 6 件中 3 件 — design.md 8 節〕)+ 変更履歴 1 行。**`H-*` の新規採番はしない・版は上げない** | PR レビュー(7.6-3 前段) |
| [データモデル設計](../../design/data-model.md) | **反映なし**(`:244` の委任を使うだけ) | — |
| [要件定義書](../../requirements/requirements-pitchlog-2026-07-22.md) | **反映なし** | — |
| [ADR-004](../../adr/ADR-004-merge-gate-scope.md) | **反映なし** | — |

**正本体系外だが同一 PR で運ぶもの**:
`contracts/authz/frozen-baselines.json`(**新設**)/ `oracle-seal.lock.json` /
`requirement-claims.json`(`corpus_version`)/ 派生 3 資産 + 各 `.lock.json` /
`scripts/check_authz_catalog.py` / **`backend/tests/db/authz/mutation_composition.py`**(`P1-1`)/
`tests/test_check_authz_catalog.py` / **`tests/test_core_guard.py`**(3 周目 `P1-2`)/
**`scripts/check_frozen_baselines.py`(新設)**/ **`scripts/frozen-baseline-scan-allowlist.json`(新設)**/
**`.github/workflows/ci.yml`**(**新設検査のステップ** — 3 周目 `P1-4`)/
`docs/features/oracle-input-baseline/` / `docs/worklog/2026-09-13-oracle-input-baseline.md`。

## 4. 実装方針

### 重さ分類の根拠 — **コア領域**

`scripts/check_authz_catalog.py`・`contracts/authz/*`・`tests/test_check_authz_catalog.py` は
**コア領域 tenant-isolation の paths**(`.claude/core-areas.json:291-310`)。
**敵対レビュー + 人間の逐行確認が必須**(設計書 `:370`・`:699`)。

### 設計の中身

**[design.md](design.md) が持つ。** 要点だけ:

- **基準台帳は連鎖の入口を持たない** — **他資産の digest は持ってよい**(anchor に要る)が、
  **誰からも digest で参照されない**。`input_assets` にも `sealed_assets` にも入れない(同 3-1)
- **`F-4` 追記のみが要** — **先例 `scripts/check_nfr021_append_only.py:397`**(同 3-4)
- **保証する / しないの境界を表で持つ**(同 3-4)。**ブランチ保護が無い**ので
  (`docs/development/github-setup.md:35-39`)、**`F-4` は「改ざんが差分として見える」までである**。
  **承認欄をコピーした新規追記は通る**(条文の骨子 3・4 もこの表現に揃えた — 3 周目 `P1-5`)
- **新設検査は `ci.yml` へ結線する**(同 3-7)— **結線が無いと実 PR に 1 度も走らない**。
  **ただし本 PR で確かめられるのは `F-7` の分岐まで**(`F-4` は台帳がマージされて初めて効く)
- **移行 PR の初期記録は `F-7` で守る**(同 3-5)— `F-4` は base にファイルが無いと効かない
- **上げ忘れの検出も追記のみが anchor**(同 4-3)。**派生の追随は `G-5`**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

**すべてのステップが完了コミットを持つ**(`P1-7` — 欠番があると `feature_status.py` が
`inconsistent` を返す。`scripts/feature_status.py:950` の
`completed != set(range(1, maximum + 1))`)。**確定ゲートの反映周はステップ表の外**である。

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **退行の物差しを作る** — N1・N2 を一時ディレクトリの複製上で実行する形で固定し、**現行実装に対して red になることを記録する** | **N1・N2 が現行で red** / **worktree を汚さない** / ルート `pytest tests/` green |
| 2 | **ハーネス設計書を `in-review` 化する** — frontmatter・変更履歴へ**起案行(射程宣言)**・索引 / **同一コミットで適用版(7.3-1)を worklog へ暫定記録** | `check_docs_status.py` exit 0 / **条文コミット SHA = 本コミットの第一親**を `git show` の差分本体で確認 / **版セルは暫定と明記** |
| 3 | **`7.7 凍結基準の更新経路` を書き、確定ゲートを通して approved にする**(`/finalize-doc`)。**反映周のコミットは `反映<r>周目` のみでステップ記法を付けない。本ステップの完了コミットは approved 化コミット** | **条文に個別の識別子が無い** / **凍結資産を列挙していない** / 収束まで反映(7.3-2)/ **6 周警告**(7.3-6)/ **frontmatter・変更履歴・索引の三者が一致** |
| 4 | **`frozen-baselines.json`(**commit 型 3 系列**)と `scripts/check_frozen_baselines.py` を新設し、`ci.yml` へ結線する** — 共通述語 `F-3`・`F-4` + commit 型の `F-1`・`F-2`・`F-5`〜`F-7`(**`corpus_versions` はステップ 8** — 4 周目 `P1-1`) | **`F-4` が PR の base と HEAD を比べている**(先例と同型)/ **N3・N5・N6・N9・N10 が red** / **`F-7` が base 側ソースから定数を抽出している**(**検査器に 40 桁の値を書いていない**)/ **`ci.yml` の当該ステップと同じコマンド・引数を手元で実行し、`N9` の複製に対して非 0 終了することを記録**(4 周目 `P1-2` — 「外すと `N5` が CI で緑」は**本 PR では実測不能**だった)/ **当該ステップが `fetch-depth: 0` のジョブにある**ことを `ci.yml` の行で示す |
| 5 | **`oracle_input` 系列へ現行の基準を移し、検査器から SHA を落とす**。**あわせて allow-list 走査を作る**(design.md 2-4) | **`scripts/check_authz_catalog.py` に 40 桁 SHA の直書きが 0 件**(**allow-list 走査が数える** — 手で列挙しない)/ **`N11` が red**(既存の値を別ファイルへ足しても red = 識別単位が `(パス, 値)`)/ **`N12` が red**(**走査で見つからない組を登録すると red** = 逆向き。**`N11` とは向きが違う** — 4 周目 `P1-4`)/ **走査の出現が `14 → 13`**(**本ステップで `check_authz_catalog.py` の `0cf994f4…` 1 件が消える** — 5 周目 `P1-3`。**14 のままにすると合格条件が同時達成不能だった**)/ **`tests/`・`backend/` に残る 3 件は `pending_removal: true` で登録**/ **N2 が red のまま** |
| 6 | **`:4798` の fail-open を fail-closed へ** | **N4 が red**(**現在は green**)/ 既存の緑を落としていない |
| 7 | **`oracle_meaning` 系列へ 2 件、`core_areas_guard` 系列へ 1 件を移す**(**別系列** — 3 周目 `P1-2`) | **`backend/tests/**` と `tests/**` に凍結基準の 40 桁 SHA 直書きが 0 件**(allow-list 走査)/ **N1 が red のまま** / **`test_core_guard.py` の既存テストが green** / **`oracle_meaning` へ追記しても `core_areas_guard` の末尾が動かないことを実測**(暗黙リベースが起きないことの実証)/ **allow-list の `pending_removal` が 0 件** / **走査の出現が `13 → 10`** / **重複は `AUTHZ_STEP2_BASE_REVISION` の 1 件だけが解消** |
| 8 | **`corpus_versions`(version 型・4 系列目)と `corpus_version` を新設する**(母集合 + **派生 3 資産**) | **N7・N8 が red** / **`G-1`〜`G-5` が実装されている**(`G-5` = 派生の版が母集合と一致)/ **共通述語は `F-3`・`F-4` の 2 つだけ**(**`F-2` は commit 型専用** — 5 周目 `P1-1`)/ **version 型の記録に `supersedes` が無い**(4-3 の構造例どおり)|
| 9 | **派生 3 資産の digest 辺 6 本を版参照へ置き換える(入力資産の変更・第 1 コミット)** | **資産全体を指す digest 辺が `21 → 16`**(**機械が変更前後を数える**。定義と実測は design.md 4-1 — **`contracts/` の digest らしきキー全部 5241 件のほうではない**)/ **派生 3 資産に `requirement_claims_blob_digest` が 0 件** |
| 10 | **新 blob を含むコミットへ基準を追記し、再封印する(第 2 コミット)** | **`P1-6` の二段構造**。台帳へ追記(`supersedes` が連鎖)/ `--reseal-oracle` / **`check_authz_catalog` ok** |
| 11 | **負例 12 件を通しで確認し、効果を実測する** | **N1〜N12 がすべて red** / **digest 辺を機械が変更前後で出力し `21 → 16` を記録** / **手で計算する digest が 6 → 1**(台帳の `canonical_sha256` が残る)/ **要件書を 1 バイト変えて追随し、検査器のソースを 1 行も編集せずに済むことを実測** |
| 12 | **クローズ処理**(`/pr`) | 3 節の宣言と PR 内容が突合 / **台帳の過去記録を書き換えず追記** / CI 全ジョブ green / 逐行確認のチェックと実施記録行 / **PR 本文に「`F-7` が効くのはこの 1 回だけなので初期記録 3 件を逐行で見る」と明記**(`core_areas_guard[0]` を含む — 4 周目 `P2`) |

**ステップ 3 が最も重い。** ハーネス設計書は approved 正本で、**確定ゲートが要る**。
**ステップ 1 を最初に置くのが要**である — **朝にこの領域で防御を落としている**ので、
**変更前の物差しを先に作る**。

## 5. DoD(受け入れ基準)

- [ ] **ハーネス設計書に `7.7 凍結基準の更新経路` が approved で存在する**(`v1.15`)
- [ ] **凍結基準の 40 桁 SHA 直書きが、`scripts/` `tests/` `backend/tests/` に 0 件** —
      **allow-list 走査が数える**(**手で列挙しない** — 2 周目 `P1-6`。初版は 3 件と数えて 1 件見落とした)
- [ ] **allow-list に無い `(パス, 値)` の組が現れると red**(**既存の値を別ファイルへ足しても red** — N11)
- [ ] **走査で見つからない組を登録すると red**(N12 — **`N11` と逆向き**)
- [ ] **走査はソース本文の部分一致**である(**AST 完全一致だと埋め込み 4 出現を見落とす**)。
      **出現が `14 → 13`(ステップ 5)→ `10`(ステップ 7)と推移したことを機械が出力した**
- [ ] **allow-list の `pending_removal` が 0 件**、かつ
      **`true` を許すのは「台帳が base に存在しないとき」だけである**(機械の期限 — 5 周目 `P1-2`)
- [ ] **`frozen-baselines.json` が 4 系列を持ち、追記のみで守られている** — **既存記録の書き換えが red**(N5)
- [ ] **commit 型 3 系列と version 型 1 系列で、適用する述語が分かれている**。
      **`supersedes` は commit 型だけが持つ**(version 型は `G-4` の連番 — 5 周目 `P1-1`)
- [ ] **台帳は他資産の digest を持つが、誰からも digest で参照されない**(片方向 — design.md 3-1)
- [ ] **`oracle_meaning` への追記が `core_areas_guard` の基準を動かさない**(3 周目 `P1-2`)
- [ ] **記録なしに基準を動かせない**(N3・N6 が red)
- [ ] **`oracle_commit` が到達不能なとき red**(N4 — fail-closed)
- [ ] **既存の性質を落としていない** — N1・N2 が**変更前と同じく red**
- [ ] **母集合の版の上げ忘れが red**(N7)・**派生の追随漏れが red**(N8 — `G-5`)
- [ ] **移行 PR の初期記録が、削除する定数の値と一致しないと red**(N9 — `F-7`)
- [ ] **`F-7` の比較元が base 側ソースである** — **base の定数値を変えると red**(N10)。
      **検査器に 40 桁の値をハードコードしていない**
- [ ] **`ci.yml` に新設検査のステップがあり、`fetch-depth: 0` のジョブにある**。
      **同じコマンド・引数を手元で実行し、`N9` の複製に対して非 0 終了することを記録した**(4 周目 `P1-2`)
- [ ] **資産全体を指す digest 辺が `21 → 16`**(**派生 −6 / 台帳 +1**)であることを、
      **機械が全数列挙して変更前後で出力した**(定義は design.md 4-1)
- [ ] **手で計算する digest が 6 → 1 になったことを示した**(台帳の `canonical_sha256` が残る)
- [ ] **要件書を 1 バイト改訂して追随し、検査器のソースを 1 行も編集せずに済むことを実測した**
- [ ] **台帳へ `H-85` の対応・候補の解消・新規候補 5 件を追記した**(過去記録は書き換えない)
- [ ] **敵対レビューと人間の逐行確認を通っている**
- [ ] **design.md 3-4 の「保証しない」欄が、実装後の実際の挙動と一致することを確認した**
      (**過大主張を 2 周続けて出しているため、DoD に置く**)

## 6. テスト計画

**NFR-019 のテスト種別に足すものは無い。** 製品コードを書かないため。
**構成検査は「要件の 4 種に属さない」**(`docs/features/pg-authz-verification-g2/plan.md:853`)。

| 種別 | 何を足すか |
| --- | --- |
| **退行**(既存の性質を落としていないこと) | **N1** 意味本文の改ざん + 再封印 / **N2** ポインタを内容等価な別コミットへ。**ステップ 1 で先に測る** |
| **負例(新設)** | **N3** 承認欄が空 / **N4** 到達不能な commit / **N5 既存記録の書き換え(最重要)** / **N6** `supersedes` の不連鎖 / **N7** 版の上げ忘れ / **N8** 派生の追随漏れ(`G-5`)/ **N9** 移行 PR の初期値すり替え(`F-7`)/ **N10** `F-7` の比較元が base 側ソースであること / **N11** allow-list の識別単位が `(パス, 値)` であること / **N12** 走査から消えた登録が残っていること(**`N11` と逆向き** — 4 周目 `P1-4`) |
| **静的** | **allow-list 走査** — **ソース本文の部分一致**で `(パス, 値)` の組を全数列挙。**未登録の出現も、消えた登録も red** / **派生 3 資産に `requirement_claims_blob_digest` が 0 件** / **`contracts/` の digest 辺の全数列挙**(**機械が**変更前後で数える) |

**負例はすべて一時ディレクトリへリポジトリを複製して実行する**
(先例: `backend/tests/test_authz_mutation_composition_full.py` の `_clone_repository`)。
**worktree を汚さない。**

**回すコマンド**

```
uv run ruff check . && uv run ty check && uv run pytest tests/
(cd backend && uv run pytest --ignore=tests/db)
uv run python scripts/check_authz_catalog.py
uv run python scripts/check_frozen_baselines.py --base origin/develop
uv run python scripts/check_plan_docs_sync.py --plan docs/features/oracle-input-baseline/plan.md --base origin/develop
```

**人が読んで確かめること**

| 何を | どう確かめるか |
| --- | --- |
| 条文が個別の識別子を持たないこと | `7.7` を読んで `oracle_commit` 等が出てこないことを確認 |
| 更新経路が 1 本であること | **台帳への追記以外に基準を動かせる経路が無い**ことを、検査器を読んで確認 |
| 負例が守りたい性質に対応していること | **N1〜N12** のそれぞれが、**どの性質が壊れたときに鳴るか**を対応づける |
| **機械が保証していない範囲** | **design.md 3-4 の「保証しない」欄 4 件**を読み、**残余リスクとして受け入れるかを人間が判断する**。とくに **① `approved_by` のコピー貼り付けは通る ② ブランチ保護が無いので直接 push で base を書き換えられる**(`github-setup.md:35-39`) |
| **移行 PR の初期記録**(1 回限り) | **`F-7` が効くのは新設 PR だけ**。**`oracle_input[0]`・`oracle_meaning[0]`・`core_areas_guard[0]` の 3 件を逐行で見る**(**PR 本文にも 3 件と書く** — 4 周目 `P2`) |
| **`F-7` がマージ後は到達しない分岐になること** | **畳み方を台帳の候補へ記録したか**(受け取り先を持たせる — 3 周目 `P1-1`) |
