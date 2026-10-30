---
feature: mvp-recording-continuation
status: active
承認: PO委任によるCodex主担当判断（2026-10-30、候補85cda279…、非作者REPORT1b279c19… P0/P1=0と限定P2反映を照合）
重さ分類: コア領域
branch: feature/mvp-recording-continuation
created: 2026-10-30
計画レビュー周回: 0
確定ゲート周回: 0
---

# 通常33座標の継続記録・prefix保存・再読込の接続

## 1. 固定点と製品到達点

基線 `54b83002`（初球HTTPS縦断1成功/46.29秒は既担当実測）。本WTは `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-recording-continuation`。初球安定WT・root台帳へ書き込まない。既544計画・操作単位先行のPO指示の有限追補であり、既承認やレビュー系列を作り直さない。本書は候補、非作者レビューと主担当のPO委任承認前に製品コードへ着手しない。

**製品DoD**: 同じ候補・owned実PG/実broker/実認証/HTTPS実画面で、新規作成→開始→支持済通常33座標に属する連続入力→各球の保存→prefix再取得→reloadを通す。2/3球専用の件数上限を設けない。到達可能な各入力で同じartifactの全T1/23flags/履歴と評価済T2を保存し、同一要求再送で行数を増やさない。履歴長は確認済prefixから導出し、球数を固定値で返さない。

初回witnessは「ボール→見逃しストライク→ボール（B2/S1）」とするが、**DoDは通常33全範囲**。B0/S1等を初球ボールからは作れないため、新ordinary形式は空prefixからの通常投球も扱い、33座標の全入力を実create/startから到達可能にする。既first-ball形式・初球API/実機準備の成功は後退させない。

取消・訂正・終了/再開・打球/走者/交代・全MVP・成績/両CSV・offline運用/実機/負荷/復旧の義務は維持する。未実装の終端球/2ストライクファウル等は501のまま成功扱いにしない。

## 2. 既成果と今回の実不足

| 再利用する実物 | 扱い |
| --- | --- |
| `frontend/src/domain/state.ts` の `deriveOrdinary` / 同単一 `applyCountRule` | 通常33数学本体をコピーせず使用。#187・544計画末尾の受理/実artifact照合の対象版を継承する |
| `contracts/state-transition/ordinary_pitch_vectors_v1.json`（33件＋historyTailCases）/ 正式 `state_transition_contract_v1.json` のcase/規範行参照 | 既期待値・formalBindings/ID移行を保持。候補headerのshadow記載だけで正式受理済としない。544の既採用根拠と照合 |
| `deriveOrdinaryPitch` の任意既履歴tail保持 / artifact公開基盤 / 既T1 typed caller | 既DTO・23flags・履歴差分を再計算せず合成。spikeの参考実装は正式ベクタと比較してから部分再利用 |
| 初球実tenant auth/C2/device/V12/RG1/writer / D5冪等・queue/attempt | 現成功経路の資格と順序を維持。実Port登録・実HTTP/実DBをコピーやstubへ置換しない |
| recorded初球read / PlayRow全値照合 / 座標operation | prefix readの根拠として必要部品だけ共有。初球exact1の判定を単に外して任意履歴を信用しない |

実不足は (a) `_apply_e1_f1` の単球D1=1入口、(b) 初球T2のS0B0→S0B1限定、(c) first_ball frame/内容検証/INSERT/admissionの初球専用束縛、(d) 再読込が水位/履歴/PlayRow exact1、(e) 画面/attemptが初球1件専用であること。**数学33成功はこの接続の完成ではない**。

## 3. 閉じた入力・結果・拒否

- 通常33の**count×result格子**は、ボールS0..2/B0..2（9）、見逃し・空振り・ファウル各S0..1/B0..3（各8）を保持する。製品射程は**記録可能な任意の有効試合状態**（回/表裏/0..2out/全8塁配置/打順1..9/得点と全scoreboard/整合したTB active）へ広げる。gameEnded/終了条件成立による入力lockは拒否。打席終了・四球・三振・S2ファウル等を成功化しない。
- **正本根拠と契約整備の差**: 要件FR-003（任意の打撃結果→付録E効果）・FR-004（走者/特殊効果の明示入力）・E-1（Advのhold/not-applicable閉型）に、通常非終端投球を初期回/空塁へ限定する条文は無い。一方、現正式4通常matrixRowsはout=0/runners=empty、sourceのsupportedStateはさらに1回表/打順1/無得点へ限定している。これは**現source/契約の供給不足**であり、最終製品の正本上の制限ではない。既規範の正式整合変更として必要row/schema/descriptor/case追加を委任判断・非作者原典照合の対象へ含める。旧33case値・履歴/IDの既採用根拠を保持する。
- **不変と観測の区別**: 同時のrunner/secondary/手動進塁・得点効果を伴わないことを閉入力で明示し、通常count以外の全fieldと実在塁者ID/出場者を保持する。在塁者の既定はhold/null、不在塁はnot-applicable/nullをE-1型から候補化するが、表示した既定値を実移動の観測成立へ読み替えない。同時効果が提示/必要な入力は対応契約へ渡すか未対応として閉じる。792新候補case（33×3out×8塁配置）を用意し、一般状態のsource拒否を恒久仕様へしない。
- 新payload候補 `ordinary-pitch-play-v1` はV7の観測/参加者/計算の閉形を再利用し、resultは既支持4キーのみ。beforeは**ロックした確認済prefixのafter**、historyは同prefixの真正な履歴、rules/実名簿は開始原典から取得。UIが作るbeforeを正解として使わない。
- 観測は実tenant有効球種・利用者が選んだ結果と画面座標。欠測球速/構え/打席側を推測しない。参加者は同prefixの現出場を照合（この非終端投球自身は同打順/同参加者）。T1の計算・フラグ・history差分を別言語で作り直さない。
- 同一artifactでordinary T1を1回評価し、同before/derivedと保存rulesをT2へ渡す。既first-ball専用T2を「33も非成立」と無検査で流用しない。保存された有効なR/L/cold/TB規則と任意の有効beforeに対して既終了規範を**実評価**する閉ABI/case/独立レビューを供給する。非終端pitchだから常に非終了という固定値を返さず、前状態の終了/入力lock・コールド等の判定条件・規範の評価時点を照合する。数学全体・E11/E07等の新裁定へ広げない。
- 入力形式不正/認可/失効/tenant越境/D1 gap/D5再送照合/内容拒否/状態前提とO4の優先は既同期契約を維持。新ordinary dispatcherを既認可・再掲の前へ移し501等で状態を漏らさない。既D06=BのD5扱い・結果不明/全取消・後着遮断も維持する。
- 既501は**有効だが既知未実装**の操作に用い、不正形式/未知語彙/権利拒否/DB一時故障を501へ潰さない。既拒否集合へ新しい成功・D5消費規則を追加しない。

