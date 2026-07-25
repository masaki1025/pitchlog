# 調査レポート: data-layer

## 要約

Tsukuba PSSのデータ層を全ファイル読解し、12テーブルの完全スキーマ（SQLite/PostgreSQL両対応、外部キーCASCADEなし・日時は全てTEXT）、play_dataの88カラムの意味と値例、APP_DB_MODE+_PgCursorWrapper（?→%s変換・識別子クオート・lastval()によるlastrowid偽装）による DB 切替機構、8リポジトリ約50関数のCRUDカタログを整理した。README未掲載のカルテ（pitcher/batter_karte_note の payload_json 構造）、コメント、team_theme、play_player_link、game_<id>.json二重書き込みも解剖した。重大な罠として「タイムの種類」列に実際はエラー選手（守備番号1-9）、「打席Id」列にフリーコメントが格納される列名ズレ、SELECT *の位置依存復元、owner_team_idが省略可能な所有権ガードを特定した。FastAPI再利用にはstreamlit依存（st.cache_resourceのPGプール・st.secrets）の除去、同期psycopg2プール(最大3)の拡張、冪等キー（プレイの番号にUNIQUE制約なし）の導入が必要。

---

# Tsukuba PSS データ層 解剖レポート（新UIバックエンドAPI設計 基礎資料）

調査対象: `C:/develop/baseball_system/config.py`, `C:/develop/baseball_system/settings.py`（切替機構の実体）, `C:/develop/baseball_system/db/` 配下全ファイル。補助的に `services/play_recording.py`, `domain/*.py`, `app/pages/game_input.py`, `README.md` を参照（値の実例確認のため）。すべて読み取りのみ。

---

## 1. 全テーブルスキーマ

テーブルは全12種。DDL の一次ソースは2つあり、**内容は一致している**（SQLite: `db/schema.py` の `init_db()` + `migrate_*` 関数群 / PostgreSQL: `db/supabase_schema.sql`）。

- SQLite: `INTEGER PRIMARY KEY AUTOINCREMENT` / PostgreSQL: `SERIAL PRIMARY KEY`
- PostgreSQL 側では大文字混在カラム（`Season`, `Kind`, `S`, `B`, `Result_col` 等）と一部日本語カラム（`試合日時`, `回`, `コースX`, `コースY`, `名前`, `チーム_id`）がダブルクオート付きで定義されている
- **外部キーに ON DELETE CASCADE は一切ない**（削除順は手動制御）。SQLite では接続ごとに `PRAGMA foreign_keys = ON`
- 日時カラムはすべて `TEXT`（ISO文字列、タイムゾーンなし）

### 1.1 team（チームマスタ）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL / INTEGER AUTOINCREMENT | PK |
| 名前 | TEXT | UNIQUE NOT NULL |
| password_hash | TEXT | NULL可（bcrypt。マイグレーション `migrate_add_team_password` で追加） |

### 1.2 player（選手マスタ）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| チーム_id | INTEGER | NOT NULL, FK→team(id) |
| 背番号 | TEXT | NOT NULL（文字列。数値ソートは CAST で対応） |
| 名前 | TEXT | NOT NULL |
| 左右 | TEXT | NOT NULL（"右"/"左"/"両" — `domain/player_side.py` の `PLAYER_SIDE_OPTIONS`） |
| — | — | UNIQUE(チーム_id, 背番号) |

### 1.3 stamem（スタメン記憶）
| カラム | 型 | 制約 |
|---|---|---|
| チーム_id | INTEGER | **PK**, FK→team(id)（1チーム1行） |
| poses / names / nums / lrs | TEXT ×4 | NOT NULL。**JSON文字列**（配列）で保存 |

### 1.4 game（試合）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| 試合日時 | TEXT | NOT NULL（例 "2026/07/09"） |
| Season / Kind / Week / Day / GameNumber | TEXT ×5 | 任意（例: Season=春季/夏季/秋季/冬季、Kind=リーグ戦/Aオープン戦等、Week=0〜12、Day・GameNumber=0〜4） |
| 主審 | TEXT | 任意 |
| 先攻チーム_id / 後攻チーム_id | INTEGER | NOT NULL, FK→team(id) |
| owner_team_id | INTEGER | NULL可, FK→team(id)。**マルチテナント境界**（データを所有するチーム）。`migrate_add_game_owner` で追加 |
| 開始時刻 / 現在時刻 / 経過時間 / created_at | TEXT ×4 | 任意 |

### 1.5 play_data（毎球データ、1プレイ=1行、88列+id+試合_id）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| 試合_id | INTEGER | NOT NULL, FK→game(id) |
| （以下88列） | — | 詳細は §2。制約なし・全列NULL可 |

### 1.6 play_player_link（プレイ⇄選手の正規化リンク）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| play_data_id | INTEGER | NOT NULL, FK→play_data(id) |
| role | TEXT | NOT NULL（"batter" / "pitcher" / "runner1" / "runner2" / "runner3" — `game_repo._PLAY_PLAYER_ROLE_SPECS`） |
| player_id | INTEGER | NOT NULL, FK→player(id) |
| created_at | TEXT | |
| — | — | UNIQUE(play_data_id, role) |

生成は `game_repo._recreate_play_player_links()` による **best-effort**（背番号+氏名がチーム内で一意に解決できた場合のみ INSERT。失敗してもプレイ保存は成功する）。よって欠損があり得る。

