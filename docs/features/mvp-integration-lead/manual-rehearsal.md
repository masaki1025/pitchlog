# 実機リハーサル手順（候補 `feature/mvp-integration-20261109@2371afee`）

実機・実ブラウザ・運用の成功を代記しないための準備票。候補環境の成功は、正式統合版・実機・運用公開の成功ではない。

## 接続先・環境

- 候補: `feature/mvp-integration-20261109@2371afee`（worktree）
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
| 5 | 27球目 | 現候補ではbroker再起動後 **B7/503**。書込みが0で、source_count=26のままであることを確認する（未回復を成功扱いしない） |
| 6 | 終了→再開→追加→再終了 | 正常v3経路で`lastVersion=2`、再送/再終了で二重加算しない |
| 7 | reload・成績27項目・成績CSV | 最新版のみ、旧版/訂正前を二重加算しない |

## 記録する証拠

- 固定HEAD、画面操作の時刻、HTTP status、ACK boundary。
- 対象試合の `operation_events` / `play_rows` / `stats_fact_versions` / P3 capsule items / CSV snapshots の件数。
- 27球目失敗時の `binding_age_ms`、DB `expires_at`、失敗時刻（30秒期限と5秒目標を別記録）。
- ZIPの行数と対象行の表示値。秘密値は保存しない。

## 既知の制限

- 27球目は非0 gate/right epoch復旧が未実装のため、broker再起動後の同一D5再送はB7/503。旧epochのまま書込みを許可しない。
- TLS資材・実機・共有DB・運用公開は未提供。候補環境の成功を実機成功へ拡張しない。
- 3試合×記録1台＋閲覧10台、バックアップ復旧は未実施。
- D11 `rbi` と旧v2/candidate DDL前提の試験に既知赤が残る。
