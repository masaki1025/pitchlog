# React → Vue 移植規則

## 1. 適用範囲と典拠

この規則は、旧 `masaki1025/Baseball_Scoring-archive` のコミット
`dd03160044aa5932d3b5a025870c9a5a56d979ef` を Vue へ移植するときに適用する。
以下の `旧:` はこの固定コミット内の `ファイル:行` を指す。典拠を確認できない
パターンは、この文書に規則として追加しない。

## 2. ディレクトリ対応

旧 `frontend/src/` の実ツリーと同じ、次の 17 ディレクトリを受け皿として置く。

```text
api/
assets/
components/
components/analysis/
components/analysis/player/
components/data-transfer/
components/diamond/
components/field/
components/game/
components/pads/
components/scoreboard/
components/settings/
components/ui/
components/zone/
lib/
screens/
stores/
```

計画書の列挙との差異は `assets/`、`components/data-transfer/`、
`components/settings/` の 3 件である。旧に存在しないディレクトリは追加していない。

## 3. props / emits / slots / attrs

| 旧 React のパターン | Vue での移植規則 | 旧実装の典拠 |
| --- | --- | --- |
| callback prop | `onTap` のような callback prop は `defineEmits` で型付き event にし、子から `emit('tap', x, y)` を呼ぶ。親は `@tap` で受ける。 | 旧: `frontend/src/components/zone/StrikeZone.tsx:14-25,35-60` |
| `className` prop | `className` prop は新設せず、単一 root では Vue の fallthrough attrs に任せる。明示的に転送する必要がある root では `useAttrs()` と `v-bind="$attrs"` を用い、呼び出し側は `class` を渡す。 | 旧: `frontend/src/components/zone/StrikeZone.tsx:24,35-43,107-116` |
| `children` | `children: ReactNode` は既定 slot の `<slot />` に置き換える。名前付き領域が必要になった場合だけ名前付き slot を追加する。 | 旧: `frontend/src/components/ui/Sheet.tsx:78-88,154` |
| `...rest` による DOM 属性継承 | `ButtonHTMLAttributes` と `...rest` は `$attrs` を root の native 要素へ `v-bind` する形にする。コンポーネント固有 props は `$attrs` に混ぜない。 | 旧: `frontend/src/components/ui/Button.tsx:1,6-12,36-49` |
| Context | `ToastContext` と `useToast` は、型付き `InjectionKey` を使う `provide` / `inject` に置き換える。Provider は App の同等位置に置き、inject 失敗は明示的に検出する。 | 旧: `frontend/src/components/ui/Toast.tsx:19-28,37-70` |

## 4. lifecycle / reactivity

| 旧 React のパターン | Vue での移植規則 | 旧実装の典拠 |
| --- | --- | --- |
| `useState` | 単一値は `ref`、相互に更新するオブジェクト状態は `reactive` を使う。テンプレートでは自動 unwrap を前提にし、`setup` 内では `.value` を明示する。 | 旧: `frontend/src/components/diamond/BaseDiamond.tsx:103-105`; `frontend/src/components/ui/Toast.tsx:37-48` |
| `useRef` | DOM ref は `const element = ref<ElementType | null>(null)` とし、template ref で結ぶ。null 判定を残し、React の `.current` 参照を Vue の `.value` に機械的に置換しない。 | 旧: `frontend/src/components/zone/StrikeZone.tsx:44,49-52,107-110`; `frontend/src/components/ui/Sheet.tsx:89-105,131` |
| `useCallback` | `useCallback` は setup 内の通常の関数・メソッドへ置き換える。依存配列をコピーせず、reactive 値を閉じ込めた不要な memo 化を作らない。 | 旧: `frontend/src/components/zone/StrikeZone.tsx:46-78`; `frontend/src/components/ui/Toast.tsx:41-51` |
| `useEffect` と cleanup | DOM listener・フォーカス・背景 lock のような副作用は `onMounted` / `onUnmounted`、または props 依存なら `watch` / `watchEffect` の cleanup で対にする。listener 除去、背景 unlock、元の focus 復帰を省略しない。 | 旧: `frontend/src/components/ui/Sheet.tsx:92-124` |
| `useMemo` | 入力から導く一覧・検索モデルは `computed` にする。副作用を入れず、依存配列ではなく reactive 参照を source of truth にする。 | 旧: `frontend/src/screens/AnalysisScreen.tsx:151-165` |
| `useId` | SVG marker ID などの一意 ID は **Vue 3.5.41 の `useId()`** を採用する。旧実装と同様に component instance ごとに一意な ID を作り、必要な文字列正規化だけを移す。 | 旧: `frontend/src/components/diamond/BaseDiamond.tsx:103-106` |

