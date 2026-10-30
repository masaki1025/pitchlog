---
feature: mvp-recording-continuation
status: approved
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
