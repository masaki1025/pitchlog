# 調査レポート: baseball-apps

## 要約

主要な野球スコアリング/分析アプリ10種以上を調査した。入力UIの主流は「フィールド図中心＋下部常時表示アクションバー＋段階的ポップアップ」で、GameChangerの2025年刷新ではボール/ストライク/ファウル/アンドゥを常時表示化して入力ステップを削減している。高速化の定石は「頻出操作の1タップ化＋低頻度操作のメニュー格納（プログレッシブ・ディスクロージャー）」「カウント/打者交代の自動進行」「多段アンドゥ＋事後編集」の3点。分析画面はヒートマップ・スプレーチャート・配球ゾーン図が標準で、TruMedia/Synergy/6-4-3 Chartsはあらゆるチャートから該当映像へ直接ジャンプできる「データ↔映像連携」を差別化要素としている。タブレットは横持ちフィールド中心レイアウト＋画面下端への操作集約が実例として確認できた。

---

# 野球スコアリング/分析アプリ UI・UXパターン調査レポート

調査日: 2026-07-09 ／ 対象: GameChanger, iScore, TruMedia, Synergy Sports, Rapsodo Cloud, TrackMan Portal, Baseball Savant, 6-4-3 Charts, 一球速報.com(EasyScore), スポナビ野球速報, スコアラー, キューステ！ ほか

---

## 1. 1球ごとのデータ入力UIの実例

