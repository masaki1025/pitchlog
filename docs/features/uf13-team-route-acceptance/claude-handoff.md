# Claude 向け申し送り: U-F13 `/team` 接続・U-F5 実 API 受入

更新日: 2026-10-14

## 現在地

- C1 branch: `feature/auth-session-verification-contract`
- C1 worktree: `/tmp/pitchlog-auth-session-verification-contract`
- base: `origin/develop` `e6e1a867f88bbdac90f2be9bed20dff900eec866`（PR #119・#129・#136 まで取り込み済み）
- 状態: 計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` のC1・C2・C3/U-F3とU-F13の3ステップ再編は2026-10-14に一括承認済み。C1は#119統合後の再照合を完了したが、共有資産の所有・統合順待ちで製品コード未変更。
- cards: U-F13 TSK-528、U-F5 TSK-520、U-F3 TSK-518。

## 再利用する統合済み資産

- PR #123: `/help`、router、共有 Pinia、共有 QueryClient。
- PR #120: U-F6 client、roster DTO、401 / authEpoch 境界。
- PR #127: TeamScreen、TeamMembersContent、paging、登録、通常編集、警告、遅延 mutation 防御。

## 外部依存とブロッカー

1. PR #119 は `8294a1b6` で統合済み。`LoginResponse` は status のみで、検証済み tenant ID を frontend へ供給しないため、承認済みC1のsession APIが必要である。
2. #119の`TenantContext`はtenant IDだけを保持する。C1の正規`team_name`取得に必要な閉じたtenant read operationは未実装で、#131/#132が所有中のrepository凍結資産と重なる。
3. roster の `Page` / `TeamRecordRead` / `PlayerRead` と response header に応答 tenant 証跡がない。
4. developにLoginScreen/`/login`がない。C1が正規auth client、U-F3がLoginScreenと失敗表示を先行統合し、本計画ステップ2/3が`/login`と`/team`のrouteを登録する。
5. C1の新規session routeは認証入口exact-setとroute / HTTP matrixの追随が必要で、#137の所有差分と重なる。`router.ts`と`App.vue`はtenant-isolationの意味範囲だが現行core pathsにないため、U-F13ステップ1/3で宣言し、ステップ2/3でJSON登録と製品変更を同時に行う。

## 依存解消の担当と追補計画

- **C1 / Codex D**: [追補計画](../auth-session-verification-contract/plan.md)。login後のsession確認を、認証済み・server未認証（401だけ）・結果未確認へ分ける。Cookieが変わり得る時点で旧store/cacheを破棄し、資格情報を自動再送しない。
- **C2 / Codex D**: [追補計画](../tenant-match-metadata-contract/plan.md)。expected-tenant request metadata、serverのoperation前exact match、成功2xx限定ack、U-F6の本文前fail-closed検証を定義する。
- **C3 / Codex D**: 正式カードは[TSK-518](https://app.notion.com/p/3f493b75e687814ca3c7fead50df2a14)。[U-F3計画](../uf3-login-screen/plan.md)で`LoginScreen.vue`を経路未登録で所有する。auth clientはC1、route/redirectはU-F13が所有する。
- core path の先行登録は行わない。外部統合前に進めるのは契約調整・追補計画・レビューまで。

## U-F3正式カードとの差分

- 従来の「正式カード未確認・担当不在」は更新する。TSK-518は未着手、優先度高、Tコアで、U-F1/U-F2/U-F6/U-A1に依存する。
- Notionの担当者プロパティには識別子があるが表示名を確定できない。会話上は山田正輝がCodex Dを担当に指名した。製品着手前にopen PR/worktreeと再照合する。
- 固有DoDは失敗理由の秘匿、移植規則と逐語性4点、NFR-023、5領域判定、横断要件、adversarial reviewと人間逐行確認、Vitest。

## PR #129・#131・#132との統合順

- #129は`93e1482a`で統合済み。未統合差分を基線にしない条件は解消した。
- #132はopen Draft / conflictingで、core-areas/core-guardとtenant boundaryの複数凍結資産を所有中。
- open PR全体のpath照合で、#131もopen Draft / conflictingのまま`.claude/core-areas.json`とtenant boundary凍結資産を所有中と判明した。U-F2 `authStore`とU-F6共通clientの直接変更を持つopen PRはなかった。
- #137はopen Draft / conflictingで、4つのauth route / HTTP matrix資産とchecker試験を変更中のため、C1 session route登録と重なる。
- C1/C2は#131・#132・#137の未統合差分をdevelop基線にしない。契約レビューは完了しており、製品実装と共有凍結資産の変更は各PRの所有・統合順確定後に行う。
- 所有・統合順の照会をPRコメントへ記録済み: [#119](https://github.com/masaki1025/pitchlog/pull/119#issuecomment-6163651661)、[#129](https://github.com/masaki1025/pitchlog/pull/129#issuecomment-6163651993)、[#131](https://github.com/masaki1025/pitchlog/pull/131#issuecomment-6163652301)、[#132](https://github.com/masaki1025/pitchlog/pull/132#issuecomment-6163652601)。返答または統合後に所有境界を再確認する。

具体的な C1 / C2 / C3 と担当は [research.md](research.md) 4 節、承認判断は [plan.md](plan.md) 8 節を参照する。

## 実装時の禁止事項

- 仮 tenant ID、team name による tenant 推定、手入力 localStorage を公開条件に使わない。
- 仮 response header / DTO / session API を本 branch だけで作らない。
- `/login` の空画面、`/` への暫定 redirect、guard 無効化で `/team` を公開しない。
- PR #119 または他担当 worktree を変更しない。
- 15 経路 + catch-all、在籍変更、削除、試合中登録を混ぜない。

## レビュー重点

- hydration 完了前の画面/API開始、`teamId=null` の扱い。
- `RouterView` の `authEpoch` key と共有 QueryClient clear 後の observer 残存。
- Cookie が先に B、`bb.auth` が A の窓では、server が A の expected ID と B の `TenantContext` の不一致を operation 前の固定 404 にすること。2xx の ack 欠落・不正は client が破棄すること。
- 遅延 mutation の結果未確認表示、自動再送禁止、B の notice/cache 非更新。
- A の entity ID を B で要求した 404 と本文非表示。
- router / App の core path 検出。未登録なら宣言 → 登録を分け、人間逐行確認を迂回しない。
- 2xx の ack exact match、認証世代・teamId不変性、ack 欠落 / 不正の結果未確認、401 の session 失効、404 / 422 の失敗処理の順序。
- tenant / stale auth 境界エラーは mutation だけでなく query の retry predicate でも自動再送対象から外す。
- B から A の player GET / PATCH、opponent PATCH、A team-record を指定した player create を行い、各 404 を不存在 ID の status・本文と比較する。

## 次の操作

横断reviewは第1周P0 2/P1 6、第2周P0 2/P1 2を全採用し、P0限定追加周はP0 0で可決。第2周P1追随は未再レビューとして人間逐行確認へ残す。C1はsession 2xxかつDTO検証成功時だけ認証済みとし、DTO不正は結果未確認、`team_name`はサーバーの認可済み表示データとしてだけ使う。#119統合後にC1専用worktreeを最新developから作り、所有・正本・凍結資産を再照合してステップ1/2だけを実装する。C2とC3は各開始条件まで待機し、U-F13はC1・C2・C3統合後にステップ1/3だけを進める。ステップ1は宣言・試験、別のステップ2コミットでJSON登録と製品変更を同時に行い、core pathだけを先行登録しない。

## 2026-10-14 C1 ステップ1開始条件の再照合

- `origin/develop` は `e6e1a867f88bbdac90f2be9bed20dff900eec866`。PR #119 は `8294a1b6`、PR #129 は `93e1482a` で統合済みである。C1専用branch / worktreeを作成し、承認済み計画へ最新developをmergeした。
- 計画承認と#119実コードの再照合は完了した。`GET /auth/session`、`AuthSessionResponse {tenant_id, team_name}`、Cookie由来の`TenantContext`だけを認可入口にする方式は承認済みのまま維持する。
- #119の実装は`TenantContext.tenant_id`だけを供給する。正規表示名`public.tenants.name`を閉じたrepository経路で読む製品operationはdevelopにない。routerからの直接SQL、login入力の再利用、未承認の`authn.verify_token`戻り型変更は採用しない。
- 推奨する最小経路は、既存`CAP:tenants:read`を用いるtenant表示情報read operationを追加し、`TenantContext`で束縛した結果から`tenant_id`と`name`を厳密に検査する方式である。候補差分は新規`backend/src/pitchlog/repositories/tenant_profile.py`、`backend/src/pitchlog/repositories/operation_registry.py`、`backend/tests/test_authz_repository_contract.py`、`contracts/tenant_boundary/repository-contract.json`と同契約の履歴・digest追随である。
- この候補は#132が変更中の`operation_registry.py`とrepository contract、#131が変更中のrepository contractに重なる。必要な回答は、#131/#132を先に統合してC1が最新develop上でoperationを追加するか、両担当が当該tenant read operationを供給してC1が利用側だけを所有するか、どちらかの統合順である。
- 新しい認証入口は既存のauthentication-entry exact-setを3件から4件へ更新する必要がある。候補差分は`contracts/authz/route-registry.json`、同lock、`contracts/authz/http-route-matrix.json`、同lock、`scripts/check_authz_catalog.py`、`tests/test_check_authz_catalog.py`、`backend/tests/test_api_app.py`である。#137が4つのroute / matrix資産とchecker試験を変更中のため、#137先行統合後にC1が追随するか、#137担当から当該ファイルの所有移管を受ける必要がある。
- auth router / schemaとsession endpoint固有試験には、現時点で重複する未統合差分を確認していない。ただし上記共有資産を変更せずにステップ1の凍結資産検査をgreenにできないため、製品コードだけを先行実装・コミットしない。
- よってC1ステップ1は未着手。停止理由は#119ではなく、正規`team_name` read operationの実装経路と#131/#132/#137とのファイル所有・統合順が未確定であること。計画全体の再承認は不要で、上記2点の狭い回答だけを残す。
- U-F13本体はC1・C2・C3の接続条件が揃うまで待機を維持する。

## 2026-10-14 C1先行変更の所有調整

- 山田正輝の指示により、tenant profileとtenant read operationはC1が担当する。新規`tenant_profile.py`はC1の専有範囲とする。
- #131へ[一時所有案](https://github.com/masaki1025/pitchlog/pull/131#issuecomment-6171263924)を提示した。C1が`repository-contract.json`と必要な履歴追随を先に更新し、C1統合後に#131が最新developへ追随する案である。
- #132へ[一時所有案](https://github.com/masaki1025/pitchlog/pull/132#issuecomment-6171264327)を提示した。C1が`operation_registry.py`、repository契約、repository契約試験と必要な履歴追随を先に更新し、C1統合後に#132が最新developへ追随する案である。
- #137へ[一時所有案](https://github.com/masaki1025/pitchlog/pull/137#issuecomment-6171264803)を提示した。C1がauth route / HTTP matrix各本体・lock、authentication-entry exact-set検査、7.7のoracle封印追随を先に更新し、C1統合後に#137が最新developへ追随する案である。
- 3件とも既存branch/worktreeは変更していない。2026-10-14 23:55 JST時点では各担当の返信がなく、共有ファイルの一時所有は未受理である。新規C1専有ファイル以外の製品実装は開始していない。
- repository系とauth route系は別の所有判断とする。#131/#132が不受理なら同2PRを既定順で統合後にC1がrebaseしてtenant read operationを追加する。#137が不受理なら#137統合後にC1がrebaseしてsession routeだけを追加する。片方の未回答を他方の一律待機理由にはしない。
- 7.7確認では、tenant-boundaryのcontract revision・凍結射影・append-only snapshotと、authzのroute/matrix lock・`frozen-baselines.json`のoracle_input履歴・seal連鎖を別々に扱う。基準値をcheckerへ直書きせず、比較不能時のfail-closedを維持し、実際の受理単位とPR番号が確定した時点で履歴の承認記録を確定する。
