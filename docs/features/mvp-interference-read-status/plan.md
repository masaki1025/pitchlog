---
feature: mvp-interference-read-status
status: active
承認: PO委任によるCodex/root判断（2026-11-08 22:46 JST、既妨害物理保存の読取型追随）
branch: feature/mvp-interference-read-status-20261108
計画レビュー周回: 0
---

# 妨害の保存ラベルを公開読取の閉型へ接ぐ

基点99e97a7d、唯一mapperの`INTERFERENCE_OUT_STATUS`は原審判裁定のout_targetsと唯一T1対象/実runnerを照合したときだけ`妨害裁定アウト/manual`を生成する。現backend StartedPlayRunnerとFE isPlayRunnerStatusはこの保存済み値を拒否する。数学・判定・保存資格は変更せず、両読取型へこの有限な組だけを追加する。

編集範囲: backend/src/pitchlog/api/schemas/started_games.py、backend/tests/test_play_runner_status_schema.py、frontend/src/api/playRunnerStatus.ts、同.spec.ts、本計画。正本/正式契約/SQL/認可/保存元/mapper/旧golden/共有台帳は編集しない。対象が実裁定由来である保証は既保存資格と元event照合に保持し、DTO単独の受理を裁定・保存成功とみなさない。label/手動以外の新しい組を受理せず、未知・逆行・余剰・資格欠落の拒否を保つ。正式ラベル受理/実保存GET/実PGは共有保存接続後の残件。

| # | 作業 | 検証 |
| --- | --- | --- |
| 1 | BE/FEの有限読取型と対向を接続 | 起点1〜3の既物理manualラベル、auto拒否、未知/不正base拒否、旧各ラベルの受理拒否を保持。型/lint/限定両試験 |
| 2 | 固定差分を非作者へ渡す | 対象HEAD/差分SHA/検査/留保を本計画へ記録し、共有保存候補との接合前にレビュー。PG/正式提供成功と混同しない |
