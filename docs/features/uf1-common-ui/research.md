---
feature: uf1-common-ui
type: research
date: 2026-10-10
---

# 調査メモ: U-F1 共通表示(汎用部品・起動補助)の計画前調査 — TSK-516

## 問い

U-F1(`docs/features/frontend-impl-units/design.md:308`)の 7 ファイルを旧 React 実装 `dd03160` から Vue 3 へ逐語移植するにあたり、
(1) 要件上の制約、(2) 旧実装の実挙動と移植上の障害、(3) 過去の決定との整合、(4) 計画で PO に上げるべき分岐は何か。

調査: spec-checker / legacy-analyst / decision-tracer の 3 並列(2026-10-10)。エージェントの「不明」のうち 2 件(呼び出し元)は
主セッションが `dd03160` を git で直接引いて埋めた(5 節)。**[推論]** と付けたものは典拠からの判断で、確認済みの事実ではない。

略記:
- `旧:` = 旧 `Baseball_Scoring` の固定コミット `dd03160044aa5932d3b5a025870c9a5a56d979ef` の `frontend/`(`git show` で取得)
- `req:` = `docs/requirements/requirements-pitchlog-2026-07-22.md`
- `PR:` = `docs/features/frontend-skeleton/porting-rules.md`

**注意(照合基準)**: ローカルの `~/projects/Baseball_Scoring` の作業ツリーは `dd03160` より**古い版**で、`queryClient.ts`・`registerServiceWorker.ts`・`teamSearch.*`・`public/sw.js` が無く、`Sheet.tsx` も別物(79 行・ポータルなし)。**照合は必ず `git show dd03160…:<path>` で固定リビジョンから行う**(同じ注意: `docs/features/req-legacy-frontend-gaps/research.md:45`)。

## 結論(要約)

1. **移植元は 8 ファイル・536 行と小さい**(Button 58 / Sheet 159 / Toast 72 / index.css 154 / queryClient 12 / registerServiceWorker 18 / teamSearch 28 + test 35)。**`index.css` は移植済み**(`#root`→`#app` の 2 行差のみ — 4-1 節)
2. **外部依存を足さないと移植できないのは 2 件**: `queryClient` → `@tanstack/vue-query`、`Sheet` の閉じるアイコン → `lucide-vue-next`。足すと `frontend/package.json`・`pnpm-lock.yaml` が**コア領域 2 つ(`sync-protocol`・`game-state`)の paths に当たる**。**U-F1 の本体ファイルはどれもコア paths に当たらない**(2 節)
3. **`registerServiceWorker.ts` は U-F1 の中で唯一、要件と食い違う**: `navigator.storage.persist()` の拒否を黙って捨てる(旧 `registerServiceWorker.ts:6-8`)が、FR-012 は拒否時の警告を要求(`req:330`)。さらに登録先の **`public/sw.js` はどの単位にも割り当てられておらず**、PWA の PO 裁定は v2.0 から未決のまま(3 節)
4. **「依存追加は別 PR」は既決ではない**が、U-F1 の範囲(`lib/sync`・`zone/` に触れない)では成り立つ。既存資料の否定(`frontend-impl-units/research.md:192`)は「同期・ゾーンに触れる画面」についての記述で、U-F1 には当たらない(2-3 節で裁定)
5. **計画で PO に上げる分岐は 3 つ**: ① 依存 2 件の導入の承認と PR の切り方 ② `registerServiceWorker` + `sw.js` を U-F1 に入れるか切り出すか ③ `.test.mjs` → `.spec.ts` の書き換えの扱い(6 節)

## 詳細と典拠

### 1. 要件上の制約(spec-checker)

