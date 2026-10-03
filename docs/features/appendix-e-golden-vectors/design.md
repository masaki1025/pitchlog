---
feature: appendix-e-golden-vectors
type: design
date: 2026-09-24
---

# 詳細設計: 付録E ゴールデンケース全表 + 終了判定ベクタ(段階 1・ベクタ資産側)

plan.md 4 節から参照される詳細設計。調査の典拠は [research.md](./research.md)。

**v9(2026-09-24)**: 計画レビュー 8 周目の P1 4 件・P2 0 件を反映(7 周目の 7 件は解消 3 / 部分的 4 / 未解消 0)。
主要な変更: **`consumerBindings[]` に `executionPaths[]`(両 runner)と 2 面の比較契約**(1-3)/
**`history-depth.json` の権威関係を一意化し `nonCoverageFields` を 3 件に**(3-3・3-4)/
**述語 AST と `StateEffect` を閉じた型に + `eventKind` 別の合法組合せ表**(4-5・4-6)/
**`gapRegister` の `open` / `resolved` の述語を分離**(7-2)。

## 1. 段階 1 の終点

### 1-1. 本タスク = 段階 1 の**ベクタ資産側**成果物の完成

ADR-003:440-444 の段階 1 は「ベクタの schema と独立に確認した期待値」と「検査基盤」の双方。
**本タスクは前者のみ**(後者は TSK-235)。

| 区分 | 内容 |
| --- | --- |
| **本タスク** | 正本改訂 / descriptor / 契約 schema / 規範行 4 層 / 期待値 / `requiredSet` / `clauseBranchRegister` / 手作業 fixture / 語彙シード / oracle 遮断機構 / 未解消レポート / **段階 2 への引き渡し契約** |
| **段階 2** | 製品 manifest への計算登録 / **runner による契約の消費** / 正規化の計算投入証跡 / FR-040 宣言の manifest 記載 / **descriptor と schema の射影検査** |

### 1-2. runner 受入を段階 2 へ送る根拠

TSK-235 の `run_vectors()` はトップレベル契約や `schemaVersion` を読まず、
case に `caseId` / `raw` / `normalized` / `expected` を要求し(`vectors.py:150`)、
**全 case で `CalculationAdapter.execute()` を呼び出力一致を必須**とする(同:205)。
一方 ADR-003:267 の契約骨格は `id` / `input` / `expected` / `tags`、
`history-depth.json:145` は `D`+1 について出力同値を要求しない。
→ **段階 1 では両立しない**。最小 runner の自作は「検査基盤を作らない」と矛盾する。

### 1-3. 引き渡し契約(7 周目 P1-1 の是正)

v7 の 7 フィールドは**名前と概括だけ**で、受取側に必要な binding が無く、
「抽象的な文を入れて通せる」合格条件だった。→ **exact 型にする**。

```
handoffVersion / calculationIds[2]

consumerBindings[]:            ← 対象計算ごとに 1 件
  calculationId / vectorId / contractPath
  version / schemaVersion     … 契約ファイルの版と schema の版を**両方**
  caseSchemaRef               … case schema への JSON Pointer
  caseFieldMapping            … **JSON Pointer ベース**。契約の id/input/expected/tags →
                                runner の caseId/raw/normalized/expected/tags
  normalizationComparison     … 正規化面の比較契約(exact | lossless)
  outputComparison            … 出力面の比較契約(exact | lossless)  ← **比較は 2 面**
  dPlusOnePolicy              … "liveness-only"(拒否しない・切り捨てないのみ。出力同値を要求しない)
  executionPaths[]:           ← **実行経路の exact-set**(単数では (α) の両 runner を表せない)
    runner                    … "pytest" | "vitest"
    runnerRevision            … その runner の commit OID
                                **段階 1 では "pending"**(Vitest 側は TSK-455 が未着手・
                                pytest 側は TSK-235 が未マージのため確定できない — 9 周目 R9-P1-1)
    normalizerId / entrypointId / directTargetId
    resolutionStage           … "stage-2"(revision の確定は段階 2)

artifacts[]:  path / version / digest
dependencies[]: taskId / artifactPath / commitOid / version / 成立条件   ← task ID だけでは不可
receiverDoD[]
fr040Declaration              … 内容と根拠(記載先は段階 2)
descriptorParity              … 3-4 の射影規則への参照
consumptionVerification: "pending"   ← 段階 1 では未検証であることを明示
stage2EntryGate               … 段階 2 の最初の停止ゲート(下記)
receiverTaskId
```

**`executionPaths[]` を exact-set にする理由**(8 周目 P1-1): 本件の 2 契約はいずれも **(α)** であり、
**pytest と Vitest の両方**による全件消費が要る(ADR-003:284)。既存 runner のキーは
`calculation / vector / case / runner / entrypointId / directTargetId` の **6 次元**で、
**比較契約も 2 面**(`vectors.py:56` / `:178`)。単数の `runnerRevision` / `entrypointId` / `directTargetId` と
単一の `comparison` では、受取側が一意に `VectorContract` を構築できない。

**段階 1 で「実際に消費可能」とは主張しない。** `consumptionVerification: "pending"` を明記し、
**段階 2 の最初の停止ゲート**を「**トップレベル読込 / 版検査 / binding 構築 / `D`+1 を含む全 case 消費**」と定める。

## 2. 正本改訂

### 2-1. 順序(plan.md と一本化 — 7 周目 P1-5)

**要件書 → ADR-003 → 同期正本 → descriptor → 3 点突合 → `gapRegister` 骨格 → ゲート投入**。

**`in-review` 化はゲート投入コミットで行う**(descriptor と 3 点突合の後)。
v7 は design.md 内に「先に `in-review` で起案」と「descriptor 後に `in-review`」が混在していた。
→ **後者に統一する**。

**ゲート投入コミットの内容**(`/finalize-doc` 手順 1 に一致させる):
3 正本の frontmatter / 変更履歴の射程宣言 / `docs/README.md` の索引 / **worklog の適用版 + 条文 commit SHA**。
**`gapRegister` の骨格作成は別ステップ**。

### 2-2. 同期プロトコル正本

S2(:1309)と :1588 の正を「**D-6 で登録された状況判定ベクタ全体**」とし、内訳を
E-1 準拠の `matrixRows[]` と、該当 FR(FR-006 / FR-009 / FR-010 / FR-011 / FR-015)を典拠とする
`operationRows[]` / `undoRows[]` として記述。**D-8 は入力・出力・比較面の参照に限定**。

## 3. 入力軸 descriptor — **両段階を通した唯一の正**(7 周目 P1-2 の是正)

v7 は「段階 1 = descriptor / 段階 2 = schema」と**正が段階で交代する**記述で、
descriptor を一意の正にしたことにならなかった。また軸が D-11 の全体を覆っていなかった。

→ **descriptor を両段階を通した唯一の正とし、段階 2 の宣言モデル schema は
「descriptor に拘束される派生物」と D-11 に明記する**。

### 3-1. 構造

