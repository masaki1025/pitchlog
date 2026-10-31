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

ステップ3の実loaded artifact束縛（2026-10-31、PO委任によるCodex主担当判断）: backend/src/pitchlog/domainrt/host.py exact1の既検証済み不変_source UTF-8 byteに対するread-only artifact_sha256 property追加を許可する。新callerのsource証拠hashと実loaded artifactを照合し、一回呼出し前に不一致拒否するため。別artifact供給/host選択/書込/野球計算を追加せず、旧constructor/検証/呼出しの意味は不変。ファイル再読込TOCTOUを避け、同実loaded sourceに束縛する。差分を最終step3非作者対象へ含める。

ステップ3の機械pin追随（2026-10-31、PO委任によるCodex主担当判断）: 再build実artifact052f5c0a61d861176a2de5ae06055e16c9a0b2a192cfdc861a740cde4d5bedc4/40239byteを照合。backend/domain/manifest.jsonとterminal-pitch-manifest.jsonの各directTargets[0].hash1ずつ、およびfirst_ball_payload_vectors_v1.jsonのartifactSha256/埋込/期待frame102の計104だけを旧0eb0fa99…から差替える。対象course/state sourceのhashは不変、逆置換で元byte完全一致を記録し意味/期待/正式履歴を変更しない。新prefixの正式manifest/BOOT/7.7成立の代替にはしない。

### ステップ3数学接合の採用保存（2026-10-31、PO委任によるCodex主担当判断）

作者18path packetff3806645b2513f05e04a816ef929f770ccd2c1a7e837b71ff7a63f88bc17d4d/実byteと非作者REPORT77cc6f959ad5ca0f53c80f2b4623be1231af9e020a61cccc27d0d6282b814222を照合、新P0/P1/P2=0として数学sourceを採用する。v1保持、T1唯一核/T2共有核、今回history1entry、runner射影、既A-2の24count＋拒否10・bridge拒否16、typed実loaded hash/一回callを対象とする。独立局所24pass/3.33秒、作者419FE/228BE/Chromium100と再buildartifact052f5c0a…/40239byteを確認。root別全frontend132file/2770test全成功121.51秒、終了後18hash不変。104pin逆置換全byte一致、旧ABIと未知拒否を保持。

実source資格/bridge一回消費・runner同TX/元D5再送/原子的取消/GET/UIはdependencies.jsonのステップ4以降で未提供。正式v2 D11宣言・vector/mutation/BOOT/7.7/最終CI・旧20fail/全T1も未閉で、数学成功や全FE成功をこれらへ代替しない。次は作者が準備する実SQL/列ACL/物理有無・head/anchor/digestの具体案を本planへ最小追補し、必要非作者確認後にステップ4のsourceを指示する。新しい全体計画や既判断の再取得は作らない。本人署名/P6 blindではない。

採用済共通候補の接合（2026-10-31、PO委任によるCodex主担当判断）: 数学step3 source9736e06dへ共通候補320f196bを通常mergeする。差分12pathは既採用ACK重複decoder/故障復旧witness・開始sourcepin・手動手順/診断と既独立レビュー済みのもの。step3全18sourceはmerge後もpacket SHA不変、T1意味/契約の再判断なし。旧e81起点へACK喪失修復を取りこぼして将来差分で後退させないための接合であり、正式develop統合ではない。接合の影響検査と同candidate実HTTPSの旧3球/ACK喪失を確認し、成功前には9736の全Vitest成功や旧320の実画面成功を接合版の証拠にしない。

### ステップ4の有限接続追補（2026-10-31、PO委任によるCodex主担当判断）

既ステップ4の範囲を維持し、[閉path manifest](step4-path-manifest.json)（原byte SHA6acda6bc2bb07311a050527e7940bb883bf54cdac95dc215096cdef3fffa5cf0、exact78path ad4afa2b40aff9601bcc04a8a35dc6affbce21c453e0e26e7e8b5e48f21f8c5b）を編集所有/SQL7署名/app4 private3/10列ACL/2policy/2trigger/共有13資産の正確な集合として採用する。schema-manifestはverify-onlyで新table/ALTERなし。未知pathへ自動拡張せずrootへ実差分を返す。ソース作者と正式rootwriterは同manifestの分離を守る。