### 1.1 GameChanger（米・ユース〜アマ最大手）
- **フィールド図中心レイアウト**: 画面中央にダイヤモンド（フィールド）図を配置し、内野中央の「PITCH」ボタンから段階的ポップアップで投球結果を入力する構成（[Chalk & Clay比較レビュー](https://chalkandclay.com/baseball-scorekeeping-apps/)）。
- **2025年の刷新（重要）**: iOS版で「ボール・見逃しストライク・空振り・ファウル・アンドゥ・リドゥ」を**常時表示のスコアリングバー**に昇格。低頻度の結果のみ「Pitch」メニュー内に残す設計に変更。スコアラーは試合中ずっとフィールド表示画面に留まれる（[公式ブログ: Streamlined Scoring](https://gc.com/post/new-scoring-experience-for-gamechanger-baseball-softball)、UIスクリーンショット: https://cdn.prod.website-files.com/612f80dfbdb6466e4a7f5c93/68138c1af43a11283ccd5e43_Scoring%20Updates.avif ）。
- **インプレー入力フロー**: 「Ball in Play」→結果（ゴロ/フライ/ヒット等）を選択→**野手アイコンを打球位置へドラッグ&ドロップ**→Done、の3ステップ（[ヘルプ検索結果](https://help.gc.com/hc/en-us/articles/30710418133005-Basic-Scorekeeping)）。
- **自動進行**: 3ストライクで自動的に三振＋次打者、4ボールで自動的に四球＋一塁進塁。カウント管理をユーザーに意識させない。
- **事後編集**: 画面下の「Plays」リストから過去のプレーを選択して結果・選手割当を修正可能（リアルタイムで未割当にしたプレーも後から補完できる）。
- 参考: [スコアキーピング機能ページ](https://gc.com/app-features/scorekeeping)

### 1.2 iScore Baseball（老舗・高機能系）
- **画面下部の結果ボタン**: 球種・球速・コースを記録しない場合、ほとんどの投球は画面下部の Ball / Strike / Foul / In Play の**1タップ**で完結（[Beyond the Box Scoreレビュー](https://www.beyondtheboxscore.com/2010/8/10/1615326/software-review-espn-iscore)）。
- **ゾーン図タップ+ドラッグ**: Pitch Trackerでコースをゾーン図タップで記録し、球速はインジケーターの**ドラッグ**で入力。蓄積結果はスペックルチャート（散布図）で確認。
- **「インタビュー方式」のプレー入力**: 打球発生時は質問形式のポップアップで順に選択。ただし「Out/Safe」の2大分類しかなく選択肢のスクロールが長い点が「雑然として遅い」と批判されている（Chalk & Clay）。
- **フルベースランナー制御**: 走者ごとに盗塁・牽制死・パスボール等を個別操作。
- **多段アンドゥ/リドゥ**: 「試合の最初のプレーまで」何段でも遡れる完全なUndo/Redo（[公式機能ページ](https://iscoresports.com/baseball/)）。
- スクリーンショット: http://cdn.iscoresports.com/website/baseball/images/sample/scorecard.jpg ／ http://cdn.iscoresports.com/website/baseball/images/multidevice.png

### 1.3 スコアラー（日本・本格スコアブックアプリ）
- **段階的選択方式**: セカンドゴロなら「ヒッティング」→「セカンド」→「ゴロ」→「打者アウト(4-3)」とボタンを順に押す設計（[公式ヘルプ](https://bbscorer.com/help/welcome.html)）。
- **走者ボタン「1」「2」「3」**: タップで進塁操作、**長押しで盗塁成功/失敗・牽制などのオプション表示**（タップと長押しの使い分けが特徴的）。
- **「戻る」ボタンで最大10操作までアンドゥ**、複雑な修正は「プレーリスト」画面で個別編集。試合終了後の選手交代修正も可能。
- スコアシートはピンチ操作で拡大縮小でき、紙のスコアブックと同書式。

### 1.4 一球速報.com / EasyScore（日本・アマチュア公式記録系）
- Omyu Technologyの無料入力アプリ**EasyScore**で、スマホ1台から1球ごとのデータを入力→そのまま一球速報.comでWeb配信される仕組み。紙のスコアブックと同じ書式で電子保存でき、少人数で大会記録を運用できる点が売り（[Omyu Technology](https://www.omyutech.com/easy-score/)、[一球速報.com アマチュア野球](https://baseball.omyutech.com/HomePageMain.action?catalog=H)、[配信員ガイドPDF](https://www.omyutech.com/wp-content/uploads/GuideLine-for-Scorer.pdf)）。
- 高校野球・大学野球の連盟公式速報で広く採用されており、「入力＝配信＝記録」の一元化の実例。

### 1.5 スポナビ野球速報（日本・閲覧側UIの定番）
入力ではなく表示側だが、1球データの「見せ方」の完成形として参考価値が高い（[公式ヘルプ: 試合詳細ページの見方](https://support.yahoo-net.jp/SccSports/s/article/H000009541)）。
- **6アイコン切替のビジュアル枠**: ①ランナー（走者状況+打球方向）②配球（コース図、同一コースは重ね表示）③ポジション図 ④条件別成績（直接対決/直近成績）⑤投球データ（球速・球種）⑥打撃データ（コース別打率・打球方向割合）。
- **配球スコープの記号体系**: 捕手視点のゾーン図に「番号=球順、記号=球種（ストレート=F等）、色=結果」をプロット（[PC版ヘルプ](https://support.yahoo-net.jp/PccSports/s/article/H000006035)）。
- **打球方向図の線種コード**: 黒線=アウト/赤線=出塁、弧線=フライ/波線=ゴロ/直線=ライナー。
- 2026年2月に速報画面へ投球・打撃データを追加（[LINEヤフー プレスリリース](https://www.lycorp.co.jp/ja/news/release/020134/)）。

---

## 2. 入力を高速化する工夫（パターン集）

| パターン | 実例 | 出典 |
|---|---|---|
| **頻出操作の常時表示化**（プログレッシブ・ディスクロージャー） | GameChanger 2025刷新: ボール/ストライク/ファウル/アンドゥをバーに常時表示、低頻度結果のみメニュー内 | [GC公式ブログ](https://gc.com/post/new-scoring-experience-for-gamechanger-baseball-softball) |
| **頻出イベントの1タップ入力** | iScore: 通常投球は画面下部ボタン1タップ | [BtBSレビュー](https://www.beyondtheboxscore.com/2010/8/10/1615326/software-review-espn-iscore) |
| **カウント・打者交代の自動進行** | GameChanger: 3ストライク→自動三振、4ボール→自動四球で次打者へ | GCヘルプ |
| **段階的ガイド付きポップアップ**（記録知識不要） | GameChanger のステップ式ポップアップ、iScoreの「インタビュー方式」 | Chalk & Clay |
| **ドラッグ&ドロップによる空間入力** | GameChanger: 野手を打球位置へドラッグ / iScore: 球速インジケーターをドラッグ | GCヘルプ / BtBS |
| **多段アンドゥ/リドゥ** | iScore: 試合開始まで無制限 / スコアラー: 10段 / GameChanger: バー上にUndo+Redo | 各公式 |
| **事後編集（追いつき運用）** | GameChangerのPlaysリスト編集、スコアラーのプレーリスト編集 — 試合進行を止めずに後で修正 | 各公式ヘルプ |
| **長押しでサブメニュー**（タップ数削減） | スコアラー: 走者ボタン長押しで盗塁/牽制オプション | bbscorer.com |
| **練習モード** | GameChanger: 本番前にスコアリング練習ができる | gc.com |
| **入力粒度の選択制** | iScore: 球種・球速・コースの記録はオプション。省略時は1タップ運用に縮退 | BtBS |

**アンチパターン**（Chalk & Clayの比較より）: iScoreの「Out/Safeの2分類の下に大量の選択肢を並べてスクロールさせる」構成は入力遅延の主因と批判。分類階層は「結果の種類ベース」で浅く保つのが良い。また旧GameChangerの「プレー編集不可」も減点要素だった（現在は解消）→ **アンドゥと事後編集は必須要件**。

---

## 3. 分析画面のモダンな見せ方

### 3.1 Baseball Savant（無料・業界標準の可視化リファレンス）
[Visualsページ](https://baseballsavant.mlb.com/visuals) に可視化ツール群が集約されている:
- **Pitch Highlighter**: コース図とスプレーチャートを粒度細かくインタラクティブに絞り込み（[URL](https://baseballsavant.mlb.com/visuals/statcast-pitch-highlighter)）
- **Texture Heatmap**: 天気図に着想を得て、球種ごとに異なるテクスチャで重ね描きするヒートマップ（[URL](https://baseballsavant.mlb.com/visuals/texture-heatmap)）
- **ゾーンヒートマップ**: 投手左右・打者左右・投球結果・打席結果・球種グループでフィルタ可能
- **Illustrator**: 任意データからカスタム可視化を作成
- **3D Pitch** (`/visuals/pitch3d`)・**Gamefeed**（ライブ一球速報+可視化）・**Statcast Field Visualizer**・**Pitch Arsenal Stats**（球種別成績を投手/打者/チームでソート、[URL](https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats)）

### 3.2 TruMedia（MLB球団・メディア向け）
- **ヒートマップの設定軸**: Stat（表示指標）/ Perspective（捕手視点⇔投手視点の反転）/ Spectrum（配色）/ Background（打者シルエットのON/OFF）の4メニューで構成（[ヘルプ](https://baseball.help.trumedianetworks.com/baseball/heat-maps)）。
- **スプリットの重ね掛け**: 任意のレポートに2つ以上のスプリット（対左/対右×カウント別など）を適用でき、フィルタ+グラフィックと組み合わせて対戦マトリクス的な分析を実現（[TruMedia Tools](https://baseball.help.trumedianetworks.com/baseball/trumedia-tools)）。
- **カスタムレポートビルダー**: 必要な指標だけのレポートを自作。1球ごとの映像とデータ連携が前提設計。

### 3.3 Synergy Sports（映像×データ検索）
- **Single Game View + Multi-Game Visualizations**の2層構成。前夜の試合の全投球をチーム/イニング/選手等でフィルタし、**ピッチチャート・スプレーチャート・データグリッド**のどこからでも該当映像を再生（[ABCA記事](https://abca.org/magazine/2018-4_July_August/The_Hot_Corner_Synergy_Sports_Technology.aspx)）。
- 分析で見つけた傾向を**動画プレイリスト化→NET Editorで編集→選手のiPad（Mobile Player App）へ配信**というワークフローが特徴。

### 3.4 6-4-3 Charts（大学野球向けアナリティクスの代表例）
- **NCAA D1の大学野球・ソフトボールが主要ユーザー**。Synergyの映像・データとTrackManデータを統合し、「ゾーンイラスト・スプレーチャート・ヒートマップ・投球シーケンス分析・キャッチャーフレーミング分析・カスタム統計レポート（テンプレート10種以上）」を提供（[643 Synergy](https://643charts.com/643-synergy/)）。
- 差別化要素は「**ほぼ全ての可視化・チャートから対応映像へ直接ジャンプできる**」こと。
- スクリーンショット例: `643charts.com/wp-content/uploads/Zone-Illustrations.gif`、`643charts.com/wp-content/uploads/643-Synergy-Heatmaps-1.gif`、`643charts.com/wp-content/uploads/2023/05/643-Synergy-Pitch-Highlighter-Stat-Table.png`、`643charts.com/wp-content/uploads/643-Synergy-Defense.png`

### 3.5 Rapsodo Cloud / TrackMan Portal（計測機器系ダッシュボード）
- **Rapsodo**: 投球直後に球速・回転数・回転方向・ジャイロ角・縦横変化量・リリースデータ・ストライクゾーンプロットをダッシュボード表示。**ムーブメントプロットは「無回転想定の軌道=破線」と「実際の軌道=実線」を重ね、1インチ刻みの偏差マーカー**で変化量を直感化（[Break Profile解説](https://rapsodo.com/blogs/baseball/understanding-rapsodo-pitching-data-break-profile-introduction)）。単/複数セッションの自動生成レポート、クラウドでの経年履歴（[PRO 2.0](https://rapsodo.com/products/pro-2-ball-flight-monitor)）。
- **TrackMan Portal**: 過去セッションのハブ。**カスタマイズ可能なダッシュボード**でリアルタイムの1球フィードバック、3D投球ビュー、映像連携、インタラクティブな投球/打撃レポート（[Practice Software](https://www.trackman.com/baseball/Portable-B1/software)）。

### 3.6 キューステ！（ライブリッツ・日本の高校/大学/アマ向け）
- 「ボタンをクリック・選択肢から選ぶだけ」の直感操作でスコア入力→成績自動集計。**入力スコアとアップロードした試合映像が自動連携**し、1球・1打席ごとにデータ+映像で振り返り（[Timely! WEB記事](https://timely-web.jp/article/4294/)、[導入事例](https://ama.sports-station.jp/case/)）。
- **検索条件**: 投打左右・投球コース・球種・ボールカウント・結果・走者状況などで横断検索。打者はコース別課題分析、投手は球種×コース別分析。「三振のみ」「本塁打のみ」など結果別の映像再生も可能。
- 監督・コーチ・選手・マネージャーがスマホ/タブレット/PCから閲覧するマルチデバイス設計。ミズノMA-Q（ボール回転計測）との連携もある（[プレスリリース](https://prtimes.jp/main/html/rd/p/000000020.000032744.html)）。
- 日本の大学野球向けではほかに **NEXT BASE（動画×トラッキング分析、BACS）**（[nextbase.co.jp](https://nextbase.co.jp/en/service/)）、**データスタジアム Pitch Base（Charlyze入力の1球データ×映像検索）**（[datastadium.co.jp](https://datastadium.co.jp/service-detail/vUy-UgMQ)）、**スコアベース（チーム情報共有+分析）**（[scorebase.net](https://scorebase.net/)）が存在。

---

## 4. タブレット対応の実例

- **GameChanger**: スコアリング/配信用途では**横持ち（ランドスケープ）が最も広い視野を提供**するとして推奨。フィールド図を中央に、頻出操作を下部バーに集約するレイアウトはタブレット横持ちで特に有効（[App Store](https://apps.apple.com/us/app/gamechanger/id1308415878)、GC公式ブログ）。
- **iScore**: iPad/iPhone/Android対応。フィールドビュー+画面下部の結果ボタン構成で、下部ボタンは横持ちタブレットの**両手親指リーチ圏**に収まる（[公式](https://iscoresports.com/baseball/)、マルチデバイス画像: http://cdn.iscoresports.com/website/baseball/images/multidevice.png ）。
- **スコアラー**: スコアシートのピンチ拡大縮小などタブレット利用を想定した設計（[公式ヘルプ](https://bbscorer.com/help/welcome.html)）。
- **キューステ！**: 入力・閲覧ともスマホ/タブレット/PCマルチデバイス。
- **片手操作ゾーンに関する示唆**: 明示的に「片手操作ゾーン」を謳う野球アプリは確認できなかったが、GameChangerの刷新（頻出操作を画面下端の固定バーへ）と iScore の下部ボタン列は、事実上「親指リーチ圏に頻出操作を置く」設計。ベンチでの立ち運用を考えると、下端固定バー+中央フィールド図+右端（利き手側）に走者操作、という配置が実例から導ける定石。

---

## 5. 設計への示唆（まとめ）

1. **画面の基本形**: 「中央にフィールド/ダイヤモンド図＋捕手視点ゾーン図、下端に常時表示の結果ボタンバー（ボール/見逃し/空振り/ファウル/インプレー＋Undo/Redo）」が2025-26年時点の収斂形。低頻度イベント（振り逃げ、ボーク、打撃妨害等）はメニューに格納する。
2. **タップ数の目標値**: 通常投球=1タップ、コース付き投球=2タップ（ゾーンタップ→結果）、インプレー=3操作（結果選択→打球位置ドラッグ→確定）が実例ベースのベンチマーク。
3. **自動化**: カウント進行・打者交代・押し出し等のルール帰結は自動処理し、入力者には「起きたこと」だけ選ばせる。球種・球速はデフォルト値/直前値の引き継ぎ+省略可能なオプション入力とし、記録粒度をチーム側で選べるようにする。
4. **リカバリー**: 多段Undo/Redo＋プレーリストからの事後編集の両方を必須とする（旧GameChangerが編集不可で批判された教訓）。
5. **分析画面**: ①捕手視点ゾーンヒートマップ（視点反転・打者シルエットON/OFF・指標切替）②スプレーチャート（線種/色で打球種と結果をコード化）③球種×コース×カウントのスプリット重ね掛け ④配球シーケンス（番号+記号+色）—の4点セットが標準。可能なら映像リンクを全チャートに付ける（6-4-3 Charts/キューステの差別化点）。
6. **閲覧側**: スポナビ式「アイコン切替式ビジュアル枠（走者/配球/守備位置/条件別成績/投球データ/打撃データ）」は限られた画面で多情報を見せる優れたパターン。

## 主要参考URL一覧
- https://gc.com/post/new-scoring-experience-for-gamechanger-baseball-softball （GameChanger刷新、スクショあり）
- https://gc.com/app-features/scorekeeping
- https://chalkandclay.com/baseball-scorekeeping-apps/ （スコアアプリUI比較）
- https://iscoresports.com/baseball/
- https://www.beyondtheboxscore.com/2010/8/10/1615326/software-review-espn-iscore
- https://baseballsavant.mlb.com/visuals ／ https://baseballsavant.mlb.com/visuals/statcast-pitch-highlighter ／ https://baseballsavant.mlb.com/visuals/texture-heatmap
- https://baseball.help.trumedianetworks.com/baseball/heat-maps ／ https://baseball.help.trumedianetworks.com/baseball/trumedia-tools
- https://abca.org/magazine/2018-4_July_August/The_Hot_Corner_Synergy_Sports_Technology.aspx （Synergy）
- https://643charts.com/643-synergy/ （大学向け、スクショGIFあり）
- https://rapsodo.com/blogs/baseball/understanding-rapsodo-pitching-data-break-profile-introduction ／ https://rapsodo.com/products/pro-2-ball-flight-monitor
- https://www.trackman.com/baseball/Portable-B1/software
- https://support.yahoo-net.jp/SccSports/s/article/H000009541 （スポナビ画面の見方）／ https://support.yahoo-net.jp/PccSports/s/article/H000006035
- https://www.lycorp.co.jp/ja/news/release/020134/
- https://baseball.omyutech.com/HomePageMain.action?catalog=H ／ https://www.omyutech.com/easy-score/ ／ https://www.omyutech.com/wp-content/uploads/GuideLine-for-Scorer.pdf
- https://bbscorer.com/help/welcome.html （スコアラー）
- https://timely-web.jp/article/4294/ ／ https://ama.sports-station.jp/case/ （キューステ！）
- https://nextbase.co.jp/en/service/ ／ https://datastadium.co.jp/service-detail/vUy-UgMQ ／ https://scorebase.net/