```
descriptorId / version / digest
stateTransitionAxes[]   … D-11:203 の全軸
gameEndAxes[]           … D-11:204 の全軸
nonCoverageFields[]     … schema で保持するが coverage 軸ではないもの
projectionRules[]       … schema への射影規則(3-4)
```

各軸: `axisId` / **由来条文 ID** / 分類(`finite-enumerable` / `boundary-partition` / `non-finite`)/
値集合 or 境界値 or 非有限の根拠。

### 3-2. `stateTransitionAxes`(D-11:203 の全軸)

| 群 | 軸 |
| --- | --- |
| 主要フラグ | `half` / `count.strikes` / `count.balls` / `outs` / `runners` / `battingOrder` / `tiebreakActive` / `gameEnded` / `inning` / `score` |
| **イベント** | **断中操作イベントの全種**(毎球入力の結果値 33 + 走者イベントの payload + 非毎球入力 4 種 + undo) |
| **履歴文脈** | **深さ**(0 / 1 / 2 / `D`)/ **構成の等価分割** / **シナリオ長**(1 / 2 / `D` / `D`+1) |

### 3-3. `gameEndAxes`(D-11:204 の全軸)

**規定イニング数** / **コールド条件**(点差・回・**段の配列長**)/ **延長上限** / **タイブレークの有無と開始回**。
組合せ規則(ペアワイズ + 境界値 × 状態×イベント の直積)も descriptor に持つ。

**`nonCoverageFields`**(付録F-1 の全 5 フィールドのうち終了判定に影響しないもの — 8 周目 P1-2):

| フィールド | 理由 |
| --- | --- |
| **DH 制** | 打順の構成に影響するが、**いつ試合が終わるか**には影響しない |
| **`tiebreak.runnerPlacement`**(走者配置) | タイブレーク**開始時の初期状態**を決めるが、終了条件の判定に入らない |
| **`tiebreak.leadoffRule`**(先頭打者規則) | 同上 |

**3 フィールドとも `nonCoverageFields` に列挙し、射影規則で schema 側に保持する**
(coverage 軸ではないが、派生 schema から脱落させない)。

### 3-4. 射影規則と拘束

| 項目 | 内容 |
| --- | --- |
| 射影規則 | descriptor の軸 → 宣言モデル schema の JSON Schema 表現への対応(整数範囲 → `minimum`/`maximum`、enum → `enum` 等)。**表現差を吸収して比較できる形** |
| 拘束 | schema は descriptor の **`descriptorId` / `version` / `digest`** を参照し、**exact-set / 値域一致**しなければ **manifest 登録不可** |
| 判定不能 | **fail**(fail-closed) |
| **既存資産との関係** | **descriptor は `history-depth.json` を参照しない**(9 周目 R9-P1-2 の是正)。同ファイルは **develop に存在しない**ため、参照すると **TSK-235 を待たない方針と両立しない**。descriptor は**値域を条文から独立に導出**し(3-2)、**`history-depth.json` との一致検査は段階 2** の `descriptorParity` で行う。**`D` の値も段階 2 で解決**する(段階 1 はシンボルのまま) |

**この射影検査の実行は段階 2**(引き渡し契約の `descriptorParity` で条件を渡す)。

### 3-5. digest

`digest` フィールドを除いた正規化 JSON の SHA-256(正規化方式を descriptor 自身に明記)。
**段階 1 の descriptor は外部参照を持たない**(3-4)ため、推移的 digest は不要。
**外部参照を持つ場合の規則**(JSON Pointer + 内容 hash による推移的 digest)は、
段階 2 で schema との射影を記録するときに適用する。

### 3-6. 数値基準は実測後に確定

契約ファイルの byte 上限 **16 MB** のみ計画時点で確定。
実サイズ・リポジトリ増分・検査の実行秒数は**フェーズ D 完了後に実測**し、
測定コマンド・試行回数・判定統計・CI ランナー条件を明記する。`ci.yml` には結ばない。

## 4. 契約の構成

```
状況判定: matrixRows[] / operationRows[] / undoRows[] / mustOperationCoverage / requiredSet / cases[]
終了判定: decisionRows[] / requiredSet / cases[] / validationErrors[]
```

### 4-1. `mustOperationCoverage` の 5 検査

①参照先の実在 ②行層・`eventKind` との一致 ③重複禁止 ④未帰属行の検出
⑤毎球入力の 3 下位分類の exact-set。**各検査に負例 1 件**。

### 4-2. `matrixRows[]` — E-1 **全 10 列**の exact 型(7 周目 P1-3 の是正)

v7 は 7 行しかなく、`イベント種別` / `結果ID・表示名` / `打席の終了` が欠けていた。

すべて `additionalProperties: false`、下表の列は**全て required**。

| # | 列 | exact 型 |
| --- | --- | --- |
| 1 | `eventKind` | `enum["batting-result", "secondary-result", "runner-event"]` |
| 2 | `resultId` | `string`(語彙シードの ID。参照整合)。**表示名は持たない**(語彙シードが正) |
| 3 | `precondition` | **述語 AST**(閉じた再帰型 — 4-6) |
| 4 | `countEffect` | `{strikes: Effect, balls: Effect}`。`Effect = {kind: "delta", value: int} \| {kind: "reset"} \| {kind: "unchanged"}`。**`kind: "reset"` と `"unchanged"` は `value` を持たない**(`additionalProperties: false`)。`delta` の `value` は strikes 0..2 / balls 0..3 |
| 5 | `plateAppearanceEnded` | `boolean \| enum["not-applicable"]` |
| 6 | `batterDestination` | `{kind: "continue" \| "out" \| "score" \| "not-applicable"}` または `{kind: "reach", base: 1..3}` |
| 7 | `runnerDefaultAdvance` | `{first: Adv, second: Adv, third: Adv}`。`Adv = {modality: enum["forced","optional","hold","not-applicable"], destination: 1..4 \| null}`。**`forced` / `optional` ⇔ `destination != null`**、**`hold` / `not-applicable` ⇔ `destination = null`**(双方向)。**起点塁別の到達可能集合**: first → {2,3,4} / second → {3,4} / third → {4}(research.md 7 節) |
| 8 | `outEffect` | `{count: 0..3, targets: [Target]}`。`Target = "batter" \| {runner: 1..3}`。**`count` と `targets` の長さが一致**。`count: 0` なら `targets` は空 |
| 9 | `statFlags` | **定義の穴 2 で確定した完全なキー集合**の各キー → `boolean`。**未知キーで fail**(`additionalProperties: false`)。**穴 2 の条文化を本表より前のステップに置く**(8 周目 P1-3 — 外延が閉じる前に exact 型は書けない) |
| 10 | `remarks` | `string`(**自由記述を許す唯一の列**) |

#### 4-2-1. 申告敬遠の `resultId` と投球有無(2026-09-29 PO 裁定)

要件書 4.0-2 の「FR-002 の必須項目（コース・球種・打撃結果）は投球イベントに限る」は、
記録画面で必須とする入力項目を定める規定であり、状態遷移契約の `resultId` に
`batting-result.intentional-walk` を用いることを禁じる規定とは読まない。申告敬遠の規範行は
`eventKind = batting-result`、`pitchEventKind = non-pitch-event` とし、`投球数`を計上しない。

