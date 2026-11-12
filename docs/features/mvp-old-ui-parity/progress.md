# 進捗: 旧 Baseball_Scoring 画面への操作感一致

## 2026-11-12 23:00 JST — ACK喪失E2Eの追従と残差

- `GameScreenAttemptRecovery.e2e.ts` の安全確認を可視Sheet導線へ、通常結果の保存を可視結果パッドへ追従させた。復元後に別Sheetが開いていてもEscapeで戻る。
- ただし同E2Eは再起動後の「同じ要求を再送」が**disabled**のままで、ACK 0件のままタイムアウトする。安全確認の`confirmed`が同期センターへ反映されない実画面の状態を次に特定する。ACK喪失・結果不明の部品単体（`GameScreenAttemptRecovery` のunit、`test_ordinary_ack_loss_e2e`）は別途維持する。
- フロント全件 **4134 passed**。

## 2026-11-12 22:35 JST — 通信断cold再起動・未送信2球・順序同期の実画面E2E通過

- `test_offline_recording_reentry_e2e` が **1 passed / 94.47秒**。production SWでオンライン開始→reload→完全断中→cold再起動→未送信2球→復帰→同原文順の2 POSTを実DBで確認した。断中はPOST 0件、復帰後の要求は保存済み原文とattemptのhashが一致した。
- 通過までに、実画面の次の欠陥を修正した。ローカル記録画面の見出し・状態文が `h-dvh` の記録画面の上に積まれ、保存操作がビューポート外になる問題（sr-onlyへ移動）、記録画面の縦スクロールと保存ボタンのsticky化、通常結果の保存がsr-onlyボタンではなく可視の結果パッドから行われること、ローカルボールカウントが折りたたみ内にしか無かった問題（常時DOMへ移動）。
- E2Eは安全確認Sheetを可視導線から開き、4項目を確認してから保存する。再接続後も同じ確認をやり直す。
- これで第3段階の「通信断・再起動・復帰後の同期」のうち、cold再起動と順序同期を実画面で確認した。ACK喪失・broker再起動・担当交代中の切断は別途。

## 2026-11-12 21:30 JST — 開始済み一覧の実ブラウザ確認とtenant照合headerの欠落を修正

- 実ブラウザでログイン→`/games/archive` を開き、2件のカード・状態バッジ・日時・試合ID・開始/成績/CSV導線を確認した。比較画像は `images/game-archive.png`。
- 最初の実画面確認で、`GET /games/archive` の200応答に `X-Pitchlog-Tenant-Match` / `X-Pitchlog-Tenant-Challenge` が付かず、フロントのtenant照合がCookie不確実としてセッションを破棄し、ログイン画面へ戻る**実欠陥**を検出した。`tenant_access._MATCH_OPERATIONS` に `game_archive_list` ほか成績・名簿・lineup memoryのtenant-bound操作を追加した。
- 再発防止として、`require_tenant_access` を使う全route（`/auth/*`を除く）が `_MATCH_OPERATIONS` に含まれることを `test_api_conventions.py` で検査する。実ブラウザ再確認ではヘッダー付与と一覧表示を確認した。
- これは「部品がある」だけでは見つからない、画面→正式API→実DBの接続確認で見つかった欠陥である。

## 2026-11-12 21:10 JST — 候補の深いリンク・安全確認・E2E追従

- 認証前の戻り先に `/games/archive`・`/stats/season`・`/games/:id/{stats,export,lineup}` を追加した。従来はすべて `/` へ閉じられ、開始済み一覧や成績へ直接開いたURLがログイン後に失われていた。
- 記録画面の「記録端末の安全確認」導線をデスクトップでも表示するようにした。従来は `lg:hidden` のモバイル専用で、デスクトップでは結果パッドを押すまで安全確認Sheetを開けなかった。E2Eも可視導線から4項目を確認してから保存する。
- 交代パネルに「その場で選手を登録」を接続した。`POST /players`（既存の正式API）で名簿へ登録し、交代原本文を再取得して登録済み選手から選ぶ。断中は登録導線を閉じ、登録済み選手の選択だけを残す。登録は交代の原子性と別の名簿操作であり、交代の成功表示とは分離している。
- 旧画面E2Eの表示文言を現行UIへ追従させた（「新しい試合」「サーバー確認済み」）。開始直後のv3 zero readは409を返し得るため、初球UIのrosterは画面で選択した実rosterから渡し、開始readの成功を保存証拠にしない。
- 実画面の通常3球E2Eは **1 passed / 33.7秒**（最初のケース）。四球ケースは開始直後の同期センター再取得待ちが5分でタイムアウトし、製品の四球保存まで到達していない。テストハーネスの待機条件を次に直す。
- `base-allowlist.json` の `_BindingAuthority._call` 署名へ実行時の `register_d1less` を反映し、既知赤 `test_allowed_repository_symbol_signatures_match_runtime` を解消した。
- フロント全件・バックエンド対象の再実行はこの節の後で行う。

