# 同期性能の実測と改善候補（2026-11-13）

## 前提の訂正

7920ms は「終了・再開」の同期ではなく、**開始直後の通常1球目（play_input）の同期**である。

- `frontend/src/screens/GameScreenLifecycleProduct.e2e.ts:294-305`: `syncStarted` → 結果ボタン click → `POST /sync/events` の response headers まで。`syncDurationsMs` へ push するのは通常球ループ（n=1）だけ。
- `:360-396` の `lifecycleOperation('end'|'reopen')` は response を待つが時間を記録していない。
- 実ログ: `elapsedMs=7920`、`beforeRequestMs=59`、`wireToHeadersMs=7859`。HTTP 200、A5「受理」。
- **クライアント準備は59ms、サーバー側が7859ms**。IndexedDB/Web Locks/送信待ちが主因ではない。

## 既知コスト

- 過去の3 writer / 30 viewer 負荷: scope 0.1s → bound 1.8s → gated 6.8s → device 8.5s → preflight 12.4s → rights 9〜10s → 30秒binding失効。
- P3 apply の cProfile: 30.4s 中 `source_binding.read` 23.25s、`_flush_native_stats` 15.96s、`_json_value` 15.08s。
- cache 是正後も追加playの最終 binding age 7.558s。初球E2Eの保存区間 約21.6s。9回E2Eは163球すべて5秒超、最大10736ms。
- マイクロベンチ: `open_domain_host()` 初回263.6ms / 2回目以降73.8ms、`host.call` 1.8〜3.3ms。アイドル時ledger no-op commit 0.1〜0.7ms。Node起動やledger commitが常時7.9秒ではない。

## 上位ボトルネック

1. **Ledger writer-binding の同期commit / broker round-trip**
   - `binding_control.py:919-980` の `bind_writer` → `binding_open`。`:394` phase登録commit、`:445-491` `publish_writer_binding` commit、`:492-519` `close_writer_binding` + observe。
   - `adapter.py:1496-1600` の journal append（intent/published/quarantined/close_requested/terminal）。
   - テストledgerは `synchronous_standby_names='FIRST 1 (ledger_standby)'`。broker timeout 10秒。7920msがtimeout内に収まることと整合。
2. **同一TX内の `source.read` / `assert_current` / wire指紋の反復**
   - `source_binding.py:522-542` の `read()` が毎回 `assert_event_source`。`writer_binding.py:94-112` の `assert_current` が毎回DB関数。`assert_event_source` は前後2回 `assert_current`。
   - `ordinary_pitch_execution.py:88-108` の `_live` が `source.read` を実行し、20箇所以上で呼ばれる。
   - cacheはJSON/指紋の再正規化だけで、`assert_current` のDB呼出しはcacheされない。
3. **1同期あたりのDB transaction fan-out と checkout 時 catalog 再検査**
   - `sync.py:472` replay、`apply.py:687` device state、`:779` game_accessible、`:819` 本体write TX。
   - 認証発行は要求ごとに isolated engine（`tenant_context_issuance.py:27-31`、`engine.py:498-507` NullPool）。
   - 各checkoutで6本のcatalogクエリ（`engine.py:343-369`, `:161-335`）。3〜5 checkout × 6クエリ + set_config + commit。

## 安全な改善候補（優先順）

0. **stage timing 追加**（挙動変更なし）: env-gated `PITCHLOG_SYNC_STAGE_TIMING=1` で route/auth/replay/device/game/TX/bind/content/host/write/commit/binding_close を計測。cookie・credential・本文は出さない。
1. **`source.read` / `assert_current` の作業だけ削減**: 同一TX・同一不変identity・write前の範囲で canonical wire/SelectedEventSource を再利用。`assert_current` / lease / fence / RG1 のDB検査は毎回維持。
2. **読み取り専用preflightのTX統合 + 認証engineの有限pool化**: B5/B6/B7の判定順・SQL・fail-closedは不変。
3. **Node domain host の起動をTX外/プロセス内で再利用**: artifact hashは毎回照合。
4. **stats/play export の同一TX内read整理**: `_flush_native_stats` のreadを再利用（書込み後のstale readはしない）。
5. **Ledger commit は計測してから**: standby health/fsync/networkを確認。control/businessのpublish統合・binding_closeのACK前省略はしない（durability/分離の弱体化）。

