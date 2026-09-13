---
feature: oracle-input-baseline
type: research
date: 2026-09-13
---

# 調査メモ: 入力ベースラインが動かせない欠陥をどう解くか

## 問い

`scripts/check_authz_catalog.py:107` の `ORACLE_INPUT_BASELINE_COMMIT`(コミット SHA 直書き)を
**正当な更新経路を持つ形へ変えたい。**

**当初の仮説**: 「**この定数が守る性質は PR #60 が backend へ入れた検査で覆われているので、
定数ごと落とせるのではないか**」。

## 結論(要約)

1. **仮説は否定された。** **定数と backend の検査は重複していない** — **双方に固有の性質がある**。
   定数が単独で守るのは「**ポインタは人間が承認した 1 点から動かない**」。
   backend が単独で守るのは「**封印資産の意味本文が固定基準から一切動いていない**」と **fail-closed**。
   **2 つは相反する不変条件を主張している**(片方が「動くな」、もう片方が「動いてよい、内容が合えば」)。
2. **正本には条文が 1 つも無い。** オラクル封印・入力ベースライン・digest 連鎖の規範は
   **資産(`oracle-seal.lock.json`)と検査器の中だけの宣言**である。
   **更新経路を定めるのは「正本への適合」ではなく「正本に無いものの新設」**であり、
   **置き場を決めないと、また資産の中だけの宣言が 1 つ増える。**
3. **定数を置いた理由はどの記録にも無い。** 導入元 PR #59 の計画書・設計・worklog・
   **コミットメッセージ全文・PR 本文**のいずれにも定数名が現れず、
   **敵対レビュー 4 周 + 規則⑤ 6 周でも指摘ゼロ**。むしろ計画書は逆に
   「**`oracle_commit` は動かさない**」を合格条件にしていた。
4. **副産物の欠陥が 3 件**。うち **1 件は定数を外すと同時に露出する fail-open** で、
   **対で直す必要がある**。
5. **台帳の `H-85`(採番済み・未対応)が本件の上位型**である。
   対応案②「**digest の連鎖を 1 段に縮める**」が既に書かれている。

## 詳細と典拠

すべて worktree `fix-oracle-input-baseline`(起点 `0bc05b8`)の相対パス。
調査は decision-tracer / spec-checker / general-purpose の 3 本 + 作成者の実測を統合した。
**作成者が自分で再現した項目には「実測」と付す。**

---

## 1. 定数を置いた理由 — **どの記録にも無い**(実測)

| 探した場所 | 結果 |
| --- | --- |
| `docs/features/pg-authz-verification-g2/plan.md`・`design.md`・worklog | 定数名の出現 **0 件** |
| **導入コミット `9259892` のメッセージ全文** | **言及なし**(**実測**。2-a〜2-e を列挙するが、この定数はどこにも入っていない) |
| **PR #59 の本文** | **0 件**(**実測** — `gh pr view 59`) |
| 成果物の敵対レビュー 4 周 / 規則⑤ 6 周 | **指摘ゼロ**。`scripts/check_authz_catalog.py` は反映コミットで一度も変更されていない(`docs/worklog/2026-09-09-pg-authz-verification-g2.md:2862`・`:2948`) |

**逆向きの記録がある**:

- `docs/features/pg-authz-verification-g2/plan.md:491` — 「**`oracle_commit` は動かさない**(入力資産が不変のため)」
- 同 `:628`(負例表)— 「**`oracle_commit` を別のコミットへ | red**」
- `9259892` のメッセージ(**実測**)— 「2-e 再封印: `--reseal-oracle` を 1 回。**`oracle_commit` は `dd2cb92` のまま**」

**同 PR は「手書き定数は規律違反」型の指摘を 2 件受けて是正している**
(`docs/worklog/2026-09-09-pg-authz-verification-g2.md:2793` / `:3051`)。
**同じ型の指摘が出ていながら、`:107` のコミット SHA 直書きは指摘されなかった。**

