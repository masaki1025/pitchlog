# 調査レポート: services-shell

## 要約

Tsukuba PSS は st.session_state["page_ctg"] による手書きルーティングの単一 Streamlit アプリで、start→member（スタメン）→main（1球入力）→db_admin/分析系の遷移を game_start フラグ（start/continue）と組み合わせて制御している。中心データは 88列のプレイ行 list（config.py の COLUMN_NAMES/IDX）で、確定済み全行の all_list・現在状態の data_list・作業行の temp_list の3つをセッションに持ち、DB（play_data）と JSON バックアップへ多重永続化しつつ sync_missing_plays で差分同期する。認証は本番が Nginx Basic 認証の X-Remote-User ヘッダ、ローカルが bcrypt＋JWT(HS256,30日) Cookie のフォールバックで、主体は個人でなく「チーム」（game.owner_team_id がテナント境界）。「1つ前に戻す」は DB の MAX(id) 行削除→all_list.pop→スコア逆演算(direction=-1)→update_list 再導出という直前1件限定 undo、途中再開は get_play_list で全行復元し最終行から次状態を導出する方式で、play_editing は記録済みアクションを保持したまま以降の状態だけ前方再計算する修正機能、play_replay は未使用の整合性検証部品である。スタメン画面は試合情報7項目＋打順9人×(守備位置/背番号/氏名)＋投手枠で、背番号入力から名簿 lookup で氏名・左右を毎 rerun 強制導出（氏名欄は実質読み取り専用）し、stamem テーブルに前回スタメンを記憶する。

---

# Tsukuba PSS アプリ骨格 解剖レポート

対象: `C:/develop/baseball_system`（Streamlit 製・1球ごと野球スコアリング）。エントリポイントは `C:/develop/baseball_system/main.py`（`streamlit run main.py`）→ `app.main.run_app()`。

---

## 0. 全体アーキテクチャの要点

- **Streamlit マルチページ機能は不使用**。`st.session_state["page_ctg"]` を使った**手書きルーティング**（単一スクリプト内の if-elif 分岐、`app/main.py` 366〜964行）。ページモジュールは分岐内で遅延 import。
- **中心データ構造は「88列のプレイ行（list）」**。列定義は `C:/develop/baseball_system/config.py` の `COLUMN_NAMES`（88列）と `IDX`（列名→添字）。1球＝1行で、試合メタ・カウント・走者・打撃結果に加え、**その時点のスタメン snapshot（top/bottom の poses/names/nums/lrs）とスコアボード配列（top_score/bottom_score）まで丸ごと1行に埋め込む**非正規化設計。
- 状態遷移は純関数 `domain/game_state.py: update_list(row, ...)`（前のプレイ行→次のプレイ開始状態を計算。カウント・アウト・走者・打順・イニング・試合終了判定 `試合継続='試合終了'` を含む）。UI 層はこれを呼ぶだけ。
- 永続化は `db/game_repo.py`。SQLite / PostgreSQL(Supabase) 切替は `settings.py`（`APP_DB_MODE`）。プレイ行はリスト列を JSON 文字列化して `play_data` テーブルに保存し、読み出し時に `_db_row_to_list` で復元。さらに**試合ごとに `data/game_{id}.json` にファイルバックアップ**（作成・insert・update・削除すべて追随）。
- 分析用 DataFrame は `services/plays_cache.py` の `get_cached_team_plays_df(team_id)`（`st.cache_data ttl=3600, max_entries=16`）に一本化。**DB 変異のたびに `clear_team_plays_cache()` で明示無効化**する規約。
- `services/perf.py`: `APP_PERF_LOG=1` のときだけ `perf_timer(label)` が計測し、logger 出力＋ `st.session_state["_perf_events"]`（最大80件）に蓄積。

---

## 1. ページ構成と遷移フロー

`app/main.py` のページ定数: `start` / `member` / `main` / `db_admin` / `pitcher_analysis` / `pitcher_stats_mode` / `batter_stats_mode` / `batter_analysis_mode` / `score_card`。

