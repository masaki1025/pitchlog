---
feature: uf13-postmerge-acceptance-followup
status: active
承認: 済(2026-10-20・山田正輝)
重さ分類: コア領域
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-uf13-postmerge-acceptance-followup
notion: https://app.notion.com/p/3f493b75e68781628422c331bfebc350
branch: feature/uf13-postmerge-acceptance-followup
created: 2026-10-19
計画レビュー周回: 2
確定ゲート周回: 1
実行方式: 通常
反映周コミット: 適用
---

# 最小追補計画: 自チームreadと既存選手管理の実API受入

## 1. 背景・目的

[TSK-528](https://app.notion.com/p/3f493b75e68781628422c331bfebc350)の保護/teamに、[TSK-520](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2)の既存選手管理を自チームでも利用できる最小readを加える。[要件FR-033/FR-034、NFR-005/014/019](../../requirements/requirements-pitchlog-2026-07-22.md)に対応する。カード全体の完了や新カード起票は対象外。

実基線はorigin/develop `ba339cf8bdaac4761b8cf437abaf21763617d064`。#157/#150/#151/#154は統合済み。正常系8項目はこの実統合HEADで成功し、ユーザーが確認済み機能として受領した。故障系はその実行で再試験したとは扱わない。

自チームreadの採用方針は2026-10-19のユーザー指示で確定。既存の[最小契約資料](../uf13-team-route-acceptance/self-team-read-addendum-candidate.md)を編集元とし、設計書を新たに複製しない。本計画§7の3ステップ・合格条件・最終指摘反映と実番号取得用Draft先行条件は2026-10-20に山田正輝が承認済み。第2周最終反映は独立再レビュー未実施であることを保持し、その範囲を人間が承認した。製品変更を開始できるが、正式7.7・担当受理・本人逐行確認は未実施。

## 2. スコープ

### やること

- 引数なし`SelfTeamRecordReadToken`、既存capabilityの独立OperationRegistration、GET /team-records/self。業務引数としてtenant/id/kind/limit等を端末から受け取らない。
- 認証済みTenantContextのbindによるself固定・hidden_at NULL・SQL LIMIT 1。TeamRecordRead DTOと共通client/C2 metadataを再利用する。
- 既存TeamScreenへ自チーム取得を接続し、選手一覧・追加・通常編集・再読込を通す。共有Pinia/QueryClient、既存ページングと部品を再利用する。
- 必要なrepository契約・base allowlistとその実ファイルに対応する最小凍結差分。authzの既存read claimを再利用し、不変の資産は変更しない。
- 対戦相手経路の回帰とself専用の境界試験、実画面/API/隔離DBの受入。既存ハーネスだけを使用する。

### やらないこと

新権限/capability/DB role、grant/RLS変更、migration/列/索引追加、自チーム作成/修復/名称変更/削除、session DTO拡張、既存opponent tokenの対象拡大、全15経路、在籍変更/削除/試合作成・移行は対象外。製品上のlogout UIも追加しない。本人確認・公開・マージは代行しない。

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| 要件・design/data-model・ADR・development・ops | 反映なし。selfを既存権限で読む製品入口の追加であり、認可原則・DB構造・要件は変更しない | この判定をAPI/認可計画レビューで確認。新たな規範・構造変更が必要と判明した場合だけ、その具体差分を7.6/7.3へ提示してから変更する |

### 正本体系外だが同一PRで更新するもの

- `backend/src/pitchlog/repositories/roster.py`、`api/routers/team_records.py`、`api/tenant_access.py`、`repositories/repository_contract.py`（新token/登録が既存の公開登録組立に必要な場合のみ）。既存OperationRegistry/transaction/bindingのロジックは変更しない。
- `frontend/src/api/roster.ts`、`lib/rosterQueryKeys.ts`、`screens/TeamScreen.vue`と各spec。共通client/auth/storeをコピー・改変しない。
- backendの既存roster repository/boundary、HTTP/metadata、隔離DB試験。rootのcaller/HTTP exact-set・契約検査は、新入口/型への必要な期待値追加だけを行い既存拒否例を残す。
- `contracts/tenant_boundary/repository-contract.json`、`base-allowlist.json`、対応する基準snapshot/受理記録。必要な公開型/登録builder差分とsource_digestだけ。7.7前後値は最終実基線から機械導出する。
- 必要性が確定した場合だけ`contracts/authz/route-registry.json`、`http-route-matrix.json`、各lock、`oracle-seal.lock.json`、`oracle-meaning-change-approvals.json`と対応snapshot/受理記録。既存CAP:team_records:read/ROUTE:RECORD:team_records:readを再利用し、新route_id/claimは追加しない。充足不能な具体的事実が後で判明した場合だけ、その差分を別ゲートへ提示する。
- 本計画、既存self候補資料、既存PR依存表/U-F13計画、同一のコミット済み作業ログ。新カード・新しい作業タブを作らない。台帳への追記は/pr前に既定の基準で判断する。

## 4. 実装方針

### 4.1 所有・開始条件

T（tenant-isolation）と、既存TeamScreen/query keyのD（data-migration）に該当するコア領域。想定する製品パスは既に機械登録されており、core3ファイルの先行登録は不要。

- 採用方針の再照会はしない。最小計画/API・認可契約の敵対レビューを行い、採否と最終差分をまとめて人間承認へ出す。承認後は表の3ステップを順に連続実行する許可として記録する。
- 非共有製品ファイルはCodex Dの担当候補。#152とのパス別調整依頼は[PRコメント](https://github.com/masaki1025/pitchlog/pull/152#issuecomment-6264299257)。返信なしを受理としない。
- #152が変更中のbase-allowlist、authz registry/matrix/lock/sealは#152先行→D追随を提案し、残編集・解除時点をパスごとに確定する。repository-contract JSONは現#152差分にはないが、同PRのrepository_contract.py等と消費関係があるため明示照合する。
- 共有正式資産の編集/受理値は、確定した所有・統合順と実developから導出する。他担当の未統合枝を基線へmergeしない。合意待ちの共有パス以外の承認済み作業は止めない。

### 4.2 採用済みAPI・認可契約の具体化

契約の詳細編集元は[既存資料§2–4](../uf13-team-route-acceptance/self-team-read-addendum-candidate.md)。本計画では実装・試験の境界を固定する。

- 新tokenはtenant/kind/limitを可変にしない。prepareはkind=self、limit=1。既存実行器によるcontextのtenant bindを保持し、既存CAP:team_records:readのSELECT内だけで実行する。
- HTTP handler名は`read_self_team_record`、operation_idは`roster_self_team_read`。成功200、既存TeamRecordReadの4項目だけ。kind=self/hidden_at=NULLを検査し、想定外のDTO/行形を成功へ写さない。
- 認証→C2 expected/challengeの照合→業務operationの順。Cookie A/expected B、metadata欠落/不正は既存の汎用404でself SQL 0回。未認証は既存401。2xxだけ既存ack/echo、対象応答no-store。URL/query/storageのtenant値を認可へ使わない。
- 0行は汎用404、1行はDTO検査後200。想定外の複数行がmaterialized結果へ注入された場合は汎用5xxで拒否し、先頭行を採用しない。内容/件数/他tenant情報を返さず、成功ackを付けない。
- 実DBの複数selfは既存tenant単位のpartial unique indexにより拒否されることを隔離DBで確認する。採用済みSQL LIMIT 1は制約を壊したDB内の複数件を検出する仕組みではない。unique indexを製品・共有DBで外す、LIMIT 2や全件集計へ変更することは本計画に含めない。DB制約の拒否と異常結果注入の拒否を別の証跡として残す。
- `/team-records/self`と既存UUID経路の識別、OpenAPI、認証/HTTP exact-set、caller閉鎖を検査し、既存経路を期待値から削除しない。未知の端末入力をtenant選択に使わない。

### 4.3 UI・旧応答の境界

self query keyは検証済みtenant+authEpochを含め、opponentページ群と分離する。未確認ではquery/mutationを開始しない。新しいself取得入口では共通clientの返却をunknownとして受け、既存TeamRecordReadの4項目（UUIDのid、kind=self、stringのname、hidden_at=null。欠落/余剰キーなし）を実行時検査してからqueryへ返す。共通apiRequestの型キャストだけをDTO検証としない。roster.tsへこの入口の検査を集約し、共通clientをコピー/改変しない。不正な200本文はqueryを失敗とし、その値を選択肢/cache/players要求へ渡さない。metadata不正の認証/cache無効化は既存C2に任せ、新たな認証状態遷移は追加しない。self queryはretry=false、retryOnMount=false、refetchOnMount=false、refetchOnReconnect=false、refetchOnWindowFocus=false、refetchInterval=falseとし、失敗後の再確認は利用者の明示操作だけにする。失敗状態も同じ認証世代では共有QueryClient内に保持し、self queryだけgcTime=InfinityとしてGC後の再マウントで暗黙に再送しない。認証世代切替時は既存cache clearによりこの失敗状態も破棄する。新たな検証済み認証世代の初回GETは新しい読取りとして区別する。storageや新しい認証状態は追加しない。

self成功時は初期自動選択するが、利用者が明示選択済みのopponentを後着selfで上書きしない。selfのpending/0件/通信失敗を独立表示し、opponent成功をself成功に見せない。

切替時に一覧/選択/cacheを破棄する既存境界を維持し、旧self query・遅延mutationは新世代へ適用しない。clientの世代/metadata拒否を保持する。新しい自動再送は追加せず、結果未確認の操作を成功と表示しない。既存選手登録/編集とopponentページングの処理を再利用する。

### 4.4 PR・7.7の順序（最小1PR）

1. 計画の最終承認後、非共有の候補実装/試験を進め、共有パスは担当受理された順で追随する。
2. 実装ステップごとにコミットし、後続修正の範囲/レビュー採否を固定する。共有凍結候補は7.7未受理であることを明記して既存履歴を保持する。受理値を変える基線追随があれば再導出する。
3. 通常pushとDraft PR1本の作成は、今回の最終計画承認後の指示範囲。正式7.7前のDraftが必要なら本追補に限るDraft先行条件として最終承認対象へ含める。plan active、未受理の検査を合格としない、実承認者/日付は先行入力しない、人間チェック未記入、Draft解除/公開/マージなしを維持する。
4. 実PR番号/最終候補からtenant-boundary・authzの必要な完全前後値/blob/snapshot/digest/受理記録案をまとめて提示する。既存C1限定例外や受理を本PRへ流用しない。正式受理の反映・再封印は正式回答後だけ。
5. 結果を単独HEAD/候補/実統合後で区別し、最終時点では正式受理と本人確認だけを残す。機械検査の未通過理由は列挙し、検査器や必須チェックを緩和しない。

### 実装ステップ（コミット単位）

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | backend self token/固定登録/HTTP/C2適用と固有試験、必要な共有資産の候補差分 | 0/1/異常複数、tenant/未認証/metadata前照合、SQL形/固定bind/既存opponent拒否が成功。共有候補は所有受理済み範囲だけとし、未受理7.7は統合前ゲートへ明示する |
| 2 | 正規roster client/query key/既存TeamScreenへのself接続と固有spec | selfの4項目実行時検査と不正200の非採用、失敗後の再接続/再マウント等で明示操作までGET増加0、取得/選択/欠損表示、認証切替/旧query・mutation/再送なし、opponentページング回帰、全frontend/type/lint/整形/build成功 |
| 3 | 実画面/API/隔離DB受入、必要な全品質検査・既定レビュー/是正、PR資料固定 | 自チーム一覧/登録/編集/reload保存、越境/遅延/未確認/通信失敗、opponent回帰の実証。root/backend/frontend全件と品質ゲートの結果・HEADを固定。正式受理/本人確認の未了を隠さず、通常push/Draftと最終資料へ進む |

表は実装候補の合格条件。TSK-528全体の完了を意味しない。7.7反映/再封印の確定ゲート周コミットはステップ記法を付けず既定手順に従う。追加修正も承認済み範囲・既定レビュー回数を保持する。

## 5. DoD（この追補の部分受入）

- [ ] 認証済みtenantのselfだけを既存権限で取得し、端末指定tenantやopponentへ代替しない。
- [ ] 0件/1件、DB重複拒否/異常結果複数の拒否、未認証/別tenant/metadata不正を証明する。
- [ ] 自チームを画面で明示確認し、既存選手一覧・登録・通常編集・reload保存を実API/隔離DBで確認する。
- [ ] 認証切替/遅延応答/遅延mutation/未確認/通信失敗を検証し、旧cache採用/自動再送/偽成功を起こさない。
- [ ] 対戦相手経路の回帰がない。旧候補の正常系8項目、ba339cf8での8項目、新候補でのself受入を別記録にする。
- [ ] 必要な全検査、規約どおりのレビューと採否、最終単独HEADのCIを提示する。環境失敗/中断を成功に読み替えない。
- [ ] 必要な7.7完全値/記録案と最終本人確認対象を一括提示する。受理・本人確認前にはそのチェックを付けず、全必須チェック成功/追補統合完了とは記録しない。

## 6. テスト計画

- backend単体: token引数不可、既存opponent固定、tenant WHERE/kind/self/hidden/limit1、既存DTO/行形のstrict確認、0/1/複数注入、metadataと認証の優先順位、非2xxに成功ackなし。
- 隔離PostgreSQL: 既存fixtureでA/Bのself/opponent、selfなしtenant、同tenant二重self INSERT拒否、文脈なし/他tenant SELECT拒否。共有DB・制約を変更しない。異常materialized行はmock/fault injectionと明記する。
- frontend Vitest: self応答の不正UUID/kind=opponent/hidden非null/name非string/欠落/余剰キーを200で返して拒否し、query成功/選択肢/cacheへの採用とplayers通信を起こさないことを確認する。共通clientを通した1回送信/自動retry0を確認する。不正200または通信失敗後にonline切替・window focus・unmount/remount・既定GC期限を超える時間進行を与え、同じ認証世代では明示再確認までGETが増えないこと、明示操作で1回だけ取得することを確認する。認証切替のcache clear後は旧失敗状態を持ち越さず、新しい検証済み世代の初回取得と区別する。self取得pending/0/失敗/成功、初期選択と明示opponent選択、ページング/登録/通常編集・再取得、遅延self queryと遅延mutationの世代切替、未確認中通信0、自動再送0。
- 実画面/API/隔離DB: production preview/既存Chromium手順、self名/kindを確認→一覧→追加→編集→reload→DB observer確認。別tenant・2タブ/遅延/通信断の既存手順を必要な影響範囲で再利用し、opponent経路も別に回帰確認する。資格情報/Cookie値を証跡へ残さず自分の環境だけ撤去する。
- 全件品質: root Ruff/ty/pytest、backend Ruff format/check/ty/pytestと既存migration/DB契約検査、frontend Prettier/ESLint/vue-tsc/Vitest/build/depcruise/閉域。frozen/tenant-boundary/authz/caller/HTTP/coreの既存検査。試験除外・timeout緩和・検出漏れを許可しない。
- レビュー: 本計画とAPI/認可意味契約は6.1/6.3の敵対レビュー（原則2回、P0例外のみ）。実装は別枠の反対側/コア敵対レビューを既定回数で実施。既存PRの枠/可決/本人確認は流用しない。


## 7. 実装前の最終承認対象（採用済み方針の再照会ではない）

1. **本計画の3ステップ・合格条件とレビュー反映差分**。0件404/1件200/想定外materialized複数5xx、実DB一意制約の拒否との分担、self応答4項目の実行時検証、失敗後の暗黙再取得を防ぐself query限定設定/試験を含む。採用済みtoken/endpoint/既存権限/DTO/client/tenant前照合の方針は再承認待ちへ戻さない。
2. **本追補だけのDraft先行条件**。正式7.7の実PR番号取得が必要な場合、承認後に通常push・Draft PR1本を作成し、plan active・7.7未受理・未通過検査・本人確認未実施を明記する。受理値/承認者/日付/チェックの先行代記、Draft解除/公開/マージはしない。正式受理は候補固定後の完全値で別途提示する。既存C1限定例外を継承した扱いにはしない。

承認後は許可済みの実装/試験/既定レビュー/是正/通常push/Draft準備を連続実行する。共有パスの所有受理は別の開始条件であり、無回答を所有移管としない。非共有範囲は合意待ちへ一括で戻さない。新権限/意味変更が必要と判明した場合だけ、その具体差分をまとめて提示する。

**計画レビュー履歴**: 第1周f7608ad6はP0=0/P1=2/P2=0を全採用。第2周d7a16feaはP0=0/P1=1/P2=0（失敗後の自動再取得試験不足）を採用反映。基本2周を使用し、第2周最終反映は未再レビューである。独立可決済み/製品実装済み/人間承認済みとは記録しない。6.1/6.3に従い採否・最終差分を人間承認へ提示し、追加の第3周は行わない。


## 2026-10-20: 承認と最新基線・実際の編集保留

ユーザーが§7の2項目を承認（山田正輝、2026-10-20）。既定2周の範囲はf7608ad6全文→d7a16fea反映差分で、最終P1反映（失敗後の再接続/再マウント/focus/GCによる暗黙再取得を防ぐself query設定・試験）は未再レビューのまま承認された。これを製品レビューや本人逐行確認実施済みへ流用しない。

最新origin/developは#158統合7c1afebab31facc71e8cfc2731da1a9fa392de4e。専用worktreeへ通常merge済み。差分はcore3とTSK-550固有計画/記録であり、自チームAPI/画面の契約前提は不変。coreの先行履歴をそのまま保持する。未統合#152等は取り込まない。

実際に重なるrepository_contract.py/jsonは#156（一部pyは#152も）、base-allowlistは#156/#161/#152、必要となるauthz共有資産は#152/#156/#161/#162の対象。共有パスの編集と受理値更新だけを保留し、roster/API/画面/固有試験は本タブで進める。#152先行は提案であって確定順序ではない。#159/#163/その他PRは、この製品経路の直接停止条件にしない。


### 実装候補c2301827の状況（2026-10-20）

最新実develop8e4698f6（#163）を通常merge済み。非共有backend/画面/固有試験と自チーム・opponentの実画面14項目は成功した。core登録は既存検出16パスで足り、新宣言/JSON登録は不要。base-allowlistの許可symbolとauthz資産本体は既存契約で不変。製品登録はrepository_contract.py公開token一覧とtenant-boundary/repository-contract.jsonの2パスが保留（#156/#152の所有返信待ち、未編集）。ただし正式7.7ではhistory_authority=trueのcontracts/tenant_boundary/base-allowlist.jsonへの単一履歴追記が必要で、この履歴編集も#156/#152/#161の所有・順序照合対象に残す。許可symbol追加不要と履歴更新不要を混同しない。7.7完全値はその順序と実基線確定後に機械導出する。新revisionや正式承認者/承認日を先行記入しない。

実装レビューは第1周全差分→第2周a60fdf5dの反映差分/影響箇所を敵対・反対側とも使用し、新規P0/P1/P2=0。計画レビューの最終P1反映の承認済み履歴は保持する。全品質/正式7.7/本人確認/単独CIは別条件であり、現時点のplan active・Draft先行は§7の承認例外による。全体/カード完了は記録しない。詳細と未再レビューの実行証跡はworklogを正とする。

### 2026-10-21 PO指定による共有3パスの限定先行

候補 `0ba9fd36b6ef014446a888eb82aaa8bc127a79eb`、実develop `8e4698f6dc254439b7d5e0c273cc2aef70cda657` を固定。POはD先行を指定した。対象は `backend/src/pitchlog/repositories/repository_contract.py`、`contracts/tenant_boundary/repository-contract.json`、`contracts/tenant_boundary/base-allowlist.json` の3パス。公開型・JSON・45登録の内容一致を修復し、base allowlistは許可symbolを追加せず7.7履歴のみ正式受理後に追記する。実際の並行未コミット変更があるパスだけ停止する。未回答を所有解除・担当受理とは扱わない。既存23履歴は保持し、新実値の正式受理・本人逐行確認は別ゲートのまま。

### 2026-10-21 PO限定追加レビュー1回の実施記録

POはHEAD5295956fの共有3パス・直接影響箇所・45登録の内容/権限境界/既存登録の保持・既存23履歴・7.7記録案/完全値に限定して追加1回を許可。既定2/2を維持し、敵対レビュー基本2回＋PO追加1回、反対側基本2回の履歴はリセットしない。限定レビュー結果はP0/P1/P2各0件、修正不要。製品/契約/2 snapshot/記録案/判断資料JSONの値は不変。7.7の新実値と本人逐行確認は未受理・未実施のまま。後発の未再レビュー範囲は本計画・README・worklogのレビュー結果記録のみ。正式回答後の反映・全検査・通常push・CI確認は既承認手順で進める。

### 2026-10-21 #165の7.7正式受理と反映1周目

山田正輝が2026-10-21、対象HEAD ba23630a1772bd3595e3042a434376175d3aa56b、判断資料SHA-256 2e20c20e16bb8d0a0566405b3592a55892f83462716afe5b4322c031a273ff8c、記録案SHA-256 f35b6bf0230064ec8817302f05c3e752972e3d90807067eab70b81a4656439a9の完全前後値をmasaki1025/pitchlog#165の単一受理として正式受理した。repository 21→22以外の8資産・authz不変、base allowlist33/許可symbol/射影不変、既受理23履歴保持を再照合。正式記録は既存23件の後に1件のみ追記し、新snapshot1件のみ追加する。計画はactiveを維持する。

既定2周＋PO追加1回の履歴、レビュー後の結果記録3ファイルが未再レビューであることを保持する。今回の正式反映・実施記録もその後の差分であり、追加レビュー済みとは扱わない。承認は7.7限定であり本人逐行確認ではない。必要全検査/最終HEAD CIを回収し、本人確認の固定差分を提示する。Draft解除・マージ・公開は行わない。

### #165 manifest連動差分の限定承認・追加レビュー2回目

POは第4共有パス `tests/fixtures/frozen-archive-cases/manifest.json` の `corpus_inputs.digest` だけを、b3accebe79a37392e96be2053fbd83b4b4471e204d4aee67d20094b9525e03ceからf50b17a2bb95e95828ced277c4288dd64a0be11a2e5132fdee691683a877634bへ追随する候補作成と、受理値に影響がない場合の正式修正・検査・通常push・CI回収を許可した。D先行を#152/#156/#161へ通知し、通知と受信側の受理/所有解除を区別する。対象worktreeの当該ファイルは2回ともcleanかつSHA-256/mtime不変だった。

ステップ3の検査是正として本1フィールドと直接影響の比較fixture/digest整合だけを扱う。case・期待値表・prefix・固定snapshot集合・比較revision・runner/検査器は変更しない。承認済み7.7値・snapshot・既存履歴を変えないことを反映前後に検証し、影響があれば別途正式受理まで停止する。履歴書換え・#165の重複追記は禁止。

今回の独立レビューは基本2周＋前回追加1回を維持したPO追加2回目の1回。33失敗の参照digestへの帰属、正式反映済み実ファイルとの一致、拒否能力と7.7への不変性を確認する。レビュー後の反映/結果記録は未再レビューとして最終本人確認へ提示する。本人確認・Draft解除・マージ・公開は代行しない。
