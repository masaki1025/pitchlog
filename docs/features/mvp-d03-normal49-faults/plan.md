---
status: active
---
# 通常49のD03 writer途中故障

起点: `fc09310484c44c63d9d0590a4451f4ca6b8beaa8`。root既D03計画step4内の試験作業として、2026-11-07 PO委任によるCodex/root判断で着手承認。本人の実値確認ではない。

製品・正式資産・共有台帳を変更せず、新規testsと本計画/進捗だけを編集する。候補SQLの後差込、資格生成、認可stubを使わない。

| ステップ | 内容 |
|---|---|
| 1/2 | 実処理後observerの2故障driver、全行snapshot比較、純driver検査を固定 |
| 2/2 | root順序の共通lockで通常49実HTTPを実行し、同source/終了/cleanup証拠を保存 |

通常投球は第9球の第3アウトで守備半回が実際に変わる要求を使う。実 `_flush_native_stats` はSaveをSessionへ直接実行するため、原関数がnative/D03/CSVを保存し終えた直後に同runtime/session/top/実writer lifetimeを確認して例外を投げる。投手交代は実 `_ConsumeNonplaySubstitution` の `run_function` が戻った直後を同様に使う。私有表をアプリへ公開して未commit行を観測する権限は追加しない。原処理が返ったことと同scopeの安全markerを到達証拠とし、原本の物理残存はhostの読取専用snapshotで判定する。

実login→新規create/start→baseline→新D5の故障要求を直列実行し、非成功/ACKなしと、event/slot/checkpoint/entry/native/CSV/bindingを含むgame所属全行の前後一致を比較する。control側の失敗試行監査は保存取引と別物として扱い、再送許可を推定しない。不正receiptは安全な既入口を分離できた場合のみ追加し、本単位の必須2writer対向と混同しない。

owned PGはfixture全寿命の共通lock、共有DSN unset、実行前後source SHA一致、正常teardownを必須とする。rootへコード固定点を渡してから実行順を調整する。既scopeGET/RRの別問題やP3/全試合0球の未供給を、この試験で成立扱いにしない。