### 1.7 user_account（ユーザー）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| username | TEXT | UNIQUE NOT NULL |
| password_hash | TEXT | NOT NULL（bcrypt — `auth.py`） |
| team_id | INTEGER | NOT NULL, FK→team(id)（所属チーム） |
| created_at | TEXT | |

### 1.8 pitcher_comment（投手フリーコメント）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| team_id | INTEGER | NOT NULL, FK→team(id)（※コメントを書く側=オーナーチーム） |
| pitcher_name | TEXT | NOT NULL（**選手IDではなく氏名文字列で紐付け**） |
| comment | TEXT | NOT NULL DEFAULT '' |
| — | — | UNIQUE(team_id, pitcher_name) |

### 1.9 batter_comment（打者フリーコメント）
pitcher_comment と同型（`batter_name`）。UNIQUE(team_id, batter_name)。

### 1.10 pitcher_karte_note（投手カルテ・構造化ノート）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| owner_team_id | INTEGER | NOT NULL, FK→team(id) |
| target_team_name | TEXT | NOT NULL（**対象チームは名前文字列**、FKなし） |
| pitcher_name | TEXT | NOT NULL |
| payload_json | TEXT | NOT NULL DEFAULT '{}'（構造は §5） |
| updated_at | TEXT | ISO秒精度 |
| — | — | UNIQUE(owner_team_id, target_team_name, pitcher_name) |

### 1.11 batter_karte_note（打者カルテ・構造化ノート）
pitcher_karte_note と同型（`batter_name`）。

### 1.12 team_theme（カルテ帳票のチーム別カラーテーマ）
| カラム | 型 | 制約 |
|---|---|---|
| id | SERIAL | PK |
| owner_team_id | INTEGER | NOT NULL, FK→team(id) |
| target_team_name | TEXT | NOT NULL |
| palette_key | TEXT | NOT NULL DEFAULT 'navy_red'（有効値は §5.3） |
| updated_at | TEXT | |
| — | — | UNIQUE(owner_team_id, target_team_name) |

### 1.13 インデックス（`migrate_add_indexes` / supabase_schema.sql 末尾、両DB同一）
- `idx_play_data_game_id` … play_data(試合_id)
- `idx_play_data_game_play_number` … play_data(試合_id, プレイの番号)
- `idx_game_owner_team_id` … game(owner_team_id)
- `idx_game_owner_id` … game(owner_team_id, id)
- `idx_game_top_team_id` / `idx_game_bottom_team_id` … game(先攻チーム_id / 後攻チーム_id)
- `idx_play_player_link_play_data_id` / `idx_play_player_link_player_id`

### リレーション図（テキスト）
```
team 1─* player ─* play_player_link *─1 play_data *─1 game *─1 team(先攻/後攻/owner)
team 1─1 stamem
team 1─* user_account
team(owner) 1─* pitcher_comment / batter_comment        （選手は氏名文字列参照）
team(owner) 1─* pitcher_karte_note / batter_karte_note   （対象チーム・選手とも文字列参照）
team(owner) 1─* team_theme                                （対象チームは文字列参照）
```

---

## 2. play_data の88カラム完全リスト

出典: `config.py` の `COLUMN_NAMES`（アプリ内メモリ表現の並び順）と `IDX`。DB型は `db/schema.py` L650-672 / `supabase_schema.sql`。デフォルト値は `config.build_initial_temp_list()` を実行して確認した実値。DB保存時は `game_repo._row_to_db()` が空文字→NULL 変換、リスト系10列を JSON 文字列化する。

**重要な物理名と実データの食い違い（§7 も参照）:**
- **列55「タイムの種類」には実際は「エラー選手」（エラーした野手の守備番号1-9）が入る**（`services/play_recording.build_confirmed_play_row` が55番目にエラー選手を渡す。`analytics/cal_stats.py` も `タイムの種類.isin([1..9])` でエラー数を数えている）
- **列60「打席Id」には実際はフリーテキストの「コメント」が入る**（同上、60番目にコメントを渡す）

