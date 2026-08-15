---
feature: frontend-skeleton
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-08-16・山田正輝)  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3bd93b75e6878175b456cc21de68c3e3
branch: feature/frontend-skeleton
created: 2026-08-16
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 7          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: frontend 骨格(Vue 3 + TypeScript)— Phase 4-1

## 1. 背景・目的

**pitchlog のプロダクトコードは 0 行**で、`backend/` `frontend/` `contracts/` はディレクトリごと存在しない。着手時点のリポジトリ約 2 万行はすべてハーネスである。**本タスクが最初のプロダクトコード**になる。

旧リポ(保全先 `masaki1025/Baseball_Scoring-archive`・タグ `pitchlog-req-v2.0-evidence`)に **React 19 + Vite + TypeScript の SPA が実在する**(10,541 行・9 画面)。既存の legacy 調査には載っていなかった。調査の全事実と典拠は [research.md](research.md)。

### PO 裁定(2026-08-16)

1. **Phase 4 を分割し、frontend から着手する**
2. **Vue へ移植する。ADR-002・要件書 7.1 は改訂しない。** 旧 `frontend/` は ADR-002 が定める**「仕様・挙動の参照資料」**として扱う
3. **目標は「完全に同じもの」** — 見た目・挙動を旧 UI と一致させ、**Vue と React の差で不可避な違いだけを許容**する
4. **設計書 13 章の改訂は確定ゲートを先に通す**(計画レビュー 1 周目 P1-4)

**3 が設計方針を決める。** 「似せる」のではなく**機械的な逐語移植**にし、不可避な差分を**あらかじめ規則として固定**する。

**4 により本タスクは 2 段構成**になる — 設計書 13 章の改訂 → **確定ゲート** → 骨格の実装。

## 2. スコープ

### やること

**A. 設計書の改訂(確定ゲート対象)** — **13 章 + 10.1 + 8.4**(確定ゲート 5・6 周目で範囲拡張)+ **`.claude/skills/release/SKILL.md` と `.claude/core-areas.json` の同期**

Phase 4 を複数 PR へ分割するため、13 章へ次を**正本として**書く。

- **分割後の PR 列 = 6 論理スロット**(**物理 PR 数ではない** — 4-6 には 0 回以上の再試行 PR が属するため、成功時 6 本・再試行 n 回なら 6+n 本。確定ゲート 3 周目 P1)**+ Phase 4 外の後処理 `P4-後` 1 本**(確定ゲート 4 周目 P1 で Phase 4 の範囲を 4-1〜4-6 に閉じた): **4-1** frontend 骨格 + CI の frontend ジョブ / **4-2** backend 骨格 + CI の backend ジョブ / **4-3** docker-compose・contracts / **4-4** 失効対象パスの正本 + `docs/ops/nfr021-acceptance/` の README・テンプレート〔**確定ゲート**〕/ **4-5** 証跡検証器・append-only 検査 / **4-6** onboarding v1.0 + `win-setup` の選定 + Phase 4 の受入判定 / **`P4-後`**(Phase 4 外) 完了証跡の記録 + `/release` 手順 0 の置き換え + 13 章の現況追随)。**CI 本体は独立 PR にせず 4-1・4-2 へ分散**し、**docs-ops と検証器は分離**する(確定ゲート 1 周目 P1)。**`/release` の置換を `P4-後` へ分離**したのは、マージと事後検査が原子的に実行できないため(同 2 周目 P0)。**`P4-後` を Phase 4 外とした**のは、Phase 4 に含めたまま完了を 4-6 時点と定めると Phase 4 の一部を 4-6 の証跡が覆えないため(同 4 周目 P1)
- **各 PR のマージ条件**(NFR-021 受入ゲートは Phase 4 **全体の完了時**に係る。各分割 PR のマージ条件は何か)
- **最終統合と NFR-021 判定の担当**(どの PR が `gate_kind: phase4` を実行するか)

**B. 骨格の実装**

1. **`frontend/` の骨格**(mise / pnpm / Vite + Vue 3 + TypeScript + **Tailwind v4**)
2. **品質ツール**(ESLint flat config + eslint-plugin-vue + typescript-eslint / Prettier / vue-tsc / Vitest + Vue Test Utils + **jsdom**)
3. **移植の受け皿と規則**(旧と 1:1 のディレクトリ + `porting-rules.md`)
4. **逐語移植の実証**(`lib/format.ts` の `cx` → `StrikeZone.vue` + 比較用 host + Vitest)
5. **CI の frontend ジョブ**