この読みは旧 88 列の実測とも整合する。`docs/legacy/research/data-layer.md` では、45 列
「打撃結果」の 26 値に「申告敬遠」が含まれる一方、40 列「プレイの種類」は
「投球」／「牽制」／「ボーク」／「ピッチクロック違反」であり、申告敬遠を含まない。
したがって、要件書 4.0-2 の「旧版も『プレイの種類』列で同じ区別をしていた」という説明は、
牽制・ボーク・ピッチクロック違反には当てはまるが、申告敬遠には当てはまらない。

PO は 2026-09-29、旧機能の全面踏襲を前提に、記録者が打撃結果のドロップダウンから
申告敬遠を選ぶ入力経路を変えないことを決め手として、上記の扱いを裁定した。
これは承認済み要件書の改訂ではなく、本実装で採る条文の読みを固定する記録である。

#### 4-2-2. `凡打出塁` の状態効果と公式記録の境界(2026-09-30 PO 裁定)

`docs/legacy/research/input-screen.md:68` が記録する旧入力画面では、`凡打出塁`は
`凡打死` / `併殺打` / `ライナー併殺` / `ファールフライ` と同じ `outs`
カテゴリにある。`エラー` / `野手選択` / `犠打失策` は別の `miss`
カテゴリにあり、記録者の入力経路も異なる。同 `:163` は `凡打出塁`について、
打者の状態を出塁とし、全在塁走者を1塁ずつ進める旧状態効果を記録している。

PO は 2026-09-30、旧機能の全面踏襲と記録者の入力経路を変えないことを決め手とし、
`凡打出塁` を「凡打だが打者が生きた」値として、打者一塁出塁・全在塁走者の1進を
状態効果に置くと裁定した。ただし、`outs` と `miss` の入力カテゴリが異なる事実は、
`凡打出塁` の公式記録上の分類や失策の有無を定めない。`FR-004` の `officialScoringPayload`
と `official-scorer-judgment-input-contract`、およびそれらからの失策フラグ導出は段階2で確定する。

この裁定は承認済み要件書の改訂ではなく、旧実態から本実装に写す状態効果と、
本段階では定めない公式記録上の分類の境界を固定する記録である。

### 4-3. `operationRows[]` / `undoRows[]` の必須列(別表)

E-1 の 10 列を持たないため**独自に定める**。

**`operationRows[]`**(選手交代 FR-011 / タイブレーク開始 FR-009 / 試合終了宣言 FR-010 / その場登録 FR-015):

| 列 | 型 |
| --- | --- |
| `operationKind` | `enum["substitution","tiebreak-start","game-end-declaration","adhoc-registration"]` |
| `clauseId` | 典拠 FR の条文 ID |
| `payloadShape` | JSON Schema(`additionalProperties: false`) |
| `precondition` | 4-2 の述語 AST と同型 |
| `stateEffect` | **`StateEffect`**(4-6 の閉じた型)。**非影響面は `{kind: "unchanged"}`** |
| `historyEffect` | `{pushes: boolean, kind: string \| null}`(`pushes: false` なら `kind: null`) |
| `operationResult` | `enum["applied","rejected-precondition","rejected-invalid-payload"]` |
| `remarks` | `string` |

**`undoRows[]`**:

| 列 | 型 |
| --- | --- |
| `targetKind` | `enum["confirmed-play"]`(**FR-040 採用時に `"state-correction"` が加わる**。**`"undo"` を含めない**のが不変条件) |
| `precondition` | 履歴文脈の述語(深さ・先頭の種別) |
| `stateEffect` | **`StateEffect`**(4-6)。対象操作の差分の逆適用。**非影響面は `{kind: "unchanged"}`** |
| `historyEffect` | `{pops: 0 \| 1}` |
| `operationResult` | `enum["applied","nothing-to-undo"]` |
| `guaranteeMode` | `enum["full-equality","liveness-only"]`。**`D`+1 の行は `liveness-only`** |
| `remarks` | `string` |

### 4-4. 交差制約(すべてに `XC-*`)

| ID | 述語 |
| --- | --- |
| `XC-01` | `eventKind = runner-event` なら `batterDestination.kind = not-applicable` |
| `XC-02` | `precondition` が当該塁の走者不在を含むなら、その塁の `Adv.modality = not-applicable` |
| `XC-03` | `Adv.modality ∈ {hold, not-applicable}` なら `destination = null` |
| `XC-04` | `outEffect.count = targets.length` |
| `XC-05` | `eventKind = runner-event` なら `countEffect.*.kind = unchanged` |
| `XC-06` | `batterDestination.kind = continue` なら `plateAppearanceEnded = false` |
| `XC-07` | **双方向**: `plateAppearanceEnded = not-applicable` ⇔ `eventKind = runner-event`(片方向だと走者イベントに `true`/`false` を設定できてしまう) |
| `XC-08` | **`Adv.destination` が起点塁別の到達可能集合に含まれる**(一塁走者の一塁到達・三塁走者の二塁到達などを禁止)。`targetKind` に `"undo"` を含まないことは **`undoRows[]` の enum が既に排除**しているため交差制約から外す |
| `XC-09` | `guaranteeMode = liveness-only` は `D`+1 の行のみ |

### 4-6. 共通の閉じた型(`$defs` 相当 — 8 周目 P1-3)

散文で書いていた型を閉じる。**すべて `additionalProperties: false`**。

**`Predicate`**(述語 AST・再帰型。**演算子ごとの arity を固定**):

```
Predicate =
  | {op: "and" | "or",  args: [Predicate, ...]}        … arity >= 2
  | {op: "not",         args: [Predicate]}             … arity == 1
  | {op: "eq" | "gte" | "lte", axisId: string, value: Literal}
  | {op: "in",          axisId: string, values: [Literal, ...]}   … 非空
Literal = integer | boolean | string            … string は当該軸の enum 値のみ
```

**`axisId` は descriptor の軸 ID として実在すること**(参照整合)。
**`value` / `values` の型と値域は当該軸の分類・値集合に適合すること**。

**`StateEffect`**(比較面 4 面への影響):

```
StateEffect = {
  stateFields:   {<比較面の各フィールド>: FieldEffect}   … 全フィールド required
  scoreboard:    {<全欄>: FieldEffect}
  statFlags:     {<完全なキー集合>: FieldEffect}
  historyAndResult: {history: FieldEffect, operationResult: FieldEffect}
}
FieldEffect = {kind: "unchanged"} | {kind: "set", value: <当該フィールドの型>}
            | {kind: "delta", value: integer}
```

**「非影響面は `unchanged`」を型で強制する**(省略を許さない — ADR-003:324 の比較面を縮小しないため)。

### 4-5. `eventKind` 別の合法組合せ表(8 周目 P1-3)

`XC-*` は**片方向の禁止**しか表せず、不正な組合せを許していた。→ **合法組合せを表で固定する**。

