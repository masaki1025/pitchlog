---
feature: mvp-preparing-read-ui
status: active
承認: 済（PO委任によるCodex判断・隔離read UI候補）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-preparing-read-ui
created: 2026-10-24
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# preparing read画面への限定供給計画

## 1. 背景・目的

固定API候補 `b3a8ef8bb7f1200c423fc32ec803300a0f1724ee` のGET2件を、既存GameScreenEntry/EntryRecordのprops境界へ供給する。FR-001/013/014、NFR-005/018/019/023と既存C2・認証世代境界を守り、準備中一覧/保存情報の閲覧だけを接続する。shared account・単一記録端末MVPの意味を変更しない。

本単位はAPI候補起点の別worktreeで、既存#175 step4の画面供給部分の隔離候補準備。親の承認/6ステップ/レビュー履歴は継承し、正式#174→#173→#175・7.7・正式追加敵対1回を完了/消費としない。本回はplan/research起案のみ。独立計画レビューとrootのPO委任承認後に1ステップを実装する。APIの独立レビューで是正が必要なら、その解消と固定依存の再確認を優先し、別wtのAPI sourceを無断修正しない。

## 2. スコープ

| 種別 | 将来の実装対象 |
| --- | --- |
| 正規GET client | 新 `frontend/src/api/games.ts` / `games.spec.ts`。GET一覧/詳細、AbortSignal、tenantBound:true、read DTOのtransport型を供給 |
| 薄い供給層 | 新 `frontend/src/screens/GameScreenEntryProvider.ts` / `GameScreenEntryProvider.spec.ts`。共有QueryClient/Pinia/正規clientからEntrySupplyへ変換。2hostのcomponent試験も同specで行う |
| route host | 新 `frontend/src/screens/GameScreenEntryHost.vue` / `GameScreenEntryRecordHost.vue`。それぞれ一覧/詳細供給と既存子へのpropsだけを担う |
| 既存表示境界 | `frontend/src/screens/GameScreenEntry.vue` / `GameScreenEntryRecord.vue` / `GameScreenEntryTypes.ts` / `GameScreenEntry.spec.ts`。明示preparing-read modeと保存詳細用propsを最小追加 |
| 共通接合 | `frontend/src/router.ts` / `router.spec.ts`、`frontend/src/api/client.ts` / `client.tenant.spec.ts`。既存2 routeのcomponent差替えとcookieMayRenewの/games分類だけ |
| 作業記録 | 本featureのresearch。実ブラウザ受入の手順/未成立条件を分離して記録する |

新QueryClient/Pinia、HTTP/wire/ACK/queue層、authStore変更、backend/正式assets、ドメインcodec/計算、UIによる規則再解決は追加しない。create/start/save/送信/初期権/RG1、全状態一覧、スタメン/記録権/下書き復元providerも対象外。未提供の入力/書込ボタンを有効化しない。

## 3. 影響する正本

反映なし。正本・親#175計画/レビュー/7.7・コア登録資産を変更しない。frontend/api/clientは既存の同期/記録権/tenant境界にも影響する共有パスなので、分類の2経路追加とCookie不確実性回帰以外へ広げない。既存許可/失効/拒否条件を緩めない。新パスに必要な正式登録/権限差分が判明すれば、その具体項目だけをrootへ返す。

## 4. 実装方針

### transportと供給

正規apiRequestのGET `/games` / `/games/{id}` へtenantBound:trueとsignalを渡す。APIのstatus=preparing・UUID・aware日時・ラベル・Page/cursorのtransport形を確認し、不正body/他状態をreadyにしない。snapshotはサーバーが検証した保存値として受け取り、その値の表示だけを行う。表示可能なJSON値/基本型の確認を、規則の値域・相関・6-key業務codec・規則行出所証明へ昇格しない。規定回/DH等は返された値をそのままラベルへ写し、現在規則から補正/計算しない。クライアント側の新resolverやschema/相関検証コピーを作らない。

appProvidersの正規Pinia・共有QueryClientを使う。query keyはpreparing専用prefixにtenant/authEpoch/path/一覧cursor又はgame IDと要求世代を含める。要求開始時にこれらをcaptureし、HTTP処理/DTO変換完了直前にも照合する。EntrySupply.requestKeyは既存子が要求したcursor（詳細はID）と対応させ、同じcursorへ戻るA→B→Aでも古いAを採らない内部request sequenceを別に持つ。auth切替/route変更で旧供給・履歴・選択を即座に破棄し、旧応答を新cacheへ書かない。

