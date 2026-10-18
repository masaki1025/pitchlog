# 自チーム取得の最小追補候補（正式変更前）

2026-10-19 / 編集担当: Codex D。候補設計と検証準備だけを収録する。API・認可・凍結資産の変更、実装計画の承認、7.7受理、本人確認を済ませた資料ではない。

## 1. 照合元と既存権限

実origin/develop `015dfa9db0b7b8740369911a9cb5195dd59a62ea` の下記実ファイルを照合した。C2の通信契約だけは未統合の自分の候補 `3eb3a0d37bffbcac3922f1656d6aa820e229fa6f` を参照する。通常基線にはしない。C1 #157内の `self-team-read-gap.md` の概要を具体化する資料の編集元は本書とし、候補を二重に改訂しない。

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

`/team-records/{team_record_id:uuid}` と文字列selfは識別できるが、実route exact-set/OpenAPI試験で曖昧性がないことを証明する。HTTP route_id等の凍結資産上の識別子は、既存read claimの利用か最小claim追加かを正式審査で決め、ここで受理済み値を予約しない。

## 4. 画面への接続とPR境界

- 正規roster clientへ `readSelfTeamRecord(options?)` を追加する候補。既存apiRequestのtenantBound、C1の認証世代/意図、C2の応答照合を使う。呼出側からtenantを指定する新入口は作らない。
- shared Pinia/QueryClientを維持。self query keyは検証済みtenantとauthEpochを含め、opponentページ群とは別に保持。結果DTOのUUID/kind=self/hidden_at=nullを確認してから選択肢へ結合する。実装上のdecoderは既存検証経路に集約し、コピーを作らない。
- self取得待ち/失敗を独立表示し、自チームが未取得なのに対戦相手で成功を代用しない。自チームが取得できた場合に自動選択するが、利用者が選択済みの対戦相手を後着selfで上書きしない。
- 認証未確認ではquery/mutationを起動しない。世代切替で選択と全旧cacheを破棄し、旧query/mutationが新画面を更新しない。登録/編集は既存選手APIと既存部品を使用する。

| 担当/PR | 所有境界・統合条件 |
| --- | --- |
| Codex D / #157 | 認証相関の現28ファイルを固定。自チームAPI/権限差分を同梱しない |
| Codex D / #150 | 既存C2 metadataと共通client。#157実統合後に承認済み680追随。self対象operationの追加は本候補が正式化されてから行う |
| Codex D / #151 | LoginScreenと固有試験。#157実統合後に実store型へ追随。self DTO/業務SQLは所有しない |
| Codex D / #154 | router/Appと既存選手画面の接続/受入。self未受入とステップ3未完了を維持し、候補資料だけ先行する |
| Codex D / self最小追補 | roster.py・team_records.py・tenant_access.py対象集合、roster client/query key/TeamScreenと固有試験。先行4PRの実develop統合後の基線から1本の最小follow-upを推奨。正式正本改訂が必要な場合だけ規約上必要な前提PRを分ける |

共有資産は着手時の編集所有を再照合する。本候補の作成は共有資産の一時所有取得を意味しない。新PRはまだ作らない。

## 5. 正式ゲートへ出す差分

1. **計画追補の審査・人間承認**: 本書のtoken/SQL/DTO/失敗境界・画面接続・試験・最小PR境界。既承認4PR全体を再承認待ちへ戻さない。
2. **正本/認可契約**: endpointと権限対応の正本を照合し、規範追加なら7.6決定表により7.3審査へ提示。既存SELECT・capabilityの範囲内である静的根拠と、新たに公開する操作を分ける。grant/認可範囲を広げる必要が判明したら個別差分を提示する。
3. **tenant-boundary/7.7**: `contracts/tenant_boundary/repository-contract.json` のproduct_operation_token_typesへ新型1件。`base-allowlist.json` は登録builderを照合し、許可済みSQLAlchemy APIを新symbolが使用する箇所だけ最小追加する候補。既存登録の削除/検査緩和をしない。inventoryやcontext発行入口は現時点で変更不要。必要なsnapshot・新旧識別値/source_digest・理由/受理記録案は実基線と最終候補から導出して正式受理へ出す。承認者/日を先行入力しない。
4. **authz/7.7**: `route-registry.json` / `http-route-matrix.json` と各lock、`oracle-seal.lock.json` / `oracle-meaning-change-approvals.json` の実際に変わる入力/claimだけ提示する。既存抽象read claimで足りる場合は不要な新claimを増やさない。pin対象の完全blob/digestと前後値は候補実装後に機械算出し、現在の未受理値を正式値として発行しない。
5. **実装レビュー・本人確認**: 新read経路はtenant-isolationの意味領域。既存path/guard検出を確認し、敵対/反対側レビュー、後発差分の明示、本人逐行確認、CIを必須とする。#157等の使用済みレビューや本人確認を流用しない。

## 6. 検証準備（未実行）

既存backend pytest/product catalog/隔離PostgreSQL2tenant fixture、frontend Vitest、既存実画面Playwrightを再利用する。新ハーネス、共有DB変更、試験除外、timeout緩和は行わない。

- 登録文/実行文のtenant WHERE、kind=self、NULL hidden、limit1、固定bindingを検査。kind変更/過大limit/任意tenant bindは拒否。opponent固定の既存負例も残す。
- A/Bそれぞれのself/opponentを作り、Aのapp role文脈でB selfをSELECTできないこと、文脈なし拒否、0件404、self非表示拒否、重複self拒否を隔離DBで確認する。
- Cookie A+期待B、header重複/欠落/非canonical、未認証でSQL0回。Cookie A+期待AならA selfだけ。非2xxに成功ackなし/no-store、正しい2xx metadata/bodyだけ採用する。
- B self IDを用いたAの選手登録は既存複合FKから汎用404。B player IDの取得/通常編集は不存在と同じ404。players一覧へ他tenant team IDを与えた場合は既存契約の空一覧を維持し、B行は返さない。
- 画面で自チームを明示確認し、選手一覧→追加→通常編集→再読込後もDB値が残ることを確認。opponentの既成功とは別証跡とする。
- self応答遅延中のA→B、mutation遅延、旧Cookie遅延、別タブ、通信失敗、認証未確認、2xx metadata不正を確認。旧選択/cache/成功を復元せず、変更要求を自動再送しない。

**現状: 候補設計/準備のみ。自チーム受入は未実施。対戦相手配下の成功、専用結合HEADの成功、各PR単独CIの成功を相互に読み替えない。**
