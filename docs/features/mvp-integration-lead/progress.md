# 初回MVP 主担当引受・進捗台帳

## 2026-11-11 02:30 JST：試合操作の在庫を実画面証拠で分類

既存台帳・コード・spike・E2Eを突き合わせ、利用者操作の現在地を次へ固定する。**実画面実証済み**は実HTTPS/実ブラウザ/owned DBで保存・再取得まで確認したもの、**実装済み未接続**は計算核・受理・保存部品はあるが製品入口/実画面が未接続のもの、**未実装**は製品経路がないもの、**意味判断待ち**はPO回答なしに確定しないもの。既存E2Eの前HEAD証拠は、今回差分がその経路を変更していない限り状態を維持する。今回再測したのは投手交代（97.17秒）、終了条件3シナリオ（1491.83秒）、9回フルゲーム（実行中）である。

| 操作 | 状態 | 根拠・停止点 |
| --- | --- | --- |
| 投球・打席 | 一部実画面実証済み | 初球は`GameScreenFirstBall`でUI保存。9回163球の`GameScreenFullGame`は**ブラウザ内fetch**で投球しており、製品の通常投球UIによる連続記録ではない（下記2026-11-11 20:45）。通常投球UIは打席終了後の次球準備で停止する |
| 打球（単打/長打/本塁打/犠打/犠飛/併殺/失策/FC） | 実画面実証済み | `test_batted_operations_batch_screen_e2e` 59プレイ、`test_batted_hits_screen_e2e`、`test_batted_out_screen_e2e` |
| 走者アウト（牽制/盗塁死/振り逃げ併殺） | 実画面実証済み | `test_runner_operations_screen_e2e`（投手・捕手牽制、caught-stealing、strikeout-double-play） |
| 走塁（盗塁/WP/PB/ボーク） | 実画面実証済み | 同runner operations（非投球盗塁、wild-pitch、passed-ball、balk） |
| 妨害7分岐 | 実画面実証済み | `test_interference_screen_e2e` INT-01〜07、5試合 |
| 交代（投手） | 実画面実証済み | `test_substitution_product_screen_e2e` **1 passed / 95.70秒**（2026-11-11再測） |
| 交代（代打/代走/守備変更） | 一部実画面実証済み | domain/HTTP/payloadは4種。**守備変更の実画面E2Eは通過**（1 passed / 82.37秒、fielding 6更新）。**代打のHTTP縦断は通過**（投手→代打、d3=5、receipt 2件）。捕手を代打にすると捕手位置が空になりserverが`continuationLineup=null`で拒否。代走は未接続 |
| 選手のその場登録 | 実装済み未接続 | backendの`player_registration`受理・一時ID mappingはある。画面は「登録はまだ行われません」で、参加登録API/UIが未接続 |
| 取消 | 実画面実証済み | `test_undo_product_screen_e2e`、ACK喪失→新attempt |
| 過去訂正 | 実画面実証済み | `test_p3_product_screen_e2e`、26球→P3→27球目→CSV |
| 9回 | HTTP縦断済み・UI連続記録は未成立 | `test_full_game_screen_e2e` **1 passed / 1653.21秒**、163球・normal-end/v1。ただし投球は`recordRealPitch`のブラウザ内fetchで、製品UIではない。**5秒応答目標も未達**（最大10736ms、163/163が5秒超） |
| 7回 | 実装済み未接続 | 規則schema/domainは規定回を可変。`resolve_stage_a_rule`が固定5組（すべて9回）で、大会割当/上書き/規則管理UIが未接続 |
| コールド | 実画面実証済み | 新`test_end_conditions_screen_e2e`のcold-end（9回・7点差7回、49 play_input + 終了宣言）。**1 passed / 1491.83秒** |
| 引き分け | 実画面実証済み | 同E2Eのlimit-draw（9回同点・延長上限9、54 play_input + 終了宣言）。**同日再測で通過** |
| 延長 | 実装済み未接続（到達不能） | 固定5組で延長上限>9は`game_official`だけだが、同規則は10回タイブレーク発動。タイブレーク開始が未接続のため10回以降へ進めない。`game_other`は上限9でlimit-draw |
| タイブレーク | 意味判断待ち | 純状態効果step1（`174fb346`）のみ。画面の「配置と回を記録」はdisabled。実画面では10回の発動ロック（54 play_input、`in_progress`）まで確認。TB-P1〜P3未回答 |
| 終了・再開・再終了 | 実画面実証済み | `test_game_lifecycle_product_screen_e2e`、P3後26球lifecycle |
| 入力ロックの理由表示 | 実装・単体試験済み | `GameScreenOrdinaryPitch`に`ordinary-pitch-locked`を追加。終了条件/タイブレーク開始の理由を表示。`ordinaryPitchLock.spec.ts` 3 passed |
| 通信断継続・再起動・再送 | 実画面実証済み | `GameScreenOfflineRecording`、`GameScreenAttemptRecovery`、lifecycle ACK喪失。担当交代は別 |
| 担当交代（記録権引き継ぎ） | 未実装 | 製品API/画面がない。server側の世代・退避部品だけではFR-013の通常/緊急引き継ぎを満たさない |
| 成績27項目 | 実画面実証済み | 新`test_stats_screen_e2e` **1 passed / 139.35秒**。公式モードで打撃18列＋投手13列−選手/チーム4列＝**27項目**、成績CSV 5262 bytesを実ダウンロード |
| 毎球CSV・成績CSV | 実画面実証済み | `test_play_export_screen_e2e`、P3 CSV、ゲーム/シーズン成績CSV |

### 2026-11-12 23:10 候補引渡し資料

- 固定HEAD `586abd72` の候補URL・ログイン方法・操作手順・実証・未達を `candidate-handoff-2026-11-12.md` にまとめた。
- 候補環境はテスト所有の使い捨てであり、製品環境・実機・バックアップ復旧の証拠ではない。

### 2026-11-13 08:10 再レビューP1/P2の是正

- Codex再レビュー（`1989001a..90c1def4`、P0なし）の指摘2件を是正した。
  - **P1**: `retry()` が照会済みattemptを局所変数へ取り込んだ後、資格読取の待機中に再照会が `unresolved` を返すと、局所変数の `skipRecovery` でPOSTへ進み得た。POST直前に `#inspectionResult` と `#recovery.attemptId` を再検査し、未確定・不一致なら送らない。
  - **P2**: 打球語彙cacheの破棄が認証watchの `immediate` に依存し、同tenantの再表示でも毎回消え、フォーム非表示中の認証切替では残った。`noteBattedBallAuthKey` を導入し、認証キーが変わった時だけ一度破棄する（初回マウント・同tenant再表示では保持）。
- ACK喪失E2Eは是正後も **1 passed / 105.31秒**。

### 2026-11-13 08:10 タイブレーク候補の隔離前進

- 別worktree `feature/mvp-tiebreak-pipeline-20261113`（HEAD `20839a5e`、リモートpush済み）へ、タイブレーク開始の**artifact入口**と非play保存骨格を固定した。統合ブランチへは未マージ。
- 追加: `transitionTiebreakStartV1`（`publicApi.ts`、artifact再ビルド sha `7f6497cb...`）、payload/projection/execution/ports/bridge、`consume_nonplay_tiebreak_start` SQL、`tiebreak_start_write_receipts` migration/model、非play read SQLのフレーム/receipt照合、apply/prefix_path/transaction配線。
- 現時点の赤: P3/nonplayの既存body pin（`read_nonplay_history_page` 等）が統合ブランチ側で既に不一致。タイブレーク候補はこの正式資産pinを更新しないとbackendテスト収集まで到達しない。画面・DB E2E・成績/CSVは未接続。
- 次の順: ①非play/P3の既存body pinを正式受理点へ追随、②read SQLの実DB対向、③画面の「配置と回を記録」有効化、④start→次球→打球/走塁→交代→生還→次半回再配置→reload→成績/CSVのE2E。

### 2026-11-13 03:20 正式資産の現状（候補と受理を分離）

- `tests/test_check_tenant_boundary_bypass.py` は **570 failed / 1237 passed / 2 errors**。`base-allowlist.json` は `contract_revision:54` のままで、統合ブランチの新規関数・経路が7.7受理へ追随していない。単一のテスト修正では閉じず、`baseline_control.history` への前後識別値・凍結射影・承認の追記が必要。
- `test_sync_apply_product_supply.py` は3件赤。`catalog_after_revision` が現在の `ddl-elements.json` と一致せず、非play通常保存で変更した prepare/finish projection と旧batted参照fixtureの同時更新が必要。
- `test_batted_hit_product_declarations.py` / `test_batted_hit_storage_boundaries.py` は、意図的SQL変更へ固定値を追随して通過。
- 候補の機能証拠（ACK喪失E2E・55プレイE2E・終了再開）と、正式受理（7.7・全件CI）を混同しない。

### 2026-11-13 03:05 独立レビューP1/P2の是正

- Codex敵対レビュー（対象 `88652997`）の指摘3件を是正した。
  - **P1**: `retry_allowed` 後の再照会が `unresolved` になっても `#recovery` が残り、次の独立操作後に `skipRecovery` で未確定attemptを送り得た。回復許可を `{d1,d5,attemptId}` へ結び、`unresolved` で失効させ、送信直前にslotのd1/d5と一致を検査する。
  - **P2**: 停止解除時に未確認要求を自動再送していた。解除時は状態再読取までに留め、照会・再送を利用者操作から開始する。
  - **P2**: 打球語彙cacheに寿命・件数上限・認証切替時の破棄がなかった。5分TTL・8件上限・tenant/epoch変更時の全破棄を追加した。
- `test_attempt_recovery_screen_e2e` は是正後も **1 passed / 109.29秒**。P1の再現specとcacheのTTL/上限specを追加した。

### 2026-11-13 02:20 ACK喪失の照会・終結・再送を分離してE2E通過

- `test_attempt_recovery_screen_e2e` **1 passed / 103.46秒**。ack-lost/before-httpの両モードで、再起動→復元→安全確認→照会→再送→次球reloadを実画面・実DBで通過。
- 照会は保存POSTを送らず、旧本文/旧attemptで権威照会だけを行う。`retry_allowed` で次attemptを固定し、`unresolved` は結果確認中のまま再送しない。照会中の切断も注入し、保存POST 0件を確認。
- フロント全件 **4139 passed**。backend対象 **193 passed**。

### 2026-11-13 01:05 終了・再開・追加・再終了の機能通過（性能5秒は未達）

- 実画面の作成→開始→1球→終了→再開→2/3球→再終了→reloadの機能assertを通過。終了版v1→v2を確認。
- 最終の5秒性能assertは **7920ms** で失敗。NFR-002は未達のまま。

### 2026-11-13 00:35 55プレイ通しE2E通過

- `test_screen_nine_innings_batted_out_stats_and_csv` **1 passed / 636.91秒**。新規作成→開始→55プレイ（18半回、本塁打1＋凡打54）→終了宣言→reload→成績27項目→毎回ZIP/成績CSVまで実画面・実DBで照合。
- 打球観測フォームの再生成競合を、同一tenant/epochの語彙cacheで解消。終了宣言はメニュー→終了・再開Sheetの可視導線へ追従。証拠readはtenant照合header付き。
- フロント全件 **4135 passed**。backend対象 **281 passed**。

### 2026-11-12 23:00 ACK喪失E2Eの追従と残差

- ACK喪失E2Eの安全確認・通常結果保存を現行UIへ追従させたが、再起動後の再送ボタンがdisabledのままで未通過。原因は次に特定する。
- フロント全件 **4134 passed**。

### 2026-11-12 22:35 通信断cold再起動・未送信2球・順序同期の実画面E2E通過

- `test_offline_recording_reentry_e2e` **1 passed / 94.47秒**。production SW、完全断中、cold再起動、未送信2球、復帰後の同原文順2 POSTを実DBで確認。断中POST 0件。
- ローカル記録画面のレイアウト（h-dvhの上への見出し積み上げ、縦スクロール、保存ボタン、結果パッド、常時カウント）を修正した。
- 安全確認Sheetを可視導線から開くE2Eへ更新し、再接続後も再確認する。