新fixture `contracts/state-transition/recording_continuation_scope_v1.json` は数学33のcase参照・実create/startから到達する33coveragePaths・3系列witness・792一般状態T1候補・新descriptor軸/交差/変異・対向検証条件を置く。期待数学をartifact/試作から生成しない。新T2期待値/ABI/schema・prefix admission/refの閉型は各所有規範と照合し、step1で未成立なら未成立として特定する。

## 4. 同期・耐久保存の共有設計

**first_ball_write_admissionsを改名して使わない。** ordinary用のadmissionを別の論理資格として設計し、同一TXの実writer/currentD4/authority世代・txid8・source event/d1/d5・確認済prefix水位n・評価frame identity・投影先PlayRowを結合する。app由来の成功boolやcaller指定のafterでは発行しない。

1. 既writerフェンス/RG1/実権利の同一順で現在の資格を検査し、ゲームの同期watermarkとprefixを同じロック範囲で取得する。
2. nまでの正規原本/イベント/PlayRow/履歴の連結を照合し、before/history/rules/参加者と新イベントの入力を束縛する。D1/D2は既採番/論理位置規則から供給する。D1とD2を一般的に同一視せず、この閉じた通常投球列では結果として同値になることを確認する。
3. 同artifactの評価済frameを一度だけ消費し、ordinary admissionを同TXで発行/消費→PlayRow/operation/event/idempotency/水位更新を不可分に行う。既SQL/installer/RLS/ACL原則を維持。別TX・別接続・savepoint/二重消費・別frame・途中故障は拒否/rollbackする。
4. 同D5再送は原要求照合後に保存済結果を再掲し、現在権利の状態と過去確定結果の再掲を既規則どおり区別する。結果不明は旧slot/同attempt/bodyを保持し、新ID置換しない。attempt欠落時は未送信耐久証拠がなければ閉じる。

取消・過去訂正・試合終了/再開は後続操作だが、admissionの「source event→投影」の結合、論理版/訂正原本、冪等履歴を先に既history/target/version規約と照合する。永久INSERT専用資格と取消/訂正用の再利用資格を混同しない。普通の1球追記を承認しただけでundo/訂正を提供済みにしない。必要migrationはowned DBのみで実証し、共有DBへ適用しない。

## 5. prefix read・画面・耐久queue

- `GET /started` のinitial/既recorded1互換は保持し、複数球は明示的なprefix variant（候補 `recorded-prefix`）として閉DTOを追加する。current after・確認水位・履歴/PlayRow列を同じ確定prefixから返す。部分水位や未送信データを保存済みに混ぜない。
- 取得はtenant/game/確定水位でDB側絞り込みを行い、外部件数入力に有限上限とページングを置く。afterを得るため履歴全件を無制限読込する設計は採らない。通常投球を任意試合状態へ接続しても、履歴長の無制限読込を許可しない。確認不能/不一致は既不可視又は503へ閉じ、UIでbeforeを現在値へ戻さない。
- フォームの結果候補を支持4種へ拡張し、最新の実after・名簿・rulesに基づく入力だけ確定する。排他/環境確認・実資格を維持。既初球attempt DBを上書きして継続要求を収容しない。ordinary用のslot-bound記録をD4/D1/D5と原本文に結合し、旧未確定要求を残したまま次のslotを新規作成しない。
- reload時のサーバーreadとqueue ACK適用を区別し、サーバーに既保存でも未終結slotは同要求で照会/再送する。失効/別tenant/他タブ/未対応結果の成功表示をしない。

## 6. 実装ステップと担当境界

