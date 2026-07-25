# 調査レポート: docs-tests-ops

## 要約

Tsukuba PSS のドキュメント・テスト・運用を調査した。docs/ には Git Flow（PRなしローカルマージ）、2段階のフォルダ再構成計画（完了済み）、選手IDリンク設計（play_player_link 採用・実装済み）、57件検証済みの総合監査、カルテ新形式設計が揃い、一貫して「DBスキーマ・88列・CSV列順は不変」を厳守事項としている。テストは38ファイル300件で、88列契約・IDX固定インデックス・import契約・Supabaseスキーマ同期・移行確認ゲート・所有権ガード・成績公式定義・420mmカルテ形式を機械的に固定しており、新アーキテクチャ移行時はこれらをそのまま契約として維持すべき。デプロイはローカルSQLite（安全既定 APP_DB_MODE=sqlite、DATABASE_URLがあっても postgres 明示なしでは接続しない）、Streamlit Cloud（Secrets）、Render（Docker+Nginx Basic認証）の三系統。.claude/ には CLAUDE.md はなく settings.local.json（パーミッションのみ、旧macOS環境の痕跡あり）だけが存在する。

---

# Tsukuba PSS ドキュメント・テスト・運用調査レポート

対象: `C:/develop/baseball_system`（読み取り専用調査、2026-07-09時点、現在のブランチは `ui-renewal`）

---

## 1. docs/ の設計方針・運用ルール

### 1.1 docs/git_flow_rules.md — Git運用ルール
- **完全 Git Flow**（`main` / `develop` / `feature/*` / `release/*` / `hotfix/*`）。ただし **Pull Request は使わない**。レビュー・検証・マージはすべてローカルで完結し、検証後に必要に応じて GitHub へ push。
- `main` へ直接コミット禁止、`develop` へ直接実装コミット禁止（`feature/*` を `--no-ff` でローカルマージ）。
- **実データ・`.env`・本番 `DATABASE_URL`・秘密情報はコミット禁止**。
- 最重要ルール: **「DBスキーマ・CSV列・毎球データ88列を変える作業は、必ず事前にテストを追加または更新する」**。
- 各マージ前後に `python -m unittest discover -s tests` を実行するのが標準手順。
- 実際のリポジトリには `main`/`develop` と多数の `feature/*` ブランチが存在。現在の作業ブランチ `ui-renewal` はこの命名規約から外れている点に注意（UI刷新は後述の再構成計画で「保留作業」とされていたもの）。

### 1.2 docs/folder_restructure_plan.md — フォルダ再構成計画（第1期・完了済み）
- 方針: **「DBスキーマ、88列の毎球データ、既存CSVの列順は再構成作業では変更しない」**「先にサービス・ドメイン層へ責務を逃がし、画面ファイルの移動は最後」「カテゴリごとに小さく移動し毎回全テスト実行」「移動前に import 検証テストを追加」。
- ステップ1〜9（reports/・analytics/・app/ui/・app/pages/ への移動、`main.py` の薄いラッパー化）はすべて完了と記録。
- `config.py`（88列契約の中心）と `auth.py` はルートに据え置き（移動リスク回避）。
- **保留作業として明記**: UIデザイン刷新 / `main_page.py`(現 game_input.py) の大規模分割 / DBスキーマ変更 / CSV列名・列順変更 / 実データ移行 — 「フォルダ再構成と混ぜると原因切り分けが難しくなるため別ブランチ」。