接続は反映1 SHA588a84a277b3b2f9f951b15af0a6fdfa96f3a4da40e13f3ab42c34c614caeec8の方式。storage anchorとhistory epochは不変、wire head ID/revision/historyVersionを明示分離、raw v1 storage-beforeを数学v2 bridge viewで置換しない。next wire digestは未信頼提案であり、実一回数学出力と真正before/sourceからexact Wのcanonical hashを組み一致までprepare不可。自己echo2以外のprior/他digestは除外せず、private full content_digestとも別。IDは元D5の耐久要求/私有frameへ一回固定、現物tenant内PK/FKとowner照合を守り、全tenant同UUID照会を追加しない。

P1旧案を不採用: V7だけ新calculation variant、V8は実newHistoryEntry.differenceのcanonical全値、readも独立評価差分と完全照合する。既D5/連番/RG1/認可/拒否優先とcommit不明・元要求再送を保持。PlayRow後のAFTERでrunner10列/実集合→checkpoint CAS→履歴→印消費を同statement/同TXで完結し、後置finalize未実行で部分commitする窓を作らない。新writer/source資格をbool/自己申告/任意SQLで代替しない。

非作者初回f6f3fd13…のP1=1は反映1で閉鎖、path閉列挙含む最終REPORT4bd16cdb1344f7b27da6cff435bd1f5bd2c7a96ec09b282bf5f620667def5a23で新指摘0を確認。旧指摘/初版/通算reviewを保持。新pure6+DB1/既stamp検査1とsourceの必要areaを先行core登録し、その追加だけを非作者確認後にsource4を指示する。正式生成資産はmanifest exactのみにrootが実SQL/宣言から生成し、D11・vector/mutation/BOOT/7.7と実PG全取消/越境/再送・GETが未成立の間は製品完了としない。

接合ab530b31の数学18hashは不変。root接合FE29成功/3.71秒、実HTTPSの通常3球＋ACK喪失復旧は2成功/114.27秒。TLS PATH未供給の2skipとbrowser tmp未作成の2失敗は別ログとして保持し、製品成功へ数えない。対象固定HEAD/同一製品版、各試験は別owned DB、実機受入とは別。source4着手前のfreezeは本実検査完了により解除可能。

### ステップ4 source開始指示（2026-10-30T17:17:40.820477+00:00、PO委任によるCodex主担当判断）

反映1/閉78pathと非作者REPORT4bd16cdb…、core57追加/14pathと非作者REPORTd9872ff10f3be5ebbde8989940229849be144c895ec37652ba2c0c29f63f1092・実sourcebadcaa52…を照合し採用。旧全core field/path同順保持・捕捉縮小0。実HTTPSfreezeはab530b31の2成功/114.27秒で解除済。本manifestのsourceAuthor集合に限り、作者pr188_final_reviewへステップ4の実装/pure検査を指示する。新手順/全体計画の待ちは追加しない。

編集順の具体化: 閉manifestのSQL7/ACL10/policy2/trigger2が先行有限宣言であり、作者は実source/SQL生成producerとpureを先に作成できる。rootFormalWriterOnlyの実JSON/配布SQL/compat/D11/生成資産はrootが実sourceから直列反映し、その反映前に未登録SQLをDBへ仮適用して成功を作らない。新modeは必要登録/実資格がなければ閉拒否のまま。正式metadata/7.7と実DB完成をsource起案の前条件へ循環させず、実owned PG/提供/通常統合の必要ゲートは全保持する。

