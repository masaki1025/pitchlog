---
date: 2026-09-03
topic: TSK-270 要件主張母集合のマージ後レビュー P0 7 件の是正(TSK-312)
branch: fix/authz-claims-corpus
---

# 作業ログ: 2026-09-03 TSK-270 要件主張母集合のマージ後レビュー P0 7 件の是正(TSK-312)

## やったこと

### /task-start — 着手

- Notion TSK-312 を起票(https://app.notion.com/p/3d093b75e68781d894cac8a869bea666 — 優先度 高・コア領域〔テナント分離〕・TSK-278 ステップ 10 のブロッカと明記)
- worktree `../pitchlog-worktrees/fix-authz-claims-corpus`・ブランチ `fix/authz-claims-corpus` を `origin/develop`(41884a9)起点で作成

## 決定

### /investigate — 調査(3 サブエージェント並列 + 本体で外部 4 方向)

- 結果は `docs/features/authz-claims-corpus/research.md` に統合(典拠つき)
- **P0 7 件の一次記録は現存しない**ことを 4 方向(リポ内文書・GitHub PR #33・Notion TSK-270 全コメント・git log 本文)+ 過去セッション scratchpad で確定 → **再列挙(敵対レビュー再実施)を計画へ**
- 既知 3 カテゴリの構造的裏付け・採取欠陥の原因箇所(`_table_cells` :229-232)・digest 連鎖の全経路・reseal 2 段制約を現物で確認

## 未決・次の一歩

- /plan: 再列挙ステップの設計・H-85 対応案③(件数の非ハードコード化)のスコープ判断・例外表ゲート区分の PO 再確認
