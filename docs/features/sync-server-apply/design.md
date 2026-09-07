---
feature: sync-server-apply
type: design
date: 2026-09-07
---

# 詳細設計: 後続 γ の機構(パーサ / allow-list / 故障系契約 / 単一実装 / ドリフト検査)

plan.md 4 節から参照される補助資料。射程・ステップ表・機構が読む状態は plan.md が正。
事実の典拠は [research.md](research.md)。**計画レビュー 1 周目(2026-09-07・`sol xhigh`)の指摘 10 件を反映済み。**

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
| `parseIdempotencyRelation`(`canonOracle.ts:737-783`) | **不可** | ① 第 1 引数が `IdempotencyRelationId`(`:473-474`)で型が通らず、union を広げると `CANON_IDEMPOTENCY_OUT_OF_SCOPE` の `satisfies`(`:515-517`)がキー不足で壊れる ② T 要素 9 行は `=` が無く `:756` で必ず throw ③ 経路行も `,` split をしない |
| `parseCanonBoundaryResults`(`:593-643`) | **不可(最も危険)** | 形式検査は `:` の個数と位置だけで **`=` を一切見ない**(`:615-621`)。`P1:D1付きイベント=T1,T2,T3,T4,T6` は **throw せず** `name = 'D1付きイベント=T1,T2,T3,T4,T6'` として **silent-pass** する |
| `parseCanonV12BoundaryRules`(`:404-458`) | 不可 | 全要素に `=` ちょうど 1 個を要求するので T 要素 9 行で throw |
| `parseCanonTemporaryIdMappingRules`(`:836-880`) | T 行のみ可 | `:` 1 個だけを要求。経路行には不可 |

### 1-2. 採る形 — `parseCanonQueueLifeRules` の `kind` dispatch

`canonOracle.ts:994-1029` がマニフェスト内で**混在要素を扱う唯一の先例**。同型にする。

```
parseCanonTxnRouteRules(sourceElements)
  要素ごとに ID を切る(最初の ':' まで。':' が無ければ全体)
  ID が /^P[1-5]$/  → 経路行
      ':' ちょうど 1 個・末尾でない / '=' ちょうど 1 個・左右とも非空
      右辺を ',' で split し、各トークンが /^T[1-9]$/ かつ重複なし
      → { kind: 'route', id, name, stepIds }
  ID が /^T[1-9]$/  → T 要素行
      ':' ちょうど 1 個・末尾でない
      '=' を含んではならない          ← 既存 parseCanonBoundaryResults に無い検査
      → { kind: 'step', id, name }
  それ以外・ID 重複 → throw
  2 つの exact-set 照合
    ① 関係全体の ID = P1..P5 ∪ T1..T9(14)
    ② 経路が参照する T の和集合 = T1..T9(9)   ← 孤立 T を許さない
```

**`,` split は既存に存在しない**(全 11 関係で `R-TXN-ROUTE` だけが `,` を使う)。新設する。

**この reader が返す 18 組の `(経路, T 要素)` を、3 章の注入点検査が唯一の出所として使う**(二重定義しない)。

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

### 1-4. 触ってはならないもの

- **`IdempotencyRelationId`(`:473-474`)に `R-TXN-ROUTE` を足さない**
- **`CANON_P3_ACCEPTED_RESULT_ID`(`:517-518`)は allow-list の添字 0 に位置依存**。`R-P3-BOUNDARY` の先頭 `変更受理` を動かすと受理結果 ID が黙って `B8` になる
- **`P5` を `SyncEventPath` で型付けしない**。`eventFieldRules.ts:148-153` の `SYNC_EVENT_PATH` は P1〜P4 のみ
- 変異テストで要素を引くときは **`startsWith(\`${id}:\`)` とコロン付き**にする(`P4` の左辺と `T8` の body が前方一致するため)

## 2. allow-list の用途別分割

### 2-1. 現状(`canonOracle.ts:520-547`)

