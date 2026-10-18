# 作業ログ・Claude向け申し送り

## 2026-10-18 承認反映と開始

- 本会話で04ecb061の相関追補が承認された。C1既済み承認は維持。
- 最新develop 5bb1ff89を確認。#150 HEAD146c774c、#151 HEADdb2bc2c7はopen、未統合。U-F13 HEAD04ecb061と結合HEAD e24c5c4eを保全。
- 本枝は最新develop起点。所有はCodex Dの非共有認証差分のみ。既存レビュー履歴は比較資料と各元枝に保全し、後発差分を再レビュー済みとしない。
- 通し試験は未実施。全品質gate/ステップ完了/本人逐行確認を先行記入しない。

## 製品候補の保全（未完了）

- 新しい相関意図モジュール、session/login/logout、store、非同期Cookie不確実通知を実装。backendはverify_tenant_idの結果だけからUUIDとCookie期限を返す。公開callerは承認済み1組だけ追加。
- 固有frontend79件、旧store/client互換110件、backend固有40件が成功。frontend全件は追加decoder試験前の候補で68ファイル1236成功。最終全件とは区別する。
- backend全件は専用使い捨てDBで実行中。新追補の実装第1周の実Claude/正規Codexレビューも進行中。後発session非401 Cookie可能性の反映と追加decoder試験は第1周入力後のため未レビュー。
- U-F3の必須UI差分は同Dの既存専用枝へ記録し、旧C1での単独UI検査と新相関clientとの結合検査を分ける。環境非対応は送信を止めて保存許可・対応ブラウザ/HTTPS・reloadを案内する。
- 以下のコミットは結合試験に用いる製品候補の保全であり、ステップ完了・全品質通過・本人確認の記録ではない。PR作成前に残るゲートを解消する。

## 実装第1周の採否・追随中

- 正規Codex: P0=0/P1=4/P2=1、tokens used 54,699。実Claude: P0=0/P1=3/P2=8。両経路とも第1周を消費。第2周は未実施。
- 非同期Cookie通知のawait漏れ、旧形式保存値残存、一時lock-busyで再loginを強制する回復不備、対象のない再確認ボタン、429表示、Cookie不受理の誤った入力拒否表示、固定503の例外範囲を採用修正中。
- lock-busyの全タブ拒否通知は6de49595へ具体案を固定し人間判断待ち。承認前に通知2キーを追加しない。
- 旧signIn公開面は製品呼出が0であり、直接のサーバー認証/認可を迂回できるものではない。ただし誤用の可能性と新clientの検証済み状態の条件について整理中。既受理やレビュー通過にはしない。
- backend全件は初期候補の途中から製品の例外境界修正が入ったため中断。完走として扱わず、修正後の全件を別実行する。修正後の固有backend41件とfrontend相関79件は成功。

## 2026-10-19 旧認証済み化の廃止・回復UI追随