### 1.3 docs/folder_structure_redesign_20260709.md — 再構成第2期（Phase A 実施済み）
- ルート直下の `pitching/`・`batting/`（計算+作図部品）と `analytics/pitching/`・`analytics/batting/`（Streamlit分析画面）の二重構造の紛らわしさを解消するため、部品層を **`charts/pitching/`・`charts/batting/`** へ移動（git log の batch 18 コミットで実施済み）。
- `charts/` は `analytics/`（画面）と `reports/`（帳票）の両方から使われる**共有の葉レイヤー**という位置づけ。
- 役割分担の記録: **設計=Fable、実装=最適モデル(Codex/Opus)**。「挙動は一切変えない純粋な移動+import更新」を原則とし、`test_import_contracts.py` + 全テスト（当時299件）を安全網とする。
- Phase B（`config.py`・`font_registry.py` 等ルートファイルの移動）は「churn が見合わない」ため**保留を推奨**と判断済み。
- 末尾の厳守事項: **「変更しないもの: DBスキーマ・88列・CSV列順・`.env`・実データ・ロジック・UIデザイン」**。

### 1.4 docs/grammar_rules.md — コーディング規則
- snake_case 変数/関数、UPPER_SNAKE_CASE 定数、`n_` 個数プレフィックス、`_df` サフィックス、f-string 優先、全関数に型ヒント、docstring は英語、インラインコメントは日英混在可。
- 特徴的な独自スタイル: **丸括弧・角括弧・波括弧の内側にスペース**（`df[ 'col' ]`、`func( a, b = c )`）、キーワード引数 `=` の前後スペース、代入・辞書の `=`/`:` 位置アライメント。
- **実態は層で二分**: `charts/`（旧 pitching/・batting/、移植元コード由来）はこの独自スタイルに従うが、`services/`・`domain/`・`tests/` など新規コードは標準 PEP8 スタイル。新アーキテクチャで既存 `charts/` を触る場合は既存スタイル維持、新規コードは PEP8 が事実上の慣行。

### 1.5 docs/player_id_data_linking_plan.md — 選手IDベース移行設計（採用済み）
- 課題: `play_data` の集計キーが氏名文字列のため、選手名修正が過去データに追従しない。
- 4案比較の結果 **案2（別リンクテーブル）+ 案3（新規データのみ内部リンク）を採用**。88列と CSV 列順は不変のまま `play_player_link`（`play_data_id` + `role`(batter/pitcher/runner1-3) + `player_id`、`UNIQUE(play_data_id, role)`）を追加。
- 既存データは「チーム+背番号+名前」照合のドライラン→確定分のみユーザー確認後INSERT。ロールバックはリンクテーブルを使わない/消すだけ。
- テスト（`test_schema_indexes.py`, `test_link_existing_plays.py`, `test_player_id_stats_integration.py`, `test_game_repo_update_play.py` の player_links 系）から、この設計は**実装済み**と確認できる。`scripts/link_existing_plays.py` は確認環境変数なしの apply を拒否し、dry-run は DB 無変更、apply は冪等（テストで保証）。

### 1.6 docs/system_audit_20260612.md — システム総合監査（意思決定の宝庫）
- 8観点監査。57件の指摘が独立エージェントの反証試行を通過（反証0件）。当時のテストは 206 passed / 1 skipped。
- **Critical/High の主要指摘はその後のコミット（batch 15〜18 等）とテスト追加で修正済み**とテスト名から確認できる: 三振略記不一致（`domain/batting_results.py` に共有定数を新設、`test_batting_result_definitions.py`）、OBP分母、WHIP死球除外（`test_cal_stats_pitching_innings.py`）、盗塁死、PG接続プール二重返却（`test_game_repo_update_play.py`）、所有権書き換えの IS NULL 条件（`test_schema_indexes.py::test_reassociate_games_by_team_keeps_existing_owner`）、.dockerignore（実在+契約テスト）、INITIAL_TEAM_PASSWORDS 上書き防止（`test_streamlit_navigation.py`）、移行スクリプト欠損（`test_safety_contracts.py`）、SQLite FK 強制（`test_sqlite_get_conn_enforces_foreign_keys`）。
- 設計上の重要な知見:
  - **「イベント正本+状態は導出」が業界標準**（Retrosheet/MLB GUMBO）。現行の1球1行スナップショット（Statcast型）は分析用として正解だが、**リプレイ整合性テスト**（全行を `update_list` でリプレイし保存済み導出列と一致検証）が推奨→ `test_play_replay.py`（`validate_replay_consistency`）として実装済み。
  - DB挿入失敗時もメモリ継続する設計は**意図的**（試合終了時 `sync_missing_plays` で回収）。ただし未同期状態での過去プレイ編集にリスクあり。
  - 任意プレー編集+下流再計算は「GameChanger にもない差別化点」。
  - 2026年春から大学野球でピッチクロック全国適用 → 単独イベント入力対応済み（`test_game_input_ui_flows.py` のピッチクロック系テスト）。
  - 将来課題: 自責点には走者ごとの「出塁させた投手」が必要（現状「失点率」と誠実にラベル）、DH制対応、走者進塁の構造化(enum)、タイブレーク設定走者の自責点除外フラグ。

