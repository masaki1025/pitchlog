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


step1候補接合の確認（2026-11-06、PO委任Codex /root判断）: 固定patch0fdf982c1a16e205b8feb13c35e70c00879f2575bda69330d809a2c5a686643bに非作者REPORT SHA256 f5de81b1ba957f2f8263adeb149d59198e1a03fa4fa618a3be855e56fb85960f。未登録候補として採用可。旧v2保存set互換・mutable read hook廃止/正式認可・真正終了receipt/pointer・登板/BF・88列CSVは製品提供前の未解消として残す。生成T5 8/T6 1と旧v1保持、preexec pin/legacy API保持を検算済み。root対象266成功25.87秒、frontend既50成功、formatter表記のE501を隣接literal分割で修正しmodule AST/生成出力は不変。正式SQL3bodyは未採用、製品registryも未登録。今回の候補保存はMVP/27項目/製品提供/実ブラウザ成立ではない。

## ステップ2・3の作者候補固定（2026-11-06）

ステップ2は native27 と BF の責任帰属、旧 v1/v2 profile と旧 D11 v2 全値を保持する新 D11 v3、0045 migration（`down_revision=0044_substitution_write_receipt`）を候補固定した。現実の交代 0044 は別作者の暫定版で、完成版と同一生成物には未結合である。純試験422件、D11/基本試験255件、read dispatcher修復後344件、authz function body check、backend Ty/Ruff は通過。これらは旧数学期待を実装出力で再作成した証拠ではなく、旧 v2 全値と新 BF の独立期待を照合した作者検査である。

ステップ3は真正 lifecycle head・終了 receipt・public pointer の一致を必須とする成績 read/CSV と認可・registry・同一 RR snapshot を候補固定した。旧 `test_only_finalize` を製品起動へ登録せず、既LC実HTTPへ成績 GET/CSV を差し込む試験へ置き換えた。0044 の正式接合、同版での全生成物再派生、owned PG の実記録→終了→成績→再開→追加球→再終了→再取得、P3 終了後 pointer、取消/訂正を含む版付き登板 source、暦年 D03 の証明、core-areas の新 D11 v3 path 登録、正式7.7/独立確認は未了であり、候補成功を製品充足へ読み替えない。
