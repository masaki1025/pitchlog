---
feature: mvp-first-ball-screen-vertical
status: approved
承認: PO委任によるCodex主担当判断（2026-10-30、32dccc90起案＋本限定追補、非作者coordinate_gate_reviewの実source照合P0/P1=0を根拠）
重さ分類: コア領域
branch: feature/mvp-first-ball-vertical
created: 2026-10-30
計画レビュー周回: 0
確定ゲート周回: 0
---

# 実画面から初球ボールを保存・再取得する接続計画

## 目的・基線

基線 `2c87758d1cbf0b5e75acd03e04b480ed4ce7cd3f`。同じ統合候補・同じowned PG/実app/実broker/実ブラウザで、新規作成→開始→初球ボール確定→ACK→サーバー再取得→reloadを通す。利用者が入力した1球が実DBに1件保存され、サーバー由来afterがballs=1/strikes=0/history=1、得点・アウト・走者不変となることを受入とする。

作成・開始・記録後GET・開始資格の耐久保存・記録後復元は既存実装を使う。APIで事前に保存した球を復元する既存E2Eは回帰検査として残し、本受入には数えない。初球ボールのみを今回の接続対象とし、取消・訂正・2球目以降は未対応として明示する。MVP全体の対象は縮小しない。

## 着手・採用条件

- 座標計画 `course-coordinate-single-operation/plan.md` の7.3ゲート成立と対象版の委任承認、同一artifactの製品operation・pin・必要検査の成立を先行条件とする。本計画は同ゲートの承認を代替しない。ただし座標に依存しないwire codec・attempt耐久保存・既transportヘッダ接続は、本計画承認後に先行できる。quantize呼出・画面封鎖解除は座標条件成立後に限る。
- 本計画の非作者レビューとPO委任による主担当承認を記録して製品コードへ着手する。承認欄は主担当が実際の対象版・日時・根拠を確認して更新する。
- 認可・記録権・RG1・原子性・冪等性・再送・不明結果の既契約は維持する。新たな意味仕様が必要なら判断票へ分離し、その機能は成功扱いにしない。
- 座標単位と共有ファイルの編集を直列化する。独立レビューは候補作成者以外が固定HEAD/差分SHAで実施し、P-6 blindとは呼ばない。

## 実装境界・正規供給

- 計算は配布された `PitchlogDomain.deriveFirstPitchWithContinuation` のみ。`GET /started` initialのbefore/rulesから要求を作り、応答のT1/T2/履歴差分をそのまま使う。球数・得点・フラグ・T2を画面側で再計算しない。
- 座標は成立済み `PitchlogDomain.quantizeCourse` の出力を使用。既存wrapper `frontend/src/lib/generated/wrappers/domainArtifact.ts` はpingだけのため、必要operationの存在・封筒検証を追加する。計算本体をwrapperへコピーしない。
- V7は既 `backend/src/pitchlog/sync/first_ball_payload.py` のexact4（formatVersion/observations/participants/calculation）、calculationは `domainrt/first_ball_projection.py` のwireと全項目を一致させる。V8は同artifact応答のhistory difference。frontendの新codecは構造・正準wireの変換だけを担当し、ドメイン結果を補わない。既fixtureはshape照合に使用し、固定計算結果の製品供給に使わない。
- 実名簿/lineupから初打順の打者と守備側投手・捕手を選ぶ。観測は画面選択の実tenant球種、ボール結果、座標。未入力の球速・構え・打席側は契約どおり欠測とし推測しない。正式な球種供給が無い場合は既preparation-options等の実tenant限定供給を照合し、取得不能なら確定を閉じる（試験値を画面に焼き込まない）。
- `GameStartPersistence.readDevice/readStart` の同tenant/gameの実資格・開始応答からD4/V12を読む。保持資格は現在の権利の証明にせず、実サーバーが照合する。
- 送信ヘッダは実route `api/routers/sync.py` の `X-Pitchlog-Device-Id` / `X-Pitchlog-Device-Credential` / `X-Pitchlog-Sync-Attempt`。別名を新設しない。資格・V12・原要求をログへ出さない。
- D02=Aの1球排他を `commitPitchEvent` で利用し、D1採番/追記の不可分性は既 `DurableQueue`、A5遷移は既 `ackAdapter`/`queueTransition` に任せる。
- attemptは送信前に端末へ耐久保存する。同一要求の再送・reloadで保持した同じattempt/D5/D2/本文を使い、不明結果で新要求へ置き換えない。新規storeは既queue DBと独立した専用DBとし、既queue schemaを無断改版しない。本文の同一性を照合し、ACK適用の耐久完了までは削除・TTL失効させない。資格原値はattempt記録へ複製しない。
- wire ACKは実routeのadvancedD3/eventResultsと任意のplayerIdMappingsを閉検証し、D4/D1/D5と対象slotを照合して既 `AckResponse` へ構造変換する。a5Resultの既canonとの写像とwireにないboundaryResultの正規導出を既契約と照合し、未成立なら適用しない。未知a5Result、不正ACK、409/503、未応答は同期済み/保存成功へ遷移させない。既codecに無い境界結果を作らない。