```
IMPLEMENTED_IDEMPOTENCY_IDS   = { 'R-BOUNDARY': {DI2, DI3}, 'R-P3-BOUNDARY': {I2, I3} }
OUT_OF_SCOPE_IDEMPOTENCY_IDS  = CANON_IDEMPOTENCY_OUT_OF_SCOPE から id を写像
EXPECTED_IDEMPOTENCY_IDS      = 実装済み ∪ 射程外
```

`EXPECTED` が和集合なので**移動しても `assertExactKnownIds` は鳴らない**。
実効的に検出するのは `canonOracle.spec.ts:509-518` の**製品表突合 1 本だけ**。

### 2-2. 採る形

製品表 `IDEMPOTENCY_COLLISION_RULES`(`idempotencyCollision.ts:70-104`)は **D5 衝突規則**の表で
`id: 'DI2' | 'DI3' | 'I2' | 'I3'` の literal union(`:58`)で閉じている。
**`DI1`(照合位置)・`RG1`(復元ゲート)は衝突規則ではない**ため、処理段階側の実装済み集合を別に設ける。

```
IMPLEMENTED_IDEMPOTENCY_IDS       (D5 衝突規則)      : {DI2,DI3} / {I2,I3}   ← 据え置き
IMPLEMENTED_PROCESSING_STAGE_IDS  (処理段階・停止境界): 下表
EXPECTED_IDEMPOTENCY_IDS = 上 2 つ ∪ 射程外                                  ← 総和は不変
```

### 2-3. 移動する 7 ID と、残す ID

**移動できるのは正本要素に `=` を持つものだけ**(`parseIdempotencyRelation:756` が `=` を要求)。

| ID | 関係 | 正本の右辺 | 扱い | ステップ |
| --- | --- | --- | --- | --- |
| `DI1` | R-BOUNDARY | `③認可後+V12前` | **移動** | 2 |
| `DI4` | R-BOUNDARY | `V12・prefix・内容検査対象` | **移動** | 2 |
| `I1` | R-P3-BOUNDARY | `③認可後+RG1後+復旧世代照合後+V12前+V11前` | **移動** | 2 |
| `I4` | R-P3-BOUNDARY | `現復旧世代+V12・V11照合対象` | **移動** | 2 |
| `RG1` | 両方 | 10 節の共通前段ゲート | **移動** | 3 |
| `DI5` | R-BOUNDARY | 混在バッチの A5(6 節) | **移動** | 4 |
| `B3b` | R-BOUNDARY | `先着原本との比較+B3+T9開始なし` | **移動** — **`T9` を開始しない**分岐なので永続化を伴わない | 4 |
| **`B3a`** | R-BOUNDARY | **`P5+T9`** | **射程外に残す** — 正本の帰結は**不可分な `P5 + T9`**(`:1248`・`:1209`)。allow-list から外すと**機械上は `P5+T9` 全体が実装済みに見え、`T9` 未実装を取り落とす**。理由を **TSK-330 名指し**へ更新する | — |
| `I5` | R-P3-BOUNDARY | 無効化意図の保存・配信 | **射程外に残す** — 保存と配信を伴う | — |
| `I6` | R-P3-BOUNDARY | 端末永続化まで成立した保持 | **射程外に残す** — 保存を伴う | — |
| `B1`〜`B7` / `変更受理` / `B8`〜`B14` | 両方 | **`=` を持たない** | **移動不可**。別ルートで既に読まれている | — |

**`B3a` の判定に相当する処理が要る場合は、`B3a` とは別の内部能力として扱い、正本 ID の実装済み集合に数えない。**

## 3. 故障系契約 — 共通 9 件と条件付き省略可否

### 3-1. 正本の読み(1 周目 P0-1 で是正)

10-3 `:1691` は **「各 JSON は」**と書いており、**条件付きの部分は加算**である:

> **各 JSON は**…**期待結果として各観測点の永続状態・キュー状態・prefix・べき等結果・一時 ID 写像・記録権・利用者への顕在化を表す。**
> `適用経路` が **P3** の JSON は、期待結果に…**と**…を**必須とする**。
> `適用経路` が **P5** の JSON は、入力の `P5分岐` に **B3a または B3b** を必須とする。
> **該当しないフィールドは省略理由を契約内に明示し**、期待値を製品実装から自動生成しない。