| # | 作業/編集範囲候補（主担当が非作者レビュー後に固定） | 受入 |
| --- | --- | --- |
| 1 | 新ordinary継続のrequest/response/schema/独立case・descriptor、一般状態のmatrixRows/hold/不変fieldと実T2、prefix/admissionの閉refと拒否・境界契約。544/T2/同期/履歴/DB規範を照合し本計画を委任承認 | 33全数学の再利用先/原典/既受理根拠を固定、全操作開始へ戻さない。source/実DBを未完成の前提として追加しない |
| 2 | `frontend/src/domain/publicApi.ts`・既continuation純核/型callerの有限拡張、artifact/manifest/pinと両runner。旧derive/deriveState/first-ball ABIの初期scope拒否と既supportedStateを保持し、ordinaryだけ一般state専用validatorへ接続。単一applyCountRuleを再利用しcount計算を複製しない | 全33×有効一般状態（回/表裏/out/走者/打順/得点/TB）の完全値・任意履歴tail、T2実評価の新閉入力、properties/mutation/host、旧初球/42座標の回帰。数学source非作者レビュー |
| 3 | syncの実prefix/frame/Port・新ordinary admission/migration/installer/token/operation登録・新投影。`first_ball_*`から共通の必要部品だけ抽出 | 実権利/原子性/冪等、n→n+1の連続ownedDB（2/3専用上限なし）、旧初球成功、認可/耐久source非作者レビュー。正式資産/7.7はroot直列 |
| 4 | recorded-prefix read API/DTO/validator、既after復元、ordinary用slot-bound attempt・画面4結果/queue接続 | 正常再取得/reload、途中prefix不一致・結果不明/attempt欠落・競合/他tenantで閉拒否。実API/DBをstubで置換しない |
| 5 | 同一候補HTTPSで33到達可能入力列をfixture経路から実行、初回witnessに加え連続/再送/切断/故障対向、最終レビュー/必要全件CI/台帳記録 | 利用者が実画面で継続記録・保存・再読込できる証拠。候補成功/正式受理/実機/MVP完成を分離 |

step2の数学契約成立後は数学を先行し、step3のSQL/実Port完成を計算本体の着手条件へ戻さない。step3のadmission規範設計はstep1で先に確認し、実PGの成功は実装後の必要検査とする。共有publicApi/artifact/登録資産は単一writer、他担当へはパスを明記する。範囲確定前の巨大一括移植・強制push・同ファイル並行編集をしない。

## 7. 検証・残条件

作業中は対象検査、候補固定時に必須全件/CIを実施。DB/ポート/tmpを分離、pytestは共有DSNをunset。最終HEAD・diffSHA・源case/ABI/受理・source非作者レビュー・実HTTP/実DBの行数/水位・HTTPS画面・故障/再送証跡を記録する。純数学の成功・比較用fixture・P6段階Bを新blind/全体受理と呼ばない。

本候補の現在地は**計画/接続fixtureだけ**。新しい意味判断は現時点で不要と考えるが、既原典から決まらない拒否消費/訂正共有意味が見つかれば判断票へ具体例/選択肢/推奨/影響をまとめ、その機能以外は進める。migration/権限を弱めず、未確定を仮仕様で成功化しない。

### 一般状態への最小追補（主担当指示、2026-10-30）

step1の準備を792候補case/新descriptorまで進めた。これらは作者規範導出候補であり、新P6 blind/独立期待値受理・新source実行・実接続の証拠ではない。既正式4rowが初期out/baseを前提にしている事実を隠さず、一般stateを受ける新rowの前提/効果をowner契約へ正式反映する。未整備の正式契約と新意味未裁定を分け、既原典から確定する通常count/全不変field/明示runner-effect分離を先行する。在塁hold/同時効果の候補導出が原典から確定できないとの非作者指摘があれば、その差分だけ判断票に残す。現在のsource限定を理由に全工程を停止したり、初期state専用をMVP完了としない。

### 非作者差分確認への最小反映（2026-10-30）

- 旧 `derive` / `deriveState` / 初球ABIの拒否範囲は保持する。`supportedState` は旧初球guardのままとし、ordinary用の一般状態validatorを別の入力検証として設け、計算は既単一 `applyCountRule` を共有する。初球guardの書換えによる旧ABIの無断拡張をしない。
- prefix全連結の検証と無制限読込禁止を両立させるため、step1の閉契約で**有限ページ＋検証済checkpoint/版付きprefix ref**の構造を確定する。checkpointは実確定原本の水位/世代/履歴版と結合し、未検証caller afterをcheckpointとして採用しない。現在値と今回のhistory pushは確認済checkpointから得て、残履歴はrefに基づき有限ページで取得する。既 `deriveOrdinaryPitch` のfull `history.stack` 入出力は後方互換のまま保持し、新接続DTOのprefix ref/ページと旧stackの境界を明示する（partial tailをfull履歴と偽らない）。この**構造契約**は同期保存・prefix readerのsource着手前に照合する。旧full stack ABIを維持するordinary純数学の一般状態validator/単一count核の着手条件へ、prefix refのDB実装完成や実PG試験を追加しない。

## 主担当の限定受理（2026-10-30）

PO委任Codex判断。対象計画85cda279…・scope fixture733275b8…を確認し、非作者の792候補全検算と計画P0/P1=0、旧ABI guard保持・prefix検証境界のP2最小反映を根拠に承認。本人署名・P6 blind・正式全T1成立ではない。

