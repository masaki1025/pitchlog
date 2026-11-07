---
feature: mvp-runner-operations-connection
status: active
branch: feature/mvp-runner-operations-connection
承認: PO委任Codex/root、2026-11-07、対象294e2b563a51b9870b763f0eff962710f23acca2、計画SHA 43ccc10010ceac0c4688f605974ea32c26f09e2d4112510efe5cc33a0797fc0c
重さ分類: コア領域
計画レビュー周回: 1
確定ゲート周回: 0
---

# 明示した走者結果を同じ計算・保存・画面へ接続する

起点91773ec03333f73a076e36f1a4aaae87e3415b91（rootの70c/P3/CSV同S修復＋f9 T5供給）。旧runner成果e90125bd/79fe実測は別WTに保全し、必要な画面driver/DB照合だけ再利用する。旧spike8e1bf431のSTATE_RULESは素材であり正式実装済みとは扱わない。AGENTS.md/CLAUDE.mdを現物確認済み。

現kernelはSO-05の固定一死一塁を計算できるが、物理runner保存がout targetを全拒否し、v3の走者ID伝播もout target除去を持たない。走者イベント・一般併殺・失策/妨害は現在の公開kernelでは未提供。今回、共通の明示runner結果→唯一核→v3 ID伝播→同TX物理保存/T5→画面を先に完成させ、失策/妨害の公式記録/ruling核はこの共通路の後へ接ぐ。MVPから除外しない。

## 操作単位と保証

- 対象は盗塁成功/盗塁死・牽制死、暴投/捕逸/ボークの進塁、SO-05の打者＋走者out。既FR-004/E-1/E-2/SO-05/OUT3/RBIを根拠とする。結果IDは既採用語彙を再利用し、strategy-category等を新意味へ読み替えない。
- 記録者が対象走者ごとにセーフ進塁/アウト/停止、到達または企図塁、out原因を明示する。live sourceの起点塁/runner ID/責任投手へ束縛し、対象不足/不在/重複/衝突・不足原因を拒否する。進塁・force・責任・打点をPython/配信層で再計算しない。
- 既`deriveLineupPlayPrefixWithContinuation`/単一`applyCountRule`を拡張し、別計算核/別artifactを製品へ追加しない。投球数/PA非該当/第3out共通リセットは既規定どおりに扱い、SO-05を通常三振へ落とさない。outとなるIDをv3次走者から除き、残るIDと責任を継承する。
- V7は既play-prefix-play-v3の中に余剰禁止の走者観測/複合out観測unionを追加する候補。既通常球/安打形を一般緩和しない。D5/DI2FP/再送順/認可/記録権/結果不明復旧の規約は変更しない。rootの同じ実保存経路と同TXを使う。
- 第3out有効得点やRBI因果に必要な観測が欠ければ未供給/拒否のまま。OUT3の時機や取消範囲を仮定せず、既原典で確定しない意味だけ具体例付きpacketへ出す。未知/未実装を成功にしない。

## 専有パスと共有所有

本担当のsource専有候補（root採用後に編集）:
- `frontend/src/domain/{runnerEvent.ts,runnerEvent.spec.ts,state.ts,stateRules.ts,stateTypes.ts,runnerOccupancy.ts,battedHit.ts,publicApi.ts,lineupPlayPrefixContinuation.ts}` と各専用spec。battedHit/occupancyは衝突検査等の既共通primitiveを抽出再利用する必要がある場合だけ。
- `frontend/src/api/{runnerEventWire.ts,runnerEventWire.spec.ts,lineupPrefixWire.ts}`、`frontend/src/screens/GameScreen{OrdinaryPitch.vue,OrdinaryPitchProvider.ts,RunnerEventObservation.vue,RunnerOperations.e2e.ts,RunnerOperations.playwright.config.ts}` と各専用spec。既runner画面driverの再利用はtestだけ。
- `backend/src/pitchlog/domainrt/{lineup_play_prefix_continuation.py,lineup_prefix_source.py}`、`backend/src/pitchlog/sync/{terminal_pitch_payload.py,terminal_pitch_projection.py,ordinary_pitch_physical.py}`、`backend/src/pitchlog/stats/facts.py` と各専用test、`backend/tests/db/test_runner_operations_screen_e2e.py`。
- 本plan、同feature内の閉input/case候補と受渡しpacket/記録。

root専有（本担当は直接編集しない）: `contracts/`・正本・共有registry/根幹SQL/認可/tenant/seal/7.7・startup/migration・shared ledger、`frontend/public/domain/pitchlog-domain.{js,json}`と既pin/manifest/vector。TS sourceは本担当、唯一製品artifactとpin/正式資産の正式追随はroot一人へ直列化する。公式buildDomain({outputDirectory:cache})で同じsourceから作者検証用の一時artifactを作れるが、正式提供と混同しない。必要な正式typed union/case/SQL/派生値はcache packetへ固定してrootへ渡す。