したがって **`prefix`・べき等結果・一時 ID 写像・記録権は全 JSON 共通の必須**であり、
**「クライアント側は基底 5 件」という例外は正本に無い**(初版の設計はここを誤っていた)。

### 3-2. 採る形 — 集合は無条件・省略可否だけ条件付き

| | 現行 | 本タスク後 |
| --- | --- | --- |
| 期待フィールドの**集合** | 5 件(無条件) | **9 件(無条件)** |
| `omittedBecause` の可否 | **一律禁止**(`validateObservations:234-239`) | **`applicationPath` で条件付き** |

```
applicationPath 省略(クライアント側)
  → 後半 4 件(prefix・idempotentResult・temporaryIdMapping・recordingRight)は omittedBecause 可
applicationPath = P1 / P2 / P4 / P5
  → 9 件すべて実値必須(省略すると red)
applicationPath = P3
  → 9 件 + 13 件(復旧世代照合・意図 ID・永続/配信/消費側反映/配信完了記録状態・再掲後件数・I6 の 4 項目・保持期限・退避状態)
applicationPath = P5
  → 入力の P5分岐 を discriminated union にする
       B3a: 未使用 D5 + 内容拒否になる原本
       B3b: 不変な先着原本 + 同一 D5・異なる内容の後着入力
     いずれも exact-key で必須化し、T9 到達分岐と非到達分岐を暗黙表現にしない
```

**`requireExactKeys` の過不足・順序検査は緩めない。** 緩めるのは「その経路で該当しないフィールドに
省略理由を書ける」ことだけで、これは正本 `:1691` 末尾の規則そのものである。

### 3-3. 既存 4 資産の `_v2` 原子移行

`expected` が変わるので 10-3 `:1689` の版繰り上げが要る:

> 入力・故障注入・期待結果・比較単位のいずれかを変えた場合は `N` を上げて別ファイルを作り、
> **参照するテストがすべて新版へ移るまで旧版を上書きまたは削除しない**

**同一コミット内で「新版作成 → 全テスト移行 → 旧版削除」を行う。**
この順序なら**旧版を参照するテストが存在する瞬間が無く**、規則を満たす。

移行の内容(4 資産 × 各観測点):

- 後半 4 件を `omittedBecause` で追記(クライアント側シナリオなので実値は書かない)
- `comparisonUnit` を **25 → 45 単位**へ(観測点が外ループ・期待フィールドが内ループの順序を守る)
- ファイル名 `_v1` → `_v2`、内部 `version: 1` → `2`
- **`failureScenarioContract.spec.ts:72-75` の `_v1` ハードコードを「現行版の宣言表」へ置き換える**

**runner 4 本は変更不要**。省略したフィールドは算出しないため、
`failureScenarioAdapter.spec.ts:110-130` の**期待値リテラル複製禁止に触れない**。

### 3-4. 注入点の閉じた語彙と実行時検査(1 周目 P1-2)

現行 `faultInjection` の検査はキーと wrapper だけで、**値も組合せも見ていない**。閉じる:

| 語彙 | 出所 |
| --- | --- |
| 経路 `P1`〜`P5` | **1 章の reader**(`SYNC_EVENT_PATH` は `P5` が無いので流用しない) |
| T 要素 `T1`〜`T9` | 同上 |
| **有効な 18 組の `(経路, T 要素)`** | 同上(二重定義しない) |
| P3 のトランザクション外 3 注入点 | 10-3 `:1691` — `T7` 確定後・無効化配信前 / 消費側反映後・配信完了記録前 / サーバー確定後・`I6` 端末永続化前 |

**無効な T ID・`P1` に `T9`・誤字のある P3 注入点はいずれも red** にする。

### 3-5. 2 つの繰り延べ表(1 周目 P0-3 / P0-4)

**runner 未実装**と**未作成資産**は別の事柄なので、表を分ける。どちらも exact-set で主張する。