## 5. JSX → template 属性

| 旧 JSX のパターン | Vue template での移植規則 | 旧実装の典拠 |
| --- | --- | --- |
| form | `onSubmit` は `@submit.prevent` とし、`preventDefault()` の意味を template 側の modifier で保つ。 | 旧: `frontend/src/screens/LoginScreen.tsx:97-100` |
| event | `onPointerDown`、`onKeyDown`、`onClick` はそれぞれ `@pointerdown`、`@keydown`、`@click` にする。必要な `preventDefault`、`stopPropagation`、keyboard 修飾の意味を handler または event modifier で保持する。 | 旧: `frontend/src/components/zone/StrikeZone.tsx:46-78,107-120`; `frontend/src/components/diamond/BaseDiamond.tsx:165-171` |
| `style={{...}}` | JSX style object は `:style="{ left: leftPct + '%', top: topPct + '%' }"` のような Vue binding にする。計算式・単位・値は変えない。 | 旧: `frontend/src/components/diamond/BaseDiamond.tsx:161-172` |
| SVG 属性 | React の SVG 属性は native SVG 属性へ移す。`strokeWidth`、`strokeLinecap`、`markerEnd`、`refX` などは `stroke-width`、`stroke-linecap`、`marker-end`、`ref-x` のケバブケースを使う。SVG 仕様上 case-sensitive な `viewBox` はそのまま保持する。 | 旧: `frontend/src/components/diamond/BaseDiamond.tsx:141-150,215-231` |

## 6. router / query / store

| 対象 | Vue での移植規則 | 旧実装の典拠 |
| --- | --- | --- |
| 認証リダイレクト | `RequireAuth` と `RequireTeamAdmin` は route meta（`requiresAuth` / `requiresTeamAdmin`）と global navigation guard に集約する。token がなければ `/login`、admin 以外なら `/` へ redirect する。 **U-F2 で改めた: 役割を持たないので `requiresTeamAdmin` は作らない。判定は token の有無でなく `isAuthenticated` と `hasHydrated`(10 節 決定 A・F)。** | 旧: `frontend/src/App.tsx:25-35` |
| 全 route | vue-router 4 に `/login`、`/help`、`/`、`/analysis`、`/analysis/pitchers/:playerId`、`/analysis/batters/:playerId`、`/team`、`/comparison-workspaces`、`/scorecards`、`/imports`、`/lineup`、`/games`、`/games/:gameId`、`/games/:gameId/lineup`、`/games/:gameId/plays`、catch-all を同じ path・認可条件で登録する。 | 旧: `frontend/src/App.tsx:55-164` |
| Provider の置き場 | `QueryClientProvider` は `@tanstack/vue-query` の plugin、`BrowserRouter` は vue-router、`ToastProvider` は `provide` に対応させる。router・Pinia・Vue Query は bootstrap 時に app へ install し、Toast は App root に置く。 | 旧: `frontend/src/App.tsx:1-7,49-54` |
| 永続化と hydration | auth state は Pinia へ移し、保存キーを **`bb.auth`** のまま維持する。旧 auth store は `persist` のみで明示的な hydration hook を置いていないため、Vue 側では hydration 完了状態を明示し、route guard と API 開始前に復元を待つ。旧 sync store の `onRehydrateStorage` / `hasHydrated` はこの待機を実装する際の既存パターンである。 **U-F2 で改めた: トークンは保存しない(HttpOnly Cookie)。`bb.auth` には秘密でない 4 キーだけを書き、hydration は生成時に同期で完了する(10 節 決定 A・D・F)。** | 旧: `frontend/src/stores/authStore.ts:23-49`; `frontend/src/stores/syncStore.ts:245-251` |
| `getState()` の命令的参照 | component 外の API client は Zustand の `useAuthStore.getState()` を使わない。export 済み Pinia instance を渡して `useAuthStore(pinia)` を関数内で取得するか、auth header / 401 logout を注入可能な HTTP client へ寄せる。 **U-F2 で前者を採った: `useAuthStore(pinia)`。auth header は付けない(Cookie)。401 では `expireSession()` を呼ぶ(10 節 決定 B・H)。** | 旧: `frontend/src/api/client.ts:46-66` |

