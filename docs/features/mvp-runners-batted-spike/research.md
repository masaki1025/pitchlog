# 走者あり打球の接続spike — 調査メモ

## 基点と確認した正本

- 基点: `feature/mvp-batted-hits@82557119314aebb5db3acb8704f71d1a91f82c9a`
- 確認: `AGENTS.md`、`docs/features/mvp-batted-hits/plan.md`、要件書 FR-003/004/005、付録A-3 RBI-01..09、付録E-1 ADV-01..04、D07限定行。
- D07は「二死二三塁の単打」1行だけ。今回の一塁走者配置へ既定進塁を拡張しない。

## 実コードの現状

| 層 | 現状 | 影響 |
| --- | --- | --- |
| `frontend/src/domain/battedHit.ts` | `before.runners !== 'empty'` と `runnerAdvanceOverrides !== 'not-applied'` を拒否 | 一塁走者がいる次の打球を計算できない |
| `frontend/src/domain/state.ts` | `applyCountRule` は `advance:'hold_all'` 前提。走者進塁の一般核は旧spikeにのみ存在 | 走者を三塁/本塁へ動かす単一核がない |
| `frontend/src/domain/lineupPlayPrefixContinuation.ts` | `finishLineupContinuation` は打者到達時、既存runnerを捨てて打者1人だけをafter runnersにする | 走者ID/責任投手を引き継げない |
| `frontend/src/screens/GameScreenOrdinaryPitch.vue` | `hitAvailable` が `state.runners === 'empty'` を要求 | 走者ありで打球入力画面を開けない |
| `frontend/src/screens/GameScreenBattedHitObservation.vue` | 「走者進塁の手動上書きなし」を確認するだけ | 走者の実結果を入力できない |
| `contracts/state-transition/lineup_play_prefix_payload_v1.d.ts` / schema | `runnerAdvanceOverridesByRunner` は `not-applied` 固定 | 正規payloadへ明示進塁を載せられない（契約追補が必要） |
| `contracts/state-transition/lineup_play_prefix_v1.d.ts` | `BattedHitT1Input.runnerAdvanceOverrides` は `"not-applied"`、`T1.runnerDefaultAdvance` は hold/not-applicable 固定 | 同上 |
| `backend/src/pitchlog/domainrt/lineup_play_prefix_continuation.py` | `BattedHitT1Input` / `T1.runner_default_advance` が同様に固定 | 候補payloadをdecodeできない |
| `backend/src/pitchlog/sync/terminal_pitch_projection.py` | `runner_physical_rows` がbefore runnerのT1 hold/nullを要求 | 進塁する走者の物理rowを作れない |
| `backend/src/pitchlog/authz/terminal_pitch_write_stamp.py` | 埋込みSQLが観測/T1の`not-applied`とrunner hold/nullを固定検査 | 候補payloadの同一TX保存を拒否する |

## 再利用できる既存資産

- 旧spike `feature/ux1-roundtrip@41d7175d` の `state.ts` には `advanceFor` / `explicit` / `force` の一般核がある。数式を新設せず、この一般核を現行`state.ts`へ戻して使う。
- 既存E2E `frontend/src/screens/GameScreenBattedHits.e2e.ts` と `backend/tests/db/test_batted_hits_screen_e2e.py` は、実HTTPS・実認証・実端末登録・実開始・実sync・再送・reload・DB照合を既に持つ。
- `backend/tests/db/test_screen_start_e2e.py` の `vertical_database` / `_browser_environment` / `_run_playwright` は使い捨てPostgreSQLと実appの起動を持つ。
- `backend/tests/db/test_batted_hit_storage.py` は途中故障の全取消を既に検査している。走者ケースを追加できる。

## 停止条件（このspikeで変更しないもの）

1. 正本・`contracts/`・共有台帳（`backend/domain/*manifest*`、`contracts/tenant_boundary/*`、census等）は編集しない。
2. 既存無走者4安打のgolden応答を変えない。
3. D07の既定進塁を他配置へ拡張しない。
4. 走者アウト・併殺・失策・妨害・第3アウト時機・HR with runnersは成功入力にしない。
5. 正式artifact pin/D11/manifest/censusの追随は提案に分離する。

## 実測方針

- 走者状態は画面の先行単打で作る。
- 2球目は画面で走者の到達塁を明示選択し、確定する。
- 保存後のGET/reloadで、`runners`（選手ID・責任投手・塁）、`after.stateFields`、`scoreboard`、`history`、`page.items`を照合する。
- 同一要求再送は既存の`__repeatBattedForTest`と同じ方法で行い、`a5Result='重複'`とDB件数不変を確認する。
- 越境は別tenantの実認証/実記録権で拒否を確認する。途中故障は保存境界の注入で全取消を確認する。