| `eventKind` | `countEffect` | `plateAppearanceEnded` | `batterDestination.kind` |
| --- | --- | --- | --- |
| `batting-result` | 任意 | `true` \| `false` | `continue` \| `reach` \| `out` \| `score` |
| `secondary-result` | `unchanged` \| `delta` | `true` \| `false` | `continue` \| `reach` \| `not-applicable` |
| **`runner-event`** | **`unchanged` 固定** | **`not-applicable` 固定** | **`not-applicable` 固定** |

**表に無い組合せはすべて fail**(allowlist 方式)。

**各 `XC-*` につき最低 1 件の負例**を置く。

## 5. `requiredSet`

①行の要求(語彙シードの ID 集合 × 前提条件の分割規則・条文 ID 必須)と
②入力座標の要求(**descriptor から導出**。展開器のルールは読まない)の 2 段。

### 5-1. ①行の要求に用いる語彙軸と分割規則

①の語彙 ID 集合は、語彙シードの全値ではなく、次の `eventKind` ごとの
`resultId` 源から取る。分類の機械可読な正は
`contracts/state-transition/required_set_row_rules_v1.json` とし、語彙シードの全軸が
`result-id-source` または `not-result-id-source` のちょうど一方へ属さなければ fail とする。

| 語彙軸 | 分類 | 理由 |
| --- | --- | --- |
| `batting-result` | `batting-result` の `resultId` 源 | E-1・FR-003 が打撃結果の状態遷移を規範行へ置く |
| `secondary-result` | `secondary-result` の `resultId` 源 | E-1・FR-004 が打撃結果2を規範行へ置く |
| `strategy-category` | `runner-event` の `resultId` 源 | FR-004・A-4 の作戦3系統を走者イベントとして識別する |
| `pitcher-pickoff-destination` / `catcher-pickoff-destination` | `runner-event` の `resultId` 源 | FR-004 の投手／捕手牽制と対象塁を識別する |
| `pitch-type` | 非 `resultId` 源 | 投球属性。4.0-3 はチーム拡張語彙に値ごとの状態遷移規範を持たせない |
| `strategy-detail` / `strategy-result` | 非 `resultId` 源 | 作戦イベントの内訳／結果であり、イベント種別ではない |
| `error-type` / `pickoff-result` | 非 `resultId` 源 | FR-004 の payload に属する公式記録／走者別結果である |
| `batted-ball-type` / `batted-ball-strength` | 非 `resultId` 源 | 4.0-3 が打撃結果から分離する打球情報である |
| `batter-status` / `first-runner-status` / `second-runner-status` / `third-runner-status` | 非 `resultId` 源 | E-1 の状態効果側の値である |

前提条件の分割は、条文が同一語彙 ID に複数行を要求すると明示するものだけを採る。
現時点の閉じた規則は、既定の単一行、E-2・`SO-03` の振り逃げセーフ／アウト、
および FR-004・E-1 の `INT-01`〜`INT-07` が定める妨害裁定3組の計5規則である。
各規則は安定した `partitionRuleId`、適用する語彙 ID、抽象 `partitionId`、
`sourceClauseIds` を持つ。抽象 identity は行の要求を数えるための識別子であり、
後続ステップの `Predicate` を先取りしたとの主張はしない。規則の追加は典拠条文 ID を必須とし、
典拠の無い分割、どの規則にも属さない `resultId`、複数規則に属する `resultId` を fail とする。

**変異耐性の検査は展開器の実装後**。検出するのは「片経路の実装差」であり、
**両経路に共通する欠落は検出しない**。

## 6. `expected`

比較面 4 面をすべて持つ。**表示値は持たせない**。
**操作イベント・undo の出力面もこの 4 面を縮小しない**(非影響面は `unchanged`)。
**再開(FR-007)** は TSK-454 へ。**FR-006 のキュー投入・同期状態非依存**は同期側のテストへ。

## 7. 要件改訂 — 定義の穴 9 件

1 H/E/K/B の定義 + 延長時の扱い / 2 成績計上フラグの外延 / 3 コールド成立のタイミング /
4 引き分け成立の条件 / 5 X 表記の一般規則 / 6 タイムプレイの判定規則 /
7 妨害系 3 種の遷移 + 強制/任意進塁・停止の判定規則 / 8 `K3` の意味 + 三重殺 /
**9 打点の算出定義**。

**穴 3〜6・8・9 には閉じた分岐 ID の集合と各分岐の正負例**を置く。

### 7-0. 穴 9(打点の算出定義)— 実装中に発見(2026-09-25)

**ステップ 2 の導出元を確認していて判明した。** 打点は要求されているが**算出定義が無い**。

| 箇所 | 記述 |
| --- | --- |
| FR-022(`:442`) | 当日打席結果の **7 列の第 6 列が「打点」** |
| FR-022(`:443`) | 当日の集計(打席数・打数・安打・**打点**・四球・死球・三振・犠打・犠飛)は上記の行から導出する |
| 付録E-1(`:1269`) | 成績計上フラグの列挙に **打点** |

一方 **付録A-3(打者指標)に打点の行が無い**(打数 / 本塁打 / 打率 / 出塁率 / 長打率 /
コース別打率マップ / 打球方向 のみ)。A-2・A-5 にも無い。
→ 「**いつ得点が打点として記録されるか**」(併殺打の間の得点・失策による得点の扱いなど)が未定義。

**典拠**: **公認野球規則 9.04**(8-3 の典拠優先順位の 2 位)。
旧システムは「『本進』集計、併殺打時は除外」(`analytics-reports.md:68`)だが**旧は規範ではない**。

**手続き**: 計画書の退路(`gapRegister` へ `open` で追記 → 再改訂の要否を判定)に従う。
**フェーズ A(確定ゲートの前)なので、同一 PR 内で 9 件目として条文化する**。

#### ステップ56で確認したフォース連鎖と打点条件の矛盾（2026-09-30 PO裁定）

要件書E-1の走者既定進塁は、フォース連鎖を
`batterDestination.kind = reach`の場合に限定している。この定義をそのまま適用すると、
打者が`out`になる併殺打の一塁走者は`ADV-02`ではなく`ADV-04`となる。一方、A-3の
`RBI-01`は、打者のゴロがフォースダブルプレイまたはリバースフォースダブルプレイと
なった間の得点を打点に算入しないため、併殺打をフォースプレイとして扱っている。
そのため、`RBI-01`の適用条件は現行の`ADV-*`の機械的判定だけから導出できない。

この矛盾は、打点算出を所有する`GAP-09`へ`open`のまま記録し、`clauseIds`に
`E-1`・`ADV-02`・`ADV-04`・`RBI-01`を追加する。行20は承認済み条文を優先して
一塁走者を`hold`とするが、野球規則上のフォースプレイとの意味的な不一致を解消したとは
扱わない。なお、現行の機械検査は`XC-02`・`XC-03`・`XC-08`による存在・null対応・
到達可能塁を検査するだけで、`ADV-01`〜`ADV-04`の最初に一致する分岐を強制していない。
この検出欠落も同じ矛盾の解決待ちとして`GAP-09`に含め、条文の解決前に検査だけを
固定しない。

