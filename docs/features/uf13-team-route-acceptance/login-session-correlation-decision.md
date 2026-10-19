# login/session相関の局所判断候補（未承認・未実装）

## 既済み事項と新たな不足

実基線`156dd139a893845428a1ecab69632143f7694e0b`。C1/#147、C2の承認済み7経路、U-F3の既定レビューを再承認待ちへ戻さない。旧frontendだけの無効化案の否決も保持し、その案を製品へ採用しない。

`require_tenant_access`はスライディング期限に合わせ同じ提示値をSet-Cookieする。旧Aのsession/保護応答は、B loginのCookie発行後・B session確認前にCookie Aを再適用し得る。現`LoginResponse`は`status`だけで、後続sessionが認証したtenantと、直前loginが認証したtenantの相関を検証できない。C2はB確定後の7経路をoperation前に閉じるが、この前段を直した証跡にはならない。これは未統合550/D4/544/545の待ちではなく、今回の実認証経路に直接関係する契約差分である。

## 推奨する具体差分（承認前は実装しない）

1. `LoginResponse`へcanonical UUIDの`tenant_id`を追加する。サーバーはloginで発行した提示値を既存`verify_tenant_id(value, active_presentation, app_engine)`へ渡し、署名・既存DB照合を通ったIDだけを返す。入力team_name・表示名・localStorageを認可キーにしない。追加照合はCookieをHTTPへ付ける前に、既存`get_login_connection()`を使う`run_in_threadpool`で行う。None/DB照合失敗は値を含まない固定503とし、資格情報不一致の401とは区別して結果未確認を表示する。既存の署名器・app role・固定認証関数を再利用し、DB関数・列・権限を追加しない。追加DB照合はlogin成功候補につき1回で、独自TTLを計算せず検証戻りの期限へCookieを追随させる。
2. C1 clientはlogin 2xxで`{status:'authenticated',tenant_id:<canonical UUID>}`の2項目だけを厳密検証する。これだけでは認証済みにせず、次のsession 2xxの厳密DTOとtenant_idが一致し、世代が不変な場合だけC1の正規signInを呼ぶ。欠落・不正・不一致はverification-unknown、cache破棄、明示再確認/再ログイン/ログアウトのみ。資格情報・mutationを自動再送しない。team_nameは照合しない。
3. reload・別タブへ期待identityと未確認の寿命を渡すため、非秘密の認証意図候補`bb.auth.intent`を固定する。候補はversion1、canonical UUIDの`intentId`、phase=`pending|expected|verification-required|signed-out`、`tenantId`（pending/signed-outはnull、expectedはcanonical UUID、verification-requiredはcanonical UUIDまたはnull）。保存値は**制約候補**であり、認証の証拠ではない。expected Bを保存してもsession未検証では認証済みへ進まない。認証意図の前後不一致は旧応答を棄却する。Cookie適用より先にstorageイベントが届くとは仮定せず、各採用直前に実storageも再照合する。意図更新・条件付き書込み・sessionの認証採用は、同一originのWeb Locks API exclusive lock `pitchlog.auth.intent`（`mode: exclusive, ifAvailable: true`）内で、同期の読取→比較→保存→再読取→memory採用として直列化する。lock内でfetch・本文読取・DB・他のlock待ちは行わない。lockが取れなければ待機・自動再試行せず、lock不在/取得失敗/利用者cancel/保存失敗では通信・採用を開始せず未確認に閉じ、代替として独自mutexやlocalStorageだけのCASを作らない。session採用に使う期待IDは要求開始snapshotと採用直前の両方が一致し、現行login操作ではそのlogin成功DTOのIDとも一致しなければならない。
4. login POST前にpending意図を保存し、旧store/cacheを破棄してtenant通信を止める。これはC1の「確定したlogin拒否では既存store/cacheを保持」からの**局所的な変更**である。拒否時にも旧cacheを自動復元せず、固定拒否表示と未検証状態を維持する。成功ackが失われたpendingには期待tenantを推測で補わず、再ログインかlogoutを明示操作で選ぶ。expected/verification-requiredの明示session確認は、その期待IDとサーバーDTOが一致した場合だけ回復する。signed-outでは起動時自動session確認で復帰せず、新たな明示loginを要求する。
5. **意図なし・削除・破損を初回の特例として認証しない**。区別できないため、いずれも未確認として明示login/logoutへ進め、sessionの自動GET/再確認GETを開始しない。期待IDのあるexpectedだけはreload時も自動session確認を1回許すが、期待ID・意図識別とserver DTOの一致前は保護画面/APIを開始しない。verification-requiredは明示GETだけ、期待IDなしは再login/logoutだけを許す。意図keyを製品から削除せず、終了はsigned-outのtombstoneを残す。storage/Web Locksが使えない場合も未確認へ閉じる。既存Cookieだけでの自動復帰廃止、旧版からの初回再login、従来best-effort storageより低い可用性を明示した人間判断へ出す。

## 所有と差分候補

Codex DがC1の局所追補として所有する。C2の既存client編集完了と固定HEADを確認してから引き継ぎ、C2製品に無断で混ぜない。

