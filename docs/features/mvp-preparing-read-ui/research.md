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

## 承認ステップ1の実装・検査記録

実装基線はPO委任承認commit `e885c58988cc3f6f03a813ca4a96c158fd42c22d`（API sourceはb3a8固定と同じ）。承認済みステップ1/1のfrontend 14pathsと本researchだけを変更した。plan、API/backend、正式assets、親#175、他worktree、frontend依存宣言/lockを変更していない。pnpm frozen installは作業wtのセットアップだけであり、最初にrepo rootからpnpm execを実行した際の「No package found」はfrontendへcwdを修正して解消した。

実装は正規GET2 wrapper、共有Pinia/QueryClient上の供給composable、既存route名を維持する2host、明示preparing-read表示mode。fetchQueryはobserverを作らずretry:false/gcTime:0、要求ごとの固有keyを使用し、完了/終了時に自分のqueryだけを除去する。認証・tenant・path・ID変更時の表示/履歴破棄は同期、通信開始はnextTickで一連の認証store変更後に行う。非協調abortの遅延結果も内部要求世代で拒否する。cancelは実query signalへ伝播し、既存clientのCookie不確実性処理を抑制しない。

一覧はサーバーの不透明cursorをそのまま利用し、成功した訪問だけ履歴に加える。canPrevious?:booleanを既存GameListPageへ追加し、初期null cursorへ戻れるようにした（nullは従来「前なし」にも使われていた）。同フラグは既存表示guardでも型確認する。送信中の多重操作を拒否し、失敗時は同page retry/直前の訪問pageへの復帰だけを行う。

詳細は別PreparingReadDetail propsで保存列と適用規則JSONをVue text表示する。規則の再解決・値域/相関codec複製はない。RecordDetailを捏造せず、スタメン・記録権・下書き復元は未取得、端末/永続化/queue前提も未取得のまま。read modeでは成功/確認中/拒否/故障の全状態でGameScreen入力をmountしない。GET以外の作成・開始・再開・保存・送信処理は追加していない。

### 途中版の失敗と是正

- V1（最初のsource/新spec追加後）: 対象147件中146成功/1失敗。既存route試験の「未接続・通信なし」期待値が新接続と不一致。また同期watchが認証storeの中間状態から通信を再開し、storage同期→認証破棄へ再入してstack overflow出力を生じた。既存routeの期待をread接続へ更新し、同期破棄/nextTick開始へ分離して是正した。
- V2: 対象154件成功。cursor二重操作等を追加したV3は159件のassertion成功だが、旧DOMの二重click handlerが消去後のvisiblePage.nextKeyを参照して未処理例外1件、exit1。handlerの参照をnull安全にし、requestPage内の実状態照合で拒否した。例外をテスト期待へ変更していない。
- V4: 対象159件成功・未処理例外0。ESLintは試験内2つのdefineComponentにone-component-per-file違反2件。共通probe factory1箇所へまとめたV5では未使用capture1件を検出し、その不要変数だけ除去した。

### 最終検査

2026-10-24 JST、最終版の対象Vitestは5files/159件成功、skip/timeout/未処理例外0（実測4.70秒、tests889ms）。対象: api/games.spec.ts、screens/GameScreenEntryProvider.spec.ts、screens/GameScreenEntry.spec.ts、router.spec.ts、api/client.tenant.spec.ts。新規GET wrapper/C2、保存値の非再計算とXSS text表示、list/detail route host、未知前提/全入力封鎖、opaque cursor往復/null初期page/失敗履歴非追加/明示retry/多重操作、A→B→A/ID切替/tenant/epoch/path/unmount/遅延headers・body/非協調abortによる旧内容/cache拒否、401/403/404/503/不正transport、games Cookie不確実性/metadata/旧headers/abort/非games分類を検査した。unitのfetch mockと既存認証単体fixtureは単体証拠であり、実HTTP認証の証拠に数えない。

同じ最終sourceで対象14pathsのPrettier check、frontend全体ESLint、vue-tsc --noEmit、pnpm run buildがexit0。build closureはscannedFiles9、externalReferences0、policyViolations0、Vite build457ms。新実装後の全Vitest再走は行わず、対象既存+追加に限定した。root docs status/plan sync/diff検査結果は下記固定時の記録とする。

frontend固定差分（`git diff --cached --binary --full-index e885c589 -- frontend`）SHA256: `6230a8b2fdd441b6bdd41e529b9621c50301dd7661f14042b496d6e79fef378b`。