## ステップ

| # | 実行 | 終了条件 |
|---|---|---|
| 1 | 既原典/型/case照合を操作単位で閉じ、明示runner入力と唯一kernel/v3 ID伝播を実装 | 前後状態・23flag・out targets・count/PA・残るID/責任の正負pureと公式cache artifact経由を照合。既規範caseを緩めず、不足の閉型/caseはrootへ固定packet。全操作契約や実Portの完成を新前提にしない |
| 2 | 厳密V7/物理runner原因/T5(SB/有効得点/責任)/画面を同経路へ接続 | 同原値を既codec/独立artifact再生へ渡し、進塁/force/責任/打点の二重実装なし。rootが受理したartifact/pin/必要な正式差分を直列採用。認可/記録権/保存保証は迂回しない |
| 3 | 一つの隔離実画面シーケンスで保存/reload/再送/越境/途中故障を検証 | 画面新規作成/開始/安打で走者を作り、盗塁/死/牽制・WP/PB/balk・SO05を記録。サーバーafter/ID/責任・T5/SB実値・物理row/ledgerを照合し、同本文再送非二重加算・第3out/reload・越境拒否・全保存面原子性を実証。DB事前走者投入/仮Port/固定ACKなし |

候補sourceの限定非作者確認はrootへ渡す。作者試験と独立/盲検を区別し、P-6曝露資格を自称しない。共通owned lockをfixture作成からcleanupまで保持し、共有DSNをunset、実行source凍結、DB/一時file/portを分離する。実機/運用信頼TLS・正式develop統合・全MVP受入は別。root委任採用後は上記3ステップを順に継続し、外部回答/CI待ちには独立作業を進める。

採用根拠: rootは上記固定計画全文を非作者レビューしP0/P1なし、source列挙pathを本担当一人へ割当、3ステップ継続を承認した。`/home/ymdms/.cache/pitchlog/mvp-runner-operations-root-intake-20261107/PLAN-ADOPTION.md` SHA a5ac58e841ccaec744f1d5dd9d72f6435854d3fe426199e9da4a2892806a6bb5。本人逐行確認/署名の代記ではない。


## ステップ1の候補成果（2026-11-07）

- `runnerEvent`が正式T1PerPitchPayloadV2の11欄/PlayerRef/起点走者結果を原値のまま閉検査し、内部Ruleを既唯一`applyCountRule`へ渡す。通常球のcount選択を`ordinaryCountRule`へ抽出して再利用し、得点/RBIは同じ算入ループの判定から有効到達根拠を出す。Pythonの野球計算は追加していない。
- 新v3候補入力だけに`runnerObservation={perPitch,primaryResultId}`を追加する。`primaryResultId`は実投球を伴う副結果の主結果であり、runner-event自身のcountを変えない（XC-05）。投球＋盗塁はbatting-resultのrunnerEventPayload、非投球盗塁/牽制はrunner-event。live ID/責任はsourceからだけ供給する。旧入力/旧出力ABIへ任意欄を足さない。
- 既v3のout対象IDを次走者から除き、走者のみの第3outでも次PA責任参照を更新する。OUT3-03/04/05で有効とされた本塁到達のみ同じ核で算入し、その判定を`runnerScoreEffects`へ写す。未観測時機/未解決temporary/force原因/未知因果は閉拒否。
- 作者検査: eslint・vue-tsc成功、domain全件35file/938passed/52.71秒。追加v3の正常7/拒否7は公式builderの一時artifactと全値一致、正常7は現正式JSONSchemaのT1PerPitchPayloadV2へ適合。独立レビュー/正式受理/追跡artifact更新/実PG/実画面の成功ではない。
- 正式供給待ち: v3T1への閉観測variantと出力runnerScoreEffects、同unionの型/schema/case、唯一artifact/pin。rootへcache packetを渡す。root以外による正式資産の編集なし。
- 今回の現成功範囲: 非終端通常球＋盗塁、非投球盗塁/牽制、通常球＋WP/PB、明示全員1塁のbalk、既固定SO-05（一死一塁/S2B0）。終端球との複合、SO-05他配置、複数得点サヨナラの順序反映、エラー/妨害等は未完として保持する。観測や自動既定の拡張は行わない。
- 次: ステップ2の閉V7/型/物理runner原因/T5/画面接合、root直列の正式型・artifact供給後にステップ3実測。stage1だけをMVP完成に読み替えない。


## ステップ2の中間固定（画面接続・実PGは未完）

