---
description: 承認済み実装計画書に基づき Codex へ実装を委任し、検証まで一気通貫で行う
argument-hint: "<plan.md のパス>"
---

# 実装の Codex 委任(設計書 6.1 / 9.2 / 9.4 / 12.1)

## 前提チェック(NG なら中断)

1. 計画書 frontmatter が `承認: 済` であること(未承認なら /plan のレビュー手順を案内して中断)
2. タスク worktree(`../pitchlog-worktrees/<slug>`)が存在すること(なければ /task-start を案内)

## 実行

1. **モデル選定**: frontmatter の重さ分類から ADR-001 の対応表で決定する:
   - 軽微 → `gpt-5.6-terra` medium / 通常 → `gpt-5.6-terra` max / コア領域 → `gpt-5.6-sol` xhigh / 機械的軽作業 → `gpt-5.6-luna` xhigh
2. **プロンプト構築**: codex:gpt-5-4-prompting の知見に沿って組む。含める: 計画書の該当節(方針・スコープ・DoD)/ 変更してよい範囲(**計画にない範囲へ触れない**ことを明記)/ テスト要求(6 節のテスト計画)/ AGENTS.md は Codex が自動で読む前提で重複させない
3. **実行**(ネットワークは既定遮断。必要時は 12.1 の例外手順 — 実行前に理由を人間へ報告):

```bash
codex exec -C <worktreeの絶対パス> --ignore-user-config -s workspace-write \
  -m <モデル> -c model_reasoning_effort=<effort> "<プロンプト>"
```

4. 継続・差し戻しは `codex exec resume --last "<修正指示>"`(仕切り直すときだけ新規実行)

## 検証(合格まで差し戻しを繰り返す)

- /check を worktree で実行(存在する品質ゲートすべて)
- 差分レビュー: 計画スコープ外の変更がないか / NFR-018 のコピー実装がないか / DoD を満たすか
- 要件との突合が必要なら spec-checker に委任

## 完了処理

- **Codex はコミットしない**。Claude が `git -C <worktree>` でコミットする(Conventional Commits・日本語要約。1 まとまり 1 コミット)
- 変更ファイル一覧・テスト結果・DoD 充足状況を報告し、次の導線(/sync-docs → /pr)を案内する
