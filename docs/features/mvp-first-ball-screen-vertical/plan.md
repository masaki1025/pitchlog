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

2026-11-01の通常統合追随（PO委任によるCodex主担当判断）: #188/#193統合済みの実develop c2e5e4ddを基線とし、保存済みf294643c（親8be972d8）へCI分割を追加mergeした。生成物は最新正式版を保持して公式helperで再導出する。既backend/tests/test_authz_tenant_binding.pyの同一key/value重複1件は辞書の実評価値を変えず削除する有限修復をステップ4へ追加する。型・認可・冪等性/再送・検査条件は不変、.env/共有DB/古いstashへ触れない。policyの#189 targetは最新基線に既登録であり重複追加しない。受理record/証拠は実PR基線c2e5e4ddと最終差分へ束縛し、古い8be基線や途中版の証拠を使い回さない。

最新develop取込後のruntime再生成（2026-11-01、PO委任によるCodex主担当判断）: 関連初球1518試験は成功したが、全非DB収集4errorと正規authz CLIはDERIVED_FIELDS_STALEで停止。最新正式runtimeを採用した結果、既#189製品DDLにあるsync_fence/sync_fence_api/sync_right_apiの3schema、writer/first_ballの3私有表、12既製品関数の保護登録が未反映だった。正式`derive_runtime_contract_fields`/`asset_digest`/`render_runtime_contract`で既`contracts/tenant_boundary/runtime-authz-contract.json`と`backend/src/pitchlog/authz/runtime_contract.py`だけを再導出する。旧8schema/50表/79関数/role属性を全保持し、実DDLからの追加3/3/12以外を変えない。revisionは実base c2e5e4ddに対する一回分として管理し、最終tenant v2受理で全前後を固定する。手書き生成定数/拒否条件緩和/共有DB適用は行わない。

既実登録の有限接続追補（2026-11-01、PO委任によるCodex主担当判断）: 読取専用診断REPORT5a7c6941…/checks35e27a9e…で、正式repositoryは30CAP/47token/4function、実registryは36CAP/64token/9function（旧全token保持）、旧checkerがStarred/Name登録を拒否すると確認。既fix60f67bf6の同objectを返す `_registered_product_function` 有限5ID方式だけを `backend/src/pitchlog/repositories/operation_registry.py` へ再利用し、既 `backend/tests/test_function_operations_boundary.py` で誤ID/未知/別型拒否と同objectを検査する。checkerの許容構文を拡張せず、関数の署名/権限/登録objectを変更しない。rootは既 `contracts/tenant_boundary/repository-contract.json` と生成 `backend/src/pitchlog/repositories/repository_contract.py` を実登録/正規asset_digestから機械導出、既 `backend/tests/test_authz_repository_contract.py` は全既値保持の64token/9function/36CAP完全一致へ追随する。生成定数の手書き修正・部分集合化はしない。最終受理値/旧source pin2件はsource固定後に正式導出し、同一条件の承認を再取得しない。

有限source pinとprivate名の接合修復（2026-11-01、PO委任によるCodex主担当判断）: 診断cache pr189-source-pin-diagnosis-20261101は、旧ledger17siteをscope/symbol/行本文で現sourceへ1対1照合し、新binding3siteも実_PgLedgerPair.recovery_fence由来の世代照合/intent搬送/資格照合と確認した。transaction ownerは本文AST完全一致で定義866→935。残TB005はSQL APIでないprivate _BindingAuthority.prepareの保守的名前衝突であり、既60f67限定rename案を再利用できる（3Python全ASTをprivate名正規化後一致、wire/journal/SQL全文字列不変の証拠あり）。次の既7pathだけをroot割当の通常step4是正へ追加する: backend/src/pitchlog/durable_rights_ledger/adapter.py、backend/src/pitchlog/sync/control_provider/binding_control.py、backend/tests/test_durable_rights_ledger_contract.py、backend/src/pitchlog/durable_rights_ledger/manifest.json、contracts/tenant_boundary/base-allowlist.json、scripts/check_tenant_boundary_bypass.py、tests/test_check_tenant_boundary_bypass.py。private prepare_writer_binding名と同test stub/期待の必要箇所、manifestの実adapter hashを機械更新する。rename後の正規raw finding20・owner935・全source hashを同一固定版から導出し、旧17の意味保持/新3の由来以外は許容しない。checkerは有限20/同件数文言/同935の追随のみ、汎用unknown許容・検査除外は変えない。候補全前後は新非作者へ渡し、全受理/凍結/corpusは最後に直列化する。

既7builder登録の回復（2026-11-01、PO委任によるCodex主担当判断）: 公式load_contractの正例exact-setが、#189元HEAD ad6588b1に既登録だった試合作成6/球種read1のsymbol/signature/API/fixtureを最新正式base採用で落としたことを検出。source7と正例7はad658から不変であるため、既base-allowlist.jsonのallowed_symbols末尾へ同7宣言だけを元Git blobから機械復元する。新たな汎用SQL許可/未知function許容ではなく既承認builderの限定登録を回復し、旧最新baseの全宣言/順/拒否を保持。fixture削除・exact-set緩和を禁止し、新非作者へ全before/afterと実原典の一致を渡す。

初期統合修復15path採用（2026-11-01、PO委任によるCodex主担当判断）: registration8は非作者REPORTadd58c26…、source pin7＋元builder7復旧は新非作者REPORTdd1a2124…（各P0/P1/P2=0）を実byteへ照合し採用。局所293/ledger非DB201/初球関連1518/FE全2638成功。公式load_contractと認可CLI1429も成功したが、全backend診断の旧private namespace期待・例外契約・schema原典2箇所・旧同期unit fixture等118未了を残す。metadata reviewer初回のDB除外漏れは既存role確認SELECTで停止し作成削除前、実DB成功とはしない手順逸脱として元REPORT/receiptへ保持した。source-adoption/receipt.jsonへ対象15SHA/根拠/実日時を保存。正式tenant v2受理・最終CI/mergeは未了。

