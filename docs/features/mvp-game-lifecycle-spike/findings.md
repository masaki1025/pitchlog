# 試合の終了・再開・再終了spike 実測結果

- 起点: `660d58554f3e0b74da2623ffd7e9a452188d7772`（公開候補 `feature/mvp-batted-hits`）
- 開始時の正式 develop: `112f771e549d6a92d724f62d9b0b45dcc89973c1`
- 起点の統合状況: **未統合**。`git merge-base --is-ancestor 660d585 112f771e` は偽、`112f771e..660d585` は 89 コミット。GitHub PR #196（base develop）は open / draft。
- 作業枝 / worktree: `feature/mvp-game-lifecycle-spike` / `~/projects/pitchlog-worktrees/feature-mvp-game-lifecycle-spike`
- **コード・証拠固定 HEAD: `bceba327beedcf473ac7ae1c3eb018da17c50827`**
- 本 `findings.md` は上記 HEAD の後に追加する記録コミットであり、コード差分を含まない。
- `contracts/`・`docs/requirements`・`docs/design`・`docs/adr`・共有台帳・他 worktree は変更していない。

## 1. 成立した範囲

### 1-1. 実画面の作成・開始・通常記録

実 HTTPS の Vite、実 app UID 20003、owned PostgreSQL、実 broker を使い、Playwright で次を通した。

1. 実ログイン
2. `新規作成` 画面で 9回制（`regulationInnings=9`）の新規試合を作成（POST `/games` 201）
3. 記録画面で実端末登録
4. 両側スタメンを画面で入力し、実 `POST /games/{id}/start` 200
5. `play-prefix-v3` の記録画面で無走者本塁打を 1 球保存（POST `/sync/events` 200 / A5「受理」）
6. 保存後 GET で `state.score = {home:"0",away:"1"}`、`prefix_ref.length="1"` を確認

試合・記録は画面の実 API だけで生成し、DB への試合状態・play の事前投入や固定成功応答は使っていない。
参照選手・球種・本塁打語彙だけを owned fixture で準備した。

### 1-2. 終了・再送・再開・再終了・reload

専用画面 `/games/{id}/lifecycle-spike` で、保存済みイベントを D1 順に畳んだ専用 GET を使い、次を実測した。

| 操作 | 結果 |
| --- | --- |
| 終了宣言 | 実 `/sync/events` 200 / A5「受理」/ watermark 2 / 終了確定版 v1（D1 2） |
| 同一 D5・同一本文・同一 attempt の再送 | 200 / A5「重複」/ watermark 2 のまま。`operation_events` も増えない |
| 追記再開 | 実 `/sync/events` 200 / A5「受理」/ watermark 3。v1 は「再開 D1 3 で失効」 |
| 再終了 | 実 `/sync/events` 200 / A5「受理」/ watermark 4 / 終了確定版 v2（D1 4）。v1 は失効のまま、v2 が有効 |
| 再取得 | 専用 GET で v2 有効・v1 失効を再取得 |
| ページ reload | 専用 GET で同じ v2 有効・v1 失効を再取得 |

E2E の実測結果（ログ原文）:

```json
{"score":{"home":"0","away":"1"},"end":{"status":200,"a5":"受理","watermark":2},"fault":{"status":500,"watermarkAfter":"1"},"duplicate":{"status":200,"a5":"重複"},"reopen":{"status":200,"a5":"受理","watermark":3},"reend":{"status":200,"a5":"受理","watermark":4},"finalVersion":"v2","finalWatermark":"4","finalizations":[{"version":1,"d1":2,"invalidatedBy":{"d1":3}},{"version":2,"d1":4,"invalidatedBy":null}],"reloaded":{"status":"finished","version":"v2","watermark":"4"},"badV12":{"status":200,"a5":"退避","watermarkAfter":"4"},"otherTenantStatus":404,"otherTenantFaultStatus":404}
```

