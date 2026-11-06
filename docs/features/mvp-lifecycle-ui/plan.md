---
feature: mvp-lifecycle-ui
status: active
承認: 済（PO委任による主担当root判断、2026-11-06。lifecycle-ui-delegation-20261106.md の受諾範囲。対象base e0be2483e29eecba478e5f4fca56d4cf4164711b）
重さ分類: コア領域
branch: feature/mvp-lifecycle-ui
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-lifecycle-ui
created: 2026-11-06
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 終了・追記再開の実画面接続（FE6）

## 目的と基点

初回MVPの「終了 → 追記再開 → 2球追記 → 再終了 → 再読込」を、spike・計画・無効ボタンではなく実transport・耐久queue・ACK・実サーバー再取得まで接続する。担当は lifecycle 専用worktreeの FE6 6pathと本plan/progressだけであり、正式契約・DDL・ACL・backend source・router・共有lib・主担当台帳は変更しない。

- 起点: `e0be2483e29eecba478e5f4fca56d4cf4164711b`（`feature/mvp-nonplay-product-connection`。後発commitを吸収しない）
- 接合仕様: `~/.cache/pitchlog/mvp-lifecycle-product-author-20261106/MINIMUM-INTERFACE.md`、packet `2f464208ef8ed53e78048ea5370e55204b60584b7397b51272882b1bed91fee8`
- 規範: 要件 FR-007（終了済み試合の追記再開はFR-005の終了条件ロックだけを解除する）・FR-010（終了宣言は常にイベント。通信断中もキューへ積む）・NFR-007/E4（受理済み操作を失わない）・NFR-018（単一計算）・NFR-023（自動escape）
- 到達点の区別: 本単位の成功は「同一隔離PG・同一版・実画面」で root が実測するまで未成立である。pure mock と transport 呼出順の成功を実認可/DB成功へ読み替えない。

## 意味と閉範囲

| 対象 | 固定する意味 |
| --- | --- |
| 読取 | `GET /games/{id}/started?projection=lifecycle-prefix-v1&limit=25[&cursor=...]` の `read_kind=nonplay-prefix` / `profile=nonplay-prefix-read-v1` / `status` / `lifecycle{formatVersion,status,lastVersion,active,activeStatsVersionId}` だけを閉じて読む。旧DTO・旧projection・metadata欠落から finished/active版/receipt を推測しない |
| 終了 | `POST /games/{id}/sync/events` へ `event_kind=5`（正本の写し）の1イベントを積み、専用transportで `game_end_declaration` へ正規写像する。`target=null`、status=in_progress・active=null のときだけ提案する |
| 追記再開 | 同じPOSTへ `event_kind=game_reopen` を送る。`target` は直GETの**最新active全3値**に限る。再開種別の正本参加区分/C12はroot追補中であり、`EVENT_KIND_RULES` に無い間は**閉拒否**する（id7やcastで通さない） |
| payload | `{formatVersion:'native-game-lifecycle-v1',action,checkpointRef{id,revision,digest},target,event{eventId,receiptId}}` の完全一致。V8/V9/V10/V11を送らない。revisionは文字列、digestは64hexのまま扱う |
| 耐久 | queue受理**前**に D5・D1・D2・予約event/receipt・attempt・V12込み全本文を IndexedDB へ strict commit する。同一要求は同本文/同D5/同attemptで再送し、未確定要求をTTLで捨てず新D5へ置換しない |
| 排他 | 既存 `singleWriterLockName(gameId)` と `runAsSingleWriter` を待たない管理機構で使う。鍵が無ければ追記せず明示blocked |
| 送信後 | ACKは既 `readOrdinaryPitchAck`/`applyAckToSlot` で同game/D4/D1/D5の受理/重複だけを同期済みへ。保存ACKと実GET再取得未了を別状態で表示する |
| 再取得 | 操作後とreloadは必ず実GETからstatus/active版/最終更新/次位置を復元する。取得未了を保存済みと表示しない |
| 追記入力 | 再開後の追加球は root の既通常/NP入力controllerへ渡す。本単位で計算・保存を二重実装しない。handoff（gameId/next_position/checkpointRef/recovery）だけを返す |