### ライブラリ対応と将来導入版

| 旧ライブラリ | Vue 側 | 導入版 | 旧実装の典拠 |
| --- | --- | --- | --- |
| Zustand | Pinia | `4.0.3` | 旧: `frontend/package.json:13-19`; `frontend/src/stores/authStore.ts:1-2` |
| `@tanstack/react-query` | `@tanstack/vue-query` | `5.101.4` | 旧: `frontend/package.json:13-19`; `frontend/src/App.tsx:1,51` |
| react-router 7 | vue-router 4 | `4.6.4` | 旧: `frontend/package.json:13-19`; `frontend/src/App.tsx:2,53-55` |
| lucide-react | lucide-vue-next | `1.0.0` | 旧: `frontend/package.json:13-19`; `frontend/src/components/ui/Sheet.tsx:1-4,144-152` |

`Pinia 4.0.3` は `pnpm view pinia version` で確認した未導入版である。ほかの 3 件も
ステップ 2 で確認済みの未導入版であり、このステップでは install しない。

## 7. 逐語移植と静的資産の既決事項

### Prettier の扱い

現行の `frontend/.prettierignore` では `src/index.css` を対象外にしている。これは旧 CSS を
`#root` → `#app` 以外は逐語で移し、旧実装との差分を意味あるものとして保つためである。

今後も、受入条件が逐語比較であるファイルは同様に Prettier の対象外にする。ただし対象外に
する前に、旧コミット・許容する変換・比較コマンドをこの文書または該当実装のテストへ記録する。
React → Vue の構文変換を含む `.vue` ファイルは逐語ファイルではないため、Prettier を適用した
まま SVG 値・Tailwind class 文字列・props 契約を比較する。

### manifest と icon

旧 `index.html` は `manifest.webmanifest` と `icons/baseball-app.svg` を link しており、manifest
自身も同 icon を参照する。現行には参照先がないため link は未移植のままとする。

- 旧の link: `frontend/index.html:10-11`
- 旧 manifest の icon 参照: `frontend/public/manifest.webmanifest:12-24`
- 移植時期: **ステップ 5 の開始時**に `public/manifest.webmanifest` と
  `public/icons/baseball-app.svg` を資産ごと逐語移植し、その後にのみ `index.html` の 2 link を復元する。

このステップでは link も資産も追加しない。

## 8. ステップ 5 の実測でわかったこと

### 逐語移植の依存は計画の列挙より広い

計画書はステップ 5 の前提を「`cx` が先に移植されている」とだけ書いていたが、
`StrikeZone.tsx` の実際の依存は次のとおりだった。**移植対象を決めるときは、必ず
旧ファイルの `import` を実物で確認すること。**

| 依存 | 旧の場所 | 逐語性 |
| --- | --- | --- |
| `cx` | `frontend/src/lib/format.ts` | 完全一致 |
| `COURSE_STRIKE_ZONE`・`DISPLAY_COORD_SIZE` | `frontend/src/lib/displayGeometry.ts` | **import パス 1 行のみ変更** |
| `moveSpatialPoint` | `frontend/src/lib/spatialInput.ts` | 完全一致 |
| `courseInputViewLabel` ほか | `frontend/src/lib/courseInputView.ts` | 完全一致 |
| 座標定義 JSON | **`shared/display_geometry_263_v1.json`**（リポジトリ直下） | バイト等価 |
| 打者シルエット 2 枚 | `frontend/src/assets/*.png` | バイト等価 |

### `display_geometry_263_v1.json` は `contracts/` へ移した（NFR-018 — Phase 4-3 で完了）

旧では**リポジトリ直下の `shared/` にあり、frontend と backend が共有する意図の唯一のファイル**
だった。Phase 4-1 の時点では `contracts/` がまだ存在しなかったため暫定で `frontend/src/lib/` に
置いていたが、**Phase 4-3（`feature/dev-db-contracts`）で `contracts/` を新設した際に移設した**。
`frontend` からは `@contracts/*` の alias 経由で参照する。

移設の理由は、**backend が同じ座標定義を必要とした時点で複製になり、NFR-018（ドメイン計算は
単一実装 — コピー実装を作らない）に違反する**ため。backend 骨格（Phase 4-2）の着手前に解消した。

**照合した項目と結果**（先に何を照合したかを列挙し、そのうえで合否を述べる）:

