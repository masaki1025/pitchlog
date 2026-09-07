---
feature: sync-server-apply
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。ラッパーの implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— ラッパーが「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d293b75e687816a8c45e921b998da75
branch: feature/sync-server-apply
created: 2026-09-07
計画レビュー周回: 4        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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

**人間の裁定により、射程は「契約・オラクル・注入点・資産の固定」に限定する**(後続 β と同型)。
裁定の全文は [research.md](research.md)「人間の裁定」節および 4 節の追加裁定。

### やること

1. **`R-TXN-ROUTE` の reader 新設** — 8-1 の経路表(`P1`〜`P5`)と T 要素(`T1`〜`T9`)の 14 要素
2. **6-2 の処理段階** + **2 層の正本ドリフト検査**(harness で正本↔スナップショット / Vitest でスナップショット↔TS)
3. **`RG1` 共通前段ゲート**
4. **既存 D5 分類器を正本 4-5 へ是正** — 判定不能・比較例外を経路別に `B3b`/`B13` へ。**複数一致は破損として内部エラーに固定**
5. **allow-list から実装済みへの移動 6 ID** — `DI1`・`DI4`・`I1`・`I4`・`RG1`・`B3b`
6. **故障系契約の再設計** — 期待フィールド共通 **10 件**(`T 要素の確定状態`を含む)/ 省略可否の条件付き / `schemaVersion: 2` / **契約検査と結果検査の分離** / P5 の値関係検査 / 注入点の 18 組
7. **母集合 26 ID・観点被覆 26 ペア・2 つの繰り延べ表・2 つの注入被覆(計 5 つの exact-set)** + **シナリオ資産 10 件**

### やらないこと(受け取り先つき)