### やらないこと

- **9 画面の移植**(`GameScreen.tsx` だけで 1,423 行)
- **`syncStore.ts` の移植** — 同期は**コア領域**。敵対レビュー + 人間の逐行確認が必須
- **Playwright(E2E)と visual regression** — **申し送り(時期は「最初の画面移植と同時または直前」)**。骨格段階は対象画面が 1 コンポーネントのみ(1 周目 P2-3 で前倒し)
- **backend / docker-compose / contracts** — Phase 4 の別タスク

## 3. 影響する正本

| 正本 | 変更内容 | ゲート |
| --- | --- | --- |
| [開発ハーネス設計書](../../development/dev-harness-design-2026-08-07.md) | **13 章の Phase 4 を複数 PR へ分割** + **10.1 の「手順 0 の置換は Phase 4 の PR でのみ」を `P4-後` へ同期**(確定ゲート 5 周目 P1 で範囲拡張)。PR 列・各 PR のマージ条件・最終統合と NFR-021 判定の担当を明記。**版繰り上げ(1.5 → 1.6)** | **finalize-doc**(運用規約の構造変更 — 7.6-3 後段。**PO 裁定 2026-08-16**・計画レビュー 1 周目 P1-4) |
| [docs/README.md(索引)](../../README.md) | 設計書を **v1.6** へ・最終更新を現行化 | PR レビュー |
| [要件定義書](../../requirements/requirements-pitchlog-2026-07-22.md) / [ADR-001](../../adr/ADR-001-codex-model-selection.md) / [ADR-002](../../adr/ADR-002-frontend-vue.md) / [改善台帳](../../improvements-from-baseball-scoring.md) / [決定記録](../../requirements/requirements-draft-pitchlog.md) / [オンボーディング](../../development/onboarding.md) / [GitHub リポジトリ設定手順](../../development/github-setup.md) / [ハーネス運用評価台帳](../../development/harness-evaluation.md) | **反映なし** — 本タスクは ADR-002 と要件書 7.1 の**決定どおりに実装する**ものであり、記述を変えない | — |

### 正本体系外だが同一 PR で更新するもの

| ファイル | 変更内容 |
| --- | --- |
| `frontend/**` | **新規**。骨格一式 |
| `mise.toml` | **新規**。Node 版の固定 |
| `.github/workflows/ci.yml` | frontend ジョブ + **Node / Corepack / pnpm のセットアップ**を追加。**`guard_paths` 該当 → core-guard 発火・逐行確認必須** |
| `.gitignore` | `node_modules` 等 |
| `docs/features/frontend-skeleton/porting-rules.md` | **新規**。React → Vue の移植規則 |
| `.claude/skills/release/SKILL.md` | **手順 0 の置換主体を `P4-後` へ同期** + **報告文の使い分け**(確定ゲート 5・7 周目)。**本タスクで `guard_paths` へ追加した**(同 6 周目 P1) |
| `.claude/core-areas.json` | **`guard_paths` へ `release/SKILL.md` を追加**(確定ゲート 6 周目 P1)。**同ファイル自身も `guard_paths`** |
| `.claude/skills/task-done/SKILL.md` | **`P4-後` の起票・相互リンクの手順を追加**(確定ゲート 7 周目 P1 — 設計書に書くだけでは実行経路が無い) |
| `docs/worklog/2026-08-16-frontend-skeleton.md` | 本タスクの記録 |

## 4. 実装方針

### 重さ分類 = 通常(根拠)

`.claude/core-areas.json` の `areas[].paths` に該当 **0 件**(`syncStore` の移植をスコープ外にしたため)。ただし **`guard_paths` に 3 件該当**するため、**core-guard が発火し逐行確認チェックが必須**になる — **`.github/workflows/ci.yml`**(ステップ 6)/ **`.claude/core-areas.json`**(ステップ 1 で `guard_paths` を変更)/ **`.claude/skills/release/SKILL.md`**(同・追加された結果として対象になる)。**逐行確認は検出パスの和集合に対して PR 全体で 1 個**のチェックで足りる(`pr/SKILL.md` の実装 — 確定ゲート 7 周目の確認結果)。

### A. 「完全に同じ」を成立させる条件

