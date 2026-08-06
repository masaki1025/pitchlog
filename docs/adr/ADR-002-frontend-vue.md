# ADR-002: フロントエンドフレームワークは Vue.js を採用

| 項目 | 内容 |
| --- | --- |
| 状態 | **in-review**(PO 決定済み 2026-08-07。確定ゲート〔敵対レビュー〕通過で approved 化 — 1周目指摘 P1-1 により approved から差し戻し。要件書 v1.8 改訂と一括検証) |
| 日付 | 2026-08-07 |
| 決定者 | プロダクトオーナー |

## 文脈

- 要件書 v1.7 の 7.1 は技術スタックを「Python / FastAPI + **React + TypeScript** / PostgreSQL」と定め、「変更には承認を要する」と明記していた(旧システムの API+React 新 UI の系譜)
- 開発ハーネス整備の指示(2026-08-06)では「フロントエンドは **Vue.js**」とされ、矛盾が顕在化(ハーネス設計書 論点A)
- ハーネス設計書 5.2 はどちらでも成立するようツールチェーンを両対応で定義していた

## 決定

**Vue.js(3系)+ TypeScript** を採用する。ツールチェーンはハーネス設計書 5.2 のとおり:

mise(Node版管理)/ pnpm / ESLint(flat config)+ eslint-plugin-vue + typescript-eslint / Prettier / vue-tsc / Vitest + Vue Test Utils / Playwright(E2E・WebKit 含む)

## 帰結

- **要件書 v1.8 改訂が必要**: 7.1 の「React + TypeScript」→「Vue.js + TypeScript」。正本確定ゲート(敵対レビュー → 人間承認)を通して実装着手(Phase 4)前に確定させる — 確定ゲートの初回適用案件
- TypeScript は維持する(NFR-018 の状況計算クライアント実装を型なしで持つことは R-3「二重計算の乖離」を悪化させるため)
- 旧システムの React UI コードは仕様・挙動の参照資料としてのみ扱い、コード再利用はしない(もともと全面再構築方針 — 要件書 2.3)
- NFR-020(iPad Safari / Chrome / Edge・スマホ幅)への影響なし。E2E は Playwright の WebKit エンジンで近似し、実機受け入れは要件書どおり実施
- コンポーネント設計規約(Composition API / `<script setup>` 等)は設計フェーズの UI 設計書で確定する

## 参照

- ハーネス設計書 2.4 / 5.2 / 論点A: [dev-harness-design-2026-08-07.md](../development/dev-harness-design-2026-08-07.md)
- 要件書 7.1(v1.7 時点): [requirements-pitchlog-2026-07-22.md](../requirements/requirements-pitchlog-2026-07-22.md)
