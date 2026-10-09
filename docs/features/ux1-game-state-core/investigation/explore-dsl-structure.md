---
type: investigation-record
date: 2026-10-03
agent: Explore
---

# 調査報告(原文): DSL の構造を精密に読む

> **本ファイルは 2026-10-03 の `/investigate`(TSK-405)でサブエージェント `Explore` が返した報告の原文である。**
> 2026-10-09 にセッションの記録から取り出し、**内容を変えずに**収載した(候補基準一覧〔[../research.md](../research.md) §9〕の出典を再現できるようにするため)。
> **報告の主張は当方未検証。** 行番号は報告時点の版(develop `f20323cb`、または `feature/domain-calc-dsl` の worktree)のものであり、現在の行とずれている場合がある。検証は計画書のステップ 2〜3 で行う。

---

# 調査報告: `feature/domain-calc-dsl`(PR #74)の DSL 表現力上限 — TSK-405 / U-X1 適合判定

worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-domain-calc-dsl`(HEAD `b3133f78`)

## 0. 先に結論(最重要)

**この DSL は、現状のままでは U-X1(状況計算核・FR 13 件)を書けません。** 根拠は 3 つで、いずれもスキーマ/検査コードから直接読めます。

| # | 書けないもの | 決定的な根拠 |
|---|---|---|
| **A** | **条件分岐そのもの**(if/else、入れ子も含む) | `Expression` の 8 種に条件式ノードが無い(`model.schema.json:529-555`)。分岐の唯一の代替は「同一イベントに guard 違いの transition を複数置く」だが、**生成前検査がイベント毎に transition ちょうど 1 件を強制**し、2 件以上は `複数の遷移が成立し決定的でない` で fail(`pregen_checks.py:155-170`) |
| **B** | **AND / OR / NOT** | 論理演算ノードが `Expression` に存在しない。`GuardRule.expression` は **`ComparisonExpression` 単体に限定**(`model.schema.json:439-441`)。`TransitionRule.guardRefs` は配列だが、**その意味(連言か選言か)を定義した条文もコードも一切無い**(`guardRefs` を読むコードはリポジトリに 0 件 — 後述 2-2) |
| **C** | **集合・配列(走者の集合、出塁状況)** | `FieldType` の 6 種に配列型は `history-stack` しか無い(`model.schema.json:176-196`)。`ReducerRule.sourceRef` が唯一の集合入口だが、**`sourceRef` を解決・検証するコードが製品側に 0 件**。唯一の実例ですら `"sourceRef": "syntheticSeries"` が**どこにも宣言されていない宙ぶらりんの識別子**(`fixtures/synthetic_dsl/model.json:151`) |

加えて、より根本的な事実(推論ではなく実測):

> **D. 宣言された `rules` / `outputs` から実行コードを生成する経路が、まだ存在しない。**
> `backends/python.py` / `typescript.py` / `sql.py` は `BackendInput.declaration` を**一度も参照しない**(`grep declaration backends/*.py` → `common.py` の型宣言 2 行のみ)。出力は固定文字列のスタブ。`Expression` を評価・出力するコードはリポジトリ全体で 0 件(`grep "extremum"` の唯一のヒットは `pregen_checks.py:273` の型推論)。

→ **TSK-405 の設計リスクは「DSL で書けるか」以前に「DSL を実行コードへ落とす部分が未着手」である**、というのが最大の発見です。

---

## 1. 宣言モデルの全構造(`backend/domain/model.schema.json`・892 行)

### 1-0. ルート(`:6-32`)
`additionalProperties:false` / required = `schemaVersion`(const 1)・`calculations`(minItems 1, `x-uniqueBy: calculationId`)・`displayRules`(各要素は `vocabulary.schema.json` ルート、`x-uniqueBy: id`)。

### 1-1. `$defs` 35 件 全数列挙

| # | `$defs` 名 | 行 | 役割 |
|---|---|---|---|
| 1 | `Identifier` | `:34-37` | `^[A-Za-z][A-Za-z0-9_.-]*$` |
| 2 | `DisplayAtomValue` | `:38-40` | `vocabulary.schema.json#/$defs/DisplayAtom` の別名(**本文中で未使用**) |
| 3 | `Calculation` | `:41-104` | 計算 1 件(下記 1-2) |
| 4 | `FieldDeclaration` | `:105-136` | `fieldId`/`type`/`nullable`/`range`/`unit`/`scale` の **6 つすべて required** |
| 5 | `OutputField` | `:137-175` | 上記 6 + `visibility`(`user-visible`/`internal`)の **7 つすべて required** |
| 6 | `FieldType` | `:176-197` | 6 型の `oneOf` |
| 7 | `IntegerType` | `:198-209` | `kind:"integer"` のみ |
| 8 | `BooleanType` | `:210-221` | `kind:"boolean"` のみ |
| 9 | `EnumType` | `:222-242` | `kind:"enum"` + `values`(Identifier 配列・minItems 1・uniqueItems) |
| 10 | `NumericValueType` | `:243-258` | `kind:"numeric-value"` + `valueSchema` は **const 固定文字列** |
| 11 | `VocabularySnapshotType` | `:259-274` | `kind:"vocabulary-snapshot"` + const |
| 12 | `HistoryStackType` | `:275-290` | `kind:"history-stack"` + const |
| 13 | `VocabularySnapshot` | `:291-296` | 任意キー → `ResolvedName`(語彙 ID→表示名の map) |
| 14 | `HistoryStack` | `:297-302` | `HistoryEntry` の配列。**maxItems 無し** |
| 15 | `HistoryEntry` | `:303-322` | `operationKind`(Identifier)+ `differences`(`StateAssignment` 配列・minItems 1)の 2 つのみ |
| 16 | `RangeOrNull` | `:323-332` | `NumericRange` or null |
| 17 | `NumericRange` | `:333-348` | `minimum`/`maximum` = `NumericValue` |
| 18 | `UnitOrNull` | `:349-358` | Identifier or null |
| 19 | `ScaleOrNull` | `:359-369` | 非負整数 or null |
| 20 | `StateDeclaration` | `:370-390` | `stateId` + `fields`(minItems 1) |
| 21 | `EventDeclaration` | `:391-410` | `eventId` + `fields`(**minItems 無し** = 引数ゼロのイベント可) |
| 22 | `RuleDeclaration` | `:411-423` | Guard / Transition / Reducer の `oneOf` |
| 23 | `GuardRule` | `:424-443` | 下記 1-3 |
| 24 | `TransitionRule` | `:444-479` | 下記 1-3 |
| 25 | `ReducerRule` | `:480-512` | 下記 1-3 |
| 26 | `StateAssignment` | `:513-528` | `fieldRef` + `value`(Expression) |
| 27 | `Expression` | `:529-556` | 8 種の `oneOf`(下記 1-4) |
| 28 | `NumericLiteralExpression` | `:557-572` | |
| 29 | `BooleanLiteralExpression` | `:573-588` | |
| 30 | `EnumLiteralExpression` | `:589-608` | |
| 31 | `ReferenceExpression` | `:609-631` | |
| 32 | `ArithmeticExpression` | `:632-660` | |
| 33 | `ComparisonExpression` | `:661-691` | |
| 34 | `ExtremumExpression` | `:692-718` | |
| 35 | `RoundingExpression` | `:719-743` | |

付記: ルート末尾に `x-authorityCatalog`(2 件・`:745-758`)、`x-pitchlog.scopeElements`(**27 件 = ADR-003 D-1 射程行の語の 1 対 1 対応表**・`:759-869`)、`targetFieldSelectors`(`:870-884`・「利用者可視の数値出力」の機械導出規則)、`vocabularyReferences`(`:885-890`)。

### 1-2. `Calculation` の 7 フィールド(`:41-104`)— 型と制約

| フィールド | 型 | 制約 | 備考 |
|---|---|---|---|
| `calculationId` | `Identifier` | required | |
| `inputs` | `FieldDeclaration[]` | **minItems 無し**(空可)・`x-uniqueBy: fieldId` | |
| `states` | `StateDeclaration[]` | **minItems 1**・`x-uniqueBy: stateId` | 空にできない |
| `events` | `EventDeclaration[]` | **minItems 1**・`x-uniqueBy: eventId` | 空にできない |
| `rules` | `RuleDeclaration[]` | **minItems 1**・`x-uniqueBy: ruleId` | Guard/Transition/Reducer の混在配列 |
| `outputs` | `OutputField[]` | **minItems 1**・`x-uniqueBy: fieldId` | **後述 1-6 のとおり導出式を持てない** |
| `displayRuleRefs` | `Identifier[]` | `uniqueItems` | ルートの `displayRules[].id` を指す |

7 つすべて `required`、`additionalProperties:false`。**`calculation` レベルに「名前」「説明」「版」を書く場所は無い。**

### 1-3. `GuardRule` / `TransitionRule` / `ReducerRule`

**`GuardRule`(`:424-443`)** — 3 キーのみ:
```
kind: "guard" / ruleId: Identifier / expression: ComparisonExpression
```
- **書ける**: 1 本の比較式(左右は任意の `Expression` なので算術の入れ子は可)。
- **書けない**: 論理結合(`expression` の型が `ComparisonExpression` に**直接固定**されており `Expression` ではない)。したがって **1 guard = 1 比較** が上限。

**`TransitionRule`(`:444-479`)** — 5 キーすべて required:
```
kind:"transition" / ruleId / eventRef:Identifier / guardRefs:Identifier[] (uniqueItems) / nextState: StateAssignment[] (minItems 1)
```
- **書ける**: 「イベント X が来たら、状態フィールド群を式で一括代入する」。`nextState` は複数代入を並べられる(同時代入)。
- **書けない**:
  - **分岐**。`eventRef` 1 つに対し transition は**ちょうど 1 件**(`pregen_checks.py:155-170`)。
  - **guard 不成立時の挙動**。スキーマにも生成器にも規定が無い。
  - **イベントの発火条件**(状態を見て発火、など)。イベントは外から来るものとしてしか書けない。
  - **遷移に伴う副作用・出力**。`nextState` は状態フィールドへの代入のみ。

**`ReducerRule`(`:480-512`)** — 6 キーすべて required:
```
kind:"reducer" / ruleId / sourceRef:Identifier / maximumItems:int(min 1) / initial:NumericValue / expression:Expression
```
- **書ける**: `(accumulator, item) → Expression` の畳み込み 1 本、上限件数付き(`maximumItems` が ADR の「有限の reducer」を担保 — `model.schema.json:821-824`)。`accumulator-ref` / `item-ref` で参照(`:618-625`)。
- **書けない**: `sourceRef` が何を指すかの定義。**`sourceRef` を解決するコードはリポジトリに存在しない**(`grep -rn sourceRef --include=*.py` のヒットは `tests/domain/test_model_schema.py:307` のみ)。畳み込みの **結果をどこに書き戻すかのフィールドも無い**(reducer は `ruleId` しか出口を持たない)。フィルタ(`where`)・射影・`groupBy` も書けない。

### 1-4. `Expression` 8 種 — 引数と入れ子

| 種 | 行 | 必須キー | 子に `Expression` を取るか |
|---|---|---|---|
| `numeric-literal` | `:557-572` | `kind`,`value`(`NumericValue`) | × 葉 |
| `boolean-literal` | `:573-588` | `kind`,`value`(bool) | × 葉 |
| `enum-literal` | `:589-608` | `kind`,`enumId`,`value` | × 葉 |
| `*-ref`(Reference) | `:609-631` | `kind`(**6 択**: `input-ref`/`state-ref`/`event-ref`/`output-ref`/`accumulator-ref`/`item-ref`), `fieldRef` | × 葉。**パス参照不可**(`a.b.c` は `Identifier` のドットで書けはするが解決器が無い) |
| `arithmetic` | `:632-660` | `kind`,`operator`(`add`/`subtract`/`multiply`/`divide`),`operands` | ○ `Expression[]`・**minItems 2**(単項マイナス無し)・上限なし(n 項) |
| `comparison` | `:661-691` | `kind`,`operator`(6 択: `equal`/`not-equal`/`less-than`/`less-than-or-equal`/`greater-than`/`greater-than-or-equal`),`left`,`right` | ○ 左右それぞれ `Expression` |
| `extremum` | `:692-718` | `kind`,`operator`(`min`/`max`),`operands` | ○ `Expression[]`・**minItems 1** |
| `round` | `:719-743` | `kind`,`mode`(**const `half-up` のみ**),`scale`(≥0),`value` | ○ `value` が `Expression` |

**入れ子は型の上では自由**(`Expression` の相互再帰、深さ制限なし)。ただし:
- `comparison` は `Expression` の一員なので **`comparison` の中に `comparison` を置けてしまう**(型的には boolean 同士の比較)。`pregen_checks.py:265` の型推論は `comparison → "boolean"` を返すだけで、それを AND と解釈する規定は無い。
- **除算は必ず `round` の内側**(`pregen_checks.py:401-427`。外にあると `除算が明示的な round 式に包まれていない`)。
- 単項否定 `NOT` は、比較演算子の反転で部分的に代替可能(`equal`↔`not-equal` 等)だが、**非比較の boolean(`boolean-literal` / `state-ref` が boolean 型)の否定は書けない**。

### 1-5. `states` と `events` — 状態機械として書けるもの

- **状態 = 名前付きフィールド束**(`StateDeclaration`)。**状態の「名前付き状態(ステート)」概念は無い**。`stateId` はレコード名であって状態ではない。初期状態の宣言場所も**無い**。
- **イベント = 名前 + 引数フィールド束**(`EventDeclaration`)。
- 遷移 = イベント → 状態代入(1 対 1 固定)。
- → 書ける状態機械は、実質 **「イベント名で分岐する 1 段の reducer」** であって、**状態に応じた遷移先の切り替えを持つ有限状態機械は書けない**。分岐が必要なら**イベントのアルファベットを分割する**しかない(例: `hit` ではなく `hitWithBasesEmpty` / `hitWithRunnerOnFirst` … をイベントとして列挙する)。これは U-X1 の走者進塁では組合せ爆発します(推論)。

### 1-6. `outputs` — 導出値をどう書くか → **書けない**

`OutputField`(`:137-175`)のキーは `fieldId` / `type` / `nullable` / `range` / `unit` / `scale` / `visibility` の **7 つだけで `additionalProperties:false`**。
**`expression` も `derivedFrom` も `sourceRef` も無い。**

- `Expression` の `ReferenceExpression` には `output-ref` が**ある**(`:622`)ので「出力を参照する」ことはできるが、**「出力を定義する」構文が無い**。
- `TransitionRule.nextState[].fieldRef` は `pregen_checks.py:347` で **states のフィールドにしか解決されない**(`未知の状態フィールド`)ので、遷移から出力へ書き込むこともできない。
- `ReducerRule` にも出力先フィールドが無い。

→ **outputs は「型・範囲・単位・scale・可視性の宣言」でしかなく、値の定義は DSL の外**(= 現状は未実装)。唯一の実例でも 10 件の output すべてが型宣言のみ(後述 4)。これは U-X1(スコアボード全欄・打者/投手成績の導出)にとって致命的です。

---

## 2. 表現力の上限 — 書けないものの名指し一覧

| 問い | 判定 | 根拠(ファイル:行) |
|---|---|---|
| **条件分岐の入れ子**(if A then (if B then X else Y) else Z) | **✗ 不可**。1 段の分岐すら不可 | `Expression` 8 種に条件ノード無し(`model.schema.json:529-555`)。同一イベント複数 transition は fail(`pregen_checks.py:163-170` `"複数の遷移が成立し決定的でない"`)。ADR-003 D-1 射程行も明文で「**条件分岐・部分文字列操作・③の宣言の外の数値整形ロジックは引き続き書けない**」(`docs/adr/ADR-003-domain-calc-method.md:101`) |
| **論理積 AND** | **✗ 不可**(式として)。**△ 未定義**(`guardRefs` 経由) | `GuardRule.expression` は `ComparisonExpression` 固定(`model.schema.json:439-441`)。`TransitionRule.guardRefs`(`:464-470`)は複数 guard を列挙できるが、**連言と定めた条文は無く、`guardRefs` を読むコードはリポジトリに 0 件**(ヒットはスキーマ定義・fixture・テストのみ)。つまり AND は「書けるかもしれないが意味が未定義」 |
| **論理和 OR** | **✗ 不可** | 選言ノード無し。OR の唯一の自然な表現である「同一イベント・別 guard の transition 2 本」が `pregen_checks.py:163-170` で禁止 |
| **否定 NOT** | **△ 部分的**。比較の反転のみ | `ComparisonExpression.operator` の 6 択が対で揃っている(`:674-681`)。boolean 値そのものの反転は不可 |
| **集合・配列への操作**(走者集合・出塁状況) | **✗ 不可** | 配列型は `HistoryStackType` だけ(`:176-196`)。`ReducerRule.sourceRef`(`:498-500`)は解決器が無い宙ぶらりんの Identifier。`map`/`filter`/`any`/`all`/`count` ノード無し。**なお `history-depth.json:239-258` は走者を `runners{first,second,third}` の boolean 3 本として定義**しており、設計側は「集合ではなく 3 フラグ」で逃げている(= DSL 側の制約への適応と読める・**推論**) |
| **履歴参照**(直前の操作・N 手前) | **△ 置き場だけある。操作は書けない** | `HistoryStackType`(`:275-290`)/ `HistoryStack`(`:297-302`)/ `HistoryEntry{operationKind, differences}`(`:303-322`)で**状態フィールドとして持てる**(実例 `auditTrail` — `fixtures/.../model.json:61-71`)。しかし**添字アクセス・push/pop・長さ取得の式が `Expression` に存在しない**。`ReferenceExpression` は `fieldRef` 単体で、インデックスを取れない。→ **undo を DSL で書く手段は現状ゼロ** |
| **ループ・反復** | **✗ 不可**(設計どおり) | `ReducerRule`(`maximumItems` 必須・`:501-504`)が唯一の反復であり、**有界・単一パス・畳み込みのみ**。while/for 無し。ADR の「有限の reducer」に対応(`model.schema.json:821-824`) |
| **文字列操作** | **✗ 不可**(設計どおり・明文) | `FieldType` に文字列型が無い。表示側も `DisplayTemplate.pattern` のプレースホルダ差し込みのみ(`vocabulary.schema.json:78-107`)で、`DisplayAtom` は「**言語既定の文字列化や文字列操作を持たない不透明な表示型**」と明記(`vocabulary.schema.json:109`)。`NumericValue` を直挿しすると生成前検査が fail(`pregen_checks.py:530-556`) |
| **日付計算** | **✗ 不可** | 日付/時刻型が `FieldType` の 6 種に存在しない |
| **外部データの参照**(規則セット・大会規則などの DB 由来の値) | **△ 入力として丸ごと渡すだけ** | `VocabularySnapshotType`(`:259-274`)で「ID→表示名 map」を入力に含められる(ADR-003 `:101` が明記した逃げ道)。しかし **map からの検索式が `Expression` に無い**。規則セット(FR-014)の数値パラメータは `inputs` に `integer` フィールドとして 1 個ずつ平板に並べるしかない。**可変長の規則配列は表現できない**(配列型が無いため) |

### 2-補足: さらに見つかった上限

1. **`events` ごとに transition 必須**(`pregen_checks.py:145-162`)。イベントを宣言したら必ず 1 本の transition を書く必要があり、「このイベントは状態を変えない」も空の `nextState` では書けない(`nextState` minItems 1)。
2. **未知イベントへの transition は fail**(`pregen_checks.py:171-179`)。
3. **型検査は遷移代入だけ**(`pregen_checks.py:335-368`)。guard 内・reducer 内の型は検査されない。
4. **`inputs`/`outputs`/`states`/`events` のフィールド ID は参照スコープごとに別々の辞書**(`pregen_checks.py:220-253`)。同名衝突は検出されない。
5. **nullable の伝播規則が無い**。`nullable` はフィールド属性だが、式の null 伝播を定めた条文もコードも無い。

---

## 3. 生成器が何を出すか(`backend/src/pitchlog/domaingen/`)

実体は 4 モジュール: `core.py` 776 / `formatter.py` 789 / `pregen_checks.py` 626 / `backends/` 計 397(`__init__` 192 + `common` 125 + `python` 48 + `typescript` 42 + `sql` 38)。

### 3-1. `core.py`(776 行)は **コード生成器ではない**

`core.py` が作るのは **「言語非依存の中間表現(IR)」という JSON 1 本**です(`core.py:559-656`)。

- 出力の形: **関数でもクラスでもテーブルでもなく、canonical JSON を stdout へ 1 本書くだけ**(`core.py:768`)。IR のスキーマは `INTERMEDIATE_REPRESENTATION_SCHEMA`(`core.py:26-107`)に Python リテラルとして埋め込まれている。
- 中身: `{schemaVersion, generatorVersion, displayRules, calculations[{calculationId, sourceId, declaration(=宣言まるごと deepcopy), targets[{directTargetId,targetClass,kind,stages[{stage,generatedId,sourceHash}],invocation}]}]}`。
- `core.py` の仕事の実質は 4 つ:
  1. 自前の縮小版 JSON Schema 検証器(`_validate_instance`・`core.py:253-371`。`$ref`/`oneOf`/`const`/`enum`/`type`/`pattern`/`minimum`/`required`/`additionalProperties:false`/`minItems`/`uniqueItems`/`x-uniqueBy`/`x-stageOrder` だけを実装)
  2. **model と manifest の calculation 集合の完全一致**(`core.py:605-611`)
  3. **生成元条項 ID の逐語が正本文書に実在するかの照合**(`_validate_authority`・`core.py:401-442`。`x-authorityCatalog` の `source`/`section`/`verbatim` で ADR・要件書を実際に読んで文字列検索する)
  4. **段(stage)ごとの SHA-256 `sourceHash`**(`core.py:530-549`)。宣言 + displayRules + target + stage の canonical JSON をハッシュする。
- `main()` の exit code は **0=生成成功 / 1=生成失敗だけ**で、「適合・不適合・判定不能の契約ではない」と docstring に明記(`core.py:724-732`)。
- CLI 既定で `backend/domain/{model,manifest,vocabulary}.schema.json` を読む(`core.py:706-720`)。

### 3-2. `backends/*.py` が各言語で出すもの — **全部スタブ**

| backend | 行 | 実際の出力 |
|---|---|---|
| `python.py` | 48 | ラッパー外 import を拒む `if __name__ != '__pitchlog_generated_wrapper__': raise ImportError`、`_PITCHLOG_SOURCE_HASH = '<hash>'`、そして **`def _pitchlog_generated(context): return {'calculationId': ..., 'context': dict(context)}`**(`python.py:24-47`)。`beta-7` のときだけ `enum_display_map[row['value']]` を返す 3 行(`python.py:30-37`) |
| `typescript.py` | 42 | `globalThis.__PITCHLOG_GENERATED_WRAPPER__` 真偽チェック + `const PITCHLOG_SOURCE_HASH` + **`function pitchlogGenerated(context) { return { calculationId, context }; }`**(`typescript.py:26-41`)。`export` を持たない |
| `sql.py` | 38 | ヘッダコメント + **固定 2 式のみ**: `beta-1-5` → `COALESCE(SUM(:pitchlog_value), 0)` / `beta-7` → `CASE WHEN :pitchlog_row_value IS NULL THEN NULL ELSE :pitchlog_row_value END`(`sql.py:26-33`) |

**「48 行で足りている理由」= 宣言を一切読んでいないから。** `BackendInput.declaration`(`common.py:48`)は 3 backend のいずれからも参照されません(`grep declaration backends/*.py` → `common.py` の 2 行のみ)。`calculation_id` と `source_hash` を文字列として埋めるだけです。
`backends/__init__.py` が担うのは **target matrix の形式検査**のみ: `TARGET_CLASSES = {alpha, beta-1-5, beta-7, beta-6-8}`(`:20`)と `_EXPECTED_STAGES`(`:22-27`。`beta-1-5` は `("sql","typed-receiver","formatter")` 順固定、`beta-7` は 2 段、`alpha`/`beta-6-8` は単一段)、段順違反を fail(`:96-101`)、そしてどの backend を呼ぶかの振り分け(`:105-125`)。

### 3-3. **唯一の本物のコード生成は `formatter.py`**

`formatter.py`(789 行)だけが宣言を読んで実コードを吐きます。ただし対象は **`displayRules` のみ**で、`calculations` の `rules`/`outputs` ではありません。

- `_python_numeric_branch`(`formatter.py:218-279`)が `fixed-decimal`/`percentage` を `Decimal.quantize(ROUND_HALF_UP)` + `format(...,'.Nf')` へ、`mixed-fraction` を `Fraction` 演算へ、`null-substitute` をリテラル返しへ展開する。
- `_python_rule_branch`(`:280-310`)が `rule_id` による `if/elif` ディスパッチャを組み立て、`enum-map` は Python dict リテラル、`template` は `str.replace` の連鎖に展開。
- TypeScript 版も対(`:339-480`)。
- 用途は `DisplayPurpose` の 3 値 `formatter` / `property-reference`(テスト専用参照実装)/ `enum-map-receiver`(`formatter.py:31-37`)。

### 3-4. 生成物の置き場と `backend/domain/manifest.json` との関係

**`backend/domain/manifest.json` は存在しません。** 存在するのは `manifest.schema.json`(666 行)と、テスト fixture の `backend/tests/domain/fixtures/synthetic_dsl/manifest.json` だけです(`find . -name manifest.json` の結果)。`backend/domain/model.json` も同様に存在しません。

- `check-sets.json:64-67` が `manifest-registrations` の source として **`backend/domain/manifest.json` を名指しして予約**している(= 将来の正本)。
- 生成物の置き場は **manifest の `generated[].path`(`RepositoryPath`)で宣言する**(`manifest.schema.json#/$defs/GeneratedArtifact`)。`artifactKind` は `python`/`typescript`/`sql`/`typed-receiver`/`formatter` の 5 択。
- フロント側の置き場は `frontend/src/lib/generated/`(`display-binding.json:35` の `generatedFormatterPathPrefix`)。**現状は `.gitkeep` 1 個だけの空ディレクトリ**(中身: `# 宣言モデルから生成される TypeScript とラッパーの配置先。`)。
- `core.py` も `formatter.py` も **ファイルを書きません**(stdout / メモリ上のデータクラスを返すのみ)。ファイルへ落とす配線はまだ無い(推論: ステップ 26〜30 の範囲が IR と matrix 生成までで、書き出しは TSK-236〜239 側)。

### 3-5. 生成物を手で書き換えられるか — `divergence.py`(441 行)が禁じるもの

4 種の違反を **PR 内の各コミット単位で**検出します(最終ツリーに丸めない・`divergence.py:349-384`)。`DivergenceKind`(`:27-33`):

| 種別 | 意味 | 検出箇所 |
|---|---|---|
| `source-without-generated` | 正本を変えたのに**対応する生成物が同じコミットに入っていない** | `:267-279` |
| `generated-without-source` | **生成物だけを変更した**(正本も generator version も変わっていない) ← **手編集の禁止条項** | `:280-295` |
| `generator-without-all-generated` | `GENERATOR_VERSION` を変えたのに**全生成物が同コミットに入っていない** | `:296-308` |
| `stale-generated` | 当該コミットで**再生成した内容と記録済み生成物が完全一致しない** | `:313-347`(`snapshot.read_text(path) != expected[path]`) |

加えて:
- `GENERATOR_VERSION` は Python AST から**一意な文字列定数として**取り出す(2 個あると判定不能・`:151-176`)。実体は `core.py:16` の `GENERATOR_VERSION = "1.0.0"`。
- 再生成器の出力パス集合が宣言と不一致なら即 `DivergenceInspectionError`(`:328-335`)。
- Python 生成物は**ラッパー外から import すると実行時 `ImportError`**(`python.py:25-26`)、TS は `globalThis.__PITCHLOG_GENERATED_WRAPPER__` が真でないと throw(`typescript.py:28-32`)、配布形態は `delivery = "wrapper-only-fragment"` 固定(`common.py:9`, `:123`)。
- **ただし本番用の `DivergenceSpecification` はまだ存在しません**。インスタンス化は `tests/domain/test_divergence.py:29-45` のテスト用 binding のみ。

---

## 4. 唯一の実例の精読 — `backend/tests/domain/fixtures/synthetic_dsl/model.json`(412 行)

**宣言 1 件(`syntheticMatrix`)で 412 行**。しかもドメインロジックは**ほぼ皆無**です。内訳:

| 区画 | 行 | 件数 | 行数 |
|---|---|---|---|
| `inputs` | `:6-37` | 2 | 32 |
| `states` | `:38-74` | 1 state / 2 field | 37 |
| `events` | `:75-100` | 1 / 1 field | 26 |
| `rules` | `:101-172` | **3** | 72 |
| `outputs` | `:173-356` | **10** | 184 |
| `displayRuleRefs` | `:357-361` | 3 | 5 |
| `displayRules`(ルート) | `:364-411` | 3 | 48 |

### 4-1. `rules` 3 件の中身(これが「全区分を書き切った」実証の全量)

**① guard `nonnegativeAmount`(`:102-120`・19 行)— 比較 1 本**
```json
{ "kind": "guard", "ruleId": "nonnegativeAmount",
  "expression": { "kind": "comparison", "operator": "greater-than-or-equal",
    "left":  { "kind": "event-ref", "fieldRef": "amount" },
    "right": { "kind": "numeric-literal", "value": { "kind": "integer", "value": 0 } } } }
```

**② transition `applyAdvance`(`:121-147`・27 行)— 加算 1 本**
```json
{ "kind": "transition", "ruleId": "applyAdvance",
  "eventRef": "advance", "guardRefs": ["nonnegativeAmount"],
  "nextState": [ { "fieldRef": "leftValue",
    "value": { "kind": "arithmetic", "operator": "add", "operands": [
      { "kind": "state-ref", "fieldRef": "leftValue" },
      { "kind": "event-ref", "fieldRef": "amount" } ] } } ] }
```

**③ reducer `sumSeries`(`:148-171`・24 行)— 総和 1 本**
```json
{ "kind": "reducer", "ruleId": "sumSeries",
  "sourceRef": "syntheticSeries",      ← どこにも宣言が無い識別子
  "maximumItems": 16,
  "initial": { "kind": "integer", "value": 0 },
  "expression": { "kind": "arithmetic", "operator": "add", "operands": [
    { "kind": "accumulator-ref", "fieldRef": "accumulator" },
    { "kind": "item-ref",        "fieldRef": "item" } ] } }
```

→ **ロジックの総量は「x ≥ 0 の判定」「x += y」「Σ」の 3 行相当。これが 72 行の JSON になっている(≈ 24 倍)。**
→ **使われていない語彙**: `subtract`/`multiply`/`divide`/`extremum(min,max)`/`round`/`boolean-literal`/`enum-literal`/`output-ref`/`input-ref`/比較演算子 5 種。ADR の射程に数えられている `explicit-rounding`・`min`・`max`・除算は、**この唯一の fixture ですら一度も使われていません**(trigger 1 の非発火裁定 `docs/features/domain-calc-dsl/design.md:1534-1540` が「5 項目すべて表現できた」と言う根拠は、**型の置き場があることと、この 3 ルールが生成を通ったこと**までです)。

### 4-2. `outputs` 10 件の中身 — **全件が型宣言のみ、導出式はゼロ**

| # | `fieldId` | type | range | unit | scale | visibility |
|---|---|---|---|---|---|---|
| 1 | `periodIndex`(`:174-193`) | integer | 1..99 | `period` | 0 | user-visible |
| 2 | `phaseCode`(`:194-208`) | enum[`left`,`right`] | null | null | null | user-visible |
| 3 | `leftTotal`(`:209-228`) | integer | 0..999 | `unit` | 0 | user-visible |
| 4 | `rightTotal`(`:229-248`) | integer | 0..999 | `unit` | 0 | user-visible |
| 5 | `counterPrimary`(`:249-268`) | integer | 0..9 | `unit` | 0 | user-visible |
| 6 | `counterSecondary`(`:269-288`) | integer | 0..9 | `unit` | 0 | user-visible |
| 7 | `remainingUnits`(`:289-308`) | integer | 0..9 | `unit` | 0 | user-visible |
| 8 | `sequenceIndex`(`:309-328`) | integer | 1..99 | `position` | 0 | user-visible |
| 9 | `occupancyCode`(`:329-343`) | enum[`clear`,`occupied`] | null | null | null | user-visible |
| 10 | `visibleMetric`(`:344-355`) | numeric-value | null | `unit` | 0 | user-visible(**唯一の `nullable:true`**) |

**10 件すべて、どう計算されるかの記述が 1 文字もありません。** 1 件あたり 15〜20 行の型宣言です。
(名前から、1=イニング / 2=表裏 / 3-4=得点 / 5-6=ストライク・ボール / 7=アウト / 8=打順 / 9=走者 / 10=率系 の匿名化と読めます — **推論**。`history-depth.json:177-264` の `principalFlags` 9 項目とほぼ一致。)

### 4-3. `displayRules` 3 件(`:364-411`)
`wholeNumber`(fixed-decimal scale 0)/ `phaseName`(enum-map `left→L`,`right→R`)/ `metricTemplate`(pattern `"{value}"`・placeholder は `numeric-primitive-output` 経由の `DisplayAtom`)。
→ **この 3 件だけが実コード(formatter.py)を生む部分**です。

### 4-4. U-X1 への分量見積(推論)
`history-depth.json` の `principalFlags` 9 項目を素直に states へ移し、FR-003/004 が要求する打撃結果・走者進塁の全組合せをイベントのアルファベットへ展開すると、`rules` だけで数千行の JSON になります。しかも 2-A のとおり **分岐が書けないのでイベント名に状態を焼き込む**必要があり、組合せ爆発します。

---

## 5. 本物の対象計算を書く準備がどこまで整っているか

### 5-1. `backend/domain/` の全 19 ファイル(※お題は 18 件でしたが実数は 19)

| ファイル | 行 | 何を定めているか |
|---|---|---|
| `model.schema.json` | 892 | **DSL 正本の文法**(上記 1) |
| `vocabulary.schema.json` | 471 | **表示語彙の文法**(下記 5-3) |
| `manifest.schema.json` | 666 | 計算 1 件につき **10 の宣言フィールドを必須化**: `calculation`/`source`/`generated`/`entrypoints`(≥1)/`directTargets`(≥1)/`comparison`/`normalization`/`vectors`(**min 1・max 1**)/`properties`(≥1)/`mutation`。`$defs` 22 件。`DirectTarget` は `SingleTarget`(alpha/beta-6-8)/`ThreeStageCompositeTarget`(beta-1-5・`x-stageOrder:[sql,typed-receiver,formatter]`)/`TwoStageCompositeTarget`(beta-7)の `oneOf`。`RepositoryPath` は絶対パスと `..` を正規表現で禁止 |
| `check-sets.json` | 225 | 4 つの **検査集合**(`requirement-targets`=要件書 NFR-018 対象欄からの導出 / `manifest-registrations`= **`backend/domain/manifest.json`(未作成)** / `production-entrypoints`=収集器 2 本 / `executed-check-layers`=vector・property・mutation)。報告語彙 3 値、**exit 契約 0/1/2**(封印内のみ=0 / 封印外あり=1 / 判定不能=2)、FR-040 非採用時の除外宣言スキーマ |
| `required-cases.json` | 558 | **表示の必須 case 18 件を軸 8 本から導出**。軸= `rounding-boundary`(before/exact/after)・`scale-boundary`(min/max)・`sign`(正/負/0)・`zero-denominator`・`empty-aggregate`・`remainder`(0/1/分母−1)・`nullable`・`overflow`(signed-64bit max+1)。具体値も固定(`0.3335` / `-1.5` / 刻み `0.0001`)。**対象は (β)①〜⑤ の集計の表示であって、状況判定(α①)ではない** |
| `property-catalog.json` | 29 | プロパティ層の述語 **2 件だけ**(`countNonnegative` / `emptyAggregateDisplay`)+ 生成器入力 allowlist 6 パス。`scope: "synthetic-dsl"` — **本物のドメイン不変条件はまだ 1 件も無い** |
| `history-depth.json` | 382 | 下記 5-2 |
| `display-binding.json` | 46 | 表示項目↔呼出箇所↔formatter の binding 契約。`exactFields`/`identityFields`/`requiredCallKind:"formatter-call"`/`generatedFormatterPathPrefix:"frontend/src/lib/generated/"`。**`manifest/displayBindings` 自体が封印済み欠落**として記録(`:37-45`) |
| `machine-conditions.json` | 180 | `[機械]` 判定の型カタログ(`section_scoped_diff` / `same_commit` / `zero_line_number_references` / `population_measurement` / `verbatim_presence` / `exit_code_separation` / `all_leaf_mutation` / `set_difference` / `independent_derivation` / `path_allowlist` …)。各型に正例・負例 |
| `review-triggers.json` | 441 | **D-1 見直しトリガー 16 件**と評価期限・判定者・発火条件。**全 16 件 `fired:false`**。**トリガー 1 = 「履歴スタック・規則配列・語彙 snapshot map・スコアボード全欄・NumericValue/DisplayAtom の型語彙で表現できない」** が表現力トリガー |
| `review-trigger-evidence.json` | 137 | 各トリガー評価の pytest node 名の固定と、**機械保証の限界の明文化**(「固定名のテスト本体の意味が発火条件を正しく評価することは保証範囲外」) |
| `step-authorities.json` | 986 | 各ステップが依拠する条項 ID と逐語のカタログ(トリガー 16 の照合元) |
| `boot-clauses.json` | 183 | NFR-018 (e) 経過規定の条項(`BOOT-SEAL` / `BOOT-GRANT` / `BOOT-NO-CLAIM` 等)を要件書から正規表現で切り出した宣言 |
| `boot-seal.json` | 2476 | **封印集合の正本**。`derivedInputs.targets` に **α5 件 + β8 件の対象名**(α① = **状況判定**、α④ = 終了判定 …)。`counts: {total:136, d11:133, b:3}` |
| `boot-seal.sealed.json` | 1 | 封印集合自身の固定 commit OID + blob digest |
| `boot-report.schema.json` | 141 | 未解消要素レポートのスキーマ |
| `boot-report.json` | 580 | **未解消 136 件の実体**。13 対象 × 10 宣言フィールド = 130、+ `manifest` 3、+ `nfr018-b-1..3` 3。**`nfr018-alpha-01/{calculation,source,generated,entrypoints,directTargets,comparison,normalization,vectors,properties,mutation}` の 10 件が、まさに U-X1 が埋めるべき穴**。`transitionMeaning` に「移行状態では NFR-018 (b)② の充足および NFR-019(a) の合格を主張しない」 |
| `path-match.schema.json` | 453 | 経路一致証跡(6 次元要求集合と 5 判定) |
| `mutation-equivalents.json` | 35 | 変異テストの等価変異台帳。`entries: []`(空)。未記録の変異は `non-equivalent` 扱い、判定者は PO |

### 5-2. `history-depth.json`(382 行)— **undo に効く唯一の資産。かつ U-X1 の状態定義が実質ここにある**

- **典拠**: FR-006 補足の逐語を丸ごと保持(`:8`)。「対象は常に直前の取消可能な操作 1 件」「取消可能 = 確定プレイ + (FR-040 採用時のみ)状態補正」「undo 自身は取消可能としない」「undo 後は 1 つ前が次の対象」。
- **深さ D はリテラルで持たない**。`derivation.formula`(`:59-73`)= `max( max(requiredScenarioCases[].events.length), max(stackCompositionCases[].stackKinds.length) )` = `max(4, 2) = 4`。
  - `requiredScenarioCases` 1 件: `two-confirmed-plays-two-undos` = `[confirmed-play-a, confirmed-play-b, undo, undo]`(長さ 4)(`:15-26`)
  - `stackCompositionCases` 4 件: `top-confirmed-play`(深さ1)/`top-state-correction`(1)/`top-and-second-different`(2)/`all-elements-same-kind`(2)(`:27-58`)
- **記録済みの限界 3 件**(`:74-96`、PO 条件付き承認の条件 — `:374-381`):
  1. `required-scenario-completeness`: **必須シナリオの網羅は証明していない。特定できたのは 1 件のみ**
  2. `longer-required-scenario-recalculation`: より長いシナリオが出れば case 追加だけで D は自動再計算される
  3. `stack-composition-completeness`: **4 件が等価分割の全件であることは示していない。示せるのは最小深さ 2 まで**
- **case セット**(`:101-143`): 深さ `0/1/2/D`、構成 4 種、シナリオ長 `1/2/D/D+1`。`D+1` には「execute / not-rejected / not-truncated は保証するが**出力同値は要求しない**」(`:145-153`)。
- **`valueRangeSchema.principalFlags`(`:162-265`)が U-X1 の実質的な状態定義**:
  `inning`(1..2147483647)/ `half`(top|bottom)/ `score{home,away}`(0..2^31-1)/ `count{strikes 0..2, balls 0..3}`/ `outs`(0..2)/ `battingOrder`(1..9)/ **`runners{first,second,third}` = boolean 3 本**/ `tiebreakActive`(bool)/ `gameEnded`(bool)。**9 項目すべて `required`・`additionalProperties:false`。**
  → **この 9 項目は model.schema の `IntegerType`/`BooleanType`/`EnumType` だけで `states` に写せます**(型の置き場はある)。**問題は状態ではなく遷移規則の側**(2-A/B/C)です。
