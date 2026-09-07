---
feature: sync-server-apply
type: design
date: 2026-09-07
---

# 詳細設計: 後続 γ の機構

plan.md 4 節から参照される補助資料。射程・ステップ表・機構が読む状態は plan.md が正。
事実の典拠は [research.md](research.md)。
**計画レビュー 1 周目(P0 5・P1 5)/ 2 周目(P0 5・P1 2・P2 1)/ 3 周目(P0 4・P1 4)の指摘を反映済み。**

## 1. `R-TXN-ROUTE` 専用パーサ

### 1-1. なぜ既存パーサを流用できないか

`R-TXN-ROUTE.source_elements` は **14 要素・2 形式混在**:

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
| `parseIdempotencyRelation`(`canonOracle.ts:737-783`) | **不可** | 型が `IdempotencyRelationId` に閉じている / T 要素 9 行は `=` が無く `:756` で throw / `,` split をしない |
| `parseCanonBoundaryResults`(`:593-643`) | **不可(最も危険)** | `=` を一切検査しない(`:615-621`)ため、経路行が **throw せず** `name = 'D1付きイベント=T1,…'` として **silent-pass** する |
| `parseCanonV12BoundaryRules`(`:404-458`) | 不可 | 全要素に `=` を要求 |
| `parseCanonTemporaryIdMappingRules`(`:836-880`) | T 行のみ可 | 経路行の `=` を分けない |

### 1-2. 採る形 — `parseCanonQueueLifeRules` の `kind` dispatch

`canonOracle.ts:994-1029` が混在要素を扱う唯一の先例。同型にする。

```
ID が /^P[1-5]$/  → 経路行: ':' 1 個・'=' 1 個・右辺を ',' split・各トークン /^T[1-9]$/ かつ重複なし
ID が /^T[1-9]$/  → T 要素行: ':' 1 個・'=' を含んではならない  ← 既存パーサに無い検査
それ以外・ID 重複 → throw
exact-set 照合 ① 関係全体 = P1..P5 ∪ T1..T9(14) ② 経路が参照する T の和集合 = T1..T9(9)
```

**`,` split は既存に存在しない**(全 11 関係で `R-TXN-ROUTE` だけ)。新設する。

**この reader が返す「経路 → T 集合」の写像を、3-6 の注入点検査(18 組)と 3-8 の
`tElementCommitment` が唯一の出所として使う**(二重定義しない)。

### 1-3. 実測した参照関係(② の根拠)

T1・T2・T6 = P1・P2・P3 / T3 = P1・P2 / T4 = P1・P2・P3 /
**T5 = P2 のみ** / **T7 = P3 のみ** / **T8 = P4 のみ** / **T9 = P5 のみ**。

### 1-4. 触ってはならないもの

- **`IdempotencyRelationId`(`:473-474`)に `R-TXN-ROUTE` を足さない**
- **`CANON_P3_ACCEPTED_RESULT_ID`(`:517-518`)は allow-list の添字 0 に位置依存**
- **`P5` を `SyncEventPath` で型付けしない**(`eventFieldRules.ts:148-153` は P1〜P4 のみ)
- 変異テストは **`startsWith(\`${id}:\`)`** で引く(`P4` の左辺と `T8` の body が前方一致)

## 2. allow-list の用途別分割

### 2-1. 現状と、なぜ分割するか

```
EXPECTED_IDEMPOTENCY_IDS = 実装済み ∪ 射程外   ← 和集合なので移動しても assertExactKnownIds は鳴らない
```

実効的に検出するのは `canonOracle.spec.ts:509-518` の**製品表突合 1 本だけ**。
製品表 `IDEMPOTENCY_COLLISION_RULES`(`idempotencyCollision.ts:70-104`)は **D5 衝突規則**の表で
`id: 'DI2' | 'DI3' | 'I2' | 'I3'` に閉じており、`DI1`(照合位置)・`RG1`(復元ゲート)は衝突規則ではない。

```
IMPLEMENTED_IDEMPOTENCY_IDS       (D5 衝突規則)  : {DI2,DI3,B3b} / {I2,I3}
IMPLEMENTED_PROCESSING_STAGE_IDS  (処理段階)     : {DI1,DI4,RG1} / {I1,I4,RG1}
EXPECTED_IDEMPOTENCY_IDS = 上 2 つ ∪ 射程外                              ← 総和は不変
```