```
[未認証] → ログインページ（st.stop）
   │ 認証成功
   ▼
start（スタート）
 ├─ ▶️ 試合開始 ──────────→ member（game_start="start", current_game_id=None, all_list=[]）
 │                              │ 確定（stamem保存 + create_game）
 │                              ▼
 ├─ 📝 入力再開 ─(pending_game_select→試合選択→get_play_list)→ main（game_start="continue"）
 │                              main ─👤交代→ member（game_start="continue"）─確定/キャンセル→ main
 ├─ 🗄️ データ確認 ────────→ db_admin（DB_ADMIN_PASSWORD で別認証）
 └─ 📊 データ分析 ─(pending_analysis_select→5択)→ pitcher_stats_mode / batter_stats_mode /
                                                   pitcher_analysis / batter_analysis_mode / score_card
main のメニュータブ「🏁 入力終了」→ 同期→確認→ reset_game_session_to_start → start
```

- **start ページ**にはこの他に、DB 接続インジケータ（Postgres/SQLite 警告）、ログイン中チーム表示＋ログアウト、使い方ガイド（expander）、**チーム・選手登録**（単発追加＋一括追加テキストエリア、背番号重複時は「修正しますか？」確認フロー）、**チームパスワード変更** expander がある。
- **main ページ**（`app/pages/game_input.py`）は `st.tabs(['メニュー','データ入力','スコアブック','データ一覧'], default=...)` の4タブ。デフォルトタブは `_game_input_default_tab` セッションキーで制御（交代キャンセル後に「データ入力」へ戻す等）。
- 戻り導線: 分析系ページは `app/ui/navigation.py: render_start_button()`（`page_ctg="start"` に戻すだけでログイン・試合状態は保持）。
- **main ページ入場時の癖**: `already_rerun` フラグで**毎回1度だけ強制 `st.rerun()`**（ウィジェット状態安定化のため）。新UIでは不要にすべき挙動。

---

## 2. セッション状態キー一覧と役割（新UIでのクライアント/サーバ配置の判断材料つき）

### 2.1 ルーティング・ナビゲーション（→新UIでは URL/クライアントルータへ）
| キー | 役割 |
|---|---|
| `page_ctg` | 現在ページ（手書きルータの唯一のソース） |
| `game_start` | `"start"`（新規試合セットアップ中）/ `"continue"`（試合進行・再開・交代）。**member ページの挙動を二分する重要フラグ** |
| `pending_game_select` / `pending_analysis_select` | start ページ内の「再開試合選択UI」「分析モード選択UI」表示フラグ |
| `_game_input_default_tab` | main ページのデフォルトタブ指定（1回読み捨て） |
| `_quick_action` | `player_sub`/`delete_last`/`edit_last`/`edit_any` のワンショットコマンド（ボタン→rerun→消費） |

### 2.2 認証（→サーバ側セッション/JWT Cookie）
| キー | 役割 |
|---|---|
| `logged_in_team_id` / `logged_in_team_name` | ログイン中チーム。**全 DB アクセスの owner_team_id として使用** |
| `_logged_out` | ログアウト直後の Cookie 自動復元抑止フラグ |
| `db_admin_authenticated` | DB管理画面の別建てパスワード認証フラグ |
| `db_inited` | プロセス内 DB 初期化・マイグレーション済みフラグ（ログアウト時も温存） |

### 2.3 試合コアデータ（→**サーバ状態。新UIでは DB を単一の真実にすべき領域**）
| キー | 役割 |
|---|---|
| `current_game_id` | 進行中試合の game.id（DB未登録失敗時は None のままメモリ運転） |
| `all_list` | **確定済みプレイ行（88列 list）の全リスト**＝DB `play_data` のメモリミラー。CSV・スコアブック・成績表示の元 |
| `temp_list` | 88列の「作業行」。member ページでスタメン・試合情報を書き込む先。再開時は `all_list[-1]` から複製 |
| `data_list` | main ページの「現在状態行」（=次のプレイの開始状態）。`update_list` の出力を保持し、確定/取消/状況変更のたび更新 |
| `last_confirmed_play_key` | `(game_id, プレイの番号, 回, 表裏)`。**確定ボタン二度押しの重複登録防止** |
| `開始時刻` / `現在時刻` / `経過時間` | 試合開始タグと経過時間（HH:MM:SS 文字列、`services/play_recording.refresh_elapsed_time` が計算） |

