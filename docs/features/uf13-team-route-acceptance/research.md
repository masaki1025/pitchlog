# U-F13 `/team` 接続・U-F5 実 API 受入 調査

調査日: 2026-10-14

## 1. 起点と担当重複

- 専用 worktree `/tmp/pitchlog-uf13-team-route-acceptance`、branch `feature/uf13-team-route-acceptance` は PR #127 統合時点から作成した。2026-10-14 の再開時に `origin/develop` `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`（PR #133 統合済み）を取り込んだ。#133 は `tests/test_core_guard.py` と計画・記録だけの変更で、U-F13 の製品契約と実装範囲に影響しない。
- PR #119 は [認証 HTTP API](https://github.com/masaki1025/pitchlog/pull/119)で、再確認時点でも open、head `bf43ef93f8a9a2244b2bd5e06d1906ffbcda11de`、`BEHIND`。`core-guard` と `harness` が失敗し、人間逐行確認も未実施である。所有 worktree `/home/ymdms/projects/pitchlog-worktrees/feature-ua1-auth-http-entry` がある。本作業から変更しない。
- open PR は #119 のほか #129（U-T1）、#131（ADR-003）、#132（U-S1）であり、U-F13 または U-F5 の同じ製品ファイルを所有する open PR は見つからなかった。再確認時の worktree 一覧にも U-F13 / U-F5 の重複所有はない。
- U-F5 初期分割は PR #127 で develop に統合済み。`TeamScreen.vue`、`TeamMembersContent.vue`、既存 API 呼び出しとテストを再利用する。
- develop に `LoginScreen` はなく、U-F3 の open PR / worktree も確認できなかった。未認証の保護 route は承認済み移植規則上 `/login` へ送るため、U-F3 は実利用可能な `/team` の外部依存である。

## 2. 正式単位と既存の承認済み契約