認可private3と例外契約の有限是正（2026-11-01、PO委任によるCodex主担当判断）: read-only診断REPORTa76df414…/checks9d86e545…により、旧public50＋sync_fence exact3は実ORM/0037・0038/DDLで成立し、旧schema8/role14/namespace未対応のfixture57失敗と、first_ball_product.validateのnested ACL型検査前countによる例外契約不備を分離した。次の既10pathだけを作者へ割当てる: backend/src/pitchlog/authz/first_ball_product.py、backend/tests/test_authz_product_classification.py、backend/tests/test_schema_manifest.py、backend/tests/test_authz_runtime_contract.py、backend/tests/test_authz_product_database_schemas.py、backend/tests/test_authz_product_roles.py、backend/tests/test_authz_product_control_access.py、backend/tests/test_authz_product_table_rls.py、backend/tests/test_authz_product_table_access.py、contracts/db/schema-manifest.json。ACLの型/shapeをcount以前に拒否し、従来同様ValueErrorとして失敗を閉じる。private正規profile/旧全判断・拒否条件は不変、検査の単純50→53置換は禁止。旧public50＋明示3のschema identity/衝突/全FK/12追加policy/3role全属性/全ACL・ENABLE/FORCEと未知拒否を完全一致で検査する。schema-manifestは旧50全値一致を確認したexact2source_rowだけ、最新baseの現正本quoteを機械復元し、列/制約/追加private3/正本は変えない。旧14role空profileは維持する。新scope/migration/SQL/共有DBへ触れず、source固定後に新非作者レビューへ渡す。

同期受付fixtureとAPI層規約の有限是正（2026-11-01、PO委任によるCodex主担当判断）: read-only診断REPORTadbf2b6e…は旧sync unit9が必須entry_token未供給で業務処理前に停止し、実HTTPは同token供給済みであると確定した。backend/tests/test_sync_apply_apply.py・test_sync_apply_repository_boundary.py・test_sync_apply_source_binding.py・test_api_conventions.py・test_authz_app_layer_surface.py・test_authz_capability_registration.py の既6pathを旧fixture/exact集合追随へ割当てる。unitは既_e1_receipt_scopeを同context/request/source/同local entry_tokenで実際に開きyield receiptを渡す。_receipt_for_entryをpatchしたり製品token既定値を設けたりしない。旧D5/拒否順/lease/実資格/最終commitの検査は保持する。

APIで_broker_generation直接import/内部generation識別子が既禁止語彙へ抵触するため、既backend/src/pitchlog/api/routers/sync.pyへ最小の層分離を行う。新private bridge backend/src/pitchlog/sync/http_recording_key.py は既_broker_generationを一回呼ぶだけで、値生成・認可・例外写像・別codec実装を追加しない。routerから元識別子を除き、dynamic getattr/文字列分割で隠蔽しない。sync route response_model=Noneは新backend/src/pitchlog/api/schemas/recording_ack.pyで既D1 ACKの全キー/値型/既A5状態を閉DTO化し、同schemaをroute宣言だけでなく実_ ack_body（実装名_ack_body）検証にも使用する。現在wireのadvancedD3/eventResults/playerIdMappings・省略条件・D4/D5の既文字列制約を維持し、新UUID強制や未対応P3成功を作らない。出力は既JSONResponseを維持できるが既codecと全response同値/未知state・余剰・bool数値拒否を既backend/tests/test_sync_route_shape.pyへ追加する（編集総数は既6＋router＋新schema/bridge＋既route testの10path）。禁止語彙集合・DTO exact2例外・response_model全件検査は緩めない。新意味承認/正本改版ではなく既wireと層規約への整合であり、候補固定後に非作者へ渡す。


### 2026-11-01 残件fixtureの有限追随（PO委任によるCodex主担当判断）

対象版c97c111a、読取専用診断REPORT f0d8c3f78647553a904c481165053ab88bee0fa455bdc6be33935e0c2dbca474に基づくステップ4の限定追補。ACKは既A5の5状態（受理/重複/拒否/退避/未処理）を維持する。意味・安全条件・CI全件範囲は変更しない。

- 群R（作者1）: backend/tests/test_rg1_lock_contract.py と test_rg1_seed_migration.py は全関数がowned PGを使うためmodule requires_db、test_initial_recording_right_candidate.py は診断で特定した実DB5関数だけ同marker。nodeidと全assert、CI全収集を保持する。test_rg1_operations.py・test_roster_self_team_read.py・test_authz_product_application_steps.py・test_product_authz_migration_batch_role.py・test_product_authz_catalog.py は実正式sourceに対する有限literal追随と不足builtin ACL観測1rowのみ。旧集合・SQL・拒否・順序対向を全保持し、部分集合/常時成功にしない。
- 群S（作者2）: backend/tests/product_authz_other_profiles_cases.py・test_product_authz_other_profiles_cases.py・product_authz_tenant_owned_cases.py・test_product_authz_tenant_owned_cases.py・db/test_schema_audit.py・db/test_product_authz_other_profiles.py。旧public50とseed32全行/主体/FK順を保持し、私有sync_fence exact3をfunction_only分類・汎用DML禁止の別母集合として明示。schema identityは既知private3だけ有限写像、未知/衝突拒否を維持。business uniqueの既31/tenant外5を保持し、採用済み6-1-a exact2 nonce/lease制約だけを追加する。private表をtenant_ownedへ再分類・無許可汎用INSERT・拒否緩和はしない。DB専用sourceを直しても実PGの成功は別途実測まで未成立。
- 群T（作者3）: contracts/authz/product/probe-product-map.json・backend/tests/test_product_authz_probe_product_map.py・test_product_authz_provisioning.py・test_product_authz_failure_injection_points.py・contracts/authz/product/failure-injection-points.json、および必要な既validator backend/src/pitchlog/authz/failure_injection.py（実パス確認後、異なる場合は主担当へ差戻し）。probeは診断の欠落40atomだけを正式asset根拠付きでproduct_onlyへ機械追加し、旧mapping/probe48/旧product_only全値を保持。provisioningは既承認tsk544 plan 362行に従い新profile UNAPPLYのSQL生成/実行前拒否と旧profile挙動双方を検証し、旧7故障点/原子性/往復義務を消さない。有限fake stage・ID引渡し・schema追随のみで製品許可を拡張しない。failure点pinは最終source版へ公式導出し、歴史fixture成功をcurrent未提供の成功へ読み替えない。現validatorが新profile前提だけで旧機能を検査不能なら、必要な最小path/保持証拠を主担当へ提示してから変更する。