### 2.4 派生キャッシュ（→新UIでは不要化 or サーバ側メモ化）
`cached_dataframe` / `cached_all_list_len`（all_list→DataFrame 変換キャッシュ、長さ比較で無効化）、`cached_df_for_season` / `cached_df_for_season_n`（DB全試合＋当該セッション結合のシーズン成績用 DataFrame）、`_perf_events`。

### 2.5 データ入力ウィジェット状態（→**純クライアント状態にすべき領域**）
`打撃結果`（'0'=未入力の中枢フラグ）、`result_ctg`、`batting_result_cont/k/bb/out/hit/miss/sac`、`radio_selection`（構えの大分類）、`stance_1ba`〜`stance_3bc`、`構え`/`構え_aim`、`pitch_type`、`pickoff_selection`（投手牽制）、`catcher_pickoff`、`intentional_walk_without_pitch`、`pitch_clock_violation_without_pitch`、`first_num`/`second_num`/`speed_100s`/`球速`、`strategy`/`strategy2_steal|bunt|endrun`/`strategy_result_*`、`press`、`other_result`、`ball_type`/`ball_speed`/`fielder`、`error_player`/`エラー選手`、`runner_0_state`〜`runner_3_state`、`reset_flag`（確定後にラジオ群を初期化する描画前フック）、`_prev_runner_suggestion_signature`（走者自動提案の再適用判定シグネチャ）、`_fielder_auto_signature`（打球位置→捕球選手自動推定の再適用判定）、`already_rerun`。コースマップ/フィールドマップ用に `latest_clicked_point`・`image_clicker_key_counter`・`field_image_key_counter`（`app/ui/plate.py`/`field.py` の clear_canvas がカウンタを回して再マウント）。

### 2.6 スタメン（member）ページ
`top_team`/`bottom_team`、`select_top_team`/`select_bottom_team`、`_prev_top_team`/`_prev_bottom_team`（チーム変更検知→ウィジェットキー掃除→rerun）、`_stamem_loaded_top`/`_stamem_loaded_bottom`（チームごと1回だけ DB 保存スタメンでウィジェットを強制初期化）、`top_pos_{0..8}`/`top_num_{0..9}`/`bottom_pos_{0..8}`/`bottom_num_{0..9}`、動的キー `f"{side}_{チーム名}_{背番号}_{i}"`（氏名欄）、試合情報 `game_試合日時`/`game_主審`/`game_Season`/`game_Kind_sel`/`game_Kind`/`game_Day`/`game_Week`/`game_GameNumber`、`member_add_*`/`member_add_duplicate`/`player_add_duplicate`/`bulk_add_success`、`member_df`（全チーム選手の DataFrame。選手追加・削除のたび None にして再ロード）。

### 2.7 修正モード・終了処理・エラー通知（ワンショット表示系）
`show_last_play_editor`/`show_any_play_editor`、`edit_any_*`（フィルタ・保存範囲・確認チェック）、`_last_play_edit_success|error`/`_any_play_edit_success|error`、`_db_insert_error`/`_db_delete_error`（DB失敗の pop 表示）、`_pos_warning`/`_just_did_substitution`（守備位置不足チェック）、`_game_end_sync_done`/`_game_end_sync_result`、状況変更/タイブレーク系 `tiebreak_*`。管理画面は `csv_selected_game_ids`/`del_selected`/`del_player_selected`/`db_admin_*`。

**新UI設計への示唆**: `all_list`/`data_list`/`temp_list` の3枚看板が最大の負債。DB には全プレイがあるのに、メモリミラー（all_list）＋現在状態（data_list）＋作業行（temp_list）を手動同期しており、`sync_missing_plays` や「DB とメモリの直前プレイ番号一致チェック」などの防御コードが至る所にある。新UIでは「現在状態＝最終プレイ行から `update_list` で導出（サーバ計算）」「入力途中の値＝クライアント」「確定行＝DBのみ」に分離するとこの複雑さの大半が消える。

---

## 3. 認証の仕組みとユーザーモデル

