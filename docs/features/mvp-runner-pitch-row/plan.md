---
feature: mvp-runner-pitch-row
status: active
branch: feature/mvp-runner-pitch-row-20261107
計画レビュー周回: 1
---
# RunnerPitch WP/PB の保存行を原payload全値へ束縛する

起点 `4a0e04b43b74cadd6ea1193d7911db6b55a72e31`。read-only純反例 `~/.cache/pitchlog/runner-pitch-pipeline-intake-20261107/REPORT.md` は、唯一mapperのWP/PB行が副結果列だけで旧NULL制約に拒否され、逆に副結果を消した行が現preflightを通ることを示した。これは実authority発行や実保存の証拠ではない。

編集範囲は `backend/src/pitchlog/repositories/ordinary_pitch_operations.py`、新専用 `backend/tests/test_runner_pitch_row_operations.py`、本計画のみ。SQL/CAP/metadata/計算/正本/asset/共有WTは変更しない。実PGはroot共通lock調整後。

| ステップ | 内容 |
|---|---|
| 1/1 | PlayPrefix tokenのWP/PB有限副結果を41列形へ許し、既RunnerNPの原payload・ID・唯一mapper照合をRunnerPitchへ共有拡張。正規/改竄/旧経路を純対向する。 |

`event_kind=pitch`・副結果WP/PBの時だけ `_NULL_COLUMNS` から副結果列を除く。主結果は既唯一核の `frontend/src/domain/runnerEvent.ts:472-490` が既 `ordinaryCountRule` を呼び、同 `stateRules.ts:68-96` の ball/called-pitch/swinging-strike を許す。foul は特殊プレイでは明示拒否される。したがって形の許可はこの既3語へ閉じ、状態・カウントの再計算はしない。未知副結果/主結果、Ordinary token、打球/旧IWは従来の拒否を維持する。preflightは元event.payloadの閉V7観測と `RunnerEventT1Input`、tenant/game/source event/play/D5、主結果/副結果/投球区分を照合してから既唯一 `pitch_physical_row` の全41列を候補行と完全比較する。元payloadがRunnerPitchなら副結果列が消えても照合を必須にし、RunnerNPの既検証は同一helperを再利用する。型/出典を変えて元数学を再実装しない。`_CASES[3]/[4]` 正規WP/PBと副結果None・別値・欠損/余剰/別ID、既NP8形、通常pitch/K/ball/batted/IWとOrdinary拒否を検査する。実PG成功は別証拠とする。

承認: rootが初回plan SHA `9bcfbe63f6917fe38c282828829fb6971e3f918e2c0013ea64d561a9b80cd0df` を非作者確認。初回のball限定は既原典にない過度な狭めとして撤回し、上記既核の3語へ修正する条件で新P0/P1なし。2026-11-07 JST、PO委任によるCodex主担当判断でstep1着手可。本人署名や実PG成功ではない。