### 2-2. 移動する 6 ID と、残す ID

**移動できるのは正本要素に `=` を持つものだけ**。

| ID | 関係 | 正本の右辺 | 扱い | ステップ |
| --- | --- | --- | --- | --- |
| `DI1` | R-BOUNDARY | `③認可後+V12前` | **移動** | 2 |
| `DI4` | R-BOUNDARY | `V12・prefix・内容検査対象` | **移動** | 2 |
| `I1` | R-P3-BOUNDARY | `③認可後+RG1後+復旧世代照合後+V12前+V11前` | **移動** | 2 |
| `I4` | R-P3-BOUNDARY | `現復旧世代+V12・V11照合対象` | **移動** | 2 |
| `RG1` | 両方 | 10 節の共通前段ゲート | **移動** | 3 |
| `B3b` | R-BOUNDARY | `先着原本との比較+B3+T9開始なし` | **移動** — **`T9` を開始しない**分岐なので永続化を伴わない | 4 |
| **`DI5`** | R-BOUNDARY | 混在バッチの A5(6 節) | **射程外に残す** — 4-5 を参照。**`U-14` の解決が前提**。理由を **TSK-330(`U-14` 依存)** 名指しへ | — |
| **`B3a`** | R-BOUNDARY | **`P5+T9`** | **射程外に残す** — 帰結が**不可分な `P5 + T9`**(`:1248`・`:1209`)。外すと機械上は全体が実装済みに見える | — |
| `I5` / `I6` | R-P3-BOUNDARY | 保存・配信 / 端末永続化 | **射程外に残す** | — |
| `B1`〜`B7` / `変更受理` / `B8`〜`B14` | 両方 | **`=` を持たない** | **移動不可**。別ルートで既に読まれている | — |

## 3. 故障系契約

### 3-1. 正本の読み(1 周目 P0-1 で是正)

10-3 `:1691` は **「各 JSON は」**と書き、**条件付きの部分は加算**である:

> **各 JSON は**…**期待結果として各観測点の永続状態・キュー状態・prefix・べき等結果・一時 ID 写像・記録権・利用者への顕在化を表す。**
> `適用経路` が **P3** の JSON は、期待結果に…**と**…を**必須とする**。
> `適用経路` が **P5** の JSON は、入力の `P5分岐` に **B3a または B3b** を必須とする。
> **該当しないフィールドは省略理由を契約内に明示し**、期待値を製品実装から自動生成しない。

さらに 10-3 `:1694`:

> 各観測点では、**当該経路に存在する T 要素が全部確定または全部非確定であること**を含め、
> 期待結果の一部だけを比較面に採らない。

### 3-2. 集合は無条件・省略可否だけ条件付き(期待フィールド 10 件)

| | 現行 | 本タスク後 |
| --- | --- | --- |
| 期待フィールドの**集合** | 5 件(無条件) | **10 件(無条件)** |
| `omittedBecause` の可否 | 一律禁止(`validateObservations:234-239`) | **`applicationPath` で条件付き** |

10 件 = `queue`・`d1`・`lock`・`acceptanceDisplay`・`reinputAvailability`
+ `prefix`・`idempotentResult`・`temporaryIdMapping`・`recordingRight`
+ **`tElementCommitment`**(3-8)。

```
applicationPath 省略(クライアント側) → 後半 5 件は omittedBecause 可
applicationPath = P1 / P2 / P4 / P5   → 10 件すべて実値必須
applicationPath = P3                  → 10 件 + 13 件
applicationPath = P5                  → 入力の P5分岐(3-4)
```

**`requireExactKeys` の過不足・順序検査は緩めない。** 緩めるのは「その経路で該当しないフィールドに
省略理由を書ける」ことだけで、これは正本 `:1691` 末尾の規則そのもの。

### 3-3. `schemaVersion` の繰り上げ(2 周目 P0-1)

必須フィールドを 5 → 10 に増やし P5 union を足すので**旧構造は新 validator を通らない = 非後方互換**。
10-3 `:1689` は「後方互換でない変更では `schemaVersion` も上げる」と要求する。

