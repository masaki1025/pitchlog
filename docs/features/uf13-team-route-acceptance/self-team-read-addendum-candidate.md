# 自チーム取得の最小追補候補（正式変更前）

2026-10-19 / 編集担当: Codex D。候補設計と検証準備だけを収録する。最小案の方針は後続の2026-10-19ユーザー指示で採用済み。具体計画の最終承認、正式資産の7.7受理、本人確認を済ませた資料ではない。

## 0. 実統合後の現在値（2026-10-19）

実develop `ba339cf8bdaac4761b8cf437abaf21763617d064` を再照合した。#157/#150/#151/#154の統合待ちはすべて解消済み。C1相関・C2・LoginScreen・保護/team・共有providerはこの基線の既存実装を再利用し、再作成しない。`SelfTeamRecordReadToken`と`GET /team-records/self`は同基線に存在せず、最小方針はユーザーが採用済みであり再照会しない。製品は未実装。具体的な実装手順/合格条件は[最小追補計画](../uf13-postmerge-acceptance-followup/plan.md)でレビューし、その最終承認と7.7等の個別ゲートを残す。

同基線の実画面/API/隔離DB正常8項目は再実行成功したが、対象は対戦相手配下の選手管理である。自チーム取得の不足は解消しておらず、自チーム受入・TSK-528全体を完了にしない。

## 1. 照合元と既存権限

初回照合は実develop `015dfa9d` と当時のC2候補を用いた。現在は統合済み実develop `ba339cf8` の下記実ファイルとC2の実通信契約を再照合し、同じ不足と既存権限を確認した。C1 #157内の `self-team-read-gap.md` の概要を具体化する資料の編集元は本書とし、候補を二重に改訂しない。

| 根拠 | 確認できた事実 | 今回追加しないもの |
| --- | --- | --- |
| `contracts/authz/product/ddl-elements.json` | `ACL:team_records:pitchlog_app` は表SELECT/INSERT/UPDATE（grant optionなし）。`POLICY:team_records:tenant_owned` は `app.tenant_id` と行tenant_idの一致をUSING/WITH CHECKに要求 | 新しいDBロール、grant、RLS緩和、SECURITY DEFINER |
| `contracts/authz/product/capability-catalog.json` | `CAP:team_records:read` はteam_recordsのread。既存アプリ権限内でid/kind/name/hidden_atをSELECTできる契約 | 新capability ID、他tenantのread権限 |
| `backend/src/pitchlog/repositories/roster.py` | TeamRecordReadTokenのprepareとRequiredBindingはopponent固定。選手read/create/updateにはkind=opponent固定がなく、tenant条件・複合FKで範囲を制限 | 既存opponent tokenのkind引数化・対象拡大、選手APIのコピー |
| `backend/migrations/versions/0002_tenants_teams_players.py`、schema-manifest、data-model §7-1 | `UNIQUE (tenant_id) WHERE kind='self'`、selfのhidden_atはNULL。高々1件はDB制約、最低1件はテナント生成の責任 | 列・索引・migration、自チーム作成/修復/非表示化 |
| `api/schemas/roster.py`、`frontend/src/api/roster.ts` | TeamRecordReadが既にselfを許す。sessionのtenant_idとteam_record_idは別の識別子 | session DTOへのself ID追加、仮ID、独自DTO |
| `frontend/src/screens/TeamScreen.vue` | 既存一覧にselfがあれば優先選択するが、GET /team-recordsがopponent限定なので現在は取得できない | fixture IDの画面注入、opponentの自チーム扱い |

権限の結論はカタログと実装の静的照合。新operationを通した隔離DB/app role実証は未実施で、後述の必須試験に残す。

## 2. 固定read operation候補

