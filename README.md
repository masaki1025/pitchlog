# pitchlog

野球の試合を1球単位（Pitch by Pitch）で記録・分析するスコアリングシステム。
Baseball_Scoring（Tsukuba PSS）を製品版として全面再構築するプロジェクト。

## ドキュメント

- **要件定義書（正本）**: [docs/requirements/requirements-pitchlog-2026-07-22.md](docs/requirements/requirements-pitchlog-2026-07-22.md)
- **改善台帳**（現行システムからの改善点と理由）: [docs/improvements-from-baseball-scoring.md](docs/improvements-from-baseball-scoring.md)
- 要件対話の決定記録: [docs/requirements/requirements-draft-pitchlog.md](docs/requirements/requirements-draft-pitchlog.md)

## ステータス

要件定義完了（v1.8 — 深層レビュー2周+旧コード全機能突合+ハーネス整備に伴う改訂）。設計フェーズ・開発ハーネス整備中。

## 開発を始める

- **ドキュメント索引**: [docs/README.md](docs/README.md)（全正本の状態）
- **開発者セットアップ**: [docs/development/onboarding.md](docs/development/onboarding.md)（Claude Code で `/setup-dev` を実行）
- **開発フロー**: [docs/development/dev-harness-design-2026-08-07.md](docs/development/dev-harness-design-2026-08-07.md) 6章（`/task-start` → 計画書ゲート → `/implement` → `/pr` → `/task-done`）

## ブランチルール

- `main`: マージ専用（直接コミット禁止）
- `develop`: 開発の統合先（直接コミット禁止）
- 作業は必ず `develop` から `feature/*`・`fix/*` ブランチを切って行う