| # | カラム名 | DB型 | 意味 | 値の例 / 初期値 |
|---|---|---|---|---|
| 0 | 試合日時 | TEXT | 試合日付 | "2026/07/09"（初期値=当日） |
| 1 | Season | TEXT | シーズン | "春季"/"夏季"/"秋季"/"冬季"（初期 ""） |
| 2 | Kind | TEXT | 試合種別 | "リーグ戦"/"全国大会"/"Aオープン戦" 等（初期 ""） |
| 3 | Week | TEXT | 週番号 | "0"〜"12"（初期 ""） |
| 4 | Day | TEXT | 日番号 | "0"〜"4"（初期 ""） |
| 5 | GameNumber | TEXT | 試合番号 | "0"〜"4"（初期 ""） |
| 6 | 主審 | TEXT | 主審名 | 初期 "" |
| 7 | 後攻チーム | TEXT | 後攻チーム名 | 初期値は文字列 "先攻チーム"（**プレースホルダが名前と逆**。スタメン確定時に実チーム名で上書き） |
| 8 | 先攻チーム | TEXT | 先攻チーム名 | 初期値は文字列 "後攻チーム"（同上） |
| 9 | プレイの番号 | INTEGER | 試合内の通しプレイ番号（同期・重複判定キー） | 0,1,2,…（初期 0） |
| 10 | 回 | INTEGER | イニング | 1〜（初期 1） |
| 11 | 表.裏（DB列名は「表裏」） | TEXT | 表/裏 | "表"/"裏" |
| 12 | 先攻得点 | INTEGER | 先攻の累計得点 | 初期 0 |
| 13 | 後攻得点 | INTEGER | 後攻の累計得点 | 初期 0 |
| 14 | S | INTEGER | ストライクカウント | 0-2（初期 0） |
| 15 | B | INTEGER | ボールカウント | 0-3（初期 0) |
| 16 | アウト | INTEGER | アウトカウント | 0-2（初期 0） |
| 17 | 打席の継続 | TEXT | 打席状態フラグ | "打席継続"/"打席完了"（`domain/game_state.py`） |
| 18 | イニング継続 | TEXT | イニング状態フラグ | "イニング継続"/"イニング開始"/"試合終了" |
| 19 | 試合継続 | TEXT | 試合状態フラグ | "試合継続"/"試合終了"（`domain/game_end_rules.GAME_FINISHED`） |
| 20 | 一走打順 | INTEGER | 一塁走者の打順 | 0=走者なし、1-9 |
| 21 | 一走氏名 | TEXT | 一塁走者名 | 初期 "" |
| 22 | 二走打順 | INTEGER | 二塁走者の打順 | 同上 |
| 23 | 二走氏名 | TEXT | 二塁走者名 | |
| 24 | 三走打順 | INTEGER | 三塁走者の打順 | |
| 25 | 三走氏名 | TEXT | 三塁走者名 | |
| 26 | 打順 | INTEGER | 現打者の打順 | 1-9（初期 1） |
| 27 | 打者氏名 | TEXT | 現打者名 | 初期 "先攻1" |
| 28 | 打席左右 | TEXT | 打席の左右（両打ちは打席ごとに決定） | "右"/"左" |
| 29 | 作戦 | TEXT | 作戦大分類 | "0"/"盗塁"/"バント"/"エンドラン" |
| 30 | 作戦2 | TEXT | 作戦詳細 | 盗塁系: "盗塁"/"ディレード"/"Wスチール"、バント系: "バント"/"打からバント構え"/"セフティ"/"スクイズ"/"バスター"/"Sスクイズ"、エンドラン系: "HAR"/"RAH"/"BAR"/"BSAR" |
| 31 | 作戦結果 | TEXT | 作戦の結果 | "0"/"成功"/"失敗"/"盗塁成功" |
| 32 | 投手氏名 | TEXT | 投手名 | 初期 "後攻P" |
| 33 | 投手左右 | TEXT | 投手の利き腕 | "右"/"左" |
| 34 | 球数 | INTEGER | 投手の累計球数 | 初期 0 |
| 35 | 捕手 | TEXT | 捕手名 | 初期 "後攻C" |
| 36 | 一走状況 | TEXT | 一塁走者の結果 | "0"/"継続"/"二進"/"三進"/"本進"/"封殺"/"投手牽制死"/"捕手牽制死"/"盗塁死"/"走塁死" |
| 37 | 二走状況 | TEXT | 二塁走者の結果 | "0"/"継続"/"三進"/"本進"/封殺系同上 |
| 38 | 三走状況 | TEXT | 三塁走者の結果 | "0"/"継続"/"本進"/封殺系同上 |
| 39 | 打者状況 | TEXT | 打者の結果 | "アウト"/"出塁"/"二進"/"三進"/"本進"/"継続"/"封殺"/牽制死・盗塁死・走塁死 |
| 40 | プレイの種類 | TEXT | このプレイ行の種別 | "投球"（初期値）/"牽制"/"ボーク"/"ピッチクロック違反" |
| 41 | 構え | TEXT | 捕手の構え位置 | 1-25 のゾーン番号（5×5グリッド、UIでは '--','3高','中中' 等の表現も使用）。初期 0 |
| 42 | コースX | REAL | 投球コースX座標（ストライクゾーン画像クリック） | ピクセル座標。初期 0 |
| 43 | コースY | REAL | 投球コースY座標 | 同上 |
| 44 | 球種 | TEXT | 球種コード | "FB"(直球)/"CB"/"SL"/"CT"/"ST"/"2S"/"CH"/"SP"/"SK"/"OT"（`game_input.py` L830） |
| 45 | 打撃結果 | TEXT | 1球の結果/打席結果 | "見逃し"/"空振り"/"ファール"/"ボール"/"見逃し三振"/"空振り三振"/"振り逃げ"/"K3"/"三振ゲッツー"/"四球"/"死球"/"申告敬遠"/"凡打死"/"併殺打"/"ライナー併殺"/"凡打出塁"/"ファールフライ"/"単打"/"二塁打"/"三塁打"/"本塁打"/"エラー"/"野手選択"/"犠打"/"犠飛"/"犠打失策" |
| 46 | 打撃結果2 | TEXT | 付帯事象 | "0"/"PB"/"WP"/"守備妨害"/"打撃妨害"/"走塁妨害"/"ボーク"/"ピッチクロック違反" |
| 47 | 捕球選手 | TEXT | 打球を処理した野手の守備番号 | 1-9 |
| 48 | 打球タイプ | TEXT | 打球の種類 | "G"(ゴロ)/"L"(ライナー)/"F"(フライ)/0 |
| 49 | 打球強度 | TEXT | 打球の強さ | "A"/"B"/"C"/0 |
| 50 | 打球位置X | REAL | 打球落下点X（フィールド画像クリック） | ピクセル座標 |
| 51 | 打球位置Y | REAL | 打球落下点Y | 同上 |
| 52 | 牽制の種類 | TEXT | 牽制の投げ先 | "0"/"1塁牽制"/"2塁牽制"/"3塁牽制"（投手牽制・捕手牽制両方で使用） |
| 53 | 牽制詳細 | TEXT | 牽制の結果 | "セーフ"/"アウト"/"牽制エラー" |
| 54 | エラーの種類 | TEXT | エラー分類 | "処理E"/"送球E"/"捕球E"/"その他" |
| 55 | タイムの種類 | TEXT | **実データは「エラー選手」**（エラーした野手の守備番号） | 1-9（列名は歴史的遺物） |
| 56 | 球速 | REAL | 球速 km/h（十の位・一の位ラジオで入力、+100） | 例 142 |
| 57 | プレス | TEXT | プレス（前進守備プレッシャー） | "0"/"3プレス"/"1プレス"/"両プレス" |
| 58 | 偽走 | TEXT | 偽走（フェイク走塁）フラグ | 0 等 |
| 59 | 打者位置 | TEXT | 打者の守備位置（スタメンposesから転記） | "P","C","1B"…（`domain/game_state.py` L358） |
| 60 | 打席Id | TEXT | **実データはフリーコメント**（1プレイへのメモ） | 任意文字列（列名は歴史的遺物） |
| 61 | 打席結果 | TEXT | 打席の最終結果（正規化済み表記） | "見三振"/"空三振"/"三振併"/"振逃"/"邪飛"/"6G"/"4L併" のような「捕球選手+打球タイプ(+併)」合成表記/打撃結果と同値 |
| 62 | Result_col | TEXT | 結果表示用カラム（スコアカード表示用） | |
| 63 | 打者登録名 | TEXT | 打者のDB登録名（player.名前） | 氏名表示と別に保持 |
| 64 | 打者番号 | TEXT | 打者の背番号 | play_player_link 解決キー |
| 65-70 | 一走登録名/一走番号/二走登録名/二走番号/三走登録名/三走番号 | TEXT ×6 | 各走者のDB登録名・背番号 | ※`build_initial_temp_list` は index 69（三走登録名）に 17 を置いており、これは旧レイアウトの残骸とみられる（§7） |
| 71 | 投手番号 | TEXT | 投手の背番号 | |
| 72 | 入力項目 | TEXT | 入力経路/入力項目の識別値 | 初期 0 |
| 73 | 先攻打順 | TEXT | 先攻の現在打順ポインタ | 初期 0 |
| 74 | 後攻打順 | TEXT | 後攻の現在打順ポインタ | 初期 0 |
| 75 | 経過時間 | TEXT | 試合経過時間 | "0:00" |
| 76 | 開始時刻 | TEXT | 試合開始時刻 | |
| 77 | 現在時刻 | TEXT | このプレイの時刻 | |
| 78 | top_poses | TEXT(JSON) | 先攻の守備位置配列（10要素、[9]=P） | `["","",…,"P"]` |
| 79 | top_names | TEXT(JSON) | 先攻の選手名配列（**20要素**: 打順1-9 + P,C,1B,2B,3B,SS,LF,CF,RF + 予備2） | `["先攻1",…,"先攻RF","先攻","先攻"]` |
| 80 | top_nums | TEXT(JSON) | 先攻の背番号配列（10要素） | `["",…,""]` |
| 81 | top_lrs | TEXT(JSON) | 先攻の左右配列（11要素） | `["右","左",…]` |
| 82-85 | bottom_poses/names/nums/lrs | TEXT(JSON) | 後攻の同上 | |
| 86 | top_score | TEXT(JSON) | 先攻のスコアボード行（**16要素**: イニング得点×12 + 集計4つ=R/H/E/K系。末尾4つ初期 0） | `["",…,"",0,0,0,0]` |
| 87 | bottom_score | TEXT(JSON) | 後攻の同上 | |

