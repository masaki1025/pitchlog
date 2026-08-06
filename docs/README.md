# pitchlog ドキュメントマップ

正本の索引。状態は draft → in-review → approved(廃止時 superseded)。規約は[ハーネス設計書](development/dev-harness-design-2026-08-07.md) 7 章。

## 正本

| 文書 | 状態 | 版 | 最終更新 |
| --- | --- | --- | --- |
| [要件定義書](requirements/requirements-pitchlog-2026-07-22.md) | **in-review**(v1.8 改訂を確定ゲートで検証中) | 1.8 | 2026-08-07 |
| [改善台帳](improvements-from-baseball-scoring.md) | approved | — | 2026-07-24 |
| [要件対話の決定記録(D-1〜D-41)](requirements/requirements-draft-pitchlog.md) | approved(記録) | — | 2026-07-24 |
| [開発ハーネス設計書](development/dev-harness-design-2026-08-07.md) | **in-review**(確定ゲート実施中) | 0.15 | 2026-08-07 |
| [ADR-001: Codex モデル選定](adr/ADR-001-codex-model-selection.md) | in-review(確定ゲートで一括検証) | — | 2026-08-07 |
| [ADR-002: フロントエンド = Vue.js](adr/ADR-002-frontend-vue.md) | in-review(確定ゲートで一括検証) | — | 2026-08-07 |
| [オンボーディング](development/onboarding.md) | draft | — | 2026-08-07 |

## 進行中の feature

静的一覧は持たない(腐るため)。**正は worktree の現存**: `git worktree list`、または SessionStart 文脈(session_context フック)が「進行中の feature(worktree 現存)」として表示する。

## テンプレート

[実装計画書](development/templates/plan-template.md) / [調査メモ](development/templates/research-template.md) / [worklog](development/templates/worklog-template.md) / [ADR](development/templates/adr-template.md)

## 参照(正本ではない)

- `legacy/` — 旧システム資料(**版固定・変更禁止**。88列の正は `legacy/research/data-layer.md`)
- `worklog/` — 作業ログ
- `features/` — feature 作業ディレクトリ(**1 feature = 1 ディレクトリ**: `<slug>/` 配下に plan.md・research.md 等。plan の状態は active → in-review の2値)
