---
date: 2026-08-10
topic: ハーネス確定ベースラインを main へ反映(設計書 6.4 例外追記)
branch: feature/harness-baseline-merge
---

# 作業ログ: 2026-08-10 ハーネス確定ベースラインを main へ反映

## やったこと

- /task-start: Notion タスク起票(優先度 高・DoD 3 点)→ `feature/harness-baseline-merge` ブランチ + worktree 作成(origin/develop 起点)→ 計画書・本 worklog 作成

## 決定

- **PO 判断(2026-08-10)**: 「ハーネス完成 = 設計書 13 章 Phase 3 完了」と定義。プロダクト初回リリースに先立ち `develop → main` のベースラインマージを 1 回実施する(**リリース非該当** — /release・DoD 8 項目・vX.Y.Z タグは適用外。実施完了をもって例外は失効)
- 実施順: 6.4 の例外追記が develop へマージされてから main への PR を作る(規約と矛盾した状態でマージしない)
- 変更履歴は**版繰り上げなし**の 1.1 追記行(7.6-3 の節更新 — v1.0 の frontmatter 追加行の先例に倣う)。索引 docs/README.md は版・最終更新とも不変のため反映なし
- 機構上の狙い: ci.yml が既定ブランチ main に載ることで gitleaks 全履歴スキャン(workflow_dispatch)が Actions から起動可能になる(現在はローカル docker 監査で代替中 — github-setup.md 3 章)

## 未決・次の一歩

- 設計書 6.4 追記 → 検査 → Codex 反対側レビュー → /pr
- develop マージ後: `develop → main` ベースライン PR → CI 確認 → 人間マージ → workflow_dispatch 起動確認 → /task-done
