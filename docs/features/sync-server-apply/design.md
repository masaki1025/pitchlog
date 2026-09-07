---
feature: sync-server-apply
type: design
date: 2026-09-07
---

# 詳細設計: 後続 γ の 2 つの機構(`R-TXN-ROUTE` パーサ / 故障系契約の条件付き必須)

plan.md 4 節から参照される補助資料。射程・ステップ表・機構が読む状態は plan.md が正。
事実の典拠は [research.md](research.md)。

## 1. `R-TXN-ROUTE` 専用パーサ

### 1-1. なぜ既存パーサを流用できないか

`scripts/design_relations/sync-protocol.json` の `R-TXN-ROUTE.source_elements` は **14 要素・2 形式混在**:

```
経路 5 行  P1:D1付きイベント=T1,T2,T3,T4,T6
           P2:D2採番・再採番あり=T1,T2,T3,T4,T5,T6
           P3:D1なし変更イベント=T1,T2,T4,T6,T7
           P4:記録権不一致検出・退避永続化・B4応答=T8
           P5:未使用D5の内容拒否=T9
T 要素 9 行 T1:べき等キーの記録 … T9:未使用D5の内容拒否原本・D5・拒否結果・理由の保存
```

| 既存パーサ | 判定 | 理由 |
| --- | --- | --- |
| `parseIdempotencyRelation`(`canonOracle.ts:737-783`) | **不可** | ① 第 1 引数が `IdempotencyRelationId`(`:473-474`)で型が通らず、union を広げると `CANON_IDEMPOTENCY_OUT_OF_SCOPE` の `satisfies`(`:515-517`)がキー不足で壊れる ② T 要素 9 行は `=` が無く `:756` で必ず throw ③ 経路行も `,` split をしないので T 集合が不透明な 1 本の文字列になる |
| `parseCanonBoundaryResults`(`:593-643`) | **不可(最も危険)** | 形式検査は `:` の個数と位置だけで **`=` を一切見ない**(`:615-621`)。`P1:D1付きイベント=T1,T2,T3,T4,T6` は **throw せず** `name = 'D1付きイベント=T1,T2,T3,T4,T6'` として **silent-pass** する。`compare_key` が要求する「各行の T 要素集合」を照合できないまま green になる |
| `parseCanonV12BoundaryRules`(`:404-458`) | 不可 | 全要素に `=` ちょうど 1 個を要求するので T 要素 9 行で throw |
| `parseCanonTemporaryIdMappingRules`(`:836-880`) | T 行のみ可 | `:` 1 個だけを要求し右辺全体を保持。経路行には不可 |

### 1-2. 採る形 — `parseCanonQueueLifeRules` の `kind` dispatch

`canonOracle.ts:994-1029` がマニフェスト内で**混在要素を扱う唯一の先例**。同型にする。

```
parseCanonTxnRouteRules(sourceElements)
  要素ごとに ID を切る(最初の ':' まで。':' が無ければ全体)
  ID が /^P[1-5]$/  → 経路行として解析
      ':' ちょうど 1 個・末尾でない
      '=' ちょうど 1 個・左辺と右辺がともに非空
      右辺を ',' で split し、各トークンが /^T[1-9]$/ かつ重複なし
      → { kind: 'route', id, name, stepIds }
  ID が /^T[1-9]$/  → T 要素行として解析
      ':' ちょうど 1 個・末尾でない
      '=' を含んではならない          ← 既存 parseCanonBoundaryResults に無い検査
      → { kind: 'step', id, name }
  それ以外          → throw('R-TXN-ROUTE に未知の ID があります: …')
  ID の重複は throw
最後に 2 つの exact-set 照合
  ① 関係全体の ID 集合 = P1..P5 ∪ T1..T9(14)
  ② 経路行が参照する T の和集合 = T1..T9(9)   ← 孤立 T を許さない
```

**`,` split は既存に存在しない**(全 11 関係で `R-TXN-ROUTE` だけが `,` を使う。既存は `+`)。新設する。

### 1-3. 実測した参照関係(② の根拠)

| T | 参照する経路 |
| --- | --- |
| T1・T2・T6 | P1・P2・P3 |
| T3 | P1・P2 |
| T4 | P1・P2・P3 |
| **T5** | **P2 のみ** |
| **T7** | **P3 のみ** |
| **T8** | **P4 のみ** |
| **T9** | **P5 のみ** |

