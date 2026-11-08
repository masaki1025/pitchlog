---
feature: mvp-viewer-three-game-load
status: active
branch: feature/mvp-viewer-three-game-load-20261108
承認: PO委任によるCodex/root判断（2026-11-08 22:59 JST、既MVP同時3試合×11端末の受入試験）
計画レビュー周回: 0
---

# 実記録3台と閲覧30contextの受入試験

既mvp-connected-rehearsal step3と初回MVP同時3試合条件に基づく試験専用追補。基点60c302d2、製品6c52/唯一71f/正常CURRENT49。製品/計算/規範期待/認可/保存/正式資産は変更しない。実機・本番負荷と隔離Chrome contextの負荷は区別する。

| # | 作業 | 成立条件 |
| --- | --- | --- |
| 1 | 既実UI helperで3試合を新規作成・開始し、各10閲覧contextを用意する | 実Cookie独立、記録context3/閲覧context30、共通team認証、各gameの初期状態と未送信非表示注記を確認 |
| 2 | 同時3記録の2waveを保存し、30閲覧の自然更新と実DBを照合する | 既recordRealPitch/正式POST・GET、server保存時刻から各閲覧表示10秒以内、全スコア/回/アウト/走者/履歴一致。閲覧APIはlogin後GETのみ/記録権端末登録等0。DB各2play/2accepted・tenant/game一貫。実測時間を出し未達を隠さない |
| 3 | 固定源でowned1回を実測し証拠を保全する | source固定/共通lock全fixture寿命/共有DSNunset/実UID20003/既TLS/cleanup。PGは現在P3担当の実走完了後root調整で開始。実機/信頼TLS/大量履歴や長時間負荷は別残件 |

編集範囲はfrontend/src/screens/GameScreenViewerThreeGameLoad.e2e.ts、同.playwright.config.ts、backend/tests/db/test_viewer_three_game_load_owned.py、本計画のみ。既実login/create/start/record helperを再利用し、事前game/play投入や仮APIを作らない。全field一致・各viewer timingの完全集合を検査する。失敗時にも新たな反復は原因と修復を固定してから。最終独立静読をPG前に受け、型/lint/collectを実行する。