| 要求 | U-F1 での押さえどころ | 典拠 |
| --- | --- | --- |
| NFR-023 自動エスケープ・生 HTML 禁止・CSP | 旧 Toast の本文・Sheet の title はテキスト補間(旧 `Toast.tsx:66`、`Sheet.tsx:140,143`)。Vue では mustache で描き、`v-html` を使わない。Toast には利用者入力(選手名など)が入り得るので**エスケープの回帰テストを付ける**。CSP(`frontend/index.html:5-8`、検査 `frontend/vite.config.ts:43-56,458-468`)を緩めない | `req:1011` |
| 生 HTML の旧実装 | `dangerouslySetInnerHTML`・`innerHTML`・`outerHTML`・`insertAdjacentHTML`・`document.write` は U-F1 の旧 13 ファイルと現行 frontend 全体で **0 件** | legacy-analyst 7 節 |
| NFR-019 テストランナー | フロントは Vitest に固定。旧 `teamSearch.test.mjs` は `node:test`(旧 `:1-2`)。旧の test スクリプトには Button・Sheet・Toast・queryClient・registerServiceWorker の試験が**無い**(旧 `package.json:9`)→ 新しく書き起こす | `req:969` |
| NFR-005 ページング | U-F1 は集計・一覧画面を持たない。teamSearch はクライアント側の候補絞り込み(旧 `teamSearch.ts:14-18`)で、「一覧系画面」に当たるかは**不明**(要件に記載なし) | `req:857` |
| NFR-010 テナント分離 | 認証変化でのクエリキャッシュ消去は **authStore(U-F2)が担う**(旧 `stores/authStore.ts:33,37` の `queryClient.clear()` — 5 節)。U-F1 の `queryClient.ts` は生成と既定値だけ | `req:887`、設計書 `:400` |
| 4.0-2 論理削除 | 削除操作なし → 非該当 | `req:163` |
| NFR-015 / 4.0-2 黙殺禁止 | Toast は自動で消え(通常 4 秒・error 6 秒、旧 `Toast.tsx:45`)最大 5 件(`:44`)。**[推論]** FR-012 の未送信件数の常時表示(`req:315`)・停止位置の明示(`req:326`)・NFR-020 の前提の全列挙(`req:995`)を Toast だけで運んではならない — **利用側(U-F7・U-F8)への申し送り** | `req:165`、`req:913` |
| 技術スタック | 7.1 の承認対象は「Python / FastAPI + Vue.js + TypeScript / PostgreSQL」。**個々のランタイムライブラリの追加がこの「変更」に当たるかは条文に定義がなく不明**。ADR-002 もフレームワーク・ツールチェーンしか決めていない(`docs/adr/ADR-002-frontend-vue.md:26-28`) | `req:1059` |
| teamSearch の FR | **チーム検索を定める FR は無い**。近いのは FR-001(先攻・後攻の設定 `req:201`)・FR-039(相手チームの選択・類似名の警告 `req:425-427`)。**[推論]** 名前の文字列で重複を除く(旧 `teamSearch.ts:14`)ため、FR-039 が認める意図的な同名登録(`req:427`)が 1 件に潰れうる — **呼び出し側(U-F5・U-F10)の問題として申し送り** | — |
| リリース判定③ | 開発者以外の部員が利用ガイドのみで 1 試合を記録、機内モードの断シナリオを含む。U-F1 は記録画面の部品の供給で間接的に関わる | `req:1085`(依頼文の `:1041` は誤り — 同行は 6.2 の論理削除) |

### 2. 外部依存とコア領域

#### 2-1. ファイルごとの外部依存(legacy-analyst 2 節)

| ファイル | 外部依存 | 移植に要るもの |
| --- | --- | --- |
| `components/ui/Button.tsx` | なし(`cx` のみ — 移植済み `frontend/src/lib/format.ts:14-16`) | なし |
| `components/ui/Toast.tsx` | なし(`cx` のみ) | なし |
| `components/ui/Sheet.tsx` | `lucide-react` の `X`(旧 `:3`)、`react-dom` の `createPortal`(`:2`) | `lucide-vue-next`(または SVG 直書き)。ポータルは Vue の `<Teleport>` |
| `lib/queryClient.ts` | `@tanstack/react-query`(旧 `:1`) | `@tanstack/vue-query` |
| `lib/registerServiceWorker.ts`・`lib/teamSearch.ts` | なし | なし |