step1の契約/descriptor・独立期待値整備と、成立したordinary純数学部分のstep2を開始する。T2・正式matrix/descriptor受理が未成立の結果を成功応答へ出さず、コードの候補検査と正式受理を区別する。DB/HTTP実装完成を純数学着手の追加条件へしない。SQL/admission/prefix readerは共有取消訂正/水位/ページ構造の先行照合後に実装する。

### 通常非バントの2ストライクファウル4座標（委任採用、2026-10-30）

rootはE-1のファール打席続行、E-2 SO-04（2SバントファウルのK3専用）、採用済research:182と読取専用旧原典の「ファールはS<2のみS+1」を照合し、通常非バントfoulのS2/B0..3据置4座標を既方針の契約具体化として同単位へ追補した。旧33期待値・source基線は保持し、適用count格子は追加4を加え37となる。従前の「S2ファウル未提供」は本追補の受理/実装/検査成立後に限って上書きされる。

`ordinary_two_strike_foul_candidate_v1.json` に4個の完全封筒と一般状態96例・descriptor/変異軸を追加する。strikes/ballsはunchanged、打席継続・out0、既投球数flagを保持し、差分が空でも履歴push1を落とさない。明示された通常非バント `batting-result.foul` の選択だけを受け、K3/SO-04/2Sバントを同IDへ推定置換しない。既33の格子・23flag・旧初球拒否は不変、通常sourceだけを広げる。正式matrix/caseの新4行受理と候補source試験を区別し、37成立をT1全体/MVP完了としない。

### step2 純数学候補の受理（2026-10-30、PO委任Codex主担当判断）

基線ae34a68dの6path作者packetを全SHA一致で確認。非作者REPORT `/home/ymdms/.cache/pitchlog/recording-continuation-math-nonauthor-20261030/REPORT.md` SHA256 `e2f135a355a133dc9342effa6b95acecdd8fd22ad09878750cd9b2b4735df3eb` はP0/P1/P2=0、独立全domain12files375成功・追加4/96値照合、旧33/初球guard・単一核・履歴tail不変を確認。主担当の指示を受け、計画追補を前置docs commit、通常数学のsource/spec/追加4候補をstep2 commitへ固定する。本人の逐行確認・正式matrix/descriptor/case受理・P6 blind・T2/実保存の完成は記録しない。

次は同WTでartifactを再生成し、生成物/SHA宣言・既fixtureのartifactSha256とmanifestの該当artifact識別だけを追随する。既期待値は変更せず、生成JS経由の一般状態/旧初球拒否を確認して別非作者へ渡す。runtime正式受理/接合・prefix read/実画面は後続の未了条件として保持する。

### step1/2 有限prefix ABIの追補候補（2026-10-30）

既5stepの範囲は維持する。`ordinary37_continuation_candidate_v1.json` と `ordinary37-continuation-abi.md` へ、版付きprefixRef(n)・前回after/T2/rulesへの束縛・今回1historyEntryだけの新operationを具体化した。旧full-stack ABIは保持し、新接続では局所stack=[]で既単一T1を一度だけ評価する。返るhistoryContext唯一要素をnewHistoryEntryへ構造変換し、これを全履歴とは呼ばない。履歴は別の有限ページ＋真正checkpointから取得する。count/差分計算は複製しない。

本追補は非作者照合前の作者候補。20caseは既数学封筒と静的after/T2/ref/history値から組んだ完全responseのexact比較であり、新しい独立ゴールデン/P6受理ではない。新operationのsource着手はこの有限ABI/caseの非作者P0/P1解消と主担当の委任判断後。全T2や全同期・DBの完成をその追加開始条件へ戻さない。実保存には真正prefix由来entryと同TX/admissionの接続検査が別途必要。

ref.generationはD4のopaque string<=128を指し、recovery_generationと混同しない。lengthはordinary-only支持37の確定水位で、D1/D2・一般履歴長・PlayRow番号とは別。rulesは実保存内容の完全一致とDRAW-01..04相関を実検査する。今回の通常open系列で説明できない再開後状態等は未対応として閉じ、恒久的な意味拒否へ拡張しない。

#### 前回T2の意味束縛（非作者P1反映、2026-10-30）

rules/afterの対比較に加え、prior.t2自身のbasisをprior.rules/afterへ意味束縛する。旧初球封筒は対応する初球after（1表/S0B1/0out/空塁/打順1/無得点・全board0/TBなし）とR/L/cold/TBの既閉条件を照合する。新ordinary封筒はR/L実値・回/表裏/TB・cold全段の順序付き分岐・DRAWを保存rules/afterへ照合する。未知/不一致はT2_NOT_EVALUATED。純数学内部一致は実prefix真正性の代わりではない。

成功期待値は既数学封筒＋静的after/T2/ref/history値から完全responseを組み、全項目のexact比較を行う。候補JSONは20caseへ追加し、旧T2移植・新basis回/cold/L不一致の対向を含む。元の16件固定を品質条件にせず、部分一致へ緩めない。

### 通常37・有限prefix T2のsource開始受理（2026-10-30）

PO委任によるCodex主担当判断。候補JSON12127d2d…/ABI3237821b…/計画c73ff228…を全SHA照合し、非作者REPORT6b149f8a1a1a605809cdc5e259fc2ce3d688a76e4da68b0577ffbf4035d0d2f0（P0/P1/P2=0、20完全応答の独立比較、前回T2移植等の対向）を採用。作者のSchema検査を実source成功に読み替えない。新P6 blind/正式全T2受理/実prefix真正性/実DB完成ではない。

