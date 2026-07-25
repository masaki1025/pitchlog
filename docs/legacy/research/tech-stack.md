# 調査レポート: tech-stack

## 要約

推奨スタックは「FastAPI + React 19 (Vite) SPA/PWA + Tailwind CSS v4 + shadcn/ui + TanStack Query v5 / Zustand + Recharts 3（標準チャート）+ visx/素SVG（ストライクゾーン・スプレーチャート）」。バックエンドは既存の domain/services/db 層（同期 sqlite3/psycopg2）をほぼ無改修で再利用できる FastAPI 0.139 が最適で、Litestar は v3 移行リスク、Django Ninja は Django ORM 前提が既存資産と噛み合わない。フロントは認証必須の業務ツールで SEO 不要のため Next.js の SSR/RSC は過剰であり、vite-plugin-pwa によるオフライン対応が容易な React+Vite SPA を推奨（SvelteKit は有力な次点）。1球入力の高速化は TanStack Query の楽観的更新＋Zustand のローカル打席状態で実現し、同期はポーリング（refetchInterval）を基本に、複数端末ライブ共有が必要になった時のみ Supabase Realtime を postgres モード限定で追加する。matplotlib の PDF 帳票資産はサーバー側にそのまま残せる。

---

# 野球スコアリングシステム 次期技術スタック調査レポート（2026年7月時点）

## 0. 前提と現状資産の確認

現行コードベース（`C:\develop\baseball_system`）を確認した結果:

- **UI**: Streamlit 1.56.0（`app/pages/game_input.py` 等）。1球ごとの多項目入力で全スクリプト rerun が発生するのが遅さの根本原因
- **ドメインロジック**: `domain/`（scoring_rules, runner_advancement, game_state, scoreboard 等）と `services/`（play_recording, play_editing, game_lifecycle 等）に**UIから分離済み** — これは移行の最大の資産
- **DB層**: `db/*_repo.py` が素の `sqlite3` / `psycopg2` を `APP_DB_MODE`（settings.py）で切替。SQLAlchemy 非依存
- **チャート**: `charts/` は matplotlib ベース（PDF帳票 `reports/score_card.py`、投手カルテPDFを含む）

この構造なら「HTTP API層を上に被せる」だけで移行でき、ドメインロジックの書き直しは不要。

---

## 1. バックエンド: **FastAPI を推奨**

| | FastAPI | Litestar | Django Ninja |
|---|---|---|---|
| 最新版 (2026-07確認) | **0.139.0** (2026-07-01, Python ≥3.10) | 2.24.0 (2026-06-11)、**3.0が開発中(63%)** | 1.6.2 (2026-03-18, Django 3.1〜6.0対応) |
| 既存資産の再利用 | ◎ 同期関数はスレッドプール実行されるため**既存の同期 sqlite3/psycopg2 リポジトリをそのまま呼べる** | ○ 同様に可能だが msgspec 前提の設計に寄せたくなる | △ Django ORM/プロジェクト構造が前提。素のSQLリポジトリとの共存は不自然 |
| スキーマ/検証 | Pydantic v2、OpenAPI自動生成 | msgspec（最速）+ Pydantic も可 | Pydantic v2 |
| エコシステム/情報量 | 最大。AIコーディング支援の学習データも最多 | 小さい（採用・学習リスクと各比較記事が指摘） | Django資産がある場合のみ有利 |
| 性能 | 十分（実運用ではDB待ちが支配的） | ベンチ最速だが「合成ベンチはLitestarが勝ち、実運用判断はFastAPIが勝つ。差はユーザ体感に出ない」というのが2026年の評価 | 十分 |

**推奨: FastAPI 0.139**

根拠:
1. **`services/` の関数をルーターから呼ぶだけ**で移行できる。`def`（非async）エンドポイントは自動でスレッドプール実行されるため、既存の同期DBコードを async 化する必要がない
2. `domain/input_validation.py` 等の検証ロジックを Pydantic モデルに段階的に寄せられる
3. 少人数チームにとってドキュメント・事例・AI支援の豊富さが最重要。Litestar は技術的に魅力的（msgspec、DI設計）だが v3.0 の破壊的変更を控えており、いま採用すると近い将来の追従コストを払う
4. Django Ninja は「Django admin が欲しい」場合のみ検討価値あり。本件は既に `app/pages/admin.py` 相当を自作しており、Django 全体を持ち込む理由が薄い

補足: 将来 async 化したくなったら SQLite は `aiosqlite`、Supabase は `psycopg`(v3)/`asyncpg` へ段階移行可能。まずは同期のままで問題ない。

---