source4は真正source資格/元D5/一回bridge・新ID固定、実T1/T2/差分V8、PlayRow＋PlayRunner＋checkpoint/history/印消費の同TX保存とGETまでを実装する。根拠のないtrue/fixture成功応答/任意SQL/認可迂回0。旧ABI/ACK復旧/元要求再送/拒否優先を保持。段階5のUIへ無断拡張せず、source4のコード/型/API不一致是正・限定検査と原子性の準備を完成まで進め、固定sourceとroot必要正式差分を渡す。PGはrootのみ、実公開/共有DB/新秘密/本人署名なし。

実HTTP Port選択の不可分2path（2026-10-31、PO委任によるCodex主担当判断）: sourceAuthorへbackend/src/pitchlog/api/routers/sync.py（既HTTP入口の新v2 modeに対する実Port対選択だけ）およびbackend/src/pitchlog/sync/port_guard.py（新実Port2クラスのexact型登録だけ）を追加許可し、閉78pathへ当該exact2を有限追補する。認証/C2/受付scope/原wire/拒否優先/同writer資格を保持し、shape不正・未知modeを旧Portへfallbackしない。json default parseで重複/原値を補修せず、既type/未知型拒否と寿命を不変とする。新2クラスの実fqnameは最終packetへ固定し、任意subclass/duck type/自由成功boolを通さない。実提供にはroot正式登録・実ownedPG・最終非作者確認が必要であり、本source許可だけで成立扱いしない。

HTTP/Port core追加の採用（2026-10-31、PO委任によるCodex主担当判断）: 非作者追補REPORT5796e39b1ff6b70a99c1c60f9c454e78bcfc8cb69ad0ddf2dac06d4c1fdabe04と実core08108152…を照合。exact2path×3areaの6追加だけ、旧57/全field/順序不変、新指摘0で採用し1063ee45の2path編集も解禁する。

PlayRunner物理row IDの安定化（同日、Codex主担当判断）: 新modeだけplay予約UUIDをnamespaceとし、正準base1..3の固定名からUUIDv5を私有frame内で生成・固定してよい。実際のname接頭辞/式はsource/pure対向へ固定する。runner本人/責任投手は真正実player/source由来のまま、物理IDを本人資格やsecretに使わない。tenant内PK/FK/全10列期待・私有印・同TXを維持し、同D5で再発番/付替えしない。旧v1のID発番は不変、他tenant同UUIDをglobal拒否へ拡大せず、衝突/不正参照は既閉拒否・全取消条件を保持する。

旧初球原本の限定互換reader（2026-10-31、PO委任によるCodex主担当判断）: backend/src/pitchlog/repositories/recorded_snapshot.py exact1を追加許可。v2内部callerだけが有限compat witnessを要求するopt-inを使い、旧呼出しは不変。実event payloadのprior hash/source formatと実loaded execution hashの組をroot JSONへ照合し、単一current実数学の全request/response/全41列と元sourceを比較してからhash metadataだけ実旧値へ対応する。旧期待lookup/出力差替/自由digestの資格化/全hash許可は不可。sourceFormatは実旧形式に閉じ、first-ballはderiveState/deriveFirstPitchWithContinuation、ordinaryは既4口の証拠を要求する。存在しない旧公開口の互換性を一律宣言しない。

GET再構築用readonly2field（同日、Codex主担当判断）: 新StartedPlayPrefixGameReadへprior_artifact_sha256とpa_start_sourceを実保存doc/初球payload/真正start原本から供給する。空sourceのpriorは実loaded hash、PA開始は真正game-start/gameIDまたは実保存play source。callerが推測せず再構築できるmetadataであり、権利/資格を発行せず旧DTOを変更しない。既許可schema/router path内で具体化する。

既Port閉集合回帰の不可分追随（2026-10-31、PO委任によるCodex主担当判断）: backend/tests/test_sync_apply_first_ball_ports.py exact1のtest_port_real_guard_and_original_event_commandにあるPORT_IMPLEMENTATIONS期待を旧5保持＋採用済pitchlog.sync.ordinary_pitch_ports.PlayPrefixContentValidationPort/PlayPrefixProjectionPortの2だけ追加したexact7へ追随可とする。既比較/未登録拒否/原イベントcommandの全assertは不変、未知型やsubclassを追加許可しない。この実登録2名は最終source/型閉集合の独立確認対象。

