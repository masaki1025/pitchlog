---
date: 2026-09-24
topic: U-A1 チーム認証
branch: feature/ua1-team-auth
---

# 作業ログ: 2026-09-24 U-A1 チーム認証

## やったこと

- /task-start: worktree `../pitchlog-worktrees/feature-ua1-team-auth` 作成、Notion TSK-399 を `進行中` へ、
  計画書・worklog の雛形作成。重さ分類は**コア領域**(タスクカードのコア判定が機械・意味とも「コア」)
- /investigate: 調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列実行し、
  [research.md](../features/ua1-team-auth/research.md) へ統合。計画を左右する主張は Claude が原典で再確認

## 決定

- 調査メモの記法: **[確認済]**(Claude が原典を読んだ)と **[報告]**(エージェント報告のまま)を区別する。
  理由 — 4 件の機構上の衝突はいずれも計画の構造を変えるため、伝聞のまま計画書に持ち込まない
- エージェント間の食い違い 2 件を原典で裁定(research.md 5 節):
  - NFR-019(b) の網羅と 12-4 ゲートは**別の事柄**(12-4「適用単位」行が明記)→ U-A1 に掛かるのは
    自 PR が開く入口の範囲であって (b) の全網羅ではない
  - `tenants.name` に UNIQUE は**無い**(`0002` の DDL で決着)。チーム名 → テナントの解決規則は正本に無い

- 人間の指摘で **TSK-424(製品認可面の確定)が進行中**と判明 → research.md に 4-8 節を追記。
  **衝突④ と未決 D-4 は U-A1 ではなく TSK-424 が決める事項**だった(カード本文が U-A1 を名指し)

## 未決・次の一歩

- **最重要**: U-A1 は帯 3 = 入口を開く単位なので `data-model.md` 12-4 のマージゲート対象。
  通過条件の産出元 **TSK-344 が未着手**(律速: TSK-367 → TSK-317 PR #3 → TSK-344)。
  **着手はできるがマージは止まる** — 進め方(待つ / stacked PR / 統合枝)を計画書が決める
- 機構上の衝突 4 件(bcrypt 依存追加の禁止 / TB002 の `generation` パターン /
  `TenantContext` 生成 allowlist が空 / operation registry が空・`tenant_credentials` に `tenant_id` 列が無い)
- 設計判断 14 件(research.md「未解決・申し送り」の D-1〜D-14)
- **順序**: TSK-424 →(TSK-317 → TSK-344)→ U-A1 のマージ。TSK-424 の許可プロファイル確定を待たないと
  リポジトリ設計が書けない(認証 5 表は「親表経由のテナント所属」「認証前グローバル可変」の新種別に該当)
- **2026-09-24 判断(人間)**: **U-A1 は一旦寝かせる**。Notion を `ブロック中`(TSK-424 待ち)へ。
  worktree とブランチは残す。/plan は TSK-424 の許可プロファイル確定後に着手する
- worktree は develop `871fd97` 起点。develop は `e6bc0cc` まで進んでいるので、再開時に rebase する
