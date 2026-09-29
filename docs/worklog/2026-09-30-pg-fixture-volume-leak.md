---
date: 2026-09-30
topic: TSK-465 pytest の使い捨て Postgres が Docker 匿名ボリュームを回収しない問題の修正
branch: fix/pg-fixture-volume-leak
---

# 作業ログ: 2026-09-30 TSK-465 pytest の使い捨て Postgres が Docker 匿名ボリュームを回収しない問題の修正

## やったこと

### /task-start

- Notion `TSK-465`(既存・優先度 高)に着手。ブランチ `fix/pg-fixture-volume-leak`・worktree `../pitchlog-worktrees/fix-pg-fixture-volume-leak`(origin/develop = `ec02a0d2` 起点)
- 着手時点の dangling ボリューム 85 個(うち匿名 84 個)。2026-09-29 の prune 後も増え続けている。別セッションのテストが稼働中(`pitchlog-authz-*` コンテナ 1 個)
- 使い捨てコンテナの `docker run` はリポジトリ内で `backend/tests/db_fixtures.py` の 1 箇所のみ(grep)
- `backend/tests/db_fixtures.py` は `.claude/core-areas.json` でコア領域「テナント分離」に登録されているため、重さ分類はコア領域(fast path 不可)

## 決定

## 未決・次の一歩

- 計画書の承認 → /implement(ステップ 1)→ 実測 → /pr → マージ後に既存の匿名ボリュームを prune