- 製品の旧signInを削除。同期Web Lock内のadoptCorrelatedSessionだけが認証済みを作り、phase/意図ID/期待tenant/観測意図/表示名を検査する。writeAuthIntentにも同じ同期lockの検査を追加。失効操作は認証済み状態を作らない。
- 認証以外のAPI/選手管理の単体試験はauth.test-support.tsの明示fixtureへ移行。これは単体用同期fake lock・検証成功後の状態準備で、製品importや実ブラウザ受入に使わない。旧の任意文字列tenant fixtureはcanonical UUIDに揃えた。APIやDTOを追加したものではない。
- 旧store試験の保存4キー/任意signIn/保存失敗でもメモリ認証継続という期待値は廃止した契約のため置換。旧形式は全破棄、新意図のstrict decoder25件、lock外/異phase/異tenant拒否、同/別tenant通知、storage/lock拒否、旧版通知による安全側失効を固定。境界spec・選手管理specの拒否/遅延/cache/queue保存の検証は維持した。
- 一時lock-busyは意図を壊さず明示GETで回復し、未知tenantでは効かない再確認ボタンを出さない。別タブの同tenant再loginでも自動復帰はせず、明示GETだけを許す。未知tenantや異tenantへの自動切替は不可。
- Web Locks/localStorage/secure contextに加え、元候補が使用するcrypto.randomUUIDも利用可能であることを検査する。生成機能がなければ送信を拒否し対応ブラウザ/HTTPSへの回復案内を出す。実測済みブラウザはChromium149.0.7827.0だけで、他ブラウザの受入済みとはしない。
- 修正後固有112件、旧境界/consumer探索187件中5失敗は明示再確認時に新意図へ移る観測IDの更新不足で、lock内で新意図を観測してから採用する修正を反映し112件再成功。探索のfrontend全件は69ファイル1248件成功したが実行中に後発のlock invariant追随があるため最終固定HEADの全件とは扱わない。型/ESLint/Prettier/buildも成功。最終HEADで必要な再検査を残す。
- 実画面の部分受入は結合HEAD4656f868、対戦相手選手の追加/編集/reloadと同tenant2タブ・別tenant旧タブ非自動切替が成功。自チームreadは既存opponent専用契約のため未実装、確定認証のlogout UIは範囲外で切替前提に実APIを明示使用した。U-F13ログへ証跡を固定。
- 2キー拒否専用通知は引き続き未承認・未実装。第2周レビュー未実施・本人逐行確認未実施。全品質通過/ステップ完了を記録しない。

## 2026-10-19 Cookieを伴う旧headersと本文遅延の分離

- 通常のplayers/team-records系列とsessionもサーバーmiddlewareがCookieを更新する。共通clientの旧headers/結果不明の処理をC1の共通無効化関数へ接続。C2のtenant不一致拒否より先に無効化し、旧ユーザー/tenant/成功を採らない。
- 401はサーバーがCookieを更新しないため新世代を無効化しない。headersを旧世代で観測済みで本文だけ遅延した応答も、新世代へ採用せず、余計な新世代無効化はしない。別の旧Cookie応答は未確認中でも新しい意図IDへ進め、途中の再確認を古い意図で採用しない。同期lock外で意図を書かず、自動再送しない。
- 第1周後の反映としてfrontend固有/共通境界154件が成功。root全件は29,670成功/2 skip、終了0・専用cluster撤去。rootのscripts/tests/contractsの検査入力は不変。tenant-boundary bypassとfrozen-baselines実CLIも成功。
- backend全件は2,578成功/4 skip/1失敗/1 warningで完走した（50分48秒）。唯一の失敗はtest_roster_boundary.pyにも残っていたverifier caller exact-set。承認済みの同一1組api.routers.auth.loginだけを追加し、同じauthモジュールのlogout/read_sessionへ許可が広がらないalias scan負例2件を追加。発行入口のcaller集合は不変。当該試験ファイルは凍結資産からpinされていないことを機械確認した。
- 修正後のbackend caller/login関連68件は成功。全件再実行を別世代で行い、修正前の全件を成功扱いにしない。
- 結合固定HEAD24cdf797のfrontend全件は71ファイル1,349成功。production buildでstorage/lock/UUID非対応、認証拒否、通信断、session明示再確認、native lock busy回復の7項目が成功。検証環境・生成資格情報・Cookieを製品へ混ぜていない。
- 遅延Set-Cookieの実ブラウザ試験では旧login/sessionで実CookieがAへ戻ったことを実APIで確認し、B cache 3→0、旧画面非採用を確認。logoutは再確認401がidleになる正しい契約と試験driverのalert期待が不一致だったためdriverを修正中。native lock保持中の旧session Cookie通知はBが/teamに残る実失敗を再現した。6de49595の未承認条件であり、合格へ書き換えない。
- 追加判断680c2a27（2xx metadata不正時のCookie未確認化）を提示。現C2が既存B cacheを保持する契約からの例外なので承認前に実装しない。6deの通知2キーと区別し、既受理のDTO/意図/照合契約を一括で未了に戻さない。第2周レビュー・本人逐行確認・公開/マージは未実施。

