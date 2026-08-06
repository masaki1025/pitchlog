---
description: 承認済み実装計画書に基づき Codex へ実装を委任し、検証まで一気通貫で行う(ラッパー経由のみ)
argument-hint: "<plan.md のパス>"
---

# 実装の Codex 委任(設計書 6.1 / 9.2 / 9.4 / 12.1)

Codex の起動は必ず **`.claude/scripts/codex_run.py`** 経由(生の `codex exec` は codex_guard がブロックする)。ラッパーが計画承認・worktree・sandbox・モデル対応表(ADR-001)を機構検証する。

## 手順

1. **プロンプト構築**(codex:gpt-5-4-prompting の知見に沿う): 計画書の該当節(方針・スコープ・DoD)/ 変更してよい範囲(**計画にない範囲へ触れない**ことを明記)/ テスト要求(計画書 6 節)。AGENTS.md は Codex が自動で読むため重複させない
2. **実行**(モデル・effort は計画書 frontmatter の重さ分類からラッパーが自動選択):

```bash
python .claude/scripts/codex_run.py implement docs/features/<slug>/plan.md - <<'EOF'
<プロンプト>
EOF
```

3. **差し戻し**(同じ Codex セッションを継続 — セッション ID はラッパーが feature 単位で保存済み):

```bash
python .claude/scripts/codex_run.py implement docs/features/<slug>/plan.md --resume - <<'EOF'
<修正指示>
EOF
```

- ネットワークが必要な例外(12.1)は、理由を人間へ報告して了承を得てから `PITCHLOG_ALLOW_NET=1` を付けて実行する

## 検証(合格まで差し戻しを繰り返す)

- /check を worktree で実行(存在する品質ゲートすべて)
- 差分レビュー: 計画スコープ外の変更がないか / NFR-018 のコピー実装がないか / DoD を満たすか
- 要件との突合が必要なら spec-checker に委任

## 完了処理

- **Codex はコミットしない**。Claude が `git -C <worktree>` でコミットする(Conventional Commits・日本語要約。1 まとまり 1 コミット)
- 変更ファイル一覧・テスト結果・DoD 充足状況を報告し、次の導線(/sync-docs → /pr)を案内する

## fast path(軽微変更 — 設計書 6.1。人間の事前 OK 必須)

非コア(`.claude/core-areas.json` に該当しない)かつ小差分(目安 50 行以下)かつ正本影響なしの変更は、計画書なしで `python .claude/scripts/codex_run.py fast -`(worktree 内で実行、terra medium 固定)。PR 本文に短縮計画(目的/変更/確認方法)を書く。
