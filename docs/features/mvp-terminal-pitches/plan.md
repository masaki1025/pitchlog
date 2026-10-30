---
feature: mvp-terminal-pitches
status: active
承認: 済（PO委任によるCodex主担当判断・ステップ1の操作単位契約作成）
重さ分類: コア領域
branch: feature/mvp-terminal-pitches
created: 2026-10-30
計画レビュー周回: 1
確定ゲート周回: 0
---

# 無走者の四球・死球で打席を進める操作単位

## 1. 背景・目的

基点は `e81c4edb5d2f55d67579e7e47aa9bbb24b6de055`。親は [TSK544 T1計画](../tsk544-t1-state-calculation/plan.md) と [通常継続計画](../mvp-recording-continuation/plan.md)。ユーザーの「全操作一括の着手条件から、操作単位の契約成立→本体着手へ変更」「MVP完成まで継続」「spikeを再利用する」指示を、この2操作に具体化する。新しい全体計画・全T1の再承認は作らず、親のステップ数・既レビュー通算・既不合格/未検証・全MVP義務を保持する。

追跡元は既 [TSK-544](https://app.notion.com/p/3f893b75e68781e5a55ce961b18fab3f)。[要件FR-003/012/014/020・NFR-018/019](../../requirements/requirements-pitchlog-2026-07-22.md) のT1対象別受入を本書5節へ写す。Notion側の状態/DoDを更新・同期したという記録ではない。

次の成果は、無走者で四球または死球を確定し、打者が一塁へ出塁、打順が進み、次打者の通常投球を記録・再取得できること。数学の契約成立、T1本体、T2/prefix、同TX保存、実画面の段階を分ける。T2/DB/全操作の完成をT1本体の着手前へ循環させず、数学成功を保存可能・Ready・ACKへ読み替えない。

本候補の作者はCodex `/root/pr188_final_review`。旧188/試験型修復での非作者役とは別で、本候補の独立採否を兼ねない。現時点の編集許可は本plan/researchと親TSK544末尾の子plan参照だけ。rootと別非作者の対象版判断前に製品/contract/正式資産/Git/ref/共有台帳/PGを変更しない。

## 2. スコープ

### 2.1 閉じる操作と有効な状態範囲

| 項目 | 今回の契約 |
| --- | --- |
| 操作 | `eventKind=batting-result`、`pitchEventKind=pitch-event`。`batting-result.walk` はS0..2/B3、`batting-result.hit-by-pitch` はS0..2/B0..3。初回実接続は明示四球/死球操作を使い、B4を作らない。B3のball選択を自動変換する場合はartifact由来の正準結果だけを使い、UI/provider/BEへ野球ルールを複製しない |
| 数学前提 | runners=empty、outs0..2、top/bottom、inning>=1、打順1..9、非負の得点/全scoreboard、gameEnded=false。回・得点・打順・アウトを初回表/0out/0対0/打順1へ縮小しない。数値は既canonical decimal/bigint。TB状態と保存規則の整合・前回openはT2/真正prefixで確認する |
| 併発観測 | 独立走塁/手動上書き/失策/打球/妨害/交代/再開などはこの操作へ合成しない。未知の同時効果を捨てて受理せず、既形式拒否または既知未実装として閉じる |
| 共通結果 | PA=true、両count reset→S0B0、batterDestination=reach/base1、既走者3枠はnot-applicable/null、out0/targets[]、after.runners=first、打順n%9+1。outs/回/表裏/得点/H/E/K/TB/gameEndedは不変 |
| BBの23flags | trueは投球数・与四球・打席・四球のexact4。他19false、board.walksのみ+1 |
| HBPの23flags | trueは投球数・与死球・打席・死球のexact4。他19false、board.walksも不変。B欄へ死球を加えない |
| 履歴 | 既push差分規則で今回1entry。count/打順/占有とBBのwalksの実前後差分・全23flagsを保持。過去tailは改変せず、prefix接続は今回entryだけを返す |

数学にはrunner実IDを生成させない。実保存は当該PAの真正打者IDと投手帰属を別に束縛し、空塁→一塁のrunnerを1名だけ投影する。四球の打席途中投手交代は要件A-2のボール優勢時の前任投手帰属を無視できない。履歴から帰属を確認できないPAはBB実保存を拒否し、現在投手へfallbackしない。PA開始以後に投手交代なしと真正に確認できる経路を最初の実接続とする（数学の状態範囲とは別）。死球は実現投手へ束縛する。既存の試合途中の交代履歴を全試合一律で禁止する意味規則は加えない。

state.scoreの両側とscoreboardの得点欄は同じ真正snapshotの値でなければならず、不整合を別の有効状態として受理しない。両score欄を独立に書き換える権限はcallerへ渡さない。

### 2.2 再利用と今回提供しない操作

spike `41d7175dcc28730c61f28ff0d9de8c27664e4628` / `8e1bf4310f3db2a4e9f3302b2e3bc2833287feae` のwalk/HBP規則、count reset、打順進行、23flags、forward差分を選別再利用する。現 `state.ts` の唯一核へ取り込み、ordinary37/初球と共有する。spike全publicApi・第二の状態計算/履歴計算は輸入しない。具体比較は [research](research.md)。

他7塁の強制連鎖、満塁得点/RBI、申告敬遠、三振、打球、交代、取消/訂正/終了再開は後続操作として残す。今回の無走者制限を恒久製品要件にせず、全操作/全T1/T2/MVP完成とはしない。取消/訂正の提供は後続でも、source/runner/history参照と版失効を今回から保持する。

## 3. 影響する正本・契約・コア領域

規範は要件FR-003/004/012/014/020、E-1のXC-06/10/13・全23flags、E-2四球、ADV-01〜04、A-2責任投手、A-3打数、RBI-07、データモデル5-2のPlayRunner正規化、4-4の状態差分。既 `state_transition_contract_v1.json` にはBB/HBP行があるが無走者全countケースと製品ABI/保存接続が不足する。新野球意味の裁定を推測しない。今回確認した不足は契約供給・接続であり、新PO回答待ちを新設しない。新意味不足を見つけたら該当規範/入力/未決結果だけrootへ返す。

| 正本 | 今回の計画差分と将来の扱い |
| --- | --- |
| requirements / design / ADR / development / ops | **反映なし**。既規範の操作限定実装であり、新設/版上げを本計画に含めない。将来実装で正本構造の改訂が必要になれば実差分と7.6判定をrootへ返す |
| docs/features/tsk544-t1-state-calculation/plan.md | 既履歴を保持し末尾に本子planの範囲と開始ゲート参照だけを追記 |
| contracts / core / authz・凍結派生値 | この計画起案では**反映なし**。後続段階の候補/受理範囲は下表。正式writeはrootだけ |

| 所有 | 有限資産・境界 |
| --- | --- |
| T1契約候補（ステップ1） | 新 `contracts/state-transition/terminal_pitch_schema_v1.json`、`terminal_pitch_v1.d.ts`、`terminal_pitch_cases_v1.json`。既 `state_transition_contract_v1.json`、`input_axes_descriptor_v1.json`、`branch_row_mapping_v1.json` の当該2操作の規範/coverage参照だけ。既case/ID/期待を削除・変更せず、不足行は別IDで追加 |
| T1 source（2） | `frontend/src/domain/{state.ts,stateRules.ts,publicApi.ts,publicApi.spec.ts}`、新 `terminalPitch.spec.ts`、配布 `frontend/public/domain/{pitchlog-domain.js,pitchlog-domain.json}`、新 `backend/src/pitchlog/domainrt/terminal_pitch.py` と `backend/tests/domainrt/test_terminal_pitch.py`。stateTypes等の追加変更が必要なら具体差分を先にrootへ返す |
| T2/prefix候補とsource（3） | 新 `contracts/state-transition/{play_prefix_v2_schema.json,play_prefix_v2.d.ts,play_prefix_v2_cases.json}`、新 `frontend/src/domain/{playPrefixContinuation.ts,playPrefixContinuation.spec.ts}`、既 `firstPitchContinuation.ts` / `ordinaryPitchContinuation.ts` / `publicApi.ts` とそれぞれの既試験、同配布artifact、新 `backend/src/pitchlog/domainrt/play_prefix_continuation.py` / 対応domainrt試験。既T2終了規則核を共有し式を複製しない |
| 同TX保存/再読込（4） | 新 `backend/src/pitchlog/{repositories/play_prefix.py,sync/terminal_pitch_payload.py,sync/terminal_pitch_projection.py,sync/terminal_pitch_tokens.py,authz/terminal_pitch_product.py,authz/terminal_pitch_write_stamp.py}`、既 `repositories/{ordinary_prefix.py,ordinary_prefix_read.py,ordinary_prefix_operations.py,ordinary_pitch_operations.py,operation_registry.py,transaction.py}`、`sync/{apply.py,ports.py,ordinary_pitch_execution.py,ordinary_pitch_ports.py,ordinary_pitch_projection.py}`、`authz/{ordinary_prefix_sql.py,product_catalog.py,product_function_acl.py,product_provisioning.py}`、`api/schemas/started_games.py` / `api/routers/started_games.py`。対応pure試験と新 `backend/tests/db/test_terminal_pitch_storage.py` を同単位で追加 |
| UI/queue（5） | 新 `frontend/src/api/{terminalPitchWire.ts,terminalPitchWire.spec.ts}`、既 `api/{startedGame.ts,recordedPrefixGame.ts,ordinaryPitchAck.ts}`、`lib/{ordinaryPitchAttemptPersistence.ts,ordinaryPitchAttemptPersistence.spec.ts}`、`screens/{GameScreenOrdinaryPitch.vue,GameScreenOrdinaryPitchController.ts,GameScreenOrdinaryPitchProvider.ts}` と各既試験、既実画面E2EへBB/HBP系列を追加 |
| root唯一writer | 各段階のcore先行宣言/test→別JSON登録、authz product生成SQL/manifest・runtime契約・schema検査・tenant/census等の実影響集合、凍結4面/7.7/必要pin。本表はこれらの無制限編集許可ではない。段階4着手前に関数署名/role/列ACL/必要物理差分とexact生成path manifestを本plan追補へ固定し、非作者確認後にsource指示する。新table/migrationが必要ならその実理由・exactを追補し、仮SQLや未登録ACLでDB成功を作らない |

コア帰属は状況計算/T2・同期プロトコル・記録権/tenant、物理変更があればデータ移行。新pathは6.3の意味範囲に従いrootが先行登録し、既pathや拒否を縮小しない。requirements/design/ADRの新設・版上げは本計画で許可しない。実装追随は7.6、正式契約/登録は実差分から7.7を守る。旧署名/受理・レビュー数を代記しない。

## 4. 実装方針・有限ステップ

重さ分類はコア領域。T1/T2状況計算、同期の冪等/原子性、記録権、tenant付き保存原本を扱うためで、単なるUI結果追加に分類しない。

### 実装ステップ(コミット単位)

| # | 実装単位 | 合格条件・次の解除条件 |
| --- | --- | --- |
| 1 | 無走者BB/HBPの操作単位契約を固定 | 下記最小case・全比較面/履歴/23flags・ABI・範囲外拒否、規範参照とspike差を非作者が確認。rootが本操作のP-1〜P-9の適用/依存を項目別に固定し、必要な独立導出/契約所有側受理・正式影響値を採用。この有限対象が成立したら2着手可。全T1/他操作/T2実保存の完了を条件へ追加しない |
| 2 | 唯一T1核と固定artifact/Python callerへ接続 | private `applyCountRule`をPA終了/出塁にも使える単一helperへ有限factorし、初球/ordinary37の全値保持。新deriveTerminalPitchだけを閉ABIで公開し、同artifact/固定host一回呼出。Python計算・case lookup禁止。契約全値/再build/旧回帰・非作者source確認後に採用。T1のみの完成を3/4成功としない |
| 3 | play-prefix v2とT2を接合 | 以下のv1→v2 bridge/履歴1entry・runner identity境界を固定し、新operationで同一T1評価結果を既終了規則核へ渡す。PA=trueの許可条件をexact2操作へ閉じ、ordinary37のv2後続も共有核で扱う。旧v1 ABI/PA=false gateは不変。typed caller/全値/拒否・独立確認後に4へ |
| 4 | 実source/runner資格と同TX保存・再読込 | 既実writer/RG1/tenant/同D5優先を保持。PlayRow＋PlayRunner＋source/event/ledger＋history＋checkpoint＋水位を同TX化し、実ownedPGで正常/再送/故障全取消/越境拒否を実証。登録sourcepin/必要7.7を実前後値へ結合。runner原本と次打者を読み返せるまで完了としない |
| 5 | 実UIでBB/HBP→次打者の通常球まで | 既観測/認証/記録権/WebLock/耐久slot/元ID再送を再利用。実ownedHTTPSの作成→開始→四球（B3で明示四球操作）/死球→prefix GET→reload→次打者通常球、HBPでB増分0を観測。最終HEAD非作者/必要正式値/必須CIを揃え、通常PR統合。全MVP完了とはしない |

各段階は指示された1ステップで停止し、次を無断実装しない。現在は計画候補だけで、ステップ1のcontract編集も未許可。rootが本固定packetを別非作者へ渡して限定承認/具体指示する。新たなPO本人承認待ちは作らない。既契約ゲートの必要な独立性/正式受理は省略しない。

### 4.1 prefix v2の具体境界

v1 PrefixRefはordinary-only長で、D1/D2/水位/全操作数ではない。新 `scope=play-prefix-v2, version=2` の参照はtenant/game/D4、確認済play長、checkpoint ID/revision/digest、historyVersionへ束縛し、D1/D2/適用水位は別fieldとして保持する。v1のlengthを文字列置換して昇格しない。実同TXでv1の開始原典またはordinary-only確定prefix、最終event/ledger/全PlayRow、history深度、artifact/rules/配置/digestを照合し、ordinary-onlyであったことを証明した一回のbridge元参照をv2に保存する。数値が同じだけではbridgeしない。旧参照/別tenant/D4/版/後着checkpointは拒否する。

v2は当該2操作と既ordinary37を区別し、T1のbefore/derived/afterを一回だけ評価する。新規runnerはserverが真正PA/実打者/責任投手から供給する別identity snapshotで、自由入力/数学の占有enumから推定しない。T2は前回open/規則の実一致と今回の実afterを既 `evaluateEndConditionNoEnd` の単一規則核へ渡し、成立/lock/未評価を固定falseで潰さない。終了/lockなら入力を閉じる。BB/HBPだから常に正常というlookupにしない。

### 4.2 runner保存と次の球

一塁snapshotは実batterId、responsiblePitcherId、base1、status=既設計の「継続」、status_source=auto、source event/playとcheckpoint/history版を持つ。既PlayRunnerのtenant付き複合FK/退役一意・親論理削除を再利用する。status文字列の実保存表現と保護対象全列を段階4の物理packetで固定する。現41列stampだけをrunner能力へ読み替えず、v2 stampにexpected runner全値/数・実frame/source/同TX・一回消費を束縛する。

次のordinary球では一塁の実runner/責任投手を保持し、次打順の真正batterへ切替えて各playのrunner snapshotを同じ原本から投影する。旧ordinary-only readerへterminal履歴を流さず、新 `recorded-play-prefix-v2` variantをread DTOに追加し、v1 fixture/旧応答の意味は保持。取得はtenant/game/確定水位でDB絞込＋有界ページ/cursor、過去全件読込でcheckpointを捏造しない。元D5再送は元body/frame/sourceを照合して再掲し、PlayRunnerも履歴も増えない。commit不明は元slotを保ち、ACK/取消/新attemptを補完しない。

## 5. DoD

- [ ] 本plan/対象SHAを非作者が確認し、rootがPO委任による有限採否・ステップ指示を記録する。作者を独立reviewへ数えない。
- [ ] 操作単位契約が無走者BB/HBP全count/状態軸/全比較面を覆い、必要独立導出・規範/既契約/descriptor/正式影響の確認を終える。通常の非作者レビューだけをP6 blind成立としない。全P6/他操作の残件を維持する。
- [ ] 初球/ordinary37/既ABIを後退させず同一T1核・同一artifact・再現build・Python固定hostを通す。未知scopeは非成功。
- [ ] v2 bridge/T2実評価と実runner帰属が成立し、同TX全取消/元ID再送/真正checkpointからのGETを実証する。
- [ ] BB B+1、HBP B不変、打順9→1と次打者/一塁runner/責任投手保持を実画面・再読込で観測する。
- [ ] 最終HEADのcore/非作者/正式pin/必要7.7/必須CIと通常PRを満たす。共有DB・運用秘密・本人署名を本単位で扱わない。

## 6. テスト計画（着手に必要な最小集合と段階別検証）

**ステップ1の最小契約集合**はBBのS0/1/2・B3の3全応答とHBPのS0..2×B0..3の12全応答、計15手規範例。全例は10列効果＋after全field/全scoreboard/23flags/今回history entryを持つ。打順/outs/表裏の独立性は15×3outs×2half×9打順=810の交差を省略せずtest展開して確認する。期待の算出元は規範と独立確認済みのcaseテンプレートで、spike/製品artifact出力から期待を生成しない。全810を手書きJSONへ重複展開することは着手条件にしない。

回1/規定回/延長回/大きな正整数、両側得点と非ゼロH/E/K/B、TB有効/無効を規則整合付きの独立性対で確認する。打順1..9（9→1必須）、outs0..2、top/bottomを初期状態へ縮小する変異を落とす。BB B0..2、HBP/BB範囲外S/B、在塁7種、未知結果/非投球/終了状態、併発観測、非canonical/余剰/重複key等の拒否を含める。HBP B欄増分、打数true、旧打者据置、reset未反映、history tail改変、全23flagsの一箇所改変が必ず赤になる対向を用意する。

ステップ2はVitest＋同artifact Node/ブラウザのfullvalue、旧通常/初球全値、再build hash、Python pytest/strict decoder/host一回/故障、ruff/ty/TS型lint。step3はv1保持、bridge証拠欠落/別owner/版/digest/長さ/水位混同、PA=trueの別操作、過去lock/規則不一致、T2未評価、terminal→ordinaryの履歴とrunner保持を対向確認する。

step4/5の実ownedPG/HTTPSはroot指定の隔離fixtureだけ。正常BB/HBP、oneTX各段階故障（PlayRow後/runner後/history/checkpoint前/commit前）でevent/ledger/投影/水位全取消、外部D4/claim消費は別観測、同D5二重再送、wrong tenant/game/player/責任投手、資格失効/RG1閉鎖、commit後応答断→元要求再掲、GET/reload/次打者/次球、旧cursor失効を実証する。数学810/純試験を実DB成功と呼ばない。重検査は固定候補の区切りで一度実施し、失敗・変更後の必要影響だけ再検査する。

### 計画の有限採用とステップ1指示（2026-10-30T23:48:11.252479+09:00）

PO委任によるCodex主担当判断。作者packet ab60a84fd5df7aa4a4845f375f0415bee41c62084e6698e9051bf018f1251680/全3path実byteと非作者計画REPORT dc2301ecc7256f03e5caab568defd4abf2bc65b93da4f517db819188915e748f（P0/P1=0、P2=1）を照合して採用。P2は明示四球/死球操作を最初の接続とし、自動分類はartifact正準結果に限定する上記2箇所の具体化で閉じる。reviewerは旧walk準備作者だった留保を維持し、その旧probeを新blindや本契約の独立導出としない。

本採用で上表ステップ1の有限契約/schema/types/cases/既2操作参照・必要な当該契約検査だけを指示する。起案段のcontract未許可記述は本対象範囲に限り解除し、製品T1本体/ABI artifact/Port/DB/正本新設・版上げはまだ指示しない。step1の全比較面/15例と810交差/範囲外拒否を別の候補非作者へ渡し、P-1〜P-9の本単位の適用/既成立/未成立を具体値で記録した後にstep2本体へ進む。実Port/T2/HTTP/DB耐久性の完成を計算開始の追加前提にしない。正式資産唯一writer/旧T1全体の未閉/P6封印・曝露履歴/全MVP義務を保持する。山田正輝本人の署名・逐行確認ではない。

ステップ1の契約検査配置（PO委任によるCodex主担当判断、2026-10-30）: 新testpath登録を契約作成の全体待ちにせず、既登録tests/test_state_transition_contract_schema.pyへ本単位専用の関数群として追加する。既JSONでsync-protocol/game-state双方に捕捉されることをrootが確認済。既test/expected/param/拒否を保持し、terminal契約だけの新検査を追加、既fixtureを緩めない。tests/test_terminal_pitch_contract.pyは今回作らず、core対象/拒否を減らさない実装配置の選択とする。

ステップ1の追加正例と参照整合（PO委任によるCodex主担当判断、2026-10-30）: 正規15caseのbranch登録と正式checkerのexact-set整合に必要なcontracts/state-transition/state_transition_manual_fixtures_v1.jsonのADV01追加正例15件、および既branch_row_mapping_v1.jsonの同15参照を有限追加許可する。旧case/期待/ID/規範・全参照を保持し、新正規caseの真正参照だけを増やす。既input_axes_descriptor_v1.jsonの値域は足りるため、不要なaxis/値/digest目的更新は行わず不変照合でよい。checkerを緩めず、関連CLI/射影/coverageをまとめて検査して整合を閉じる。候補の作成許可であり正式受理ではない。

正例本文の配置を現物に従い訂正（PO委任によるCodex主担当判断）: 追加15正例の実本文は既fixtureSources登録済contracts/state-transition/state_transition_manual_fixtures_v1.jsonへ置く。manual_fixture_branch_coverage_v1.jsonは本文ではなく索引/免除一覧なので今回不変とする。branch_row_mapping_v1.jsonの同15参照とのpair、旧例/規範/期待/全既参照保持という範囲は同じ。上の許可文のpathをこの実体へ訂正済みで、誤った索引を編集する許可ではない。

required-setの不可分参照追補（2026-10-31、PO委任によるCodex主担当判断）: 新無走者2rowが既identity区分と重複するCLI拒否を解消するため、required_set_row_rules_v1.jsonのBB/HBP各empty-runners区分、およびrequired_set_coverage_declaration_v1.jsonの旧first-third/newemptyの提示4観測だけを候補編集に追加する。checker/旧case/旧期待/過去履歴を保持し、全8配置が新たに成立したとはしない。partitionの排他性・旧範囲/残未充足不縮小とcovered/missing/partition集合の前後を検査・固定し、別非作者確認とroot採否へ渡す。正式受理や全P成立ではない。

既明示true到達性の保持（2026-10-31、PO委任によるCodex主担当判断）: 新2matrixのgameEnded=falseにより、旧operationRowsに既存の明示gameEnded=true到達性までcheck_input_coverage_exactが排除するfalse-positiveを確認した。same checker内の当該固定状態フィルタ＋既test_required_set_coverage.pyの最小是正を許可する。matrixの制限は保持し、別layerが自身の明示fixed/finite predicateまたは既row bindingから当該値を真正に実現すると証明できる場合だけ除外対象外とする。無関係操作の自由値穴埋め、一律gameEnded=true許可、全descriptor許可、未知row/fieldの許可は禁止。矛盾predicate/自由値/未宣言値/ended perPitchを拒否し旧正例/missingを減らさない対向を固定して別非作者へ渡す。新row条件/旧caseを削って緑化せず、正式履歴/受理の書換えなし。

新15caseの機械的派生追随（2026-10-31、PO委任によるCodex主担当判断）: game_end_coverage_declaration_v1.jsonのnormalCaseCounts.stateTransitionを旧117＋新15=132へ候補更新する。同15caseに必然のcount/source blob hash/参照digestについてはcontracts/state-transition配下の既存JSONの派生fieldに限り実CLI依存閉包へ追随できる。実path/field/完全前後/算出元SHA/旧集合完全保持を最終packetで固定する。semantic predicate/期待/旧case/拒否/過去履歴/受理/seal/資格の変更は含まない。checker論理の変更許可は既明示範囲に限定、無関係な基線やrevisionを動かさず、正式受理/全gate成立とはしない。

### 操作単位契約の受理とステップ2開始（2026-10-30T15:38:42.728062+00:00、PO委任によるCodex主担当判断）

全13path packet53615ab01fe4cbbe1742ffcaa5b270087ba05056bdca231714a270ac45f02ac3/実byteと非作者REPORTa82076b57bc7fd529f4392fa9c28d8f65e96fbd4c3cf34c6dc62c698565363e5（新P0/P1/P2=0、独立15全応答/810/履歴45・pure62/正式関連CLI成功）を照合し、数学操作単位の契約候補基線を受理する。旧117case/49row/12ID対応・到達4集合/missing5を保持。項目別判断はcache terminal-pitches-root-step1-acceptance-20261031.jsonに固定する。P2/P6/P7/P8は本無走者2操作/対象版の値と責任境界だけを採用し、旧20fail・歴史baseline/正式7.7/pin・全P6/P8/T1の残件は別未完として保持する。新blind/本人逐行確認/正式develop統合ではない。

本契約基線に従うステップ2の唯一T1核共通化・新閉ABI/同artifact/固定Python caller・必要試験を指示する。step3以降T2/Port/DB/HTTPの完成をこの着手条件へ追加しない。型/15全値/変異/旧37/初球の回帰・新artifact再現値と非作者source確認が揃うまで提供完了にしない。必要なsourcepin/既fixture内artifactSha256等の機械的追随は実新hashをrootへ渡し、正式writerが直列化する。

ステップ2の公開ABI個数の厳密追随（2026-10-31、PO委任によるCodex主担当判断）: 既firstPitchContinuationArtifact.spec.ts/ordinaryPitchContinuationArtifact.spec.tsの公開口一覧・見出しだけを旧7名保持＋deriveTerminalPitch1名のexact8へ追随する。未知extraやpartial比較は許可せず旧assert/順序を保持する。旧flag変異testは変更せず、共有sourceでfalse再代入が旧変異を打消す部分を除き、BB/HBP時だけtrue設定する。artifact再build実hash確定後にrootが機械pinを更新し、同入力の既知hash失敗を重全件で反復しない。

artifact機械pin追随（2026-10-31、PO委任によるCodex主担当判断）: 実再build0eb0fa99fc3fac4e3dfc13e3cb33be2d452e52bd1c6908ceb41925e442f0a08a/31220byteをroot照合し、backend/domain/manifest.jsonの既directTarget1hashとfirst_ball_payload_vectors_v1.jsonのartifactSha256/埋込/期待frame計102だけを旧f0acから差替えた。逆変換で旧filebyte完全一致、caseの意味・期待結果・旧履歴は不変。全前後はcache terminal-pitches-step2-pin-root-20261031/files.jsonへ固定。新T1の対象別manifest/runnerの追加記録は実源に基づく別追補とし、旧quantization宣言のhash更新だけを新操作の正式提供/BOOT全成立/7.7受理とはしない。

ステップ2の既基線型公開表とD11実測記録（2026-10-31、PO委任によるCodex主担当判断）: prohibitions.spec.tsの既DurableQueuePage1名だけを既13名保持のexact14へ追随する。新runtime公開や未知typeを許す変更ではない。重全件1失敗/残2757成功を保全し、そのstatic1行修正後は当該41検査で確認、同入力の重全件を直ちに反復しない。D11は既course定義/閉schemaを緩めず、backend/domain/terminal-pitch-manifest.json・terminal-pitch-property-catalog.json・同.schema.jsonの候補3pathと既test_terminal_pitch.pyの実測structured property/trace出力を許可する。真正実行値/実hash/全比較/明示propertyを持つrecordだけ採取し、未計測60単体をpropertyとして埋めない。別manifestを置くだけで既BOOTへ結線済/wholeJUnitComplete=true/正式vector・mutation全成立としない。対象別宣言/2propertyの限定実証は最終sourceレビューへ渡す。


### ステップ2数学source採用とステップ3指示（2026-10-30T16:09:15.594980+00:00）

PO委任によるCodex主担当判断。作者17path packet52814b4e60355c177b5944207ee2cfcdf4e8be92bc7abcd621854a7c62cf547dの全実byte、および非作者REPORT b2da6d22ded5877ac81acf9d2d28d423eaaf811a97f94d5c4c5d9acf8b742879を再照合し数学sourceを採用する。新P0/P1/P2=0、独立810交差＋追加150状態・typed host15例、BE62/FE95＋旧119の成功が対象。旧全件2757成功/型表1失敗→局所41成功という履歴は保持し、最終全件成功へ読み替えない。D11の2recordのみ成立、60除外・wholeJUnitComplete=false、正式vector/mutation/BOOT・旧20fail・正式7.7は未閉である。

本採用により上表ステップ3だけを指示する。v1 ABI/PA=falseを保持し、真正v1→v2 bridge・T2共通核・履歴1entry・runner identity/責任投手境界とterminal後の通常投球を契約と実artifactへ結線する。数学でrunner UUIDや真正性を捏造せず、保存段の実source資格を要求する。ステップ4のSQL/ACL/migration/DBおよび5の画面は未許可で、具体依存を固定した上で次の指示へ渡す。本人署名・P6 blind・全T1/全MVP完成ではない。

ステップ3のcore先行捕捉追補（2026-10-31、PO委任によるCodex主担当判断）: 新playPrefixContinuation.ts/同.spec.ts・play_prefix_continuation.py/同testは既game-state等に捕捉済だが、同期のprefix/source証拠も扱うためsync-protocolへexact4pathを追加する。既path/area/拒否を削除せず、独立レビューで追加だけを確認する。作者のsource編集許可とcore登録のroot直列所有を分ける。

同期core捕捉4path採用（2026-10-31、PO委任によるCodex主担当判断）: 非作者REPORT terminal-core-path-nonauthor-20261031/REPORT.md SHA0bc6e0c501b2227586fafca70e38b3ce1ebfcf26dcb27ef3eb72f23e5449ea8e、実source2405701134ebbcb2338655df05f9784e80c025e59116162b28807740209a0b3bを照合。新指摘0、逆JSON差分で全旧field/area/path同順一致・捕捉縮小0。6.3⑤の有限追加を委任採用し先行登録する。同期の数学/真正資格/DB成功や全MVPの受理ではない。
