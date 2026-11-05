# 走者あり打球の接続spike — 実測報告

## 固定HEAD

- 起点: `feature/mvp-batted-hits@82557119314aebb5db3acb8704f71d1a91f82c9a`
- 専用枝: `feature/mvp-runners-batted-spike`
- 作業worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-runners-batted-spike`
- コードHEAD: `f293cf87750870be93b93063f99d6f254bb1cb40`
- 報告HEAD: 本ファイルを含むコミット（`git rev-parse HEAD`で確認）

## 結論

無走者の既存製品経路を、記録者が明示した走者進塁だけを使って走者あり単打・二塁打へ接続できた。
実HTTPS・実ログイン・実端末登録・実開始・実sync・同一TX・使い捨てPostgreSQLで、次を実測した。

- シナリオA: 一塁走者が単打で三塁へ、打者が一塁へ。after=`first-third`、得点0、安打2、打順3。
- シナリオB: 一塁走者が二塁打で本塁へ、打者が二塁へ。after=`second`、得点1、打点1、安打2、打順3。
- 同一要求の再送は`重複`で、得点・安打・履歴は二重加算されない。
- reload後のafter/runners/history/prefix_ref/page.itemsが保存後GETと一致。
- 別tenantは対象試合の`lineup-prefix`を取得できない（404）。
- 既存のno-runner保存境界試験（越境・語彙・野手・全取消）2件は本変更後も成功。

正本・`contracts/`・共有台帳は変更していない。必要な追補は`proposal.md`へ分離した。

## 再現手順

### 1. 作業枝

```bash
git worktree add -b feature/mvp-runners-batted-spike \
  /home/ymdms/projects/pitchlog-worktrees/feature-mvp-runners-batted-spike \
  82557119314aebb5db3acb8704f71d1a91f82c9a
cd /home/ymdms/projects/pitchlog-worktrees/feature-mvp-runners-batted-spike
```

### 2. artifact再生成

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm build:domain
# 5f4caa1f89963fadbad2664dd245dac94afb91977e525fbd5acf01949a3fcc28 65773 bytes
```

### 3. 隔離PostgreSQLと実HTTPS

- `backend/tests/db/test_runners_batted_hits_screen_e2e.py` の `vertical_database` が
  使い捨てPostgreSQLクラスタ・実appコンテナ・実Vite・実brokerを起動する。
- 実測時はloopbackの自己署名TLSを次のように用意した（証拠は隔離loopback用であり、
  実機の信頼済みTLS検証ではない）。

```bash
mkdir -p /tmp/opencode/pitchlog-runner-e2e
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /tmp/opencode/pitchlog-runner-e2e/key.pem \
  -out /tmp/opencode/pitchlog-runner-e2e/cert.pem -days 2 \
  -subj '/CN=127.0.0.1' -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost'
```

### 4. 実測コマンド

```bash
cd backend
PITCHLOG_E2E_TLS_CERT_PATH=/tmp/opencode/pitchlog-runner-e2e/cert.pem \
PITCHLOG_E2E_TLS_KEY_PATH=/tmp/opencode/pitchlog-runner-e2e/key.pem \
uv run pytest tests/db/test_runners_batted_hits_screen_e2e.py -q -s
```

結果: `1 passed`（Playwright 3 tests passed、DB照合込み）。

### 5. 実測時にだけ使った一時ローカル差分（未コミット・実測後に復元）

正式契約を変更せずに実測するため、次の2点だけを一時適用し、実測後に`git checkout --`で復元した。

1. `contracts/authz/product/function-bodies/functions/FUNCTION:sync_right_api:prepare_play_prefix_projection(...).sql`
   を`terminal_pitch_write_stamp.py`の新bodyへ差し替え。
2. `backend/domain/*manifest.json`の`directTargets[].hash`を新artifact SHAへ差し替え。

この2点は**最終ブランチに含まれない**。正式化は`proposal.md`の別ゲート。

## 実測証拠（最終実行）

Playwrightの`PITCHLOG_RUNNER_SCREEN_RESULT`から抜粋。

### シナリオA: 単打・一塁走者→三塁

- game: `9eccb927-1c20-45b8-a83d-4751f101d877`
- 1球目: `batting-result.single`、before=`empty`→after=`first`、hits 0→1、打順1→2。
- 2球目: `batting-result.single`、before=`first`→after=`first-third`、hits 1→2、打順2→3。
- after:
  - `state.runners=first-third`
  - `state.count.strikes=0`, `state.count.balls=0`
  - `state.outs=0`, `state.half=top`, `state.inning=1`
  - `state.score={home:"0",away:"0"}`
  - `scoreboard={inningScores:{home:"0",away:"0"},hits:"2",errors:"0",strikeouts:"0",walks:"0"}`
  - `battingOrderBySide={away:"3",home:"1"}`
- runners:
  - `{runnerId:"00000000-0000-0000-0000-000000000065", responsiblePitcherId:"...00d2", base:"3"}`
  - `{runnerId:"00000000-0000-0000-0000-000000000066", responsiblePitcherId:"...00d2", base:"1"}`
- 2球目の物理`play_runners`: before走者`...0065`がbase 1、責任投手`...00d2`。
- 再送: 同一request/attemptの再POSTが`a5Result="重複"`。`play_rows`/`operation_events`/`event_slots`/ledgerは2件のまま。
- reload: after/runners/prefix_ref/page.items/last_entryが保存後GETと一致。

