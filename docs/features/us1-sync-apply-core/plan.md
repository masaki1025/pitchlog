---
feature: us1-sync-apply-core
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3da93b75e6878108a4c1e66253a25065
branch: feature/us1-sync-apply-core
created: 2026-10-08
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-S1 同期適用核(TSK-391)

## 1. 背景・目的

調査: [research.md](research.md) / 詳細設計: [design.md](design.md)

- Notion: [TSK-391 U-S1 同期適用核](https://app.notion.com/p/3da93b75e6878108a4c1e66253a25065)。出所は TSK-363 の単位分割(`docs/features/product-impl-unit-split/plan.md:205`)。帯 1(核)
- 主所有は [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012)(通信断耐性・同期)。関係する要件は NFR-007・NFR-010・NFR-015・NFR-019(d) と、[FR-013](../../requirements/requirements-pitchlog-2026-07-22.md#FR-013) の記録権拒否
- サーバー側で同期を適用する製品コードは、まだ 1 行もない。表・制約・トリガ・RLS はあるが、それを使って「重複到達しても二重適用しない」「欠落以降を適用しない」「べき等キー・イベント・prefix・状態遷移を単一トランザクションで確定する」(REQ:302-303)を実行する層がない(research C-1)
- **目的**: 同期プロトコル正本(`docs/design/sync-protocol.md` v0.4)の 6〜9 章のサーバー側を、経路 P1〜P5 の適用核として実装する。後で HTTP 入口から直接呼べるサービス層として作る

裁定(2026-10-08・人間。research.md 末尾):

| ID | 内容 |
| --- | --- |
| R-1 | U-S1 が TSK-330(8 章の適用実装と runner)を全部吸収する |
| R-2 | 記録権の判定(V12・D4・RG1・復旧世代)と状態遷移(T4・再計算)・内容検証は、注入境界で受ける。FR-012 は U-S1 では部分充足 |
| R-3 | HTTP 入口は開かない。入口は TSK-331 で wire 形式が決まった後に、別の小さな PR で開く |
| R-5 | UM01 の #95 の上に積む(起点 `3e19b295`)。実装の開始は #95 のマージ後 |

## 2. スコープ

### やること

1. 適用核のサービス層 `backend/src/pitchlog/sync/`(構成は [design.md 1 節](design.md#1-置き場とモジュール構成))
   - 段階③〜⑧の順序(SP 6-2)。③認可は UM01/U-T1 の `TenantContext` 束縛を使う
   - ④ D5 の内部分類 DI1〜DI5・I1〜I4
   - P1・P2: ⑥ D3+1 からの走査、T1・T2・T3・T4・T6、墓標(R3)・改訂(R4)、B2・B3b、A5 の合成、一時 ID 写像 C1〜C4
   - P2 の T5: O1(試合単位の直列化)・O2(局所再採番)・O4(同値停止)
   - P5 / T9(B3a)、P4 / T8(B4・退避)
   - P3: ③-b 復旧世代、B8〜B14、T7・I5(無効化意図)、I6 の `accepted_at`
   - ③-a RG1 と ⑧ のコミット直前再検証
   - クラッシュ注入点(テストからだけ有効化)
2. 注入境界 3 種(`RecordingRightsPort`・`ProjectionPort`・`ContentValidationPort`)の Protocol 定義([design.md 2 節](design.md#2-注入境界裁定-r-2))
3. 同期表 9 表の operation 登録(`backend/src/pitchlog/repositories/sync_apply.py`)
4. リポジトリ基底の拡張: 複合主キーによる UPDATE 条件と、行ロックの宣言([design.md 4 節](design.md#4-リポジトリ基底の拡張tenant-isolation-のコア))
5. TB002(条件 2)に同期核の所有パスを宣言し、そのパスに限って条件 2 を適用しない([design.md 5 節](design.md#5-tb002条件-2との衝突の解き方))
6. 原子性・再送・越境の DB テスト(pytest)
7. TSK-330 を受け取り先として書いている箇所を TSK-391 へ追随させる(`frontend/src/lib/sync/canonOracle.ts:493-515`・`canonOracle.spec.ts:685-688`・SP の受け取り先の記述)
8. core-areas.json に `backend/src/pitchlog/sync/*` と `repositories/sync_apply.py` を sync-protocol × recording-rights の重複帰属として登録する(宣言コミットと登録コミットの 2 段)

### やらないこと

- **HTTP 入口・wire 形式・API スキーマ**(R-3。TSK-331)。route_id の付与と 12-4 ゲートも入口 PR が持つ
- **記録権の判定の本物**(V12・D4・復旧世代・RG1 の状態)。U-R1(TSK-392)が `RecordingRightsPort` に差し込む
- **状態計算(投影・再計算・内容検証)の本物**。U-X1(凍結中)・U-G2 がポートに差し込む
- **クライアント側**(キュー・採番の不可分性・単一書き手・通知)。強制点はクライアントで、α・β で実装済み(SP:1401、DM:803-812)
- **(d) 故障系のシナリオ資産と契約の再設計**(TSK-332)。runner の扱いは 4 節の Q-1
- 通知の文面と契約(TSK-441)。U-1・U-2・RR-1 の 3 経路(TSK-267)
- `backend/src/pitchlog/db/` へのファイル追加と、表・列・マイグレーションの追加(`docs/features/product-impl-unit-split/plan.md:467`)
- 依存パッケージの追加

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/sync-protocol.md` | 受け取り先の記述「TSK-330」を TSK-391 へ追随させる(11-4 節ほか。意味規則は変えない)+ 変更履歴に 1 行 | PR レビュー(実装追随の節更新) |
| `contracts/tenant_boundary/base-allowlist.json`(凍結資産) | 条件 2 に同期核の所有パスの宣言を足す。凍結基準の履歴追記を伴う | PR レビュー + 敵対レビュー + 人間承認(コア) |
| `contracts/tenant_boundary/repository-contract.json`(凍結資産) | 複合主キー UPDATE と行ロックの登録形式を足す | 同上 |
| `.claude/core-areas.json` | `backend/src/pitchlog/sync/*`・`backend/src/pitchlog/repositories/sync_apply.py` を sync-protocol と recording-rights の両方に登録する | 敵対レビュー + 人間承認(6.3 規則⑤) |
| 要件書・data-model.md・ADR | **反映なし**。意味規則と物理写像は変えない | — |
| `docs/README.md` | **反映なし**(新しい正本を作らない) | — |

## 4. 実装方針

**重さ分類 = コア領域**。根拠: U-S1 は sync-protocol × recording-rights の重複帰属(`docs/features/product-impl-unit-split/design.md:101`、ハーネス設計書 6.3-③)。加えて、ステップ 1・2 は tenant-isolation の凍結資産(`contracts/tenant_boundary/*`)と repositories の基底に触れる。**触れるコア領域は 3 つ**(sync-protocol・recording-rights・tenant-isolation)。全ステップで敵対レビューと人間の逐行確認を受ける。

設計の詳細は [design.md](design.md)。要点:

- 1 イベント = 1 トランザクション(design.md 3 節)。ACK は確定の後に組み立てる
- 判定の所有者が別単位のものは、ポートで受ける。製品コードに既定実装を置かない(fail-closed)
- 正本の規則 ID(DI1・R3・O1・T9 など)を、実装関数の docstring とテスト名に書き、追跡できるようにする

**開始条件**: #95(UM01)のマージ。ステップ 1・2 は #95 が入れた書き込み経路の上で作る。

**計画レビューで確認する論点**(design.md 7 節):

| ID | 論点 |
| --- | --- |
| Q-1 | TSK-330 の runner は TSK-332 の資産に依存する。U-S1 はクラッシュ注入の pytest までとし、runner は TSK-332 と同じ射程で作る案。**人間の確認が必要**(R-1「全部吸収」との関係) |
| Q-2 | サーバー側の D5 分類・処理段階の Python 実装が、frontend の TS 実装に対する NFR-018 のコピー実装に当たるか |
| Q-3 | O1 の直列化を、試合行の `SELECT ... FOR UPDATE` で行う案 |
| Q-4 | 内容同一性を `source_fingerprint`(正規化 JSON の全フィールド)で判定する案 |
| Q-5 | 改訂版と通常版を区別する列がない(TSK-373)。U-S1 では列を足さない |
| Q-6 | D3 = `confirmed_watermark` とする案。`applied_prefix` の意味の確定 |
| Q-7 | RG1 の所有者を `RecordingRightsPort` に含める案 |

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **TB002 の所有パス宣言**: 条件 2 に同期核の所有パス(`backend/src/pitchlog/sync/**`・`backend/src/pitchlog/repositories/sync_apply.py`)を宣言する機構を、base-allowlist と検査器に足す。凍結基準の履歴を追記する | 所有パス内の同期語彙が TB002 にならない(正例)。所有パス外(例: `repositories/roster.py`)の同期語彙は従来どおり TB002 になる(負例)。条件 1・3・4・5 は所有パス内でも効く(負例 3 件)。`tests/` の迂回検査テストが green |
| 2 | **リポジトリ基底の拡張**: 複合主キーによる UPDATE 条件と、行ロック(`FOR UPDATE`)の宣言を登録形式へ足す。repository-contract を改訂する | 複合主キーの全列を束縛しない UPDATE が登録時に拒否される(負例)。`FOR UPDATE` を宣言していない文はロックを取らない。既存の roster の operation が変わらず green。`backend/tests/conftest.py` の差分 0 行 |
| 3 | **型とポート**: `sync/model.py`(要求・A5・B1〜B14・ACK 結果)と `sync/ports.py`(3 ポート)。テスト用の合成実装を `backend/tests/` に置く | 型の単体テストが green。製品コードにポートの既定実装がない(静的検査)。`ruff`・`ty` green |
| 4 | **同期表の operation 登録**: `repositories/sync_apply.py` に 9 表の read/insert/update を登録する | 全 operation が登録時の検査(テナント列・capability 一致・UPDATE の行識別)を通る。2 テナントの越境テスト(他テナント行を読めない・書けない)が green |
| 5 | **④ D5 の内部分類**: `sync/idempotency.py`(DI1〜DI5・I1〜I4)と内容同一性の判定(Q-4) | 既存同一内容 → 保存済み結果候補、既存異内容 → B3b / B13 候補、未使用 → 後段候補の 3 分類を DB テストで確認。**他テナントの同じ D5 は未使用として扱われ、存在が判別できない**(越境)。分類の段階では書き込まない |
| 6 | **P1 の適用**: `sync/prefix_path.py`。⑥ D3+1 からの走査、T1・T2・T3・T4(ポート)・T6、墓標で前進(R3)、改訂で水位を戻さない(R4)、B2(gap 以降は保存しない・R5)、B3b、A5 の合成、一時 ID 写像 C1〜C4 | SP 6-3 の例(D3 = 4・D1 = 5 欠落・D1 = 6 未使用・D1 = 7 既存異内容 → B2・D1 6 と 7 は未処理)が DB テストで再現する。墓標で D3 が前進し、改訂で戻らない。ACK 消失後の再送で同じ結果が再掲され、二重適用も選手 ID の重複生成も起きない |
| 7 | **P2 の T5**: `sync/ordering.py`。O1 の直列化(Q-3)・O2 の局所再採番・O4 の同値停止 | 同じ試合への並行 2 トランザクションで D2 が重複しない(DB テスト)。隙間枯渇時に局所再採番と新イベントの保存が同じトランザクションで確定する。O4 で B3 と A5「拒否」を返し、投影を止める |
| 8 | **P5 / T9 と P4 / T8**: `sync/rejection.py`。B3a で拒否原本・D5・拒否結果・理由を一体で保存し D3 を進めない。B4 で退避原本と A5「退避」を保存してから応答する | 同じ `(D4, D1, D5)` の再送に同じ拒否結果と理由が返る。既存 D5 との衝突では T9 を開始しない。保存済みの退避結果は、現在の記録権によらず再掲される(引き継ぎ後の再送) |
| 9 | **P3**: `sync/change_path.py`。③-b 復旧世代(B9)、④ D5(B13)、⑤ V12(進行中だけ)、⑥ 内容(B14・ポート)、⑦ V11(B8)、T7 と I5 の無効化意図(安定 ID で 1 件)、I6 の `accepted_at` | B8〜B14 の各分岐が DB テストで再現する。保存済み結果の再掲で無効化意図を重複作成しない。終了後の P3 では V12 を照合しない |
| 10 | **RG1 とコミット直前再検証**: `sync/gate.py`。③-a で止め、⑧ でも再検証する | 復元調整中なら P1・P2・P4 は B7、P3 は B10 で、D5 を消費しない。③-a 通過後に復元調整へ移ったら、⑧ で全ロールバックする(DB テスト) |
| 11 | **公開入口とクラッシュ注入**: `sync/apply.py`(段階の順序の固定)と `sync/crash_points.py`。経路ごとに T 要素間へ注入するテスト | P1〜P5 の各経路で、どの T 要素の間に注入しても「全部確定か全部未確定か」になる(DB テスト)。段階の順序を入れ替えると落ちるテストがある。他テナントの試合への要求は B6 で、D5・記録権・連番の状態が応答に現れない |
| 12 | **TSK-330 参照の追随**: `canonOracle.ts`・`canonOracle.spec.ts` の受け取り先文字列と、SP の受け取り先の記述(+ 変更履歴) | `pnpm test` の該当 spec と `check_design_propagation.py` が green。SP の意味規則の行に差分がない |
| 13 | **core-areas の宣言**: `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` に、sync-protocol と recording-rights への追加分を宣言する(窓口が空いていることを 469 master と確認してから) | `tests/test_core_guard.py` が green。宣言と JSON を同じコミットで変えていない |
| 14 | **core-areas の登録**: `.claude/core-areas.json` に登録し、`test_core_guard.py` の期待集合を追随させる | core-guard の CI 相当が green。新しいパスが 2 領域の両方に一致する(重複帰属の明示) |

## 5. DoD(受け入れ基準)

Notion カードの DoD と対応づける。カードの文言と食い違う 1 項目は、カードを直す(下記)。

- [ ] 段階③〜⑧の順序と P1〜P5 の T 要素の集合が、DB テストで固定されている(ステップ 6〜11)
- [ ] 再送・競合の故障系テスト: ACK 消失後の再送、引き継ぎ後の再送、並行トランザクションの D2、クラッシュ注入(カード「再送・競合の故障系テスト」)
- [ ] **NFR-018 のコピー実装を作らない**: ドメイン計算(状態遷移・内容検証)はポートで受け、適用核に書かない。Q-2 の結論を計画レビューで得ている
- [ ] **core-areas.json への paths 登録を本 PR で行う**。**重複帰属(sync-protocol × recording-rights)を登録時に明示する**(ステップ 13・14)
- [ ] **`backend/tests/conftest.py` の差分が 0 行**
- [ ] `backend/src/pitchlog/db/` にファイルを足していない。依存パッケージを足していない
- [ ] pytest / ruff / ty green。frontend の該当 spec green
- [ ] 横断要求: 物理削除しない(墓標はイベントの追加・改訂は旧版を残す)/ テナント分離(越境テスト)/ 利用者 ID を持たない
- [ ] 緑を「FR-012 充足」と報告しない。FR-012 は、ポートの本物(U-R1・U-X1)が入るまで部分充足

**カードの修正(人間へ上げる)**: カードの「ゴールデンベクタ(`contracts/`)との一致」は対象が存在しない。同期の故障系テストの置き場は `tests/fixtures/sync-protocol-failures/`(SP:1712)で、`contracts/` は NFR-019(a) 専用(`contracts/README.md:3`)。本 PR では「段階・経路の DB テスト」に読み替え、シナリオ資産は TSK-332 に残す。

## 6. テスト計画

| NFR-019 の種別 | 足すもの | 置き場 |
| --- | --- | --- |
| 単体 | 型・ポート・D5 分類・A5 合成の純粋関数 | `backend/tests/test_sync_apply_*.py` |
| 越境 | 他テナントの同じ D5 が未使用扱いになり存在が判別できない、他テナントの試合は B6、9 表の operation が他テナント行を読めない・書けない | `backend/tests/db/test_sync_apply_*_boundary.py`(DB) |
| 故障系 (d) | クラッシュ注入(P1〜P5 × T 要素間)、ACK 消失後の再送、引き継ぎ後の再送、並行 D2、RG1 のコミット直前ロールバック | `backend/tests/db/test_sync_apply_*.py`(DB。pytest で直接書く。シナリオ資産化は TSK-332) |
| 一致性 (a) | **対象外**。同期は NFR-018 の対象列挙に入っていない(REQ:892) | — |
| E2E (c) | **対象外**。入口を開かないため(R-3)。入口 PR で足す | — |

- DB テストは `backend/tests/db/` の既存 fixture(`disposable_postgres_cluster`・`provisioned_product_catalog`)を使い、conftest は変えない。前例は `backend/tests/db/test_tenant_transaction_scope.py`(fixture の上書きと registry の monkeypatch)
- 検証はステップごとに影響範囲だけを回す。ステップ 14 の後に非 DB の全件を 1 回回し、DB の全件は CI に任せる
