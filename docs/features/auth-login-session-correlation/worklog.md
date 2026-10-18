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
