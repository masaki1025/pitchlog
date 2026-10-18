# U-F13 `/team` 接続・U-F5 実 API 受入 計画記録

## 2026-10-14 調査

- `origin/develop` `b81ae1ac` から専用 worktree / branch を作成した。PR #127 の U-F5 初期分割は統合済み。
- PR #119 は open、behind、別担当 worktree 所有。変更していない。
- U-F13 / U-F5 の同範囲を持つ open PR / worktree は見つからなかった。U-F3 の製品実装も見つからなかった。
- 共有 Pinia / QueryClient、router、U-F6 client、U-F5 TeamScreen の実コードを確認した。
- PR #119 の login response に tenant ID がなく、roster response に tenant 証跡がなく、develop に `/login` がないため、現時点では `/team` 公開条件を満たさない。
- 仮契約を作らず、C1（検証済み tenant ID 供給）、C2（応答 tenant 証跡と exact match）、C3（正規 auth client・LoginScreen・login→store 接続）を開始ゲートにした。`/login` route は U-F13 が `/team` と同時に登録する。

## 計画レビュー

### 1 周目（全文）

`codex_run.py review adversarial` は P0 1 件、P1 3 件、P2 0 件で否決。全件採用した。

- P0: router / App の core path 登録がステップにない。`frontend/src/router*` と `frontend/src/App*` を tenant-isolation へ宣言、JSON 登録する別ステップ 1/4・2/4 を追加した。
- P1: U-F3 を本縦断へ含める代替開始条件が未定義。U-F3 の先行統合を硬い開始条件にし、範囲変更時は計画改訂・再レビューへ戻す。
- P1: 401 と tenant 証跡欠落の処理順が曖昧。tenant 証跡は一致した 2xx で必須、401 は session 失効、404 / 422 は成功扱いせず tenant 所有本文を出さない規則へ分けた。
- P1: 越境受入が任意 ID 1 件だけ。player GET / PATCH、opponent PATCH、foreign team-record を指定した player create と B の一覧を対象にし、404 の status・本文を不存在 ID と比較する条件を追加した。

1 周目の指摘反映差分と影響節は 2 周目の対象とする。

### 2 周目（1 周目の反映差分と影響節）

P0 0 件、P1 1 件、P2 0 件で否決。P1 を採用した。

- C2 の照合主体が一意でない。server が expected tenant ID と `TenantContext.tenant_id` を exact match して不一致を operation 前の固定 404 にし、比較通過 2xx にだけ ID を含まない ack literal を付ける二段へ分離した。client は ack literal、認証世代、teamId の不変性を検証する。ack と tenant ID を比較するとは記述しない。

基本枠 2 回を使い切り、2 周目に P0 はないため自動の 3 周目は行わない。最終反映は Codex の再レビューを受けていない。人間承認ではこの C2 最終反映差分と、1・2 周目の採否記録を確認対象にする。

## 人間承認

2026-10-14、山田正輝が`docs/features/uf13-team-route-acceptance/plan.md` 8節の5判断、外部依存成立後にステップ1/4だけへ進む方針、C1・C2・C3のCodex D担当を承認した。C1・C2・C3の各追補計画は別の人間承認待ちである。

## 製品実装

未着手。計画承認と外部契約の着地前に `/team` を route へ登録しない。

## 2026-10-14 再開時の再照合

- `origin/develop` `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`（PR #133 統合済み）を専用ブランチへ取り込んだ。#133 の差分は core-guard 回帰試験と計画・作業記録で、U-F13 の API・DTO・認証契約に影響しない。
- PR #119 は head `bf43ef93f8a9a2244b2bd5e06d1906ffbcda11de`、open / behind。`core-guard` と `harness` が失敗し、人間逐行確認も未実施。所有 worktree は維持されており、本作業から変更していない。
- PR #119 の `LoginResponse` は引き続き `status: authenticated` だけで、C1 の検証済み tenant ID / team name は供給しない。
- develop の `frontend/src` に `/login` / `LoginScreen` はなく、C3 は未着地。共通 client に expected tenant と server context の照合済み証跡もなく、C2 は未着地。
- open PR と worktree を再確認し、U-F13 / U-F5 の同一製品範囲を所有する別担当は見つからなかった。
- 計画の 2 周レビューは繰り返していない。最新基点と再照合証跡だけを更新し、計画承認と C1 / C2 / C3、PR #119 統合を待つ。

## 2026-10-14 依存解消案の明確化

- core path 登録だけを先行する開始順変更は、利用者の指示により見送った。
- #119 の成功本文は現行 scope で `status` だけであり、所有 PR を変更しない。C1 は #119 統合後の `GET /auth/session -> {tenant_id}` 追補として分割する案に改めた。
- C2 の候補契約を request `X-Pitchlog-Expected-Tenant`、通過 2xx の response `X-Pitchlog-Tenant-Match: 1` とし、U-F5 が使う 7 経路を対象候補にした。正式化は追補計画のコアレビューと人間承認で行う。
- U-F3 の open PR、worktree、正式カードの担当記録は見つからなかった。本セッションが `api/auth.ts` と `LoginScreen.vue` を別 PR で担当し、route 登録は U-F13 に残す先行分割を承認候補にした。
- C1 / C2 / U-F3 はいずれも担当候補を本セッションとしたが、製品実装は未承認・未着手。#119 統合前は契約調整、競合表、テスト matrix、計画レビューだけを進める。
- 今回の明確化差分は、計画レビュー 2 周後の人間確認対象として plan 9 節に記録した。自動 3 周目は実施していない。
## 2026-10-14 追補計画と正式カード照合

- 山田正輝がU-F13計画の5判断、外部依存成立後にステップ1/4だけへ進む方針、C1・C2・C3のCodex D担当を承認した。
- C1 `auth-session-verification-contract`、C2 `tenant-match-metadata-contract`、C3 `uf3-login-screen` を別承認単位として計画化した。製品コードとcore pathは変更していない。
- U-F3正式カードはTSK-518。未着手、優先度高、依存U-F1/U-F2/U-F6/U-A1、Tコア。固有DoDを計画へ転記した。Notion担当者は識別子だけ取得できたため氏名を推測しない。
- C1はlogin後のsession結果を認証済み、401によるserver未認証、その他の結果未確認へ分ける。Cookieが変わり得る時点で旧store/cacheを破棄し、明示session再確認だけを許し、資格情報を自動再送しない案とした。
- C2はexpected tenantをoperation前に照合し、成功2xxだけにackを付け、clientが本文前にack/epoch/teamIdを検査する案とした。
- C1が正規auth clientを所有し、C3は経路未登録のLoginScreenだけを所有する。route/redirectはU-F13へ残す。
- PR #129・#132が所有するauthz/core/tenant boundary共有凍結資産は変更しない。未統合branchをdevelop基線にせず、統合状態確定後に必要差分を導出する。
- U-F13最終P1反映と後追加契約案は未再レビュー。各追補のadversarial reviewと人間承認を実装開始条件として維持する。

## 2026-10-14 追補横断adversarial review 第1周

- P0 2 / P1 6 / P2 0。全件採用した。
- P0: reload時に保存済み`bb.auth`だけで`/team`へ到達できる。C1に起動時session未検証と共有確認を追加し、U-F13 guard/APIを2xxまで待機させた。
- P0: U-F13のJSON登録だけのステップが先行登録禁止に反する。宣言はステップ1/3に残し、JSON登録をrouter/App製品変更と同じステップ2/3へ移した。総数変更は人間再承認対象とする。
- P1: login 401の共通client自動失効抑止、C2 metadataのvalidation優先、`Cache-Control: no-store`とcache再利用故障注入、mutation 5xxの結果未確認、U-F3ステップ1の基本Vitest、U-F13 researchの旧契約を是正した。
- 最終P1反映後の契約案に対する最初の再レビューとなった。反映差分を再レビューしてから承認対象を提示する。

## 2026-10-14 追補横断adversarial review 第2周

- P0 2 / P1 2 / P2 0。全件採用した。
- P0: C2の固定ackとno-storeではAの過去応答をB要求へ注入した場合にclientが判別できない。要求ごとのchallenge UUIDを追加し、serverはtenant照合後の成功2xxだけexact echo、clientは本文前にexact matchする候補へ改めた。
- P0: C1合格条件に後続U-F13の実`/team` routeが必要だった。C1はstore/client単体試験へ閉じ、実reload受入をU-F13ステップ2/3へ移した。
- P1: route登録stepと`api/auth.ts`所有の残存参照を、C1 auth client / U-F13 step2/3へ統一した。researchのteamNameをserver正規表示名へ直した。
- 基本枠2周を使い、P0が残ったためP0反映だけを第3周へ掛ける。P1反映は未再レビューとして人間確認対象に残す。

## 2026-10-14 追補横断adversarial review P0限定追加周

- 対象は第2周P0のC2 challengeとC1/U-F13試験分担だけ。P0 0で可決した。
- C2は要求ごとのchallenge UUIDを成功2xxだけでexact echoし、clientが本文前に照合するため、過去応答注入を識別できる。
- C1ステップ2はstore/client単体でgreenにでき、実`/team` guard/reload受入はU-F13ステップ2/3へ割り当て済み。
- 第2周P1の参照同期は回数上限により未再レビューであり、人間承認時の確認対象として残す。

## 2026-10-14 追補計画と3ステップ再編の一括承認

