# タイブレーク候補の独立レビュー是正（2026-11-13）

対象: `feature/mvp-tiebreak-pipeline-20261113`
レビュー対象: `60eccff3`（比較元 `1989001a`）
是正後: `a00ab577`（正式資産ブランチ `dd8b4a90` を統合）
P0: 0件 / P1: 8件。全件を是正した。

## P1と是正

1. **パネル表示時は通常入力が停止しており、保存処理の `canAppend` 要求と矛盾**
   - `GameScreenOrdinaryPitchController` に `canStartTiebreak` を追加し、`t2.tiebreakStartRequired` の時だけ通常入力を止めたまま開始を許可した。
   - `GameScreenOrdinaryPitch.vue` の保存条件から `canAppend` を外した。
2. **`#credentials` が `tiebreak-start-event-v1` を拒否**
   - 専用wireの `tiebreakStartBody` をattemptへ固定し、許可形式へ追加した。
3. **投影分岐が `bind_tiebreak_start_projection` を通らない**
   - `prefix_path.py` の projection 分岐と完了確認へタイブレークを追加した。
4. **最新 `d3` が `tiebreak_start` の時、read SQLの最新元証明が拒否**
   - `nonplay_prefix_read_sql.py` の最新checkpoint証明へ `tiebreak_start_write_receipts` の `UNION ALL` を追加した。
5. **同半回の二重配置を識別できない**
   - artifact入力へ `lastPlacementHalf` を追加し、同半回を `duplicate-placement` で拒否、次半回の再配置を許可した。
   - 実行側は直前の `tiebreakFrames[-1].afterContext` から半回を渡し、投影でも同じ検査をした。
   - `lineupPlayPrefixContinuation` は半回完了時に `tiebreakStartRequired` を再設定する。
6. **タイブレーク中の打球を画面とproviderが拒否**
   - `hitAvailable` と `prepareLineupPrefix` の `tiebreakActive === false` 条件を外した。
7. **照会済みattemptと再送attemptの同一性**
   - `RecoverableSyncOptions.expectedAttemptId` を追加し、barrierの現在attemptと不一致なら送らない。
   - controllerの `retry` は照会済みattemptを渡す。
8. **tenant契約に新operationがない**
   - `repository-contract.json` / `repository_contract.py` に `SYNC_NONPLAY:consume_nonplay_tiebreak_start` を追加（正式資産ブランチで実施、統合済み）。

## 実証

- フロント全件: **217 files / 4146 tests passed**（`a00ab577` の直前の同一ツリー）
- `GameScreenOrdinaryPitchController.spec`: **40 passed**
- `lineupPlayPrefixContinuation` / `tiebreakStart` / `endConditionCore`: **85 passed**
- backend 非play/投影/prefix: **142 passed**
- 正式資産統合後: domainrt + v7/v8 + registry: **1413 passed**
- `tests/db/test_substitution_vertical_http.py`: **1 passed / 102.51秒**（製品資産setup・migration 0051通過）

## 残る不足（成功扱いしない）

- タイブレークの実DB/実画面E2Eは未通過。`test_tiebreak_start_vertical_http.py` は、10回CPをlegacy v3へ直接seedすると P3 current / lifecycle GET の相関と整合しないため **skip** として理由を固定した。製品資産のsetup通過は substitution vertical で確認済み。実試合の9回消化後に行うE2Eへ置換する。
- 7.7のPR197後継受理は独立レビュー待ち。`tests/test_check_tenant_boundary_bypass.py` の563失敗は未解消。
- 統計27項目・両CSVのタイブレーク実走は未実施。
