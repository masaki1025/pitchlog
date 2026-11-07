---
feature: mvp-recovery-current-startup
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-07、既復旧保証の正規配置）
重さ分類: コア領域
branch: feature/mvp-recovery-current-startup
created: 2026-11-07
計画レビュー周回: 0
確定ゲート周回: 0
---

# 復旧用の耐久遮断表を正規起動へ接合する

既採用候補6058888bの0046 migrationと復旧SQLを再利用し、rootの0045起動修復（9d2e8097/f938f10f/a122c7ef）だけを移植する。P3/control/FE作者の現行WTは変更しない。旧不正な競合解消候補はローカルpreserved-conflict枝へ保存し採用しない。移植後は試験補助の全関数保持/構文/差分を再検査する。

| # | 実装単位 | 成立条件 |
|---|---|---|
| 1 | 0046原本に一致する私有モデルと閉構造検査を追加する | 全11列/PK/FK/CHECK/index/owner/FORCE RLSを比較し、旧13表を保持。migrationを独自再実装しない |
| 2 | 正規current起動の0046配置・権限・追記専用の接合を行う | 標準provisioner/catalogに必要な正式差分を公式helperで作成し、余剰権限/更新削除/部分配置を拒否。正式値受理前は候補と明記 |
| 3 | S0から起動/同版再開/旧版からの移行・故障全取消を隔離PGで検証する | source固定・共有DSNunset・共通lock・実owner/app/actorを使用。別非作者確認/7.7/CI後のみ通常統合 |

編集範囲: db/writer_binding/attempt_recovery_models.py、同models.py、db/current_product_startup.py、関連backend model/startup試験・既migration0046の参照、必要な正式authz候補原本/公式派生と本計画。migration/bodyの新意味・sync/control/唯一数学/FEを変更しない。0046予約を維持、CSV0047/P3 0048と混同しない。CURRENT定数だけを変更して成功扱いにせず、標準認可資産と実配置が未成立なら正規起動未達とする。人間本人の確認/署名/P6blind/実機/運用公開を代記しない。
