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
