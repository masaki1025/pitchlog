---
feature: mvp-pr197-anchor-exception
status: active
branch: feature/mvp-pr197-anchor-exception
worktree: /home/ymdms/projects/pitchlog-worktrees/feature-mvp-pr197-anchor-exception
重さ分類: コア領域
notion: 未接続（既ユーザーGoal・PR197を作業根拠とする）
created: 2026-11-06
実行方式: 通常
反映周コミット: 適用
承認: 済（PO委任によるCodex主担当/root判断、2026-11-06。本人署名ではない）
計画レビュー周回: 0
確定ゲート周回: 3
---

# PR197の固定Git期待1件の例外

対象はハーネス7.7-1への今回限定の一項と、同項の検査/対向・typed移設・同7.7正式派生。一般統制を再設計せず、27値の自己期待化を避ける固定Git基点1件だけを認める。ユーザーの安全を維持するハーネス調整・最小例外手続き委任で案Aを選ぶ。案Bの外部証拠からの原典取得は局所検証の外部依存と時系列を増やすため採らない。

1. v1.19を適用版とする7.3でv1.20一項を起案し、初回全文敵対レビュー→採否→必要差分確認→PO委任判断を追跡する。承認前はv1.20を自己適用しない。
2. cache修復案を非作者レビューし、偽Git/同時改変/欠落/版違い/重大指摘の拒否と、他全allow-list追加禁止/既反例/旧基準を保持する。source固定後に正式派生/最終HEADレビュー・公開証拠・必須CIを通す。

対象正本: docs/development/dev-harness-design-2026-08-07.md と docs/README.md索引。source対象はscripts/frozen_history.py/check_frozen_baselines.pyと関連型付き資産/試験の最小差分。source候補の独立P0は未採用のまま保持し、偽履歴を通した候補を緑としない。共有DB/運用秘密/本人署名には触れない。


## 重さ・担当・影響する正本

重さ: 重（凍結基準の保護・検査経路を含む）。rootが専用WT唯一writer。非作者の正本レビューとsourceレビューを別に固定し、正式資産追記はrootが直列処理する。正本対象はハーネス/索引、秘密・共有DB・署名・一般承認制度には変更なし。

## 実装ステップ

| # | ステップ | 合格条件 |
| --- | --- | --- |
| 1 | v1.19適用の単一7.3ゲートで限定条文と索引を整合 | 全採否・適用条文・対象版/SHA・PO委任の最終判断を記録 |
| 2 | 対象一件のみのsource/資産/検査を接合 | 独立レビュー・正負対向・7.7前後・公開証拠・必須CI。PR197本体は既mvp-stats-primitives step4へ引き渡す |

## テスト計画

正本はdocs-status/design-propagation/link/索引整合。sourceは固定Git不在/別祖先/偽初出・typed/source同時改変・未知値・別PR/branch/HEAD/diff・証拠欠落・自己レビュー・P0/P1未解消を拒否する。通常allow-list追加禁止・既ブートストラップ/除去規則・develop不変継承を保持。候補の単体成功を正式受理にしない。

## DoD

- [ ] 限定条文のゲート採否と委任判断、sourceの独立レビューを固定する。
- [ ] 正負対向と公式派生の前後/履歴・最終HEAD証拠・必須CIを通す。
- [ ] PR197へ受渡し、正式統合と未実施の製品/実機受入を区別する。


背景・追跡: 既ユーザーMVP Goalと[PR197](https://github.com/masaki1025/pitchlog/pull/197)の継承修復であり、[NFR-015](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-015)の正本整合と[NFR-019](../../requirements/requirements-pitchlog-2026-07-22.md#NFR-019)の拒否検査を保つ。Notionタスクは未取得で、同期したとは記録しない。
