---
description: 正本の確定ゲート。敵対レビュー → 反映ループ → 人間承認 → approved 化・索引更新
argument-hint: "<対象ドキュメントのパス>"
disable-model-invocation: true
---

# 正本確定ゲート(設計書 7.3)

**敵対レビューを経ずに approved にする経路は存在しない。**

## 手順

1. 対象の変更履歴表/frontmatter を `in-review` に更新する
2. 敵対レビューを実行する: `python .claude/scripts/codex_run.py review adversarial -` に対象ドキュメント全文と挑戦観点を渡す(モデルはラッパーが ADR-001 どおり sol xhigh に固定)
3. 指摘を「採用(反映内容)/不採用(理由)」に分類して反映する
4. **収束するまで 2〜3 を繰り返す**(実質的な新規指摘が出なくなるまで。回数を稼ぐことが目的ではない)。1 周(指摘反映まで)ごとに、**実行中 feature の plan.md** の frontmatter `確定ゲート周回` を +1 する(更新先 = 実行時 worktree の `docs/features/*/plan.md` で status が active|in-review かつ branch が worktree と一致するもの。一意に解決できなければ人間に確認 — 黙って省略しない)
5. 採用/不採用の一覧を提示して**人間の承認を明示的に求める**(曖昧な同意で進めない)
6. 承認後: 状態を `approved`・版数確定・変更履歴表に追記・`docs/README.md` 索引を現行化する
7. レビュー往復の要点(重要指摘と対応)を worklog に記録する