三群の編集pathは重複させず、共有plan/正式tenant受理/生成定数/seal/台帳/refsは主担当だけが編集する。各群は影響範囲の非DB検査と全前後SHAを保存後に凍結し、非作者レビューを受ける。pytestは両PITCHLOG_TEST_*_DSNをunsetし、not requires_dbを明示、DB/dockerは別の主担当所有環境まで実行しない。新たなPO意味判断は追加しない。


群Sへの追加exact1path（2026-11-01、PO委任によるCodex主担当判断）: backend/tests/db/test_alembic_migrations.py の既 _index_catalog_contract に後方互換のschemaキーワード（既定public）とpg_namespace照合を追加し、schema auditから明示schemaを渡す。旧呼出/旧返値5項目・全SQLの列順/一意性/述語検査を保持する。namespaceを問わない索引名だけのfetchoneによる同名衝突を拒否し、未知/privateを黙ってpublicへ補完しない。新pure spy/SQL構造対向は既群Sのunit fileへ置き、同名public/private・欠落/未知の拒否を検証する。正式DDL/移行/共有DBを変えず、実PGの成功は未実施として別記する。


oracle基準台帳の限定追随（2026-11-01、PO委任によるCodex主担当判断）: 非作者REPORT9edd03ec…で固定8入力の旧AUTH187/全正負cell/4lock完全保持と3dd1bfa1への技術pin採用が成立。既97行の6oracle_context＋seal追随に加え、contracts/authz/frozen-baselines.json のoracle_input系列へ#189末尾1recordを追記する。旧全history/規範状態/placementsを保持し、旧70684628→3dd1bfa1のprior/new identityと委任判断・根拠のみを記録。公式CLIがboundary proposalの基準版一致を要求するための必須伝播で、既凍結値の手動書換/本人承認代記はしない。生成後8pathは非作者最終差分確認し、正式7.7/全件CIは別に確認する。


root型境界の限定整合（2026-11-01、PO委任によるCodex主担当判断）: 非作者診断REPORTd86078ef…でroot/BE独立venvの既設計と、新import9診断（checker8/test1）を特定。scripts/check_authz_catalog.pyのfirst_ball_productへの8local importとtests/test_check_authz_catalog.pyのasset_spec import1だけへ、既同境界10statementと同じunresolved-import限定注記を追加する。2fileのPython AST100%同一、runtime/全拒否/テスト対象/ルール不変を検査する。新Any・広域ignore・fixture除外・backend全体の検索path追加は行わない。backend本体は別tyで検査するが、rootからの具体的呼出型を完全検査する保証を新たに主張しない。影響試験・root ty/ruffと非作者候補照合後に保存する。


凍結scanの正規移設（2026-11-01、PO委任によるCodex主担当判断）: 通常allow-list追加は禁止のため一切追加しない。公式scanが検出した新35組は、backend5test fileの旧期待30、tests/test_required_set_coverage.pyの歴史anchor1、scripts/check_human_review_signature.pyのordinary4pinである。既値・全比較・負対向を保持して次の2単位へ分離する。

1. test側: backend/tests/test_first_ball_write_stamp.py・test_sync_apply_first_ball_payload.py・test_sync_apply_product_supply.py・test_sync_apply_writer_binding.py・test_sync_right_sql.py、およびtests/test_required_set_coverage.pyの該当固定値だけを独立tracked JSON fixture（backend/tests/fixtures/first_ball_expected_source_pins_v1.json、tests/fixtures/required_set_coverage_legacy_pin_v1.json）へ機械移設する。必要な共通閉readerはbackend/tests/first_ball_expected_source_pins.pyだけ。旧固定期待を製品sourceから再計算せず、元Gitと全値一致/既testの完全比較・未知/欠落拒否を維持する。新35以外の旧allow-list値を移設で除去した場合は、公式scanで消えたexact組だけallow-listから削除（旧残存全byte保持、追加0）する。
2. core側: 独立contracts/state-transition/gate6_t1_ordinary_pitch_pins_v1.jsonへad6588b1の旧4定数（anchor/public_base/record_sha256/schema_sha256）を機械抽出して先にcommitし、非作者全値確認。そのcommitで既8oracle入力が3dd固定byteと同一であることを確認してoracle_inputを当該commitへ追随（同PR189の未正式受理末尾record1件へ最終実値だけ反映）。verifierは既frozen_baselines readerの承認済み単一commitからgit showで固定JSONを読み、exact4key/重複/40・64桁を閉検査する。current JSON/検査対象record/schemaの値・任意HEADへのfallbackは禁止。旧PR187限定/ancestor/旧policy prefix/record-schema hash/拒否条件を保持。読込不明は閉拒否。新frozen系列/比較strategy/検査除外は作らない。

