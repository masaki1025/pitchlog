---
description: 進行中の worklog への軽量追記
argument-hint: "<メモ内容>"
---

# worklog 追記(設計書 7.5)

1. 対象: 現在の作業に対応する `docs/worklog/*.md`(worktree 内で作業中ならそちら)。なければ本日分を `docs/development/templates/worklog-template.md` から作成する
2. $ARGUMENTS を適切な節に時刻付きで追記する:
   - 事実・進捗 → `## やったこと`
   - 決定事項 → `## 決定`
   - 未決・積み残し → `## 未決・次の一歩`
3. 形式より継続を優先(整形に凝らない)