## 固定後の検査と正本同期宣言

7e18a91aの単独frontend全件は69ファイル1,251成功（69.84秒）。型・ESLint・Prettier・production buildも成功。結合HEAD0cb5ab4bは71ファイル1,352成功（74.83秒）で、単独の結果へ読み替えない。U-F3単独ac748ed5と同じ製品のaa143553は69ファイル1,273成功（70.56秒）、型/lint/整形/buildも成功。

plan-docs同期検査で「影響する正本」節欠落が検出されたため、正本変更なしと同梱する正本外対象を明示した。検査器・凍結契約を変更する修正ではない。ハーネス運用評価台帳への追記なし（既存手順に従う局所追補であり、新しいハーネス制御は導入していない）。

## 実ブラウザ反例の固定と通常pushの範囲

結合0cb5ab4bのattempt12（Chromium149/production preview/実API/隔離DB、15.05秒）は旧login/logout/session/選手登録応答の4ケース成功。実ブラウザのfetchで実CookieのAへの巻戻りまたはlogout消去をサーバー確認し、B query cache3→0を確認した。lock保持中の旧sessionだけはBが/teamに残り失敗し、6de49595を必要とする実反例として固定する。最終summaryはexit1であり全成功ではない。attempt11は実行器のresponse.finished待機が全ケースtimeoutし、成功へ数えない。

同結合HEADのattempt13は正常8項目成功（8.48秒、Vite開発server）。実DB observerで対戦相手配下の選手「受入選手編集済」番号17の保存とB選手0を確認した。これを単独C1での画面受入とはしない。

U-F3 Draft #151は37c41110へ通常push、U-F13 Draft #154はe05303e2で作成した。両方の本人確認欄は未記入。C2 #150の製品HEAD146c774cは不変で、本文に新相関の承認済み/追加2案の未承認を区別した。C1本枝の通常pushは承認済み候補保全であり、全品質gate・ステップ完了・最終レビューの記録ではない。backend全件はcaller修正後の専用世代で実行中。

未承認2案は未実装のまま。既受理のDTO・相関・C1完了を一括待ちへ戻さず、この2件だけを人間判断に提示する。新相関第2周のレビュー基本枠は残してある。

## 限定2件の承認とbackend全件成功

山田正輝が6de49595/680c2a27を承認。失効専用・server検証必須・自動再送禁止を維持して着手する。caller修正後backend全件は2,581成功/4 skip/1 warning、2200.45秒、exit0。警告はfixture import済みのpytest assert rewriteであり、試験除外ではない。製品backendは7e18a91aから不変。

## 2026-10-19: 限定追補の固定・検査

- C1製品3ac39ce3と試験import追随a15128a1を固定。拒否通知はlock外で先に保存し、ackはstrict session/意図/世代/期待tenantの一致後だけ同期lock内。明示確認開始後の新通知、ack破損/削除/逆順、重複storage eventでは旧成功を採用しない。確認済み状態をstorageから復元しない。storage保存失敗はローカル拒否で、通知全タブ到達の証明には使わない。
- 固有130成功。frontend全69ファイル1,266成功（69.98秒）。全件実行中の最終変更は同じ2試験の動的importを静的importへ揃えるだけで、製品/specのassertは不変。ESLintが動的importを検出したため修正し、型/lint/整形/buildを再検査した。除外・timeout緩和なし。
- 専用結合8a0437c0はmetadata不正2xxで本文前拒否に加えて同じ共通失効へawaitし、自動再送しない。正しいmetadataの不正JSONを認証失効へ一律変換しない負例も追加。consumer158成功、frontend全71ファイル1,369成功（73.61秒）、production build成功。
- attempt14: production preview/実API/隔離DB/Chromium149で旧login/logout/session/選手登録とnative Web Lock保持中旧sessionの全5ケース成功（16.23秒）。旧Cookie A/消去をブラウザfetchからserver確認し、B cache3→0・旧採用拒否・明示再確認まで実測。以前のlock-busy失敗を期待値変更せず解消。
- attempt15: 新結合productionでstorage/lock/UUID拒否、認証拒否、通信断、session明示再確認、native lock-busy回復の7項目成功（7.83秒）。attempt16: 同productionで正常8項目成功（8.97秒、opponent配下、保存observer確認）。各自分のcluster/server cleanupを確認。自チーム受入は未了。
- 相関第2周は固定C1 a15128a1/結合8a0437c0の反映差分と影響を2正式経路へ投入済み。後発の資料/実測は査読済みと推定しない。第3周の実行指示はない。
- PR依存をpr-dependency-map.mdの一枚へ集約。C1→C2 #150（C1実統合後にmetadata680を正式追随）→U-F3 #151→U-F13 #154。専用結合結果を各PR単独のCI成功へ読み替えず、#154のLoginScreen欠落をコピーで埋めない。