実測で、**フレームワーク層以外はそのまま運べる**ことを確認した(research.md §1)。

| 資産 | 移植のしかた |
| --- | --- |
| `index.css` | **`#root` → `#app` 以外そのまま**。`@import "tailwindcss"`・`@apply`・keyframes・dark utility は**そのまま使える**(1 周目の確認結果) |
| `vite.config.ts` | **`@vitejs/plugin-react` → `@vitejs/plugin-vue` のみ差し替え**。`@tailwindcss/vite`・`/api` プロキシは同一 |
| SVG マークアップ | **逐語**。`viewBox="0 0 263 263"` は保存座標系と同一で変換不要 |
| Tailwind クラス文字列(**1,102 箇所**) | 値を変えない |
| ディレクトリ・ファイル名・props | **1:1** |

**CSS 以外で置換が必要なもの**(1 周目の確認結果): `index.html` の mount id と entry / `main.tsx` / `tsconfig.json` の `jsx: react-jsx`。

### B. 移植規則 — 必須カバレッジ(1 周目 P1-1)

**当初は「対応表 11 行」としていたが、旧実装の実在パターンを覆えないと判明した。** 行数ではなく**カバレッジ**で規定する。`porting-rules.md` は次の **4 分類すべて**を扱い、**各項目に旧実装の典拠(ファイル:行)を付ける**。

| 分類 | 必ず扱う項目 | 旧実装の実例 |
| --- | --- | --- |
| **props / emits / slots / attrs** | callback prop → `emit` / `className` prop → **ルートへの fallthrough attrs** / `children` → **slots** / `...rest`(DOM 属性の継承) / Context → **provide/inject** | `StrikeZone`(`onTap`・`className`)/ `Button`(`ButtonHTMLAttributes` + spread)/ `Sheet`(`children`)/ `Toast`(Context) |
| **lifecycle / reactivity** | `useState` → `ref`/`reactive` / `useRef` → template ref / `useCallback` → メソッド / `useEffect` + **cleanup** → `onMounted`/`onUnmounted`/`watchEffect` / `useMemo` → `computed` / `useId` → **`useId()`**(採用 Vue 版を明記) | `Sheet`(フォーカス復帰・window listener の cleanup)/ `BaseDiamond`(`useId`) |
| **JSX → template 属性** | form / event / `style={{...}}` / **SVG 属性**(ケバブケース) | `BaseDiamond`(`style`・SVG 属性) |
| **router / query / store** | 認証リダイレクトと全 route / Provider の置き場 / **永続化方式**(キー `bb.auth`)と **hydration** / **`getState()` の命令的参照**の代替 | `App.tsx`(route + Provider)/ `authStore`(永続化)/ `api/client.ts`(`getState()`) |

**ライブラリの対応**: Zustand → **Pinia** / `@tanstack/react-query` → **`@tanstack/vue-query`** / react-router 7 → **vue-router 4** / lucide-react → **lucide-vue-next**。

### C. 依存と版固定(1 周目 P1-3)

**「無指定 install」を禁じる。** 次を**すべて明示 pin** する。

- **今すぐ入れるもの**: `vue` / `vite` / `@vitejs/plugin-vue` / `typescript` / `tailwindcss` / `@tailwindcss/vite` / ESLint 一式(`eslint`・`eslint-plugin-vue`・`typescript-eslint`)/ `prettier` / `vue-tsc` / `vitest` / `@vue/test-utils` / **`jsdom`**(**Vitest の既定環境は Node** — コンポーネント mount に必要)
- **将来入れるもの(バージョンだけ先に決めて `porting-rules.md` に記録)**: `pinia` / **`vue-router@4`**(**無指定だと 4 系が入らない可能性がある** — 明示 pin する)/ `@tanstack/vue-query` / `lucide-vue-next`

**セットで固定する**: `mise.toml` の Node 版 / `package.json` の `packageManager`(corepack)/ **`pnpm-lock.yaml` をコミット** / CI は **`pnpm install --frozen-lockfile`**。

**未確認**(実装ステップの最初に `pnpm add` で確かめ、無ければ計画へ差し戻す): `@tanstack/vue-query` / `lucide-vue-next` / `vue-router` の 4 系指定。

### D. 「同じ」を検証する手段(H-48 対策)

**「完全に同じ」を掲げる以上、検証手段がなければ合格条件が実効性を持たない**(台帳 H-48)。