## 2. フロントエンド: **React 19 + Vite（SPA/PWA）を推奨**

| | React + Vite | Next.js | SvelteKit |
|---|---|---|---|
| 最新版 | React **19.2.7** / Vite **8.1.4**（Rolldownベースのビルド） | 16.2.10（16.3系の発表あり。Turbopack標準、React Compiler安定化） | SvelteKit **2.69.2** / Svelte **5.56.4**（runes構文） |
| 本件への適合 | ◎ 認証必須ツールでSEO不要 → SPAで十分 | △ SSR/RSC/キャッシュ制御は本件では過剰。サーバー運用も増える | ○ 軽量・高速。次点 |
| PWA/オフライン | ◎ **vite-plugin-pwa 1.3.0**（Workbox内蔵、ゼロコンフィグ寄り） | △ 公式PWAサポート弱め（Serwist等サードパーティ） | ○ vite-plugin-pwa が同様に使える |
| タッチUI部品の入手性 | ◎ shadcn/ui, Radix, visx 等 React 専用資産が最多 | ◎（同左） | △ shadcn-svelte 等移植はあるが層が薄い |
| 学習コスト（Python出身の少人数） | 中。情報量とAI支援で実質最も低い | 高（RSC/キャッシュのメンタルモデルが重い） | 低〜中（構文は最も素直） |
| バンドル/初期表示 | SPAで42KB級（Next SSGの92KBの半分以下という比較データあり) | 大きめ | 最小 |

**推奨: React 19 + Vite 8 の SPA + PWA 構成**

根拠:
1. 本件は「ログインして使う入力ツール」であり、Next.js が優位性を持つ SEO・初回表示・ISR が全て不要。2026年の比較記事も「認証ゲート付き画面は React+Vite、公開ページは Next.js」と役割を明確化している
2. **1球入力の速さはクライアント状態管理の問題**であり、SPA ならボタンタップ→即時UI更新（楽観的更新）→バックグラウンドPOSTにできる。Streamlit の rerun 問題が構造的に消える
3. PWA 化（ホーム画面追加・全画面表示・オフラインキャッシュ）は vite-plugin-pwa + Workbox で完結。グラウンドでの回線不安定対策として、入力を IndexedDB の outbox に積んで復帰時に送信するパターンが確立している
4. SvelteKit は次点として十分実用（`adapter-static` でSPA化可能、Svelte 5 の runes は学習しやすい）。ただし後述の UI ライブラリ・チャート資産が React 前提のものが多く、少人数で「作らずに済ませる」には React が有利

---

## 3. UIライブラリ: **Tailwind CSS v4 + shadcn/ui を推奨**

| | Tailwind + shadcn/ui | Mantine | Chakra UI |
|---|---|---|---|
| 最新版 | Tailwind **4.3.2**（CSSファースト設定、OKLCH）/ shadcn/ui は Tailwind v4 + React 19 完全対応済み | @mantine/core **9.4.1**（v9は2026-03リリース、120+コンポーネント） | @chakra-ui/react **3.36.0**（v3で Panda CSS + Ark UI に全面書き換え） |
| コンポーネントの所有 | ◎ **コードを自分のリポジトリにコピーして所有** → タッチターゲット44〜48px化などの改変が自由 | △ テーマAPI経由 | △ テーマAPI経由 |
| カスタムSVG部品（ストライクゾーン、フィールド図）との親和性 | ◎ ただの React SVG コンポーネントを Tailwind クラスで装飾するだけ。ライブラリのスタイルと衝突しない | ○ 可能だが Mantine のスタイルシステムと二重管理になる | ○ 同左 |
| 既製部品の量 | 中（必要十分。Radixベースでアクセシビリティ担保） | 最多（DatePicker、通知、リッチエディタまで） | 多 |

**推奨: Tailwind v4 + shadcn/ui**

根拠:
1. 本アプリのUIの核心は**既製部品ではなく自作部品**（ストライクゾーングリッド、フィールド図タップ、球種・結果の大型ボタンパッド）。現行の `app/ui/plate.py` / `field.py` / `coordinate_click.py` に相当するものは、どのライブラリでも結局 SVG + ポインタイベントで自作する。ならばスタイル層が最も薄く衝突しない Tailwind + 所有型の shadcn/ui が最適
2. タッチファースト要件（最小44px・望ましくは48pxのタップ領域、`touch-action: manipulation`、`pointerdown` での即時反応）は、コンポーネントのソースを直接編集できる shadcn/ui 方式が最も実装しやすい
3. 次点は **Mantine v9**:「作る時間を最小化したい」「フォーム・日付・通知を既製で済ませたい」なら合理的。Chakra は v3 で基盤총入れ替え（Emotion→Panda CSS）直後で、今から採用する積極的理由が薄い

