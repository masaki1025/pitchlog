# 進捗: 旧 Baseball_Scoring 画面への操作感一致

## 2026-11-12 01:45 JST — 記録画面1枚を旧 3 ペイン構成へ置換

### 固定した基準

- 旧リポジトリ: `/home/ymdms/projects/Baseball_Scoring`、固定 HEAD **`dd03160`**。
- 旧画面の確認方法: 旧リポジトリの mock モード (`VITE_MOCK=1`) を別ポートで起動し、`1440×900` / `1024×768` / `390×844` で実画面を取得した。
- 旧 `GameScreen.tsx` の構成を基準に、ヘッダー（スコア・回表裏・B/S/O・打者・投手・走者）、左ペイン（構え 5×5・球速）、中央（ストライクゾーン・球種チップ）、右ペイン（結果パッド）、下部バー（1球戻す・直前修正・牽制・作戦・交代・メニュー）を Vue で再実装した。

### 実装したもの

- `GameScreenOrdinaryPitch.vue` を旧 3 ペイン構成へ変更。既存の Controller/Provider/耐久キュー/ACK/記録権/認可はそのまま接続し、別の計算・保存経路は追加していない。
- `StanceGrid.vue`（25分割・捕手/投手後方視点）、`SpeedPad.vue`（直前球速中心の20候補・未計測・3桁テンキー）、`RunnerDiamond.vue`、`CountDisplay.vue`、`LegacyResultPad.vue`、`RecordBottomBar.vue`、`Sheet.vue`、`FieldDiagram.vue` を追加。
- 旧の結果パッドに合わせ、見逃し/空振り/ファール/ボール、打球結果5件+全打球、三振詳細、四死球を配置。2ストライクの見逃し/空振りは三振、3ボールのボールは四球として次打者確認へ進む。
- 打球結果では既存の `GameScreenBattedHitObservation` を右ペインに表示し、打球位置をフィールド図から入力できるようにした。安全確認・未観測・走者到達の既存入力は維持。
- 下部バーから取消（既存 Undo）、交代（既存 Substitution）、終了・再開（既存 Lifecycle）、同期センターをシートで開く。未接続の直前修正・作戦・タイブレーク・過去訂正は「未接続」と明示して無効化した。
- 記録端末の4確認は旧画面のヘッダーに常設せず、初回の安全確認シートへ統合した。未確認のまま結果を押すと安全確認シートを開く。
- 画面幅 `lg` 以上は旧と同じ3ペイン、`lg` 未満は旧と同じく上部集約ヘッダー＋縦積みにした。iPhone 幅では既定でヘッダーを折りたたみ、ストライクゾーンを最初に表示する。
- 旧画面の「サーバーから再取得」に相当する入口を同期センターへ置き、開始後の実 prefix 再取得を画面から行えるようにした。

### 実 API/実 DB の確認（テスト所有の一時環境）

`test_ordinary_screen_e2e.py` の通常3球シナリオを、画面の可視ボタンだけで実行するよう更新した。

- 新規試合作成 → 端末登録 → スタメン入力 → 試合開始（HTTP 200）。
- 可視の球種チップ、ストライクゾーン、結果ボタンから **ボール3球** を保存。各 `POST /api/games/{id}/sync/events` は **200**。
- 4球目は「四球」へ昇格し、次打者確認シートで次打者を選択して保存。**200**。
- 保存後、ヘッダーは `2番`・`1塁走者` を表示し、`/started` は `lineup-prefix` の長さ 1→2→3→4 を返した。
- ブラウザ内 `fetch` で投球を代行した証拠は使っていない。可視の `[data-result-id]`・`[data-pitch-type]`・StrikeZone のタップを使った。
- コード凍結後の再実行: `test_screen_three_ordinary_pitches_https_save_replay_reload[ordinary]` **1 passed / 91.30秒**。同期 POST 200、`play_rows` / `operation_events` / `event_slots` / 冪等台帳の件数一致、d1/d2の連番、batting_result_key の並びを実DBで照合した。

### 比較画像

- `/tmp/opencode/pitchlog-comparison-normal.png`（通常時）
- `/tmp/opencode/pitchlog-comparison-runner.png`（一塁走者あり）
- `/tmp/opencode/pitchlog-comparison-substitution.png`（交代入口）
- 個別画像: `/tmp/opencode/new-record-wide.png`、`new-record-wide-runner.png`、`new-record-wide-substitution.png`、`new-record-ipad.png`、`new-record-phone.png`
- 旧側画像: `/tmp/opencode/old-game-wide.png`、`old-game-runner.png`、`old-game-substitution.png`

### 残る差（隠さない）

| 項目 | 現状 | 次の対応 |
| --- | --- | --- |
| 交代画面 | 旧は全画面のスタメン変更（両チームの打順・守備位置・選手を一覧編集）。PitchLog は「正式な選手交代 / 臨時代走」の選択シートから既存の交代フォームを開く | 旧 `LineupScreen mode="change"` の全画面編集を移植し、既存の交代 API へ接続する |
| 付加結果・プレス・その他詳細 | 旧は PB/WP/妨害/ボーク/プレスを選択可能。PitchLog は未接続として無効表示 | 既存の runner event / non-play 経路へ接続する |
| 直前修正・作戦・タイブレーク・過去訂正 | 下部バー/メニューに入口はあるが「未接続」で無効 | 既存 Undo/P3/作戦/タイブレークの各製品部品をシートへ接続する |
| 打球位置 | 右ペインの確認フォーム内のフィールド図で入力。旧は中央ペインのフィールド図に入力し、捕球選手を図から選ぶ | 中央ペインの `FieldDiagram` へ移動し、観測フォームと双方向に接続する |
| 走者表示 | デスクトップはヘッダーの塁別チップ、モバイルは折りたたみ内のダイヤモンド。旧はヘッダーの走者ポップオーバー＋ダイヤモンド | ヘッダーの走者ポップオーバーを追加する |
| 開始直後の `/started` | 初球前の `projection=play-prefix-v3` 読みが 409 を返す場合がある。初球保存後は `lineup-prefix` を取得できる | 初球前読みの 409 原因を調査し、開始画面から記録画面への復元を安定させる |
| 7回/延長/タイブレーク | 未接続 | 既存 plan の残ステップで対応 |

### 検証

- フロント全件: **214 files / 4102 tests passed**（2026-11-12 01:44）。
- `vue-tsc --noEmit`・eslint（変更ファイル）成功。
- `LegacyResultPad.spec.ts` を追加し、犠打の状況適格性・走者なし野手選択・打球入力不可を検証。
- 旧 mock の比較画像と、テスト所有 DB の実画面画像を取得。
