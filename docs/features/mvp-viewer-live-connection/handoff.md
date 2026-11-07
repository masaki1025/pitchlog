# 閲覧ライブ接続 引渡し

## 固定点

- 固定HEAD: `5cb4407d2f4df63428f15d8da8c576ff684e5a16`
- ブランチ: `feature/mvp-viewer-live-connection`
- worktree: `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-viewer-live-connection`
- コード最終HEAD: `e71c36dbaf21c0415bb5fec5527fc8f73b38b9f1`（このhandoff文書のコミットはdocs-onlyで、その次）
- 共有接合patch: `docs/features/mvp-viewer-live-connection/patches/shared-integration.patch`
- patch SHA-256: `270683c7f85613f82f2f2b6463387dbf47d6dbfaaf11c4adf09086f432bc7968`

## 完成した利用者操作

1. 同一チームの共有アカウントで別ブラウザcontextからログインし、記録権・端末登録・同期送信なしに試合を閲覧する。
2. スコア、回・表裏・outs、走者、出場選手、1球履歴を表示する。
3. 記録端末の保存後、正常通信時はサーバー保存ACKから10秒以内に自動表示する（実測1532ms）。
4. 最終取得成功時刻、更新中、未更新、閲覧不可を区別する。
5. 通信断・復帰・reload後はサーバー確定値へ戻り、他端末の未送信値を保存済みとして表示しない。

## 変更パス

### featureブランチ（共有pathの直接変更なし）

- `backend/src/pitchlog/repositories/viewer_probe.py`
- `backend/src/pitchlog/repositories/viewer_read.py`
- `backend/src/pitchlog/repositories/transaction.py`
- `backend/src/pitchlog/repositories/started_snapshot.py`
- `backend/src/pitchlog/repositories/ordinary_prefix_read.py`
- `backend/src/pitchlog/repositories/nonplay_prefix_read.py`
- `backend/src/pitchlog/api/routers/viewer.py`
- `backend/src/pitchlog/authz/viewer_read_sql.py`
- `backend/tests/test_viewer_probe.py`
- `backend/tests/test_viewer_read_sql.py`
- `backend/tests/test_started_snapshot.py`
- `backend/tests/db/test_viewer_live_owned.py`
- `backend/tests/db/test_viewer_screen_owned.py`
- `frontend/src/api/viewerGame.ts` / `.spec.ts`
- `frontend/src/screens/GameScreenViewerLiveController.ts` / `.spec.ts`
- `frontend/src/screens/GameScreenViewerLive.vue` / `.spec.ts`
- `frontend/src/screens/GameScreenViewerLive.e2e.ts` / `.playwright.config.ts`
- `docs/features/mvp-viewer-live-connection/plan.md`
- `docs/features/mvp-viewer-live-connection/patches/README.md`
- `docs/features/mvp-viewer-live-connection/patches/shared-integration.patch`

### 共有接合patchが変更するpath

- `backend/src/pitchlog/api/app.py`: 閲覧router登録
- `backend/src/pitchlog/api/tenant_access.py`: C2照合operation追加
- `contracts/authentication/cookie_identity_v1.json`: 同token Cookie対象operation追加
- `backend/src/pitchlog/authz/{ordinary_pitch_product,terminal_pitch_product,runtime_contract}.py`
- `backend/src/pitchlog/repositories/{function_operations,operation_registry,repository_contract}.py`
- `contracts/authz/product/ddl-elements.json`
- `contracts/authz/product/function-bodies/manifest.json` と閲覧SQL body 2本
- `contracts/tenant_boundary/{repository-contract,runtime-authz-contract}.json`
- `frontend/src/router.ts`: `/games/:gameId/view`
- `frontend/src/screens/GameScreenEntryNavigation.ts`: 認証後戻り先
- `frontend/src/screens/GameScreenEntry.spec.ts`: 戻り先の有限形を検査
- `backend/tests/test_api_app.py` / `test_api_conventions.py` / `test_authz_repository_contract.py` / `test_function_operations_boundary.py` / `test_roster_self_team_read.py` / `test_stats_native_function_registration.py` / `test_terminal_pitch_product.py`: 閲覧route/関数/token/C2対象の期待値

## 実装要点

- 3秒ごとに `/games/{id}/viewer-head` の小さな版probeだけを取得し、版変化時だけ `/games/{id}/viewer` を取得する。全試合・全イベントの定期全件取得はしない。
- 本体はRR READ ONLY + `GameRead`/`RecordingGenerationRead` と閲覧専用有限page関数だけを使う。行ロックreaderを閲覧から呼ばない。
- 履歴は最大25件/page。v3は最新25件から旧pageへ遡り、境界のsentinelをcursorにして有限に読む。非playは旧pageから新pageへ進む。
- controllerは認証世代・tenant・gameの組で旧応答を破棄し、AbortControllerで中断する。401/404/503/通信断は「未更新」または「閲覧できません」へ閉じ、保存成功・更新完了に読み替えない。
- 画面は常に「サーバー確定分のみ。記録端末の未送信分は含まれません。」を表示する。
- 公開API DTOは同期語彙を出さず `version`（不透明値）を使う。

## 検証結果

### 1. 単体試験（実HTTP/DB/ブラウザを含まない）

featureブランチ（共有patch未適用）:

```bash
cd backend
uv run pytest tests/test_viewer_read_sql.py tests/test_viewer_probe.py \
  tests/test_started_snapshot.py -q
# 80 passed
uv run ty check
# All checks passed

cd ../frontend
pnpm exec vue-tsc --noEmit
# 0 errors
pnpm exec vitest run src/screens/GameScreenViewerLiveController.spec.ts \
  src/screens/GameScreenViewerLive.spec.ts src/api/viewerGame.spec.ts \
  src/screens/GameScreenEntry.spec.ts
# 94 passed
```