#### ステップ57で確認した犠打失策の記録員判断(2026-09-30 PO裁定・案A)

公認野球規則9.08は、打者のバントで走者が進塁し、失策がなければ一塁でアウトに
なったと思われる場合に犠打を記録する。ただし同条は、走者を進めるためでなく安打を
得るためであったことが明らかと記録員が判断したときは、犠打を記録せず打数を記録する
という分岐を本文に持ち、疑義のあるときは常に打者に有利に扱うと定めている。
つまり`犠打`と、その帰結として9.02(a)(1)が定める`打数`の除外は、記録員判断に依存する。

この分岐は現行の入力からは導出できない。要件書に「犠打失策」の語は現れず、語彙シードの
`batting-result.sacrifice-bunt-error`は`id`・表示名・`classification`の3フィールドだけで
記録員判断を含意しない。さらに`docs/legacy/research/input-screen.md:70`・`:71`が記録する
とおり、旧システムは同じ「犠打失策」を`miss`(`batting_result_miss`)と
`sacrifice`(`batting_result_sac`)の2カテゴリに持っており、新語彙はこれを1値へ統合した。
statFlagsは23件必須のexact型であるため、値を置かずに段階2へ送ることはできない。

そこで行26は規則9.08の既定側、すなわち`犠打 = true`・`打数 = false`に倒して確定させ、
表現できない分岐を観測入力の欠落として`GAP-09`へ`open`のまま記録し、`clauseIds`に
`FR-004`を追加する。`FR-004`は結果IDが「エラー」以外のプレイに付随する失策を
`officialScoringPayload`へ保持することを定める条文であり、犠打失策の公式記録側の所有に
あたる。`gapId`は9件のexact-setとして機械検査されているため新規IDは立てず、
`rowIds`は既存9件と同じく空のままとする。記録の実体は本節と行26の`remarks`が持ち、
双方が`GAP-09`を名指しして相互に辿れるようにする。

この判断で製品のふるまいは変わりうる。安打狙いのバントが失策で出塁した打席で、
本来は打数に算入され犠打が付かないところを、打数から除外し犠打を計上するため、
打率と犠打数が変わる。段階2で記録員判断を観測入力として確定するまで、本行を
規則9.08の全体を満たしたものとして扱わない。

#### ステップ58で確認したピッチクロック違反の違反主体(2026-10-01 PO裁定・案C)

ピッチクロック違反は、違反した側によって逆向きのカウント効果を持つ。NPBが
2026-08-03に導入を決定した規則では、投手が制限時間内に投球動作へ入らなければ
1ボールが加えられ、打者が残り8秒までに打撃姿勢を整えなければ1ストライクが
加えられる。したがって1語彙値に対して本来3行が要る。投手側(ボール+1・打席継続)、
打者側の2ストライク未満(ストライク+1・打席継続)、打者側の2ストライク
(アウト・打席終了・カウントreset)である。

違反主体を区別する入力は存在しない。descriptorの26軸に主体を持つ軸はなく、
`event.perPitch.pitchEventKind`は投球イベントと非投球イベントの別だけを持つ。
`event.perPitch.resultId`も「ピッチクロック違反」の1値である。入力座標は
`eventKind`・`resultId`・`precondition`の自然キーであるため、軸も語彙値も
増やさずに2行を置くと座標が衝突する。

要件書E-1はこの穴を一方の側だけ前提にしている。付録E-1の合法組合せallowlistは、
`secondary-result`へ`batterDestination.kind = out`を許す理由として`INT-06`と並べて
「打者側のピッチクロック違反が第3ストライクに当たる場合」を名指ししている。
投手側を代表に採ると、この`out`許容は本軸のどの行からも到達不能になる。

PO裁定により、投手側を代表1行として置き、打者側の2件を未解決差として残す。
投手側を選んだ根拠は1行で表せる唯一の側であることだけであり、規則上の優位でも
既定でもない。ステップ57の犠打失策とは性質が異なる。あちらは規則9.08が
「疑義のあるときは常に打者に有利に扱う」という既定を与えていたため既定側へ倒せたが、
本件に既定はなく、代表に選ばなかった側は単純に誤りになる。製品の実装前に、
違反主体の入力軸の追加または語彙値の分割として別途起票する。どちらもADR-003 D-11の
descriptorと要件書D-4の改訂にあたり、確定ゲートを要するため本タスクの射程外である。

帰属は`GAP-07`とする。同GAPの`clauseIds`は既に`E-1`と`FR-004`を持つため、
レジスタ側に足すものがない。穴の中身は本節と規範行の`remarks`が持つ。
これはステップ57の犠打失策と同じ型で、`gapId`が9件のexact-setとして機械検査される
一方、レジスタのエントリがID対応だけで本文を持てないため、後から見つかった穴は
意味の異なる既存GAPへ相乗りするほかなく、レジスタからは中身が読めない。
本タスクで2件目となるため、ハーネスの台帳へ候補として起票する。

#### ステップ58で確認した暴投・捕逸の分類と投球判定(2026-10-01 PO裁定・記録のみ)

要件書は暴投／捕逸・ボークを2通りに分類している。E-1の1410行は、allowlistの
`runner-event`行を説明する文脈で「盗塁・牽制・暴投／捕逸等の走者イベントは、打者の
カウントも打席の成否も変更しない」と書く。一方1460行は「PB／WP／ボーク等を伴うときは、
その特殊プレイの行で`optional`と到達塁を定める」と書き、同じ3値を特殊プレイ、すなわち
`secondary-result`として扱う。語彙シードはPB・WP・ボークを`secondary-result`軸の値として
持つため、行27・28・32は`secondary-result`として作った。`countEffect`を
`unchanged`としたのは1410行の「打者のカウントを変更しない」が直接の典拠である。

その帰結として、PB・WPが起きた投球のボールとストライクの判定がどこにも記録されない。
要件書1345行はイベント種別を「打撃結果／打撃結果2（特殊プレイ）／走者イベントの別」と
定め単一値としているため、1球1行の記録ではこの2つを同時に持てない。旧システムは
打撃結果と打撃結果2を同一行の別列として持っており
(`docs/legacy/baseball-scoring-db-structure.md:190`)、この情報は旧では失われていなかった。
たとえば1ボール1ストライクからの暴投で走者が進んだ場合、現行の規範行ではカウントが
1-1のまま残る。

これは規範行の誤りではなく要件書側の穴であり、行を変えても解決しない。本タスクの
射程外のため行は触らず、`GAP-07`へ帰属させて記録だけを残す。同GAPの`clauseIds`は
既に`E-1`と`FR-004`を持つため、レジスタ側に足すものはない。段階2で毎球記録の
イベント種別が単一値でよいかを判断するまで、PB・WPの行がその投球の判定を保持していると
扱わない。

#### ステップ61〜64の`payloadShape`の射程(2026-10-03 PO裁定・案A)

