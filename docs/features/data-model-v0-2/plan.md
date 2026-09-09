---
feature: data-model-v0-2
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5
branch: feature/data-model-v0-2
created: 2026-09-09
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: `docs/design/data-model.md` v0.2 の改訂ゲート(`search_path` 契約の是正)

## 1. 背景・目的

**Notion タスク**: [TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5)(高)
**起票元**: [TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2) の計画敵対レビュー
**正本**: [`docs/design/data-model.md`](../../design/data-model.md)(**approved v0.1** → **v0.2**)
**要件**: [`NFR-010`](../../requirements/requirements-pitchlog-2026-07-22.md)(テナント分離)/ `FR-034`(認可行列)

### なぜやるか

**approved 正本に、実機で「誤り」と反証済みの契約が 1 行残っている。**

**TSK-317 のマージの前提**(同計画書の DoD 項目)なので、並行で先に閉じる。

### 是正する 1 件

#### 【P0】`search_path` の対処方法が、実機で「誤り」と判定された記述のまま

**正本の側**(`docs/design/data-model.md:240` — 3-2 節の契約表の 1 行):

```
| **一時スキーマ** | 書き込み可能スキーマ・一時スキーマを `search_path` から外す |
```

**この 1 行は 2 つの条件を持つ**(計画レビュー 1 周目 `P1-6` の指摘):

| 条件 | `REJ-003` の判定 | 扱い |
| --- | --- | --- |
| **書き込み可能スキーマを `search_path` から外す** | 反証されていない | **維持する** |
| **一時スキーマを `search_path` から外す** | **`incorrect`** | **是正する** |

**凍結資産の側**(`contracts/authz/rejected-configs.json` の `REJ-003` — 実測値):

| フィールド | 実値 |
| --- | --- |
| `configuration_id` | `SEARCH_PATH_WITHOUT_EXPLICIT_TRAILING_PG_TEMP` |
| `verification_environment` | `postgresql_17_11_real_instance` |
| `candidate_statement` | **`remove_temporary_schema_from_search_path`** |
| `candidate_statement_status` | **`incorrect`** |
| `corrected_expectation` | **`place_pg_temp_explicitly_last`** |
| `observed_result` | **`temporary_relation_hijack_returned_attacker_rows`** |
| `rejection_reason_id` | `IMPLICIT_PG_TEMP_PRECEDES_LISTED_SCHEMAS` |

**正本の記述に従うと一時リレーションによる乗っ取りが成立する。** `pg_temp` を列挙から外すと
**暗黙の `pg_temp` が列挙スキーマより前に来る**のが原因で、正しい対処は**末尾に明示すること**。

**実装側は既に正しい** — `contracts/authz/ddl-elements.json` の関数 3 件の `search_path` は
いずれも末尾 `pg_temp`。`scripts/check_authz_catalog.py` も「末尾が `pg_temp` で出現回数が 1」を検査する。
**食い違っているのは正本の 1 行だけ**である。

**なぜ TSK-342 の確定ゲート 13 周が捕まえなかったか**: 反証が `contracts/authz/` にあってレビュー射程外
だったこと、そして**正本側が `pg_temp` という語を 1 度も使っていない**こと(実測 0 件)。
**台帳 `H-79` の型。**

### 取り下げた項目 — 返却契約(計画レビュー 1 周目で判明)

**当初は「越境関数の返却契約が三者不一致」として是正対象に入れていたが、要件書の実測で撤回した。**

| 層 | 何を返すか | 根拠 |
| --- | --- | --- |
| **製品**(正本) | **集計値** | `REQ:122`「自テナントの**付与範囲の集計データ**を相互に参照する」/ `REQ:630-634` の認可行列が粒度を「**チーム合算の打撃・投球の率指標**」と定義 / `REQ:510`「突合は**集計値の比較まで**」 |
| **probe**(凍結資産) | 認可済みの**業務行** | `aggregation_contract: none` — **probe は集計を模していない**(認可の検証が目的) |