- Pythonは旧T1/Valueを一般緩和せずRunnerT1/RunnerValue（NP継続も独立variant）を追加。perPitchの全原値・V7観測と数学要求を全比較し、新wire-headだけにrunnerObservation/runnerScoreEffectsを束縛する。物理41列は主結果/副結果を各既列へ写し、非投球の球種/コース等は実際に非該当のNULL。out原因を既投手牽制死/捕手牽制死/盗塁死/走塁死語彙へ写し、責任IDはsourceのまま。API runner表示型は既にこれらを受理済みで、追加変更は不要だった（最初の不足推測は現物照合で解消、編集なし）。
- T5は同codecを通った原V7と唯一artifactのrunnerScoreEffectsから生還者/責任/有効得点/RBI判定をコピーし、stealの明示実結果を既生成T5のattempted/successfulへ渡す。新しい得点/RBI/盗塁の算式を作らない。新variantの欠測根拠を旧ordinaryゼロへ落とす経路は拒否する。生成model/生成物は非編集。
- 独立確認で01a6の通常foul＋走者進塁成功を再現したため、普通foul＋進塁/out/WP/PBを閉拒否する修復と4artifact対向を追加した。普通foul/ファウルチップ等を読み替えない。複数塁取得の盗塁数量は候補で未供給のため未対応拒否へ置き、正式合法入力を次塁だけへ変更したとは扱わない。既採用計数の追加照合/接合はMVP残件。
- 中間作者検査: backend専用34passed/2.27秒、先行関連129passed/3.72秒、Ruff/Ty成功。FE domain全35file/943passed/44.44秒（foul修復4/未対応拒否1追加）、明示runner観測panel5passed/0.687秒、eslint/vue-tsc成功。panelの原観測・原因必須・source ID変更時の再確認だけの検証で、まだ既記録画面へmount/送信未接続。
- 広げた実host回帰373件は331passed/42failed/15.19秒。2系統を診断すると数学前のpin不一致（fixture execution9ae9…、追跡artifact4e7d…）で停止した。両関連fileは91773ec0から全byte不変をGit比較した。残る失敗の全個別原因は未分類で、同じ42再実行をしない。正式pinのroot追随後に接合を検査する。全緑/実host成立へ読み替えない。
- rootへ`formal-union-packet/manifest.json` SHA56c9643a68b1268fd4bf395f04c4b8f6677c9556174ee07dd69f75d160bd0e4dを送付。既正式perPitch定義再利用のschema/d.ts候補、新V7/Head7件、新旧正負、candidate rendererをcacheに固定。正式asset/追跡artifactは非編集。汎用checkerのuuid/uniqueItems厳格対応はcache patchのみで、sourceはroot直列対象。NP-source実ケース/FE型全件は未確認。
- ステップ2は継続中: root受理した正式union/唯一artifactを同SDKへ接合し、既provider/耐久queue/ACK/GETへ観測panelをmountする。ステップ3の実画面/DB/再送/越境/故障は未実施である。


## ステップ2の担当path最小追補（2026-11-07）

rootがPO委任で`frontend/src/screens/GameScreenOrdinaryPitchController.ts`の限定変更を本担当へ追加した。同pathの他writerはなし。変更は引数の閉union（非投球は`{kind:non-pitch-event,runnerEvent:原観測}`）と、非v3 contextで新variantをblockedへ返すguardだけ。既D5/attempt/V12原文耐久・writer/認証/記録権・ACK・再送・キュー順は変更しない。非投球に仮座標/仮球種を補わず、通常投球の必須観測を緩めない。scope/実差分は次固定HEADへ保持する。


rootの追加所有（同2026-11-07）: `frontend/src/lib/ordinaryPreparedEnvelopePersistence.ts`の型importとobservation型の2行だけをRecordingScreenObservationへ追随する。runtime検査/DB store/本文/V12/D5/attempt・digest・再送条件は変更しない。起動直後に球種取得が済む前の通信断では、NPにも空vocabularyを既保存器が拒否し得るため未解消として保持する。最小解除案は『新NP閉観測とV7の同原値一致・投球非該当・既本文/slot束縛が成立した場合だけ空球種配列を許す』別対向であり、一般空配列許可/旧本文修復/仮球種の補完はしない。今回このruntime変更は未実施。


追加所有（同2026-11-07、root PO委任）: `backend/src/pitchlog/sync/play_export_identity.py`のNP course identity分岐と専用tests。本担当が唯一writer、rootは非編集。既意図的四球/通常投球の拒否・唯一座標生成は維持し、新NPの閉V7・元runnerObservationの全値一致・実row.non_pitch/全投球列NULLを確認して非該当None,Noneを写す。仮座標・現在名簿補完・新計算は追加しない。