- 現行 `frontend/package.json:13-15` の dependencies は `vue` だけ
- 版は `PR:79-84` に記録済み(`@tanstack/vue-query` 5.101.4 / `lucide-vue-next` 1.0.0)。**ただしこれは承認済み計画で「版だけ先に決めた」もの**(`docs/features/frontend-skeleton/plan.md:123`)で、`PR:86-87` は「このステップでは install しない」。**導入するタスクの指定は無い**(同 plan.md:191-196)。版の確認は 2026-08-16 の `pnpm view` で、**現在も適合かは要再測**
- 版の固定規則: 無指定 install を禁じ、すべて明示 pin(frontend-skeleton/plan.md:120)
- `lucide-react` は `dd03160` で **43 ファイル**が import(主セッションが `git grep -l` で計数)。U-F1 で使うのは `X` 1 個だが、後続単位でいずれ要る

#### 2-2. コア領域 paths への当たり(主セッションが `.claude/core-areas.json` に当てて実測)

| ファイル | 当たる領域 |
| --- | --- |
| `frontend/package.json`・`pnpm-lock.yaml`・`vite.config.ts`・`tsconfig.app.json` | `sync-protocol`・`game-state` |
| `frontend/vitest.config.ts`・`tsconfig.json` | `game-state` |
| `components/ui/*.vue`・`*.spec.ts`・`lib/queryClient.ts`・`lib/teamSearch.ts`・`lib/registerServiceWorker.ts`・`public/sw.js`・`App.vue`・`main.ts`・`eslint.config.js`・`.prettierignore`・`src/index.css` | **なし** |

経緯: `game-state` へは TSK-281 が fail-closed で登録(`docs/features/core-area-paths/plan.md:126-132`)、`sync-protocol` の `package.json`・`pnpm-lock` は sync-queue-lifecycle の実装敵対レビュー P2-12(`docs/features/sync-queue-lifecycle/plan.md:88`)。`sync-protocol` の `vite.config.ts`・`tsconfig.app.json` の追加経緯は**不明**。

#### 2-3. 「依存追加を別 PR に切り出す」の位置づけ(エージェント間の食い違いを裁定)

- Notion TSK-516 の「注意」欄は「足すなら別 PR へ切り出す」と書く
- decision-tracer は「決定でも推奨でもなく、資料はむしろ否定している」と報告(`docs/features/frontend-impl-units/research.md:192`、`docs/worklog/2026-10-09-frontend-impl-units.md:85`)
- **裁定(原典確認)**: 否定は「**同期キュー・undo・ストライクゾーン・生成ドメイン計算に触れる画面**は、依存を別 PR に切るだけでは非コアにならない」という趣旨で、境界を「`src/lib/sync` と `components/zone` に触れる面 / 触れない面」で切れと続く(`research.md:192`)。**U-F1 はどちらにも触れない**ので、依存を別 PR に切れば本体は非コアで回せる。**ただし既決事項ではなく、PR の切り方は「各単位の計画書が決める」**(worklog `:26-29`、frontend-impl-units/plan.md:58)
- 前例: sync-queue-lifecycle は `fake-indexeddb` を自分の PR 内で追加した(`docs/worklog/2026-09-05-sync-queue-lifecycle.md:97`)。ただし同 PR は元々コア領域
- 設計書 6.3 規則④: 過剰包含は PR 単位の例外で外さない(`docs/development/dev-harness-design-2026-08-07.md:404`)→ 依存追加の PR は**敵対レビュー + 人間の逐行確認**の対象になる

### 3. Service Worker(`registerServiceWorker.ts` と `public/sw.js`)

#### 3-1. 旧実装の挙動(legacy-analyst 3 節)

