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
| 1 | 実画面driverを作り、3新規試合/各10閲覧/2waveの自然更新を検査する | 実Cookie独立、記録context3/閲覧context30、共通team認証、各gameの初期状態と未送信非表示注記を確認 |
| 2 | owned wrapperで正式API/実DBの保存値と60件の閲覧時間を照合する | 既recordRealPitch/正式POST・GET、server保存時刻から各閲覧表示10秒以内、全スコア/回/アウト/走者/履歴一致。閲覧APIはlogin後GETのみ/記録権端末登録等0。DB各2play/2accepted・tenant/game一貫。実測時間を出し未達を隠さない |
| 3 | 固定源でowned1回を実測し証拠を保全する | source固定/共通lock全fixture寿命/共有DSNunset/実UID20003/既TLS/cleanup。PGは現在P3担当の実走完了後root調整で開始。実機/信頼TLS/大量履歴や長時間負荷は別残件 |

編集範囲はfrontend/src/screens/GameScreenViewerThreeGameLoad.e2e.ts、同.playwright.config.ts、backend/tests/db/test_viewer_three_game_load_owned.py、本計画のみ。既実login/create/start/record helperを再利用し、事前game/play投入や仮APIを作らない。全field一致・各viewer timingの完全集合を検査する。失敗時にも新たな反復は原因と修復を固定してから。最終独立静読をPG前に受け、型/lint/collectを実行する。

実装前の単位整理: step1はFE driver/config、step2はBE owned wrapper/検証、step3は非作者確認後の実走と結果を対象とする。3記録POSTの実要求〜応答時間帯が両waveで重なることを観測し、試合ごと異なる通常結果を指定して別試合混同を検出する。総試験期限は900秒だが製品RPC/leaseや10秒閲覧条件を延ばさない。

非作者REPORT2b087deaのP1を採用。履歴だけの時刻採取を廃し、status/score/回/アウト/走者/count/対象履歴結果/18出場枠/保存時刻を一回のDOM snapshotで同時観測する。同saved_atは元実保存GETへ完全一致させる。後段45秒pollで修復して10秒成功にしない。追加所有は試験用viewerThreeGameSnapshot.e2e-support.tsと同.spec.tsのみ、DOM全状態が遅れて20秒ならその20秒を返す対向を同じcallbackで検査する。実画面/実PG成功の代わりにはしない。

## 2026-11-09 実走前のfixture整合

PO委任によるCodex主担当判断。owned launcherが継承DSNを拒否して新規隔離PGのDSNを注入する既経路に合わせ、共通lock fixtureの環境変数「存在」拒否2行を削除。db subject/role identity guard・同一fixture・commonlockを維持し、外部DSNをunsetして共有先へfallbackする処理は追加しない。実3game負荷はこの修復後固定点で実施する。