旧原本互換readerのcore採用（2026-10-31、PO委任によるCodex主担当判断）: 非作者追補4f4809970210d1d62692a1dc0cb6e0f2c81da0aa2639d09eeedd26ecc96a0154/実corefc9be827…を照合。recorded_snapshot.py exact1×4area追加のみ、旧全field/path同順保持・新指摘0として採用、59659b6cのreader編集も解禁する。旧caller不変・有限hash/実sourceFormat別・数学全値比較の条件は保持する。

新GETの元要求識別の復元（2026-10-31、PO委任によるCodex主担当判断）: 新StartedPlayPrefixGameReadだけへlast_source: PlayIdentity|nullを追加可。実checkpoint.last_sourceのeventId/D5と実last PlayRow.idを同tenant/game/D4の原本へ結合して供給し、0球はnull。D5は識別子であり資格/nonce/secretではなく、返却によって記録権を発行しない。既GET2pathのreadonly値に限定し、旧DTO/応答と越境拒否を保持する。ブラウザに欠落値の推測をさせず、未知D5の新発番や他tenant照会を増やさない。

既API応答型の閉集合追随（2026-10-31、PO委任によるCodex主担当判断）: backend/tests/test_api_started_game.py exact1の既tenant-matched GET応答union期待を旧3全保持＋採用済StartedPlayPrefixGameRead1だけのexact4へ追随可。route/tenantmatched/未知型拒否/他全assertは不変、新variantを実OpenAPIから隠して回避しない。

有限legacy compat候補供給（2026-10-31、PO委任によるCodex主担当判断）: rootが予定のplay_prefix_v2_source_compatibility_v1.jsonへsourceFormat別7組を候補作成。実Git 54b83002/e81c4edb/5226a667/9736e06dのJS byte/SHAと公開口を確認、firstは2口/ordinaryは4口。旧/現artifactを別VMで実行しfirst24・ordinary1840（一般888含む）全応答を型/全field比較して全組差0。witnessはcache terminal-prefix-compat-readiness-20261031の各JSON/compare.cjs/indexに全入力hash/出力hash/accepted拒否件数を固定しJSONのwitnessSha256で参照。旧期待をruntime lookupしない。root候補は非作者確認前で正式受理ではなく、実source/登録/完全request-response照合が無ければ資格として使わない。任意hash/未存在APIを一律互換にしない。

有限compat登録の採用（2026-10-31、PO委任によるCodex主担当判断）: 実JSON621137eb696944dd548816840aea74f5287c1fbb5f50de2a5f65a07704184fe3と非作者REPORT4d54c61b4e336b66f7a3d2474cb8b31186d827b7fa4be63d1900279aa783ab4fを照合、新指摘0で限定7組を採用。実Git4artifact/入力/旧出力/現出力/witnessの全hashと全5616比較（正常5499/拒否117）を独立再現、差0。実行時の期待lookup/任意hash許可ではなく、真正DB source/現一回数学との全値比較が別途必要。DB互換・全ABI任意入力・P6blind・D11/BOOT/7.7/Port提供の完了は未成立。root供給JSONだけ保存し作者のsource4とは別履歴にする。

### PlayRunner物理意味の是正（2026-10-31、PO委任によるCodex主担当判断）

原典data-model5-2/旧20-25・36-38の起点塁走者triplet、FR003/ADVの走者別実結果と非作者REPORT95ebdbfd88c614bc732f0bf6edbb59f0e1ed29d014f1cafff722228b63075392を照合し、先行案のafter snapshotを既PlayRunnerへ流す混同を是正する。新意味裁定ではなく保存仕様への整合で、source3数学/P6期待は変更しない。