**作成者の読み(記録ではない)**: この定数は「**今回は動かさない**」という当時の事実を
検査器へ焼き込んだもので、「**将来も永久に動かない**」という決定があったわけではない。
**ただしこれは推論であり、典拠は無い。**

---

## 2. 正本の条文 — **無い**

| 正本 | 「oracle / 封印 / seal / ベースライン / digest」 |
| --- | --- |
| 要件書 | **0 件**(3 件ヒットするが全部無関係 — branded type・記録権の凍結・旧システム) |
| ハーネス設計書 | **0 件**。`contracts/` の記述は `:182`・`:199` の 2 箇所のみ |
| `docs/design/data-model.md` | 封印・`oracle_commit`・digest の条文 **なし** |
| 改善台帳 | **0 件**(I-1〜I-28) |
| ADR-003 | `:284` に oracle の語があるが「**期待値を正本実装から自動生成しない**」の話で、封印規律ではない |

**規範として存在するのは 3 点だけ**:

1. 資産の宣言 — `contracts/authz/oracle-seal.lock.json:4-5`(`oracle_commit` / `oracle_commit_semantics`)・`:78-88`(`review_policy` / `reseal_policy`)
2. それを要求する検査器 — `scripts/check_authz_catalog.py:4765-4769`・`:4840-4854`(dict 完全一致)
3. その宣言を置くよう命じた**実装計画書の合格条件** — `docs/features/pg-authz-verification/plan.md:390`

**`docs/features/` は正本ではない**(ハーネス設計書 `:421`)。worklog も同様(同 `:422`)。

### 根拠にしてよい条項・いけない条項

| | |
| --- | --- |
| **根拠にできる** | **`NFR-010`**(要件書 `:848` 測定方法)+ **`NFR-019(b)`**(同 `:930`)。構成検査は **`data-model.md:244` の明示委任**(「**各項目の検査対象集合と合格述語は実装が確定する**」— 範囲確定・PO 裁定 2026-09-09) |
| **根拠にできない** | **`NFR-018`**。対象列挙に**認可構成は入っていない**(要件書 `:890-892`)。承認済み計画書が明文で禁じている — `docs/features/pg-authz-verification-g2/plan.md:854`「**`NFR-018`(b)② を根拠に引かない**」 |

### ゲートの扱い

- **7.2 の確定ゲート表は `docs/` 配下のみ**を列挙する(ハーネス設計書 `:414-423`)。
  **`contracts/` にも `scripts/` にもゲートを課す行は無い。**
- **7.6-3 の前段/後段は「正本文書の変更」についての区別**である(同 `:506`)。
  検査器の合否条件変更が後段を呼ぶのは**その合否条件が正本に書かれている場合**で、
  前例が両方ある(後段 = 同 `:720` の TSK-343・裁定 `Q-1` / 前段 = 同 `:718`・`:722`)。
  **本件の基準は正本に無い**ので、後段を機械的に発火させる条文は無い。
- **それでも必ず掛かる拘束**: `scripts/check_authz_catalog.py`・`contracts/authz/*`・
  `tests/test_check_authz_catalog.py` は**コア領域 tenant-isolation の paths**
  (`.claude/core-areas.json:291-310`)。**敵対レビュー + 人間の逐行確認が必須**
  (ハーネス設計書 `:370`・`:699`)。

---

## 3. 「凍結」を主張している検査の全数 — **4 系統**

| 系統 | 実体 | CI |
| --- | --- | --- |
| **A** | `scripts/check_authz_catalog.py` の `validate_oracle_assets` / `validate_oracle_seal` / **`:4525`** | `tests/test_check_authz_catalog.py:2698` 経由で **harness ジョブ** |
| **B** | `backend/tests/db/authz/mutation_composition.py:1186` `verify_frozen_oracle_unchanged` ほか | **backend ジョブ**(`contracts/**` のパスフィルタで発火) |
| **C** | `tests/test_check_authz_catalog.py:3345` `test_oracle_reseal_preserves_inputs_and_changes_only_two_asset_digests` | **harness ジョブ**(無条件) |
| **D** | `mcdc-map.json` の `claim_mutant_map.blob_digest` / `failure-injection-points.json` の `source_asset.git_blob_digest` | harness ジョブ |

