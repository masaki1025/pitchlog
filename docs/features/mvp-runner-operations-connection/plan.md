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
