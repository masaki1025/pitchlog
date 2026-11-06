---
feature: mvp-full-game-rehearsal
status: active
branch: feature/mvp-full-game-rehearsal
承認: PO委任によるCodex/root判断（2026-11-06、既1試合実証の通し試験）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 実画面から9回の通常試合を終了確定する

既LC実画面の新規作成/開始driverと真正v3/唯一artifact/E1/保存/終了providerを再利用し、短い3球試験から9回の通常試合へ広げる。基線afd74ea9。隔離HTTPS/ownedPG専用、事前game投入・仮Port・固定成功を使わない。DB fixtureの名簿/tenantは試験準備、画面で作成した別gameだけを実証する。実機/運用TLS・全操作・MVP完成と区別する。

1. 実画面create/start/pitch driverを共通test helperへ抽出し、163球の9回シナリオを準備。先攻に無走者HR1点、その後両側27三振ずつ（全54打席162投球）。新規作成で実regulationInnings=9を確認し、異なる規則をDBで書換えない。T2の最終通常終了、得点、打順/攻守交代/履歴をサーバー応答で確認。1球毎の5秒条件を維持し、機能実証と性能を別出力。共有コードはtest helperだけでドメイン式を複製しない。
2. owned wrapperで最終finished/head/confirmed_ended/163source/受理164eventを実DB全値照合、同一要求再送の重複不増・途中reloadを通す。既共通lockはPG/browser生成から破棄まで保持。性能候補と交代の短いowned試験を先行させ、長時間lockを無計画に占有しない。
3. 実行結果・固定HEAD・実時間・未達を台帳へ渡す。通常9回経路が成立しても、取消/過去訂正/交代/走塁/故障/成績27/両CSV/実機等は別のMVP必須条件として残す。性能/失敗を緩めない。最終非作者確認とCIの前に正式提供としない。

編集範囲はfrontend/src/screensの新E2E/helper/config、backend/tests/dbの新ownedwrapper、本feature文書。製品コード/正式assets/他WTを変更しない。rootのみwriter。

## 優先順位の追補（2026-11-06、PO回答に基づくCodex/root判断）

PO回答「むずかしそうなら5秒以内は後回しでもいいよ」に従い、まず通常1試合の機能証拠を揃える。本新試験は全投球時間/5秒超件数を出力して機能判定と分離する。既LCの5秒assertは削除・緩和せず、性能未達として残す。性能達成/MVP全完成の判定には使わない。