補足:
- メモリ上の 88 要素リスト（`all_list` 行）と DB 行の相互変換は `game_repo._row_to_db()`（保存: 空文字→None、リスト→JSON）と `game_repo._db_row_to_list()`（読出: `SELECT *` の 3列目以降を位置ベースで復元、JSON列は `json.loads`）。**列の並び順に完全依存**しているため、テーブルに列を追加すると読出しが壊れる。
- 多くの列が DB 上 TEXT のため、`0`（int）/"0"（str）/""/NULL が混在し得る。集計側は文字列比較主体。

---

## 3. SQLite / PostgreSQL 切替の仕組み

### 3.1 モード決定（`settings.py`）
- `APP_DB_MODE`（env → Streamlit secrets の順で解決、`load_environment()` が `.env` を読む）。`postgres|postgresql|supabase|pg` のとき postgres モード、それ以外・未設定は **sqlite が安全側デフォルト**。
- `DATABASE_URL` は postgres モードのときだけ返される（`get_database_url()`）。`postgres://`→`postgresql://` 正規化、`DATABASE_URL=` プレフィクス除去付き。
- SQLite ファイルは `APP_SQLITE_DB_PATH`（任意）または既定 `data/app_data.db`（`schema.resolve_sqlite_db_file()`）。
- `schema.is_postgres()` = 「postgres モード かつ URL あり」。**リポジトリ層はこの関数で毎回分岐**。