### 1.7 docs/karte_format_update_design_20260708.md — カルテ新形式対応設計（実施済み）
- 外部参照パッケージ（`baseball_karte_package_20260708.zip`、正本ルールは参照側の `AGENTS.md`）の新形式へ投手カルテを追随、打者カルテを新規追加。git log の K1/K2a/K2b コミットで実装済み。
- 決定事項: 用紙は **420mm×300mm**（A4横から変更）、ヘッダーのチームカラー（team_theme パレット）は**アプリ固有機能として維持**、collect_stats の既存合算キーは残し側別キーを追加（後方互換）、参照コードの忠実移植を原則。
- 打者カルテに必要な35列は **play_data 88列で完全充足**を調査済み（語彙も互換）。`batter_karte_note` テーブルは `pitcher_karte_note` と同型（owner_team_id + target_team_name + batter_name + payload_json）。
- 実装体制の記録: 実装は Codex/Opus に委任、検証は Claude（pytest 全件 + 実HTML生成の参照突合 + AppTest/プレビュー実駆動）。

---

## 2. テストスイートの構成と守っている契約

- 38ファイル・**300テストメソッド**（docs 記載の「299件」とほぼ一致、その後1件増）。実行は `python -m unittest discover -s tests`（README/git flow 標準）または `.venv/Scripts/python.exe -m pytest tests/ -q`（近年のdocs）。**アプリ起動・実データ・外部DB接続なしで完走する**設計が明記されている。

### 2.1 契約テスト（新アーキテクチャ移行時の最重要安全柵）
- **`tests/test_safety_contracts.py`**:
  - `COLUMN_NAMES` が**ちょうど88列**、`build_initial_temp_list()` の行長一致、`IDX` の固定インデックス検証（試合日時=0, プレイの番号=9, 回=10, 表裏=11, 打者氏名=27, 投手氏名=32, 球種=44, 打撃結果=45, 球速=56, top_poses=78, bottom_poses=82, top_score=86, bottom_score=87）。列名 `"表.裏"`（ドット付き）も固定。
  - 初期行の可変デフォルトが行間で独立していること（共有参照バグ防止）。
  - `.dockerignore` に `.env` `.venv/` `tmp/` `data/` `build/` `dist/` `__pycache__/` `.git/` `.pytest_cache/` `*.db` `.claude/` が含まれること。
  - 移行スクリプトが team/game/user_account/pitcher_comment/batter_comment/pitcher_karte_note/team_theme/play_data と password_hash・owner_team_id を移行し、`ON CONFLICT ("id") DO NOTHING` と件数検算を持つこと。
  - `db/supabase_schema.sql` に全ランタイムテーブル（user_account, pitcher_comment, pitcher_karte_note, batter_karte_note, team_theme, batter_comment）と全インデックス（idx_play_data_game_id, idx_play_data_game_play_number, idx_game_owner_team_id ほか）が存在すること。
  - 秘密情報のハードコード禁止（auth.py はシークレット未設定で `raise RuntimeError`、admin は `hmac.compare_digest`）。
  - ルート `main.py` が `from app.main import run_app` の薄いラッパーであること、build/ の spec ファイルが旧レイアウト（main_page.py 等）を参照しないこと。
  - 移行スクリプトが `CONFIRM_SQLITE_TO_SUPABASE_MIGRATION` なしで exit 1 すること（サブプロセスで実検証）。