T5・T7・T8・T9 は単一経路からしか参照されない。② の照合はこの構造を固定する。

### 1-4. 触ってはならないもの

- **`IdempotencyRelationId`(`:473-474`)に `R-TXN-ROUTE` を足さない**(1-1 の理由 ①)
- **`CANON_P3_ACCEPTED_RESULT_ID`(`:517-518`)は allow-list の添字 0 に位置依存**している。`CANON_IDEMPOTENCY_OUT_OF_SCOPE['R-P3-BOUNDARY']` の先頭 `変更受理` を動かすと、受理結果 ID が黙って `B8` になる
- **`P5` を `SyncEventPath` で型付けしない**。`eventFieldRules.ts:148-153` の `SYNC_EVENT_PATH` は P1〜P4 のみ
- 変異テストで要素を引くときは **`startsWith(\`${id}:\`)` とコロン付き**にする。`P4` の左辺 `記録権不一致検出・退避永続化・B4応答` と `T8` の body が前方一致するため

## 2. allow-list の用途別分割

### 2-1. 現状の構造(`canonOracle.ts:520-547`)

```
IMPLEMENTED_IDEMPOTENCY_IDS   = { 'R-BOUNDARY': {DI2, DI3}, 'R-P3-BOUNDARY': {I2, I3} }
OUT_OF_SCOPE_IDEMPOTENCY_IDS  = CANON_IDEMPOTENCY_OUT_OF_SCOPE から id を写像
EXPECTED_IDEMPOTENCY_IDS      = 実装済み ∪ 射程外
```

`EXPECTED` が和集合なので、**allow-list から実装済みへ移しても `assertExactKnownIds` は鳴らない**。
実効的に移動を検出するのは `canonOracle.spec.ts:509-518` の**製品表突合 1 本だけ**:

```
expectIdempotencyRulesToMatchCanon(IDEMPOTENCY_COLLISION_RULES, readCanonIdempotencyCollisionRules())
  → id 集合と (id → rightHandSide) の Map を toEqual で照合
```

### 2-2. なぜ分割するか

製品表 `IDEMPOTENCY_COLLISION_RULES`(`idempotencyCollision.ts:70-104`)は **D5 衝突規則**の表であり、
`id: 'DI2' | 'DI3' | 'I2' | 'I3'` の literal union(`:58`)で閉じている。
**`DI1`(照合位置)・`DI4`(未使用 D5 の検査対象)・`RG1`(復元調整ゲート)は衝突規則ではない。**
ここへ混ぜると `NFR-018` の意味でのコピー実装ではないが、表の意味が壊れる。

### 2-3. 採る形

`IMPLEMENTED_IDEMPOTENCY_IDS` は **`DI2`/`DI3`/`I2`/`I3` のまま据え置き**、
**処理段階側の実装済み集合を別に設ける**。`EXPECTED = 実装済み(両方) ∪ 射程外` の不変条件は保つ。

```
IMPLEMENTED_IDEMPOTENCY_IDS       (D5 衝突規則)      : {DI2,DI3} / {I2,I3}
IMPLEMENTED_PROCESSING_STAGE_IDS  (処理段階・停止境界): 下表
EXPECTED_IDEMPOTENCY_IDS = 上 2 つ ∪ 射程外        ← 総和は不変
```

パーサは「実装済み(両方の和)なら右辺を逐語で切る / 射程外なら ID の存在だけ」を判定し、
どちらの集合由来かを規則に付ける。reader は用途別に 2 本へ分ける。

### 2-4. 移動する ID と、しない ID

**移動できるのは正本要素に `=` を持つものだけ**(`parseIdempotencyRelation:756` が `=` を要求)。