### 2026-11-12 21:30 開始済み一覧の実ブラウザ確認とtenant照合header修正

- 実ブラウザで `/games/archive` の2カード・状態・日時・試合ID・導線を確認。画像 `docs/features/mvp-old-ui-parity/images/game-archive.png`。
- `GET /games/archive` がtenant照合headerを返さず、フロントがセッションを破棄してログインへ戻る実欠陥を検出。`_MATCH_OPERATIONS` へ `game_archive_list`・成績・名簿・lineup memoryを追加し、tenant-bound全routeの網羅試験を追加した。
- 再確認でヘッダー付与と一覧表示を確認した。

### 2026-11-12 21:10 候補の深いリンク・安全確認・E2E追従

- 認証前の戻り先へ `/games/archive`・`/stats/season`・`/games/:id/{stats,export,lineup}` を追加。開始済み一覧・成績への直接URLがログイン後に失われない。
- 記録画面の安全確認導線をデスクトップでも表示。E2Eは可視導線から4項目を確認して保存する。
- 交代パネルの「その場で選手を登録」を `POST /players` へ接続。断中は閉じる。交代の成功表示とは分離。
- 旧E2Eの「新しい試合」「サーバー確認済み」への文言追従、開始直後のv3 zero read 409を前提にしたroster受渡しへ変更。
- 通常3球E2Eの最初のケース **1 passed / 33.7秒**。四球ケースは同期センター再取得待ちのタイムアウトで未到達。
- `_BindingAuthority._call` のallowlist署名を実行時に一致させ、既知赤1件を解消。

### 2026-11-12 19:20 開始済み試合のサーバー一覧APIとアーカイブ画面

- `GET /games/archive` を追加。準備中・進行中・終了を状態別の閉じた operation 3件で読み、日時・ID降順の1ページへ統合する。tenant条件・可視性・keyset cursor・limit上限は既存一覧と同じ。
- `/games/archive` に状態バッジ、チーム名、日時、試合ID、開始/再開/追記・再開、閲覧、成績、CSV、状態フィルタ、ページ内検索、ページングを追加。StartScreen・nav・`/games` から導線を追加した。
- 契約は repository-contract 39 / base-allowlist 54 へ更新したが、**tenant-boundary の正式受理は未実施**。受理済みとは扱わない。
- フロント全件 **4125 passed**。backend 対象 **288 passed / 2 failed**（2件はHEADでも失敗する既存不整合）。新規 archive 境界試験 **11 passed**。

### 2026-11-12 18:45 付加結果の走者前提と試験を整理

- PB/WP/ボークは走者ありのみ有効。PB/WPは走者確認後に主結果を選ぶと同一プレイへ付加。打撃妨害の保存をunitで確認。
- フロント全件 **4113 passed**。旧runner operations E2Eは新シートへ未更新。

### 2026-11-12 18:30 付加結果PB/WP/ボーク/妨害を接続

- 結果パッドの付加結果を既存のrunner event/妨害観測へ接続。PB/WPは走者結果確認後に主結果を選び、`prepareRunnerEvent` へ送る。ボーク/時計違反は非投球イベント。新しい保存経路なし。
- 対象試験: `LegacyResultPad.spec.ts` 8件、PBシート・打撃妨害保存のlifecycle試験。

### 2026-11-12 18:00 スタメン・試合開始を旧テーブル構成へ変更

- 開始画面を2カラムの打順・守備・背番号・氏名・左右＋名簿の表へ変更。端末登録・開始要求の保存/POST/復元は維持。
- フロント全件 **4109 passed**。

### 2026-11-12 08:45 試合一覧を旧カード構成へ変更

- `/games` を状態バッジ・検索・ページング付きのカード一覧へ変更。開始済み試合のサーバー一覧APIは未接続のため準備中のみ。
- router/GameScreenEntry回帰 **115 passed**。

### 2026-11-12 08:35 旧画面UIの独立レビューP1を是正

- 三振結果をlineup-prefixかつ2ストライク以上に限定し、保存時の最終ガードと保存後の結果リセットを追加した。v2の可視パッドがv2で拒否される三振結果を送らない。
- 全画面スタメンは現在の打順と開始時の守備・名簿を区別し、v3以外では交代フォームを開かない。tenant一致確認、過去訂正のsuspended合成、DH表示の誤用も是正。
- フロント全件 **4107 passed**。P0なし、P1 6件はすべて解消または未追跡除外。

### 2026-11-12 08:15 攻守交代と過去訂正の入口を確認

- 可視の「見逃し」ボタンだけで9球（3人連続三振）を保存し、**1回表→1回裏**の攻守交代を実画面で確認。各POST 200。2ストライク未満の三振詳細は無効化した。
- メニューの「過去の訂正」を既存P3製品部品へ接続。フロント全件 **4107 passed**。
- 残差: 行ごとのインライン交代編集、初球前 `undo-prefix-v1` 409、付加結果/プレス/作戦/タイブレーク。

### 2026-11-12 08:00 全画面の選手交代（スタメン確認）を追加

- `/games/:gameId/lineup` を追加し、旧 `LineupScreen mode="change"` と同じ2カラムの打順・守備・背番号・氏名・左右・名簿を表示する。記録画面の「交代」はこの画面へ遷移し、既存の交代フォームをシートで開く。
- 実画面で1球保存（POST 200）後に両チーム18行・名簿・交代候補（投手交代/代打/守備変更）を確認。フロント全件 **4104 passed**。
- 残差: 行ごとのインライン編集と対象選手のプリセット、初球前の `undo-prefix-v1` 409。

### 2026-11-12 01:45 記録画面を旧 Baseball_Scoring の3ペイン構成へ置換

- 旧固定 HEAD `dd03160` の実画面（mock 起動）と現行を同じ状態で比較し、記録画面を旧 `GameScreen` のヘッダー・左ペイン（構え/球速）・中央（ストライクゾーン/球種）・右ペイン（結果パッド）・下部バーの構成へ置き換えた。詳細と比較画像は `docs/features/mvp-old-ui-parity/progress.md`。
- 可視の球種チップ・ストライクゾーン・結果ボタンから、テスト所有 DB の実試合へ**ボール3球と四球**を保存。同期 POST は各 **200**、保存後は打順2番・一塁走者を表示し、`/started` は `lineup-prefix` 長 1→4 を返した。ブラウザ内 fetch の代行は使っていない。コード凍結後の E2E は **1 passed / 91.30秒**。
- フロント全件 **4102 passed**。`vue-tsc`・eslint 成功。
- 未接続として残るもの: 旧の全画面スタメン変更（交代）、付加結果/プレス/その他詳細、直前修正/作戦/タイブレーク/過去訂正、中央ペインの打球位置入力、開始直後の `play-prefix-v3` 読取 409。台帳の表に明示した。

### 2026-11-11 23:30 開始画面を旧トップ構成へ合わせる

- 旧リポジトリ `dd03160:frontend/src/screens/StartScreen.tsx` を**仕様・見た目の参照**として、Vueの`StartScreen.vue`を追加した。チーム名ヘッダ、設定/使い方/ログアウト、「新しい試合」の大カード、チーム・選手／データ分析／試合一覧／データ入出力、比較グループ、最近の試合の構成を踏襲した。
- `/` は `StartScreen`、`/games` は試合一覧のまま。「新しい試合」は `/games?create=1` へ遷移し、新規作成フォームを直接開く（実ブラウザで確認）。
- 旧画面のうち分析ダッシュボード・個人カルテ・比較グループ・CSV取り込み・スコアカード・スタメン変更は未移植。比較グループは「共有分析は未提供」と明示し、動作するように見せていない。
- 回帰 **133 passed**、`vue-tsc`・eslint 通過。製品コードは旧Reactを依存にせず、Vueで再実装している。

### 2026-11-11 22:15 トップ画面を試合一覧へ変更

- トップ `/` が開発時目視比較専用の`StrikeZoneCompareHost`（カラースキーム/ストライクゾーン比較）になっており、ログイン後の製品入口として不適切だった。`/`を`GameScreenEntryHost`（試合一覧・新規作成）へ変更し、比較画面は`/design/strike-zone`へ移動した。
- ログイン後の既定戻り先を`/team`から`/`へ変更し、未認証の`/`は`/login?redirect=/`へ送る。`/team`への明示的な戻りは維持する。
- router/App/入口の回帰 **133 passed**。実ブラウザで `/` → ログイン → `/`（新規作成・試合navあり）を確認した。
- 実機用の一時保持環境（`backend/tests/db/test_manual_app.py`、未追跡）でログインとトップ描画を確認。製品環境の証拠ではない。

### 2026-11-11 21:15 非作者レビューP1の是正とドメイン検査の赤を解消

- レビュー `review-7bcc5f28-20261111` の **P1 1件**を採用。v3の`prepareLineupPrefix`が`observation.nextBatter`を消費していなかったため、四球・死球で未選択・別選手・別枠でも同一要求を作れていた。`response.value.participants`（唯一核が返す次打者）と`batterId`・`battingOrder`の両方を照合し、不一致は`OrdinaryPitchWireError`で拒否するよう修正した。画面の次打者候補も現打順の直後枠だけに限定した。
- 回帰: `GameScreenOrdinaryPitchProvider.spec.ts` に v3死球の「正しい確認=受理」「未選択/別選手/別枠=拒否」を追加。四球は同じ照合コードを通るが、v3 fixtureが0ボールのため3ボール状態の単体再現は未作成（実画面の3ボール→四球で別途確認）。
- **レビュー対象外で見つかった赤**: `tiebreakStart.ts` がドメイン検査の閉じた構文（条件式・正規表現・`String`・spread・number）に違反し、`pnpm build:domain` と全frontend試験5件が赤だった。手書きUUID検証・`formatDecimalInteger`・明示的なオブジェクト複写へ書き換え、`pnpm build:domain` は既存artifact SHA `b5656418...` を維持して成功。**frontend全213ファイル / 4097テスト passed**。
- **未解決**: 三振後停止の原因は未確定（レビュー指摘どおり、artifact単体では三振→次球が成功）。次はv3 controllerで三振→次球を実際に送る回帰と、通常UIで打席終了後・攻守交代後を含む1イニングの実画面E2Eを行う。

### 2026-11-11 20:45 通常球UIの連続記録停止点を特定

- 実画面E2Eで、初球（`GameScreenFirstBall`）→通常投球UI（`GameScreenOrdinaryPitch`）へ**ページ再読込なしで**引き継げることを確認した。初球保存のACK後、同じ画面に通常投球パネルが現れ、サーバー確認済み状態・履歴1件で入力できる。
- しかし**打席終了イベントの後、次の投球がPOSTされない**。三振を1球保存した後の次球で、`__pitchlogSubmitError` は `Error: 初球の正式計算が成立しませんでした`（`prepareLineupPrefix`、`head:2`）を返し、`waitForResponse` は30秒でタイムアウトした。1球目と三振のPOSTは200/受理、次球はPOST 0件。**製品UIは打席終了後に文脈（次打者・next d1）を更新できず、連続記録が止まる**。
- 四球は「3ボール→四球→次打者確認」の順でないと成立せず、`terminal-next-batter` は**lineup-prefixでも必須**だった。従来の`terminal`計算はlineup文脈で次打者選択を隠していたため、`GameScreenOrdinaryPitch.vue`で四球/死球は文脈に関係なく次打者確認を表示するよう修正した。既存4 spec **115 passed**。
- 四球の保存には`admin_vocabularies`の`batting-result.walk`が必要で、未投入では`play_rows`のFK違反→503（fail-closed、ACKなし）になる。テストfixtureで語彙を投入すれば、四球は受理され走者一塁・打順2・walks=1になった。
- 代走の実画面E2Eは、この**通常球UIの連続記録停止**に阻まれて未成立。代走パイプライン自体の拒否ではない（捕手以外の走者を作る前段で停止）。代打の画面E2Eも同じ理由で、以前の「捕手位置の空き」だけが原因ではない。
- 次は、保存ACK/再取得後に`nextPosition.d1`と次打者を製品UIへ反映する接続を直し、通常球UIだけで1イニングを連続記録できることを先に証明する。その上で代走・代打・タイブレークへ進む。