rootはcore verifier/authority JSON/oracle/台帳/allow-listの唯一writer、分離作者はtest側exact9pathのみ。各scopeは候補凍結後に非作者review。文字列分割・走査対象変更・判定緩和で回避しない。正式source7.7/最終CIは最終版で直列導出する。


core pin移設の回帰path（2026-11-01、PO委任によるCodex主担当判断）: tests/test_human_review_signature.pyを追加exact1pathとして旧ordinary対向を全保持し、authority JSON/台帳の欠落・重複・不正型/桁・Git欠落・現JSON改変と自己申告fallback拒否を追加する。verifierはordinary実行時に遅延取得し、reader/authority JSON/凍結台帳も最終HEADへ束縛する。新JSONの先行候補は非作者REPORTd6980069…でad6588b1旧4値完全一致/closed4keyを確認済み（実SHA8c448a69…）。新JSONと実loaderの検証は分離して記録する。


A31/root局所検査の有限是正（2026-11-01、PO委任によるCodex主担当判断）: root認可検査25943成功/34失敗を保全。32失敗は新製品認可readerがSQLAlchemyを必要とするのにroot dev依存が無い環境不足で、pyproject.toml/uv.lockへbackendと同一sqlalchemy==2.0.52をdev依存として固定し、root/BE二環境・lock検査・型対象は不変とする。残2はtests/test_check_authz_catalog.pyのinitial_http限定負対向がdesign_provenance末尾の無関係な新初球行をpop/改変しているため、既initialのprovenance_idを明示選択して同じ欠落/余剰fieldの拒否を検査する。validatorの検査条件を緩めず、旧負対向全件を保持する。追加exact3pathのみ、候補固定後非作者確認。正式認可8入力は変更しない。


移設単位のwriter割当て追補（2026-11-01、PO委任によるCodex主担当判断）: rootはauthority JSON/oracle/凍結台帳/allow-listの唯一writerを維持し、stageBのscripts/check_human_review_signature.py・tests/test_human_review_signature.py exact2は単独作者pr189_source_pin_independentへ割り当てる。rootは当該2へ並行書込しない。元4値/旧全拒否を保持した遅延readerと最終HEADのmetadata/reader束縛を実装し、別非作者が最終2pathを確認する。


共通製品DBfixtureの実接合（2026-11-01、PO委任によるCodex主担当判断）: read-only診断REPORTf7633428…で現0038/S3に対する旧0036 assertとcurrent unapply呼出の不整合を特定。製品source/guardを変更せず、backend/tests/db_fixtures.py・db/conftest.py・db/test_product_authz_provisioning.py・db/test_product_authz_failure_injection_points.py・db/test_product_authz_round_trip.py・test_product_authz_provisioning.py・新product_authz_legacy_profile.py・新fixtures/product_authz_legacy_profile_v0036.jsonのexact8を単独作者へ割当てる。

current ownedfixtureは正規advanceS0による0038/S3と公開catalog照合を保って再apply前snapshotを供給し、新profile未提供unapplyを呼ばない。current snapshotは既public全row/field/順を保持し、正式assetの閉schema/table集合へ有限拡張してsync_fence3も含む。未知schemaを包括採用せず、外部供給経路・主体・owned cleanup・seedアクセス閉鎖は不変。current pre-snapshotのrole期待は正式全roleへ追随し、旧owner-only/fresh-role生成の義務は次のlegacy側へ残す。

旧0036profileは0033/S1 fixtureとは別のowned cluster/fixtureで供給し、Git c2e5e4ddの採用済み全JSON/380SQL/steps/必要migrationを固定metadata JSONから忠実に読む。既Tの独立照合済みlegacy組立を共通helperへ移す。期待を現UTから再生成せず、実DDL/公開provisioning/実catalog inspectorを用いreport.ok等を固定しない。current advanceS0の0038を偽装せず、旧0033→pre-rule→正規0036→旧fullapplyを実施する。旧7checkpointの実A-B-C全snapshot/rollback、unapply/migration往復/再applyと別DB基線の全assertを保存し、current APPLY5点/UNAPPLY SQL前拒否を別対向として追加する。current成功を旧未実測へ読み替えない。

作者はまずcache-only候補と非DB検査を準備し、rootのbackend全非DB回帰r4完了後に実WTへ適用する（実装順の承認は成立済み、同sourceを検査中に書き換えない）。固定sourceは非作者review後にroot所有PGで実証する。共有DB/新権限/製品unapply拒否撤廃/CI選別緩和/旧DB試験削除はしない。


製品状態copyの依存供給（2026-11-01、PO委任によるCodex主担当判断）: backend全非DB r4は10326成功/4skip/918非対象/1失敗（275.64秒）。失敗はbackend/tests/test_authz_runtime_contract_repository.pyのcopy_product_test_repositoryが新classification依存test_schema_manifest.pyとtype_boundary_contract.pyをコピーせず子pytestが収集失敗する環境不足。既コピー対象/全reader検査/child対象は不変のままexact2ファイルを明示追加する。編集exact1path、対象の実子pytestを完走して供給を検証し、検査対象/拒否は緩めない。


PR189限定の候補統合carry（2026-11-01、PO委任によるCodex主担当判断）: 診断REPORT40d0d21e…で、旧policy14期待と正式c2 policy18（旧12＋188〜193）が不一致、加えて実baseにordinary recordが無いため旧新受理187限定分岐で189が拒否されることを特定。旧数学/record/schema/9資産/4pinは全byte保持し、policy.json/core_guard.pyは変更しない。対象はscripts/check_human_review_signature.py・tests/test_human_review_signature.pyと、実required jobへの接続.github/workflows/pr-body.yml・tests/test_ci_wiring.pyのexact4。stageB作者が同一source2の唯一writerとして統合候補へ連続実装し、stageBの中間packet/旧基線失敗を保持したうえで最終4pathを別非作者へ渡す（小分けの再承認や自己採用はしない）。