**本タスクは目視比較。ただし比較条件を固定する**(1 周目 P1-2 — 条件を固定しない目視は再現できない):

| 軸 | 固定する値 |
| --- | --- |
| `point` | あり / なし |
| `plateSide` | 右打者 / 左打者 |
| 状態 | 通常 / `disabled` / `highlight` |
| カラースキーム | light / dark |
| viewport | **固定値を決めて worklog に記録** |

旧フロントは **`npm run dev:mock`(バックエンド不要)**で起動できる。**同じ組合せを両方で表示して比較し、結果を worklog に記録する。**

**自動比較(Playwright の visual comparison)は申し送り。時期は「最初の画面移植と同時または直前」**(1 周目 P2-3 — 「Phase 4 完了時」では遅い)。**本タスクでは「目視で確認した」以上を主張しない。**

### 落とし穴

| # | 内容 |
| --- | --- |
| 1 | **Tailwind v4 は CSS-first 設定**。`tailwind.config.js` は無く `index.css` の `@import "tailwindcss"` が正。**v3 の設定方法を持ち込まない** |
| 2 | **`/check` の frontend 層は「存在すれば実行」**。`frontend/package.json` を作った時点で 4 種すべてが対象になる。**1 つでも落ちると /check が赤** |
| 3 | **`.github/workflows/ci.yml` は `guard_paths`**。触ると core-guard が発火する |
| 4 | **旧 `frontend/` はリポジトリ外**(scratchpad の clone)。**参照は典拠(リポ + コミット SHA)で記録**し、`docs/legacy/` へは追加しない(**版固定アーカイブで変更禁止** — 絶対規則 3) |
| 5 | **jsdom はレイアウト計算をしない**。`getBoundingClientRect()` は幅・高さが 0 になるため、**座標テストは固定スタブを置かないと意味を失う**(1 周目 P1-2) |
| 6 | **既存 CI に Node / Corepack / pnpm の準備が無い**。frontend ジョブはセットアップから書く。**Action は SHA pin**(既存方針) |

## 5. 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | 内容 | 合格条件 |
| --- | --- | --- |
| 1 | **設計書の改訂**: `status` を in-review へ + 変更履歴に **v1.6** 行 + 索引の同時更新。**13 章**へ Phase 4 の分割(PR 列・各 PR のマージ条件・最終統合と NFR-021 判定の担当)。**10.1・8.4** の「手順 0 の中断条件」を**状態ベース**へ・置換主体を **`P4-後`** へ。**`release/SKILL.md` を同期**し **`core-areas.json` の `guard_paths` へ追加** | `check_docs_status.py` exit 0(**版と最終更新を索引と同時に更新しないと落ちる**)/ 13 章に **PR 列・マージ条件・判定担当の 3 点**がある / **NFR-021 の合格項目は変えていない**(要件書 NFR-021 の測定方法が正)。**変えたのは運用プロトコル** — 中断条件の判定方法(時点 → 状態)・置換の時点と資格・完了の成立時点 |
| — | **← ここで `/finalize-doc`(確定ゲート・敵対レビュー + 人間承認)→ 設計書 v1.6 approved** | 確定ゲート通過 |
| 2 | **`frontend/` の骨格**: `mise.toml`(Node 固定)/ corepack + pnpm(`packageManager`)/ Vite + Vue 3 + TS / **Tailwind v4**。`index.css`・`vite.config.ts` を移植(`#root`→`#app`・plugin 差し替え)。`index.html`・entry・`tsconfig.json` は Vue scaffold 側へ置換 | `pnpm install --frozen-lockfile` が通る / **`pnpm-lock.yaml` がコミットされている** / `pnpm dev` で開発サーバが起動し**ブラウザに表示される** / `pnpm build` が通る / **C 節の「今すぐ入れるもの」がすべて明示 pin されている** |
| 3 | **品質ツール**: ESLint(flat config)+ eslint-plugin-vue + typescript-eslint / Prettier / vue-tsc / Vitest + Vue Test Utils + **jsdom** | **`/check` の frontend 層 4 種がすべて通る** / **`pnpm test` は `vitest run`**(watch にしない — `/check`・CI と一致させる)/ **`pnpm build` に `vue-tsc` を含めるかを決めて固定**(1 周目 P2-2)/ Vitest のテストが 1 件以上あり green |
| 4 | **移植の受け皿と規則**: 旧と 1:1 のディレクトリ(`api` / `components/{analysis,analysis/player,diamond,field,game,pads,scoreboard,ui,zone}` / `lib` / `screens` / `stores`)+ **`porting-rules.md`** | ディレクトリが旧と 1:1(**`components/analysis/player` を含む** — 1 周目 P2-1)/ `porting-rules.md` が **4 節 B の 4 分類すべて**を扱う / **各項目に旧実装の典拠(ファイル:行)がある** / **C 節の「将来入れるもの」のバージョンが記録されている** |
| 5 | **逐語移植の実証**: `lib/format.ts` の `cx` → `StrikeZone.vue` + **比較用 host** + Vitest | **`cx` が先に移植されている**(`StrikeZone` が import するため — 1 周目 P1-2)/ **SVG マークアップが逐語**(`viewBox`・ゾーン矩形 `Z` の値・3 分割)/ **Tailwind クラス文字列が同一** / **props が 1:1**(`onTap` → `emit`・`className` → fallthrough)/ **比較用 host が D 節の組合せをすべて表示する** / **`getBoundingClientRect()` の固定スタブ**を置いた座標テスト / **旧をモックモードで起動して目視比較し、結果を worklog に記録** |
| 6 | **CI の frontend ジョブ**: Node / Corepack / pnpm のセットアップ + `pnpm install --frozen-lockfile` → ESLint → `prettier --check` → `vue-tsc` → Vitest | paths filter に **`frontend/**`・`mise.toml`・`pnpm-lock.yaml`・`ci.yml` 自身**を含む(1 周目 P1-3)/ **追加 Action は SHA pin** / 既存 4 ジョブに影響しない / `tests/test_core_guard.py` green(**`REQUIRED_CHECK_TEXT` に触れない**) |

