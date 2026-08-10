---
description: PR 作成の唯一の入口。クローズ処理のコミット → 正本反映の突合 → push → PR 作成(コア領域なら人間逐行確認チェックを付与)
argument-hint: "[feature slug]"
disable-model-invocation: true
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

## fast path 分岐(設計書 6.1。人間の事前 OK 済みが前提)

- 計画書は /task-start の**雛形がメタデータとして残っている**前提(承認・ステップ表・3節の記入は不要)。手順 1-1 の status 更新と frontmatter(branch・notion)の参照は通常どおり行う
- 突合 2-2(正本反映)は「正本への影響がない」ことの差分確認に置換。2-3(/check)は同じ
- PR 本文に**短縮計画**を必須記載: 目的 / 変更内容 / 確認方法 / 人間の事前 OK への言及
- 以降(push・PR 作成・Notion 遷移)は通常経路と同じ

## 3. 作成

1. `git -C <worktree> push -u origin <branch>`(承認付き。branch は計画書 frontmatter の `branch` — `feature/*` と `fix/*` の両方に対応)
2. `gh pr create --head <branch> --base develop`(**--head を明示** — メインツリーのカレントブランチに依存しない)。本文は `.github/pull_request_template.md` に沿って生成:
   - 概要 / Notion タスク URL / 計画書リンク / 正本反映の要約 / テスト結果
   - **コア領域/検査経路判定**: 変更ファイルを `.claude/core-areas.json` の各領域 `paths` と `guard_paths` の**両方**に突合する。コア領域該当 → テンプレのコメントアウト部を有効化(adversarial レビュー + 逐行確認の 2 項目)。guard_paths のみ該当 → 逐行確認チェックのみ有効化。**チェック文言は `scripts/core_guard.py` の `REQUIRED_CHECK_TEXT` と完全一致**させる(CI の core-guard ジョブが `- [x]` を機械検査する — 文言を変えない)
   - **fast path 判定**: fast の場合はテンプレの fast path コメントアウト部を有効化する
3. Notion タスクの URL プロパティに PR URL を記録し、ステータスを `確認待ち` へ(綴りの正: `.claude/notion-map.json` — 推測しない)。「確認待ち時の依頼事項」欄にレビュー観点を書く(ポータルの規律)

## レビュー導線の案内

反対側レビュー(Codex 実装 → Claude 一次レビュー〔要件適合・規約・NFR-018 — spec-checker 併用可〕/ Claude 直実装 → `python .claude/scripts/codex_run.py review normal -` に差分レビュー指示)→ コア領域は敵対レビュー(`review adversarial`)+ 人間逐行確認 → CI 全グリーン → **人間がマージ**。プラグイン `/codex:*` は使わない(経路はラッパーに一本化)。

- **差し戻しが発生したら**(PR の OPEN/CLOSED を問わない): Notion ステータスを `差し戻し` へ(指摘要約をタスクへコメント — notion-map.json)。**修正の再開時は、先に計画書 frontmatter を `status: in-review → active` に戻してから** Notion を `進行中` に戻す(現在地導出が「実装中(差し戻し修正)」を示す — scripts/feature_status.py。この状態更新コミットにはステップ記法を付けない)。修正は**通常経路では** /implement の `--resume` でステップ単位に行う(修正も 1 まとまり 1 コミット)。**fast path の差し戻しは `codex_run.py fast` の新規実行または Claude 直修正**で行う(`--resume` は使わない — fast にステップ表・保存セッションはない)。**差し戻し修正のたびに fast の 3 条件(非コア・小差分・正本影響なし)と人間の事前 OK を再確認**し、満たさなくなったら通常計画(/plan)へ切り替える
- **修正・検証完了(再レビュー依頼)**: 計画書 frontmatter を `active → in-review` に戻し、Notion を `確認待ち` へ。**OPEN の既存 PR には `gh pr create` を行わず再レビュー依頼のみ**。CLOSED の場合は reopen または新 PR(本スキルの手順 3)による