- E2E: `tests/db/test_spike_end_reopen_screen_e2e.py` **1 passed / 60.14 秒**（最終 HEAD）。
- Playwright ログ: `/tmp/opencode/pitchlog-screen-e2e/game-lifecycle-playwright.log`
- app ログ: `/tmp/opencode/pitchlog-screen-e2e/game-lifecycle-app.log`
- Vite ログ: `/tmp/opencode/pitchlog-screen-e2e/game-lifecycle-vite.log`

### 1-3. 権限不足・越境・故障・再送

- **V12 改竄**: 終了 D1 5 を新しい D5/attempt で送ると 200 / A5「退避」。`operation_events` は 0 件、`idempotency_ledger` は `evacuated`、watermark は 4 のまま（DB 監査で確認）。
- **越境 GET**: 別 tenant で実ログインし、その `tenant_id` を assert したうえで専用 GET → 404。
- **越境 fault**: 別 tenant から対象試合の fault POST → 404。fault は試合単位で保持し、他 tenant の試合へ影響しない。
- **保存途中故障**: `after_lifecycle_projection` の故障を実 app に注入。終了 POST は 500（非成功）、専用 GET は watermark 1 のまま。イベント・prefix・ledger は全取消され、成功扱いしていない。故障解除後の終了は v1 として成功。
- **再送**: 同一 D5・同一本文・同一 attempt は A5「重複」で、水位・イベント数が不変。
- **env gate**: `PITCHLOG_SPIKE_END_REOPEN != "1"` では lifecycle payload を D5 再掲より前に 501 で閉じる（コード確認）。

### 1-4. 品質ゲート

| コマンド | 結果 |
| --- | --- |
| `cd backend && uv run pytest -q tests/test_spike_end_reopen_ports.py tests/test_sync_first_ball_registration.py tests/test_sync_apply_first_ball_ports.py tests/test_sync_apply_model_ports.py tests/test_roster_self_team_read.py` | **164 passed** |
| `cd backend && uv run ruff check .` | All checks passed |
| `cd backend && uv run ty check` | All checks passed |
| `cd frontend && pnpm test` | **144 files / 3326 tests passed** |
| `cd frontend && pnpm exec vue-tsc --noEmit` | pass |
| `cd frontend && pnpm exec eslint src` | pass |
| `uv run python scripts/check_tenant_boundary_bypass.py --base-ref 660d585...` | ok |
| `uv run python scripts/check_plan_docs_sync.py --plan ... --base 660d585 --head HEAD` | exit 0 |
| `uv run python scripts/check_authz_catalog.py --asset-spec product` | ok（total=1429） |
| `uv run python scripts/check_authz_function_bodies.py --asset-spec product` | OK |
| `uv run python scripts/check_failure_injection_points.py` | OK |
| `uv run python scripts/check_frozen_baselines.py --invariants-only` | OK |
| `uv run python scripts/check_docs_status.py` | 21 documents, 0 violations |

## 2. 成績側へ渡す版の整理（提案・未接続）

本spikeは成績 API / CSV へ接続していない。イベント列から次の版を導出し、専用 GET で返すところまでを実装した。

| 項目 | 本spikeの値 |
| --- | --- |
| 終了確定版 v1 | `version=1`, `d1=2`, `d5=<end v1>`, `stateDigest`, `finalizationDigest` |
| 再開による失効 | `finalizations[0].invalidatedBy = {d1:3, d5:<reopen>}` |
| 再終了 v2 | `version=2`, `d1=4`, `previous={version:1,d1:2}`, 新しい `finalizationDigest` |
| 有効版 | `activeFinalization = v2`。v1 は最新として返さない |
| 再送 | 同一 D5 は保存済み結果を再掲し、版を増やさない |

`finalizationDigest` は `{gameId,version,d1,d5,state}` の正準 JSON の SHA-256。成績側が公開版の同一性キーとして使える形を `proposal.md` §3 に提案した。
ただし **`games.status` は更新していない**ため、現行の成績 SQL が要求する `status='finished'` とは未接続。成績側の `confirmed_ended` / 公開 pointer へ渡すには、終了イベント受理と同一 TX の status 投影・receipt が必要（`proposal.md` §1・§5）。

