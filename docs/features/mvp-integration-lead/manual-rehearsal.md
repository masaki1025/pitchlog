# 実機リハーサル手順（候補 `feature/mvp-integration-20261109@85fdbfa5`）

実機・実ブラウザ・運用の成功を代記しないための準備票。候補環境の成功は、正式統合版・実機・運用公開の成功ではない。

## 接続先・環境

- 候補: `feature/mvp-integration-20261109@85fdbfa5`（worktree）
- DB/権利worker: 隔離owned PostgreSQL + owned RG1/binding worker。共有DB・利用者データへ適用しない。
- HTTPS: 既存のループバック証明書/鍵PATHを
  `PITCHLOG_E2E_TLS_CERT_PATH` / `PITCHLOG_E2E_TLS_KEY_PATH` に絶対PATHで渡す。
  未供給時は実ブラウザHTTPS試験を未実施として扱い、HTTP成功で代替しない。
- frontend: Vite preview（`pnpm exec vite preview`）を app の `/api` proxy と共に起動。
- 端末: 記録用1端末（cookie/端末資格を保持）と閲覧用1端末以上。Chrome/Safariの実機または実ブラウザ。
- 秘密: Cookie・端末資格・V12・TLS鍵を画面/ログ/チケットへ出さない。

## データ準備

1. 専用tenantに2チーム、打順・守備位置・投手/捕手を含む名簿を用意する。
2. 画面から新規試合を作成し、開始する（fixtureの既存gameを新規作成の証拠にしない）。
3. 26球を実画面から記録する（P3対象はd1=26）。
4. 対象d1=26の変更対象を取得し、置換結果を「ボール」等の正式closed keyにする。
5. 27球目以降の追加、終了・再開・再終了、CSV取得の順を固定する。

## 操作手順と期待結果

| # | 操作 | 期待 |
|---|---|---|
| 1 | ログイン→端末登録→試合開始 | 201、開始応答、端末資格が画面に保持される |
| 2 | 26球記録 | 各球ACK、GET/reloadで状態・履歴が一致 |
| 3 | d1=26の過去訂正 | ACK `変更受理`、confirmation、capsule/head、P3 snapshot 26件 |
| 4 | ZIP取得 | `GET /games/{id}/exports/plays.zip` 200、26行、d1=26「ボール」 |
| 5 | 27球目 | 候補実測 **受理**。P3訂正後の27球目はprefix=27、play_rows=28（26元+P3有効版1+27球目） |
| 6 | 終了→再開→追加→再終了 | 候補実測 **受理**（追加play=28球目、`lastVersion=2`）。追加playのbinding ageは7.558秒で30秒内、**5秒目標は未達**。broker再起動を挟む場合は別試験の非0 epoch復旧条件に従う |
| 7 | reload・成績27項目・成績CSV | 候補実測 200。play_rows=29、stats current `source_count=28`/`confirmed_ended`/current版1、ゲームCSV 20行・シーズンCSV 10行。旧版/訂正前を二重加算しない |

## 終了条件の候補E2E（2026-11-11追加）

- 実行: `cd backend && PITCHLOG_E2E_TLS_CERT_PATH=... PITCHLOG_E2E_TLS_KEY_PATH=... uv run pytest -q tests/db/test_end_conditions_screen_e2e.py`
- シナリオ: `game_semi_official`の7点差7回コールド、`game_other`の9回同点limit-draw、`game_official`の10回タイブレーク発動ロック。**候補実測: 1 passed / 1491.83秒（Playwright 3 passed / 23.9分）**。
- 期待: cold-end 49 `play_input` + `game_end_declaration`、limit-draw 54 + 終了宣言、tiebreak-required 54 `play_input`で`in_progress`のまま。記録画面には`ordinary-pitch-locked`で理由を表示する。
- 7回規則・延長上限>9・タイブレーク開始操作・担当交代・その場登録は未接続であり、このE2Eの成功へ読み替えない。

## 9回通常試合の現HEAD再測（2026-11-11）

- `test_full_game_screen_e2e` **1 passed / 1653.21秒**。163球、18半回、1–0、normal-end、終了版v1。
- 性能は **最大10736ms / 163球すべて5秒超**。機能完走をNFR-002の5秒達成へ読み替えない。

## 記録する証拠

- 固定HEAD、画面操作の時刻、HTTP status、ACK boundary。
- 対象試合の `operation_events` / `play_rows` / `stats_fact_versions` / P3 capsule items / CSV snapshots の件数。
- 追加play又は失敗時の `binding_age_ms`、DB `expires_at`、失敗時刻（30秒期限と5秒目標を別記録）。
- ZIPの行数と対象行の表示値。秘密値は保存しない。
- 追加playの`binding_age_ms`と5秒目標の実測（候補: 7.558秒、30秒内）。lifecycle readの所要（候補: P3 packet cache hit時 約1.6〜2.0秒）。

## 既知の制限

- P3訂正直後（27球目前）の`lifecycle-prefix-v1`も候補実測200（capsule 26 itemの実効stackを同じ公開viewへ再構成）。27球目後の祖先P3 readも200。
- 同一epochのbroker再起動（記録中に子PID kill→supervisor再起動）は候補実測で27球目まで成立。非0 gate/right epoch復旧は未実装のため、fail-closed後の旧epoch同一D5再送はB7/503のままで、旧epochの書込みを許可しない。
- TLS資材・実機・共有DB・運用公開は未提供。候補環境の成功を実機成功へ拡張しない。
- 3試合×記録1台＋閲覧10台、バックアップ復旧は未実施。
- D11 `rbi` と旧v2/candidate DDL前提の試験、固定registry期待の`test_void_adapter_preserves_every_other_registered_function`に既知赤が残る。
- 2026-11-11追記: 通常球が終了条件/タイブレーク開始で閉じたとき、記録画面に`ordinary-pitch-locked`で理由を表示する。コールド/引き分け/タイブレーク発動回の実画面E2Eは候補環境で追加したが、7回規則・延長上限>9・タイブレーク開始操作・担当交代・その場登録は未接続。実機ではこれらを成功扱いにしない。
