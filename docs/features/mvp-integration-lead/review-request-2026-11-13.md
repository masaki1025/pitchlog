# 独立レビュー依頼（2026-11-13）

## 対象

- リポジトリ: `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-integration-20261109`
- ブランチ: `feature/mvp-integration-20261109`
- 比較元: `1989001a`
- レビュー対象HEAD: `88652997`
- 差分: 31コミット / 60ファイル / +1529 −225
- 変更一覧: `git diff --stat 1989001a..88652997`
- リモート: `origin/feature/mvp-integration-20261109` は同一HEADへ通常push済み（force pushなし）

## 重点対象

1. **打球語彙cache** `frontend/src/api/battedBallOptions.ts`
   - tenant/認証世代（`teamId`/`authEpoch`）分離
   - 有界性（tenant/世代が増えた場合の上限・無効化）
   - 先頭ページだけを再利用する条件と、語彙更新・tenant切替・ログアウト時の無効化
   - `GameScreenBattedHitObservation.vue` の watch 分割が、文脈変更時の入力初期化と語彙再利用を混同していないか
2. **ACK喪失の照会・終結・再送**
   - `GameScreenOrdinaryPitchController.ts` の `inspectAttempt` / `retry` / `#recovery` / `#inspectionResult` / `#sendAbort`
   - 保存要求の二重送信、照会と送信の競合、旧attemptの後着遮断、照会中の切断・再起動
   - `recoverableSyncPost.ts` の `skipRecovery` が、照会済みの次attemptを正しく使い、未照会の送信へ誤って適用されないか
   - `unresolved` のときに保存済み/未保存を断定せず、再送しないこと
3. **記録権・認可**
   - `#credentials` の端末資格・attempt・録音権proofの照合が、照会経路でも維持されているか
   - tenant-bound header、C2、記録権世代の取り違えがないか
4. **タイブレーク保存**
   - 今回は純遷移核と画面の無効表示のみで、正式pipeline・保存・同期は未接続。差分に含まれる範囲で、既存の通常球・終了・再開を壊していないかだけを確認する（未実装を成功扱いしない）。

## 検査証拠

- `test_screen_nine_innings_batted_out_stats_and_csv`: **1 passed / 636.91秒**（実HTTPS・実ブラウザ・owned DB。55プレイ、終了、reload、成績27項目、毎球ZIP/成績CSV）
- `test_attempt_recovery_screen_e2e`: **1 passed / 103.46秒**（ack-lost/before-httpの両モード。再起動→復元→安全確認→照会→再送→次球reload。照会中の切断で保存POST 0件、再送1回、ack-lost=`重複`、before-http=`受理`）
- `test_game_lifecycle_product_screen_e2e`: 機能assert通過、同期1回 **7920ms** で5秒性能assertのみ未達
- フロント全件: **216 files / 4139 tests passed**
- backend対象: **193 passed**（`test_attempt_recovery_response` / `test_api_conventions` / `test_api_app` / `test_authz_repository_contract`）
- 固定値追随: `test_batted_hit_product_declarations` / `test_batted_hit_storage_boundaries` は通過。`test_sync_apply_product_supply` は歴史的 `ddl-elements.json` 射影の3件が未解消（後述）。

## 既知の未達（成功扱いしない）

- タイブレーク: 正式operationRows/case・保存・同期・画面・次球・再配置が未接続。
- 7回制・延長: 固定5規則は9回のみ。`resolve_stage_a_rule` が9回以外を拒否。
- FR-013 記録担当端末の引き継ぎ: 通常/緊急・世代更新・旧世代イベント退避が未実装。
- 断中のその場選手登録: 一時ID・耐久キュー・交代順序が未実装（オンラインのみ）。
- `POST /players` の冪等性: 安定キー照会・再送が未実装。
- 同期性能: 終了・再開E2Eの1回が7920msで5秒目標未達。
- tenant-boundary 7.7: `repository-contract` 39 / `base-allowlist` 54 の履歴・snapshot・承認が未追随。
- `test_sync_apply_product_supply.py` の歴史的射影3件: `catalog_after_revision` が現在の `ddl-elements.json` と一致せず、byte比較が失敗。意図的追加の累積に対する射影モデル更新が必要。
- 実機・本番TLS・バックアップ復旧・運用公開は未実施。

## 依頼

P0/P1/P2のみ、ファイル・行・再現条件・修正方向を付けて報告してください。スタイル指摘は不要です。既存のレビュー履歴（`docs/features/mvp-integration-lead/progress.md`）は維持し、今回の指摘は追記形式で返してください。特に、語彙cacheのtenant/世代分離・有界性・無効化、ACK回復の競合、記録権、タイブレーク保存の未接続を重点的に確認してください。