---

## 4. 状態管理・データ同期: **TanStack Query v5 + Zustand、同期はポーリング基本 + 必要時 Supabase Realtime**

**推奨バージョン**: @tanstack/react-query **5.101.2** / zustand **5.0.14** / @supabase/supabase-js **2.110.1** / dexie **4.4.4**（IndexedDB用）

### 設計指針（2026年のコンセンサス「サーバー状態とクライアント状態の分離」に従う）

1. **サーバー状態 = TanStack Query v5**
   - 試合データ・成績の取得/キャッシュ/再取得を全部任せる
   - **1球入力は `useMutation` + `onMutate` の楽観的更新**: タップ瞬間にスコアボード・カウント表示を更新し、失敗時のみロールバック。これが「rerun の遅さ」の直接的な解になる
   - `networkMode: 'offlineFirst'` + mutation キューでオフライン入力→復帰時送信。恒久化が必要なら IndexedDB（Dexie）に outbox を置く（localStorage は同期APIなので不可、が定石）
2. **クライアント状態 = Zustand**
   - 「入力中の1球の途中状態（球種選択→コース→結果）」「選択中打者」「UIモード」など送信前の状態のみを持つ。小さく速く、Redux 不要
3. **同期方式**
   - **基本はポーリング/再取得で十分**: 入力者1人＋閲覧者少数のユースケースでは、mutation 成功時の `invalidateQueries` + 閲覧画面の `refetchInterval`（例: 5〜15秒）で成立する。SQLite ローカルモードでは Realtime が存在しないため、どのみちこの経路が必要
   - **複数端末でのライブ共有が要件化したら Supabase Realtime を追加**（postgres モード限定）: Postgres Changes / Broadcast / Presence の3モード。注意点として (a) WebSocket 専用でロングポーリングfallbackなし、(b) 対象テーブルに RLS + レプリケーション設定が必須、(c) 再接続戦略は自前実装が必要
   - FastAPI 自前 WebSocket も可能だが、接続管理・スケール・再接続を自作する運用コストに見合わない。SSE（FastAPI が公式サポート）は「片方向のライブ配信だけ欲しい」場合の中間解

---

## 5. チャート: **Recharts 3（標準チャート）+ visx / 素SVG（ヒートマップ・スプレーチャート）の併用を推奨**

| | Recharts | visx | Plotly.js | Observable Plot |
|---|---|---|---|---|
| 最新版 | **3.9.2**（v3で内部状態管理を全面書き換え、活発に開発中） | @visx/visx **4.0.0**（@visx/heatmap あり） | 3.7.0 | 0.6.17 |
| 位置づけ(2026) | React標準チャートのデファクト（npm週間DL最多） | D3+Reactの低レベル部品。「自分専用チャートライブラリを作る」ためのもの | 科学技術・3D向け。**フルバンドルはminifiedで2MB超**（partial bundle で削減可） | ggplot2的文法。ただしReactネイティブでない（useEffectでDOM生成） |
| ヒートマップ適性 | △（自作寄り） | ◎ @visx/heatmap + d3-scale | ◎ 組み込み | ○ cellマーク |
| スプレーチャート（フィールド図上の打球）適性 | △ | ◎ 任意SVG（フィールド図）に重ねるのが自然 | △ 背景画像上scatterで可能だが重い | △ |
| タッチ操作・PWAとの相性 | ○ | ◎（素のReactイベント） | △ バンドル重量が痛い | ○ |

**推奨:**
- **打撃成績推移・球速分布・投球割合などの定型チャート → Recharts 3.9**（Reactコンポーネントとして最も素直、情報量最多）
- **ストライクゾーンヒートマップ（現行 `plot_courseDetail.py`/`plot_course_dist.py` 相当）とスプレーチャート（`plot_battedBall.py` 相当）→ visx（@visx/heatmap, @visx/scale）または素のSVG + d3-scale**。ゾーン9分割/25分割グリッドやフィールド扇形は固定座標系なので、実は visx すら不要で素SVGが最速。入力UI（ゾーンタップ・フィールドタップ）と描画コンポーネントを共通のSVG座標系で共用できるのが最大の利点
- **Plotly.js は非推奨**: タブレットPWAに2MB級バンドルは過剰。既存が Plotly ではなく matplotlib なので移行上の利点もない
- **重要**: `charts/*/calc_*.py` の集計ロジックはPythonに残し、**APIがJSONを返してフロントは描画だけ**行う分担にする。また **PDF帳票（スコアカード・投手カルテ）は matplotlib のままサーバー側で生成し続けられる** — フロント移行の対象外にできるので移行コストが大幅に減る