### 認証フロー（`app/main.py` 313〜350行、`auth.py`、`settings.py`）
1. **本番**: Nginx Basic 認証が付与する `X-Remote-User` ヘッダ（`st.context.headers`）→ その値＝**チーム名**として `team` テーブルを引き、`logged_in_team_id/name` をセット。DB に無ければエラーで停止。ローカルは `DEV_USER` 環境変数でも代替可。ログアウトは `ClearAuthenticationCache` ＋ 無効 Authorization ヘッダ fetch の JS ハック。
2. **ローカル/フォールバック**（`ENABLE_COOKIE_AUTH=1` のとき）: `streamlit_cookies_controller` で Cookie `tsukuba_pss_auth` を読み、**JWT（HS256, `JWT_SECRET_KEY`, 有効期限30日）** を `auth.verify_token` で検証して復元。未認証ならチーム選択＋パスワードのログインページ（`_login_page`）を表示して `st.stop()`。ログイン成功時に `auth.create_token(team_id, team_name)` を Cookie 保存（30日）。ログアウトは Cookie 削除＋ `st.session_state.clear()`（`db_inited` のみ温存）＋ `_logged_out` フラグ。
3. パスワードは **bcrypt**（`auth.hash_password`/`check_password`）。`team.password_hash` に保存。ログインページから**新規チーム自己登録**も可能。初期パスワードは環境変数 `INITIAL_TEAM_PASSWORDS`（JSON）から未設定チームにのみ一括投入。

### ユーザーモデル
- **認証主体は「チーム」であり個人ユーザーではない**。JWT ペイロードは `{team_id, team_name, exp}`（`user_id`/`username` はオプション引数として実装済みだが、現行ログインフローでは未使用）。
- `user_account` テーブル（id, username, password_hash, team_id, created_at）と `db/user_repo.py` は存在し、管理画面（admin タブ8）に一覧・削除 UI があるが、**ログインには使われていない**（将来の個人アカウント化の布石とみられる）。
- **データ分離**: `game.owner_team_id` が唯一のテナント境界。`game_repo` の read/write 全関数が `owner_team_id` を受け取り、SQL サブクエリまたは `_assert_owner`（PermissionError）で強制。分析キャッシュも team_id キー。
- **管理画面は別建て認証**: `DB_ADMIN_PASSWORD`（env/secrets）と `hmac.compare_digest` の平文比較。チームログインとは独立。

---

## 4. 試合ライフサイクル（開始・再開・終了）

### 開始
1. start「試合開始」: `page_ctg="member"`, `game_start="start"`, `current_game_id=None`, `all_list=[]`, `_stamem_loaded_*` 削除。
2. member ページで試合情報＋スタメン入力 → 「確定」で
   - 両チームのスタメンを `player_repo.save_stamem_by_team_name` に保存（保存後に読み戻し確認）。
   - `game_repo.create_game(...)`: `game` 行 INSERT（owner_team_id 付与）＋ `data/game_{id}.json` バックアップ作成。**DB 登録失敗でも warning のみで続行**（current_game_id=None のままメモリ運転）。
   - `current_game_id=gid`, `all_list=[]`, `game_start="continue"`, `page_ctg="main"`。
3. main ページ入場時、`temp_list` 未生成なら `all_list[-1].copy()` か `build_initial_temp_list()`（この場合 `get_game_teams` でチーム名を補完）。
4. **開始時刻は自動記録されない**。メニュータブ「▶ 試合開始（開始時刻を記録）」で `services/game_lifecycle.record_game_start_time`（HH:MM:SS を `開始時刻` にセット）。未押下だと経過時間が "0:00" のまま（確定バリデーションで検査対象）。

### 再開（途中再開の実装方式）
- start「入力再開」→ `pending_game_select` → `game_repo.list_games(team_id)` から選択 → `get_play_list(gid, owner_team_id)`（`プレイの番号` 順の全行、JSON列を list に復元）を `all_list` に投入、`current_game_id=gid`、`temp_list` 削除、`page_ctg="main"`。
- main 側では `temp_list = all_list[-1]` を種に `update_list` で「最後のプレイの次の状態」を再計算して `data_list` を作る。**つまり再開＝最終行からの状態導出であり、リプレイ全再計算ではない**（各行に累積状態が保存されているため最終行だけで足りる）。
- **セッション切れ復旧**: PAGE_MEMBER の continue 分岐に「`all_list` が空でも `current_game_id` があれば DB から `get_play_list` で復元」するリカバリコードあり（`app/main.py` 880〜899行）。どちらも無ければ start へ強制送還。