step2純数学の新合成operationは `frontend/src/domain/ordinaryPitchContinuation.ts` と同spec、`publicApi.ts`、既firstPitchContinuationの共有rules parser/型、公開型caller/宣言・artifact/pin・実host検査の有限追加を編集範囲とする。旧ABIを保持し、count計算を複製しない。新ABIはfinite prefixRef＋今回履歴1entry、前回T2/rules/afterの完全一致と相関を検査する。未評価/既lock/ref不整合は成功にしない。新T2全体やDB/HTTPの完成を純数学source着手の条件へ追加せず、保存と画面はstep3以降の実証で閉じる。

新合成ABIのPython接続はstep2の型callerとして `backend/src/pitchlog/domainrt/ordinary_pitch_continuation.py` と `backend/tests/domain/test_ordinary_pitch_continuation.py` に追加する（PO委任Codex判断）。既固定Node hostを1回呼び、不変・閉wire DTOと重複key/NaN/alias/余剰の拒否だけを担当し、T1/T2をPythonで再計算しない。旧初期状態限定DTOは拡張せず別型で一般stateと今回1entryを保持する。構造単体検査と実artifact全値照合を分け、実prefix/認可/保存証拠とはしない。

### T2判定核の重複P0と通常是正（2026-10-30）

追加非作者REPORT `14a164c95741ae48955939fb5548838eba06082da24e9ec4c8a3ade84110d581` のP0=1（旧初球T2と新ordinary T2の規則判定が重複）を採用し、前source採用は当該指摘に関して保留する。既レビュー系列をリセットせず、先の実artifact成功をNFR-018保証の代わりにはしない。旧失敗候補artifact `41ccdde57c0ca85815e05d066a684ed93d477a4571ce41b6b5a22c3d9fe5309b` とpacketをcache保全した。

既委任の通常是正として、firstPitchContinuationのtyped EndConditionState＋rulesからEndConditionFactsを導出する唯一の共通核へR/L/cold全段/TBの実判定を集約する。旧firstOrdinaryBall・旧支持範囲はguardとして維持し、旧formatterも新formatterも同じfactsを消費する。新ordinary側の別規則核は削除する。両ABI/20完全期待値/37count核/BE callerは変更せず、共通核の状態/規則による分岐検査を追加する。source固定SHAと再生成artifactSHAを別に記録し、是正候補の非作者確認前にP0解消済とは扱わない。

P0是正の採用（2026-10-30、PO委任Codex主担当判断）: 非作者REPORT633bc63596bcf5a9ad98c4a83e52468036d6ad5e2da777d519d49f10f5fbe9ccで重複P0解消・残P0/P1/P2=0を確認し、10path全SHAを照合して是正を採用する。旧/新T2が唯一evaluateEndConditionNoEndを用い、scope guardとformatterだけを分ける。前の採用保留と見落とし訂正の履歴を保持する。新artifact f0ac1ee0…cb80/29129bytes、source/実host/再現検査は成功。実保存と画面継続/正式全T2成立は未実施のまま。

### 通常継続の実保存step3開始受理（2026-10-30）

PO委任Codex主担当判断。保存境界候補JSON0a279f77…/境界docs5c14a6d9…を全SHA照合、非作者REPORT3e6d5a9af46c140f59952de3a8f84e3610c32ee7b01d01a8494cf49a1c9dfa2e（P0/P1/P2=0、末尾LF/CRLF拒否）を採用。44対向の設計/Schema成功を実保存・原子性の成功へ読み替えない。境界docs6章の閉source集合と必要なprivateモデル/migration・installer・既初球guard排他接合・source登録/テストの最小編集をstep3として開始する。正式共有登録資産/受理履歴の書込みはrootが直列管理し、作者の候補を正式受理済としない。全TX/冪等/認可/結果不明/既先行拒否を維持し、まず新規作成・開始からordinaryの連続保存と再取得を実PGで通す。数学sourceの完成を実prefix真正性の代用にしない。

### step4 再送レビューの有限是正範囲

送信済み結果不明slotのattempt欠落を新規生成で補わずread必須とし、HTTP0で閉拒否する。serverNext-1だけに依存する再開を廃し、既durableQueueの主複合key `[game,d4,d1]` を用いる `readSlotsPage` の有限keyset/limit+1読取と既read effect分類/specを追補する。新DBindex/version・queue書込意味・他slotのACKみなし受理は追加しない。最小未終結slotから原要求を順に終結する。非作者のP1指摘への技術的是正であり新野球意味の承認ではない。主担当はPO委任で本範囲の編集を承認、source反映後の非作者再確認は必須。

step4 source23pathの有限採用: PO委任によるCodex主担当判断、2026-10-30T20:30:03+09:00。対象files.json SHA9d61da89be3bba09a2f3956c1ee81d99fcc5d339cbf78cc9a34c094d1f8eae04、非作者反映1REPORT SHAded706e7e79bf3d7ba77ee7cafa123599e23cdec2a2dc7dce2257ef1935c412a（P0/P1/P2=0）。初回2P1と是正履歴を保持し、影響132件/独立70件成功を確認。source候補の採用であり実API/DB/HTTPS複数球、真のoffline再起動、MVP全体は未成立。本人の署名/逐行確認ではない。

