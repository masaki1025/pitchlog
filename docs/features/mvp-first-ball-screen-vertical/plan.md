---
feature: mvp-first-ball-screen-vertical
status: active
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

### 接続時に判明した供給不足の最小追補（2026-10-30、PO委任Codex判断）

- `frontend/eslint.config.js`: 正規wrappers自身を誤拒否する一般patternだけを修正。artifact/ドメイン正本への直接import禁止は維持し対向検査を追加する。
- 球種の実tenant供給は未提供。専用 `GET /vocabularies/pitch-types` と固定category/disabled/tenant/limit+cursorの新read token、key/display_nameの閉DTO、C2・認可/登録資産候補を同単位で追加する。大会read tokenを他categoryへ転用しない。既CAP再利用、7.7正式受理は隔離候補成功と区別する。固定語彙を製品へ焼き込まない。新規repo/service/router/schemaと対応試験、既operation_registry/app/tenant_accessおよび関連正式資産の必要最小追随を編集範囲とする。意味仕様・保存保証・MVP射程は変更しない。

### 実画面の接合位置（2026-10-30、PO委任Codex判断）

未接続の汎用draftへ実経路を重ねず、既 `GameScreenRecordedRestore.vue` が取得した同じinitialを新規 `GameScreenFirstBall.vue` / `GameScreenFirstBallController.ts` と同specへ渡す。既StrikeZone・実球種read・正式provider・queue/ACK/排他を利用する。ACK後は同じrestore.reloadを呼び、recordedへ変わるとフォームを閉じる。未応答/reloadでは旧slot/同attemptを再送しcommit再呼出しで新D1を作らない。専用初球フォームの実前提で確定を許可し、未接続の汎用GameScreenの常閉ゲートは維持する（MVPの全操作接続は後続として残る）。

球種供給の実DB受入は `backend/tests/db/test_pitch_type_options.py`（同owned fixture、実2tenant login/Cookie/C2/正式token）で行う。既画面E2EとDB・port・tmpを分離する。

実HTTPS初回で開始応答後も準備中providerが古い表示を保持し復元入口が出ない接合欠陥を検知。`GameScreenEntryRecordHost.vue` に開始応答保存(received)後の既provider.retryを接続し、実サーバー結果によって既復元入口へ移す（状態成功を合成しない）。同specを追加する。

HTTPSで初球保存/同一要求再送後のreload停止を検知。`GameScreenEntryRecord.vue`・`GameScreenRecordedRestore.vue` と同specのoptional Boolean省略値を明示undefinedへ是正し、保存開始の存在を照合して自動取得する既hookに到達させる。明示falseは従来どおり自動取得しない。

### 正式認可登録の追補と出典母集合の受理（2026-10-30、PO委任Codex判断）

実画面初球達成後の正式整合として `contracts/authz/requirement-claims.json` と同lock、route-registry/http-route-matrixと同lock、必要auth-catalog lock/oracle seal、`scripts/check_authz_catalog.py` と新 `tests/test_authz_first_ball_routes.py` を直列追随する。既187auth_claim全field/digestとclosed-world参照は不変。source候補9435cd0e…は非作者REPORT7c9b14a0…により1429行分類/対象blob/決定digest一致を確認し委任受理。route/checker/pytestは別の非作者REPORTe536708c…/c2a44cd3…に従い拒否条件を保持した有限追加のみ。rootで前後値を保全し正式CLIを段階実行、途中拒否を全体成功へ読み替えない。本人実値確認/署名の代記はしない。正式7.7とoracle完了は別途検査する。

初球実証後の手動確認用に `backend/tests/manual_e2e_hold_support.py` と非DB unit `test_manual_e2e_hold.py` を追加し、実E2Eの全検査後だけ任意のloopback保持を呼ぶ。既定0、明示最大3600秒、資格/鍵ログ禁止、終了は既owned cleanupへ委譲する。製品動作・保証・運用公開を変更しない。

認可oracle再封印では、step4入力8資産を固定commitへ揃えた後、`oracle-seal.lock.json.oracle_commit` と既封印6資産（ddl-elements/rejected-configs/claim-mutant-map/attack-tree/boundary-proposal/verification-evidence）の `oracle_context.oracle_commit` だけを同commitへ追随する。既oracle意味本文・期待値・承認履歴は変更しない。前後の8blob一致と6資産のcontext以外不変を非作者照合後、正式 `--reseal-oracle` を実行し通常CLIで確認する。7.7や実行時oracle成立の代用にはしない（PO委任によるCodex主担当判断）。

正式CLIが要求する `contracts/authz/frozen-baselines.json` のoracle_input系列も本単位の7.7対象へ含める。既履歴を保持し、実製品統合Draft PR #189の受理ID、旧8a40519d→固定e4f53dabの完全前後値・根拠・Codex主担当の委任判断を1record追記する。単なるcontext置換では通らない拒否条件を保持し、独立差分確認後に再封印へ進む。

### CI型検査の有限是正（2026-10-30、PO委任によるCodex主担当判断）

