---
feature: sync-server-apply
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。ラッパーの implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— ラッパーが「済」でないと実行を拒否する
重さ分類: コア領域          # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3d293b75e687816a8c45e921b998da75
branch: feature/sync-server-apply
created: 2026-09-07
計画レビュー周回: 6        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: 同期プロトコル — 6 章のオラクル固定と D5 分類の正本是正(後続 γ)

## 1. 背景・目的

Notion タスク: [TSK-321](https://app.notion.com/p/3d293b75e687816a8c45e921b998da75)(TSK-280 の `/pr` クローズ処理で 2026-09-04 に起票)

TSK-280(イベント契約)が `DI1`・`DI5`・`I1`・`B3a` を「6 章の処理段階に依存する」として
**理由つき allow-list で除外**し(`frontend/src/lib/sync/canonOracle.ts:480-511`)、
後続 α(TSK-319)が「6 章の処理段階 / 8 章」を、後続 β(TSK-320)が「サーバー実装」を、
それぞれ後続 γ へ送った。本タスクはその受け皿である。

**射程は計画レビュー 5 周の結果、人間の裁定で分割された**(4 節の裁定 10)。
本タスクは **6 章のオラクル固定と D5 分類の正本是正**に限定し、
**`NFR-019(d)` の故障系契約と資産は [TSK-332](https://app.notion.com/p/3d493b75e687816eb9fbd19dda889d5e) へ**、
**実行検証と backend 実装は [TSK-330](https://app.notion.com/p/3d493b75e68781ce8417d9ed882ece5b) へ**送る。

正本: `docs/design/sync-protocol.md`(**v0.3 approved・2026-09-07**)の
**4-5**(D5 衝突規則)・**6-2**(処理段階)・**6-3**(境界結果)・**8-1**(経路表)。

対応する要件:

- [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012) — 「べき等キーの記録・イベント保存・prefix 更新・状態遷移が**単一の DB トランザクションで確定する**」/ 改訂・墓標・記録権拒否の別カテゴリ
- [FR-013](../../requirements/requirements-pitchlog-2026-07-22.md#FR-013) — 記録権のない端末のイベントをサーバーが拒否する(`P4` / `B4`)
- [FR-034](../../requirements/requirements-pitchlog-2026-07-22.md#FR-034) / [NFR-010](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-010) — 「内容・存在が応答から判別できない」(**段階順序「③認可 < ④D5」の根拠**)
- [NFR-018](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-018) — **ドメイン計算の単一実装**。D5 分類を再実装しない

調査の正: [research.md](research.md)。詳細設計: [design.md](design.md)。

**目的**: 4-5・6 章・8-1 を**機械が読める形へ固定**し、**既存実装が正本 4-5 から乖離している箇所を是正**する。

## 2. スコープ

### やること

1. **`R-TXN-ROUTE` の reader 新設** — 8-1 の経路表(`P1`〜`P5`)と T 要素(`T1`〜`T9`)の 14 要素。
   **TSK-332 が使う 18 組の `(経路, T 要素)` の唯一の出所**になる
2. **6-2 の処理段階の語彙と順序不変条件** + **2 層の正本ドリフト検査**
3. **`RG1` 共通前段ゲート**
4. **既存 D5 分類器を正本 4-5 へ是正** — 判定不能・比較例外を経路別に `B3b`/`B13` へ。**複数一致は専用例外の送出へ一意化**(`IdempotencyDecisionResult` では表現できなくする)
5. **allow-list から実装済みへの移動 6 ID** — `DI1`・`DI4`・`I1`・`I4`・`RG1`・`B3b`

### やらないこと(受け取り先つき)

| 項目 | 受け取り先 | 理由 |
| --- | --- | --- |
| **`NFR-019(d)` の故障系契約の再設計とシナリオ資産 10 件** | **[TSK-332](https://app.notion.com/p/3d493b75e687816eb9fbd19dda889d5e)** — 起票済み | **計画レビュー 4・5 周目の指摘が全件この領域に集中**し、契約スキーマの詳細設計(`caseId`・到達不能の判別子・被覆のペア集合化)に入った。**人間の裁定 10 で分割**。設計の蓄積は [design.md](design.md) の **3 章・6 章**にあり、そのまま引き継ぐ |
| **全シナリオの runner**(実行検証)+ **`backend/` 実装** + **8 章の適用実装** | **[TSK-330(後続 γ')](https://app.notion.com/p/3d493b75e68781ce8417d9ed882ece5b)** — 起票済み・**開始条件は TSK-250 の完了** | `backend/` は `GET /health` の 11 行のみで DDL・マイグレーション・ORM が皆無 |
| **`DI5`(混在バッチの A5)と A5 の停止境界** | **TSK-330**(**`U-14` の解決後**) | **外部境界結果を返すには「保存済み退避の再掲を `B1` と `B4` のどちらにするか」を決める必要があり、それがまさに `U-14`**(裁定 8) |
| **`B3a`(= `P5 + T9`)** | **TSK-330** | 正本の帰結が**不可分な `P5 + T9`**(`:1248`・`:1209`)。allow-list から外すと機械上は全体が実装済みに見える |
| **`T9` の保存 / `T7` の無効化意図の保存・配信 / `I5`・`I6`** | **TSK-330** | いずれも永続化を伴う |
| **wire 形式・プロパティ名・JSON / API スキーマ** | **[TSK-331](https://app.notion.com/p/3d493b75e687811bb75de7d0f366cc9d)** — 起票済み | 要件書に要求が一切無く、置き場も未決 |
| **`U-13`・`U-14`** | **TSK-329** | v0.1 由来の既存欠陥。**`U-14` は `DI5` の前提** |
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
| `docs/development/harness-evaluation.md` | **`## 候補` へ 2 件**: ① **ハーネス設計書の `contracts/` 記述の揺れ**(`:181` は OpenAPI を含む / `:198` は NFR-019a のベクタに限定。10-3 と `ADR-003 D-1-b` は後者を援用 — TSK-331 の置き場裁定に直撃)② **正本由来の橋渡し資産を既存フィルタ外へ新設すると、正本と同時変更したときに frontend ジョブが起動しない**(`ci.yml:124-130` の filters は `frontend/**`・`contracts/**`・**`scripts/design_relations/sync-protocol.json`** を列挙する**個別列挙方式**。**既存の 3 資産は既に載っている**が、新しい橋渡し資産を足すたびに `ci.yml`〔`guard_paths`〕の更新が要り、漏らすと黙ってすり抜ける)。変更履歴表へ 1 行(**`H-*` の新規採番なし・版は上げない**) | **PR レビュー** |
| `docs/README.md` | 台帳行の最終更新日を現行化 | **PR レビュー** |

**台帳と索引の更新は `/pr` のクローズ処理で行う**。**実装ステップ表には置かない**
(クローズ処理はステップ表の外側にある — 設計書 6.1)。
**同一コミットの対象は②台帳・③変更履歴表・④索引**であり、**①計画書 3 節への宣言はその前に完了させる**
(pr スキル手順 1-3)。**本計画の改訂で①は完了済み**。

### 正本体系外だが同一 PR で更新するもの

| 対象 | 変更内容 |
| --- | --- |
| `frontend/src/lib/sync/canonOracle.ts` | `R-TXN-ROUTE` の専用パーサと reader / allow-list の用途別分割と **6 ID の移動** |
| `frontend/src/lib/sync/idempotencyCollision.ts` +`.spec.ts` | **判定不能・比較例外を経路別に `B3b`/`B13` へ是正** / **複数一致を専用例外の送出へ一意化**(正本 4-5 との乖離の解消) |
| `frontend/src/lib/sync/processingStages.ts` +`.spec.ts`(新規) | 6-2 の処理段階・順序不変条件・スナップショット照合 |
| `frontend/src/lib/sync/processingStages.snapshot.json`(新規) | **6-2 の段階表のスナップショット**。**`frontend/` 配下に置き、既存の `frontend/**` フィルタで Vitest が起動するようにする**(裁定 9) |
| `frontend/src/lib/sync/restoreAdjustmentGate.ts` +`.spec.ts`(新規) | `RG1` 共通前段ゲート |
| `frontend/src/lib/sync/prohibitions.spec.ts` | **3 つの exact-set** の追随 |
| `scripts/check_processing_stages.py` + `tests/test_check_processing_stages.py`(新規) | **harness(常時実行)で正本 6-2 ↔ スナップショットを照合** |
| `.claude/core-areas.json` / `tests/test_core_guard.py` | **新規ファイル 5 件**(2 モジュール + 各 spec + スナップショット)を `sync-protocol` の `paths` へ。**あわせて重複帰属を登録** — `processingStages.ts`・`.spec.ts`・`.snapshot.json` は**認可順序(③認可 < ④D5)を固定するので `tenant-isolation` にも、記録権照合の段階⑤を含むので `recording-rights` にも**、`restoreAdjustmentGate.ts`・`.spec.ts` は**新 D4 の開始境界を扱うので `recording-rights` にも**登録する。**新規検査器 2 パス**を `guard_paths` へ。`test_core_guard.py` の**各 area の期待集合も追随**させる |

**`failureScenarioContract.ts` / `failureScenarioAdapter.ts` / `tests/fixtures/sync-protocol-failures/` は
本タスクでは 1 行も変更しない**(TSK-332 の射程)。

## 4. 実装方針

### 重さ分類 = コア領域(根拠)

`.claude/core-areas.json` の `sync-protocol` 領域に `frontend/src/lib/sync/**`(製品と spec を**個別に**列挙)と
`docs/design/sync-protocol.md` が登録されており、本タスクの主対象がそこに含まれる。
`game-state` / `recording-rights` / `tenant-isolation` にも重複帰属する。
→ **`sol xhigh`・敵対レビュー必須・人間の逐行確認必須(PR 作成者以外)**。

**本タスクは既存のコア領域コード(`idempotencyCollision.ts`)の振る舞いを変更する**(正本 4-5 への是正)。
逐行確認の優先度で最上位に置く。

### 機構の詳細設計

[design.md](design.md) へ分離した(内容を本節へ複製しない):

- **1 章** `R-TXN-ROUTE` 専用パーサ / **2 章** allow-list の用途別分割
- **4 章** D5 分類の正本 4-5 への是正 / **5 章** 2 層のドリフト検査 / **7 章** 新規資産の登録先
- **3 章・6 章は本タスクの射程外**(TSK-332 への申し送り — 5 周分のレビュー知見を保存してある)

### 人間の裁定

| # | 論点 | 裁定 | 周 |
| --- | --- | --- | --- |
| 1 | 射程 | 案 A: 契約・オラクル・注入点の固定に限定 | 着手時 |
| 2 | 6-2 の関係化 | 登録しない(正本を改訂しない) | 着手時 |
| 3 | `U-13`・`U-14` | γ の射程外 | 着手時 |
| 4 | wire スキーマ | 含めない → TSK-331 | 着手時 |
| 5 | 期待フィールド | 条件付き必須へ(→ 1 周目で共通 9 件へ是正)| 着手時 |
| 6 | `DI5`・`B3b` | 両方やる(→ **裁定 8 で `DI5` を部分撤回**) | 2 |
| 7 | ドリフト検査の置き場 | **2 層**(harness の Python / Vitest) | 2 |
| 8 | `U-14` との衝突 | **`DI5` を射程外へ戻す** | 3 |
| 9 | スナップショットの置き場 | **`frontend/` 配下** | 3 |
| **10** | **打ち切り** | **射程を分割** — ステップ 1〜4 を γ とし、**故障系契約と資産を TSK-332 へ**。4 周目以降の指摘が全件そこに集中し、ステップ 1〜4 は 2 周連続で無傷だった | 5 |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

合格条件は **`[機械]`** と **`[手動]`** に書き分ける。**`[手動]` を機械 green に数えない。**

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **`R-TXN-ROUTE` の専用パーサと reader**(`canonOracle.ts`)。経路行 = `:` 1 個 + `=` 1 個 + `,` split、T 要素行 = `:` 1 個かつ **`=` を明示的に禁止**。2 つの exact-set 照合(関係全体 = 14 / 経路が参照する T の和集合 = 9)。**経路 → T 集合の写像を公開**する(TSK-332 が 18 組の出所として使う) | `[機械]` `pnpm test` green / **変異 5 件以上**(未知 ID・T 行に `=` 混入・経路行から `=` 欠落・参照 T 欠落・ID 重複)/ `prohibitions.spec.ts` の 3 exact-set 追随 / `[手動]` 14 要素が正本 8-1 と逐語一致 |
| 2 | **`processingStages.ts`(新規)+ スナップショット + 2 層ドリフト検査 + `DI1`・`DI4`・`I1`・`I4` を実装済みへ**。スナップショットを **`frontend/src/lib/sync/processingStages.snapshot.json`** に置き、**harness の `check_processing_stages.py` が正本 6-2 の 2 表と逐語照合**、**Vitest がスナップショットと TS 実装を照合**する | `[機械]` 全 green / **正本 6-2 を 1 行変えると harness の検査が red** / **スナップショットを 1 行変えると Vitest が red** / **同時に変えてもスナップショットが `frontend/**` に当たり Vitest が起動する** / `EXPECTED = 実装済み ∪ 射程外` の総和が不変 / **`sync-protocol` の `paths` に 3 パス・`guard_paths` に 2 パスを登録し、同じ 3 パスを `tenant-isolation` と `recording-rights` にも重複登録**(`test_core_guard.py` の各 area 期待集合も追随)/ `[手動]` 9 段階 + 11 段階の逐行確認 |
| 3 | **`restoreAdjustmentGate.ts`(新規)+ `RG1` を両関係で実装済みへ**。右辺 10 節(③認可後 / D5 照合前 / 全通常書き込み・内部ジョブ停止 / P1・P2・P4 は `B7` / P3 は `B10` / D5 消費なし / コミット直前再検証 / サービス再開 fail-closed / 解除・新 D4 開始不可分 / 復旧制御面だけ許可)を逐語固定 | `[機械]` 全 green / 右辺 10 節が正本 `:768` と逐語一致 / **`R-P3-BOUNDARY` の allow-list 先頭 `変更受理` を動かしていない**(`CANON_P3_ACCEPTED_RESULT_ID` の添字 0 依存)/ **`sync-protocol` の `paths` に 2 パス登録し、同じ 2 パスを `recording-rights` にも重複登録**(`test_core_guard.py` も追随)/ `[手動]` fail-closed の向きが**止める側**に倒れている |
| 4 | **既存 D5 分類器を正本 4-5 へ是正 + `B3b` を実装済みへ**。① **判定不能・比較例外を経路別に `B3b`/`B13`** へ写像(正本 `:404`)② **複数一致は「一意な先着原本が無い破損」として専用例外(例: `IdempotencyCollisionCorruptionError`)の送出へ一意化**し、**`IdempotencyDecisionResult` の値としては表現できなくする** | `[機械]` 全 green / **正本 `:404` どおり D1 付き経路 = `B3b`・P3 = `B13`** / **両経路の変異試験** / **複数一致で当該例外が送出されることを厳密に検査**(現行の `REJECT_LATER` を返す実装では red になる — 「混ざらない」だけの条件はコードを変えなくても通ってしまうため)/ **複数一致時に内容同一性の判定器が呼ばれないことを検査** / 製品表と canon の突合で `B3b` の右辺が逐語一致 / `[手動・最重要]` **既存振る舞いの変更**なので逐行確認。**呼び出し元への波及を確認** |

**順序の根拠**: **ステップ 1 が先**。**経路 → T 集合の写像を使うのは TSK-332 であり、本タスクの
ステップ 2〜4 は使わない**が、TSK-332 との契約面を最初に確定させておく。
**ステップ 2・3・4 は相互に独立**で、この順序は依存ではなく**レビューしやすい粒度**による。

**確定ゲートは回さない**(正本を改訂しないため)。コミット件名には `(ステップ <k>/4)` をちょうど 1 個含める。

### 主要リスク

| # | リスク | 緩和 |
| --- | --- | --- |
| R1 | `parseCanonBoundaryResults` を流用すると **silent-pass** する(`=` を検査しないため T 集合が `name` に折り畳まれる) | ステップ 1 で専用パーサ。**T 行への `=` 混入変異**を合格条件に |
| R2 | **allow-list の移動を既存テストがほぼ検出しない**(`EXPECTED` が和集合のため。`canonOracle.spec.ts:543-562` も `:563-580` も偽 green) | 実効的に検出するのは `:509-518` の製品表突合 1 本だけ。**各ステップで製品表と canon の突合テストを必ず足す** |
| R3 | `prohibitions.spec.ts` の 3 exact-set 漏れで同ファイル 34 件が collection エラー | 各ステップの合格条件に明記。**型 export 0 件でも `[]` エントリが必須** |
| R4 | `CANON_P3_ACCEPTED_RESULT_ID` が allow-list の添字 0 に位置依存 | ステップ 3 で「先頭 `変更受理` を動かさない」 |
| R5 | `P4` の左辺と `T8` の body が前方一致し、変異テストが誤マッチする | **`startsWith(\`${id}:\`)`** で引き、`toBeGreaterThanOrEqual(0)` を先に主張 |
| R6 | **既存 D5 分類器の是正がコア領域の振る舞いを変える** | ステップ 4 を**逐行確認の最優先**に。両経路の変異試験と**呼び出し元への波及確認**を必須に |
| R9 | **正本と機械資産を同時変更すると CI をすり抜ける** | スナップショットを **`frontend/` 配下**に置き既存フィルタに載せる(裁定 9)。台帳の候補へも送る |

## 5. DoD(受け入れ基準)

- [ ] **`R-TXN-ROUTE` の 14 要素**が `canonOracle.ts` から読め、正本 8-1 と逐語一致する。**経路 → T 集合の写像が公開**され TSK-332 が使える
- [ ] **6-2 の処理段階**(D1 付き 9 段階・P3 11 段階)と順序不変条件が固定され、**正本を変えると harness が red**・**スナップショットを変えると Vitest が red**・**同時に変えても Vitest が起動する**
- [ ] **既存 D5 分類器の判定不能・比較例外が正本 4-5 どおり経路別に `B3b`/`B13`** を返し、**複数一致は専用例外へ一意化**されて `IdempotencyDecisionResult` では表現できない。**判定器が呼ばれないことも固定**されている
- [ ] **allow-list の 6 ID**(`DI1`・`DI4`・`I1`・`I4`・`RG1`・`B3b`)が実装済みへ移り右辺が逐語照合されている。**`B3a`・`DI5`・`I5`・`I6` は射程外に残り、理由が受け取り先(`DI5` は `U-14` 依存で TSK-330)を名指し**
- [ ] **`EXPECTED = 実装済み ∪ 射程外` の総和が不変**
- [ ] **`backend/` を 1 行も変更していない**・**正本 `docs/design/sync-protocol.md` を 1 行も変更していない**
- [ ] **`failureScenarioContract.ts` / `failureScenarioAdapter.ts` / `tests/fixtures/sync-protocol-failures/` を 1 行も変更していない**(TSK-332 の射程)
- [ ] **新規ファイル 5 件が `sync-protocol` の `paths` に、新規検査器 2 件が `guard_paths` に**登録され、**`processingStages` 系 3 件が `tenant-isolation`・`recording-rights` にも、`restoreAdjustmentGate` 系 2 件が `recording-rights` にも重複帰属**している(`test_core_guard.py` の各 area 期待集合も一致)
- [ ] **TSK-330・TSK-331・TSK-332 が起票され、本タスクと相互リンクされている**
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
| **(d) 故障系** | **足さない — TSK-332 へ送る** | 契約の再設計と資産 10 件は TSK-332。**本タスクは (d) の資産・契約に一切触れない** |

**本タスクが足すのは `NFR-019` のどの区分でもない「オラクルと正本の逐語照合」**である。
既存の `canonOracle.spec.ts` / `prohibitions.spec.ts` と同じ層で、**正本と実装の乖離を機械で防ぐ**ためのもの。

### ランナー別

| 層 | 追加するテスト |
| --- | --- |
| **Vitest**(`frontend/`) | ステップ 1: reader/parser 一致 + **変異 5 件以上** / ステップ 2: 段階の単体テスト + **スナップショット↔TS 照合**(1 行変異で red)/ ステップ 3: `RG1` の逐語照合 + 変異 / **ステップ 4: 判定不能の経路別変異(D1 → `B3b` / P3 → `B13`)・複数一致で専用例外が送出されること・判定器が呼ばれないこと・呼び出し元への波及** |
| **pytest**(ルート) | **`tests/test_check_processing_stages.py`(新規)** — 正本 6-2 ↔ スナップショットの照合と、**正本 1 行変異で red** になること。`test_core_guard.py` に**新規ファイル 5 件(`sync-protocol` の `paths`)+ 検査器 2 件(`guard_paths`)+ 重複帰属**(`tenant-isolation` へ 3 件・`recording-rights` へ 5 件)を登録 |
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
5. `uv run python scripts/feature_status.py` がステップ表を **4 本**として読む
6. `uv run python scripts/check_plan_docs_sync.py --plan docs/features/sync-server-apply/plan.md --base origin/develop` が rc=0