### 2026-11-11 18:30 TB-P1/P2/P3=A採用と純遷移核

- PO回答 **TB-P1=A / TB-P2=A / TB-P3=A** を採用。P1は記録者が規則適合配置を確認・確定する方式（自由配置ではない）、P2は半回開始時投手への失点帰属を維持し自責点計算はMVP対象外、P3は各半回に再配置する。
- `tiebreakStart.ts` に `transitionTiebreakStart` を追加。実選手ID（攻撃側の実出場者のみ、先頭打者・同一IDを拒否）、半回開始投手の責任固定、初回と次半回の再配置、二重配置/途中アウト/別規則の拒否を純対向で固定。`tiebreakStart.spec.ts` **5 passed**。
- 実装HEAD `489d3cbf`。計画は `docs/features/mvp-tiebreak-start-product/plan.md`。
- **未接続（step2/3）**: 既存正式operationRowsは`tiebreakActive=false`の初回だけで、P3の再配置（`tiebreakActive=true`の新半回）には新しい正式行/caseが必要。非play frameの保存形式（substitution frameの再利用か新fieldか）、新consume関数/ACL/registry、画面の確認UI、次球、成績/CSV、独立レビュー、実DB/実画面E2Eは未実施。**完成扱いにしない**。

### 2026-11-11 05:35 守備変更の実画面縦断を追加

- `test_defense_change_screen_e2e` は **1 passed / 82.37秒**。新規試合で1球保存後、控え選手213を遊撃手（position 6）へ守備変更し、**200/受理**、receipt 1件、current checkpointの`substitutionState.home.fielding['6']=213`を実DBで照合した。
- これで交代4種のうち**投手・守備変更が実画面通過**、**代打がHTTP通過**、代走が未接続。捕手を代打にする場合は捕手位置の補充が必要で、serverは`continuationLineup=null`のまま受理しない（別の意味判断・複合操作）。

### 2026-11-11 05:10 代打のHTTP縦断を追加

- `test_substitution_vertical_http` を投手交代→次球→**代打**へ拡張し、**1 passed / 91.43秒**。代打は `pinch-hitter`（side=away、現在打者・打順、控え選手212）で **受理**、D3=5、`substitution_write_receipts` 2件、次打者と`substitutionState.away.battingOrder[slot]`が212へ更新されたことを実DBで照合した。
- これで代打の**server/domain/保存**は成立。実画面の代打POSTが拒否される原因は、**先頭打者が捕手**であり、捕手を代打にすると`fielding['2']`が空になり、serverの`transitionSubstitutionV1`が`continuationLineup=null`で`afterContext`を返せないこと。**非捕手の代打はHTTPで成立**しており、画面E2Eは打順を進めるか、捕手以外を対象にする必要がある（捕手の代打＋捕手交代を同一操作で扱うかは別の意味判断）。
- 既存の投手交代画面E2Eは **1 passed / 97.17秒** を維持。

### 2026-11-11 04:40 公式成績27項目・成績CSVの実画面通過

- `test_stats_screen_e2e` は **1 passed / 139.35秒**。新規試合で7プレイ（本塁打1＋6アウト）を保存し、終了宣言後に `/games/{id}/stats` の公式モードを表示した。
- 実画面の表は **打撃18列 + 投手13列 − 選手/チーム4列 = 27項目**。`CSVダウンロード` は実ファイル **5262 bytes** を保存した。
- DBは `operation_events` 7 play_input + game_end_declaration、current stats `source_count=7`/`confirmed_ended`/`is_current=true`。
- これで「成績27項目はHTTP/DBのみ」の留保を解消した。実機・本番TLS・バックアップ復旧は別。

### 2026-11-11 04:15 9回163球の現HEAD再測

- `test_full_game_screen_e2e` は **1 passed / 1653.21秒**。実画面で163球を保存し、18半回完了、1–0、`normal-end`、終了版v1、reload後の確定版一致を確認した。
- **性能は未達**: 1球あたりの保存時間は最大 **10736ms**、163球すべてが5秒目標を超過。機能完走とNFR-002の5秒目標を分離して記録する。timeoutは延長していない。
- 今回の表示変更（`ordinary-pitch-locked`）とE2E補助の待機は、通常進行の163球を妨げなかった。

### 2026-11-11 04:05 代打・代走・守備変更の実画面接続を試行

- 既存の投手交代E2Eへ代打・守備変更を追加する試行を行った。投手交代と次球は成立し、代打のPOSTは **200/a5拒否**。`idempotency_ledger`の理由は **「交代内容が保存済み原本または実評価値と不一致」** で、D3は3へ進み内容拒否として固定された。
- 代打候補は実`/api/players`から**先発に含まれない控え**を選び、側・打順・現在打者を保存readと一致させた。クライアントの`substitution-validation`はvalid、サーバーの`transitionSubstitutionV1`だけが不一致だった。**製品欠陥か、投手交代後の非play readとserver保存状態の差かは未確定**。
- 試行差分は破棄し、既存の投手交代E2Eを再実行して **1 passed / 97.17秒** を維持した。代打/代走/守備変更の実画面E2Eは未成立のまま残す。domain/payload/providerの単体は **28 passed**。

### 2026-11-11 03:25 終了条件E2Eの最終通過

- `test_end_conditions_screen_e2e` は **1 passed / 1491.83秒**（Playwright **3 passed / 23.9分**）。実HTTPS/実ブラウザ/owned DBで、次の3シナリオを保存・終了宣言・DB照合した。
  - **cold-end**: `game_semi_official`、9回・7点差7回。**49 play_input + game_end_declaration**、`finished`/v1/source_count 49。記録画面の`ordinary-pitch-locked`に「終了条件」を表示。
  - **limit-draw**: `game_other`、9回同点・延長上限9。**54 play_input + game_end_declaration**、`finished`/v1/source_count 54。
  - **tiebreak-required**: `game_official`、9回同点。**54 play_inputのみ**、`in_progress`のまま終了イベントなし。10回表で`tiebreakStartRequired=true`、通常球フォームを閉じ「タイブレーク開始」を表示。
- **到達不能の確定**: 固定5規則では7回・延長上限>9を製品から作れない。`game_official`だけが延長上限12だが10回タイブレーク発動で、開始操作が未接続のため10回以降へ進めない。`game_other`は上限9でlimit-draw。7回は`resolve_stage_a_rule`の固定9回/defaultのみで、大会割当・上書き・規則管理UIが未接続。
- **限定**: 実機・本番TLS・バックアップ復旧・運用公開は未実施。候補環境の成功を実機成功へ読み替えない。

### 2026-11-11 03:15 既知赤の再確認

- `backend/tests/test_p3_function_product.py::test_normal_profile_contains_the_same_full_p3_publishers` は **1 failed / 6.34秒**。差分は`save_primitive_source`本文のD03投手出場フック（`persist_writer_pitcher_entry`）がP3 baseline側に無いこと。P3の数学・保存経路の失敗ではなく、baseline/正式資産の追随待ちとして分離する。
- `tests/domainrt/test_game_lifecycle.py` + `tests/test_game_state_models.py` は **133 passed / 1.96秒**。終了条件核と規則snapshotの固定値は維持。
- `test_p3_verification_cache` / viewer probe/route は **22 passed**、viewer specs **16 passed**、substitution specs **28 passed**。今回のE2E/表示変更の範囲で回帰なし。

### 2026-11-11 02:40 追記：閲覧10秒の測定起点

- 先行する1試合10閲覧の測定はwriter ACK起点だった。要件の「サーバー保存から10秒」と混同しないよう、`GameScreenViewerThreeGameLoad.e2e.ts`の合否を**サーバー保存時刻（`last_saved_at`）起点**へ戻した。ACK起点は`ackMilliseconds`として補助記録だけに残す。
- したがって10.0秒台の既測値は**ACK起点の補助値**であり、サーバー保存起点の10秒合格へ読み替えない。サーバー保存起点の3試合30閲覧は未再測・未達。
- 30秒DB writer bindingは延長していない。

### 未回答の意味判断（タイブレーク製品接続）

`docs/features/mvp-integration-lead/decision-sheet.md`のTB-P1〜P3は未回答。推奨は採用扱いにしない。依存しないコールド/引き分け/タイブレーク検知までは実画面で確認し、開始操作の保存・次球・成績は回答後に接続する。

| ID | 具体例 | 選択肢 | 回答が必要な時点 |
| --- | --- | --- | --- |
| TB-P1 | 10回表、継続打順4、無死一二塁。配置走者の個人IDをどう決めるか | A=記録者が現在出場中の攻撃選手を各塁へ明示指定（推奨候補）/ B=継続打順の直前2枠を自動配置 | 実runner IDを保存し次球へ渡す前 |
| TB-P2 | 配置走者が生還し、その間に投手交代。責任投手をどうするか | A=配置時点の実投手を責任投手として固定（推奨候補）/ B=配置走者を投手個人失点の対象外にする専用区分 | 配置走者の失点計上前 |
| TB-P3 | 10回表3out後、10回裏/11回表へ進む。再配置するか | A=発動後は各半回に規則どおり再配置し、半回別イベントを記録（推奨候補）/ B=最初の半回だけ配置 | 次半回の記録実装前 |


## 2026-11-11 00:30 JST：1試合10閲覧は10.0秒台まで到達、RG1 controller livenessと表示経路が残る

- **1試合0閲覧**: 同E2Eが **1 passed / 83.26秒**。wave 1保存は約7.6秒。
- **1試合10閲覧**: 保存自体は成立する回があり、閲覧更新は **10040ms / 10167ms / 10558ms** と10秒直後まで到達した。ただし安定せず、再実行では `RG1:RG1ControlUnavailable` の503、または `閲覧全表示の同時成立が未達`（120秒observer）で失敗。**成功扱いにしない**。
- **是正**: 閲覧loginを`/games/{id}/view`へ直接向け、記録画面の一覧/詳細readを挟まない。writer ACK時刻を「保存から10秒」の起点へ変更（`last_saved_at`は保存TX内刻印でcommit前）。同一P3 packetの同時検証を単一inflightへ集約し、閲覧名簿の同一選手二重取得を抑止。閲覧pollは3秒へ戻した。
- **残る停止点**: 10閲覧下のRG1 controller liveness（`RG1ControlUnavailable`）と、閲覧ページが記録画面APIを読む経路。3試合30閲覧は未再測・未達。
- **限定**: 3試合30閲覧、実機、本番TLS、バックアップ復旧、運用公開は未実施。30秒DB bindingは延長していない。

## 2026-11-11 01:20 JST：閲覧負荷の基準点を分離、1試合0閲覧は通過・10閲覧で保存503

- **新たに通った基準点**: `PITCHLOG_VIEWER_LOAD_GAMES=1 PITCHLOG_VIEWER_LOAD_VIEWERS_PER_GAME=0` の同E2Eが **1 passed / 83.26秒**。wave 1の保存は約7.6秒で、単一writer・閲覧なしの縦断は通る。
- **1試合10閲覧**: 初回閲覧loadは通過（fixtureの`applied_rules`を`cold/overtime`から正準`coldConditions/extensionLimit`へ是正し、`realLogin`後に認証済み画面のhydrateを待つ）。ただしwriter保存は約3秒で **503**。play_rows 0で原子性は維持。
- **3試合30閲覧**: 同じ保存503が残り、NFR-004は未達。timeout延長・成功読み替えはしない。
- **実施した是正**: 共有engineのpoolを20+20へ拡張（認証発行はNullPool）、閲覧負荷E2Eに`PITCHLOG_VIEWER_LOAD_GAMES`/`PITCHLOG_VIEWER_LOAD_VIEWERS_PER_GAME`の規模注入を追加（既定3/10）、fixtureの規則shapeを正準化、`realLogin`のhydrate待ち、初回cold startを60秒へ分離。
- **残る停止点**: 10閲覧時の保存503。`sync_events`の503種別とplay export binding照合の実測を次のunitで行う。台帳・HEADは診断計装を含まない。

## 2026-11-11 00:05 JST：閲覧負荷の次の停止点はplay exportのwriter binding不一致

