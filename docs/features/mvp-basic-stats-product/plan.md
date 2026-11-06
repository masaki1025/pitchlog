---
feature: mvp-basic-stats-product
status: active
branch: feature/mvp-basic-stats-product
承認: PO委任によるCodex /root判断（2026-11-06、既MVP・mvp-stats-primitives範囲の接合追補）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 受領済み基本成績・CSVの製品接合追補

既mvp-stats-primitives計画のstep3～5と外部候補feature/mvp-basic-stats-csv@41507aa09592ff8d7422008b6d2a88e79027eba5を再利用する。起点native a59c654e3366d2be9c6456e47b07118e1674bce2。D02～D05/JST暦年・27指標/両CSV・最新終了版の既採用方針を再裁定しない。担当rootは本WTの唯一writer、他WT/共有DB/秘密/公開環境を変更しない。

## 既受領差分と範囲

外部28pathはGitで受領済み、reflection19はcache stats-basic-csv-reflection-author-20261106/reflection.patch SHA43834e31b91459c50770f8e580c79606d224337a3d397d0d31bc38adc030ee17。独立reflection結果はcache stats-basic-csv-intake-independent-20261106/reflection1/に固定済み。単位ごとの最終source/正式資産/共有generator差分は非作者レビュー後に採用する。

1. 外部枝を通常mergeで接合し、現在のlegacy generator helper/preexec pin/native RRRO/source guardsを保持してreflection19を適用。最初は既25/27と候補API・SQL/画面・CSVを再現し、正式app/registryへ候補tokenを先に登録しない。変更範囲は外部28＋reflection19の和集合と、backend/domain/stats-manifest.json・既native D11該当hash・preexec literal・本計画の必要最小追随。旧計画の「generated facts不変」は実際の追加accessorに整合して訂正する。
2. 登板/打者数の真正出場source・責任帰属を供給し、native27 CHECK/codec/Save/read/credit/D11を同版へ接合。source不足を0へ補完しない。
3. 正式read SQL/認可/tenant/DTO/routerを受理後に登録し、終了/再開providerの真正receiptとlatest confirmed pointerを同TXへ接続。test-only finalizeを製品にしない。
4. 既U-D2を再利用して毎球88列CSVを実DB抽出/HTTP/ZIP/画面DLへ接続し、成績CSVと双方を完成する。全件読み込み集計/ページング欠落/部分CSV成功を認めない。
5. 同一版の実画面/実API/owned PGで記録→終了→成績/CSV→再開/訂正→再終了を確認し、原子性/再送/越境/切断/負荷を検証。運用公開/実機/復旧の未実施は別記する。

各stepを別commit・非作者確認し、状態/実値/検証の対象版を記録する。step1の候補成功を27項目提供/正式統合/MVP全完成に読み替えない。PO本人署名・人間逐行確認を代記しない。
