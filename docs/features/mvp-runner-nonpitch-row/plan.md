---
feature: mvp-runner-nonpitch-row
status: active
branch: feature/mvp-runner-nonpitch-row-20261107
計画レビュー周回: 1
---
# 既RunnerNPの41列分類を保存入口へ接続する最小追補

起点 `b7dc96bae001b5405dda422cb433bd65622a6410`。既走者計画の実物理保存接合の追補。run11 exact2f01は新prepare SQLを通過したが、`ordinary_pitch_operations._row` がnon_pitchを申告敬遠だけに限定し503となった。計算・記録権・原子性の仕様を変えず、この供給不足を直す。

編集は `backend/src/pitchlog/repositories/ordinary_pitch_operations.py`、新 `backend/tests/test_runner_nonpitch_row_operations.py`、本planのみ。製品SQL/共有asset/台帳/他WTは変更しない。正式資産の追随が必要ならcache packetへ分離する。

| ステップ | 内容 |
|---|---|
| 1/1 | 有限RunnerNP物理形と原payloadの全値照合を既preflightへ接ぎ、正負/旧操作回帰を固定する |

既 `RunnerNonpitchPlayObservations` / `RunnerEventT1Input` / `RunnerPerPitch` の閉型から、非投球の盗塁・投手/捕手牽制各3塁（既ExplicitRunnerEventの7 literal）とボークだけを受ける。外側result/kind/pitch種別、原観測との同一は既型から検査する。投球中盗塁・暴投・捕逸・三振併殺は既pitchとして保ち、今回のnon_pitch集合へ含めない。非play後normal計算profileは今回の対象にせず、既v3計算profileに閉じる。

41列の実mapper `pitch_physical_row` は既に、非投球時の主結果NULL、投球6列NULL、牽制type/detail又はボーク副結果を返す。現在 `_row` はこれらNULL/付随列を拒否するため、PlayPrefix tokenだけで有限な候補物理形を認める。物理行だけでは盗塁と未知の全NULL形を区別できないので、**prepareの形受理だけを操作の成立としない**。INSERT前の既 `_preflight.validate` が同tenant/game/D1/D2/D5/event/ledger/未投影を照合した後、受理済み原event.payloadを既閉DTOへ読み、唯一mapperを再利用して全41列を候補行と完全一致させる。これは計算再実装やauthority発行ではなく原観測の既物理写像の照合である。未知/欠損/余剰payload/別結果/別観測/種別偽装はINSERT前に拒否する。既prepare/stamp/guardの真正writer/nonce/XID照合は不変更。

通常Ordinary tokenへnon_pitchを横展開しない。既IWは旧形を維持する。新有限列以外のNULL制約、UUID/型/participants/41列集合は維持。新語彙を打撃結果として保存しない。投球6列への仮値や成功応答を生成しない。

試験は既唯一mapperと既runner固定caseを使い、盗塁/牽制6/ボーク正例、原payloadと行の不一致、未知operation/種別偽装/余剰/欠損/非PlayPrefix/投球6列混入/不正付随列の拒否、既IW/pitch/battedへの不変を確認。候補固定後recovery担当の非作者レビューを受け、実first2+故障はroot順序で別実行する。純検査を実保存成功・全MVP成立としない。

承認: rootが29a39523/plan SHA5bbb773713861cec0d80fbe12c8cf592d34f7eab01d4819464b46bb5a85c1496全文を非作者確認し、新P0/P1なし。2026-11-07 JST、PO委任によるCodex主担当判断で採用・step1着手可。PO本人の実値確認/署名ではない。
