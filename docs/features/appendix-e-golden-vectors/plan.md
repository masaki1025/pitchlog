---
feature: appendix-e-golden-vectors
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-25・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3c193b75e6878156882ddd1c59b808f5
branch: feature/appendix-e-golden-vectors
created: 2026-09-24
計画レビュー周回: 9        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 付録E ゴールデンケース全表 + 終了判定ベクタ(段階 1 のベクタ資産側)

## 1. 背景・目的

Notion: [TSK-236](https://app.notion.com/p/3c193b75e6878156882ddd1c59b808f5)(優先度 高)
調査メモ: [research.md](./research.md) / 詳細設計: [design.md](./design.md)

要件書 付録E は「FR-003/FR-004/FR-005 の**状態自動更新と成績計上の正**」だが、
載っているのは E-1 の 10 列スキーマと **E-2 の代表 7 行のみ**(要件書:1247-1275)。
NFR-018 は「**正解ベクタは完成をもって発効する**」と定める(同:920)。**中身を作る**のが本タスク。

### 1-1. 本タスクの終点 = 段階 1 の**ベクタ資産側**成果物の完成

| 区分 | 内容 |
| --- | --- |
| **本タスク** | 正本改訂 / descriptor / 契約 schema / 規範行 4 層 / 期待値 / `requiredSet` / `clauseBranchRegister` / 手作業 fixture / 語彙シード / oracle 遮断機構 / 未解消レポート / **段階 2 への引き渡し契約** |
| **段階 2** | 製品 manifest への計算登録 / **runner による契約の消費** / 正規化の計算投入証跡 / FR-040 宣言の manifest 記載 / **descriptor と schema の射影検査** |

**段階 1 で「実際に消費可能」とは主張しない** — 引き渡し契約に `consumptionVerification: "pending"` を明記し、
**段階 2 の最初の停止ゲート**を「トップレベル読込 / 版検査 / binding 構築 / `D`+1 を含む全 case 消費」と定める
(design.md 1-3)。

### 1-2. 計画レビュー 9 周の経緯と打ち切り

| 周 | P1 | P2 | 備考 |
| --- | --- | --- | --- |
| 1〜3 | 12 / 12 / 12 | 2 / 3 / 3 | |
| 4 | 13 | 3 | PR 構成を検証済み。**undo の規範行が無かった** |
| 5 | 14 | 2 | **段階 1 で実行不能**が判明(`H-68` 型)→ **PO がスコープ裁定** |
| 6 | 11 | 1 | **初めて減少**。「追加の裁定は不要。最小是正であと 2 周」 |
| 7 | 6 | 1 | 解消 7 / 部分的 5 / 未解消 0 |
| 8 | 4 | 0 | 解消 3 / 部分的 4 / 未解消 0 |
| **9** | **5** | **1** | 解消 1 / 部分的 3 / 未解消 0。**ここで打ち切り**(下記) |

**打ち切りの判断(2026-09-25・PO 承認)**

- **P0 は 9 周を通じて 0**。**未解消は 6 周目以降ずっと 0**(すべて「部分的」= 実質は前進)
- P1 は 14 → 11 → 6 → 4 → 5 で**頭打ち**。「あと 2 周」という見立ては **6・7・8・9 周目と 4 回連続**で出た
- 9 周目の新規 3 件はいずれも**契約 schema のフィールドレベルの細部**
  (`Predicate` の `Literal` が複合軸を表現できない / `FieldEffect` が全フィールドで `delta` を許す /
  合法組合せ表と `XC-*` の両方を通る不正行)であり、
  **ADR-003:251 が「ベクタ整備タスクと検査基盤の実装タスクで、実機とともに確定する」と委任している範囲**。
  計画書は契約であって実装仕様ではない
- 前例: **TSK-235 も 6 周で PO が打ち切り**(「是正のたびに『自己申告を検査する層』が 1 つ増えるだけ」—
  評価台帳 `H-68` 型)

**打ち切り前に是正した 3 件**(いずれも計画側の実質的な欠陥):

| # | 欠陥 | 是正 |
| --- | --- | --- |
| 1 | `history-depth.json` を descriptor の正本グラフに入れたが、**同ファイルは develop に存在せず** TSK-235 を待たない方針と両立しない | **参照をやめ、値域を条文から独立に導出**。一致検査と `D` の実値解決は**段階 2** |
| 2 | Vitest runner の commit OID は **TSK-455 が未着手で段階 1 に確定できない** | `runnerRevision` を段階 1 では `"pending"` とし `resolutionStage: "stage-2"` を持たせる |
| 3 | 再番号付け後に `XC-08` の旧参照が残っていた | `targetKind` の `"undo"` 排除は **enum 側**であり交差制約ではないと明記 |

**実装フェーズへ送る 3 件**(ADR-003:251 の委任範囲): `Predicate` の複合軸表現 /
`FieldEffect` のフィールド別 union / 合法組合せ表と `XC-*` の隙間(打席終了・第三アウト上限・対象一意性)。
**契約 schema を実際に書く時点で閉じる**。

### 1-3. 送り先

FR-007 再開 → [TSK-454](https://app.notion.com/p/3e593b75e687813bbe17c36d17ebee63)(並行可・DoD からは落とさない)/
Vitest 側 runner → [TSK-455](https://app.notion.com/p/3e593b75e687812ba2e8c20d469ea6db)(段階 2 の依存)/
FR-006 のキュー投入・同期状態非依存 → 同期側のテスト / 管理者の有効化拒否の実装 → 該当 FR の実装タスク。

## 2. スコープ

### やること

正本改訂(要件書 / ADR-003 D-11・D-6・D-8・D-12 / 同期プロトコル正本)/
**入力軸 descriptor**(両段階を通した唯一の正・D-11 の全軸・射影規則)/
契約 schema(E-1 全 10 列の exact 型・operation / undo の別表・交差制約 `XC-01`〜`XC-09`)/
`mustOperationCoverage` / `requiredSet`(2 段)/ 語彙シード + 内容 hash /
`clauseBranchRegister` / **手作業 fixture**(作成・突合・凍結)/ oracle 遮断 4 層 /
展開器と `cases[]` / **`gapRegister` の 5 段を各所有ステップで充填** /
`.claude/core-areas.json` への paths 追加 / 台帳候補 (10) を `H-90` へ昇格 /
未解消レポート / **段階 2 への引き渡し契約**(`consumerBindings[]` を含む exact 型)

### やらないこと

| やらないこと | 理由 |
| --- | --- |
| **runner による契約の消費** | **段階 2**。TSK-235 の runner は実計算を必須とし(`vectors.py:205`)、最小 runner の自作は「検査基盤を作らない」と矛盾する |
| **製品 manifest 登録** / **正規化の計算投入証跡** / **FR-040 宣言の manifest 記載** / **descriptor と schema の射影検査** | **段階 2** |
| **対象計算の実装コード** / **検査基盤(runner・生成器・変異器)** | ADR-003:440-444 / TSK-235 |
| **FR-006 のキュー投入・同期状態非依存の検証** | 同期側のテスト |
| **FR-040 の優先度変更** / **NFR-019(a) の充足宣言** | Should のまま / `BOOT-NO-CLAIM` |
| **FR-007 再開の case** / **結果表示名の合成規則** / **付録A の固定ベクタ** / **`core-areas.json` の全領域充填** | 他タスク |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| **要件書** | 付録E-1(境界 / **全 10 列の exact 型** / **交差制約 `XC-*`** / 表示名の読み替え)/ **定義の穴 9 件** / 管理者語彙の二段階ゲート / NFR-018(b)②。**版繰り上げ** | **finalize-doc** |
| **ADR-003** | **D-11**(規範行駆動 + **descriptor を両段階を通した唯一の正**とし schema を派生物に + **射影規則**)/ **D-6** / **D-8** / **D-12**。**版繰り上げ** | **finalize-doc**(同一ゲート) |
| **`docs/design/sync-protocol.md`** | :1309 / :1588 の正を「D-6 で登録された状況判定ベクタ全体」へ。**版繰り上げ** | **finalize-doc**(同一ゲート) |
| **`docs/development/harness-evaluation.md`** | 候補 (10) → **`H-90`** + 変更履歴 1 行。**`docs/README.md` の台帳行と同一コミット** | **PR レビュー** |
| **`contracts/README.md`** / **`docs/README.md`** | 索引の追加と現行化 | **PR レビュー** |
| **`docs/design/data-model.md`** / **`dev-harness-design-2026-08-07.md`** / **ADR-001・002・004** | **反映なし** | — |

**正本体系外**: `.claude/core-areas.json`(**6.3-⑤**)/ `tests/test_core_guard.py`

**oracle の追随で動く資産**(ステップ 17 — 台帳 `H-85`。**要件書の改訂が blob digest の凍結を発火させる**):
`contracts/authz/` の `requirement-claims.json`(+ `.lock.json`)/ `route-registry.json`(+ `.lock.json`)/
`auth-catalog.json`(+ `.lock.json`)/ `http-route-matrix.json`(+ `.lock.json`)/ `oracle-seal.lock.json` /
`shared-preconditions.json` / `mcdc-map.json` / `failure-injection-points.json` / `boundary-proposal.json` /
**`frozen-baselines.json`**(TSK-421 が検査器の `ORACLE_INPUT_BASELINE_COMMIT` を台帳へ移した先)、
および `tests/test_check_authz_catalog.py`(期待件数のハードコード)。

**`docs/design/data-model.md` も `shared-preconditions.json` に digest を凍結されている**が、
**本タスクは同ファイルを変更しない**ため追随の対象外。

## 4. 実装方針

### 重さ分類 — コア領域

`game-state` に直撃。**sol xhigh・敵対レビュー必須・人間の逐行確認必須**。
3 正本の版繰り上げを含むため **finalize-doc** も通る(前例: PR #64)。

### 機械保証と人間統制の境界

**依存トレースは実行可能な導出器・展開器のファイル読み取りしか検出しない**。
**design.md 8 節の表が層ごとの境界を定める**。境界を越えて機械保証を主張しない。
**手作業 fixture は「展開器からの独立」だけを主張する**。
**変異テストは「片経路の実装差」のみを検出し、両経路に共通する欠落は検出しない**。

### ステップ 1〜16 のあいだ `pytest tests/` は red になる(既知)

**要件書を 1 文字でも変えると authz 系の blob digest 凍結が発火する**(台帳 `H-85`)。
次の **3 件**が「`git_blob_digest` が現ファイルと不一致」で落ちる。

- `test_check_authz_catalog.py::test_repository_catalog_covers_the_entire_requirements_file`
- `test_check_authz_catalog.py::test_normal_validation_never_reseals_a_semantically_valid_drift`
  (**リポジトリを clone した基準状態の検査**が同じ digest 不一致で落ちるため。
  **ステップ 13 の後の全走行で判明** — 当初 2 件と書いていたのは数え漏れ)
- `test_check_shared_preconditions.py::test_repository_shared_preconditions_are_valid`

**これは機構が設計どおり動いているもので、凍結を緩めてはならない**
(台帳: 「oracle 先行固定は『検査が正本に合わせられる』ことを防ぐ正しい規律」)。
→ **ステップ 17 でまとめて追随させ、そこで緑に戻す**。
ステップ 1〜16 の各コミットでは **`check_docs_status.py` / docs-lint / lychee** を合格条件とし、
**`pytest tests/` の当該 3 件の red は既知として許容**する(それ以外の red は許容しない)。

### ステップ外の手続き

**確定ゲート**(ステップ 29 の後)/ **develop 同期 3 点** / **`/check`** / **`/pr`**。
`/finalize-doc` は反映周ごとに番号なしコミットを作るため、1 ステップ = 1 コミットで表現できない。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ | 合格条件 | 相 |
| --- | --- | --- | --- |
| 1 | 要件書 付録E-1 — 操作イベント・undo との境界 | 走者イベントが E-1 の 3 種に留まる | A |
| 2 | **定義の穴 2 — 成績計上フラグの外延**(**exact 型より前に置く** — 8 周目 P1-3)。導出元は付録A-2 / A-2b / A-3 / A-3b / A-5 **+ FR-022 の当日集計 9 項目**(design.md 7-1) | **閉じた列挙**。Won't 境界(自責点・防御率・勝敗投手・セーブ)を含まない。付録E-1 の「等」が解消。**`statFlags` の完全なキー集合が確定**する。**FR-022:443 の 9 項目がすべて導ける**ことを逐条で対応づけ | A |
| 3 | **定義の穴 9 — 打点の算出定義**(**実装中に発見** — design.md 7-0) | **閉じた分岐 ID**と各分岐の正負例。典拠は**公認野球規則 9.04**。併殺打の間の得点・失策による得点の扱いが条文で判定できる。**付録A-3 に行が追加**され、FR-022 の第 6 列と整合 | A |
| 4 | 要件書 付録E-1 — **全 10 列の exact 型**(design.md 4-2・4-6) | 10 列すべてに JSON shape・required・`additionalProperties: false`。**`statFlags` がステップ 2 のキー集合を参照**。自由記述は `remarks` のみ | A |
| 5 | 同 — **`eventKind` 別の合法組合せ表**(design.md 4-5) | 3 種すべてに行がある。**表に無い組合せは fail**(allowlist 方式)。`runner-event` は `unchanged` / `not-applicable` / `not-applicable` に固定 | A |
| 6 | 同 — **交差制約 `XC-01`〜`XC-09`** | 9 件すべてに述語。**`XC-07` が双方向**。**`XC-08` が起点塁別の到達可能集合**(`targetKind` の `"undo"` 排除は enum 側) | A |
| 7 | 同 — 結果表示名を語彙シード参照へ読み替え | 「表示名は語彙シードが正」と明示 | A |
| 8 | 定義の穴 1 — H/E/K/B + 延長時の扱い・空欄規則 | 4 欄に定義。延長時と空欄規則が条文化 | A |
| 9 | 定義の穴 3 — コールド成立のタイミング | **閉じた分岐 ID**と各分岐の正負例 | A |
| 10 | 定義の穴 4 — 引き分け成立の条件 | 同上 | A |
| 11 | 定義の穴 5 — X 表記の一般規則 | 同上。要件書:234 を特例として包含 | A |
| 12 | 定義の穴 6 — タイムプレイの判定規則 | 同上。付録E-2 の「第3アウト超過を許さない」と別規則 | A |
| 13 | 定義の穴 7 — 妨害系 3 種 + 強制/任意進塁・停止 | `runnerDefaultAdvance.modality` を決定できる。**起点塁別の到達可能集合**(first→{2,3,4} / second→{3,4} / third→{4})が条文から導ける | A |
| 14 | 定義の穴 8 — `K3` + 三重殺 | **閉じた分岐 ID**と正負例。語彙シードの ID と対応 | A |
| 15 | 要件書 — 管理者語彙の二段階ゲート | 要件書:168 と矛盾しない。実装担当を明記 | A |
| 16 | 要件書 — NFR-018(b)② の保証範囲 | 軸の列挙がステップ 1・4〜6 と整合。縮小の根拠 | A |
| 17 | **oracle の追随**(台帳 `H-85` の対応案① — **要件書の改訂が oracle の入力凍結を発火させる**)。ステップ 1〜16 の要件書改訂をまとめて追随させる | **2 コミット必須**(`_verify_manifest_commit` が「`commit` が指すコミットの blob が `source_blob_digest` と一致」を要求するため、**新しい blob を含むコミットが先に存在しないと母集合を更新できない**)。`uv run pytest tests/` が**緑に戻る**。**`reseal_policy.human_review_required` の人間確認を得る**。**`source_id` の位置移動**(`{見出し}/{種別}-{連番}` は位置依存)を同一見出し内の本文 digest で引き当てて解決する | A |
| 18 | ADR-003 **D-11** — 規範行駆動 + **descriptor を両段階を通した唯一の正**とし schema を派生物に + **射影規則**(design.md 3-4) | 3 点が条文化。**「段階で正が交代する」記述が無い**。**「主要フラグの閉包は宣言モデルの schema が定める」等、schema を正とする既存文言が 1 件も残っていない**(逐語検索で確認 — 8 周目 P1-2) | A |
| 19 | ADR-003 **D-6** | `requiredSet` の帰属 / 規範行の層 / 語彙シードの分類の 3 点 | A |
| 20 | ADR-003 **D-8** | 5 種の型が閉じる。「既存比較面を縮小しない」が条文にある | A |
| 21 | ADR-003 **D-12** | 語彙シードのパス・版・内容 hash の宣言先 | A |
| 22 | `docs/design/sync-protocol.md`(:1309 / :1588) | **D-8 を状態効果の正にしていない**。内訳が 2 層 | A |
| 23 | descriptor — **構造と digest 定義**(design.md 3-1・3-5) | schema 検証緑。digest が再現可能。参照先だけ変えると digest が変わる(負例 1 件) | A |
| 24 | descriptor — **`stateTransitionAxes`**(D-11:203 の**全軸** — 主要フラグ 10 + **イベント全種** + **履歴文脈**) | **D-11:203 の軸をすべて収容**(逐条で対応づけ)。典拠の無い軸で fail(負例 2 件)。**値域は条文から独立に導出**し、**`history-depth.json` を参照しない**ことを依存トレースで確認(9 周目 R9-P1-2)。**`D` はシンボルのまま**(実値は段階 2) | A |
| 25 | descriptor — **`gameEndAxes`**(D-11:204 の全軸)+ **`nonCoverageFields` 3 件** | D-11:204 の 4 軸 + 組合せ規則を収容。**`nonCoverageFields` が DH 制・`tiebreak.runnerPlacement`・`tiebreak.leadoffRule` の 3 件**(付録F-1 の全 5 フィールドが coverage 軸か `nonCoverageFields` のどちらかに帰属し、**脱落が 0 件**)。**射影規則で schema 側に保持される** | A |
| 26 | descriptor — **`projectionRules`**(schema への射影 + ID・版・digest 拘束 + 判定不能 fail) | 射影規則が全軸を覆う。**判定不能で fail**(負例 1 件) | A |
| 27 | **要件書 / ADR / descriptor の 3 点突合検査** | 3 点一致で緑。1 点ずらすと fail(負例 3 件)。抽出対象が機械可読 ID | A |
| 28 | **`gapRegister` の骨格**を作り `clauseIds` を埋める | 全 9 エントリが `open` で `clauseIds` を持つ。**条文 ID の実在検査**が緑 | A |
| 29 | **ゲート投入コミット** — 3 正本の frontmatter を `in-review` へ / 変更履歴の射程宣言 / `docs/README.md` の索引 / **worklog の適用版 + 条文 commit SHA** | `check_docs_status.py` 緑・docs-lint 緑・lychee 緑。**4 点すべてが同一コミット**(`/finalize-doc` 手順 1 と一致)。→ **確定ゲート(ステップ外)** | A |
| 30 | 状況判定契約 schema — **構造** | 層の欠落で fail(負例 3 件) | B |
| 31 | 同 — **参照制約**(行 ID 一意 / `cases[]` の解決 / 語彙シード参照) | 3 種の負例で fail | B |
| 32 | 同 — **値域制約**(ステップ 4 の全 10 列) | 10 列それぞれに負例 1 件以上 | B |
| 33 | 同 — **交差制約**(`XC-01`〜`XC-09`) | **各 `XC-*` に負例 1 件**が fail | B |
| 34 | **`operationRows[]` の別表 schema**(design.md 4-3) | 8 列すべてが required。欠落で fail(負例 2 件) | B |
| 35 | **`undoRows[]` の別表 schema**(同)— `targetKind` の閉じた enum・`guaranteeMode` | `"undo"` を含むと fail(**`targetKind` の enum が排除** — 交差制約ではない)。`guaranteeMode` の enum 外で fail | B |
| 36 | **`mustOperationCoverage`** — 写像と **5 検査** | 5 検査それぞれに負例 1 件 | B |
| 37 | 終了判定契約 schema | 付録F-1 の 5 フィールド。schema 外値の混入で fail(負例 5 件) | B |
| 38 | 語彙シードを作成する | `vocab.ts` 由来の集合と完全一致。ID の一意性。同一 ID に異なる表示名で fail | B |
| 39 | 語彙シードの内容 hash 宣言と乖離検出 | 1 文字変えると fail(負例 1 件)。宣言先が D-12 どおり | B |
| 40 | `provenance` の schema と検査 | 作成者 = 独立確認者 / 旧資料のみ / 宣誓欠落で fail(負例 各 1 件) | B |
| 41 | allowlist と依存トレース — **導出器** | allowlist 外で fail(負例 3 件)。**主張を導出器に限る**と文書化 | B |
| 42 | allowlist と依存トレース — **展開器** | 同上(負例 3 件) | B |
| 43 | 人間確認の署名記録形式 | digest 不一致 / 宣誓欠落で fail(負例 各 1 件)。機械保証を装う文言が無い | B |
| 44 | `gapRegister` の schema と**状態別の検査述語**(design.md 7-2) | **`open`**: **連続した prefix のみ許可**。途中段の飛ばし・存在しない参照・既に埋めた段の逆方向不一致で fail(負例 3 件)。**`resolved`**: **5 段すべて必須 + 全段で双方向一致**(負例 2 件)。**`open` の途中状態を拒否しない**ことを正例で確認 | B |
| 45 | `.claude/core-areas.json` へ paths 追加 + `contracts/README.md` + `tests/test_core_guard.py` | `pytest tests/` 緑・`core-guard` 緑。**6.3-⑤ の敵対レビュー + 人間承認** | B |
| 46 | **`clauseBranchRegister`** — 改訂後の条文から分岐を列挙。**分岐数の実数を出す** | 各分岐に由来条文 ID(実在検査)。終了判定に**通常終了 / 延長継続 / 上限引き分け / タイブレーク継続**を含む。作成者を署名記録に残す | C |
| 47 | **`gapRegister.branchIds` を埋める** | 全 9 エントリが `branchIds` を持ち、`clauseBranchRegister` と双方向一致。**実資産へ `open` の prefix 検査を適用して緑** | C |
| 48 | `requiredSet` ①行の要求の独立導出器 | 規範行を 1 行削ると fail / 要求に無い行を足すと fail / 典拠の無い分割規則で fail | C |
| 49 | `requiredSet` ②入力座標の要求(descriptor から導出) | 依存トレースで展開器のルールを読んでいないことを確認。「全規範行 + 各 1 case」で fail | C |
| 50 | `requiredSet`(終了判定) | 「既定の 9 回制だけ」で fail | C |
| 51 | `matrixRows[]` — 打撃結果(継続 4) | 全行が exact 型と `XC-*` を充足。`provenance` 緑。**人間の逐行確認** | C |
| 52 | `matrixRows[]` — 打撃結果(三振系 5) | 同上 | C |
| 53 | `matrixRows[]` — 打撃結果(四死球系 3) | 同上 | C |
| 54 | `matrixRows[]` — 打撃結果(安打系 4) | 同上 | C |
| 55 | `matrixRows[]` — 打撃結果(凡打系 3: 凡打死・凡打出塁・ファールフライ) | 同上 | C |
| 56 | `matrixRows[]` — 打撃結果(併殺系 2 + エラー・野手選択 2) | 同上 | C |
| 57 | `matrixRows[]` — 打撃結果(犠打系 3: 犠打・犠飛・犠打失策) | 同上。**26 値すべてが揃う**ことを検査 | C |
| 58 | `matrixRows[]` — 打撃結果2(7・妨害系 3 種を含む) | 同上。妨害系がステップ 13 の条文を典拠にしている | C |
| 59 | `matrixRows[]` — 走者イベント(作戦 3 系統) | 同上 | C |
| 60 | `matrixRows[]` — 走者イベント(投手牽制・捕手牽制) | 同上。**走者イベントが `matrixRows[]` 側にある**ことを検査 | C |
| 61 | `operationRows[]` — **選手交代(FR-011)** | ステップ 20 の D-8 の型に適合。`provenance` 緑 | C |
| 62 | `operationRows[]` — **タイブレーク開始(FR-009)** | 同上 | C |
| 63 | `operationRows[]` — **試合終了宣言(FR-010)** | 同上 | C |
| 64 | `operationRows[]` — **その場登録(FR-015)** | 同上 | C |
| 65 | `undoRows[]` — **規範行**(空履歴 / 履歴先頭の種別 / 連続 undo / 深さ `D`) | 全行が必須列を充足。`provenance` 緑 | C |
| 66 | `undoRows[]` — **`D`+1 の行**(`guaranteeMode: liveness-only`) | `XC-09` を充足。**出力同値を要求していない**。**`mustOperationCoverage` が 6 種を覆う** | C |
| 67 | `decisionRows[]` — 規定イニング数・延長上限 | 全列充足。**通常終了 / 延長継続 / 上限引き分け**の分岐 | C |
| 68 | `decisionRows[]` — コールド・タイブレーク | 同上。**タイブレーク継続**の分岐 | C |
| 69 | **`gapRegister.rowIds` を埋める** | 全 9 エントリが `rowIds` を持ち、規範行 4 層と双方向一致。**実資産へ `open` の prefix 検査を適用して緑** | C |
| 70 | **手作業 fixture — 状況判定**(`clauseBranchRegister` の該当分岐に最低 1 件) | 各 fixture の `provenance` が要件書または公認野球規則の典拠を持つ。作成者を記録 | C |
| 71 | **手作業 fixture — 終了判定** | 同上 | C |
| 72 | 手作業 fixture と `clauseBranchRegister` を双方向突合 | 台帳にあって fixture に無い分岐 0 件 / 逆も 0 件 | C |
| 73 | 手作業 fixture を凍結(7.7 準拠) | 資産側への宣言 / 追記のみの更新履歴 / 宣言不読・digest 不一致で fail(負例 2 件) | C |
| 74 | **`gapRegister.fixtureCaseIds` を埋める** | 全 9 エントリが `fixtureCaseIds` を持ち、fixture と双方向一致。**実資産へ `open` の prefix 検査を適用して緑** | C |
| 75 | 展開器 — **状況判定** | allowlist と依存トレースが有効。schema 検証を通る `cases[]` を出力 | D |
| 76 | 展開器 — **終了判定** | 同上 | D |
| 77 | 展開器の**決定性**と**手作業 fixture 一致** | 2 回実行で bit 一致。fixture と全分岐で完全一致(不一致 1 件で fail) | D |
| 78 | **`requiredSet` の変異耐性** | 軸削除 / 境界値変更で `requiredSet` 側に差分(変異 2 種で生存 0)。**限界の明記**がある | D |
| 79 | `cases[]` — 打撃結果(継続・三振系・四死球系) | `requiredSet` の①②両方との差分が空。件数と digest を記録 | D |
| 80 | `cases[]` — 打撃結果(安打系・凡打系) | 同上 | D |
| 81 | `cases[]` — 打撃結果(併殺系・エラー・野手選択・犠打系) | 同上 | D |
| 82 | `cases[]` — 打撃結果2 | 同上 | D |
| 83 | `cases[]` — 走者イベント | 同上 | D |
| 84 | `cases[]` — 操作(**FR-011**) | 同上 | D |
| 85 | `cases[]` — 操作(**FR-009**) | 同上 | D |
| 86 | `cases[]` — 操作(**FR-010**) | 同上 | D |
| 87 | `cases[]` — 操作(**FR-015**) | 同上 | D |
| 88 | `cases[]` — undo・履歴文脈 | 同上。空履歴 undo が存在。**`D`+1 が `liveness-only` と `tags` に明示** | D |
| 89 | 正規化 — **schema**(生値 / 規則識別子 / 正規化後の値の 3 点) | schema 検証緑。3 点を欠くと fail(負例 1 件) | D |
| 90 | 正規化 — **既存 case への反映** | 全 case が 3 点を持つ。正規化前後で値が変わる case が最低 1 件 | D |
| 91 | 正規化 — **identity 変異の負例** | **非正規形 raw + normalizer を identity へ変異すると突合が fail**(負例 2 件)。**「正規形 raw を拒否」は条件に含めない** | D |
| 92 | `cases[]` — 終了判定(**通常終了・延長継続**) | `requiredSet` との差分が空。両分岐が存在 | D |
| 93 | `cases[]` — 終了判定(**上限引き分け・タイブレーク継続**) | 同上 | D |
| 94 | `cases[]` — 終了判定(**コールド・サヨナラ**) | 同上。**サヨナラ余剰得点が付録A-1:1103 どおりクランプ** | D |
| 95 | `cases[]` — 終了判定(**X 表記・入力ロック・促し・自動遷移なし**) | 同上。**全 case が「試合状態は遷移しない」を `expected` に持つ** | D |
| 96 | `validationErrors[]` を分離 | 正常系に schema 外値が 0 件。各件が「保証範囲外」と明示 | D |
| 97 | **`gapRegister.generatedCaseSelector` を埋め `resolved` へ遷移** | 全 9 エントリが 5 段すべてを持ち双方向一致。**全エントリが `resolved`**。**実資産へ `resolved` の検査を適用して緑** | D |
| 98 | 検査配線 — **全行参照** | 緑。負例で fail | E |
| 99 | 検査配線 — **孤立行なし・行 ID 解決** | 緑。負例 2 件で fail | E |
| 100 | 検査配線 — **`mustOperationCoverage`** | 5 検査が CI で走る | E |
| 101 | 検査配線 — **値域・交差制約** | ステップ 32・33 の負例がすべて fail | E |
| 102 | 検査配線 — **`requiredSet` 差分(①②)** | 緑。負例 2 件で fail | E |
| 103 | 検査配線 — **件数・digest** | 緑。負例 2 件で fail | E |
| 104 | 検査配線 — **凍結と fixture 一致** | 緑。fail-closed(宣言不読で fail) | E |
| 105 | **数値基準を実測して確定**(design.md 3-6) | 実サイズ・増分・実行秒数に実測値と測定条件(コマンド・試行回数・判定統計・ランナー条件)。**16 MB を超えていない** | E |
| 106 | 台帳候補 (10) → **`H-90`** + 変更履歴 1 行 + **`docs/README.md` の台帳行を同一コミットで** | `check_docs_status.py` 緑。**採番時の未使用検査**。**3 点が 1 コミット** | E |
| 107 | **未解消レポート** | `gapRegister` の状態 / 人間統制に委ねた項目 / 段階 2 へ送った項目の 3 区分。各項目に送り先または担当 | E |
| 108 | 引き渡し契約 — **`consumerBindings[]` の本体**(design.md 1-3) | 対象計算 2 件それぞれに `contractPath` / **`version` と `schemaVersion` の両方** / `caseSchemaRef` / **JSON Pointer ベースの `caseFieldMapping`**(`id`/`input`/`expected`/`tags` → `caseId`/`raw`/`normalized`/`expected`/`tags`)/ **`normalizationComparison` と `outputComparison` の 2 面** / `dPlusOnePolicy`。**schema 検証が緑** | E |
| 109 | 引き渡し契約 — **`executionPaths[]`**(design.md 1-3)| 各 binding に **runner の exact-set**。**`"pytest"` と `"vitest"` の 2 経路**((α) は両 runner が対象 — ADR-003:284)。各経路に `normalizerId` / `entrypointId` / `directTargetId`。**`runnerRevision` は段階 1 では `"pending"`**(Vitest 側は TSK-455 未着手・pytest 側は TSK-235 未マージ)で `resolutionStage: "stage-2"` を持つ。**片方の経路しか無いと fail**(負例 1 件) | E |
| 110 | 引き渡し契約 — **`dependencies[]` / `stage2EntryGate` / 残りのフィールドと受取タスクの起票** | 各依存に **commit OID・版・成立条件**(task ID だけでは不可)。`stage2EntryGate` が「トップレベル読込 / 版検査 / binding 構築 / `D`+1 を含む全 case 消費」を含む。`artifacts[]` の digest が実ファイルと一致。`consumptionVerification: "pending"`。`receiverTaskId` が実在。**`descriptorParity` が射影規則を参照** | E |

## 5. DoD(受け入れ基準)

- [ ] **要件書**が改訂されている(付録E-1 の境界・**全 10 列の exact 型**・**`XC-01`〜`XC-09`**・表示名の読み替え /
      **定義の穴 9 件** / 管理者語彙の二段階ゲート / NFR-018(b)②)
- [ ] **ADR-003 D-11 / D-6 / D-8 / D-12** が改訂され、**D-11 で descriptor が両段階を通した唯一の正**になっている
- [ ] **`docs/design/sync-protocol.md`** が改訂されている
- [ ] 上記 3 正本が**同一 PR・同一確定ゲート**(7.3)を通っている
- [ ] **descriptor** が D-11:203-204 の**全軸**を収容し、**`nonCoverageFields` 3 件**(DH 制・`tiebreak.runnerPlacement`・
      `tiebreak.leadoffRule`)と `projectionRules` を持ち、要件書・ADR と**3 点突合が緑**。
      **値域を条文から独立に導出**し、**`history-depth.json` を参照していない**(一致検査は段階 2)
- [ ] **`gapRegister` の全エントリが `resolved`** で、**5 段**(clause → branch → row → fixture → case)が双方向一致。
      **`open` の途中状態は連続 prefix のみ許可**する述語が実資産へ適用されている
- [ ] 付録E 全表が完成している(**`mustOperationCoverage` の 5 検査が緑**、
      **`requiredSet` の ①行 / ②座標の双方向差分が空**、**変異耐性が生存 0**)
- [ ] **終了判定ベクタが別契約**として作成され、**通常終了 / 延長継続 / 上限引き分け / タイブレーク継続**を含む
- [ ] **語彙シード**と**内容 hash による乖離検出**
- [ ] **`clauseBranchRegister`** と **手作業 fixture** の双方向差分が空で、**fixture が 7.7 準拠で凍結**
- [ ] **oracle 遮断 4 層**が配線され、**機械保証と人間統制の境界が明示**されている
- [ ] **数値基準が実測で確定**している
- [ ] **`.claude/core-areas.json`** に paths 登録(6.3-⑤ の承認済み)
- [ ] **候補 (10) が `H-90` へ昇格**し、**台帳・変更履歴・索引が同一コミット**
- [ ] **規範行の人間確認が署名付きで記録**され、**PR の逐行確認記録と対応**している
- [ ] **未解消レポート**と、**exact 型の引き渡し契約** — `consumerBindings[]` に
      **`executionPaths[]`(pytest / vitest の 2 経路)**・**2 面の比較契約**・JSON Pointer ベースの `caseFieldMapping`、
      `dependencies[]` に **commit OID・版・成立条件**、`consumptionVerification: "pending"`、`stage2EntryGate`、
      受取タスク起票済み
- [ ] **FR-007 再開の検証先が [TSK-454](https://app.notion.com/p/3e593b75e687813bbe17c36d17ebee63) として記録**

**DoD に書かないこと**: 「NFR-019(a) 合格」(`BOOT-NO-CLAIM`)。
**runner による契約の消費 / 製品 manifest 登録 / 正規化の計算投入証跡 / FR-040 の manifest 記載 /
descriptor と schema の射影検査も書かない**(**段階 2**)。

## 6. テスト計画

| 種別 | 追加するもの |
| --- | --- |
| **(a) 一致性テスト** | 成果物が正解ベクタ。**段階 1 では runner を動かさない**(段階 2)。合格の宣言もしない(`BOOT-NO-CLAIM`) |
| **単体** | 契約 schema — 構造 / 参照 / **値域(全 10 列に負例)** / **交差制約(`XC-01`〜`XC-09` に各 1 件)** |
| **単体** | **`operationRows[]` / `undoRows[]` の別表** — 必須列の欠落 / `targetKind` に `"undo"` / `guaranteeMode` の enum 外 |
| **単体** | **`mustOperationCoverage` の 5 検査** |
| **単体** | **descriptor** — 典拠の無い軸 / digest の再現性 / 参照先だけの変更 / 射影の判定不能 / 3 点突合の 1 点ずらし |
| **単体** | **`requiredSet`** — 双方向差分(2 段)/ **変異耐性**(生存 0) |
| **単体** | **`clauseBranchRegister` と fixture の双方向差分** / **fixture の凍結**(fail-closed) |
| **単体** | **語彙シード** — `resultId` の解決 / 同一 ID に異なる表示名 / 内容 hash の乖離検出 |
| **単体** | **正規化** — 非正規形 raw + identity 変異で突合 fail / 3 点の欠落 |
| **単体** | **oracle 遮断** — 作成者 = 独立確認者 / 旧資料のみ / 宣誓欠落 / allowlist 外(導出器・展開器)/ digest 不一致 / fixture 不一致 |
| **単体** | **展開器の決定性** |
| **単体** | **`gapRegister`** — 逆遷移 / 重複 ID / 未知 ID / 実在しない条文 ID / **5 段の途切れ** / **5 段未充足での `resolved`** |
| **(b) 越境** / **(c) E2E** / **(d) 故障系** | **反映なし**。FR-007 再開は TSK-454、FR-006 のキュー投入は同期側のテスト |
| ハーネス | `tests/test_core_guard.py` — `contracts/state-transition/**` が `game-state` として判定されること |

**最終検証は `/check` を実行する**(コマンドは `/check` の SKILL 本文が正)。