旧187新受理は元PR/branch/publicBase/旧14policy/実187委任に限定したまま維持。新189はmasaki1025/pitchlog/PR189/feature/mvp-first-ball-verticalのexact event、baseのordinary2fileが両方不存在・head両存在、既全4hash/9数学資産/旧入力・ancestor・head blobを実照合し、固定oracle_input Git原典cc0eの正式policy18を実base/headとも全fieldで要求する。旧12prefix保持、186/187targetの挿入はしない。既core_guard.verify_delegated_confirmationで今回実189のbase/head/diff/paths/policySHA/公開URL・掲載主体/非作者/P0P1未解消0を必須照合し、欠落/版違い/重大未解消を拒否する。出力は189統合carryの委任検証のみで旧187受理/本人署名を主張しない。

localは旧14か固定18の閉policyモードで同じ数学を検証しTECHNICAL ONLY、公開成功とはしない。190以降は実baseに同全hashのordinary両資産が存在して全原本不変のときだけ従来base-firstを継承する（旧14系と正式189後18系を明示区別）。未知PR初導入・base片側欠損/改変はcurrentより先に拒否し、結果不明から別モードへfallbackしない。workflowは既core-guard job/権限/required context名と旧core_guard実行を維持して公開Gate6 CLIを追加する。新required contextは増減しない。

最終非作者レビューはこの限定例外手続き自体と全拒否対向を含む。rootの実公開CLI/実CIが最終189証拠へ束縛されるまで正式成立/mergeと扱わない。人間逐行欄の自動check・コアpath除外・署名record代記はしない。


手動入口の実環境追随（2026-11-01、PO委任によるCodex主担当判断）: 同featureのmanual-check.mdのみを現統合WT/SSD tmpへ更新し、旧54b83002の実証を歴史証拠として保持する。既検証専用自己署名の期限切れと、既ignoreHTTPSErrorsによる隔離技術検証を信頼済み運用TLS/実機から区別し、新鍵/新秘密の発行許可を推定しない。新しい最終HEADでの実測証拠は主担当台帳/cacheへ記録し、文書更新で事後的に実測HEADを変えない。


実PG回帰の限定是正（2026-11-01、PO委任によるCodex主担当判断）: source-freeze4b548194…でcurrent/schema2成功9.95秒、別scope回帰47成功/10失敗313.25秒。9件はother_profilesの旧直接seedが新first-ball guardへ拒否される正しい製品動作、1件は旧0036別cluster往復のbuiltin ACL比較へランダムbootstrap管理者名が追加されたことによる環境座標差。既source8を再利用し、backend/tests/db/test_product_authz_other_profiles.pyを追加exact1として、必要なdb_fixtures.py・db/test_product_authz_round_trip.py・既pure test_product_authz_provisioning.py内だけを修復する。

ガード/trigger/role権限/実validationを無効化せず、旧public32/全seed tupleをowned環境の正規0036後・writer guard配置前へ供給してから実0038/S3を完走する準備順へ変更する。実advanceS0を成功応答へ置換せず、旧データを準備したACL試験であることを明記し新規画面保存の証拠にはしない。専用owned fixture/hookを使う場合は外部供給を拒否し、元共通外部分岐は不変。seed先/実revision/所有DBを明示照合し、既ガード下の直接投入を許可しない。

別cluster比較はpg_control_system()の実ownerと各owned clusterのbootstrap管理者が一致しsuperuserであることを実照合した、その1identityだけを明示対応付けする。PUBLIC/pg_monitor/他grantee/privilege/grantable/全ACL行・重複を保持し、同cluster A/B/Cは生値で比較する。builtin ACLをsnapshotから削らず、未知role/不一致から期待値を緩めない。全10失敗/旧成功logを保全し、必要な純対向と実PGの同scope再検証/非作者差分確認を行う。新PO意味裁定/製品source変更/共有DB適用は不要。


seed主体の明確化（2026-11-01、PO委任によるCodex主担当判断）: 上記のowner投入はtest所有環境の既seed主体を保持する意味で、FORCE RLSがあるpitchlog_owner接続へ新たに権限を与える指示ではない。既seedと同じowned bootstrap適用主体を使い、実session/current_user同一・superuser・所有cluster/DB座標・DBowner=pitchlog_owner・0036 marker・writer guard未配置を照合して、正規036/038間に固定fixtureデータを投入する。role属性/FORCE RLS/policy/guardを変更しない。これは移行前データを準備するACL試験であり、製品APIの新規保存・認可成功を代替しない。


### A31導入後の意図的負例の型注記（2026-11-01、PO委任によるCodex主担当判断）

root最終tyで、SQLAlchemyの正規型解決が有効になったため既negative fixture `tests/fixtures/tenant_boundary/negative/pitchlog/services/c5_function_direct_session.py` の任意objectをSession.executeへ直接渡す行だけがno-matching-overloadとなる。これは条件5の不正直実行を意図的に含む入力である。対象1行に理由付きの限定 `ty: ignore[no-matching-overload]` コメントのみ追記し、AST/実コード/負例の期待違反/走査対象を保持する。root型検査の対象除外や製品Any化は行わない。公式fixture検査とroot型検査を実行し、正式assetのhashへ影響する場合は公式helperで追随する。候補作成に関与しないレビューを経て採用し、本人の確認を代記しない。

同じA31型解決によりunused-ignore-commentとなった64箇所・34fixture（正負ともtenant_boundary配下）の旧import用ty ignoreも、実診断のpath/行だけを対象に削除する。34fileの前後SHAとAST同一をcacheへ固定し、検査範囲・各期待違反・SQL・定数・assertは不変とする。実装writerはrootのみ、修復後に非作者が全差分を確認する。


