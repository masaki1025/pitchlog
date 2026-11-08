---
feature: mvp-interference-v6-compat
status: active
承認: 済（PO委任Codex主担当/root限定採用、2026-11-08 22:06 JST、対象計画SHA2a517a859e1f646c1d2173b0458330a115e377752268fad9cf59ecff17a4bcaf）
重さ分類: コア領域
branch: feature/mvp-interference-integration-candidate-20261108
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-interference-integration-candidate-20261108
created: 2026-11-08
計画レビュー周回: 1
確定ゲート周回: 0
実行方式: 通常
---

# 妨害artifactの有限v6互換と現行pin候補

基点は隔離候補 `17732cd9224ddb1cb5017cc7e9960b5b505a7243`。旧公式artifact `71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff` とINT-04修復済み公式artifact `859986408d75994d6f1530ce99c0331da1644da9d5ae6339bb479e3926ee7f2e` を実Git/公式hostで照合する。初版計画で対象とした `0e260cd916e4cd4da189132a52adb3e065f261d477bc65f5352bb121e8b45f15` はINT-04反例により未採用とし、許可priorにも含めない。既v1–v5 witness/registry・validator本体・旧53数学期待・runtime10原本を全byte保持し、有限v6だけを追加する。未知prior/execution、余分操作、改変数学は拒否する。正式7.7、SQL妨害overlay、core採否、実PGはrootの後続範囲。

## 編集範囲

- 新2資産: `contracts/state-transition/nonplay_v3_compatibility_witness_v6.json`、`contracts/state-transition/play_prefix_v3_source_compatibility_v6.json`。
- 有限検証: `backend/src/pitchlog/repositories/play_prefix.py`、新 `backend/tests/test_interference_v6_compatibility.py`、既 `backend/tests/test_batted_operations_v5_compatibility.py`、`backend/tests/test_runner_v3_compatibility.py`、`backend/tests/test_batted_operations_schema.py`。旧v5検証関数は不変更。runtime10原本fixtureは不変更で、実71f hostと新hostの比較を別検査にする。
- 現行metadata: `frontend/src/api/fixtures/{currentPlayPrefixV2Payload.v1,currentLineupPrefixPayload.v1,currentFirstBallPayload.v1,currentBattedHitPrefixCases.v1,nativeUndoProduct.current.v1}.json`、`contracts/state-transition/{lineup_play_prefix_d11_vectors_v1,batted_hit_d11_vectors_v1,strikeout_pitch_d11_vectors_v1,game_lifecycle_d11_vectors_v1,play_prefix_v2_d11_vectors}.json`。旧規範数学は固定し、実行SHAと正準自己echoだけ追随する。既7 domain manifest は前ステップで新artifactへ追随済みのため編集しない。
- 開始投手の現行実行pin: `contracts/authz/product/function-bodies/functions/FUNCTION:initial_right_api:persist_start_pitcher_entry(uuid, uuid, bigint).sql` と対応純対向 `backend/tests/test_batted_operations_product_bodies.py`。既 `stats_appearance.candidate_start_entry_function()` の唯一生成本文を使用し、旧3pin以外の本文、署名、owner、ACLは不変。既79 selected/canonical全値一致をDB前に検査する。正式authz資産の受理値生成はrootへ渡す。
- 本計画とcache内の導出script・差分/全値証拠。追加pathが不可避なら本計画へ先に追記してrootに伝える。共有main、他WT、台帳、DBは不変更。

## INT-04反例の是正範囲（root委任追補）

旧候補0e26に対し、妨害された実打者走者が一塁到達前であるのに `play_kind=no-play-on-obstructed-runner` とした入力から打者アウトを返す反例が見つかった。正本INT-04の「または打者走者が一塁到達前」を唯一核へ適用し、裁定アウトと実授与欠落を閉拒否する。追加編集は `frontend/src/domain/interference.ts`、同 `interference.spec.ts`、`frontend/src/screens/GameScreenInterferenceObservation.vue` と同spec、`backend/src/pitchlog/domainrt/lineup_play_prefix_continuation.py`、`backend/tests/domainrt/test_interference_input.py`、`backend/tests/test_interference_payload_boundary.py`。二重の得点/野球計算は増やさず、BEは同一裁定の閉形・ID検証、画面は確認前の矛盾排除に限る。

是正後は本計画のartifact2・manifest7・v6資産2・現行metadata10・開始投手SQL1と対応testを新固定SHAへ一括再導出する。未採用0e26を許可priorへ追加しない。旧71fの53数学/10runtime/過去原本は保持する。元1e15/0e26の候補履歴を成功版へ読み替えない。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 旧71fと修復済み859の実hostからv6有限53証拠を導出 | 旧v5原本/旧raw全hash不変、4自己識別値以外の全値一致、有限pair/unknown拒否を対向化 |
| 2 | 現行pin/D11/runtime10/開始投手生成SQLを接ぐ | 元期待を新actualから採取せず、旧原本保持、公式BODIESと79選択本文全値一致 |
| 3 | pure検査と候補packetを固定 | 変更path前後SHA、再生成一致、残root条件を明示し、実PG・正式7.7成功と区別 |

## 実装記録

- ステップ1の初版: Git基点の旧71f IIFE/宣言と当時の0e26を各1 hostで旧v5の53入力に実行した。この初版は後発INT-04反例で未採用。修復済み859で同じ53入力・旧期待との全値比較をやり直し、4自己識別欄以外の全値一致を確認した。新v6は旧5 priorと現自己だけの6組を閉登録し、旧v1–v5原本と旧validator本体を保持した。
- ステップ2: 旧metadata10ファイルの元byteをshadowへ固定し、旧計算期待から実行SHAと依存する正準digestだけ再導出。全変更leafを自己識別欄へ限定した。旧runtime10 fixtureを保持し、実Git旧71f hostと現公式hostの数学全値比較を別試験に追加。開始投手SQLは旧3pinだけ新値へ換えて公式生成本文とbyte一致し、選択79関数も全本文一致した。
- INT-04追補: 未採用0e26候補の「一塁前打者アウト」を `3632467d` の唯一核・閉API・画面で拒否。公式artifact `cadd2ac8` の85998640へ再生成し、Git旧71f→fixed859の53件/6組だけを再導出。旧0eを先行許可版へ含めない。現行metadata10も真の旧71f byteから固定SHAへ再導出し、開始投手SQLの3pin/選択79本文を再照合した。
- ステップ3: 固定859版で互換・schema・開始投手SQL・旧v5回帰のbackend128件を通過。現行metadataと妨害入力のfrontend24件、型検査と静的検査を実施し、変更pathの前後byteと候補差分をcacheに封印する。作者検査であり、非作者レビュー、正式値受理、実PG、妨害のSQL保存は後続のまま残す。