### step3 source/正式資産候補の採用とstep4供給の同時接合

2026-10-30T20:50:20+09:00、PO委任によるCodex主担当判断。対象runtime48path packet SHA4cc21d57accd9c9d5437398f6927a24d7df5f890ae7b0663780bd3de5a6a4ce6＋root8 source packet65439104…＋逐次生成した正式DDL候補を、cache `ordinary37-backend-adoption-20261030.json` SHA73ca160c7b16ac327e345f4e69aa58a971cfb3a9bdaeadfc3597d84a112b7036 の全path/hashで固定。非作者最終REPORT361db72a…/反映1 2d07b4a5…/反映2 cd54b1a7…はP0/P1を解消。単位778/独立778・独立後発33・root guard271・ownedPG構造/故障負/既初球原子性16成功を確認。実API3球の1passed/88.60秒は8c46e2f8＋本未commit source集合、結果SHA5394344d0739035dfdfdee45cd29e836e46fa19c031f99c1bb51c323401dc2ba。

backend prefix原本readとstep4閉DTO/routerは相互import/共通真正性の接合を持つため、このbackend供給だけを同commitで保存する。step4画面source23は別8c46e2f8に保全済。正式HEADの画面縦断、故障全44、正式7.7/reseal/sourceallowlist/repository改訂/CI/通常統合は別残件であり、step3/4全体の受入完了としない。本人逐行確認/署名の代記ではない。4path書式のみの9feb3db3はAST完全一致で意味/入出力不変を別保全。

### step4 送信中controller寿命の是正

2026-10-30T22:34:01+09:00、PO委任によるCodex主担当判断。実b34e0b91のHTTPS診断（1failed/104.54秒）でsend.sent=true/ACK本文読取とparser/adapter全正常、disposedDuringSubmit=true→readAckなし→no-ack-receivedを確認。同内容DTOの新参照だけでwatchが送信中controllerを破棄する再現を旧componentで確認し、全入力snapshot/認証scopeの同値なら維持、真正変更は失効する最小2sourceを採用。files.json SHA5bf8b54a40386a36da945bea1a9e7251d9b15b9e57c65428fe3c9d35ddb0d9d2、作者34試験/型lint、非作者21試験とREPORT SHA91cd5bfdc5c990e4fca9dd1dd69baa5d62128d821dbece74559a046bcd53cc7c（P0/P1=0）。P6blind/本人確認ではない。

真正なgame/D4/recovery/checkpoint/rules/state/位置/auth変更と同参照深部変更は旧ACKを採らない。WebLocksの保持単位・認可・記録権・原要求・成功条件は変更しない。実環境の親再評価が全値同一だったかは未観測なので、修正の実原因解消は同HEAD実HTTPSで検証する。非blocking留保: 初期inspectがblockedだった後の同値DTO再供給だけの復帰は未保証（reload再生成は別）。MVP故障/復旧受入で扱い、今回source採用を実画面成功へ読み替えない。

### 保存後readの先行依存是正（2026-10-30T22:50:58.951507+09:00）

PO委任によるCodex主担当判断。通常prefix readを旧初球reader成功から独立させ、新prefix成功時は直採用、既codecが明示unsupportedとする場合だけ旧ABIへfallbackする。認可/404/409/503/破損の成功化なし。packet dbd590c950baafc9519d568177cade0c7fd15bf0c34e3e9af5168123ebddbc9eと3source実hashを照合し、非作者REPORT5761a97250c12d1f77d0de0290bf2ab56d1901bbbd1741c46e86aeab3ff02d9b（P0/P1=0、独立37成功）を採用。作者48成功/型lintと区別。実HTTPS再試験は本保存後に実施する。旧GETが503だったとの推定は実HTTP記録で未確定とし、旧read例外で新GETへ到達しない先行依存の解消を対象とする。E2Eの同水位待機条件は維持し30秒で失敗を報告、cleanupで元の失敗を覆わない。新しい意味/認可/正式契約変更ではない。

### 開始503の試験専用段階観測（2026-10-30、PO委任によるCodex主担当判断）

04d93b06の実HTTPSは開始POST503で88.78秒失敗し、再取得是正の実証へ未到達。既app.log0のため同条件再試行の前にbackend/tests/db/test_screen_start_e2e.pyの_app_container exact1へ明示opt-in診断bootstrapを追加する。既uvicorn factory/host/port/log設定・UID/envを保持し、元broker call/encode/reply_sourceを必ず呼ぶ透過wrapperで段階/処理種の有限enum/経過ms/公開status/限定exception classだけ記録する。原要求/資格/返値本体/例外message/SQLparamsを観測しない。原return objectとbare raiseを保持し、診断自身の出力失敗は業務結果へ影響させない。通常実行は既CLIのまま、期限/認可/成功判定の変更なし。限定非作者確認後に実試験へ供給し、原因未確定をtimeoutと断定しない。

### step3 正式登録の隔離修復候補（2026-10-30）

主担当の担当移管指示により、`fix/mvp-ordinary-registration` WTだけで登録表面を具体化する。通常CAP36は保持、repository34→35のtoken64→65/function8→16、base40→41のSQLA_INSERT単一窓口/fixtureを対象とし、生成定数/digest・全field対向を同期する。checker/拒否条件/対象集合を緩めない。