Queryのretry/refetchOnMount/focus/reconnect/intervalは無効にし、明示再試行だけを行う。supersede/unmountではsignalをabortし、自分の旧queryをcancel/remove、gcTimeを0として不要cacheを残さない。認証切替の全体cache破棄は既存authStoreへ委ねる。abort後に解決する非協調的な応答もsequence/epoch/path照合で拒否する。

一覧cursorはサーバーの不透明値のまま扱い、decode/生成をしない。初期nullと実訪問済みcursorの履歴だけを持ち、前へ戻る/同page retryで架空cursorや履歴を作らない。送信中の二重操作を抑止し、失敗時は現在の取得先を明示して同page再試行を可能にする。pageLabelは表示履歴に基づく番号だけで、全件数や全状態の提供を示さない。

### 最小表示拡張

routerの `/games` / `/games/:gameId/record` の名前/認証guard/戻り経路契約を保ち、薄いhostへだけ差し替える。子へ `mode='preparing-read'` を明示し、従来modeのprops試験/封鎖を保持する。

GameScreenEntryはpreparing modeで「準備中の試合」と限定範囲を表示する。既存GameListPageへ同tenant/準備中の項目を写し、未取得のチーム名等を捏造しない。APIが持つ日時/任意ラベル/IDだけを表示し、全状態一覧や開始候補readyへ写さない。開始UIはこのmodeでは供給せず、閲覧先へだけ遷移する。

GameScreenEntryRecordには `preparing?: EntrySupply<PreparingReadDetail>` を追加し、保存項目/保存された適用規則だけを表示する。既存RecordDetailはlineup/draftRestorationを必須にするため、このread DTOから構築しない。lineup/recordingRight/draftRestoration・永続化/queue等は未取得として残す。preparing-read modeでは状態/失敗にかかわらずGameScreenのローカル入力欄も表示しない。read成功を記録再開や入力権の取得へ拡張しない。

404/越境はdenied、通信/503/不正bodyはfailedとして古いreadyを見せず、401/認証世代変更は既存auth処理を優先する。失敗/abort/失効で他試合や別tenantの内容を代替表示しない。詳細の不正UUIDは読取前に拒否する。利用者文字列・保存規則値はVueの自動エスケープで表示し、v-html/innerHTML/HTML文字列注入は行わない。

### Cookie更新の共通client影響

cookieMayRenewの既存経路分類へ `/games` と `/games/…` だけを加え、`/gamesx` 等へ拡張しない。GETでもCookieが更新され得るため、古いheaders/epoch応答、metadata不正、応答不明/abortで既存のCookie不確実性無効化・通知dedupeを維持する。provider側でabortを理由に不確実性通知を抑制しない。分類は認可条件として使わず、認証/共有通信規約を変更しない。

### 実ブラウザ受入の準備を分離

本実装単位の受入はVitestのclient/provider/host/表示接合と静的検査までとし、実画面→実API→DBのPlaywright受入は別の実行単位へ残す。researchへ環境/実login/断定可能範囲/不足を具体化する。unitのfetch mockを実API証拠へ数えない。

既存GameScreenE2eSupport.tsと対応Python helperは新TLS鍵/署名鍵を生成するため実行・globalSetup再利用しない。sealed/P6素材も利用しない。後続候補は非秘密固定試験署名素材の実製品backendとHTTP localhost上の実Chromiumとし、最初に本物のPOST login→Secure Cookie受領→認証済みGETの能力検査を行う。browser.addCookies、手製成功Cookie、route.fulfillやauth overrideで成立させない。TLS/運用鍵を新規発行せず、能力が成立しなければbrowser受入を未実施と記録する。これは単体UI接続の開始条件にはしない。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | 準備中read APIを既存入口へ薄いhost/providerで供給する | 正規client/C2/QueryClientから一覧/詳細propsへ接続。subset表示、保存値の非再計算、未知前提未取得と全書込封鎖、cursor履歴、同時/stale/epoch/path/requestKey/unmount破棄、拒否/失敗/明示retry・XSS・Cookie更新不確実性をVitestで確認。frontend対象Prettier/ESLint/vue-tsc/Vitest/buildとdocs/差分検査。実browser受入の準備/未成立を記録し、固定差分を独立レビューへ提出 |