## 3. 未達・残件

### 3-1. 再開後の記録追加（最重要の未達）

再開後の通常投球・prefix 読取は接続していない。現行 v3 play prefix projection は、同一 PA の `pa_start_source` 以降に `event_kind <> 'play_input'` のイベントがあると `prepare_play_prefix_projection` で拒否する。終了・再開は D1 を消費するため、再開後の play は次の bridge なしには保存できない。

- 本spikeの画面は再開後に「製品 prefix 境界が非 play イベントをまだ橋渡ししないため未接続（残件）」を明示する。
- E2E は再開後の play を **実行していない**。終了→再開→再終了は成立するが、要求された「再開→記録追加→再終了」の記録追加部分は未達。
- 必要案は `proposal.md` §4（bridge checkpoint か、ライフサイクルを D1 列外へ移すか）。

### 3-2. 9回制の完了による自動終了は未実測

対象試合は `regulationInnings=9` の非同時点試合だが、E2E は 1回表の本塁打後に **FR-010 の早期終了宣言**（日没・時間切れ等を想定）で終了した。9回を完了した自動終了検知（FR-005/T2）や、コールド・サヨナラ・タイブレーク・引き分けは未実測。
本spikeの終了条件は「9回制・進行中・非同時点」の内容検証だけで、T2 の終了検知を再計算していない（既存の保存済み T1/T2 を再利用）。

### 3-3. `games.status` と終了後ロック

- `games.status` は `in_progress` のまま（E2E の DB 監査で確認）。
- 終了後の play/substitution/tiebreak を P1/P2 入口で fail-closed にする製品投影は未実装。
- 終了後修正（P3）は `finished` のまま許可する既存仕様との整合が必要。
- 本spikeの `spike_end_reopen_ports` に置き場所の候補はあるが、DB 更新 operation・認可 catalog・route registry の正式登録が必要なため提案に留めた。

### 3-4. 画面の再送保持

サーバーは D5 冪等を満たすが、画面の `postEndReopen` は毎回新しい D5、panel は毎回新しい attempt を生成する。ACK 喪失時に画面から同じ D5/attempt を再送する経路は未実装。E2E の「重複」は元 HTTP 要求の raw replay で確認した。

### 3-5. 故障時の 503 写像

`after_lifecycle_projection` の注入故障は app で 500 になった。イベントは全取消され、クライアントは成功扱いしないが、製品の一時障害としては 503 へ写すのが望ましい。E2E は 500/503 を許容し、watermark 不変を確認している。

### 3-6. 画面の truncated 表示

512 件超の履歴では `truncated=true` を返し、status を「履歴上限のため終了状態を確定できません」、終了/再開ボタンを無効化する。ただし `lifecycle-version` / `finalizations` は先頭 512 件由来の部分データを表示し続ける。完全な製品接続では、最終ライフサイクル行の専用読み取りか、truncated 時の確定版非表示が必要。

### 3-7. テスト・証拠の限界

- E2E の TLS は隔離 loopback の自己署名証明書で `ignoreHTTPSErrors: true`。実機の信頼済み TLS の証拠ではない。
- 実端末（iOS/Android）・実運用ネットワーク・実運用 DB は未検証。
- full backend 非DB実行は開始点由来の `tests/test_product_authz_provisioning.py::test_current_sync_roles_have_strict_all_attribute_collision_sql` が 1 件失敗する。`pitchlog_recording_vocab_fn_owner` を期待集合へ追加していない 660d585 の既知差分で、後続 `82557119` では解消済み。本枝の退行ではない。
- 409 経路は純粋試験で `SpikeEndReopenRejected` を 1 件固定した。実 DB の 409 応答は未実測。
- 再開後の play 追加、9回完了、コールド、サヨナラ、タイブレーク、引き分け、終了後修正は未実行。

## 4. 再現手順

### 4-1. 固定 HEAD の確認