既developのlegacy記録とauthority#188を維持する。親PR189の未受理repo33候補の原文・基線をcacheへ保全し、親のpending修復/完全9射影候補と子PR190の受理候補を分離する。現実PR190基線が未修復pendingを含むため、子WTだけで履歴prefixを変更して正式CLI成立とは扱わない。親修復候補のレビュー/主担当反映後に実基線を追随し、正式受理の対象版・実前後値・独立レビューを照合する。本節は既step3登録範囲の候補具体化であり、7.7成立/本人確認/署名を代記しない。

登録修復の追加具体化（主担当指示、2026-10-30）: 既承認BigInteger生成形をcheckerの別exact ASTとして保持し、旧形・未知形拒否・対象集合は維持する。実registryはstar展開を許可する検査拡張を行わず、既source groupの各同一registration objectと静的literal IDを照合するdirectCallへ正規化する。helperは実型・閉ID集合・同IDを照合し、別group/偽reg/余剰IDを拒否する。SQL/IO/CAPのコピーや変更はしない。外部checker射影の動く8資産だけ現実基線から1世代追随する（repo35/base41だけを独立確定とはしない）。frozen-inputs6はこのcheckerを外部対象に持たず据置。親189/188固定点留保は上記と同じである。

### 既source登録13件の限定追随候補（2026-10-30、独立採否前）

通常37の正式登録検査で検出した既source/deploymentの旧pinを、実Git前後byteと
実全siteへ追随させる候補。製品処理は変更せず、所有pathと未知API/余剰site拒否を維持する。
ledger実装のbinding journal/G20追随は耐久意味の実差分を含むため、単なる行移動とは呼ばず
既採用根拠と全差分を独立レビュー対象へ渡す。7pathの開始条件2はD4単一符号化の移管で
51→49site、ledgerは17→20site、段階起動は同一path内の既5helper・実APIのみ追加する。
全前後値・元commit・対向結果はcacheの`ordinary37-registration-repair-20261030/pin13/`。
既188公開HEAD/受理記録差と親189history prefixは別留保。正式reseal/受理は未実施。

### 物理境界の残18所見を閉じる最小候補（2026-10-30、未採用）

通常保存repositoryのD5/原event/世代照合8点とtransactionのphase/実epoch参照を、
別exact2path・全16site・既SHA256・line/symbol/scope登録へ固定する。旧15siteは
既2型constructorをliteral分岐へ正規化することでfield参照が1回増え、実再導出16とする。
自由token_typeの許可や未知API/世代の許可は追加しない。

同Session committed再交付の所有照合helper1点はTB002へ混ぜず、別TB001登録単位とする。
path/FQName/実finding scope/line/symbol/sourceSHAのexact一致に加え、既全body ASTを
固定する。context/runtime/lookup/device/outcome/owner6値照合の削除・短絡・述語追加は、
自己申告hashを同時変更しても拒否する。未知owner/同path別scope/copyは拒否を維持する。
実helper自体の改名/意味変更なし、同MVP対象PRの実現物のみ、正式受理/reseal未実施。

候補はcache`ordinary37-registration-repair-20261030/remaining18/`へ分離し、
pin13のレビュー対象WT固定版を変更しない。candidateでのpytestは正式WT実証と別に記録。
既188公開HEADと記録after差/親189history prefixは引続き留保する。

### 正式登録候補の保存判断（2026-10-30T22:47:16.353326+09:00）

PO委任によるCodex主担当判断。全51path packet SHAfa5f1fd760389d9e3312953e7f90eb0e9e0b4d21bd36dcdf9103b9f6404ffcf4と全実byteを照合し、pin13非作者REPORT5963fb363f9a014c4e4f487c0c493732140914f834d62187841b2cda6c83ba95および残18非作者REPORT538efca0ceb019cd3ae5d5cb0318cfe8f8ed52edba5ea5397f25c707f1f2ecf9（いずれもP0/P1=0）を採用。新TB001/002登録とTB007有限2型のsource保存のみを承認する。独立34対向/current_product1/BE236成功、作者root123+追補35/BE608成功と区別。親履歴prefix/188公開版の追随/完全実前後7.7/公式CLI/最終CIは未成立であり、本保存で正式受理や本人逐行確認を代記しない。root記録: cache ordinary37-registration-root-adoption-20261030.json。

開始503観測sourceの保存（2026-10-30、PO委任によるCodex主担当判断）: exact1 source a37a2613af3436c4603e42787b955fd5eb382b9277e843a86b76960153ef5df9/packet1f903998280b582c28b305cd1324a3dd6e87b63ef59755efa3c82a09d2f92dbbと非作者REPORT8978af2ca0b47fabca85f44b10872b0886bba5c2ddfac0bbe430ca50edb8e580（P0/P1=0、独立pureprobe/ruff成功）を実照合して採用。通常CLI/返値/例外/観測故障の透過性、有限scalarと秘密不出を保持。実開始503原因や実HTTPS成功は本保存では未成立。共有helperの既型2件は別review済typefixへ追随予定。