## 変更対象

既存編集対象（当該接続に必要な箇所のみ）:

- `frontend/src/lib/generated/wrappers/domainArtifact.ts` と同spec
- `frontend/src/api/client.syncEvents.ts` と同spec
- `frontend/src/api/client.ts`（既共通認証/Cookie処理を使ったまま同期POST専用資格を閉じて渡すための最小追補）
- `frontend/src/screens/GameScreenPitchCommit.ts` と同spec（実資格/attemptをtransportへ渡す接続）
- `frontend/src/screens/GameScreenCommitGate.ts` / `GameScreenCommitGate.spec.ts`
- `frontend/src/screens/GameScreenEntryRecordHost.vue` / `GameScreen.vue`
- `frontend/src/screens/GameScreenRecordedRestore.ts` / `.vue` / 同spec（ACK後の再取得接続）
- `backend/tests/db/test_screen_start_e2e.py`

新規:

- `frontend/src/screens/GameScreenFirstBallProvider.ts` / 同spec（実供給の合成）
- `frontend/src/api/firstBallWire.ts` / 同spec（V7/V8/ACKの閉wire codec）
- `frontend/src/lib/firstBallAttemptPersistence.ts` / 同spec（送信前バリア・不明結果の保持）
- `frontend/src/screens/GameScreenFirstBall.e2e.ts` / `GameScreenFirstBall.playwright.config.ts`

既queue・Port・T1/T2・backend成功経路・正式資産を本単位でコピー/変更しない。列挙外の変更が必要なら、原因と最小対象を本計画に追補して主担当が委任判断する。

## ステップ

| # | 実装 | 受入 |
|---|---|---|
| 1 | artifact wrapperとV7/V8/ACK codecを追加。既first-ball payload/combined DTOとの全値照合。実before/rules・名簿から要求を供給するproviderの純合成を追加 | 配布JSで初球ボールのT1/T2を実評価。欠落/余剰/不正UUID/参加者不整合/未対応操作を拒否。固定応答を製品経路へ置かない |
| 2 | attempt耐久保存とdevice/V12/D4供給、既transport/commitの接続 | 耐久保存完了前は送信0。再起動・未応答・同要求再送で同じattempt/D5/D2/本文。異内容付替えと資格欠落を拒否。既排他/採番/queue/ACK試験が維持される |
| 3 | 実画面入力→provider→commitを配線し、必要条件成立時の初球ボールだけ封鎖解除。ACK後に既recorded復元を再取得 | 実資格なし/他タブ/未対応操作/計算失敗/不正ACKは成功表示しない。サーバー再取得失敗時に未検証の旧状態を保存済みと表示しない |
| 4 | owned E2Eを追加して同じ候補・環境で作成からreloadまで連続実測。非作者の最終差分レビューと是正、台帳への証拠固定 | 画面新規作成→開始→ボール確定→実ACK→GET recorded→reloadでballs=1/strikes=0/history=1。同一要求再送でDB play_rows/event/idempotencyが各1件。別tenant/不正資格/不明結果保持の技術検証を併記 |

各ステップを別commitにし、件名に `(ステップ k/4)` を1個付ける。重大指摘未解消や検査失敗を成功へ読み替えない。正式7.7受理・develop統合と隔離候補の成功は別記する。

## 実行・証拠

作業中は変更したspecと関連commit/queue/ACK/復元の影響範囲を実行し、候補固定後frontend eslint/vue-tsc/Vitestと必要backend検査を完了する。座標artifactは同単位のproperties/mutation/host検査結果を固定版で引用する。無関係な既知赤は基線の失敗IDと照合し、新規赤を残さない。

画面E2Eはホストで `env -u PITCHLOG_TEST_ADMIN_DSN -u PITCHLOG_TEST_ROLE_DSN PYTHONPATH=tests:src PITCHLOG_PYTEST_TMPDIR=/tmp/opencode/pytest-tmp-e2e .venv/bin/python -m pytest tests/db/test_screen_start_e2e.py -q --rootdir .`（backend cwd）。node/pnpmとdockerが必要。shared DBへ接続しない。既fixtureのowned DB/実UID/実brokerを再利用する。

記録する証拠: 最終HEAD・差分SHA・実行コマンド・環境・成功/失敗log・画面操作とHTTP順序・実DB件数・サーバーafterとreload表示の一致・独立レビュー対象/採否。台帳の更新は主担当だけが行う。実機/HTTPS運用・全操作・MVP全体の完成とは扱わない。