```bash
git -C ~/projects/pitchlog-worktrees/feature-mvp-game-lifecycle-spike rev-parse HEAD
# bceba327beedcf473ac7ae1c3eb018da17c50827（コード・証拠固定 HEAD）
git -C ~/projects/pitchlog-worktrees/feature-mvp-game-lifecycle-spike status --short
```

### 4-2. 純粋・品質ゲート

```bash
cd ~/projects/pitchlog-worktrees/feature-mvp-game-lifecycle-spike/backend
uv run pytest -q tests/test_spike_end_reopen_ports.py \
  tests/test_sync_first_ball_registration.py \
  tests/test_sync_apply_first_ball_ports.py \
  tests/test_sync_apply_model_ports.py \
  tests/test_roster_self_team_read.py
uv run ruff check .
uv run ty check

cd ../frontend
pnpm test
pnpm exec vue-tsc --noEmit
pnpm exec eslint src
```

### 4-3. 実画面 E2E

自己署名 TLS を `/tmp` に用意し、実 app / Vite / owned PG を起動する pytest を実行する。

```bash
mkdir -p /tmp/opencode/pitchlog-lifecycle-tls
cd /tmp/opencode/pitchlog-lifecycle-tls
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem \
  -days 2 -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1'

cd ~/projects/pitchlog-worktrees/feature-mvp-game-lifecycle-spike/backend
PITCHLOG_E2E_TLS_CERT_PATH=/tmp/opencode/pitchlog-lifecycle-tls/cert.pem \
PITCHLOG_E2E_TLS_KEY_PATH=/tmp/opencode/pitchlog-lifecycle-tls/key.pem \
uv run pytest -q tests/db/test_spike_end_reopen_screen_e2e.py
```

E2E は実 app コンテナへ `PITCHLOG_SPIKE_END_REOPEN=1` を渡し、実 HTTPS Vite から
`/games/{id}/lifecycle-spike` を開く。試合・開始・本塁打は画面の実 API で作り、
終了・再開・再終了・再送・fault・越境は実 HTTP と DB 監査で確認する。

## 5. 非作者レビュー

- 1 回目: 固定 HEAD `7aa766c4`。P0 0 / P1 3 / P2 11。
  - P1-1 tenant-boundary-bypass 126 件 → `spike_end_reopen` / `SpikeEndReopen` / `PITCHLOG_SPIKE_END_REOPEN` へ rename して解消。
  - P1-2 fault POST の越境 200・プロセス全体 fault → `GameReadToken` による試合所属確認と試合単位 fault へ変更。E2E で越境 404。
  - P1-3 env 未設定でも lifecycle 書込みが開く → `/sync/events` の D5 再掲より前に env gate を追加。
- 2 回目: 固定 HEAD `76ae3ed3`（その後 `bceba327` で V12/409 試験を追加）。
  - 追加 P0/P1 なし。P1-1/P1-2 は解消、P1-3 は新規書込みについて解消。
  - 残 P2 は `findings.md` 不在、409/V12 の試験固定、画面の同一 D5/attempt 再送、truncated の部分表示、E2E の HEAD 整合。本 findings と `bceba327` で 409/V12/固定 HEAD を補完した。残りは §3 に分離した。

## 6. 受理判定

**条件付き可（spike の観測結果としては受理可 / 正式統合は不可）。**

- 成立: 実画面の作成・開始・通常記録、正式 `/sync/events` による終了 v1、同一 D5 再送の重複、再開による v1 失効、再終了 v2、再取得・reload、V12 退避、越境 GET/fault 404、故障時の全取消。
- 未達: 再開後の記録追加（prefix bridge）、`games.status` / 終了後ロック、成績 API/CSV、9回完了・コールド・サヨナラ・タイブレーク・引き分け、画面の同一 D5/attempt 再送、fault 500→503、truncated の部分表示。
- 正式統合の前提: `proposal.md` の契約採否、`games.status` 投影と終了後ロック、非 play イベント bridge、成績側の confirmed_ended 接続、実端末/実運用 TLS の受入。