Port登録期待集合の接合追随（2026-10-30、PO委任によるCodex主担当判断）: backend/tests/test_sync_first_ball_registration.pyだけ、既3Portに実ordinary content/projectionの2literalを追加し実5件の完全一致へ追随する。patch704682dc886f8cb1474ec4302dfa16e3427bce878e2941fdc9c4b584cc9ac2ca、非作者test差分REPORT2f8e6fe664402a79eb93ff69dee6a194a9ffcd63013d6be4065f7784ef1097cf（P0/P1/P2=0、独立pure2成功）を採用。定数以外AST/拒否試験を保持。レビュアーは元ordinary製品作者であるため、このtest追随差分の非作者確認だけに限定し、元coreの独立レビューを代替しない。

### 通常接合後の試験型22診断の是正（2026-10-30、PO委任によるCodex主担当判断）

初球型修復を接合後、819cd2ffでbackend全体tyが新ordinary試験側22診断を報告した。隔離fix/mvp-ordinary-type-checkの編集はbackend/tests/db/test_ordinary_pitch_storage.py、backend/tests/test_ordinary_order.py、backend/tests/test_ordinary_pitch_binding.py、backend/tests/test_ordinary_pitch_operations.py、backend/tests/test_ordinary_pitch_product.py、backend/tests/test_ordinary_preparation_binding.py、backend/tests/test_sync_apply_replay_before_binding.py、backend/tests/test_sync_route_shape.pyのexact8だけ。実shape narrowing/既正負fixtureの明示型castへ限定し、製品source/期待値/不正入力/readonly操作/全assertを保持する。Any/ignore/除外や検査緩和は禁止。実DBではないpure影響検査・全体ty/ruff/formatと非作者確認後に採用する。PG/主WT/ref/台帳/共有資産は作者が変更しない。新しい型診断を既CI28修復の失敗や全CI成功と混同しない。

上記型22診断の実内訳照合でtests/test_ordinary_pitch_payload.pyの2診断（Success|Failureの実narrowing/打順Literal）も同じ試験型是正であることを確認した。PO委任によるCodex主担当判断で当該1pathを追加しexact9へ限定する。製品/期待値/正負入力/全assert保持、Any/ignore/除外禁止、独立確認等の条件は同じ。

通常試験型修復の保存判断（2026-10-30、PO委任によるCodex主担当判断）: exact9 packet bc9c06b76e30630c66bd27981e007fa8dffda0838a3b138e78c5a31f7cfddd9aと全実byte、非作者REPORT59edf81029b67321ce26aefac7a37370a8a8fadbc1ae8ec18ac1ad4901cb7a8e（P0/P1/P2=0、独立109pure/全体ty成功）を採用。全旧assert/paramを保持し、cast/narrowing/正規immutable空mapping/preflight alias以外module AST不変を確認。製品source/期待値/拒否条件を変更せず、実DB/正式pin/最終CIは別条件。主WT実HTTPS中は取り込まず隔離枝へ保存する。

再送期待の正本整合（2026-10-30、PO委任によるCodex主担当判断）: exact1 helper patch bfe72aaf7a0c867e2e9795a03993db8ee3d1a348fd74cf577ecc9930adfb20a0、非作者REPORT44d1a438f56209e954aee2baa6f550954a1530eb40d3cb8677e01352cef2dcef（P0/P1=0、NodeVM9/BE22成功）を照合して採用。sync-protocol417/DI2は保存済受理の同D5同内容再送をA5重複と定める。初回受理期待は不変、late replayはD3=3/重複/sameSlot/HTTP200/count3を別々にstrict確認し、DB/reload全assertを保持する。0670実runは複合boolfalseしか記録されず実A5値未確定なので、次実測で正規結果を確認する。未ACKslotの重複による端末終結はこの既ACK済raw再送とは別故障残件であり、完成へ拡張しない。

開始期限sourceの有限pin追随保存（2026-10-30、PO委任によるCodex主担当判断）: 実broker31d740cce24a9bbeba7e5e4bd83d3d760df6533d8b411d22700dce686e06f519/全3前値を照合し、packet480f8a825a3348a5ca82c3c023733fee20bdcb14a4db2f4c8f402ba7c2548a8f/patch0766c7daa67abd62d5b70c3aa6c173c2431ff038ac4901bd257818bb097f8607/独立REPORTaae15bf3238eeff98ffe6f03e88d6ef4f3eb6eff4ee7e05fe72f135f838930c8（P0/P1=0、独立28成功/current_product0）を採用。20symbol/scope/API集合は不変、SHA/13行位置だけの追随。公式9射影で8変化・識別値据置、全外部byteをcache固定し、同未受理candidateの反映として保存する。親189prefix/完全7.7/公式CI未了、188公開不一致は既解消で再未決化しない。新受理/reseal/署名の代記ではない。

手動確認引渡しの保存（2026-10-31、PO委任によるCodex主担当判断）: manual-check/通常3球E2E exact2の最終packet60e0a70e2a4b55f178ab911e1b936cdae506d514d9542f93e68238635b8ba5db/実byteと、非作者REPORT864d249f…・文言反映4433b608…（最終P0/P1/P2=0、独立hold13pure/型ruff成功）を採用。既helperのdefault0/上限1h・全旧assertを保持し、DB照合後のadmin外/API/browser/brokers内に任意hold1callだけ追加する。E81成功/新hold未実行/歴史初球/実機と運用HTTPS待ちを区別、loopbackの一時URLを稼働中/公開URLと記載しない。鍵生成0/既証明書期限10/31 14:57:45JST、失効後は勝手に再発行しない。本保存は実機/新hold実施済や正式MVP完成ではない。