- 山田正輝が計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` のC1・C2・C3/U-F3計画とU-F13の3ステップ再編を一括承認した。各開始条件成立後も最初のステップだけを実装して停止する。
- C1はsession 2xxかつDTO検証成功時だけ認証済みとする。2xxでもDTO不正は結果未確認。`team_name`はサーバーの認可済みデータから取得し、認可・tenant照合には使わない。
- U-F13ステップ1/3はcore pathの宣言・試験だけを別コミットにする。ステップ2/3の別コミットでJSON登録とrouter/App製品変更を同時に行い、core pathだけの先行登録は行わない。
- open PR全体のpathを再照合した。#119がauth router/schema/tenant access、#129がauthz catalog/route registry等、#131と#132がcore-areasとtenant boundary凍結資産を所有中。U-F2 `authStore`とU-F6共通clientを直接変更するopen PRはなかった。
- #119はopen/behindでcore-guardとharness失敗、#129・#131・#132もopenで未統合。開始条件は未成立のため製品実装と専用worktree作成はまだ行わない。draft/merge stateは照合中にも変化したため、着手直前に再取得する。
- #129・#131・#132の未統合差分をdevelop基線にしない。個別の正本、schema、凍結資産の受理と所有確認を省略しない。
- 第2周P1追随の未再レビュー範囲は、各製品PRの人間逐行確認対象として維持する。
- #119へC1のauth router/schema/tenant access境界の契約整合レビュー、#129・#131・#132へauthz/tenant boundary/core資産の統合順と継続所有をPRコメントで照会した。各worktreeと製品差分は変更していない。

## 2026-10-14 C1 ステップ1開始条件の再照合

- C1専用branch `feature/auth-session-verification-contract` とworktree `/tmp/pitchlog-auth-session-verification-contract`を承認済み計画HEADから作成し、`origin/develop` `e6e1a867f88bbdac90f2be9bed20dff900eec866`をmergeした。
- PR #119は`8294a1b6`、PR #129は`93e1482a`で統合済み。login / logout / password、Cookie検証、`require_tenant_access`、`TenantContext`の実コードを再照合した。
- #119の発行境界は検証済み`TenantContext.tenant_id`だけを返し、C1 DTOに必要な正規`team_name`を返さない。`public.tenants.name`には既存`CAP:tenants:read`があるが、製品repository operationと`repository-contract.json`への登録は存在しない。
- routerからの直接SQLは閉じたrepository境界を迂回する。login入力のteam名は正規表示値でも認可値でもない。`authn.verify_token`の戻り型拡張は別の凍結関数契約を変更する。この3案は承認済み計画から自動選択しない。
- 最小候補をtenant表示情報read operationとした。新規repository module、`operation_registry.py`、repository契約・履歴とrepository contract試験が必要で、open Draft / conflictingの#131/#132差分と重なる。両担当から「先行統合後にC1が追加」または「担当側がoperationを供給」の統合順回答が必要である。
- `GET /auth/session`の追加にはauthentication-entry exact-setとroute / HTTP matrixの追随が必須である。`scripts/check_authz_catalog.py`、checker試験、4つのroute / matrix資産とAPI route exact-set試験が必要で、open Draft / conflictingの#137差分と重なる。#137先行統合または所有移管の回答が必要である。
- 開始条件1（計画承認）と2（#119統合・実コード再照合）は成立。開始条件3（共有凍結資産の所有確定）は未成立。開始条件4のendpoint / DTO / 認可方式は承認済みだが、正規表示名read operationという不足実装経路は個別の所有・統合順確定が必要である。
- 凍結資産検査までを一つのステップ合格条件としているため、backend製品コードだけの先行コミットは作成していない。C1ステップ1は未着手、U-F13本体もC1・C2・C3接続待ちを維持する。

## 2026-10-14 C1先行変更の所有調整

- 利用者がC1を小さな先行変更として進め、tenant profile / tenant read operationをC1が担当する方針を確定した。
- #131コメント`6171263924`、#132コメント`6171264327`、#137コメント`6171264803`で、対象ファイル、read-onlyの変更境界、C1先行統合後に各PRがdevelopへ追随する順序を提示した。
- #131/#132には、新規`tenant_profile.py`、`operation_registry.py`、repository契約・試験、必要なtenant-boundary履歴をC1が一時所有する案を提示した。既存`CAP:tenants:read`を使い、自tenant 1行の`id`/`name`だけを返す。書込・一覧・cross-tenant・汎用実行入口は追加しない。
- #137には、route registry / HTTP matrixの本体とlock、exact-set検査、必要なauthz凍結履歴とseal追随をC1が一時所有する案を提示した。追加は`ROUTE:AUTH:session:read` 1件とconditional matrix 1件に限定する。
- 2026-10-14 23:55 JST時点で受理返信はない。各既存branch/worktreeは変更していない。共有ファイルの編集は未開始で、C1ステップ1の製品コミットも未作成。
- 既存PR先行時の最小順序はrepository系とroute系を分離する。前者は#131/#132統合後、後者は#137統合後に、C1が既存方針どおり最新developをmergeして該当差分だけを適用する。rebaseを自動前提にせず、全3PRを一括待機条件にはしない。
- 7.7-1の宣言、7.7-2の一行為一記録、7.7-3のfail-closedを維持する。tenant-boundary snapshotとauthz oracle封印は別の受理単位として導出し、checkerの直書き基準追加では代用しない。

## 2026-10-15 Claude調整役への判断依頼と契約具体化

- 各担当から一時所有案への返信がないため、未回答を不受理・所有移管とせず、Claude調整役へ二択の決定を依頼した。
- Repository側は#131コメント`6171537559`と#132コメント`6171538188`。R1=C1先行、R2=#131/#132既定順先行として、担当・対象ファイル・統合順の確定を求めた。
- 認証経路側は#137コメント`6171538865`。A1=C1先行、A2=#137先行として、担当・対象ファイル・統合順の確定を求めた。
- 追随は各branchの既存方針で最新developを取り込む意味とし、rebaseを必須化しない。C1はこれまでどおりorigin/developのmergeを使用する。
- 回答待ちに`auth-session-verification-contract/research.md`を更新した。引数なし`TenantProfileReadToken`、既存`CAP:tenants:read`、`tenants.id = :tenant_id`の固定2列SELECT、`GET /auth/session`の入力なし・Cookieだけの認証、exact DTO、401/500の非漏洩境界、repository/API/7.7試験項目を具体化した。
- 共有資産、backend製品コード、既存PRのbranch/worktreeは変更していない。C1先行判断を受理した側からステップ1の依存が閉じる実装へ進み、ステップ1完了コミットは全合格条件が揃った時点で作成する。

## 2026-10-15 調整役中継後の統合待ち再分類

- Claude調整役から「共有凍結資産は既存PR先行」「#137との意味衝突なし」と中継された。C1先行の一時所有案は採用せず、各担当の未回答を不受理・所有移管とは扱わない。
- #131実差分のrepository contractはrevision 16→17とsource digestだけで、product capability/token集合に意味差分なし。C1の実装形は決めず、#132が追随する封印順の前段である。
- #132は`operation_registry.py`、repository契約schemaの`operation_guards`、capability/token exact-set、生成契約試験を実際に変更する。C1 token/operation tupleの公開面判定を決める唯一の直接回答待ちとして、コメント`6171748012`で10/15回答を確認中。
- #137のAUTH route 3件とHTTP matrixの意味はdevelopと同一。差分はrequirement digest、lock、oracle封印なので、session endpointの製品コードと固有試験を開始する意味依存ではない。正式route登録・lock・7.7履歴は#137統合後へ置く。
- 「残る待ちは#132だけ」は非共有製品コード・固有試験の開始条件として成立する。ステップ1完了条件では、#131→#132後のtenant-boundary資産と#137後のauthz資産への追随を残す。
- 計画追補候補は2点だけ: 開始条件3を所有・順序確定と共有資産編集禁止へ分解し、ステップ1内部順を非共有実装→develop merge→凍結/7.7→全検査→単一コミットと明記する。TSK-391回答後に確定し、ステップ数・DoD・正式コミット単位は変えない。
- 山田正輝がこの2点の最小追補を承認したため、C1計画へ反映した。TSK-391の公開面回答は未着のため、repository製品実装はまだ開始しない。未回答を承認・所有移管とは扱わず、予定期限超過時はClaude調整役へ中継を依頼する。

## 2026-10-15 TSK-391接続回答の受理記録

- 回答証跡はTSK-391 branchのコミット`43f8ad0114015bc415d7e7d9b58081ecfc8c4f6c`。未統合branchはC1の基線へ取り込まず、接続契約の回答だけを参照した。
- **C1**: `CAP:tenants:read`の`TenantProfileReadToken` / `TENANT_PROFILE_OPERATIONS` 1件は公開面へ登録する形で**採用**。`tenants.c.id = :tenant_id`の`:tenant_id`はrepository基底が検証済み`TenantContext`から注入する。戻り値は`TenantOperationResult`。非共有実装・固有試験を先行し、共有registry・凍結資産は#131→#132統合後に追随する。`tenants`のRLSとapplication roleのSELECT可否はC1の隔離DB試験に残す。
- **U-R1**: `read_rg1_before_d5(writer) -> bool`と`check_rg1_before_commit(writer) -> bool`、`game_id`なし、False/例外時のB7（P3はB10）と全取消を**採用**。PortWriterはどのロックよりも前に発行し、③-aを試合行ロック・D5照合前、⑧を全書込後・commit直前に呼ぶ。P1/P2/P4/P5/P3は両方、内部配信は③-aだけ。scopeのcommit/rollbackで失効し、以後の`run`/`run_function`を拒否する。
- **U-R1の条件付き項目**: `PortWriter.run_function(token)`はTSK-550のexact token型だけを同一scopeの`_TenantTransaction.run_function`へ渡す形で条件付き採用。TSK-550実行器のdevelop統合、port token契約・`port_guard.py`適合、コアレビューと人間逐行確認はU-R1新ステップ6の開始条件として維持する。
- Claude向け申し送りは今後、このコミット済み作業ログへ集約する。既存の`claude-handoff.md`は過去記録として残すが、消失した別worktreeの申し送りファイルを復元済みとは扱わない。

### A-1意図IDと実装の照合

- A-1の「イベントのD5」と実装の`event_identity`はD1付き経路では同一。`prefix_path.py`は正規UUIDの`event.d5`を`UUID`化して`record_d1_intents(scope, game_id, d5)`へ渡し、同関数は再採番・hash化せず`str(d5)`を`derive_sync_intent_id`へ渡す。
- 実装形式は`sync:<D5>:<scope_kind>`。固定`sync`は同期所有の配信行を判別する接頭辞であり、イベント識別本体はD5のまま。P3は`sync:<game_id>:<generation>:<target_d1>:<confirmed_version>:<scope_kind>`なので、D1のUUID 1成分とは構造上区別できる。
- 再送は同じD5から同じ5 IDを導出し、既存行を再読して追加しない。競合時も`pk_invalidation_intents`だけをsavepoint後に再読する。D5自体は`idempotency_ledger`の`(tenant_id, d5)`主キー、意図は`(tenant_id, intent_id)`主キーで一意である。
- 同期経路の判別は`sync:`と既知の末尾5範囲を同時に検査する。同期を通らないtokenは`sync`で始まるtrigger値を拒否し、同期・非同期意図の混在ページから同期行だけを選ぶDB試験がある。接頭辞の維持で再送時の同一性、一意性、同期経路判別は変わらない。
- よって差分はA-1の抽象表記`<トリガー>`を実装で確定した固定literalへ合わせるものに限る。最小追補候補は、A-1の形式を**`sync:<イベントのD5>:<範囲>`**へ変更し、`sync`はトリガー1/3/4の個別種別ではなく同期所有行の固定接頭辞であると注記すること。理由欄のD5一意性・再送・5範囲の説明は変更不要。data-model v0.10は導出材料をD5+範囲と定め、文字列形式を実装時確定へ残しているため、この追補だけでは正本7.3の再審査を発火させない。
- TSK-391計画は別担当・別branchの所有物なので、このbranchから変更しない。上記候補をTSK-391担当の計画追補・受理記録へ提示し、必要な計画/契約ゲートを維持する。
- TSK-391担当への提示先: PR #132コメント`6172127718`。A-1の最小追補候補、再送・一意性・同期経路判別への影響なし、正本7.3を再発火しない判定を記録した。

### C1ステップ1の非共有実装開始

- TSK-391回答により開始条件3の直接回答待ちが解消したため、承認済み内部順の(1)だけを開始した。`tenant_profile.py`、auth schema/router、C1固有のrepository/API試験を実装した。共有`operation_registry.py`、repository契約、route matrix、seal履歴、既存exact-set試験は変更していない。
- `GET /auth/session`は`require_tenant_access`が発行した`TenantContext`だけを受け、引数なし`TenantProfileReadToken`で`tenants.id`と`name`を読む。0行は固定401、複数行・列数/型不正・contextとのID不一致・空表示名は固定500。query/headerのtenant指定は入力面に持たない。
- 検証: 変更5ファイルのruff green、backend `ty check` green、新規13件green、既存login/logout/passwordを含む対象32件green。
- 共有exact-setを意図どおり未更新のため、`tests/test_api_app.py`は8件中1件だけ、`/auth/session`追加を未反映のroute exact-setで失敗する。#137統合後の共有route資産追随で更新する対象であり、検出を弱めない。
- 製品差分はステップ1完了前なので未コミット。#131→#132と#137の統合後にlatest developをmergeし、共有凍結資産・7.7・隔離DB試験・全品質gateを完了してから単一の`(ステップ 1/2)`コミットにする。

### C1非共有製品差分の保全と共有PR待ち（2026-10-15）

- A-1の表記追補はTSK-391側へ引き渡し済みとし、C1からの追加調査を終了した。以後の作業対象はC1ステップ1の完了条件だけとする。
- 未コミットの製品差分5ファイルは、受理記録のコミットと混ぜず、専用worktree`/tmp/pitchlog-auth-session-verification-contract`の作業treeに保持した。さらに同一内容を名前付きstash`C1 step1 nonshared product diff backup 2026-10-15`（object `4dce8a0e9e90990433229bfee11119c19be0306d`）へ退避してから再適用し、作業treeとstashの二経路で保全した。
- 保全対象は`backend/src/pitchlog/api/routers/auth.py`、`backend/src/pitchlog/api/schemas/auth.py`、`backend/src/pitchlog/repositories/tenant_profile.py`、`backend/tests/test_api_auth_session.py`、`backend/tests/test_tenant_profile_repository.py`。共有registry・凍結契約・route matrix・seal履歴・既存exact-set試験は含めていない。
- `git fetch origin develop`後の最新`origin/develop`は`e6e1a867f88bbdac90f2be9bed20dff900eec866`（PR #136統合）。このcommitはC1の現HEADの祖先で、追加mergeは不要だった。
- GitHub上でPR #131・#132・#137はいずれも未統合。#131と#132はtenant-boundary共有資産、#137はauthzのroute registry / HTTP matrix / seal資産を変更するため、既定の先行順を維持し、C1から共有資産を更新しない。
- route exact-setの1件失敗は未完了検出として維持する。共有PR統合後に正式な登録差分で解消し、期待集合の緩和・除外・skipは行わない。
- 次の再開点は、#131→#132および#137の統合確認、latest `origin/develop`のmerge、共有登録・凍結資産・7.7履歴、`tenants` RLS / application role SELECTを含む隔離DB試験、全品質gate、単一の`(ステップ 1/2)`コミットの順とする。ステップ2と公開は開始しない。

### TSK-538統合後のC1依存再照合（2026-10-15）

- TSK-538の対応PRは#131、developへの実統合SHAは`e2e78cfbcd8ae7bba0c1ad71263e48765c9aa860`（2026-10-15 07:02:54 UTC）。`git fetch origin develop`後、保全済み製品差分を名前付きstashへ退避し、`origin/develop`をmerge commit`418062ca92e9389597ef090c51480c0d05e3b529`で競合なく取り込み、同じ5ファイルを再適用した。
- merge直前の製品差分もstash`C1 step1 nonshared product diff before TSK-538 merge 2026-10-15`（object `0c640526c56ab854411dcc5788dbf4dfc5f46916`）として追加保全した。従来のstash`4dce8a0e9e90990433229bfee11119c19be0306d`も残している。
- TSK-538はC1の5製品ファイルを変更していない。repository contractはrevision 16→17とdigest、tenant context / runtime authzもrevision・digestが進んだが、`TenantProfileReadToken`の公開面・引数・戻り値に関わる意味契約は変わっていない。`create_app()`にdomain artifact検証が加わった影響は、C1 API試験を含む実行で問題なしと確認した。
- 取込後検証は変更5ファイルのruff green、backend `ty check` green、auth/session・login/logout・repository・app対象45件中44件green。残る1件は`/auth/session`を未登録として検出する既存route exact-setで、意図した未完了状態を維持している。
- PR #132はDraft・`CONFLICTING/DIRTY`で、head`d5c2f5953fb84470f8a537957dc2dbc6587b75df`はTSK-538統合SHAを含まない。C1が必要とする`operation_registry.py`、repository contractとtenant-boundary 7.7再封印を所有するため、統合と最新基線追随を待つ。
- PR #137もDraft・`CONFLICTING/DIRTY`で、head`1eac40d70caa6bf5edb69312aedbe8b61279edbe`はTSK-538統合SHAを含まない。route registry、HTTP matrix、lock / seal資産を所有するため、C1の`GET /auth/session`登録と7.7確認は同PR統合後に行う。
- 現時点で進められた作業は、TSK-538取込、製品差分の再適用、意味差分照合、非共有のlint・型・固有回帰試験まで。operation登録に依存する隔離DB試験、共有凍結資産、route exact-set解消、全検査、ステップ1製品コミットは#132・#137統合後に続ける。既済みの計画承認・担当受理に変更はなく、新たな人間判断は発生していない。

### C1固有route exact-setの所有確定と検証完了（2026-10-15）

- `/auth/session`の製品実装は承認済みC1計画のbackend範囲。`backend/tests/test_api_app.py`と`backend/tests/test_api_conventions.py`の静的route exact-setは、#132・#137のいずれも変更しておらず、C1経路追加に直接追随する試験としてC1が所有する。`GET /auth/session`と`auth_session_read`を期待集合へ追加し、経路数を16→17へ厳密に更新した。除外・skip・部分集合比較への変更は行っていない。
- `AuthSessionResponse`の`Session`をDB接続型の禁止語と誤認した既存規約試験は、禁止識別子を単語境界で判定するよう修正した。禁止語7件それぞれの負例を追加し、実際の`Session`・`sqlalchemy`・`engine`・`session.execute`等を拒否する能力を維持した。
- C1固有差分7ファイルに対し、ruff green、backend `ty check` green、auth exit / login / session / tenant profile repository / app / API conventionsの59件green、`git diff --check` green。従来のroute exact-set失敗は正式なC1期待値追随により解消した。
- 現在の7ファイルはworktreeへ未コミットで保持し、名前付きstash`C1 step1 specific implementation with route exact set 2026-10-15`（object `d4be5f1f6e252cc490baa18b7e5686d4c92fb099`）にも同一内容を保全した。
- C1固有実装とDB不要の固有検証は完了。残る依存は、#132統合後の`TENANT_PROFILE_OPERATIONS`共有registry登録・tenant-boundary 7.7再封印・隔離DBでのRLS/application role SELECT確認と、#137統合後のauthz route registry / HTTP matrix / lock / seal追随。その後に全品質gateと単一の`(ステップ 1/2)`コミットを行う。現時点ではステップ1未完了のためPR作成不可。

### C1共有資産追随の事前準備（2026-10-15）

- 再確認時点でPR #132はDraft・`CONFLICTING/DIRTY`（head `0297a8dacce2135834a54c995d0a4167c5ac5c98`）、PR #137はDraft・`MERGEABLE/BLOCKED`（head `dffe108cec6b916c938e63cc4d1fd4e3b4399f5a`）で、いずれも未統合。共有資産の編集再開条件は成立していない。PR headのrevisionやdigestは候補値としても転記せず、統合後の`origin/develop`を唯一の比較元にする。
- `git fetch origin develop`後の先端は`9b8f9bc689fb70dc9d084fbad9758bf4b3c353fb`（PR #139統合）で、C1 branchは5コミット遅れている。#132/#137をどちらも含まないため今回はmergeせず、両PR統合確認後にその時点のlatest developを一度取り込む。
- C1固有差分7ファイルはworktreeに保持され、stash `d4be5f1f6e252cc490baa18b7e5686d4c92fb099`にも保全済み。共有資産の準備調査ではこれらを変更していない。

#### #132統合後のrepository / tenant-boundary追随

1. `git fetch origin develop`後、PR #132のmerge SHAが`origin/develop`の祖先であることを確認し、C1 branchへ既存方針どおりmergeする。競合時は`operation_registry.py`、`repository_contract.py`、repository契約試験、tenant-boundary資産を意味単位で照合し、PR headのrevisionをそのまま採用しない。
2. `backend/src/pitchlog/repositories/operation_registry.py`へ`TENANT_PROFILE_OPERATIONS`をimportし、`PRODUCT_OPERATIONS`へ1組だけ追加する。`TenantProfileReadToken`は既存`CAP:tenants:read`を再利用し、caller指定tenant、任意SQL、一覧・書込operationを増やさない。
3. 統合後の生成契約の現在値から、`backend/src/pitchlog/repositories/repository_contract.py`、`contracts/tenant_boundary/repository-contract.json`、`backend/tests/test_authz_repository_contract.py`のcapability/token/registry exact-setを同時に追随する。capabilityは既存値なので重複追加せず、token型`pitchlog.repositories.tenant_profile.TenantProfileReadToken`だけを対応するregistry位置へ追加する。#132で導入される`operation_guards`を保持する。
4. 変更したtenant-boundary資産のrevisionと`source_digest`を統合後の値から1受理分だけ進める。`runtime-authz-contract.json`等は実差分が生成された場合だけ対象にし、無関係な全資産を機械的に版上げしない。
5. `base-allowlist.json`を唯一の`history_authority`として、`runtime_contract_acceptance`が出す実差分由来のv2記録と不足snapshotをappend-onlyで追加する。旧履歴・旧snapshotは変更しない。比較元、previous/new identifiers、外部資産digestは統合後に再計測する。
6. `uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`、凍結履歴・archive・repository契約の負例を含む試験で、未登録token、digest不一致、履歴欠落、snapshot欠落が引き続き拒否されることを確認する。

`.claude/core-areas.json`のtenant-isolationには`backend/src/pitchlog/repositories/*`、`backend/src/pitchlog/api/*`、`backend/tests/test_api_*.py`、`backend/tests/test_*_repository.py`、`contracts/tenant_boundary/*`が既に含まれる。C1の既知パスを検出するための登録追加は不要で、#132/#137の同ファイル差分へC1から触れない。

#### #137統合後のauthz route / HTTP matrix / seal追随

1. PR #137のmerge SHAと`origin/develop`包含を確認し、latest developをmergeした後の認可資産を比較元にする。#137のrequirement digest、route/matrix lock、oracle sealを先に着地した既存値として保持する。
2. `contracts/authz/route-registry.json`へ`ROUTE:AUTH:session:read`を`authentication_entry`、`design` origin、C1計画由来として1件登録する。既存login/logout/password 3件と他経路を変更しない。
3. `contracts/authz/http-route-matrix.json`へ`HTTP:ROUTE:AUTH:session:read`、対応route ID、`conditional` disposition、TSK-528/C1の試験所有を1件登録する。method/path/operation IDの実API exact-setは既にC1試験で`GET /auth/session` / `auth_session_read`として固定済み。
4. `scripts/check_authz_catalog.py --reseal-derived`で`route-registry.lock.json`と`http-route-matrix.lock.json`を再導出し、session 1件以外の意味差分がないことを確認する。検査器の列挙、route kind、dispositionを広げる変更は不要である。
5. route registry変更はoracle入力を動かすため、第1段の実コミットSHAを`oracle_commit` 7箇所へ反映し、入力blob digestを追随する。人間逐行確認後に`frozen-baselines.json`の`oracle_input`へ1受理記録をappendし、`--reseal-oracle`で再封印する。履歴上の旧commit識別値は書き換えない。
6. `uv run python scripts/check_authz_catalog.py`、`uv run python scripts/check_frozen_baselines.py --invariants-only`、関連checker試験で、未登録route、derived lock不一致、oracle digest不一致、受理履歴欠落、人間確認なしの再封印を引き続き拒否する。

authzの`frozen-baselines.json`は`acceptance_id_source=repository_and_pr_number`、tenant-boundaryの受理CLIも`owner/repository#number`を要求する。現行計画はステップ1を単一コミットとし、利用者指示は全条件成立前のPR作成を禁止しているため、最終受理記録にはPR番号を先に得られない循環がある。共有差分の準備と`--reseal-derived`前までを進めた後、完了コミット/PR前に、既存の3段再封印手順に沿うDraft PR先行を今回だけ許可するかを人間判断対象として提示する。仮番号、`PENDING_ACCEPTANCE`、他PR番号の流用は行わない。

#### 隔離PostgreSQLのRLS / application role試験条件

- 正本には`CAP:tenants:read`、`POLICY:tenants:self_tenant_row`、`pitchlog_app`への`tenants`表SELECT、RLS enabled/forcedが既にある。C1はACLやmigrationを追加せず、その既存契約が`name`列を含む実行経路で成立することを証明する。
- `ProvisionedProductCatalog`の隔離DBへ異なる名称のtenant A/Bを外部適用主体で投入する。実際の`pitchlog_app`接続、または同roleへ切り替えたSQLAlchemy sessionで、検証済み`TenantContext(A)`と登録済み`TenantProfileReadToken()`を`tenant_transaction_scope`から実行し、exact `(A, nameA)` 1行だけを得る。Bでも対称に確認する。
- A文脈でBのID・名称が返らないこと、tokenにtenantを指定する入力面がないこと、文脈未設定/不正時に読み取れないことを確認する。`current_user`、RLS enabled/forced、SELECT privilegeも同じ隔離DBで実測し、管理者接続だけの成功を証跡にしない。
- endpoint側では0行を固定401、複数行・shape/type不正・文脈ID不一致を非漏洩の固定500とする既存固有試験を維持する。DB試験はregistry登録後に実製品operationを通し、手書きSELECTだけで代用しない。

#### latest develop統合後の全品質gate

1. 差分検査: `git diff --check`、変更対象と計画scopeの照合、7ファイル保全stashとの内容照合。
2. backend: `cd backend && uv run ruff format --check . && uv run ruff check . && uv run ty check && uv run pytest -c pyproject.toml --cov`。隔離DBの新規C1試験が収集・実行された件数を別記する。Alembic差分は作らないがCIと同じ`uv run alembic upgrade head`、`uv run alembic current --check-heads`、`uv run alembic check`も実行する。
3. repository / tenant-boundary: repository契約・登録・C1 DB試験の対象pytest、`uv run python scripts/check_tenant_boundary_bypass.py --base-ref origin/develop`、`uv run pytest tests/test_check_tenant_boundary_bypass.py tests/test_frozen_history.py tests/test_frozen_archive.py tests/test_frozen_archive_case_runner.py tests/test_census_baseline_check.py`。
4. authz / 7.7: `uv run python scripts/check_authz_catalog.py`、`uv run pytest tests/test_check_authz_catalog.py`、`uv run python scripts/check_frozen_baselines.py --invariants-only`。PR番号と人間逐行確認後はCI相当の`--ci`でイベント由来acceptance IDも確認する。
5. root harness: `uv run ruff check .`、`uv run ty check`、CIと同じ除外条件のroot pytest、design/doc checker、`scripts/core_guard.py`。core-guardはtenant-isolationとしてC1製品・契約・DB試験を検出し、人間逐行確認欄が未記入なら拒否する状態を維持する。
6. PR作成後にGitHub CIのsecrets、docs-lint、core-guard、harness、consistency、mutation、tenant-boundary-bypass、backend各jobを確認する。人間逐行確認は第2周P1未再レビュー範囲、tenant profile readのRLS/ACL実測、route/matrix 1件、tenant-boundary履歴、oracle入力・sealを対象とし、未実施のチェックを代記しない。

以上は再開手順の固定であり、共有資産、ステップ2、公開経路を実装した記録ではない。#132・#137の統合確認まではC1ステップ1を未完了のまま保持する。

### Draft PR先行に必要なC1最小追補案（2026-10-15・未承認）

#### 正本との照合

- 6.1の通常サイクルは、ステップの実装・検証・正本追随が完了した後にPRを作り、1ステップごとに1コミットを作る。通常の`/pr`はworklogを締め、planを`in-review`へ移す。
- 6.3により、C1はテナント分離のコア領域であり、最終PR差分に反対側一次レビュー、敵対レビュー、人間逐行確認が必要である。Draft作成はこれらの完了や代替にならない。
- 7.7自体は受理単位を固定しないが、authzの`frozen-baselines.json`はGitHubのrepository/PR番号、tenant-boundaryの受理CLIも`owner/repository#number`を受理IDに要求する。さらにauthz oracleは入力資産を確定した先行コミットSHAを識別値として持つ。この資産固有契約により、C1ステップ1を単一コミットのまま正式受理することはできない。
- したがって正本6.1/6.3/7.7の本文改訂や7.3確定ゲートは不要で、C1計画6節・7節・10節だけに限定した例外追補が必要である。既存のendpoint、DTO、認可、DoD、ステップ数、ステップ2の未着手、公開禁止は変更しない。

#### 計画へ反映する最小差分

1. ステップ1を、凍結資産の自己参照を閉じるための3段・3コミットへ限定分割する。件名はそれぞれ`(ステップ 1/2 第1段)`、`(ステップ 1/2 第2段)`、`(ステップ 1/2 第3段)`を1個だけ含める。`feature_status.py`は異なるコミットの同一ステップ番号を再委任として扱えるが、6.1の1ステップ1コミットに対するC1固有例外であることを計画本文へ明記する。
2. **第1段**: #132/#137統合後のlatest develop、保全済みC1製品差分、`TENANT_PROFILE_OPERATIONS`登録、repository契約、route registry / HTTP matrix、derived lock、隔離DB試験と実行可能な品質検査をまとめる。未受理履歴を仮値で埋めず、PR番号依存・oracle commit依存の検査はfail-closedの未完了として記録する。
3. **第2段**: 第1段の実コミットSHAをauthzの`oracle_commit` 7箇所へ反映し、入力blob digestを追随する。履歴・sealはまだ正式受理せず、旧履歴を書き換えない。
4. 第2段までをpushしてDraft PRを作り、実PR番号を取得する。このpush/PRは別途明示承認後にだけ行う。Draft本文へ「C1ステップ1未完了」「7.7第3段待ち」「CI/レビュー/人間逐行確認未完了」を明記する。通常の`/pr`完了処理ではないため、planは`active`、worklogは進行中、TSK-528は未完了のまま維持し、Draft解除・マージを禁止する。
5. **第3段**: 実PR番号を用い、tenant-boundaryのv2受理記録・不足snapshotとauthzの`oracle_input`記録を候補化する。人間が実差分のprevious/new identifiers、変更理由、承認者・承認日、oracle入力・sealを逐行確認して正式受理した後だけ、`--reseal-oracle`を実行して第3段コミットを作る。仮番号、`PENDING_ACCEPTANCE`、他PR番号、事前の包括承認は使わない。
6. 第3段後に全品質gate、CI、反対側レビュー、コア敵対レビュー、人間逐行確認を行う。全条件成立後に通常の`/pr`完了処理としてplanを`in-review`へ移し、PR本文を最終化する。Draft解除とマージは別の人間判断に残す。

#### 品質gateの分割

- Draft前にgreenを要求するもの: C1対象ruff/format/ty、固有/API/repository試験、実製品operationを通す隔離DBのA/B RLS試験、route/matrixとrepository exact-set、`git diff --check`、実行可能なroot/backend品質gate。
- Draft前に未完了を明示してよいもの: PR eventの実番号を要求するtenant-boundary正式受理、`check_frozen_baselines.py --ci`、人間受理後の`--reseal-oracle`、最終core-guard、PR CI。検査をskip・除外・期待値緩和でgreenにしない。
- 第3段後にgreenを要求するもの: tenant-boundary bypass/history/archive、authz catalog、frozen baseline invariantsとPR event検査、root/backend全件、core-guard、GitHub CI。DB試験が収集・実行された件数も記録する。

#### 必要な承認

1. **計画レビュー追加枠のPO裁定**: C1計画は基本2回+P0例外の3回を使用済みなので、6.3に従い、上記追補差分と影響節（計画6・7・10節）に限定した敵対レビュー1回を追加する裁定が必要。
2. **追補の人間承認**: 追加レビューの採否と最終差分を確認し、3段コミット、Draft先行、Draft中の`active`維持、品質gate分割をC1だけの例外として承認する必要がある。
3. **push / Draft PR作成承認**: 第1・第2段とDraft本文を提示した後、実際のpushとDraft作成を別途承認する必要がある。現時点では未許可。
4. **7.7正式受理**: PR番号取得後の実際の受理記録・snapshot・oracle差分に対し、承認者・承認日を含む人間逐行確認が必要。計画追補の承認では代替しない。
5. **コアPRのレビューと逐行確認**: 第3段後の最終差分に対する反対側一次レビュー、敵対レビュー、人間逐行確認が必要。Claude経路が利用できない場合、過去PRへの代替許可を流用せず、C1 PRに限定した代替レビュア承認を得る。未実施チェックは代記しない。

PR #132と#137は本記録時点でも未統合であり、追補承認後も共有資産の実装再開条件は未成立である。新規ACL・migration、凍結対象・比較述語・検査器の緩和は追補範囲に含めない。

### PR #137統合後の認証経路側追随（2026-10-15）

- TSK-238の対応PR #137は2026-10-15 11:32:45 UTCに統合された。PR headは`dffe108cec6b916c938e63cc4d1fd4e3b4399f5a`、developへの実統合SHAは`f36d0fee81479d75861ecbbfc8c2218adaaf8227`である。`git fetch origin develop`後、C1差分をstash`C1 step1 seven-file diff before TSK-238 merge 2026-10-15`（object `e2cb7e9753ad663b36a495ae5e5f46815dbe39ef`）へ保全し、`origin/develop`をmerge commit`db3eb598b48c6ba2fdd2d2e41db351c8db62e145`で競合なく取り込んだ。
- 再適用後のC1製品・固有試験7ファイルはstash内容とファイル単位SHA-256がすべて一致した。#137はこれら7ファイルを変更せず、影響はauthz route registry / HTTP matrix、その派生lock、oracle入力・sealと関連要件資産に限られる。
- #137の正式受理後を比較元として、`ROUTE:AUTH:session:read`を`authentication_entry` / `design` originで、`HTTP:ROUTE:AUTH:session:read`を`conditional` / TSK-528.C1試験所有で候補登録した。派生lockは`--reseal-derived`で再導出し、route registryは244→245件、HTTP matrixは59→60件となった。既存3認証経路その他の行は変更していない。
- 実コード照合により、`scripts/check_authz_catalog.py`が認証入口を3経路のexact-setとして固定していることが判明した。C1経路を加えた4経路exact-setへ追随し、対応する正例・未宣言追加拒否試験とfixtureだけを更新した。部分集合化、除外、skip、route kind / dispositionの許容拡大は行っていない。事前準備記録の「検査器の列挙変更は不要」はこの実コード差分で訂正する。
- fixtureの設計出所を既存の要件入力へ偽装せず、`auth-session-plan.md`へ分離して逐語一致を検証し、fixtureのroute registry派生lockも再導出した。個別検証は、新しい4経路集合と未宣言経路拒否の2件green、変更checker/testのruff green、`git diff --check` green、frozen baseline invariants green。oracle sealを直接検証する既知2件だけを分離したauthz catalogは25,818件greenである。直接検証2件はどちらも`route-registry.json: oracle input blob が不一致`でfail-closedとなることを確認した。正式な`oracle_commit`、`frozen-baselines.json`、`oracle-seal.lock.json`は未変更であり、7.7人間受理前の期待状態である。
- 認証経路側で現時点まで進められるのは、route / matrix候補、派生lock、strict checkerと試験の追随までである。製品7ファイルと検証済み認証経路候補をまとめた名前付きstash`C1 step1 product and validated auth route candidate after TSK-238 merge 2026-10-15`（object `27b0081773c955cb33cd29ec3ce3bca64f82415f`）を作成してから作業treeへ再適用した。oracle commit・受理履歴・sealの正式更新、製品コミット、push、Draft PRは未承認の3段追補と7.7確認に残す。
- repository側はPR #132が引き続きDraft・`DIRTY`（head `0297a8dacce2135834a54c995d0a4167c5ac5c98`）であり、`TENANT_PROFILE_OPERATIONS`登録、repository contract、tenant-boundary履歴・snapshot、隔離DBの実製品operation試験は統合待ちのまま分離する。#137統合を理由に#132の未統合差分を基線へ採らない。
- 既済みのC1計画承認・担当受理は維持する。今回新たに必要と判明した人間確認対象は、4経路exact-setへ追随するchecker/test差分を、route / matrix 1件とともにコア敵対レビュー・逐行確認へ含めることだけである。新規ACL・migration、ステップ2、公開経路には進んでいない。

### PR #132統合後のC1ステップ1再開（2026-10-16）

#### 統合基線と差分保全

- TSK-391の対応PR #132は2026-10-15 15:51:20 UTCに統合された。PR headは`afb8b08f2d89107603d848eae8c98dcd0c2e59a6`、developへの実統合SHAは`966d7a38aa8dab2113c1d8ec6d30e5d32088ede5`である。
- `git fetch origin develop`後、C1候補をstash`C1 step1 validated candidate before TSK-391 merge 2026-10-16`（object `229fcd0921a45b776d329fffc4af0ccee4f8aa33`）へ保全し、`origin/develop`をmerge commit`02f08626faba6683932d4eb11562e3c89e3b3db0`で競合なく取り込んだ。再適用後もC1製品・認証経路候補は維持された。
- #132統合後の共有追随とDB証跡を加えた現候補もstash`C1 step1 shared contracts and DB evidence after TSK-391 merge 2026-10-16`（object `be185a5e28d6df57d9e766d558c9eba8e0599bd2`）へ保全し、同じ内容を作業treeへ再適用した。既存PRのbranch/worktreeは変更していない。

#### 共有operation・repository契約・tenant-boundary追随

- `TenantProfileReadToken` / `TENANT_PROFILE_OPERATIONS`を製品registryへ1件登録した。既存`CAP:tenants:read`だけを使用し、呼出元がtenant ID、SQL、列、並び順を指定する入力面はない。固定SELECTは検証済み`TenantContext`から基底が注入する`:tenant_id`で`tenants.id`と`tenants.name`だけを読む。
- repository契約をrevision 18→19へ進め、公開capabilityに`CAP:tenants:read`、公開token型に`pitchlog.repositories.tenant_profile.TenantProfileReadToken`を各1件追記した。生成Python契約を同じ集合へ追随し、source digestは`4248511d1135ff0082b2276a199f7829f3cd8ebc91e11e48efc29a916eb9a8ea`で一致する。
- base allowlistをrevision 30→31へ進め、`pitchlog.repositories.tenant_profile._tenant_profile_statement() -> Select[Any]`の`SQLA_SELECT`だけを正例fixture付きで登録した。既存条件・禁止API・検査器の許容範囲は広げていない。
- 新規ACL・migrationは追加していない。#132が供給した既存repository基底、operation guard、`tenants`のRLS/ACLをそのまま再利用した。

#### 隔離DB証跡

- `backend/tests/db/test_tenant_profile_repository_boundary.py`にDB必須試験2件を追加した。隔離PostgreSQLへ異なる名称のtenant A/Bを作り、実`pitchlog_app`資格情報の同時2接続で、`current_user=pitchlog_app`、`tenants`へのSELECT可、RLS enabled/forced、A/B各接続で自tenant 1行だけ、tenant文脈なしで0行を確認した。
- 同じ隔離DBで`tenant_transaction_scope(make_tenant_context(...))`と登録済み`TenantProfileReadToken()`を通し、A/BのID・名称が各1行だけ返り、存在しない検証済みtenantは0行になることを確認した。手書きSELECTだけを製品operationの証跡にはしていない。
- 対象DB試験は2件収集・2件成功。使い捨てcluster外のACL、role、migrationは変更していない。

#### 検査結果とfail-closedの残り

- C1固有/API/repository/共有契約の対象試験は186件成功。共有契約群の先行実行は149件成功。backendのRuff、format check、ty、rootのRuff、ty、`git diff --check`は成功した。
- backend全件は`2458 passed, 4 skipped, 5 failed`。4件はworktreeの`node_modules`にtypescriptが無かった環境要因で、`pnpm install --frozen-lockfile`後に同4件を再実行して成功した。残る1件は未受理のroute registry blobを既存authz oracle sealが拒否する`test_frozen_oracle_paths_have_no_branch_diff`であり、7.7第3段前の期待どおりのfail-closedである。
- root全件は`29579 passed, 2 skipped, 40 failed`。失敗は、authz oracle入力/seal未受理、tenant-boundary履歴末尾がbase 31 / repository 19へ未追随、正式snapshot未配置、archive corpus未再封印という正式受理前の4系統に限られる。試験除外、期待値緩和、skip追加は行っていない。
- `alembic upgrade/current/check`の直接CLIは`PITCHLOG_MIGRATION_DATABASE_URL`未設定のため開始前に拒否された。`.env`は参照せず、新規migrationもない。GitHub CIまたは明示した使い捨てmigration URLで最終確認する。`core_guard.py`はPRイベント不在を検出してskipしたため、Draft PR取得後に実イベントで人間逐行確認未記入の拒否を確認する。

#### 7.7正式受理へ出す実値

- tenant-boundaryのprevious/new識別値で変わるのは、`base-allowlist.json`の`contract_revision:30`→`contract_revision:31`と`repository-contract.json`の`contract_revision:18`→`contract_revision:19`だけである。cache 14、census 13、DB inventory 14、frozen inputs 4、negative fixtures 16、runtime authz 15、tenant context 15は不変である。
- 受理aspectは`asset_snapshots`と`declaration`。不足snapshotは、repository契約projection `2b5e271498149e09e4d885faab9b58c8cee5cfc7ef2c434eaef7d25bd1592cb5`（7000 bytes）とbase allowlist projection `667c1103b6202dc5f9ce282860d70d6ab2a6aa1af64b8d3cb8dfc82650798840`（10860 bytes）の2件である。
- tenant-boundaryの正式record理由案は「C1で検証済みtenantの表示情報を既存CAP:tenants:readの固定operationとして登録し、repository契約とDB API許可境界を追随する。」、movement fact案は「base-allowlist.jsonはcontract_revision 30から31、repository-contract.jsonは18から19へ移動した。他のtenant-boundary識別値は不変。」とする。
- authzの現行`oracle_commit`は7資産すべて`62fdfe81de7029d49b2b5d80683f49b2dce3e327`。C1候補のGit blobはroute registry `2cd82db822df203d9608b6d72e4bbfb518dab2ad`、そのlock `e110a75541cca22d349fe6f765e7b8c7ba741e64`、HTTP matrix `c2d03ad51a9d1961e1fdf5c5730e4705acf6907e`、そのlock `5882c2b918ed8d06feb12fa905434d916b685c7f`である。routeは244→245、matrixは59→60で、追加は`GET /auth/session` 1件だけである。
- authz受理recordのprior identityは上記`62fdfe81...`、new identityは第1段の実コミットSHA、acceptance IDは実C1 PR番号とする。placementと同一性の解釈は不変、履歴はappend only、受理後に`--reseal-oracle`でsealを導出する。tenant-boundary recordの`acceptance_id`、`approved_by`、`approved_on`も同じ実PRと実確認値にする。
- `/tmp/c1-tenant-boundary-acceptance-preview.json`は候補導出だけに使用し、仮番号`#999999`、`DRYRUN`、`1970-01-01`を含むため正式資産へ取り込まない。archive corpus digestは実record metadataを含む第3段で再導出し、暫定値をpinしない。

#### 一括判断が必要な最小例外

- 資産固有契約が「authz入力を確定した先行コミットSHA」と「GitHubの実repository/PR番号」を要求するため、通常の1ステップ1コミット・ステップ完了後PR作成では自己参照を閉じられない。2026-10-15のC1最小追補案どおり、ステップ1だけを第1段（製品・共有契約・derived lock・DB試験）、第2段（第1段SHAを7つの`oracle_commit`へ反映）、第3段（実PR番号によるtenant/authz受理履歴・snapshot・seal・archive再封印）の3コミットへ分ける必要がある。
- 一度に必要な人間判断は、(1) 既存3周を越えてこの追補差分だけを対象に敵対レビュー1回を追加するPO裁定、(2) C1限定の3段コミット、Draft先行、Draft中のplan `active`維持、品質gate分割の承認、(3) 第1・第2段のコミットとpush、実番号取得だけを目的とするDraft PR作成の許可、の3点である。
- 上記が承認された後も、実PR番号入り第3段候補に対する7.7逐行受理、最終差分の反対側レビュー・コア敵対レビュー・人間逐行確認は省略しない。Draft解除、C2、U-F3、U-F13公開、マージはこの例外に含めない。

### C1限定3段追補の承認・追加独立レビュー（2026-10-16）

- 山田正輝が、追補差分と計画6・7・10節に限定した追加独立レビュー1回、C1ステップ1限定の3段コミット、Draft中のplan `active`維持、第1・第2段のコミット・push・実番号取得用Draft PRまでを一括承認した。第3段の正式7.7受理、人間逐行確認、Draft解除、マージは未承認のまま維持する。正式な承認者・承認日は第3段の正式受理前に入力しない。
- 追加独立レビューはP0 0 / P1 2 / P2 0。P1-1は共有実行器A→C1の順と再導出条件が計画へ未反映、P1-2は`test_api_conventions.py`が禁止DB語彙の部分一致をword boundaryへ弱めたこと。追加仕様・権限・承認範囲の変更を要する指摘はなかった。
- P1-2は、従来の部分一致拒否を復元し、承認済みDTO識別子`AuthSessionResponse`だけを単語境界で除外する形へ修正した。`AsyncSession`、`DatabaseSession`、`sqlalchemy_session`、`db_engine`、`sqlalchemy2`、DTO後続の`Session.execute`を拒否する回帰試験を追加した。対象21件、Ruff check、format checkはすべて成功した。
- 同じ独立レビュアが修正差分を再確認し、P1-1/P1-2とも収束、新たなP1なしと判定した。第1段の開始条件がPR #141の再基線化・正式統合後の再導出であることも確認した。
- 共有実行器AのPR #141はhead `0b203dcdd5831c881943657ec915dc96fc3724a4`、Draft、`CONFLICTING/DIRTY`で、PR #132統合後のdevelopへ未追随である。C1と`operation_registry.py`、生成repository契約、repository exact-set試験、base allowlist、repository契約、tenant-boundary履歴・snapshot・archive corpusが重なる。
- PR #141コメント`6197437468`でA→C1の順を担当へ提示した。Aが#132統合後のlatest developへ追随し、必要な再受理・検査を終えて先に統合された後、その実merge SHAを含む`origin/develop`をC1へmergeする。#141側の受理記録への反映を依頼し、意味衝突や別順序が必要な場合は重複ファイルと最小差分の返信を求めた。
- 前節に記録したC1のrepository 18→19、base allowlist 30→31、2件のsnapshot hashは、#132直後基線に対する導出確認値であり、第3段の正式候補値ではない。A統合後の確定revision・履歴をbeforeとしてC1のrevision、source digest、snapshot、previous/new identifiersを再導出するまで第1段コミットを作らない。異なるbranchの同じrevision番号を同一内容として扱わない。
- 3段追補、A→C1順、追加独立レビューとP1採用を計画へ反映した。P1修正後のC1製品候補は作業treeとstash `0100de2077257aafd8b5e11c14957894687f6cd2`に保全されている。現時点の残る開始条件はPR #141の再基線化・正式統合だけで、C2、U-F3、公開には進んでいない。

### 共有実行器A統合後の第1段再導出（2026-10-16）

- 共有実行器Aの対応PR #141は2026-10-15 21:01:27 UTCに統合された。PR headは`f06a3dc7c61dc9c274ea3485e8d25031fcaa66b7`、developへの実統合SHAは`e7e8d3a4324687ada828b1e4b49692c087af5c44`である。
- P1修正済みC1候補をstash`C1 step1 reviewed candidate before shared executor A merge 2026-10-16`（object `5b4cb306fbbd3cc78e3e883982618d9aca1acf36`）へ保全し、`origin/develop`を競合なくmergeした。C1候補の再適用時は、`repository_contract.py`、`base-allowlist.json`、`repository-contract.json`の3ファイルだけが内容競合した。
- 競合3ファイルはA側を基準に解消した。Aの固定関数公開面、`PRODUCT_FUNCTION_OPERATIONS`空集合、関数実行器、許可シンボル2件、受理履歴・snapshotを保持し、その後にC1の`TenantProfileReadToken`、既存`CAP:tenants:read`、tenant profile固定SELECTの許可シンボル1件を追加した。
- A確定値をbeforeとして、repository契約はrevision 19→20、base allowlistは31→32へ直列化した。repository source digestは`22ecaa00ad393d2c7695ec53f68fdd23239ada64e293d070fda7793087a0a3b6`で、生成Python契約と一致する。
- A統合後のtenant-boundary previewでは、変わる識別値はbase allowlist 31→32とrepository contract 19→20だけである。cache 15、census 14、DB inventory 15、frozen inputs 4、negative fixtures 17、runtime authz 16、tenant context 16は不変である。
- 不足snapshotはbase allowlist projection `20c8f0f71734d244e8734a0ded0903d380cfcae79315549ccd318a8a6e6ebabf`（11578 bytes）とrepository contract projection `71cb7a8bba95d335571411198044da40b1ac05d06707a9c34a9fb396bf6c2a00`（7527 bytes）の2件で、base64復号後のSHA-256一致を確認した。
- 検証は、C1 API/repository/共有契約193件、隔離PostgreSQLのRLS/application role 2接続試験2件、backend対象Ruff/format/ty、root Ruff/ty、`git diff --check`が成功した。authz全変異試験は25818件成功・2件失敗で、2件とも未受理route registryと既存oracle sealのblob不一致。tenant-boundary全検査は367件成功・3件失敗で、3件ともauthority履歴末尾がbase 31 / repository 19のままであることを拒否した。期待値・検査器・skipは緩和していない。
- `/tmp/c1-tenant-boundary-acceptance-after-a-preview.json`は、仮PR番号・`DRYRUN`・`1970-01-01`を含む導出確認専用であり、正式資産へ取り込まない。正式受理の理由・movement factは前回案を維持し、識別値だけをA後の値へ更新する。

### C1ステップ1 第1段・第2段（2026-10-16）

- 第1段コミットは`d5ccc18ef39179857c9a4c793ea28a416432efba`。C1製品、共有operation、A後のrepository契約・base allowlist、route/matrix候補、derived lock、strict checker、隔離DB試験、作業記録の25ファイルを含む。件名は`(ステップ 1/2 第1段)`で、正式7.7履歴・snapshot・oracle sealは未受理のまま保持した。
- 第2段では、authz 6 oracle資産と`oracle-seal.lock.json`の計7箇所の`oracle_commit`を旧`62fdfe81de7029d49b2b5d80683f49b2dce3e327`から第1段SHAへ更新した。
- sealの入力blobは、route registry `2cd82db822df203d9608b6d72e4bbfb518dab2ad`、同lock `e110a75541cca22d349fe6f765e7b8c7ba741e64`、HTTP matrix `c2d03ad51a9d1961e1fdf5c5730e4705acf6907e`、同lock `5882c2b918ed8d06feb12fa905434d916b685c7f`へ追随した。
- 第2段ではsealed asset canonical digest、`frozen-baselines.json`の受理履歴、tenant-boundary authority履歴・snapshot、archive corpusを更新しない。第3段の正式受理前なので、authz sealとtenant-boundary履歴検査は引き続きfail-closedになる。
- 第2段後のbackend全件は`2271 passed / 1 failed / 254 errors`だった。1件は未受理oracle入力を既存sealが拒否する期待どおりのfail-closedであり、254件は並行実行中に共有pytest一時領域`/tmp/pytest-of-ymdms/pytest-550`が消失した同一の`FileNotFoundError`だった。消失時にerrorとなったdomain host、authz generator、descriptor parity、migration hygiene、wording scanの代表27件をC1専用`--basetemp`で再実行し、27件すべて成功した。製品/API/repository/隔離DBの対象検査は前節の成功状態を維持する。
- 第2段後のroot全件はC1専用`--basetemp`で`29559 passed / 2 skipped / 79 failed`。失敗は、第2段で先に更新した7資産の`oracle_commit`と未更新のoracle baseline/sealの不一致、tenant-boundary authority履歴末尾がbase 31 / repository 19のままである不一致、正式snapshot未配置、それらを入力にするarchive corpus未再封印の連鎖である。第3段の7.7正式受理・再封印で解消すべき未通過項目として保持し、検査除外・skip・期待値緩和は行っていない。
- Draft前の正本突合で、C1計画に`影響する正本`節がなく機械検査が開始前拒否したため、正本改訂なしと同一PRで運ぶ正本体系外資産を明記した。製品仕様・権限・ステップ・7.7候補値は変更していない。

### C1とU-R1の統合順・7.7正式判断資料（2026-10-16）

- PO調整役はPR #144コメント`6209131420`で、C1 / PR #144の正式受理・統合を先行し、U-R1 / PR #143が受理済み履歴と実merge SHAを含むdevelopから再導出する順序を固定した。C1はPR #143コメント`6209084415`で同じ順序を受領し、技術上の阻害差分がないことを確認した。
- U-R1のC1統合前候補はbase allowlist 31→32、repository contract 19→20でC1とrevision番号が同じだが、snapshotは`699ee0ed84cd98ff5dbf83c6f8bb474b33db372be438136f38417a0a166cae23` / `fe307e0cd718fbc505549681c80459ee0413c4a09bd99400a56fdd3df7bba925`である。C1候補の`20c8f0f71734d244e8734a0ded0903d380cfcae79315549ccd318a8a6e6ebabf` / `71cb7a8bba95d335571411198044da40b1ac05d06707a9c34a9fb396bf6c2a00`とは別内容なので、同一候補として流用しない。
- PR #144の実番号を用いたtenant-boundary 2資産・2 snapshot、authz 8入力blob・6 sealed digest、両受理記録案を`docs/features/auth-session-verification-contract/step1-stage3-7.7-review-material.md`と同ディレクトリのJSONへ固定した。実ファイル、共有実行器A統合後develop、第1段・第2段コミット、Git object IDから機械照合し、承認者・承認日は`null`で保持した。
- 候補作成に関与していない独立レビュアが、production generator / checkerを使った再生成、隔離cloneへのtenant record・2 snapshot適用、authz record仮適用・再封印を確認した。tenant-boundary検査、frozen-baseline invariants、authz再封印はいずれもgreenで、資料のblob・digest・canonical hashと完全一致した。判定は可決（P0=0 / P1=0 / P2=0）。
- この固定は正式受理、第3段、人間逐行確認、Draft解除、マージを表さない。U-R1はC1の実統合後にrevision、source digest、snapshot、履歴、archiveを再導出する。

### C1ステップ1 第3段の7.7正式受理・反映（2026-10-16）

- 山田正輝が判断資料SHA-256 `75b65bf4f9f92a97e771e305bcd0c9a9b270d39467f71b5f25280562033d1f69`、受理記録案SHA-256 `43acdfa1b1e88ad235af019fd230615a702a191d91c3c158ca7b1466b4a0e141`に固定した両系列の完全値を正式受理した。承認者は山田正輝、承認日は2026-10-16。`origin/develop`は固定資料の基線`e7e8d3a4324687ada828b1e4b49692c087af5c44`から進んでおらず、受理値の変更はなかった。
- production `runtime_contract_acceptance`で実承認値入りtenant記録を再生成し、固定案との差分が`approved_by` / `approved_on`だけであることを確認した。`base-allowlist.json`の既存21履歴を保持して#144記録を末尾へ追記し、受理済み2 snapshot `20c8f0f…ebabf` / `71cb7a8b…c2a00`を内容アドレスで追加した。
- `frozen-baselines.json`の既存10履歴を保持して#144 `oracle_input`記録を末尾へ追記し、専用フラグ`--reseal-oracle`で8入力blobと6 sealed digestを再封印した。反映後は固定案と全14値が一致した。正式記録のcanonical SHA-256はtenant `4d0f185f3d9d086c2bacdb20f92790bc6a7966c6e5281069e17a34af4444c8d0`、authz `7a692712f25cc9d8828bdd304228de8754b638177d7b00aa824d1696344e4d99`、sealファイルSHA-256は`2ae1b99a2ee2492e2e478126b2cc2ca54526eca36069f8aa0ee75fb74ca89ead`。
- 比較archiveは既存files / trees、固定履歴prefix、snapshot名集合、11ケースを維持し、現況入力digestだけを`96b217bd…a4b7`から`68dbc129…a32`へ再導出した。tenant-boundary、authz catalog、frozen-baseline invariantsはgreen。凍結・履歴・archive対象581件は専用basetemp・2 workerで全件成功した。
- 最初の対象pytestは共有`/tmp`が満杯になり39件が同一の`ENOSPC`で失敗した。生成元`pytest-608`だけを除去し、リポジトリ外専用basetempで再実行して581件成功した。検査のskip、除外、期待値緩和は行っていない。
- この正式受理をPR全体の本人逐行確認へ流用しない。planは`active`を維持し、第3段後の全品質gate、最終レビュー、本人逐行確認をステップ1完了条件として残す。Draft解除、マージ、C2、U-F3、公開には進まない。U-R1 / #143はC1の実統合後developから再導出する。

### 第3段後の全件検査と参照digest追随（2026-10-16）

- root全件は29,635件成功・2件skip・3件失敗で完走した。失敗3件は`failure-injection-points.json`のDDL blob参照と`mcdc-map.json`のclaim-mutant blob参照の追随漏れに限られた。参照先の変更はoracle_commit追随だけで、失敗注入点5件・MC/DC分岐47件の意味・期待値は不変。2参照を実Git blobから再導出し、関連23試験と両検査CLIが成功した。正式受理済み8入力blob・6 sealed digest・2 snapshot・記録本文は不変である。
- root/backendのRuff・ty、backend format、docs-status/伝播/coverage、authz/tenant-boundary/frozen-baseline不変量は成功。frontendはPrettier・ESLint・vue-tsc・Vitest 67ファイル1,182件・buildが成功した。backend全件と最終PRレビューは実行中。

### 最終候補レビューとP2反映（2026-10-16）

- 候補作成に関与していないCodexがHEAD `7f46800b404691aea376f4250e941fd09ec9c547`のPR全差分を敵対観点で査読し、P0=0 / P1=0 / P2=0で可決した。履歴prefix、固定案との差分、2 snapshot・8 blob・6 digest、Cookie→TenantContext→固定operation→DTO検証、既存A境界とexact-setを確認し、独立34試験とproduct authz checkerが成功した。
- 規約6.3の反対側一次レビューはClaude CLI（`--print --tools ''`、製品・試験diffをstdin入力）で実行した。P0=0 / P1=0 / P2=1で可決。P2は空名・不正名型・複数行拒否試験のtenantが文脈と不一致で先に短絡する点だった。採用し、その3入力を文脈と同じUUIDへ変更して各条件へ到達させ、2行目の名称非漏洩assertを追加した。新規製品仕様・受理値は変更していない。
- 同じ独立CodexがP2反映差分と影響箇所だけを再査読し、P0=0 / P1=0 / P2=0で可決。session10試験、Ruff、format、ty、diff-checkが成功した。本人逐行確認は未実施のまま維持する。


### C1ステップ2の再開・所有（2026-10-17）

- 山田正輝が承認済みC1ステップ2の実装・検査・レビュー・コミット・PR準備を指示した。専用worktreeのfeature branchを最新`origin/develop=3052e0db743877c7f15c0ec10daa0142cba7ab7e`へfast-forwardした。C1ステップ1・#119・#120の実コード統合と正規DTOを確認し、開始条件は成立。
- open PRとworktreeを照合し、C2/U-F3/U-F2/U-F6の並行編集はなかった。C1が`api/auth.ts`、`authStore.ts`、共通clientの確認前拒否/認証Cookie成功フック、固有specを一時所有する。C2のmetadata、U-F3画面、U-F13のroute/guardは変更しない。後続計画へC1ステップ2統合待ちと引渡し条件を追随した。
- 保存値は確認候補にとどめ、起動時・別タブ変更時に認証を復元しない。login成功headersで旧tenant/cacheを破棄し、session DTO確認成功後だけ認証済みとする。login確定拒否・session未認証・結果未確認を分け、資格情報を自動再送せず、正規APIの明示再確認/logoutを供給する。最終試験・正式レビュー・人間逐行確認は未了。

### C1ステップ2の品質検査・敵対指摘（2026-10-17）

- 未コミット製品候補はfrontend全68ファイル・1,220試験、対象6ファイル167試験、Prettier/ESLint/vue-tsc/dependency-cruiser/buildが成功。rootのRuff/ty、正本同期・coverage・propagation、frozen-baseline invariants、tenant-boundary、diff-checkも成功した。backend全件は今回未実施。
- 正式wrapperの敵対レビュー第1周は否決（P0=1/P1=1/P2=1）。P0は旧loginのSet-Cookieが新世代検証後に到着する競合で、JS側のstale棄却だけではCookieとtenantの一致を保てない点。採用し、現行の「旧操作は新世代store/cacheを変更しない」に安全側の認証未確認化の例外を設ける最小追補を人間判断へ提示した。承認前に製品契約を変更せず、ステップ2完了・PR可能とは扱わない。
- P1の確認開始時bb.auth除去とP2の共有abort後の明示再確認要求は、承認済み§4項6・§3の契約どおり。可用性制約として引渡し対象に残す。Claude一次レビューは実行中。
- 判断資料は`docs/features/auth-session-verification-contract/step2-review-material.md`。Claude向け申し送りは本コミット済み作業ログへ集約する既定方針を維持し、消失した別資料の復元とは扱わない。C2/U-F3/U-F13の実装・公開は未着手。

- Claude一次レビューは差し戻し（P0=0/P1=2/P2=10）。Cookie競合は敵対指摘と一致し、人間判断が必要との結論。試験追加可能なP2には同じ承認範囲で対応し、epoch、競合拒否、login不正JSON、確定未認証後の自動再送禁止を追加した。auth固有42試験成功。全件1,220成功は追加前であり、最終候補の全件完走とは扱わない。
- 最小追補の承認は未着。P0を残した実装完了コミット・PR作成は行わず、製品差分は専用worktreeと外部patchへ保全する。記録のみをコミットし、ステップ2の完了トークンは付けない。2026-10-17再fetchでもdevelopは3052e0dbのまま。凍結資産・backend・認可・実行器への変更はない。

### C1ステップ2の承認追補・第2周（2026-10-17）

- 山田正輝が遅延旧login/logoutのCookie変更可能性に限る安全側の無効化例外を承認した。新世代から旧ユーザー/tenant/成功を採る許可ではない。計画§12、C2/U-F3/U-F13の接続条件へ同期。新API/DTO/ACL/凍結資産変更はない。
- 共通clientで2xx headersまたはHTTP未確認失敗を一回だけ通知し、通知前の旧要求判定を保持する。旧Cookie変更で新世代を未確認へ戻しcacheを破棄するが、旧本文を成功へ昇格させない。確定非2xx/旧sessionは新世代を維持し、資格情報/mutationの自動再送やsession自動再確認は行わない。
- 第2周は指定wrapper敵対レビュー可決（P0=0/P1=0/P2=0）、Claude反対側レビュー可決（P0=0/P1=0/P2=2）。2件とも採用し、現世代headers後本文失敗の一回破棄試験、旧応答の本文非読取assert、資料の現在状態を補正。製品コード追加変更・第3周レビューは不要。件数外の参考は判断資料へ照合結果を記録した。
- `/tmp`容量不足でauth.spec.tsの書込みが中断したため、保全済みpatchと追加差分から対象ファイルを照合して復旧し、固有51試験成功を確認した。他担当のファイルを削除せず、C1専用worktreeの再生成可能なnode_modules/backend venvを空き領域へ移した。直後に更なるP2試験2件を追加し、最終全件検査へ含める。容量不足の実行を合格には数えない。
- Claude向け申し送りは本worklogへ集約する。C1がauth/client/storeを一時所有し、C2/U-F3はC1統合後の実基線へ追随する。epochが同じ未確認結果のUI通知は冪等に扱い、旧結果を成功表示しない。実ブラウザの複数タブCookie受入、応答tenant照合、保護route/team接続は後続未完了。
- 台帳への追記なし。今回の契約衝突と単発の一時領域容量不足は本タスク内の追補・保全と既存レビュー手順で扱い、ハーネス仕様変更や新規機能を必要としない。

- PR前の全件検査では共有環境で容量・swap圧迫と他担当の並列全件実行が重なった。最初のroot実行は25,605 passed / 2 skipped / 1 failed（core-guard subprocessの既存30秒timeout）で原因特定のため中断。該当1件を同条件の単独実行で成功確認した。2並列での次の実行も直列化のため中断し、12,684 passed / 2 skipped。いずれも全件完走・合格と数えない。
- backend既存共有試験DBでは被検査ロールが既存というfail-closedを観測した。既存ロールを削除せず、既存のdisposable_postgres_cluster fixtureをそのまま使うC1専用クラスタへ切り替えた。専用クラスタの全件実行でもgame_state/authentication migrationの子クラスタが既存60秒起動期限に達し、2 failed / 12 passedで直列化のため中断した。別診断でも同じ起動期限を観測。migration・認可・fixture・timeoutを変更せず、環境による未検証として保持する。最初の中断時のadmin接続closedによるteardownエラーも成功扱いにしない。
- frontend並列検査は1 failed / 1,156 passed・4 worker起動エラーで終了。失敗は既存StrikeZoneのtimeout、workerは既存Button/sync/domain等。C1対象の別実行は5ファイル177 passedだがauthStore境界workerの起動待ちエラーがあり、対象全体を合格とは数えない。C1が起動したPython全件を停止し、frontendから直列再実行する。他担当プロセスは変更していない。

- 認証コード3ファイルの第2周レビュー対象hashはmanifestと一致し、製品・試験候補を検証待ちのコミットで保全する。計画はactiveを維持し、ステップ2全DoD成立は宣言しない。全件検査の環境障害と未通過は判断資料・PR準備本文へ明記した。ローカル/check green前にDraftを作成する例外・push/PR作成は未承認であり、自動でゲートを移さない。今回の契約追補承認は本人逐行確認ではない。

- 製品候補を`1fea2c60f04f9c50c882298042b5a0458dd5879a`へコミット保全。9ファイルを既存コア登録で検出し、実HEAD/基線で領域別基線検査成功・本人逐行確認未チェックのproduction guardによる9ファイル拒否を確認した。本人チェックの代記はない。正式第2周の製品hashと一致し、新規7.7対象はない。
- 直列frontend全件は68ファイルで1,236 passed / 1 failed（既存domain-sql再帰試験のtimeout、worker errorなし）。該当1件の単独再検査は成功（1 passed、非対象14 skipped）。全件exit 0とは扱わず、さらに全件を同一候補で確認中。最新auth.specのPrettier/ESLintも成功。
- `feature_status.py`はC1に「完了ステップに欠番」を表示した。ステップ1は既にdevelopへ統合され新差分がステップ2だけのため。全出力をPR準備本文へ固定し、ハーネスや履歴を改変して警告を消さない。TSK-528全体やU-F13残部を完了にしない。
- `pr`手順2.4により、ローカル/check未通過でpush/PR作成は行わない。共有環境の繰返しtimeoutに対し、C1ステップ2限定でローカルgreen前にDraftを作りCIで全件検証する例外・push/作成の承認を一括提示した。回答待ちは承認ではない。C2/U-F3・公開・Draft解除・マージへは進まない。

- 最新の直列frontend全件は68ファイル1,236 passed / C1外domain-sql1 timeout。C1対象6ファイル184試験は成功し、当該domain-sql1件の単独再検査も成功（非対象14 skipped）。単一全件greenとは扱わない。更なる全件実行もworker終了timeout反復で中断した。型/format/lint/dependency/buildの成功は維持する。
- C1が起動した全件実行は停止して保全した。ローカル/check未通過のため現行pr手順ではpush/PR作成へ進めない。Draft先行の限定例外を回答待ちとし、時間経過を承認とは扱わない。計画active、TSK-528/U-F13全体未完了、本人確認は未実施。最終fetchのdevelopは3052e0db。今回の本人確認対象は基線からの17ファイル全差分。

### C1ステップ2 Draft先行承認・develop追随（2026-10-18）

- 山田正輝がpr手順2.4のC1ステップ2限定Draft先行例外、通常push・Draft作成・CI・承認範囲内の修正/検査/資料更新を承認した。本人確認は未実施、全品質ゲート通過・ステップ2完了とは記録せず、Draft解除・公開・マージ・C2/U-F3へは進まない。
- #146（TSK-565）は2026-10-18T03:30:13Zにce0c0e8697252a89bce0c57e69b4821e0a6cac2bへ統合。#145（188acf83）を含む最新developを専用worktreeへmergeし、競合なし。C1製品3ファイルは第2周review hashと一致する。新基線の受理済みauthz資産は保持し、C1の変更として7.7履歴を追加しない。
- /tmpは5.0G空き、home側は869G空きで、専用/home/ymdms/.cache/pitchlog/c1-step2-20261018はhomeと同じデバイス・/tmpとは異なることを実測した。#146はTMPDIR/PYTEST_DEBUG_TEMPROOTの明示で挙動が変わるため、今回それらを外し、専用PITCHLOG_PYTEST_TMPDIRによる移送と実pytest配線を確認する。rootは4並列（子のautoも4）、ローカル全層の高負荷同時実行は避ける。
- Draft提出用statusはin-reviewとするが、DoD完了の宣言ではない。既存のレビュー採否・本人未チェックを維持する。台帳への追記なし：容量対策は統合済みTSK-565に帰属し、C1でハーネス機能を追加しない。

- #146 backend配線試験は1 passed・skipなし。実tmp_pathは専用backend基底配下のpytest-of-ymdms/pytest-1/test_tmp_path_is_under_bootstr0へ作られ、home側のディスクデバイスである。最初の計測はファイル名短縮を誤ったglobで照合したため失敗したが、実試験は成功しており、実生成名を再取得して照合した。root全件は4 workers・29,669項目で開始した。

- Draft PR #147を作成（作成時HEAD f5d19665025b4eaa35378d4fcc330664056280ac）。本文に前回timeout/単独再試験・root/backend未完走・レビュー後の試験/記録修正・本人未確認を明記し、通常pushのみ実施した。PRはMERGEABLEだがDraftのまま。
- 初回CI 39094298692ではfrontendが68ファイル1,237 passed、dependency-cruiser/build/closureも成功。前回の環境timeoutはこのCIでは再現していない。core-guardは本人未チェックで9ファイルを拒否し、代記していない。
- secretsはreview manifestの公開ソースSHA-256の2件（1fea2c60の4/6行）がgeneric-api-keyに誤検知された。同コミットのgit blobから再計算して保存値と完全一致を確認した。github-setup.md §4は誤検知にも人間判定を要求するため、限定2 fingerprintの登録判断を資料/PRコメントへ提示し、回答前に.gitleaksignoreへ追加しない。
- 通常PR CIはbackend差分なしでbackendをskipする。skipを成功扱いにせず、最終HEADで既存workflow_dispatchを使用してbackend全件も実行する。正本・workflow・試験・timeoutの変更は行わない。
- Notionの親TSK-528にPR #147のURLを記録し、async更新のsucceededを確認した。親全体の進行中・未完了を維持し、DoD/完了日は変更していない。

### C1ステップ2 本人回答・公開hash限定登録

- 山田正輝がHEAD a3934fb7283f194ba5544e542bbddc056ff9645bの全18ファイルの本人逐行確認完了を回答。確認方法は未申告のため推定して記入しない。承認済み2件や当該本人確認を一括未了へ戻さない。
- 公開ソースhash2件が実認証情報ではないとの人間確認と、理由付きfingerprint限定登録承認を受領。既存5件を保持し2件のみ追加する。製品/spec、workflow、凍結契約、検査条件を変更しない。追加差分は計画・判断資料・本人確認記録・PR資料・本ログへの追随で、元の18ファイルの確認対象外であることを明示する。
- 前HEADの最終検査：ローカルroot 29,668 passed/2 skipped、両CI root 29,409 passed/2 skipped、backend 2,523 passed/4 skipped・coverage89%、frontend68ファイル1,237 passed。全必須チェックの成功前に完了やDraft解除を記録しない。
- 既存履歴の別1件は同期故障試験の母集合における固定試験ID。backend/frontend双方のペア集合検査用途を照合し、詳細をstep2-gitleaks-decision.mdへ固定した。この1件は未判定・未登録で、承認済み2件と別管理する。
- 新HEADの通常push・PR CI更新を進め、全必須チェック成功後だけDraft解除する承認を受領。マージ・公開、C2/U-F3実装は行わない。台帳への追記なし：既存の誤検知登録運用の承認反映であり、新たなハーネス知見は追加しない。

### C1ステップ2統合完了・C2/U-F3への引継ぎ（2026-10-18）

PR #147は実SHA493342be37d4383ca572f8d1c826a3f184a4d213へ統合。最終d56c178eの必須チェック成功、本人完了回答の対象a3934fb7全18ファイル（方法未申告）、承認済みhash2件限定登録、既済みレビュー採否を照合しC1ステップ2を完了とした。C1待ちとC1一時所有を解消し、clientはC2へ、auth/storeは後続による単一実装再利用へ移る。

C2/U-F3からU-F13接続と実画面/API/DB通しまでの自律指示を受領。非共有実装は専用worktreeで並行し、接続は確定C2契約に従う。現在open PRは143/142/138で、C2/U-F3同範囲のPR/worktreeは無い。#143が共有core3ファイルとauthz/repository凍結資産を所有するため無断変更しない。agmsgは本プロジェクトの登録が無く別チーム候補のみだったため未登録の送信や所有移管を行わず、open PR/worktreeの実差分から所有を照合した。

U-F3は経路未登録の正規auth接続と24固有試験/全frontend1,261試験が成功。C2は共通server metadata境界と7routeを実装し、backend対象365件の初回検査が成功、frontend固有185件/追加56件が成功。最終全検査・正式レビュー・機械core登録・本人確認/統合/通し受入は未了であり、完了を先行記録しない。TSK-528/TSK-520全体未完了を維持する。