- **逐次保存での再測**: 3 writer同時を逐次へ変えた診断では、rights 2.3秒、validate 0.04秒、projection 0.46秒まで進み、約12秒で `PlayExportWriterUnavailable`（原因 `ProgrammingError: writer binding rejected`）になった。30秒期限切れではなく、`save_writer_play_export_snapshot` の `assert_writer_binding` が同一TX内で拒否している。
- **同時保存では**: 同じ経路が約41秒まで延び、30秒DB binding期限切れの503にもなる。rightsは同時3 writerで9〜10秒、逐次では2.3秒。負荷の主因はwriter間/閲覧pollの競合とplay export保存のbinding照合。
- **維持した修正**: 業務engineのプロセス内共有（接続枠枯渇の解消）、閲覧poll 5秒。30秒bindingは延長していない。
- **未達**: 3試合×30閲覧の保存完了。`PlayExportWriterUnavailable` のbinding不一致を解消するまでNFR-004を成功扱いにしない。診断用の一時計装はHEADへ残していない。

## 2026-11-10 23:10 JST：artifact再pin後のP3 CSVも継続成功

- **再測**: `test_actual_p3_26_csv_export_http` **1 passed / 322.78秒**。26球→P3訂正後の毎球ZIPが200・26行、対象d1=26「ボール」まで一致した。`test_actual_p3_26_lifecycle_end_reopen_add_reend_stats` は **1 passed / 478.54秒**。
- **現在の固定点**: `feature/mvp-integration-20261109`、作業ツリーclean。artifactは`b565641886c758b81787baff95bdacceb3dea648781515cac39f868583c156ad`。
- **未達**: 3試合×30閲覧のwave 1保存は30秒binding超過（rights 9〜10秒）。P3 baselineの`save_primitive_source`本文不一致、stats候補DDL前提の既知赤は残る。

## 2026-11-10 22:55 JST：artifact再pin後もP3 26球lifecycle縦断は継続成功

- **再測**: `test_actual_p3_26_lifecycle_end_reopen_add_reend_stats` **1 passed / 478.54秒**。新しいdomain artifact `b5656418` で26球→P3 26件訂正→27球目→終了→再開→追加play→再終了→lifecycle read→成績/CSVの縦断が通った。妨害修正の再pinは既存P3経路の数学・保存を変えていない。
- **併走確認**: backend対象 **672 passed**（engine共有・registry pin・interference v6・batted/interference schema・nonplay prefix等）、frontend domain/api/viewer **1007 passed**。Ruff/Ty/ESLint/vue-tscは対象変更で0。
- **未達**: 3試合×30閲覧のwave 1保存は引き続き30秒binding超過（rights 9〜10秒）。成功へ読み替えない。

## 2026-11-10 22:20 JST：妨害7分岐は全通し、閲覧負荷は接続枯渇を解消したが30秒内保存は未達

- **新たに通った**: `test_interference_screen_e2e` **1 passed / 183.66秒**。INT-02、INT-01+INT-03、通常三塁打+INT-02本盗、INT-04+INT-05、INT-06+通常単打+INT-07の5試合・全7分岐を実画面から保存し、play_row 41列・走者・current stats version・source metric_states・facts・重複ACK・reloadを実DBで照合した。
- **コア是正**: 採用妨害のdomain ruleが`scoringEvidence`を落としていたためtyped `runnerScoreEffects`を返さず、server wire headで停止していた。`battedHit.ts`を是正しartifactを`b565641886c758b81787baff95bdacceb3dea648781515cac39f868583c156ad`へ再生成、manifest/D11/現行metadata/v6 witness/開始投手SQL/test pinを自己識別子だけ再導出した。妨害personの`batter_id`/`runner_id`を生IDと誤認していた投影も入れ子解決へ是正した。
- **負荷の新計測**: `test_viewer_three_game_load_owned` は未達。writerのclick handlerは即時（heartbeat最大gap 476ms）、POSTは実送信され、約41秒後に503 `writer binding rejected`。stage実測は scope 0.1秒 → bound 1.8秒 → gated 6.8秒 → device 8.5秒 → preflight 12.4秒 → game lock 0.1秒 → **rights 9〜10秒** → 30秒binding失効。3 writerすべて同じ10秒rightsを示し、同時刻押下を1秒ずらしても変わらない。DB activityはapp role最大45 session、待機は`authn.verify_token`のtuple/transactionidで、rg1/record rowの待機ではない。
- **実施した是正**: 業務engineをプロセス内で共有し（`create_database_engine`の設定key付きcache、認証発行だけisolated engine）、要求ごとのengine生成による接続枠枯渇を解消。閲覧poll既定を3秒→5秒へ広げ、10秒更新の余裕と負荷低減を両立。30秒DB bindingは延長していない。
- **残る失敗**: 3試合×30閲覧のwave 1保存は、`rights` stageの約10秒とpre-apply約13秒で30秒を超える。timeout延長・成功読み替えはしない。次unitはrights/authorityの10秒（`binding_check`/`check_current_right`）の内訳を削る製品修正。
- **既知赤**: `test_p3_function_product`の`save_primitive_source`本文不一致（P3 baselineがD03投手出場hookより前に取得される順序）は継続。`test_stats_queries`/`test_stats_appearance_http`の候補DDL前提も継続。`test_sync_apply_writer_binding`の固定registry pinは現行33操作を明示pinして通した。
- **限定**: 実機・本番TLS・バックアップ復旧・運用公開は未実施。負荷はheadless Chromiumの候補環境。

## 2026-11-10 20:50 JST：妨害7分岐の実画面E2Eが全分岐成立、artifactを再pin

- **新たに通った**: `test_interference_screen_e2e` **1 passed / 183.66秒**（self-signed TLSの実Playwright/Chromium）。INT-02、INT-01+INT-03、通常三塁打+INT-02本盗、INT-04+INT-05、INT-06+通常単打+INT-07の**5試合・全7分岐**を実画面から保存し、各行のplay_row 41列・走者行・current stats version・source metric_states・facts・重複ACK・reloadを実DBで照合した。
- **原因と是正（コア）**: 採用された妨害実プレイ（INT-01/03）のdomain ruleが通常打球へ委譲する際に`scoringEvidence`を落とし、server wire headが要求するtyped `runnerScoreEffects`を返していなかった。`battedHit.ts`で採用実プレイも明示裁定として空集合を含む根拠を必ず返すよう是正し、domain specを追加。artifactを`b565641886c758b81787baff95bdacceb3dea648781515cac39f868583c156ad`へ再生成し、7 manifest・D11/現行metadata・v6 witness/registry・開始投手SQL・固定test pinを自己識別子だけ再導出した（数学期待は不変）。v6 witnessのcurrent/registry digestを再封印。
- **投影の是正**: 妨害裁定のperson object（`batter_id`/`runner_id`）を`prefix_path._resolve_payload`が生の選手ID文字列と誤認して422にしていた。入れ子person参照だけを再帰解決し、生IDの閉検査は維持。INT-04/05/06/07の保存が成立。
- **E2E入力の是正**: INT-05は妨害対象を一塁走者にし、一塁前選択は打者妨害時だけ操作。reload中断応答の本文読取失敗を次応答待ちへ限定。live試合のcurrent stats versionはlifecycle headではなく`stats_fact_versions.is_current`で照合。`stolen_bases`の閉値は`source_unavailable`。
- **限定**: 実ブラウザはheadlessで実機ではない。負荷・実機・本番TLS・バックアップ復旧・運用公開は未実施。

## 2026-11-10 08:40 JST：走者打球の実画面E2E成立、interferenceは2試合目で停止

- **新たに通った**: `test_runners_batted_hits_screen_e2e` **1 passed 142.56秒**（self-signed TLSの実Playwright/Chromium）。開始直後の`?recording=play-prefix-v3`自動接続へ追随し、走者生還時のRBI因果`ordinary-play`を明示、結果ファイルの親ディレクトリを用意した。単打→三塁、二塁打→生還、一二塁→本塁打の3シナリオと別tenant prefix拒否を実DB/HTTPで照合。
- **interferenceは未成立**: 1シナリオ目はINT-02まで1play保存。2シナリオ目は**INT-01の`adopted: single`**で、UIが「この入力を確定できません。結果・打者と最新の記録を確認してください」を表示して送信前に遮断（`first-ball-status=blocked`、POST/GET 0）。試合bindingではなく、当該分岐の結果/打者整合が次の停止点。成功へ読み替えない。
- **全pure一括**: `pytest tests/ --ignore=tests/db` は15分超で未完了（21%で打切り）。全件成功とは書かない。変更範囲はP3/CSV/wire/bindingの個別スイート（151 passed、1188 passed等）で確認した。
- **限定**: 走者打球E2Eは実ブラウザ（headless）であり実機ではない。interference/3試合30閲覧/実機・運用は未実施。

## 2026-11-10 08:10 JST：P3直後lifecycle readをcapsule実効stackへ接続し200

- **新たに通った**: `test_actual_p3_26_csv_export_http` **1 passed 331.56秒**（ZIP 26行・対象d1=26「ボール」）、`test_actual_p3_26_lifecycle_end_reopen_add_reend_stats` **1 passed 506.61秒**。`lifecycle_after_p3=200`（従来503）、`lifecycle_after_27=200`、lifecycle_d3=31、lastVersion=2、CSV 20/10、play_rows=29、stats current source_count=28/confirmed_ended、P3 cache hit 51/miss 6/key error 0。
- **原因**: P3訂正直後は物理CP列/contentと論理nextが過渡的に一致せず、`_legacy_undo_metadata`のlast payload照合と`read_started_nonplay_active_history`のCP tokenが不成立。P3 packet/stack自体は正常で、27球目後の祖先P3 readは従来どおり200。
- **是正**: v3枝は`verified_p3.checkpoint == doc`のとき、anchor枝はanchor capsuleのwatermarkが現d3以上（同一論理current）のとき、`p3_effective_nonplay_frames`でcapsule 26 itemから実効ActiveFrameを再構成し、同じpublic nonplay viewへ写す。post-27の祖先P3は従来の物理history pathへ戻す。item_digestは派生key（`original_source`/`original_event_d2`）を除外する共有`p3_item_digest_source`へ寄せ、DB固定列のdigestを変えない。
- **限定**: 5秒目標は追加playで未達のまま別測定。実機・3試合×10閲覧・バックアップ復旧・運用公開は未実施。既知赤（`save_primitive_source`、`tenant_transaction_scope`、固定registry期待、旧v2/candidate）は継続。

## 2026-11-10 07:40 JST：P3直後readの停止点を`read_undo_prefix`のanchor枝へ限定

- **再測**: `test_actual_p3_26_csv_export_http` **1 passed 336.59秒**（ZIP 26行・対象d1=26「ボール」）。`lifecycle_after_p3` は503のままで、応答bodyは汎用エラー。
- **停止点**: `read_p3_nonplay_current`/`p3_effective_nonplay_frame`/`p3_effective_nonplay_stack`/`_read_legacy_undo_source` の例外traceは空。停止は `read_undo_prefix` の `nonplay-prefix-checkpoint-v1` 枝が `read_lineup_prefix` へ委譲した先の `OrdinaryPrefixError:通常投球の確定prefixを確認できません`。P3訂正直後は物理CPがanchor形式のまま、27球目保存後にv3 CPへ進み同readが200になる。
- **次unit**: `read_undo_prefix` のanchor枝で、P3 capsuleの合成checkpoint/effective frameを `read_lineup_prefix` と同じ `_read_p3_lineup_projection` へ渡し、物理anchorと論理nextの差を二重実装せずに扱う。実装時はP3直後read 200を同じ26球試験で再測する。

## 2026-11-10 07:20 JST：D11実DBと走者操作の実ブラウザ縦断が成立

