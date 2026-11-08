---
feature: mvp-p3-screen-current-followup
status: active
承認: PO委任Codex主担当/root、2026-11-08 22:45 JST、対象65a46950・SHA6925856d4d0037ce723b1c3040fbfebccb648e508f12cd9e2501b88c0b8cca86
重さ分類: コア領域の試験追随
branch: feature/mvp-p3-screen-current-followup-20261108
created: 2026-11-08
計画レビュー周回: 1
---

# 固定6c52の26件訂正画面・後続操作を最後まで検証する

基点6c52fd2b3b665b825d9c4aaf4aabc5d3ab03c732。既正常CURRENT49/唯一71fの製品sourceを一切変えず、既実画面P3試験の26モードだけが早期returnで未検証となっていた後続をつなぐ。旧3球の期待を削らず26球へ同じ操作を適用する。

## 編集範囲と不変条件

- frontend/src/screens/GameScreenPastCorrectionProduct.e2e.ts、必要なら同playwright.config.ts。保存後は実GETの同版next_cursorをC2付きで有限最大2頁取得し、対象26の実event/playを特定する。headだけの配列添字でD1を読む旧想定を除く。26時の早期returnを終端へ移し、既1追記→終了→再開→1追記→再終了→reloadの同成功条件をpitchCount基準にする。同試合の終了確定版に対する既製品stats/CSV readをC2付きで検証し、fixtureのfact/projection補完を行わない。
- backend/tests/db/test_p3_paging_screen_e2e.py。既正常S0→49を保持し後付SQLなし、固定源/artifact前提を確認。SQL列/型をUI前EXPLAINで検査し、同gameのslots/T5旧新版/終了確定版/CSVを有限WHEREで照合する。UI失敗時も実在する証拠だけfinallyで採取し、元失敗を成功へ変えない。
- 新規専用tests（必要ならfrontendの試験用paging helper/spec、およびbackend/tests/test_p3_paging_screen_driver.py）と本計画。製品src/正式assets/共有fixture/台帳は編集しない。新しい疑似Port・mock認証・資格/原要求本文ログなし。
- T2/T4故障原子性は基点に存在するtest_p3_paging_lifecycle_http.pyの既26HTTP原本を次の別caseで再利用する。今回screen1本へ故障用endpoint等を新設しない。故障条件を削らず、画面成功とHTTP故障成功を別証拠として報告する。
- targetは既4通常球、置換は既2種のまま。D5/attempt/原要求再送、writer30秒/受信/SQL期限、認可、未知閉拒否、数学期待は変えない。試験の機能待ちと性能SLOを分けるが製品期限延長はしない。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 画面driverの26件頁/後続操作を追随 | C2/同版頁/対象identity、26モードの既suffix/終了再開再終了/reload/CSVが静的・型検査を通る |
| 2 | 正常49/末尾DB照合と封印 | 既元期待と同試合版を全値照合、有限SQLpreflight、対象純検査、source前後SHAと専用driverをrootへ供給 |
| 3 | root許可後の実走 | CSV owned終了後に共通lock/共有DSNunset/既TLS/source全byte固定/cleanupで1回。画面と別HTTP故障の到達/未到達を区別、失敗同条件反復なし |

PGはrootの固定源受領・実行許可まで開始しない。候補完成は製品完成/正式受理と読み替えない。

## 実装追随

同じ終了版のCSVは成績CSV `/stats.csv?mode=official` を200・実API全表示値と全byte比較する。現製品のP3後毎球ZIPは88列producer未供給で409が正しいため、これを明示的な未完として維持し、fixtureで補完しない。26モードの集合全体だけ900秒・外側960秒へ有界化し、旧3球480秒/個々の操作30秒/製品writer30秒・RPC/SQL期限は不変更。旧動的import案はlintで拒否されたため廃止し、実画面GETから保存した同C2ヘッダを同origin/同gameのcursor GETへ再利用する。資格/ヘッダ原値は出力しない。

step1候補: 同版最大2頁の全head/位置/実ID・件数を検査する試験helperを追加（6正負）。26モードも既追記/終了/再開/再追記/再終了を通す。実行待ちの集合時間だけ有界化し、製品期限は不変。型/対象lint成功、Playwright collect1成功。動的import案のlint拒否と、製品DTOのNode直接importのJSON attribute収集失敗は是正前として保持し、最終はC2実GET原本の再利用＋test-only比較にした。実PGは未実施。
