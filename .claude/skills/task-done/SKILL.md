---
description: タスク完了の唯一の出口。マージ確認 → worktree 除去 → 索引・worklog・Notion の締め
argument-hint: "[feature slug]"
---

# タスク完了(設計書 6.1 / 12.1)

## 前提

`gh pr view feature/<slug> --json state` で PR が **MERGED** であることを確認する(未マージなら中断してレビュー状況を報告)。

## 手順

1. メインツリーで `git switch develop` → `git pull`(最新化)
2. worktree に未コミット変更が残っていないか確認(残っていれば内容を見せてユーザーに確認してから)
3. `git worktree remove ../pitchlog-worktrees/<slug>` → `git worktree prune`
4. develop 上で計画書の `status: merged` と `docs/README.md` 索引が正しく反映されているか検算する(/pr で仕込み済みのはず。ずれていれば次のタスクで直す旨を worklog に記録)
5. worklog の「未決・次の一歩」を締める(残件があれば新しい Notion タスクとして起票を提案)
6. Notion タスクを完了へ(完了日も記録)

## 報告

完了サマリ: マージされた PR / 更新された正本 / 残件(あれば)。