### 終了
- メニュー「🏁 入力終了」→ `prepare_game_end_sync` → `game_repo.sync_missing_plays(gid, all_list)`: **DB に無い `プレイの番号` の行だけ INSERT**（1件失敗しても続行し最後に例外集約）。結果を `_game_end_sync_result` に格納して確認画面（成功件数/エラー表示）→「スタートへ戻る」で `reset_game_session_to_start`: `GAME_END_RESET_KEYS`（data_list, all_list, temp_list, current_game_id, スタメン8配列, スコア, 時刻3種, runner_state, 各種フラグ計36キー）を一括 pop し `page_ctg="start"`, `game_start="continue"`。
- **DB 上に「試合終了」フラグは書かれない**。試合終了はプレイ行の `試合継続` 列（`domain/game_end_rules.should_finish_game` が `update_list` 内で判定）にのみ現れ、UI は `試合継続=='試合終了'` なら確定ボタンを隠して案内を出す。`game` テーブルにステータス列は無い。
- 手動同期ボタン「DBに同期（未送信プレイを送信）」も同じ `sync_missing_plays` を使用（保存失敗後のリカバリ手段）。

---

## 5. play_recording / play_editing / play_replay の責務

### `services/play_recording.py` — 確定と「1つ前に戻す」
- `build_confirmed_play_row(**88項目)`: キーワード引数から 88列行を組み立て、列数検証。
- `make_play_key` / `is_duplicate_play`: `(gid, プレイの番号, 回, 表裏)` と `last_confirmed_play_key` の比較で**ダブルクリック二重登録防止**。
- `record_confirmed_play`: ①`persist_play`（`insert_play` を DB へ。**失敗しても例外にせずエラーメッセージを `_db_insert_error` に格納し、メモリには必ず append**＝オフライン継続方針）②`mark_confirmed_play`（all_list へ append、キャッシュ長無効化）③`refresh_elapsed_time`。成功時は `clear_team_plays_cache()`。
- **確定ボタンの全体フロー**（`game_input.py` 1563〜1668行）: `validate_play_confirmation`（domain/input_validation。開始時刻・コース・球種・打球情報などの必須チェック）→ 重複チェック → 行構築 → `record_confirmed_play` → `apply_scoreboard_event`（domain/scoreboard、得点加算 direction=+1）→ `update_list` で次状態を計算 → イニング交代時の守備位置不足警告 → `data_list` 更新 → `reset_confirm_input_state`（打撃結果='0' ほか入力ウィジェット状態を一掃）→ plate/field キャンバス clear → rerun。
- **「1つ前に戻す」（↩ 戻る → `_quick_action='delete_last'`、`game_input.py` 505〜573行）は DB 先行の2段階**:
  1. `delete_persisted_last_play` → `game_repo.delete_last_play`: `play_data` の **MAX(id) 行を DELETE**（play_player_link も先に削除、owner 検査つき、対象0行なら RuntimeError）。**DB 削除に失敗したらメモリは触らず中断**（`st.stop()`）。
  2. 成功後 `pop_last_confirmed_play`（all_list.pop）→ 取り消した行の内容で `apply_scoreboard_event(direction=-1)` により**得点・スコアボードを逆演算で減算** → `build_revert_base_row`（all_list が残っていれば `all_list[-1]` を、全削除なら temp_list の deepcopy に得点/スコアをパッチした行を基底に）→ `update_list` で現在状態を再導出 → `reset_revert_input_state`（last_confirmed_play_key や走者選択などを掃除）→ キャンバス clear → rerun。
  - つまり **undo は「直前1件のみ・スタック無し」**。多段 undo は「もう一度押す」ことで実現（毎回 DB の MAX(id) を消す）。
- `refresh_elapsed_time`: 現在時刻−開始時刻（日跨ぎは+1日補正）。

