---
feature: data-model-v0-2
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5
branch: feature/data-model-v0-2
created: 2026-09-09
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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
| **書き込み可能スキーマを `search_path` から外す** | 反証されていない | **維持するが表現を精密化する** — 凍結 DDL は `authz_private` / `management_private` を `search_path` に含めており(いずれも関数所有ロールが所有 = そのロールから見れば書き込み可能)、**逐語のまま維持すると資産と矛盾する**。実測では `schemas` の `create_role_ids` が全件 `[]` で、**`app_role` は `USAGE` だけを持つ**。→ 正確な条件は「**呼び出しロールが `CREATE` を持つスキーマを含めない**」(2 周目 `P1-6`) |
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
| **製品**(正本) | **集計値** | **`FR-034/認可行列/チーム集計(打撃・投球成績)`** と **`FR-034/認可行列/↳ 内容`**(粒度を「チーム合算の打撃・投球の率指標」と定義)/ **`FR-041`**(共有の受入基準 — 突合は集計値の比較まで)/ **`1.2`**(用語「共有グループの参加テナント」— 付与範囲の集計データを相互に参照する)。**行番号では引かない**(正本 `:26` の引用規約 — 2 周目 `P1-7`) |
| **probe**(凍結資産) | 認可済みの**業務行** | `aggregation_contract: none` — **probe は集計を模していない**(認可の検証が目的) |

**三者不一致ではなく、probe と製品を同じ層として比べていた**のが誤りだった。
正本の「返す列を集計値に限定」(`:479` / `:484`)は**要件どおりで正しく、是正しない**。
`:1349`(「選手の集計だけを返す」)・`:1882`(`P-47`「共有経路は集計値のみ」)も**維持する**。

**PO 裁定 2026-09-09**: ② を取り下げる。**代わりに層の違いを 1 行明記する**(下記ステップ 2)。

### 射程外(**`H-68` 対策 — 輪に入らないため**)