## 5. DoD

GET2件と既存表示propsが接続し、準備中の同tenant保存値だけを表示する。認証/経路/要求の変化で旧結果を捨て、未知記録前提をreadyへ捏造せず、新規書込/ドメイン計算を増やさない。既存画面とauth/client拒否の回帰を保持する。

候補コード/対象検査と実browser受入準備をレビュー可能にする。実API独立レビューで見つかった未解消P1、正式基線/7.7/#175追加敵対、実ブラウザのSecure Cookie能力・実画面到達は別に記録し、未実施を成功にしない。公開/実機/運用HTTPS・MVP全体・親step4完成は本DoDに含めない。

## 6. テスト計画

- games client: GETだけ、tenantBound/C2・signal・limit/cursor/ID、status/preparingとtransport不正拒否。保存snapshotを現行規則へ変換しない。
- provider/host: 正規provider installerとqueryClientを使用し、一覧/詳細ready・denied/failed/未取得、null開始cursor/実履歴back/retry、二重操作/多重要求、A→B→A、tenant/epoch/path/ID切替、遅延headers/body・非協調abort・unmount・旧cache破棄を確認する。unitのHTTP応答mockはunit証拠として限定する。
- 既存Entry/spec/router: preparing mode追加と従来propsの互換、RecordDetail偽装なし、read中/成功/拒否/失敗すべてで入力/再開/保存/送信を開かない。不正ID/別tenant/401/404/503、利用者HTML/属性/event文字列がtextとして見え実行/DOM挿入されないことを検査する。
- client.tenant.spec: /gamesと詳細のCookie更新分類、stale headers/epoch・metadata不正・通信/abort後の既存不確実性通知/重複抑止、非games経路と既存players/team-recordsの非緩和。
- 対象既存＋追加Vitest、対象Prettierとfrontend ESLint/vue-tsc/build、docs/差分検査。失敗/skip/timeoutは残す。実Playwrightは上記の別手順で準備し、実行を指示された後だけ検証する。既存鍵生成helper/秘密/手製Cookieで前提を満たさない。

### 計画承認記録

2026-10-23T15:41:15.129055+00:00、Codex主担当/rootがPO委任4/5/6/8/10に基づき、本単位ステップ1の限定実装を承認。対象は上記API基線b3a8ef8b、独立レビュー対象plan SHA256 `894c9d593781efeb1404f01bd3cb8753e12463dfc57a076aec082781c34d6c7c` / research `2e0786d61e1837f478862054c9df36d3fba701f7248b07aba35baaeb39a012d4`。非作者/root/independent_reviewの第1回全文レビューは可決P0/P1/P2=0/0/0。本反映は承認メタデータ/記録だけ。正式7.7/親追加敵対1回/作成保存/実ブラウザ/実機の未達を解除せず、山田正輝の個別実値確認や署名は代記しない。

## 7. 未承認の最小追補案: Appの戻り先callerと保護画面ナビゲーション

本節は追補案であり、既存の承認を追加scopeへ流用しない。rootと独立レビュー/PO委任承認の後に、既存ステップ1/1の是正として実装する。現時点では製品sourceを変更しない。

### 発見事実・保持する履歴

UI旧固定点83e62a17の独立コードレビュー第1回P0/P1/P2=0/1/0を受け、transport文字列型P1をbb0973d1で是正した。旧159件成功ではそのP1を検出しておらず、追加回帰2件の修正前失敗と是正後161件成功をresearchへ保持している。独立第2回差分レビューは可決0/0/0、独立実行161件成功/5.56秒とのroot通知を受領した。レビュー2回や159→161の履歴をリセットしない。

rootの別単位で実browser初回2件が失敗した。root報告では実POST /auth/loginは200だが、その後の期待経路へ進まない。現物のApp.vueはfinishLoginでredirect queryを読まず/team固定、認証失効watchでもredirect=/team固定。一方、既存resolveGameEntryReturnPathは/team・/games・canonical UUIDの/games/{id}/recordをすでに許可する。今回の不足はこの既存境界をApp callerへつなぐ点にあり、API認証失敗やSecure Cookie非対応の成功/失敗へ読み替えない。browser2failedを保持し、auth override・Cookie注入・route応答の成功偽装で迂回しない。