## 変更禁止

- NFR-002の5秒目標と `syncDurationsMs.every(elapsed <= 5000)` を維持。timeout延長・assert緩和・「機能成功なら性能成功」への読み替えは禁止。
- 30秒DB writer bindingを延長しない。認証・tenant照合・記録権・RG1・writer bindingの検査を省略しない。
- 認可判断・lease・nonceを要求跨ぎでcacheしない。source cacheは同一TX・同一不変identity・write前だけ。
- ログにcookie・credential・request body・secretを出さない。

## 最小検証

1. stage timing を追加。
2. E2Eの計測対象を6同期全部（通常球・end・reopen・追加球）へ拡張し、`beforeRequestMs` / `wireToHeadersMs` を記録。
3. timing有効で1回実行し、stage合計が7920msを再現するか確認。
4. `EXPLAIN (ANALYZE, BUFFERS)` / `pg_stat_statements`、broker時間、ledger commit時間、standby lagを測る。
5. 機能assert全通過 + 計測した全同期が5秒以内 + 30秒binding/認可/RG1/durability検査不変を確認。

## 2026-11-13 実測追記（stage timing と source 純値cache）

- 実装: `PITCHLOG_SYNC_STAGE_TIMING=1` の時だけ、`POST /games/{game_id}/sync/events` の
  route entry・auth・body parse・replay・device state・game accessible・main TX open・
  writer bind・device verify・preflight D5・content eval（host open/call）・
  write・projection・stats/export・RG1 commit check・binding close・commit・response を
  1行JSON（標準エラー）と `Server-Timing` に出す。cookie・端末資格・V12・本文・
  tenant/game識別子は出さない。既定は無効で、5秒assertの代用にはしない。
- 同一TX・不変identity・write前だけ `SelectedEventSourceValue` を再利用する。
  `assert_current`（lease/fence）、device、RG1、記録権、write後の読みは毎回維持する。
- 実測 `test_first_ball_vertical_http_records_and_refuses_reload`（実HTTP/実writer/実broker）:
  - cache前: total 9320.8ms、`source_read` 6792.1ms/135回、
    `assert_current` 7409.8ms/311回（うち`lease_check` 7113.9ms）、
    `stats_flush` 6085.3ms（`play_export` 3179.2ms、
    `stats_save_source` 941.8ms、`stats_read_writer_state` 449.2ms）、
    `content_eval` 856.5ms、`writer_bind` 173.8ms（`ledger_binding_open` 114.5ms）、
    `binding_close` 33.6ms、`commit` 6.2ms。
  - cache後: total 9764.2〜12764.9ms（同一負荷条件の反復ではなく環境変動を含む）、
    `selected_source_derive` 378.8ms/136回 → 328.2〜396.1ms/120回。
    write前だけの再利用のため総時間の改善は測定誤差内（約25〜50ms）に留まる。
- 実画面E2E（`test_game_lifecycle_product_screen_e2e`、timing有効）:
  6同期のサーバー時間は 23783.4 / 12930.8 / 8031.8 / 12075.6 / 12202.4 / 7057.3ms。
  機能assert（6要求・3球・version 2・DB最終状態）は通過したが、
  `syncDurationsMs.every(elapsed <= 5000)` は 24018ms で失敗した。
  実行時は既存の隔離コンテナ69個が稼働し load average 3.9〜6.8 だったため、
  7920ms との厳密な前後比較には使わない。
- 結論: 現行の支配要因は (1) `source.read` ごとに2回走る `assert_current` の
  broker `binding_check` 往復（311回、7.1〜10.0秒）と (2) stats/play export の
  同一TX読み書き（6.1〜8.5秒）である。`binding_open` 114.5〜169.0ms・
  `binding_close` 33.6〜36.6ms は支配的ではなく、ACK時closeの削除・非同期化は行わない。
  今回の安全な純値cacheだけでは5秒目標へ届かない。timeout延長・assert緩和・検査省略は
  していない。