`operationRows[]`の`payloadShape`について、承認済みの2正本が正面から食い違う。
ADR-003のD-8は、各行が当該操作のpayloadを定める閉じたJSON Schemaを持ち、許可する
全フィールドを`properties`へ列挙して`additionalProperties: false`とすることを必須に
している。一方、入力軸descriptorの`stage2ExternalConstraints`は、`payloadAxisIds`へ
`event.operationPayload`を挙げ、`requiredArtifacts`へ`closed-payload-schemas`を
挙げて、これを段階2の確定対象としている。両者は要件書v2.10・ADR-003 v0.4・
同期プロトコル設計v0.5を一括検証した同じ確定ゲート12周を通っており、矛盾が残った。

FR-011は交代の種類と期待動作を定めるが、payloadのフィールド名・必須区分・型を
列挙していない。したがって推測でスキーマを書けばD-8違反か段階2の先取りのどちらかに
なる。この構造は選手交代に固有ではなく、ステップ62のタイブレーク開始、63の
試合終了宣言、64のその場登録にも同じ形で現れ、ステップ66の
`mustOperationCoverage`が6種を覆うという合格条件にも波及する。

PO裁定により、段階1と段階2で`payloadShape`の射程を次のように分ける。段階1が置くのは
**当該FRの受け入れ基準が名指しする要素だけを`properties`へ列挙した最小の閉じた形**で
あり、D-8が要求する`type: "object"`・`properties`の全列挙・`required`・
`additionalProperties: false`の4点を満たす。段階2が確定する`closed-payload-schemas`は
**内部制約まで含む完全形**であり、`constraintClasses`が挙げる`field-uniqueness`・
`reference-integrity`・`mutual-exclusion`・`payload-string-policy-reconciliation`を
伴う。段階1の最小形は段階2の完全形の部分集合であって競合しない。

この分け方で段階1が保証しないものを明示する。フィールドの一意性、他資産への参照整合、
相反するフィールドの同時指定の排除、およびD-8の文字列型制約とFR-015の任意選手名との
整合は、いずれも段階1では検査しない。段階1が保証するのは、列挙したフィールド以外を
payloadが持てないことと、必須フィールドの欠落が拒否されることだけである。
`operationResult`の`rejected-invalid-payload`は、この範囲での拒否を表す。

選手交代の`stateEffect`が比較面の全欄で`unchanged`になる点は、欠落ではない。
`stateFieldEffects`の10欄はいずれも状態量(回・表裏・カウント・アウト・走者・打順枠・
タイブレーク・試合終了・得点)であり、選手の識別子も守備位置も持たない。選手交代は
これらを変えないため、全面`unchanged`は「交代は状態中立である」という検証可能な主張に
なる。FR-011が定める以降のプレイの選手への紐づけは、出場履歴と成績帰属の側が持つ
関心であり、本契約の比較面ではない。この切り分けを各行の`remarks`へ残す。

`historyEffect`は`{pushes: false, kind: null}`とする。FR-006の補足が取消可能な操作を
「確定プレイ」と、FR-040を採用した場合の「状態補正」に限っており、選手交代を含めない
ためである。FR-011の補足が境界に挙げる「直前交代の取り消し」は、undoではなく同一枠への
再交代として記録する経路を指すものと解する。

#### ステップ62(タイブレーク開始)を段階2へ送る(2026-10-03 PO裁定・案B)

FR-009は、タイブレーク開始の結果がpayloadで指定した走者配置・先頭打者・回を反映する
ことを求める。これを規範行で表す手段が現行の機構に無い。

理由は2つある。第一に、要件書E-1が定める`FieldEffect`は`unchanged`、固定値の`set`、
整数の`delta`の3種に閉じており、payloadの指定値を参照する種別を持たない。第二に、
入力軸descriptorの`event.operationPayload`は`classification: boundary-partition`
であるが、その`boundaryValues`は`not-applicable`・`substitution`・`tiebreak-start`・
`game-end-declaration`・`adhoc-registration`・`state-correction`という操作種別の
タグだけで、payloadの中身を`precondition`で固定できない。

この2点により、置ける行はいずれも偽の主張になる。走者を固定値で`set`すると、別の
走者配置を指定したタイブレーク開始にも同じ結果を主張することになる。`unchanged`と
すると、走者が配置されないという条文に反する主張になる。

ステップ58までの穴とは強制の有無が違う。犠打失策の記録員判断、ピッチクロック違反の
違反主体、暴投・捕逸の分類は、いずれも`statFlags`が23件必須のexact型であるため値を
置かない選択肢がなく、規則の既定側または代表へ倒して差を記録した。本件は
`operationRows[]`に行を置かない選択ができるため、強制がない。

PO裁定により、ステップ62は段階2へ送る。`operationRows[]`へ
`operationKind = "tiebreak-start"`の行を作らず、`mustOperationCoverage`へ
`tiebreak-start`の対応も足さない。ステップ66の合格条件
「`mustOperationCoverage`が6種を覆う」は未達となるが、これは偽の主張を契約へ
入れないことと引き換えに受け入れる正直な未達であり、段階2の入口条件として扱う。

段階2で確定すべきものは2点である。第一に、`FieldEffect`がpayloadの指定値を参照する
表現、または`event.operationPayload`の境界値をpayload内容まで分割する表現のいずれか。
第二に、適用規則の発動条件を述語へ写す方法。現行の`Predicate`は軸とリテラルの比較で
あり、規則の発動回と現在回の関係を一般形で表す方法が未定義である。なお確定ゲートの
人間確認で「タイブレークの発動回 = 延長のみ」は決まっているが、これは発動回の範囲を
定めるものであって、規則条件を述語へ写す方法を与えるものではない。

ステップ63(試合終了宣言・FR-010)とステップ64(その場登録・FR-015)は本件の影響を
受けない。FR-010の状態効果は`state.gameEnded`を真にすることでpayloadに依存せず、
FR-015は選手の作成であって比較面の状態量を動かさないためである。両ステップは予定どおり
段階1で進める。

`historyEffect`については、FR-006の補足が取消可能な操作を「確定プレイ」とFR-040採用時の
「状態補正」に限るため、タイブレーク開始も`{pushes: false, kind: null}`となる。段階2で
行を作る際の前提として記録しておく。

### 7-1. 成績計上フラグの導出元(8 周目までの記述を補正)

v9 までは「付録A-2 / A-2b / A-3 / A-3b / A-5 から逆算」としていたが、**それだけでは足りない**。
**FR-022 の当日集計 9 項目**(打席数・打数・安打・**打点**・四球・死球・三振・犠打・犠飛)を導出元に加える。
`:443` が「上記の行から導出する(別実装で数え直さない → NFR-018)」と定めており、
**この 9 項目は付録E-1 の成績計上フラグから導けなければならない**。

### 7-2. `gapRegister` の 5 段と**所有**(7 周目 P1-4 の是正)

```
gapId / state(open → resolved の片方向)
clauseIds[] / branchIds[] / rowIds[] / fixtureCaseIds[] / generatedCaseSelector
```

