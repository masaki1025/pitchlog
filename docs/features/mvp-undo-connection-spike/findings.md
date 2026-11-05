# 取消の接続spike 実測結果

- 起点: 正式 develop `112f771e549d6a92d724f62d9b0b45dcc89973c1`
- 作業枝 / worktree: `feature/mvp-undo-connection-spike` / `~/projects/pitchlog-worktrees/feature-mvp-undo-connection-spike`
- 契約・正本・共有台帳: 変更なし
- artifact: `frontend/public/domain/pitchlog-domain.js` sha256 `74409235f49930e09101dbcd6b241ba29a49083022238bad9881dd9fb730573d`（67,132 bytes）

## 1. 成立した範囲

### 1-1. 正式 artifact の取消計算

`feature/ux1-undo-ts@b2ed1905` の `undo.ts` を現行 `stateTypes.ts` と v3
`battingOrderBySide` へ追随させ、`publicApi.applyUndo` として公開した。

- `frontend/src/domain/undo.spec.ts`: 契約 `undoRows` **10/10** を消費。
  `full-equality` 9 件は `stateEffect`・`historyEffect`・`historyContext` を完全一致、
  `liveness-only` 1 件は契約スキーマの比較規則どおり。
- `frontend/src/domain/publicApi.spec.ts`: JSON 境界（空スタック・1 球取消・v3 cursor・
  数値型/未知キー/不正差分拒否）を追加。
- `frontend/src/domain/undoArtifact.spec.ts`: ビルド済み artifact 経由で取消を実行。
- `pnpm exec vitest run src/domain`: **22 files / 753 tests passed**。
- `pnpm exec vue-tsc --noEmit`: 成功。
- `pnpm build:domain`: 2 回実行して同一 SHA（再現ビルド一致）。

### 1-2. 実認証・実記録権・同期核・実DBの接続

`backend/tests/db/test_spike_undo_connection.py` が、owned の使い捨て PostgreSQL と
Docker の実 app UID 20003・実 broker・実 HTTP で次を通した（**1 passed / 約 50 秒**）。

1. 実 login → 実 POST `/games` 作成 → 実端末登録 → 実 POST `/start`。
2. 通常投球 `batting-result.ball` を実 `/sync/events` で 1 球保存。
3. 専用 GET `/spike/games/{id}/state` が、保存済みイベントを正式 artifact で畳み込み、
   現在状態・履歴 1 件・取消対象 D1=1 を返す。
4. 専用 POST `/spike/games/{id}/undo` が、実認証・実端末提示・実記録権・
   同期核 P1・実 DB の同一トランザクションで取消を **受理**。
5. 再取得で `balls=0`・履歴 0 件・イベント `[play_input, undo]`・対象なしを確認。
6. 同一 D5・同一内容の再送は **重複** を返し、水位・状態・イベント数が不変。
7. 同じ対象を新しい D5 で名指すと **拒否**（B3）し、イベントを追加しない。
8. 別 tenant の実 login では GET が **404**（越境拒否）。
9. 提示 V12 を変えた要求は **退避** となり、イベントを保存しない。
10. `after_t4_projection` の名前付き故障注入で例外を出し、**取消イベント・D3・状態が
    一切残らない**（部分保存なし）。
11. 監査: `operation_events` は play 1 + undo 1 の 2 行、`play_rows` は 1 行のまま、
    対象 play の `retired_at` / `replaced_at` は NULL。台帳は 2 行。

### 1-3. 回帰

- `backend/tests/db/test_ordinary_pitch_vertical_http.py`: **1 passed / 約 55 秒**
  （既存の通常 3 球・再送・prefix 再読込が継続）。
- `backend/tests/test_sync_apply_model_ports.py` +
  `test_sync_apply_first_ball_ports.py`: **134 passed**。
- `backend/tests/test_sync_apply_prefix_path.py` +
  `test_sync_apply_operations_boundary.py` +
  `test_operation_event_kind_contract.py`: **79 passed**。
- `uv run ruff check .` / `uv run ty check`: 成功。

### 1-4. 画面

- `frontend/src/screens/GameScreenUndoSpike.vue` と実 API client を追加。
- `GameScreenRecordedRestore.vue` の同じ記録画面に、通常投球 v1 の取得と取消 panel を
  埋め込んだ（route 遷移を伴わない）。
- `GameScreenUndoSpike.e2e.ts` / `.playwright.config.ts` と
  `backend/tests/db/test_undo_screen_e2e.py` を用意した。

## 2. 実画面 E2E の結果（未達）

`backend/tests/db/test_undo_screen_e2e.py` は **失敗**した。原因はこの枝の取消実装では
なく、起点 `112f771e` の既存画面経路で次の 2 点が再現するためである。

1. 開始直後の `/started?projection=play-prefix-v2` と `play-prefix-v3` が **503**。
   `require_registered_product` の DDL/repository/manifest 照合が起点で成立しない。
2. 実画面の router guard が、保存後の route 遷移で **login へ redirect** する。

