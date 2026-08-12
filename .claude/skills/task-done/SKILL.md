---
description: タスク完了の唯一の出口。マージ確認 → worktree 除去 → Notion 完了(develop への直接編集は行わない)
argument-hint: "[feature slug]"
disable-model-invocation: true
---

# タスク完了(設計書 6.1 / 12.1)

worklog の締めと計画書の status 更新は **/pr が PR 内で実施済み**(マージ後の develop を直接編集しない)。本スキルはリポジトリ外の後片付けだけを行う。

## 前提

`gh pr view <branch> --json state` で PR が **MERGED** であることを確認する(branch は計画書 frontmatter の `branch` — `feature/*`・`fix/*` 両対応。未マージなら中断してレビュー状況を報告)。

## 手順

1. メインツリーで `git switch develop` → `git pull --ff-only`(最新化。fast-forward 不可なら**中断**して状況を報告 — 保護ブランチにマージコミットを作らない)
2. worktree に未コミット変更が残っていないか確認(残っていれば内容を見せてユーザーに確認してから)
3. `git worktree remove ../pitchlog-worktrees/<worktree名>` → `git worktree prune`
4. Notion ステータスを `完了` へ・完了日 = マージ日を記録(綴りの正: `.claude/notion-map.json` — 推測しない)。残件があれば新しい Notion タスクとして起票を提案する
5. **マージ後に気づいたハーネス運用上の知見は follow-up タスクとして Notion に起票する**(または既存タスクへリンクする)。**本スキルから評価台帳(`docs/development/harness-evaluation.md`)を編集しない** — 本スキルは develop 上で走るため、正本を直接編集すると絶対規則 1(main/develop へ直接コミットしない)に反する。**台帳への追記は次の `/task-start` で別 feature/PR として行う**(追記の主経路は /pr のクローズ処理 — `pr/SKILL.md` 手順 1)

## 報告

完了サマリ: マージされた PR / 更新された正本 / 残件(あれば)。
※ 完了状態の正は「PR merged + Notion Done + worktree 不在」の組(計画書の frontmatter は in-review のまま残る — 設計書 6.1)。