- 公開型: `pitchlog.repositories.roster.SelfTeamRecordReadToken`。引数なしのfrozen token。tenant_id、record_id、kind、include_hidden、limitを端末から受け取らない。
- `capability_id = CAP:team_records:read` を再利用し、`ROSTER_OPERATIONS` に独立した `OperationRegistration` を1件追加する。実行入口は既存 `tenant_transaction_scope(context).run(token)`。任意SQL・関数実行入口は増やさない。
- SQL形: team_records単表、選択列id/kind/name/hidden_at、`tenant_id=:tenant_id AND kind=:kind AND hidden_at IS NULL LIMIT :limit`。tenant bindは既存実行器が検証済みcontextから注入。prepareはkind=self、limit=1だけを返す。RequiredBindingでkind=selfを固定し、required limit上限1を登録する。FOR UPDATEなし。
- 初期概要の `ROSTER:self_team_read` は未承認の仮ラベルだった。現行の非function OperationRegistrationは独立operation_id欄を持たないため、新literalを製品契約に追加しない案。token型と既存capabilityで識別する。この訂正も候補の審査対象とする。
- 0件は汎用404。DB一意制約を前提に上限1で取得する。self欠損をopponent選択や暗黙作成で埋めない。制約破損を正常とする仕様は追加しない。
- 既存TeamRecordRead/Create/Update/DeleteTokenのopponent RequiredBindingと試験は保持する。selfの名称編集・削除APIを追加しない。

## 3. HTTP・DTO・認証tenantの導出候補

| 項目 | 候補 |
| --- | --- |
| endpoint / handler / OpenAPI operation_id | `GET /team-records/self` / `read_self_team_record` / `roster_self_team_read` |
| 入力 | 業務path/query/body引数なし。Cookieの提示値から既存require_tenant_accessが発行するTenantContextを使う。期待tenant/challengeはC2の既存header契約に従い、認証・認可の代用にしない |
| 成功 | 200 / 既存TeamRecordRead `{id: UUID, kind: self, name: string, hidden_at: null}`。tenant_id/password等は本文へ追加しない |
| metadata | TenantMatchedRouteの対象operationへ追加し、業務SQLより先に検証済みcontext.tenant_idと期待tenantを照合。成功だけ既存ack/challenge、対象応答はno-store。新header/literalを作らない |
| 未認証・不正資格情報 | 既存RequestGateErrorの分類を維持。Cookieの未確認を端末tenantで補完しない |
| tenant不一致・metadata欠落/不正 | C2の汎用404。self read SQLが0回であることを試験する。入力値/他tenantの存在を本文に含めない |
| selfなし | 同じ汎用404。別tenantのself、推測ID、opponentへフォールバックしない |
| DB/通信/DTO不正 | 既存エラー分類へ従う。成功表示・旧cache復元・mutation自動再送なし。2xx metadata不正は承認済みC2無効化境界へ接続 |

`/team-records/{team_record_id:uuid}` と文字列selfは識別できるが、実route exact-set/OpenAPI試験で曖昧性がないことを証明する。API/認可計画レビュー第1周で、既存CAP:team_records:readとROUTE:RECORD:team_records:read、app roleのSELECT/tenant RLSで本readを表せることを確認した。既存IDを再利用し、新route_id/claim/権限は追加しない。具体的な充足不能が後で判明した場合だけ、その差分を別ゲートへ出す。

## 4. 画面への接続とPR境界

- 正規roster clientへ `readSelfTeamRecord(options?)` を追加する候補。既存apiRequestのtenantBound、C1の認証世代/意図、C2の応答照合を使う。呼出側からtenantを指定する新入口は作らない。
- shared Pinia/QueryClientを維持。self query keyは検証済みtenantとauthEpochを含め、opponentページ群とは別に保持。共通clientからのunknown結果をroster.tsのself取得入口で既存DTOの4項目（UUIDのid/kind=self/stringのname/hidden_at=null、欠落・余剰キーなし）として実行時検査してからqueryへ返し、選択肢へ結合する。型キャストだけを検証としない。不正な200は選択/cacheへ採用せず、players通信を始めない。共通clientはコピー/改変しない。self queryの自動retryは無効とし、明示再確認だけを許す。
- self取得待ち/失敗を独立表示し、自チームが未取得なのに対戦相手で成功を代用しない。自チームが取得できた場合に自動選択するが、利用者が選択済みの対戦相手を後着selfで上書きしない。
- 認証未確認ではquery/mutationを起動しない。世代切替で選択と全旧cacheを破棄し、旧query/mutationが新画面を更新しない。登録/編集は既存選手APIと既存部品を使用する。

