---
feature: uf13-team-route-acceptance
status: active
承認: 済(2026-10-14・山田正輝、3ステップ再編を含む)
重さ分類: コア領域
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-uf13-team-route-acceptance
notion: https://app.notion.com/p/3f493b75e68781628422c331bfebc350
branch: feature/uf13-team-route-acceptance
created: 2026-10-14
計画レビュー周回: 4
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書案: U-F13 `/team` 認証入口と U-F5 実 API 受入

## 1. 目的

[TSK-528](https://app.notion.com/p/3f493b75e68781628422c331bfebc350) の残部から保護 `/team` と認証世代ごとの画面再生成を切り出し、[TSK-520](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2) の統合済み `TeamScreen` を実 API で利用できる縦断へ接続する。

対象は `/team` だけとする。15 経路 + catch-all 全体、U-F5 の在籍変更・論理削除・試合中登録、他画面は含めない。調査の詳細と契約不足は [research.md](research.md) を正とする。

## 2. 起点、所有、開始ゲート

以下の起点・open状態は2026-10-14の調査履歴。2026-10-18の現状は末尾「最新指示による独立準備の再開」を正とし、解消済みの#119/C1待ちを現行の停止理由にしない。

- 起点は `origin/develop` `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`。PR #127 の U-F5 初期分割と、PR #133 の core-guard 回帰試験修正を含む。2026-10-14 の再開時に専用ブランチへ取り込み済みで、製品契約への影響はない。
- 専用 worktree `/tmp/pitchlog-uf13-team-route-acceptance`、branch `feature/uf13-team-route-acceptance` を作成済み。製品コードは未変更。
- PR #119 は別担当の worktree と PR を持ち、open / behind。変更しない。
- U-F13 / U-F5 の同範囲を持つ open PR / worktree は見つからなかった。U-F3 の実装も見つからなかった。

**製品実装の開始条件**:

1. adversarial review 2 周の採否記録と最終 C2 反映差分を人間が確認し、本計画を承認する。**2026-10-14 承認済み**。
2. PR #119 が develop へ統合される。**充足済み**（8294a1b602ae1c99d6d10d02780fa8fcfc7e8e24）。現行の待ちから除外する。
3. C1（認証成功から検証済み tenant ID を供給）が承認済み契約として develop に着地する。**充足済み**（#144と#147、最終493342be37d4383ca572f8d1c826a3f184a4d213）。現行の待ちから除外する。
4. C2（応答 tenant の独立証跡と U-F6 client の exact match）が承認済み契約として develop に着地する。
5. C3（U-F3の`LoginScreen`、失敗表示、C1 auth clientへの接続）がdevelopに着地する。`api/auth.ts`はC1、`/login`と`/team`のroute登録は本計画ステップ2/3が所有する。

上の条件が欠けた状態で仮 tenant、手入力 localStorage、仮 response header、空の login 画面、guard の迂回を使って公開しない。

## 3. スコープ

### 3.1 実装するもの

- `.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py`
  - `frontend/src/router*` と `frontend/src/App*` を tenant-isolation へ登録する。
  - 既存の回転式追加層へ先に宣言し、次の製品変更コミットでJSON登録とrouter/Appを同時に着地させる。登録前、宣言のみ、登録後、各パターンを外した負例、未記入の人間逐行確認での拒否を検証する。
- `frontend/src/router.ts`
  - 公開 `/login` に統合済み U-F3 `LoginScreen` を登録する。
  - `/team` を `meta.requiresAuth` の保護 route として登録する。
  - global guard は共有 Pinia の `useAuthStore(pinia)` を使い、`hasHydrated` 完了後の `isAuthenticated` と検証済み `teamId` を確認する。
  - 未認証または tenant 未確定なら `/login` へ redirect し、元の `/team` を安全な redirect query として渡す。外部 URL は受け付けない。
- `frontend/src/App.vue`
  - `RouterView` の表示 subtree を `authEpoch` で再生成し、認証切替時に旧 observer / component state を残さない。
  - 既存 `/help` の `back` emit と公開性を維持する。
- 既存 `TeamScreen.vue` / `TeamMembersContent.vue`
  - C2 の正規 U-F6 client 契約を再利用するために必要な最小追随だけを行う。個別 API、DTO、tenant 推定は追加しない。
- Vitest
  - hydration 前後、未認証 `/team`、認証済み `/team`、tenant 未確定、A→B 切替、遅延 response / mutation、応答 tenant 不一致・欠落、公開 `/help` を検証する。
- 実 API browser 受入
  - 実ログイン後に `/team` へ到達し、一覧 paging、選手と対戦相手の登録・通常編集、一覧再取得、browser reload 後の再表示を確認する。
  - A の画面から B へ認証を切り替え、A の一覧・選択・入力・notice・cache が B に残らないことを確認する。
  - A の entity ID を B の session で直接要求し 404、画面へ A の本文を出さないことを確認する。

### 3.2 スコープ外

- 15 経路 + catch-all の一括登録。
- U-F3 の画面実装とC1のauth client実装。U-F3 の `LoginScreen` と login → auth store 接続は別所有の先行依存とし、本縦断は route 登録だけを持つ。統合されない場合は本計画を開始せず、範囲を変える新しい計画レビューと人間承認へ戻る。
- 新しい認証、tenant、roster API / DTO の独自定義。C1 / C2 はそれぞれの所有担当が着地させた契約を使う。
- 在籍変更、一括変更、論理削除、試合中登録、試合作成、前回スタメン、移行。
- 新しい browser/E2E harness。
- PR #119 や他担当 worktree の変更。

## 4. 影響する正本とコア領域

### 4.1 5 領域判定

| 領域 | 判定 | 理由 |
| --- | --- | --- |
| S 同期 | 非該当 | 同期 queue / protocol を変更しない |
| G 状況計算 | 非該当 | 状況計算を持たない |
| R 記録権 | 非該当 | 記録権を扱わない |
| T テナント分離 | **該当** | 認証入口、tenant 確定、応答 tenant 照合、越境拒否、認証切替時の破棄を変更・検証する |
| D データ移行 | **該当（U-F5 既存画面の意味範囲）** | `TeamScreen*` と `TeamMembersContent*` は既存の U-F5 登録で T / D に属する。今回の route / App 自体は T のみ |

`frontend/src/router.ts` と `App.vue` は T の意味範囲だが、現行 `.claude/core-areas.json` の path に一致しない。`frontend/src/router*` と `frontend/src/App*` の登録を必須とする。既存回転式追加層への宣言はステップ1/3、JSON登録はrouter/App製品変更と同じステップ2/3で行い、core path登録だけを先行させない。登録差分をadversarial reviewと人間逐行確認に含め、検出を迂回しない。

### 4.2 正本影響

要件書、design、ADR、development、ops の正本は改訂しない。既存の FR-033 / FR-034、U-F2 決定 J、U-F6 利用条件を実装する追随である。正本外の本計画、research、worklog、Claude 申し送りを同じ変更で維持する。

## 5. 実装ステップ

契約 C1 / C2 / C3 の着地後、最新 `origin/develop` を取り込み、前提差分と担当重複を再確認してから開始する。

| # | ステップ（何を作るか） | 合格条件（このステップの検証方法） |
| --- | --- | --- |
| 1 | core pathの追加層を宣言する。`scripts/core_guard.py`と`tests/test_core_guard.py`に`frontend/src/router*`、`frontend/src/App*`のtenant-isolation登録予定を固定する | JSON未変更の宣言のみ状態と、合成した「登録+製品変更」状態が受理される。未宣言追加、部分追加、順序変更、各パターン欠落、未記入の人間逐行確認を拒否する。既存U-F8/U-F5登録を維持する。guardのpytest/ruff/tyがgreen |
| 2 | `.claude/core-areas.json`へ宣言済み2パターンを登録する同じコミットで、公開`/login`、保護`/team`、global auth guard、`RouterView`の`authEpoch` keyを実装する | step1とは別コミット。保存済み`bb.auth`だけでは通過せず、C1のsession検証2xxまで保護画面/APIを開始しない。未認証またはtenant未確定は`/login?redirect=/team`。認証済みはTeamScreen。`/help`公開維持。A→Bで再生成。router/Appとspecがコア検出され、逐行確認未記入なら拒否。frontendとguard gate green |
| 3 | C2の正規U-F6 client契約をTeamScreenの一覧・mutationと接合し、実API browser受入と越境受入を実施する | 実login→`/team`→paging→登録・編集→query refetch→reload成功。reloadはsession再確認完了まで画面/API 0件。2xxはtenant照合済み証跡後だけ更新。不一致・欠落、遅延応答/mutationは旧本文・notice・cacheを更新せず自動再送しない。越境拒否を不存在応答と比較。品質gateと受入証跡が揃う |

コミット件名には`(ステップ 1/3)`から`(ステップ 3/3)`を各1個だけ含める。人間が再承認したステップだけを実装して止まる。

### 5.1 C2 の応答処理順

C2 の具体形式は契約担当の承認物を使う。計画上は照合を二段に分ける。

1. **server の ID 照合**: U-F6 client は認証成功で得た `teamId` を `expectedTenantId` として共通 request metadata に渡す。server の共通境界 `require_expected_tenant(context, expectedTenantId)`（名称は契約で確定）が、これを `TenantContext.tenant_id` と exact match する。不一致・欠落なら業務 operation の前に固定 404 で拒否し、2xx を返さない。
2. **client の証跡検証**: serverは比較を通った2xxにだけ固定ackと要求ごとのchallenge exact echoを付ける。clientは認証世代と`teamId`の不変性、ack literal、challenge exact matchを本文返却前に検証する。ackはtenant IDではなくserver比較済みの証跡、challengeは応答を今回の要求へ結び付ける値である。

これにより U-M1 の「roster DTO に `tenant_id` を出さない」契約を維持する。request / response header 名、ack literal、適用 route は C2 の承認契約で固定する。

| 応答 | client の処理 |
| --- | --- |
| 2xx + 認証世代・teamId不変 + ack/challenge exact match | 本文を返し、画面/cache/success notice更新を許す |
| 2xx + ack/challenge欠落・不正・別要求値、または要求後の認証世代・teamId変更 | 本文を画面/cacheへ渡さない。mutationは結果未確認、一覧は破棄。自動再送せず、query retryからも除外する |
| expected tenant の欠落 / server Context との不一致 | server が operation 前に固定 404。client は成功扱いせず本文・cache・notice を更新しない |
| 401 | tenant 証跡を要求せず、現行どおり `expireSession()`。本文を画面へ出さない。古い認証世代の 401 は現行 `ApiStaleAuthError` で新 session を失効させない |
| 404 | tenant 所有本文として扱わず固定エラーのみ。cache / success notice を更新しない。越境と不存在の status・本文同一性を確認する |
| 422 | validation error として失敗させ、tenant 所有本文を表示しない。mutation 完了や cache 更新を行わない |
| network / abort | 現行分類を維持。network は結果確認を案内し自動再送しない。abort はそのまま伝える |

C2 が専用例外を追加する場合、既存 `TeamMembersContent` の結果未確認分岐へ統合し、例外本文や tenant 値を表示・ログ出力しない。

## 6. DoD

- [ ] 未認証で `/team` へ直接到達すると、hydration 後に実在する `/login?redirect=/team` へ遷移し、TeamScreen と roster API を開始しない。
- [ ] `POST /auth/login` と C1 の session 確認の両方が成功したときだけ、server が検証した tenant ID と表示用 team name が auth store へ入り、`/team` へ戻れる。具体 DTO は C1 追補のレビューと人間承認で正式化し、team name を認可・tenant 照合に使わない。
- [ ] 認証後の実 API で team / player 一覧を paging し、対戦相手と選手を登録・通常編集し、query refetch と browser reload 後に結果を確認できる。
- [ ] serverがexpected tenant IDと`TenantContext.tenant_id`をexact matchし、不一致・欠落をoperation前の固定404で拒否する。clientは固定ack、要求ごとのchallenge echo、認証世代、teamIdを検証し、欠落・不正・別要求値の2xxをfail closedで破棄する。
- [ ] A→B 認証切替で旧一覧、選択、form、notice、query cache、遅延 response / mutation の結果を B へ持ち越さない。
- [ ] B の session で A の player ID を GET / PATCH、A の opponent team-record ID を PATCH、A の team-record ID を player create に指定した各経路が 404 となる。各応答は同種のランダムな不存在 ID の status・本文と一致し、A の存在・内容を表示・ログ出力しない。B の一覧には A の行が混ざらない。
- [ ] `/help` の公開経路と共有 provider の instance 同一性を維持する。
- [ ] TSK-528 の 15 経路 + catch-all と TSK-520 の初期範囲外 DoD を未完了として維持する。

## 7. テストと品質ゲート

- frontend: `pnpm exec prettier --write .`、`pnpm exec eslint .`、`pnpm exec vue-tsc --noEmit`、`pnpm test`、`pnpm build`。
- core / harness: `core_guard.py`、`tests/test_core_guard.py`、tenant boundary bypass 検査。変更対象に応じて repository root の ruff / ty / pytest。
- backend contract が別 PR で着地する場合、その PR で schema / router / authz の pytest と DB 越境試験を実行し、本 PR では統合後の結果と実 API browser evidence を確認する。
- 実 API browser 受入は既存 docker compose、backend、Vite proxy を使う。新しい harness は作らない。証跡に secret、password、Cookie、token を含めない。
- コア領域として反対側レビュー、adversarial review、人間逐行確認を行う。未実施の人間確認を代記しない。

## 8. 計画承認で必要な判断

1. **C1（検証済み tenant 情報）の形と所有**: PR #119 の `LoginResponse={status}` と所有範囲は変更しない。#119 統合後の追補で session 確認を追加し、Cookie から検証した tenant 情報だけを返す。client が tenant ID を入力する経路は作らない。session 確認失敗を一律にサーバー未認証とせず、資格情報を自動再送しない。担当は Codex D。具体 endpoint / DTO / 認可 / 凍結資産は [C1追補計画](../auth-session-verification-contract/plan.md) のレビューと人間承認で正式化する。#119 の branch / worktreeは変更しない。
2. **C2（応答 tenant 照合）の形と所有**: request metadata と比較通過2xxのackを用い、serverで`TenantContext.tenant_id`と業務operation前にexact matchし、clientで本文前にack・`authEpoch`・`teamId`を検査する。U-M1 DTOにtenant IDを追加しない。担当はCodex D。header名・literal・固定error・対象routeは [C2追補計画](../tenant-match-metadata-contract/plan.md) のレビューと人間承認で正式化する。
3. **C3（`/login` と `LoginScreen`）の形と所有**: 正式カードは [TSK-518](https://app.notion.com/p/3f493b75e687814ca3c7fead50df2a14)。会話上の担当はCodex D。U-F3先行分割でC1の正規auth clientを利用する`LoginScreen.vue`とVitestを実装し、U-F13が公開`/login`と保護`/team`のroute/redirectを所有する。具体状態遷移と正式DoDは [U-F3計画](../uf3-login-screen/plan.md) のレビューと人間承認で確定する。
4. **core paths とレビュー**: `frontend/src/router*`と`frontend/src/App*`をtenant-isolationへ登録する。ステップ1/3で追加層を宣言し、ステップ2/3でJSON登録とrouter/App製品変更を同時に着地させる。登録差分、router/App、C1/C2追補は反対側レビュー、adversarial review、人間逐行確認の対象にする。
5. **開始順と停止点**: core path登録だけの先行は行わない。契約調整と追補計画レビューは外部統合前に進めるが、製品コードの順序は(a) PR #119統合、(b) C1とC2追補統合、(c) U-F3先行分割統合、(d) 最新develop取込、(e) 本計画ステップ1/3の順とする。各追補と本計画は人間が承認した最初のステップだけを実装して止まる。

これら5項目と、外部依存成立後に当時のステップ1/4だけへ進む方針は2026-10-14に山田正輝が承認した。その後のadversarial review P0により、core pathだけの先行登録を除く3ステップへ再編し、同日に計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` のC1・C2・C3計画とあわせて一括再承認された。開始条件成立後もステップ1/3だけを実装して停止する。

### 8.1 C1・C2・C3 の成果物、担当、状態、統合条件

| 契約 | 具体的な成果物 | 担当 | 2026-10-14 時点 | 統合条件 |
| --- | --- | --- | --- | --- |
| 前提 PR #119 | `POST /auth/login`、`POST /auth/logout`、`PATCH /auth/password`、HttpOnly Cookie | 既存 #119 担当（別 worktree） | open / behind。`core-guard`・`harness` が失敗し、人間逐行確認待ち | #119 所有者による CI 解消、逐行確認、レビュー、マージ。Codex D は変更しない |
| C1 | session endpoint / DTO、backend test、U-F2の検証待ち境界 | **Codex D**。#119担当は契約整合レビュー | [追補計画](../auth-session-verification-contract/plan.md)承認済み、製品未着手 | #119統合後のdevelop起点。所有再照合、tenant-isolationレビュー、品質gate、人間逐行確認 |
| C2 | expected-tenant metadata、request challenge、server exact match、2xx ack/echo、U-F6 client検証 | **Codex D**。U-M1 / #119担当は整合レビュー | [追補計画](../tenant-match-metadata-contract/plan.md)承認済み、製品未着手 | #119とC1統合後。所有再照合、コアレビュー、人間逐行確認、越境試験、CI green |
| C3 | `LoginScreen.vue`とspec。auth clientはC1、route登録はU-F13ステップ2/3 | **Codex D** | 正式カードTSK-518を照合し、[U-F3計画](../uf3-login-screen/plan.md)承認済み。製品未着手 | #119とC1統合後。所有再照合、frontend gate、コアレビュー、人間逐行確認 |

### 8.2 外部統合前に進められるものと製品実装条件

| 今進められる契約作業 | 統合前に進めない製品実装 |
| --- | --- |
| C1 endpoint / DTO / 失敗境界の追補計画、#119 差分との競合表、backend test matrix のレビュー | #119 のファイル変更、仮 session endpoint の実装、LoginScreen から未統合 API を正式経路として利用 |
| C2 header / ack / 固定 404 / 適用経路 / retry 禁止の契約レビュー、core path と逐行確認対象の確定 | `tenant_access.py`、U-F6 client、roster route の変更、tenant 所有データの公開 |
| U-F3 の正式カード・担当確認、LoginScreen の入力・失敗・redirect 契約と試験計画 | LoginScreen、`/login`、`/team` の製品コード、仮 tenant / 仮認証による受入 |
| U-F13の5判断とC1〜C3の統合順の人間承認 | core path登録、本計画ステップ1〜3 |

## 9. 計画レビュー結果と最終反映差分

- **1 周目（全文）**: P0 1、P1 3、P2 0。全件採用。router / App の core path 宣言・登録を別ステップ化し、U-F3 を開始条件へ追加し、401 / 404 / 422 と 2xx tenant 証跡の処理順を分離し、越境受入を player GET / PATCH、opponent PATCH、foreign team-record 指定 create、B の一覧まで具体化した。
- **2 周目（1 周目反映差分）**: P0 0、P1 1、P2 0。採用。C2 を「server が expected tenant と `TenantContext` を exact matchして不一致を operation 前の固定 404」「通過 2xx に ID を含まない ack」「client は ack・認証世代・teamId の不変性を確認」の二段へ確定した。
- 基本枠 2 周を使い切り、2 周目に P0 がないため自動 3 周目は実施していない。
- **2 周目後の最終差分**: C2 の照合主体を server に一本化、ack と tenant ID の直接比較を削除、2xx / 401 / 404 / 422 / network の処理表、query retry 除外、4 越境経路と不存在応答比較を DoD・試験・申し送りへ反映した。
- **今回の承認前明確化差分**: #119 へ C1 を同梱する案を取り下げ、#119 統合後の `GET /auth/session` 追補へ分離した。C2 metadata の候補名と対象経路、U-F3 担当不在、本セッションによる C1 / C2 / U-F3 の別 PR 候補、`/login` route は U-F13 が所有する境界を追加した。この明確化差分は追加の自動レビューを行わず、5 判断とともに人間承認の対象にする。
- **人間承認（2026-10-14）**: 山田正輝が5判断、外部依存成立後にステップ1/4だけへ進む方針、C1・C2・C3のCodex D担当を承認した。
- **承認後の追補差分**: C1・C2・U-F3を別計画へ分離し、U-F3正式カードTSK-518と固有DoDを照合した。C1のsession失敗3分類、C2のmetadata/error/ack、C3の状態遷移と経路所有を具体化した。最終P1反映とこれら後追加契約案は未再レビューであり、各追補のレビュー・人間承認を製品実装の開始条件として維持する。
- **3周目（追補4計画横断）**: P0 2、P1 6、P2 0。全件採用。U-F13対象のP0はcore JSON登録だけの先行ステップ。JSON登録をrouter/App製品変更と同じステップへ移し、4ステップから3ステップへ再編した。もう1件のP0である起動時session未検証もステップ2/3のguard/API待機へ反映した。総ステップ数変更は人間再承認対象とする。
- **4周目（3周目反映差分）**: P0 2、P1 2、P2 0。全件採用。C2に要求ごとのchallengeを追加し、C1の実`/team` reload受入を本計画ステップ2/3へ移した。route stepとauth client所有の残存参照、researchの表示名出所を同期した。P0反映は規約どおりP0限定の追加周へ掛け、P1反映は未再レビューとして人間確認へ出す。
- **P0限定追加周**: 第2周P0反映だけを対象にP0 0で可決。C2 challengeとC1/U-F13試験分担が実行可能と確認された。第2周P1の参照同期は対象外で、未再レビューの残余として人間確認へ出す。
- **一括再承認（2026-10-14）**: 山田正輝が計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` のC1・C2・C3/U-F3計画と本計画の3ステップ再編を承認した。ステップ1/3は宣言・試験だけ、ステップ2/3は別コミットでJSON登録とrouter/App製品変更を同時に行う。core pathだけの先行登録は行わない。第2周P1追随の未再レビュー範囲は人間逐行確認対象として残す。


### C1依存の更新（2026-10-17）

C1ステップ1はPR #144 / develop `3052e0db743877c7f15c0ec10daa0142cba7ab7e`へ統合済み。C1ステップ2（正規auth clientと検証済みstore）はCodex Dが同専用worktreeで実装中であり、C1全体の開始条件が成立したとは扱わない。`api/auth.ts` / `authStore.ts`と、最小追随中の`api/client.ts`はC1が一時所有し、統合後の基線から後続が再照合する。本計画の製品実装は今回開始しない。

### C1遅延Cookie追補の接続条件（2026-10-17）

山田正輝がC1の安全側への例外を承認した。旧login/logoutのCookie変更可能性を観測した場合、新世代も`verification-unknown`へ戻しcacheを破棄する。旧ユーザー/tenant/成功は採用せず、tenant-bound通信を止め、明示session GETだけで再確認する。資格情報やmutationの自動再送は行わない。UIは`stale`だけでなく新世代の`verification-unknown`も成功として扱わず、結果epochを照合する。C2はこの破棄境界を維持して業務operation前の応答tenant照合を追加する。C1が共有client/storeを一時所有し、統合後に後続が基線から引き継ぐ。今回C2/U-F3/保護routeの製品実装は行わない。

## C1ステップ2統合後の依存照合（2026-10-18）

PR #147は493342be37d4383ca572f8d1c826a3f184a4d213へ実統合済みであり、C1完了・統合待ちは解消した。C2/U-F3はCodex Dが専用worktreeで製品/試験を実装中。共通clientはC2、LoginScreenはU-F3、router/Appは本計画の所有とし、C1のauth/storeと共有providerを再利用する。

最新指示は既存計画のC2→U-F3→U-F13接続→専用環境の実画面/API/DB通しまでを自律進行するもの。各ステップ/レビュー/個別受理と本人確認を維持する。C2/U-F3のdevelop統合前という本計画既定の開始条件、共有3ファイルを編集中のopen PR #143との所有順は、C1待ちとは別に管理する。core path宣言→製品と同時JSON登録の順序を変えず、仮認証/tenant・未統合の他担当branchを使わない。

本worktreeは2026-10-18に6b09503dから最新develop 493342beへfast-forwardした。C2/U-F3の候補を基線へ混ぜず、router/App/core3ファイルの製品変更はまだ開始していない。C2では既存コア登録で検出できる境界を実装・検証中、U-F3ではLoginScreenの意味範囲Tと既存path未一致を確認した。必要な最小1パターンの追補と共有3ファイルの順序は、C2側`docs/features/tenant-match-metadata-contract/connection-decisions.md`へ集約する。既承認のrouter/App登録を再承認待ちには戻さない。


## 最新指示による独立準備の再開（2026-10-18）

最新developはPR #143の実統合`156dd139a893845428a1ecab69632143f7694e0b`。C1/#119の統合待ちと#143の共有3ファイル編集待ちは解消済み。本セッションが本計画の`router.ts`/`App.vue`/各specと、共有`core_guard.py`/固有試験/`core-areas.json`の編集を順に所有する。C2は共通client/roster/管理画面追随、U-F3はLoginScreen/固有specを所有し、同一ファイルの二重編集をしない。

依頼者の「今進められる作業を待機させず、承認済みコアパス宣言・JSON登録を進める」に従い、製品統合に依存しないステップ1の宣言・合成履歴検証を先行する。既承認の2パターンだけを宣言し、JSONはまだ変えない。ステップ2/3のC2・U-F3のdevelop着地条件は、自分の固定候補だけを別の検証環境に結合する局所追補への回答と区別する。未回答を承認と扱わない。

U-R1登録済み層は現行宣言から外しても実基線と現候補の両方に保持し、各パターンの除去を拒否する。新2パターンの宣言のみ・合成登録・各パターン欠落・4製品/spec検出・本人未記入拒否を検証する。U-F3の`LoginScreen*`は別の最小追加案であり、このステップ1に無断で追加しない。550・D4・544/545はこの選手管理経路の依存ではなく、停止条件にしない。


### 独立作業の検査完了と次の接続条件（2026-10-18）

宣言ステップ1/3はe5fcff3cで固定し、JSON不変・core全264成功・Ruff/ty/基線成功。C2とU-F3の最新156dd139基線に対するroot/backend/frontend全件も成功した。C2の17製品/試験、U-F3の2製品/試験は検査時から不変。詳細件数・最終HEAD・未再レビュー・残判断は[コミット対象の作業ログ](../../worklog/2026-10-14-uf13-team-route-acceptance.md)の最終節に集約する。

LoginScreen1パターンの登録追補、自分の固定候補だけを専用検証環境で接合する条件追補、新しいlogin/session相関1ステップ/追加PRは未承認であり、ステップ2/3と実ブラウザ受入は未実施。旧C1/#119/#143等の待ちへ戻さず、人間判断対象だけを限定する。push/Draft PR許可・本人逐行確認・公開・マージも未実施。


## 2026-10-18 承認済み接続例外と編集所有

山田正輝がLoginScreen*のT登録、自分の固定C2/U-F3候補だけの専用検証worktree結合、現承認範囲の通常push/Draft PR作成を承認。ステップ2/3の自分の候補結合に限りdevelop着地待ちを外し、単独/結合のHEAD・差分・検査を区別する。各PR境界と他担当未統合枝を基線にしない条件は維持。

コア3ファイルはU-F3のLoginScreen宣言→別JSON登録が先、U-F13のrouter/App追随が後。新login/session相関案は未承認であり、現C1を再利用してJSON/経路接続/試験準備を進めるが、相関不足まで解消済みとはしない。本人逐行確認・公開・マージは含まない。