- `displayPrimitiveParameters`(`:267-371`)で 4 primitive のパラメータ範囲を固定(`fixed-decimal` scale 0..3 等)。

### 5-3. `vocabulary.schema.json`(471 行)が語彙をどう縛るか

- ルートは **3 類の `oneOf` のみ**(`:7-17`): `EnumDisplayMap` / `DisplayTemplate` / `NumericDisplayPrimitive`。**4 つ目は作れない。**
- **`EnumDisplayMap`(`:23-59`)に強い縛り**: `stability` は **const `"stable"`**、`managedBy` は **const `"system"`**。
  → **管理者が改名できる語彙(打撃結果・打球情報・シーズン — 要件書 4.0-3)は写像テーブルに焼き込めない**。代替は `VocabularySnapshotType` を計算の入力に含めること(ADR-003 `:101`)。**FR-022「結果表示名」は U-X1 の持ち物なので、ここが直撃します。** design.md:1880 も「**U-X1(状況計算核)が結果表示名を実装する時点で必ず再浮上する**」と申し送っています。
- **`DisplayTemplate`(`:78-107`)**: `pattern` は正規表現 `^(?:[^{}]|\{[A-Za-z][A-Za-z0-9_.-]*\})*$` で**プレースホルダ以外の `{}` を禁止**。`placeholders` の値は **`DisplayAtom` のみ**(`:102-104`)。条件分岐・部分文字列操作は構文的に不可能。
- **`DisplayAtom`(`:108-124`)**: 「**言語既定の文字列化や文字列操作を持たない不透明な表示型**」。供給源は 3 つに閉じる(`:125-137`): `NumericPrimitiveOutput` / `EnumMapOutput` / `ResolvedName`(語彙 ID 解決)。
- **`NumericPrimitive` 4 種**(`:224-349`): `FixedDecimal`(scale 0..3・rounding const `half-up`・`leadingZero`・sign const)/ `Percentage`(scale 0..2・symbol const `percent`)/ `MixedFraction`(denominator ≥1・integerSuffix・`zeroRemainder` ∈ {omit-fraction, show-zero-fraction}・fractionStyle const)/ `NullSubstitute`(substitute 文字列)。**全パラメータが宣言時固定**、`rounding` は half-up 一択。
- **`NumericValue` 4 形**(`:350-366`): `IntegerValue` / `ExactDecimalValue`(正規表現 `^-?(0|[1-9][0-9]*)\.[0-9]+$` — **整数文字列は不可、小数点必須**)/ `RationalValue`(denominator ≥1)/ `null`。**float は存在しない。**
- `x-pitchlog.closedSets`(`:428-450`)が 4 つの閉集合を機械可読に再掲。`appendixABindingPopulation`(`:451-469`)が要件書 付録A の binding 母集合(A-2/A-2b/A-3/A-4/A-5、複合行 4 件は分解しない)を定義。

