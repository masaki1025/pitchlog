# 調査: frontend 骨格(Vue 3 + TypeScript)— Phase 4-1

- 日付: 2026-08-16
- 対象: 旧リポの `frontend/` の実態、ADR-002・要件書 7.1 との関係、移植の前提

**すべての事実に典拠を付ける。** 旧リポの記述は保全先 `masaki1025/Baseball_Scoring-archive`（private・タグ `pitchlog-req-v2.0-evidence`）の実物を読んだ結果。

---

## 0. 最重要の発見 — 既存の legacy 調査に載っていない実在の React SPA

**旧リポには実在する `frontend/`（React 19 + Vite + TypeScript の SPA）がある。**

`docs/legacy/research/` の既存調査はこれを扱っていない。既存調査が対象にしていたのは:

- **Streamlit 版のメイン入力画面**（`app/pages/game_input.py` 約 1,680 行 — `docs/legacy/research/input-screen.md`）
- **未ビルドで死んでいた React カスタムコンポーネント**（`components/plate_component/` — 同 `:203`・`:263`「**rerun 削減の切り札だった React コンポーネントが未ビルドで死んでいる**」）

**この 2 つと `frontend/` は別物である。** ADR-002 が「旧システムの React UI コード」と書いているのは、実質この `frontend/` を指すと解される（要件書 2.3 の「API+React 新 UI」に対応）。

### 典拠の固定

| 項目 | 値 |
| --- | --- |
| リポジトリ | `masaki1025/Baseball_Scoring-archive`（private・保全済み） |
| タグ | `pitchlog-req-v2.0-evidence` |
| `frontend/` の最終更新コミット | `042385188761b3fd1cdcd5aaf7dcde98fb48d04d`（2026-07-14) |

---

## 1. 旧 `frontend/` の実測

### 1-1. 技術スタック（`frontend/package.json`）

| 種別 | 採用 |
| --- | --- |
| ビルド | **Vite 7** |
| フレームワーク | **React 19** |
| 言語 | **TypeScript 5.9** |
| ルーティング | react-router 7 |
| サーバ状態 | **TanStack Query v5**（`useMutation` + `onMutate` の楽観的更新） |
| クライアント状態 | **Zustand 5** |
| CSS | **Tailwind CSS v4**（`@tailwindcss/vite`） |
| アイコン | lucide-react |

### 1-2. 規模

**TS/TSX 48 ファイル・10,541 行。**

| 画面 | 行数 |
| --- | --- |
| `GameScreen.tsx` | **1,423** |
| `LineupScreen.tsx` | 497 |
| `TeamScreen.tsx` | 319 |
| `KarteScreen.tsx` | 317 |
| `AnalysisScreen.tsx` | 294 |
| `LoginScreen.tsx` | 202 |
| `StartScreen.tsx` | 197 |
| `PlaysScreen.tsx` | 149 |
| `HelpScreen.tsx` | 81 |

### 1-3. 構成

```
src/
├── api/        client.ts / endpoints.ts / types.ts / mock.ts
├── components/
│   ├── analysis/   KarteExportSheet / StrategyDashboard / player/PlayerAnalysisPanels
│   ├── diamond/    BaseDiamond
│   ├── field/      FieldDiagram
│   ├── game/       BottomBar / CheatSheet / EditLastSheet / HeaderPlayerInfoPopover /
│   │               MenuSheet / PickoffSheet / QuickKarteNoteSheet / StateOverrideSheet / StrategySheet
│   ├── pads/       PitchTypeChips / ResultPad / SpeedPad
│   ├── scoreboard/ BatterPitcherCard / CountDisplay / MiniScoreboard
│   ├── ui/         Button / Sheet / Toast
│   └── zone/       StanceGrid / StrikeZone
├── lib/        count.ts / fielder.ts / format.ts / useKeydown.ts / vocab.ts
├── screens/    (上表の 9 画面)
└── stores/     authStore.ts / pitchDraft.ts / syncStore.ts
```

### 1-4. 設計上の重要点