## 2026-11-12 19:20 JST — 開始済み試合のサーバー一覧APIとアーカイブ画面

- `GET /games/archive` を追加した。準備中・進行中・終了を、状態ごとに閉じた repository operation 3件で読み、日時・IDの降順で1ページへ統合する。tenant条件・trashed/hidden除外・keyset cursor・limit上限は既存の試合一覧と同じ。
- フロントに `GameArchiveScreen` と `/games/archive` を追加した。状態バッジ、チーム名、日時、試合ID、開始/再開/追記・再開、閲覧、成績、CSV、状態フィルタ、ページ内検索、ページングを表示する。StartScreen・上部nav・`/games` から導線を追加した。
- 契約: `repository-contract.json` を revision 38→39、`base-allowlist.json` を 53→54 へ更新し、3 token と `_game_archive_list_statement` の許可symbol/fixtureを追加した。**tenant-boundary の正式受理（base-allowlist 履歴・snapshot・承認）は未実施**であり、受理済みとは扱わない。
- 回帰: フロント全件 **4125 passed**（216 files）。backend 対象 **288 passed / 2 failed**（失敗は既存の `test_allowed_repository_symbol_signatures_match_runtime` と `test_stage_a_function_registration_matches_exact_asset_and_retains_rg1`。HEADでも同じ失敗を確認）。新規 `test_game_archive_read_boundary.py` **11 passed**。
- 残: archive API の実DB/実画面E2E、tenant-boundary 7.7 受理、authz catalog の再検査。

## 2026-11-12 18:45 JST — 付加結果の走者前提と試験を整理

- PB/WPは走者がいる場合だけ有効化し、走者観測シートで実結果を確認した後、ボール・見逃し・空振り・ファウルを選ぶと同一プレイへ付加する。走者なしのPB/WPはdomainが成立させないため、UIでも無効にした。ボークも走者ありのみ。
- 妨害は既存の妨害観測へ接続し、打撃妨害の保存をunitで確認。
- 回帰: フロント全件 **4113 passed**。
- 残テスト債務: `GameScreenRunnerOperations.e2e.ts` は旧フォームの `runner-operation-enable` を前提にしており、新しい走者シートへ未更新。実画面のPB/WP/ボークは既存runner event E2Eの更新後に再測する。

## 2026-11-12 18:30 JST — 付加結果（PB/WP/ボーク/妨害）を既存観測へ接続

- 結果パッドの「付加結果」を有効化した。PB/WPは走者観測シートで実結果を確認し、その後ボール・見逃し・空振り・ファウルを選ぶと、既存の `prepareRunnerEvent` へ `primaryResultId` を合わせて送る。ボーク/時計違反は非投球イベントとして送る。
- 打撃妨害・守備妨害・走塁妨害は既存の `GameScreenInterferenceObservation` へ接続した。新しい計算・保存経路は追加していない。
- 付加結果の選択中は、打球結果・三振詳細・四死球・昇格する四球/三振を無効化し、解除ボタンで戻せるようにした。
- 回帰: `LegacyResultPad.spec.ts` 8件、`GameScreenOrdinaryPitch.lifecycle.spec.ts` のPBシート・打撃妨害保存を含む **4111 passed**（全件は接続前回実行、追加分は対象試験で確認）。

## 2026-11-12 18:00 JST — スタメン・試合開始を旧テーブル構成へ変更

- `GameScreenStart` を、旧 `LineupScreen mode="new"` に近い2カラムのスタメン表へ変更した。各チームに打順・守備位置・背番号・氏名・左右の表と、右側に名簿一覧を表示する。
- 既存の開始入力ID（`start-{side}-{index}-player` / `-position`）と、端末登録・開始要求の保存・POST・応答復元は維持した。選手の `bats` はAPI値、未提供時は「—」。
- 回帰 **4109 passed**（GameScreenStart/StartHostを含む）。

## 2026-11-12 09:25 JST — 最終E2E再実行

- 試合一覧の「新しい試合」への文言変更に合わせてE2E補助を更新し、通常3球の実画面E2Eを再実行した。**1 passed / 90.30秒**。可視の球種チップ・ストライクゾーン・結果ボタン、同期POST 200、実DBの件数・d1/d2・結果キー照合は維持。
- フロント全件 **4109 passed**、`vue-tsc`・eslint・`pnpm build` 成功。

## 2026-11-12 08:45 JST — 試合一覧を旧カード構成へ変更

