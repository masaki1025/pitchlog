---
feature: mvp-interference-v6-compat
status: draft
承認: 未了
重さ分類: コア領域
branch: feature/mvp-interference-integration-candidate-20261108
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-interference-integration-candidate-20261108
created: 2026-11-08
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 妨害artifactの有限v6互換と現行pin候補

基点は隔離候補 `17732cd9224ddb1cb5017cc7e9960b5b505a7243`。旧公式artifact `71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff` と新公式artifact `0e260cd916e4cd4da189132a52adb3e065f261d477bc65f5352bb121e8b45f15` を実Git/公式hostで照合する。既v1–v5 witness/registry・validator本体・旧53数学期待・runtime10原本を全byte保持し、有限v6だけを追加する。未知prior/execution、余分操作、改変数学は拒否する。正式7.7、SQL妨害overlay、core採否、実PGはrootの後続範囲。

## 編集範囲

- 新2資産: `contracts/state-transition/nonplay_v3_compatibility_witness_v6.json`、`contracts/state-transition/play_prefix_v3_source_compatibility_v6.json`。
- 有限検証: `backend/src/pitchlog/repositories/play_prefix.py`、新 `backend/tests/test_interference_v6_compatibility.py`、既 `backend/tests/test_batted_operations_v5_compatibility.py`、`backend/tests/test_runner_v3_compatibility.py`、`backend/tests/test_batted_operations_schema.py`。旧v5検証関数は不変更。runtime10原本fixtureは不変更で、実71f hostと新hostの比較を別検査にする。
- 現行metadata: `frontend/src/api/fixtures/{currentPlayPrefixV2Payload.v1,currentLineupPrefixPayload.v1,currentFirstBallPayload.v1,currentBattedHitPrefixCases.v1,nativeUndoProduct.current.v1}.json`、`contracts/state-transition/{lineup_play_prefix_d11_vectors_v1,batted_hit_d11_vectors_v1,strikeout_pitch_d11_vectors_v1,game_lifecycle_d11_vectors_v1,play_prefix_v2_d11_vectors}.json`。旧規範数学は固定し、実行SHAと正準自己echoだけ追随する。既7 domain manifest は前ステップで新artifactへ追随済みのため編集しない。
- 開始投手の現行実行pin: `contracts/authz/product/function-bodies/functions/FUNCTION:initial_right_api:persist_start_pitcher_entry(uuid, uuid, bigint).sql` と対応純対向 `backend/tests/test_batted_operations_product_bodies.py`。既 `stats_appearance.candidate_start_entry_function()` の唯一生成本文を使用し、旧3pin以外の本文、署名、owner、ACLは不変。既79 selected/canonical全値一致をDB前に検査する。正式authz資産の受理値生成はrootへ渡す。
- 本計画とcache内の導出script・差分/全値証拠。追加pathが不可避なら本計画へ先に追記してrootに伝える。共有main、他WT、台帳、DBは不変更。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 旧71fと新0e26の実hostからv6有限53証拠を導出 | 旧v5原本/旧raw全hash不変、4自己識別値以外の全値一致、有限pair/unknown拒否を対向化 |
| 2 | 現行pin/D11/runtime10/開始投手生成SQLを接ぐ | 元期待を新actualから採取せず、旧原本保持、公式BODIESと79選択本文全値一致 |
| 3 | pure検査と候補packetを固定 | 変更path前後SHA、再生成一致、残root条件を明示し、実PG・正式7.7成功と区別 |
