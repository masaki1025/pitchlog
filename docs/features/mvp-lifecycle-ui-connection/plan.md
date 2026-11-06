---
feature: mvp-lifecycle-ui-connection
status: active
承認: 済（PO委任による主担当root判断、2026-11-06。lifecycle-ui-intake-independent-20261106 の P0×1/P1×4 を反映する接続改訂）
重さ分類: コア領域
branch: feature/mvp-lifecycle-ui-connection
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-lifecycle-ui-connection
created: 2026-11-06
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 終了・追記再開 FE6 の実接続改訂（レビュー反映）

## 目的と基点

独立レビュー `~/.cache/pitchlog/lifecycle-ui-intake-independent-20261106/REPORT.md` の否決（P0=1・P1=4）を、旧候補をレビュー対象として固定したまま新しい専用枝で解消する。対象は従来のFE6 6pathと本plan/progressだけで、共有ファイル・router・正式contracts/DDL・backend sourceは変更しない。

- 旧候補（レビュー対象・変更しない）: `feature/mvp-lifecycle-ui` = `a36c323bdab235e51a480f43ecfc956bc04e1139`
- 新branch/worktree: `feature/mvp-lifecycle-ui-connection` / `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-lifecycle-ui-connection`（旧候補から作成）
- 接合仕様: 独立レビュー全文と、主担当の確定ゲート候補 `feature/mvp-lifecycle-product-connection@291451965c3eabf2914aaedca3a01fb685617264`（**in-review。正式受理済みとは扱わない**）
- 旧`MINIMUM-INTERFACE.md` のflat V7は現gate候補の閉unionと異なるため、旧形を受理しない。

## レビュー指摘への対応方針

| # | 指摘 | 対応 |
| --- | --- | --- |
| P0-1 | 書込前GET必須のため通信断中に終了宣言を耐久保存できない。未確定終了があると再開を追記前に止める | 最後に実GETで確認したbase（status/lastVersion/active/CP ref/d3/nextD2/appendPolicy）を耐久storeへ保存し、断中はbaseと耐久queueのchainだけで終了/再開/再終了を追記する。実GETはACK後の確認だけに使う |
| P1-2 | 既定writerとmount例に実preconditionsが無く常にLOCK_UNAVAILABLE | `writer`を必須オプションにし、`createGameLifecycleWriter(environment)`で既存記録画面と同じHTTPS/プロファイル/モード/bucket/Lockdown/認証のgetterから組み立てる。常時trueの既定を作らない |
| P1-3 | 旧flat V7が現gateの閉unionに適合しない | `checkpointRef`を`confirmed|confirmed_prefix|queued_predecessor`、reopen `target`を`confirmed|queued_end`の閉unionへ改訂する。flat形は閉拒否 |
| P1-4 | ACK後の古いGETを「再取得済み」とする | ACK後に期待status/確定版/receiptを計算し、GETがACK対象またはそれ以後を示した時だけbaseを更新する。古いGETは採用せず`refresh=pending`/`stale-read` |
| P1-5 | 不可視試合E2Eが可視の共通fixtureを使う | 不可視専用の環境変数`PITCHLOG_LIFECYCLE_E2E_INVISIBLE_GAME_ID`を要求する。2球driverの未接続は明示失敗のまま残す |

## 意味の固定（推測しない）