同じ使い捨て DB/実 app/Vite で、既存の
`backend/tests/db/test_lineup_screen_e2e.py` も **同じ 503 と redirect で失敗**した。
したがって、取消接続だけの退行ではなく、起点の既存 E2E 環境の未成立として扱う。
本枝では E2E を green と記録しない。

ログ:
- `/tmp/opencode/pitchlog-screen-e2e/undo-spike-https-playwright.log`
- `/tmp/opencode/pitchlog-screen-e2e/undo-spike-https-vite.log`
- `/tmp/opencode/pitchlog-screen-e2e/undo-spike-https-app.log`
- baseline: `/tmp/opencode/pitchlog-screen-e2e/lineup-https-playwright.log`

## 3. 未決事項（主担当へ返す）

### 3-1. 製品 read 経路は取消後の tail を表現できない

現行 `/started?projection=...` の history page は D1 連続性と `last_source` を
play 行に前提しており、水位末尾が undo（play 行なし）になると成立しない。
spike は専用 GET でイベント列を畳み込んだ。製品接続には history version /
retired / checkpoint の設計判断が必要。

### 3-2. undo の V7 payload schema がない

契約に取消 payload の形がないため、spike は
`{"formatVersion":"undo-connection-spike-v1","target":...,"result":...}` を
暫定使用した。製品の wire 契約は主担当の判断対象。

### 3-3. 取消対象の範囲

spike は「水位末尾が確定プレイ」の 1 件取消だけを受理する。非 play イベント越しの
「直前の取消可能な操作」、連続取消、状態補正は未接続。FR-006 の全範囲には
履歴スタック全体の解決規則が必要。

### 3-4. artifact SHA と凍結 vector

`applyUndo` を単一 artifact に追加したため SHA が
`cda0b594…` → `74409235…` に変わった。旧 SHA を固定した frontend の凍結 vector 照合
（`firstBallWire.spec.ts`・`lineupPrefixWire.spec.ts`・`terminalPitchWire.spec.ts` など）
が **59 件失敗**する。`contracts/` は変更していない。

選択肢:
- 契約所有者の承認の下で vector の artifact SHA を更新する。
- 取消を別 artifact に分離し、既存 artifact の SHA を固定したままにする。

本枝ではどちらも独断で選ばない。

### 3-5. 既知の取消契約の仕様不足

`docs/features/ux1-undo-ts/findings.md` §3-1〜§3-9・§4-1 をそのまま保持する。
特に delta/set 分類の不在、現在状態の不在、liveness-only の履歴文脈欠落、
D+1 スタックの前進合成不能は未解決。

## 4. 変更パス

### 新規

- `backend/src/pitchlog/sync/spike_undo_artifact.py`
- `backend/src/pitchlog/sync/spike_undo_http.py`
- `backend/src/pitchlog/sync/spike_undo_ports.py`
- `backend/src/pitchlog/sync/spike_undo_validation.py`
- `backend/tests/db/test_spike_undo_connection.py`
- `backend/tests/db/test_undo_screen_e2e.py`
- `frontend/src/api/undoSpike.ts`
- `frontend/src/domain/undo.ts`
- `frontend/src/domain/undo.spec.ts`
- `frontend/src/domain/undoArtifact.spec.ts`
- `frontend/src/screens/GameScreenUndoSpike.vue`
- `frontend/src/screens/GameScreenUndoSpike.e2e.ts`
- `frontend/src/screens/GameScreenUndoSpike.playwright.config.ts`
- `docs/features/mvp-undo-connection-spike/{plan,findings}.md`

### 変更

- `backend/src/pitchlog/api/app.py`（`PITCHLOG_UNDO_SPIKE=1` 時だけ install）
- `backend/src/pitchlog/repositories/transaction.py`（spike Port 命令・content read 許可）
- `backend/src/pitchlog/sync/apply.py`（`spike_p1`・再掲 `path`）
- `backend/src/pitchlog/sync/port_guard.py`（spike Port の遅延 import）
- `backend/src/pitchlog/sync/ports.py`（spike Port 登録）
- `backend/tests/db/test_screen_start_e2e.py`（E2E app へ `PITCHLOG_UNDO_SPIKE=1`）
- `backend/tests/test_sync_apply_model_ports.py`・`test_sync_apply_first_ball_ports.py`
  （登録集合の固定期待へ spike Port を追加）
- `frontend/public/domain/pitchlog-domain.js` / `.json`（再生成）
- `frontend/src/api/client.ts`（spike 取消 POST だけ実端末提示を許可）
- `frontend/src/domain/publicApi.ts` / `publicApi.spec.ts`
- `frontend/src/domain/{firstPitch,ordinaryPitch,strikeoutPitch}...Artifact.spec.ts`
  （公開表の固定期待へ `applyUndo` を追加）
- `frontend/src/lib/generated/wrappers/domainArtifact.ts`
- `frontend/src/router.ts`
- `frontend/src/screens/GameScreenRecordedRestore.vue`
- `frontend/src/screens/GameScreenE2eServer.py`