v7 は 5 段を定義したが、**誰がいつ埋めるか未所有**だった。→ **段ごとに所有ステップを置く**。

| 段 | 埋めるタイミング |
| --- | --- |
| `clauseIds` | 条文化の直後(フェーズ A) |
| `branchIds` | **`clauseBranchRegister` の作成後** |
| `rowIds` | **規範行 4 層の完了後** |
| `fixtureCaseIds` | **手作業 fixture の凍結後** |
| `generatedCaseSelector` | **`cases[]` の生成完了後** |

### 7-3. 状態別の検査述語(8 周目 P1-4 の是正)

v8 は「どの段で途切れても fail」と無条件に書いており、**`open` の途中状態**(ステップ 25 で `clauseIds` だけ、
44 で `branchIds` まで…)を**ステップ 41 の検査が拒否してしまう**。
→ **状態別に述語を分ける**。

| 状態 | 述語 |
| --- | --- |
| **`open`** | **連続した prefix だけを許可**(`clauseIds` → `branchIds` → `rowIds` → `fixtureCaseIds` → `generatedCaseSelector` の順に、先頭から途切れなく埋まっている)。**途中段の飛ばし**・**存在しない参照**・**既に埋めた段の逆方向不一致**は **fail** |
| **`resolved`** | **5 段すべてが必須**かつ**全段で双方向一致** |

ここでいう**双方向一致**は、`gapRegister` から所有資産を引いた参照集合と、所有資産から当該
`gapId` へ帰属させた参照集合が一致することを指す。片方にだけ存在する参照は fail とする。
`clauseIds` は `open` 中は要件書での実在を検査し、`resolved` への遷移時は後続資産から導出した
逆方向帰属も含めて全5段を突合する。参照元が未整備の段を先に埋めた場合は判定不能として fail とする。

**各所有ステップ(44 / 66 / 71 / 94)の合格条件に、実資産へこの検査を適用して緑になることを含める。**

## 8. oracle 循環の遮断

| 層 | **機械が保証すること** | **人間統制** |
| --- | --- | --- |
| ① 由来の記録 | 典拠 ID の実在 / 作成者 ≠ 独立確認者 / 宣誓項目の充足 | 実際に独立確認したか |
| ② 依存遮断 | **実行可能な導出器・展開器のファイル読み取りのみ** | 手作業時に何を読んだか |
| ③ 人間確認 | digest の一致 / 宣誓内容の存在 | 別人による条文からの直接レビュー |
| ④ 手作業 fixture | **展開結果との完全一致** / digest の凍結 | 分岐の意味的完全性 |

**① `provenance` の宣誓と保証境界**:

- ①の宣誓項目は次の3件の閉じた一覧とする。(a) **独立確認者が典拠の条文そのものから確認し、導出物・生成物・他者の要約を根拠にしていないこと**、(b) **独立確認者が作成者の作業結果を見る前に典拠を読んだか、見た場合はその事実を記録したこと**、(c) **典拠が主張を支持すると独立確認者が判断したこと**。
- 機械が保証するのは、典拠種別ごとに下表で宣言した範囲の参照検査、記録上の作成者と独立確認者が異なること、および3宣誓項目の記録が充足することまでとする。**実際に独立確認したか、宣誓が真実か、および典拠が主張を支持するかは人間統制**であり、機械保証に含めない。
- ①は「どう作ったか」の由来記録である。③は「approved とする成果物を別人が条文から直接レビューしたか」の署名記録であり、③の宣誓はステップ43が所有する。①の `provenance` に③の宣誓を混ぜない。

**③ 人間確認の署名記録と保証境界**:

- ③の署名記録は対象成果物へ埋め込まず、`contracts/state-transition/human_review_signature_schema_v1.json` に従う**独立文書**とする。対象 JSON 文書全体の RFC 8785 JCS + SHA-256 digest を記録して自己参照を避ける。記録は、署名 ID、対象のリポジトリ相対 path と digest、記録上の成果物作成者 ID と確認者 ID、記録日、確認範囲、記録された方法、および宣誓記載を持つ。
- 機械が保証するのは、必須記録の形式、対象 path の宣言領域内での解決、**署名の記載と対象 digest の一致だけ**である。別人性については記録上の作成者 ID と確認者 ID が異なることまで、宣誓については閉じた宣誓 ID と充足応答が記載されていることまでを検査する。
- 実際にレビューしたか、確認者が実人物として別人か、典拠条文から直接レビューしたか、記録された作成者・確認者・日付・範囲・方法と宣誓が真実か、および判断が正しいかは**人間統制**であり、機械保証に含めない。①の `provenance` は作成由来、③の独立署名記録は approval 前の確認記録であり、相互に代用しない。
- 本記録は、開発ハーネス設計書 **6.3 の PR 側の逐行確認実施記録とは別**である。6.3 の記録は PR 運用規律であり本検査の対象にせず、本署名記録も 6.3 の実施記録を代替しない。

### 8-0. 導出器・展開器の依存遮断

本節でいう**導出器**は、ADR-003 D-6 の `requiredSet` を独立に作る実行可能な処理、すなわち
①行の要求、②入力座標の要求、および終了判定の要求を作るステップ48〜50の処理を指す。
ステップ41は導出器の実体を先取りせず、その3役割の読み取り許可集合と実行時トレース機構を置く。

読み取り許可集合の正は
`contracts/state-transition/deriver_dependency_policy_v1.json` とする。①行の要求は要件書、共有語彙の
seed / manifest、および5-1の機械可読な軸分類・分割規則、②入力座標の要求は入力軸 descriptor、
終了判定の要求は要件書と入力軸 descriptorだけを読める。検査は導出器の呼出区間で CPython の
`open` 監査イベントとして観測したパスを、
解決後のリポジトリ相対パスに戻して当該役割の allowlist と突合する。リポジトリ外・解決不能・
allowlist 外の読み取り、および追跡されない子プロセスの起動は fail とする。

**この検査が主張するのは、実行可能な導出器の追跡対象呼出区間で観測したファイル読み取りだけ**
である。展開器はステップ42の所有であり、本宣言の保証対象ではない。また、手作業で何を読んだか、
allowlist 内の資産の意味的独立性、実行されなかった分岐、追跡開始前に開かれたファイル記述子からの
読み取り、CPython の監査イベントを発生させない native 読み取り、および環境変数・ネットワーク等の
非ファイル入力は保証しない。これらを確認済みまたは異常なしと扱ってはならない。

本節でいう**展開器**は、ADR-003 D-6 の正である規範行から派生物の `cases[]` を作る実行可能な処理、
すなわち状況判定と終了判定を展開するステップ75・76の処理を指す。ステップ42は展開器の実体を
先取りせず、両役割の読み取り許可集合と、導出器と共通の実行時トレース機構を置く。

展開器の読み取り許可集合の正は
`contracts/state-transition/expander_dependency_policy_v1.json` とする。状況判定の展開器は入力軸
descriptor、共有語彙 seed / manifest、状況判定契約、および `clauseBranchRegister` だけを読める。
終了判定の展開器は入力軸 descriptor、終了判定契約、および `clauseBranchRegister` だけを読める。
契約と register の実体は後続の所有ステップで作成するが、展開器実装前に依存先のリポジトリ相対パスを
宣言しておく。手作業 fixture はいずれの allowlist にも含めない。