- **全資産を `schemaVersion: 2`** にする
- **validator が「構造」と「`schemaVersion`」の組を照合**する
- **旧 `schemaVersion` + 新構造 / 新 `schemaVersion` + 旧構造をいずれも red** にする

### 3-4. P5 の値関係検査(2 周目 P0-4)

exact-key と存在検査だけでは、`B3b` に同一内容や異なる D5 を入れても通ってしまう。**値の関係**を検査する:

| 分岐 | 実行時に検査すること |
| --- | --- |
| **`B3b`** | 先着原本が**初期永続状態と一致**する / 先着と後着の **D5 が同一** / **内容が異なる** |
| **`B3a`** | 対象 D5 が**初期べき等集合に存在しない**(未使用である) |

**異なる D5・同一内容・既存 D5 の各変異が red** になることを合格条件にする。

**単一の資産では union の片方しか表せない**(3 周目 P0-3)。**`p5-b3a-crash-boundaries` と
`p5-b3b-unreached-t9` の 2 資産に分割**する。`b3b-after-gap` は外部結果が `B2` なので、
**直接の `B3b` と `T9` 到達不能の検査を代替しない**。

### 3-5. 契約検査と結果検査の分離(2 周目 P1-2)

`validateFailureScenarioResult`(`:416-449`)も同じ `validateObservations` を使うため、
集合を増やすと **既存 runner が必ず red** になる。同じ validator を緩めると実値必須まで緩む。**分離する**:

| | 要求 |
| --- | --- |
| **契約(資産 JSON)の検査** | 常に **10 キー**を要求。省略可否は 3-2 の条件付き |
| **結果(runner 出力)の検査** | **契約が `omittedBecause` としたキーの不在だけ**を許可。実値対象の欠落・省略表現は**拒否** |

合格条件に **「既存 runner が green のまま」と「サーバー経路の欠落が red」の両方**を入れる。

### 3-6. 注入点の閉じた語彙(1 周目 P1-2)

| 語彙 | 出所 |
| --- | --- |
| 経路 `P1`〜`P5` / T 要素 `T1`〜`T9` / **有効な 18 組** | **1 章の reader**(二重定義しない。`SYNC_EVENT_PATH` は `P5` が無いので流用しない) |
| P3 のトランザクション外 3 注入点 | 10-3 `:1691` — `T7` 確定後・無効化配信前 / 消費側反映後・配信完了記録前 / サーバー確定後・`I6` 端末永続化前 |

**無効な T ID・`P1` に `T9`・誤字のある P3 注入点はいずれも red** にする。

### 3-6a. 注入 case の被覆 — 許可語彙だけでは足りない(4 周目 P1-3)

**18 組を「許可語彙」として閉じても、各資産が有効な組を 1 件選ぶだけで合格条件を通る。**
それでは「**各 T 境界で落とす**」という正本 10-2 の目的(`:1643-1645`・`:1658-1659`)を満たさず、
TSK-330 で資産構造から作り直しになる。

**資産の故障注入を複数 `case` として表す構造に固定し、被覆を exact-set で照合する。**

```
資産の faultInjection = case の配列(1 件以上)
  各 case = { target(経路 × T 要素 または クライアント操作), injectionPoint, stopOperation, restartOperation }

被覆 ①(トランザクション内)
  TRANSACTION_INJECTION_COVERAGE : scenarioId → 宣言した (経路, T 要素) case の集合
  主張: ⋃(作成済み ∪ 未作成繰り延べ) = 1 章の reader が返す 18 組     (exact-set)

被覆 ②(トランザクション外)
  OUT_OF_TRANSACTION_INJECTION_COVERAGE : scenarioId → 宣言した P3 の 3 注入点
  主張: ⋃(作成済み ∪ 未作成繰り延べ) = 3 点                          (exact-set)
```

**γ が作る資産での 18 組の分担**: `p1-crash-boundaries` が P1 の 5 組、`p2-…` が P2 の 6 組、
`p3-…` が P3 の 5 組、`p4-…` が P4 の 1 組、`p5-b3a-…` が P5 の 1 組 = **18 組を γ で覆い切る**。
`p5-b3b-unreached-t9` は **`T9` に到達しない**分岐なので**トランザクション内 case を宣言しない**(空集合)。

