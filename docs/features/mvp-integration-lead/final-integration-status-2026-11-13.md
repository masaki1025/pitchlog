# 最終統合候補の実測（2026-11-13）

対象: `feature/mvp-integration-final-20261113` HEAD `7c07fccb`
統合元: タイブレーク候補 `2ed9fa30`、正式資産 `dd8b4a90`、性能 `ed0c4f2f`、7回制 `da2bcb01`、引き継ぎ `56e99ea5`、断中登録 `df8f37d0`。
`feature/mvp-integration-20261109@216d09e6` を祖先に含む。

## 実証済み

- フロント全件: **222 files / 4188 tests passed**
- backend 対象（domainrt、v7/v8、registry、登録、引き継ぎ、規則）: **1595 passed**
- 実DB交代縦断: **1 passed / 102.51秒**（製品資産・migration 0051を含む）
- 実DB通常引き継ぎ: **2 passed / 85.02秒**（旧holder拒否・新holder再開）
- 初球同期（timing有効）: **totalMs=3699.7 / 5秒目標 met**
- 初球実HTTP（timingなし）: **1 passed / 92.47秒**

## 未通過・残差（成功扱いしない）

- **タイブレーク実DB/実画面E2E**: `test_tiebreak_start_vertical_http.py` は、10回CPのlegacy v3直接seedがP3 current/lifecycle GETと整合しないため **skip**。製品資産setupの通過は交代縦断で確認したが、タイブレークイベントの実DB保存・次球・生還・再配置・成績/CSVは未通過。
- 7.7: `tests/test_check_tenant_boundary_bypass.py` は **563 failed / 272 passed / 2 errors**。PR197 facts/sourceの後継受理候補は独立レビュー待ちで、自己承認していない。
- 製品供給: `test_sync_apply_product_supply.py` に **5 failed**（生成statement件数・後継fixture受理待ち）。
- 7回制: `rule_sets` 実行列が未作成。実ブラウザcreate→start→record→end→reloadは未実行。
- 断中登録: 実DB E2Eはbaseline fixtureの赤で未実行。server-sideの一時ID参照substitution解決は未実装（画面は確定まで適用を保留）。
- 引き継ぎ: 緊急経路と専用の結果不明照会・終結は未実装。実ブラウザ2端末E2Eは未実施。
- 性能: lifecycle E2Eの6同期は未計測（UI/networkでE2Eがsync前に失敗）。初球/通常球の5秒達成は確認したが、3試合×記録1台＋閲覧10台の実測は未完了。
- 実機・本番TLS・バックアップ復旧・運用公開は後日受入。

## 判定

`7c07fccb` は「複数トラックを統合した最終候補」であり、MVP完成版・正式受理済みではない。上記の未通過を解消するまで最終マージ・完了報告をしない。


## 2026-11-14 追試（HEAD `7d84b7b3`）

9回消化後のタイブレークE2Eを実画面/実DBで実行し、タイブレーク開始POSTまで到達した。通過した工程:

- 9回54アウトの実画面保存
- タイブレーク発動回のロック表示
- 配置選手選択から `tiebreak_start` POST の発行
- 製品資産（`consume_nonplay_tiebreak_start` / receipt table）の実DB setup
- 非play CP ref を `readCompleteUndoGame` から取得してpayloadへ束縛
- 資格scope（`tiebreak_start`）とport登録（`TiebreakStartProjectionPort`）の実接続

最後の停止:

- サーバーの `read_confirmed_nonplay_prefix` が **`NonplaySourceUnavailable: 交代frameの連結が不一致です`** を返した。
- 9回54frameのnonplay source chainで、隣接play frameの `afterContext` と次frameの `beforeContext` が一致しない区間がある。2球程度の既存substitution縦断では再現せず、長い試合のsource chainで顕在化する。
- このため `test_tiebreak_screen_e2e.py` は skip。タイブレーク開始POSTの内容・製品資産・資格・CP refは通過済みだが、保存成功・生還・交代・再配置・reloadは未通過。

製品供給:

- `tests/test_sync_apply_product_supply.py` は 2642 passed / 4 failed。
- 残りは batted source extension reference の後継（terminal 30文のうち変更された読み取り関数）と stats extension pin の再導出。`catalog_after_revision` の後継受理が必要。


## 2026-11-14 追試2（HEAD `84ec5b7d`）

- 9回54frameのnonplay source chainに `tiebreakFrames` を接続し、`NonplaySourceUnavailable: 交代frameの連結が不一致` を解消した。
- タイブレーク開始のnative台帳へ `_fresh_tiebreak` を追加し、実評価frameの同一性・lease・phase・payloadを保持した。
- 画面は非play CP refを `readCompleteUndoGame` から取得し、タイブレーク開始POSTまで到達。
- 残る停止: `consume_nonplay_tiebreak_start` のSQL実行後に `psycopg.errors.InFailedSqlTransaction: current transaction is aborted` が返る。先のSQLエラーが後続の `assert_writer_binding` で隠れており、元エラーの特定が必要。
- このため `test_tiebreak_screen_e2e.py` は skip を維持。タイブレーク保存成功・生還・交代・再配置・reloadは未通過。


## 2026-11-14 追試3（HEAD `84ec5b7d` + 診断）

- `consume_nonplay_tiebreak_start` の最初のSQLエラーを捕捉した。
- 結果: **`P0002 query returned no rows`**、関数本体 line 57 の
  `SELECT c.* INTO STRICT cp FROM sync_fence.ordinary_pitch_checkpoints ...`
  で0行。
- 条件は `c.internal_generation=stamp.internal_generation` と
  `c.recovery_generation=stamp.recovery_generation`。nonplay stampとCP行の
  世代/復旧世代が一致していない。
- 後続の `assert_writer_binding` が `InFailedSqlTransaction` を返していたため、
  元エラーはこれまで隠れていた。
- 修正対象: tiebreakのnonplay consumeへ渡すstampの世代（D4/internal）と
  CP行の世代の対応。substitutionの同SQLは2球試験で通るため、長い試合/
  legacy CPでの世代解決差を追う。


## 2026-11-14 追試4（世代の実測）

9回E2Eの失敗後にowned PGを読み取り専用で照合した。

- CP: `internal_generation=1`, `recovery_generation=1`, `state=current`,
  `revision=55`, `content.version=3`（legacy v3）。
- `recording_generations`: `(generation,recovery_generation)=(1,1)`。
- `nonplay_write_admissions`: 失敗TXのrollbackにより0行。
- したがってCP側の世代は1/1で一貫しており、残る不一致は
  `consume_nonplay_tiebreak_start` に渡るnonplay stampの世代値。
- 次の最小再現: 2球程度のnonplay admissionを作り、stampの
  internal/recoveryをCP行と比較する短いDB試験を追加する。54アウトE2Eの
  反復は修正後まで行わない。