### 3.2 接続取得（`db/schema.py`）
- `get_conn()`:
  - postgres 時: `@st.cache_resource` でキャッシュされた `psycopg2.pool.SimpleConnectionPool(1, 3, url, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5)` から取得。`conn.closed != 0` の死活ローカルチェック → 死んでいれば pool ごと作り直し（`_get_pg_pool.clear()`）。`autocommit=False`。`_PgConnWrapper` にラップして返す。
  - sqlite 時: `sqlite3.connect(DB_FILE, timeout=30.0)` + `PRAGMA foreign_keys = ON`。
- `release_connection(conn, discard=False)`: PGラッパーなら rollback → pool へ返却（discard=True で破棄）、SQLite なら close。`managed_conn()` コンテキストマネージャあり。
- `reset_pg_pool()`: 全滅時のリカバリ用に pool キャッシュをクリア。

### 3.3 `_PgCursorWrapper` — SQLite 方言の SQL を PostgreSQL に透過変換
リポジトリのコードは SQLite 方言（`?` プレースホルダ、裸のカラム名）1本で書かれており、PG 実行時にカーソルラッパーが `execute()` 内で書き換える:
1. **識別子クオート**: `_PG_QUOTE_COLS` に列挙された14識別子（`Season, Kind, Week, Day, GameNumber, Result_col, S, B, 試合日時, 回, コースX, コースY, 名前, チーム_id`）を正規表現 `\b<col>\b` で `"<col>"` に置換（PG は unquoted 識別子を小文字化するため、schema 側でクオート定義されたこれらを保護する目的）。
2. **プレースホルダ**: `?` → `%s` の単純置換。
3. **lastrowid エミュレーション**: SQL が `INSERT` で始まる場合、SAVEPOINT を張って `SELECT lastval()` を実行し `lastrowid` プロパティで返す（失敗時は SAVEPOINT へロールバックし None）。
4. `rowcount` はプロパティで保持。

`_PgConnWrapper` は `cursor()/commit()/rollback()/close(discard)` を提供し pool への返却を担う。

### 3.4 リトライ規約（リポジトリ層の共通パターン）
- `game_repo._is_conn_error(e)`: PG 時のみ `psycopg2.DatabaseError / InterfaceError` を接続断とみなす。
- 読み取り系: 2回試行（失敗時 `reset_pg_pool()` して再試行）。
- 書き込み系（insert_play / update_play(s) / delete_last_play / update_game_date）: PG は最大3回、`time.sleep(0.3 * 2**attempt)` の指数バックオフ。SQLite は1回。
- 各 DDL は `migrate_*` 関数群（冪等な CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS）。SQLite は `init_db()` が全テーブル作成、**PG は `supabase_schema.sql` を Supabase 側で手動実行する前提**（`init_db()` は PG では no-op）。

---

## 4. リポジトリ公開関数カタログ（= APIエンドポイント候補）

### 4.1 `db/game_repo.py`（試合・プレイ）
| 関数 | シグネチャ | 動作 | API候補 |
|---|---|---|---|
| create_game | (試合日時, 先攻チーム名, 後攻チーム名, 主審='', Season='', Kind='', Week='', Day='', GameNumber='', owner_team_id=None) → game_id | チームを ensure_team で自動作成しつつ game INSERT。副作用: `data/game_<id>.json` を新規作成 | POST /games |
| get_game | (game_id) → row(tuple) | game 1件を SELECT *（生タプル） | GET /games/{id} |
| list_games | (limit=100, team_id=None) → [(id, 試合日時, Season, Kind, 先攻名, 後攻名)] | team JOIN 済み一覧、新しい順。team_id 指定で owner フィルタ | GET /games?owner_team_id= |
| update_game_date | (game_id, game_date, owner_team_id=None) → 更新プレイ行数 | game.試合日時 + 配下 play_data.試合日時 を一括更新。所有権チェック、JSON も更新 | PATCH /games/{id}/date |
| delete_game | (game_id, owner_team_id=None) | play_player_link → play_data → game の順で削除、JSONファイルも削除 | DELETE /games/{id} |
| get_game_teams | (game_id, owner_team_id=None) → (先攻名, 後攻名) | 所有権不一致は (None, None) | GET /games/{id}/teams |
| insert_play | (game_id, row_list[88], owner_team_id=None) → play_data.id | 1プレイ INSERT + play_player_link 再生成（best-effort）+ JSON 追記。所有権不一致は PermissionError | POST /games/{id}/plays |
| update_play | (game_id, play_data_id, row_list, owner_team_id=None) | 1プレイ UPDATE + リンク再生成。0件更新は RuntimeError | PUT /games/{id}/plays/{play_id} |
| update_plays | (game_id, [(play_data_id, row_list)], owner_team_id=None) | 複数プレイを**1トランザクション**で UPDATE | PUT /games/{id}/plays (bulk) |
| delete_last_play | (game_id, owner_team_id=None) | 最終プレイ（MAX(id)）とそのリンクを削除。「1つ前に戻す」 | DELETE /games/{id}/plays/last |
| get_play_list | (game_id, owner_team_id=None) → [row_list] | プレイの番号順に88要素リスト復元 | GET /games/{id}/plays |
| get_plays_with_id | (game_id, owner_team_id=None) → [(id, row_list)] | 編集画面用（play_data.id 付き） | GET /games/{id}/plays?with_id=1 |
| get_last_play_with_id | (game_id, owner_team_id=None) → (id, row_list) or None | 試合再開用 | GET /games/{id}/plays/last |
| sync_missing_plays | (game_id, mem_rows, owner_team_id=None) → 補完件数 | プレイの番号ベースでメモリ↔DB差分を INSERT（オフライン同期） | POST /games/{id}/plays/sync |
| get_all_plays_df | (team_id) → pandas.DataFrame | owner_team_id の全試合の全プレイ（分析用） | GET /teams/{id}/plays |
| get_plays_df_for_game | (game_id, owner_team_id=None) → DataFrame | 1試合分 DataFrame（回/打順/得点を数値化） | 同上の試合版 |