**三者不一致ではなく、probe と製品を同じ層として比べていた**のが誤りだった。
正本の「返す列を集計値に限定」(`:479` / `:484`)は**要件どおりで正しく、是正しない**。
`:1349`(「選手の集計だけを返す」)・`:1882`(`P-47`「共有経路は集計値のみ」)も**維持する**。

**PO 裁定 2026-09-09**: ② を取り下げる。**代わりに層の違いを 1 行明記する**(下記ステップ 2)。

### 射程外(**`H-68` 対策 — 輪に入らないため**)

| 項目 | 送り先 | 理由 |
| --- | --- | --- |
| **定義の言い換えによる重複** | **12-8 節の申し送り**(ただし**受け取り先の記述を是正する** — ステップ 4) | **正本自身が「原理的に尽きない」と書いている**(`:2775-2778`「13 周目までに 98 件を是正したが毎周 5〜6 件出る」「走査は字面を探すが、残滓は言い換えで残る」)。本タスクへ入れると **TSK-342 と同じ 13 周の輪**に入る |
| `contracts/authz/` の凍結資産の変更 | **TSK-317 の改訂 3**(`S-1`・`S-5`・`S-7`) | oracle の封印が発火する |
| 設計書 5.1・10.1 の改訂 | **TSK-343** | `data-model.md` の受け取り先表が割り当てている |
| `AUTH-*` と `CATALOG:*` の ID 体系の食い違い | **申し送り(/pr で起票)** | TSK-250 の計画書が期待する `AUTH-*` は実在しない(実測 0 件・全 187 件が `CATALOG:*`) |
| `ddl-elements.json` に DB レベル権限の記述が無い件 | **申し送り(/pr で起票)** | TSK-317 のステップ 4 で顕在化(実測: `ON DATABASE` / `CREATE ON` / `connect` が各 0 件) |

## 2. スコープ

### やること

1. **`:240` の是正** — 「一時スキーマを外す」を `pg_temp` の末尾明示へ。**「書き込み可能スキーマを外す」は維持**
2. **probe と製品の層の違いを 1 行明記**(② の取り下げに伴う予防)
3. **`H-79` 対策の全節走査** — **概念名で走査し、走査結果と分類表を exact-set で突合する**
4. **12-8 節の申し送りの受け取り先を是正**(射程外裁定を正本側にも記録し、自己参照を解消)
5. **版を v0.2 へ繰り上げ**(**7.3 の正規順序に従う** — `in-review` → 敵対レビュー → 人間承認 → `approved`)
6. **退行 fixture の検査を新設**(既存テストは登録しか見ておらず、バイト一致を検査していない)

### やらないこと

上記「射程外」の 5 項目と、**返却契約の是正**(取り下げ済み)。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PR レビュー / finalize-doc) |
| --- | --- | --- |
| [`docs/design/data-model.md`](../../design/data-model.md) | **`:240` の是正 + 層の明記 1 行 + 12-8 節の受け取り先の是正 + 射程宣言(7.3-7)+ 版を v0.2 へ + 変更履歴 1 行** | **7.3 の確定ゲート**(敵対レビュー + 人間承認 — `/finalize-doc`)。AGENTS.md 絶対規則 4・7.6-3「**版繰り上げを伴う構造的変更**はその部分だけ 7.3 の確定ゲートを通す」 |
| [`docs/README.md`](../../README.md) | 索引の版と最終更新日を現行化 | —(常に現行化 — 7.2) |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **追記の判断は /pr のクローズ処理で行う** | PR レビュー(`H-*` の追記では版を上げない — 7.6-3 前段) |
| `docs/requirements/**` / `docs/adr/**` / `docs/ops/**` / `docs/development/dev-harness-design-2026-08-07.md` / `contracts/**` / `backend/**` / `frontend/**` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| `tests/fixtures/data-model-source.txt` | 是正後の本文とバイト一致させる |
| `scripts/design_relations/fixture-sha256-data-model.txt` | SHA-256 を追随 |
| `tests/test_data_model_fixture.py` | **新設** — fixture と正本のバイト一致・SHA-256 の一致を検査(ステップ 6) |
| `docs/features/data-model-v0-2/{plan,scan-table}.md` | feature 作業ディレクトリ(記録・正本ではない) |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域**

