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

**各所有ステップ(44 / 66 / 71 / 94)の合格条件に、実資産へこの検査を適用して緑になることを含める。**

## 8. oracle 循環の遮断

| 層 | **機械が保証すること** | **人間統制** |
| --- | --- | --- |
| ① 由来の記録 | 典拠 ID の実在 / 作成者 ≠ 独立確認者 / 宣誓項目の充足 | 実際に独立確認したか |
| ② 依存遮断 | **実行可能な導出器・展開器のファイル読み取りのみ** | 手作業時に何を読んだか |
| ③ 人間確認 | digest の一致 / 宣誓内容の存在 | 別人による条文からの直接レビュー |
| ④ 手作業 fixture | **展開結果との完全一致** / digest の凍結 | 分岐の意味的完全性 |

### 8-1. 手作業 fixture

**主張は「展開器からの独立」のみ**。`clauseBranchRegister` からの独立は主張しない
(fixture は register の各分岐を見て作るため)。**作成者の同一性は記録してレビュー対象にする**。

### 8-2. 凍結(7.7 準拠)

資産側への宣言 / 追記のみの更新履歴(承認者・日付・理由)/ fail-closed。
**再基線化**: 条文の再改訂 / `clauseBranchRegister` の変更 / develop 取り込みでの入力変化。

### 8-3. 典拠の優先順位

1 要件書 / 2 公認野球規則 / 3 旧 `vocab.ts`(版固定ミラー)/ 4 `docs/legacy/research/`(照合資料)。

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
