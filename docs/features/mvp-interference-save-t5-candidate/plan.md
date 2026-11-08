---
feature: mvp-interference-save-t5-candidate
status: draft
承認: 未
重さ分類: コア領域
branch: feature/mvp-interference-save-t5-20261108
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-interference-save-t5-20261108
created: 2026-11-08
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 妨害の保存原本とT5候補

基点はINT-04修復済み候補 `99e97a7debf9b44362aa28cbc627716cfad0b3d6`。要件書INT-01〜07の採用裁定、既唯一T1、真正V7原本を同じ保存経路へ接ぐ。旧0e26 artifactは未採用であり、固定859の純成功を実保存成功とみなさない。新しい野球計算、RBI/OUT3の再判定、旧V7の形への書換えは行わない。

## 編集範囲

- `backend/src/pitchlog/authz/interference_evidence_sql.py`（新規）、`backend/src/pitchlog/authz/first_ball_product.py`、新規専用 `backend/tests/test_interference_evidence_sql.py`。現 `prepare_play_prefix_projection` の公式生成親SHAは `c2758d69d452fba961fc63459e84e951a2600129a4cf65c03aedaa44f5afc55f`。同関数の既宣言を固定し、妨害原裁定・T1・全41物理列の有限条件だけを追加する。他のBODIES、owner、ACL、関数署名、nonce、同TX、拒否順は不変更。
- `backend/src/pitchlog/repositories/ordinary_pitch_operations.py`、新規専用 `backend/tests/test_interference_play_row.py`。`PlayPrefixPlayRowInsertToken`だけで妨害3 secondaryと打撃妨害の採用プレイ形を有限識別し、既同TX event/ledger/D5照合に加え、原V7/審判裁定/実参加者/唯一物理mapperの全41列一致を要求する。旧通常、走者8形、打球12形の受入は不変更。
- `backend/src/pitchlog/stats/facts.py`、新規専用 `backend/tests/stats/test_interference_native_connection.py`。既T1のtyped効果と固定sideの結果から実得点・責任投手・打者creditを原IDへ写し、既生成T5へ渡す。無効得点、裁定アウト、打席継続の区別は既T1効果からのみ取得する。盗塁/打点の未観測値は補わない。
- 本計画。共有契約、正式authz/tenant/seal資産、旧golden、artifact、registry、台帳、他WTは編集しない。候補SQLの正式7.7値と実PGはroot後段。

## 閉じた入力と留保

- `secondary-result.batting-interference` は罰則採用と実プレイ採用を区別し、後者は真正主結果とbatted物理列を保持する。`secondary-result.obstruction` と `secondary-result.offensive-interference` は主結果NULL・妨害副結果を保持し、審判の授与/アウト/帰塁を原V7と実T1に束縛する。
- 物理ラベル「妨害裁定アウト」は既 `runner_physical_rows` が審判の `out_targets` とT1 `outEffect.targets` の全一致を確認したときだけ出す内部保存表現とする。ラベル単独を裁定の根拠にせず、同TX原event・実runner ID・起点塁と照合する。
- 現 `_row` は副結果列をNULL必須とし、妨害3形を拒否する。現 `_validate_runner_source` はrunner観測だけを全41列へ再束縛する。現T5は妨害のtyped走者別効果と裁定アウトの有限原本を供給対象に含めない。親SQLも新妨害を閉拒否する。これらを本候補で一括修復する。正式SQL配備と実DBはこの候補の純検査では証明できない。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 固定親へ妨害の厳格SQL overlayを接続 | 親SHA/宣言/対象箇所を閉検査し、公式BODIESのprepare1本文だけ変化、他本文全byte一致、未知/原本改竄拒否 |
| 2 | 同TX物理41列とT5を接続 | INT3 secondary/採用プレイの正負、元event/ledger/ID/裁定/物理改竄拒否、既T1 typed効果からの成績だけを生成T5へ写す |
| 3 | 候補差分を封印 | 対象path前後SHA・純BE検査・残る正式7.7/実PGを区別してroot/非作者へ渡す |