- **ゾーン・フィールド・ダイヤモンドは素の SVG**で、**`viewBox="0 0 263 263"` = 保存座標系（0〜263 float）と同一**（`frontend/README.md`）。旧 Streamlit 版が PIL で画像へ焼き込んでいた方式（`docs/legacy/research/input-screen.md:200-211`）とは異なり、**座標変換が不要**
- **モックモード**がある（`VITE_MOCK=1` または `--mode mock`）。**バックエンドなしで UI を確認できる**（`src/api/client.ts`）
- **`stores/syncStore.ts` が存在する** — 同期は `.claude/core-areas.json` の**コア領域**。移植時は**敵対レビュー + 人間の逐行確認が必須**になる
- **リトライキュー**の概念がある（`isRetryableError` — `src/api/client.ts`）
- 設計根拠は旧リポの `docs/ui_renewal_design_20260709.md`（§5 1球入力UX / §7 画面構成）と `docs/api_contract_v1.md`（API 契約 v1）

### 1-5. 欠けているもの

- **テストが 0 件**（`*.test.*`・`*.spec.*`・Vitest 設定のいずれも無し）
- ESLint / Prettier の設定なし（`package.json` の scripts は `dev` / `dev:mock` / `build` / `preview` のみ）
- 型検査は `build` 時の `tsc --noEmit` のみ

---

## 2. 正本との関係

### 2-1. 技術スタックは Vue で確定している

| 正本 | 記述 | 状態 |
| --- | --- | --- |
| **ADR-002** | **Vue.js(3系) + TypeScript** を採用 | approved(2026-08-07) |
| **要件書 7.1** | 技術スタック = Vue.js + TypeScript | approved(v1.9・2026-08-12 に確定ゲート通過) |

**ADR-002 は実装着手前に確定させる条件を満たしている**（同 ADR の帰結欄）。

### 2-2. コード再利用の禁止条項

ADR-002:

> 旧システムの React UI コードは**仕様・挙動の参照資料としてのみ扱い、コード再利用はしない**(もともと全面再構築方針 — 要件書 2.3)

要件書 2.3:

> pitchlog は既存システム（Streamlit版・API+React新UI）を**置き換える**。旧2UI併存は行わない（UIは1本）

### 2-3. PO 裁定(2026-08-16)

**Vue へ移植する。正本(ADR-002・要件書 7.1)は改訂しない。**

旧 `frontend/` は **ADR-002 が定める「仕様・挙動の参照資料」として扱う**。画面構成・入力 UX・座標系・状態設計・API 契約を踏襲し、**実装は Vue 3 + TypeScript で書く**。

**この裁定により確定ゲートは不要**（正本を変えないため）。

---

## 3. 移植の前提と留意点

| # | 論点 | 内容 |
| --- | --- | --- |
| 1 | **`GameScreen.tsx` が 1,423 行** | 1 画面で全体の 13%。**骨格タスクでは移植しない**。骨格は「移植先の受け皿」を作るところまで |
| 2 | **同期はコア領域** | `syncStore.ts` の移植は `.claude/core-areas.json` のコア領域に該当し、**敵対レビュー + 人間の逐行確認が必須**。**骨格タスクのスコープ外**にする |
| 3 | **座標系 0〜263 は要件由来** | 素の SVG で `viewBox="0 0 263 263"` を使う設計は移植先でも有効。**PIL 焼き込み方式へ戻さない** |
| 4 | **モックモードは踏襲価値が高い** | バックエンド未着手（Phase 4 の別タスク）でも UI を確認できる。**骨格に含める候補** |
| 5 | **旧フロントにテストが無い** | 移植先では **NFR-019 が Vitest を要求**する。テストは**新規に書く**ことになる |
| 6 | **API 契約 v1 は旧リポの文書** | `docs/api_contract_v1.md`。pitchlog 側の `contracts/` は未作成（Phase 4 の別タスク） |

---

## 4. 未確認・要判断

| # | 論点 | 状態 |
| --- | --- | --- |
| 1 | 設計書 13 章の Phase 4 分割の**ゲート区分** | **PO 裁定へ**(7.6-3 前段 = PR レビュー / 後段 = 確定ゲート) |
| 2 | CI の frontend ジョブを本タスクに含めるか | 計画段階で決める |
| 3 | Playwright(E2E)を骨格に含めるか | 計画段階で決める(NFR-019 は 3 ランナーを要求) |
| 4 | 旧 `frontend/` の**参照資料としての置き場** | `docs/legacy/` は**版固定アーカイブで変更禁止**(絶対規則 3)。**典拠(リポ + コミット SHA)の記録に留める**のが妥当か、`docs/legacy/` へ版固定で追加すべきかは要判断 |
| 5 | 旧 `frontend/` が要件書 v2.0(全面踏襲)を**どこまで満たしているか** | **未調査**。移植の前に画面ごとの差分を取る必要がある |