`docs/design/data-model.md` は `.claude/core-areas.json` の **5 領域すべて**に登録済み。
**core-guard が発火する**ため**敵対レビュー + 人間の逐行確認(PR 作成者以外)が必須**。
`tests/fixtures/data-model-source.txt` と `fixture-sha256-data-model.txt` は `guard_paths` 収載。

### 7.3 の正規順序に従う(計画レビュー 1 周目 `P1-4` の是正)

設計書 7.3 の順序は **`in-review` → 敵対レビュー → 人間承認 → `approved`・版数・変更履歴・索引確定**。
当初計画は `approved` のまま版と変更履歴を確定してから `/finalize-doc` に回しており**逆転していた**。

→ **ステップ 1〜4 で `status: in-review` へ落として本文を是正**し、**`/finalize-doc` の通過後に
ステップ 5 で `approved`・版・変更履歴・索引を確定**する。
**7.3-7 の射程宣言は、既存正本の改訂ではレビュー前の変更履歴行に置く**(同節)。

### `H-79` 対策は「概念で走査 → exact-set 突合」にする(`P1-3` の是正)

**計画作成時に私(Claude)が字面検索で 2 箇所を取りこぼした**(`:1349`「集計**だけ**を返す」・
`:1882`「集計値**のみ**」)。**字面の一覧を人が作る形では `H-79` を閉じない。**

→ ステップ 3 は **走査コマンドの出力と分類表を機械で exact-set 突合**する。
**走査語を計画書に固定**し(下表)、**その出力行の全数が表に現れることを検査**する。

| 概念 | 走査語(この集合を機械で固定する) |
| --- | --- |
| `search_path` の対処 | `search_path` / 一時スキーマ / `pg_temp` / 完全修飾 / 名前解決 |

**「名前解決」は `:1374` に別概念(選手の名寄せ)としても出る**ので、分類に
「**無関係**」の区分を持たせ、**未分類 0 件**ではなく**全出現行の分類完了**を条件にする。

### 合格条件の書き方

**`[機械]`** と **`[手動・外部]`** に書き分け、**`[手動・外部]` を機械 green の一部として数えない**。
**「検査が green」ではなく「割り当てが正しい」に置く。**

### 確定ゲートの周回の見込みと打ち切り基準