physical PlayRunnerはrequest.source.runners(beforeの起点塁実本人/責任投手)に対する今回の実T1既定/観測結果であり、private doc.runners/GET runnersはresponse.runners(after占有)である。無走者BB/HBPは当該physical0行、新打者出塁はPlayRow＋after checkpointへ、次ordinaryでbefore一塁走者のphysical継続1行。snapshot物理期待/AFTER stampはbefore実結果集合、checkpointのafterは別集合として同時に束縛・個別照合する。未来の本進/アウト走者をafterから消して記録喪失させる共用はしない。

作者は既許可projection/SQL prepare/GET/新pure・owned期待の該当箇所だけを是正し、旧candidate69b2fa30…を履歴として保持して新版source/producer packetへ固定する。追加path/表/role/権限は不要、rootは旧producerを未適用のまま維持する。新AFTER全取消/元D5/tenant・FK/全10列/metadata seal/非循環digestと一回評価の条件は不変。

### ステップ4のD11登録における期待値包絡（2026-10-31、PO委任によるCodex /root判断）

既許可root3宣言play-prefix-manifest/property-catalog/schemaへ登録するvectorは、既play_prefix_v2_cases.jsonの56全期待をそのまま消費する。既契約/旧18固定hashを変更せず、root専有のcontracts/state-transition/play_prefix_v2_d11_vectors.json exact1を追加し、各期待をmanifest.schemaのExpectedValue（expected/comparison/provenance）へ包む。比較方式はexact、規範期待そのものは全値一致、元ケースID/request/expected hashとauthorityを追跡する。製品計算やruntimeのlookupには使わない。

登録3宣言とvector1は非作者照合を経て正式pathへ反映する。実在のtyped caller/public operation/source/direct target/現loaded052fを指し、既全56host照合とsource-binding拒否検査をpropertyの実検査箇所へ対応付ける。mutation宣言は実施義務の登録であり未実施を成功扱いしない。structured propertyの新測定/全BOOT/全D11/正式7.7は残件のまま、登録だけで完了としない。旧terminal manifestの別未完も黙って閉じない。

D11 runnerの有限追随（同PO委任によるroot判断）: backend/tests/domainrt/test_play_prefix_continuation.py exact1をroot writerへ追加。既test_all_56_through_product_host_and_typed_callerの56全値・実direct host/型付きcaller比較を維持し、上記期待包絡を同じ56の独立期待と完全比較して実消費する。record_propertyへ実count56/最終case/期待・実二経路出力・loaded artifact hashを記録する。宣言runnerはpytestに限定し、Vitestが新包絡を読んだとは記録しない。新propertyはこの実測equivalence1のみとし、未実測source-binding等をcatalogへ採用しない。旧全拒否・元契約hash・数学sourceは不変。構造schema/実消費/影響全件と非作者確認後に登録採用、mutation/全BOOT未完は維持する。

ステップ4 SQL r3候補の正式path反映（2026-10-31、PO委任によるCodex /root判断）: packet a9d584c405bd3ae0541048e6a1c6263cf85aa6257c4a95bd39ff742f668d7a05/root22files d9f2d7280b195e6fb2c4de552b8d4cff44a928509e62ea22e0781658650ddd1fを非作者REPORT4fbc480a0d210215f9a5431591c2090c6defceb365a8480be285d7021720dab1と全byte照合し採用。20SQL（既BEFORE1改訂/新19）とDDL宣言/manifest2JSONを反映する。旧r2は正規installerがCREATE改行3で停止するP1を検出し不採用保全、r3は生成側3のみ空白へ是正、既parser不変・公式8function描画成功。before physicalとafter占有の分離/所有nonce/xid/xmin/ACL列10/4app3private/2policy2triggerを独立確認。root正規path反映は実PG/実画面/正式7.7/BOOT/CI/通常merge成功を意味しない。実source/metadata残件とowned PGの実証を次に行う。本人署名0。