**被覆 ② の分担**: `p3-crash-boundaries` が「`T7` 確定後・無効化配信前」と
「サーバー確定後・`I6` 端末永続化前」の 2 点、
**`p3-invalidation-consumed-before-complete`(繰り延べ)が「消費側反映後・配信完了記録前」の 1 点**。

### 3-7. `_v2` 原子移行(2 周目 P2 で不変条件を是正)

10-3 `:1689` が要求する不変条件は「**旧版参照が存在する間に旧資産を削除しない**」である
(1 周目の「旧版を参照するテストが存在する瞬間が無い」は誤り — 親コミットには当然存在する)。

**同一コミット内で順に**「① 新版 `_v2` を追加 → ② 旧資産を残したまま全参照を移行 → ③ 旧版を削除」。
親(旧参照 + 旧資産)と子(新参照 + 新資産)の**どちらにも参照切れが無い**。

移行の内容: 後半 5 件を `omittedBecause` で追記 / `comparisonUnit` を 10 件分へ拡張 /
ファイル名と内部 `version` / **`schemaVersion: 2`** /
**`failureScenarioContract.spec.ts:72-75` の `_v1` ハードコードを現行版の宣言表へ置き換える**。

### 3-8. `tElementCommitment` — T 要素の全確定/全非確定(3 周目 P0-4 / 4 周目 P1-1)

正本 10-3 `:1694` が比較面に含めることを要求している。**1 周目の計画にはあったが 2 周目の
書き直しで落としていた退行**である。

**単一の集約値にすると、runner が T 要素ごとの実状態を示さず部分確定を隠せる**(4 周目 P1-1)。
**資産側と結果側で形を分ける。**

| 側 | 形 | 検査 |
| --- | --- | --- |
| **資産(期待値)** | `{ mode: "allCommitted" \| "allNotCommitted" }` | 2 値のいずれか。**T 集合を資産に列挙させない** |
| **結果(runner 出力)** | **T ID を exact-key とする状態 record** — `{ T1: "committed", T2: "committed", … }` | ① **キー集合が当該経路の T 集合(1 章の reader 由来)と一致** ② 各値が `committed` \| `notCommitted` ③ **全要素が同値** ④ その同値が資産の `mode` と一致 |

**部分確定の変異試験**: **結果 record の 1 要素だけを反転**させ、③ が red になることを確かめる。

`applicationPath` を持たないクライアント側資産では `omittedBecause` 可(3-2)。

これが無いと、**`T2` のイベント保存や `T4` の状態遷移が部分確定しても
共通フィールドと注入点の組検査だけでは green になり得る**。

## 4. D5 分類の正本 4-5 への是正

### 4-1. 既存実装が既に持っているもの(1 周目 P0-5)

`idempotencyCollision.ts` は**すでに D5 を分類し、D1 付き経路の異内容を `B3b` に決定している**
(照合キー `:52-55` / 判定器の注入 `:163-186` / 規則表 `:70-104` / 結果語彙 `:33-39`)。
**新しい分類器を書くとコピー実装になり `NFR-018` 違反(P0)。**

### 4-2. 正本 4-5 との乖離(2 周目 P0-2)

正本 `:404`:

> **内容の同一性を判定できない** | **判定不能は異内容として扱い、先着を正として後着を拒否する**
> (判定不能を「同じ」と見なさない)。**D1 付き経路は B3b、D1 を持たない変更イベントは B13 を返す**

現行実装は例外・`INDETERMINATE` を **`REJECT_LATER`**(`B3b`・`B13` とは**別の第 3 の値**)にしている。
**このまま `B3b` を実装済みへ移すと、非正本の結果を封印する。**

**是正**: 判定不能・比較例外を**経路別に `B3b` / `B13`** へ写像する。

### 4-3. 複数一致の扱いを計画段階で確定する(3 周目 P1-2)

現行 `:172-174` は照合キーが 2 件以上一致した場合も `REJECT_LATER` にしている。
**正本 4-5 はこのケースを扱っていない**(同じ D5 に 2 つの原本を作らない前提)。