### シナリオB: 二塁打・一塁走者→本塁

- game: `72266df5-369e-4090-b613-46b80d05c19e`
- 1球目: `batting-result.single`、before=`empty`→after=`first`、hits 0→1。
- 2球目: `batting-result.double`、before=`first`→after=`second`、hits 1→2、打順2→3。
- after:
  - `state.runners=second`
  - `state.score={home:"0",away:"1"}`
  - `scoreboard={inningScores:{home:"0",away:"1"},hits:"2",errors:"0",strikeouts:"0",walks:"0"}`
  - `state.outs=0`, `state.count.strikes=0`, `state.count.balls=0`
  - `battingOrderBySide={away:"3",home:"1"}`
- runners:
  - `{runnerId:"00000000-0000-0000-0000-000000000066", responsiblePitcherId:"...00d2", base:"2"}`
- 2球目のhistory flags: `得点=true`, `打点=true`, `失点=true`（RBI-08の範囲。追加の因果観測を要求していない）。
- 2球目の物理`play_runners`: before走者`...0065`がbase 1、責任投手`...00d2`。
- reload: after/runners/page.items/last_entryが保存後GETと一致。

### 越境・rollback

- 別tenantの実ログインで`GET /api/games/<game>/started?projection=play-prefix-v3`を実行し、**404**を確認（Playwright 3件目）。
- 既存`backend/tests/db/test_batted_hit_storage.py`を本変更後に実行し、**2 passed**。
  - 同試験は実APIの越境（他tenant語彙・他tenant選手）と、保存境界の拒否時に
    `operation_events`/`play_rows`/`event_slots`が0件のままである全取消を検査する。
  - 走者あり固有の故障注入は別途未実施（下記「未達」）。

## 変更パス

### frontend

- `frontend/src/domain/battedHit.ts`
- `frontend/src/domain/state.ts`
- `frontend/src/domain/lineupPlayPrefixContinuation.ts`
- `frontend/src/domain/publicApi.ts`
- `frontend/src/domain/battedHit.spec.ts`
- `frontend/src/api/lineupPrefixWire.ts`
- `frontend/src/api/runnerAdvanceWire.ts`（新）
- `frontend/src/screens/GameScreenBattedHitObservation.vue`
- `frontend/src/screens/GameScreenOrdinaryPitch.vue`
- `frontend/src/screens/GameScreenOrdinaryPitchProvider.ts`
- `frontend/src/screens/GameScreenRunnersBattedHits.e2e.ts`（新）
- `frontend/src/screens/GameScreenRunnersBattedHits.playwright.config.ts`（新）
- `frontend/public/domain/pitchlog-domain.js` / `.json`（公式builder再生成）

### backend

- `backend/src/pitchlog/domainrt/lineup_play_prefix_continuation.py`
- `backend/src/pitchlog/domainrt/lineup_prefix_source.py`
- `backend/src/pitchlog/sync/terminal_pitch_payload.py`
- `backend/src/pitchlog/sync/terminal_pitch_projection.py`
- `backend/src/pitchlog/authz/terminal_pitch_write_stamp.py`
- `backend/tests/db/test_runners_batted_hits_screen_e2e.py`（新）

### docs

- `docs/features/mvp-runners-batted-spike/plan.md`
- `docs/features/mvp-runners-batted-spike/research.md`
- `docs/features/mvp-runners-batted-spike/proposal.md`
- `docs/features/mvp-runners-batted-spike/report.md`

## 未達・残る停止条件

1. **正式契約は未変更**。V7観測/T1の`applied`と`optional|forced`は候補であり、
   現行`contracts/`では未受理。正式化は`proposal.md`の追補が必要。
2. **artifact pin/manifest/D11は未追随**。新artifact SHA `5f4caa1f...`に対し、
   既存のpin期待は旧`51d4d0f...`のまま。実測時だけmanifestを一時差し替えた。
   そのため既存のD11/pin試験は旧SHA期待で失敗する（実装の失敗ではない）。
3. **SQL関数body契約は未追随**。実測時だけ契約assetを一時差し替えた。
   最終ブランチの`contracts/authz/product/...prepare_play_prefix_projection...sql`は旧body。
4. **走者あり固有の途中故障注入は未実施**。同一TXの全取消は既存storage試験の
   no-runner経路で確認したが、runner payload固有の故障注入は別途必要。
5. **走者アウト・併殺・失策・妨害・第3アウト時機・HR with runners・サヨナラ/コールド・
   取消/訂正・交代・タイブレークは対象外**。D07の既定進塁も二死二三塁の単打1行のまま。
6. **実機の信頼済みTLS・運用環境・全MVP・全NFRは未成立**。実測は隔離loopback。

## 参照した正本

- `AGENTS.md`
- `docs/features/mvp-batted-hits/plan.md`
- `docs/requirements/requirements-pitchlog-2026-07-22.md` FR-003/004/005、付録A-3 RBI-08、付録E-1 ADV-01..04、D07限定行
- `contracts/state-transition/lineup_play_prefix_payload_v1.d.ts` / schema
- `contracts/state-transition/lineup_play_prefix_v1.d.ts`
- `backend/src/pitchlog/authz/terminal_pitch_write_stamp.py`
- `backend/tests/db/test_batted_hits_screen_e2e.py` / `test_batted_hit_storage.py`
