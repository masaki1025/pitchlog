---
feature: mvp-runner-operations-connection
status: draft
branch: feature/mvp-runner-operations-connection
承認: 未
重さ分類: コア領域
計画レビュー周回: 0
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
