# preparing read UI接続の限定調査

2026-10-24、root委任により新branch/worktreeの不存在を確認し、API固定候補 `b3a8ef8bb7f1200c423fc32ec803300a0f1724ee` 起点で `feature/mvp-preparing-read-ui` を作成した。変更は本featureのplan/researchだけ。API source・元API/#175 worktree・正式assetsを変更していない。APIはrootが独立レビュー依頼中で、指摘が来れば別API是正を先行する。

## 既存の境界と不足

- `frontend/src/router.ts:33/39` はGameScreenEntry/EntryRecordを直接mountし、page/detail providerを持たない。既存route名/pathと認証guardは再利用できる。
- GameScreenEntryのpropsはEntrySupply<GameListPage>/starts/environment。currentEntrySupplyは正規Pinia、tenant/authEpoch/path/requestKeyを照合する。現一覧headerは全一覧未接続を表すため、preparing-onlyの表示modeが必要。
- EntryRecordのRecordDetailはlineup/recordingRight/draftRestorationを要求する。preparing GETはそれらを提供しないため、既存型へ架空pending/readyを詰める案は採らない。別preparing propsと明示modeを追加し、保存情報だけを表示する。
- 現EntryRecordは認証済み・非deniedならローカルGameScreenを表示し得る。preparing-read modeではこの入力も表示しない。default modeの従来動作を今回のread供給へ流用しない。
- `frontend/src/api/client.ts:223` のcookieMayRenewはauth/players/team-recordsのみ。gamesの実GETはCookie更新を伴うので、同既存不確実性処理へ分類を追加する必要がある。
- appProvidersのPinia/共有queryClient、authStoreの認証切替時queryClient.clear、既存currentEntrySupplyを使える。TeamScreenのQuery実装は参考になるが、今回は自動retry/refetchとInfinity cacheを持ち込まない。

## 選択した最小接合

api/games.tsは既存apiRequestへのGET2件の薄いwrapper、GameScreenEntryProvider.tsは共有QueryClient上でfetch/transport確認→表示用EntrySupply変換だけを担う。2 route hostはそれぞれpage/detailを既存子へ渡し、routerはcomponent差替えだけに限定する。既存EntryTypesへpreparing保存詳細型とmodeを加える。新サービス/HTTP/queue/providerの代替成功層は作らない。

requestKeyは子が要求したcursor/詳細IDと対応させる。同じcursorへ戻る場合の古い応答は別のrequest sequenceで拒否する。query keyへ要求世代を含め、自動retry/refetchを切り、cancel/remove/gcTime0で旧結果を保持しない。過去に訪れたcursorだけをback履歴として扱い、失敗/retryで訪問歴を偽造しない。

transportのstatus/preparing・基本型・UUID等の確認は、保存規則の業務検証や出所証明ではない。規則は正規backend codecが検証した保存値を表示するだけで、値域/相関/優先順位/規則ID照合をfrontendにコピーしない。未知lineup・記録権・下書き復元・端末前提は未取得のまま。実team名称等がAPIにない場合は日時/任意ラベル/IDを使い、名称を推測しない。

## Cookie/失効の直接影響

正規clientはHTTP応答が不明な場合や古いCookie更新可能応答でinvalidateUncertainCookieを実行し、tenant/epoch/challenge再照合後にだけ本文を返す。/gamesをcookieMayRenewへ加えるとunmount abortもこの既存処理の対象になり得る。providerがabortを黙って吸収して認証を維持する実装にはしない。表示側は認証変化で結果/選択/履歴を落とし、新tenantのcacheへ遅延結果を採用しない。

変更は/gamesと/games/…の分類と直接回帰試験まで。authStoreの署名/認証意図/共有アカウント・単一記録端末契約を変えず、新Cookieや本人/運用署名を作らない。nonceは既存clientの要求challengeであり、別の認証手段を作らない。

## 実画面→実API→DBの後続受入準備

API候補は単体127・実HTTP/隔離DB11成功を記録しているが、これを実ブラウザ証拠にはしない。本UI単位ではVitest/静的接合を検査し、実ブラウザの環境立上げ/実行は別実行単位の指示へ残す。

rootの追加観測により、既存GameScreenE2eSupport.tsはopenssl -newkey、対応Python helperはランダムTOKEN_SIGNING_KEYを生成する。今回の委任外なので実行せず、既存GameScreen.playwright.config.tsのglobalSetupも再利用しない。sealed/P6資料やプロジェクトを参照/実行しない。

後続の最小候補は、専用のHTTP localhost originへbuilt frontendと/api→実製品backendの同origin転送を置き、既存disposable PostgreSQLと非秘密固定試験署名素材を使う方法である。現vite.config.tsは開発用backend port8800への/api転送を持つため、共有8800を使わず、専用runnerの転送先/portを動的分離する必要がある。実装ファイル/設定/起動責任は後続の限定計画で確定し、本単位でVite設定や旧E2e helperを変更しない。

最初に実Chromiumでログイン画面→本物のPOST /auth/login→Secure Cookie受領→GET /auth/sessionの能力検査を行う。Cookieをbrowser.addCookies等で注入したり、auth dependency override/route.fulfillで認証成功にしたりしない。HTTP localhostで能力が成立しなければ手順を未実施のまま残し、新TLS/運用鍵発行や認証成功stubへ切り替えない。運用HTTPS/実機完了とは区別する。単体UI実装はこの能力検査を待たない。

rootからの追加実測報告では、Chromium149.0.7827.0が非認証のHTTP 127.0.0.1動的portでHost-prefix/Secure/HttpOnly/Path=/ Cookieを受理した（boolean確認のみ）。これはloopback browserの部分能力検査で、製品login/署名/実API認証成功の証拠ではない。新TLS鍵なしの経路を検討できる根拠として保持し、上記の製品auth/session能力確認は後続へ残す。API受領追記270347f0はsourceがb3a8と同一とのroot報告を受け、本UI基線b3a8を変更しない。

能力成立後の受入候補は、実loginから準備中一覧→詳細→reload、同じ保存ID/status/snapshot、同tenantだけのページング、越境/失効/旧snapshot拒否、ネットワーク失敗・複数tab/stale破棄と全書込封鎖。DB seedはread準備に限定する。資格/鍵/HTML・CookieをtraceやDOMコピーへ出さず、port/profile/一時領域/containerを自前の所有範囲でcleanupする。現在は起動/検証/Playwright code作成を行っていない。

## ゲートと引渡し

独立計画レビュー・PO委任承認前であり、製品未着手。APIレビュー是正が必要なら固定依存更新をrootへ返す。親#175の正式追加敵対1回は#174→#173後の実基線条件が未成立で未消費。今回の計画/候補コードのレビューをその枠や既存回数のリセットへ使わない。実ブラウザの能力/受入・正式7.7/実統合・公開は未達として残す。

独立計画レビュー第1回: /root/independent_review、上記plan894c9d59/research2e0786d6、可決0/0/0。rootはPO委任によって同scopeステップ1を承認（日時/根拠/対象はplan末尾）。既存レビュー回数・正式追加枠を保持。
