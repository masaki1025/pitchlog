---
feature: uf13-team-route-acceptance
status: active
承認: 未
重さ分類: コア領域
worktree: ../../..
notion: https://app.notion.com/p/3f493b75e68781628422c331bfebc350
branch: feature/uf13-team-route-acceptance
created: 2026-10-14
計画レビュー周回: 2
確定ゲート周回: 0
実行方式: 通常
反映周コミット: 適用
---

# 実装計画書案: U-F13 `/team` 認証入口と U-F5 実 API 受入

## 1. 目的

[TSK-528](https://app.notion.com/p/3f493b75e68781628422c331bfebc350) の残部から保護 `/team` と認証世代ごとの画面再生成を切り出し、[TSK-520](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2) の統合済み `TeamScreen` を実 API で利用できる縦断へ接続する。

対象は `/team` だけとする。15 経路 + catch-all 全体、U-F5 の在籍変更・論理削除・試合中登録、他画面は含めない。調査の詳細と契約不足は [research.md](research.md) を正とする。

## 2. 起点、所有、開始ゲート

- 起点は `origin/develop` `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`。PR #127 の U-F5 初期分割と、PR #133 の core-guard 回帰試験修正を含む。2026-10-14 の再開時に専用ブランチへ取り込み済みで、製品契約への影響はない。
- 専用 worktree `/tmp/pitchlog-uf13-team-route-acceptance`、branch `feature/uf13-team-route-acceptance` を作成済み。製品コードは未変更。
- PR #119 は別担当の worktree と PR を持ち、open / behind。変更しない。
- U-F13 / U-F5 の同範囲を持つ open PR / worktree は見つからなかった。U-F3 の実装も見つからなかった。

**製品実装の開始条件**:

1. adversarial review 2 周の採否記録と最終 C2 反映差分を人間が確認し、本計画を承認する。
2. PR #119 が develop へ統合される。
3. C1（認証成功から検証済み tenant ID を供給）が承認済み契約として develop に着地する。
4. C2（応答 tenant の独立証跡と U-F6 client の exact match）が承認済み契約として develop に着地する。
5. C3（U-F3 の正規 auth client、`LoginScreen`、login → auth store 接続）が develop に着地する。`/login` の route 登録自体は本計画のステップ 3 が `/team` と同時に行う。

上の条件が欠けた状態で仮 tenant、手入力 localStorage、仮 response header、空の login 画面、guard の迂回を使って公開しない。

## 3. スコープ

### 3.1 実装するもの

- `.claude/core-areas.json`、`scripts/core_guard.py`、`tests/test_core_guard.py`
  - `frontend/src/router*` と `frontend/src/App*` を tenant-isolation へ登録する。
  - 既存の回転式追加層に宣言し、別コミットで JSON へ登録する。登録前、宣言のみ、登録後、各パターンを外した負例、未記入の人間逐行確認での拒否を検証する。
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
- U-F3 の画面・auth client 実装。U-F3 の `LoginScreen` と login → auth store 接続は別所有の先行依存とし、本縦断は route 登録だけを持つ。統合されない場合は本計画を開始せず、範囲を変える新しい計画レビューと人間承認へ戻る。
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

`frontend/src/router.ts` と `App.vue` は T の意味範囲だが、現行 `.claude/core-areas.json` の path に一致しない。`frontend/src/router*` と `frontend/src/App*` の登録を必須とし、既存回転式追加層への宣言と JSON 登録をステップ 1/4、2/4 の別コミットで行う。登録差分を adversarial review と人間逐行確認に含める。検出を迂回しない。

### 4.2 正本影響

要件書、design、ADR、development、ops の正本は改訂しない。既存の FR-033 / FR-034、U-F2 決定 J、U-F6 利用条件を実装する追随である。正本外の本計画、research、worklog、Claude 申し送りを同じ変更で維持する。

## 5. 実装ステップ

契約 C1 / C2 / C3 の着地後、最新 `origin/develop` を取り込み、前提差分と担当重複を再確認してから開始する。

| # | ステップ（何を作るか） | 合格条件（このステップの検証方法） |
| --- | --- | --- |
| 1 | core path の追加層を宣言する。`scripts/core_guard.py` と `tests/test_core_guard.py` に `frontend/src/router*`、`frontend/src/App*` の tenant-isolation 登録予定を固定する | JSON 未変更の宣言のみ状態と、合成した登録後状態が受理される。未宣言追加、部分追加、順序変更、各パターン欠落、未記入の人間逐行確認を拒否する。既存 U-F8 / U-F5 の登録を維持する。guard の pytest / ruff / ty が green |
| 2 | `.claude/core-areas.json` の tenant-isolation に宣言済み 2 パターンだけを登録する | step 1 とは別コミット。最新 develop 基線に対する `core_guard.py`、`test_core_guard.py`、baseline 検査が green。router / App と spec の変更がコア領域として検出され、人間逐行確認未記入なら拒否される |
| 3 | 公開 `/login` と保護 `/team` の route、global auth guard、`RouterView` の `authEpoch` key を接続する。既存の共有 Pinia / QueryClient、統合済み U-F3 `LoginScreen`、TeamScreen を登録する | hydration 完了前に保護画面を描画しない。未認証または tenant 未確定では `/login?redirect=/team`、認証済みかつ検証済み tenant ID ありでは TeamScreen を描画する。`/help` は未認証で維持。A→B で component が再生成され旧状態が消える。API は条件成立前に 0 件。Vitest、型検査、lint、format、build が green |
| 4 | C2 の正規 U-F6 client 契約を TeamScreen の一覧・mutation と接合し、実 API browser 受入と越境受入を実施する | 実ログイン → `/team` → paging → 登録・編集 → query refetch → reload が成功。2xx は tenant 一致済み証跡を確認してから表示/cacheを更新する。不一致・欠落、遅延応答、遅延 mutation は旧本文・success notice・cache を更新せず自動再送しない。選手と対戦相手の越境拒否を不存在応答と比較する。品質 gate と受入証跡が揃う |

コミット件名には `(ステップ 1/4)` から `(ステップ 4/4)` を各 1 個だけ含める。人間が承認したステップだけを実装して止まる。

### 5.1 C2 の応答処理順

C2 の具体形式は契約担当の承認物を使う。計画上は照合を二段に分ける。

1. **server の ID 照合**: U-F6 client は認証成功で得た `teamId` を `expectedTenantId` として共通 request metadata に渡す。server の共通境界 `require_expected_tenant(context, expectedTenantId)`（名称は契約で確定）が、これを `TenantContext.tenant_id` と exact match する。不一致・欠落なら業務 operation の前に固定 404 で拒否し、2xx を返さない。
2. **client の証跡検証**: server は上の比較を通った 2xx にだけ、契約で固定した `tenantMatchAck` の exact literal を response metadata へ付ける。client は認証世代と `teamId` が要求開始時から不変であること、および ack が exact literal であることを本文返却前に検証する。ack は tenant ID ではなく「server で expected ID と Context を比較済み」の証跡である。

これにより U-M1 の「roster DTO に `tenant_id` を出さない」契約を維持する。request / response header 名、ack literal、適用 route は C2 の承認契約で固定する。

| 応答 | client の処理 |
| --- | --- |
| 2xx + 認証世代・teamId 不変 + ack exact match | 本文を返し、画面 / cache / success notice の更新を許す |
| 2xx + ack 欠落 / 不正、または要求後の認証世代・teamId 変更 | 本文を画面 / cache へ渡さない。mutation は結果未確認、一覧は破棄。mutation は自動再送せず、query の retry predicate もこの境界エラーを再送対象から外す |
| expected tenant の欠落 / server Context との不一致 | server が operation 前に固定 404。client は成功扱いせず本文・cache・notice を更新しない |
| 401 | tenant 証跡を要求せず、現行どおり `expireSession()`。本文を画面へ出さない。古い認証世代の 401 は現行 `ApiStaleAuthError` で新 session を失効させない |
| 404 | tenant 所有本文として扱わず固定エラーのみ。cache / success notice を更新しない。越境と不存在の status・本文同一性を確認する |
| 422 | validation error として失敗させ、tenant 所有本文を表示しない。mutation 完了や cache 更新を行わない |
| network / abort | 現行分類を維持。network は結果確認を案内し自動再送しない。abort はそのまま伝える |

C2 が専用例外を追加する場合、既存 `TeamMembersContent` の結果未確認分岐へ統合し、例外本文や tenant 値を表示・ログ出力しない。

## 6. DoD

- [ ] 未認証で `/team` へ直接到達すると、hydration 後に実在する `/login?redirect=/team` へ遷移し、TeamScreen と roster API を開始しない。
- [ ] `POST /auth/login` と `GET /auth/session` の両方が成功したときだけ、server が検証した tenant ID と、成功したログイン入力の表示用 team name が auth store へ入り、`/team` へ戻れる。team name を認可・tenant 照合に使わない。
- [ ] 認証後の実 API で team / player 一覧を paging し、対戦相手と選手を登録・通常編集し、query refetch と browser reload 後に結果を確認できる。
- [ ] server が要求開始時の検証済み expected tenant ID と `TenantContext.tenant_id` を exact match し、不一致・欠落を operation 前の固定 404 で拒否する。client は一致済み ack の exact literal、認証世代、teamId の不変性を検証し、ack 欠落・不正の 2xx を fail closed で破棄する。
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

1. **C1（検証済み tenant 情報）の形と所有**: PR #119 の `LoginResponse={status}` と所有範囲は変更しない。#119 統合後の追補 PR で `GET /auth/session -> {tenant_id: UUID}` を追加し、既存 `require_tenant_access` が Cookie から発行した `TenantContext.tenant_id` だけを返す。client が tenant ID を入力する経路は作らない。U-F3 は `POST /auth/login` 成功後にこの endpoint を 1 回呼び、両方が成功した場合だけ `auth.signIn({teamId, teamName})` を呼ぶ。`teamName` は成功したログイン入力の表示値としてのみ使い、認可・tenant 照合には使わない。session 確認失敗をログイン成功と表示せず、資格情報を自動再送しない。担当候補は本セッション（Codex D）の新規追補単位、#119 担当は契約整合のレビューだけとする。#119 の branch / worktree は変更しない。
2. **C2（応答 tenant 照合）の形と所有**: request metadata を `X-Pitchlog-Expected-Tenant: <canonical UUID>`、比較通過 2xx の response metadata を `X-Pitchlog-Tenant-Match: 1` とする案を承認対象にする。server の `require_expected_tenant` は `require_tenant_access` が発行した `TenantContext.tenant_id` と header の UUID を業務 operation 前に exact match し、欠落・不正・不一致を固定 404 にする。U-F6 client は tenant-bound request だけに header を付け、2xx の ack exact match、要求開始時からの `authEpoch`・`teamId` 不変性を本文返却前に検査する。対象は U-F5 が使う `GET/POST /team-records`、`PATCH /team-records/{id}`、`GET/POST /players`、`GET/PATCH /players/{id}`。login、session、health には適用しない。U-M1 DTO に tenant ID を追加しない。担当候補は本セッションの U-F6 / backend 追補単位、#119 と U-M1 の担当は既存契約との整合レビューだけとする。header 名・literal・対象経路は追補計画のコアレビューと人間承認で正式化する。
3. **C3（`/login` と `LoginScreen`）の形と所有**: U-F3 の open PR、worktree、正式カードの担当記録は見つからず、現状は担当不在と扱う。#119 統合後、本セッションが別の U-F3 先行分割で `frontend/src/api/auth.ts`、`LoginScreen.vue` と Vitest を実装する。画面はチーム名・パスワード、固定の失敗表示、送信中の二重送信防止、C1 成功後の store 更新だけを持つ。token / Cookie を JavaScript へ露出せず、仮 tenant、localStorage 手入力、空画面を使わない。router の所有競合を避けるため U-F3 PR は経路未登録とし、本計画のステップ 3/4 が公開 `/login` と保護 `/team` を同時に登録する。U-F3 の正式カードを取得できた場合は担当・固有 DoD と差分を再照合する。
4. **core paths とレビュー**: `frontend/src/router*` と `frontend/src/App*` を tenant-isolation へ、ステップ 1/4 と 2/4 の別コミットで登録する。登録差分、router / App、C1 / C2 の追補はコア領域として反対側レビュー、adversarial review、人間逐行確認の対象にする。未実施の人間確認を代記しない。
5. **開始順と停止点**: core path 登録だけの先行は行わない。契約調整と追補計画レビューは外部統合前に進められるが、製品コードの順序は (a) PR #119 統合、(b) C1 と C2 の追補統合、(c) U-F3 先行分割統合、(d) 最新 develop を本 branch へ取り込み、(e) 本計画ステップ 1/4、の順とする。各追補と本計画はそれぞれ人間が承認した最初のステップだけを実装して止まり、本計画の後続ステップへ自動で進まない。

これら 5 項目の判断と計画承認が得られるまでは製品コードを変更しない。

### 8.1 C1・C2・C3 の成果物、担当、状態、統合条件

| 契約 | 具体的な成果物 | 担当 | 2026-10-14 時点 | 統合条件 |
| --- | --- | --- | --- | --- |
| 前提 PR #119 | `POST /auth/login`、`POST /auth/logout`、`PATCH /auth/password`、HttpOnly Cookie | 既存 #119 担当（別 worktree） | open / behind。`core-guard`・`harness` が失敗し、人間逐行確認待ち | #119 所有者による CI 解消、逐行確認、レビュー、マージ。Codex D は変更しない |
| C1 | `GET /auth/session`、`AuthenticatedTenant{tenant_id}`、backend test、U-F3 の login→session→`signIn` 接続 | **担当候補: Codex D の新規追補**。#119 担当は契約整合レビュー | 未着手、計画未作成、PR なし | #119 統合後の develop 起点。追補計画承認、tenant-isolation のレビュー、backend / frontend 品質 gate、人間逐行確認 |
| C2 | expected-tenant header、server exact match、2xx ack、U-F6 client の fail-closed 検証、server / client fault injection | **担当候補: Codex D の新規追補**。U-M1 / #119 担当は整合レビュー | 要求は U-F2 / U-F6 計画に存在。具体 metadata と製品コードは未着手 | #119 が変更する `tenant_access.py` との競合を避けて #119 統合後に実装。追補計画承認、コアレビュー、人間逐行確認、越境試験、CI green |
| C3 | `frontend/src/api/auth.ts`、`LoginScreen.vue`、spec。route 登録は U-F13 ステップ 3 | **担当候補: Codex D の U-F3 先行分割** | open PR / worktree / 担当記録なし。正式カード未確認 | #119 と C1 の統合後。U-F3 計画・正式 DoD の承認、frontend gate、コアレビュー、人間逐行確認 |

### 8.2 外部統合前に進められるものと製品実装条件

| 今進められる契約作業 | 統合前に進めない製品実装 |
| --- | --- |
| C1 endpoint / DTO / 失敗境界の追補計画、#119 差分との競合表、backend test matrix のレビュー | #119 のファイル変更、仮 session endpoint の実装、LoginScreen から未統合 API を正式経路として利用 |
| C2 header / ack / 固定 404 / 適用経路 / retry 禁止の契約レビュー、core path と逐行確認対象の確定 | `tenant_access.py`、U-F6 client、roster route の変更、tenant 所有データの公開 |
| U-F3 の正式カード・担当確認、LoginScreen の入力・失敗・redirect 契約と試験計画 | LoginScreen、`/login`、`/team` の製品コード、仮 tenant / 仮認証による受入 |
| U-F13 の 5 判断と C1〜C3 の統合順の人間承認 | core path 登録、本計画ステップ 1〜4 |

## 9. 計画レビュー結果と最終反映差分

- **1 周目（全文）**: P0 1、P1 3、P2 0。全件採用。router / App の core path 宣言・登録を別ステップ化し、U-F3 を開始条件へ追加し、401 / 404 / 422 と 2xx tenant 証跡の処理順を分離し、越境受入を player GET / PATCH、opponent PATCH、foreign team-record 指定 create、B の一覧まで具体化した。
- **2 周目（1 周目反映差分）**: P0 0、P1 1、P2 0。採用。C2 を「server が expected tenant と `TenantContext` を exact matchして不一致を operation 前の固定 404」「通過 2xx に ID を含まない ack」「client は ack・認証世代・teamId の不変性を確認」の二段へ確定した。
- 基本枠 2 周を使い切り、2 周目に P0 がないため自動 3 周目は実施していない。
- **2 周目後の最終差分**: C2 の照合主体を server に一本化、ack と tenant ID の直接比較を削除、2xx / 401 / 404 / 422 / network の処理表、query retry 除外、4 越境経路と不存在応答比較を DoD・試験・申し送りへ反映した。
- **今回の承認前明確化差分**: #119 へ C1 を同梱する案を取り下げ、#119 統合後の `GET /auth/session` 追補へ分離した。C2 metadata の候補名と対象経路、U-F3 担当不在、本セッションによる C1 / C2 / U-F3 の別 PR 候補、`/login` route は U-F13 が所有する境界を追加した。この明確化差分は追加の自動レビューを行わず、5 判断とともに人間承認の対象にする。