D11限定5path採用（2026-10-31、PO委任によるCodex /root判断）: files5e2e863426b0758d703bfee06773f3d95f053964539aae304b0990d3c89c9e33/非作者REPORTcc8847c2118613bf14b8870e2acce0b7de0a8373d96e7a9b937e481fab933130に基づき登録3・期待包絡1・既pytest1を実反映。schema/旧56全request期待不変と実host/型付きcallerの独立56全値照合成功、runnerをpytestのみへ限定。rootはこれから公式pytest/JUnitを実行する。cache実行を公式pytestと混同せず、未実施mutation/BOOT/実PG/正式7.7は残す。

D11限定登録の公式消費結果: 上記同5pathでtests/domainrt/test_play_prefix_continuation.pyは24passed/3.41秒。official-junit.xmlの実propertyId/playPrefixHostParity/generatedCases56、traceのexpected=entrypointOutput=directTargetOutputと実052fを確認。xunit2のrecord_property warning1は保持し、XMLに実propertyが存在することを別検査。全mutation/BOOT未完・実PG未了は不変、全T1成立へ拡張しない。

ステップ4登録の生成module追随（2026-10-31、PO委任によるCodex /root判断）: 既許可runtime/repository JSON2と不可分なbackend/src/pitchlog/authz/runtime_contract.py、backend/src/pitchlog/repositories/repository_contract.py exact2をroot生成writerへ追加。runtimeは正規derive_runtime_contract_fields/render_runtime_contractを使用し既基線090b99e7から新7関数のみを導出、役割属性/既schema・表/旧関数保持、revisionとidentity/source_digestのみ正規追随。repositoryは既cap36/既token集合/既16function順を維持し、実登録の新PlayPrefixPlayRowInsertToken1と新4function IDのみ追加して全値生成、revision/source_digest/identityを一致させる。backend/tests/test_authz_repository_contract.py exact1の既function閉集合期待も実新4署名へ有限追随し、旧16全比較/拒否を維持する。未知型/任意function許可に広げない。全5pathはcacheで完全前後固定・非作者確認後反映し、正式7.7履歴/全CIは別に閉じる。

正規runtime再導出による既存未反映の発見（2026-10-31、PO委任によるCodex /root判断）: 上記「新7関数のみ/既表不変」は新DDLの範囲を述べたが、実正規deriveでは既旧runtimeの未追随も検出した。実DDLからの全差分はschema11不変・role属性全不変・旧table53全保持＋既ordinary private3（checkpoints/history/write_admissions）・旧function91全保持＋既ordinary8＋新play-prefix7で106となる。新table/ALTERを追加するものではなく、既保存経路の保護対象の登録欠落を正式に是正する。root初稿は「表不変/関数+7」のassertでcache段階停止し正式write0、誤った基線へ合わせず全完全差分を固定する。既ordinary8とprivate3も原本/採用source/DDL宣言の閉集合として非作者へ渡し、正規derive/renderの106関数/56表を採用対象とする。既全object/role属性・順序相対は保持し、任意object許可/検査の除外をしない。revisionは実基線から一回の移動として導出し7.7の前後実値へ反映する。

長署名の生成字句是正（2026-10-31、PO委任によるCodex /root判断）: 正規runtime generatorは個々の引数署名が長い場合90/98文字のliteral行を生成してE501となることをcacheで検出。検査の除外/生成後手編集をせず、backend/src/pitchlog/authz/runtime_contract_state.pyの_render_rowのみ、長literalを値不変の隣接Python文字列として折り返す。backend/tests/test_authz_runtime_contract_generator.py既全値・88文字試験へ実長署名2/escape対向を追加するexact2をroot作者へ許可。旧短literal/全object/順序の出力不変、ast.literal_eval全値/88桁/正規再生成の冪等性を検査する。source2と生成5を非作者へ渡し反映後の正規check・影響検査を実施する。DB型/認可意味/行長検査設定は変更しない。

