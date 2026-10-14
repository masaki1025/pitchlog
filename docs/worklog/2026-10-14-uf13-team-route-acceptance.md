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
