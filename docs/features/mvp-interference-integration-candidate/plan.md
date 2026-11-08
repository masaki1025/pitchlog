---
feature: mvp-interference-integration-candidate
status: draft
承認: 待機（PO委任rootによる限定技術採否）
重さ分類: コア領域
branch: feature/mvp-interference-integration-candidate-20261108
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-interference-integration-candidate-20261108
created: 2026-11-08
計画レビュー周回: 0
確定ゲート周回: 0
実行方式: 通常
---

# 妨害の閉操作と唯一artifactを隔離候補へ接ぐ

基点は `d074b72ba01cc4d05af29e7b534189c496c5c49c`。既作者候補 `e6a16109d2d7940d77ee2e0d2ef70180d5852f3c..180322d531a9ced9b7ad91ac06e3366cde801d15` を通常mergeし、基点のSH/RBI head/NoRun/host reuse等の後発を保持する。打球旧artifact `71f2726a288dfcfaff4c2fcdf293651dda0fb610b9ead325b352bd4f23a07aff` はGit基点として保持し、新候補だけを公式builderで生成する。既53数学/旧23 flags/旧request・responseを緩めない。

## 編集範囲

- 通常mergeの25 path: `backend/src/pitchlog/domainrt/{lineup_play_prefix_continuation,lineup_prefix_source}.py`、`backend/src/pitchlog/sync/{ordinary_pitch_physical,runner_physical_labels,terminal_pitch_payload,terminal_pitch_projection}.py`、`backend/tests/domainrt/{test_interference_input,test_lineup_shared_host}.py`、`backend/tests/test_interference_payload_boundary.py`、`docs/features/mvp-interference-product/plan.md`、`frontend/src/api/lineupPrefixWire.ts`、`frontend/src/domain/{battedHit,interference,lineupPlayPrefixContinuation,publicApi,state,stateTypes}.ts`、`frontend/src/domain/{interference,publicApi}.spec.ts`、`frontend/src/screens/{GameScreenBattedHitObservation.spec.ts,GameScreenBattedHitObservation.vue,GameScreenInterferenceObservation.spec.ts,GameScreenInterferenceObservation.vue,GameScreenOrdinaryPitch.vue,GameScreenOrdinaryPitchProvider.ts}`。衝突解消はこの25 path内で既成果全値を保つ。
- 閉契約4 path: `contracts/state-transition/lineup_play_prefix_schema_v1.json`、`contracts/state-transition/lineup_play_prefix_payload_schema_v1.json`、`contracts/state-transition/lineup_play_prefix_v1.d.ts`、`contracts/state-transition/lineup_play_prefix_payload_v1.d.ts`。cacheの旧byte固定2 JSON候補を基点同SHAから新3 variantだけ再基線し、d.tsと同じ閉unionにする。旧variant/必要観測/未知拒否は維持。
- 唯一artifact2 path: `frontend/public/domain/pitchlog-domain.js`、`frontend/public/domain/pitchlog-domain.json`。公式builderで同入力の再現一致を確認する。必要な実行pinの候補は `backend/domain/{manifest,lineup-prefix-manifest,batted-hit-manifest,terminal-pitch-manifest,play-prefix-manifest,strikeout-pitch-manifest,game-lifecycle-manifest}.json` に限定する。追加対象が判明すれば先に本計画へ記録する。
- 対応の純試験は上記既専用spec/testを優先し、必要な新専用testだけ同計画へ追記してから作る。本計画pathも編集対象。

## 実装単位

| # | 内容 | 完了条件 |
| --- | --- | --- |
| 1 | 既妨害sourceを通常mergeし同唯一核を維持 | 旧後発を保持し、妨害3 familyの原裁定・actual ID・得点/OUT3観測を閉じる。衝突/差分を固定 |
| 2 | 閉JSON/ABIと公式artifactを新候補だけに生成 | 旧JSON/d.ts variant全値、妨害3 variant、公式builder再現、既53/23flags、必要pin/manifestを照合 |
| 3 | rootへ候補packetを引渡し | 差分SHA/各before-after/残依存を固定。v6 compat/witness、SQLoverlay、current pin全体、正式7.7受理、実PGはrootの後続範囲として分離 |

この枝の純検査を製品HTTP/PG保存成功、正式認可・7.7受理と扱わない。共有main/台帳/正本の本適用・DB/Docker起動をしない。妨害以外の新野球意味を追加しない。
