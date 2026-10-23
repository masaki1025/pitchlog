---
feature: mvp-preparing-read-ui
status: active
承認: 済（PO委任によるCodex判断・隔離read UI候補）
重さ分類: コア領域
worktree: ../../..
branch: feature/mvp-preparing-read-ui
created: 2026-10-24
計画レビュー周回: 1
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