### 5-4. 準備状況のまとめ

| 整っているもの | 整っていないもの |
|---|---|
| DSL の文法(model/vocabulary/manifest の 3 スキーマ) | **`backend/domain/model.json` / `manifest.json` が存在しない**(find 結果) |
| 宣言→IR 変換と条項逐語検証(`core.py`) | **IR→実行コードの変換**(backends はスタブ) |
| 表示規則の実コード生成(`formatter.py`) | **計算規則の実コード生成** |
| 生成前検査 5 系統(`pregen_checks.py`) | **guard の意味論・reducer の sourceRef 解決・outputs の導出** |
| 乖離検出の判定器(`divergence.py`) | **本番 `DivergenceSpecification`**(テスト内のみ) |
| 履歴深さの導出と undo の典拠(`history-depth.json`) | 必須シナリオの網羅(限界 3 件が未解消) |
| 表示の必須 case 18 件(`required-cases.json`) | **状況判定(α①)の必須 case**(required-cases は (β)①〜⑤ 向け) |
| 封印集合と未解消レポート | **`nfr018-alpha-01`(状況判定)の 10 宣言フィールドがすべて未解消** |
| プロパティ述語 2 件 | 本物のドメイン不変条件 0 件 |
| `frontend/src/lib/generated/` のディレクトリ | その中身(`.gitkeep` のみ) |