所有権ガード: `_assert_owner()`（該当なしで PermissionError）+ 各 UPDATE/DELETE の WHERE 句に `owner_team_id` サブクエリを二重に埋め込む方式。

### 4.2 `db/player_repo.py`（チーム・選手・スタメン）
| 関数 | シグネチャ | 動作 | API候補 |
|---|---|---|---|
| ensure_team | (名前) → team_id | UPSERT 的にチーム作成 | POST /teams |
| list_teams | () → [(id, 名前)] | | GET /teams |
| get_team_name_by_id / get_team_id_by_name | id⇄名前 | | GET /teams/{id} |
| add_player | (チーム_id, 背番号, 名前, 左右) | 左右は normalize_player_side で正規化 | POST /teams/{id}/players |
| add_players_bulk | (チーム_id, [(背番号,名前,左右)]) → 挿入数 | 重複(チーム,背番号)は無視 | POST /teams/{id}/players:bulk |
| update_player | (チーム_id, 背番号, 名前, 左右) → bool | | PUT /teams/{id}/players/{num} |
| delete_player | (チーム_id, 背番号) | | DELETE 同上 |
| get_player_by_number | (チーム_id, 背番号) → (名前, 左右) | | GET 同上 |
| get_players_by_team | (チーム_id) → [(背番号, 名前, 左右)] | 背番号数値順 | GET /teams/{id}/players |
| get_member_df_equivalent | (チーム名) → [dict(大学名,背番号,名前,左右)] | | 同上（名前指定） |
| get_all_players_with_team | () → [dict] | 全選手 JOIN 一覧 | GET /players |
| resolve_player_id | (team_id, jersey, name) → id or None | 一意一致のみ返す（リンク解決用） | 内部利用 |
| get_player_names_by_ids | ([id]) → {id: 名前} | | 内部利用 |
| get_stamem / get_stamem_by_team_name | (チーム_id or 名) → {poses,names,nums,lrs} or None | JSON 復元済み dict | GET /teams/{id}/lineup |
| save_stamem / save_stamem_by_team_name | (チーム, poses, names, nums, lrs) | UPSERT（PG: ON CONFLICT） | PUT /teams/{id}/lineup |
| list_teams_with_password | () → [(id, 名前)] | チームパスワード認証（ログイン画面の選択肢） | GET /auth/teams |
| get_team_password_hash / set_team_password | (team_id[, hash]) | bcrypt ハッシュの取得/設定 | POST /auth/team-password |
| migrate_member_remember | (old_db_path=None) | 旧DB移行（レガシー） | 対象外 |

### 4.3 `db/user_repo.py`（ユーザーアカウント）
| 関数 | シグネチャ | API候補 |
|---|---|---|
| create_user | (username, password_hash, team_id) → id | POST /users |
| get_user_by_username | (username) → (id, username, password_hash, team_id) | ログイン検証 |
| username_exists | (username) → bool | GET /users/exists |
| list_users_by_team | (team_id) → [(id, username, created_at)] | GET /teams/{id}/users |
| delete_user | (user_id) | DELETE /users/{id} |
| update_password | (user_id, password_hash) | PUT /users/{id}/password |

（ハッシュ生成/検証と JWT は `auth.py`: bcrypt + JWT_SECRET_KEY。リポジトリはハッシュ済み文字列を受け取るだけ）

### 4.4 `db/comment_repo.py`（投手コメント）/ `db/batter_comment_repo.py`（打者コメント）
| 関数 | シグネチャ | 備考 |
|---|---|---|
| comment_repo.get_comment | (team_id, pitcher_name) → str | 例外時は `_ensure_table()`（遅延マイグレーション）して '' を返す |
| comment_repo.upsert_comment | (team_id, pitcher_name, comment) | ON CONFLICT DO UPDATE。**PG 分岐は `%s` を直書き**（ラッパー変換に依存しない箇所） |
| batter_comment_repo.get_comment | (team_id, batter_name) → str | |
| batter_comment_repo.get_all_comments | (team_id) → {batter_name: comment} | 打者側のみ一括取得あり |
| batter_comment_repo.upsert_comment | (team_id, batter_name, comment) | |

### 4.5 `db/pitcher_karte_repo.py` / `db/batter_karte_repo.py`（構造化カルテ）
| 関数 | シグネチャ | 備考 |
|---|---|---|
| get_note | (owner_team_id, target_team_name, name) → dict | 行が無ければ empty_note() |
| get_notes_for_pitchers / get_notes_for_batters | (owner, target, [names]) → {name: note} | **N+1**（名前ごとに get_note を呼ぶ） |
| upsert_note | (owner, target, name, payload) | normalize_note で正規化して JSON 保存、updated_at 更新 |
| empty_note / is_empty_note / normalize_note | 純関数 | ペイロードのスキーマ定義（§5） |