**確定**: **「一意な先着原本が存在しない破損状態」として明示的な内部エラーに固定**し、
**`B3b` / `B13` へ混ぜない**。境界結果の語彙を汚さないためであり、
呼び出し元は破損として扱う(正本の境界結果として返さない)。

### 4-4. `DI5` を射程外へ戻す(3 周目 P0-1・P0-2 / 人間の裁定 8)

当初は `batchStopBoundary.ts` を新設して `DI5`(混在バッチの A5)を閉じる計画だったが、
**A5 は「受理 / 重複 / 拒否 / 退避 / 未処理」という外部境界結果を返す**必要があり、
そのとき**保存済み退避の再掲を `B1` と `B4` のどちらにするか**を決めねばならない。
これがまさに **`U-14`(選択規則が無い — `sync-protocol.md:2084`)** である。

| 選択肢 | 判定 |
| --- | --- |
| 任意に決める | **不可** — 正本の一方に反する |
| `U-14` を γ で解決する | 正本改訂 + 確定ゲートが必要。裁定 2・4 と衝突 |
| **`DI5` を射程外へ戻す** | **採用**(裁定 8)。**`batchStopBoundary.ts` は作らない** |

**`DI5` の allow-list の理由を「`U-14` の選択規則が未確定のため。TSK-330(`U-14` 解決後)」へ更新する。**

## 5. 2 層の正本ドリフト検査

### 5-1. 何を解くか

裁定 2 により 6-2 の段階表を関係マニフェストへ登録しない。
そのままだと **TypeScript 側の順序テストは通るが、正本の 9/11 段階が後日変わっても鳴らない**。

さらに **`ci.yml:124-128` の `frontend-changes` フィルタは `frontend/**` のみ**で正本を含まないため、
**検査を Vitest だけに置くと、正本だけを変えた PR では skip される**(2 周目 P1-1)。
一方 **harness ジョブは「paths filter は付けない」と明記**されている(`ci.yml:88`)。

**さらに 3 周目 P1-1**: スナップショットを `scripts/design_relations/` に置くと、
**正本とスナップショットを同時に変えた PR** で harness は green・**Vitest はフィルタ外で skip** になり、
**TS 実装だけ旧状態でも検出されない**。

### 5-2. 採る形(人間の裁定 9)

```
docs/design/sync-protocol.md 6-2
   ↓ ① harness(Python・paths filter なし)  scripts/check_processing_stages.py
frontend/src/lib/sync/processingStages.snapshot.json   ← スナップショット(frontend 配下)
   ↓ ② Vitest(frontend/** フィルタで起動)   processingStages.spec.ts
frontend/src/lib/sync/processingStages.ts
```

**スナップショットを `frontend/` 配下に置く**ことで、同時変更でも**既存の `frontend/**` フィルタが当たり
Vitest が起動**する。`ci.yml` と `test_ci_wiring.py`(いずれも `guard_paths`)を触らずに穴が閉じる。
`prohibitions.spec.ts` の走査は `./**/*.ts` のみなので **JSON は影響しない**。

**スナップショットの内容**: D1 付き経路 9 段階の `(段階番号, 何を確かめるか, 境界結果)` と、
P3 経路 11 段階の `(順序, 進行中, 終了後, 境界結果)`。

**合格条件**: 正本 6-2 を 1 行変えると ① が red / スナップショットを 1 行変えると ② が red /
**同時に変えても ② が起動する**。いずれも**原本のファイルを書き換えず**、複製に対して変異させる。

### 5-3. 採らなかった案

| 案 | 却下理由 |
| --- | --- |
| 関係マニフェストへ登録 | 正本 2-5 表の改訂 = **確定ゲート**。裁定 2 で見送り |
| Vitest 1 本で正本を直接読む | `ci.yml` の frontend フィルタが正本を含まず skip される |
| スナップショットを `scripts/design_relations/` へ | **同時変更で Vitest が skip され穴が残る**(3 周目 P1-1) |
| `ci.yml` のフィルタに足す | `ci.yml` と `test_ci_wiring.py` はいずれも `guard_paths` |
| harness の Python が TypeScript も直接パースする | 既存の検査群はすべて markdown ↔ JSON で、形が異質になる |

## 6. 母集合・観点被覆・2 つの繰り延べ表

