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
- 不受理時の最小順序はrepository系とroute系を分離する。前者は#131/#132統合後、後者は#137統合後にC1をrebaseして該当差分だけを適用する。全3PRを一括待機条件にはしない。
- 7.7-1の宣言、7.7-2の一行為一記録、7.7-3のfail-closedを維持する。tenant-boundary snapshotとauthz oracle封印は別の受理単位として導出し、checkerの直書き基準追加では代用しない。