- backend: `api/routers/auth.py`、`api/schemas/auth.py`、対応するlogin/session・schema・実DB認証試験、`tests/test_authz_app_layer_surface.py`のcaller完全一致検査。
- frontend: 正規`api/auth.ts`、共通`api/client.ts`の採用前/通信前照合、`stores/authStore.ts`、固有spec。`LoginScreen.vue`/specの状態表示追随（拒否後も未確認、再login/logout、期待IDのないpendingでは再確認GETを送らない、503は結果未確認）は必須成果物としてU-F3所有と順次調整する。router/AppはU-F13所有。
- 既存のHTTP operation_id・endpoint・認可ロール・app grant・DB schema・C2の7経路/DTOは不変。正式な認可/凍結資産の差分が実検査で判明した場合は実前後値を別ゲートへ出す。いま資産受理済みとは記録しない。
- 新規の全体計画・新E2E基盤・ブラウザ間同期の自作ハーネスは作らない。実装前にC1追補の計画レビューと人間承認、必要な個別ゲートを通す。

## 必須の検証と残る判断

- A session/7経路/対象外の既存Cookie更新応答をB login前、login成功後session前、B session確定後へ遅延。Bのlogin ackとAのsession DTOの組はauthenticatedにならず、本文・cache・noticeへ旧identityを新しいloginの成功として採用しない。C2の7経路ではサーバーexpected-tenant照合前にoperationを開始しない。
- 複数世代、旧login/logout、旧403/405/401、headers後だけの本文遅延、network/abort、DTO不正、明示再確認と競合を維持。同一要求の通知/破棄重複を防ぐ。
- 2実ブラウザタブ、reload、pending中のタブ破棄、storage拒否/破損/意図変更、password/logout後を確認。storageだけで認証せず、session 401と結果未確認を区別する。
- 実DBで新たなlogin応答のtenant出所、既存認可境界不変、期限追随、照合失敗ではHTTP成功/Cookie採用なしを確認。login本体のDB発行は既にcommitし得るため、新追加照合との一体transactionや全取消を主張しない。
- 前回案のJS検出だけで完全解消したとは扱わない。期待identity保存の競合条件と初回意図なしの例外は、この具体候補のレビュー対象であり、未検証のまま受理しない。

必要な人間判断は、新しいlogin DTO、IDの出所と固定503、認証意図の保存/直列化契約、login拒否時も旧cacheを復元しない変更、初回再login・storage/Web Locks失敗時の可用性低下、および今回の保証をlogin/session採用とC2の7経路へ限定することに限る。これらはU-F13の既承認router/App登録やC2/U-F3の既存候補を一括で再審査する理由にしない。


## 第2周指摘への差分（P0修正とP1/P2の採用。P1/P2は未再レビュー）

| 現phase/事象 | 次phase・意図更新 | 自動/明示session GET | 表示・通信 |
| --- | --- | --- | --- |
| absent/破損/削除/読取不能 | 未確認。可能ならverification-required(null)を保存 | いずれも不可 | 再login/logout。旧Cookieだけで復帰しない |
| 任意/明示login | lock内で新intentIdのpending(null)を保存・再読取成功した場合だけPOST | 不可 | 送信前に旧cache破棄、tenant通信拒否。保存/lock失敗はPOST 0件 |
| pending/login 2xx+厳密DTO | 自身のpendingが現行の場合だけ新intentIdのexpected(B) | 新expectedを使い1回GET | まだ認証済みではない |
| pending/loginの確定拒否 | 新intentIdのverification-required(null) | 不可 | 固定拒否、旧cacheは復元せず再login/logout |
| pending/login結果未確認 | 新intentIdのverification-required(null) | 不可 | 結果未確認、資格情報再送0、再login/logout |
| expected(B)/reload | expected(B)をsnapshotとして維持 | 自動1回。並行呼出しはC1で集約 | session採用まで保護画面/API 0 |
| expected(B)/session 2xx+DTO B+識別不変 | lock内で再照合、新intentIdのexpected(B)へ保存してから正規signIn | 検証後の自動追加GETなし | 認証済み、C2の7経路だけへ接続 |
| expected(B)/sessionの非401失敗・DTO不正・ID不一致 | 新intentIdのverification-required(B) | 自動不可、明示GETのみ | 本文/cache/成功不採用 |
| verification-required(B)/明示GET | Bと現意図をsnapshotにし、成功一致時だけexpected(B) | 明示1回のみ | 不一致なら未確認、再login/logoutも選べる |
| expected/verification-required(B)/session401 | 新intentIdのsigned-out(null) | 不可 | サーバー未認証、cache破棄、明示login |
| 任意/明示logout | 先にlock内で新intentIdのsigned-out(null)、cache破棄してPOST | 不可 | 結果未確認をlogout成功と表示しない。再送0 |
| logout成功/失敗 | signed-out維持、古い操作なら現在意図を置換しない | 不可 | 成功のみ完了、失敗は結果未確認と再loginの案内 |
| password変更通知・成功 | 新intentIdのsigned-out(null) | 不可 | 新規password画面は追加せず、既存正規操作の完了通知へ最小追随 |
| 他タブの意図変更 | 旧observer/結果を破棄しmemory/cacheを未確認化。別意図の期待IDを旧要求へ移さない | expectedなら次の正規起動/guardでのみ検証。required/pending/signed-outは不可 | 自動mutationなし |
| 旧Cookie変更可能応答の観測 | lock内で現意図を再読し、新intentIdのverification-required(現期待IDまたはnull)。旧結果のIDを使わない | 期待IDありでも明示のみ | 同一要求の通知は1回。別旧要求は別の可能性として扱う |