**この検査が主張するのは、実行可能な展開器の追跡対象呼出区間で観測したファイル読み取りだけ**
である。手作業 fixture の独立性について主張するのは展開器からの独立だけであり、fixture が各分岐を
見て作られる **`clauseBranchRegister` からの独立を主張しない**。そのため register は展開器にも明示的に
許可する。また、手作業で何を読んだか、allowlist 内の資産の意味的独立性、実行されなかった分岐、
追跡開始前に開かれたファイル記述子からの読み取り、CPython の監査イベントを発生させない native
読み取り、および環境変数・ネットワーク等の非ファイル入力は保証しない。これらを確認済みまたは
異常なしと扱ってはならない。

### 8-1. 手作業 fixture

**主張は「展開器からの独立」のみ**。`clauseBranchRegister` からの独立は主張しない
(fixture は register の各分岐を見て作るため)。**作成者の同一性は記録してレビュー対象にする**。

### 8-2. 凍結(7.7 準拠)

資産側への宣言 / 追記のみの更新履歴(承認者・日付・理由)/ fail-closed。
**再基線化**: 条文の再改訂 / `clauseBranchRegister` の変更 / develop 取り込みでの入力変化。

### 8-3. 典拠の優先順位

| 優先順位 | 典拠 | 機械が確かめる範囲 | 人間統制 |
| --- | --- | --- | --- |
| 1 | 要件書 | 本リポジトリの正本から抽出した条文 ID の実在 | 条文が主張を支持するか |
| 2 | 公認野球規則 | **条番号の書式のみ**。原典が本リポジトリに無いため、条番号の実在と内容は機械で確かめない | 条番号の実在と内容 |
| 3 | 旧 `vocab.ts`(版固定ミラー) | 共有語彙 manifest 経由で語彙 ID の実在 | ミラーの版が正しいか |
| 4 | `docs/legacy/research/`(照合資料) | リポジトリ内のパスと行の実在 | 照合資料としての妥当性 |

優先順位4のみの `provenance` は fail とする。優先順位3のみで充足できるのは**語彙の由来**だけとし、分岐または状態効果の由来は優先順位1または2を少なくとも1件持たなければならない。公認野球規則の実在は、機械に確認能力があるのに解決できない状態ではなく、**そもそも本リポジトリ内の原典を持たないため機械保証の範囲外**である。この非保証範囲を、確認済みまたは異常なしと扱ってはならない。

### 8-4. 旧システムの既知事項(5 不具合 + 1 制約 + 1 推奨)

不具合 2(不変条件ガード欠如)・3(サヨナラ余剰得点)・4(スコア取消の情報喪失)・5(9 回固定)は**正す**。
6(走者同定)は**制約**で射程外、7 は**推奨**で穴 7 として解決。**タイムプレイ**は穴 6。

### 8-5. 台帳候補 (10)

**`H-90`** を採番。**台帳追記・変更履歴・`docs/README.md` の台帳行は同一コミット**。

## 9. 語彙シード

**②参照データ契約**。schema・参照整合・**内容 hash** が必須。D-12 でパス・版・hash の宣言先を確定。
**管理者変更への二段階ゲート**(契約 PR 登録 → 管理者有効化)。製品側の拒否の実装は該当 FR の実装タスク。

## 10. 正規化規則(段階 1 の範囲)

case は 3 点(生値 / 規則識別子 / 正規化後の値)を持つ。**段階 1 は schema と例まで**。
**負例**: 非正規形の raw を使い、normalizer を identity へ変異すると正規化後の突合が fail。
「正規形 raw 自体を拒否する」は条件に含めない。

## 11. PR 構成 — 1 タスク・1 ブランチ・1 PR

4 周目に `check_plan_docs_sync.py` で検証済み(violations 0 / warnings 0)。

### 11-1. コミット順

| 相 | 内容 |
| --- | --- |
| **A** | 要件書 → ADR-003 → 同期正本 → descriptor → 3 点突合 → `gapRegister` 骨格 → **ゲート投入コミット** |
| **(ゲート)** | `/finalize-doc` の確定ゲート(**番号付きステップにしない**) |
| **B** | 契約 schema(構造 → 参照 → 値域 → 交差制約 → operation/undo 別表)→ `mustOperationCoverage` → 終了判定 schema → 語彙シード → 遮断機構 → `gapRegister` 検査 → core-areas |
| **C** | `clauseBranchRegister` → **`gapRegister.branchIds`** → `requiredSet` → 規範行 4 層 → **`gapRegister.rowIds`** → 手作業 fixture(作成 → 突合 → 凍結)→ **`gapRegister.fixtureCaseIds`** |
| **D** | 展開器 → 一致検査 → 変異耐性 → `cases[]` → 正規化 → **`gapRegister.generatedCaseSelector` と `resolved` 遷移** |
| **E** | 検査配線(検査器単位)→ 数値基準の実測 → 台帳 `H-90` → 未解消レポート → 引き渡し契約 |

**`/check` と `/pr` はステップのコミット内容から外す。**

### 11-2. develop 同期は 3 点

フェーズ A の確定前 / フェーズ D の完了後 / `/pr` の直前。

### 11-3. 退路

`gapRegister` へ `open` で追記 → 再改訂の要否 → 要るなら同一 PR 内で条文改訂 + `/finalize-doc` 再実施 + 再基線化。

## 12. 分担

| 事項 | 担当 |
| --- | --- |
| 契約 schema・規範行 4 層・`requiredSet`・descriptor・`clauseBranchRegister`・手作業 fixture・語彙シード | **本タスク** |
| **runner による契約の消費** / 製品 manifest 登録 / 正規化の計算投入証跡 / FR-040 の manifest 宣言 / **descriptor と schema の射影検査** | **段階 2** |
| 検査基盤(runner・生成器・変異器) | TSK-235 |
| Vitest 側の runner | [TSK-455](https://app.notion.com/p/3e593b75e687812ba2e8c20d469ea6db)(段階 2 の依存) |
| FR-007 再開の検証先 | [TSK-454](https://app.notion.com/p/3e593b75e687813bbe17c36d17ebee63) |
| FR-006 のキュー投入・同期状態非依存 | 同期側のテスト |
| 管理者による未登録 ID の有効化拒否の実装 | 該当 FR の実装タスク |

## 未解決・検討メモ

- **確定ゲートの周回数**。3 正本の同時改訂は過去実績で 7〜8 周。
- **`matrixRows[]` の行数**。数百行を想定。**1 コミットあたりの上限行数**をフェーズ C の開始時に決める。
- **`clauseBranchRegister` の分岐数**。手作業 fixture の作成量を規定するため、
  フェーズ C の開始時に実数を出して分割単位を決める。
- **descriptor の軸の完全性**と**分岐の完全性**は人間統制(8 節)。レビューの実施記録を署名に残す。