### 6-1. 母集合 — 24 の stable scenarioId

scenarioId は `FILE_NAME_PATTERN`(`failureScenarioContract.ts:90`)の
`^[a-z0-9]+(?:-[a-z0-9]+)*$` に適合させる(**小文字英数とハイフンのみ**)。

| 正本 10-2 の観点 / 10-3 の名指し | stable scenarioId | 状態 |
| --- | --- | --- |
| 複数タブの単一書き手 | `multi-tab-single-writer` | **作成済み**(後続 α) |
| フリーズ後の再選出 | `leader-freeze-reelection` | **作成済み**(後続 α) |
| 待機中の入力非受理 | `waiting-input-not-accepted` | **作成済み**(後続 α) |
| 永続追記失敗 | `durable-append-failure` | **作成済み**(後続 α) |
| **墓標の適用** | `tombstone-application` | **γ ステップ 7** |
| **改訂の適用** | `revision-application` | **γ ステップ 7** |
| **P1** | `p1-crash-boundaries` | **γ ステップ 8** |
| **P2** | `p2-crash-boundaries` | **γ ステップ 8** |
| **P3** | `p3-crash-boundaries` | **γ ステップ 8** |
| **P4** | `p4-crash-boundaries` | **γ ステップ 8** |
| **P5(B3a のクラッシュ境界)** | `p5-b3a-crash-boundaries` | **γ ステップ 8** |
| **P5(B3b と T9 到達不能)** | `p5-b3b-unreached-t9` | **γ ステップ 8** |
| **D1 混在バッチ** | `d1-mixed-batch` | **γ ステップ 8** |
| **gap より後ろの B3b** | `b3b-after-gap` | **γ ステップ 8** |
| P3 の消費側反映後・配信完了記録前(10-3 `:1702`) | `p3-invalidation-consumed-before-complete` | **繰り延べ → TSK-330** |
| `O4` の永続化済み D2 同値 | `o4-persisted-d2-equivalence` | **繰り延べ → TSK-330** |
| 復元ライフサイクルの完走 | `restore-fence-escrow-new-generation` | **繰り延べ → TSK-330** |
| 復元途中のクラッシュ | `restore-crash-before-new-generation` | **繰り延べ → TSK-330** |
| 復元時の未回収端末 | `restore-uncollected-device` | **繰り延べ → TSK-330** |
| RG1 移行とのコミット競合 | `restore-commit-race` | **繰り延べ → TSK-330** |
| 復元中の 24 時間清掃(保持中) | `restore-cleanup-held` | **繰り延べ → TSK-330** |
| 復元中の 24 時間清掃(期限切れ未回収) | `restore-expired-not-collected` | **繰り延べ → TSK-330** |
| D4 のロールバック後非再利用(過去発行 D4 集合) | `restore-d4-issued-set` | **繰り延べ → TSK-330** |
| D4 のロールバック後非再利用(連続復元) | `restore-d4-consecutive-rollbacks` | **繰り延べ → TSK-330** |
| 復元調整中の全変更経路 | `restore-all-write-paths-blocked` | **繰り延べ → TSK-330** |
| RG1 解除と新 D4 の境界 | `restore-release-new-generation-boundary` | **繰り延べ → TSK-330** |

**合計 26**(作成済み 4 + γ **10** + 繰り延べ **12**)。

復元系のうち 8 ID は **10-3 `:1692` が逐語で名指し**したもの。ただし同節は「**少なくとも**」と書いており、
**10-2 の観点「復元調整中の全変更経路」(`:1648`)と「RG1 解除と新 D4 の境界」(`:1652`)を
8 ID のどれも一意に覆わない**ため、上の 2 ID を追加した(正本の許す範囲)。

### 6-2. 観点被覆 — 和集合では足りず、ペア集合で照合する(3 周目 P1-3 / 4 周目 P1-2)

`作成済み ∪ 繰り延べ = scenarioId 母集合` は **ID の存在しか検査しない**。
さらに **`観点集合 = ⋃ covers` という和集合検査も不十分**である(4 周目 P1-2):

- `OBSERVATION_KEYS` と `SCENARIO_COVERS` を**同時に作れば、両方から同じ観点を落としても green**
- **別シナリオへ誤って付け替えても和集合は不変**
- **重複被覆では 1 辺を消しても red にならない**

