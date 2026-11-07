---
feature: mvp-p3-current-startup
status: active
branch: feature/mvp-p3-current-startup
承認: PO委任によるCodex主担当/root判断（2026-11-07、既P3/復旧成果の正規接合）
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# 過去訂正と結果不明復旧を通常配置へ接合する

起点5cb4407d2f4df63428f15d8da8c576ff684e5a16は正式develop45bを取り込んだ通常CSV47候補。ae82631b同sourceの新規配置/再開/全故障改変49件と、後付SQLなしの実画面記録/取消/再入力/ZIPは成立済み。旧source/レビューを継承し、P3候補9687caa038629409d024cac54270df3d186d5a27の訂正→終了→再開→追加球→再終了/reloadと、復旧e690dba8の真正P3照会/旧生存拒否/終結後だけ許可を再利用する。

| # | 実装単位 | 成立条件 |
|---|---|---|
| 1 | 既P3と復旧を通常mergeで同居し、必要なFE接合patchを適用する | 元枝不変更、実固定点/全編集集合/競合理由を記録。旧P1/P2/CSV/記録権とD5原本文資格を保持し、古いcatalogでroot47を上書きしない |
| 2 | 原本schemaの0048・型元・全構造/ACL/catalog/標準controlを通常起動へ供給する | 手書き成功DDLの後付けを除き、実sourceから閉派生。旧47/復旧guardと実P3資格を保持。全故障を同TX全取消、正式7.7はsource固定後に別ゲート |
| 3 | 同版新規画面→複数球→過去訂正→終了再開追記→再終了/reload・結果不明復旧を実証する | 実認証/記録権/唯一artifact/同TX保存、旧版失効/同D5再掲/越境/途中故障/遅着遮断。P3の88列CSV未供給・25超/複数/終了後訂正は別残件として完了へ読み替えない |

rootのみが本WT/共有接合を編集する。編集は既P3/recoveryの実source集合・専用fixture/tests・FE耐久/画面接合、既cache原本からの0048 migrationと専用型元、current_product_startup/閉検査、authz候補catalog/公式派生と本計画。元P3作者は別WTで25超/複数/終了後の純sourceを担当し、同じ物理pathを並行編集しない。既capsuleのwatermark<=25などを上限だけ外して全試合成立にせず、ページ完全性の追補を受けて整合する。新しい野球意味を裁定せず既採用意味と保存保証を維持する。

正式共有DB/運用公開/新秘密/本人署名は行わない。試験はowned PG全寿命共通lock、共有DSNをunsetし実source前後と所有cleanupを固定。独立reviewは対象版/差分SHA/作者別に維持、既13path等の部分reviewを全依存へ拡張しない。最終認可/tenant/7.7/必須CI/通常merge/実機の未了を保持する。8分割CIの保留を本製品接続の条件にしない。