- `/games` の試合一覧を、旧 `GameListScreen` に近いカード一覧へ変更した。試合ごとの状態バッジ、試合ラベル、閲覧入口、再開（未提供）、検索トグル、ページングを表示する。通信・端末の前提は折りたたみへ移した。
- 既存の準備中試合一覧API・認証境界・ページング・キュー保持は変更していない。開始済み試合のサーバー一覧APIは未接続のため、現時点では準備中試合だけを表示する。
- 回帰 **115 passed**（router/GameScreenEntry）。

## 2026-11-12 08:35 JST — 独立レビューP1の是正

- 独立レビュー（P0なし・P1 6件）を反映した。
- 三振詳細は **lineup-prefix かつ2ストライク以上**のときだけ有効にし、v2の可視パッドがv2 preparerの拒否する三振結果を送らないようにした。
- `save()` に最終適格性ガード（四球/死球の次打者未選択、三振結果の文脈・カウント）を追加し、保存成功後に `resultId` をボールへ戻すことで、sr-onlyフォールバックからの古い三振結果の再送を防いだ。
- 全画面スタメンは、**現在の打順**と**開始時の守備位置・名簿**を区別して表示し、v3以外の読みでは交代フォームを開かない（v2/startedの誤用防止）。戻り先も読みの種類に応じてv3/v2/開始時を保持する。tenant IDの一致を表示前に確認する。
- 過去訂正の `suspended` を親の入力停止と合成した。名簿の非守備選手を一律DHと表示しない。
- 独立レビューのP1-5（型検査）はテストfixtureの型付けで解消。P1-6の未追跡`test_manual_app.py`はコミットしない。
- フロント全件 **4107 passed**、`vue-tsc`成功。

## 2026-11-12 08:15 JST — 攻守交代と過去訂正の入口を確認

- 可視の「見逃し」ボタンだけで9球（3人連続三振）を保存し、**1回表 0アウト → 1回裏 0アウト**への攻守交代を実画面で確認した。各同期POSTは200。投球結果の詳細は既存artifactが決定し、画面は状態を再計算しない。
- 2ストライク未満は「三振詳細」と三振結果を無効化した。0ストライクで三振結果を送ると保存が成立しないため、野球のカウントと旧画面の適格性に合わせた。
- 記録画面メニューの「過去の訂正」を既存 `GameScreenPastCorrectionProduct` へ接続した。`lineup-prefix` の現在readがあるときだけ開き、保存後は記録画面を再取得する。
- 回帰: `GameScreenOrdinaryPitch.lifecycle.spec.ts` に可視「見逃し」9球で1回裏へ変わる試験、`LegacyResultPad.spec.ts` に三振詳細の2ストライク条件を追加。フロント全件 **4107 passed**。
- 実画面画像: `/tmp/opencode/new-half-change.png`（1回裏・0アウト）。

## 2026-11-12 08:00 JST — 全画面の選手交代（スタメン確認）を追加

- 旧 `LineupScreen mode="change"` の構成に合わせ、`/games/:gameId/lineup` に **全画面の選手交代画面** を追加した。先攻/後攻の2カラムに、打順・守備位置・背番号・氏名・左右と、右側の名簿一覧を表示する。
- 記録画面の下部「交代」は、従来の選択シートではなくこの全画面へ遷移する。画面下部の「選手交代を記録」から既存の `GameScreenSubstitutionProduct` をシートで開き、投手交代・代打・守備変更を既存の同期経路で記録する。
- 読み取りは v3 → v2 → 開始済み詳細の順にフォールバックし、現在の `lineup` があれば打順の現在値を優先する。名簿は `roster.teams` と `/players` の表示名を突合する。
- 実画面確認: 新規試合を開始し、可視ボタンで1球保存（POST 200）した後 `/games/{id}/lineup` を開き、両チーム18行と名簿、交代シートの操作候補（投手交代・代打・守備変更）を確認した。
- 残差: 旧画面の表は行ごとのインライン編集（守備位置・選手の直接変更）だが、PitchLogは現在値の表示＋交代フォーム。行から対象選手をプリセットする操作は次の接続で追加する。初球前の `undo-prefix-v1` 読みは409、初球保存後は200だった。

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

- `images/comparison-normal.png`（通常時）
- `images/comparison-runner.png`（一塁走者あり）
- `images/comparison-substitution.png`（交代入口）
- `images/record-ipad.png`（iPad 幅）
- `images/record-phone.png`（iPhone 幅）
- `images/record-lineup.png`（全画面の選手交代）
- `images/record-half-change.png`（1回裏へ攻守交代）
- `images/game-list.png`（試合一覧カード）
- 元画像は `/tmp/opencode/` 配下にも残している（旧: `old-game-*.png`、PitchLog: `new-record-*.png`）。

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
