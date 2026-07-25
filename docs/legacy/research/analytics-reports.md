# 調査レポート: analytics-reports

## 要約

Tsukuba PSSの分析機能は「リアルタイム試合中統計（analytics/cal_stats.py）」「期間集計型の投手・打者分析画面（analytics/pitching, analytics/batting）」「純粋計算・描画層（charts/）」「帳票生成（reports/）」の4層で構成される。統計計算の中核（charts/batting/calc_stats.py, charts/pitching/calc_stats.py, charts/batting/analyse_strategy.py, reports/*_karte_html_pdf.py の collect系）はStreamlit非依存の純粋pandas関数であり、DataFrame（1球1行・88列）を渡せばそのままバックエンドAPI化可能。Streamlit依存はUI層（analytics/の各show()、score_card.show()）とキャッシュデコレータ（@st.cache_data）に限定される。チャートはmatplotlib/plotnine/scipyでPNG静止画を生成してst.imageで表示する方式が主流で、唯一plotlyを使うのは試合入力画面の球種円グラフのみ。帳票はreportlab/pypdf/python-pptx/PyMuPDF製に加え、HTML+SVG+CSSをheadless Chrome/EdgeでPDF化する新型「カルテ」が2種ある。捕手別・ストーリー性のある球順分析・走者状況別成績・時系列推移・対戦マトリクスなど、データは存在するが可視化されていない領域が多数残っている。

---

# Tsukuba PSS 分析・可視化・帳票機能 棚卸しレポート

対象: `C:/develop/baseball_system/analytics/`, `charts/`, `reports/`（読み取り専用調査、2026-07-09時点）

## 0. 全体アーキテクチャ

```
DB(SQLite: play_data 88列・1球1行)
  └ services/plays_cache.py  get_cached_team_plays_df(team_id)   ← @st.cache_data(ttl=3600)
       派生列を付与: 守備チーム/攻撃チーム/コースYadj(=263-コースY)/打球位置Yadj/_date
  └ db/game_repo.get_plays_df_for_game(game_id)                  ← スコア表用（1試合）
       ↓
charts/    …… 純粋計算 + matplotlib/plotnine描画（Streamlit非依存）
analytics/ …… Streamlit画面（show()）+ リアルタイム統計 cal_stats
reports/   …… PDF/PPTX/HTML帳票生成（score_card.py のみ画面を持つ）
app/pages/game_input.py …… 試合入力画面。analytics/cal_stats を呼びリアルタイム表示
```

- データ列（`config.py` COLUMN_NAMES, 88列）: 試合メタ（試合日時/Season/Kind/主審…）、カウント（S/B/アウト）、走者（一〜三走の氏名・番号・状況）、作戦（作戦/作戦2/作戦結果）、投球（構え/コースX/コースY/球種/球速）、打撃（打撃結果/打撃結果2/打席結果/打球タイプ/打球強度/打球位置X/Y/捕球選手）、その他（牽制の種類/牽制詳細/エラーの種類/タイムの種類/プレス/偽走/捕手/経過時間 等）。
- 用語定義は `domain/batting_results.py`（HIT_RESULTS, STRIKEOUT_RESULTS, WALK_RESULTS, WHIP_WALK_RESULTS, 犠打犠飛, 妨害, 盗塁死等）と `domain/pitching_innings.py`（アウト数→投球回変換: 表示用 1.1形式 / レート用 outs/3 / スコアブック用 ⅓表記）に集約されている。**新UIでもこのdomain層は再利用価値が高い。**

---

## 1. 算出している統計指標の完全リスト

### 1-A. 投手・シーズン総合（`charts/pitching/calc_stats.py :: calc_overallStats()` L276-394）
呼び出し元: `analytics/pitching/stats_mode.py`（チーム全投手一覧）、`analytics/pitching/analysis.py`（個人・vs右/vs左/チーム平均の4行比較）、`reports/pitcher_pdf.py`, `pitcher_pptx.py`

| 指標 | 計算式（コード上） |
|---|---|
| 登板数 | (試合日時,先攻,後攻)のdrop_duplicates数 |
| 投球回 | count_pitcher_outs（打者状況+走者状況のアウト集計）→ 1.2形式 |
| 投球数 / 打席数 / 安打数 / 本塁打数 / 奪三振数 / 四死球数 | 打撃結果ベースの単純カウント |
| 失点数 | 打者/一走/二走/三走状況の「本進」件数（自責点ではない） |
| 失点率 | 9×失点/投球回（ERA相当。ただし失点ベース） |
| ストライク率 | 非(ボール・四死球)投球 / 全投球 |
| 空振り率 | (空振り+空振り三振) / スイング数 |
| 被打率 / 被出塁率 / 長打率 / OPS | 打数=打席-除外(四死球・犠打飛・妨害)、塁打数は単打1〜本塁打4 |
| K% / BB% / K-BB% | 対打席数比 |
| 奪三振率(K/9) | 9×K/投球回 |
| 内野フライ率 | フライかつ捕球選手1〜6 / 打球総数 |
| ゴロ率 | ゴロ / 打球総数 |

補助: `prepare_overall_stats_table()` が「平均値」行のカウント系と、非本人行の登板数・投球回・失点系を "--" にマスクする表示整形。

### 1-B. 投手・球種別（`charts/pitching/calc_stats.py :: calc_stats()` L107-273）
球種×打者左右ごとに算出（球種リストは `calc_ptList.py`＝出現数降順）:
- 投球数、ストライク率、**ゾーン率**（コースX/Yadj∈[53,210]）、スイング率、**空振り率(Whiff%)**、**ゾーン外スイング率(O-Swing%)**、**PutAway率**（2ストライク投球のうち三振で終えた率）、ゴロ率、フライ率、被打率、出塁率、長打率、OPS
- **構え位置割合**: 3塁側/真ん中/1塁側/高め（捕手の構えコード1〜25を集約。ゲーム入力画面のコード体系と対応）

### 1-C. 投手・登板履歴（`calc_appearance_history()` L397-430）
試合ごとに 投球回/投球数/打者数/被安打数/四死球数/失点数。

### 1-D. 打者（`charts/batting/calc_stats.py :: calc_batting_stats()`）
呼び出し元: `analytics/batting/stats_mode.py`（チーム一覧+チーム計行）、`analysis_mode.py`（個人・対右/対左/平均、球種グループ別〔ストレート/スラ系/落ち系〕）

| 指標 | 備考 |
|---|---|
| 打席数 / 打数 / 打率 / 出塁率 / 長打率 / OPS | 打席結果（打席完了行）ベース |
| 安打数 / 本塁打数 / 打点 / 三振数 / 四死球数 / 犠打数 | 打点は「本進」集計、併殺打時は除外 |
| K% / BB% | 対打席比 |
| 平均投球数 / 2S以降平均投球数 | P/PA |
| スイング率 / ゾーン外スイング率 / 空振り率 / 1stストライクスイング率 | 投球単位 |
| ゴロ率 / フライ率 | フライは捕球選手<7:内野、>=7:外野に分解して合算 |

### 1-E. チーム作戦分析（`charts/batting/analyse_strategy.py` + `analytics/batting/analysis_mode.py`）
- 状況別打席結果内訳（0死1塁 / 1死1塁 / 走者2塁）: 単打/長打/四死球/三振/犠打/盗塁成功/盗塁失敗/進塁打/凡打/併殺/牽制死（`analyse_R1_strategy`, `analyse_R2_strategy`）
- 盗塁: 二盗/三盗の企図数・成功数・成功率（チーム計+選手別）、状況分布（アウトカウント別、S-Bカウント別）
- バント: 犠打企図率・成功率（0死/1死 × R1/R2/R12 の6状況）、セフティ（選手別成功/失敗）、スクイズ/セフティスクイズ成功率

### 1-F. リアルタイム（試合中）統計（`analytics/cal_stats.py`）
- `cal_stats()`: **当日**投手成績（投球回/最速/ストレート平均球速/被安打H/奪三振K/四死球B/失点R、対戦投手球数・自投手球数）+ **シーズン**投手成績（被打率OAV/対右vsR/対左vsL/通算投球回/WHIP/FIP）+ 現打者・次打者の「Today打席結果列挙」「シーズン打率/対右/対左/HR数」。**WHIPとFIP（定数3.1、13HR+3BB-2SO）/9…はこのファイルにしか存在しない**（シーズン分析画面には未実装）。
- `pt_pct()`: 投手の球種割合（リアルタイム円グラフ用）
- `calc_hekb()`: 当該試合の表裏別 H/E/K/B（Eは「タイムの種類∈1..9」で判定）

### 1-G. カルテ帳票内の独自集計（画面には出ない指標）
- **投手カルテHTML** `reports/pitcher_karte_html_pdf.py :: collect_stats()`: コース3×3被打率ヒート（全体/左右別）、捕手構え位置3×3分布+球種構成、カウントバケット別球種傾向（0S0B/1S0B/0S1B/1S1B/打者有利）、**2ストライク後**の球種構成・ゾーン率・ゾーン外空振り球種、**初球ゾーン率**（左右別3×3+球種構成）、球種別コース密度（SVGヒート）、球速の10-90パーセンタイル帯
- **打者カルテHTML** `reports/batter_karte_html_pdf.py :: collect_batter_stats()`: 基本成績+結果ピル（単打〜犠打8種）、**配球用データカード**（初球スイング率と多く振る球種／2スト後成績と空振りしやすい球種／ゾーン外スイング率と振る球種／「注意球種・注意コース」「攻め候補（低結果球種・コース）」の自動抽出）、対右/対左投手ヒートマップ（コース3×3打率）、球種別成績（左右別 投球数と結果）、カウント別反応（投球/スイング/空振り/結果）、選球・コンタクト（ゾーン内コンタクト率とその内訳ファール/凡打/安打、全体空振り率）、球速帯別成績（〜129/130-134/135-139/140〜）、打球質（ゴロ/ライナー/フライ別安打、打球強度A+B比率）、小技・走塁（盗塁/送りバント/セフティ/バスター/エンドラン/スクイズの成功/企図）、スプレーチャート（打球位置が無い行は結果テキストから合成座標を生成する `synthetic_batted_ball` あり）

---

## 2. チャート種類一覧と使用ライブラリ

| チャート | 実装場所 | ライブラリ | 出力形態 |
|---|---|---|---|
| 球種割合 円グラフ（全体/カウント別B-S対角グリッド12個） | `charts/pitching/plot_pt_pieChart.py` | matplotlib | Figure→PNG |
| コース分布 2Dカーネル密度（ストライクゾーン枠+ホームベース） | `charts/pitching/plot_course_dist.py` | **plotnine**(stat_density_2d) | PNG |
| コース詳細 散布図（打球タイプ色×結果マーカー、凡例2種） | `charts/pitching/plot_courseDetail.py` | matplotlib | PNG |
| 打球方向図（フェンス・ファールライン描画、ゴロ=破線/フライ=弧、ヒット赤/凡打黒/ファール橙） | `charts/pitching/plot_battedBall.py` | matplotlib(FancyArrowPatch) | PNG |
| 球速分布 KDE（球種別色分け+平均球速矢印） | `charts/pitching/plot_velocityDist.py` | matplotlib + **scipy** gaussian_kde | PNG |
| 被打球性質 100%積み上げ横棒（完全アウト/ゴロ/外野フライ+ライナー/四死球/本塁打、個人vs全体比較） | 同上 `batted_type_plot` | matplotlib | PNG |
| 投手スタッツ表（カテゴリ帯色: スタッツ紺/構え緑） | `charts/pitching/plot_statsTable.py` | matplotlib ax.table | PNG |
| 投手総合スタッツ表 / 打者スタッツ表（チーム計行ハイライト） | `plot_overallStatsTable.py`, `charts/batting/plot_statsTable.py` | matplotlib ax.table | PNG |
| 登板履歴テーブル | `charts/pitching/plot_appearanceHistory.py` | matplotlib ax.table | PNG |
| 攻撃分析 円グラフ×3（0死1塁/1死1塁/走者2塁）、盗塁状況 円グラフ×4 | `analytics/batting/analysis_mode.py` | matplotlib | PNG |
| コース別打率 13分割ゾーン図（9マス+四隅、打率で赤/青/灰着色） | `analysis_mode.py :: _calc_course_chart()` | **plotnine**(geom_rect+annotate) | PNG |
| リアルタイム球種円グラフ（試合入力画面） | `app/pages/game_input.py` L592-642 | **plotly** go.Pie | st.plotly_chart（唯一のインタラクティブチャート） |
| コース3×3被打率ヒートマップ、構え位置3×3、球種構成ミックスバー、球種別コース密度SVG（ガウスぼかし3層）、初球ゾーン3×3 | `reports/pitcher_karte_html_pdf.py` | **手書きHTML+CSS+SVG** | HTML→Chrome/EdgeでPDF |
| 打者ヒートマップ3×3、スプレーチャート（球場SVG+打球線+HRマーカー）、打球方向サマリ | `reports/batter_karte_html_pdf.py` | 手書きHTML+CSS+SVG | 同上 |

特徴: **画面表示はほぼ全て「matplotlib/plotnineでPNG化→st.image」**。ズーム・ツールチップ等の対話性はない。日本語フォントは `font_registry.py`（IPAexGothic）で登録。分析画面は `@st.cache_data(ttl=1800, max_entries=48)` でプリミティブキー（team_id, 期間, チーム, 選手, side, 球種）による画像バイトキャッシュを実装済み。

---

## 3. リアルタイム統計 vs シーズン通算統計の区別

| 区分 | 実装 | データ範囲 | 更新タイミング |
|---|---|---|---|
| **リアルタイム（試合中）** | `analytics/cal_stats.py` → `app/pages/game_input.py` のHTMLカード（P/打者/次打者カード、B-S-Oカウント、球種円グラフ、H/E/K/Bスコアボード） | 「今日」= 試合日時+先攻+後攻で特定した当該試合。同一DF内でシーズン累計（全期間）も同時算出し1枚のカードに併記 | 1球入力ごと（st.rerun）。`@st.cache_data(show_spinner=False)` |
| **シーズン/期間集計** | `analytics/pitching/{stats_mode,analysis}.py`, `analytics/batting/{stats_mode,analysis_mode}.py` | `get_cached_team_plays_df(team_id)` の全プレイを**開始日〜終了日**のdate_inputで任意フィルタ（デフォルトは全期間）+ チーム選択 | 手動「データを更新」ボタンでキャッシュクリア |
| **1試合単位** | `reports/score_card.py`（スコア表・スコアブック・投手スコア） | game_id 単位 | ttl=60のキャッシュ |

注意点: リアルタイム側の WHIP/FIP/対左右被打率は「シーズン累計」を試合中に見せるためのもの。**同じ指標でも計算実装が cal_stats.py と charts/ 側で二重実装**されている（例: 被打率・投球回。定義は domain/ 共有だがロジックは別コード）。新UI設計時は統一必須。

---

## 4. PDF/PPTX帳票の内容

| 帳票 | 場所 | 形式 | 内容 |
|---|---|---|---|
| **スコアカード** | `reports/score_card.py :: generate_score_card_pdf()` | matplotlib→PDF 1ページ | ①イニングスコア表（1-9回+延長、計/H/E/K/B、得点イニング赤字、未消化「×」）②先攻/後攻スコアブック（打順×イニング、代打は元選手直下に行追加、守備位置変遷「P→LF」、スタメン丸数字、得点丸数字①-⑨、打者一巡「/」区切り、ヒット赤・四死球青・犠打緑）③両軍投手成績（投球回⅓表記/投球数/打者数/H/K/B） |
| **投手分析PDF** | `reports/pitcher_pdf.py :: generate_pitcher_pdf()` | reportlab A4縦 3ページ | P1: 総合スタッツ4行表・球速分布・被打球性質・登板履歴（ページまたぎ対応rlテーブル）・コメント / P2: vs右打者（球種別スタッツ表、球種割合パイ+カウント別4×3グリッド、コース分布/詳細/打球方向の3行×5球種グリッド）/ P3: vs左打者（同構成） |
| **投手分析PPTX** | `reports/pitcher_pptx.py :: generate_pitcher_pptx()` | python-pptx A4縦スライド | PDF版と同一コンテンツを画像貼付で再構成。`_Canvas` クラスがオーバーフロー時に自動でスライド追加。編集可能なのはテキストボックスのみで実質は画像羅列 |
| **投手カルテPDF（簡易版）** | `reports/pitcher_karte_pdf.py` | reportlab A4横 1人1ページ | ヘッダー（チーム/期間/被打率サマリ）、球種表（球種/球速帯/備考、手入力ノート優先・なければ実データから球速帯自動生成）、特徴（緑箱）、対右/対左パネル（メモ+球種別スタッツ表+球種割合パイ+コース分布）、全体対応（黄箱） |
| **投手カルテHTML型** | `reports/pitcher_karte_html_pdf.py` | HTML+SVG→**headless Chrome/Edge** `--print-to-pdf`（420×300mm、1人1ページ）| §1-Gの独自集計を1枚に凝縮: 球種表+特徴 / 対右・対左（メモ、被打率ヒート3×3、構え位置3×3+球種ミックスバー）/ カウント別球種傾向・2スト後プラン（左右別）/ 球種別コース密度SVG / 初球ゾーン率 / 全体対応。チームテーマカラー（`domain/team_theme.py` パレット）でヘッダー着色。Chrome不在時は `HtmlPdfRenderError` → HTMLだけダウンロード可能にフォールバック |
| **打者カルテHTML型** | `reports/batter_karte_html_pdf.py` | 同上（min_pa打席数フィルタ付き） | §1-G打者側の全部: 基本成績グリッド+結果ピル、特徴（手入力優先・なければ自動要約 `feature_items`）、配球用データ5カード、対右/対左ヒート+メモ、球種別成績表、カウント別反応表、スプレーチャートSVG、選球/コンタクト、球速帯成績、打球質、小技/走塁 |
| **打者スタッツ一覧PDF** | `analytics/batting/stats_mode.py :: _generate_stats_pdf()` | reportlab A4横 3ページ | 全体/対右投手/対左投手のチーム全打者スタッツ表（画像化テーブル、チーム計行つき） |
| **チーム作戦分析PDF** | `analytics/batting/analysis_mode.py :: _generate_strategy_pdf()` | matplotlib GridSpec→PDF 1ページ（A4横） | 3列構成: 攻撃分析円グラフ×3 / 盗塁（サマリ表・選手別表・円グラフ4）/ バント（犠打・セフティ・スクイズ表） |
| **プレイヤー分析PDF** | 同 `_generate_player_pdf()` | reportlab+pypdf 選手×3ページ | P1: ヘッダー+コメント+スタッツ4行+コース別打率13分割×3（全/右/左）/ P2: 対右（球種グループ別スタッツ+球種別散布・打球位置2行×3列）/ P3: 対左 |
| **統合出力（combined_output）** | `reports/combined_output.py` | pypdf マージ / PPTX | PDF: 紺色タイトルページ+スタッツ一覧(3p)+作戦分析(1p)+プレイヤー分析(選手×3p) を `_merge_pdfs` で結合。**PPTX版は統合PDFをPyMuPDF(fitz)でページごとPNG化し、A4横スライドに全面貼付するだけ**（編集不可のスクリーンショット集） |

---

## 5. 計算ロジックのStreamlit依存 — バックエンドAPI化の可否

`import streamlit` が存在するのは以下のみ（grep確認済み）:
`services/plays_cache.py` / `services/perf.py` / `reports/score_card.py` / `analytics/cal_stats.py` / `analytics/{batting,pitching}/*.py`（4画面）

| 層 | Streamlit依存 | API化評価 |
|---|---|---|
| `domain/`（batting_results, pitching_innings, team_theme） | なし | **そのまま移植可** |
| `charts/pitching/calc_stats.py`, `calc_ptList.py`, `charts/batting/calc_stats.py`, `analyse_strategy.py` | なし（pandas/numpyのみ） | **そのままAPI化可**。入力は前処理済みDataFrame（守備チーム/攻撃チーム/コースYadj/_date 列が必要 → plays_cache._add_derived_columns のロジックをAPI側に移せばよい） |
| `charts/*/plot_*.py` | なし（matplotlib Agg固定, PNG BytesIO返却） | サーバサイド画像生成APIとして流用可。ただし新UIでは JSON を返してフロントで描画する方が対話性で有利 |
| `reports/pitcher_pdf.py`, `pitcher_pptx.py`, `pitcher_karte_pdf.py`, `combined_output.py` | なし | API化可。combined_pdf は `analytics.batting.*` の `_generate_*_pdf`（プライベート関数）を逆importしている点だけ要リファクタ |
| `reports/{pitcher,batter}_karte_html_pdf.py` | なし | HTML生成は純粋関数。**PDF化はheadless Chrome/Edgeのサブプロセス起動**（Windowsパス優先、`tmp/karte_html_pdf` に一時ファイル）なのでサーバ環境ではChromiumの同梱が必要。HTMLをそのまま新UIに埋め込む選択肢もある |
| `analytics/cal_stats.py` | **@st.cache_data のみ**（本体はpandas演算） | デコレータを剥がせば即API化可。ただし戻り値が**添字アクセスの生リスト27要素**で、game_input.py が stats[0]〜[26] を直接参照する脆い契約。API化時はdict/スキーマ化必須 |
| `analytics/` 4画面・`reports/score_card.py::show()` | 全面依存（UI） | 新UIで置換される層。ただし内部のプライベート関数（_build_stats_df, _steal_rows, _generate_*_pdf, _calc_course_chart 等）に計算とPDF生成が同居しているため、切り出しが必要 |

その他の依存ライブラリ: pandas, numpy, matplotlib, plotnine, scipy(KDE), plotly(1箇所), reportlab, pypdf, PyMuPDF(fitz), python-pptx, PIL, IPAexGothicフォント（fonts/ipaexg.ttf）。

**結論**: 統計計算・集計は9割方Streamlit非依存で、DataFrame前処理（plays_cache）とキャッシュ機構だけ差し替えればFastAPI等でAPI化できる。要注意は (1) cal_stats のリスト戻り値契約、(2) analytics画面内に埋もれた計算関数（盗塁・バント・コース13分割）、(3) HTML→PDFのChrome依存、(4) 同一指標の二重実装。

## 6. 未実装領域（データはあるのに可視化されていない = 新分析アプリの追加価値候補）

1. **捕手別分析**: `捕手` 列は全球記録されているが analytics/charts/reports のどこからも参照されていない（grep 0件）。捕手別の配球傾向・盗塁阻止率・失点率が丸ごと未開拓。
2. **牽制・けん制効果**: `牽制の種類`/`牽制詳細` 列は未使用（牽制死は走者状況からの間接集計のみ）。牽制回数と盗塁企図抑止・牽制死の関係分析が可能。
3. **プレス/偽走**: 記録列があるが完全未使用。
4. **球順・配球シーケンス分析**: 1球ごとの時系列（プレイの番号・球数）があるのに「前の球→次の球」の遷移（例: 外スライダー後のストレート被打率）は未実装。カウント別集計はあるがシーケンスはない。
5. **走者状況別・得点圏成績**: 走者列は完備。打者の得点圏打率、投手のランナーあり時成績（セットポジション時の球速差・被打率）が未実装（作戦分析でR1/R2状況の作戦内訳のみ）。
6. **時系列推移**: 打者の月別/試合別打率推移、投手の球速推移（登板履歴テーブルはあるがグラフなし）、疲労分析（イニング別・球数帯別成績）が皆無。試合内の球速低下（球数×球速の散布）はデータ的にすぐ作れる。
7. **対戦マトリクス**: 特定打者vs特定投手の対戦履歴・成績。cal_stats がリアルタイムで断片的に出すのみで、閲覧画面がない。
8. **打球強度の本格活用**: `打球強度`（A/B等）は打者カルテの「強い打球」1行のみ。投手側のハードヒット率、コース×打球強度は未実装。
9. **カウント別打者成績の画面表示**: 打者カルテPDFにはカウント別反応があるが、**Streamlit画面には出ていない**（カルテ限定）。同様に初球ゾーン率・2スト後分析・配球用データカードもPDF限定 → 新UIで画面化するだけで価値が出る。
10. **審判傾向**: `主審` 列あり。ゾーン判定傾向（コース×見逃しストライク率）が算出可能だが未実装。
11. **試合時間・テンポ**: `経過時間`/`開始時刻` があるがタグ打刻ボタン以外に活用なし。投球間隔と結果の関係など。
12. **エラー・失策分析**: `エラーの種類`/`タイムの種類`（守備位置別失策）はスコア表のE数集計のみ。守備分析（ポジション別失策、捕球選手データからの守備範囲）が未開拓。
13. **チーム間比較・リーグビュー**: 全画面が「自チーム/選択チーム単発」。相手チーム横断のスカウティング一覧やランキングがない。
14. **対話的可視化**: 現状ほぼ全て静的PNG。plotly実装は1箇所だけあり、ヒートマップのドリルダウン（マスをクリック→該当打席一覧）等はデータ構造上（打席Id列あり）容易。
15. **指標の拡充**: FIP/WHIPがリアルタイム画面限定でシーズン分析画面に無い。BABIP、wOBA、ISO、QS率、K/BB、盗塁許可率（投手別）なども既存列だけで算出可能。
