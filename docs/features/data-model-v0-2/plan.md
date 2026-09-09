---
feature: data-model-v0-2
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5
branch: feature/data-model-v0-2
created: 2026-09-09
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: `docs/design/data-model.md` v0.2 の改訂ゲート(2 件の是正)

## 1. 背景・目的

**Notion タスク**: [TSK-348](https://app.notion.com/p/3d693b75e687816b8911f266f9bb59c5)(高)
**起票元**: [TSK-317](https://app.notion.com/p/3d193b75e687815b83a1faed4848dba2) の計画敵対レビュー 1〜2 周目
**正本**: [`docs/design/data-model.md`](../../design/data-model.md)(**approved v0.1** → **v0.2**)
**要件**: [`NFR-010`](../../requirements/requirements-pitchlog-2026-07-22.md)(テナント分離)/ `FR-034`(認可行列・既定拒否)/ `FR-041`(共有)

### なぜやるか

**approved 正本に、実機で「誤り」と反証済みの契約が残っている。**

TSK-317 の計画敵対レビューで検出した 2 件で、**どちらも 4 行以内の是正**である。
**TSK-317 のマージの前提**(同計画書の DoD 項目)なので、並行で先に閉じる。

### 是正する 2 件(位置は実測済み)

#### ①【P0】`search_path` の契約が、実機で「誤り」と判定された記述のまま

**正本の側**(`docs/design/data-model.md:240` — 3-2 節「既定 `EXECUTE` の剥奪」に続く契約表の 1 行):

```
| **一時スキーマ** | 書き込み可能スキーマ・一時スキーマを `search_path` から外す |
```

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
**台帳 `H-79`(同種の欠陥を全経路へ適用せず字面で検索して取りこぼす)の型。**

#### ② 越境関数の返却契約が三者不一致

| 位置 | 記述 |
| --- | --- |
| `:479`(3-6 節の候補評価表) | 「**返す列を集計値に限定**すれば認可行列と構造的に整合する」 |
| `:484`(同節の採用理由) | 「関数のシグネチャが**返す列を集計値に限定**すれば」 |
| `:486` | 「**生記録・カルテを返す経路を持たない**ことがコードの形として見える」 |
| `:528` | 「**下段 4 行(404 側)は関数が「返す経路を持たない」形**にする。付与の値で分岐させない」 |
| 凍結資産 `ddl-elements.json` の `functions` | `return_contract: "typed_authorized_business_rows"` / **`aggregation_contract: "none"`** |

**同じ実装を一意に導けない。** 「返す列を集計値に限定」と、資産の
「**認可済みの業務行を返し、関数内で集計しない**」が食い違う。
**TSK-317 のステップ 1 は凍結資産の読みで実装済み**(`authorized_shared_rows` が業務行を返す)。

**注意**: 「常に 404 の 4 資源は返す経路を持たない」(`:486`・`:528`)は**いずれの読みでも維持する**。
これは返却の粒度ではなく**資源種別の構造的除外**の話であり、①② と独立している。

### 射程外(**`H-68` 対策 — 輪に入らないため**)

| 項目 | 送り先 | 理由 |
| --- | --- | --- |
| **定義の言い換えによる重複** | **12-8 節の申し送りに残したまま**(PO 裁定 2026-09-09) | **正本自身が「原理的に尽きない」と書いている** — 「13 周目までに 98 件を是正したが毎周 5〜6 件出る」「走査は字面を探すが、残滓は言い換えで残る」「2,800 行規模の自然言語文書では原理的に尽きない」(`:2775-2778`)。本タスクへ入れると **TSK-342 と同じ 13 周の輪**に入る |
| `contracts/authz/` の凍結資産の変更 | **TSK-317 の改訂 3**(`S-1`・`S-5`・`S-7`) | oracle の封印が発火する |
| 設計書 5.1・10.1 の改訂 | **TSK-343** | `data-model.md` の受け取り先表が割り当てている |
| `AUTH-*` と `CATALOG:*` の ID 体系の食い違い | **申し送り(/pr で起票)** | TSK-250 の計画書が期待する `AUTH-*` は実在しない(実測 0 件・全 187 件が `CATALOG:*`) |
| `ddl-elements.json` に DB レベル権限の記述が無い件 | **申し送り(/pr で起票)** | TSK-317 のステップ 4 で顕在化(実測: `ON DATABASE` / `CREATE ON` / `connect` が各 0 件) |

## 2. スコープ

### やること

1. **`:240` の `search_path` 契約を `pg_temp` の末尾明示へ是正**(①)
2. **同種の記述を概念名で全節走査**して取りこぼしを防ぐ(`H-79` 対策)
3. **返却契約を一本化**(②)— 凍結資産の読み(認可済み業務行を返し関数内で集計しない)へ揃える
4. **版を v0.2 へ繰り上げ、変更履歴表に記録**し、`docs/README.md` を現行化
5. **退行 fixture(`tests/fixtures/data-model-source.txt`)と SHA-256 を追随**
6. **7.3 の確定ゲート**を通す(敵対レビュー + 人間承認 — `/finalize-doc`)

### やらないこと

上記「射程外」の 5 項目。とくに **③ 定義の言い換えによる重複は探さない**。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PR レビュー / finalize-doc) |
| --- | --- | --- |
| [`docs/design/data-model.md`](../../design/data-model.md) | **2 件の是正(4 行以内)+ 版を v0.2 へ繰り上げ + 変更履歴 1 行** | **7.3 の確定ゲート**(敵対レビュー + 人間承認 — `/finalize-doc`)。AGENTS.md 絶対規則 4・7.6-3 の決定表「**版繰り上げを伴う構造的変更**はその部分だけ 7.3 の確定ゲートを通す」 |
| [`docs/README.md`](../../README.md) | 索引の版と最終更新日を現行化 | —(常に現行化 — 7.2) |
| [`docs/development/harness-evaluation.md`](../../development/harness-evaluation.md) | **追記の判断は /pr のクローズ処理で行う**(該当時は本節へ宣言を先に追記) | PR レビュー(`H-*` の追記では版を上げない — 7.6-3 前段) |
| `docs/requirements/**` / `docs/adr/**` / `docs/ops/**` / `docs/development/dev-harness-design-2026-08-07.md` / `contracts/**` / `backend/**` / `frontend/**` | **反映なし** | — |

### 正本体系外だが同一 PR で運ぶもの(/pr 突合の別枠宣言)

| ファイル | 変更内容 |
| --- | --- |
| `tests/fixtures/data-model-source.txt` | 是正後の本文とバイト一致させる(退行 fixture) |
| `scripts/design_relations/fixture-sha256-data-model.txt` | SHA-256 を追随 |
| `docs/features/data-model-v0-2/{plan,research}.md` | feature 作業ディレクトリ(記録・正本ではない) |

## 4. 実装方針

### 重さ分類の根拠 — **コア領域**

`docs/design/data-model.md` は `.claude/core-areas.json` の **5 領域すべて**に登録されている
(TSK-342 のステップで登録済み)。**core-guard が発火する**ため、
**敵対レビュー + 人間の逐行確認(PR 作成者以外)が必須**。
あわせて `tests/fixtures/data-model-source.txt` と `fixture-sha256-data-model.txt` は `guard_paths` 収載。

### 是正の位置は実測済み(委任前に確定させた)

| 件 | 是正対象 | `H-79` 対策で走査する概念名 |
| --- | --- | --- |
| ① | **`:240` の 1 行** | 「一時スキーマ」/「`pg_temp`」/「`search_path`」/「名前解決」— 実測で `:238`〜`:245` と `:2437`・`:2661`・`:2670`・`:2750` に出現 |
| ② | **`:479` / `:484`**(集計値に限定)/ **`:486` / `:528`**(返す経路を持たない — **維持する側**) | 「集計値に限定」/「集計は関数に書かない」/「返す経路を持たない」 |

**`:2437`・`:2661`・`:2670`・`:2750` は「`search_path` の乗っ取りが効かないこと」を要求する側**で、
**是正の対象ではない**(要求は正しい)。①の是正は `:240` の**対処方法の記述**だけである。
この区別を機械検査に落とす(下記)。

### 合格条件の書き方

**`[機械]`** と **`[手動・外部]`** に書き分け、**`[手動・外部]` を機械 green の一部として数えない**。
**合格条件を「検査が green」に置かず「割り当てが正しい」に置く**。

### 確定ゲートの周回の見込みと打ち切り基準

**射程を 2 件・4 行以内に絞ったので 1〜2 周で閉じる見込み**である。
**7.3-6 の発火条件**(前周修正起因が 2 周連続で過半)に達した場合は **PO 裁定を起動**する。
**③ を射程へ戻さない**(戻すと TSK-342 の 13 周の輪に入る)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **① `search_path` 契約の是正** — `:240` を `pg_temp` の末尾明示へ。**`REJ-003` の `corrected_expectation`(`place_pg_temp_explicitly_last`)と逐語一致**させる | `[機械]` 正本に「一時スキーマを `search_path` から外す」相当の記述が **0 件**・**`pg_temp` を末尾に明示する記述が本文にある**・**「乗っ取りが効かないことを要求する」側の 4 箇所(`:2437`・`:2661`・`:2670`・`:2750` 相当)を変更していない**。`[手動・外部]` **`REJ-003` の `corrected_expectation` と逐語一致していることを確認した** |
| 2 | **`H-79` 対策の全節走査** — 「一時スキーマ」/「`pg_temp`」/「`search_path`」/「名前解決」の **4 概念名すべてで全文走査**し、同種の記述の取りこぼしが無いことを示す | `[機械]` 4 概念名の**全出現箇所を列挙した表を feature ディレクトリへ置き**、各箇所が「是正済み」「要求側(変更不要)」「無関係」のいずれかに**分類されている**(未分類 0 件)。`[手動・外部]` 分類の判定が正しいことを逐行で確認した |
| 3 | **② 返却契約の一本化** — `:479` / `:484` の「返す列を集計値に限定」を、**凍結資産の読み**(`return_contract: typed_authorized_business_rows` / `aggregation_contract: none` = 認可済み業務行を返し関数内で集計しない)へ揃える。**`:486` / `:528` の「返す経路を持たない」は維持する** | `[機械]` 「集計値に限定」相当の記述が **0 件**・**「集計は関数に書かない」が残っている**・**「返す経路を持たない」が `:486` / `:528` 相当に残っている**・**`contracts/authz/` の差分が 0**。`[手動・外部]` **正本・凍結資産・TSK-317 の計画書が同じ実装を一意に導くことを確認した**(3 者の記述を並べた表を worklog へ) |
| 4 | **版の繰り上げと索引の現行化** — 変更履歴表に v0.2 の行を追記(是正 2 件・起票元・根拠)。`docs/README.md` の版と最終更新日を現行化 | `[機械]` frontmatter の `status: approved` を維持・**変更履歴に v0.2 の行が 1 行**・`uv run python scripts/check_docs_status.py` green・`docs/README.md` の版表記が v0.2 |
| 5 | **退行 fixture と SHA-256 の追随** — `tests/fixtures/data-model-source.txt` を是正後の本文とバイト一致させ、`scripts/design_relations/fixture-sha256-data-model.txt` を更新する。**確定ゲート通過後に行う** | `[機械]` fixture が正本とバイト一致・SHA-256 が一致・`uv run pytest tests/` green・**本ステップのコミットが正本本文を変更していない** |

**確定ゲートは実装ステップの外**で行う(`/finalize-doc`)。**ステップ 5 は確定ゲート通過後**に置く
(TSK-342 が 4 周目 `P1-1` で同じ順序を指摘され是正した形を踏襲する)。
**反映周コミットにはステップ記法を付けず `反映<r>周目` だけを含める**(設計書 6.1)。

## 5. DoD(受け入れ基準)

- [ ] **① `search_path` 契約が `REJ-003` の `corrected_expectation` と逐語一致している**
- [ ] **① の是正で「乗っ取りが効かないことを要求する」側の 4 箇所を変更していない**
- [ ] **`H-79` 対策の全節走査を 4 概念名で行い、全出現箇所を分類した**(未分類 0 件)
- [ ] **② 返却契約を一本化した** — 正本・凍結資産・TSK-317 の計画書が同じ実装を一意に導く
- [ ] **② で「常に 404 の 4 資源は返す経路を持たない」を維持した**
- [ ] **版を v0.2 へ繰り上げ、変更履歴表に 1 行記録した**。`docs/README.md` を現行化した
- [ ] **7.3 の確定ゲートを通した**(敵対レビュー + 人間承認 — `/finalize-doc`)
- [ ] **退行 fixture と SHA-256 を追随させた**(確定ゲート通過後のステップ 5)
- [ ] **`contracts/authz/` の差分が 0**(oracle の封印を発火させていない)
- [ ] **③ 定義の言い換えによる重複を射程へ戻していない**(12-8 節の申し送りのまま)
- [ ] **設計書 5.1・10.1 の差分が 0**(TSK-343 の所有)
- [ ] **申し送りを起票した** — `AUTH-*` と `CATALOG:*` の ID 体系の食い違い / `ddl-elements.json` に DB レベル権限の記述が無い件
- [ ] **コア領域として敵対レビュー + 人間の逐行確認を通っている**(逐行確認は **PR 作成者以外**が行い、**実施記録行を確認者本人が記入**した)

## 6. テスト計画(NFR-019)

**要件が定義する CI のテストは 4 種**((a) 一致性 /(b) 越境 /(c) E2E 主要分岐 /(d) 同期故障系)。

| 種別 | 追加内容 |
| --- | --- |
| **(a)〜(d)** | **追加なし** — 本タスクは正本の文言の是正であり、実装を変えない |
| **文書検査** | `scripts/check_docs_status.py`(status と変更履歴)/ `check_design_propagation.py` / `check_doc_coverage.py` が green |
| **退行(本物の資産)** | `tests/fixtures/data-model-source.txt` と `fixture-sha256-data-model.txt` の一致(ステップ 5)。**TSK-342 が作った既存テストがそのまま効く** |
| **回帰** | `uv run pytest tests/` の既存全件が green(**期待件数のハードコードに触れない**) |

## 7. 検証(このタスクが終わったことの確認方法)

```bash
WT=/home/ymdms/projects/pitchlog-worktrees/feature-data-model-v0-2

# 1. 文書検査
(cd "$WT" && uv run python scripts/check_docs_status.py)
(cd "$WT" && uv run python scripts/check_design_propagation.py)
(cd "$WT" && uv run python scripts/check_doc_coverage.py)

# 2. 退行 fixture と SHA-256
(cd "$WT" && uv run pytest tests/ -q)

# 3. 品質ゲート
(cd "$WT" && uv run ruff check . && uv run ty check)

# 4. 凍結資産と他正本に触れていないこと
git -C "$WT" diff --exit-code origin/develop...HEAD -- contracts/ docs/development/dev-harness-design-2026-08-07.md docs/requirements/ docs/adr/

# 5. 現在地導出
uv run python scripts/feature_status.py
```

**人間が確認すること**: `:240` の是正が `REJ-003` の `corrected_expectation` と逐語一致していること /
`H-79` 対策の走査表の分類 / 返却契約の 3 者(正本・凍結資産・TSK-317 の計画書)が一意に導くこと。

## 8. 進め方

1. 本計画書を**コア領域の敵対レビュー**へ: `python .claude/scripts/codex_run.py review adversarial -`
2. 指摘を反映(1 周ごとに `計画レビュー周回` を +1)→ 収束したら**人間の承認**
3. 承認後 `/implement` でステップ 1 から(件名は `(ステップ k)`)
4. ステップ 4 の後に **`/finalize-doc`** で 7.3 の確定ゲート(**反映周コミットは `反映<r>周目`**)
5. 確定ゲート通過後に**ステップ 5**(退行 fixture と SHA-256)