**`scenarioId × 観点key` の期待ペア集合そのものを exact-set 照合する。**

`(d)` の故障系観点は **10-2 `#### (d) の故障系観点 — 実行可能なシナリオ` の 22 行**
(`:1670` 以降の「通信断 → 復帰同期」「記録権の通常/緊急引き継ぎと退避経路」の 2 行は
**`#### (c) のうち同期側が関わる 2 経路` = `NFR-019(c)` であり (d) ではない**)。

| # | 観点 key(10-2 の行) | scenarioId |
| ---: | --- | --- |
| 1 | `tombstone-apply` | `tombstone-application` |
| 2 | `revision-apply` | `revision-application` |
| 3 | `p1` | `p1-crash-boundaries` |
| 4 | `p2` | `p2-crash-boundaries` |
| 5 | `p3` | `p3-crash-boundaries` |
| 6 | `p3` | `p3-invalidation-consumed-before-complete` |
| 7 | `d1-mixed-batch` | `d1-mixed-batch` |
| 8 | `b3b-after-gap` | `b3b-after-gap` |
| 9 | `d4-no-reuse-after-rollback` | `restore-d4-issued-set` |
| 10 | `d4-no-reuse-after-rollback` | `restore-d4-consecutive-rollbacks` |
| 11 | `all-write-paths-during-restore` | `restore-all-write-paths-blocked` |
| 12 | `rg1-commit-race` | `restore-commit-race` |
| 13 | `rg1-release-new-d4-boundary` | `restore-release-new-generation-boundary` |
| 14 | `restore-lifecycle-complete` | `restore-fence-escrow-new-generation` |
| 15 | `restore-crash-midway` | `restore-crash-before-new-generation` |
| 16 | `restore-uncollected-device` | `restore-uncollected-device` |
| 17 | `restore-24h-cleanup` | `restore-cleanup-held` |
| 18 | `restore-24h-cleanup` | `restore-expired-not-collected` |
| 19 | `o4-persisted-d2-equivalence` | `o4-persisted-d2-equivalence` |
| 20 | `multi-tab-single-writer` | `multi-tab-single-writer` |
| 21 | `p4` | `p4-crash-boundaries` |
| 22 | `p5` | `p5-b3a-crash-boundaries` |
| 23 | `p5` | `p5-b3b-unreached-t9` |
| 24 | `leader-freeze-reelection` | `leader-freeze-reelection` |
| 25 | `waiting-input-not-accepted` | `waiting-input-not-accepted` |
| 26 | `durable-append-failure` | `durable-append-failure` |

**観点 key 22 種・ペア 26 件・scenarioId 26 件**(各 scenarioId はちょうど 1 回現れる)。

```
主張 ①  OBSERVATION_SCENARIO_PAIRS = 上表の 26 ペア            (exact-set・ペアそのものを照合)
主張 ②  ペアの第 1 要素の集合 = OBSERVATION_KEYS(22)           (取りこぼし・余剰を拒否)
主張 ③  ペアの第 2 要素の集合 = scenarioId 母集合(26)          (同上)
```

**ペアを 1 件消しても、別シナリオへ付け替えても、観点を落としても red** になる。

### 6-3. 2 つの繰り延べ表 — 和集合に加えて交差が空(4 周目 P1-2)

```
未作成繰り延べ  : 作成済み ∪ 未作成繰り延べ = 母集合   かつ  作成済み ∩ 未作成繰り延べ = ∅
runner 繰り延べ : SCENARIO_RUNNERS ∪ runner 繰り延べ = FAILURE_SCENARIO_IDS
                  かつ SCENARIO_RUNNERS ∩ runner 繰り延べ = ∅
it.each は runner 繰り延べを除いた集合で回す
```

**和集合だけだと両方への重複登録を許す**ため、**交差が空であること**も要求する。
γ が作る 10 資産はすべて **runner 繰り延べ**に入る(実行検証は TSK-330)。

### 6-4. exact-set の一覧(6 本)

