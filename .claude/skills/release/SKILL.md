---
description: リリースの唯一の入口。要件書8章 DoD チェック → develop→main PR → タグ
argument-hint: "<バージョン vX.Y.Z>"
disable-model-invocation: true
---

# リリース(設計書 6.4 / 要件書 8 章)

## 手順

1. **DoD チェック**: 要件書 8 章の判定基準 8 項目(Must充足 / CI全グリーン / 実戦リハーサル / 性能実測 / 移行完了 / バックアップ復元リハーサル / ドキュメント現行化 / 未決事項の決着)を 1 項目ずつ、根拠(テスト結果・文書リンク)付きで確認する。未達があれば**中断**して残作業を列挙する
2. 全項目 OK なら**人間にリリース可否の判定を明示的に求める**(判定者 = システム管理者。要件書 8 章)
3. 判定 OK 後:
   - `gh pr create --base main --head develop`(タイトル: `release: vX.Y.Z`)
   - CI 全グリーンと人間のマージを確認
   - `git tag vX.Y.Z` → `git push origin vX.Y.Z`(承認付き)
4. リリース記録を worklog と Notion に残す(日時・バージョン・DoD 根拠へのリンク)