### 初球製品DB起動の有限登録A（2026-11-01、PO委任によるCodex主担当判断）

6ff509bdの実画面縦断は成功したがtenant CLI149件は未成立。旧ad658にもwriter専用登録が無いため、喪失登録の復元とは扱わない。まず独立可能な起動3関数だけを既allowed_symbols方式で正式登録する（残137件を成功扱いしない）。根拠は既承認mvp-first-ball-product-activation unit C、0037/0038の実同owner transaction・revision別の全列/全制約/所有者/FORCE RLS照合、および本計画の実owned PG検証。新しい認可やDB操作は供給しない。

範囲はcontracts/tenant_boundary/base-allowlist.jsonのallowed_symbols3行、tests/fixtures/tenant_boundary/positive/pitchlog/db/startup_allowed/の新3file（_check_writer_storage.py、_apply_writer_storage.py、_require_writer_state.py）、新tests/test_first_ball_startup_boundary_registrations.pyのみ。既50symbol/全fieldと既fixtureは保持する。3署名は実sourceと完全一致し、API集合は _check_writer_storage=PSYCOPG_CONNECTION_CURSOR/PSYCOPG_CURSOR_EXECUTE、_apply_writer_storage=SQLA_CREATE_ENGINE/SQLA_ENGINE_BEGIN/PSYCOPG_CONNECTION_CURSOR/PSYCOPG_CURSOR_EXECUTE、_require_writer_state=PSYCOPG_CONNECT/PSYCOPG_CONNECTION_CURSOR/PSYCOPG_CURSOR_EXECUTE に限定。scope外・未知symbol/API・署名/fixture欠落・別関数移植を拒否する対向を追加する。全source正例は他の未登録149件を隠すために使用せず、この3scopeだけの結果と残存全違反を分離して検査する。

rootは計画/台帳/正式値導出の唯一writer、実装writerは別担当にexact5を移管し、checker/既tests/製品sourceには触れない。実装前計画を非作者確認し、候補source/全前後SHA・拒否対向を非作者review後採用する。正式値全9資産とcorpusは他修復完了後に単一189受理として一括再導出する。検査path除外・全pathの恒久許可・任意declared hashの自己受理は行わない。


### 初球固定関数builderの完全形接合B（2026-11-01、PO委任によるCodex主担当判断）

初球sourceの実builderは既check_current_right入力bindのinternal_generation/recovery_generationの2項目にBigIntegerを用い、sync_fence_api/assert_writer_bindingの非table返値assertedだけ専用voidを使う。checkerは旧simple完全ASTしか認めず、旧16変異試験が正常sourceの時点で停止していた。対象はscripts/check_tenant_boundary_bypass.pyとtests/test_check_tenant_boundary_bypass.pyのexact2のみ。旧_FIXED_BUILDER_BODYは変更せず、189現sourceの閉じた完全本文を別AST定数として追加し、旧builder期待の場合だけ2択で完全比較する。canonical_bind等の他期待へ一般化せず、source宣言/任意hashで未知本文を許可しない。既190の別完全AST比較構造・有限拒否testを参考に、ordinary関数/6prefix列/通常球計算部分は取込禁止。製品sourceをcheckerに合わせて簡略化しない。

既16対向の入力/全assertと『変異前source緑』前提は保持し、BigIntegerの型/2列/関数/schema/int、voidのnamespace/function/table_valued/result_names/typeを各1変更する拒否、旧simple正例を追加する。旧broker fixed-import2の現在存在しないimport_module文字列は、現静的from importを別moduleへ変える対向へ移し、正例_evidenceと同じ拒否assertを保持する。broker正例が別未成立の間はテストをskip/前提削除せず未成立と記録する。

writerはregistration担当のexact2へ一本化し、別担当Aのallowlist/fixture3/test新fileに触れない。計画と候補を非作者確認し、rootが正式値/履歴/corpusを最後に一括導出する。残るtenant149の他群をB成功で閉じず、全CLI/最終HEAD/必須CIまでmergeしない。

Aの既exact期待追随（同日）: tests/test_stage_a_startup_tenant_boundary.pyを追加exact1とし、既11関数/API全値を保持したまま新3関数の有限集合だけを明示追記する。未知関数/API/別module/署名変更の拒否対向は全件維持する。Aの総対象は6path、許可の拡張根拠は上記3実関数だけであり、単なる件数更新やsubset比較への変更は行わない。


### 初球縦断の条件2有限登録C（2026-11-01、PO委任によるCodex主担当判断）

実測の再計測: 単位A/B適用後のtenant必須検査は136件（TB000 3/TB002 88/TB005 20/TB007 25）で合格0件。引継ぎの「149件中4件失敗」は149件の違反が4コードに分布する意味であり、単位Aで13件（TB005）減っただけである。旧ad658の限定登録（`condition_2_initial_start_scoped_findings`）の復元で説明できるのは35件まで（`product_function_acl.py` 2／`initial_grant_broker.py` 33。後者は`_initial_population_semantics`もFalse）で、残る98件（17ファイル）+SQL3件は現行checkerに登録機構が無い。したがって残件を単位分割し、1単位ごとに既方式の有限登録として積む。1単位の成功を全CLI合格・最終HEAD・必須CI成功へ読み替えない。

第一の単位Cは件数最大の条件2（TB002）だけを対象にする。既RG1方式（固定path集合 + 実source SHA-256 + (行,記号)のexact-set）と同型の登録を追加し、`pitchlog/repositories/first_ball.py`、`first_ball_operations.py`、`recorded_snapshot.py`、`started_read.py`、`started_snapshot.py`、`transaction.py`の6path・66出現を閉じる。期待投影はchecker側の固定定数`FIRST_BALL_CONDITION2_SCOPES`に置き、allowlistはsource SHAと出現だけを持つ。allowlistから新しいpath/行/記号を自己申告できない形（固定集合との完全一致を要求）にし、source 1byteでも変われば免除が全て無効になる。