- 登録条件: `import.meta.env.PROD` かつ `'serviceWorker' in navigator` のときだけ(旧 `registerServiceWorker.ts:2`)。**開発時は登録しない**
- 先に `navigator.storage.persist()` を呼び、**拒否を `.catch(() => false)` で捨て、結果も使わない**(`:6-8`)
- `register('/sw.js', { scope: '/' })`、失敗は `console.error` のみ(`:10-14`)。load 後に 1 回(`:16-17`)。呼び出し元は `main.tsx:5,7`(U-F13)
- `sw.js`: キャッシュ名 `baseball-static-v2`(手で上げる)。install で index.html と APP_SHELL、JS 本文から `assets/...` を**正規表現で再帰的に拾って**事前キャッシュ(旧 `sw.js:19-64`、1 つでも失敗すると install 失敗 `:28`)。`skipWaiting` を呼ばない(未送信 outbox を壊さないため `:68-72`)。`/api/*` は network-only(`:90-95`)、ページ遷移はネットワーク優先 → キャッシュの index.html → 503(`:99-111`)、静的資産はキャッシュ優先(`:114-126`)

#### 3-2. 要件・決定との関係

- **要件書に PWA / Service Worker / オフライン起動の記載は無い**(`docs/features/req-v2-legacy-parity/research.md:85`)。v2.0 で「踏襲対象」とされ、PO 裁定を「v2.1」へ送ったが(`req-v2-legacy-parity/design.md:437`)、実際の v2.1 は NFR-018 の改訂で(`req:25`)、**PWA を扱った版は無い**
- **`sw.js` を移植する/しない決定は無い**。棚卸しは `frontend/src/` の 130 件だけで(`frontend-impl-units/design.md:11`)、`public/sw.js` は**どの単位にも割り当てられていない**
- 2.2 は「完全オフライン記録」を Won't(`req:101`)、FR-001 はオフラインの試合作成を不可(`req:206`)。SW でアプリを起動できること自体は衝突しない。**[推論]** 移植の要件上の根拠は FR-012「入力を継続できる」(`req:315`)・NFR-007(`req:868`)— 断中のタブ再読み込みで記録画面に戻れるかだけ
- **[矛盾]** persist の拒否の黙殺は FR-012 の「永続化要求が拒否されたら記録画面で警告」(`req:330`)・NFR-020 の拒否とストレージ不可の区別(`req:996-997`)・黙殺禁止(`req:165,913`)と食い違う。I-28 により要件が優先(`docs/improvements-from-baseball-scoring.md:241-242`)。**persist は意味上 FR-012 の耐久キュー(U-F7)に接する**
- NFR-018 (b)③: 入口の全列挙に Service Worker と `public/` を含む(`req:952`、`docs/adr/ADR-003-domain-calc-method.md:173`)。収集器は `public/` 全ファイルを入口として数え(`backend/src/pitchlog/domaincheck/collect_entrypoints_fe.py:752-756`)、`serviceWorker.register` の第 1 引数を解決する(`:596-607`)。**[推論]** `registerServiceWorker` だけ移して `sw.js` を置かないと解決不能になる。入口宣言との突合が CI でどう効くかは**不明**(`docs/features/domain-calc-dsl/plan.md:450`「この段階では entrypoints[] と突合しない」)。旧 `sw.js` の正規表現による資産の再帰取得が「非リテラルな動的読み込み」に当たるかは、要件にも ADR にも判定が無く**不明**
- CSP は `worker-src 'self'`・`manifest-src 'self'` を既に含み(`frontend/index.html:7`)、APP_SHELL の 2 資産(`public/manifest.webmanifest`・`public/icons/baseball-app.svg`)は移植済み

### 4. 各ファイルの移植上の注意(legacy-analyst 1・4・6 節、decision-tracer 1 節)

#### 4-1. `index.css`