正式登録7path反映2採用（2026-10-31、PO委任によるCodex /root判断）: files75ce0d3592753345ecc91099e16e97b0543b6b0eb1f9c59db9d4ae60e980d2a5/非作者REPORTf13b4ec52e2ab1f0194dbe1d66fc3a231f386fd6e52898b4413014b188378abbを全byte照合。runtime28→29（53→56表/91→106関数）、repo35→36（cap36保持/token65→66/function16→20）を正規導出。旧ordinary3/8は既採用f7caa524 DDLから独立確認、新7との識別を保持。formatterの162実row＋seed固定150組のescape/Unicode literal全値/88桁、旧constant不変を独立確認。初回testのtoken-capability zip相手1欠落P1をstrict維持で並行追加し閉鎖、証拠filesSHA旧値P2も是正・旧packet保全。root公式全module/正規checkをこれから実行し、7.7/CI/実PG成功とは分ける。本人署名0。

登録後の公式検査: repository contract/runtime generatorの全2moduleは155passed/3.98秒、正規runtime generator checkは成功。tyは初回環境未指定でsystem Python3.14に解決し依存975診断となったため製品型失敗と混同せず、既完備backend環境を--pythonで明示して全backend成功。source/生成の検査除外なし。7path全hashを反映2へ再照合して保存する。実PGはfixture closure確認後にrootが実行、全7.7/CIは未了のまま。

ステップ4 source40/r4の採用保存（2026-10-31、PO委任によるCodex /root判断）: author files e096e2f2abe0ff3f331b88abc890c9bac1e7394696578a15de3ba3561f5b4516/SQL packet2e46b2e9a5172c875c4c5ba08dc53df38f9953f02a7256510c1a8d1882bc71eaと非作者REPORTc08a9b2fe351942b6155b20be0fd9fd82f4feb54d8bec78286c958157f379b3bを全40byte照合。独立222pure＋r4最終10成功、新指摘0、真正source/実Port/one-use frame/実artifact一回/元D5/責任/GET有界/旧v1・有限互換を確認。初回owned PGの42601はprepare IF内CASE5式に括弧がなかったため。r4は括弧5だけ逆変換して旧raw全byte一致・残38source不変・正規8installer成功。root正式SQLはprepare1fileのみ116dd368…→476eecda…へ再導出反映、他19SQL/DDL/catalog/runtime/repo値は不変。実失敗2setup errors16.76秒/record実行0と初回r4testのraw/wrapper SHA層誤認1failは保全・是正し、これから新固定HEADで実PG再試験する。7.7/CI/D11全条件/実保存・画面成功へ繰り上げない。本人署名0。

ステップ4の実owned PG正常/再送/原子性の到達（2026-10-31、PO委任によるCodex /root判断）: 実行固定989ed1ac、source40/全tracked byteは前後不変・clean、artifact052f…、2passed/186.90秒。実ASGI製品入口/実認証/新規POST作成・開始/記録権/実broker/単一artifact/実Port/owned PGで3ball→BBまたはHBP→次打者ballを各系列として確認。各prefix5/history5、打順2/after一塁、原本打者runner/責任投手、physical PlayRunnerは終端0→次球1、operation_events/play_rows各5を実DB照合。同D5/同bodyの実重複ACKで二重保存なし。after_t2_event/after_t4_projection故障でGET完全不変、元D5/同予約IDの再試行が正常成立。証拠cache terminal-pitches-owned-storage-20261031/attempt2/result.json SHA3763b63a81f13d627b95c678c620a66e2077a45d19a185acab24e76f5df5c07d。初回r3の42601/2setup-errorは別保持。これは新BB/HBPのTCP/実画面や全越境/全故障/7.7/CIの完了ではない。新v2の実越境負例と正式統合をrootが残件として保持し、次に隔離画面候補へ接続する。本人署名0。

新v2の実tenant負例（2026-10-31、PO委任によるCodex /root判断）: rootが既許可test_terminal_pitch_storage.py1pathへ、別tenantの実ログイン/真正expected tenantで元試合のv2 GETと元D5再送を404拒否し元ownerのGET完全不変である負例を追加する。両tenant資格は既ownedfixtureの準備のみ、auth/C2/記録権/実保存をstub化せず、元5行/履歴/runner数も全維持する。ユーザー情報の返却や元重複ACKを別tenantへ漏らさないことを確認し、独立差分確認後に新固定点で実owned PGを再検証する。新製品source/共有DB変更なし。

