---
feature: mvp-csv-effective-product-connection
status: active
branch: feature/mvp-csv-effective-product-connection
承認: PO委任によるCodex主担当/root判断（2026-11-07、既毎球CSVの実接合）
計画レビュー周回: 0
確定ゲート周回: 0
---

# 有効版の毎球CSVを唯一Sの実readへ接続する

既ud2-csv-export/mvp-play-csv-deliveryの未完接合を具体化する。root候補c181166cを起点とし、作者42d8924cの13pathと共有3path patchを再利用する。非作者REPORT d05b3661e00a431111857a987dd718aa8dca2d2b88e29a58d1f095c7352a2b2aで新P0/P1/P2なし、独立127試験/登録・codec拒否probeを照合済み。作者r13の実画面取消→全取消→再入力→reload/T5 source一致、r14の真正3球とRR/RO読取を、まだ製品接合成功とは扱わない。P3/復旧の枝を一括移植しない。

1. rootが13pathを通常mergeし、共有registry/transaction/read operationsの3path patchを現在の型・登録へ直列接合する。正式assets/生成module/history/seal/7.7はrootだけが編集し、公式helper・別非作者値確認・実base確定後に扱う。
2. 接合作者は本WTのrepositories/play_export.py、play_export_source_*、authz/play_export_source_read_product.py、exports/play_export_csv.pyと対応専用testsだけを編集し、CSV repositoryの有効行選択を唯一canonical S由来の閉source pageへつなぐ。500keysetと版/health/source集合を同じRR/RO内で検査し、source_event/play_row/generation/D1/D2/slot版を全結合する。全監査と有効集合を分け、取消前のsnapshotを消さない。生成元が欠けるP3等は409のまま。現在roster/0/NULLによる補完や別の野球計算をしない。
3. 同じ候補・owned実PG/実HTTP/実画面で2球→取消→全取消→再入力→reloadのZIP/T5同一性と、越境/不正scope/部分ZIPを拒否する。P3の88列producer、終了再開との結合、正式受理/全CI/通常統合/実機/負荷は別残件を維持する。仮Port/fixtureの88列投入だけを製品成功とはしない。

owned実行は全寿命で共通lock `/home/ymdms/.cache/pitchlog/test-coordination/owned-pg-browser-network.lock` を保持し、共有DSNをunset、実行中sourceを固定する。root共有台帳だけを更新し、作者は専用planへ検査/固定版/未達を追記する。主担当台帳/他WT/公開環境/秘密は非編集。sourceの実装は正式値の受理とは分離し、本人署名/P6blindを記録しない。
