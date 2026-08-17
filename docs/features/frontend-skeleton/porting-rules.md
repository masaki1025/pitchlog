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
| 認証リダイレクト | `RequireAuth` と `RequireTeamAdmin` は route meta（`requiresAuth` / `requiresTeamAdmin`）と global navigation guard に集約する。token がなければ `/login`、admin 以外なら `/` へ redirect する。 | 旧: `frontend/src/App.tsx:25-35` |
| 全 route | vue-router 4 に `/login`、`/help`、`/`、`/analysis`、`/analysis/pitchers/:playerId`、`/analysis/batters/:playerId`、`/team`、`/comparison-workspaces`、`/scorecards`、`/imports`、`/lineup`、`/games`、`/games/:gameId`、`/games/:gameId/lineup`、`/games/:gameId/plays`、catch-all を同じ path・認可条件で登録する。 | 旧: `frontend/src/App.tsx:55-164` |
| Provider の置き場 | `QueryClientProvider` は `@tanstack/vue-query` の plugin、`BrowserRouter` は vue-router、`ToastProvider` は `provide` に対応させる。router・Pinia・Vue Query は bootstrap 時に app へ install し、Toast は App root に置く。 | 旧: `frontend/src/App.tsx:1-7,49-54` |
| 永続化と hydration | auth state は Pinia へ移し、保存キーを **`bb.auth`** のまま維持する。旧 auth store は `persist` のみで明示的な hydration hook を置いていないため、Vue 側では hydration 完了状態を明示し、route guard と API 開始前に復元を待つ。旧 sync store の `onRehydrateStorage` / `hasHydrated` はこの待機を実装する際の既存パターンである。 | 旧: `frontend/src/stores/authStore.ts:23-49`; `frontend/src/stores/syncStore.ts:245-251` |
| `getState()` の命令的参照 | component 外の API client は Zustand の `useAuthStore.getState()` を使わない。export 済み Pinia instance を渡して `useAuthStore(pinia)` を関数内で取得するか、auth header / 401 logout を注入可能な HTTP client へ寄せる。 | 旧: `frontend/src/api/client.ts:46-66` |

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

### `display_geometry_263_v1.json` は `contracts/` へ移すこと（NFR-018）

旧では**リポジトリ直下の `shared/` にあり、frontend と backend が共有する意図の唯一のファイル**
だった。pitchlog での置き場は `contracts/`（ゴールデンベクタ・スキーマ）だが、**その作成は
Phase 4-3 の担当**で本タスクの範囲外のため、暫定で `frontend/src/lib/` に置いている。

**backend が同じ座標定義を必要とした時点で複製になり、NFR-018（ドメイン計算は単一実装 —
コピー実装を作らない）に違反する。** Phase 4-3 で `contracts/` を作る際に移すこと。

### Prettier 対象外にしたファイル（7 節の規則の適用結果）

`src/index.css` に加えて、逐語移植した次を `.prettierignore` へ加えた。

- `src/lib/format.ts` / `src/lib/displayGeometry.ts` / `src/lib/spatialInput.ts` /
  `src/lib/courseInputView.ts` / `src/lib/display_geometry_263_v1.json`

**比較コマンド**（7 節が「対象外にする前に記録する」と定めているもの）:

```bash
gh api "repos/masaki1025/Baseball_Scoring-archive/contents/frontend/src/lib/<name>?ref=dd03160044aa5932d3b5a025870c9a5a56d979ef" \
  --jq '.content' | base64 -d | diff -u - frontend/src/lib/<name>
```

JSON は旧 `shared/display_geometry_263_v1.json`、資産は `sha256sum` で比較する。

### `.vue` の逐語性は何を見て判定するか

`.tsx` → `.vue` は構文変換が入るため機械的な diff が取れない。**次の 4 点で判定する。**

1. **SVG の値** — `viewBox`・ゾーン矩形の座標・分割構造
2. **Tailwind クラス文字列** — 内容と並び順（静的クラスは集合として過不足なく一致させる）
3. **props / emits** — 名前・型・必須性が 1:1（`className` は prop を新設せず fallthrough）
4. **座標変換の結果** — テストで検査する。**jsdom はレイアウト計算をしないので
   `getBoundingClientRect()` は固定スタブが必須**（無いと 0 が返り検査が無意味になる）