対象は`scripts/check_tenant_boundary_bypass.py`、`contracts/tenant_boundary/base-allowlist.json`、`tests/test_check_tenant_boundary_bypass.py`のexact3。既`condition_2_scoped_findings`47件／台帳20件／RG1 2path／ad658由来7pathの全値を保持し、TB002以外（TB000/TB005/TB007）の扱いを変えない。拒否対向として、登録pathの1byte改変で免除が消えること、登録行に別記号を置いても拒否されること、allowlistへ未知path・余剰行・欠落行・別SHAを足すと契約が成立しないことを検査する。`initial_grant_broker.py`と`product_function_acl.py`は本単位に含めず、束縛先の再導出と意味条件の診断を別単位に残す。

条件2の禁止語彙そのもの、owner_paths、他の免除機構、検査対象範囲は変更しない。製品sourceは触らない。正式9資産/corpus/受理recordは残単位完了後に単一189受理として一括再導出し、本単位の実装だけではrevisionを進めない（途中状態を正式受理と扱わない）。


### 初球操作4symbolのDB API有限登録D（2026-11-01、PO委任によるCodex主担当判断）

単位C後の実測は65件（TB000 3/TB002 22/TB005 15/TB007 25）。次に、関数として登録可能なTB005 5件だけを既`allowed_symbols`方式で閉じる。対象は`pitchlog.repositories.recorded_snapshot_operations._registration`、`pitchlog.repositories.started_snapshot_operations._registration`（いずれもSQLA_SELECT）、`pitchlog.sync.control_provider.binding_control._BindingAuthority._call`（実行系8 API。receiver型が未解決なため既scannerが返す和集合と同じ集合）、`BindingControl._channel`（connect系2 API。AF_UNIX socket.connectを既RG1と同じ扱いにする）の4symbol。

範囲は`contracts/tenant_boundary/base-allowlist.json`の4行、正例fixture4file、`tests/test_check_tenant_boundary_bypass.py`の3試験。署名は実sourceのAST完全一致を要求し、正例は宣言APIだけを呼ぶ。登録symbol内への許可外API追加と、同一モジュール内の未登録関数へのSQL構築を拒否する対向を置く。

`pitchlog/repositories/first_ball_operations.py`（module-level `_INSERT`/`_READ`）と`first_ball_vocabulary_operations.py`（module-level `_READ`）は関数でないため本単位に含めない。source refactorか別mechanismを要する別単位とする。TB002/TB007/TB000の扱いと既50+3+4行の全fieldは変更しない。製品sourceは触らない。正式値/corpus/受理recordは残単位後に一括再導出する。


### 初球縦断の条件5有限登録E（2026-11-01、PO委任によるCodex主担当判断）

単位D後の実測は65件（TB000 3/TB002 22/TB005 15/TB007 25）。次に、broker（初期付与callerは既`_INITIAL_POPULATION_POLICY`の束縛先再導出で扱う）を除く条件5の27出現を、条件2単位Cと同型の固定投影登録で閉じる（うちmodule-level 3出現は単位D-followで登録関数化し、最終は9path/24出現）。当初対象は11path: `repositories/first_ball_operations.py`2（module-level `_INSERT`/`_READ`）、`repositories/first_ball_vocabulary_operations.py`1（module-level `_READ`）、`repositories/started_read.py`1、`repositories/started_snapshot.py`1、`sync/control_provider/store_contract.py`7、`sync/control_provider/writer_binding.py`1、`sync/first_ball_bridge.py`4、`sync/source_binding.py`3、`sync/stop_contract.py`1、`sync/wire_fingerprint.py`4、`sync/wire_source.py`2。

内容は、module-levelの固定`select`/`insert`宣言、frozen dataclassの`object.__setattr__`初期化、封印値オブジェクトの`object.__new__`、検証用`dataclasses.replace`、`cast(Any, cls)(**fields)`による自己型構築であり、いずれもTenantContextの生成・改竄ではない。期待投影はchecker側の固定定数`FIRST_BALL_CONDITION5_SCOPES`に(line, code, symbol, scope)で置き、allowlistはsource SHAと出現だけを持つ。path/行/記号/scope/codeの追加・欠落・別値は契約不成立とし、source 1byteの変更で免除を全て無効にする。条件5の規則自体、`forbidden_construction_symbols`、TenantContext正規構築経路、他条件の扱いは変更しない。

範囲は`scripts/check_tenant_boundary_bypass.py`、`contracts/tenant_boundary/base-allowlist.json`、`tests/test_check_tenant_boundary_bypass.py`のexact3。拒否対向として、1byte改変での免除消滅、登録行への別scope/別code、合成Contractでの欠落・重複・別path・別出現を検査する。broker 33件・acl 2件・SQL3件は本単位に含めない。製品sourceは触らない。正式値/corpus/受理recordは残単位後に一括再導出する。


### writer-binding候補DDLの未統合登録F（2026-11-01、PO委任によるCodex主担当判断）

単位E後の残件は38件（broker33＋acl2＋SQL3）。うち`backend/src/pitchlog/sync/control_provider/sql/`の3 SQLは**test専用の構造候補**で、自headerに「role/固定保存器/正式受理は未提供」と明記し、参照は`backend/tests/db/sync_writer_binding_support.py`と`backend/tests/test_sync_apply_writer_binding.py`だけで製品runtimeは読まない。`ledger/rg1_deployment_assets`と同型の「配備資産」として扱うと正式配備権を偽るため、RG1前例（`status: unintegrated_candidate`の閉manifest）に倣い、**配備権なしの未統合候補**として登録する。

