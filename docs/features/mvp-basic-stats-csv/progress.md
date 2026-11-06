# 基本成績・CSV MVP接続 進捗・引継ぎ

最終更新: 2026-11-06（候補・未統合）

## 1. 固定点とGit照合

| 項目 | 値 |
| --- | --- |
| 主repo | `/home/ymdms/projects/pitchlog` |
| 作業worktree | `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-basic-stats-csv` |
| 作業branch | `feature/mvp-basic-stats-csv` |
| 起点（指示の固定HEAD） | `a018b896bfc1ee49efc5b0912f1b6a04fd24e363` |
| 本枝の候補commit | `（最終反映commitを下記に追記）` |
| 成績基盤worktreeの実HEAD（開始時） | `49bf535ce73c51ab843217e2dab706a0d257b2f6` |
| 差 | 固定HEADの子3コミット（`3be91ac0`/`dbda56c9`/`49bf535c`。D11比較資産9path）。本枝は取り込んでいない |
| 主担当台帳のD11固定候補 | `a524277f`（別枝 `feature/mvp-stats-d11-reflection-root`）。本枝へ未統合 |

開始時の foundation worktree は clean で、`a018b896` は祖先。指示の固定HEADと実worktree HEADが
一致しないため、本枝は固定HEADから作成し、D11未統合候補を混ぜていない。台帳の「固定a018」と
実branch先端の差はこの記録を正とする。

## 2. 今回の実装（候補）

- `backend/domain/stats-display.model.json` + 生成 `stats/generated/rates.py`:
  打率/WHIPを **T6表示率だけ** として単一宣言。出塁率/長打率は **T5 OPSの同じcomponent pair** を
  表示し、式を複製しない（NFR-018）。`facts.py`/`statsPrimitives.ts` は byte 不変で、
  T5 artifact set/native profile/5関数は変更していない。
- `backend/src/pitchlog/stats/basic_stats.py`: 27項目の写像。既存26十分統計 + OPS + 新T6率。
  D03（登板）/D04（打者数）は `source_unavailable` + 理由。0補完しない。
- `backend/src/pitchlog/stats/basic_sql.py`: 既存 `stats/generated/stats.sql` のscopeだけを
  試合/暦年・公式/暫定に差し替える候補SQLビルダー。式は追加しない。
- `backend/src/pitchlog/repositories/stats_basic.py`: `ReadBasicStatsToken` と固定関数登録
  （**製品registry/appには登録していない**。owned検証でapp scriptが試験注入する）。
- `backend/src/pitchlog/api/routers/stats.py`: JSON 4経路 + CSV 2経路。
  - `GET /games/{game_id}/stats?mode=current|official`
  - `GET /stats/seasons/{year}?category=official|practice|all`
  - `GET /games/{game_id}/stats.csv?mode=...`
  - `GET /stats/seasons/{year}/stats.csv?category=...`
- `frontend`: `SeasonStats.vue`（JST年/区分切替/CSV）、`GameStatsScreen.vue`（暫定/公式/CSV）、
  `BasicStatsTable.vue`（打撃16/投手11）。routerに `/stats/season`・`/games/:gameId/stats` を追加。
- 候補正式資産: `candidates/basic_stats_functions.sql`（readのみ、SHA256
  `88b7b765e255c73893d809003d80d1108bbb6c29e961baa8c43a20dd3a2177b2`）、
  `candidates/finalize_game_stats.test-only.sql`（owned検証専用、SHA256
  `eab73d07f0d6e506050ddd5bb4dc4b8a867548968c4bdcd970b3588665d90f3e`）、
  `candidates/authz-diff.md`。`contracts/` は未編集。

## 3. 実DB/画面の検証結果

### 3-1. owned隔離PG縦断（実API→実DB）

`backend/tests/db/test_stats_basic_vertical_http.py` **1 passed / 76.25秒**。

- 既存の実HTTP縦断（新規作成→開始→通常3球→再送/reload）を再利用。
- 候補finalizeを実app UID20003の `pitchlog_app` から呼び、`current_open`→`confirmed_ended`。
- `GET /games/{id}/stats?mode=official` 200・20名。`mode=current` はfinalize後0名。
- `GET /stats/seasons/2026?category=all` 10名、`official` 0名（`game_other` のため）、
  `practice` 10名。D02写像の実測。
- 同一finalize再実行は同一結果（冪等）。
- 試合別/シーズンCSV 200・BOM `EFBBBF`・行数20/10・ヘッダ27項目・pending/unavailable列。
  CSVは全ページを一時ファイルへ完成させてから返し、途中失敗で部分CSVを200保存しない。
- 保存factのplayer/metric合計とAPIのcount値を全件照合。
- 別tenantログインで当該試合の成績は404、未ログインは401、別receiptのfinalizeは42501。
- 試合は `game_other`。試合区分の公式/練習切替を実データで確認した。
- 候補ACL（ownerのSELECT列/RLS policy/finalize UPDATE policy）は**owned DBにだけ**適用。
  正式catalogは未受理。

### 3-2. 候補SQL/finalize単体

`backend/tests/db/test_stats_basic_db.py`:
- 現行0041の後に候補SQLを適用し、schema/2関数/SECURITY DEFINER/owner/ACLを実PGで確認。
- 最小のcurrent_open版を作り、finalizeの冪等と別receipt拒否を確認。
（この2件は個別実行で成功。同一pytest sessionで縦断と連続実行した際、fixtureの
 disposable cluster接続が一度失敗したため、最終報告では個別実行の結果を採る。）

### 3-3. 純検査