1. **移設前後のバイト等価** — 移設前の Git blob と移設後のファイルを `cmp` で比較 → 一致
   （sha256 `e0c4d336e169e567325c4fd645f595ae856b4bbd7e9be3e5cde53515ff8901f6`）。
   Git も rename（内容差分 0）として認識している
2. **旧リポジトリとのバイト等価** — 保全アーカイブの `dd03160044aa5932d3b5a025870c9a5a56d979ef`
   における **`shared/display_geometry_263_v1.json`** を取得して `cmp` → 一致（同 sha256）
3. **複製の不在** — `test ! -e frontend/src/lib/display_geometry_263_v1.json` → 成功
4. **`displayGeometry.ts` の逐語性** — 変更は `import` パス 1 行のみ（下記の依存表が許した逸脱枠と同形）。
   他の行に差分なし

**判定: 4 項目すべて合格。**

**移設に伴う配線**（いずれも新規の設定であり逐語移植の対象外）: `tsconfig.app.json` の `paths` /
`vite.config.ts` の `resolve.alias`（絶対パス）と `server.fs.allow`（`frontend/` と `contracts/` の
**両方** — `allow` を明示すると Vite の workspace root 自動検出が無効になるため）/
`vitest.config.ts` の `mergeConfig` 化（alias の二重定義を避ける）。
dev サーバが `/@fs/` 経由で `contracts/` の JSON を 200 で配信することを実測して確認した。

### Prettier 対象外にしたファイル（7 節の規則の適用結果）

`src/index.css` に加えて、逐語移植した次を `.prettierignore` へ加えた。

- `src/lib/format.ts` / `src/lib/displayGeometry.ts` / `src/lib/spatialInput.ts` /
  `src/lib/courseInputView.ts`

> **Phase 4-3 の追随**: `src/lib/display_geometry_263_v1.json` の行は削除した。ファイルが
> `contracts/` へ移り `frontend/` の外に出たため、`frontend/.prettierignore` の射程外になり
> 空振りするからである。**`contracts/` は現在どの Prettier からも検査されない**
> （frontend の Prettier は `working-directory: frontend` で動き、リポジトリルートに Prettier は
> 無い）。将来ルート側に整形ツールを入れる場合は、この JSON を対象外にする手当てが要る。

**比較コマンド**（7 節が「対象外にする前に記録する」と定めているもの）:

```bash
gh api "repos/masaki1025/Baseball_Scoring-archive/contents/frontend/src/lib/<name>?ref=dd03160044aa5932d3b5a025870c9a5a56d979ef" \
  --jq '.content' | base64 -d | diff -u - frontend/src/lib/<name>
```

**旧側のパスはファイルごとに違う。上のコマンドは `frontend/src/lib/` 配下のものにしか使えない。**
座標定義 JSON は旧 **`shared/display_geometry_263_v1.json`**（URL の `contents/` 以降を差し替える）、
資産は `sha256sum` で比較する。

### `.vue` の逐語性は何を見て判定するか

`.tsx` → `.vue` は構文変換が入るため機械的な diff が取れない。**次の 4 点で判定する。**

1. **SVG の値** — `viewBox`・ゾーン矩形の座標・分割構造
2. **Tailwind クラス文字列** — 内容と並び順（静的クラスは集合として過不足なく一致させる）
3. **props / emits** — 名前・型・必須性が 1:1（`className` は prop を新設せず fallthrough）
4. **座標変換の結果** — テストで検査する。**jsdom はレイアウト計算をしないので
   `getBoundingClientRect()` は固定スタブが必須**（無いと 0 が返り検査が無意味になる）

## 9. U-F1 共通表示で追加した差分(TSK-516 — 2026-10-10)

計画書: [`../uf1-common-ui/plan.md`](../uf1-common-ui/plan.md)(4 節の決定表が正)。対象は旧 `components/ui/{Button,Sheet,Toast}.tsx`・`lib/queryClient.ts`・`lib/teamSearch.ts`。

### 作り方の方針(決定 K — PO 決定 2026-10-10)

**U-F1 は、旧コードを複製せず Vue / TypeScript で書き起こした**(PO の選択)。**これは ADR-002 の要求ではない** — ADR-002 v1.1(2026-10-10)は「コード再利用はしない」が禁じるのを旧システムを依存として抱えることに限り、本リポジトリの資産として取り込み保守責任を負うものは逐語一致でも当たらないとした(`docs/adr/ADR-002-frontend-vue.md:36`)。後続の単位は、逐語取り込みと書き起こしのどちらも選べる(計画書で決める)。
見た目と挙動が旧と同じであることは、Tailwind クラス文字列の一致と試験で確かめる。`.ts` も逐語で置かないため、7 節の Prettier 対象外には当たらない
(`queryClient.ts`・`teamSearch.ts` は `.prettierignore` に入れていない)。8 節で逐語移植した `.ts` 4 件は変えていない。