- **`tests/test_import_contracts.py`**: 約50モジュール（app.pages.*, analytics.*, charts.*, reports.*, db.*, domain.*, services.*）が `.venv` の Python で import 可能なこと。フォルダ移動時の破損検出用で、**移動系リファクタでは必ずこのリストを追従更新する運用**。

### 2.2 ドメイン層テスト（野球ルールの正しさ）
- `test_update_list_behavior.py`（34件）: カウント進行、押し出し、イニング交代、打順一巡の折返し、サヨナラ、オープン戦引き分け、延長13回以降がH/E/K/Bカラムを壊さないこと、タイブレーク開始状態、手動状況変更。
- `test_runner_advancement.py`: 単打/二塁打/三塁打/本塁打/四球（フォース時のみ進塁）/申告敬遠/犠飛/併殺/暴投/ボーク/盗塁成功・失敗/牽制死/振り逃げ警告。
- `test_scoring_rules.py`: フォース第3アウト・サヨナラ超過得点の**非ブロッキング警告**（監査の推奨「警告するが強行も許す」を反映）。
- `test_scoreboard.py`, `test_pitching_innings.py`（投球回の表示用1.1/率計算用1.333/スコアブック表記2⅓の3表現分離）, `test_pitch_speed.py`, `test_player_side.py`（両打対応）, `test_status_labels.py`, `test_input_validation.py`。

### 2.3 成績定義テスト（監査P0の再発防止）
- `test_batting_result_definitions.py`: 三振の**略記（見三振/空三振/三振併/振逃/K3）と正式名称の両対応**、打率・出塁率の公式分母（犠打・申告敬遠込み）、打点の限定条件、打撃妨害の打数除外、盗塁失敗判定（盗塁死/走塁死含む）。
- `test_cal_stats_pitching_innings.py`: WHIP は死球除外・FIP は死球込み、申告敬遠のB列計上、犠打失策の打数除外。
- `test_pitching_overall_stats.py`(14件), `test_score_card_pitcher_innings.py`: 投手アウト数に走者アウト・牽制死を含む一貫性、ERA は真の分数使用。

### 2.4 DB・リポジトリテスト
- `test_game_repo_update_play.py`(21件): **owner_team_id 所有権ガード**（wrong owner 拒否）、PG接続プール二重返却防止、update/delete が件数を変えないこと、player_links の再作成・削除追随、JSON バックアップの削除。
- `test_schema_indexes.py`: 起動/再開用インデックス、play_player_link の SQLite/Supabase 両宣言、**SQLite の FK 強制（PRAGMA foreign_keys）**、QA 用 DB ファイル差替え、所有権再関連付けが既存 owner を保持。
- `test_settings_db_mode.py`: **sqlite 既定・DATABASE_URL 無視、postgres 明示時のみ URL 使用、URL 欠落時は sqlite 継続**、パフォーマンスログはオプトイン。
- `test_db_connection_management.py`: 例外時の接続返却、プールリセット。

