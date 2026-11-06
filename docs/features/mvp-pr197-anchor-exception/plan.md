---
feature: mvp-pr197-anchor-exception
status: active
branch: feature/mvp-stats-native-foundation
承認: PO委任によるCodex主担当/root判断（2026-11-06、既MVP・安全を維持するハーネス最小整合）
計画レビュー周回: 0
確定ゲート周回: 0
---

# PR197の固定Git期待1件の例外

対象はハーネス7.7-1への今回限定の一項と、同項の検査/対向・typed移設・同7.7正式派生。一般統制を再設計せず、27値の自己期待化を避ける固定Git基点1件だけを認める。ユーザーの安全を維持するハーネス調整・最小例外手続き委任で案Aを選ぶ。案Bの外部証拠からの原典取得は局所検証の外部依存と時系列を増やすため採らない。

1. v1.19を適用版とする7.3でv1.20一項を起案し、初回全文敵対レビュー→採否→必要差分確認→PO委任判断を追跡する。承認前はv1.20を自己適用しない。
2. cache修復案を非作者レビューし、偽Git/同時改変/欠落/版違い/重大指摘の拒否と、他全allow-list追加禁止/既反例/旧基準を保持する。source固定後に正式派生/最終HEADレビュー・公開証拠・必須CIを通す。

対象正本: docs/development/dev-harness-design-2026-08-07.md と docs/README.md索引。source対象はscripts/frozen_history.py/check_frozen_baselines.pyと関連型付き資産/試験の最小差分。source候補の独立P0は未採用のまま保持し、偽履歴を通した候補を緑としない。共有DB/運用秘密/本人署名には触れない。
