---
feature: frozen-baseline-ledger
type: research
date: 2026-09-20
---

# 調査メモ: 凍結基準を検査器から台帳へ移す(TSK-421)

**表記**: 行番号はすべて 2026-09-20 に実ファイルを読んで採番した。木が 2 つあるので記号で区別する。

- **[D]** = `origin/develop` = `5e9ffd9`(本 worktree `feature-frozen-baseline-ledger`)
- **[A]** = `fix/oracle-input-baseline` = `76e98ff`(PR #63 の失敗ブランチ。**資料として保存・削除しないこと**)
- **[P]** = 実験用クローン `<scratchpad>/probe`(ブランチ `feature/probe-frozen`・`5e9ffd9..8c03e5e` の 3 コミット)。要件書 1 文字変更の連鎖を green まで再現した。**本体リポジトリは一切変更していない**

## 問い

1. 凍結基準 4 件はそれぞれ何を主張しているか。**内容の同一性**か**履歴上の地点**か
2. `H-85` の 2 段コミットは、4 件を台帳へ移せば消えるか
3. 要件書を 1 文字変えると何が壊れ、最小何コミットで閉じるか
4. PR #63 はなぜ 3 周連続 `P0` だったか。「落ちたのは `R-2` とその周辺だけ」は正しいか
5. 失敗ブランチの実装のうち何が再利用でき、何が作り直しか

## 結論(要約)

- **4 件のうち「履歴上の地点」を要求しているものは 0 件。** 4 件とも `git show <rev>:<path>` による内容取得か文字列一致で、**到達可能性(ancestry)を検査するコードは 1 行も無い**。
- **`H-85` の 2 段コミットは、4 件を台帳へ移しても消えない。** 2 段を強制しているのは `requirement-claims.json` の `input_manifest.commit` と `oracle-seal.lock.json` の `oracle_commit` という**資産側の 2 つのポインタ**で、**いずれも本タスクの 4 定数に含まれない**。
- **要件書 1 文字の変更は 20 ファイル・最小 3 コミット**で閉じる([P] で green まで到達)。動く検査器定数は **`ORACLE_INPUT_BASELINE_COMMIT` の 1 件だけ**。
- **「落ちたのは `R-2` とその周辺だけ」は記録から確認も否認もできない。** PR #63 の 3 周目は `P0` 2 / `P1` 2 の計 4 件だが、**内容が残っているのは 1 件だけ**。
- **失敗ブランチの台帳スキーマは v1.15 の 7.7-4 に対して設計されており、[D] の v1.16 7.7-2 を満たさない。** `declarations` の 4 キー構造は再利用できるが、記録のレコード構造は作り直しが要る。

---

## 詳細と典拠

### 0. 本タスクの前提の訂正 — 起案時に私が書いた機構は誤りだった

**誤り**: 「要件書を改訂すると `STEP2_BASE_REVISION` も進める必要があり、進める唯一の方法は `mutation_composition.py:36` の書き換えなので 7.7-1② に反する」

**実測([P] の最終差分)**: 要件書 1 文字変更 → 連鎖を全部直して green に到達した 20 ファイルのうち、**動いた検査器定数は `ORACLE_INPUT_BASELINE_COMMIT` の 1 件だけ**。

```
-ORACLE_INPUT_BASELINE_COMMIT = "24ef4fcc682b42b504edc1d6264d380760c54929"
+ORACLE_INPUT_BASELINE_COMMIT = "a67d4771da302a2ef98d54680627de63e5cabe4e"
```

**`STEP2_BASE_REVISION` は動いていない。** 理由は [D] `backend/tests/db/authz/mutation_composition.py:1056-1076` `_oracle_seal_meaning_body` が seal から `oracle_commit` / `input_assets[].git_blob_digest` / `sealed_assets[].canonical_sha256` を**除去**してから比較し、同 `:983-992` `_oracle_meaning_body` が各資産から `oracle_context.oracle_commit` を**除去**してから比較するため。**可動ポインタを除いた意味本文は要件書改訂で変わらない。**[P] で連鎖修復後に `verify_frozen_oracle_unchanged()` が `OK` を返すことを実測した。

**訂正後の機構**(結論は変わらない):

1. 要件書を改訂する → 7.7-1 は発動しない(変わるのは凍結対象であって基準ではない)
2. 連鎖を解消するため **`ORACLE_INPUT_BASELINE_COMMIT` を進める** → **ここで 7.7-1 が発動する**(値の変更)
3. 7.7-1 が ①宣言を資産側へ ②検査器ソースへ直書きしない の両方を要求する
4. 宣言の実体は現在存在しない → TSK-306 は自分で作るか本タスクを待つか

**→ 「TSK-421 は TSK-306 の前提」という結論は成立する。ただし効いているのは `STEP2_BASE_REVISION` ではなく `ORACLE_INPUT_BASELINE_COMMIT`。**

### 1. 凍結基準 4 件の性質(すべて [D])

| 定数 | 定義 | 使用箇所 | 主張の型 | digest 化 |
| --- | --- | --- | --- | --- |
| `ORACLE_INPUT_BASELINE_COMMIT` = `24ef4fcc…` | `scripts/check_authz_catalog.py:109` | **同 `:4984-4985` の 1 箇所のみ**(`tests/` `backend/` に参照 0) | **値の固定**(Python の `!=` による文字列一致。Git コマンドを一切実行しない) | **不可**(凍結対象そのものが commit SHA という値。digest 化する対象が無い)。台帳へは期待値文字列として移せる |
| `STEP2_BASE_REVISION` = `099a8fa2…` | `backend/tests/db/authz/mutation_composition.py:36` | 同 `:1170`・`:1186`、`backend/tests/test_authz_mutation_composition_full.py:14,53` | **内容の同一性**(`git show <rev>:<path>` で本文取得 → 可動ポインタ除去 → deep-equal) | **可能**。意味本文の canonical sha256 を 7 件置けば同じ検査になる |
| `AUTHZ_STEP2_BASE_REVISION` = `56c281c4…` | `tests/test_check_authz_catalog.py:38` | `:223` `_base_json`(任意 path)/ `:300` `_base_checker`(**基準版の検査器を `exec` する**)/ `:310`。間接使用 22 箇所 | **内容の同一性** | **部分的に不可**。本文をそのまま値として使うため digest 単独では不可。「digest + `git cat-file blob` で本文取得」なら可能 |
| `AUTHZ_GUARD_BASE_REVISION` = `56c281c4…` | `tests/test_core_guard.py:47` | `:781`・`:891`・`:945`(いずれも既定引数) | **内容の同一性**(`git show <rev>:.claude/core-areas.json` のみ) | **可能**(読むのは 1 ファイル) |

**重要**: **4 件とも到達可能性(ancestry)を検査していない。** `merge-base --is-ancestor` の grep 結果に authz 系は皆無。

**`ORACLE_INPUT_BASELINE_COMMIT` の実効機能**(台帳設計の論点 1): この定数の機能は「oracle 基準を進めるには **`guard_paths` 配下のソースファイルを編集させる**」という人手レビューの強制である。台帳(データファイル)へ移すと**その性質が失われる**。**台帳ファイル自身を `core-areas.json` の `guard_paths` へ入れないと保護レベルが下がる。**

**`AUTHZ_STEP2_BASE_REVISION` の理解の補正**: 「`check_authz_catalog.py` 自身を読む基準」という TSK-421 カードの記述は**不完全**。使用箇所 22 のうち `_base_checker` は 1 箇所で、**主用途は `contracts/authz/` 配下の資産本文の取得**(`_base_json`)。

### 2. `AUTHZ_GUARD_BASE_REVISION` を統合してはいけない機構的理由

| 定数 | 読む対象 | 前進の動機 |
| --- | --- | --- |
| `AUTHZ_GUARD_BASE_REVISION` | **`.claude/core-areas.json` のみ**(`tests/test_core_guard.py:784-789`) | **無い**(30 件は固定のままでよい) |
| `AUTHZ_STEP2_BASE_REVISION` | `contracts/authz/*.json` 14 件 + `check_authz_catalog.py` | **発生しやすい**(`oracle_commit` の前進・検査器の改修) |

実測: `56c281c` 時点の `guard_paths` = **30 件** / 現行 = **42 件** / 差分 12 件は `AUTHZ_GUARD_PATH_ADDITIONS`(`tests/test_core_guard.py:68-81`)と**完全一致**。`expected_authz_guard_paths()`(`:943-949`)= `base(30) ∪ additions(12)` の exact-set。

**統合して基準を進めると壊れるもの**:

1. `test_guard_paths_population_remains_unchanged`(`:1209-1211`)が**空虚になる** — base が 42 件になり additions 12 件が吸収され、**以後 `guard_paths` に何が足されても黙って通る**
2. `test_guard_paths_reject_removal_and_same_size_replacement`(`:1214-1228`)の検出力低下
3. **authz 側の都合で core-areas の基準が暗黙にリベースされる**(前進の動機が非対称)
4. `derive_authz_guard_candidate_paths(root, base_revision)` は `:1436,1444` で**合成リポジトリの revision** を渡される。GUARD 側は「既定値つきパラメータ」、STEP2 側は「固定値」という別の形が要る

**値が同じなのは歴史的偶然。台帳では別エントリにする。**

### 3. `oracle_commit` は何のためにあるか — 2 段コミットの正体

**検査しているのは三者一致**(2 者ではない):

- [D] `scripts/check_authz_catalog.py:5246-5247` — 作業ツリー vs seal
- 同 `:5255-5268` — **`oracle_commit` の木 vs seal**
- [D] `backend/tests/db/authz/mutation_composition.py:1104-1115` `_verify_oracle_input_assets` — 同じ三者(`worktree != baseline or baseline != recorded`)

**設計意図はテスト名が明言している**: [D] `backend/tests/test_authz_mutation_composition_full.py:121-132` `test_frozen_oracle_rejects_input_change_without_baseline_advance`「sealのoracle_commitを進めない入力資産変更を三者照合でredにする」。

**`git_blob_digest` があるのに `oracle_commit` が要る理由**: digest だけなら**作業ツリー vs seal の 2 者比較**になり、「入力資産を書き換えて、同じコミットで seal の digest も書き換える」が通る。**第 3 の参照点はコミットしないと SHA が決まらない**ため同一コミットで偽装できない。**これが 2 段コミットの正体。**

**同型の装置がもう 1 つ**: `requirement-claims.json` の `input_manifest.commit`([D] `scripts/check_authz_catalog.py:5498-5535`)。**要件書自体を先にコミットしないと通らない。**

**`oracle_commit` は到達可能性を保証していない(実験で証明)**: `git commit-tree` で HEAD の祖先でない commit を作り(`merge-base --is-ancestor` exit 1・`cat-file -e` exit 0)、`oracle_commit` をそれに差し替えたところ、`check_authz_catalog.py` は **ok**、`verify_frozen_oracle_unchanged()` も **OK**。**言っているのは「ローカルのオブジェクト DB にその 8 blob を持つ木の commit が存在する」だけ。**

> 推測: CI は fresh clone(`fetch-depth: 0`)なので push されていない dangling commit は解決できず red になる。したがって実運用上は「push 済みの ref から到達可能」までは効く。**ただし実 CI で未検証。**

**この穴は 7.7-3 の対象ではない**(条文の書き手による指摘・2026-09-20): 7.7-3 は「**基準の妥当性を確かめられないとき**、検査を不合格にしなければならない」を定める。到達可能性の件は「**確かめられない**」のではなく「**確かめていない**」ので、**7.7-3 では正当化も批判もできない。別の論点として立てる必要がある。**

**構造の指摘**: [A] の `F-5` が当初「commit が実在し、到達可能(`git cat-file -e`)」と書いて**要求とそれを満たせない機構を同じセルに書いた**のと同じ取り違えが、**検査器の側に実在していた**ことになる([A] `design.md:683` = PR #63 1 周目の `P0` #41 と同型)。

**台帳設計の論点 3(最重要)**: `oracle_commit` を「入力 8 件の blob digest」に置き換えると 2 段コミットは消えるが、**「同一コミットで入力と seal を同時に書き換える」抜け道が開く**。塞ぐには別機構(例: 台帳の追記を append-only にし `supersedes` 系列で人間承認を要求)が要る。

### 4. 要件書 1 文字変更の連鎖 — 20 ファイル・最小 3 コミット([P] で実測)

**失敗の順序**(すべて実測。典拠は [D] の行):

| # | 失敗箇所 | メッセージ | 典拠 |
| --- | --- | --- | --- |
| 1 | `_validate_manifest` | `source blob digest が不一致` | `check_authz_catalog.py:711-716` |
| 2 | `validate_catalog` | `構造属性または原文 digest が入力と一致しない` | 同 `:1362-1376` |
| 3 | `validate_decision_lock` | `decision_digest が現在の分類決定と一致しない` | `--reseal` で回避 |
| 4 | `_verify_manifest_commit` | `input commit 上の source blob がマニフェストと一致しない` | 同 `:5498-5535` ← **1 段目のコミットがここで要る** |
| 5-6 | 派生 3 資産 | `requirement_claims_blob_digest が入力資産と一致しない` 他 | 同 `:1728,1735` |
| 7 | decision lock | `route-registry.json: decision lock と不一致` | `--reseal-derived` |
| 8 | `validate_oracle_seal` | `oracle input blob が不一致` | 同 `:5246-5247` |
| 9 | 同上 | `oracle commit 上の blob が不一致` | 同 `:5255-5268` ← **2 段目のコミットがここで要る** |
| 10 | `check_mcdc_map` | `claim-mutant-map の digest 連鎖が不一致` | `contracts/authz/mcdc-map.json:7,11` |
| 11 | `check_failure_injection_points` | `ddl-elements.json: git_blob_digest が不一致` | `contracts/authz/failure-injection-points.json:6` |
| 12 | `check_shared_preconditions` | `requirements-….md: git_blob_digest が不一致` | `contracts/authz/shared-preconditions.json` |

**更新が必要な 20 ファイル**: 要件書 / `requirement-claims.json` + `.lock` / `route-registry.json` + `.lock` / `auth-catalog.json` + `.lock` / `http-route-matrix.json` + `.lock`(ここまで oracle 入力 8 件)/ `oracle-seal.lock.json` / 封印 6 資産(`ddl-elements` `rejected-configs` `claim-mutant-map` `attack-tree` `boundary-proposal` `verification-evidence`)/ **第 2 階層 3 件**(`mcdc-map` `failure-injection-points` `shared-preconditions`)/ `scripts/check_authz_catalog.py`(定数 1 行)。

> **訂正(2026-09-21・ステップ 4 完了後に再検証)**: ここに「**`shared-preconditions.json` は台帳 `H-85` の記述に無い 1 件**」と書いていたが**誤り**。`H-85` 本文は更新ファイル 20 の内訳として **`shared-preconditions` を明記している**(`harness-evaluation.md` の `H-85` 節・「更新ファイル **20**(母集合 + lock + 派生 3 + 各 lock + shared-preconditions + oracle 6 + seal + 下流 2 + 定数 + tests)」)。調査時に引用した行範囲(`:766-772,788-792`)の**外**にあったため見落とした。
>
> したがって**本調査の 20 ファイルは新発見ではなく `H-85` 本文の追認**である。**`H-85` へ「記述に無い 1 件」として追記してはならない。**

**最小 3 コミットの構造的下限**:

| コミット | 内容 | 分けざるを得ない理由 |
| --- | --- | --- |
| 1 | 要件書 | `input_manifest.commit` が**このコミットの SHA** を要る |
| 2 | oracle 入力 8 資産 | `oracle_commit` が**このコミットの SHA** を要る |
| 3 | seal + 封印 6 + 第 2 階層 3 + 定数 1 行 | **不可分**(分割すると `test_normal_validation_never_reseals_a_semantically_valid_drift`〔`tests/test_check_authz_catalog.py:4260-4300`〕が red。clone して作業コピーの検査器を走らせるため) |

コミット 1・2 の時点では検査は red(自己参照のため**原理的に回避不能**)。

**`req-universe.json` / `check_doc_coverage.py` は絡まない**(実測 EXIT=0)。同ファイルは要件 ID の期待母集合(`total: 212`)で**本文 digest を持たない**。散文 1 文字では ID 集合が動かない。**絡むのは ID 集合が動く改訂のときだけ**(FR/NFR 見出しの増減等)。

### 5. `H-85` の 2 段コミットは本タスクの射程では消えない

2 段を強制しているのは:

- `contracts/authz/requirement-claims.json` の `input_manifest.commit`
- `contracts/authz/oracle-seal.lock.json` の `oracle_commit`

**いずれも本タスクの 4 定数に含まれない。**4 件を台帳へ移しても 2 段は残る。**構造的に消すには、この 2 つのポインタを台帳へ移す設計が別途要る**(そして上記「論点 3」の抜け道を塞ぐ別機構が要る)。**本タスクの射程に含めるかは PO 裁定事項。**

### 6. PR #63 の失敗の経緯

**3 周の一覧**(唯一の一次記録 = [D] `docs/worklog/2026-09-16-frozen-baseline-clause.md:17-28`):

| 周 | 判定 | 要旨 |
| --- | --- | --- |
| 1 | 否決 `P0 3 / P1 1` | 3 指定が宣言に無い / `F-5` が到達可能性を見ない / 更新経路の閉塞 |
| 2 | 否決 `P0 3 / P1 2` | **宣言を足しただけで実装が使っていない**(`identity` をでたらめにしても通る) |
| 3 | 否決 `P0 2 / P1 2` | **比較関数を no-op にしても「実行済み」を出力する** |

**原文の残存状況**:

- **1 周目**: 全文あり([A] `docs/features/oracle-input-baseline/design.md:677-685` の #39〜#43)
- **2 周目**: 指摘の原文表は**無い**。反映側の記述([A] `design.md:286-301`)と実測 2 件のみ
- **3 周目**: **原文なし。両木を全文検索しても [D] worklog:23 の 1 行要旨以外に記録が存在しない**

**→ 「落ちたのは `R-2` とその周辺だけ」は記録から確認も否認もできない。** 確認できるのは「記録に残っている唯一の 3 周目要旨が `R-2` に当たる」ことのみ。**`P0` 2 / `P1` 2 の残り 3 件の宛先は不明。本タスクは『`R-2` だけ直せばよい』という前提を置けない。**

**効いた対策の出どころ**: **2 周目の `P0`**。[A] `design.md:302-311` `R-1` の結び「**これで `identity` を変えると挙動が変わる。変えて何も起きないなら、それは使われていない。**」。実際に効いた実例は TSK-420 側([D] worklog:535・:556-574 → `:728-738` **敵対レビュー初回可決**)。**違いは 2 つ — ①条文を先に確定させ実装を条文の帰結として書いた ②変異感度を実装に申告させず、レビュー依頼の前に自分で測って結果を渡した。**

**失敗記録「43 件」の実数**(実測): **表の行 45 / ユニーク番号 43 / 最大番号 43 / 重複 = #39・#40**。「収束後の自己点検」表と「PR #63 敵対レビュー」表が両方 #39 から振り直している。**「43 件」は最大番号であって行数ではない。**

**「自己申告を証拠にした」型の典型例は 43 件の表に入っていない**: 2 周目の「`frozen-declaration-used=` は『使った証跡』ではなく『読んだ宣言のエコー』だった」は [A] `design.md:297` の本文側、3 周目のものは [D] worklog:23 の 1 行のみ。**「43 件を読めばこの型が分かる」という読み方はできない。**

### 7. 失敗ブランチの実装の切り分け

**⚠ 「比較の原本は `4011dd3..fix/oracle-input-baseline`」は射程を 1 段取り違えている**(実測):

- `4011dd3` は BR の祖先 = **YES** / develop の祖先 = **NO** → **分岐点ではない**
- 正体: 「docs: ハーネス設計書 v1.15 を approved にする **(ステップ 3/12)**」= **ブランチ自身の途中コミット**
- 真の merge-base = **`0bc05b8`**
- `docs/` 以外: `4011dd3..BR` = **38** / `0bc05b8..BR` = **39**

**帰結**: 「38 ファイル」で語ると **7.7 条文本体(+125 行)が視界から落ちる**。

**新規追加 6 ファイル(develop に 1 つも存在しない)**:

| ファイル | 行数 |
| --- | --- |
| `contracts/authz/frozen-baselines.json`(台帳) | 100 |
| `scripts/check_frozen_baselines.py`(検査器) | 1555 |
| `scripts/frozen-baseline-scan-allowlist.json` | 42 |
| `tests/frozen_baseline_reader.py` | 58 |
| `tests/test_check_frozen_baselines.py` | 883 |
| `tests/test_frozen_negative_inventory.py` | 143 |

**述語は 13 個すべて実在**(`F-1`〜`F-8` + `G-1`〜`G-5`)。`F-8` のみ検査器外(`tests/test_ci_wiring.py`)。**負例 14 件も実数一致**(`pytest.mark.frozen_negative` の実測)。

**develop 側の fail-closed はブランチより厳しい形で着地している**: [A] は `--allow-historyless-oracle` という opt-out を持つが、[D] は**無条件 red**(`grep allow.historyless` → 0 件)。**TSK-420 / PR #71 が持ち込んだのは条文と fail-closed だけ。**

**contracts 資産の値が別系統へ進んでおり単純リベース不可**: [A] の `oracle_commit` = `b64fdefc…` vs [D] = `24ef4fcc…`。[A] が消そうとしている digest 辺の値も [D] では既に別の値へ進んでいる。**再封印のやり直しが要る。**

### 8. 台帳スキーマ — 再利用できる部分と作り直しが要る部分

**7.7 の項番号が [A](v1.15・7 項)と [D](v1.16・4 項)でずれている。**[A] の台帳は **v1.15 の 7.7-4** に対して設計されており、[D] の **7.7-2** は要求が増えている。

**[A] `contracts/authz/frozen-baselines.json` のスキーマ**:

- トップレベル exact-set: `schema_version` / `asset_kind` / `declarations` / `baselines`
- `declarations.<系列>` exact-set 4 キー: `frozen_targets` / `identity` / `granularity` / `basis_series` ← **v1.16 の 7.7-4 委任事項とほぼ対応。再利用できる**
- `baselines.<系列>`: commit 型(`commit` / `supersedes` / `approved_by` / `approved_at` / `reason`)と version 型の 2 種

**[D] の 7.7-2 に対する充足状況**:

| 7.7-2 の要求 | [A] の対応 | 判定 |
| --- | --- | --- |
| 新しい基準の識別値(**複数あればそのすべて**。1 つも無いときはその旨) | `commit` 文字列 **1 つ** | **部分** — 複数化できず「置かれていないことを表す値」も無い |
| 直前の基準の識別値(同上) | `supersedes`(先頭は `null`) | **部分** — 単数のみ。`null` が「履歴の先頭」を意味しており、7.7-2 が明示的に禁じる「履歴が無いこと ≠ 直前が無いこと」の混同をそのまま実装 |
| **何を変えたか — 変えた事柄と変更前後の内容** | **専用フィールドなし**(`reason` の自由文のみ) | **欠落** — `declarations` は現在値しか持たず履歴が無いので `identity`/`granularity` を変えても復元できない |
| 動かした事実・理由・承認者・承認日 | `reason` / `approved_by` / `approved_at` | 対応 |
| 追記のみ | `F-4` が base と HEAD を比較 | 対応 |
| **取り除くときも記録を要する** | **表現手段なし** | **欠落** |

**→ レコード構造の改訂が要る。`declarations` の 4 キー構造は再利用可能。**

**さらに 2 件の不整合**:

- **4 件目 `AUTHZ_STEP2_BASE_REVISION` が台帳の系列に載っていない。**[A] `scripts/check_frozen_baselines.py:25-38` の `INITIAL_SOURCE_BY_SERIES` は 3 件のみ。「直書き 4 → 0」は 4 件目を「値を消す」形で処理し系列へ載せていない
- **[A] の `oracle_input[0].commit = 0cf994f4…` は [D] の `24ef4fcc…` と違う値。**`F-7`(base 側ソースの定数値との一致)が**現在の develop に対して即 red** になる

### 9. 5 件目の直書き候補(伝聞になし)

[D] `scripts/check_docs_status.py:61-63` の `CHANGE_HISTORY_EXEMPT_DIGESTS` — 64 桁 digest。**コメント自身(`:57-60`)が「ダイジェスト値の更新は禁止。再計算して差し替えると…『履歴を残さず正本を書き換える経路』が復活する」**と書いており、**性格は凍結基準そのもの**。

[A] の走査正規表現は **40 桁 hex のみ**(`scripts/check_frozen_baselines.py:64-66`)なので**射程外**だった。

**あわせて**: `.github/workflows/ci.yml` に GitHub Actions の SHA pin が 19 出現。[A] の `SOURCE_PATHSPECS` は `*.py` のみで対象外。**7.7-1 の「検査器のソースへ直書きしない」から見て射程の妥当性は要判断。**

---

## 未解決・申し送り

1. **PR #63 3 周目の `P0` 2 / `P1` 2 のうち 3 件の内容が不明。** 記録が存在しない。「`R-2` だけ直せばよい」という前提を置けない
2. **`H-85` の 2 段コミットを本タスクの射程に含めるか**(`input_manifest.commit` と `oracle_commit` の台帳化)。含めると射程が大きく広がり、含めないと `H-85` は未対応のまま残る。**PO 裁定事項**
3. **`oracle_commit` を内容 digest へ寄せると「同一コミットで入力と seal を同時改竄できる」抜け道が開く。** 塞ぐ別機構の設計が要る
4. **`ORACLE_INPUT_BASELINE_COMMIT` の台帳化で人手レビュー強制が失われる。** 台帳ファイルを `core-areas.json` の `guard_paths` へ入れるかの判断が要る
5. **CI の fresh clone で `oracle_commit` がどこまで到達可能である必要があるか未検証。** 「push 済みの ref から到達可能」までは効くと推測したが実 CI で未確認
6. **要件書の ID 集合が動く改訂の連鎖は未実験**(本調査は散文 1 文字のみ)。`req-universe.json` / `check_doc_coverage.py` / `citation-map-*.json` が加わることは確実だが順序と完全集合は未確定
7. ~~**`shared-preconditions.json` が `H-85` の記述に無い。** 台帳へ追記する価値がある~~ → **取り下げ(2026-09-21)**。`H-85` 本文に記述がある(上記「訂正」を参照)。**ステップ 8 の `H-85` 追記からこの 1 件を外すこと。**
8. **5 件目の直書き候補**(`check_docs_status.py:63` の 64 桁 digest)と `ci.yml` の action pin 19 件を射程に含めるか
9. **[A] のブランチと worktree は資料として保存する。削除しないこと**(`design.md` の失敗記録・実装 38 ファイルはレビューを通っている)
10. **実験用クローン [P]** は `<scratchpad>/probe` に残してある。再現・追試に使える