```
① runner 繰り延べ
   SCENARIO_RUNNERS のキー集合 ∪ 繰り延べ = FAILURE_SCENARIO_IDS
   it.each は繰り延べを除いた集合で回す

② 未作成資産の繰り延べ(ID・必要な契約拡張・受け取り先を個別に列挙)
   復元ライフサイクル 8 シナリオ            (10-3 :1692)  → TSK-330
   p3-invalidation-consumed-before-complete (10-3 :1702)  → TSK-330
   P1〜P5 の故障行列                        (10-2 :1641-1659) → TSK-330
```

**どちらの表も 1 件消すと red** にする(黙って追跡対象から外れることがない)。

**ステップ 6 と 7 を分けたうえで、繰り延べ表・資産・scenarioId はステップ 7 で原子的に追加する。**
ステップ 6 時点では繰り延べ対象が存在せず「1 件消すと red」を試せず、
先に ID だけ足すと `failureScenarioContract.spec.ts:72-75` の fixture exact-set が red になるため。

### 3-6. 新 scenarioId の追加位置

**`FAILURE_SCENARIO_IDS` の末尾に足す。** `failureScenarioAdapter.ts:65-70` の分割代入と
`failureScenarioAdapter.spec.ts:133/146/159/168` が**位置依存**で、中間挿入は TypeScript が検出しない。
scenarioId は `FILE_NAME_PATTERN`(`:90`)の `^[a-z0-9]+(?:-[a-z0-9]+)*$` に適合させる。

## 4. `DI5`・`B3b` の単一実装(`NFR-018`)

### 4-1. 既存実装が既に持っているもの

`idempotencyCollision.ts` は**すでに D5 を分類し、D1 付き経路の異内容を `B3b` に決定している**:

| 既存 | 場所 |
| --- | --- |
| 照合キー `(テナント, D5)` と別テナントの扱い | `:52-55`・`:138-141` |
| 内容同一性判定器の注入と fail-closed(throw / `INDETERMINATE` / 複数一致 → 後着拒否) | `:163-186`・`:172-174` |
| 分類規則 `DI2`(same → 再掲)・`DI3`(different → **`B3b`**)・`I2`・`I3` | `:70-104` |
| 結果語彙 `NOT_DUPLICATE` / `REPLAY_SAVED_RESULT` / `D1_COLLISION='B3b'` / `P3_COLLISION='B13'` / `REJECT_LATER` | `:33-39` |

**新しい分類器を書くとコピー実装になり `NFR-018` 違反(P0)。**
合格条件で比較していた `rejectionReason.ts` は **DTO パーサ**であって重複先ではない。

### 4-2. 採る形

```
batchStopBoundary.ts の責務は「分類済み結果に対する D1 昇順の停止」だけ

  入力: イベント列(D1 と、decideIdempotencyCollision が返した分類結果)
  処理: D3 + 1 から D1 昇順に走査
        最初の B2(gap)または B3 で停止
        それ以降は「事前分類済み B3b を含め」すべて A5 の「未処理」
  出力: A5(受理 / 重複 / 拒否 / 退避 / 未処理)の列 + 境界結果

  D5 の同一性判定・分類は一切持たない(呼び出し側が decideIdempotencyCollision の結果を渡す)
  B3b は同関数の D1_COLLISION を合成して表現する
```

**機械的な確認**: `batchStopBoundary.ts` が `CONTENT_IDENTITY` の比較や照合キーの構築を
自前で持たないことを、AST または import グラフで検査する。

### 4-3. 正本の受け入れ例(`:760`)

> 例えば D3 = 4 で D1 = 5 が欠け、D1 = 6 が未使用 D5、D1 = 7 が既存 D5・異内容なら、
> 境界結果は **B2**、D1 = 6 と 7 はともに**未処理**であり、**D1 = 7 の B3b は返さない**。

これをテストの正解ベクタにする。

## 5. スナップショット・ドリフト検査(1 周目 P1-5)

### 5-1. 何を解くか