| ID | 関係 | 正本の右辺 | γ の扱い | ステップ |
| --- | --- | --- | --- | --- |
| `DI1` | R-BOUNDARY | `③認可後+V12前` | **移動** | 2 |
| `DI4` | R-BOUNDARY | `V12・prefix・内容検査対象` | **移動** | 2 |
| `I1` | R-P3-BOUNDARY | `③認可後+RG1後+復旧世代照合後+V12前+V11前` | **移動** | 2 |
| `I4` | R-P3-BOUNDARY | `現復旧世代+V12・V11照合対象` | **移動** | 2 |
| `RG1` | 両方 | 10 節の共通前段ゲート | **移動** | 3 |
| `DI5` | R-BOUNDARY | 混在バッチの A5(6 節) | **移動** | 4 |
| `B3a` | R-BOUNDARY | `P5+T9` | **移動(判定のみ)** | 5 |
| `B3b` | R-BOUNDARY | `先着原本との比較+B3+T9開始なし` | **移動(判定のみ)** | 5 |
| `I5` | R-P3-BOUNDARY | 無効化意図の保存・配信 | **据え置き** — 保存と配信を伴う | γ' |
| `I6` | R-P3-BOUNDARY | 端末永続化まで成立した保持 | **据え置き** — 保存を伴う | γ' |
| `B1`〜`B7` / `変更受理` / `B8`〜`B14` | 両方 | **`=` を持たない** | **移動不可**。別ルート(`parseCanonBoundaryResults` / `parseCanonP3BoundaryResults`)で既に読まれている | — |

`B3a`・`B3b` を移すのは**右辺を逐語固定するため**であり、`T9` の保存を実装するという意味ではない。
モジュールヘッダの慣習(「射程外にした ID とその理由」)で **`T9` の保存は γ' へ送る**と明記する。

## 3. 故障系契約の条件付き必須

### 3-1. 現状と正本の食い違い

| 正本 10-3 `:1691` | 現行実装 |
| --- | --- |
| 「**`適用経路` が P3 の JSON は**、期待結果に…**を必須とする**」 | `validateObservations`(`failureScenarioContract.ts:203-244`)が **`applicationPath` の値を読まず**、常に同一の `FAILURE_EXPECTED_FIELD_IDS`(5 値)を `requireExactKeys` で要求 |
| 「**`適用経路` が P5 の JSON は**、入力の `P5分岐` に `B3a` または `B3b` を**必須とする**」 | `INPUT_FIELD_IDS`(`:61-73`)に **`P5分岐` が無い** |
| 期待結果に **prefix・べき等結果・一時 ID 写像・記録権** | `FAILURE_EXPECTED_FIELD_IDS` は `queue`/`d1`/`lock`/`acceptanceDisplay`/`reinputAvailability` の **5 値のみ** |

**条件付き必須の仕組みが存在しない**ため、経路ごとに必須項目が変わる正本の要求を表現できない。

### 3-2. なぜ「全資産一律に増やす」を採らないか

`validateObservations:234-239` が**期待フィールドに `omittedBecause` を明示的に禁止**している:

```
if (isRecord(fields[fieldId]) && Object.hasOwn(fields[fieldId], 'omittedBecause')) {
  fail(`${location}.fields.${fieldId} に省略理由は指定できません`)
}
```

したがって一律 5 → 9 にすると:

1. **既存 4 資産 × 全 5 観測点に 4 フィールドの実値**を書く(クライアント側シナリオに存在しない概念を値で表現する)
2. `comparisonUnit` を **25 → 45 単位**へ拡張
3. **runner 4 本を全部改修**。しかも `failureScenarioAdapter.spec.ts:110-130` が**期待値リテラルの複製を禁止**しており、現行アダプタは `[].length`(0 の代わり)・`Boolean(id)`(true の代わり)で回避している。新フィールドごとに同種の派生式を考案する必要がある
4. `input`/`expected` が変わるので **10-3 `:1689` の版繰り上げ**が発生
5. ところが**現行実装は同一 scenarioId の複数版を共存できない** — `failureScenarioContract.spec.ts:72-75` が `_v1` をハードコードし、`readFailureScenarioAssets`(`failureScenarioAdapter.ts:669-679`)がディレクトリを全走査して全件 validate する。旧版を残すと throw する

**条件付き必須はこの 5 段の連鎖を丸ごと回避する。既存 4 資産は 1 バイトも変わらない。**

### 3-3. 採る形

`input.applicationPath` の値で、必須の期待フィールド集合と入力キー集合が決まる。

| `applicationPath` | 必須の期待フィールド | 入力の追加必須 |
| --- | --- | --- |
| **省略**(クライアント側) | 基底 5(`queue`/`d1`/`lock`/`acceptanceDisplay`/`reinputAvailability`) | なし |
| **P1・P2・P4** | 基底 5 + **prefix・べき等結果・一時 ID 写像・記録権** | なし |
| **P3** | 上記 + 復旧世代照合・意図 ID・永続状態・配信状態・消費側反映状態・配信完了記録状態・再掲後の意図件数・`I6` の 4 項目・保持期限・退避状態 | なし |
| **P5** | 基底 5 + 4 | **`P5分岐` に `B3a` または `B3b`** |