## 6. DoD(受け入れ基準)

- [ ] **設計書 13 章に Phase 4 の分割が正本として書かれ、確定ゲートを通過して approved**(v1.6)
- [ ] **`frontend/` が存在し、`pnpm install --frozen-lockfile` → `pnpm dev` でブラウザに表示される**
- [ ] **`/check` の frontend 層 4 種がすべて通る**
- [ ] **依存が明示 pin されている** — C 節の「今すぐ入れるもの」全件 + `pnpm-lock.yaml` をコミット + `mise.toml` の Node 固定 + `packageManager`
- [ ] **`porting-rules.md` が 4 分類(props/emits/slots/attrs・lifecycle/reactivity・JSX→template 属性・router/query/store)すべてを扱い、各項目に旧実装の典拠がある**
- [ ] **逐語移植の実証 1 件**(`StrikeZone.vue`)— SVG・クラス文字列・props が旧と一致
- [ ] **比較条件を固定した目視比較の結果が worklog にある**(point / plateSide / 状態 / light-dark / viewport)
- [ ] **CI に frontend ジョブがあり緑**。paths filter が `frontend/**` 以外も拾う
- [ ] **コア領域に触れていない**(`syncStore` はスコープ外)

## 7. テスト計画

| 対象 | ケース |
| --- | --- |
| `StrikeZone.vue`(ステップ 5) | **正例 3**(ゾーン矩形の描画が定数 `Z` どおり / `plateSide` で打者シルエットの左右が入れ替わる / `highlight` でクラスが付く)・**負例 2**(`disabled` のときタップを無視する / **範囲外の座標が `0.1`〜`262.9` に丸められる**)。**すべて `getBoundingClientRect()` の固定スタブ**の上で行う |
| 骨格(ステップ 2・3) | `pnpm build` が通る(型検査を含む) |

**視覚的な同一性は自動テストしない**(本タスクでは固定条件の目視比較のみ)。

## 8. 本タスクに含めないもの(申し送り)

- **9 画面の移植** — 移植規則が固まってから 1 画面ずつ。`GameScreen`(1,423 行)は単独タスク
- **`syncStore` の移植** — **コア領域**。敵対レビュー + 人間の逐行確認が必須
- **Playwright(E2E)と visual regression** — **最初の画面移植と同時または直前**に導入する(1 周目 P2-3)。「完全に同じ」の自動検証はここで入る
- **旧 `frontend/` が要件書 v2.0(全面踏襲)をどこまで満たしているか** — **未調査**。移植前に画面ごとの差分を取る
