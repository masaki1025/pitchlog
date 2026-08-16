# pitchlog — Claude Code ハーネス

@AGENTS.md

## Claude 固有の導線

**役割分担(設計書 3 章)**: 実装コードは自分で書かず Codex へ委任する(/implement)。例外的に直接書いた場合は `codex_run.py review normal` を必ず通す。Web 調査は Codex(/research)。Git 操作・PR・ドキュメントは Claude の役割。最終判断は常に人間。**Codex 起動はすべて `codex_run.py` ラッパー経由**(プラグイン `/codex:*` は使わない — 経路の一本化)。

### スキル導線(迷ったらこれ)

| 場面 | スキル |
| --- | --- |
| 初回セットアップ | /setup-dev |
| タスク着手(唯一の入口) | /task-start |
| 計画段階の調査(リポ内) | /investigate |
| 計画段階の調査(Web) | /research |
| 実装計画書の作成 | /plan |
| 実装(Codex 委任) | /implement |
| 品質チェック一括 | /check |
| 正本への反映 | /sync-docs |
| 正本の確定ゲート | /finalize-doc |
| PR 作成 | /pr |
| タスク完了(唯一の出口) | /task-done |
| リリース | /release |
| 作業メモ | /worklog |

### コア領域(強化レビュー対象 — 設計書 6.3)

**同期プロトコル / 状況計算(クライアント・サーバー) / 記録権 / テナント分離 / データ移行**(意味範囲の正は設計書 6.3 の境界定義表 / paths〔機械可読〕の正: `.claude/core-areas.json` — /pr・CI が参照)
→ 実装は sol xhigh・敵対レビュー必須・**人間の逐行確認必須**

### 調査サブエージェント(設計書 8.5)

spec-checker(要件突合)/ legacy-analyst(旧システム事実)/ decision-tracer(決定経緯)。
**既定 3 並列**で投げ、作業の重さで増減する。モデルは Opus 5・effort high 固定(frontmatter 済み)。出典のない回答は受け取らない。

### モデル対応表

`docs/adr/ADR-001-codex-model-selection.md` が正。/implement・レビュー系スキルが自動適用する(人が都度選ばない)。

### ドキュメント規律

- 正本の変更は必ず変更履歴表に追記し、`docs/README.md`(索引)を現行化する
- 実装は計画書ゲートを通ってから(いきなりコーディングしない — 設計書 6.1)
- 実装委任は**ステップ単位**(1 委任 = 1 ステップ = 1 コミット)。一括実装させない(設計書 6.1 段階実装)
- Notion タスクの状態遷移・綴りは `.claude/notion-map.json` を参照する(推測しない — 設計書 11.1)
- worktree 運用: 1 タスク = 1 ブランチ = 1 worktree(`../pitchlog-worktrees/<ブランチ名のスラッシュを - に置換>`)。ファイル編集・git 操作は worktree 側で行う(`git -C`)
- **Codex の起動は `.claude/scripts/codex_run.py` ラッパー経由のみ**(生の `codex exec` は codex_guard がブロック — plan status〔implement のみ・`active` 必須〕・計画承認・worktree・sandbox・モデル対応表をラッパーが機構検証する)