| 項目 | 受け取り先 | 理由 |
| --- | --- | --- |
| **全シナリオの runner**(実行検証)+ **`backend/` 実装** + **8 章の適用実装** | **[TSK-330(後続 γ')](https://app.notion.com/p/3d493b75e68781ce8417d9ed882ece5b)** — 起票済み・**開始条件は TSK-250 の完了** | `backend/` は `GET /health` の 11 行のみで DDL・マイグレーション・ORM が皆無 |
| **`DI5`(混在バッチの A5)と A5 の停止境界の実装** | **TSK-330**(**`U-14` の解決後**) | **外部境界結果を返すには「保存済み退避の再掲を `B1` と `B4` のどちらにするか」を決める必要があり、それがまさに `U-14`(選択規則なし)**。任意に決めると正本の一方に反する(**人間の裁定 8**) |
| **`B3a`(= `P5 + T9`)** | **TSK-330** | 正本の帰結が**不可分な `P5 + T9`**(`:1248`・`:1209`)。allow-list から外すと機械上は全体が実装済みに見える |
| **`T9` の保存 / `T7` の無効化意図の保存・配信 / `I5`・`I6`** | **TSK-330** | いずれも永続化を伴う |
| **復元ライフサイクル系 8 資産・`p3-invalidation-consumed-before-complete`・`o4-persisted-d2-equivalence`** | **TSK-330** | 9 章(復元)・5 章(`O4`)の論点であり `NFR-019(d)` の 2 項目ではない。**stable ID と観点被覆つきの繰り延べ表で追跡**(ステップ 7) |
| **wire 形式・プロパティ名・JSON / API スキーマ** | **[TSK-331](https://app.notion.com/p/3d493b75e687811bb75de7d0f366cc9d)** — 起票済み | 要件書に要求が一切無く、置き場も未決 |
| **`U-13`・`U-14`** | **TSK-329** | v0.1 由来の既存欠陥。**`U-14` は `DI5` の前提**(上記) |
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
| `docs/development/harness-evaluation.md` | **`## 候補` へ 2 件**: ① **ハーネス設計書の `contracts/` 記述の揺れ**(`:181` は OpenAPI を含む / `:198` は NFR-019a のベクタに限定。10-3 と `ADR-003 D-1-b` は後者を援用 — TSK-331 の置き場裁定に直撃)② **CI の frontend ジョブが正本の変更で起動しない**(`ci.yml:124-128` の filters が `frontend/**` のみ。正本由来の機械資産を `scripts/` に置くと同時変更ですり抜ける)。変更履歴表へ 1 行(**`H-*` の新規採番なし・版は上げない**) | **PR レビュー** |
| `docs/README.md` | 台帳行の最終更新日を現行化 | **PR レビュー** |

**台帳と索引の更新は `/pr` のクローズ処理で行う**。**実装ステップ表には置かない**
(クローズ処理はステップ表の外側にある — 設計書 6.1)。
**同一コミットの対象は②台帳・③変更履歴表・④索引**であり、**①計画書 3 節への宣言はその前に完了させる**
(pr スキル手順 1-3)。**本計画の改訂で①は完了済み**。

### 正本体系外だが同一 PR で更新するもの

| 対象 | 変更内容 |
| --- | --- |
| `frontend/src/lib/sync/canonOracle.ts` | `R-TXN-ROUTE` の専用パーサと reader / allow-list の用途別分割と **6 ID の移動** |
| `frontend/src/lib/sync/idempotencyCollision.ts` +`.spec.ts` | **判定不能・比較例外を経路別に `B3b`/`B13` へ是正** / **複数一致を破損として内部エラーに固定**(正本 4-5 との乖離の解消) |
| `frontend/src/lib/sync/processingStages.ts` +`.spec.ts`(新規) | 6-2 の処理段階・順序不変条件・スナップショット照合 |
| `frontend/src/lib/sync/processingStages.snapshot.json`(新規) | **6-2 の段階表のスナップショット**。**`frontend/` 配下に置き、既存の `frontend/**` フィルタで Vitest が起動するようにする**(人間の裁定 9) |
| `frontend/src/lib/sync/restoreAdjustmentGate.ts` +`.spec.ts`(新規) | `RG1` 共通前段ゲート |
| `frontend/src/lib/sync/failureScenarioContract.ts` | 共通 10 件 / 条件付き省略可否 / `schemaVersion` 照合 / **契約検査と結果検査の分離** / **T 要素の全確定・全非確定** / P5 の値関係検査 / 注入点の 18 組 |
| `frontend/src/testing/failureScenarioAdapter.ts` | 2 つの繰り延べ表(exact-set) |
| `frontend/src/lib/sync/prohibitions.spec.ts` | **3 つの exact-set** の追随 |
| `scripts/check_processing_stages.py` + `tests/test_check_processing_stages.py`(新規) | **harness(常時実行)で正本 6-2 ↔ スナップショットを照合** |
| `tests/fixtures/sync-protocol-failures/` | 既存 4 資産の **`_v2` 移行** + **シナリオ資産 10 件**(新規) |
| `.claude/core-areas.json` / `tests/test_core_guard.py` | **新規 2 モジュール + 各 spec + スナップショットの 5 パス**を `paths` へ / **新規検査器 2 パス**を `guard_paths` へ |

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
- **3 章** 故障系契約(共通 10 件・条件付き省略可否・`schemaVersion`・契約検査と結果検査の分離・T 要素の確定状態・P5 の値関係・注入点・`_v2` 移行)
- **4 章** D5 分類の正本 4-5 への是正 / **5 章** 2 層のドリフト検査
- **6 章** 母集合と観点被覆と 2 つの繰り延べ表 / **7 章** 新規資産の登録先

### 追加の人間裁定

| # | 論点 | 裁定 | 周 |
| --- | --- | --- | --- |
| 6 | `DI5`・`B3b` | 両方やる(→ **裁定 8 で `DI5` を部分撤回**) | 2 |
| 7 | ドリフト検査の置き場 | **2 層**(harness の Python が正本↔スナップショット / Vitest がスナップショット↔TS) | 2 |
| **8** | **`U-14` との衝突** | **`DI5` を射程外へ戻す** — 外部境界結果には `U-14` の選択規則が要る。`batchStopBoundary.ts` は作らない。**裁定 3(`U-14` は射程外)を優先し、裁定 6 を部分撤回** | 3 |
| **9** | **スナップショットの置き場** | **`frontend/` 配下**へ置き、既存の `frontend/**` フィルタで Vitest を起動させる。`ci.yml` と `test_ci_wiring.py`(いずれも `guard_paths`)を触らない | 3 |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

合格条件は **`[機械]`** と **`[手動]`** に書き分ける。**`[手動]` を機械 green に数えない。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`R-TXN-ROUTE` の専用パーサと reader**(`canonOracle.ts`)。経路行 = `:` 1 個 + `=` 1 個 + `,` split、T 要素行 = `:` 1 個かつ **`=` を明示的に禁止**。2 つの exact-set 照合(関係全体 = 14 / 経路が参照する T の和集合 = 9) | `[機械]` `pnpm test` green / **変異 5 件以上**(未知 ID・T 行に `=` 混入・経路行から `=` 欠落・参照 T 欠落・ID 重複)/ `prohibitions.spec.ts` の 3 exact-set 追随 / `[手動]` 14 要素が正本 8-1 と逐語一致 |
| 2 | **`processingStages.ts`(新規)+ スナップショット + 2 層ドリフト検査 + `DI1`・`DI4`・`I1`・`I4` を実装済みへ**。スナップショットを **`frontend/src/lib/sync/processingStages.snapshot.json`** に置き、**harness の `check_processing_stages.py` が正本 6-2 の 2 表と逐語照合**、**Vitest がスナップショットと TS 実装を照合**する | `[機械]` 全 green / **正本 6-2 を 1 行変えると harness の検査が red** / **スナップショットを 1 行変えると Vitest が red** / **正本とスナップショットを同時に変えても Vitest が起動する**(スナップショットが `frontend/**` に当たることを `paths-filter` の設定から確認)/ `EXPECTED = 実装済み ∪ 射程外` の総和が不変 / **core-areas の `paths` に 3 パス・`guard_paths` に 2 パスを登録** / `[手動]` 9 段階 + 11 段階の逐行確認 |
| 3 | **`restoreAdjustmentGate.ts`(新規)+ `RG1` を両関係で実装済みへ**。右辺 10 節を逐語固定 | `[機械]` 全 green / 右辺 10 節が正本 `:768` と逐語一致 / **`R-P3-BOUNDARY` の allow-list 先頭 `変更受理` を動かしていない** / core-areas の `paths` に 2 パス登録 / `[手動]` fail-closed の向きが**止める側**に倒れている |
| 4 | **既存 D5 分類器を正本 4-5 へ是正 + `B3b` を実装済みへ**。① **判定不能・比較例外を経路別に `B3b`/`B13`** へ写像(正本 `:404`)② **複数一致は「一意な先着原本が無い破損」として内部エラーに固定**し `B3b`/`B13` へ混ぜない。**新規モジュールは作らない**(`DI5` は射程外 — 裁定 8) | `[機械]` 全 green / **正本 `:404` どおり D1 付き経路 = `B3b`・P3 = `B13`** / **両経路の変異試験** / **複数一致が `B3b`/`B13` に混ざらないことの検査** / 製品表と canon の突合で `B3b` の右辺が逐語一致 / `[手動・最重要]` **既存振る舞いの変更**なので逐行確認。呼び出し元への波及を確認 |
| 5 | **故障系契約の再設計**。期待フィールドを**共通 10 件(無条件)** — 既存 5 + `prefix`・`idempotentResult`・`temporaryIdMapping`・`recordingRight`・**`tElementCommitment`** — にし**省略可否だけを `applicationPath` で条件付き**に。**`schemaVersion: 2`** へ繰り上げ**構造との組を照合**。**契約検査と結果検査を分離**。**`tElementCommitment` は資産側が `{ mode: "allCommitted" \| "allNotCommitted" }`、結果側が T ID を exact-key とする状態 record** とし、キー集合が経路の T 集合(reader 由来)と一致・全要素が同値・`mode` と一致することを要求する。既存 4 資産を **`_v2`** へ移行 | `[機械]` 全 green / **結果 record の 1 要素だけを反転させる部分確定変異が red** / **キー集合が経路の T 集合と違うと red** / 旧 `schemaVersion` + 新構造 / 新 `schemaVersion` + 旧構造がいずれも red / **`applicationPath` が `P1`〜`P5` の資産で後半 5 件を省略すると red** / **既存 runner が green のまま**(結果検査の分離)/ **サーバー経路で実値が欠落すると red** / 旧 `_v1` への参照が残っていない / `[手動]` `_v2` 移行が 10-3 `:1689` を満たす(不変条件は「**旧版参照が存在する間に旧資産を削除しない**」) |
| 6 | **P5 の値関係検査 / 注入点の 18 組 / 故障注入を複数 `case` 構造へ**。`P5分岐` を discriminated union にし、**`B3b` は先着原本が初期永続状態と一致・先着と後着の D5 が同一・内容が異なる**、**`B3a` は対象 D5 が初期べき等集合に存在しない**ことを実行時検査。注入点は経路型・`T1`〜`T9`・**有効な 18 組**・P3 のトランザクション外 3 注入点を閉じる(**18 組と T 集合はステップ 1 の reader から導出し二重定義しない**)。**`faultInjection` を 1 件以上の `case` 配列**にし、被覆を宣言できる形にする | `[機械]` 全 green / **異なる D5・同一内容・既存 D5 の各変異が red** / **無効な T ID・`P1` に `T9`・誤字のある P3 注入点が red** / **既存 4 資産が単一 case として `_v2` の枠に収まる** / `[手動]` 18 組が正本 8-1 と一致 |
| 7 | **母集合・観点被覆・繰り延べ表・注入被覆 + 資産 2 件**。① **母集合 26 の scenarioId** を定義 ② **10-2 の `(d)` の観点 22 種に stable key を与え、`scenarioId × 観点key` の 26 ペアそのものを exact-set 照合** ③ `作成済み ∪ 未作成繰り延べ = 母集合` **かつ交差が空** ④ `SCENARIO_RUNNERS ∪ runner 繰り延べ = FAILURE_SCENARIO_IDS` **かつ交差が空** ⑤ **トランザクション内注入被覆 = reader の 18 組** / **トランザクション外注入被覆 = P3 の 3 点** ⑥ 資産 `tombstone-application`・`revision-application` を作成 | `[機械]` **5 つの exact-set のいずれからも 1 件消すと red** / **ペアを別シナリオへ付け替えると red** / **両方の繰り延べ表に重複登録すると red** / 契約検査 green かつ実行ケースが増えない / `FIXTURES` と件数 assert を更新 / `[手動]` **22 観点が 10-2 の `(d)` 表の全行と一致**((c) の 2 行を含めていない)。繰り延べ行に**必要な契約拡張と TSK-330** が書かれている |
| 8 | **資産 8 件**を追加し繰り延べ表から外す — `p1-crash-boundaries`・`p2-crash-boundaries`・`p3-crash-boundaries`・`p4-crash-boundaries`・**`p5-b3a-crash-boundaries`**・**`p5-b3b-unreached-t9`**・`d1-mixed-batch`・`b3b-after-gap`。**`FAILURE_SCENARIO_IDS` の末尾に追加**。**`p1`〜`p4` と `p5-b3a` で 18 組を覆い切る**(`p5-b3b-unreached-t9` は `T9` 未到達なのでトランザクション内 case を宣言しない) | `[機械]` 5 つの exact-set が保たれる / **トランザクション内注入被覆が 18 組ちょうどになる**(1 組でも欠けると red)/ 各資産が経路別の必須項目と `tElementCommitment` を満たす / **`p5-b3a-…` と `p5-b3b-…` が P5 union の両分岐をそれぞれ固定** / `[手動]` 各資産が正本 10-2 の対応行の「期待する不変条件」を表している |

**順序の根拠**: 1 が先(T 要素・経路の語彙をステップ 2・5・6 が使う)/ 2 → 3 → 4 は独立だが依存の浅い順 /
5 が 6 より先(共通 10 件の枠が無いと P5 の追加検査を載せられない)/
**7 で母集合と繰り延べ機構を原子的に立ててから、8 で資産を移す**(ステップ 7 時点で繰り延べ表が非空なので「1 件消すと red」を実証できる)。

**確定ゲートは回さない**(正本を改訂しないため)。コミット件名には `(ステップ <k>/8)` をちょうど 1 個含める。

### 主要リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | `parseCanonBoundaryResults` を流用すると **silent-pass** する | ステップ 1 で専用パーサ。**T 行への `=` 混入変異**を合格条件に |
| R2 | **allow-list の移動を既存テストがほぼ検出しない**(`EXPECTED` が和集合のため) | 各ステップで**製品表と canon の突合テスト**を必ず足す |
| R3 | `prohibitions.spec.ts` の 3 exact-set 漏れで 34 件が collection エラー | 各ステップの合格条件に明記。**型 export 0 件でも `[]` エントリが必須** |
| R4 | `CANON_P3_ACCEPTED_RESULT_ID` の添字 0 依存 | ステップ 3 で「先頭 `変更受理` を動かさない」 |
| R5 | `P4` の左辺と `T8` の body が前方一致 | **`startsWith(\`${id}:\`)`** で引く |
| R6 | **既存 D5 分類器の是正がコア領域の振る舞いを変える** | ステップ 4 を**逐行確認の最優先**に。両経路の変異試験と**呼び出し元への波及確認**を必須に |
| R7 | `_v2` 移行が 10-3 `:1689` に反する | 不変条件を「**旧版参照が存在する間に旧資産を削除しない**」とし、**同一コミット内で「新版追加 → 全参照移行 → 旧版削除」** |
| R8 | 契約検査と結果検査を同じ validator で緩めると `P1`〜`P5` の実値必須まで緩む | ステップ 5 で**両者を分離**。「既存 runner green」と「サーバー経路の欠落 red」を**両方**合格条件に |
| R9 | **正本と機械資産を同時変更すると CI をすり抜ける** | スナップショットを **`frontend/` 配下**に置き既存フィルタに載せる(裁定 9)。台帳の候補へも送る |
| R10 | **`tElementCommitment` を単一の集約値にすると部分確定を隠せる** | **資産側は `mode`・結果側は T ID を exact-key とする状態 record** に分け、キー集合を reader 由来の T 集合と照合。**結果 record の 1 要素だけを反転させる変異が red** になることを合格条件に |
| R11 | **18 組を「許可語彙」として閉じても、各資産が 1 件選ぶだけで通る** | **故障注入を複数 `case` 構造**にし、**`⋃ 宣言 case = 18 組` を exact-set 照合**する(ステップ 6・8) |
| R12 | **観点被覆を和集合で見ると、誤写像・重複・両方からの脱落を検出できない** | **`scenarioId × 観点key` のペア集合そのものを exact-set 照合**し、繰り延べ表には**交差が空**も要求する(ステップ 7) |

## 5. DoD(受け入れ基準)

- [ ] **`R-TXN-ROUTE` の 14 要素**が `canonOracle.ts` から読め、正本 8-1 と逐語一致する
- [ ] **6-2 の処理段階**が固定され、**正本を変えると harness が red**・**スナップショットを変えると Vitest が red**・**同時に変えても Vitest が起動する**
- [ ] **既存 D5 分類器の判定不能・比較例外が正本 4-5 どおり経路別に `B3b`/`B13`** を返し、**複数一致は破損として分離**されている
- [ ] **allow-list の 6 ID**(`DI1`・`DI4`・`I1`・`I4`・`RG1`・`B3b`)が実装済みへ移り右辺が逐語照合されている。**`B3a`・`DI5`・`I5`・`I6` は射程外に残り、理由が TSK-330(`DI5` は `U-14` 依存)を名指し**
- [ ] **`EXPECTED = 実装済み ∪ 射程外` の総和が不変**
- [ ] **期待フィールドが共通 10 件**・**省略可否だけが条件付き**・**`schemaVersion: 2`** で構造との組で照合される
- [ ] **`tElementCommitment` が資産側 `mode` / 結果側 T ID の状態 record** に分かれ、**キー集合が経路の T 集合と一致**し、**1 要素だけ反転させた部分確定が red** になる
- [ ] **契約検査と結果検査が分離**され、既存 runner が green のまま**サーバー経路の欠落は red**
- [ ] **P5 の値関係**(先着/後着の D5 同一・内容差異・未使用性)が実行時検査され、**両分岐が別資産で固定**されている
- [ ] **注入点の 18 組と P3 の 3 注入点が閉じ**、無効な値・組合せが red
- [ ] **故障注入が複数 `case` 構造**で、**`⋃ 宣言 case = 18 組`**・**トランザクション外 = 3 点**が exact-set で照合される
- [ ] **5 つの exact-set**(母集合 / 観点被覆のペア / 未作成繰り延べ / runner 繰り延べ / 注入被覆 2 種)が宣言され、**どれも 1 件消すと red**。**2 つの繰り延べ表は交差が空**
- [ ] **観点 22 種と scenarioId 26 件の 26 ペア**が、10-2 の `(d)` 表の全行と対応している((c) の 2 行を含めない)
- [ ] **シナリオ資産 10 件**が存在し契約検査を通る
- [ ] **`backend/` を 1 行も変更していない**・**正本 `docs/design/sync-protocol.md` を 1 行も変更していない**
- [ ] **新規 5 パスが `paths` に、新規 2 パスが `guard_paths` に**登録されている
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
| **(d) 故障系** | **契約・注入点・資産 10 件を足す。runner は TSK-330 へ送る** | 共通 10 件 / `tElementCommitment` / `schemaVersion: 2` / 契約検査と結果検査の分離 / P5 の値関係 / 18 組 / 故障注入の `case` 構造 / **5 つの exact-set** |

### ランナー別

| 層 | 追加するテスト |
| --- | --- |
| **Vitest**(`frontend/`) | ステップ 1: reader/parser 一致 + 変異 5 件以上 / ステップ 2: 段階の単体テスト + **スナップショット↔TS 照合**(1 行変異で red)/ ステップ 3: `RG1` の逐語照合 + 変異 / **ステップ 4: 判定不能の経路別変異(D1 → `B3b` / P3 → `B13`)・複数一致が混ざらないことの検査** / ステップ 5: 経路別省略可否の変異・`schemaVersion` の組の変異・**部分確定の変異**・**既存 runner が green のままであること** / ステップ 6: P5 の値関係変異・注入点の無効値と無効組合せ / ステップ 7・8: 4 つの exact-set 変異 + 資産の契約検査 |
| **pytest**(ルート) | **`tests/test_check_processing_stages.py`(新規)** — 正本 6-2 ↔ スナップショットの照合と、**正本 1 行変異で red** になること。`test_core_guard.py` に**新規 5 パス(`paths`)+ 2 パス(`guard_paths`)**を登録 |
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
