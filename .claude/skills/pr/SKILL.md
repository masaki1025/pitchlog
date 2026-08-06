---
description: PR 作成の唯一の入口。正本反映の突合 → push → PR 作成(コア領域なら人間逐行確認チェックを付与)
argument-hint: "[feature slug]"
---

# PR 作成(設計書 6.1 / 6.3 / 7.6)

## 突合(いずれか NG ならブロックして案内)

1. **正本反映**: 計画書 3 節の宣言と `git -C <worktree> diff origin/develop... --name-only` を突合する。宣言済みで未反映の正本があれば /sync-docs を案内して中断
2. **品質**: /check が本セッションで未実行または失敗なら中断
3. **worklog**: 更新されているか確認(なければ追記を促す)

## クローズ処理(この変更も PR に含める)

- 計画書 frontmatter を `status: merged` に更新し、`docs/README.md` の進行中一覧から外す(マージされた瞬間に develop 上の状態が正しくなる)

## 作成

1. `git -C <worktree> push -u origin feature/<slug>`(承認付き)
2. `gh pr create --base develop` — 本文は `.github/pull_request_template.md` に沿って生成する:
   - 概要 / Notion タスク URL / 計画書リンク / 正本反映の要約 / テスト結果
   - **コア領域**(CLAUDE.md の列挙に対応するパス)に触れる場合、テンプレのコメントアウト部を有効化して「/codex:adversarial-review 済み」「**人間の逐行確認 済み(必須)**」のチェック項目を追加する
3. Notion タスクに PR URL を記録し、ステータスをレビュー待ち(確認待ち)へ。「確認待ち時の依頼事項」欄にレビュー観点を書く(ポータルの規律)

## レビュー導線の案内

Claude 一次レビュー(要件適合・規約・NFR-018 — spec-checker 併用可)→ `/codex:review` → コア領域は `/codex:adversarial-review` + 人間逐行確認 → CI 全グリーン → **人間がマージ**。