---

## 6. 推奨スタック総括

| レイヤ | 採用 | バージョン (2026-07-09 確認) |
|---|---|---|
| API | FastAPI | 0.139.0 |
| ASGIサーバー | Uvicorn | 最新安定版 |
| DB | 既存 repo 層を継続（sqlite3 / psycopg2、APP_DB_MODE切替） | — |
| フロント基盤 | React + Vite + TypeScript | React 19.2.7 / Vite 8.1.4 |
| PWA | vite-plugin-pwa (Workbox) | 1.3.0 |
| UI | Tailwind CSS + shadcn/ui (Radix) | Tailwind 4.3.2 |
| サーバー状態 | TanStack Query | 5.101.2 |
| クライアント状態 | Zustand | 5.0.14 |
| オフラインoutbox | Dexie (IndexedDB) | 4.4.4 |
| ライブ同期(任意) | Supabase Realtime (supabase-js) | 2.110.1 |
| チャート | Recharts + visx/素SVG | Recharts 3.9.2 / visx 4.0.0 |
| 帳票 | matplotlib（サーバー側で継続） | 既存のまま |

### 段階的移行シナリオ（Streamlit 併存前提）
1. **Phase 1**: FastAPI を追加し `services/`・`db/` を API 化（Streamlit はそのまま稼働）
2. **Phase 2**: 最痛点の**試合入力画面のみ** React SPA/PWA で新規実装（ゾーン/フィールドSVG入力 + 楽観的更新）
3. **Phase 3**: 分析・帳票画面を順次移行。PDF系はAPI経由で matplotlib 出力を配信し最後まで残してよい

---

## 7. 参考URL

**バックエンド**
- FastAPI PyPI: https://pypi.org/project/fastapi/ / リリースノート: https://fastapi.tiangolo.com/release-notes/
- Litestar PyPI: https://pypi.org/project/litestar/ / 3.0変更点: https://docs.litestar.dev/3-dev/release-notes/whats-new-3.html
- Django Ninja PyPI: https://pypi.org/project/django-ninja/
- フレームワーク実測ベンチ比較: https://github.com/tanrax/python-api-frameworks-benchmark

**フロントエンド**
- Next.js vs React+Vite (2026): https://techsy.io/en/blog/nextjs-vs-react-vite
- Next.js 代替比較 (2026): https://naturaily.com/blog/best-nextjs-alternatives
- Svelte vs React (2026): https://strapi.io/blog/svelte-vs-react-comparison
- Next.js 16: https://nextjs.org/blog/next-16
- Svelte近況 (2026-07): https://svelte.dev/blog/whats-new-in-svelte-july-2026
- vite-plugin-pwa: https://github.com/vite-pwa/vite-plugin-pwa / https://vite-pwa-org.netlify.app/workbox/generate-sw
- オフラインPWA実践: https://css-tricks.com/vitepwa-plugin-offline-service-worker/ / https://adueck.github.io/blog/caching-everything-for-totally-offline-pwa-vite-react/

**UIライブラリ**
- shadcn/ui Tailwind v4対応: https://ui.shadcn.com/docs/tailwind-v4
- React UIライブラリ比較: https://makersden.io/blog/react-ui-libs-2025-comparing-shadcn-radix-mantine-mui-chakra
- Mantine vs Chakra vs MUI (2026): https://adminlte.io/blog/mantine-vs-chakra-ui-vs-mui/

**状態管理・同期**
- TanStack Query 楽観的更新: https://tanstack.com/query/v5/docs/react/guides/optimistic-updates
- TanStack Query 2026解説: https://blog.codercops.com/blog/tanstack-query-server-state-2026
- Supabase Realtime: https://supabase.com/realtime / フォールバック無しの議論: https://github.com/orgs/supabase/discussions/17644
- Socket.IO vs Supabase Realtime (2026): https://ably.com/compare/socketio-vs-supabase

**チャート**
- 可視化ライブラリ比較 (2026): https://www.youngju.dev/blog/culture/2026-05-14-data-visualization-libraries-2026-d3-plot-visx-recharts-echarts-vega-comparison-deep-dive-2026.en
- Recharts 3.0 移行ガイド: https://github.com/recharts/recharts/wiki/3.0-migration-guide
- Plotly.js partial bundles: https://github.com/plotly/plotly.js/blob/master/dist/README.md
- visx ギャラリー: https://airbnb.io/visx/gallery