- **D11実DB**: `test_stats_native_d11` **2 passed 159.41秒**。27指標を実SQL/RRRO/receiver/formatterへ通し、`ordinary-pitch-play-v1` は走者の得点/盗塁観測をwireに持たないため `rbi`/`runs`/`steals` を `source_unavailable`（reason `MISSING_OBSERVATION`）として返す。score不変から0を推定しない。
- **走者操作の実ブラウザ**: `test_runner_operations_screen_e2e` **1 passed 250.22秒**。ローカル生成self-signed TLS（SAN `IP:127.0.0.1`）でPlaywright/Chromium→Vite HTTPS→製品app→owned DBを実走。UI作成/開始、実走塁の保存、重複、reload、越境拒否、DB全値を照合した。**実機・実利用者端末・本番TLSではない**（候補環境の実ブラウザ）。
- **同時実行の切分け**: 同一invocationのHTTP/DB試験は substitution vertical、lifecycle v3、stats undo helper×2 の **4 passed**。runner/batted hits/interference/substitution/undo の画面E2EはTLS PATH未供給で4 skipped + interference setup errorだったため、self-signed TLSを明示して個別に再実行した（skipを成功へ読み替えない）。
- **画面E2Eの実測**（self-signed TLS、実Playwright/Chromium）:
  - **pass**: runner operations **1 passed 250.22秒**、substitution product **1 passed**。
  - **fail（未解決）**: batted hits 3件は零読み後の「三振・攻守交代を含む投球の記録へ」ボタンが30秒以内に現れず、4件目は結果ファイル欠落。interferenceはINT-02（1play）まで保存後に次分岐のPOST/GETが30秒timeout（2試合目は0play）。undoはACK喪失→reload→retryで同一undoの`attemptSha256`が変わり、同要求再送の期待に反した（新attemptで送信）。いずれもobtained rejection/失敗として残し、成功へ読み替えない。
  - **undoの再実行**: 上記のattempt差は、`recoverableSyncPost.spec.ts`が固定する既採用の結果不明解決（`retry_allowed`後に同本文/同D5のまま新attemptへ進める`SyncAttemptBarrier`）と一致していた。E2Eの旧期待「attemptまで同一」を、本文/D5同一・attempt更新の期待へ是正し、`test_undo_product_screen_e2e` は **1 passed 115.05秒**。旧attemptの再利用を成功条件にしない。
- **3試合×30閲覧load**: **未成立**。E2E導線のcold start待ちを分離した後、30閲覧の初回`更新済み`・server-only注記・18名 lineupは通過したが、wave 1の実保存で`recordRealPitch`のPOST/GETが45秒timeout。30閲覧同時poll下でwriter保存が45秒以内に成立せず、保存後10秒更新の測定へ到達しない。**NFR-004の3試合×10閲覧（本試験は30閲覧）は未達**として残す。タイムアウトを延ばして成功へ読み替えない。
- **次の実行**: 30閲覧下のwriter starvation（app/DB/uvicorn worker/ブラウザ資源の切り分け）、共有E2E導線（create→start→record）の現行UX追随、interference分岐の停止点、P3直後read。TLS資材は`/tmp/opencode/tls`の試験専用で、リポジトリ/シークレットへ保存しない。

## 2026-11-10 06:55 JST：broker再起動B（同一epoch）も26球→P3→27球目で成立

- **新たに通った**: `test_p3_26_broker_restart_vertical` **1 passed 359.39秒**。26球記録中にinitial grant brokerの子PIDをkillし、supervisorが**新しい子PID**で同じsocketへ再起動した後、P3 26件訂正→27球目まで受理。DBはgate open/recovery_generation=1、`recording_generations=(1,normal,NULL,NULL,1)`、play_rows=28（26元+P3有効版1+27球目）、現在stats source_count=27、open writer_bindings=0を実測した。endpointファイルの再出現だけでなく新child PIDを確認している。
- **意味の限定**: これは**同一epoch**のbroker再起動であり、非0 gate/right epoch復旧ではない。fail-closed後の旧epoch同一D5再送がB7/503のままであること（再起動だけでは権利を復活させない）は既存試験で確認済み。新generation/D4+V12付与・旧generation失効・旧holder/epoch拒否・結果不明の別解決は未実装。
- **次の実行**: D11実DB、操作在庫（走者/併殺/失策/妨害/交代/取消/タイブレーク/終了条件）のowned画面E2E、3試合×10閲覧、P3直後read。

## 2026-11-10 06:50 JST：P3後28球目まで同一候補で成立、30秒はwire指紋の重複再計算が原因

- **新たに通った**: 26球→P3 26件訂正→27球目→`lifecycle-prefix-v1` 200→終了受理→再開受理→**追加play（28球目）受理**→再終了→reload→公式成績/ゲームCSV/シーズンCSV。`test_actual_p3_26_lifecycle_end_reopen_add_reend_stats` は **1 passed 492.58秒**。DBは `play_rows=29`（26元+P3有効版1+27球目+追加）、有効版イベント行1、現在stats `source_count=28`/`confirmed_ended`/current版1、最大source_count 28、gate open、ゲームCSV 20行・シーズンCSV 10行を実測した。
- **原因の確定**: 以前の`writer binding rejected`（binding_age 30.1秒）はP3 26件検証の重複ではなく、同一の不変wire sourceに対する`source_binding.read`/`assert_event_source`が117回、各回で全V7 activeStackの指紋・正規化・原本encodeを再実行していたこと。cProfileで当該apply 30.4秒のうち`source_binding.read` 23.25秒、`_flush_native_stats` 15.96秒、`_json_value` 15.08秒を実測した。
- **是正**: `wire_event_fingerprint`と`wire_original`の正規化を、不変`MappingProxyType`の同一性で有界に再利用するcacheを追加した。seal/型/指紋一致の比較は毎回維持し、差替え/偽値の拒否試験は不変。P3 current/頁の全bytes keyによるプロセス内packet cacheも追加し、anchor CP行の`quoted_name` keyだけをkey生成時にplain strへ正規化した。**30秒DB writer bindingは延長せず、不変のまま**。
- **実測**: P3 packet cacheはhit 27/miss 6/key error 0。hit時`verify_p3_current_packet`は約90ms、miss時約3.4秒。lifecycle readは約1.6〜2.0秒（以前約5.3秒）。追加playの最終binding ageは7.558秒で30秒内。**5秒目標は未達**（追加playは7.5秒超）だが、30秒期限拒否とは別測定として記録する。
- **限定**: P3訂正直後（27球目前）のlifecycle readは503のまま（P3 current CPの物理行と論理next contentの差）。実機/実TLSブラウザ/3試合×10閲覧/バックアップ復旧/運用公開は未実施。
- **既知赤の追加**: `test_sync_apply_writer_binding::test_void_adapter_preserves_every_other_registered_function` は固定registry期待が現行operation数に追随しておらずHEAD前から赤（本差分外）。既存の`save_primitive_source`本文不一致と`tenant_transaction_scope`欠落も継続。

## 2026-11-10 05:30 JST（履歴）：追加playはdomain TIME_LIMITを解消、30秒bindingの原因切り分け

- **新たに通った**: 26球→P3訂正→27球目→lifecycle read 200→終了受理→再開受理→**追加playのdomain評価**。27frame級の非play継続が`vmTimeoutMs=100`の`TIME_LIMIT`になったため、5秒応答目標・2秒reply期限の内側で`_VM_TIMEOUT_MS=500`へ有限上限を広げた（30秒DB bindingは不変）。
- **現在失敗**: 追加playの`persist_accepted_play_export`で`writer binding rejected`（`precommit_failure.binding_age_ms=30145`、`expires_at<=now`）。DB writer bindingの30秒総保持を**延長せず**、server側`read_confirmed_nonplay_normal`がP3 capsuleの26-item T5/監査検証を再実行する重複で30秒を超えた。クライアント直後のlifecycle readと同一P3不変原本を二重検証している。
- **次の作業**: P3 capsule/head/current CPをkeyにした同一プロセス内の検証済みP3 packet cache（またはsource専用の軽量検証）で、write bindingの30秒区間から重複T5/監査再計算を除く。30秒は延長しない。その後、追加play→再終了→reload→成績27/CSV、P3直後read、broker再起動B、D11実DB、残操作、閲覧、正式統合へ進む。

## 2026-11-10 04:30 JST：P3後27球目の終了・再開は受理、追加playは次unit

- **新たに通った**: 26球→P3訂正→27球目→`lifecycle-prefix-v1` 200→**終了宣言 受理**→**再開 受理**。write側 `read_confirmed_lineup_prefix` と `read_confirmed_nonplay_prefix` に、P3 next CPが現在docの祖先である場合の同一限定（watermark/revisionの祖先+現在headからのlast source）を接続した。P3-effective stackをread/writeで同じ `p3_effective_nonplay_stack` に限定し、物理/論理の二重実装を作っていない。
- **現在失敗**: 再開後の追加play（28球目）が server-side domain guest で `DomainRuntimeError: ゲストの実行に失敗`（`_evaluate_nonplay_normal_bound` → domain host）。クライアント側の同じ継続評価は成功しているため、serverが再構成するP3-effective中間frame（d1=26の実効play/historyEntry/source）と継続requestのsource束縛の不一致を次に切り分ける。終了・再開のACK、read 200、gate openは実測済み。
- **次の作業**: (1) 追加playのserver-side source再構成（`_evaluate_nonplay_normal_bound`）でP3-effective frameの`play.source.eventId`/historyEntry/playIdを現在chainへ束縛する、(2) 追加→再終了→reload→成績27/CSV、(3) P3直後（27球目前）のlifecycle read 503、(4) broker再起動B、D11実DB、残操作、閲覧、正式統合。

## 2026-11-10 03:20 JST：P3後27球目のlifecycle readは成立、終了書込みは次unit

- **新たに通った**: 26球→P3 26件訂正→27球目保存（`prefix=27`）に続き、27球目後の `lifecycle-prefix-v1` が **200**。P3 capsuleのwatermark 26・item 26・頁chain形式のsource/evaluation digest・非current候補版・T5評価26件・後続27球frameを実DB readerで照合し、P3 next CPを履歴ancestorとして受理した。P3/CSV純201 passed、追加76 passed。
- **残る503**: P3訂正直後（27球目前）のlifecycle readは503（P3 current CPが物理行と論理next contentで異なるP3 stateの未対応）。27球目後の **終了宣言** は503 `OrdinaryPrefixError: 通常投球の確定prefixを確認できません`。原因は lifecycle write の `read_confirmed_lineup_prefix` が物理/旧履歴のactive sourceを照合し、lifecycle readのP3-effective source（d1=26の訂正後frame）と一致しないこと。終了・再開・追加・再終了へ進むには、同じ `p3_effective_nonplay_stack` をwrite側actual sourceへ適用し、P3 next CPの祖先を限定する専用unitが必要。
- **次の作業**: (1) `read_confirmed_lineup_prefix`/`_confirmed_lineup_source` のactual sourceへP3-effective stackを同一関数で適用（物理／論理の二重実装をしない）、(2) 27球目後のend→reopen→additional play→re-end→stats/CSVの再実測、(3) P3直後readのcurrent CP論理next対応、(4) broker再起動B・D11実DB・残操作・閲覧・正式統合。
- **既知赤**: `test_p3_function_product` の `save_primitive_source` 本文不一致と `test_nonplay_prefix_read` の `tenant_transaction_scope` 属性欠落は変更前から。D11実DBは未実行。実機/運用/3試合10閲覧/バックアップは未実施。

## 2026-11-10 02:10 JST：P3後のlifecycle読取を候補版・履歴CP・頁chainへ接続

- **診断の確定**: `lifecycle-prefix-v1` はP3訂正直後と27球目後の双方で503。traceは `read_p3_current` の `P3 current ... rejected` → 修正後 `P3 current count rejected`（capsule watermark 26が旧1..25上限を超過）→ `P3 current source count rejected`（P3 headが後続版を指す）→ verifierの `P3 current stats row/CP linkage/source集合`。P3候補版はcurrentでなく、後続playがhead/capsuleのstats pointerを進め、頁chain形式の `source_set_digest`/`stats_evaluation_set_digest` を持つ。
- **是正**: `read_p3_current` はP3 capsuleのwatermark一致・model一致の版を選び、非current候補/履歴版のhealthを要求しない。応答checkpointはcapsuleのnext content/id/revision/digest/水位を合成し、現在CPとは分離。verifierはP3版のwatermark/item/原本/有効/CP連結/change eventを個別に照合し、頁chain digest（source/evaluation）も再計算して受理。非play frameは既に実効版なら再適用せず検証、stackの現状態はP3 watermark frameで照合。P3 next CPは現在chainの祖先として許可。item上限を26（25頁+対象）へ。契約function bodyを再生成。
- **現在**: P3/CSV純 **201 passed**、追加76 passed。26球→P3→27球目の保存は成立済み。lifecycle readの実DB縦断は反復中で、次の未達は verifierの後続段（`P3現head`/T5評価/履歴再構成）または end/reopen 接続。台帳の既知赤（`save_primitive_source` 本文不一致、`tenant_transaction_scope` 属性欠落）は変更前から赤。

