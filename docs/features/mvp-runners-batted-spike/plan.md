---
feature: mvp-runners-batted-spike
status: active
重さ分類: コア領域（spike・契約追補は未確定）
branch: feature/mvp-runners-batted-spike
base: feature/mvp-batted-hits@82557119314aebb5db3acb8704f71d1a91f82c9a
created: 2026-11-05
---

# 走者あり打球の接続spike（限定計画）

## 目的

無走者4安打の既存製品経路（v3 lineup prefix → 単一artifact → 同期核 → 同一TX保存 → GET/reload）を、
**記録者が明示した走者の実進塁**だけを使って走者ありの単打・二塁打へ接続し、隔離した使い捨てPostgreSQLで実測する。

調査で止めない。ただし、正本・`contracts/`・共有台帳は変更しない。必要な契約追補・artifact更新・pin更新は
`proposal.md` に分離し、このspikeの成功を正式受理・MVP完成へ読み替えない。

## 閉じた対象

| 項目 | このspikeで行うこと |
| --- | --- |
| シナリオA | 新規試合→開始→単打で一塁走者を作る→次の単打で「一塁走者→三塁、打者→一塁」を記録者が明示して確定 |
| シナリオB | 新規試合→開始→単打で一塁走者を作る→二塁打で「一塁走者→本塁（生還）、打者→二塁」を記録者が明示して確定 |
| 走者状態 | 実際の記録操作（先行する単打）だけで作る。DBへの事前投入・test-only保存APIで代替しない |
| 進塁 | 記録者が確定した明示的な到達塁だけ。既定進塁の自動拡張・推測補完をしない |
| フォース連鎖 | 打者の出塁でフォースされる走者は、到達先がさらに先でも`modality=forced`とする。forced走者のholdは成功にしない |
| wire検証 | 明示進塁の原値を旧形へ書き換えない。正準schemaを複製したspike拡張schemaで、元のwire値を厳格に検証する |
| D07 | 二死二三塁の単打1行だけ、という既存の限定を変更しない。今回の配置へ拡張しない |
| 得点・打点 | 既存の付録A-3/RBI-08の範囲で、明示観測（失策なし・妨害なし・第3アウトなし）から決まる値だけを返す。因果観測が不足する分岐は成功にしない |
| 対象外 | 一塁以外の走者、複数走者、走者ありの三塁打/本塁打、走者アウト、併殺、失策、妨害、第3アウト時機、サヨナラ/コールド、取消/訂正、交代、タイブレーク、複数走者の同時進塁一般 |

## 既存経路の再利用

- 唯一の計算核: `frontend/src/domain/state.ts` の `applyCountRule` と `battedHit.ts`。
  走者進塁は旧spike（`feature/ux1-roundtrip@41d7175d`）の `advanceFor` と同じ
  `Rule.advance` / `Rule.explicit` の一般核を**同じmodule内へ戻して使う**。別module・別算式を作らない。
- 唯一のartifact: `frontend/scripts/domain-build/build.mjs` が生成する
  `frontend/public/domain/pitchlog-domain.js` / `.json`。手編集しない。
- 製品入口: `deriveLineupPlayPrefixWithContinuation`。既存のv3 source/T2/履歴/queue/ACK/GETを維持する。
- 保存: 既存の `prepare_play_prefix_projection` / `runner_physical_rows` / 同一TX admission。
  物理`play_runners`は従来どおり**before各塁**を保存し、after占有はcheckpoint/sourceへ保存する。
- 実測: 既存の `vertical_database` / 実HTTPS / 実認証 / 実記録権 / Playwright の画面操作。
  新規の固定応答・mock・DB事前投入は使わない。

## 候補wire（spike限定・契約追補前）

既存の `runnerAdvanceOverridesByRunner` は `{kind:"not-applied",overrides:[]}` に閉じている。
このspikeでは、記録者が明示した進塁だけを次の閉形で運ぶ候補を使う。

```json
{
  "kind": "applied",
  "overrides": [
    { "runnerBase": "1", "destination": "3" }
  ]
}
```