共有patch適用済みclean worktree（`/tmp/opencode/viewer-patch-check`、HEAD `706e9f2e` + patch）:

```bash
cd backend
uv run pytest tests/test_viewer_read_sql.py tests/test_viewer_probe.py \
  tests/test_started_snapshot.py tests/test_api_app.py \
  tests/test_api_conventions.py tests/test_authz_repository_contract.py \
  tests/test_terminal_pitch_product.py \
  tests/test_stats_native_function_registration.py \
  tests/test_function_operations_boundary.py -q
# 530 passed
```

### 2. 実HTTP・実DB（owned PG・実app role・C2）

```bash
cd backend
export PITCHLOG_E2E_TLS_CERT_PATH=/home/ymdms/.cache/pitchlog/viewer-live-connection-author-20261106/tls/cert.pem
export PITCHLOG_E2E_TLS_KEY_PATH=/home/ymdms/.cache/pitchlog/viewer-live-connection-author-20261106/tls/key.pem
flock -x /home/ymdms/.cache/pitchlog/test-coordination/owned-pg-browser-network.lock \
  -c 'uv run pytest tests/db/test_viewer_live_owned.py tests/db/test_viewer_screen_owned.py -q -s'
# 3 passed in 354.61s
```

確認内容:

- 別Cookieの同チーム閲覧loginで、記録権・端末登録なしに `/viewer-head` と `/viewer` が成功。
- 未認証 `/viewer-head` = 401。
- 可視だが確定世代のない試合 = `/viewer-head` と `/viewer` とも503。
- 別tenantの `/viewer` = 404。
- 2球保存・終了版の保存済み表示。
- 4球を `limit=3` で取得し、page1=第2〜4球、page2=第1球、次cursorなし。

### 3. 実HTTPS・2ブラウザcontext

- 記録側: 新規UI作成→開始→1球保存（実POST）。
- 閲覧側: 別Cookieでlogin→`/games/{id}/view`→自動表示→reload→offline→復帰→不存在404。
- 実測:
  - 保存ACK→閲覧表示: **1532ms**
  - 通信断→未更新検知: **3310ms**
  - 復帰→サーバー状態表示: **2815ms**
- 閲覧contextのAPI要求は全てGET。`/devices/enroll`・`/start`・`/sync/events`・`/sync/attempts/recover` は0件。
- 生ログ: `/tmp/opencode/pitchlog-screen-e2e/viewer-https-playwright.log`

## 再現手順

```bash
# 1. 固定HEADからfeatureブランチworktreeを作る（既存worktreeを使う場合は不要）
git worktree add --detach /tmp/viewer-check 5cb4407d2f4df63428f15d8da8c576ff684e5a16
cd /tmp/viewer-check
git checkout feature/mvp-viewer-live-connection

# 2. 共有接合patchを適用
git apply docs/features/mvp-viewer-live-connection/patches/shared-integration.patch

# 3. 単体
cd backend && uv run pytest tests/test_viewer_read_sql.py tests/test_viewer_probe.py \
  tests/test_started_snapshot.py tests/test_api_app.py tests/test_api_conventions.py \
  tests/test_authz_repository_contract.py tests/test_terminal_pitch_product.py \
  tests/test_stats_native_function_registration.py \
  tests/test_function_operations_boundary.py -q

# 4. 実HTTP/DB + 実ブラウザ（共通lock必須）
export PITCHLOG_E2E_TLS_CERT_PATH=/home/ymdms/.cache/pitchlog/viewer-live-connection-author-20261106/tls/cert.pem
export PITCHLOG_E2E_TLS_KEY_PATH=/home/ymdms/.cache/pitchlog/viewer-live-connection-author-20261106/tls/key.pem
flock -x /home/ymdms/.cache/pitchlog/test-coordination/owned-pg-browser-network.lock \
  -c 'uv run pytest tests/db/test_viewer_live_owned.py tests/db/test_viewer_screen_owned.py -q -s'
```

## patch

```bash
sha256sum docs/features/mvp-viewer-live-connection/patches/shared-integration.patch
# 270683c7f85613f82f2f2b6463387dbf47d6dbfaaf11c4adf09086f432bc7968
```

適用順・含むpathは `patches/README.md` を参照。patchはfeatureブランチに直接コミットせず、接合確認用の一時worktreeだけに適用する。

## 未達・既知の制約

- 共有router/認可catalog/contractsはfeatureブランチに直接変更していない。製品へ入れるにはpatchの正式受理が必要。
- 固定HEADの全件backend suiteは既に赤（`DERIVED_FIELDS_STALE`、複数のauthz/tenant model/migration検査）。clean fixed HEADでも再現し、本featureの変更起因ではない。全件greenを主張しない。
- 全件frontend suiteは `GameScreenPitchCommit.spec.ts` の1件がclean fixed HEADでも失敗（本featureと無関係）。
- 実ブラウザE2Eは隔離loopback HTTPSで、実機の信頼済みTLS・本番性能の証拠にはしない。
- 終了済みv3 lineupの閲覧は既契約どおり非対応。終了版はnonplay lifecycleの閉契約だけを表示する。
- 記録端末の未送信件数をサーバーから動的検知する機構は現MVPにない。画面は常時注記し、viewer自身の通信不能だけを未更新として示す。
- PR作成・マージ・正式CI・人間確認は主担当へ渡す。本作業は通常pushまで。

## 独立レビュー

独立read-onlyレビューを実施し、P0なし。P1指摘（API同期語彙、API経路試験、入口ラベル、終了半回）と主要P2（paging方向、live region、不正gameId、response_model、GET限定、非play成功経路、patch契約検査）を反映済み。