### 追加する編集scope（2paths）

| path | 最小変更 |
| --- | --- |
| `frontend/src/App.vue` | 既存resolveGameEntryReturnPathをimport。finishLoginの既存storage同期とprotectedReady確認の後、route.query.redirectを同helperで正規化してrouter.replaceする。認証失効watchは失効前に残るroute.fullPathを同helperへ渡した結果だけをlogin query.redirectへ保持する。認証済み保護画面のnavに既存named route team/gamesへの「チーム」「試合」2リンクを追加する |
| `frontend/src/router.spec.ts` | 既存App＋正規provider/router/clientの結合試験を拡張。許可戻り先、失効→再login、拒否入力、保護navの実RouterLink移動と未認証非表示を検査する |

戻り先のquery値はunknownのまま既存helperへ渡す。配列・欠落・外部URL・protocol-relative・query/hash付き値・不正UUID等を独自に文字列化/URLデコード/切詰めせず、既存helperの/team fallbackを採用する。route.fullPathにも同じ既存許可集合を適用する。新route・whitelist拡張・新権限・authStore/C1/C2/client/保存規則/記録入力の変更を行わない。認証が未確認なら既存finishLogin同様に移動しない。

navはroute.meta.requiresAuth === trueかつ既存protectedReadyの時だけ表示し、保護画面間を既存の認証guard経由で移動する。認証前の新データ通信を追加せず、未提供の作成/開始/保存/再開導線は設けない。利用者値をHTMLへ挿入しない。

### 同ステップの追加合格条件

1. /loginのredirect=/gamesとcanonical UUID detailは、実login ack後の実client session確認が完了してからその経路へ進み、各read hostのGETを開始する。認証確認前に保護host/GETを開始しない。/teamの既存動作は維持する。
2. /gamesまたは許可detailで失効すると、表示/cacheを既存経路で破棄してloginへ移り、正規化した同じpathnameを保持する。再login後はそのpathnameへ戻れる。fullPathにquery/hashがあれば既存helperと同じ/teamへ落とす。古い本文/tenant内容を代替表示しない。
3. 欠落・配列・外部URL・//・不正UUID・query/hash付き戻り先は/team。route名や任意URLを新たに解釈しない。認証失敗/未確認時は保護画面へ戻さない。
4. 認証済み/teamから「試合」をクリックして/gamesの準備中一覧へ到達し、「チーム」で/teamへ戻れる。未認証時は保護navを表示せず、read成功を入力/書込権へ昇格させない。
5. 追加/既存router.specと本単位の対象既存5spec、対象Prettier、frontend ESLint/vue-tsc/build、docs/plan同期/diffを確認する。旧browser2failedは別単位で是正source接合後に再実行し、本単体greenをbrowser成功として数えない。実browser再実行・DB環境・driverは引き続きrootの別承認単位の所有とする。

実装可能な追補の上限は上記2pathsと既存feature researchへの証跡追記。planの承認反映はrootが別途行う。親#175の正式追加敵対1回・正式基線/7.7/公開・新秘密/運用鍵の発行禁止・API/他worktree編集禁止を維持する。

### 上記最小追補の承認記録

2026-10-23T16:02:21.816805+00:00、Codex主担当/rootはPO委任4/5/6/8/10に基づき、上記未承認表記時のplan SHA4157f098d56a8cfeacfa89c91d7be2953d6aea6ef1eade424425575edc7dd62a（基線bb0973d141d0695c139f7ced690cdc1727b27947）の追加2paths/同ステップ是正を承認。独立非作者/root/o5_final_reviewの計画追補限定追加1回は可決0/0/0。前段の未承認表記は起案時履歴として残し、本記録を現在判断とする。新規意味/route/whitelist/auth state/実書込は追加しない。元計画レビュー1+今回限定1、元コードレビュー2回/P1採用と初回browser2failedを保持。実装後の限定追加コード確認1回を必要と判断し許可する。正式7.7/親175追加枠/実機/運用の未達を解除せず、本人署名や人間逐行確認は代記しない。