| 担当/既存PR | 現在の所有境界・統合条件 |
| --- | --- |
| Codex D / #157・#150・#151・#154 | すべて実developへ統合済み。既存auth/store/client/LoginScreen/router/Appを再利用し、既存PRへ追加しない |
| Codex D / self最小追補候補 | `repositories/roster.py`、`api/routers/team_records.py`、`api/tenant_access.py`、正規roster client/query key/TeamScreenと固有試験が最小候補。最小方針は採用済み。具体計画の最終承認・正式登録の個別受理は未了 |
| 共有凍結資産 | 着手時に所有・統合順を調整。open #152はbase-allowlist、route registry/matrix/lock/seal等と重なる。未統合差分を基線にせず、候補準備は進めるが共有ファイルを先取り編集しない |

#154は既存部分実装として統合済みであるため、「同じ#154へ同梱する第一案」は終了した候補配置案とする。推奨は最小追補1本の後続PRであり、不要な前提PRは作らない。実PR番号が正式受理前に必要となる場合のDraft先行は、既存C1だけの例外を流用せず、その必要差分だけ判断対象へ出す。現在の同一worktreeで最小追補計画をレビューする。新PR・正式資産変更・製品実装にはまだ進んでいない。

## 5. 残る正式ゲートとレビュー現在値（計画2周実施済み）

既承認の認証・C2・U-F3・U-F13計画と成果の再審査ではなく、この新read経路だけが対象。既存権限内のSELECTであることは、新しい公開operationの承認済みを意味しない。

| 時点 | ゲート・具体的差分 | 担当・必要な人間判断 |
| --- | --- | --- |
| 実装開始前 | **最小計画追補**。採用済みの本書§2–4を具体化する最小計画を2周レビュー済み。3件のP1を採用反映し、最終P1の未再レビュー差分を含むステップ・失敗境界・試験・Draft先行条件を最終承認へ出す | 起案・実装候補はCodex D。採用済み方針は再照会せず、レビュー採否と実装前の最終差分だけ人間承認へ一括提示。既存4PRの計画・レビューを再作成しない |
| 実装開始前 | **API・認可の意味契約**。`GET /team-records/self`を新公開入口にし、既存`CAP:team_records:read`と`ROUTE:RECORD:team_records:read`を再利用する。第1周の静的照合で充足を確認し、第2周もこの反映に追加指摘なし。新claim/literal/権限を増やさない | 既存read契約/SELECT/RLSの再利用と正本構造変更なしの判定を計画レビューで確認。新規範・権限追加の具体的必要が後で判明した場合だけ、その本文を7.6/7.3へ提示。既存方針を再照会しない |
| 共有資産編集前 | **所有・順序**。#152と重なるbase-allowlist、authz registry/matrix/lock/seal等の一時担当と統合順を確定 | 共有資産の担当受理が必要。返事なしを所有移管としない。#152全体をすべての準備作業の停止条件にはしない |
| 候補固定後・正式受理前 | **tenant-boundary / 7.7**。repository-contractのproduct_operation_token_typesへ新型1件、source_digest、必要なbuilder symbolだけbase-allowlistへ追加。現基線revisionは21/33だが、最終実基線から再導出し、今は次番号を予約しない | Codex Dが実ファイル/blob・前後値・2系列の必要snapshot/理由/受理記録案を機械導出。7.7の正式受理者・日付を先行入力せず人間判断へ提示。inventory/context発行入口を広げない |
| 候補固定後・正式受理前 | **authz / 7.7**。実際に変わるroute registry / HTTP matrix / 各lock、oracle seal、meaning-change記録の差分と入力・sealed digestを完全値で提示。既存read claimをそのまま使えて不変の資産は変更しない | Codex Dと認可資産担当が対象を特定し、人間が変更対象だけを正式受理。C1/#154の受理・本人確認は流用しない |
| 統合前 | **製品試験・既定レビュー・本人確認・CI**。新経路のtenant一致/古い応答/自動再送禁止、隔離DB/app role、実画面の自チーム受入 | Codex Dが実施証跡・既定の反対側/敵対レビュー採否と最終差分を提示し、人間が逐行確認・統合を判断。新追補のレビュー枠を既存PRの使用済み枠と混同しない |