### Vue と React の差で不可避な差分

| 決定 | 対象 | 規則 | 旧の典拠 |
| --- | --- | --- | --- |
| A | `Sheet` の背景ロック | `getElementById('root')` → **`'app'`**。現行のマウント先は `#app`(`index.html`・`main.ts`)で、`'root'` のままだと常に代替経路(body 直下の全要素を inert)に入る。`index.css` の `#root` → `#app` と同じ扱い | 旧: `frontend/src/components/ui/Sheet.tsx:38` |
| B | `Sheet` のポータル | `createPortal(…, document.body)` → **`<Teleport to="body">`** | 旧: `Sheet.tsx:127,157` |
| C | `Sheet` の開閉副作用 | `useEffect(…, [open])` → **変化は `watch(() => props.open, …, { flush: 'post' })`、初期 `open=true` は `onMounted`、後始末は閉じたときと `onBeforeUnmount`**。Vue の `watch` は初期値では走らず既定で DOM 反映前に走るため。`immediate: true` は初回を同期実行し template ref が null のため使わない | 旧: `Sheet.tsx:95-124` |
| D | `Sheet` の閉じるアイコン | lucide-react 0.525.0 の `<X size={22} />` → lucide-vue-next 1.0.0 の `<X :size="22" />`。パス 2 本と svg 属性は一致し、**class だけ `lucide lucide-x` → `lucide lucide-x-icon lucide-x`**(1.0.0 が `lucide-<name>-icon` を足す)。`index.css` に `lucide` のセレクタは無く見た目は変わらない | 旧: `Sheet.tsx:3,144-152` |
| E | `Toast` の Context | 3 節の規則どおり `InjectionKey` の `provide` / `inject`。**inject 失敗は例外を投げる**(旧の既定値は何もしない関数) | 旧: `Toast.tsx:23` |
| F | `Toast` のファイル構成 | `Toast.vue` の通常の `<script lang="ts">` で `ToastTone`・`ToastApi`・`toastKey`・`useToast` を名前付き export し、`<script setup>` を Provider 本体(既定 export)にする。ファイルの 1:1 対応を保つため | 旧: `Toast.tsx:11-37` |
| H | 1 語のコンポーネント名 | `eslint.config.js` で `vue/multi-word-component-names` の `ignores` に `Button`・`Sheet`・`Toast` を入れる。現行 eslint は `flat/recommended` を全 error に引き上げており、ファイル名を変えると 1:1 対応が崩れる。**後続の単位で 1 語の部品を足すときも同じ `ignores` へ追加する** | — |
| J | 旧の `node:test` の試験 | `*.test.mjs`(`node:test` + `node:assert/strict`)は **Vitest の `*.spec.ts` へ書き換える**(NFR-019)。入力と期待値は変えない。`assert.deepEqual` → `toStrictEqual`、`equal` → `toBe`、undefined → `toBeUndefined`。旧ファイルを残すと Vitest の既定 include に拾われる | 旧: `lib/teamSearch.test.mjs:1-35` |

### 旧からの意図的な逸脱

| 決定 | 対象 | 内容 | 根拠 |
| --- | --- | --- | --- |
| L | `Button` の active | **active のときは variant 側の競合する色クラス(背景・枠線色・文字色とその `dark:` 版)を外し、`activeCls` を効かせる**。外す対象は variant ごとの表で明示する。active でないときのクラス文字列は旧と同一 | ビルド CSS(tailwindcss 4.3.3)では同じプロパティの規則が名前順に並び、active の `sky` 系クラスが danger の背景以外すべて variant 側に負けて、選択中の表示が効かなかった(旧と同じクラス構成の欠陥 — 旧の 4.3.2 でも同じと推論)。PO 決定 2026-10-10 |
| M | `Sheet` の重ね表示 | **開いている Sheet をモジュール全体の積み重ね(開いた順)で管理し、最前面の 1 枚だけが Escape と Tab を処理する(フォーカスがパネルの外なら中へ引き戻す)。最前面でない Sheet を閉じるときはフォーカスを動かさず、戻り先をすぐ上の Sheet へ引き継ぐ** | 各 Sheet が `window` の capture 段階に keydown を登録し、`stopPropagation()` は同じ対象(window)の後続リスナーを止めないため、旧では 2 枚重ねて Escape を押すと両方が閉じ、中段を閉じると最前面からフォーカスが外れていた(旧: `Sheet.tsx:95-124`)。PR #113 の敵対レビュー 1・2 回目で検出。PO 決定 2026-10-10 |

