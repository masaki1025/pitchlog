---
status: in-review
---

# ADR-002: フロントエンドフレームワークは Vue.js を採用

| 版 | 日付 | 変更内容 | 状態 |
| --- | --- | --- | --- |
| 1.0 | 2026-08-07 | 新設。ハーネス設計書の確定ゲート(敵対レビュー5周 → PO 承認)で一括検証・approved 化。要件書側の 7.1 改訂は 2026-08-12 に v1.9 として 7.3 の確定ゲートを通過 | approved |
| 1.0 | 2026-08-17 | 様式の正規化(変更履歴表の新設。決定内容の変更なし) | approved |
| 1.1 | 2026-10-10 | 「帰結」節の「コード再利用」の判定を明確化し、コンポーネント設計規約の委任先を主体と経路へ付け替えた。「決定」節は変更していない。**射程宣言(7.3-7)**: **本改訂で確定する範囲** = 上記 2 項の判定と委任先。**実装時に確定する範囲** = 共通 UI 部品の実測に基づくコンポーネント設計規約。本改訂の条文が要求しないこと 4 項: ① `U-F` 系の実装単位に対する着手条件・着手順・レビュー経路を 1 つも要求しない ② コンポーネントの命名・ディレクトリ構成・props の約束・スタイルの当て方を 1 つも定めない ③ `porting-rules.md` の内容・置き場・正本性について何も要求しない ④ アクセシビリティ・国際化について何も要求しない(NFR-022 が Won't)。適用版(7.3-1): 適用版 = ハーネス設計書 **v1.19**(初回敵対レビュー時点で approved の版・2026-10-10 実測)。計画: `../features/ui-design-doc-reference/plan.md` | in-review |

| 項目 | 内容 |
| --- | --- |
| 状態 | **approved**(2026-08-07。ハーネス設計書の確定ゲート〔敵対レビュー5周 → PO 承認〕で一括検証・approved 化。**要件書側の 7.1 改訂は 2026-08-12 に v1.9 として 7.3 の確定ゲートを通過**) |
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

- **要件書 7.1 の改訂は完了**: 「React + TypeScript」→「Vue.js + TypeScript」。v1.8 で本文へ反映し、**v1.9(2026-08-12)で 7.3 の確定ゲートを通過して approved 化**した(実装着手〔Phase 4〕前という条件を満たしている)
- TypeScript は維持する(NFR-018 の状況計算クライアント実装を型なしで持つことは R-3「二重計算の乖離」を悪化させるため)
- 旧システムの React UI コードは仕様・挙動の参照資料として扱う。「コード再利用はしない」(要件書 2.3 の全面再構築方針)が禁じるのは、旧実装のソースを製品へ取り込む形(旧リポジトリを依存として参照する・旧ビルド成果物を同梱する等)であり、挙動・見た目の一致を目的とした逐語移植は本項に当たらない。PO 裁定(2026-08-16・[移植計画](../features/frontend-skeleton/plan.md) / [作業ログ](../worklog/2026-08-16-frontend-skeleton.md))は旧 frontend を「仕様・挙動の参照資料」としたうえで目標を「完全に同じもの」と定め、この判断を「ADR-002 の条項どおり」としてコード流用案を退けた。`frontend/src/index.css`、`frontend/src/lib/format.ts`、`frontend/src/lib/displayGeometry.ts`、`frontend/src/lib/spatialInput.ts`、`frontend/src/lib/courseInputView.ts` はこの逐語移植側に当たる。「完全に同じもの」の限定は[改善台帳 I-28](../improvements-from-baseball-scoring.md)に従う
- NFR-020(iPad Safari / Chrome / Edge・スマホ幅)への影響なし。E2E は Playwright の WebKit エンジンで近似し、実機受け入れは要件書どおり実施
- コンポーネント設計規約は、共通 UI 部品の実装単位が実装の実測から定め、その成果を `docs/design/` の正本として確定する

## 参照

- ハーネス設計書 2.4 / 5.2 / 論点A: [dev-harness-design-2026-08-07.md](../development/dev-harness-design-2026-08-07.md)
- 要件書 7.1(v1.7 時点): [requirements-pitchlog-2026-07-22.md](../requirements/requirements-pitchlog-2026-07-22.md)