### 2.5 UIフロー（Streamlit AppTest）・帳票・スクリプト
- `test_game_input_ui_flows.py` / `test_streamlit_navigation.py`(計27件): 画面遷移がブランクにならないこと、ピッチクロック違反の単独入力と B=4 防止（3ボール時は四球化）、2ストライク空振りの正しい三振分類、途中再開、代打キャンセル、初期チームパスワードが設定済みハッシュを上書きしないこと。
- `test_pitcher_karte_html_pdf.py` / `test_batter_karte_html_pdf.py`: セクション文言の存在、**420mm ページサイズ**、チームカラーパレット、エラー結果の被打率除外、1打者1ページ、所見上書き。ブラウザPDF化テストは環境フラグでオプトイン。
- `test_link_existing_plays.py`: 既存データ紐づけの分類（確定/要確認/不可/リンク済み）、dry-run 無変更、確認環境変数なし拒否、冪等 apply。
- `test_play_replay.py`: **リプレイ整合性**（保存行を先頭から再計算し導出列一致を検証）— 新アーキテクチャでもこの恒等式は移植価値が高い。

---

## 3. デプロイ構成と環境変数

### 3.1 三系統のデプロイ
| 系統 | エントリ | 認証 | DB |
|---|---|---|---|
| ローカル（テスト運用の正） | `streamlit run main.py`（SETUP.md は `.venv` + Python 3.11 前提、Windows PC 向け手順） | アプリ内ログイン | SQLite `data/app_data.db` |
| Streamlit Community Cloud | `main.py` 指定、Secrets に TOML で `APP_DB_MODE="postgres"` / `DATABASE_URL` / `JWT_SECRET_KEY` / `DB_ADMIN_PASSWORD` | アプリ内 | Supabase PostgreSQL |
| Render（`render.yaml`, runtime: docker） | `Dockerfile`(python:3.11-slim + nginx + apache2-utils) → `start.sh` | **Nginx Basic 認証**（UTF-8で日本語ユーザー名対応、`X-Remote-User` ヘッダを Streamlit へ転送） | Supabase PostgreSQL |

- `start.sh`: `PORT`(既定10000) で nginx.conf を動的生成 → `scripts/generate_htpasswd.py` が `BASIC_AUTH_USERS` または `INITIAL_TEAM_PASSWORDS` から .htpasswd 生成 → Streamlit を 127.0.0.1:8501 でバックグラウンド起動（headless, CORS有効, XSRF は環境変数で制御）→ nginx がフロントで WebSocket プロキシ（`proxy_read_timeout 86400`）。
- `render.yaml` の envVars: `APP_DB_MODE=postgres`（値固定）、`DATABASE_URL` / `BASIC_AUTH_USERS` / `JWT_SECRET_KEY` は `sync: false`（ダッシュボード手動設定）。
- `.streamlit/config.toml`: headless=true, address=0.0.0.0, enableCORS=true, enableXsrfProtection=true。`runtime.txt`: python-3.11.9。`requirements.txt` は完全ピン留め（batch 16「reproducible deploys」コミット）。streamlit 1.56.0 / pandas 3.0.2 / numpy 2.4.4 / psycopg2-binary / PyJWT / bcrypt / plotnine / reportlab / python-pptx / pypdf / PyMuPDF。

### 3.2 環境変数の全一覧（`settings.py` が env → Streamlit secrets → default の順で解決）
| 変数 | 既定/必須 | 意味 |
|---|---|---|
| `APP_DB_MODE` | `sqlite`（安全既定） | `postgres`/`postgresql`/`supabase`/`pg` のときだけ PostgreSQL。**未指定なら DATABASE_URL があっても SQLite** |
| `DATABASE_URL` | 任意 | postgres モード時のみ使用。`postgres://`→`postgresql://` 正規化あり |
| `JWT_SECRET_KEY` | **必須**（未設定は auth.py が RuntimeError） | セッション/ログイントークン署名 |
| `DB_ADMIN_PASSWORD` | **必須** | DB管理画面パスワード（hmac.compare_digest 比較） |
| `ENABLE_COOKIE_AUTH` | false | ブラウザCookieでのログイン復元（オプトイン） |
| `STREAMLIT_ENABLE_XSRF_PROTECTION` | true | 信頼できるリバースプロキシ配下でのみ false 可 |
| `APP_PERF_LOG` | false | パフォーマンスログ（オプトイン、テストで保証） |
| `BASIC_AUTH_USERS` / `INITIAL_TEAM_PASSWORDS` | Render のみ | nginx .htpasswd 生成元（後者はチーム初期パスワードと兼用） |
| `CONFIRM_SQLITE_TO_SUPABASE_MIGRATION` | 未設定 | 移行スクリプトの明示確認ゲート（=1 必須） |
| `PORT` | 10000 | Render が注入 |