rootのPO委任による表示追随（同2026-11-07）: `backend/src/pitchlog/exports/record_projection.py`と専用testsも追加所有。既XC-05/XC-07のrunner-event/plateAppearanceEnded:not-applicableを打席結果非該当として列17/61/62の明示NULLへ写す（CSV空欄、元T1はsidecar保持）。bool false/打席継続/新PAを推測しない。列18/19は既saved_half_completed/T2とgameEnded実boolを維持し、旧bool表示は不変。新Runner NPの閉V7/元観測/実rowが整合するときだけNAを扱い、その他のNA/未知は拒否。生成plate_result_display/モデルは変更しない。UD2正本追随の根拠記録はrootが担当する。


## ステップ2 SDK/画面・CSVの接合固定（2026-11-07）

- root固定de3bfb27240c3ed2f126abd76b0af9c355d91c21から4 schema/d.ts＋汎用checker＋専用specを全byte同一で受領（patch SHA84ff27122e8c8564b6889d6281516eb985f44f20e3ad92097c3f8eff4d1fada1）。checker/specはroot後発f29097b4へ全byte追随（patch SHA23d4b4b5063274ba2186947e07019d6b25df1e5647d2958eaaf5e35dd0b44766）。この受領は候補接合で、正式受理/実保存済みの宣言ではない。規範依存定義は22、既旧正例53件を維持する。
- SDKは正式候補型へのaliasを使い、旧型cast/原値書換をしない。共通lineupWireHeadへ新2欄を束縛し、fresh一回計算後の自己echo二欄だけを共通sealerで形成する。formatter/再読込時は既固定echoを検証し、不正echoを再封印で補修しない。同原観測/参加者/現行artifact pinを照合する。rootの型先行一時拒否は実封印SDKへ置換し、元要求/差分/同D5の再構成を比較した。
- 観測panelを既記録画面へmountした。原観測を確認してから既controller→元本文/同D5/attempt耐久→同期要求/ACK/GETへ渡す。非投球は専用閉観測だけを渡し、球種・座標を仮補完しない。controller変更は閉union/非v3拒否/計算formatVersionの正確な型絞り込みのみ。保存器は型alias2行だけ。sourceKeyが変わると同じrunner IDでも旧確認をresetする。
- CSV NP course identityは新閉V7/原観測/実41列NP一致を確認して非該当None,Noneへ写す。runner-eventのPA:not-applicableは列17/61/62に明示NULL（CSV空欄）を渡し、元T1はsidecarへ保持。列18/19・旧bool表示・生成表示/座標関数は不変更。単体で旧fixtureへの参照共有が原因となる検査順依存を確認し、作者helperのdeepcopy不足を是正した（製品の期待値/codecを緩めていない）。
- 現固定前検査: frontend全eslint/vue-tsc成功、8対象file/102passed/10.46秒。backend全Ruff/Ty成功、関連pure330passed/11.52秒（共有DSN unset、DBなし）。domain既固定35/943passed44.44秒を保持する。新SDK検査は作者の構造候補を現在pinの封筒へ載せる純検査であり、実host/実認可の成功ではない。
- **未成立**: 唯一追跡artifact/現行pin・D11/manifestのroot接合、実PG/実画面/途中故障。既pin停止を根拠なく再走しない。rootは同受領sourceへ公式builder/現行pin/manifestを直列追随してから正規CURRENT48環境へ接合する方針。NPの球種未取得直後の断中受理は既保存器条件の未解消事項として保持する。終端球との複合・複数塁盗塁数量・SO05他配置・複数得点サヨナラ・エラー/妨害等もMVP残件であり、今回の実装範囲を正式な機能削減へ読み替えない。


## 非作者P1の後発是正（aa8レビュー、2026-11-07）

非作者レポート`/home/ymdms/.cache/pitchlog/runner-operations-independent-20261107/REPORT.md` SHA 91c1fa3a6c9818ba9af32e01bfe04af168850dd60e35b0ea5e32837f4adedd82の『親主結果ballと子SO05の相反観測』を是正した。子のSO05操作選択時点で親主結果も同じSO05へ変更し、親が後からball等へ変われば子SO05選択/確認を解除する。子自身もballのままSO05確定を拒否する。Providerはすべての投球batting-resultで親resultIdと実perPitch.resultIdの一致を必須にし、WP/PBは実primaryResultId一致、NPは主結果非該当をそれぞれ別条件で検査する。既計算/保存結果を補修せず、親から選べるSO05へ実際に整合させる。作者のUI正負/親観測対向と既SDK/controller/providerを7spec/99passed/8.93秒、eslint/vue-tsc0で確認。これは非作者再確認/実画面実PGではない。固定後に非作者へ再提示する。
