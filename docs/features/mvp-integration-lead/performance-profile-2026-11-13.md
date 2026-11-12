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