### 4.6 `db/team_theme_repo.py`（帳票テーマ）
| 関数 | シグネチャ | 備考 |
|---|---|---|
| get_palette_key | (owner_team_id, target_team_name) → key or None | 無効キーは None |
| get_effective_palette_key | (owner or None, target) → key | チーム既定（七十七銀行=navy_red 等）へフォールバック |
| upsert_theme | (owner, target, palette_key) | 正規化して UPSERT |
| delete_theme | (owner, target) | |

---

## 5. README 未掲載機能のデータ構造（カルテ・コメント・テーマ）

README の「DB テーブル設計」には team / player / stamem / game / play_data の5テーブルしか記載がない。以下は**未掲載**の追加機能。

### 5.1 投手カルテ `pitcher_karte_note.payload_json`
```json
{
  "pitch_notes": [ {"球種": "SL", "球速帯": "120-125", "備考": "カウント球"} ],
  "features":    ["行単位の特徴メモ", "..."],
  "vs_right":    ["対右打者への傾向メモ"],
  "vs_left":     ["対左打者への傾向メモ"],
  "approach_all": ["全体的な攻略方針"]
}
```
- `pitch_notes` は `("球種","球速帯","備考")` の3キー固定の dict 配列（空行は除去）
- テキスト4フィールドは「1行=1要素」の文字列配列（保存時に splitlines + strip で正規化）
- キー: (owner_team_id, target_team_name, pitcher_name)。**相手チーム・選手とも文字列参照**であり、チーム名変更・選手名変更で孤児化する

### 5.2 打者カルテ `batter_karte_note.payload_json`
```json
{ "features": [...], "vs_right": [...], "vs_left": [...] }
```
（投手版から pitch_notes / approach_all を除いた3フィールド）

### 5.3 team_theme.palette_key の有効値（`domain/team_theme.py`）
`navy_red`（既定）/ `teal_red` / `charcoal_red` / `blue_gold` / `green_navy` / `black_silver`。各キーは {label, primary, secondary, accent} の配色を持ち、カルテ帳票（`reports/pitcher_karte_html_pdf.py` 等）のヘッダグラデーションに使う。チーム名による既定マップあり（七十七銀行→navy_red、バイタルネット→teal_red、日本製鉄鹿島→charcoal_red）。

### 5.4 その他 README 未掲載
- `pitcher_comment` / `batter_comment`: カルテとは別系統の素朴な1テキストコメント（team_id=書き手チーム、選手は氏名キー）
- `play_player_link`: プレイ⇄選手マスタの正規化リンク（role: batter/pitcher/runner1-3）。best-effort 生成で欠損許容
- `user_account` + チームパスワード（team.password_hash）: 2系統の認証（ユーザーログインとチーム共有パスワード）。JWT は `auth.py`
- `data/game_<id>.json`: DB と並行して**ローカルファイルにも全プレイを二重書き込み**するバックアップ機構（create_game で作成、insert/update/delete で追随）

---

## 6. FastAPI バックエンドで再利用する際の注意点

