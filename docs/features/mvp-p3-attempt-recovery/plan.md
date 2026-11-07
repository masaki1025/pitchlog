---
feature: mvp-p3-attempt-recovery
status: active
branch: feature/mvp-p3-attempt-recovery
承認: PO委任によるCodex主担当/rootの2026-11-07移管・閉P3接合指示に基づく技術具体化（最終source採否は別）
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# P3元本文の結果不明復旧と標準controlへの閉接合

既採用のsync-protocol 6-3-A/DI1〜DI5と既P3契約を実接続する追補。新しい野球意味、D5/拒否優先順、取消範囲を決めない。P1/P2復旧6058888b89824be35bee19f75af80bb03cae4763を不変更で保全し、本専用WTでP3固定4d43e08c8d10e44eda40fa3bf611529b38479d6cへ接合する。既候補/既レビュー回数を保持し、実Port/DB完成を型/契約具体化の開始条件へ追加しない。

## 既成立と不足

- P1/P2は真正E1 receiptから原本文全値（V12込み）の独立body digestを導出し、control原本/journal、業務同鍵遮断、control同鍵の再照合/永久retirementへ束縛する。旧登録NULLの現在本文からの補完は禁止。39adの最終owned4case、605の実browser閉鎖2モード/実旧live・認証越境を候補証拠として保持する。
- P3は同じ真正receiptと既`D1lessPhaseBinding`/`freeze_wire_source(d1less=True)`を持つ。既`/sync/change`は同attempt再送で、P1/P2用recoveryの対象外。
- P3の標準control SQLは未供給。旧実測はcache `mvp-past-correction-product-20261106/p3-d1less-control-functions.candidate.sql` SHA256 a306da167df929d3e150b9f66da8e90d12abb0c44a712cd175f5e31025255ef2 の専用register/read 2関数をowned fixtureへ適用したもの。標準配備済みとはしない。

## 編集所有と境界

本WTのみを本担当が編集する。共有`writer-binding-control.sql`はroot移管により本担当を唯一writerとする。P3作者のWT/共有台帳は編集しない。

対象は既P3と復旧の接合に必要な `api/routers/sync.py`、`sync/{apply.py,attempt_recovery.py,source_binding.py,wire_source.py,wire_fingerprint.py}`、`sync/control_provider/{evidence.py,binding_control.py,writer_binding.py,sql/control-phase-schema.sql,sql/writer-binding-control.sql}`、`durable_rights_ledger/{adapter.py,manifest.json}` と専用試験。FE共通 `api/{recoverableSyncPost.ts,syncAttemptRecovery.ts}` と `lib/syncAttemptBarrier.ts` の閉P3分岐を接続する。P3 FE本体はP3作者所有を維持し、`postP3Change`接合差分をcache patchでrootへ渡す。P3計算/投影を複製・再実装しない。

P3固定点と復旧起点が異なるため、復旧topic7commit（b3de166c/68a4a459/ad90662e/e1f8f6ea/a207d4a4/39ad4f20/6058888b）の差分だけを3-way接合する。計算/NP/断中画面/artifactの基線差分は取り込まない。復旧topicの既承認対象52pathを依存として再利用し、新しいP3の正式資産の衝突/不一致はrootへ渡す。生成module/正式authz・tenant・seal・7.7は手作業で受理しない。標準current起動/移行の正式追随はroot所有。appへDB表権限を追加せず、body source pinは実byteからの候補再計算として分離する。

## ステップ

| # | 実装単位 | 完了条件 |
|---|---|---|
| 1 | 固定P3＋P1/P2復旧のsource接合、P3専用control 2関数の標準供給 | 旧EventPhase/d1=1を維持。P3だけD1less/NULL-D1の閉union、unknown kind/混在/余剰拒否。専用register/readも同attempt advisory鍵/retirement guard/body digestを持ち、旧NULLを補完しない。計算/投影/既D5指紋を変更しない |
| 2 | P3真正原本文の登録・照会・後着遮断とHTTP入口 | P3元change/recovery_generation/V12/target全値を真正receiptから独立digestへ束縛。P1/P2とP3を型由来で区別し、専用control原本とbusiness tombstoneを閉照合。借用/全旧RPCの終結・後着遮断の証拠を維持。DI2をV12/内容検査の後ろへ動かさない |
| 3 | 共通端末barrierの閉P3接合、FE差分受渡し、owned実対向と候補固定 | 元本文/D5をstrict保存し、retry_allowed後だけ新attempt。P3 FE本体はroot直列で接合。P3のACK喪失/故障/未登録/旧live/異内容・越境とP1/P2回帰を実PGで確認し、実装のない成功・固定応答を使わない。独立レビューへHEAD/全diff/全値/試験証拠を渡す |

## 検証と未成立の管理

source固定した各WTで共通owned PG/browser/network lockを全寿命保持し、外側の共有DSNをunsetする。作業中は影響範囲、統合候補固定後に必須全件を実行する。旧caseの期待値を現在出力から作り直さない。P3候補計算の一般化/旧世代/長prefixと、共通復旧の成立を別に報告する。

候補source成功、正式受理/通常統合、実機/運用TLS/復旧、MVP全完成を区別する。本人逐行確認/本人署名/P6 blindを代記しない。rootのPO委任採否/最終独立レビュー/正式manifestと7.7は別ゲートとして保持する。


step1接合記録: 4dへの605全mergeは起点差により無関係な約170pathを含むため未commitでabortした。復旧7topicだけを接合し、C2登録はP3 3操作とrecoverの両方、client資格の閉URL集合はevents/change/attempts-recover、交代POSTは既耐久barrier/C2経由を保持。P3 phase_kindと復旧body_fingerprintを同じ私有phaseへ保持し、business bindingへは両方を混入しない。既artifact/数学/保存値vectorには差分なし。標準P3専用2関数へ元候補SHAを照合して同鍵遮断/body保存を追加し、旧first-ball EventPhase分岐は維持する。正式受理/実PG/独立source確認はまだ。

step1検査: backend関連307件・Ruff/Ty成功。FE関連51成功、Undo8件は起点4dのfixture artifact 4e8b3252…に対し実artifact ce622726…の既存不一致（対象資産の差分0）。期待値は変更しない。標準control owned初回は共有DSN未設定のままdefault admin fixtureが先に解決されたsetup errorで、DB確認には未到達。既owned admin/tested-role fixtureを明示importして再検証する。標準関数catalog照合は非作者cache patch 1da9acfd…を元byte照合して採用したが、正式受理・独立source採否は未了。