- stats/生成runtime/function boundary/native registration/function codec/contract/API conventions:
  **643 passed**。
- `backend/tests/test_stats_basic_sql.py`: **8 passed**（候補SQL byte固定、27項目、率、重複JSON拒否、
  JST境界、任意の登板/打者数metric受理）。
- `tests/domain/gen`: **87 passed**（`PYTHONDONTWRITEBYTECODE=1`。未設定だとpycacheで
  formatterのtree監視が落ちる環境差がある）。
- backend `ruff check`/`ruff format`/`ty check`: 成功。
- frontend `BasicStatsTable.spec.ts` + `SeasonStats.spec.ts` + `router.spec.ts`: **46 passed**、`vue-tsc`/ESLint成功。
- 実Vite/Chromium/実機の画面操作は未実施。

## 4. 利用者が候補環境で完了できる操作

候補DB（`candidates/basic_stats_functions.sql` + `authz-diff.md` のACL/RLSを適用した隔離DB）で:

1. `/stats/season` を開き、年・公式/練習/合算を切り替えて25項目と未取得理由を見る。
2. 同じ画面でCSVをダウンロードする（BOM付きUTF-8、27項目+未取得一覧）。
3. `/games/{id}/stats` を開き、暫定/公式を切り替えて試合別成績を見る/CSVを落とす。
4. 終了確定は候補 `finalize_game_stats` を呼ぶ経路が必要。製品の終了操作からは未接続。

正式develop/正式DBでは、上記はまだ利用できない（候補関数/認可が未統合）。

## 5. 未接続の依存と主担当への差分

| 依存 | 状態 | 主担当が統合する差分 |
| --- | --- | --- |
| 正式authz/tenant資産 | 未受理 | `candidates/authz-diff.md` の関数本体/schema/ACL/RLS、repository contract token、route registry、capability catalog、seal/7.7 |
| 終了確定provider | 未接続 | 終了/再開の同一TXで `finalize_game_stats` を呼ぶ。`games.status` とreceiptの真正性は呼出側 |
| 打者数（D04/BF） | 数学候補のみ | native 27 CHECK/配列/上限、current v3 profile、Save/read/credits、D11/ART再束縛。本枝のAPIは `batters_faced` がmetric JSONに現れれば自動表示 |
| 登板（D03） | source未供給 | participation interval/交代の正式出場source。本枝は `appearances` が現れれば自動表示 |
| 毎球/プレイCSV 88列 | 未接続 | `ud2-csv-export` step2〜5（DB抽出/HTTP/ZIP/画面DL）。step1の `play_rows.py`/`archive.py` を再利用 |
| 実ブラウザ/実機/性能 | 未実施 | 実Vite/Chromium/端末、15万play/同時負荷、CSV大容量/切断 |

## 4-1. 独立レビュー反映（2026-11-06）

独立レビュー（`feature/mvp-basic-stats-csv`、対象 `05241ebc`）で以下を検出し、反映した。

- **P0 finalize**: 任意receiptを受け取るapp実行可能finalizeはreceipt真正性未検証。製品候補から
  除外し、`candidates/finalize_game_stats.test-only.sql` のowned検証専用へ分離。正式catalog/HTTPへ
  接続しない。終了確定providerが自身のTXでcompletion列を更新する。
- **P1 製品登録/routeの先行**: `STATS_BASIC:read` とstats routerを製品registry/appから外し、
  候補moduleを `backend/tests/stats_basic_candidate.py`・`stats_api_candidate.py`・
  `stats_schemas_candidate.py` へ移した。`test_authz_repository_contract`/`test_api_conventions`
  は成功へ復帰。DB縦断のapp scriptだけが候補registry/routerを試験注入する。
- **P1 CSV部分成功**: 全ページを一時ファイルへ完成させてから返す方式へ変更済み（`6cb83584`）。
- **P1 NFR-018**: 出塁率/長打率をT5 OPSのcomponent pairの表示だけに変更し、式の二重実装を解消。
- **P1 テスト主張**: 別receipt拒否、cross-tenant/no-cookieを縦断へ追加し、実測した。
- **P2**: `derive_rates` の生成module再読込、選手ごとのcanonical CTE反復、カテゴリ写像の重複は
  未解消として残す（性能・整理であり、計算式の重複ではない）。

## 5-1. マージ前ゲートの実測

- `uv run python scripts/check_tenant_boundary_bypass.py --base-ref a018b896` は
  **「固定tupleのreadonly原典全byteが不一致」で失敗**した。これは
  `operation_registry.py`/`batted_ball_options.py` をPR196固定source revisionのbyteへ
  照合する検査で、固定HEAD `a018b896` の時点で既に一致しないharness baseline差である
  （候補tokenの未登録が原因ではない）。`operation_registry.py`/`batted_ball_options.py` は
  a018b896とbyte一致のまま。共有tenant資産の正式化は `candidates/authz-diff.md` のとおり
  主担当が行うまで、本枝は**マージ不可**。この失敗を成功扱いしない。
- `scripts/core_guard.py` はPRイベント外のためスキップ（判定不能）。
- `contracts/`・seal・`first_ball_product`・`current_product_startup` の差分は0。

## 6. レビュー

- 本枝の独立非作者レビューは依頼中（結果は最終報告に追記）。自己確認のみで正式採用・
  製品提供・MVP完成とはしない。
- 既存のBF数学/取消/終了再開の採用済み判断を再承認待ちへ戻していない。
- 固定成功・仮の終了済みデータ・未定義0補完はしていない。D03/D04は明示的な未取得。
