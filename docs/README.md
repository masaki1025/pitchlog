# pitchlog ドキュメントマップ

正本の索引。状態は draft → in-review → approved(廃止時 superseded)。規約は[ハーネス設計書](development/dev-harness-design-2026-08-07.md) 7 章。

## 正本

| 文書 | 状態 | 版 | 最終更新 |
| --- | --- | --- | --- |
| [要件定義書](requirements/requirements-pitchlog-2026-07-22.md) | **approved**(v2.0 — 敵対レビュー5周 → PO 承認) | 2.0 | 2026-08-15 |
| [改善台帳](improvements-from-baseball-scoring.md) | **approved**(v1.0 — 要件書 v2.0 と同一ゲートで確定) | 1.0 | 2026-08-14 |
| [要件対話の決定記録(D-1〜D-44)](requirements/requirements-draft-pitchlog.md) | approved(記録) | — | 2026-08-10 |
| [開発ハーネス設計書](development/dev-harness-design-2026-08-07.md) | **approved** | 1.4 | 2026-08-12 |
| [ハーネス運用評価台帳](development/harness-evaluation.md) | **approved**(v1.0 — 敵対レビュー9周 → PO 承認) | 1.0 | 2026-08-15 |
| [ADR-001: Codex モデル選定](adr/ADR-001-codex-model-selection.md) | approved(ハーネス確定ゲートで一括) | — | 2026-08-10 |
| [ADR-002: フロントエンド = Vue.js](adr/ADR-002-frontend-vue.md) | approved(ハーネス確定ゲートで一括) | — | 2026-08-12 |
| [オンボーディング](development/onboarding.md) | draft | 0.5 | 2026-08-10 |
| [GitHub リポジトリ設定手順](development/github-setup.md) | **approved**(敵対レビュー2周 → PO 承認) | 1.0 | 2026-08-10 |

## 進行中の feature

静的一覧は持たない(腐るため)。**正は worktree の現存**: `git worktree list`、現在地の導出表示 `uv run python scripts/feature_status.py`(段階・ステップ進捗・PR 状態・Notion 期待 — 無保存の派生表示)、または SessionStart 文脈(session_context フック — feature_status.py へ委譲)が表示する。

## テンプレート

[実装計画書](development/templates/plan-template.md) / [詳細設計](development/templates/design-template.md) / [調査メモ](development/templates/research-template.md) / [worklog](development/templates/worklog-template.md) / [ADR](development/templates/adr-template.md)

## 参照(正本ではない)

- `legacy/` — 旧システム資料(**版固定・変更禁止**。88列の正は `legacy/research/data-layer.md`)
- `worklog/` — 作業ログ
- `features/` — feature 作業ディレクトリ(**1 feature = 1 ディレクトリ**: `<slug>/` 配下に plan.md〔契約〕・research.md〔調査〕・design.md〔詳細設計・任意〕等。plan の状態は active → in-review の2値 — 差し戻し再開時は in-review → active に戻す〔設計書 6.1〕)
