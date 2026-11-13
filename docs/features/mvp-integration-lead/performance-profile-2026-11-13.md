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

## 2026-11-13 追記2（隣接する `_live`/`source.read` の統合）

- 統合した隣接区間（間に外部呼出し・DB書込み・host.call・projection適用が無い区間だけ）:
  - `_bind_first_ball_execution` の入口 `source.read` 直後の `_live` を identity 検査へ。
  - `_bind_source_first_ball` の `_fingerprint` 直後の `_live` を identity 検査へ。
  - 評価直後の `_live` は `_read_ready_first_ball_frame` の `_state` 再検査へ一本化。
  - `_require_first_ball_projection_completed` /
    `_require_ordinary_projection_completed` が state を返し、
    `_read_*_stats_source` の重複 `_live` を除去。
  - `_read_first_ball_stats_source` の末尾は `bridge._assert_live_state` とし、
    直前の `_require` の `source.read` を再利用。
  - `_read_values` は直前 `_execution` が照合した `state.event_fingerprint` を使い、
    同じ source.read を重ねない。
  - `_consume_first_ball_projection` の入口は `_projecting_state` と
    `consume_first_ball_frame` の `_state` に委ねる。
  - `_bind_lifecycle_execution` は `_execution_live` の戻り値（source view）を使い、
    二度目の `source.read` を除去。
  - `native_ledger_insert` の execute 直前の重複 `_fresh` を除去（書込み前後は維持）。
  - stats: read前の重複 `_assert_scope`、consumeの再読、persist入口、substitutes先頭の
    重複を統合（読み取り後・書込み前後・consume/projection境界は維持）。
  - `ordinary_prefix._locked_prefix_context` は各DB read前の `live()` を
    前回read直後の `live()` と統合（最初のread前と全read後は維持）。
  - `apply_ordinary_pitch_projection` の consume直後・prepare直前の重複 `_live` を統合
    （consume境界と `_bind_ordinary_preparation` 入口は維持）。
- 実測（`PITCHLOG_SYNC_STAGE_TIMING=1`。同一コードの連続実行）:
  - 初球 `test_first_ball_vertical_http_records_and_refuses_reload`:
    `source_read` **135→42回**、`assert_current` **311→112回**、
    `lease_check` 7113.9ms/311 → 2473.1ms/112、
    total **9320.8ms → 4126.0 / 4514.8ms**（5秒assertは両回とも通過）。
  - 通常球 `test_ordinary_pitch_vertical_http`（3球）:
    `source_read` **62〜68→53〜56回**、`assert_current` **151〜163→133〜139回**、
    total **5167〜5992ms→4523 / 4431 / 4507ms**（直近3回はすべて5秒以内）。
    ただし負荷上昇時は5秒境界に近く、余裕は小さい。
- 残る呼出しの境界（削除せず維持）:
  - 初球: stats `_read_values` の開始/終了 `_execution`（19回）、`_state`（6）、
    評価のDB read後・host前後（3）、bind入口/終了（2）、projection前後（2）、
    write前後（2）、content検証（1）等。
  - 通常球: stats `_read_values`（19）、prefixの各DB read直後（8〜11）、
    qualification device/rights（5）、bind入口/終了（4）、projection（3）等。
- 実画面E2E（`test_game_lifecycle_product_screen_e2e`）は、同期前のUI/ネットワーク
  失敗（`net::ERR_NETWORK_CHANGED`、`ordinary-state-source`/「開始入力を確認できます」
  未表示）で完走できず、公式の5秒assertは未観測。5秒達成の主張には使わない。
- timeout・30秒binding・認可・tenant照合・記録権・RG1・lease/fence/deviceのDB検査は
  延長・省略していない。