現行 `frontend/src/index.css` と旧は `:9`・`:52` の `#root`→`#app` 以外同一(主セッションが `diff` で確認)。Prettier 対象外(`frontend/.prettierignore:5-6`)。**U-F1 での作業は無い**。ただし他単位のスタイルが同居している: 印刷用 `.scorecard-*`(U-F12、`:59-115`)、`.analysis-page`(U-F10、`:117-153`)、`.missing-highlight`(`:29-32` — 利用側は `FieldDiagram`・`PitchTypeChips`・`ResultPad`・`StanceGrid`・`StrikeZone`・`GameScreen`、主セッションが `git grep` で確認)。

#### 4-2. Button

- props: `variant`(6 種、既定 `'secondary'`)・`keyHint?`・`active?`・`className`・`children`・残りは `...rest` で `<button>` へ(旧 `Button.tsx:4-12,36-48`)。`type="button"` は `...rest` より前なので呼び出し側が上書きできる(`:46-48`)
- 移植規則: `...rest` は `$attrs` を root の native 要素へ(`PR:44`)、`className` は prop を作らず fallthrough(`PR:183-191` の 4 点判定 ③)
- **[推論]** active かつ result/secondary/chip で `bg-white` と `bg-sky-100` が同時に付く(`:22-24,30,34`)。勝ち負けは Tailwind の CSS 生成順で決まる → **見た目の突合が要る**

#### 4-3. Sheet

- `createPortal` → `<Teleport to="body">`。`role="dialog" aria-modal` / Escape で閉じる / Tab の循環 / 開く前のフォーカスを記録し閉じたら戻す / 背景ロック(参照カウンタ・body の overflow 退避・`#root` を `inert`+`aria-hidden`)(旧 `Sheet.tsx:17-157`)
- **`document.getElementById('root')`(旧 `:38`)は `'app'` への置き換えが不可避**。逐語のまま移すと常に代替経路(body 直下の全要素を inert — `:39-43`)に入る。**`PR:93-94` は index.css の `#root`→`#app` しか規定していない** → 計画書で不可避差分として明記する
- **[推論]** React の `useEffect` は DOM 反映後に走る(`:98` で閉じるボタンへフォーカス)。Vue の `watch` は既定で DOM 反映前なので、`flush: 'post'` か `nextTick` が要る
- 閉じるボタン: `aria-label="閉じる"`、lucide の `<X size={22} />`(`:144-152`)
- **lucide の `X` の照合(主セッション・2026-10-10)**: `dd03160` の `package-lock.json` の解決版は lucide-react **0.525.0**(react-query 5.101.2・tailwindcss 4.3.2)。lucide-react@0.525.0 と lucide-vue-next@1.0.0 を `npm pack` で取得して比較:
  - パス: 両方とも `M18 6 6 18`・`m6 6 12 12`(`dist/esm/icons/x.js`)
  - svg 属性: `defaultAttributes.js` の値は同一(react は camelCase で描画時に kebab 化)。`aria-hidden="true"` は子もアクセシビリティ属性も無いとき両方とも付く(`Icon.js`)
  - **class だけ違う**: react は `createLucideIcon.js:17-20` で `lucide-x` を足し `mergeClasses` が重複を除くので `lucide lucide-x`。vue 1.0.0 は `Icon.js` で `lucide`・`lucide-x-icon`・`lucide-x` → `lucide lucide-x-icon lucide-x`
  - `frontend/src/index.css` に `lucide` のセレクタは無い → 見た目に影響しない

#### 4-4. Toast

- export: `ToastTone`・`useToast()`・`ToastProvider`。`push(message, tone='info', durationMs?)`、最大 5 件、error 6000ms / 他 4000ms、アンマウント時にタイマーを解除しない(旧 `Toast.tsx:11-48`)
- **旧の既定 Context は何もしない関数**(`:23`)だが、**移植規則は「inject 失敗は明示的に検出する」と既に決めている**(`PR:45`)→ 規則に従う(旧挙動からの既決の逸脱)
- Provider の置き場は「App の同等位置」(`PR:45,73`)。`App.vue`・`main.ts` は **U-F13** の範囲(`frontend-impl-units/design.md:320`)→ 計画書で境界を決める

#### 4-5. queryClient