- このspikeの`runnerBase`は一塁走者を表す`"1"`だけ。`overrides`は1件だけを受理する。
- `destination` は `"2"|"3"|"4"`。`"4"` は生還。
- 一塁走者は打者の出塁でフォースされるため、到達先が三塁・本塁でもT1は`forced`を返す。
- 列挙しない占有塁はhold。ただし打者到達塁と衝突するholdは拒否する。
- 走者アウト・帰塁・複数走者・一塁以外・走者あり三塁打/本塁打はこのspikeの成功入力にしない。
- T1入力の `runnerAdvanceOverrides` は既存の文字列`not-applied`または`applied` object、
  V7観測の `runnerAdvanceOverridesByRunner` は既存の`not-applied` objectまたは`applied` objectを運ぶ。
- 既存の `not-applied` は無走者・進塁なしの既存経路として完全保持する。
- 明示進塁の原値は旧形へ書き換えず、正準schemaを複製したspike拡張schemaで検証する。

## 期待するT1効果（独立固定）

| シナリオ | before | 明示override | after runners | 得点 | 23flags |
| --- | --- | --- | --- | --- | --- |
| A: 単打 | 一塁走者、打者→一塁 | 一塁→三塁 | 一塁（打者）+ 三塁（走者） | 0 | 非HRの6true/17false |
| B: 二塁打 | 一塁走者、打者→二塁 | 一塁→本塁 | 二塁（打者） | +1 | 非HRの6true + 得点/打点（RBI-08） |

- 両シナリオともカウントはreset、打席終了、旧攻撃側cursorだけ次打順、outs/half/inning不変。
- 走者の選手ID・責任投手は、先行プレイで作られた実source runnerを引き継ぐ。
- 得点はbefore.halfの攻撃側へ加算する。打点はRBI-08で1（シナリオBのみ）。
- 第3アウト・失策・妨害・HRの既定進塁を推測しない。

## 実装ステップ（このspike内）

| ステップ | 内容 | 停止条件 |
| --- | --- | --- |
| 1 | 単一核へ明示進塁の一般核を戻し、battedHitの閉観測を拡張。独立手例・既存無走者回帰・衝突拒否を固定 | 既存無走者goldenが1件でも変わるなら停止 |
| 2 | v3 prefixのprepare/finishへ候補観測を接続。source runnerからafter runnerを導出し、T1/T2/履歴へ渡す | source/参加者/runner identityの不一致を成功にしない |
| 3 | 保存境界（Pydantic DTO・物理runner・SQL admission）へ候補観測を接続。同一TX/再送/越境/rollbackを維持 | 既存のnot-applied経路を緩める必要が出たら停止 |
| 4 | 実画面E2Eを追加し、シナリオA/B・再送・reloadを実測。DB保存値とGETを照合 | 画面で走者状態を作れない、または実artifact/実DBへ到達できないなら記録して停止 |
| 5 | 証拠・未達・変更パス・正式追補を`report.md`/`proposal.md`へ固定 | 正本/contracts/共有台帳を変更しない |

## 検証

- frontend: Vitest（単一核、battedHit、prefix continuation、wire）と `vue-tsc` / eslint。
- backend: 対象Pydantic/DTO/物理row/SQL境界のpytest。既存no-runner回帰を保持。
- 実測: 使い捨てPostgreSQL + 実HTTPS + 実ログイン + 実端末登録 + 実開始。
  - シナリオA/Bの保存後GETとreloadで、走者ID・得点・アウト・カウント・打順・履歴を照合。
  - 同一要求の再送が`重複`で、得点・安打・履歴が二重加算されないこと。
  - 別tenantの要求が拒否され、元tenantの状態が変わらないこと。
  - 途中故障（保存境界の注入）で親・runner・履歴・checkpoint・ledgerが全取消になること。
- 得点・打点は既存契約の範囲だけを検査し、不足観測を推測で補わない。

## 正本・契約への提案（変更しない）

1. `contracts/state-transition/lineup_play_prefix_payload_v1.d.ts` と
   `lineup_play_prefix_payload_schema_v1.json` の `runnerAdvanceOverridesByRunner` を、
   `applied` 候補と閉相関させる追補。
2. `contracts/state-transition/lineup_play_prefix_v1.d.ts` の `BattedHitT1Input.runnerAdvanceOverrides`
   と `T1.runnerDefaultAdvance`（現在hold/not-applicableのみ）の追補。
3. artifact SHA/pin/D11/manifest/censusの正式追随。
4. 走者アウト・併殺・妨害・第3アウト・HR with runners等の別単位。

これらは`proposal.md`に分離し、このspikeのコード変更を正式受理と扱わない。
