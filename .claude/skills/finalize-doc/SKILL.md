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
4. **収束するまで 2〜3 を繰り返す**(実質的な新規指摘が出なくなるまで。回数を稼ぐことが目的ではない)。**指摘反映を伴う** 1 周ごとに、**実行中 feature の plan.md** の frontmatter `確定ゲート周回` を +1 する(指摘なしの収束確認周は数えない。更新先 = 実行時 worktree の `docs/features/*/plan.md` で status が active|in-review かつ branch が worktree と一致するもの。一意に解決できなければ人間に確認 — 黙って省略しない。キーが無い旧 plan は `0` を追記してから更新する)
5. 採用/不採用の一覧を提示して**人間の承認を明示的に求める**(曖昧な同意で進めない)
6. 承認後: 状態を `approved`・版数確定・変更履歴表に追記・`docs/README.md` 索引を現行化する
7. レビュー往復の要点(重要指摘と対応)を worklog に記録する

- 指摘反映で**コード修正**が必要になり、かつ実行中 feature の plan が `in-review`(PR 段階)の場合は、先に /pr の「差し戻しが発生したら」手順で `status: active` へ戻してから /implement する(`codex_run.py implement` は `active` 以外を拒否する — 設計書 6.1 差し戻しの往復)
