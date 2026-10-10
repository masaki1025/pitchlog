---
feature: uf1-common-ui
status: in-review            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-10-10・山田正輝) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: コア領域        # 軽微 | 通常 | コア領域 | 機械的軽作業 — /plan が必ず置換する(空値・欠落はラッパーが停止。ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3f493b75e687810aafaaf6ba6d7a34a8
branch: feature/uf1-common-ui
created: 2026-10-09
計画レビュー周回: 2        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: U-F1 共通表示(汎用部品・取得補助)— TSK-516

## 1. 背景・目的

Notion: [TSK-516](https://app.notion.com/p/3f493b75e687810aafaaf6ba6d7a34a8)(優先度 中)。
単位定義: [frontend-impl-units/design.md](../frontend-impl-units/design.md) の U-F1 行(`:308`)。

製品 frontend は画面 0 枚で(`frontend/src/screens` 0 ファイル)、リハーサル(要件書 8 章の判定③ `:1085`)に必要な画面を移植する前に、
**全画面が共有する UI 部品**(`Button`・`Sheet`・`Toast` — 旧 `components/ui/`)と**取得補助**(`queryClient`・`teamSearch`)を
旧 React 実装 `dd03160` から Vue 3 へ移す。U-F1 は他の frontend 単位への実装依存が無く、U-X1(凍結中)を待たない。

担う FR の面(**分担のみ・主所有なし**): FR-002 の入力操作、FR-020〜023 の表示に共通する UI 器具
(分担行「FR-002 / U-X1 / U-F1 / 1 球入力に使う選択ボタンと操作通知の共通部品面」— 同 design.md `:429`)。

**作り方(PO 決定 2026-10-10 — 計画レビュー 1 回目 P0-1 の採用)**: 旧 React 実装は**仕様・挙動の参照資料としてのみ扱い、コードは複製しない**
(計画時の典拠は ADR-002 v1.0「旧システムの React UI コードは仕様・挙動の参照資料としてのみ扱い、コード再利用はしない」。**ADR-002 v1.1(2026-10-10・PR #112)はこの条項を「旧システムを依存として抱えることを禁じる。本リポジトリの資産として取り込み保守責任を負うものは、逐語一致でも当たらない」と明確化した**(`docs/adr/ADR-002-frontend-vue.md:36`)。したがって書き起こしは ADR の要求ではなく **PO の選択**であり、v1.1 とも矛盾しない)。
Vue 3 + TypeScript で書き起こし、**見た目と挙動が旧と同じであること**(PO 裁定 2026-08-16「完全に同じもの」の目標 — [frontend-skeleton/plan.md](../frontend-skeleton/plan.md) `:28`)を
Tailwind クラスの一致と試験で確かめる。`.ts` も逐語で置かず、リポジトリの書式(Prettier・日本語コメント)で書く。
要件書・改善台帳が改善を既決にした箇所は要件を優先する(I-28 — `docs/improvements-from-baseball-scoring.md:241-242`)。
`.tsx` → `.vue` の変換の形は[移植規則](../frontend-skeleton/porting-rules.md)に従う。

**既存の逐語 `.ts` との関係**: 骨格タスクで逐語移植した `.ts` 4 件(`frontend/.prettierignore:9-12`)は本タスクでは触らない。
ADR-002 の文言と 8/16 裁定の「機械的な逐語移植」の並存は、**ADR-002 v1.1 で整理された**(上記 `:36` — 逐語の 4 件と `index.css` は「本項に当たらない」と明記)。

調査: [research.md](research.md)(3 並列・2026-10-10)。

## 2. スコープ

### やること

| 旧(`dd03160:frontend/src/`) | 新(`frontend/src/`) | 移植の形 |
| --- | --- | --- |
| `components/ui/Button.tsx`(58 行) | `components/ui/Button.vue` + `Button.spec.ts` | `.tsx` → `.vue`(4 点判定) |
| `components/ui/Toast.tsx`(72 行) | `components/ui/Toast.vue` + `Toast.spec.ts` | 同上 |
| `components/ui/Sheet.tsx`(159 行) | `components/ui/Sheet.vue` + `Sheet.spec.ts` | 同上 |
| `lib/queryClient.ts`(12 行) | `lib/queryClient.ts` + `queryClient.spec.ts` | 書き起こし(既定値 3 つは旧と同じ) |
| `lib/teamSearch.ts`(28 行) | `lib/teamSearch.ts` | 書き起こし(仕様は旧と同じ — 試験で固定) |
| `lib/teamSearch.test.mjs`(35 行) | `lib/teamSearch.spec.ts` | Vitest へ書き換え(4 ケースの入力・期待値は不変) |

- **依存 2 件の追加**(PO 決定 2026-10-10 — 本 PR に含める): `@tanstack/vue-query` **5.101.4**・`lucide-vue-next` **1.0.0**
  (版は [porting-rules.md](../frontend-skeleton/porting-rules.md) `:79-84` の記録。2026-10-10 に `pnpm view` で再測 — vue-query の最新は 5.104.1 だが記録版を採る。
  記録版の公開日は 2026-07-21 / 2026-03-23 で十分に古い)。**本計画書の承認をもって、両ライブラリの導入の承認とする**
  (要件書 7.1 `:1059` の「技術スタックの変更」に当たるかは条文に定義が無い — research.md 1 節。安全側で計画書の人間承認に載せる)
- 移植規則に無い不可避差分の記録(4 節の逸脱表)を [porting-rules.md](../frontend-skeleton/porting-rules.md) へ追記する
- 単位定義の U-F1 行に、`registerServiceWorker` の切り出しを注記する

### やらないこと

- **`lib/registerServiceWorker.ts` と `public/sw.js`** — **U-F1 から外し [TSK-533](https://app.notion.com/p/3f493b75e68781db829cfa994b45a9e0) へ切り出した**(PO 決定 2026-10-10)。
  理由: `sw.js` はどの単位にも未割り当て・PWA の PO 裁定が v2.0 から未決・旧の persist 拒否の黙殺が FR-012 `:330` と矛盾(research.md 3 節)
- **`index.css`** — 移植済み(`#root`→`#app` 以外は逐語 — research.md 4-1 節)。触らない
- **`App.vue`・`main.ts` への配線**(VueQuery plugin の install・`Toast` を App root に置く)— **U-F13 の範囲**(design.md `:320`)。
  U-F1 は部品と `queryClient` を export するだけで、配線は U-F13 が行う。U-F1 の試験は試験側で Provider を組んで検証する
- 認証変化での `queryClient.clear()` — 旧 `authStore.ts:33,37` にあり **U-F2 の範囲**(テナント分離のキャッシュ無効化の面)
- `pinia`・`vue-router` の追加(U-F1 は使わない)
- Playwright による見た目の自動比較の導入(画面ではないため。最初の画面移植の単位へ — frontend-skeleton/plan.md `:59,195`)
- teamSearch の重複除去規則の変更(FR-039 の同名登録との衝突は呼び出し側 U-F5・U-F10 への申し送り — research.md 末尾)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| (なし) | **反映なし**。要件書・設計書・ADR・ハーネス設計書・ops のいずれも変えない。ライブラリ 2 件の導入は ADR-002(フレームワーク・ツールチェーンのみを決定 — `:26-28`)の射程外で、本計画書の承認で扱う | — |
| `docs/development/harness-evaluation.md` | `/pr` クローズ処理で追記(PR 作成時に宣言を追加): **H-69 へ再発の実測**(Codex の sandbox で pnpm ストアを `/tmp` へ逃がし `--frozen-lockfile` が TTY 確認で停止・閉域 spec の子プロセス起動が `EPERM`)と **候補 (13) へ再発・亜種の実測**(`git -C $W`・heredoc 本文の語句・複雑な引用符で git_guard が遮断)。`H-*` は採番しない・版は上げない | PR レビュー(7.6-3 前段) |
| `docs/README.md` | 台帳行の最終更新日を現行化 | PR レビュー |

正本ではない文書で更新するもの(PR レビューで扱う):
- `docs/features/frontend-skeleton/porting-rules.md` — 4 節の逸脱表を「U-F1 で追加した不可避差分」として追記
- `docs/features/frontend-impl-units/design.md` — U-F1 行(`:308`)に `registerServiceWorker` を TSK-533 へ切り出した旨を注記

## 4. 実装方針

### 重さ分類: コア領域

- **根拠**: 依存追加で `frontend/package.json`・`frontend/pnpm-lock.yaml` を変更し、両者は `.claude/core-areas.json` の
  **`sync-protocol` と `game-state` の paths** に当たる(research.md 2-2 節で実測)。PO が依存追加を本 PR に含めると決めたため(2026-10-10)、
  **PR 全体がコア領域**になる → 敵対レビュー + 人間の逐行確認
- **意味上の判定(契約 4 — 6.3 の 5 領域)**: U-F1 が担う面(汎用 UI 部品・取得キャッシュの生成)は **5 領域すべて非該当**
  (design.md `:329,356`)。S 同期: 同期キュー・送信に触れない / G 状況: 状況計算を持たない / R 記録権: 触れない /
  T テナント: キャッシュの消去は U-F2(旧 `authStore.ts:33,37`)で U-F1 は生成と既定値のみ / D 移行: 触れない(`format.ts` は読むだけで変更しない)。
  **機械判定(paths)だけがコアで、意味判定は非該当**という状態である
- 本体ファイル(`components/ui/*`・`lib/queryClient.ts`・`lib/teamSearch.ts`・spec・`eslint.config.js`・`.prettierignore`)はコア paths に当たらない(research.md 2-2 節)

### 移植の決定(移植規則に無い・または規則から外れるもの)

| # | 対象 | 決定 | 根拠 |
| --- | --- | --- | --- |
| A | `Sheet` の背景ロック | 旧 `getElementById('root')`(旧 `Sheet.tsx:38`)を **`'app'`** にする | 現行のマウント先は `#app`(`frontend/index.html:22`・`src/main.ts:5`)。逐語のままだと常に代替経路(body 直下の全要素を inert — 旧 `:39-43`)に入る。`porting-rules.md:93-94` は `index.css` の `#root`→`#app` しか規定していない → 同じ不可避差分として追記 |
| B | `Sheet` のポータル | `createPortal(…, document.body)` → **`<Teleport to="body">`** | React と Vue の差で不可避 |
| C | `Sheet` の開閉副作用 | React の `useEffect([open])` → **変化は `watch(() => props.open, …, { flush: 'post' })`、初期 `open=true` は `onMounted` で同じ開く処理を走らせ**(どちらも DOM 反映後)、**後始末は閉じたとき・`onBeforeUnmount` の両方で行う** | React の effect は初回描画後にも走り(旧 `:95`)、DOM 反映後に閉じるボタンへフォーカスする(`:98`)。Vue の `watch` は値が変わったときしか走らず(初期値では走らない)、既定では DOM 反映前に走る。`immediate: true` は初回を同期で実行し template ref がまだ null のため使わない(計画レビュー 1 回目 P0-2) |
| D | `Sheet` の閉じるアイコン | `lucide-react` の `<X size={22} />` → **`lucide-vue-next` の `<X :size="22" />`** | 規則 `porting-rules.md:84`。**計画段階で照合済み(2026-10-10・両パッケージの tarball を `npm pack` で取得 — `dd03160` の lock の解決版は lucide-react 0.525.0)**: パス 2 本(`M18 6 6 18`・`m6 6 12 12`)と svg 属性(`xmlns`・`viewBox 0 0 24 24`・`fill none`・`stroke currentColor`・`stroke-width 2`・`stroke-linecap/linejoin round`・`aria-hidden true`・`width/height` = size)は一致。**差は class のみ**: 旧 `lucide lucide-x` / 新 `lucide lucide-x-icon lucide-x`(1.0.0 の `createLucideIcon` が `lucide-<name>-icon` を足す)。`index.css` に `lucide` のセレクタは無く、見た目は変わらない → 不可避差分として記録(research.md 4-3 節) |
| E | `Toast` の Context | `createContext` / `useContext` → **型付き `InjectionKey` の `provide` / `inject`**。**inject 失敗は例外を投げる**(旧の既定値は何もしない関数 — 旧 `Toast.tsx:23`) | 規則 `porting-rules.md:45`(既決の逸脱)。黙殺禁止(要件書 `:165,913`)とも整合 |
| F | `Toast` のファイル構成 | `Toast.vue` の**通常の `<script lang="ts">` ブロックで** `ToastTone` 型・`useToast()`・`InjectionKey` を名前付き export し、`<script setup>` を Provider 本体(既定 export)にする | ディレクトリ・ファイルの 1:1 対応(`porting-rules.md` 2 節)を保つため。旧 `ToastProvider` は `Toast.vue` の既定 export に当たる |
| G | `Button` の `...rest` | `$attrs` を root の `<button>` へ(`inheritAttrs` 既定)。`className` は prop を新設せず fallthrough。**`type="button"` は呼び出し側が上書きできる**(旧 `:46-48` の順序を保つ) | 規則 `porting-rules.md:44` と 4 点判定 ③ |
| H | 1 語のコンポーネント名 | `eslint.config.js` で `vue/multi-word-component-names` の `ignores` に `Button`・`Sheet`・`Toast` を足す | 現行 eslint は `flat/recommended` を全 error に引き上げる(`eslint.config.js:11-19`)。2026-10-10 に `Button.vue` で実測し error を確認(research.md 4-7 節)。ファイル名を変えると 1:1 対応が崩れる |
| I | `queryClient` | **`@tanstack/vue-query` の `QueryClient`** を、旧と同じ既定値 3 つ(`retry: 1`・`refetchOnWindowFocus: false`・`staleTime: 30_000` — 旧 `queryClient.ts:4-12`)で生成して export する | ライブラリ対応 `porting-rules.md:82` |
| J | `teamSearch` の試験 | `node:test` の `.test.mjs` → **Vitest の `.spec.ts`**。4 ケースの入力と期待値は変えない。`assert.deepEqual`(strict)→ `toStrictEqual`、`equal` → `toBe`、undefined → `toBeUndefined` | NFR-019(要件書 `:969`)がフロントのランナーを Vitest に固定。旧の `.test.mjs` を残すと Vitest の既定 include に拾われ失敗する見込み(research.md 4-6 節)。移植規則に `.test.mjs` の定めが無い(`frontend-impl-units/design.md:13`)ため逸脱として記録する |
| K | `.ts` の作り方 | `queryClient.ts`・`teamSearch.ts` は**逐語で置かず書き起こす**。`.prettierignore` に足さず、Prettier を全ファイルに適用する | PO 決定 2026-10-10(ADR-002 v1.1 `:36` は逐語取り込みも許すが、本単位は書き起こしを選んだ)。`porting-rules.md` 7 節の Prettier 対象外は「受入条件が逐語比較であるファイル」に限るため、本タスクの `.ts` は当たらない |
| L | `Button` の active の色 | **active のときは variant 側の競合する色クラス(背景・枠線色・文字色とそれぞれの `dark:` 版)を外し、`activeCls` を効かせる**。形・寸法・`hover:`・`active:`(押下)・`disabled:` のクラスは残す | 実装中の計画変更(PO 決定 2026-10-10)。ステップ 4 のビルド CSS の規則順序で、`sky` 系の active クラスは danger の背景以外すべて variant 側に負け、active の見た目が効かないと判明(tailwindcss 4.3.3 — ステップ 4 のコミット本文)。旧と同じクラス構成の欠陥(旧 4.3.2 でも同じと推論)を、旧の意図(選択中を示す)どおりに直す。I-28 の「改善既決」ではない旧挙動からの逸脱のため、PO 決定として記録する |
| M | `Sheet` の重ね表示 | **開いている Sheet をモジュール全体の積み重ね(開いた順)で管理し、最前面の 1 枚だけが Escape と Tab を処理する。最前面でない Sheet を閉じるときはフォーカスを動かさず、その Sheet の「戻り先」(開く前にフォーカスがあった要素)をすぐ上の Sheet へ引き継ぐ**(PR #113 敵対レビュー 2 回目 P0 で拡張 — PO 決定 2026-10-10) | 実装中の計画変更(PO 決定 2026-10-10 — PR #113 敵対レビュー 1 回目 P0)。各 Sheet が `window` の capture 段階に keydown を登録し、`stopPropagation()` は同じ対象(window)の後続リスナーを止めないため、2 枚重ねて Escape を押すと両方が `close` を通知していた。旧 `Sheet.tsx:100-118` も同じ構造の欠陥。I-28 の「改善既決」ではない旧挙動からの逸脱のため、PO 決定として記録する |

### 照合の手順(H-59 — 照合した項目を先に列挙してから合否を述べる)

各 `.vue` ステップの合格判定は、次の 4 点(`porting-rules.md:183-191`)を**項目ごとに結果つきで列挙**してから合否を述べる。

1. SVG の値 — `Sheet` の閉じるアイコンのみ(決定 D)。`Button`・`Toast` は SVG なし → 「非該当」と書く
2. Tailwind クラス文字列 — 旧の静的クラスを**集合として過不足なく一致**。条件付きクラス(`cx` の分岐)は分岐ごとに一致
3. props / emits — 名前・型・必須性・既定値が 1:1。callback prop(`onClose`)は `defineEmits` の `close`(規則 `porting-rules.md` 3 節)
4. 座標変換 — 3 部品とも座標計算なし → 「非該当」と書く

**旧** `Button` では active かつ result/secondary/chip のとき `bg-white` と `bg-sky-100` が同時に付いていた(旧 `:22-24,30,34`)。ステップ 4 でビルド CSS の規則順序を確かめた結果、sky 系の active クラスは danger の背景以外すべて負けていたため(ステップ 4 のコミット本文)、**決定 L で active 時は競合する色クラスを外す形に改めた**。現在の合格条件は「active 時に外す色クラスが付かず、activeCls が付く」こと(ステップ 4 是正のコミット)。画面全体の見た目の照合は利用画面の移植時に行う(計画レビュー 2 回目 P1・PR #113 敵対レビュー 1 回目 P2)。

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **依存 2 件を追加する** — `frontend/package.json` の `dependencies` に `@tanstack/vue-query` **5.101.4**・`lucide-vue-next` **1.0.0** を**完全一致の版で**(`^`・`~` なし)足し、`pnpm-lock.yaml` を更新する。**`frontend/pnpm-workspace.yaml` を新設し `allowBuilds: { vue-demi: false }` を置く**(実装中の計画変更 — PO 決定 2026-10-10: `@tanstack/vue-query` の依存 `vue-demi@0.14.10` が postinstall を持ち、pnpm 11 は許否未設定のビルドスクリプトを `ERR_PNPM_IGNORED_BUILDS` で error にする。CI も `pnpm install --frozen-lockfile`〔`.github/workflows/ci.yml:277`〕で同じく落ちる。postinstall は Vue 2/3 でファイルを差し替えるだけで、同梱の `lib/index.mjs` は既定で Vue 3 用〔`isVue3 = true`〕のため実行しない)。ソースは触らない | `package.json` の差分が 2 行の追加だけで版指定が完全一致 / `pnpm-workspace.yaml` が `allowBuilds` の 1 件(`vue-demi: false`)だけ / `pnpm install --frozen-lockfile` 成功 / `pnpm exec vue-tsc --noEmit`・`pnpm exec eslint .`・`pnpm test`・`pnpm build` が green(既存の閉域 spec を含む) |
| 2 | **`teamSearch` を作る** — `lib/teamSearch.ts` を旧 `teamSearch.ts:1-28` の仕様(型 `TeamSearchModel`・NFKC → `toLocaleLowerCase('ja')` → 空白全削除の正規化・正規化前の文字列での重複除去と出現順の維持・空 query は全件・部分一致・完全一致の優先・候補 1 件なら `selectionTarget`)で書き起こし(決定 K)、`lib/teamSearch.spec.ts` に旧 4 ケースを Vitest で書き換えて足す(決定 J)。端の挙動 2 件(空白だけの query は全件・query が空でもチームが 1 件なら `selectionTarget` になる)も試験で固定する | export 名・型・関数の引数が旧と同じ / spec の旧 4 ケースの入力・期待値が旧 `teamSearch.test.mjs:6-35` と一致(対応表をコミット本文に書く)/ 端の 2 件が green / `pnpm test`・`prettier --check .` green |
| 3 | **`queryClient` を作る** — `lib/queryClient.ts`(決定 I・K)と、既定値 3 つを検査する `queryClient.spec.ts` | spec が `getDefaultOptions().queries` の 3 値を検査して green / `vue-tsc` green |
| 4 | **`Button` を移植する** — `components/ui/Button.vue` と `Button.spec.ts`。`eslint.config.js` に決定 H の `ignores` を足す(本ステップで 3 名すべて) | 4 点判定を項目ごとに列挙(① 非該当 ② variant 6 種・active・keyHint の各クラス集合が旧と一致 ③ props `variant`(既定 `'secondary'`)・`keyHint?`・`active?`(既定 false)が 1:1 ④ 非該当)/ spec: 各 variant のクラス・active・keyHint の `<span>` の有無・attrs と class の fallthrough・`type` の上書き / **`pnpm build` の出力 CSS で `.bg-white` と `.bg-sky-100` の規則の順序を確かめ、active 時にどちらが勝つかをコミット本文に記録する** / `eslint .` green |
| 5 | **`Toast` を移植する** — `components/ui/Toast.vue`(決定 E・F)と `Toast.spec.ts` | 4 点判定を列挙(① 非該当 ② コンテナ・各トースト・色 4 種のクラス集合が旧と一致 ③ export(`ToastTone`・`useToast`・既定 export の Provider)と `push(message, tone='info', durationMs?)` の引数が 1:1 ④ 非該当)/ spec(fake timers): 最大 5 件(6 件目で最古が消える)・info 4000ms / error 6000ms / `durationMs` 優先・`role="status"`・**Provider の外で `useToast()` を呼ぶと例外**・**`<img src=x onerror=…>` を含む文言が要素にならずテキストで出る**(NFR-023) |
| 6 | **`Sheet` を移植する** — `components/ui/Sheet.vue`(決定 A〜D・M)と `Sheet.spec.ts` | 4 点判定を列挙(① 閉じるアイコンの描画結果が決定 D の照合結果(class の差 1 件のみ)と一致することを spec で検査 ② 外枠・背景・パネル(right / bottom / wide)・見出し・閉じるボタン・本文のクラス集合が旧と一致 ③ props `open`・`title`・`side`(既定 `'right'`)・`wide`(既定 false)と emit `close` が 1:1 ④ 非該当)/ spec: 閉じているとき何も描かない・body へ Teleport・`role="dialog" aria-modal aria-label`・開くと閉じるボタンへフォーカス・Escape で `close`・Tab / Shift+Tab の循環・閉じたら元の要素へフォーカスが戻る・背景ロック(`#app` が `inert`+`aria-hidden`、body の overflow が `hidden`、閉じると復元)・**2 枚重ねて 1 枚閉じてもロックが残り、2 枚目を閉じると解ける**(参照カウンタ)・背景クリックで `close`・**`open=true` のままマウントしても、開いた直後と同じ状態(閉じるボタンへフォーカス・背景ロック・Escape と Tab が効く)になる**・**開いたままアンマウントしてもロックが解ける**・**title に HTML を入れてもテキストで出る**(NFR-023)・**重ね表示(決定 M): 2 枚で Escape は上だけ閉じる・下にフォーカスがあっても Tab は最前面の中へ収まる・3 枚の真ん中を閉じてもフォーカスは最前面に残り、その後最前面を閉じると引き継いだ戻り先へ戻る** |
| 7 | **移植規則と単位定義へ追記し、下流へ申し送る**(Claude) — ① `porting-rules.md` に「U-F1 で追加した不可避差分」節を足す。**載せるのは決定 A・B・C・D・E・F・H・J・K・L・M の 11 件**(L・M は旧からの意図的な逸脱として、K は「U-F1 から `.ts` を逐語で置かず書き起こす — PO 2026-10-10」の方針として載せる。G・I は既存規則どおりのため載せない)。D は照合結果(パス・svg 属性は一致、class に `lucide-x-icon` が 1 つ増える)を書く ② `frontend-impl-units/design.md` の U-F1 行に「`registerServiceWorker.ts` は TSK-533 へ切り出し(PO 2026-10-10)」を注記 ③ research.md「下流への申し送り」の 4 件を、宛先 6 単位(U-F2・U-F5・U-F7・U-F8・U-F10・U-F12)の Notion カードへコメントで届け、各コメントの宛先と日付を worklog に記録する | ① の節に 11 件すべてがあり 4 節の決定表と食い違わない / ② の注記がある / ③ worklog に 6 カード分の記録がある / `uv run python scripts/check_plan_docs_sync.py` が 3 節の宣言(正本の反映なし)と矛盾しない |

各ステップ共通: `pnpm exec prettier --check .`・`pnpm exec eslint .`・`pnpm exec vue-tsc --noEmit`・影響する spec が green。

## 5. DoD(受け入れ基準)

Notion TSK-516 の DoD と同期(括弧内は担当ステップ)。

- [ ] 旧コードを複製せず Vue / TS で書き起こし(PO 2026-10-10)、**見た目と挙動が旧と同じ**であることを Tailwind クラスの一致・競合するクラスの勝敗の記録(`Button` の active)・試験で示した。旧と変えた箇所は 4 節の決定表に全件ある(2〜6)
- [ ] 移植規則に従った(4 分類の変換規則・ディレクトリ 1:1 対応)(2〜6)
- [ ] `.vue` の旧との同等性を 4 点で判定し、照合項目を列挙してから合否を述べた(H-59)(4〜6)
- [ ] 自分が担う面を 6.3 境界定義表の 5 領域すべてに当てた結果を計画書へ書いた(契約 4 — 4 節「意味上の判定」)
- [ ] 横断要求を破っていない(契約 5): **論理削除**(4.0-2 — 削除操作なし)/ **テナント分離**(NFR-010 — キャッシュ消去は U-F2、U-F1 は生成のみ)/ **自動エスケープと生 HTML 禁止**(NFR-023 — `v-html` 不使用・Toast と Sheet でエスケープの回帰試験)/ **一覧のページング**(NFR-005 — 一覧画面なし)(5・6)
- [ ] Vitest の試験を伴う(NFR-019)(2〜6)
- [ ] `pnpm exec vue-tsc --noEmit` / `pnpm test` / `pnpm exec eslint .` / `pnpm exec prettier --check .` / `pnpm build` が green(全ステップ)
- [ ] 依存 2 件が完全一致の版で入っている(1)
- [ ] `registerServiceWorker` の切り出し先 TSK-533 が起票され、単位定義に注記されている(起票済み・注記は 7)
- [ ] 不可避差分と意図的な逸脱(決定 A・B・C・D・E・F・H・J・K・L・M)が `porting-rules.md` に記録されている(7)
- [ ] 下流への申し送り 4 件(research.md 末尾)が宛先 6 単位の Notion カードへ届き、worklog に記録されている(7)
- [ ] コア領域のレビュー: 敵対レビュー + 人間の逐行確認(PR)

## 6. テスト計画

NFR-019 のテスト種別ごと(すべて Vitest・jsdom):

| 種別 | 追加するもの |
| --- | --- |
| 単体 | `teamSearch.spec.ts`(旧 4 ケースの書き換え)/ `queryClient.spec.ts`(既定値 3 つ)/ `Button.spec.ts`(variant・active・keyHint・attrs と class の fallthrough・`type` の上書き)/ `Toast.spec.ts`(件数上限・表示時間・tone・`role`)/ `Sheet.spec.ts`(描画条件・Teleport・aria・フォーカス・Escape・Tab の循環・背景ロックと参照カウンタ・背景クリック) |
| 故障系 | `Toast`: Provider の外で `useToast()` を呼ぶと例外(黙殺しない)/ `Sheet`: `#app` が無い場合に代替経路(body 直下の `data-sheet-layer` 以外を inert)へ入る |
| 越境(NFR-023) | `Toast` の文言・`Sheet` の title にタグを含む文字列を渡し、要素として解釈されずテキストで出ることを検査する |
| 一致性・E2E | 対象なし(ドメイン計算を持たず、画面ではない。見た目の自動比較は最初の画面移植の単位へ — 2 節「やらないこと」) |

jsdom はレイアウト計算をしないが、U-F1 は座標計算を持たないため `getBoundingClientRect()` のスタブは要らない(4 点判定 ④ 非該当)。