## 第2周採否・残条件（2026-10-19）

正規Codex第2周P0=0/P1=4/P2=0（63,777tokens）、実Claude第2周P0=0/P1=2/P2=7で双方条件未了。全P1を採用し、0599d01c/0feaecab/0a057b97で現行結果不明・password遅着・session本文/DTO/lock失敗・quota時の意図fallback・reload試験を追随。storageイベント設定→削除の拒否と通知setItem1回も検査した。全採否・保留案はreview-round2.mdに固定。既定枠は各2/2消費、第3周なし。後発修正を再査読済みとせず本人対象へ残す。

108c7562は試験fixtureのthis型だけを修正（TS2683でbuild手前停止した検査を成功に数えない）。結合全件は1,381成功/1失敗で、LoginScreen試験の「確認済みB」fixtureが未ack通知をnullとして採用していた。912585d1で単体fixtureにも確認開始時のnoticeを渡し、関連114件が成功。製品の採用条件を緩めず、fixtureはproduction closure対象外。最終全件は別ログで再実行中。

実ブラウザattempt25/26/27/29は結合製品cdaf49fdで実測。正常production8項目成功（9.25秒）、metadata replayのlock-free/busy2項目成功（10.56秒）、環境/失敗7項目成功（7.48秒）、遅延Cookie5項目成功（17.08秒）。自分の隔離clusterを撤去済み。通常Cookie試験のreload前に未完了queryが中断されると保守側の未確認化が発生し、旧driverの自動GET待ちが止まった。通信完了を待って対象の旧sessionだけを遅延する前提へdriverを修正した。timeout緩和や自動再送ではない。

attempt20/21はbuild手前の型検査失敗を確認する前に旧bundleで起動したため、manifestを保全し最終HEAD受入へ数えない。attempt24もreload直前のquery中断による明示再確認待ちで未合格。attempt18はdriverのposts変数未定義で不合格。履歴を成功へ置換しない。

C1のbackend全2,581成功4skipとroot全29,670成功2skipは検査入力不変を維持し、既定品質を理由なく再実行しない。全件frontend・実ブラウザは単独/結合を区別。自チームIDの正式read契約は未承認・未実装。self-team-read-gap.mdの最小案を提示しており、自チーム受入を完了扱いにしない。

## レビュー提示候補の検査完了（全体完了ではない）

912585d1で単独frontend69ファイル1,278成功（69.99秒）。結合d1f467f5は71ファイル1,382成功（73.25秒）。型/ESLint/Prettier/build成功、production製品はcdaf49fd以降不変。初期TS2683と結合1件失敗を解消後の固定再検査であり、失敗ログは残す。本人確認対象をpr-preparation.mdへ固定。

C1単独候補を人間へ提示するためin-reviewへ移す。未消化の自チームread契約/受入と後発差分の本人確認を保持し、ステップ全体/TSK全体完了は記入しない。ハーネス運用評価台帳への追記なし（既存の局所実装/レビュー/専用検証のみで、新しいハーネス制御を作らない）。