| 項目 | 送り先 | 理由 |
| --- | --- | --- |
| **定義の言い換えによる重複** | **[TSK-352](https://app.notion.com/p/3d693b75e68781f5a762dbf173379773)**(ステップ 4 で 12-8 節へ実 ID を書く) | **正本自身が「原理的に尽きない」と書いている**(`:2775-2778`「13 周目までに 98 件を是正したが毎周 5〜6 件出る」「走査は字面を探すが、残滓は言い換えで残る」)。本タスクへ入れると **TSK-342 と同じ 13 周の輪**に入る |
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
| `.claude/core-areas.json` | `guard_paths` へ新設 2 パスを追加(ステップ 6) | **6.3 規則⑤(敵対レビュー + 人間承認)** |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **追記の判断は /pr のクローズ処理で行う** | PR レビュー(`H-*` の追記では版を上げない — 7.6-3 前段) |
| `docs/requirements/**` / `docs/adr/**` / `docs/ops/**` / `docs/development/dev-harness-design-2026-08-07.md` / `contracts/**` / `backend/**` / `frontend/**` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| `tests/fixtures/data-model-source.txt` | 是正後の本文とバイト一致させる |
| `scripts/design_relations/fixture-sha256-data-model.txt` | SHA-256 を追随 |
| `tests/test_data_model_fixture.py` | **新設** — fixture と正本のバイト一致・SHA-256 の一致を検査(ステップ 6) |
| `scripts/check_data_model_scan.py` | **新設** — 走査語を定数に固定し、走査出力と分類表を exact-set 突合(ステップ 4) |
| `tests/test_check_data_model_scan.py` | **新設** — 走査スクリプトの負例テスト(走査語を減らすと red) |
| `.claude/core-areas.json` | `guard_paths` へ新設 2 パスを追加(ステップ 6・**6.3 規則⑤**) |
| `tests/test_core_guard.py` | 新設 2 パスの登録検査を追随(ステップ 6) |
| `docs/features/data-model-v0-2/{plan,scan-table}.md` | feature 作業ディレクトリ(記録・正本ではない) |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域**

`docs/design/data-model.md` は `.claude/core-areas.json` の **5 領域すべて**に登録済み。
**core-guard が発火する**ため**敵対レビュー + 人間の逐行確認(PR 作成者以外)が必須**。
`tests/fixtures/data-model-source.txt` と `fixture-sha256-data-model.txt` は `guard_paths` 収載。

### 7.3 の正規順序に従う(1 周目 `P1-4` / 2 周目 `P1-1` の是正)

設計書 7.3 の順序は **`draft` → `in-review`(敵対レビューを反復)→ 人間承認 → `approved`**。
**`approved`・版・変更履歴の確定行・索引の版は確定ゲート自身の終端処理**であり、
**「`/finalize-doc` 通過後の番号付きステップ」には置けない**(2 周目 `P1-1`)。

**さらに `scripts/check_docs_status.py` は frontmatter と `docs/README.md` の状態・版・最終更新を突合する**
(実測 — `INDEX_RELATIVE_PATH` と `index_status` / `index_version` / `index_updated`)。
したがって **`in-review` へ落とすときは索引も同時に `in-review` へ落とす**必要がある。

**確定した順序**:

| 段 | 何をするか | 状態 |
| --- | --- | --- |
| **ステップ 1** | 正本と**索引の両方**を `in-review` へ。射程宣言(7.3-7)と変更履歴の**起案行**を置く | `in-review` |
| **ステップ 2〜4** | 本文の是正(`search_path` / 層の明記 / 12-8 節の受け取り先) | `in-review` |
| **確定ゲート**(`/finalize-doc`) | 敵対レビューを反復(**反映周コミットは `反映<r>周目`**)→ **人間承認** → **その中で `approved`・版 v0.2・変更履歴の確定行・索引の版を確定する** | `in-review` → `approved` |
| **ステップ 5〜6** | 退行 fixture とその検査の新設・コア領域への登録(**確定後の本文に対して固定する**) | `approved` |

**ステップ 5〜6 を確定ゲート後に置くのは、fixture が確定した本文とバイト一致する必要があるため**
(TSK-342 が 4 周目 `P1-1` で同じ順序を指摘され是正した形を踏襲)。

### `H-79` 対策は走査自体をスクリプトに固定する(1 周目 `P1-3` / 2 周目 `P1-3` の是正)

**計画作成時に私(Claude)が字面検索で 2 箇所を取りこぼした**(`:1349`「集計**だけ**を返す」・
`:1882`「集計値**のみ**」)。**走査語を計画文中に書くだけでは、実装者が語を狭めれば通る**(2 周目 `P1-3`)。

→ **走査を `scripts/check_data_model_scan.py` として新設し、走査語をスクリプトの定数に固定する。**

| 固定するもの | 値 |
| --- | --- |
| 入力パス | `docs/design/data-model.md`(固定) |
| 走査語(**スクリプトの定数**) | `search_path` / `一時スキーマ` / `pg_temp` / `完全修飾` / `名前解決` |
| 分類表のパス | `docs/features/data-model-v0-2/scan-table.md`(固定) |
| 分類の値域(**閉じた集合**) | `是正済み` / `要求側` / `無関係` |

**検査の内容**:

1. **走査語ごとの出現行の全数**を計算し、**分類表の行集合と exact-set 突合**する(**片方でも欠けたら rc=1**)
2. **各行が閉じた 3 区分のいずれか**に分類されている(自由文を許さない)
3. **`要求側` に分類した行が `origin/develop` から未変更**であることを確認する
4. **走査語の集合をスクリプトから減らすと、テストが red になる**(語の集合自体を負例で守る)

**「名前解決」は `:1374` に別概念(選手の名寄せ)としても出る**ので `無関係` 区分を持たせる。
**未分類 0 件ではなく「全出現行の分類完了」を条件にする。**

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
| 1 | **`in-review` へ落とし、射程宣言と起案行を置く** — 正本 frontmatter を `status: in-review` へ。**`docs/README.md` の状態も同時に `in-review` へ**(`check_docs_status.py` が突合するため — 2 周目 `P1-1`)。**射程宣言(7.3-7)を「本書で確定する範囲 / 実装時に確定する範囲」の対**で置き、**本改訂の実変更 3 点すべてを覆う**(2 周目 `P1-2`)。変更履歴に**起案行**を 1 行 | `[機械]` frontmatter が `status: in-review`・**索引の状態も `in-review`**・`uv run python scripts/check_docs_status.py` **green**(frontmatter と索引が一致)・**射程宣言が「本書で確定する範囲」と「実装時に確定する範囲」の 2 つを持つ**・**確定する範囲に 3 点(`search_path` / 層の明記 / 12-8 節の受け取り先)すべてが現れる**・**確定しない範囲に TSK-352 が受け取り先として現れる**・**本文の是正をまだ行っていない** |
| 2 | **`search_path` 契約の是正** — 「一時スキーマを外す」を **`pg_temp` を末尾に明示する**へ(`REJ-003` の `corrected_expectation` と逐語一致)。**「書き込み可能スキーマを外す」は「呼び出しロールが `CREATE` を持つスキーマを含めない」へ精密化**(2 周目 `P1-6` — 逐語のままだと `authz_private` / `management_private` を含む資産と矛盾する) | `[機械]` **`pg_temp` の末尾明示が当該行にある**・「一時スキーマを `search_path` から外す」単独の記述が **0 件**・**「呼び出しロールが `CREATE` を持つスキーマ」相当の条件が同じ行に残っている**(安全条件を落としていない)・**`schemas` の `create_role_ids` が全件 `[]` である資産と矛盾しない**・**`:2437` / `:2661` / `:2670` / `:2750` 相当(要求側)が未変更**。`[手動・外部]` **是正文が `REJ-003` の `corrected_expectation` と逐語一致していることを確認した** |
| 3 | **probe と製品の層の明記** — 3-6 節へ 1 行。**製品は集計値を返す**(`FR-034/認可行列/↳ 内容`・`FR-041`・`1.2` の**安定 ID で引く**)/ **probe の `aggregation_contract: none` は集計を模していないだけ**。**行番号では引かない**(正本 `:26` の引用規約 — 2 周目 `P1-7`) | `[機械]` 3-6 節に層の明記がある・**引用が安定 ID で行われ、`REQ:<行番号>` 形式が 0 件**・`uv run python scripts/check_design_propagation.py` green・**`:479` / `:484` / `:1349` / `:1882` / `:486` / `:528` が未変更**(返却契約は取り下げ) |
| 4 | **走査スクリプトと分類表の新設**(`P1-3`)— `scripts/check_data_model_scan.py` を新設し**走査語 5 つを定数に固定**。`docs/features/data-model-v0-2/scan-table.md` に全出現行を 3 区分(`是正済み` / `要求側` / `無関係`)で分類。**あわせて 12-8 節の受け取り先を TSK-352 の実 ID へ**(`P1-4`) | `[機械]` **走査出力の行集合と分類表の行集合が exact-set 一致**(片方でも欠けたら rc=1)・**分類が閉じた 3 区分**・**`要求側` の行が `origin/develop` から未変更**・**走査語をスクリプトから 1 つ減らすとテストが red**・**12-8 節に TSK-352 が受け取り先として書かれている**・入力不正で rc=2。`[手動・外部]` 分類の判定を逐行で確認した |
| 5 | **【確定ゲート通過後】退行 fixture と恒久検査の新設**(`P1-5`)— `tests/fixtures/data-model-source.txt` を**確定後の本文**とバイト一致させ、`fixture-sha256-data-model.txt` を更新し、**`tests/test_data_model_fixture.py` を新設** | `[機械]` fixture が正本とバイト一致(`cmp`)・`sha256sum -c` が通る・**新設テストが green**・**負例: fixture を 1 バイト変えると red**・**負例: SHA を書き換えると red**・**本ステップのコミットが正本本文を変更していない** |
| 6 | **【確定ゲート通過後】新設資産をコア領域へ登録**(`P1-5`)— `.claude/core-areas.json` の `guard_paths` へ **`tests/test_data_model_fixture.py`** と **`scripts/check_data_model_scan.py`** を追加し、`tests/test_core_guard.py` を追随させる | `[機械]` `scripts/core_guard.py` の突合が新設 2 パスにマッチ・`uv run pytest tests/test_core_guard.py` green・**登録を外すと発火しないことを負例で示す**・`uv run pytest tests/` green。`[手動・外部]` **`guard_paths` 追加の敵対レビュー + 人間承認**(6.3 規則⑤・逐行確認は PR 作成者以外) |

**確定ゲート(`/finalize-doc`)はステップ 4 の後・ステップ 5 の前**に行い、
**その中で `approved`・版 v0.2・変更履歴の確定行・索引の版を確定する**(2 周目 `P1-1`)。
**反映周コミットにはステップ記法を付けず `反映<r>周目` だけを含める**(設計書 6.1)。

## 5. DoD(受け入れ基準)

- [ ] **`:240` の是正文が `REJ-003` の `corrected_expectation`(`place_pg_temp_explicitly_last`)と逐語一致している**
- [ ] **「書き込み可能スキーマを外す」を「呼び出しロールが `CREATE` を持つスキーマを含めない」へ精密化した** — 逐語のままだと `authz_private` / `management_private` を `search_path` に含む凍結資産と矛盾する(2 周目 `P1-6`)。**安全条件そのもの(呼び出しロールが書けるスキーマを名前解決に載せない)は落としていない**
- [ ] **返却契約(`:479` / `:484` / `:1349` / `:1882`)を変更していない** — 要件書が集計値を定めており、当初の是正方針は誤りだった(PO 裁定 2026-09-09 で取り下げ)
- [ ] **「返す経路を持たない」(`:486` / `:528`)を維持した**
- [ ] **probe と製品の層の違いを 3-6 節に明記した**
- [ ] **`H-79` 対策の走査を `scripts/check_data_model_scan.py` に固定した** — **走査語 5 つはスクリプトの定数**であり、入力パス・分類表パスも固定。**走査出力の行集合と分類表の行集合が exact-set 一致**し、**走査語を 1 つ減らすとテストが red**(2 周目 `P1-3` — 走査語の集合を自分で狭めれば通る形を閉じた)
- [ ] **「要求側」に分類した行を変更していない**
- [ ] **12-8 節の申し送りが本改訂を自己参照していない**。PO 裁定を記録し、**受け取り先を TSK-352 の実 ID で書いた**(「未定(要起票)」を残していない — 2 周目 `P1-4`)
- [ ] **7.3 の正規順序に従った** — ステップ 1 で **正本と索引の両方**を `in-review` へ(`check_docs_status.py` が突合する)→ ステップ 2〜4 で本文を是正 → **確定ゲート(`/finalize-doc`)** → **その中で** `approved`・版 v0.2・変更履歴の確定行・索引の版を確定 → ステップ 5〜6(2 周目 `P1-1`)
- [ ] **射程宣言(7.3-7)をレビュー前の変更履歴行に「本書で確定する範囲 / 実装時に確定する範囲」の対で置き、本改訂の実変更 3 点すべてを覆った**(2 周目 `P1-2`)
- [ ] **版を v0.2 へ繰り上げ、変更履歴に確定行を 1 行記録した**。`docs/README.md` を現行化した
- [ ] **退行 fixture の検査を新設した** — バイト一致と SHA-256 を**恒久的に**検査し、負例 2 種で red
- [ ] **新設した検査 2 本を `.claude/core-areas.json` の `guard_paths` へ登録し、`tests/test_core_guard.py` を追随させた** — **登録を外すと発火しないことを負例で示し**、`guard_paths` 追加の敵対レビュー + 人間承認(6.3 規則⑤)を通した(2 周目 `P1-5`)
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
(cd "$WT" && sha256sum -c scripts/design_relations/fixture-sha256-data-model.txt)  # digest ファイルは既に "<hash>  <path>" 形式(2 周目 `P1-8`)

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