**`unchanged_frozen_oracle_paths` は現存しない**(`0faab75` で削除。**実測** — 全 `.py` を走査して 0 件)。

**`.github/workflows/ci.yml` に authz 系スクリプトの実行ステップは 1 つも無い**(**実測** — 0 件)。
**すべて `tests/` 経由でのみ CI に乗っている。**

---

## 4. 重複判定 — **A と B は重複しない**(clone 上の実測)

| 実験 | 操作 | A | B |
| --- | --- | --- | --- |
| E0 | 無改変 | GREEN | GREEN |
| **E1** | **`oracle_commit` を、8 入力 blob が同一の別コミットへ前進** + 再封印 | **RED** | **GREEN** |
| **E2** | `oracle_commit` を入力が存在しない古いコミットへ + 定数も追随(= 定数を実質無効化した模擬) | GREEN | **RED**(`oracle commit上のblob を取得できない`) |
| **E3** | `verification-evidence.json` の `residual_risks[0].handoff_owner` を改ざん + 再封印 | **GREEN** | **RED**(`承認済みのoracle意味本文と不一致`) |
| **E4** | `boundary-proposal.json` の `pending_human_reviews[0].alternative_value` を 7→999 + 再封印 | RED | **RED** / **C は GREEN** |

### `:4525` が単独で担っている性質(1 対 1 の対応表)

| `:4525` が導く性質 | backend 側の対応 | 覆われるか |
| --- | --- | --- |
| (a) `boundary_proposal` の `oracle_commit == seal.oracle_commit` | `_verify_current_sealed_assets:1136` | **✅ 対応** |
| (b) 6 資産すべてが同じ `oracle_commit` を持つ | 同上(6 資産をループ `:1133-1137`) | **✅ 対応** |
| (c) その commit に記録どおりの 8 入力 blob が存在する | `_verify_oracle_input_assets:1112-1119` | **✅ 対応**(**backend の方が強い** — A-2 の fail-open が無い) |
| **(d) その `oracle_commit` が `0cf994f4…` ちょうどであること** | **無し。** `_oracle_seal_meaning_body:1064` と `_oracle_meaning_body:995` が **`oracle_commit` を明示的に pop している**(**実測**) | **❌ 覆われない** |

**(d) は理論上の穴ではない。**(**作成者が実測**)

```
seal.oracle_commit = 0cf994f4…
8 入力のうち oracle_commit と HEAD で blob が同一なもの: 8 件 / 8 件
```

**`contracts/authz/` の 8 入力を触らないコミットはすべて候補になる**ので、
**該当するコミットは履歴上多数ある**。**ポインタを別コミットへ書き換えて再封印しても
backend は green のまま通り、止めているのは検査器の定数だけである。**

### C は B にほぼ完全に包含され、しかも弱い

C-1〜C-5 はすべて B-1〜B-5 に包含される。**C-4 は B-4 より弱く、`E4` で
「B が捕まえる改ざんを C は通す」ことが実証された。**
**C を消しても backend ジョブが走る限り守られなくなる性質は無い。逆に B を消して C を残すと `E4` が抜ける。**

**ただし C は harness ジョブで無条件に走り、B は backend ジョブでパスフィルタ依存**である点が違う
(`.github/workflows/ci.yml` の `backend` フィルタは `backend/**` / `contracts/**` / `ci.yml`)。

---

## 5. 副産物の欠陥 3 件

### 5-1. `A-2` の fail-open(**定数を外すと同時に露出する** — 実測)

`scripts/check_authz_catalog.py:4798`(**実測で現物を確認**):

