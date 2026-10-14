# Claude 向け申し送り: U-F13 `/team` 接続・U-F5 実 API 受入

更新日: 2026-10-14

## 現在地

- branch: `feature/uf13-team-route-acceptance`
- worktree: `/tmp/pitchlog-uf13-team-route-acceptance`
- base: `origin/develop` `fd7445cb7e5bd1d5a75137f48c2237c9126dbea5`（PR #133 まで取り込み済み）
- 状態: 調査・計画作成中。製品コード未変更。計画承認前。
- cards: U-F13 TSK-528、U-F5 TSK-520。

## 再利用する統合済み資産

- PR #123: `/help`、router、共有 Pinia、共有 QueryClient。
- PR #120: U-F6 client、roster DTO、401 / authEpoch 境界。
- PR #127: TeamScreen、TeamMembersContent、paging、登録、通常編集、警告、遅延 mutation 防御。

## 外部依存とブロッカー

1. PR #119 は head `bf43ef93f8a9a2244b2bd5e06d1906ffbcda11de`、open / behind で、`core-guard` と `harness` が失敗し、人間逐行確認も未実施。別 worktree が所有するため変更しない。
2. PR #119 の `LoginResponse` は status のみ。検証済み tenant ID を frontend へ供給できない。
3. roster の `Page` / `TeamRecordRead` / `PlayerRead` と response header に応答 tenant 証跡がない。
4. develop に LoginScreen / `/login` がない。既決 guard は未認証を `/login` へ送るため、U-F3 の別担当・先行統合までは本計画を開始しない。
5. `router.ts` と `App.vue` は tenant-isolation の意味範囲だが現行 core paths にない。`frontend/src/router*` と `frontend/src/App*` を宣言 → JSON 登録の別ステップで必ず追加する。

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

人間承認後も C1 / C2 / C3 と PR #119 の develop 統合を再確認し、最新 develop を取り込んでからステップ 1/4 だけを実装する。2 周目の最終 C2 反映は Codex の再レビューを受けていないため、人間承認時に採否記録と差分を確認する。PR #133 は core-guard 回帰試験と記録だけで、計画の製品前提に影響しないことを再照合済み。
