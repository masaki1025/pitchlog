---
feature: mvp-recovery-current-startup
status: active
承認: PO委任によるCodex主担当/root判断（2026-11-07、既復旧保証の正規配置）
重さ分類: コア領域
branch: feature/mvp-recovery-current-startup
created: 2026-11-07
計画レビュー周回: 1
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

ステップ1固定ff2ded1dは非作者REPORT SHA13ddf8ed20f41f7ce489532f027cac95009f9723954b960dfac74b4dc2a0e3f2/独立173passedを根拠にPO委任rootが限定採用。実移植1c7a7193/ecd20392/89b58526は元9d/f938/a122に対応し、既補助関数集合を保持、過剰削除の旧候補は不採用。

ステップ2候補はCURRENT0046・全14表/全構造indexを閉比較し、既root45の全検査を保持。配備前の退役trigger0件と全配備のexact2件をcatalog段階に束縛し、部分/無効/余剰を権限適用前に拒否する。catalog/DDLは605に既供給されたconnection_declarations/公式builder由来候補を再利用し、正式7.7未受理のまま成功扱いにしない。175関連pure成功、既pre-full/full単体seamへ専用guardの検査を別に追加し旧呼出順/IDLE境界は維持。次に固定sourceで実S0→0046/同版resume/0046 table作成後故障全取消/構造・ACL・trigger改変拒否をowned PGへ渡す。0039以外の中間版からのcurrent直接移行は本候補で成立を主張しない。

固定f43のowned run1は4passed43.92秒、run2は5passed58.93秒、両方source前後同一/共有DSN未継承/owned cleanup。実S0→46/同版resume/46表作成後の全取消、RLS/未知列/余剰UPDATE/更新guard無効/TRUNCATE guard欠落拒否とpre-full正規再開・partial ACL拒否を確認。これは候補環境で、正式7.7/通常統合/運用公開ではない。

同表の宣言分類の追補: first_ball_product.TABLESが13のままで、退役表の未知policyをpitchlog_appへ追加したメモリ内反例が_reserved=False/直接profile validate=Trueとなる不足を確認（母集合全検査が同変異を受理するかは未検証で、実越境の成立とはしない）。閉TABLESへ同表1件のみ追加し、元資産positiveと同変異negativeを固定する。DDL/権限そのものを追加せず、余剰を拒否する分類を元設計へ揃える。追加2pathを限定非作者確認し、最新HEADのS0/同版resumeを再確認してから候補最終版へ束縛する。

ステップ3の実測固定: f43のrun1=4passed43.92秒/run2=5passed58.93秒に加え、分類是正e3433c2b42584915f97d3833ff6be766c5af67f7でも実S0→46/同版resumeをrun3=1passed18.49秒で再確認。各source前後同一・共有DSN未継承・所有container撤去。分類是正の限定非作者REPORT SHA cfc6380dd3bf71409bbae377151e0361dd82216fd30bae6aa14f4ade4843d45d/4pure/Ruff/Ty成功、旧605の自己レビューではなくroot追加deltaだけを対象とする。rootは全14構造/保護のf43非作者報告と本deltaを合成して、PO委任による限定source採用（2026-11-07）を記録する。候補正規起動の成立と、正式値7.7/最終CI/通常merge/運用適用の成立は別。証拠cache recovery-current46-startup-root-20261107のrun1/2/3-{source-before,source-after,result}.json・各log/xml・ROOT-ADOPTION.json。後発は本計画の記録だけで製品sourceを変えない。
