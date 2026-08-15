---
date: 2026-08-16
topic: frontend 骨格(Vue 3 + TypeScript)— Phase 4-1
branch: feature/frontend-skeleton
---

# 作業ログ: 2026-08-16 frontend 骨格(Vue 3 + TypeScript)

## やったこと

- /task-start: Notion へ新規起票(**Phase 4 は未起票だった**)→ `feature/frontend-skeleton` ブランチ + worktree 作成(origin/develop 起点・`2f220ea`)→ 計画書雛形・本 worklog 作成

## 位置づけ — これが pitchlog の最初のプロダクトコード

**着手時点のリポジトリは約 2 万行あるが、そのすべてがハーネス**(docs 11,591 行 / scripts 4,726 行 / tests 4,224 行)。**プロダクト本体は 0 行**で、`backend/` `frontend/` `contracts/` はディレクトリごと存在しない。

PO から「**ハーネスが自己目的化している**」との指摘があり(2026-08-15)、F1(ガードの誤検知と fail-open)を閉じたうえで Phase 4 へ移ることになった。**本タスクが pitchlog の最初のプロダクトコード**になる。

## Phase 4 の分割(PO 判断 2026-08-16)

設計書 13 章の Phase 4 は「各 Phase = 1 PR」と定めているが、中身は **8 系統**ある。

| # | 内容 | 性質 |
| --- | --- | --- |
| 1 | `backend/`(uv / ruff / ty / pytest 雛形) | プロダクト骨格 |
| 2 | **`frontend/`(Vue 3 + TypeScript)** | **プロダクト骨格 ← 本タスク** |
| 3 | `docker-compose.yml`(開発用 PostgreSQL) | プロダクト骨格 |
| 4 | `contracts/` 雛形 | プロダクト骨格 |
| 5 | CI 本体(backend / frontend ジョブ) | ハーネス |
| 6 | `onboarding.md` の完成と **v1.0 approved 化** | **確定ゲートが要る** |
| 7 | `docs/ops/nfr021-acceptance/` の新設 | 受入統制 |
| 8 | `verify_nfr021_evidence.py` + 失効パス正本 + append-only の CI 検査 | 受入統制(重い) |

完了条件も「**NFR-021 受入ゲート(10.1)の Phase 4 判定に合格**」で、`gate_kind: phase4` の判定を Phase 4 PR 上で検証器を直接実行して行い、合格した場合にのみ develop へマージ、と定められている。

**PO 判断: 分割し、frontend から着手する。**

## 本タスクで扱うもの(着手時点の把握)

- `frontend/` の骨格。**Vue 3 + TypeScript**(ADR-002 で approved・要件書 7.1 も v1.9 で追随済み)
- ツールチェーンは ADR-002 / 設計書 5.2 のとおり: **mise**(Node 版管理)/ **pnpm** / **ESLint**(flat config)+ eslint-plugin-vue + typescript-eslint / **Prettier** / **vue-tsc** / **Vitest** + Vue Test Utils
- `/check` の frontend 層 4 種が通る状態にする

## 計画段階で決めること

1. **設計書 13 章の Phase 4 行を分割する節更新のゲート区分** — 7.6-3 前段(PR レビュー)か後段(確定ゲート)か。**Phase の分割は完了条件の構造に触れる**ため、F1 のときより判断が微妙。**PO 裁定に掛ける**
2. **CI の frontend ジョブを本タスクに含めるか** — 含めないと、骨格が CI で検証されない状態が残る
3. **Playwright(E2E)を骨格に含めるか** — NFR-019 は 3 ランナー(pytest / Vitest / Playwright)を要求するが、E2E は実画面が要る。骨格段階では過剰かもしれない
4. **`docs/design/` の扱い** — 設計書 4 章の目標ツリーは `docs/design/`(アーキテクチャ・DB スキーマ・API・同期プロトコル)を挙げているが**未作成**。frontend 骨格に設計文書が要るかは要判断

## 調査(2026-08-16)— 旧リポに実在の React SPA を発見

PO から「**旧リポのフロントをそのまま流用したい**」との提起があり、保全先
`masaki1025/Baseball_Scoring-archive`(タグ `pitchlog-req-v2.0-evidence`)を取得して実物を読んだ。
全事実と典拠は [research.md](../features/frontend-skeleton/research.md)。

**既存の legacy 調査に載っていない `frontend/` が実在した。**

| 項目 | 実測 |
| --- | --- |
| 実体 | **React 19 + Vite + TypeScript の SPA** |
| 規模 | **10,541 行** / TS・TSX 48 ファイル / **9 画面** |
| 状態管理 | Zustand(`pitchDraft` / `authStore` / **`syncStore`**) |
| 通信 | TanStack Query v5(楽観的更新)+ **モックモード**付き |
| 描画 | 素の SVG・**`viewBox="0 0 263 263"` = 保存座標系と同一** |
| テスト | **0 件** |

既存調査が扱っていたのは **Streamlit 版の入力画面**(`app/pages/game_input.py`)と
**未ビルドで死んでいた `components/plate_component/`** で、**この `frontend/` とは別物**だった。

`GameScreen.tsx` だけで **1,423 行**(全体の 13%)。`syncStore.ts` があり、**同期はコア領域**。

## 決定(PO 裁定 2026-08-16)

**Vue へ移植する。正本(ADR-002・要件書 7.1)は改訂しない。**

旧 `frontend/` は **ADR-002 が定める「仕様・挙動の参照資料」として扱う** — 画面構成・入力 UX・
座標系・状態設計・API 契約を踏襲し、**実装は Vue 3 + TypeScript で書く**。**確定ゲートは不要**。

**この判断は ADR-002 の条項どおり**である(「旧システムの React UI コードは仕様・挙動の参照資料と
してのみ扱い、コード再利用はしない」)。コードを流用する案も検討したが、**ADR-002 と要件書 7.1 の
両方が approved** で、改訂には確定ゲートが要る。**PO は正本を維持する方を選んだ**。

## 未決・次の一歩

- **設計書 13 章の Phase 4 分割のゲート区分** — PO 裁定へ(7.6-3 前段 = PR レビュー / 後段 = 確定ゲート)
- **CI の frontend ジョブを本タスクに含めるか**
- **Playwright(E2E)を骨格に含めるか**(NFR-019 は 3 ランナーを要求)
- **旧 `frontend/` の参照資料としての置き場** — `docs/legacy/` は**版固定アーカイブで変更禁止**
  (絶対規則 3)。典拠(リポ + コミット SHA)の記録に留めるか、版固定で追加するか
- **旧 `frontend/` が要件書 v2.0(全面踏襲)をどこまで満たしているか** — **未調査**。移植前に画面ごとの
  差分を取る必要がある
- 次の一歩: 上記のゲート区分を裁定に掛けて `/plan`