```python
if result.returncode == 0 and result.stdout.strip() != digest:
    raise CatalogError(f"{path_text}: oracle commit 上の blob が不一致")
```

**`git rev-parse` が失敗したとき(returncode ≠ 0)は何も起きない。**
**`oracle_commit` が到達不能なコミットや、そのパスを含まないコミットを指していると、
入力ベースラインの照合が丸ごと黙って飛ぶ。**
**いまは `:4525` の定数照合が先に赤くなるので表に出ていない**(`E2` が実証)。

### 5-2. `C` が `B` に包含され、しかも弱い(上記 4)

### 5-3. `.github/workflows/ci.yml` に authz 系スクリプトの実行ステップが無い

**すべて `tests/` 経由**。スクリプト単体を CI が直接叩く経路は無い。
**本件の射程かは別途判断**(検査の実効には影響しないが、`H-85` の連鎖の見え方に効く)。

---

## 6. 台帳の既存項目 — **`H-85` が本件の上位型**(採番済み・**未対応**)

`docs/development/harness-evaluation.md:745` **`H-85`**
「**oracle の入力凍結が、正本の 1 文字の変更を 8 資産 + ハーネステストの更新へ拡大する**」

- 同 `:773-777` — 「**oracle 先行固定は…正しい規律**であり、**凍結そのものを緩めてはならない**。
  一方で **凍結の範囲が広すぎると…改訂タスクの見積もりが破綻する**」
- **対応案②** 同 `:789-790` — 「**派生資産が母集合の blob digest を直接固定するのをやめ、
  母集合側の単一の版識別子を参照する…(digest の連鎖を 1 段に縮める)**」
- **状態: 未対応**(同 `:793`)

**TSK-379 が 4 段の連鎖を手で追ったのは、まさにこの型である。**

**本件の候補**(同 `:2673`「2 つの機械検査が正面から矛盾し…」)の**対応案(b)**
(同 `:2711`)が「**「凍結」を謳う検査には、正当な更新経路を必ず 1 本定義させる**」で、
**受け取り先が本タスク**と名指しされている(同 `:2708`)。

**関連候補**: 同 `:1755`(`H-85` の連鎖の実行手順が正本にもヘルプにも無い)/
`:1790`(`source_text_digest` が一意でない)/ `:1810`(ハーネス設計書の `contracts/` 記述の食い違い)。

---

## 7. 設計に効く制約(実測にもとづく)

1. **「凍結を緩めてはならない」は台帳の既定**(`H-85` `:773-777`)。
   **定数を外すだけの案は、(d) の性質を失う**ことを明示して裁定を仰ぐ必要がある。
2. **朝に一度、この領域で防御を落としている**
   (`docs/worklog/2026-09-13-merge-gate-clause.md:657-689`)。
   **設計変更の前後で同じ物差しの負例を測ること。**
3. **定数を外すなら `A-2` の fail-open を対で直す**(5-1)。
4. **更新経路の置き場を決めない限り、資産の中だけの宣言が 1 つ増えるだけになる**(2)。

## 未解決・申し送り

- **① ポインタを固定し続けるか、動かせるようにするか**(= (d) の性質を残すか捨てるか)。**PO 裁定が要る。**
- **② 更新経路の置き場**。正本に条文を新設するのか、資産内宣言のままにするのか。**PO 裁定が要る。**
- **③ 射程**: `A-2` の fail-open / `C` の整理 / `ci.yml` / `H-85` 対応案② まで踏み込むか。**PO 裁定が要る。**
- **`oracle_commit_semantics = "last_committed_step_4_input_baseline"` の意味を定めた一次記録は無い**
  (decision-tracer が「不明」と判定)。現行の解釈は事後に書かれた 2 つの読みだけである。
- **`review_policy` / `reseal_policy` の 3 キーを決めた一次記録も無い**(同上)。
  変更するなら典拠は資産と旧実装計画書 `docs/features/pg-authz-verification/plan.md:390` しかない。