## 2026-11-10 01:20 JST：P3後のlifecycle読取を候補版・履歴anchorへ接続

- **診断**: 26球→P3訂正→27球目はアプリ結果 `prefix=27` で保存成立。しかし `lifecycle-prefix-v1` はP3訂正直後・27球目後の双方で503。traceで `read_p3_current` の `P3 current read rejected`（line 159）を確認。原因は非play lifecycle readがP3候補版（`is_current=false`）を拒否し、さらに現在CPのみを選んでいたこと。
- **是正**: `read_p3_current` はcapsuleの `next_checkpoint_id` を履歴anchorとして選び、P3版がcurrentでない場合はcapsule/checkpoint/source束縛だけを検証してcanonical healthを要求しない。verifierは非anchorの候補/履歴版を受け、`p3_effective_nonplay_frame` は既に実効版のframeを再適用せず検証して保持、stackの現状態照合はP3 watermarkのframeで行う。`read_undo_prefix` はP3 next CPが現在chainの祖先である場合だけ許可。`read_p3_nonplay_current` のanchor行はpacket原本から供給。契約function bodyを再生成。
- **現在**: 既存P3/CSV純201 passed。`test_p3_function_product` の `save_primitive_source` 本文不一致と `test_nonplay_prefix_read` の `tenant_transaction_scope` 属性欠落は変更前から赤（今回差分外）として分離。
- **次の実行**: 26球→P3→27→終了→再開→追加→再終了→成績/CSVの再実測。

## 2026-11-10 00:10 JST：27球目503の原因確定とP3後縦断の再開

- **原因確定**: 訂正後27球目の503は、RG1 controllerが `LedgerOutcomeUnconfirmed` で終了しgateがclosedになったため。authorityのbinding lease channelが一般timeout（隔離fixture 2秒）で、30秒保持中の正当な無通信を切断→authority全体がblocked→controllerのidle確認が失敗、というliveness欠陥。DB bindingの30秒期限切れではない（失敗時も期限余裕24.7秒）。診断実行では27球目保存のbinding_age 5.5秒で同じ経路を再現し、controllerの終了理由とgate closedを実測した。
- **是正**: `authority.py` の受付channelを `sync_binding` だけ35秒（30秒総保持+余裕）にした。DBの30秒・immutability・sliding renewalの意味は変更しない。test-only binding brokerのapp channelも35秒へ揃えた。manifestのadapter/source SHAを実ファイルへ追随（adapterはHEAD時点で既に不整合だった）。
- **D11 rbi/runs/steals**: `ordinary-pitch-play-v1` は走者の得点/盗塁観測をwireに含まないため、score不変だけからcompleteを推定しない。D11 current_openの `source_unavailable` 期待へ整合。stats純 **395 passed**。
- **A（broker障害なし・訂正→27球目）**: 26球→P3 26件訂正→27球目の実HTTPが **成功**（app結果 `prefix=27`, controller running, gate open, 504旧assertのみ）。旧testのP3 snapshot DB照合が `打席結果` を見ていたため `打撃結果` へ修正した。製品経路は27球目まで書込み成立。
- **新規回帰**: `test_p3_fault_controller_liveness.py` を追加。P3故障取消直後とP3受理直後に `/sync/attempts/recover` でgate生存を照合する。第1故障後は200を実測。
- **次の実行**: 26球→P3→27→終了→再開→追加→再終了→reload→成績27項目/毎球ZIP/成績CSVの同一候補試験、broker再起動を挟む同縦断、D11実DB。


## 2026-11-09 03:20 JST：P3有限INSERTと訂正CSV0050を同一統合候補へ接合

- **引継ぎ照合**: `feature/mvp-integration-lead@743f137b` clean、固定候補は台帳どおり。新統合枝 `feature/mvp-integration-20261109` を `c327d7ee` から作成し、`d5e63831`（CSV共有0050）と `3952d2c0`（CSV P1後発）を通常mergeした。main/developへの直接変更なし。
- **接合内容**: P3有限37列/INSERT policy1/保護4列cleanと、CSV0050の17列append-only/5関数/既9列SELECT追補/世代束縛/動的列原本照合を同一資産へ統合。`first_ball_product` はCSV activation→P3 insert activationの順で両方を保持。公式helperからddl-elements/manifest/4関数body/runtime contract protected objectsを再導出（revision 34→35）。P3/CSVの対象129 passed、0050 current startup実PG 1 passed 61.51秒、P3/CSV storage純219 passed、backend Ruff/Ty 0。
- **UI是正**: 妨害公開口 `deriveInterference` 追加に伴うartifact spec 3件と、runner enum/artifact identityに追随していないschema spec 2件を現行正準へ修正（5 files）。root `tests/domain/gen/test_undo_selector.py` のbackend importを既規約（importlib）へ修正しroot Ty 0。frontend vue-tsc/ESLint 0。
- **実E2Eの停止と切分け**: 初球HTTPはowned実DBで `LedgerUnavailable`。broker観測では `binding_check` が0.4〜30.2秒に200回超、authority lease 30秒で失効していた。97a単独は同試験成功、c327単独は再現。P3 insert差分はapp role権限を変えないため、保存処理が30秒境界に達するliveness問題として切分け、次の3点だけを実装した。
  - 生存確認ごとに同一leaseを30秒延長するsliding renewalをapp/authority双方へ実装。非文字列/後退応答/期限切れは拒否し、DBの `publish_writer_binding` が持つ30秒上限・immutabilityは変更しない。
  - authorityのread-only接続をbinding中だけ再利用し、書込みは従来どおり呼出ごとの独立接続+commitを維持。
  - binding_checkの `_live_matches` だけを1秒に1回へ抑制。control原本照合・fence生存確認・期限・主体は毎回実施。
  - 初球E2Eはcleanup後の同sourceで **1 passed 236.95秒**、保存区間は約21.6秒（5秒目標には未達）。純14 passed。
- **P3訂正の現在地**: 有限INSERTは実P3入口まで到達し、前版CSVアンカーが0行になる原因を「P3変更後のcanonical healthと保存済前版T5版の混同」と特定。前版を `v.source_count=p_watermark` + 実checkpoint + 保存済primitive件数へ束縛する方式に修正し、純43 passed。頁読取のヘッダは `p3_projection_write_admissions.transaction_id=own_xid/state=consumed` とcapsule/headの同一TX束縛へ置換した。**P3 shortの応答本文は B14「P3変更内容が確定原本または有限対応範囲と不一致」**（confirmedContentなし、capsule/snapshot 0）であり、200でも訂正保存成功ではない。shortの置換結果は正式closed key `ball/called-strike` に合わせたが、対象/prefixが有限範囲外で拒否された。
- **P3 26pagedの実接続**: 26球変更は begin/finalize/CSVまで通過した。停止原因は4点で、いずれも比較条件を緩めず保存元の意味へ合わせて修正した。(1) `project_p3_direct` の打席結果はV7の `calculation.request.t1.resultId` が正本で、`observations.resultId` や最上位`t1`ではない。(2) P3頁CSVのwriter読取は通常Sの`canonical_s`を使うと訂正change eventの薄いpayloadからartifactを再計算して対象行を落とすため、頁確定と同じcapsule item優先の生成canonicalへ束縛した。(3) 回別スコアのtarget判定もP3対象だけcapsule itemの訂正payloadで行う。(4) `read_p3_current_header` はcheckpoint contentの実キー`version`と`#variable_conflict use_column`を使う。実E2Eは **ACK `変更受理`（d5・対象参照・confirmed_content）**、confirmation、capsule items 26件（corrected 1件）、head revision 1、page rows 26件、P3 CSV snapshot 26件、d1=26の直接列/入力項目まで通過し、故障2点の取消も通過した。26th通常球の旧42501は再現せず、begin/finalizeの42501/42703は期限切れではない。
- **27球目の通信断（30秒期限とは別）**: P3訂正後の27球目は **503**。原因は `RG1Unavailable` → `RG1ControlUnavailable` → `BrokenPipeError`（RG1 control channel）で、DB writer bindingの期限切れではない。commit前検査は **binding_age 5.303秒**、DB binding `expires_at=09:18:14.260`、検査時刻 `09:17:49.581`（余裕24.7秒）、authority期限`09:18:16.286`。27球目の書込みは成立せず、current `source_count=26` のまま（原子性維持）。次は同一D5再送・再起動・ACK喪失として復旧を検査する。**5秒目標は未達（5.303秒>5秒）だが、30秒期限による拒否ではない**。
- **broker再起動後の境界**: RG1 brokerをfail-closed後に同一socketへ再起動するtest-only supervisorを追加し、endpoint再出現を実測した。27球目の503後に同一D5・同一本文・同一attemptで再送し、`/sync/attempts/recover` も照会したが、復帰結果は **B7/503**（RG1 gate/right epoch不一致）。書込みは不成立のままで、再起動だけでは同一ゲート権利を復元しない。次は新epochのright再取得（再開/復旧handshake）を製品経路で接続する。30秒binding期限とは無関係。
- **正常lifecycleの再確認**: `test_actual_v3_two_ball_end_reopen_append_reend` は現候補で **1 passed 128.86秒**。終了→再開→追加→再終了の通常v3経路は成立。P3訂正後の同経路は27球目のgate復旧待ち。既存v2 lifecycle read試験は現行v3試験に置換済みとしてskipし、v2互換の再検証は別途保留。
- **独立レビュー指摘の是正**: 固定HEAD `5a5ccc93` のCodexレビューでP1/P2×2。P1はP3 CSV読取が `observations.resultId` を要求し、通常投球V7で失敗する点。T1 `calculation.request.t1.resultId` の共有helperへ寄せ、P3 coverageのDiskRows `append` 不在、change eventの`target_generation`、P3で置換された旧playの監査coverageも是正した。実26球訂正後の **`/exports/plays.zip` 200・26行・対象d1=26「ボール」** を実DB/HTTPで確認（**1 passed 339.66秒**。snapshot保存だけでは代替しない）。P2はv2 lifecycle skipで故障取消が失われる点と、broker再起動testがendpoint存在だけで偽陽性になり得る点。v3 lifecycleへ実故障注入→全取消→再終了を追加し、broker再起動testは新child PID一致まで確認する形へ強化した。
- **現行候補の横断スイート**: 0050現行で `test_stats_native_vertical_http`・`test_stats_basic_lifecycle_http`・`test_play_export_v3_product_http`・`test_play_export_score_vertical`・`test_play_export_substitution_http`・`test_viewer_live_owned` の **9 passed**（CSV/ZIP・27項目成績・交代後CSV・viewer実DB）。candidate DDLの二重適用を0050では行わず、viewer catalog期待を0050へ更新した。`test_game_lifecycle_v3_http` の終了/再開/追加/再終了も **1 passed**。これらは訂正後P3経路の完成を意味しない。
- **P1/P2再レビュー後の現在地（HEAD 99b4a0b5）**: P3訂正後の実CSV ZIPは **1 passed 332.17秒（200・26行・d1=26「ボール」）**。P3 coverage純18 passed。v3 lifecycle故障は **1 passed 146.67秒**（故障D5のevent/ledger/admission 0、stats版4、HTTP全取消、再終了）。broker supervisor新childは **1 passed 49.66秒**。Ruff/Ty 0。Codex再レビューはP2 1件（故障要求D5と照合D5の不一致）を指摘し、`99b4a0b5`で一致させた。
- **0050 legacy試験の分離**: `test_stats_appearance_http` の候補DDL再適用を0050では行わないよう分離し、`start-zero` は **1 passed 56.38秒**。ただし同ファイルの残り5件は故障注入とCSV候補DDLの旧前提が残り赤。`test_play_export_primitives`等のv2前提も未整理。
- **追加の旧試験**: `test_terminal_pitch_storage` / `test_sync_apply_idempotency_boundary` の同時実行は 2 failed/5 errors。内訳は旧v2 `OrdinaryPrefixError` と所有DB fixtureの後続接続拒否で、P3/P1の成功証拠へ数えない。個別のv3経路は別途通す。
- **実機準備**: `manual-rehearsal.md` に接続先・HTTPS/端末/データ/操作/期待/既知制限を固定。27球目はB7/503の未回復として明記し、実機成功を代記しない。
- **既知赤（最終統合前に是正）**: D11 `rbi` が期待`source_unavailable`に対し`available 0`（2 failed）。`test_stats_queries` 2件・`test_stats_appearance_http` 8件は現行v3/0050前提へ未追随（空診断のAssertionError）。旧v2/candidate DDL前提のbackend試験群（play_export_primitives等）は現行v3へ未整理。27球目はbroker再起動後 **B7/503** のままで、非0 gate/right epoch復旧が未実装。実TLS browser・実機・運用・3試合/10閲覧・バックアップ復旧は未実施。
- **30秒契約の確認**: `docs/design/data-model.md` は writer_bindings の期限を含む27列を不変とし、`state/close_id` のopen→closed一度だけを許す。`publish_writer_binding` は `expires_at > now+30s` を拒否し、`assert_writer_binding` は `expires_at<=now` を拒否する。したがってDBの30秒は**更新不可の総保持上限**であり、DB行の期限更新は単なる不具合修正ではなく契約改訂（data-model/SQL/trigger/レビュー）を要する。既存委任の範囲では実装しない。authority側のsliding renewalはDB行を延長せず、書込みを30秒超へ許可しない。
- **未了**: 26paged全体（P3本体と故障取消は通過、27球目はbroker再起動後もB7/503で停止）、broker再起動後のgate/right epoch再取得、同D5再送・ACK喪失・担当交代の復旧、閲覧3試合、正式corpus reseal（requirements pinが現行文書と不一致でcatalog checker停止）、7.7/seal/必須CI/通常PR統合、実機・運用復旧。`test_p3_candidate_compile_author` は0048候補DDLを0050 currentへ重ねる旧試験で、有限INSERTの失敗ではない。