## 复用する既存成果（重複実装しない）

- `api/client.syncEvents.ts` の `buildSyncEventRequestBody`（wire形・D1/D4/D5・V12要求・正本検査）
- `lib/sync/durableQueue.ts` の `openDurableQueue` / `prepareAppend` / `append` / `readNextD1` / `readSlot` / `readSlotsPage`
- `lib/sync/singleWriter.ts` + `screens/GameScreenSingleWriter.ts` の単一書き手
- `screens/GameScreenPitchAcceptance.ts` の `appendPitchEventUnderLock`（D5/identity/reconcile）
- `screens/GameScreenAckApplication.ts` の `applyAckToSlot`、`api/ordinaryPitchAck.ts` の `readOrdinaryPitchAck`
- `api/nativeUndoGame.ts` の `isNativeUndoGame`（NP read閉検査。finished用にstatusだけ差し替えて再利用）
- `api/nativeUndoWire.ts` の `NativeEnvelopePersistence`（V12込み全本文＋eventのstrict耐久store。新storeを作らない）
- `lib/gameStartPersistence.ts` の実tenant/device/start grant（`recording_right_proof`/`recovery_generation`/`d4`）

## 閉拒否・非成功条件

- 読取: 404=不可視/不存在/真正proof無し、409=記録済みで閉じない、400/422/501=旧server → 成功にしない
- 書込: 409/422/503・abort・通信断・parse不明・ACK無し/不一致は保存成功にしない
- 前提: 認証epoch/tenant不一致、grantのd4/recovery/lineup不一致、先行未終結slot、未受理準備行、status/active不一致は追記しない
- 再開種別が未裁定の間は `reopen-kind-unavailable` でblocked（画面に接合待ちを明示）
- 実GET未了は `acked` と `refresh=pending` を分けて表示し、「保存済み」とだけ表示しない

## 実装ステップ

| # | 単位 | 合格条件 |
| --- | --- | --- |
| 1 | 読取・書込transportの閉実装 | lifecycle-prefix-v1の閉検査、payload閉検査、ordinal→literalの専用写像、未裁定種別の閉拒否を実装し、transport specで旧DTO/欠落/不一致/未知種別を拒否する |
| 2 | 耐久・排他・ACK・再取得controller | queue受理前のstrict耐久、同本文/同D5/同attempt再送、二重タブ/認証変更/通信断/ACK喪失/再起動/409/422/503の非成功、ACKとGET未了の区別、reload復元を spec で検査する |
| 3 | 画面パネルと実画面E2E骨子 | status/active版/最終更新/未送信/結果不明/取得待ちを自動escapeで表示し、終了/再開/再送/再読込と戻る導線を提供する。実画面E2Eは実server/実PG未供給を明示して成功にしない |
| 4 | 接合差分の返却と検査記録 | eventKinds/eventFieldRules/router mount/backend正式化の具体差分をprogressへ固定し、frontend検査（prettier/eslint/vue-tsc/vitest）結果と残る接合を記録する |

## 接合差分（rootが直列反映する。本単位では書かない）

1. `frontend/src/lib/sync/eventKinds.ts`: 再開種別（例 `id:'13', name:'試合再開', participation:LOGICAL_POSITION, hasRevisionOrder:false, group:'A'`）の正式裁定と追加
2. `frontend/src/lib/sync/eventFieldRules.ts`: 上記種別のV5/V6必須・V8/V9/V10/V11禁止が既条件写像で成立することの確認（新条件文を足さない）
3. `frontend/src/router.ts` / `frontend/src/screens/GameScreen.vue`: 本パネルのmountと`resume-recording`→既通常/NP入力controllerの接続
4. backend: `game_reopen`のV5 literal・参加区分/C12・operation_events CHECK・0043・ACL/body/registry・finished GETの正式受理
