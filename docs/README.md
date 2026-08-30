# pitchlog ドキュメントマップ

正本の索引。状態は draft → in-review → approved(廃止時 superseded)。規約は[ハーネス設計書](development/dev-harness-design-2026-08-07.md) 7 章。

## 正本

| 文書 | 状態 | 版 | 最終更新 |
| --- | --- | --- | --- |
| [要件定義書](requirements/requirements-pitchlog-2026-07-22.md) | **approved**(v2.4 — 同期プロトコル設計 v0.1 と同一の確定ゲートで一括検証。敵対レビュー10周 → PO 承認) | 2.4 | 2026-08-30 |
| [改善台帳](improvements-from-baseball-scoring.md) | **approved**(v1.1 — 要件書 v2.1 と同一ゲートで確定) | 1.1 | 2026-08-18 |
| [要件対話の決定記録(D-1〜D-44)](requirements/requirements-draft-pitchlog.md) | approved(記録) | — | 2026-08-10 |
| [同期プロトコル設計](design/sync-protocol.md) | **approved**(v0.1 — 要件書 v2.4 と一括検証。敵対レビュー10周・射程縮小2回 → PO 承認) | 0.1 | 2026-08-30 |
| [開発ハーネス設計書](development/dev-harness-design-2026-08-07.md) | **approved**(v1.11 — 13 章へ受入の前提 PR 第 3 号を新設〔対象 4 本・順序・**本数 8 → 9**〕+ 10.1 へ「正式受入」「4-6 マージ前条件」の単一定義と実施順序のゲート別分岐。敵対レビュー9周 → PO 承認) | 1.11 | 2026-08-30 |
| [ハーネス運用評価台帳](development/harness-evaluation.md) | **approved**(v1.0 — 敵対レビュー9周 → PO 承認。H-20・H-78・H-79 の実測を記入) | 1.0 | 2026-08-30 |
| [ADR-001: Codex モデル選定](adr/ADR-001-codex-model-selection.md) | approved(ハーネス確定ゲートで一括) | 1.0 | 2026-08-17 |
| [ADR-002: フロントエンド = Vue.js](adr/ADR-002-frontend-vue.md) | approved(ハーネス確定ゲートで一括) | 1.0 | 2026-08-17 |
| [ADR-003: ドメイン計算の実現方式と契約化](adr/ADR-003-domain-calc-method.md) | **approved**(要件書 v2.2 と一括検証) | 0.1 | 2026-08-19 |
| [オンボーディング](development/onboarding.md) | **approved**(v1.2 — 受入プロファイルの複製を要件書参照へ寄せ、2-2 節「アーキテクチャの採取」を新設〔3 値の採取・正規化表・不適合判定・arm64 実機で実測〕。敵対レビュー9周 → PO 承認) | 1.2 | 2026-08-27 |
| [GitHub リポジトリ設定手順](development/github-setup.md) | **approved**(v1.1 — 敵対レビュー2周 → PO 承認) | 1.1 | 2026-08-24 |
| [NFR-021 受入証跡の運用](ops/nfr021-acceptance/README.md) | **approved**(v1.3 — ブートストラップ手順を前提 PR 第 3 号へ対応し、手順 6・7 へ 10.1 の共通順序とマージ後検査を伝播。敵対レビュー9周 → PO 承認) | 1.3 | 2026-08-27 |
| [NFR-021 予約レコードのテンプレート](ops/nfr021-acceptance/reservation-template.md) | **approved**(敵対レビュー6周 → PO 承認) | 1.0 | 2026-08-19 |
| [NFR-021 結果証跡のテンプレート(phase4)](ops/nfr021-acceptance/evidence-phase4-template.md) | **approved**(敵対レビュー6周 → PO 承認) | 1.0 | 2026-08-19 |
| [NFR-021 結果証跡のテンプレート(release)](ops/nfr021-acceptance/evidence-release-template.md) | **approved**(敵対レビュー6周 → PO 承認) | 1.0 | 2026-08-19 |

## 進行中の feature

静的一覧は持たない(腐るため)。**正は worktree の現存**: `git worktree list`、現在地の導出表示 `uv run python scripts/feature_status.py`(段階・ステップ進捗・PR 状態・Notion 期待 — 無保存の派生表示)、または SessionStart 文脈(session_context フック — feature_status.py へ委譲)が表示する。

## テンプレート

[実装計画書](development/templates/plan-template.md) / [詳細設計](development/templates/design-template.md) / [調査メモ](development/templates/research-template.md) / [worklog](development/templates/worklog-template.md) / [ADR](development/templates/adr-template.md)

## 参照(正本ではない)

- `legacy/` — 旧システム資料(**版固定・変更禁止**。88列の正は `legacy/research/data-layer.md`)
- `worklog/` — 作業ログ
- `features/` — feature 作業ディレクトリ(**1 feature = 1 ディレクトリ**: `<slug>/` 配下に plan.md〔契約〕・research.md〔調査〕・design.md〔詳細設計・任意〕等。plan の状態は active → in-review の2値 — 差し戻し再開時は in-review → active に戻す〔設計書 6.1〕)
