---
feature: sync-server-apply
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d293b75e687816a8c45e921b998da75
branch: feature/sync-server-apply
created: 2026-09-07
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 同期プロトコル — サーバー適用の処理段階と原子性(後続 γ)

## 1. 背景・目的

Notion タスク: [TSK-321](https://app.notion.com/p/3d293b75e687816a8c45e921b998da75)(TSK-280 の `/pr` クローズ処理で 2026-09-04 に起票)

TSK-280(イベント契約)が `DI1`・`DI5`・`I1`・`B3a` を「6 章の処理段階に依存する」として
**理由つき allow-list で除外**し(`frontend/src/lib/sync/canonOracle.ts:480-511`)、
後続 α(TSK-319)が「6 章の処理段階 / 8 章」を、後続 β(TSK-320)が「サーバー実装」を、
それぞれ後続 γ へ送った。本タスクはその受け皿である。

正本: `docs/design/sync-protocol.md`(**v0.3 approved・2026-09-07**)の **6 章**(処理段階・境界結果)・
**8 章**(サーバー適用の原子性・経路表)・**10-3**(`NFR-019(d)` のテスト資産契約)。

対応する要件:

- [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012) — 「べき等キーの記録・イベント保存・prefix 更新・状態遷移が**単一の DB トランザクションで確定する**」(8 章の一次典拠)/ 「連番に欠落があればそれ以降を適用しない」/ 改訂・墓標・記録権拒否の別カテゴリ
- [FR-013](../../requirements/requirements-pitchlog-2026-07-22.md#FR-013) — 記録権のない端末のイベントをサーバーが拒否する(`P4` / `B4`)
- [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034) / [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010) — 「内容・存在が応答から判別できない」(6-5 の非開示規則・段階順序「③認可 < ④D5」の根拠)
- [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019) **(d)** — 同期プロトコルの故障系テスト。**6 項目のうち 4 項目は後続 α が実装済み**で、残る **2 項目(墓標/改訂の適用・サーバー適用の原子性〔クラッシュ注入〕)がサーバー側**として本タスクへ残っている
- [NFR-018](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-018) — **ドメイン計算の単一実装**。D5 分類を再実装しない(本計画の中核制約の 1 つ)

調査の正: [research.md](research.md)。詳細設計: [design.md](design.md)。

**目的**: 6 章の処理段階と 8 章の原子境界を**機械が読める形へ固定**し、
`NFR-019(d)` の残り 2 項目を**実行できる状態の 1 歩手前(契約・オラクル・注入点)まで**進める。

## 2. スコープ

**人間の裁定(2026-09-07)により、射程は「契約・オラクル・注入点の固定」に限定する**(後続 β と同型)。
裁定の全文と根拠は [research.md](research.md)「人間の裁定」節。

### やること

1. **`R-TXN-ROUTE` の reader 新設** — 8-1 の経路表(`P1`〜`P5`)と T 要素(`T1`〜`T9`)の 14 要素を
   `canonOracle.ts` から読めるようにする。**マニフェストには既に存在するが frontend の reader が無い**
2. **6-2 の処理段階の語彙と順序不変条件** + **正本からのスナップショット・ドリフト検査**
3. **`RG1` 共通前段ゲート** — 復元調整中の fail-closed 停止
4. **`DI5` の A5 停止境界** — **既存の D5 分類器の結果を消費し、分類を再実装しない**
5. **allow-list から実装済みへの移動 7 ID** — `DI1`・`DI4`・`I1`・`I4`・`RG1`・`DI5`・`B3b`
6. **故障系契約の期待フィールドを共通 9 件へ**し、**省略可否を `applicationPath` で条件付き**にする
7. **注入点の閉じた語彙と実行時検査** / **繰り延べ表(exact-set)と `NFR-019(d)` のシナリオ資産 2 件**

### やらないこと(受け取り先つき)

| 項目 | 受け取り先 | 理由 |
| --- | --- | --- |
| **`NFR-019(d)` 2 項目の実行器** + **`backend/` 実装** + **8 章の適用実装** | **[TSK-330(後続 γ')](https://app.notion.com/p/3d493b75e68781ce8417d9ed882ece5b)** — 起票済み・**開始条件は TSK-250 の完了** | `backend/` は `GET /health` の 11 行のみで DDL・マイグレーション・ORM が皆無。原子性を実測する対象が存在しない |
| **`B3a`(= `P5 + T9`)** | **TSK-330** | **正本の `B3a` の帰結は不可分な `P5 + T9`**(設計 `:1248`・`:1209`)であり、判定だけの下位能力ではない。**allow-list に射程外として残す**(理由を TSK-330 名指しへ更新) |
| **`T9` の保存 / `T7` の無効化意図の保存・配信 / `I5`・`I6`** | **TSK-330** | いずれも永続化を伴う原子境界 |
| **繰り延べる故障系資産** — 復元ライフサイクル 8 シナリオ(10-3 `:1692`)/ `p3-invalidation-consumed-before-complete`(同 `:1702`)/ `P1`〜`P5` の故障行列 | **TSK-330** | **本タスクの exact-set 繰り延べ表で ID・必要な契約拡張・受け取り先を個別に追跡する**(ステップ 7) |
| **wire 形式・プロパティ名・JSON / API スキーマ** | **[TSK-331](https://app.notion.com/p/3d493b75e687811bb75de7d0f366cc9d)** — 起票済み | **要件書に API・wire・JSON スキーマの要求が一切無く**、置き場も未決(ハーネス設計書 `:181` と `:198` の記述が食い違う) |
| **`U-13`(部分成功の同期済み遷移)・`U-14`(退避結果再掲の `B1`/`B4` 分岐)** | **TSK-329** | v0.1 由来の既存欠陥。正本自身が「実装が一意にならない」と認めている |
| **6-2 の段階表の関係マニフェスト登録** | — | 裁定 2。代わりに**スナップショット・ドリフト検査**(ステップ 2)でドリフトを検出する |
| **`T4`(状態遷移)の計算本体** | **`NFR-018` 区分 (α)** | 設計 8-6 P-50「本書は再計算の実現方式を決めない」 |
| **(B) 論点 18(HTTP 形状・バッチ単位)・論点 21(再計算の粒度)** | **実装計画(バックエンド)** | 論点 21 は「15 万プレイ蓄積での実測が要る」(設計 `:1555`) |
| **移行取り込みが適用経路 `P1`〜`P5` を通るかの規定** | **移行仕様タスク** | 設計 `:219` が移行の禁止事項を同タスクへ割り当て済み |
| **正本 `docs/design/sync-protocol.md` の改訂** | — | 裁定により行わない。**確定ゲートを回さない** |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/sync-protocol.md` | **反映なし** — 本タスクは正本を改訂しない(裁定 2・4)。既存の記述を機械へ固定するだけ | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/adr/*` | **反映なし** | — |
| `docs/development/harness-evaluation.md` | **`## 候補` へ 1 件**: **ハーネス設計書の `contracts/` 記述の揺れ** — `:181` は「OpenAPI スキーマ・付録 E ゴールデンベクタ」、`:198` は「NFR-019a のゴールデンベクタの置き場」に限定し、10-3 と `ADR-003 D-1-b` は後者を援用している(TSK-331 の置き場裁定に直撃する)。変更履歴表へ 1 行(**`H-*` の新規採番なし・版は上げない** — 設計書 7.6-3 前段) | **PR レビュー** |
| `docs/README.md` | 台帳行の最終更新日を現行化 | **PR レビュー** |

### 正本体系外だが同一 PR で更新するもの

| 対象 | 変更内容 |
| --- | --- |
| `frontend/src/lib/sync/canonOracle.ts` | `R-TXN-ROUTE` の専用パーサと reader / allow-list の用途別分割と **7 ID の移動** |
| `frontend/src/lib/sync/processingStages.ts` +`.spec.ts`(新規) | 6-2 の処理段階・順序不変条件・**正本ドリフト検査** |
| `frontend/src/lib/sync/restoreAdjustmentGate.ts` +`.spec.ts`(新規) | `RG1` 共通前段ゲート |
| `frontend/src/lib/sync/batchStopBoundary.ts` +`.spec.ts`(新規) | `DI5` の A5 停止境界(**既存 D5 分類器の結果を消費**) |
| `frontend/src/lib/sync/failureScenarioContract.ts` | 期待フィールドを共通 9 件へ / 省略可否の条件付き化 / P5 入力の discriminated union / 注入点の実行時検査 |
| `frontend/src/testing/failureScenarioAdapter.ts` | 繰り延べ表(exact-set) |
| `frontend/src/lib/sync/prohibitions.spec.ts` | **3 つの exact-set** の追随 |
| `tests/fixtures/sync-protocol-failures/` | 既存 4 資産の **`_v1` → `_v2` 移行** + `NFR-019(d)` の資産 2 件(新規) |
| `.claude/core-areas.json` / `tests/test_core_guard.py` | **新規 3 モジュール + 各 `.spec.ts` の計 6 パス**を登録(製品と spec は個別登録が現行の作法) |

## 4. 実装方針

### 重さ分類 = コア領域(根拠)

`.claude/core-areas.json` の `sync-protocol` 領域に `frontend/src/lib/sync/**`(製品と spec を**個別に**列挙)と
`docs/design/sync-protocol.md` が登録されており、本タスクの主対象がそこに含まれる。
`game-state` / `recording-rights` / `tenant-isolation` にも重複帰属する
(6-5 の非開示規則がテナント分離、`P4`/`B4` が記録権、`T4` が状況計算に触れる)。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須(PR 作成者以外)**。

### 機構の詳細設計

密度が高いため [design.md](design.md) へ分離した(内容を本節へ複製しない):

- **1 章** `R-TXN-ROUTE` 専用パーサ — 既存 3 パーサがいずれも使えない理由
- **2 章** allow-list の用途別分割 — 移動する 7 ID / 残す ID の判定表
- **3 章** 故障系契約 — 共通 9 件と条件付き省略可否・`_v2` 移行・P5 の discriminated union
- **4 章** `DI5` の単一実装 — 既存 `decideIdempotencyCollision` をどう消費するか
- **5 章** スナップショット・ドリフト検査
- **6 章** 新規モジュールの登録先(`prohibitions.spec.ts` の 3 exact-set + core-areas)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

合格条件は **`[機械]`**(コマンドで判定)と **`[手動]`**(人間が確認し worklog へ記録)に書き分ける。
**`[手動]` を機械 green に数えない。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`R-TXN-ROUTE` の専用パーサと reader**(`canonOracle.ts`)。経路行 = `:` 1 個 + `=` 1 個 + `,` split、T 要素行 = `:` 1 個かつ **`=` を明示的に禁止**。2 つの exact-set 照合(関係全体の ID = 14 / 経路が参照する T の和集合 = 9) | `[機械]` `pnpm test` green / reader と parser の一致 + **変異 5 件以上**(未知 ID・T 行に `=` 混入・経路行から `=` 欠落・参照 T の欠落・ID 重複)/ `prohibitions.spec.ts` の 3 exact-set 追随 / `[手動]` 14 要素が正本 8-1 の経路表・T 要素表と逐語一致 |
| 2 | **`processingStages.ts`(新規)+ 正本ドリフト検査 + `DI1`・`DI4`・`I1`・`I4` を実装済みへ**。D1 付き 9 段階・P3 11 段階・各段階の停止境界写像・順序不変条件(「③認可 < ④D5」「④D5 < ⑤〜⑦」「外部確定は D1 昇順」)。**ドリフト検査は `docs/design/sync-protocol.md` の 6-2 の 2 表を実際に読み、段階番号・確認内容・境界結果を逐語照合する** | `[機械]` 全 green / **正本 6-2 の 1 行を書き換える変異で検査が red になる**(ドリフト検出の実証)/ **`EXPECTED = 実装済み ∪ 射程外` の総和が不変** / 移動した 4 ID が製品表に現れ canon と逐語一致 / **`core-areas.json` と `test_core_guard.py` に製品 + spec の 2 パスを登録** / `[手動]` 9 段階 + 11 段階の逐行確認 |
| 3 | **`restoreAdjustmentGate.ts`(新規)+ `RG1` を両関係で実装済みへ**。右辺 10 節(③認可後 / D5 照合前 / 全通常書き込み・内部ジョブ停止 / P1・P2・P4 は `B7` / P3 は `B10` / D5 消費なし / コミット直前再検証 / サービス再開 fail-closed / 解除・新 D4 開始不可分 / 復旧制御面だけ許可)を逐語固定 | `[機械]` 全 green / 右辺 10 節が正本 `:768` と逐語一致 / **`R-P3-BOUNDARY` の allow-list 先頭 `変更受理` を動かしていない**(`CANON_P3_ACCEPTED_RESULT_ID` の添字 0 依存)/ **core-areas に 2 パス登録** / `[手動]` fail-closed の向きが**止める側**に倒れている |
| 4 | **`batchStopBoundary.ts`(新規)+ `DI5`・`B3b` を実装済みへ**。**D5 の分類は既存 `decideIdempotencyCollision` の一系統だけに限定**し、本モジュールは**その分類済み結果に対する D1 昇順の停止だけ**を担う(`NFR-018`)。`B3b` は同関数の結果を合成して表現する | `[機械]` 全 green / **`batchStopBoundary.ts` が D5 の同一性判定・分類を自前で持たない**(AST または import で機械的に確認)/ **正本 `:760` の例**(D3=4・D1=5 欠落・D1=6 未使用 D5・D1=7 既存異内容 → 境界結果 `B2`・D1=6 と 7 はともに未処理・**`B3b` を返さない**)が通る / **core-areas に 2 パス登録** / `[手動]` 内部照合順と外部停止境界が**別軸**として実装されている |
| 5 | **故障系契約の期待フィールドを共通 9 件へ**(`queue`・`d1`・`lock`・`acceptanceDisplay`・`reinputAvailability` + **`prefix`・`idempotentResult`・`temporaryIdMapping`・`recordingRight`**)。**集合は無条件**、**省略可否だけを `applicationPath` で条件付き**にする。**P5 入力を discriminated union** にし、`B3a` は未使用 D5 + 拒否原本、`B3b` は不変な先着原本 + 同一 D5 異内容の後着を exact-key で必須化。**既存 4 資産を `_v2` へ移行**(`omittedBecause` を 4 行ずつ追記・`comparisonUnit` 25 → 45・ファイル名と内部 `version`)。**`_v1` のハードコード(`failureScenarioContract.spec.ts:72-75`)を現行版の宣言表に置き換える** | `[機械]` 全 green / **`applicationPath` が `P1`〜`P5` の資産で後半 4 件を省略すると red** / **P5 の必須値を 1 つ落とす変異が全て red** / 旧 `_v1` への参照が残っていない / `[手動]` `_v1` → `_v2` の**原子移行**が 10-3 `:1689`(「参照するテストがすべて新版へ移るまで旧版を上書きまたは削除しない」)を満たす — 同一コミット内で新版作成・全テスト移行・旧版削除が完了し、**旧版を参照するテストが存在する瞬間が無い**こと |
| 6 | **注入点の閉じた語彙と実行時検査**。`P1`〜`P5` の経路型(**`SYNC_EVENT_PATH` を流用しない** — `P5` が無い)、`T1`〜`T9`、**有効な 18 組の `(経路, T 要素)`**、P3 のトランザクション外 3 注入点(`T7` 確定後・無効化配信前 / 消費側反映後・配信完了記録前 / サーバー確定後・`I6` 端末永続化前)を閉じ、**JSON パーサで値と組合せを検査**する | `[機械]` 全 green / **無効な T ID・`P1` に `T9`・誤字のある P3 注入点がいずれも red** / 18 組は `R-TXN-ROUTE` の reader(ステップ 1)から導出し**二重定義しない** / `[手動]` 18 組が正本 8-1 の経路表と一致 |
| 7 | **繰り延べ表(exact-set)+ `NFR-019(d)` のシナリオ資産 2 件**。① **runner 未実装**の繰り延べ(`SCENARIO_RUNNERS ∪ 繰り延べ = FAILURE_SCENARIO_IDS`)② **未作成資産**の繰り延べ(復元系 8 シナリオ・`p3-invalidation-consumed-before-complete`・`P1`〜`P5` の故障行列 — ID・必要な契約拡張・受け取り先 TSK-330 を個別に列挙)。資産 2 件は **`FAILURE_SCENARIO_IDS` の末尾に追加** | `[機械]` **契約検査 green かつ実行ケースが繰り延べ分だけ減る** / **両方の繰り延べ表から 1 件消すと red** / `failureScenarioContract.spec.ts` の `FIXTURES` と件数 assert を更新 / `[手動]` 2 資産が 10-3 `:1691` の必須項目を満たし、注入点が**ステップ 6 で閉じた 18 組**から選ばれている。**未作成資産の繰り延べ理由に TSK-330 が名指しされている** |

**順序の根拠**: 1 が先(T 要素・経路の語彙をステップ 2〜4 の停止境界写像とステップ 6 の 18 組が使う)/ 2 → 3 → 4 は依存順(段階の枠が無いと `RG1` の位置も `DI5` の停止境界も表せない)/ 5 が 6・7 より先(共通 9 件と P5 の union が無いと資産を書けない)/ **6 と 7 を分けたうえで、繰り延べ表と資産と scenarioId をステップ 7 で原子的に追加する**(ステップ 6 時点では繰り延べ対象が存在せず「1 件消すと red」を試せないため — 1 周目 P0-4)。

**確定ゲートは回さない**(正本を改訂しないため)。ステップ 1〜7 のコミット件名には `(ステップ <k>/7)` をちょうど 1 個含める。

### 主要リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | **`parseCanonBoundaryResults` を流用すると silent-pass する**(`=` を検査しないため T 集合が `name` に折り畳まれる) | ステップ 1 で専用パーサを新設。**T 行への `=` 混入変異**を合格条件に入れる |
| R2 | **allow-list の移動を既存テストがほぼ検出しない**。`EXPECTED = 実装済み ∪ 射程外` なので `assertExactKnownIds` は鳴らず、`canonOracle.spec.ts:543-562` も `:563-580` も**偽 green** のまま通る | 実効的に検出するのは `:509-518` の製品表突合 1 本だけ。**各ステップで製品表と canon の突合テストを必ず足す** |
| R3 | **`prohibitions.spec.ts` の 3 exact-set 漏れ**で同ファイル 34 件が丸ごと collection エラー | 各ステップの合格条件に明記。**型 export 0 件でも `[]` エントリが必須** |
| R4 | **`CANON_P3_ACCEPTED_RESULT_ID` が allow-list の添字 0 に位置依存**(`canonOracle.ts:517-518`) | ステップ 3 の合格条件に「先頭 `変更受理` を動かさない」を入れる |
| R5 | **`P4` の左辺と `T8` の body が前方一致**する。変異テストで `startsWith('T8')` と書くと誤マッチ | **`startsWith(\`${id}:\`)` とコロン付き**で引き、`toBeGreaterThanOrEqual(0)` を先に主張する |
| R6 | **`DI5`・`B3b` が既存 D5 分類器のコピー実装になる**(**`NFR-018` 違反 = P0**) | ステップ 4 で **`batchStopBoundary.ts` が分類を自前で持たない**ことを機械的に確認する。D5 分類は `decideIdempotencyCollision` の一系統に限定 |
| R7 | **`_v1` → `_v2` の移行が 10-3 `:1689` に反する** | **同一コミット内の原子移行**(新版作成・全テスト移行・旧版削除)とし、**旧版を参照するテストが存在する瞬間を作らない**。`_v1` のハードコードを現行版の宣言表へ置き換える |
| R8 | **注入点が任意文字列のまま green になる** | ステップ 6 で 18 組を閉じ、**組合せまで実行時検査**する |

## 5. DoD(受け入れ基準)

- [ ] **`R-TXN-ROUTE` の 14 要素**(経路 `P1`〜`P5` + T 要素 `T1`〜`T9`)が `canonOracle.ts` から読め、正本 8-1 と逐語一致する
- [ ] **6-2 の処理段階**(D1 付き 9 段階・P3 11 段階)と順序不変条件が固定され、**正本を書き換えるとドリフト検査が red になる**
- [ ] **allow-list の 7 ID**(`DI1`・`DI4`・`I1`・`I4`・`RG1`・`DI5`・`B3b`)が実装済みへ移り、**右辺が逐語照合されている**。**`B3a`・`I5`・`I6` は射程外に残り、理由が TSK-330 を名指ししている**
- [ ] **`EXPECTED = 実装済み ∪ 射程外` の総和が不変**
- [ ] **D5 の分類が `decideIdempotencyCollision` の一系統に限定**され、コピー実装が無い(`NFR-018`)
- [ ] **故障系契約の期待フィールドが共通 9 件**で、**省略可否だけが `applicationPath` で条件付き**。P5 入力が discriminated union で判定証拠を必須化している
- [ ] **既存 4 資産が `_v2` へ原子移行**され、`_v1` への参照が 1 件も残っていない
- [ ] **注入点の 18 組と P3 の 3 注入点が閉じ**、無効な値・組合せが red になる
- [ ] **`NFR-019(d)` のシナリオ資産 2 件**が存在し契約検査を通る。**runner 繰り延べと未作成資産繰り延べの 2 つの exact-set** が宣言され、どちらも 1 件消すと red になる
- [ ] **`backend/` を 1 行も変更していない**・**正本 `docs/design/sync-protocol.md` を 1 行も変更していない**
- [ ] **新規 3 モジュール + 各 spec の 6 パス**が `core-areas.json` と `test_core_guard.py` に登録されている
- [ ] **[TSK-330](https://app.notion.com/p/3d493b75e68781ce8417d9ed882ece5b)(γ')と [TSK-331](https://app.notion.com/p/3d493b75e687811bb75de7d0f366cc9d)(wire スキーマ)が起票され、本タスクと相互リンクされている**
- [ ] /check が全グリーン(`[手動]` 条件を green に数えていない)
- [ ] **人間の逐行確認(PR 作成者以外)が完了**している — 最優先はステップ 2 の段階順序

## 6. テスト計画

`NFR-019` の区分は **(a) 一致性 / (b) 越境 / (c) E2E 主要分岐 / (d) 同期故障系**。
**「(a) 単体」という区分は要件書に存在しない**(後続 α の計画書と PR #44 本文の誤記 — `sync-ack-contract/research.md:150` の `E-1`)。

| 区分 | 足すか | 内容 |
| --- | --- | --- |
| **(a) 一致性** | **足さない** | 対象は `NFR-018` 区分 (α) の対象計算のみ(要件書 `:920`)。同期プロトコルは対象外 |
| **(b) 越境** | **足さない** | 対象は `FR-034` の認可行列。ただし **6-5 の非開示規則が (b) と接する**ため、帰属が要件書から一意に決まらない点を worklog に残す |
| **(c) E2E** | **足さない** | 列挙が閉じている(要件書 `:928`) |
| **(d) 故障系** | **契約と資産を足す。実行器は TSK-330 へ送る** | 期待フィールドを共通 9 件へ / P5 の判定証拠を必須化 / 注入点の 18 組を閉じる / シナリオ資産 2 件 / 2 つの繰り延べ表 |

### ランナー別

| 層 | 追加するテスト |
| --- | --- |
| **Vitest**(`frontend/`) | ステップ 1: reader/parser 一致 + **変異 5 件以上** / ステップ 2: 段階の単体テスト + **正本ドリフト検査**(正本の 1 行変異で red)+ canon 突合 / ステップ 3・4: 各モジュールの単体テスト + canon 突合 + 変異。ステップ 4 は **分類の自前実装が無いことの機械確認**を含む / ステップ 5: 経路別の省略可否の変異・P5 必須値の変異 / ステップ 6: 無効な T ID・無効な組合せ・誤字の変異 / ステップ 7: 2 つの繰り延べ表の exact-set 変異 + 資産 2 件の契約検査 |
| **pytest**(ルート) | `test_core_guard.py` に**新規 6 パス**を登録。それ以外は既存のまま green を維持 |
| **pytest**(`backend/`) | **追加なし**(`backend/` を変更しないため) |
| **Playwright** | **追加なし**(E2E は射程外) |

### 変異試験の規律(既存作法に従う)

- 変異は **`structuredClone(syncProtocolRelations)`** に対して行い、**オラクル原本を編集しない**
- 正本 markdown のドリフト検査も**読み込んだ文字列を複製して変異**させ、ファイルを書き換えない
- 要素の位置は添字リテラルでなく **`startsWith(\`${id}:\`)`** で引き、**`toBeGreaterThanOrEqual(0)` を先に主張**する
- `toThrowError(/…/)` は**正規表現でメッセージの一部**を照合する

### 検証コマンド

1. `frontend/` で `pnpm exec prettier --check .` / `pnpm exec eslint .` / `pnpm exec vue-tsc --noEmit` / `pnpm test`
2. リポジトリルートで `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/`
3. `uv run python scripts/check_design_propagation.py` / `check_doc_coverage.py` / `check_docs_status.py` が rc=0(**正本を変えないので現状維持**)
4. `uv run python scripts/feature_status.py` がステップ表を **7 本**として読む
5. `uv run python scripts/check_plan_docs_sync.py --plan docs/features/sync-server-apply/plan.md --base origin/develop` が rc=0
