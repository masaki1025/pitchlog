---
date: 2026-08-17
topic: Phase 4-3 開発用 PostgreSQL(docker-compose)+ contracts/ 雛形
branch: feature/dev-db-contracts
---

# 作業ログ: 2026-08-17 Phase 4-3 開発用 PostgreSQL + contracts/ 雛形

## やったこと

- /task-start: 引数 `4-3` を既存 Notion タスク TSK-222「Phase 4-3: docker-compose(開発用 PostgreSQL) + contracts/ 雛形」と同定(新規起票はしていない)→ `feature/dev-db-contracts` ブランチ + worktree 作成(origin/develop = 5164c4d 起点)→ 計画書雛形・本 worklog 作成 → Notion を 進行中 へ

- /investigate: 調査サブエージェント 3 本(spec-checker / legacy-analyst / decision-tracer)を並列実行 → 決定的な引用を原典で再確認 → `docs/features/dev-db-contracts/research.md` へ統合。計画書 1 節・4 節から参照

## 決定

- slug は `dev-db-contracts`(Phase 4-1 = `frontend-skeleton` に倣い、内容が分かる英小文字ハイフン)

## 未決・次の一歩

調査で出た論点(詳細は research.md):

- **論点 A**: 設計書 `:177`・要件書 `:856` が「Phase 4 着手前に確定する」と定めた **NFR-018 実現方式 ADR が未起票**。4-3 は `contracts/` の中身を初めて決める PR なのでこの空白の上に立つ。推奨は A-1(4-3 は置き場 + 最小規約 + 座標 JSON 移設に限定し、ベクタの中身と実現方式は ADR へ送る)— **人間判断待ち**
- **論点 B**: PostgreSQL のメジャー版がどの正本にも未規定。/research(Codex)で Supabase の現行版と公式イメージのタグを確認してから決める
- **論点 C**: 設計書 `:603-604` は CI の paths filter に `contracts/` を含めると定めるが現行 `ci.yml:99-104` に無い。4-3 で追随する場合、`ci.yml` は guard_paths なので core-guard 発火 + 人間の逐行確認が必須
- **論点 D**: `core-areas.json` の paths 充填は 4-3 ではやらない(敵対レビュー + 人間承認が要り、13 章が 4-3 に与えたマージ条件で通らない)
- **論点 E**: `.env.example` の初版作成を 4-3 のスコープに入れるか
- **論点 F**: 移設後の逐語性(バイト等価)の担保先
- **論点 G**: TS/Vite/Vitest で frontend 外の JSON を import する実現可否 — 実装ステップ 1 で実測

次の一歩: 論点 A・B の判断を得てから /plan で計画書を確定する