範囲は`backend/src/pitchlog/sync/control_provider/sql/writer-binding-manifest.json`の新設、`contracts/tenant_boundary/base-allowlist.json`の新キー`writer_binding_deployment_assets`4path、`scripts/check_tenant_boundary_bypass.py`の固定定数・loader・validator・population供給、`tests/test_check_tenant_boundary_bypass.py`の試験。manifestは`schema_version`/`status`/`purpose`/`deployment_authority`/`files`/`evidence_boundaries`の閉集合とし、`deployment_authority`は`none_unintegrated_candidate`に固定する。

validatorはmanifestの自己申告を信じず、**実SQL本文から**`CREATE SCHEMA/TABLE/INDEX/FUNCTION/POLICY/TRIGGER/ROLE`を抽出し、checker側の固定構造面（2 schema/3 table/2 index/9 function/6 policy/4 trigger/2 role）と完全一致を要求する。manifestの`files`SHAは実byteとallowlist宣言SHAの双方に一致しなければならない。したがって、SQLとmanifestのSHAを協調して追随しても、閉じた構造面を越えるDDL追加は受理されない。宣言外の非Python変更は従来どおりTB000へ戻し、検査を緩めない。製品runtimeへの配備・実行権、正式7.7受理、実機/運用受入は与えない。broker33＋acl2は確定単位（policy・frozen revision・受理recordの一括移動）へ残す。


### broker/acl束縛の確定移動G（2026-11-01、PO委任によるCodex主担当判断）

単位F後、tenant必須検査の残件は初期付与caller33件と`product_function_acl.py`2件だけ。両ファイルは旧`f174428d`から変更済みで、`_initial_population_evidence`のbyte束縛が外れていた。`_INITIAL_POPULATION_POLICY`の2ファイル分を現行sourceの実出現へ更新し、`_initial_population_semantics`を現行形（RG1型の静的import、`_broker_d4`の`encode_d4_reference`委譲）へ追随させる。旧inline形を要求する条件は残さないが、委譲先`pitchlog/sync/d4_reference.py`は同じ型/範囲検査を持ち、NFR-018の単一実装である。

束縛先`ci_scope_proof_source_revision`は、両ファイルの現行byteが既に揃っている既存祖先`d141fa70a85d85c01fdbb6ddd1956e3f9ba01525`へ移す。新しい自己参照commitを作らず、レビュー済みの既存状態へ束縛する。`_INITIAL_POPULATION_POLICY`はbaseline側scanにも適用されるため、policy・revision・受理record・snapshot/corpusは同一の確定単位で一括移動し、途中状態で部分更新しない（部分更新はbaseline側の免除を外し、既存違反として差し引かれる偽の減少を生む）。

この移動でtenant必須検査は0件、tenant試験は733件全成功。ただし正式9資産の受理record・snapshot・corpusは別途公式helperで一括再導出し、非作者レビューと必須CIを経るまで統合済みとは扱わない。


### 不変値構築のTB007緩和宣言H（2026-11-01、PO判断）

census述語`removed_tb007_matches_declared_relaxations`は、減分TB007を「発行入口constructor」「固定登録statement初期化」の2緩和だけで説明できることしか許さない。本PRの残TB007のうち、封印値の`object.__new__`、frozen dataclassの`object.__setattr__`、検証用`dataclasses.replace`、read tokenの`token_type`構築、`cast(Any, cls)(**fields)`はどちらにも該当せず、tenant免除を維持したままではcensusが赤になる。

PO判断により、`census-baseline.json`の当該述語へ第3の緩和種別`immutable_value_construction`を正式宣言する。宣言は`kind`・`allowed_symbols`（`builtins.object.__new__`/`builtins.object.__setattr__`/`dataclasses.replace`/`token_type`/`<unresolved-callable>`の5つに閉じる）・`sites`（path/line/end_line/scope/code/symbol/messageの完全一致22件）を持つ。test側`_declared_relaxation_identities`は宣言の形・symbol閉集合・site重複を検査し、`declared <= removed`（宣言済み緩和が実減分に無い場合は拒否）を要求する。宣言外のTB007は従来どおり発行入口/固定登録の説明を要する。

範囲は`contracts/tenant_boundary/census-baseline.json`と`tests/test_census_baseline_check.py`のexact2。tenant検査条件・`_INITIAL_POPULATION_POLICY`・`FIRST_BALL_CONDITION5_SCOPES`・製品sourceは変更しない。`first_ball_bridge.py`の332/361はanchor censusに存在しないため宣言へ含めない（実減分との完全一致を優先）。本宣言はsecurity policyの変更であり、docゲートと非作者reviewを要する。censusの他pin（ledger限定identity等）は別途再導出する。

単位H追補（2026-11-02）: census述語へ初球条件2登録を説明源として接続する。`_validated_first_ball_condition2_identities`で固定6path/66出現を実source SHAとbefore/after差分へ束縛し、`unadjudicated_removed_tb002_remains_in_current_census`の説明集合へ加える。anchor側checkerが返す短いsymbol綴り（`...__table__`等）は同一siteの登録所見へ`_first_ball_registration_explains`で束縛する。`added_equals_independently_derived_condition_2_candidates`では、独立列挙が変数名・実scannerが型名を返す差があるため、登録siteの(path,行,code)で控除する。あわせて`implementation_field_inventory`へ`declared_relaxations`の10 fieldを追加し、`ledger_removed_checker` digest・`pure_helper_references`のbroker site（1468-1477）・initial population site総数（70）を実測へ追随する。これらは宣言の意味を変えず、実測との一致を回復する追随である。
