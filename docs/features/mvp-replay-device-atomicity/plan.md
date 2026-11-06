---
feature: mvp-replay-device-atomicity
status: active
branch: fix/mvp-replay-device-atomicity
承認: PO委任によるCodex/root判断（2026-11-06、既DI1拒否順と端末失効保証の技術修復）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 保存済D5再掲の真正端末資格を同TXで保持する

正本sync-protocolの②B5→③B6→④D5→⑤V12を変えず、不足した端末credential照合を接続する。旧作者cache `di1-replay-device-auth-author-20261106` のf1507955候補は、非作者REPORT-di1-b5-independentの失効窓P1により不採用。source/token/固定SQLの既成果は再利用するが、同候補の別TX認証を採用しない。基線d7394e93。rootのみ本WTを編集する。実機/共有DB/秘密発行は対象外。

1. 既候補を再利用し、閉operation/tokenとSQLを追加。真正tenant/device/digestを同tenant scopeで照合、既bind_deviceと同じtrusted_devices行FOR SHAREをD5読取終了まで保持する。既ACLで成立させ新たなUPDATE権限を便宜追加しない。B6/RG1/D5も同scope内。資格不成立は401/no ACK、DB不明は503/no ACK、未使用D5は既fresh経路で再照合。route/helperは資格引数必須で迂回の既定なし。関連正式assetは公式rendererで候補再導出、採用と未受理を区別。
2. 対向unitとowned実PGで、先行失効→不成立、行lock後の失効→D5読取完了まで待機、誤端末/credential/tenant拒否、同D5同本文/異本文/古いnull V12再掲、未使用D5の拒否順を検証する。全owner/ACL/migration/core登録の固定値を照合。共通owned PG lockは生成から破棄まで保持。作者検査と非作者を別記。
3. 非作者レビューでP0/P1を閉じ、統合候補に接合し実HTTP/画面の再送・失効・結果不明の退行を検証。最終HEADレビュー/正式値受理/必須CI後のみ通常PR統合。認証時点は同TX行lockとD5読取の線形化であり、HTTP配達完了を保証したと記録しない。
