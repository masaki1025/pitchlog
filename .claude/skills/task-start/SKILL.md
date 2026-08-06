---
description: タスク着手の唯一の入口。Notion タスク・feature ブランチ・worktree・計画書雛形・worklog を一括準備する
argument-hint: "<タスク名 or NotionタスクURL>"
---

# タスク着手(設計書 6.1 / 11.1 / 12.1)

## 前提チェック(NG なら中断して案内)

- env `PITCHLOG_NOTION_USER_ID` が未設定 → /setup-dev を案内して中断(担当者なしのタスクを黙って作らない)
- メインツリーの `git status` がクリーンであること(未コミット変更があれば先に退避を促す)

## 手順

1. **Notion**: $ARGUMENTS が URL ならタスクを取得、名前なら「✅ タスク」DB に起票する:
   - プロジェクトリレーション = ⚾ baseball_scorering ページ
   - 担当者 = env の自分/優先度/期限(わかる範囲)
   - 本文にテンプレどおり DoD 欄を用意
   - ステータスを着手状態へ(DB の実際の選択肢を確認して遷移する。綴りを推測しない)
2. **ブランチ + worktree**: slug を決める(英小文字とハイフン)。種別はバグ修正なら `fix/`、それ以外は `feature/`。**worktree 名 = ブランチ名のスラッシュを `-` に置換**(例: `feature/sync-protocol` → `feature-sync-protocol`):
   `git fetch origin` → `git worktree add -b <type>/<slug> ../pitchlog-worktrees/<type>-<slug> origin/develop`
3. **計画書雛形**: worktree 内に `docs/features/<slug>/plan.md` を `docs/development/templates/plan-template.md` から作成し、frontmatter(slug / branch / **worktree 相対パス** / notion URL / created)を埋める(worktree フィールドは /implement ラッパーの検証に使われる — 単一の情報源)
4. **worklog**: worktree 内に `docs/worklog/YYYY-MM-DD-<slug>.md` をテンプレから作成
5. 以後の作業はすべて worktree 側(`../pitchlog-worktrees/<slug>`)で行う。ファイル編集はそのパス配下、git 操作は `git -C <worktree>` を使う

## 報告

worktree パス・ブランチ・Notion タスク URL と、次の導線(/investigate で下調べ → /plan で計画書)。
