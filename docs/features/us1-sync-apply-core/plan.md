---
feature: us1-sync-apply-core
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3da93b75e6878108a4c1e66253a25065
branch: feature/us1-sync-apply-core
created: 2026-10-08
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-S1 同期適用核(TSK-391)

## 1. 背景・目的

調査: [research.md](research.md)(スパイクの結果を含む)/ 詳細設計: [design.md](design.md)

- Notion: [TSK-391 U-S1 同期適用核](https://app.notion.com/p/3da93b75e6878108a4c1e66253a25065)。出所は TSK-363 の単位分割(`docs/features/product-impl-unit-split/plan.md:205`)。帯 1(核)
- 主所有は [FR-012](../../requirements/requirements-pitchlog-2026-07-22.md#FR-012)(通信断耐性・同期)。関係する要件は NFR-007・NFR-010・NFR-015・NFR-019(d) と、[FR-013](../../requirements/requirements-pitchlog-2026-07-22.md#FR-013) の記録権拒否
- サーバー側で同期を適用する製品コードは、まだ 1 行もない。表・制約・トリガ・RLS はあるが、それを使って「重複到達しても二重適用しない」「欠落以降を適用しない」「べき等キー・イベント・prefix・状態遷移を単一トランザクションで確定する」(REQ:302-303)を実行する層がない(research C-1)
- **目的**: 同期プロトコル正本(`docs/design/sync-protocol.md` v0.4)の 6〜9 章のサーバー側を、経路 P1〜P5 の適用核として実装する。あわせて NFR-019(d) の故障系テスト資産の契約を作り直し、適用核をその資産で実行検証する

裁定(2026-10-08・人間。research.md 末尾):

| ID | 内容 |
| --- | --- |
| R-1 | U-S1 が TSK-330(8 章の適用実装と runner)を吸収する |
| R-2 | 記録権の判定(V12・D4・RG1・復旧世代)と状態遷移(T4)・内容検証は、注入境界で受ける。FR-012 は U-S1 では部分充足 |
| R-3 | HTTP 入口は開かない。入口は TSK-331 で wire 形式が決まった後に、別の小さな PR で開く |
| R-5 | UM01 の #95 の上に積む(起点 `3e19b295`)。実装の開始は #95 のマージ後 |
| R-9 | **U-S1 が TSK-332(NFR-019(d) の資産契約の再設計とシナリオ資産)も吸収する**。スパイク(`feature/us1-sync-spike`)で資産の実際の形が見えたため |

## 2. スコープ

### やること

1. 適用核のサービス層 `backend/src/pitchlog/sync/`(構成は [design.md 1 節](design.md#1-置き場とモジュール構成))
   - 段階③〜⑧の順序(SP 6-2)。③認可は U-T1 の `TenantContext` 束縛を使う
   - ④ D5 の内部分類 DI1〜DI5・I1〜I4 と、イベントのトランザクション内での再照合([design.md 3 節](design.md#3-トランザクションの単位と-d5-の再照合スパイク-s-1s-5))
   - P1・P2: ⑥ D3+1 からの走査、T1+T6・T2・T3・T4、墓標(R3)・改訂(R4)、B2・B3b、一時 ID 写像 C1〜C4
   - P2 の T5: O1・O2・O4
   - P5 / T9(B3a・B3b)、P4 / T8(B4・退避)
   - P3: ③-b 復旧世代、B8〜B14、T7・I5(無効化意図の保存と配信・冪等な再試行)、I6 の `accepted_at`
   - ③-a RG1 と ⑧ のコミット直前再検証(同期経路の範囲)
   - 公開入口: D1 昇順の外部結果の確定、DI5 の混在バッチ、ACK の合成、名前付きのクラッシュ注入点
2. 注入境界 4 種と、ポートの拘束([design.md 2 節](design.md#2-注入境界とポートの拘束裁定-r-2スパイク-s-2))
3. リポジトリ基底の拡張: 複合主キーの UPDATE・行ロック・JSONB の結果の実体化・registry を複数モジュールから集める形・適用中に新しいスコープを開けない検査([design.md 4 節](design.md#4-リポジトリ基底の拡張tenant-isolation-のコアスパイク-s-3))
4. 同期表 9 表の operation 登録(`backend/src/pitchlog/repositories/sync_apply.py`)と registry への接続
5. TB002(条件 2)の所有パス。core-areas.json の sync-protocol の paths と機械で結ぶ([design.md 5 節](design.md#5-tb002条件-2との衝突の解き方))
6. **NFR-019(d) の資産契約の再設計**(TSK-332 の吸収。[design.md 7 節](design.md#7-nfr-019d-の資産契約tsk-332-の吸収スパイク-s-4)): 構造の改訂、契約検査と結果検査の分離、既存 4 資産の版移行と frontend の消費側の追随、新規資産 10 件
7. **サーバー側の (d) runner**(pytest): 資産を読み、適用核に注入して DB を観測する
8. core-areas.json への登録(宣言と登録の 2 段)
9. TSK-330・TSK-332 を受け取り先として書いている箇所を TSK-391 へ追随させる(`frontend/src/lib/sync/canonOracle.ts:493-515`・`canonOracle.spec.ts:685-688`・`idempotencyCollision.ts:3`)

### やらないこと

- **HTTP 入口・wire 形式・API スキーマ**(R-3。TSK-331)。route_id の付与と 12-4 ゲートも入口 PR が持つ。**B5・B11(認証失効)は入口がないと発生しないので、入口 PR へ送る**
- **記録権の判定の本物**(V12・D4・復旧世代・RG1 の状態)。U-R1(TSK-392)が `RecordingRightsPort` に差し込む
- **状態計算(投影・再計算・内容検証)の本物**。U-X1(凍結中)・U-G2 がポートに差し込む
- **復元ライフサイクルの故障シナリオ 12 本**(`docs/features/sync-server-apply/design.md:392-405`)と、**RG1 による同期以外の変更経路の停止**。記録権・復元の状態が U-S1 の外にあるため。送り先は 4 節の Q-9(人間の確認が必要)
- **クライアント側の実装**(キュー・採番の不可分性・単一書き手・通知)。強制点はクライアントで、実装済み(SP:1401、DM:803-812)。ただし (d) 資産の版移行に伴う frontend の消費側の追随はやる
- I5 の配信先の本物(キャッシュ層)。通知の文面と契約(TSK-441)。U-1・U-2・RR-1 の 3 経路(TSK-267)
- `backend/src/pitchlog/db/` へのファイル追加と、表・列・マイグレーションの追加(`docs/features/product-impl-unit-split/plan.md:467`)。依存パッケージの追加

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/design/sync-protocol.md` | **反映なし**(意味規則を変えない。「TSK-330」の記述は本文にない — 計画レビュー 1 周目 P2-2)。ただし (d) 資産の `cases` 構造が 10-3 と食い違う場合は改訂が要る(Q-8) | Q-8 の結論しだいで finalize-doc |
| `contracts/tenant_boundary/base-allowlist.json`(凍結資産) | 条件 2 に同期核の所有パスを足す。凍結基準の履歴追記を伴う | PR レビュー + 敵対レビュー + 人間承認(コア) |
| `contracts/tenant_boundary/repository-contract.json`(凍結資産) | 複合主キー UPDATE・行ロック・JSONB 結果・registry の集約・同期の capability と token を足す | 同上 |
| `.claude/core-areas.json` | `backend/src/pitchlog/sync/*`・`backend/src/pitchlog/repositories/sync_apply.py`・`backend/tests/test_sync_apply_*.py` を sync-protocol と recording-rights の両方に登録する | 敵対レビュー + 人間承認(6.3 規則⑤) |
| 要件書・data-model.md・ADR・`docs/README.md` | **反映なし** | — |

## 4. 実装方針

**重さ分類 = コア領域**。根拠: U-S1 は sync-protocol × recording-rights の重複帰属(`docs/features/product-impl-unit-split/design.md:101`、ハーネス設計書 6.3-③)。ステップ 3・4 は tenant-isolation の凍結資産と repositories の基底に触れる。**触れるコア領域は 3 つ**(sync-protocol・recording-rights・tenant-isolation)。テストは平場に置き、`backend/tests/db/`(全 5 領域に一致)を使わない。全ステップで敵対レビューと人間の逐行確認を受ける。

設計の詳細は [design.md](design.md)。スパイクで確かめた前提(research.md「スパイクの結果」):

- 1 イベント = 1 トランザクションで、名前付き注入点を置ける(S-1)
- ポートにハンドルを渡すだけでは、独自スコープの書き込みを防げない(S-2)→ 書き手を制限し、適用中は新しいスコープを開けなくする
- #95 の形では D3 の UPDATE・スロットの版 UPDATE・JSONB の結果が表せない(S-3)→ ステップ 4 で拡張する
- D5 の再照合をイベントのトランザクション内で行えば、同時到達でも正しく B3b / 再掲になる(S-5)
- T1 と T6 は同じ書き込みで確定する(台帳の `result` は NOT NULL かつ不変)

**開始条件**:
- #95(UM01)のマージ(UPDATE の CompileError の是正 = #95 の「ステップ 5 是正」を含む)。マージ後に develop を取り込んでから始める
- ステップ 1・2(core-areas)は、追加の窓口が空いていることを 469 master と確認してから(UM01 の注意: #95 の宣言を累積させない。PR #81 も同じ窓口を使う)

**計画レビューで確認する論点**(design.md 8 節): Q-2(NFR-018 — 1 周目で「当たらない」)/ Q-3(O1 の直列化)/ Q-4(内容同一性)/ Q-5(改訂版の区別・TSK-373)/ Q-6(D3 の列)/ Q-7(RG1 の範囲)/ **Q-8((d) 資産の `cases` 構造と正本 10-3)**/ **Q-9(復元シナリオ 12 本の送り先 — 人間の確認が必要)**/ Q-10(I5 の配信先)

**到達可能な境界結果**(計画レビュー 1 周目 P1-8): P1・P2・P4 = B1・B2・B3(B3a・B3b・O4)・B4・B6・B7。P3 = 変更受理・B8・B9・B10・B12・B13・B14。**B5・B11 は入口 PR へ送る**。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **core-areas の宣言**: `scripts/core_guard.py` の `AREA_PATH_ADDITIONS` に、sync-protocol と recording-rights への追加分(`backend/src/pitchlog/sync/*`・`backend/src/pitchlog/repositories/sync_apply.py`・`backend/tests/test_sync_apply_*.py`)を宣言する | `tests/test_core_guard.py` が green。宣言と JSON を同じコミットで変えていない。#95 の宣言を累積していない |
| 2 | **core-areas の登録**: `.claude/core-areas.json` に登録し、`test_core_guard.py` の期待集合を追随させる | core-guard の CI 相当が green。新しいパスが sync-protocol と recording-rights の両方に一致する(重複帰属の明示) |
| 3 | **TB002 の所有パス**: 条件 2 に同期核の所有パスを足す。所有パスは、検査時点で core-areas.json の sync-protocol の paths に一致するパスに限って発効する。凍結基準の履歴を追記する | 所有パス内の同期語彙が TB002 にならない(正例)。所有パス外(例: `repositories/roster.py`)は TB002 になる(負例)。core-areas.json から外したパスは免除されない(負例)。条件 1・3・4・5 は所有パス内でも効く(負例 3 件)。迂回検査のテストが green |
| 4 | **リポジトリ基底の拡張**: 複合主キーの UPDATE 条件、行ロックの宣言、JSONB の結果の不変表現への実体化、registry を複数モジュールから集める形、適用中に新しい `tenant_transaction_scope` を開けない検査。repository-contract を改訂する | 複合主キーの全列を束縛しない UPDATE が登録時に拒否される(負例)。宣言していない文はロックを取らない。JSONB の結果が不変な表現で返る。適用中の印があると新しいスコープを開けない(負例)。#95 の roster の operation が変わらず green。`backend/tests/conftest.py` の差分 0 行 |
| 5 | **型とポート**: `sync/model.py`(要求・A5・境界結果・ACK 結果)と `sync/ports.py`(ポート 4 種と `PortWriter`)。テスト用の合成実装は `backend/tests/` に置く | 型の単体テストが green。製品コードにポートの既定実装がない(静的検査)。`PortWriter` は token の実行だけを受け付け、SQL を受け付けない |
| 6 | **同期表の operation 登録**: `repositories/sync_apply.py` に 9 表の read/insert/update を登録し、registry に接続する | 全 operation が構築時の検査を通り、registry から引ける。2 テナントの越境テスト(他テナントの行を読めない・書けない)が green |
| 7 | **D5 の分類と再照合**: `sync/idempotency.py`(DI1〜DI5・I1〜I4、内容同一性 Q-4、イベントのトランザクション内の再照合、一意制約違反での再照合のやり直し) | 3 分類(保存済み結果候補・B3b / B13 候補・未使用)を DB テストで確認。順序を固定した並行試験(両方が未使用と分類した後に先着を確定)で、後着が再照合により再掲か B3b になる。他テナントの同じ D5 は未使用として扱われ、存在が判別できない |
| 8 | **P1 の 1 イベントの適用**: `sync/prefix_path.py`。T1+T6(同じ書き込み)・T2・T3(D3 を `FOR UPDATE` で読み直す)・T4(ポート経由)、墓標(R3)・改訂(R4)、一時 ID 写像 C1〜C4 | 1 イベント単位の DB テスト: 墓標で D3 前進、改訂で D3 が後退しない、拒否位置の改訂でその位置まで前進。独自スコープを開くポートを差し込むと、適用が失敗し何も残らない。ACK 全体の検査はステップ 13 |
| 9 | **P2 の T5**: `sync/ordering.py`。O1 の直列化(Q-3)・O2 の局所再採番・O4 の同値停止 | 同じ試合への並行 2 トランザクションで D2 が重複しない。隙間枯渇時に局所再採番と新イベントの保存が同じトランザクションで確定する。O4 で B3 と A5「拒否」になり、投影を止める |
| 10 | **P5 / T9 と P4 / T8**: `sync/rejection.py` | B3a の再送で同じ拒否結果と理由。B3b の前後で台帳と原本表が変わらず、T9 を開始しない。B4 で退避原本と A5「退避」を保存してから結果を返す。保存済みの退避結果は、現在の記録権によらず再掲される |
| 11 | **P3 と I5**: `sync/change_path.py`(③-b・B8〜B14・T7・I6)と `sync/invalidation.py`(未配信の意図を `InvalidationSinkPort` へ渡し、完了まで冪等に再試行) | B8〜B10・B12〜B14 の各分岐が DB テストで再現する。保存済み結果の再掲で無効化意図を重複作成しない。配信先が消費した後・完了記録の前にクラッシュしても、再試行で二重の完了にならない。終了後の P3 では V12 を照合しない |
| 12 | **RG1 とコミット直前再検証**: `sync/gate.py`(同期経路の範囲) | 復元調整中なら P1・P2・P4 は B7、P3 は B10 で、D5 を消費しない。③-a の通過後に復元調整へ移ったら、⑧ で全ロールバックする |
| 13 | **公開入口と注入点**: `sync/apply.py`(段階の順序、D1 昇順の外部結果、DI5、ACK の合成)と `sync/crash_points.py`(トランザクションの前後、各 T 要素の間、T8・T9 の内部の保存境界) | SP 6-3 の例(D3 = 4・D1 = 5 欠落・D1 = 6 未使用・D1 = 7 既存異内容 → B2、D1 6 と 7 は未処理)を再現する。ACK 消失後の再送・引き継ぎ後の再送で、保存済み結果が再掲され、二重適用も選手 ID の重複生成も起きない。段階の順序を入れ替えると落ちるテストがある。他テナントの試合は B6 で、D5・記録権・連番の状態が応答に現れない。P1〜P5 の全注入点で、全部確定か全部未確定 |
| 14 | **(d) 資産契約の改訂**: `cases` 構造・共通の期待フィールド・`tElementCommitment`(T の内部単位・`no-write` / `no-change`)・判別共用体・到達性。注入点の組は `R-TXN-ROUTE` から導出する。契約検査と結果検査を分ける(Python 側) | 契約検査の正例・負例(部分確定・孤立した観測点・重複注入・判別共用体の食い違い・到達性の不一致)が期待どおり。母集合の exact-set 照合が green |
| 15 | **既存 4 資産の版移行と frontend の追随**: 既存 4 資産を最終構造へ一度だけ移行し、`frontend/src/testing/failureScenarioAdapter.ts`・`frontend/src/lib/sync/failureScenarioContract.ts` を追随させる | 移行後の 4 資産が契約検査を通る。frontend の該当 spec(`pnpm test`)が green |
| 16 | **新規資産 10 件**: 墓標・改訂、P1〜P4、`p5-b3a`、`p5-b3b`、`d1-mixed-batch`、`b3b-after-gap` | 10 件が契約検査を通る。母集合のペア集合と一致する |
| 17 | **サーバー側の (d) runner**: 資産を読み、適用核に注入して DB を観測し、結果検査で比較する | サーバー側の資産がすべて green。負例(部分確定を起こす変異)が red になる |
| 18 | **TSK-330・TSK-332 の参照の追随**: `canonOracle.ts`・`canonOracle.spec.ts`・`idempotencyCollision.ts` の受け取り先 | `pnpm test` の該当 spec が green。射程外として残す ID とその理由が、本計画の「やらないこと」と一致する |

## 5. DoD(受け入れ基準)

Notion カードの DoD と対応づける。カードの文言と食い違う 1 項目は、カードを直す(下記)。

- [ ] 段階③〜⑧の順序と P1〜P5 の T 要素の集合が、DB テストで固定されている(ステップ 7〜13)
- [ ] 再送・競合の故障系テスト: ACK 消失後の再送、引き継ぎ後の再送、並行 D5、並行 D2、クラッシュ注入、(d) 資産の runner(カード「再送・競合の故障系テスト」)
- [ ] **NFR-018 のコピー実装を作らない**: ドメイン計算(状態遷移・内容検証)はポートで受け、適用核に書かない
- [ ] **core-areas.json への paths 登録を本 PR で行う**。**重複帰属(sync-protocol × recording-rights)を登録時に明示する**(ステップ 1・2)
- [ ] **`backend/tests/conftest.py` の差分が 0 行**。`backend/src/pitchlog/db/` にファイルを足していない。依存パッケージを足していない
- [ ] pytest / ruff / ty green。frontend の該当 spec green
- [ ] 横断要求: 物理削除しない(墓標はイベントの追加・改訂は旧版を残す)/ テナント分離(越境テスト)/ 利用者 ID を持たない
- [ ] 緑を「FR-012 充足」と報告しない。FR-012 は、ポートの本物(U-R1・U-X1)が入るまで部分充足
- [ ] TSK-330・TSK-332 を Notion で U-S1 に統合した(取り下げ + 相互リンク)

**カードの修正(人間へ上げる)**: カードの「ゴールデンベクタ(`contracts/`)との一致」は対象が存在しない。同期の故障系テストの置き場は `tests/fixtures/sync-protocol-failures/`(SP:1712)で、`contracts/` は NFR-019(a) 専用(`contracts/README.md:3`)。本 PR では「(d) 資産と runner」に読み替える。

## 6. テスト計画

| NFR-019 の種別 | 足すもの | 置き場 |
| --- | --- | --- |
| 単体 | 型・ポート・D5 分類・A5 合成・契約検査 | `backend/tests/test_sync_apply_*.py` |
| 越境 | 他テナントの同じ D5、他テナントの試合は B6、9 表の operation の越境 | `backend/tests/test_sync_apply_*_boundary.py` |
| 故障系 (d) | 資産 14 件(既存 4 の移行 + 新規 10)と runner、クラッシュ注入、並行 D5・D2、RG1 のロールバック、I5 の配信 | `tests/fixtures/sync-protocol-failures/`(資産)、`backend/tests/test_sync_apply_*.py`(runner・DB) |
| 一致性 (a) | **対象外**。同期は NFR-018 の対象列挙に入っていない(REQ:892) | — |
| E2E (c) | **対象外**。入口を開かないため(R-3)。入口 PR で足す | — |

- DB テストは平場に置き、`backend/tests/db_fixtures.py` の fixture(`disposable_postgres_cluster`・`provisioned_product_catalog`)を明示 import する。seed と観測は RLS に掛からない接続(applicator / observer)で行う(スパイクで確認)。conftest は変えない
- Codex の sandbox では Docker を使えないので、DB テストは Claude が各ステップで実行する(スパイクで確認)
- 検証はステップごとに影響範囲だけを回す。ステップ 18 の後に非 DB の全件を 1 回回し、DB の全件は CI に任せる
