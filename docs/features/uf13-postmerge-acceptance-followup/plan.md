---
feature: uf13-postmerge-acceptance-followup
status: active
承認: 未
重さ分類: コア領域
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-uf13-postmerge-acceptance-followup
notion: https://app.notion.com/p/3f493b75e68781628422c331bfebc350
branch: feature/uf13-postmerge-acceptance-followup
created: 2026-10-19
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 最小追補計画: 自チームreadと既存選手管理の実API受入

## 1. 背景・目的

[TSK-528](https://app.notion.com/p/3f493b75e68781628422c331bfebc350)の保護/teamに、[TSK-520](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2)の既存選手管理を自チームでも利用できる最小readを加える。[要件FR-033/FR-034、NFR-005/014/019](../../requirements/requirements-pitchlog-2026-07-22.md)に対応する。カード全体の完了や新カード起票は対象外。

実基線はorigin/develop `ba339cf8bdaac4761b8cf437abaf21763617d064`。#157/#150/#151/#154は統合済み。正常系8項目はこの実統合HEADで成功し、ユーザーが確認済み機能として受領した。故障系はその実行で再試験したとは扱わない。

自チームreadの採用方針は2026-10-19のユーザー指示で確定。既存の[最小契約資料](../uf13-team-route-acceptance/self-team-read-addendum-candidate.md)を編集元とし、設計書を新たに複製しない。本計画のステップ・合格条件と最終指摘反映差分は未承認。製品変更は計画レビュー後の最終承認から開始する。

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
- 必要性が確定した場合だけ`contracts/authz/route-registry.json`、`http-route-matrix.json`、各lock、`oracle-seal.lock.json`、`oracle-meaning-change-approvals.json`と対応snapshot/受理記録。既存ROUTE:RECORD:team_records:readが充足するなら新route_id/claimは増やさない。
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

self query keyは検証済みtenant+authEpochを含め、opponentページ群と分離する。未確認ではquery/mutationを開始しない。self成功時は初期自動選択するが、利用者が明示選択済みのopponentを後着selfで上書きしない。selfのpending/0件/通信失敗を独立表示し、opponent成功をself成功に見せない。

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
| 2 | 正規roster client/query key/既存TeamScreenへのself接続と固有spec | self取得/選択/欠損表示、認証切替/旧query・mutation/再送なし、opponentページング回帰、全frontend/type/lint/整形/build成功 |
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
- frontend Vitest: self取得pending/0/失敗/成功、初期選択と明示opponent選択、ページング/登録/通常編集・再取得、遅延self queryと遅延mutationの世代切替、未確認中通信0、自動再送0。
- 実画面/API/隔離DB: production preview/既存Chromium手順、self名/kindを確認→一覧→追加→編集→reload→DB observer確認。別tenant・2タブ/遅延/通信断の既存手順を必要な影響範囲で再利用し、opponent経路も別に回帰確認する。資格情報/Cookie値を証跡へ残さず自分の環境だけ撤去する。
- 全件品質: root Ruff/ty/pytest、backend Ruff format/check/ty/pytestと既存migration/DB契約検査、frontend Prettier/ESLint/vue-tsc/Vitest/build/depcruise/閉域。frozen/tenant-boundary/authz/caller/HTTP/coreの既存検査。試験除外・timeout緩和・検出漏れを許可しない。
- レビュー: 本計画とAPI/認可意味契約は6.1/6.3の敵対レビュー（原則2回、P0例外のみ）。実装は別枠の反対側/コア敵対レビューを既定回数で実施。既存PRの枠/可決/本人確認は流用しない。
