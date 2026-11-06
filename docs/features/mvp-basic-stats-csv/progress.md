# 基本成績・CSV MVP接続 進捗・引継ぎ

最終更新: 2026-11-06（候補・未統合）

## 1. 固定点とGit照合

| 項目 | 値 |
| --- | --- |
| 主repo | `/home/ymdms/projects/pitchlog` |
| 作業worktree | `/home/ymdms/projects/pitchlog-worktrees/feature-mvp-basic-stats-csv` |
| 作業branch | `feature/mvp-basic-stats-csv` |
| 起点（指示の固定HEAD） | `a018b896bfc1ee49efc5b0912f1b6a04fd24e363` |
| 本枝の候補commit | `103f4c5d`（push済み・PR未作成。実装 `05241ebc`、27受理 `88b1cd42`、CSV一時ファイル `6cb83584`、画面テスト `103f4c5d`） |
| 成績基盤worktreeの実HEAD（開始時） | `49bf535ce73c51ab843217e2dab706a0d257b2f6` |
| 差 | 固定HEADの子3コミット（`3be91ac0`/`dbda56c9`/`49bf535c`。D11比較資産9path）。本枝は取り込んでいない |
| 主担当台帳のD11固定候補 | `a524277f`（別枝 `feature/mvp-stats-d11-reflection-root`）。本枝へ未統合 |

開始時の foundation worktree は clean で、`a018b896` は祖先。指示の固定HEADと実worktree HEADが
一致しないため、本枝は固定HEADから作成し、D11未統合候補を混ぜていない。台帳の「固定a018」と
実branch先端の差はこの記録を正とする。

## 2. 今回の実装（候補）

- `backend/domain/stats-display.model.json` + 生成 `stats/generated/rates.py`:
  打率/出塁率/長打率/WHIPを **T6表示率だけ** として単一宣言。`facts.py`/`statsPrimitives.ts` は
  byte 不変で、T5 artifact set/native profile/5関数は変更していない。
- `backend/src/pitchlog/stats/basic_stats.py`: 27項目の写像。既存26十分統計 + OPS + 新T6率。
  D03（登板）/D04（打者数）は `source_unavailable` + 理由。0補完しない。
- `backend/src/pitchlog/stats/basic_sql.py`: 既存 `stats/generated/stats.sql` のscopeだけを
  試合/暦年・公式/暫定に差し替える候補SQLビルダー。式は追加しない。
- `backend/src/pitchlog/repositories/stats_basic.py`: `ReadBasicStatsToken` と固定関数登録。
- `backend/src/pitchlog/api/routers/stats.py`: JSON 4経路 + CSV 2経路。
  - `GET /games/{game_id}/stats?mode=current|official`
  - `GET /stats/seasons/{year}?category=official|practice|all`
  - `GET /games/{game_id}/stats.csv?mode=...`
  - `GET /stats/seasons/{year}/stats.csv?category=...`
- `frontend`: `SeasonStats.vue`（JST年/区分切替/CSV）、`GameStatsScreen.vue`（暫定/公式/CSV）、
  `BasicStatsTable.vue`（打撃16/投手11）。routerに `/stats/season`・`/games/:gameId/stats` を追加。
- 候補正式資産: `docs/features/mvp-basic-stats-csv/candidates/basic_stats_functions.sql`
  （SHA256 `bf9ab9d52fab486e109d397585bac994a9a4106563a3269497787d35e6a7b2e9`）と
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

- `backend/tests/stats/test_basic_stats.py` + 生成runtime + function boundary + native registration +
  function codec: **492 passed**。
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

## 5-1. マージ前ゲートの実測

- `uv run python scripts/check_tenant_boundary_bypass.py --base-ref a018b896` は
  **「固定tupleのreadonly原典全byteが不一致」で失敗**した。原因は新規
  `ReadBasicStatsToken` を `contracts/tenant_boundary/repository-contract.json` と
  生成 `repository_contract.py` に未登録のまま、runtime registryだけに追加しているため。
  共有tenant資産を直接編集しない指示に従い、`candidates/authz-diff.md` の差分を主担当が
  正式導出するまで本枝は**マージ不可**。この失敗を成功扱いしない。
- `scripts/core_guard.py` はPRイベント外のためスキップ（判定不能）。
- `contracts/`・seal・`first_ball_product`・`current_product_startup` の差分は0。

## 6. レビュー

- 本枝の独立非作者レビューは依頼中（結果は最終報告に追記）。自己確認のみで正式採用・
  製品提供・MVP完成とはしない。
- 既存のBF数学/取消/終了再開の採用済み判断を再承認待ちへ戻していない。
- 固定成功・仮の終了済みデータ・未定義0補完はしていない。D03/D04は明示的な未取得。