ステップ5隔離接続の開始範囲（2026-10-31、PO委任によるCodex /root判断）: 実固定989ed1acのBB/HBP→次球/元D5/故障rollbackが成立したため、最優先の実画面接続を先行する。step4の実越境追加と正式7.7はrootが並行で閉じ、step4全完了/通常merge条件の免除としない。既UI/queue表に不可分なfrontend/src/screens/GameScreenRecordedRestore.ts/.vueおよびfrontend/src/lib/generated/wrappers/domainArtifact.ts exact3を追加し、既許可UI/queue source/test範囲を作者へ割当てる。実v2 GET variantへ接続し、既配布artifactのderivePlayPrefixWithContinuationを閉unionへ登録するだけでUI独自T1/T2を作らない。generated配下wrapperの既生成元がある場合は正規生成へ追随、未特定のまま生成完了と記録しない。

新terminalPitchWire.ts/.spec.tsは既tenant wildcardに加えsync/game-state/recording-rights/data-migrationへexact2×4=8pairをrootが先行登録し非作者確認後に編集開始。旧全path/拒否条件は保持。次打者は実roster候補の確認入力で提案し、唯一artifactのafter/打順と実source資格が正式結果を決める。画面に内部資格/metadataを入力させず、既WebLock/元ID耐久slot/実ACK/GET/reload/unknown保持/旧V1slot元body再送を維持。未知操作の成功表示は禁止。新baseline/実機/全MVP未完を維持する。

新v2実越境test候補の採用（2026-10-31、PO委任によるCodex /root判断）: source e4409b11…/非作者REPORT87f75112e1c48d9e6dd9140ed217b6f0f3fceb96d1ea6cfa96808bfd776299efを照合、新指摘0。実foreign認証/真ExpectedTenant、POSTはB6/game_accessibleがD5再掲/ownerdevice/RG1より先となる404拒否順を原本/実routerから確認。元全assertは逆差分で全byte保持、対象再送は各case最後の次ordinary-v2要求でありterminal自身のforeign再送へ拡張しない。実PGはこれから新固定HEADで実行、旧2passed186.90秒を新負例成功へ読み替えない。

ステップ4実越境の到達と5開始（2026-10-31、PO委任によるCodex /root判断）: 固定6003fc1e/source40全hash不変/cleanで同owned PG両系列2passed195.70秒。実foreignログイン・真ExpectedTenantによるv2 GET404、各case最後ordinary-v2の元D5再送404/ACK非漏洩、元owner GET全値不変と旧正常/再送/故障rollback/DB5行・history5/physical1を確認。証拠attempt3-tenant/result.jsonを固定、terminal自身のforeign再送/全故障へ拡張しない。実画面はまだ未実施。

step5 core8pairはcandidatebce0bf4c9ebb6a75a7d005f58defaa4a8c6bc0800e08ea856e17d85dfdafa383/非作者REPORT90b2a5312e756584cd26b5c0c11ae33a6f37e64b7ddf66e5e28604601c3e23acを照合して先行反映。旧全field/path順/拒否は逆変換でbyte一致、正規loader/matcherで対象2＋追加3を捕捉。接続packet6d321172740929023f92a2968f98877cfed78e56d0aa0b52a2c51a35775aaaed/path-manifest06586686…を採用し、不可分3sourceの既spec2（GameScreenRecordedRestore.spec.ts/domainArtifact.spec.ts）も明示追加する。wrapperは手書きの閉操作union履歴/正規builderの出力2を確認し、生成完了と偽らずsourceとして1operation追加のみ許可。rootは作者へ同有限frontend範囲でstep5実装を指示する。v1/v2を利用者に選ばせず通常記録画面へ接続し、旧slot/旧ABIを保持、既started-initialによる開始直後HBPも実証対象。正式7.7/必須CI/通常merge/全MVP受入は未完のまま。