| # | 名前 | 主張 |
| --- | --- | --- |
| 1 | **母集合** | `作成済み ∪ 未作成繰り延べ = 26 の scenarioId` かつ **交差が空** |
| 2 | **観点被覆** | `OBSERVATION_SCENARIO_PAIRS = 26 ペア`(+ 第 1/第 2 要素の集合一致) |
| 3 | **runner 繰り延べ** | `SCENARIO_RUNNERS ∪ 繰り延べ = FAILURE_SCENARIO_IDS` かつ **交差が空** |
| 4 | **トランザクション内注入被覆** | `⋃ TRANSACTION_INJECTION_COVERAGE = reader の 18 組` |
| 5 | **トランザクション外注入被覆** | `⋃ OUT_OF_TRANSACTION_INJECTION_COVERAGE = P3 の 3 点` |
| 6 | **`canonOracle` の既知 ID** | `EXPECTED = 実装済み ∪ 射程外`(既存・総和が不変) |

**1〜5 はどれも 1 件消すと red** にする。

### 6-4. 新 scenarioId の追加位置

**`FAILURE_SCENARIO_IDS` の末尾に足す。** `failureScenarioAdapter.ts:65-70` の分割代入と
`failureScenarioAdapter.spec.ts:133/146/159/168` が**位置依存**で、中間挿入は TypeScript が検出しない。

## 7. 新規資産の登録先(漏らすと 34 件が collection エラー)

| # | 対象 | 場所 | 注意 |
| --- | --- | --- | --- |
| 1 | `EXPECTED_PRODUCT_FILE_NAMES` | `prohibitions.spec.ts:112-141` | ソート後比較。**JSON は走査対象外**(`./**/*.ts` のみ) |
| 2 | `EXPECTED_VALUE_EXPORTS` | 同 `:143-318` | **値 export の完全集合** |
| 3 | `EXPECTED_TYPE_EXPORTS` | 同 `:319-536` | **型 export が 0 件でも `[]` エントリが必須** |
| 4 | **`.claude/core-areas.json` の `paths`** | `sync-protocol` | **製品と spec を個別に列挙**するのが現行の作法。**新規 2 モジュール + 各 spec + スナップショット JSON = 5 パス** |
| 5 | **`.claude/core-areas.json` の `guard_paths`** | — | **`check_processing_stages.py`・`test_check_processing_stages.py` の 2 パス**(既存の検査器が `guard_paths` にある作法に合わせる) |
| 6 | **`tests/test_core_guard.py`** | 期待値 | 4・5 と一致させる。**両方を同時に更新しないと green のまま逐行確認の対象から外れる** |

`tests/fixtures/sync-protocol-failures/**` は**グロブ**なので資産 JSON の追加では 4〜6 は不要。

**台帳(`harness-evaluation.md`)と索引(`docs/README.md`)は `/pr` のクローズ処理で更新する**
(pr スキル手順 1-3)。**クローズ処理はステップ表の外側**にあるため実装ステップには置かない。

**同一コミットの範囲**(4 周目 P2 で是正): pr スキルが同一コミットに要求するのは
**②台帳・③変更履歴表・④索引**である。**①計画書 3 節への宣言は「先に」行うもの**であり、
同一コミットの構成要素ではない。本タスクでは**①は本計画の改訂時点で完了済み**で、
②〜④を `/pr` の同一クローズコミットで更新する。

## 未解決・検討メモ

- **`CANON_P3_ACCEPTED_RESULT_ID` の添字 0 依存**(`canonOracle.ts:517-518`)はステップ 2・3 で踏みやすい。
  解消できるならステップ 2 で解消するが、射程を広げないため必須にはしない
- **`faultInjection` を実行器が一切読んでいない**。3-6 で語彙と組合せを閉じても、
  **γ の射程では資産に書けるだけで実測されない**。実測は **TSK-330** の責務
- **観点 key の完全な列挙はステップ 7 で確定**する。本書は写像の**機構**(6-2 の exact-set)を定め、
  列挙そのものは正本 10-2 を全行読んで固定する
- **`DI5` を射程外へ戻したことで、混在バッチの A5 停止境界は γ で一切固定されない**。
  `d1-mixed-batch` と `b3b-after-gap` の**資産は作る**が、**規則の実装と実行検証は TSK-330**(`U-14` 解決後)