`requireExactKeys` の**過不足と順序の同時検査は経路ごとに保つ**(緩めない)。
`comparisonUnit` の直積生成(`validateComparisonUnits:255-264`)も経路ごとの期待フィールド集合から作る。

### 3-4. runner 繰り延べ機構

資産だけ足して runner が無いと `failureScenarioAdapter.spec.ts:99-108` の `it.each` の当該ケースが red になる
(`executeFailureScenario:695-698` が `シナリオ実行器がありません` を throw)。

`canonOracle.ts` の allow-list と**同じ形**で解く:

```
DEFERRED_SCENARIO_IDS = [
  { id: '<墓標/改訂の適用>',        reason: 'サーバー適用の実行検証は TSK-250 後(γ\')のため' },
  { id: '<サーバー適用の原子性>',    reason: '同上' },
]
主張: SCENARIO_RUNNERS のキー集合 ∪ DEFERRED = FAILURE_SCENARIO_IDS(exact-set)
     it.each は DEFERRED を除いた集合で回す
```

**繰り延べ集合から 1 件消すと red**(= 黙って実行対象から外れることがない)。

### 3-5. 新 scenarioId の追加位置

**`FAILURE_SCENARIO_IDS` の末尾に足す。** `failureScenarioAdapter.ts:65-70` の分割代入と
`failureScenarioAdapter.spec.ts:133/146/159/168` の `const [, scenarioId]` / `const [, , , scenarioId]` が
**位置依存**で、中間挿入は TypeScript が検出しない silent な取り違えになる(型はいずれも `FailureScenarioId`)。

scenarioId は `FILE_NAME_PATTERN`(`:90`)の `^[a-z0-9]+(?:-[a-z0-9]+)*$` に適合させる(小文字英数とハイフンのみ)。

## 4. 新規モジュールを足すときの登録先(漏らすと 34 件が collection エラー)

`prohibitions.spec.ts` は `describe` の外(`:581-611`)で走査対象の集合を exact-set 照合している。
**新しい `.ts` を `frontend/src/lib/sync/` に置くたび、同一コミットで 3 箇所を追随する。**

| # | 定数 | 行 | 注意 |
| --- | --- | --- | --- |
| 1 | `EXPECTED_PRODUCT_FILE_NAMES` | `:112-141` | ソート後比較なので並び順は自由 |
| 2 | `EXPECTED_VALUE_EXPORTS` | `:143-318` | **値 export の完全集合**。実行時の `Object.keys(module)` と照合 |
| 3 | `EXPECTED_TYPE_EXPORTS` | `:319-536` | **型 export が 0 件でも `[]` のエントリが必須**(先例 `'receptionInput.ts': []` `:493`) |

あわせて **`.claude/core-areas.json`** と **`tests/test_core_guard.py`** にも登録する
(`tests/fixtures/sync-protocol-failures/**` はグロブなので資産 JSON は不要)。

## 未解決・検討メモ

- **`CANON_P3_ACCEPTED_RESULT_ID` の添字 0 依存**(`canonOracle.ts:517-518`)はステップ 2・3 で
  `R-P3-BOUNDARY` の allow-list を触るため踏みやすい。**解消できるならステップ 2 で解消する**が、
  射程を広げないため必須にはしない(合格条件は「先頭 `変更受理` を動かさない」に留める)
- **`faultInjection` を実行器が一切読んでいない**(`fieldValue(contract.faultInjection, …)` の呼び出しが 0 件)。
  注入点を語彙化しても、γ の射程では**資産に書けるだけで実測されない**。
  実測は runner を書く γ' の責務であることを、繰り延べ理由に明記する
- **P3 の 3 注入点(`T7` 確定後・無効化配信前 / 消費側反映後・配信完了記録前 / サーバー確定後・`I6` 端末永続化前)は
  8-1 の T 要素境界では表せない**(T7 の「後」・配信・端末永続化はトランザクション外)。
  語彙として別建てにするか、`injectionPoint` の自由文字列に留めるかはステップ 7 で決める
