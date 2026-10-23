---
feature: mvp-preparing-browser-read
status: active
承認: 済（PO委任によるCodex判断）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-preparing-browser-read
created: 2026-10-24
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 準備中試合の実ブラウザread経路

## 1. 背景・目的

U-G1/#175のread接続候補を、実ログイン画面→正規client/C2→実FastAPI→隔離PostgreSQL→一覧/詳細/reloadまで検証する。API基線はb3a8ef8bb7f1200c423fc32ec803300a0f1724ee。別単位の承認済みUI候補が固定されたら、その固定HEADをこの枝へmergeし接続する。UI型やproviderの別実装を作らない。PO委任4/5/6/8/10に基づく候補検証単位で、正式7.7/#174→#173→#175の統合、作成/保存、1試合、運用HTTPS、実機受入は完了にしない。

## 2. スコープ

- `frontend/src/screens/GameScreenE2eSupport.ts` / `.py`: 既存専用DB/bootstrap/子プロセス/0700資格保管/finally cleanupを共用し、明示的なpreparing-readモードを追加。既存sealed-uiとreal-game未達試験の意味は維持。
- `frontend/src/screens/GameScreenPreparingRead.playwright.config.ts`、`GameScreenPreparingRead.e2e.ts`、`GameScreenPreparingReadE2eSupport.ts`: 独立1workerのChromium候補。最後の薄いglobalSetup wrapperが既存Supportからexportする共用関数を明示preparing-readモードで呼び、既存default sealed-ui入口はそのまま保持する。既存GameScreenE2eProcessを再利用しtrace/video/screenshot/失敗DOM出力なし。既存frontend/src/screens/GameScreen*はcore既登録、新core登録/検査緩和なし。
- `frontend/src/screens/GameScreenE2eProcess.spec.ts`: 共用起動/モード境界の必要な回帰だけ。既存型・backend pytest fixtureを再利用し、新DBfixtureや常時成功サービスを作らない。
- 本plan/researchのみ。正式資産・要件/設計/ADR・親plan・7.7・通常製品sourceは編集しない。UI候補の固定供給はその単位のsourceだけを実履歴付きmergeする。

## 3. 影響する正本

正本変更なし。FR-001/013/014、NFR-005/014/018/019/023の既存意味を維持。新TLS/運用署名鍵の発行・既存.env/秘密の読書き・共有DB/運用公開は行わない。既存親の正式追加敵対1回は未消費のまま。

## 4. 実装方針

preparing-readモードは**HTTPの127.0.0.1動的portだけ**。既存HTTPS sealed-uiモードのopenssl/TLS生成器は呼ばない。署名素材は既存test_roster_boundary.py::_client_appの非秘密固定32byte素材設定式だけを使い、認可stubを呼ばない。loopback HTTPでSecure/HttpOnly/__Host Cookieを受理するChromium能力は別の非認証serverで実測済み（149.0.7827.0、boolean true）。この能力検査自体を製品認証証拠にしない。

Python driverは既存provisioned_product_catalogと実認可/identity準備を再利用し、可能ならAPI候補のpreparing_read_database fixtureを直接共有する。新read用fixtureがcreate_app前に固定素材を設定できる順序を明示し、実署名・DB認証・C2・tenant scopeを差し替えない。アプリengine factoryを実専用engineへ向ける以外にscope/SQL/authの代替実装を置かない。実uvicornをloopback動的portで立て、Viteの通常/api proxyから接続する。ViteはenvDir:falseで.envを読まず、外部PITCHLOG_*やDSNを継承しない。Origin/HTTP loopbackの許可はこの試験driverの明示modeに限定し、製品認証設定の既定や制限を緩めない。

試合・親・大会のseedは既存read DBfixtureだけを隔離DBで使い、作成成功と数えない。成功Cookieを事前投入したり、認証済みPinia/stateをブラウザへ注入しない。実ログインフォームを入力して通常POST /auth/login→session確認→一覧GET/詳細GETを通す。ブラウザに表示された保存ラベル/規則/IDをseed原本と突合し、再読込後も同じ値。seed中のHTML風ラベルはテキスト表示で、DOM注入なしを確認。ページ移動・404/別tenant・失敗時未取得/再試行を観測し、利用可能な実経路だけを検証する。期待応答をroute.fulfill等で代用しない。通信を止める故障注入は可能だが、応答を偽造しない。

資格情報は0700専用dir/0600ファイルだけに限定し、標準出力/trace/画面証跡へ残さない。自分が起動したPID/DB/container/portだけをfinallyで片付ける。timeout/非0/cleanup失敗/skipは失敗または未実施として記録。既存全1試合real-gameの未達sentinelをread成功で置換しない。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 明示readモードと固定UI候補の実ブラウザ接続 | 新鍵なし・実製品ログイン画面/Cookie/C2/API/DBで一覧・詳細・reloadを確認、保存値/越境/表示escape/再試行/ページ境界を利用可能範囲で実測。対象Vitest/Prettier/ESLint/vue-tsc、driverのbackend Ruff/ty、差分/文書検査。固定HEAD/diffと実証範囲を独立レビューし、cleanup後の残存資源0。正式check未達と実機/運用未実施を区別 |

## 5. DoD

上記候補browser経路を再実行可能にし、実ログイン・保存済みreadのHTTP/DBを通す。試験成功と、正式develop/作成/1試合/HTTPS運用/実端末/全故障系は分けて記録する。既存runner/封鎖UI/正式追加レビュー枠/旧履歴は保持。PO委任の承認記録に対象版/判断者/日時/根拠を固定し、本人署名や人間逐行確認を代記しない。

## 6. テスト計画

実Chromiumで通常login/list/detail/reload・cursor・HTMLテキスト・別tenant404・通信故障と明示再試行。製品のログ/ブラウザtraceから資格値を回収しない。UI単位のVitest/型/escape回帰を再利用、共用bootstrap変更はmode選択/禁止Origin/異常終了/cleanupを検査。既存sealed-ui fullは新鍵発行器を伴うためこの委任で実行しないことを記録し、readモードの実測で置き換えたとはしない。正式checker TB005等を成功へ読み替えない。

### 計画承認

2026-10-23T15:42:35.663053+00:00、Codex主担当/rootはPO委任4/5/6/8/10に基づき、plan SHA e9a4fc1a91a04b89820e7c2d120679ca23b1ea8eb6097e2f5739a796b83ac8ff / research735f6702ce6800fa9f8de01cc748bc4b215360abaedaca09628abd6a0b4c0d24のステップ1を承認。独立非作者/root/o5_final_reviewは第1回P1=2を採用後、第2回差分/影響で可決0/0/0。旧履歴保持。承認は隔離read browser候補だけで、正式7.7/親追加枠/実機/運用を解除せず、山田正輝の署名・人間逐行確認を代記しない。本記録追記は承認メタデータだけ。