**射程を 1 件・1 行に絞ったので 1〜2 周で閉じる見込み**である。
**7.3-6 の発火条件**(前周修正起因が 2 周連続で過半)に達したら **PO 裁定を起動**する。
**取り下げた ② と射程外の残滓を射程へ戻さない。**

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`status` を `in-review` へ落とし、射程宣言と変更履歴の起案行を置く**(7.3 の正規順序 — `P1-4`)。**射程宣言(7.3-7)は「本改訂で確定する範囲 = `search_path` の対処方法の是正と層の明記」「確定しない範囲 = 定義の言い換えによる重複」**を書く | `[機械]` frontmatter が `status: in-review`・**変更履歴に起案行が 1 行**・**射程宣言が変更履歴行に紐づいている**・`uv run python scripts/check_docs_status.py` green・**本文の是正をまだ行っていない**(`:240` が未変更) |
| 2 | **`:240` の是正と層の明記** — ① 「一時スキーマを外す」を **`pg_temp` を末尾に明示する**へ(`REJ-003` の `corrected_expectation` と逐語一致)。**「書き込み可能スキーマを `search_path` から外す」は維持**(`REJ-003` は反証していない — `P1-6`)② **probe と製品の層の違いを 1 行明記**(製品は集計値を返す〔`REQ:122`・`REQ:630-634`〕/ probe の `aggregation_contract: none` は集計を模していないだけ) | `[機械]` **`:240` 相当の行に「書き込み可能スキーマを外す」が残っている**・**同じ行に `pg_temp` の末尾明示がある**・「一時スキーマを `search_path` から外す」単独の記述が **0 件**・**`:479` / `:484` / `:1349` / `:1882` / `:486` / `:528` が未変更**(返却契約は取り下げ)・**層の明記が 3-6 節にある**。`[手動・外部]` **是正文が `REJ-003` の `corrected_expectation` と逐語一致していることを確認した** |
| 3 | **`H-79` 対策の全節走査** — 5 つの走査語(`search_path` / 一時スキーマ / `pg_temp` / 完全修飾 / 名前解決)で全文走査し、`docs/features/data-model-v0-2/scan-table.md` に**全出現行**を「是正済み / 要求側(変更不要)/ 無関係」で分類する | `[機械]` **走査コマンドの出力行集合と分類表の行集合が exact-set 一致**(表を自作しても通らない)・**全出現行が 3 区分のいずれかに分類されている**・**「要求側」に分類した行が未変更**であることを機械で確認。`[手動・外部]` 分類の判定が正しいことを逐行で確認した |
| 4 | **12-8 節の申し送りの受け取り先を是正**(`P1-2`)— 「定義の言い換えによる重複」の行が**本改訂を受け取り先として自己参照しないよう**、**PO 裁定 2026-09-09 で射程外とした事実と、受け取り先が未定であること**を記録する | `[機械]` 12-8 節の当該行に**本改訂(v0.2)を受け取り先とする記述が 0 件**・**PO 裁定の日付と射程外の判断が記録されている**・**受け取り先が「未定(要起票)」と明示されている** |
| 5 | **【確定ゲート通過後】`approved` 化と版・索引の確定** — `status: approved` へ戻し、変更履歴を v0.2 の確定行へ、`docs/README.md` の版と最終更新日を現行化 | `[機械]` frontmatter が `status: approved`・**変更履歴に v0.2 の確定行が 1 行**(周回数・指摘件数・承認者・承認日)・`docs/README.md` の版表記が v0.2・`check_docs_status.py` green |
| 6 | **【確定ゲート通過後】退行 fixture と検査の新設**(`P1-5`)— `tests/fixtures/data-model-source.txt` を正本とバイト一致させ、`fixture-sha256-data-model.txt` を更新し、**`tests/test_data_model_fixture.py` を新設**して**バイト一致と SHA-256 の一致を恒久的に検査**する | `[機械]` fixture が正本とバイト一致・SHA-256 が一致・**新設テストが green**・**負例: fixture を 1 バイト変えると red**・**負例: SHA を書き換えると red**・`uv run pytest tests/` green・**本ステップのコミットが正本本文を変更していない** |

**確定ゲート(`/finalize-doc`)はステップ 4 の後・ステップ 5 の前**に行う。
**反映周コミットにはステップ記法を付けず `反映<r>周目` だけを含める**(設計書 6.1)。

## 5. DoD(受け入れ基準)

- [ ] **`:240` の是正文が `REJ-003` の `corrected_expectation`(`place_pg_temp_explicitly_last`)と逐語一致している**
- [ ] **「書き込み可能スキーマを `search_path` から外す」を維持した**(`REJ-003` は反証していない)
- [ ] **返却契約(`:479` / `:484` / `:1349` / `:1882`)を変更していない** — 要件書が集計値を定めており、当初の是正方針は誤りだった(PO 裁定 2026-09-09 で取り下げ)
- [ ] **「返す経路を持たない」(`:486` / `:528`)を維持した**
- [ ] **probe と製品の層の違いを 3-6 節に明記した**
- [ ] **`H-79` 対策の全節走査を 5 語で行い、走査出力と分類表が exact-set 一致している**(表の自作では通らない)
- [ ] **「要求側」に分類した行を変更していない**
- [ ] **12-8 節の申し送りが本改訂を自己参照していない**。PO 裁定と受け取り先未定を記録した
- [ ] **7.3 の正規順序に従った** — `in-review` → 敵対レビュー → 人間承認 → `approved`・版・変更履歴・索引
- [ ] **射程宣言(7.3-7)をレビュー前の変更履歴行に置いた**
- [ ] **版を v0.2 へ繰り上げ、変更履歴に確定行を 1 行記録した**。`docs/README.md` を現行化した
- [ ] **退行 fixture の検査を新設した** — バイト一致と SHA-256 を**恒久的に**検査し、負例 2 種で red
- [ ] **`contracts/authz/` の差分が 0**(oracle の封印を発火させていない)
- [ ] **定義の言い換えによる重複を射程へ戻していない**
- [ ] **設計書 5.1・10.1 の差分が 0**(TSK-343 の所有)
- [ ] **申し送りを起票した** — `AUTH-*` と `CATALOG:*` の ID 体系の食い違い / `ddl-elements.json` に DB レベル権限の記述が無い件 / **定義の言い換えによる重複の受け取り先**
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(逐行確認は **PR 作成者以外**が行い、**実施記録行を確認者本人が記入**した)