更新: 2026-10-23。判断者: Codex主担当。根拠: 同日POの `/goal` 指示と例外委任（撤回または今回MVP終了まで）。山田正輝の個別実値確認・署名とは記録しない。

## 引受と固定点

全体目標・編集権を引受。各領域の現HEAD・作業状態は [takeover.json](takeover.json)。既存引継ぎを正として参照し、全保全物を読了したとは扱わない。P-6は役割・封印・曝露履歴を維持し、候補作成へ吸収しない。TSK-545はHEAD一致・clean、対象cwdの稼働なし。独立引継ぎ未受領の不足は残し、今回POによる主担当移管を記録する。旧担当への再許可照会は要しない。

- develop: `1ab398cc7b2e0f54eafc038fc761a8a8ab42d2a0`。2026-10-23 fetch確認。
- #176/#174/#175公開HEADは報告値一致、Draft。#173は公開`dac2ff15`、ローカル`6af8c801`と未コミット36パス。既存引継ぎmanifest照合前に触れない。
- #176: `c1413b25`と未コミット3文書は引継ぎ通り。pytest/ruff等の変更・検査プロセスなし。停止記録と今回指示に基づき引受。旧担当通知はPRコメントを使う（agmsgは当該project未登録で既存担当との経路がない）。送付と受諾を分ける。
- #174未コミット引継ぎ文書、T2未追跡JSON、成績未追跡文書は原状保存。採用・削除前に確認。
- 初回MVP Pageは接続tool read_pageで取得済み: https://chatgpt.com/space/page_711a9b1ac7d88191a6b0bc313a60db01 。元正本への反映は未実施。

## 編集所有と順序

主担当管理worktree: `feature-mvp-integration-lead`（develop起点）。一括移植をせずPR単位を維持。

| 単位 | 編集所有/場所 | 現在の範囲 | 提供・接続・検証 |
| --- | --- | --- | --- |
| O5コア登録・委任手続 | 主担当worktree、担当をpath別指定 | 独立planと前提PRへ分割するPO委任判断。既存#176一件ステップへの押込みを避ける | 計画作成中。#176のO5製品runner成功は未成立 |
| #175 step3 codec接合 | 分離`feature/mvp-preparing-codec-connection`、product_connection担当 | 保存JSON復元と正式codec接合の2製品パス＋テストのみ | #174固定候補との隔離接続。正式統合とは別記 |
| #176→#174→#173→#175 | 主担当、共有正式資産は直列 | 各最終HEADの独立レビュー・受理・CI後通常merge | 全て未統合。チェック欄だけで成立扱いしない |
| T5/T6・成績CSV | 主担当（今回責任移管） | 既存U-X1と調査・計画候補照合後にstep単位 | 製品未提供。毎球CSVはU-D2調査/計画を再利用（製品実装は未存在） |
| P-6 | 独立役割、既存資料参照 | 封印物/期待値を候補作成担当へ渡さない | 新blind導出未実施。段階B一致を一般化しない |

## 製品到達点と残件

| 到達点 | 実装場所/提供版 | 状態 | 次の証拠 |
| --- | --- | --- | --- |
| A 試合作成・preparing再取得 | #174 resolver後続、#175 components後続、U-F8 | 候補部品あり・実画面→実API→実DB未接続 | 正式codec拒否を先に接合、resolver operation/read route/providerを順次供給 |
| B 開始・権利・1球保存と復元 | U-R1/T1/U-S1/TSK506 | 接合未成立 | 実権利・計算・永続providerを結ぶ |
| C 通常全操作・終了後訂正 | U-F8/T1/T2/U-S1 | 未検証 | 実製品1試合・版一貫性 |
| D 故障・再起動・再送・交代 | U-S1/U-R1 | 部品検査と実DB/HTTPを区別 | 隔離DBの原子性/復旧試験 |
| E 閲覧・基本成績・CSV・負荷 | U-F8/U-D2/T5/T6 | 未接続/未提供を含む | 暦年JST、終了確定版、毎球/成績CSV双方 |
| 実機・運用HTTPS・バックアップ復旧 | 山田正輝（運用責任）/主担当準備 | 未実施 | 実機版と機種、許可済環境を固定。エミュレーションと区別 |

MVP-FR-001〜017 / MVP-NFR-001〜012の個別対応は実装場所確認時にこの台帳へ追記する。現時点で正式受入を推定しない。委任外の未裁定意味、実機/運用資源は具体判断票へ集約予定。Goalは継続中。

## 照合の追記と判断票（2026-10-23）

- `/root/o5_registration`がUR1 manifest全46パスのSHA/集合一致、HEAD一致、後発差分0を確認。status通常36行は未追跡ディレクトリ集約によるもの。旧公開#173との差分を後続の正式受理時に扱う。
- U-F8は封鎖UIの統合と実接続/受入の未着手を分離。9パス追補は旧最終承認待ち、既存追加レビュー残0を保持。US1 C1/F1候補成功はF2/F3の実耐久provider完成を表さない。
- U-D1は544一次引継ぎで未承認計画/製品実装0。毎球CSVもUG1 A01で一時保留/製品0。どちらも実装済みという調査側表示を採用しない。
- TSK-545のE11/E07未裁定表示は2026-10-18の旧状態。T2 post-153引継ぎと `p8-human-decisions-and-receivers-2026-10-18.md`、planはE11=A/E07=B採用済みを保持する。再裁定を求めない。正本/正式契約反映は別条件。545からの個別受領回答は未取得だったため、これから主担当が版を特定して受領範囲を確認する。
- P6はALL-WORK-HANDOFF.txtの資格/封印注意のみ照合。結果JSON/期待値/封印物は未読。主担当・候補担当を新blind検証者にしない。
- 保存codec接合: 隔離候補HEAD `6ddbc341`。実体2パスの新差分だけを独立レビュー（P0/P1/P2=0/0/0）。対象pytest100成功。#174固定codec+#175既存成果を供給した候補で、正式API/DB/画面の成功ではない。patch/bundleはcache保全。正式基線統合後の再接合が必要。
- O5パス宣言: commit `6ca9d157`。対象pytest274成功/Ruff/ty成功。JSON登録は次ステップ、元#176には変更なし。引受通知: https://github.com/masaki1025/pitchlog/pull/176#issuecomment-6364057612 （送付済・受諾未確認）。
- 限定委任手続PR #177はDraftで準備中。計画第1回P1×2/P2×1全採用、第2回0件、PO委任で承認。人間チェックの代記は行わない。

### POの新意味判断を要する事項（同一事項の再照会を避ける）

| ID | 具体例・現在の根拠 | 選択肢と推奨 | 影響・再開条件 |
| --- | --- | --- | --- |
| MVP-D01 | 9回裏2対2→3対2、9回から1点差でコールド可という有効規則。サヨナラとコールドが同時成立。T2引継ぎはoutcome優先だけを未採用と明記。既採用E08はコールド対通常終了だけで、サヨナラには拡張しない | B推奨: walk-off（サヨナラ）を返す。A: cold-end（コールド）を返す。どちらも検知/ロック/宣言促しtrue、自動終了falseは既存方針維持 | 終了理由の正式値・画面表示・契約case/独立期待値が変わる。PO回答後にその範囲だけ正本/契約へ反映。未回答中は仮仕様で確定せず、保存接合・guard等を継続 |

実機/運用資源は製品経路準備と並行で具体化し、利用直前の委任外承認が必要なものだけ同表へ追記する。

## 接続・故障検証の証拠追記

2026-10-23、#174固定HEAD `e30edc79a7f90aa27cb14303910676e414c2cab6`（未コミット差分は既存引継ぎ文書のみ）のbackendで、既存使い捨てPostgreSQL fixtureを使った実DB検査を主担当が実行。Docker Server29.1.3、既存postgres:17.11-bookworm。共有DB/利用者データへ適用なし。

コマンド: `uv run pytest tests/db/test_stage_a_rule_candidates.py -q -k 'formal_stage_a_startup_preserves_closed_publication or formal_stage_a_startup_authz_failure_keeps_placement_closed or stage_a_staged_startup_from_empty_database_and_retry or stage_a_candidate_insert_fault_rolls_back_everything or stage_a_function_candidate_rejects_override_and_guc_mismatch'`

結果: **5 passed, 21 deselected in 33.82s / exit0**。正式段階起動、認可失敗の非公開保持、空DB→配置→再試行、配置途中故障の全取消、override/GUC不一致拒否を実測。DBの独立接続試験であり実HTTP/画面作成成功ではない。O5製品runner/実耐久provider完成/実機受入の代替ではない。

#178コード候補 `719bb308`は独立実装レビュー第1回可決（P0/P1/P2=0/0/0）。reviewer `/root/independent_review`、候補作者 `/root/o5_registration`と主担当。対象base1ab398cc、diff SHA256 `dab69624aad19aeaf093d8fc2968cb165c23808d4a5bbb14fb0bda989546c13f`（git diff --no-ext-diff --binary base head）。JSON登録時の旧試験1件失敗は隠さず51a030d3のステップ1範囲是正に記録し、公開履歴を書き換えていない。最終274件成功・履歴基線成功。root全件は実行中。#177手続実統合後の基線追随と最終版の限定確認を残す。

成績引継ぎ文書・台帳のSHA256はPO提示値とそれぞれ一致。未追跡は引継ぎ2＋候補4の計6文書で原状保存。現候補の配信層をT5/T6実装と混同しない。暦年は既決、登板/打者数など未裁定境界は既採用判断の追加照合を続ける。

### 成績の未裁定境界（既採用判断の照合後）

/root/o5_registrationのread-only照合で、次の意味を一意に定める既採用記録は確認範囲に見つからなかった。D1暦年、率のhalf-up・分母0null→−、既存得点/盗塁の計上原則は再裁定しない。CSV列・分割・表記の具体化は委任内で進める。

