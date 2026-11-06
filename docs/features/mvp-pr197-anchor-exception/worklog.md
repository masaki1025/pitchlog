# 単一7.3ゲート

起案2026-11-06、PO委任によるCodex /root判断。適用版は初回実行時点でapprovedのv1.19、条文commit e1cbd72921b4b234bc44dfeb2c0a95c2c221376d、起案前全文SHA256 0ccca7291f56a8b64e5d416b96d3be3a70377298206be0d7e2702d5481003fef。v1.20はin-reviewで本ゲートへ自己適用しない。

対象はハーネスv1.20の全文（初回）と今回PR197限定の一項。既7.3/レビュー上限/7.7履歴・閉拒否は不変。基本枠2回、まだレビュー未実施。ユーザーのMVP内技術整合・必要レビュー・コア最終確認・安全を維持するハーネス調整委任に基づく案A採用であり、PO本人の実値確認や署名ではない。

不採用のsource候補: native-pr197-frozen-literals-author-20261106/reflection1 は非作者P0で偽Gitの初出を原典扱いしたため破綻。新source候補はreflection2で別に固定し、正本確定/実装レビュー/7.7/CIの成立と分ける。


## 初回全文レビューの採否と反映1周目

非作者REPORT SHA256 08b1d127f3b6ababc70eaed5d5278558a92c8b903cd13da185a6a4ff6d1515c2、否決P0=0/P1=2/P2=0。両P1を起因(A)として採用、不採用0。①索引をin-review(v1.20)/直前approved v1.19へ整合。②専用feature/mvp-pr197-anchor-exception WTをf99e58f4から作り、slug/branchを一致、重さ・step表・テスト計画/DoDを補足。初回全文の条文/射程とPO委任根拠は不変、ゲートは未承認。第2回の対象は反映差分と索引/計画の影響節。終了済み2件は反映を再確認、不採用一覧は空。