1. **Streamlit 依存の除去が必須**: `db/schema.py` が `import streamlit as st` し、PG プールを `@st.cache_resource` でキャッシュしている（L144）。`settings.py` も `st.secrets` を参照。FastAPI ではモジュールレベルのシングルトン（またはlifespanで管理する pool）+ 環境変数のみに置き換える必要がある。ここが唯一の Streamlit 結合点で、他のリポジトリコードは純粋な Python。
2. **同期 psycopg2 + プール最大3接続**: SimpleConnectionPool(1,3) は Streamlit の単一プロセス前提のサイズ。ASGI で並列リクエストを受けると即枯渇する。asyncpg/psycopg3 async への移行か、最低でもプールサイズ拡大 + `run_in_threadpool` が必要。SQLite 側も timeout=30s の単純接続で、並列書き込みはロック競合する。
3. **`_PgCursorWrapper` の正規表現置換は脆い**: `?`→`%s` と識別子クオートを **SQL 文字列全体**に適用するため、リテラル内に `?` や `_PG_QUOTE_COLS` の語（例: データ値としての「名前」）を含むクエリを新規に書くと壊れる。新 API で SQL を追加する場合はこのラッパーの制約を引き継ぐか、SQLAlchemy 等で層ごと置き換えるのが安全。`lastval()` ベースの lastrowid もトリガー追加時に誤動作し得る（`INSERT ... RETURNING id` への書き換え推奨）。
4. **`SELECT *` + 位置ベース復元**: `_db_row_to_list()` は「1列目=id、2列目=試合_id、以降 `_PLAY_DATA_COLS` 順」という物理列順に完全依存。play_data に列を追加・並び替えすると静かに壊れる。API 化の際は明示的カラムリストの SELECT に変えるべき。
5. **所有権チェックはオプショナル引数**: ほぼ全関数の `owner_team_id` が省略可能（省略すると全データにアクセス可能）。API 層では認証トークンから解決した team_id を**必ず**渡す規約を強制すること。エラーは `PermissionError`（→403）、対象なしは `RuntimeError`（日本語メッセージ、→404/409）、バリデーションは `ValueError`（→422）に素直にマップできる。
6. **ローカルファイル副作用**: `create_game` / `insert_play` / `update_play(s)` / `update_game_date` / `delete_game` は `data/game_<id>.json` を読み書き・削除する（失敗は握りつぶし）。複数インスタンス・コンテナ環境では意味を成さないので、API 化時は無効化オプションかオブジェクトストレージ化を検討。
7. **遅延マイグレーションパターン**: comment/karte/theme 系リポジトリは `_ensure_table()`（=migrate_*）を**読み書きのたび**に呼ぶ。API では起動時に一括実行（SQLite: `init_db()` + 全 migrate_*、PG: supabase_schema.sql 適用済み確認）へ寄せ、リクエストパスから DDL を排除すべき。
8. **型のゆるさ**: play_data は大半が TEXT で、`0`(int)・"0"(str)・""・NULL が意味的に同居する。`_row_to_db` は '' を None に落とす一方、UI は "0" 文字列をセンチネルとして多用。Pydantic モデル化するなら「0/"0"/None を吸収する正規化層」を最初に設けること。日本語カラム名は Pydantic の alias（例: `pitch_type = Field(alias="球種")`）で ASCII 化するのが現実的。
9. **名前文字列ベースの参照**: comment/karte/theme は選手ID・チームIDでなく氏名/チーム名の文字列キー。play_data 自体も選手はチーム内の氏名+背番号文字列で保持し、`play_player_link` は補助に過ぎない（欠損あり）。新 UI で選手名変更機能を出すなら、これらのテーブルの追随更新 API が必要。
10. **一意性・整合性の穴**: `プレイの番号` に UNIQUE 制約はなく（重複防止はアプリの `is_duplicate_play` とキー比較のみ）、game の削除は3テーブル手動削除（CASCADE なし）。トランザクション境界は関数単位（`update_plays` のみ複数行を1トランザクション化）。API のバルク操作設計時はこの粒度を踏襲すること。
11. **pandas 依存**: `get_all_plays_df` / `get_plays_df_for_game` は DataFrame を返す分析用。API のレスポンスにはリスト/バイナリ(parquet等)化した薄い関数を別途切るのが良い。カルテの `get_notes_for_*` は N+1 なので一括 SELECT に書き換える価値がある。
12. **再試行ロジックの二重化に注意**: リポジトリ内に接続断リトライ（指数バックオフ、pool リセット）が既に埋まっている。API 層やクライアントで再試行を重ねると、insert_play が重複実行される可能性がある（プレイの番号 UNIQUE 制約がないため DB では防げない）。冪等キー（game_id+プレイの番号）を API 契約に載せることを推奨。

---

## 7. 発見した特記事項・レガシーの罠（新UI設計者向け）

1. **列名と実データのズレ（最重要）**: `play_data.タイムの種類`(idx 55) には「エラー選手（守備番号1-9）」、`play_data.打席Id`(idx 60) には「フリーコメント」が格納される。根拠: `services/play_recording.build_confirmed_play_row()` の引数列（…エラーの種類, **エラー選手**, 球速, …, 打者位置, **コメント**, 打席結果…）と `analytics/cal_stats.py` L194-200 のエラー集計。新 API のフィールド名はこの実態（error_fielder, comment）に合わせてリネームすべき。
2. **初期値リストの怪しい 17**: `config.build_initial_temp_list()` は index 69（三走登録名）に 17 を置く（実行して確認済み）。旧レイアウト（おそらく 打者位置 の初期値）の残骸とみられ、既存データの初回行に 17 が混じり得る。
3. **初期プレースホルダの先攻/後攻逆転**: 初期リストでは COLUMN_NAMES[7]=後攻チーム に文字列 "先攻チーム"、[8]=先攻チーム に "後攻チーム" が入る（スタメン確定前の行のみ）。生データを読むときの罠。
4. **COLUMN_NAMES[11] は「表.裏」だが DB 列名は「表裏」**（schema.py/supabase_schema.sql ともドットなし）。CSV エクスポート名とDB列名が一致しない。
5. **リスト長の非対称**: top_names/bottom_names は20要素（打順9+守備9+予備2）、poses/nums は10要素、lrs は11要素、score は16要素。JSON 列をモデル化する際は固定長を仮定しないこと。
6. 認証は bcrypt（`auth.py`、requirements: bcrypt==5.0.0）+ JWT（`JWT_SECRET_KEY`）。user_account 認証とチームパスワード（team.password_hash）の2系統があり、新 API では統合を検討する余地がある。

## 主要ファイルパス
- スキーマ/接続: `C:\develop\baseball_system\db\schema.py`, `C:\develop\baseball_system\db\supabase_schema.sql`, `C:\develop\baseball_system\settings.py`
- 88列定義: `C:\develop\baseball_system\config.py`（COLUMN_NAMES / IDX / build_initial_temp_list）
- リポジトリ: `C:\develop\baseball_system\db\game_repo.py`, `player_repo.py`, `user_repo.py`, `comment_repo.py`, `batter_comment_repo.py`, `pitcher_karte_repo.py`, `batter_karte_repo.py`, `team_theme_repo.py`
- 行構築の実態（列名ズレの根拠）: `C:\develop\baseball_system\services\play_recording.py`
- 値ドメイン: `C:\develop\baseball_system\domain\batting_results.py`, `player_side.py`, `team_theme.py`, `game_state.py`, `C:\develop\baseball_system\app\pages\game_input.py`