- `new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 } } })`(旧 `queryClient.ts:4-12`)。**[推論]** FR-024 のバックグラウンド再試行(`req:498`)・鮮度表示(`req:437,474`)は既定値では閉じず、個別クエリ側の手当て
- 呼び出し元(`dd03160`、主セッションが `git grep` で確認): `App.tsx:7,51`(U-F13)、`stores/authStore.ts:3,33,37`(U-F2 — 認証変化で `clear()`)。画面側は `useQueryClient()` で注入されたものを使う

#### 4-6. teamSearch

- NFKC → `toLocaleLowerCase('ja')` → 空白全削除で正規化、生文字列で重複除去、部分一致、完全一致優先、候補 1 件なら `selectionTarget`(旧 `teamSearch.ts:1-28`)
- テスト 4 件(旧 `teamSearch.test.mjs:6-35`)は `node:test` + `node:assert/strict`。**Vitest の既定 include は `.test.mjs` も拾い、中身が node:test なので失敗する見込み [推論]** → `.spec.ts` へ書き換えが要る。ただし `frontend-impl-units/design.md:13` は「旧 `.test.mjs` を勝手に `.spec.ts` とみなさない」と書き、**移植規則に `.test.mjs` の扱いは無い**
- 呼び出し元(`dd03160`、主セッションが確認): `screens/AnalysisScreen.tsx:13,161`(U-F10)、`screens/TeamScreen.tsx:33,538`(U-F5)

#### 4-7. ESLint の 1 語コンポーネント名

**[推論・未実行]** 現行 eslint は `flat/recommended` の全規則を error に引き上げる(`frontend/eslint.config.js:11-19`)。`vue/multi-word-component-names` が含まれ、`Button.vue`・`Sheet.vue`・`Toast.vue` は当たる見込み。ディレクトリ 1:1 対応(移植規則)とぶつかる。`eslint.config.js` はコア paths に当たらない(2-2 節)。**実装前に実測する**。

### 5. 過去の決定との整合(decision-tracer)

- **「完全に同じもの = 機械的な逐語移植」**: frontend-skeleton/plan.md:24-31(承認 2026-08-16)。**正本(要件書・ADR)には収載されていない**(`frontend-impl-units/research.md:199`)。I-28 が射程を限定: 要件書・改善台帳が改善を既決にした箇所は対象外、判断が割れたら計画書ゲートで PO へ(`docs/improvements-from-baseball-scoring.md:237-243`)
- **ADR-002 の「旧 React UI コードは参照資料としてのみ扱い、コード再利用はしない」(ADR-002:26-36)と逐語移植の並存は未裁定**。送り先は未起票(`docs/worklog/2026-10-09-frontend-impl-units.md:104-106,154`)。U-F1 で解くものではないが、計画書は I-28 と承認済み計画を典拠にする
- **`.vue` の逐語性 4 点判定**(`PR:183-191`): ① SVG の値 ② Tailwind の静的クラスを集合として過不足なく一致 ③ props/emits が 1:1(`className` は fallthrough)④ 座標変換をテストで検査。`.ts`・CSS は diff で比較し Prettier 対象外、対象外にする前に旧コミット・許容変換・比較コマンドを記録(`PR:96-97,172-181`)
- **StrikeZone の前例**: 自動検査 5 種が通ったのに横線の誤りを人間の目視で見つけた(`docs/worklog/2026-08-16-frontend-skeleton.md:199-228`)。**H-59**: 照合した項目を列挙してから合否を述べる(`docs/development/harness-evaluation.md:1256-1264` — 状態欄なし・未解決とみられる)
- **契約 1〜5**(`docs/features/product-impl-unit-split/plan.md:175-183`、frontend 版 `frontend-impl-units/plan.md:87-97`): U-F1 は主所有を持たず分担のみ。分担行は「FR-002 / U-X1 / U-F1 / 1 球入力に使う選択ボタンと操作通知の共通部品面」(`design.md:429`)。5 領域判定は全非該当(`design.md:329,356`)。契約 4 の 5 領域判定と契約 5 の横断要求を計画書・DoD に書く義務
- **Playwright の見た目自動比較**: 「最初の画面移植と同時または直前」に導入と申し送り(frontend-skeleton/plan.md:59,195)。U-F1 は画面ではない → 時期に当たるかは判断が要る

