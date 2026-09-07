---
feature: sync-server-apply
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。ラッパーの implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— ラッパーが「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d293b75e687816a8c45e921b998da75
branch: feature/sync-server-apply
created: 2026-09-07
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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

正本: `docs/design/sync-protocol.md`(**v0.3 approved・2026-09-07**)の **4-5**(D5 衝突規則)・
**6 章**(処理段階・境界結果)・**8 章**(原子性・経路表)・**10-2 / 10-3**(`NFR-019(d)` の観点と資産契約)。

対応する要件:

- [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012) — 「べき等キーの記録・イベント保存・prefix 更新・状態遷移が**単一の DB トランザクションで確定する**」/ 「連番に欠落があればそれ以降を適用しない」/ 改訂・墓標・記録権拒否の別カテゴリ
- [FR-013](../../requirements/requirements-pitchlog-2026-07-22.md#FR-013) — 記録権のない端末のイベントをサーバーが拒否する(`P4` / `B4`)
- [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034) / [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010) — 「内容・存在が応答から判別できない」(6-5 の非開示規則・段階順序「③認可 < ④D5」の根拠)
- [NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019) **(d)** — 同期プロトコルの故障系テスト。**6 項目のうち 4 項目は後続 α が実装済み**で、残る **2 項目(墓標/改訂の適用・サーバー適用の原子性〔クラッシュ注入〕)がサーバー側**として本タスクへ残っている
- [NFR-018](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-018) — **ドメイン計算の単一実装**。D5 分類を再実装しない

調査の正: [research.md](research.md)。詳細設計: [design.md](design.md)。

**目的**: 4-5・6 章・8 章を**機械が読める形へ固定**し、`NFR-019(d)` の残り 2 項目を
**実行できる状態の 1 歩手前(契約・オラクル・注入点・資産)まで**進める。

## 2. スコープ

**人間の裁定(2026-09-07)により、射程は「契約・オラクル・注入点・資産の固定」に限定する**(後続 β と同型)。
裁定の全文と根拠は [research.md](research.md)「人間の裁定」節および 4 節の追加裁定。

### やること

1. **`R-TXN-ROUTE` の reader 新設** — 8-1 の経路表(`P1`〜`P5`)と T 要素(`T1`〜`T9`)の 14 要素
2. **6-2 の処理段階** + **2 層の正本ドリフト検査**(harness で正本↔スナップショット / Vitest でスナップショット↔TS)
3. **`RG1` 共通前段ゲート**
4. **既存 D5 分類器の正本への是正**(判定不能を経路別に `B3b`/`B13` へ)+ **`DI5` の A5 停止境界**(後段候補をコールバックで注入)
5. **allow-list から実装済みへの移動 7 ID** — `DI1`・`DI4`・`I1`・`I4`・`RG1`・`DI5`・`B3b`
6. **故障系契約の再設計** — 期待フィールド共通 9 件 / 省略可否の条件付き / `schemaVersion: 2` / **契約検査と結果検査の分離** / P5 の値関係検査 / 注入点の 18 組
7. **正本必須資産 ID の母集合と 2 つの繰り延べ表(exact-set)** + **シナリオ資産 9 件**

### やらないこと(受け取り先つき)

| 項目 | 受け取り先 | 理由 |
| --- | --- | --- |
| **全シナリオの runner**(実行検証)+ **`backend/` 実装** + **8 章の適用実装** | **[TSK-330(後続 γ')](https://app.notion.com/p/3d493b75e68781ce8417d9ed882ece5b)** — 起票済み・**開始条件は TSK-250 の完了** | `backend/` は `GET /health` の 11 行のみで DDL・マイグレーション・ORM が皆無 |
| **`B3a`(= `P5 + T9`)** | **TSK-330** | 正本の帰結が**不可分な `P5 + T9`**(`:1248`・`:1209`)。allow-list から外すと機械上は全体が実装済みに見える |
| **`T9` の保存 / `T7` の無効化意図の保存・配信 / `I5`・`I6`** | **TSK-330** | いずれも永続化を伴う |
| **復元ライフサイクル系 8 資産・`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence`** | **TSK-330** | **9 章(復元)・5 章(`O4`)の論点であり `NFR-019(d)` の 2 項目ではない**。**stable ID つきの繰り延べ表で追跡**(ステップ 7) |
| **wire 形式・プロパティ名・JSON / API スキーマ** | **[TSK-331](https://app.notion.com/p/3d493b75e687811bb75de7d0f366cc9d)** — 起票済み | 要件書に要求が一切無く、置き場も未決 |
| **`U-13`・`U-14`** | **TSK-329** | v0.1 由来の既存欠陥 |
| **6-2 の段階表の関係マニフェスト登録** | — | 裁定 2。代わりに**2 層のドリフト検査**で守る |
| **`T4`(状態遷移)の計算本体** | **`NFR-018` 区分 (α)** | 設計 8-6 P-50「本書は再計算の実現方式を決めない」 |
| **(B) 論点 18・論点 21** | **実装計画(バックエンド)** | 論点 21 は「15 万プレイ蓄積での実測が要る」 |
| **正本 `docs/design/sync-protocol.md` の改訂** | — | 裁定により行わない。**確定ゲートを回さない** |

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/sync-protocol.md` | **反映なし** — 正本を改訂しない(裁定 2・4) | — |
| `docs/requirements/requirements-pitchlog-2026-07-22.md` | **反映なし** | — |
| `docs/adr/*` | **反映なし** | — |
| `docs/development/harness-evaluation.md` | **`## 候補` へ 2 件**: ① **ハーネス設計書の `contracts/` 記述の揺れ**(`:181` は OpenAPI を含む / `:198` は NFR-019a のベクタに限定。10-3 と `ADR-003 D-1-b` は後者を援用 — TSK-331 の置き場裁定に直撃)② **CI の frontend ジョブが正本の変更で起動しない**(`ci.yml:124-128` の filters が `frontend/**` のみ。正本↔実装の照合を Vitest だけに置くと後日のドリフトを取り落とす — 本タスクは harness 側に置いて回避した)。変更履歴表へ 1 行(**`H-*` の新規採番なし・版は上げない**) | **PR レビュー** |
| `docs/README.md` | 台帳行の最終更新日を現行化 | **PR レビュー** |

### 正本体系外だが同一 PR で更新するもの

| 対象 | 変更内容 |
| --- | --- |
| `frontend/src/lib/sync/canonOracle.ts` | `R-TXN-ROUTE` の専用パーサと reader / allow-list の用途別分割と **7 ID の移動** |
| `frontend/src/lib/sync/idempotencyCollision.ts` +`.spec.ts` | **判定不能・比較例外を経路別に `B3b`/`B13` へ是正**(正本 4-5 との乖離の解消) |
| `frontend/src/lib/sync/processingStages.ts` +`.spec.ts`(新規) | 6-2 の処理段階・順序不変条件・スナップショット照合 |
| `frontend/src/lib/sync/restoreAdjustmentGate.ts` +`.spec.ts`(新規) | `RG1` 共通前段ゲート |
| `frontend/src/lib/sync/batchStopBoundary.ts` +`.spec.ts`(新規) | `DI5` の A5 停止境界(**分類は持たず、後段候補をコールバックで注入**) |
| `frontend/src/lib/sync/failureScenarioContract.ts` | 共通 9 件 / 条件付き省略可否 / `schemaVersion` 照合 / **契約検査と結果検査の分離** / P5 の値関係検査 / 注入点の 18 組 |
| `frontend/src/testing/failureScenarioAdapter.ts` | 2 つの繰り延べ表(exact-set) |
| `frontend/src/lib/sync/prohibitions.spec.ts` | **3 つの exact-set** の追随 |
| `scripts/design_relations/processing-stages.json`(新規) | **6-2 の段階表のスナップショット**(2 層検査の中間資産) |
| `scripts/check_processing_stages.py` + `tests/test_check_processing_stages.py`(新規) | **harness(常時実行)で正本 6-2 ↔ スナップショットを照合** |
| `tests/fixtures/sync-protocol-failures/` | 既存 4 資産の **`_v2` 移行** + **シナリオ資産 9 件**(新規) |
| `.claude/core-areas.json` / `tests/test_core_guard.py` | **新規 3 モジュール + 各 spec の 6 パス**を `paths` へ / **スナップショットと新規検査器の 3 パス**を `guard_paths` へ |

## 4. 実装方針

### 重さ分類 = コア領域(根拠)

`.claude/core-areas.json` の `sync-protocol` 領域に `frontend/src/lib/sync/**`(製品と spec を**個別に**列挙)と
`docs/design/sync-protocol.md` が登録されており、本タスクの主対象がそこに含まれる。
`game-state` / `recording-rights` / `tenant-isolation` にも重複帰属する。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須(PR 作成者以外)**。

**本タスクは既存のコア領域コード(`idempotencyCollision.ts`)の振る舞いを変更する**(正本 4-5 への是正)。
逐行確認の優先度で最上位に置く。

### 機構の詳細設計

密度が高いため [design.md](design.md) へ分離した(内容を本節へ複製しない):

- **1 章** `R-TXN-ROUTE` 専用パーサ / **2 章** allow-list の用途別分割
- **3 章** 故障系契約(共通 9 件・条件付き省略可否・`schemaVersion`・契約検査と結果検査の分離・P5 の値関係・注入点)
- **4 章** D5 分類の単一実装と正本への是正 / **5 章** 2 層のドリフト検査
- **6 章** 正本必須資産 ID の母集合と 2 つの繰り延べ表 / **7 章** 新規資産の登録先

### 追加の人間裁定(2026-09-07・計画レビュー 2 周目)

| # | 論点 | 裁定 |
| --- | --- | --- |
| 6 | `DI5`・`B3b` | **両方やる** — 既存 D5 分類器の判定不能を正本どおり `B3b`/`B13` へ是正し、後段候補をコールバックで注入する |
| 7 | ドリフト検査の置き場 | **2 層**(harness の Python が正本↔スナップショット / Vitest がスナップショット↔TS)。`ci.yml` と `test_ci_wiring.py` を触らない |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

合格条件は **`[機械]`** と **`[手動]`** に書き分ける。**`[手動]` を機械 green に数えない。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`R-TXN-ROUTE` の専用パーサと reader**(`canonOracle.ts`)。経路行 = `:` 1 個 + `=` 1 個 + `,` split、T 要素行 = `:` 1 個かつ **`=` を明示的に禁止**。2 つの exact-set 照合(関係全体 = 14 / 経路が参照する T の和集合 = 9) | `[機械]` `pnpm test` green / **変異 5 件以上**(未知 ID・T 行に `=` 混入・経路行から `=` 欠落・参照 T 欠落・ID 重複)/ `prohibitions.spec.ts` の 3 exact-set 追随 / `[手動]` 14 要素が正本 8-1 と逐語一致 |
| 2 | **`processingStages.ts`(新規)+ 2 層ドリフト検査 + `DI1`・`DI4`・`I1`・`I4` を実装済みへ**。スナップショット `scripts/design_relations/processing-stages.json` を新設し、**harness の `check_processing_stages.py` が正本 6-2 の 2 表と逐語照合**、**Vitest がスナップショットと TS 実装を照合**する | `[機械]` 全 green / **正本 6-2 を 1 行変えると harness の検査が red**(常時実行ジョブで確認)/ **スナップショットを 1 行変えると Vitest が red** / `EXPECTED = 実装済み ∪ 射程外` の総和が不変 / **core-areas の `paths` に 2 パス・`guard_paths` に 3 パスを登録** / `[手動]` 9 段階 + 11 段階の逐行確認 |
| 3 | **`restoreAdjustmentGate.ts`(新規)+ `RG1` を両関係で実装済みへ**。右辺 10 節を逐語固定 | `[機械]` 全 green / 右辺 10 節が正本 `:768` と逐語一致 / **`R-P3-BOUNDARY` の allow-list 先頭 `変更受理` を動かしていない** / core-areas に 2 パス登録 / `[手動]` fail-closed の向きが**止める側**に倒れている |
| 4 | **既存 D5 分類器を正本 4-5 へ是正 + `batchStopBoundary.ts`(新規)+ `DI5`・`B3b` を実装済みへ**。① `idempotencyCollision.ts` の**判定不能・比較例外を経路別に `B3b`/`B13`** へ写像(複数一致による破損は別ケースとして明示)② 新モジュールは**分類を持たず**、**未使用 D5 の後段候補を遅延評価のコールバックで注入**し、**gap 後は呼ばれないことを保証**する | `[機械]` 全 green / **正本 4-5 の判定不能行(`:404`)どおり D1 付き経路 = `B3b`・P3 = `B13`** / 両経路の変異試験 / **`batchStopBoundary.ts` が D5 の同一性判定・分類を自前で持たない**(機械確認)/ **正本 `:760` の例**(D3=4・D1=5 欠落・D1=6 未使用 D5・D1=7 既存異内容 → `B2`・両方未処理・`B3b` を返さない)/ **gap 後にコールバックが呼ばれない**ことの検査 / core-areas に 2 パス登録 / `[手動・最重要]` **既存振る舞いの変更**なので逐行確認 |
| 5 | **故障系契約の再設計**。期待フィールドを**共通 9 件(無条件)**にし**省略可否だけを `applicationPath` で条件付き**に。**`schemaVersion` を 2 へ繰り上げ**、**validator が構造と `schemaVersion` の組を照合**する。**契約検査と結果検査を分離**し、結果側は**契約が `omittedBecause` としたキーの不在だけを許可**する。既存 4 資産を **`_v2`** へ移行し、**`_v1` のハードコードを現行版の宣言表へ**置き換える | `[機械]` 全 green / **旧 `schemaVersion` + 新構造 / 新 `schemaVersion` + 旧構造がいずれも red** / **`applicationPath` が `P1`〜`P5` の資産で後半 4 件を省略すると red** / **既存 runner が 5 キーを返しても green**(結果検査の分離)/ **サーバー経路で実値が欠落すると red** / 旧 `_v1` への参照が残っていない / `[手動]` `_v1` → `_v2` の移行が 10-3 `:1689` を満たす(**「旧版参照が存在する間に旧資産を削除しない」**という不変条件で説明する) |
| 6 | **P5 の値関係検査と注入点の 18 組**。`P5分岐` を discriminated union にし、**`B3b` は先着原本が初期永続状態と一致・先着と後着の D5 が同一・内容が異なることを実行時検査**、**`B3a` は対象 D5 が初期べき等集合に存在しないことを実行時検査**。注入点は `P1`〜`P5` の経路型・`T1`〜`T9`・**有効な 18 組**・P3 のトランザクション外 3 注入点を閉じる(**18 組はステップ 1 の reader から導出し二重定義しない**) | `[機械]` 全 green / **異なる D5・同一内容・既存 D5 の各変異が red** / **無効な T ID・`P1` に `T9`・誤字のある P3 注入点が red** / `[手動]` 18 組が正本 8-1 と一致 |
| 7 | **母集合 exact-set と 2 つの繰り延べ表 + 資産 2 件**。① **正本必須資産 ID の母集合**(10-2 の故障系シナリオ表 + 10-3 が名指しする ID)を stable な小文字 scenarioId で全件定義 ② **`作成済み ∪ 未作成繰り延べ = 母集合`** ③ **`SCENARIO_RUNNERS ∪ runner 繰り延べ = FAILURE_SCENARIO_IDS`** ④ 資産 `tombstone-application`・`revision-application` を作成 | `[機械]` **3 つの exact-set のいずれからも 1 件消すと red** / 契約検査 green かつ実行ケースが増えない / `FIXTURES` と件数 assert を更新 / `[手動]` 母集合が 10-2 の全行を覆い、繰り延べ行に**必要な契約拡張と TSK-330** が書かれている |
| 8 | **資産 7 件**を追加し繰り延べ表から外す — `p1-crash-boundaries`・`p2-crash-boundaries`・`p3-crash-boundaries`・`p4-crash-boundaries`・`p5-crash-boundaries`・`d1-mixed-batch`・`b3b-after-gap`。**`FAILURE_SCENARIO_IDS` の末尾に追加**(位置依存を壊さない) | `[機械]` 3 つの exact-set が保たれる / 各資産が経路別の必須項目を満たす / **`p5-crash-boundaries` が `P5分岐` の値関係検査を通る** / `[手動]` 注入点が**ステップ 6 で閉じた 18 組**から選ばれ、正本 10-2 の各行の期待する不変条件と対応している |

**順序の根拠**: 1 が先(T 要素・経路の語彙をステップ 2〜4 とステップ 6 の 18 組が使う)/ 2 → 3 → 4 は依存順 / 5 が 6 より先(共通 9 件の枠が無いと P5 の追加検査を載せられない)/ **7 で母集合と繰り延べ機構を原子的に立ててから、8 で資産を移す**(ステップ 7 時点で繰り延べ表が非空なので「1 件消すと red」を実証できる)。

**確定ゲートは回さない**(正本を改訂しないため)。コミット件名には `(ステップ <k>/8)` をちょうど 1 個含める。

### 主要リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | `parseCanonBoundaryResults` を流用すると **silent-pass** する | ステップ 1 で専用パーサ。**T 行への `=` 混入変異**を合格条件に |
| R2 | **allow-list の移動を既存テストがほぼ検出しない**(`EXPECTED` が和集合のため) | 各ステップで**製品表と canon の突合テスト**を必ず足す |
| R3 | `prohibitions.spec.ts` の 3 exact-set 漏れで 34 件が collection エラー | 各ステップの合格条件に明記。**型 export 0 件でも `[]` エントリが必須** |
| R4 | `CANON_P3_ACCEPTED_RESULT_ID` の添字 0 依存 | ステップ 3 で「先頭 `変更受理` を動かさない」 |
| R5 | `P4` の左辺と `T8` の body が前方一致 | **`startsWith(\`${id}:\`)`** で引く |
| R6 | **既存 D5 分類器の是正がコア領域の振る舞いを変える** | ステップ 4 を**逐行確認の最優先**に置く。両経路の変異試験を必須に |
| R7 | **`_v2` 移行が 10-3 `:1689` に反する** | 不変条件を「**旧版参照が存在する間に旧資産を削除しない**」と正しく述べ、**同一コミット内で「新版追加 → 全参照移行 → 旧版削除」**の順に行う |
| R8 | **契約検査と結果検査を同じ validator で緩めると `P1`〜`P5` の実値必須まで緩む** | ステップ 5 で**両者を分離**。「既存 runner green」と「サーバー経路の欠落 red」を**両方**合格条件に |
| R9 | **正本ドリフト検査が CI で起動しない**(`ci.yml:124-128` は `frontend/**` のみ) | **harness ジョブ(paths filter なし)**に Python 検査を置く。台帳の候補へも送る |

## 5. DoD(受け入れ基準)

- [ ] **`R-TXN-ROUTE` の 14 要素**が `canonOracle.ts` から読め、正本 8-1 と逐語一致する
- [ ] **6-2 の処理段階**が固定され、**正本を書き換えると harness の検査が red**・**スナップショットを書き換えると Vitest が red** になる
- [ ] **既存 D5 分類器の判定不能・比較例外が正本 4-5 どおり経路別に `B3b`/`B13`** を返す
- [ ] **allow-list の 7 ID**(`DI1`・`DI4`・`I1`・`I4`・`RG1`・`DI5`・`B3b`)が実装済みへ移り右辺が逐語照合されている。**`B3a`・`I5`・`I6` は射程外に残り理由が TSK-330 を名指し**
- [ ] **`EXPECTED = 実装済み ∪ 射程外` の総和が不変**
- [ ] **D5 の分類が `decideIdempotencyCollision` の一系統に限定**され、`batchStopBoundary.ts` が分類を持たない(`NFR-018`)
- [ ] **期待フィールドが共通 9 件**・**省略可否だけが条件付き**・**`schemaVersion: 2`** で構造と組で照合される
- [ ] **契約検査と結果検査が分離**され、既存 runner が green のまま**サーバー経路の欠落は red**
- [ ] **P5 の値関係**(先着/後着の D5 同一・内容差異・未使用性)が実行時検査される
- [ ] **注入点の 18 組と P3 の 3 注入点が閉じ**、無効な値・組合せが red
- [ ] **3 つの exact-set**(母集合 / 未作成繰り延べ / runner 繰り延べ)が宣言され、**どれも 1 件消すと red**
- [ ] **シナリオ資産 9 件**が存在し契約検査を通る
- [ ] **`backend/` を 1 行も変更していない**・**正本 `docs/design/sync-protocol.md` を 1 行も変更していない**
- [ ] **新規 3 モジュール + 各 spec の 6 パス**が `paths` に、**スナップショットと新規検査器の 3 パス**が `guard_paths` に登録されている
- [ ] **TSK-330 と TSK-331 が起票され相互リンクされている**
- [ ] /check が全グリーン(`[手動]` 条件を green に数えていない)
- [ ] **人間の逐行確認(PR 作成者以外)が完了** — 最優先は**ステップ 4(既存振る舞いの変更)**、次にステップ 2 の段階順序

## 6. テスト計画

`NFR-019` の区分は **(a) 一致性 / (b) 越境 / (c) E2E 主要分岐 / (d) 同期故障系**。
**「(a) 単体」という区分は要件書に存在しない**(後続 α の計画書と PR #44 本文の誤記 — `sync-ack-contract/research.md:150` の `E-1`)。

| 区分 | 足すか | 内容 |
| --- | --- | --- |
| **(a) 一致性** | **足さない** | 対象は `NFR-018` 区分 (α) の対象計算のみ。同期プロトコルは対象外 |
| **(b) 越境** | **足さない** | 対象は `FR-034` の認可行列。6-5 の非開示規則が (b) と接する点は worklog に残す |
| **(c) E2E** | **足さない** | 列挙が閉じている |
| **(d) 故障系** | **契約・注入点・資産 9 件を足す。runner は TSK-330 へ送る** | 共通 9 件 / `schemaVersion: 2` / 契約検査と結果検査の分離 / P5 の値関係 / 18 組 / 3 つの exact-set |

### ランナー別

| 層 | 追加するテスト |
| --- | --- |
| **Vitest**(`frontend/`) | ステップ 1: reader/parser 一致 + 変異 5 件以上 / ステップ 2: 段階の単体テスト + **スナップショット↔TS 照合**(スナップショット 1 行変異で red)/ ステップ 3: `RG1` の逐語照合 + 変異 / **ステップ 4: 判定不能の経路別変異(D1 → `B3b` / P3 → `B13`)・`:760` の正解ベクタ・分類の自前実装が無いことの機械確認・gap 後にコールバックが呼ばれないこと** / ステップ 5: 経路別省略可否の変異・`schemaVersion` の組の変異・**既存 runner が green のままであること** / ステップ 6: P5 の値関係変異・注入点の無効値と無効組合せ / ステップ 7・8: 3 つの exact-set 変異 + 資産の契約検査 |
| **pytest**(ルート) | **`tests/test_check_processing_stages.py`(新規)** — 正本 6-2 ↔ スナップショットの照合と、**正本 1 行変異で red** になること。`test_core_guard.py` に**新規 6 パス(`paths`)+ 3 パス(`guard_paths`)**を登録 |
| **pytest**(`backend/`) | **追加なし**(`backend/` を変更しない) |
| **Playwright** | **追加なし** |

### 変異試験の規律(既存作法に従う)

- 変異は **`structuredClone`** した複製に対して行い、**オラクル原本・正本ファイルを書き換えない**
- 要素の位置は添字リテラルでなく **`startsWith(\`${id}:\`)`** で引き、**`toBeGreaterThanOrEqual(0)` を先に主張**する
- `toThrowError(/…/)` は**正規表現でメッセージの一部**を照合する

### 検証コマンド

1. `frontend/` で `pnpm exec prettier --check .` / `pnpm exec eslint .` / `pnpm exec vue-tsc --noEmit` / `pnpm test`
2. リポジトリルートで `uv run ruff check .` / `uv run ty check` / `uv run pytest tests/`
3. `uv run python scripts/check_design_propagation.py` / `check_doc_coverage.py` / `check_docs_status.py` が rc=0(**正本を変えないので現状維持**)
4. `uv run python scripts/check_processing_stages.py` が rc=0(新規)
5. `uv run python scripts/feature_status.py` がステップ表を **8 本**として読む
6. `uv run python scripts/check_plan_docs_sync.py --plan docs/features/sync-server-apply/plan.md --base origin/develop` が rc=0