### `services/play_editing.py` — 保存済みプレイの安全な修正
- `EDITABLE_FIELD_INDEXES`: 修正可能14項目（球種・球速・打撃結果1/2・打球タイプ・捕球選手・打者/一二三走状況・コースXY・打球位置XY）。`build_updated_play_row` が deepcopy＋`derive_plate_result`（打席結果の表示名を打撃結果から再導出）。
- **前方再計算** `recalculate_play_rows_from_edit(plays_with_id, edited_play_id, edited_row)`: 編集行以降を「`_next_base_row`（前行に `update_list` を適用した次状態）に、元行の**記録済みアクション項目**（`PLAY_EFFECT_FIELD_INDEXES`: 打席の継続・作戦・状況・球種・結果・打球・牽制・球速など33項目）だけを `_merge_recorded_play_effect` で上書き」して連鎖再構築。**「何をしたか」は保存値を尊重し、「その結果のスコア・カウント・走者・打順」だけ再計算**する設計。
- `apply_lineup_snapshot_from_play`: 交代入力忘れの遡及反映。現在の `temp_list` のスタメン snapshot を指定プレイ以降へ side（先攻/後攻/両方）単位でコピーし、`refresh_play_identities_from_lineup` で打者・投手・捕手・走者の氏名/背番号/左右を snapshot から引き直して前方再計算。
- `build_recalculation_preview` / `build_play_edit_diff`: 保存前の before/after 差分表（プレイID・項目・修正前後）。
- `replace_last_play_in_session` / `replace_play_in_session_by_number`: メモリ側 all_list の該当行差し替え＋派生キャッシュ4キー破棄。
- **UI 側**（`app/pages/game_input_edit.py`）:
  - 「✏️ 直前修正」: セッション最終行と DB 最終行の `プレイの番号` 一致を検査してから通常入力と同じ盤面（コース/フィールドマップ含む）で1行だけ `game_repo.update_play`。
  - 「🔎 過去修正」: 回/表裏/打者/投手フィルタ→プレイ選択→保存範囲を「この1行だけ」or「このプレイ以降を再計算して更新」（`update_plays` 一括UPDATE、差分プレビューと確認チェック必須）。さらに「メンバー表をこのプレイ以降に反映」機能。
  - 「🔧 状況変更」expander: `apply_manual_state_change`（イニング・表裏・得点・SBO・打順・走者打順の手動上書き→update_list）と**タイブレーク開始**（`apply_tiebreak_state`、開始回・先頭打者・走者配置・開始アウト）。これは**メモリの data_list のみ変更**で DB は書かない。

### `services/play_replay.py` — 整合性検証（リプレイ）
- `validate_replay_consistency(plays_with_id)`: 先頭行を種に全行を `_next_base_row`＋`_merge_recorded_play_effect` で頭からリプレイし、保存値と再計算値の不一致（回・表裏・得点・S/B/アウト・打順・走者打順）と**カウント上限違反**（S>2, B>3, アウト>2）を `{play_id, field, saved, replayed, reason}` のリストで返す。
- **現状 UI からは未使用**（`tests/test_play_replay.py` のみ）。新UIでは保存データの健全性チェック・修正候補提示に転用できる部品。

---

## 6. スタメン入力画面（`app/pages/lineup.py: member_page`）の全入力項目と自動補完

### 入力項目一覧
**A. 試合情報（`game_start=="start"` のときだけ表示、7カラム）**
| 項目 | ウィジェット | 選択肢/形式 |
|---|---|---|
| 日時 | text_input (`game_試合日時`) | 例 `2025/03/15`。**未入力だと確定を拒否** |
| 主審 | text_input (`game_主審`) | 自由入力 |
| Season | selectbox (`game_Season`) | 春季/夏季/秋季/冬季 |
| Kind | selectbox (`game_Kind_sel`) | 全国大会/関東大会/リーグ戦/準公式戦/A〜Cオープン戦/A〜C紅白戦/部内リーグ/その他（その他選択時は自由入力 `game_Kind`） |
| Day / Week / GN | selectbox | Day 0–4 / Week 0–12 / GameNumber 0–4 |

**B. 選手を追加登録（expander）**: チーム／背番号／名前／左右（`PLAYER_SIDE_OPTIONS`＝右/左/両）。背番号重複時は既存選手名を出して「登録内容を修正する/キャンセル」の確認（`member_add_duplicate`）。

**C. スタメン本体（先攻・後攻の左右2カラム、構造は対称）**
- チーム選択: `game_start=="start"` のみ selectbox（`select_top_team`/`select_bottom_team`）。**交代モードでは temp_list[8]/[7] から固定表示**（変更不可）。
- 名簿一覧: 当該チームの `member_df`（背番号/名前/左右）を `st.dataframe(height=550)` で参照表示。
- 打順1〜9の**守備位置** selectbox ×9（key `top_pos_{i}` 等）: 選択肢は表裏に依存 — **攻撃側の交代時は `[現値, 'H', 'R']`（代打/代走のみ）**、それ以外は `[現値, 2,3,4,5,6,7,8,9,'D','P']`。10行目はラベル固定「P」（投手枠）。
- **背番号** text_input ×10（打順9人＋投手、key `top_num_{i}`）。
- **氏名** text_input ×10（動的キー `f"top_{チーム名}_{背番号}_{i}"`）。