### 6. 他ブランチとの衝突面

- `domain-calc-dsl`: develop との frontend 差分は **0**(主セッションが `git diff --stat origin/develop...HEAD -- frontend/` で確認)。衝突なし
- `us1-sync-apply-core`: `frontend/src/testing/`・`lib/sync/` を触る(同 plan.md:58,124,127)。U-F1 の対象とは重ならない
- `components/ui`・`queryClient`・`main.ts`・`App.vue` を触る計画は他に無い(decision-tracer の grep)
- `req-legacy-frontend-gaps`(承認待ち): FR-002 を改訂する(A-5〜A-7)が、25 件の穴に汎用部品・取得キャッシュ・SW を名指しするものは 0 件(同 research.md:61-85)。**[推論]** U-F1 の受入条件を直接は変えない

## 未解決・申し送り

### 計画書ゲートで PO に上げる分岐(/plan の入力)

1. **依存 2 件(`@tanstack/vue-query`・`lucide-vue-next`)の導入の承認と PR の切り方**
   - 7.1 `req:1059` の「技術スタックの変更」に当たるかは不明。版の記録(`PR:79-84`)は承認ではない → **計画書の承認で明示的に承認対象にする**
   - 切り方の候補: (a) 依存追加だけの小さなコア PR を先に出し、U-F1 本体は非コア PR(Notion カードの注意書きの形)/ (b) U-F1 の 1 PR に含め、全体をコア扱い / (c) queryClient を U-F1 から外して U-F13(vue-query の plugin 導入と同時)へ寄せ、Sheet の `X` は lucide-vue-next だけ足す
2. **`registerServiceWorker.ts` と `public/sw.js` の扱い**
   - persist の黙殺は FR-012 `req:330` と矛盾し、I-28 で要件が優先 → 逐語移植できない
   - `sw.js` は未割り当て、PWA の PO 裁定は v2.0 から未決
   - 候補: (a) U-F1 から外し、`sw.js` と合わせた別単位(PWA の裁定を含む)へ切り出す / (b) U-F1 に `sw.js` まで含め、persist は FR-012 に沿って警告を出す形に直す(U-F7 との境界が要る)
3. **`teamSearch.test.mjs` → `teamSearch.spec.ts` の書き換え**(NFR-019 が強制。移植規則に定めが無い — 逸脱として計画書に記録)

### 計画書で決めること(PO 裁定までは要らない見込み)

- Sheet の `getElementById('root')` → `'app'` を不可避差分として明記(`PR:93-94` の拡張)
- Toast の inject 失敗の明示検出(`PR:45` に従う)と、Provider を `App.vue` に置く作業を U-F1 と U-F13 のどちらが持つか
- 1 語コンポーネント名の lint(4-7 節)の実測と対処
- 照合項目の列挙(H-59)と、4 点判定 + `.ts` の diff 比較の手順
- 新規に書き起こす試験(Button・Sheet・Toast・queryClient)の範囲 — NFR-023 のエスケープ回帰を含む

### 下流への申し送り

- **U-F7・U-F8**: Toast は自動で消え最大 5 件。FR-012 の常時表示・停止位置、NFR-020 の前提列挙を Toast だけで運ばない
- **U-F5・U-F10**: teamSearch は名前で重複を除く。FR-039 の意図的な同名登録(`req:427`)と衝突しうる
- **U-F2**: 認証変化での `queryClient.clear()`(旧 `authStore.ts:33,37`)はテナント分離(設計書 `:400` の「キャッシュ無効化」)の面
- **U-F12・U-F10**: `index.css` に印刷用スタイルが同居している
