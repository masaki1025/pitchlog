---
feature: frozen-archive-literal-pins
type: research
date: 2026-10-01
---

# 調査メモ: frozen_archive のテストのリテラル固定(TSK-466)

**基準**: `origin/develop` = `f527cddf`(PR #83 マージ後)。調査サブエージェント 3 本(spec-checker / decision-tracer / Explore)の統合。**矛盾した 1 件は委任元が原典で裁定した**(下記 6 節)。

## 問い

1. **是正範囲の exact-set** — 「受理記録を 1 件足す PR が落ちる」箇所は全部でどこか
2. **各リテラルが何を守っているか** — 導出値へ変えると失われるものは何か
3. **上位根拠と条文** — 要件・設計書の改訂が要るか
4. **先例** — 同型の是正が過去にあるか。流用できるか
5. **否決の有無** — 「テストの期待値を導出値にする」案が過去に否決されていないか

## 結論(要約)

- **落ちるのは 11 箇所**(起票時の認識は 4 箇所。**`SnapshotArchiveMetrics` の 3 群が漏れていた**)。**11 箇所がすべてで、他に無いことを全数走査で確認した**
- **製品経路(`scripts/frozen_archive.py` / `scripts/check_tenant_boundary_bypass.py`)に現況のリテラル固定は 1 件も無い。** 壊れているのはテスト側だけ
- **要件(FR/NFR)に上位根拠は無い。正本の改訂も不要で、PR レビューで足りる**(7.6-3 前段)
- **`== 50` 系・metrics 3 群・履歴件数は「非空 + 構造条件」へ落とせる見込み。** 「ちょうど 50」でなければならない根拠は無く、守っている実体は「空集合での素通り」の検出だけ
- **残る設計判断は `corpus_inputs.digest` の 1 点に絞られる。** **`history-snapshots/` の除外では解けず**、digest を現況から再計算する方式にすると **drift 変異テスト 5 本が恒真になる**

## 詳細と典拠

### 1. 是正範囲の exact-set(11 箇所)

**前提**(`scripts/frozen_history.py` / `scripts/check_tenant_boundary_bypass.py` の契約): 受理記録の追加は必ず ① `baseline_control.history` への v2 記録 1 件の append、② 影響資産の識別値の繰り上げ(top-level field なので射影 digest を必ず動かす)、③ 新しい sha256 が `change.after` に最低 1 件現れ `history-snapshots/` に新ファイルが最低 1 件増える、を伴う。**「新 digest が 0 件」は契約上作れない**ので、下記は例外なく落ちる。

| # | 箇所 | 固定している現況 |
| --- | --- | --- |
| 1 | `tests/test_frozen_archive.py:120-127` | 履歴の版列 `[1,2,2,2,2,2]` |
| 2 | `tests/test_frozen_archive.py:131` | 一意参照 50 件 |
| 3 | `tests/test_frozen_archive.py:139` | 同上(変異前 green の前提) |
| 4 | `tests/test_frozen_archive.py:164` | 同上(4 パラメータ) |
| 5 | `tests/test_frozen_archive.py:198-200` | 同上 |
| 6 | `tests/test_frozen_archive.py:210-212` | 同上 |
| 7 | `tests/test_frozen_archive.py:332-336` | `SnapshotArchiveMetrics(83, 2_958_228, 33, 1_214_665)` |
| 8 | `tests/test_frozen_archive.py:339-340` | 同じ 4 値を `base` / `head` 両方へ exact 一致 |
| 9 | `tests/test_frozen_archive.py:514-517` | 同じ 4 値を個別 assert |
| 10 | `tests/test_check_tenant_boundary_bypass.py:3346` | `len(authority_history) == 6`(**`FROZEN_BASELINE_ASSETS` で parametrize される。実測では 7 failed / 1 passed** — `census-baseline.json` は `history=[]` のため `if not history: return` を通り当該 assertion に到達しない。**ステップ 1 の実測 2026-10-01 で訂正**〔当初は「8 インスタンスが同時に落ちる」と書いていた〕 — `:3323`) |
| 11 | `tests/fixtures/frozen-archive-cases/manifest.json:7` | `corpus_inputs.digest` |

**11 の連鎖**: `runner.py:735 prepare_case` の冒頭で `validate_corpus_inputs`(`:440-448`)が必ず呼ばれるため、**31 テストインスタンスが連鎖的に落ちる**(`test_frozen_archive_case_runner.py:257` の 11 ケース / `test_frozen_archive.py:814` の F1〜F11 ほか)。

**条件付きで落ちるもの**(本タスクの設計次第):

| 箇所 | 条件 |
| --- | --- |
| `tests/test_frozen_archive_case_runner.py:47-58` | corpus の `files` / `trees` を exact-set で固定。**`trees` を分解・除外キー追加で落ちる** |
| `tests/test_check_tenant_boundary_bypass.py` の 11 箇所(`:2595` `:2647` `:2706` `:2720` `:2759` `:2939` `:2976` `:3001` `:3042` `:3077` `:3112`) | `acceptance_id` に `#79` / `#81` を literal で使用。`frozen_history.py:1441-1446` が重複を拒否するので、**新しい受理記録が #79 / #81 を名乗ると一斉に red** |
| `manifest.json` の `cases[9]` / `cases[10]` の `description` | **digest の入力**(`runner.py:362-373 _normalized_manifest_input`)。文言を直すと digest 再導出が要る |
| `scripts/frozen-baseline-scan-allowlist.json` + `tests/test_frozen_baseline_declarations.py:287-293` | 走査対象は `*.py` のみ(`check_frozen_baselines.py:34, 42, 1627-1645`)。**是正が .py に 40/64 桁 hex を増減させると落ちる** |

**落ちないと判定したもの**: 合成 `tmp_path` の値(`:430-431` `:458-459` `:491-501` ほか)/ 設計閾値(`:337-338`)/ F1〜F11 の失敗分類(`:587-597`)/ `census-baseline.json` の anchor(`git ls-tree` で解決するため現況非依存 — `tests/test_census_baseline_check.py:380-460`)。

### 2. 各リテラルが守っているもの

**`== 50` の由来はレビュー指摘ではなく計画書の合格条件(実測値)**: `docs/features/frozen-history-7d-remainder/plan.md:176` `:193`、`design.md:496`。**design 1-2 の合格条件は当初値の「一意参照 18 件」のまま残っており**(`design.md:120`)、18 → 50 の更新を記録した改訂履歴の行は**無い**(典拠なし)。

**守っている実体**(4 周目 P1 の逐語 — `design.md:92`):

> **キー集合の一致だけでは、`declaration` や `movement_policy` に誤った extractor を割り当てても現行データで空集合を返して通ってしまう**

**「ちょうど 50」でなければならない理由を書いた典拠は無い。**

**変異テストの事前条件としての強さ**(Explore の判定):

| 事前条件 | 消すと変異を検出できなくなるか |
| --- | --- |
| `:139` `:164` `:198-200` `:210-212` の `== 50` | **ならない**。後続の `pytest.raises` が残る。失うのは「変異前が green」の保証 |
| `:265-268` `extract(history, tmp_path) == {digest}` | **なる**。唯一の「正しい参照は抽出される」側。消すと「常に `ContractError` を投げる」実装が通る |
| `:363-364` `:396-397`(閾値ちょうどの受理) | **なる**。オフバイワン(500 で拒否)の実装が red 側だけで通る |
| `:430-431` `:458-459`(比較元と同数の孤児は受理) | **なる**。常に拒否する実装が通る |
| **`:832-834`(F1〜F11 の改変前 green)** | **決定的になる**。**合成リポジトリが元から red でも全 11 ケースが通る。本ファイル中で最も重要な事前条件** |
| **`test_frozen_archive_case_runner.py:140-144`(digest 照合)** | **なる**。**corpus drift を検出する唯一の機構**。`:147` `:167` `:193` `:212` `:237` の 5 本がこれと対になっており、**digest を現況から再計算すると 5 本すべてが恒真になる** |
| `:390-392`(受理が成立した状態からの変異) | **なる**。元から red でも後続を満たす |
| `:450-453`(比較元と HEAD が別集合) | **なる**。両者が同一集合でも green として通り、独立算出の証明にならない |

**無力な assertion が 1 件**: `:225-228` は `clean_history` も期待も共に空集合なので、**「常に空集合を返す」退化実装がこの試験全体を素通りする**(Explore の判定)。

### 3. 上位根拠と条文

**要件(FR/NFR)に上位根拠は無い。** TSK-448 と同じ結論(`docs/features/frozen-history-7d-remainder/research.md` 5 節)を spec-checker が独立に再確認した。

- **NFR-019**(`requirements-pitchlog-2026-07-22.md:925`)が求めるのはテストランナーの標準化・PR ごとの CI 実行・全グリーンでのマージの 3 点。本タスクに効くのは「pytest のまま CI の harness ジョブで実行され続けること」まで
- **NFR-021** の母集団は `docs/ops/nfr021-acceptance/` 配下のみ(設計書 `:886` `:893` `:895`、実装は `scripts/check_nfr021_append_only.py:423-455`)。**`contracts/tenant_boundary` は入らない**
  - ただし**別の効き方が 1 つ**: `tests/` `contracts/` `scripts/` は NFR-021 証跡の**失効対象パス**(設計書 `:892`)。本タスクのマージは進行中の受入があればその証跡を失効させる
- **NFR-018** の対象列挙(状況判定・座標変換・捕球選手推定・成績集計の前処理・終了判定 — `:892`)に「参照集合を数える処理」は入らない。**448 が NFR-018 を引いたのは類推適用**(`plan.md:176` `:203`)で、要件の文言から来たものではない

**正本の改訂は不要。PR レビューで足りる**(7.6 決定表 `:509-516`、7.6-3 は `:515`)。**計画書の「影響する正本」には「反映なし」と明記する**(7.6-1 `:513`)。

**コア領域に当たる理由**: 6.3 の落とし込み規則 ①「コアの不変条件・強制点・契約(ベクタ・スキーマ・テスト)を変え得るファイルを含める」(`:400`)と「判定に迷うコードは含む側に倒す」(`:399`)の当てはめ。登録は `.claude/core-areas.json:365-374`。**6.3 の表と要件書・設計書に `check_tenant_boundary_bypass` / `frozen_archive` の名前は出てこない**(spec-checker が 0 件を実測)ので、**結び付けは当てはめである**。

### 4. 先例

**census-baseline の免除(台帳候補 4 件目)**:

- **最初の形は `current_minus_anchor`(免除を宣言の差分から導出)だったが、P1「相関であって因果ではない」を受けて作り直された**(`docs/features/product-authz-apply/plan.md:103`・2026-09-30 山田正輝承認)。「許可した関数の中の、許可 API と無関係な TB005 が消えても通る」
- **最終形**は `removed_outside_allowed_codes_equals_measured_allowlist_suppression`。**anchor の許可記号へ差し替えた反実仮想を実測し、その差を上限にする**(`contracts/tenant_boundary/census-baseline.json:96-111`、実装 `tests/test_census_baseline_check.py:1441-1621`、derivation は `counterfactual_allowlist_substitution`)
- 設計は TSK-460(235)、実装と記録は TSK-424 PR A2(#84)(`product-authz-apply/plan.md:101`)
- **流用するなら最終形。** 類比になるのは「比較元の参照集合 ⊆ 現行の参照集合、かつ増分は比較元より後に追記された記録だけから来る」のような形(decision-tracer の推論)

**TSK-322**(`harness-evaluation.md:2028-2037`): 「リテラル固定をやめ**文書から正規表現で導出**する形へ」変えた先例。ただし**同じ箇所に「正本の literal をテストに置くこと自体は、意図した変更を検出する正当な手段でもある」とあり、線引きは未決のまま残っている**。

### 5. 否決の有無

**「テストの期待値を導出値にする」案が否決された記録は見つからなかった。** 否決されたのは次の 2 件で、**どちらも別の対象**:

1. **本番の抽出表を `ASPECT_NAMES` から導出する案**(3 周目 P1 — `design.md:88-90`)。逐語: 「**`ASPECT_NAMES` が与えるのは 4 個の名前だけで、どの値が配列か・どこに `snapshot_ref` があるかという型と経路の情報を持たない。「機械導出」は成立しない。**」
2. **完全な hermetic 化**(費用対効果 — `harness-evaluation.md:4135`)

**実装レビュー 4 周・計画レビュー 8 周のレビュー原文はリポジトリに無い**ので、「導出値にすると自己参照になる」等の指摘が出たかどうかは**確認できない**(典拠なし)。

### 6. corpus digest(**残る設計判断**)

**設計意図**(`harness-evaluation.md:4135` の逐語):

> **有効だった手当て**: **完全な hermetic 化は費用対効果で退け**(runner の大幅な書き換えと 11 ケースの期待値の導き直しになる)、**「黙って陳腐化する」を「落ちて気づく」へ変えた。** **corpus の入力**(契約資産・検査器・履歴)**と生成規則**(`runner.py`・ケース定義)**を digest で固定し、現況が動いたら `ValueError` で落とす。**

**陳腐化の根本原因**: 合成 base が現行作業木から作られている(`prepare_case` が `_initialize_test_repository` 経由で現況をコピー — `harness-evaluation.md:4117`)。

**`trees` の範囲**は `_initialize_test_repository` が丸ごとコピーする 2 ディレクトリ(`tests/test_check_tenant_boundary_bypass.py:1131-1138`)と一致する。**ただし範囲の選定理由を書いた文書は無い**(design.md・plan.md・worklog のいずれにも典拠なし)。

**実装上の制約**(Explore が原典で確認):

| 制約 | 典拠 |
| --- | --- |
| `corpus_input_digest` に除外引数・フィルタ分岐が無い | `runner.py:411-423` |
| `load_manifest` が `corpus_inputs` のキー集合を `{digest, files, trees}` の **exact-set で拒否** | `runner.py:228-229` |
| `_normalized_manifest_input` の `corpus_inputs` も `{files, trees}` でハードコード | `runner.py:354-361` |
| `_path_list` が**非空配列**を要求(`"trees": []` で逃げられない) | `runner.py:185-186` |

**`history-snapshots/` だけの除外では解決しない。** 受理記録は `base-allowlist.json` 本体の `baseline_control.history` を変え、**それ自体が digest 対象**だから。digest を受理記録に対して不変にするには、**`baseline_control.history` を正規化で落とす**か、**当該資産を digest 対象から外す**必要がある。

**既存機構の範囲で取れる唯一の経路**: `trees` から `contracts/tenant_boundary` を外し、8 本の資産 JSON を `files` に列挙する。`_path_list` も `runner.py:238-243` の重複検査も通る。**代償は「資産ファイルの新設を digest が検出しなくなる」こと**と、`test_frozen_archive_case_runner.py:55-58` の `trees` exact-set assertion の書き換え。

**除外しても合成リポジトリの構成は変わらない。** `prepare_case` は `shutil.copytree` で `contracts/tenant_boundary` を丸ごと複製するので、**除外は「漂流検出の対象」にだけ効き、「ケースが見る世界」には効かない**(`tests/test_check_tenant_boundary_bypass.py:1125-1150`)。

**7.7 の射程に入るかが条文から決まらない**(spec-checker の判定):

- 7.7 は「検査が『この資産は変わらない』と主張するとき」全般に掛かり(設計書 `:520`)、**テストを除く文言が無い**
- 対象と読めば、digest の除去・置換は**「基準の削除」**(`:556-561`)に当たり、**取り除くときも記録が要る**(`:605`)
- 対象外と読めば掛からない
- **どちらの読みかを決める条文は見つからなかった**(典拠なし)
- 先例として、台帳の走査はテスト内の 40/64 桁 hex を凍結基準として扱っている(`check_frozen_baselines.py:34`、`frozen-baseline-scan-allowlist.json:17-28`)。**ただし走査対象は `*.py` のみで、JSON の manifest と件数リテラルは機械検査の外**

**7.7-3 は既存の検査にも掛かる**(`:617`)。導出値や構造条件が確かめられないとき(読めない・解決できない等)は**不合格にしなければならず、保留・skip・中立は認められない**(`:609-612`)。

## 未解決・申し送り

### 計画で人間の判断を仰ぐ事項

1. **`corpus_inputs.digest` をどう扱うか。** 消せば drift 変異テスト 5 本が恒真になり、残せば受理記録を足す全 PR が税を払い続ける。**既存機構で取れるのは「`contracts/tenant_boundary` を `trees` から外し 8 資産を `files` に列挙する」経路のみで、代償は資産の新設を検出しなくなること**
2. **その変更が設計書 7.7 の「基準の削除」に当たるか。** 条文が決めていない。当たると読むなら 7.7-2 の記録が要る
3. **`acceptance_id` の `#79` / `#81` の literal 11 箇所**(`test_check_tenant_boundary_bypass.py`)を本タスクの射程に含めるか。いまは落ちないが、**将来 #79 / #81 を名乗る受理記録が出たら一斉に red になる**。`runner.py:698-713 _pull_request_number_for_case` は同じ衝突を動的回避で解いており、**非対称が残っている**

### 本タスクの射程外として送り出す候補

- **`design.md:120`(448)の「一意参照 18 件」が 50 へ更新されないまま残っている**(改訂履歴の行も無い)。448 は閉じているため別タスク
- **448 の `research.md` の典拠に行ずれ**: 「追記のみ」は現行 `:607`(research は `:605`)、10.1 の「保持」は `:895`(research は `:900`)
- **`tests/test_frozen_archive.py:225-228` の無力な assertion**(`clean_history` も期待も空集合で、退化実装が素通りする)
- **`:3346` が `FROZEN_BASELINE_ASSETS` で parametrize されているため 8 インスタンスが同時に落ちる構造**(1 行の literal が 8 倍に効く)

### 委任元が原典で裁定した矛盾(1 件)

**decision-tracer が「`tests/test_check_tenant_boundary_bypass.py:3346` は TSK-448 より前から存在する literal」と報告したが、誤り。**

- `ec02a0d2`(#83 マージ前)に `len(authority_history)` の assert は **0 件**(委任元が実測)
- 現 develop の `:3346` に存在
- 関数 `test_every_frozen_baseline_asset_has_a_valid_chained_history` 自体は `ec02a0d2:3323` に既にあった

**→ 関数は前からあり、assert 行は #83 が足した。11 箇所すべてが #83 由来。**

誤りの原因は `design.md:574` の「authority 履歴期待件数を **2 → 3 へ更新**」を「元の literal が存在した」と読んだこと。**実際は計画時点の見込みで、実装時には #80・#86・#84 が入って実件数が 6 になっており、448 は新しい assert 行として実装した。**

### 他タスクとの関係

- **TSK-444(#82)が本タスクの着地を待っている。** 実測 48 件の失敗の内訳が本調査の 11 箇所と一致している(444 の突き合わせ)。**ただし 444 の内訳の合計(11 + 7 + 1 + 1 + 1 = 21)が 48 にならない**。種類を数えている可能性が高いが**未確認**
- **#74・#87・#443 も同じところで落ちる**(未実測。契約上そうなるという推論)