意図更新は全て同じlockを使い、古いread結果による後続意図の上書きをしない。採用前のHTTP/本文読取はlockの外、比較・保存・memory採用はlockの内。初回例外削除と7経路への保証限定、直列化をP0是正の対象にする。遷移表・caller試験・UI・503・配布順のP1/P2追随は未再レビューとして本人確認へ残す。

**保証範囲**: ブラウザによる古いCookieの適用やCookie送出自体を止める保証ではない。login/sessionで誤ったtenantを新loginの成功として採用せず、C2の7経路の業務前照合を維持する。既存の対象外DELETE・lineup・password等を保護済みと主張せず、新しいUIからも呼ばない。logoutはその時点のCookieを無効化/除去し、前のB token全てを失効したとは表示しない。tenant単位の相関であり、同tenantの別tokenの識別は保証しない。

**検証手段**: 既存VitestでCookie適用順・意図変更順を制御し、実ブラウザでは既存Chromium/Playwrightの実行環境と既存DB fixtureだけを使う一時的な受入操作記録を採る。2タブ、reload、pendingタブ終了、storage/lock拒否を別の証跡欄に残す。新しい常設E2E/ハーネスを作らず、Vitestだけで実ブラウザCookie挙動を証明しない。実ブラウザを動かせない場合は未実施とし受入完了へ進まない。

**配布境界**: login DTOの厳密1項目→2項目の変更は後方互換ではない。backend/frontendと必須U-F3状態表示を同じC1追補ステップの候補として検査し、部分配布で旧clientが失敗する期間を成功扱いにしない。承認・本人確認・配布判断前の公開はしない。

**直列化の根拠**: [Web Locks仕様](https://w3c.github.io/web-locks/)は同一storage bucketの複数contextで同名exclusive lockを共有する。これはCookie通信を排他する機能ではなく、今回の非秘密な認証意図の条件付き更新と採用を揃えるためだけに使う。非対応ブラウザへの可用性差分は未承認である。


### 事前の認可面照合

現行`route-registry.json`のloginは`ROUTE:AUTH:login:create` / `authentication_entry`、HTTP matrixは`HTTP:ROUTE:AUTH:login:create` / conditionalであり、今回の候補でroute ID・認可分類・DB呼出しregistry行は増えない。両資産のinput manifestはrequirement claims/lockを参照し、この候補ではその正本/claimsを変更しない。backend認可面の公開caller完全一致試験には、次の**1組だけ**の追加が必要になる：`api.routers.auth.login` → `authz.verified_tenant.verify_tenant_id`。DB endpointの唯一の実装は従来の`authz.verified_tenant.verify_tenant_id` → `authn.verify_token`を保持する。PUBLIC/app grant、TokenPresentationの公開面、任意UUID/SQL入口は広げない。新たなcaller許可自体は個別人間判断対象であり、現時点で試験や資産に反映しない。最終のstatic/実DB/corpus照合で差分が出た場合は、当該実値だけ別途正式受理へ出す。


## 実装承認を求める最小単位（新しいC1局所追補1ステップ）

C1本体の完了・2ステップ履歴は変更しない。上記契約を採用する場合、専用`feature/auth-login-session-correlation` worktreeの局所追補1ステップとして、backend DTO/HTTP/caller検査とfrontend auth/client/store/必須LoginScreen状態追随を同時に実装・試験する。C2・U-F3・U-F13の既存PR境界を維持し、認証契約の変更をC2の業務metadata PRへ混ぜないため、追加の局所PR1本を人間判断へ出す。承認後は承認本文と本資料を根拠に`docs/features/auth-login-session-correlation/plan.md`へ同じ1ステップを記録し、実装前ゲートを省略しない。

| # | 成果物 | 合格条件 |
| --- | --- | --- |
| 1 | 本候補のlogin DTO相関・意図状態と排他・C1/U-F3接合・固有試験を一体で実装 | 上の遷移表・拒否・旧応答/別タブ/reload・実DB出所・失敗境界を試験。root/backend/frontend全件、型/lint/build、既定2経路レビューと採否、必要な正式資産の実値照合を完了し、本人逐行確認資料へ提示する。公開・マージを代行しない |

このステップ表の記録は第3周P0限定査読後の人間確認対象であり、新たな自動全文レビューを追加しない。追加サービス・新しい認証DB/ACL・新E2E基盤は不要。新しいPR1本の既定レビューと全件検査の工数が増える。別タブ保証にWeb Locks非対応時の可用性低下と、既存Cookieだけでの初回復帰廃止を含むため、人間承認前に着手しない。
