# U-F5 チーム・選手管理 初期分割の計画記録

## 2026-10-13 調査

- 正式カード TSK-520 を再取得し、担当者・固有 DoD・T / D のコア領域判定を確認した。
- `origin/develop` を再取得し、PR #123 統合済みの `928280e6` から専用 worktree `feature/uf5-team-player-management` を作成した。
- worktree、branch、open PR と既知担当を照合し、U-F5 の重複担当は見つからなかった。
- develop の U-M1 API / DTO、PR #120 の U-F6 client / roster DTO、PR #119 の認証応答、develop の U-F13 router / provider を実コードで確認した。
- PR #119 の login 応答は tenant ID を返さず、PR #120 は応答テナント完全照合まで画面公開を禁止している。U-F13 の認証ガードと `authEpoch` key も未実装である。
- PR #121 は一括在籍変更の選手行取得を UUID 順へ直している。初期範囲は在籍変更を除外し、PR #121 非依存とした。

## 計画レビュー

### 1 周目

`codex_run.py review adversarial` で P0 0 件、P1 4 件、P2 1 件、否決。

- P1: 公開ゲートに検証済み tenant ID の取得条件と応答側の独立した照合情報がない。
- P1: TSK-520 固有の残余へ U-F13 / U-F6 の完了条件が混在している。
- P1: 選手 mutation が U-F8 と共有する `['players', teamId]` 全体を invalidation する保証がない。
- P1: A→B 切替中の遅延 mutation が B のフォーム・警告・cache を更新しない試験と、送信元チームで結果確認する案内が不足。
- P2: ステップ 1 の合格条件にステップ 2 のフォーム入力破棄が混在。

すべて採用した。公開前提を U-F5 固有 DoD と分離し、検証済み tenant ID と応答証跡の契約を外部ゲートへ追加した。選手 mutation の共有 prefix 全体の invalidation、遅延 mutation の世代照合と負例、ステップ境界を計画へ反映した。

### 収束確認

1 周目の 5 指摘だけを対象に再レビューし、P0 0 件、P1 0 件、P2 0 件で可決した。検証済み tenant ID と応答証跡の公開ゲート、TSK-520 固有残余の分離、共有 query prefix の invalidation、認証切替中の遅延 mutation、ステップ境界がすべて解消済みで、新たな指摘はなかった。

## 人間承認

2026-10-13、山田正輝が現行計画と次の 4 点を承認した。

- `TeamScreen` を経路未登録で先行実装する。
- PR #120 の develop 統合まで製品実装を待機する。
- 認証、検証済み tenant ID の供給、認証ガード、応答 tenant 照合が揃うまで `/team` へ接続しない。
- 初期分割完了後も TSK-520 を未完了として維持する。

同日の再確認で PR #120 は open のままで、`origin/develop` は `928280e6` だった。製品コードには着手せず、PR #120 統合後に固定済み SHA ではなく最新 `origin/develop` を取り込み、前提差分を再確認してからステップ 1/2 を開始する。

## ステップ 1/2

PR #120 が `1160e5dd` で develop へ統合されたことを確認し、PR #121 統合済みの最新 `origin/develop` を専用ブランチへ取り込んだ。`frontend/src/api/{client,roster,types}.ts`、共有 Pinia、共有 QueryClient、U-M2 の変更を再照合した。

- U-F6 の `listTeamRecords` / `listPlayers` と実在 DTO は計画どおりで、API や DTO の追加は不要だった。
- U-F2 の `authEpoch` と query cache 全消去、U-F6 の送信前・応答後・本文読取後の世代照合を再利用した。
- PR #121 は在籍変更とスタメン記憶の範囲であり、在籍変更を除外した本ステップの実装境界に影響しなかった。
- `router.ts` と `App.vue` は変更せず、`/team` は未接続のまま維持した。

`TeamScreen.vue` に self / opponent のチーム一覧と選択チームの選手一覧を追加した。どちらも `limit=25` と `next_cursor` を使うカーソルページングで、次 cursor がない場合は停止する。初回、空、初回失敗、追加取得失敗を区別し、追加取得失敗時は取得済み行を残して同じ cursor を再試行する。

query key は `rosterQueryKeys.ts` へ集約し、選手は `['players', teamId]`、チームレコードは `['team-records', teamId]` を共有 prefix にした。`teamId=null` では query を送らない。`authEpoch` と tenant ID を key に含め、認証切替を同期監視して選択を消す。切替前の遅延応答は API client の世代照合に加えて画面 query でも世代を確認し、新認証の一覧へ混ぜない。

自動試験には、ページングと cursor、選択切替、空一覧、初回・追加取得の再試行、認証切替直後の旧一覧・選択破棄、切替前の遅延応答、Vue 補間によるエスケープ、共有 query prefix を含めた。

品質ゲート:

- `pnpm exec prettier --check .`: 成功
- `pnpm exec eslint .`: 成功
- `pnpm exec vue-tsc --noEmit`: 成功
- `pnpm test`: 最終全件 56 files / 958 tests 成功。対象試験は 2 files / 10 tests 成功。
- `pnpm build`: 成功。build closure は conforming、違反 0。