- U-F13: [TSK-528](https://app.notion.com/p/3f493b75e68781628422c331bfebc350)。PR #123 で `/help`、共有 Pinia、共有 QueryClient、router の先行部分だけ統合済み。15 経路 + catch-all、認証ガード、`RouterView` の `authEpoch` key、越境試験は残っている。
- U-F5: [TSK-520](https://app.notion.com/p/3f493b75e68781ac8f9be34909d424a2)。PR #127 は一覧、ページング、登録、通常編集、警告、認証世代切替時の破棄を未公開 component として統合した。`/team` 接続、実 API ブラウザ受入、応答 tenant 照合、越境拒否は残っている。
- `frontend-skeleton/porting-rules.md` 6 節は、保護 route を `meta.requiresAuth` と global guard に集約し、`isAuthenticated` と `hasHydrated` で判定し、未認証なら `/login` へ送ると定める。U-F2 決定 J は `authEpoch` を `RouterView` の key にする。
- U-F6 は `credentials: 'include'`、非 GET の提示ヘッダ、401 失効、送信前・応答後・本文読取後の `authEpoch` 照合を実装済み。Cookie が `bb.auth` より先に別 tenant へ切り替わる窓は閉じておらず、応答 tenant の完全照合まで tenant 所有画面を公開しないという利用条件が残る。

## 3. 実コードの契約充足状況

| 境界 | 実在するもの | 不足 |
| --- | --- | --- |
| 起動/provider | `appProviders.ts` の共有 Pinia と QueryClient、`main.ts` の install、`router.ts` | なし |
| 認証状態 | `authStore.ts`: `hasHydrated`、`isAuthenticated`、`teamId`、`authEpoch`、切替時の cache clear | 実ログインから `signIn` へ検証済み tenant ID を渡す製品経路 |
| route | `/` と公開 `/help` | `/login`、保護 `/team`、global guard、`authEpoch` key |
| 認証 HTTP | PR #119 の `POST /auth/login`、`POST /auth/logout`、`PATCH /auth/password` | develop 未統合。`LoginResponse` は `{status:'authenticated'}` だけで tenant ID を返さない |
| roster HTTP | U-M1 の `/team-records` と `/players`。全経路が `require_tenant_access` から `TenantContext` を得て repository を呼ぶ | `Page`、`TeamRecordRead`、`PlayerRead` に tenant 証跡がなく、response header にもない |
| 画面 | U-F5 の `TeamScreen` と `TeamMembersContent`。カーソル paging、登録、編集、警告、遅延応答・mutation の世代防御 | route 接続と実 API browser evidence |

`teamName`、Cookie の有無、requested entity ID は tenant ID の証跡として使用できない。テストで `auth.signIn({teamId: 'tenant-a'})` を呼ぶ既存 setup は component の境界試験であり、公開経路の認証契約には使えない。

## 4. 閉じる必要がある契約

### C1: 認証成功から検証済み tenant ID を供給する

**必要な型・関数**:

- PR #119の`LoginResponse={status}`は維持する。#119統合後のC1追補でsession確認を追加し、Cookieから検証したtenant情報だけを返す。候補endpoint/DTOは`../auth-session-verification-contract/plan.md`のレビューと人間承認で正式化し、client入力のtenant IDは受けない。起動時の保存値はsession 2xxまで認証済みとして使わない。
- frontend: C1の正規auth clientがlogin成功後にsessionを確認し、両方が成功した場合だけserver応答のtenant IDと正規表示名をstoreへ渡す。login入力は認可、tenant照合、永続復元の正にしない。
- 証跡: 不正資格情報ではtenant情報を返さない、入力名をID/表示名の復元元にしない、別tenant tokenへすり替えられないbackend testと、session成功値だけをstoreへ渡すfrontend test。

**担当状況**: #119は既存担当が所有し、C1はCodex Dが担当する。#119担当には契約整合レビューを依頼し、同担当のbranch/worktreeは変更しない。

### C2: 保護 API の応答 tenant を独立に照合する

**必要な関数・DTO**:

- U-F6 `apiRequest` が、要求開始時の `authStore.teamId` を `expectedTenantId` として共通 request metadata へ渡す処理。
- server の共通境界 `require_expected_tenant(context, expectedTenantId)` が、期待 ID と `TenantContext.tenant_id` を業務 operation 前に exact match し、欠落・不一致を固定 404 にする処理。
- 上の比較を通った 2xx にだけ `tenantMatchAck` の exact literal を付け、U-F6 client が本文の解釈・cache 更新より前に ack、認証世代、teamId の不変性を検証する処理。
- 一覧、登録、編集の全 2xx 応答で同じ規則を適用する契約。401 は tenant 文脈がないため現行の session 失効を優先し、404 / 422 は tenant 所有本文を画面へ渡さず cache / success notice を更新しない。

U-M1 の承認済み設計は roster DTO に `tenant_id` を出さない。上の二段方式では、ID の exact match は server が行い、client は「比較済み」を示す ack literal と要求開始時からの認証世代・teamId不変性を検証する。client が ack と tenant ID を比較するわけではない。team 名で代用する案、個別 roster DTO へ `tenant_id` を足す案は採らない。metadata は request `X-Pitchlog-Expected-Tenant: <canonical UUID>`、response `X-Pitchlog-Tenant-Match: 1` を候補とする。対象は U-F5 が使う team-record / player の一覧・登録・取得・通常編集で、login / session / health は対象外とする。形式は追補計画のコアレビューと人間承認で正式化し、本計画の承認だけで製品コードへ追加しない。

**証跡**: A の expected ID と B の Cookie を組み合わせると operation 前に固定 404 となる server test、2xx の ack 欠落・不正を fault injection して本文・cache・success notice を更新しない client test、同 tenant + 正規 ack が通る試験、401 が session を失効させる試験、404 / 422 が成功扱いされない試験、機微値をログへ出さない試験。

**担当状況**: U-F6 計画は必要性だけを下流条件として残し、PR #120 は具体形式を実装せず統合済み。現在の担当は不在。本セッションが #119 統合後の U-F6 / backend 追補として担当する案を人間承認へ出す。#119 が `tenant_access.py` を変更するため、契約レビューは先行できるが製品コードは #119 統合後に開始する。

### C3: `/login` の実在

未認証`/team`の遷移先は既決の`/login`。正式カードはTSK-518で、未着手、優先度高、Tコア、依存U-F1/U-F2/U-F6/U-A1。会話上の担当はCodex D。C1が`api/auth.ts`、U-F3が`LoginScreen.vue`と試験を所有し、経路未登録で統合する。U-F13ステップ2/3が`/login`と`/team`を登録する。

## 5. 実 API 受入で使う既存経路

- backend: PR #119 統合後の認証経路、U-M1 の roster 経路、既存 tenant DB fixture / seed。
- frontend: 共有 Pinia、共有 QueryClient、U-F6 client / roster DTO、U-F5 `TeamScreen`。
- 開発接続: 既存 docker compose、backend、Vite `/api` proxy。新しい E2E harness は作らない。
- 証跡: browser の操作記録と network response、backend の既存越境 test、Vitest の guard / stale response / stale mutation test。認証情報や Cookie 値はログ・文書へ残さない。

## 6. 結論

route と画面は実装可能だが、現時点で公開条件は満たさない。PR #119 の develop 統合だけでも不足し、C1、C2、C3 が必要である。承認前および契約着地前に `/team` を route へ登録しない。
