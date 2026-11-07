---
feature: mvp-runner-csv-nonpitch
status: active
branch: feature/mvp-runner-csv-nonpitch-20261107
計画レビュー周回: 1
---
# Runner NP の受理済み CSV 直接射影を既原本に接ぐ

起点 `730536ebf676e826e2f7cf29c0e6307435df146c`。実 run12 は 41 列原本と `_row` の閉検査を通過し、`record_projection._accepted_pitch_speed` が既申告敬遠の観測だけを受けるため 503 となった。記録時の88列と sidecar の原本品質を保持し、ここでの欠落を直す。

編集は `backend/src/pitchlog/exports/record_projection.py`、新専用 `backend/tests/test_runner_nonpitch_record_projection.py`、本計画のみ。共有 asset、正本、他 WT、既 DTO と唯一計算は変更しない。実 PG は root の共通 lock 調整後とする。

| ステップ | 内容 |
|---|---|
| 1/1 | 既 `_course_screen(payload, play)` の厳格な Runner NP 原観測・物理行照合を再利用し、未観測の球速だけを `None` として写す。`project_recorded_direct` の残余列と申告敬遠の旧形を正負純試験で確認する。 |

Runner NP は既 `RunnerNonpitchPlayObservations` と `RunnerEventT1Input` の閉形、原観測同値、主結果非該当、6 投球列 NULL、副結果有限分類を満たす場合だけ受ける。申告敬遠は旧12列 NULL と打球列無しを厳格に保つ。未知 non_pitch、球速 0 の仮値、別語彙や別計算を導入しない。後続の走者欄、打席表示、入力由来、admin/tenant 語彙の全列を静的・実 fixture 純経路で確認し、途中の別停止点を一括捕捉する。純検査は製品実保存成功とは扱わない。

承認: root が起案 plan SHA `698ec174c22c0fbef58fc65d5360226acd4a8e7e24dde1e1d21efec78f8964c2` を非作者確認し P0/P1 なし。2026-11-07 JST、PO 委任による Codex 主担当判断で step 1 着手可。本人署名や製品実走の証拠ではない。