**後続の単位への注意**: Tailwind では `cx` に渡す順序でなく生成 CSS の規則順序で勝敗が決まる。**同じプロパティのクラスを条件で重ねるときは、上書きされる側を外す**(決定 L と同じ形)。


## 10. U-F2 認証状態で追加した差分(TSK-517 — 2026-10-10)

計画書: [`../uf2-auth-state/plan.md`](../uf2-auth-state/plan.md)(4 節の決定表が正)。調査: [`../uf2-auth-state/research.md`](../uf2-auth-state/research.md)。
対象は旧 `stores/authStore.ts`。旧コードは複製せず Vue / TypeScript で書き起こした(9 節の決定 K と同じ扱い)。

### 旧の形を移せない理由(要件・正本が既決にした改善 — I-28)

- **トークン**: 新方式では `HttpOnly` Cookie で運ばれ、JavaScript から読めない(H-2 — `../ua1-team-auth/design.md:18`)。正本は提示値を応答本文に出さない(`docs/design/data-model.md:1678`)。
- **`authKind`・`username`**: 個人アカウントは Won't(要件書 `:99`、PO 裁定 B-1)。
- **`role`**: チーム管理者ロールは導入しない(要件書 `:1127`)。旧のチームログインは常に `role:'admin'` だったので(旧 `api/mock.ts:2872-2879`)、役割を落としてもチームアカウントの見え方は変わらない。

### 規則から外れる決定

| 決定 | 対象 | 規則 | 6 節の該当行 |
| --- | --- | --- | --- |
| A | 状態 | `teamName`・`teamId`(null 可)・`sessionExpired`・`hasHydrated`・`authEpoch` と computed `isAuthenticated` だけを持つ。トークン・`authKind`・`username`・`role` は持たない | 認証リダイレクト・永続化と hydration |
| B | 操作 | `signIn({ teamName, teamId? })`・`signOut()`・`expireSession()`。3 つとも先に `queryClient.clear()` と `authEpoch` の加算を行う。`expireSession()` は失効を `sessionExpired` で示す(旧は 401 で黙ってログアウトしていた) | `getState()` の命令的参照 |
| D | 永続化 | キー `bb.auth` を維持し、`{version:1, sessionId, teamName, teamId}` だけを書く。`sessionId` はログインごとの乱数で認証情報ではない。保存に失敗したタブは**切り離し状態**に入り、古い保存値へ戻らない | 永続化と hydration |
| E | 読めない値 | JSON でない・形が違う(旧 zustand 形式を含む)値は消して未認証で始める。旧形式は移行しない | 永続化と hydration |
| G | タブ間の同期 | `syncFromStorage()` を公開し、`storage` イベントと U-F6 の送信前に呼ぶ。保存値の `sessionId` が変わったときだけキャッシュを消して差し替える。**旧からの意図的な逸脱**(旧はタブ間同期を持たない — PO 決定 2026-10-10) | — |
| H | 命令的な参照 | component の外からは `useAuthStore(pinia)` で取る。Pinia の instance は U-F13 が作る | `getState()` の命令的参照 |
| J | 購読中の画面 | `authEpoch` を鍵にして、認証が変わったら購読中の画面を作り直す(`RouterView` の `:key` — U-F13)。`queryClient.clear()` は購読中の observer の直前結果を消さないため。**旧からの意図的な逸脱**(旧も同じ欠陥を持つ) | — |

**後続の単位への注意**:
- `isTeamAdmin`(`role === 'admin'`)による出力・削除・編集の出し分けは、チームログインでは常に真だった。役割を持たないので、すべて「出す」側で移す。
- 未同期キュー・端末設定の `bb.*` キーは、認証が変わっても消さない(要件書 `:329`)。
- 別タブのログインで Cookie が先に変わる窓は、クライアントだけでは閉じない。応答のテナントを照合する契約が δ(TSK-470)と U-F6 に要る(計画書 決定 G)。
