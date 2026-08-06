---
description: PR 作成の唯一の入口。クローズ処理のコミット → 正本反映の突合 → push → PR 作成(コア領域なら人間逐行確認チェックを付与)
argument-hint: "[feature slug]"
---

# PR 作成(設計書 6.1 / 6.3 / 7.6)

すべて worktree 側で行う(`git -C <worktree>`)。

## 1. クローズ処理(この変更を最後のコミットとして PR に含める — マージ後の develop 直接編集を不要にする)

1. 計画書 frontmatter を `status: in-review` に更新する(merged は Git に置かない — 完了は PR 状態・Notion・worktree 除去から導出する)
2. worklog に結果サマリ(何を実装し何を正本へ反映したか)を追記して締める
3. 上記と未コミットの文書変更をすべてコミットする

## 2. 突合(いずれか NG ならブロックして案内)

1. **未コミット確認**: `git -C <worktree> status --porcelain` が空であること(残があれば 1 に戻る)
2. **正本反映**: 計画書 3 節の宣言と `git -C <worktree> diff origin/develop...HEAD --name-only` を突合。宣言済みで未反映の正本があれば /sync-docs を案内して中断
3. **品質**: /check が本セッションで未実行または失敗なら中断

## 3. 作成

1. `git -C <worktree> push -u origin feature/<slug>`(承認付き)
2. `gh pr create --head feature/<slug> --base develop`(**--head を明示** — メインツリーのカレントブランチに依存しない)。本文は `.github/pull_request_template.md` に沿って生成:
   - 概要 / Notion タスク URL / 計画書リンク / 正本反映の要約 / テスト結果
   - **コア領域判定**: 変更ファイルを `.claude/core-areas.json` と突合し、該当する場合はテンプレのコメントアウト部を有効化して「/codex:adversarial-review 済み」「**人間の逐行確認 済み(必須)**」のチェック項目を追加する
3. Notion タスクに PR URL を記録し、ステータスをレビュー待ち(確認待ち)へ。「確認待ち時の依頼事項」欄にレビュー観点を書く(ポータルの規律)

## レビュー導線の案内

Claude 一次レビュー(要件適合・規約・NFR-018 — spec-checker 併用可)→ Codex 技術レビュー(`python .claude/scripts/codex_run.py review normal -` に差分レビュー指示を渡す)→ コア領域は敵対レビュー(`review adversarial`)+ 人間逐行確認 → CI 全グリーン → **人間がマージ**。