## 6. テスト計画(NFR-019)

**要件が定義する CI のテストは 4 種**((a) 一致性 /(b) 越境 /(c) E2E 主要分岐 /(d) 同期故障系)。

| 種別 | 追加内容 |
| --- | --- |
| **(a)〜(d)** | **追加なし** — 本タスクは正本の文言の是正であり、実装を変えない |
| **文書検査** | `check_docs_status.py` / `check_design_propagation.py` / `check_doc_coverage.py` が green |
| **退行(本物の資産)** | **`tests/test_data_model_fixture.py` を新設**(ステップ 6)。**既存テストは登録と `guard_paths` しか見ておらず、fixture と正本のバイト一致を検査していない**(実測 — `test_core_guard.py:41-42`・`:241-246` にパスが現れるだけ)。**負例 2 種**(fixture の 1 バイト改変 / SHA の書き換え)で red |
| **回帰** | `uv run pytest tests/` の既存全件が green(**期待件数のハードコードに触れない**) |

## 7. 検証(このタスクが終わったことの確認方法)

```bash
WT=/home/ymdms/projects/pitchlog-worktrees/feature-data-model-v0-2

# 1. 文書検査
(cd "$WT" && uv run python scripts/check_docs_status.py && uv run python scripts/check_design_propagation.py && uv run python scripts/check_doc_coverage.py)

# 2. 退行 fixture の恒久検査(新設)
(cd "$WT" && uv run pytest tests/test_data_model_fixture.py -q)

# 3. バイト一致と SHA-256 を直接確認
(cd "$WT" && cmp docs/design/data-model.md tests/fixtures/data-model-source.txt && echo "バイト一致 OK")
(cd "$WT" && sha256sum -c <(printf '%s  %s\n' "$(cat scripts/design_relations/fixture-sha256-data-model.txt)" tests/fixtures/data-model-source.txt))

# 4. 品質ゲートと回帰
(cd "$WT" && uv run ruff check . && uv run ty check && uv run pytest tests/ -q)

# 5. 他正本と凍結資産に触れていないこと
git -C "$WT" diff --exit-code origin/develop...HEAD -- contracts/ docs/development/dev-harness-design-2026-08-07.md docs/requirements/ docs/adr/ docs/ops/

# 6. 現在地導出
uv run python scripts/feature_status.py
```

**人間が確認すること**: 是正文が `REJ-003` の `corrected_expectation` と逐語一致していること /
走査表の分類(とくに「要求側」と「無関係」の判定)/ 層の明記が要件と整合していること。

## 8. 進め方

1. 本計画書を**コア領域の敵対レビュー**へ: `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(1 周ごとに `計画レビュー周回` を +1)→ 収束したら**人間の承認**
3. 承認後 `/implement` でステップ 1〜4(件名は `(ステップ k)`)
4. **`/finalize-doc`** で 7.3 の確定ゲート(**反映周コミットは `反映<r>周目`**)
5. 確定ゲート通過後に**ステップ 5〜6**