| 対象 | 固定 |
| --- | --- |
| base | 実GET成功時だけ更新する。`tenantId/gameId/d4/status/lastVersion/active/CP ref/d3/nextD2/appendPolicy/recovery/lastSavedAt`。書込資格ではない |
| 期待status | baseのstatusへ、baseのd3より後の**耐久lifecycle slot**（未送信または同期済み）をD1順で適用した値。要操作/退避は適用せずblocked |
| checkpointRef | 直前D1がbaseに含まれる→`confirmed`。直前D1が受理済みでbase以降→連続受理を確認して`confirmed_prefix`。直前D1が未送信→`queued_predecessor`。baseのd3より前の未送信lifecycleはACK喪失時だけ再送対象 |
| reopen target | 直前の確定終了がbaseに含まれる/一致する→`confirmed`。直前終了が端末耐久chainにある（受理済みだが表示未追従、又は未送信）→`queued_end`（予約eventId/receiptId/D5/D1を固定）。終了slotが無いサーバー確定済み終了→`confirmed` |
| D2 | 直前slotのV6があれば`nextOrdinaryD2`（既存共通allocator）、無ければbaseの`nextD2`をそのまま使う。物理play番号/activeDepth/終了版番号と混ぜない |
| 送信順 | 未終結の先行slotがあれば追記だけ受理し、送信しない（`queued-awaiting-predecessor`）。再送は先頭がlifecycleのときだけ順に送り、通常操作の先行は既入力の再送に譲る |
| 再取得完了 | ACK対象の確定版/eventId/receiptId、又はそれ以後の真正pointerがGETに現れた時だけ`refresh=done`。古い/後退するGETはbaseに採用しない |
| 再開種別 | 正本の写しに無い間は`reopen-kind-unavailable`。cast・id7流用・固定成功をしない |

## 編集範囲と再利用

- 編集: `frontend/src/api/gameLifecycle.ts`、`frontend/src/screens/gameLifecycleController.ts`、`frontend/src/screens/GameScreenLifecyclePanel.vue`、各spec、`GameScreenLifecycle.e2e.ts`、本plan/progress。
- 再利用: `buildSyncEventRequestBody`/`checkSyncEvent`、`openDurableQueue`、`runAsSingleWriter`+`withNonBlockingSingleWriter`、`appendPitchEventUnderLock`、`readOrdinaryPitchAck`/`applyAckToSlot`、`isNativeUndoGame`、`NativeEnvelopePersistence`（V12込み全本文）、`GameStartPersistence`、`nextOrdinaryD2`、`isStartedGameTimestamp`。
- 追加する小storeは「送信試行マーカー」と「最後の実GET base」だけで、資格・本文の別正本を作らない。

## 実装ステップ

| # | 単位 | 合格条件 |
| --- | --- | --- |
| 1 | 閉union V7と読取transport | `confirmed/confirmed_prefix/queued_predecessor`と`confirmed/queued_end`を閉検査し、flat形・欠落・非正準を拒否する。ordinal→literalの専用写像と未裁定種別の閉拒否を維持する |
| 2 | 実writer・断中base・依存順のcontroller | 実preconditionsの必須注入、baseの耐久保存、実GET不能下のend→reopen→end、ACK喪失/再起動、先行未確定の送信待ち、ACK後の古いGET拒否をspecで検査する |
| 3 | パネルとE2E前提 | 期待status/サーバー確認済み/未送信/結果不明/取得待ちを表示し、断中E2Eと不可視専用fixtureを用意する。実driver未接続は明示失敗 |
| 4 | レビュー反映の記録と接合差分 | HEAD/全SHA/検査/残る接合（backend閉union・種別・mount・実PG）を固定し、非作者再確認へ渡す |

## 接合差分（rootが直列反映）

1. `frontend/src/lib/sync/eventKinds.ts`: `game_reopen`の正式種別（候補 `id:'13', name:'試合再開', participation:LOGICAL_POSITION, hasRevisionOrder:false, group:'A'`）。
2. `frontend/src/lib/sync/eventFieldRules.ts`: 上記がLOGICAL_POSITION・非取消・非墓標/改訂なら変更不要（V6必須/V8..V11禁止）。
3. backend候補 `lifecycle_payload.py`/`lifecycle_execution.py`: 閉unionの受理と、`confirmed_prefix`/`queued_predecessor`/`queued_end`のprefix解決。`checkpointRef`の現行canonical比較は`confirmed`専用のため、そのままでは新形を受理できない。
4. mount: `createGameLifecycleWriter`へ既存環境getterを渡し、`resume-recording`を既通常/NP入力へ接続する。
5. backend正式化: `game_reopen`のV5/参加区分/C12/CHECK、0043/ACL/registry/artifact/pins、finished GETの実PG実測。