### 正式変更に含めないもの

- 新capability・DB role・列・索引・migration・grant・RLS緩和・SECURITY DEFINER。必要性が新たに判明した場合だけ個別差分を提示する。
- session DTOの拡張、端末指定tenant/self ID、opponent tokenの対象拡大、自チーム作成/修復/名称変更/削除。
- core pathだけの先行登録。想定する製品6パスは実JSONで既にTの対象であり、query key/TeamScreenはT/D。今回の候補準備でcore3ファイルは変更しない。

上記は必要な受理対象の整理であり、完全値が未算出の7.7や新APIの承認済みを表すものではない。契約・所有の開始前条件と、実装後の証跡/正式受理・統合条件を区別し、未実装経路の実DB成功を計画作成の前提にはしない。

## 6. 自チーム最小追補の検証準備（未実行）

既存backend pytest/product catalog/隔離PostgreSQL2tenant fixture、frontend Vitest、既存実画面Playwrightを再利用する。新ハーネス、共有DB変更、試験除外、timeout緩和は行わない。

- 登録文/実行文のtenant WHERE、kind=self、NULL hidden、limit1、固定bindingを検査。kind変更/過大limit/任意tenant bindは拒否。opponent固定の既存負例も残す。
- A/Bそれぞれのself/opponentを作り、Aのapp role文脈でB selfをSELECTできないこと、文脈なし拒否、0件404、self非表示拒否、重複self拒否を隔離DBで確認する。
- Cookie A+期待B、header重複/欠落/非canonical、未認証でSQL0回。Cookie A+期待AならA selfだけ。非2xxに成功ackなし/no-store、正しい2xx metadata/bodyだけ採用する。
- B self IDを用いたAの選手登録は既存複合FKから汎用404。B player IDの取得/通常編集は不存在と同じ404。players一覧へ他tenant team IDを与えた場合は既存契約の空一覧を維持し、B行は返さない。
- 画面で自チームを明示確認し、選手一覧→追加→通常編集→再読込後もDB値が残ることを確認。opponentの既成功とは別証跡とする。
- self応答遅延中のA→B、mutation遅延、旧Cookie遅延、別タブ、通信失敗、認証未確認、2xx metadata不正を確認。旧選択/cache/成功を復元せず、変更要求を自動再送しない。

**現状: 最小方針は採用済み。具体計画/契約の基本レビュー2周を実施し全P1採用反映、最終差分の人間承認待ち。製品未実装・自チーム受入は未実施。対戦相手配下の成功、専用結合HEADの成功、各PR単独CIの成功を相互に読み替えない。**


## 2026-10-19: 既存部分PRの統合指示との対応（統合前の履歴）

上記「#154へ同梱する第一案」「部分実装の先行統合をここでは採用しない」は候補提示時点の記録。後続のユーザー指示「150.151.154を順にマージして。コンフリクトなどが起きたらその都度解除し実施」に従い、#154は既存の保護経路・対戦相手配下の管理に限る部分実装として統合準備する。この指示をself取得契約の承認とは扱わず、本候補は未採用・未実装を維持する。API・認可・凍結資産の正式ゲートと自チーム実画面受入は後続に残す。TSK-528全体と自チームを含む受入完了は主張しない。