裁定 2 により 6-2 の段階表を関係マニフェストへ登録しない。
そのままだと **TypeScript 側の順序テストは通るが、正本の 9/11 段階が後日変わっても鳴らない**。
`DI1`・`I1`・`RG1` を実装済みへ移した後に認可順序が乖離し得る。

### 5-2. 採る形

**`docs/design/sync-protocol.md` の 6-2 の 2 表を実際に読み、TypeScript 側の段階定義と逐語照合する。**

```
Vitest から docs/design/sync-protocol.md を読む(node 環境。
  failureScenarioAdapter.ts:669-679 が tests/fixtures を readdirSync している先例がある)
  ↓ 6-2 の見出し配下から 2 表を抽出
     D1 付き経路: (段階番号, 何を確かめるか, 境界結果) × 9
     P3 経路:     (順序, 進行中, 終了後, 境界結果) × 11
  ↓ 逐語照合
TypeScript の段階定義

正本を 1 行でも変えると red
```

**正本を 1 行も改訂しない**ので確定ゲートを回さずに済み、裁定 2 を維持したままドリフトを検出できる。

**合格条件**: 読み込んだ文字列を複製して 1 行変異させたとき検査が red になること(ドリフト検出の実証)。
**原本のファイルは書き換えない。**

### 5-3. 採らなかった案

| 案 | 却下理由 |
| --- | --- |
| 関係マニフェストへ登録 | 正本 2-5 表の改訂 = **確定ゲート**(敵対レビュー + 人間承認)。TSK-322 の 11 周の直後にもう一度回すコスト。裁定 2 で見送り |
| 検査を作らず台帳の候補へ送るだけ | **台帳の候補は実装への強制点ではない**。`DI1`・`I1`・`RG1` を実装済みへ移す本タスクでは釣り合わない(1 周目 P1-5) |

## 6. 新規モジュールを足すときの登録先(漏らすと 34 件が collection エラー)

`prohibitions.spec.ts` は `describe` の外(`:581-611`)で走査対象の集合を exact-set 照合している。
**新しい `.ts` を置くたび、同一コミットで下記を追随する。**

| # | 対象 | 場所 | 注意 |
| --- | --- | --- | --- |
| 1 | `EXPECTED_PRODUCT_FILE_NAMES` | `prohibitions.spec.ts:112-141` | ソート後比較なので並び順は自由 |
| 2 | `EXPECTED_VALUE_EXPORTS` | 同 `:143-318` | **値 export の完全集合**。実行時の `Object.keys(module)` と照合 |
| 3 | `EXPECTED_TYPE_EXPORTS` | 同 `:319-536` | **型 export が 0 件でも `[]` エントリが必須** |
| 4 | **`.claude/core-areas.json`** | `sync-protocol` の `paths` | **製品と spec を個別に列挙**するのが現行の作法(例: `ackAdapter.ts` と `ackAdapter.spec.ts` の両方)。**新規 3 モジュール + 各 spec = 6 パス** |
| 5 | **`tests/test_core_guard.py`** | 同上の期待値 | `core-areas.json` と一致させる。**両方を同時に更新しないと green のまま逐行確認の対象から外れる**(1 周目 P1-3) |

`tests/fixtures/sync-protocol-failures/**` は**グロブ**なので資産 JSON の追加では 4・5 は不要。

## 未解決・検討メモ

- **`CANON_P3_ACCEPTED_RESULT_ID` の添字 0 依存**(`canonOracle.ts:517-518`)はステップ 2・3 で
  `R-P3-BOUNDARY` の allow-list を触るため踏みやすい。解消できるならステップ 2 で解消するが、
  射程を広げないため必須にはしない(合格条件は「先頭 `変更受理` を動かさない」に留める)
- **`faultInjection` を実行器が一切読んでいない**。3-4 で語彙と組合せを閉じても、
  **γ の射程では資産に書けるだけで実測されない**。実測は runner を書く **TSK-330** の責務であることを
  繰り延べ理由に明記する
- **P3 の 3 注入点は 8-1 の T 要素境界では表せない**(`T7` の「後」・配信・端末永続化はトランザクション外)。
  18 組とは**別の語彙**として閉じる
