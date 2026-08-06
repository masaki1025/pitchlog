---
description: タスク完了の唯一の出口。マージ確認 → worktree 除去 → Notion 完了(develop への直接編集は行わない)
argument-hint: "[feature slug]"
---

# タスク完了(設計書 6.1 / 12.1)

worklog の締めと計画書の status 更新は **/pr が PR 内で実施済み**(マージ後の develop を直接編集しない)。本スキルはリポジトリ外の後片付けだけを行う。

## 前提

`gh pr view feature/<slug> --json state` で PR が **MERGED** であることを確認する(未マージなら中断してレビュー状況を報告)。

## 手順

1. メインツリーで `git switch develop` → `git pull`(最新化)
2. worktree に未コミット変更が残っていないか確認(残っていれば内容を見せてユーザーに確認してから)
3. `git worktree remove ../pitchlog-worktrees/<worktree名>` → `git worktree prune`
4. Notion タスクを完了へ(完了日も記録)。残件があれば新しい Notion タスクとして起票を提案する

## 報告

完了サマリ: マージされた PR / 更新された正本 / 残件(あれば)。
※ 完了状態の正は「PR merged + Notion Done + worktree 不在」の組(計画書の frontmatter は in-review のまま残る — 設計書 6.1)。