- games.ts SHA256 `b1e3e91d87c2dba42da76b6273ed93e96761dc2acac2f7a5913ce13106899191`
- GameScreenEntryProvider.ts SHA256 `334029d9661436679218c3db92527adb67ef975191b243732ddda12c2fe99fec`
- GameScreenEntryRecord.vue SHA256 `7605525bcbe076d5a17e787b155bf1ac081f6c7fe88607f8eb1b4b5c8ec7c0a1`

実装commitのHEAD/全差分SHAは自己参照を避けて引渡し応答で固定する。親#175の正式追加敵対1回は未消費、正式#174→#173→#175/7.7/閉集合登録・運用提供・作成保存・実機完了を主張しない。本単位でDB/browser/HTTP serverは起動していない。既存鍵生成helperを実行せず、新TLS/運用署名鍵・secretを生成していない。実browser driverはrootの別worktree/別承認単位が担当し、本UI固定HEADの受入後に評価する。

browser受入との表示接合: 既存accessible label「試合一覧」「次のページ」「前のページ」「閲覧画面へ」は維持。新詳細見出し「準備中試合の保存情報」、保存規則項目「保存された適用規則」、詳細再試行「この試合を再試行」。保存ラベルはraw HTML挿入せずtext表示する。

固定前のroot検査はcheck_docs_status.py（20 documents/0 violations）、check_plan_docs_sync.py --plan docs/features/mvp-preparing-read-ui/plan.md --base e885c589 --head HEAD、git diff --checkがすべてexit0。正式assets/default閉集合の検査成功をこの結果に含めない。

## 独立コードレビュー第1回P1の採用・同ステップ是正

非作者/root/o5_final_reviewの第1回全文コードレビューは旧HEAD `83e62a178347bbb4792e94d4ed55447107c850d1` に対してP0=0/P1=1/P2=0。rootの通知によりtransport型P1を採用し、承認済みステップ1同scopeの最小是正を行った。旧commit/159件成功とそのreview差分（承認e885→83eのfull-index binary SHA256 `8e2207eecdf4eaac03863c2e4f72a1974d37914bc7d4ecafa9793bffc4ecdbe6`）は改変せず保持する。159件成功は本P1を検出しておらず、不正body拒否の完了証拠として十分ではなかった。

原因はgames.tsの既知語彙判定でString(value.game_type_key)を使い、JSON配列['game_open']を文字列へ強制変換して受理したこと。typeof === 'string'の確認を先行させ、強制変換を除去した。許可語彙・backend/業務規則/codec・認可/Pinia/client/Cookie・表示動作は変更していない。編集はgames.ts、既存games.spec.ts、本researchの3pathsだけ。API・正式assets・他worktree・planは変更しない。

回帰は正規clientに有効C2 metadataを返すJSON応答で、詳細のgame_type_keyと一覧のitems[0].game_type_keyへ同じ配列を入れ、それぞれtransport不正としてrejectすることを検査する。HTTPは1回のみで、認証が有効のまま失敗するため、認証拒否による偶然のgreenではない。まずsource未修正で追加した回帰を実行し、games.spec.tsの18件中16成功/2失敗（一覧・詳細ともPromiseがresolveし拒否されない）を再現した。その後sourceの型判定だけ是正した。

是正後の同対象5specは161件成功（旧159+追加2）、skip/timeout/未処理例外0、実測4.66秒/tests918ms。変更2pathsのPrettier、frontend全体ESLint、vue-tsc --noEmit、pnpm run buildもexit0。build462ms、closure scannedFiles9/externalReferences0/policyViolations0。全Vitest・DB/browserは再走していない。rootの別browser候補は旧83eのsource受入済み/実行未着手との通知を受け、是正HEAD固定後にrootが接合更新する。本wtから別候補へ反映しない。

旧83eからのfrontend是正差分SHA256（full-index binary）`30320f56c2a51cac07b7f555c39807d6b5867e641b727f4313ac8d2522ac6851`。是正games.ts SHA256 `ae7978a6d3f50ada0abbe63e627b68cdc0f9955ab65edcbf52649a9ef023f019`。是正HEAD/全差分SHAはcommit後の引渡しで固定する。新secret/運用鍵・push・DB/実browser・正式7.7・親追加敵対枠について、前記の未実施/未消費を維持する。