### 自動補完（背番号→名前・左右）の実装方式
1. `member_df` から当該チーム分を絞り、`{背番号(str): (名前, 左右)}` の lookup 辞書を構築。
2. 背番号 text_input の値でこの辞書を引き、`top_names[i]`（無ければ ''）と `top_lrs[i]` を決定。
3. 氏名欄は**描画前に `st.session_state[動的キー] = lookup結果` を毎 rerun 強制代入**してから `text_input(key=...)` を描画。つまり氏名欄は編集可能に見えるが**実質は背番号から導出される読み取り専用**（手入力は次の rerun で lookup 値に上書きされる。名簿に無い背番号なら空欄）。左右は UI に出ず、確定時に member_df から背番号で再導出。
4. 確定時 `_build_from_session` が session_state のフォームキーから poses/nums/names/lrs を再構築（チーム名の前後空白差異のフォールバックキーも参照）。

### 初期値ロードとキャッシュ
- `get_member_data(チーム名)`（`st.cache_data ttl=60`）が `player_repo.get_stamem_by_team_name` から**前回保存スタメン（stamem テーブル）**を取得。無ければ `config.py` の DEFAULT_* プレースホルダ。
- `_stamem_loaded_top/bottom` フラグにより「チームごとに1回だけ」ウィジェットキーへ強制上書き（ユーザー編集後は上書きしない）。チーム変更検知（`_prev_top_team` 比較）時は `top_pos_*`/`top_num_*` を全削除＋キャッシュクリア＋rerun して新チームの値で再初期化。
- 守備配置の派生: `top_names` は20要素に拡張され、poses が 2〜9 の選手名を `names[10..17]` にコピー（守備位置→選手の逆引き。`names[9]`=投手、`names[10]`=捕手として game_input 側が参照）。

### 確定処理
両チームの stamem 保存（読み戻し検証つき）→（start 時のみ）`create_game` → `game_start="continue"`, `_just_did_substitution=True`（main 側で守備位置不足 2〜9 の欠落チェック警告）→ `page_ctg="main"` → rerun。キャンセルは start モードなら `reset_game_session_to_start`＋セットアップキー全削除、交代モードならフォームキー掃除のみで main の「データ入力」タブへ復帰。

---

## 7. 新UI設計者向け・要注意ポイント（発見事項）

1. **temp_list の添字直書き**が main.py に散在（`t[78:86]`, `t[7:9]=後攻,先攻`, `t[27]/t[28]/t[32]/t[33]/t[35]` 等）。列 7/8 が「後攻, 先攻」の順である点に注意。main.py 871行では start モードで `initial_top_names`（DEFAULT 値）を打者名に入れており、更新後の値ではない（実害は update_list 側の再導出で吸収されている模様）。
2. **状況変更・タイブレークは DB に書かれない**（data_list のみ）。以後のプレイ確定行に反映される間接方式のため、新UIでは監査可能なイベントとして永続化を検討すべき。
3. **オフライン耐性の設計**: insert 失敗→メモリ保持＋手動/終了時 `sync_missing_plays`（プレイの番号差分で補完）。undo は DB 先行。JSON ファイルバックアップも並走。新UIの同期プロトコル設計の参考。
4. **開始時刻の手動記録**が運用上の最大の落とし穴（ガイドで「必ず押す」と強調）。新UIでは自動化候補。
5. 使い方ガイドの記述（メニューに「1つ削除」「状況変更」等）と実装（データ入力タブ内のクイックアクション4ボタン＋expander）が乖離している。
6. `all_list` の行には**スタメン配列とスコア配列が毎行 deepcopy で埋まる**ため、1試合300球でメモリ・転送量が嵩む。新UIのデータモデル正規化の主対象。
7. 認証は「チーム＝アカウント」。個人ユーザー（user_account）と JWT の user_id/username 拡張は未接続の将来布石。