---

## 6. TSK-405 / U-X1 への示唆

- **U-X1 = FR-002/003/004/005/006/009/010/014/020/021/022/023/040 の 13 件**(`docs/features/product-impl-unit-split/design.md:73`)。凍結理由は ADR-003「この段階では対象計算のコードを追加しない」(`docs/features/product-impl-unit-split/plan.md:234, 396`)。
- 封印集合側の対応物は **`nfr018-alpha-01` = 状況判定**(10 フィールド未解消)+ **`nfr018-alpha-04` = 終了判定**(FR-010、同 10 件)。
- **DSL で書けるか判定する際に使えるトリガー**: `review-triggers.json` のトリガー 1。ただし**その非発火裁定は「置き場がある」+「合成 fixture が通った」までで、製品データでの実証は TSK-236〜239 に先送り**と明記(`docs/features/domain-calc-dsl/design.md:1527-1542`)。**U-X1 が書けないと判明した場合に発火すべきトリガーは、既に「ステップ 30 が最後の評価地点」として閉じられています**(`:1541`)— つまり **TSK-405 で表現力不足が出たら、トリガーではなく ADR 改訂ゲートへ直行する構造**(推論)。
- **最優先で潰すべき設計リスク 3 点**(優先順):
  1. **条件分岐の不在**(2-A)。走者進塁・得点計算・アウトカウント更新・タイブレーク・終了判定のすべてが分岐を要する。イベント分割で回避すると、イベント名の組合せ爆発 + `pregen_checks.py:145-162` の「全イベントに transition 必須」で宣言量が爆発する。
  2. **`outputs` に導出式を書く構文が無い**(1-6)。FR-020〜023(スコアボード・投手/打者成績・球種分布)は全部 outputs。
  3. **履歴の添字アクセスが無い**(2・履歴行)。FR-006(undo)は `HistoryStack` を**持てる**が**読めない**。`history-depth.json` が D=4 まで用意しているのに、DSL 側に消費手段が無い。
