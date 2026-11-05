# 走者あり打球spike — 正式追補の提案（未適用）

このspikeは`contracts/`・正本・共有台帳を変更していない。以下は、実測した候補経路を正式化するために
必要な追補であり、**採用・反映は別ゲート**とする。spikeの成功を正式受理・MVP完成へ読み替えない。

## 1. V7観測の明示進塁

### 現状

`contracts/state-transition/lineup_play_prefix_payload_v1.d.ts` と
`contracts/state-transition/lineup_play_prefix_payload_schema_v1.json` は
`runnerAdvanceOverridesByRunner` を `{kind:"not-applied",overrides:[]}` に閉じている。

### 提案

記録者が確認した実進塁だけを、次の閉形で受理する。

```json
{
  "kind": "applied",
  "overrides": [
    { "runnerBase": "1", "destination": "3" }
  ]
}
```

- `runnerBase`: beforeで占有している `"1"|"2"|"3"`。
- `destination`: `"2"|"3"|"4"`。`"4"`は生還。
- 空配列は未確認として拒否する。
- 列挙しない占有塁はhold。打者到達塁との衝突は拒否する。
- 走者アウト・帰塁・複数走者の一般形は別単位。

V7とT1の両方で同じ内容を運び、SQL admissionでも両者の一致を検査する。

## 2. T1入力・T1応答の進塁型

### 現状

`contracts/state-transition/lineup_play_prefix_v1.d.ts` は
`BattedHitT1Input.runnerAdvanceOverrides` を `"not-applied"` に、
`T1.runnerDefaultAdvance` を `hold|not-applicable` + `destination:null` に閉じている。

### 提案

- `runnerAdvanceOverrides`: `"not-applied"` または上記`applied`。
- `runnerDefaultAdvance`: 既存`hold|not-applicable`に加え、
  `optional|forced` + `destination:"1"|"2"|"3"|"4"`を受理する。
- `optional|forced`は`destination != null`、`hold|not-applicable`は`destination == null`の
  双方向制約を維持する。
- 打者到達塁と走者到達塁の重複を拒否する。

## 3. artifact・pin・manifest

- 唯一artifactのSHAは `5f4caa1f89963fadbad2664dd245dac94afb91977e525fbd5acf01949a3fcc28`
  （65773 bytes、公式builder再生成）。
- `backend/domain/*manifest.json` の`directTargets[].hash`を上記へ更新する。
- `contracts/state-transition/batted_hit_d11_vectors_v1.json`、
  `batted_hit_prefix_cases_v1.json`、`lineup_play_prefix_d11_vectors_v1.json`等の
  execution pinを正式手順で追随する。
- `backend/tests/domainrt/test_batted_hit_d11.py`等のpin期待を更新する。
- `census-baseline.json`・tenant boundary・frozen inputs等の共有台帳は公式helperで再導出する。

## 4. 製品SQL関数bodyの正式契約

`contracts/authz/product/function-bodies/functions/FUNCTION:sync_right_api:prepare_play_prefix_projection(...).sql`
は旧bodyのままである。spikeの実測では、次の一時ローカル差分（**未コミット**）を適用した。

- 物理`play_runners`のT1進塁検査を`hold`固定から`hold|optional|forced`へ拡張。
- 観測`runnerAdvanceOverridesByRunner`とT1`runnerAdvanceOverrides`の一致検査を追加。

正式化には、`terminal_pitch_write_stamp.py`の生成bodyと上記契約asset・
`first_ball_product`の凍結bodyを同一ゲートで更新する必要がある。

## 5. 走者物理行の意味

`runner_physical_rows`は従来どおり**before各塁**を`play_runners`へ保存し、
after占有はcheckpoint/sourceへ保存する。今回、before走者のT1進塁が`optional|forced`でも
物理行のbase/runner ID/責任投手はbeforeのまま保持する、という既存意味を明示する追補が必要。

## 6. 追加が必要な正式試験

- 走者あり単打・二塁打のV7/T1/D11ゴールデンケース。
- 同一要求再送・別tenant拒否・途中故障全取消のrunner固有ケース。
- 実画面E2Eの正式登録（今回のspike E2Eは候補）。
- 走者アウト・併殺・失策・妨害・第3アウト時機・HR with runnersの別単位。

## 7. 採用しないもの

- D07の既定進塁を二死二三塁の単打以外へ拡張しない。
- 走者状態のDB事前投入・test-only保存API・固定成功応答を正式経路にしない。
- 今回のspikeコードを正式受理済み・全NFR成立・MVP完成と扱わない。
