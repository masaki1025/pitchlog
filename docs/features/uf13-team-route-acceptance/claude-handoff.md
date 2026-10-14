# Claude 向け申し送り: U-F13 `/team` 接続・U-F5 実 API 受入

更新日: 2026-10-14

## 現在地

- branch: `feature/uf13-team-route-acceptance`
- worktree: `/tmp/pitchlog-uf13-team-route-acceptance`
- base: `origin/develop` `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`（PR #133 まで取り込み済み）
- 状態: 計画HEAD `e42a2ddbd2db58dd1fca642959ff4a2870299f63` のC1・C2・C3/U-F3とU-F13の3ステップ再編は2026-10-14に一括承認済み。外部依存待ちで製品コード未変更。
- cards: U-F13 TSK-528、U-F5 TSK-520、U-F3 TSK-518。

## 再利用する統合済み資産

- PR #123: `/help`、router、共有 Pinia、共有 QueryClient。
- PR #120: U-F6 client、roster DTO、401 / authEpoch 境界。
- PR #127: TeamScreen、TeamMembersContent、paging、登録、通常編集、警告、遅延 mutation 防御。

## 外部依存とブロッカー

1. PR #119 は head `bf43ef93f8a9a2244b2bd5e06d1906ffbcda11de`、open / behind で、`core-guard` と `harness` が失敗している。別 worktree が所有するため変更しない。
2. PR #119 の `LoginResponse` は status のみ。検証済み tenant ID を frontend へ供給できない。
3. roster の `Page` / `TeamRecordRead` / `PlayerRead` と response header に応答 tenant 証跡がない。
4. developにLoginScreen/`/login`がない。C1が正規auth client、U-F3がLoginScreenと失敗表示を先行統合し、本計画ステップ2/3が`/login`と`/team`のrouteを登録する。
5. `router.ts`と`App.vue`はtenant-isolationの意味範囲だが現行core pathsにない。ステップ1/3で宣言し、ステップ2/3でJSON登録と製品変更を同時に行う。

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

- #129はopenで、authz catalog、route registry、HTTP route matrix、base allowlist等を所有中。
- #132はopenで、core-areas/core-guardとtenant boundaryの複数凍結資産を所有中。
- open PR全体のpath照合で、#131も`.claude/core-areas.json`とtenant boundary凍結資産を所有中と判明した。U-F2 `authStore`とU-F6共通clientの直接変更を持つopen PRはなかった。
- C1/C2は#129・#131・#132の未統合差分をdevelop基線にしない。契約レビューは進めるが、製品実装と共有凍結資産の変更は#119統合後かつ各PRの所有状態確定後に行う。
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
