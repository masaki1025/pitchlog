---
date: 2026-10-03
topic: ステップ履歴監査が develop で必ず赤になる問題の是正
branch: fix/step-audit-merge-premise
---

# 作業ログ: 2026-10-03 ステップ履歴監査が develop で必ず赤になる問題の是正

## やったこと

### /task-start

- 発端: PR #74(TSK-235)をマージした直後、develop の `consistency` ジョブが赤になった
- Notion タスクを起票。`fix/step-audit-merge-premise` + worktree を `origin/develop`(`0492b9af`)起点で作成

## 事象と原因(実測 2026-10-03)

```
tests/test_step_history_audit.py::test_real_repository_artifacts_exist_at_each_completed_step_commit
AuditViolation: 実装ステップコミットを第一親履歴から取得できない   (:500)
```

検査は `git log --first-parent origin/develop..HEAD` でステップコミットを集め、
**0 件なら違反**とする(`:500` の `if not records`)。

**develop 上では HEAD == origin/develop なので範囲が空**になり、必ず 0 件になる。

| | 実測 |
| --- | --- |
| develop の第一親履歴のステップコミット | **0 件** |
| 全履歴なら | **816 件** |

**feature ブランチにいることを前提にした検査を、全ブランチに課していた。**
PR では緑で、**マージした瞬間に真偽が反転する**。
TSK-440(census の merge-base)/ TSK-460 と**同じ型**。

## 影響の確定

- `consistency` は**必須チェックではない**(実機 ruleset `protect-main-develop` の必須 10 件に
  `consistency` と `mutation` は含まれない — u-x1 master が実測、こちらでも確認)
- → **誰のマージもブロックされない**
- 実害は **CI に赤が出続け、レビューする人が別の問題と誤認する**こと
- `docs/development/github-setup.md:124` の Ruleset JSON には `consistency` が書かれており、
  **文書と実機が食い違っている**(別件。その食い違いが今回は偶然セーフティネットになった)

## 他タブへの連絡

`u-x1 master` / `444 344 393` / `236` の 3 本へ、#74 のマージ完了と
**`consistency` の赤は私のもので待たずに進めてよい**ことを連絡済み。

## 方針(計画段階)

**範囲が空のときを違反にしない。** 検査の目的は「このブランチが申告したステップの成果物が、
その時点のコミットに在るか」であり、**審査対象が存在しない状況(develop 上・計画段階のブランチ)を
違反と呼ぶのが誤り**。緩和ではなく前提の明示。

**落ちてはいけないもの**: 申告したステップがあるのに成果物が無い / ステップ番号の重複 /
`/N` の総数不一致 — これらは従来どおり赤であること。