- 実 `.env` には Supabase の **Pooler（Session mode）** 接続 URL が設定されており、コメントに「Direct のホストはこの環境で解決しないため Pooler を使用。実行前にダッシュボードで『Restore project』すること」という運用注意が残っている（Supabase 無料枠の休止運用を示唆）。

---

## 4. .claude/ 配下の内容（全文引用）

`CLAUDE.md` は存在しない。`.claude/settings.local.json` のみ存在（内容はパーミッション設定のみで、プロジェクト固有の指示・規約はなし。macOS 時代の別パス `/Users/yutakanno/...` への grep 許可が残っており、本リポジトリが移植・引き継ぎされたコードベースであることを示す）。全文:

```json
{
  "permissions": {
    "allow": [
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git push:*)",
      "Bash(python:*)",
      "Bash(ls:*)",
      "Bash(grep -i \"pypdf\\\\|fitz\\\\|memory\\\\|gc.collect\" /Users/yutakanno/Documents/py26/_0211_tsukuba_pss/*.py /Users/yutakanno/Documents/py26/_0211_tsukuba_pss/*/*.py)",
      "Bash(grep -n \"def _build_figure\\\\|def course_detailPlot\\\\|def batted_ball_plot\" /Users/yutakanno/Documents/py26/_0211_tsukuba_pss/batter_analysis_mode.py /Users/yutakanno/Documents/py26/_0211_tsukuba_pss/pitching/*.py)",
      "Bash(python3 -c \"import tkinter; print\\('tkinter OK'\\)\")",
      "Bash(pip3 show:*)",
      "Bash(python3 launcher.py)",
      "Bash(chmod +x /Users/yutakanno/Documents/py26/_0211_tsukuba_pss/build/build_mac.sh)",
      "Bash(bash build/build_mac.sh)",
      "Bash(open:*)",
      "Bash(flutter analyze:*)",
      "Bash(flutter doctor:*)"
    ]
  }
}
```

---

## 5. 「壊してはいけないもの」リスト（並行運用の互換性制約）

複数の docs で繰り返し明文化され、テストで機械的に守られている不変条件。優先度順:

1. **play_data の88列契約**（最上位）: `config.py` の `COLUMN_NAMES`（列名・列順・列数=88）と `IDX` の固定インデックス。列名 `"表.裏"`（ドット付き）を含む。**CSV出力の列名・列順もこれと同一**。全 docs が「変更しない」と明記し、`test_safety_contracts.py` がインデックス単位で固定。変更する場合は git_flow_rules により「必ず事前にテスト追加/更新」。
2. **DBスキーマ互換**: `team` / `player`（UNIQUE(チーム_id,背番号)）/ `stamem`（poses/names/nums/lrs を JSON 文字列保存）/ `game` / `play_data` のコア5テーブル + 後付けテーブル（`user_account`, `pitcher_comment`, `batter_comment`, `pitcher_karte_note`, `batter_karte_note`（payload_json 型）, `team_theme`（palette_key 既定 'navy_red'）, `play_player_link`（UNIQUE(play_data_id, role)））。**SQLite の実 DDL と `db/supabase_schema.sql` の同期**が契約テストで固定されており、スキーマ変更は両方+移行スクリプトの3点同時更新が必要。
3. **SQLite/PostgreSQL 両対応の単一リポジトリコード**: `_PgCursorWrapper` による `?`→`%s` 変換とカラム名クオートで両DBを吸収。新アーキテクチャでも「リポジトリコードは1系統で両DB動作」の維持、または移行時に両DBでの検証が必要。
4. **DBモードの安全既定**: `APP_DB_MODE=sqlite` が既定で、**DATABASE_URL が存在しても postgres を明示しない限り外部DBに接続しない**（誤って本番 Supabase を触らないための多重防御。テスト4件で固定）。
5. **owner_team_id 所有権ガード**: 試合データの読み書き・削除は所有チーム検証付き（SQL二重化）。再関連付けは既存 owner を奪わない（IS NULL 条件）。マルチチーム運用の根幹。
6. **破壊的操作の明示確認ゲート**: `CONFIRM_SQLITE_TO_SUPABASE_MIGRATION=1`（移行）、`link_existing_plays` の確認環境変数 + dry-run 既定 + 冪等 apply。
7. **秘密情報の扱い**: `JWT_SECRET_KEY` / `DB_ADMIN_PASSWORD` はハードコード禁止・未設定時は起動失敗。`.dockerignore` の必須パターン（.env/data/tmp/*.db/.claude 等）は契約テストで固定（過去に実DB・秘密情報が Docker イメージに混入した監査指摘 #10 の再発防止）。
8. **成績計算の公式定義**: 三振略記の正規化（`domain/batting_results.py` の共有定数）、OBP分母、WHIP（死球除外）/FIP（死球込み）、申告敬遠・犠打失策・打撃妨害の打数除外、盗塁失敗の全ステータス、投球回の3表現（表示1.1/率1.333/表記2⅓）。監査で「表示成績が信頼できない」状態から立て直した経緯があり、**これらの定義テストは新実装でもそのまま契約として移植すべき**。
9. **カルテ帳票形式**: 420×300mm ページ、セクション文言（テストが文字列一致で検証）、team_theme チームカラーパレット（参照パッケージにないアプリ固有の上位互換機能）、1投手/1打者=1ページ。正本は外部参照パッケージの AGENTS.md。
10. **起動・ビルド互換**: ルート `main.py` は `streamlit run main.py` 用の薄いラッパー（app/main.py が実体）。build/ の PyInstaller/Nuitka spec、Dockerfile、render.yaml が現レイアウトを参照していることも契約テスト対象。
11. **記録継続性の設計思想**: DB保存失敗時もメモリで入力継続し試合終了時に `sync_missing_plays` で回収（意図的設計）。プレイ確定の二重クリック防止・重複キー検知。undo（1つ前に戻す）とプレイ編集+編集点以降の再計算+リプレイ整合性検証。これらは「試合に追いつくことを最優先する」スコアリングUXの中核で、新UIでも維持必須。
12. **運用前提**: 同一試合の複数ブラウザ同時入力は非対応、リロードでセッション消失（確定前データは失われる）、SQLite は `data/app_data.db` のファイルコピーがバックアップ手段 — SETUP.md がテストユーザー向けにこの前提で配布されている。

### 補足: 過去の意思決定の時系列（git log と docs の突合）
- 2026-04〜05: grammar_rules 抽出、git flow 制定、フォルダ再構成第1期、player_id リンク設計（案2+案3採用）。
- 2026-06-12: 総合監査（57件検証済み指摘）→ 以後 batch 番号付きコミットで P0/P1 を順次修正（batch 15: ensure_team 原子化・日跨ぎ経過時間、batch 16: requirements ピン、batch 17: update_list の IDX 化、batch 18: charts/ 集約）。
- 2026-07-08: カルテ新形式設計 → K1/K2a/K2b で実装（設計=Fable、実装=Codex/Opus、検証=Claude という多モデル分業が文書化されている）。
- 2026-07-09: SETUP.md 追加（テストユーザーへの配布開始）。現在 `ui-renewal` ブランチで UI 刷新（再構成計画の「保留作業」）が着手されている。
