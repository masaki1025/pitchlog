---
feature: pr191-historical-sql-proof
status: active
branch: fix/pr191-historical-sql-proof
承認: PO委任によるCodex/root判断（2026-11-06、安全性を維持する検査対象版の修復）
計画レビュー周回: 0
確定ゲート周回: 0
---

# PR191括弧修正の履歴証拠と現行SQL検査を分離する

PR191の「5個の括弧以外は同一」の検査が現行可変rendererに掛かり、採用済み走者statusの3CASE追加で失敗する。旧SHAを実値へ変更しない。既frozen-inputsの旧SQL SHA `18fb89b0d4065b536a726bc5f17ccfcb5b3577825a42990387e08e07c891712d` は不変。対象はbackend/tests/test_terminal_pitch_write_stamp.py、新backend/tests/fixtures/pr191-historical-sql-proof/、本計画。製品SQL/認可/拒否条件に変更なし。

1. immutable Git 8712866dのbackend/srcを隔離cacheへ展開し当時のcandidate_function_bodiesで括弧修正後SQLを導出。5括弧を戻したSHAが既frozen-inputsと一致することを確認し、その当時SQLを試験fixtureへ固定（修正後SHA6a51bc53df61ecd37262d8fa3b05c4f702f4861f419376d752062de170bce6b6）。現行出力から期待値を作らない。
2. 履歴全byte比較の入力をその固定SQLへ変更し、5個/旧SHA一致を維持。現行v2/v3には別に非括弧CASE危険構文拒否と既走者status/TX検査を維持する。改竄fixtureが既frozen値で拒否される対向を確認。
3. 関連検査、非作者レビューでP0/P1解消後に接続候補へ接合し、必須CIは最終候補で行う。単なる期待緩和で赤を消さない。正式資産値受理や人間確認を自称しない。