既step5の必須CI是正として、PR189固定5ee01162のbackend job124047601114で確認した28型診断を、隔離fix/mvp-first-ball-type-checkで修正する。編集対象はbackend/src/pitchlog/api/routers/sync.py、backend/tests/db/test_first_ball_vertical_http.py、backend/tests/db/test_screen_start_e2e.py、backend/tests/test_e1_receipt_binding.py、backend/tests/test_recorded_snapshot.py、backend/tests/test_sync_apply_replay_before_binding.py、backend/tests/test_sync_apply_wire_source.py、backend/tests/test_sync_first_ball_registration.pyのexact8。runtime検査/認可/拒否順/保存/不正入力の実行やassertは保持し、既型契約との整合/テストの実shape narrowing/意図的不正入力の明示castに限定する。Anyやignore追加、検査対象除外、正常化で不正例を消すことは禁止。実挙動変更が必要なら範囲外として返す。型検査/関連pytest/ruff/formatと非作者確認後に保存する。正式frozen sourcepinへ影響する差分は別に実再導出し、型通過を受理や最終CI成功としない。主WT/台帳/共有DB/Git refsへの並行書込なし。

型修復のsource保存判断（2026-10-30、PO委任によるCodex主担当判断）: 全8path packet SHA2dc25b49651388e1678e318e9851d0a7fe1c527be5f6493c4206f1689062ae9eと実byte、非作者REPORT e9a1ef8af703d556abbc6aa7f0089143c432d05cd1bcd32af870c65741a651c5（P0/P1=0、独立291成功・backend全体ty成功、製品型erase AST不変）を照合して採用。検査除外/Any/ignoreなし、既不正入力/readonly代入実行/全assert維持。rootは型修復8pathの保存を承認し、handler sourcepin/正式7.7・最終CIは別未成立とする。本人逐行確認/署名ではない。

### PR189の実9関数・親登録を閉じる最小追補案（2026-10-31、主担当採否前）

固定ad6588b1の実registry9に対し正式候補8のread_device_state欠落、旧star/BigInteger検査不整合、
旧source pinと未受理pending重複を同じ初球候補内で追随する。CAP36/token64を保持し、
通常投球のordinary7関数/INSERT/専用admission/bridge/migrationを親へ持ち込まない。

編集閉集合の候補はcache `pr189-registration-scope-20261031/exact-scope.json` の26pathと、
既公式射影から導出する必要history-snapshotsだけ。実9登録を同object/SQL/IO/CAP不変の
finite directCallへ正規化し、checkerは親BigIntegerの実exact AST形だけを追加する。
unknown/star/dynamic/Float/Textを許可しない。既source pin/開始7path/ledger/段階起動5helperは
実source全site・署名/API/現役割境界へ限定追随し、旧legacy/受理188全prefixを保持する。
再交付所有helper935のTB0011点とwriter/Port参照のTB0021path7は別exact登録とし、
未知owner/型/path/hashと自己申告hash更新によるbody短絡を拒否する。

旧private prepare用途名だけの明確化は既採用修復を最小移植し、旧D1=1/wire/lease/journal
動作を変えない。source/契約/checkerの実編集はこの閉集合への主担当承認後。
実brokerの旧API/再輸出13所見は黙って許可せず、188/dccとの実差分へ分離し必要時その範囲だけ戻す。
未受理rowは原文保全してcandidateだけ正規化する。正式基線/7.7/受理/sealは未成立でroot直列。
checkerの外部byteが動く8資産は実188基線から最終値を1回導出し、既に動いた識別値を
同じ候補内で無意味に増やさない。子190のbefore/値は親採用後に再導出する。

PR189親修復のsource着手承認（2026-10-31、PO委任によるCodex主担当判断）: 実ad6588b1とscope55e55d2f7c48914c4d719c91c9f9a98d5aabd41d99fbd71cec2ffdee1ae1f773、既child修復の限定レビュー系列5963fb36…/538efca0…を根拠に親に適合する登録修復候補の実装を指示する。新testpathは作らず既登録test_check_tenant_boundary_bypass.py内へ専用関数群を追加する。repository実9関数への正規追随でruntime派生が必要な場合だけruntime-authz-contract.json/既runtime_contract.pyを加え、approved-scope.jsonの限定27path＋公式必要snapshotを対象とする。CAP36/token64/SQL/IO/旧legacy/受理188prefix/全旧拒否を保持し、child ordinary実装は混入しない。全9射影/外部byte/前後と源hashは最後の安定候補で一括導出、識別値は実変化に応じ同未受理候補で不必要に反復繰上げない。runtimeが無変化なら未編集でよい。

旧private prepare用途名は逆ASTで意味不変確認、所有helper1/Port7の新登録はfullbody固定と自己申告hash更新付き削除/追加/短絡拒否を必須とする。broker旧13は188/dccとの差で新規なしとしたcache診断を正式基線成立へ読み替えず、未知API許可にしない。candidate pendingだけ原文保全して正規化し、legacy/正式受理行は改変しない。独立source確認・実前後7.7・親実develop統合/最終CI前に正式受理/reseal/mergeを行わない。作者は隔離候補だけを編集し、root唯一の正式writer/refs/台帳/共有DB/PG境界を保持する。

親既frozen外部入力の正式派生追随候補（2026-10-31、PO委任によるCodex主担当判断）: 実188dccと親ad658の既外部2byte（backend/tests/test_api_conventions.py/tests/test_check_authz_catalog.py）差が存在し、本修復で両者は未編集。frozen-inputsの同既fieldを保持したままcontract_revision6→7を今回候補に加えることを許可し、全9射影/必要snapshotを実byteで再導出する。旧6は188受理prefix/旧snapshotとして保持、正式受理行/台帳を変更しない。追加編集はcontracts/tenant_boundary/frozen-inputs.jsonのrevisionだけ、機械的派生が不可分なら具体field根拠を返す。新1field差と全前後を別候補追補として固定し、既source137/494検査を不必要に全反復しない。実基線/7.7採否/root正式writer/最終CIは別条件のまま。