| ID | 具体例・選択肢 | 推奨・影響 |
| --- | --- | --- |
| MVP-D02 | 5試合区分を公式/練習へどう対応させるか。A=公式official+semi_official、練習open+intrasquad+other。B=公式officialのみ、練習残4キー。C=公式official+semi、練習open+intrasquad、otherは合算のみ | AをMVP判断案として提示（全5キーを2群に分割できる）。名前だけで採用はしない。全シーズン成績の母集団が変わる |
| MVP-D03 | 登板: 投手として出場し0球で申告敬遠だけを記録。A=投手出場試合1件、B=実投球あり試合だけ1件。再登板を別件に数えるか | A、同一試合の再登板は合計1件を推奨。0球牽制アウト等も同じ出場基準。登板件数が変わる |
| MVP-D04 | 打者数: 2-0で投手交代し救援が四球。A=既存責任帰属（前任1/救援0）、B=打席終了時投手（前任0/救援1） | Aを既存A-2との整合案として提示。A-2自体は走者責任なので自動適用しない。一般標準TBFの断定は根拠にしない。投手別打者数が変わる |
| MVP-D05 | OPS: 3打数1単打、四死球等なし。A=丸め前出塁率+長打率を最後に丸め .667、B=表示済.333+.333=.666 | A推奨。既存half-up/分母0規則を適用し、先頭0・注記は委任で具体化。成績値が変わる |

根拠: 正本183行の5区分、483行は投手交代表示、A-1（0除算/全試合区分）、A-2責任帰属、A-3出塁率/長打率、FR-022のOPS未定義注記。候補decisions.mdの推奨を承認事実として流用しない。

## Must要件ごとの接続状態（初回対応表）

提供部品の存在と正式受入を分ける。下表の『候補』は実接続/正式受入を意味しない。個別の正式受入証拠がないものは未受入とする。

| Page ID | 実装場所・供給単位 | 接続・検証状態 / 残件 |
| --- | --- | --- |
| MVP-FR-001 | develop: api/routers/auth.py、frontend LoginScreen/authStore | チーム共有認証部品あり。今回リハーサル経路未検証 |
| MVP-FR-002 | develop: repositories/roster.py、api/schemas/roster.py | 名簿部品あり。作成/開始への名簿供給と実画面接続未検証 |
| MVP-FR-003 | #174/#175、隔離6ddbc341/b4b8aaf2 | strict codec接合100成功、固定resolver operation69成功。実作成API/DB/画面未完 |
| MVP-FR-004 | U-R1 #173、新5 / U-G1 | 初期権利候補。開始同一取引と再取得の実接合未完 |
| MVP-FR-005 | U-F8 GameScreenPitchEvent / T1 / U-S1 sync | 封鎖UIと同期核部品。実T1計算・Port・保存接合未完 |
| MVP-FR-006 | U-F8 GameScreenSubstitutions / T1/T2 | 交代/特殊進行の候補。7/9回・延長・cold/TBの実製品受入未完 |
| MVP-FR-007 | U-F8 GameScreenUndo/PastCorrection / U-G2 / U-X1 | 候補あり。訂正後状態再導出・成績再集計接続未完 |
| MVP-FR-008 | #153 T2基盤、post-153/TSK545候補、U-G1 | 終了/再開/再終了の実接合未完。MVP-D01のみ新意味回答待ち |
| MVP-FR-009 | U-S1 durable provider F1〜F3、端末キュー | 候補部品。全通常操作の通信断継続は未受入 |
| MVP-FR-010 | 同provider/端末保持、開始時事前取得 | 未送信保持/再起動復元の実画面故障検証未完 |
| MVP-FR-011 | develop sync/apply.py、U-S1/TSK506 | apply核とHTTP候補。実登録/通知/耐久provider/結果不明・再送の受入未完 |
| MVP-FR-012 | U-R1新6、U-S1最終同期 | 通常交代の実2端末・旧権利拒否未検証。緊急交代をMVP受入へ追加しない |
| MVP-FR-013 | U-F8 live display/閲覧入口 | 保存済み版・最終更新時刻・10秒更新の実API接続未完 |
| MVP-FR-014 | U-F8スコア表示、T5、成績配信 | 公式試合成績の製品提供未完。fixture表示だけを完成にしない |
| MVP-FR-015 | 暦年整合4517a33e、T5/T6、成績配信候補 | 暦年は既決。方式/固定ベクタ/投影/集計未実装。D02〜05回答待ち範囲を区別 |
| MVP-FR-016 | U-D2/FR031 | 毎球/プレイCSVの製品実装なし。成績CSVとは別資源 |
| MVP-FR-017 | 基本成績配信候補/新CSV契約 | 製品実装なし。画面と同一対象版・集計条件を維持して供給予定 |
| MVP-NFR-001 | 実画面入力/単一計算 | 実機250球以上のp95/入力15秒測定未実施 |
| MVP-NFR-002 | 同期/サーバー確定時刻 | p95 5秒以内の実負荷測定未実施 |
| MVP-NFR-003 | 保存済み閲覧版 | 保存→閲覧10秒の同時負荷測定未実施 |
| MVP-NFR-004 | 1チーム3試合×記録1+閲覧10 | 同時負荷/15万プレイ規模は未検証 |
| MVP-NFR-005 | iPhone/iPad/Windows Chrome・Edge | 実機未実施。幅調整/ブラウザエミュレーションと区別 |
| MVP-NFR-006 | RLS/認証/記録権 | #174隔離DBでoverride/GUC不一致拒否5件群の一部を実測。全入口/旧端末/複数タブの受入は未完 |
| MVP-NFR-007 | 既存認証・HTTPS運用 | 秘密/鍵新発行なし。チーム用HTTPS配置・運用公開は未実施/委任外判断対象 |
| MVP-NFR-008 | codec拒否/停止/故障表示 | codec100、段階起動DB5の部分証拠あり。保存/同期/CSV/バックアップ全経路は未完 |
| MVP-NFR-009 | 同一取引/apply/冪等 | 規則配置途中故障の全取消を実DB確認。同期イベント/投影/冪等台帳の実原子性・二重適用0件は未受入 |
| MVP-NFR-010 | 運用バックアップ/実復元 | 日次外部バックアップ/RPO24h・アクセス制限の実運用証拠なし |
| MVP-NFR-011 | 復旧世代/RG1/D4 | 設計・候補あり。実台帳/端末保持回収・突合を含む復元演習は未実施 |
| MVP-NFR-012 | 画面自動escape/CSV無害化 | 既存規律維持。実CSV実装後の数式注入/保存XSS回帰と実入口確認は残る |

## 継続運用と連絡（同一台帳へ集約）

- 2026-10-23 PO補足『CIは40分程度』を受領。CI全件はこの所要を前提とし、同じ入力の再実行・短間隔pollを避け、独立作業を継続する。
- #177是正版c32439d7、第2回独立差分レビュー0件。新証拠 https://github.com/masaki1025/pitchlog/pull/177#issuecomment-6364693623 。実無認証API照合成功。GitHub生成マージ候補8e764b48（親1ab/c324）の隔離worktreeでtenant-boundary checkerとcore-guardを実行してexit0。raw単親HEADでPR受理modeを直接実行した際の2親要求拒否は、検査省略で回避せず実merge版で確認した。
- CI run39952551462はcore-guard/tenant-boundary等成功、harness全件待ち。旧run39950625656のCI設定変更起因失敗は履歴保持。是正はCIバイトの基線復元によって外部凍結差分を空にしたもので、8資産の再受理/検査弱体化をしていない。
- P6既存threadへ受領通知を送付。宛先01a15952-4e55-77f1-975b-1b41649d7660、期待値/封印内容の返送や新blind導出は依頼せず、版/資格/手続だけ照会。送付済・受諾未確認。
- 550既存thread01a133de-8208-7660-9105-136ced77cb05へ#176/TSK550主担当引受と並行編集停止維持を通知。追加編集/検査/公開は依頼していない。送付済・受諾未確認。
- T5/T6責任は主担当へ移管済み。現在のD-14-m例外はT1/T2限定なので、T5/T6に同一TS artifactを使う場合は限定正式追補を先行する。手書きの別言語計算/集計で迂回しない。公開artifactはpingのみ、formatter/公式27項目snapshot投影は未提供と確認した。

P6から引継ぎ受領・独立担当継続の実返信を受領。候補編集なし、期待値/封印内容の返送なし。版/範囲メタデータは `/home/ymdms/projects/pitchlog-tsk564-p6-report/20261023-independent-v20-lead-receipt/INPUT-SCOPE-METADATA.json` に固定された。正式受理には権限/対象commit-hash-ID-射影/未検証面/曝露留保/正式case・7.7対応と必要な未曝露担当が残る。受け手を主担当と明示したが、現時点はメタデータ受領だけでP6結果の正式受理・全成立ではない。既存純入力再発行の所在と版だけを追加照会し、新blind導出/比較は依頼していない。

## 再開後の固定点・完走結果

ユーザーの中断/モデル変更希望で編集を停止し、その後『作業を再開』により再開。中断前のCSV計画書は未作成だったため、再開後にrootが計画起案・独立レビュー・承認を行った。

- #177: 最終c32439d7、CI39952551462は全必須成功（frontend/backendは変更検知に基づきskip）。独立差分レビュー第2回0件、証拠6364693623と再照合し、PO委任によるCodex主担当判断で通常merge。正式develop統合は **28c5aee685b3cbf9792e903577fbe79d2dffd7d7**。本人確認や署名を代記していない。
- #178: develop28c5をeceedb4bへ通常mergeで取り込み、O5宣言/登録と#177検査を接合。共有正式凍結資産の値変更なし。接合後core対象356件成功/14.99秒、root Ruff/ty・文書20件0違反・正本突合成功。最終差分独立レビューと新証拠を固定し、必須CI後に通常mergeする。
- ローカル全件（O5コード719bb308・記録追記後、#177取り込み前）: **29,907 passed / 3 failed / 2 skipped / 2596.86秒**。2失敗はbackend/.venv/bin/python FileNotFound、測定スイート1失敗は子スイートexit1。成功へ読み替えていない。uv sync backend後、専用の使い捨てPG17.11（127.0.0.1ランダムport、利用者DB非接続）を用いて同3件だけ再実行し **3 passed/14.45秒/exit0**。単一の全件成功実行を主張しない。ログ: cache/pitchlog/mvp-o5-root-tests.log と mvp-o5-mutation-rerun.log。
- CSV共通部品: root実装7d3b2f18、最終候補762796ee（develop28c5取り込み）。54件成功・独立再実行54成功。最終HEADの第2回独立レビュー0件、diff SHA256263d5918ec978586f779184c38ea6c5d5d5cec1854945e73831248b8da9ad82c。正式資源の提供/実Excel安全性/HTTPダウンロードは未完。
- 新109入力の独立導出候補: fork_turns=none、配布dirだけを許可した/root/p6_fresh_derivationがAを封印。derivation SHA256 bb4fef2d5c73b204f4bfd6feb33329ad562ed824c99850e3fee120150584528d、seal SHA2565434712153b8fc733b78cfcee2e50f8242fc8faa0100076f1913b0ac442f1e76を主担当再計算で照合。可視材料に作者期待値/分類への曝露なしとの資格記録、潜在手掛かり不在は未保証。**新agentという理由だけでblind/P6正式成立を認めない**。対象は旧v2.15/ADR0.8/1e57ff02の109だけ。旧P6担当へBの機械比較を別役割として依頼、旧成果/新封印を変更せず、不足を推測補完しない。新版T1/T2全体成立へ広げない。
- U-S1旧担当から引受了解・停止維持の実回答。F2はe41f7c35の隔離構成承認済み、正本/DDL-ACL/必要7.7のゲートが残る。P7結果ID/wire/O4優先/J6型ACLの最終受理は未取得、B+D/除外Aの方針採用だけを確認。F2準備全体を止める条件へ広げない。

MVP-D01〜05のPO回答は未取得。待ちを承認に置換しない。Goal管理は再開時点でpausedを返すため、実作業の再開と自動継続状態は区別してユーザーへ通知した。
