---
date: 2026-09-26
topic: TSK-463 ハーネスのモデル世代更新とトークン効率改善(Opus 5.5・GPT-6 Astra)
branch: feature/harness-model-refresh
---

# 作業ログ: 2026-09-26 TSK-463 ハーネスのモデル世代更新とトークン効率改善

## やったこと

### /task-start

- PO 指示(2026-09-26): 「Opus 5.5・GPT-6 が出たのでそれらを使い、サブスクの利用上限内でより長く作業できるようトークン効率を改善する」
- Notion `TSK-463` を起票(担当 = 徳光・優先度 中・DoD 3 項目)。ブランチ `feature/harness-model-refresh`・worktree `../pitchlog-worktrees/feature-harness-model-refresh`(origin/develop = `1a404101` 起点)
- メインツリーの develop はローカルが 998 コミット遅れていたため `git pull --ff-only` で現行化してから着手(ADR-001・`codex_run.py`・`.claude/agents/*`・CLAUDE.md は fdda374 以降変更なし。設計書は v1.17)

### 事実確認(ローカルで確認できたもの — 出典つき)

- Codex CLI **0.153.4**。モデルカタログ(`~/.codex/models_cache.json`・fetched 2026-09-23): `gpt-6-astra`(GPT-6 世代・"Frontier intelligence for the most demanding work"・effort low/medium/high/xhigh/max/ultra・既定 medium・multi_agent effort xhigh・ctx 272K)/ `gpt-5.6-sol`・`gpt-5.6-terra` は **"Older"** 表記 / `gpt-5.6-luna` / `gpt-5.5` は **2026-10-14 廃止**(後継 gpt-5.6-sol)。**"gpt-6-sol" という ID はカタログに無い**(PO の呼称は astra を指すと解釈 — 要確認)
- Claude Code **2.1.283**。バイナリ内のモデル一覧に `claude-opus-5-5` が存在し、「Opus 5.5(`claude-opus-5-5`), now the default Opus model — 1M context」の記述あり
- 利用者設定(`~/.claude/settings.json`): 主セッション `fable[1m]`・`effortLevel: xhigh`

### /investigate + /research(調査メモ `docs/features/harness-model-refresh/research.md`)

- **Web 調査を Codex `research`(terra high・live search)で 3 回**実行: A = OpenAI/Codex 側(164K tok)・B = Anthropic/Claude Code 側・C = GPT-6 Sol の原文引用(89K tok)。**重要事実は Claude が公式 URL を再取得して照合**(platform.claude.com・code.claude.com・support.claude.com・developers.openai.com は取得可 / openai.com・help.openai.com は 403 のため Codex の原文引用に依存 — research.md に「未照合」と明記)
- **decision-tracer(Opus 5 high)1 本**で ADR-001・設計書 8.5/9.4/6.3/7.x・台帳・要件書の決定記録を突合(研究メモ C 節)。報告が長く 1 通目が途中で切れたため 2 通に分けて再送させた
- **訂正**: 着手時にカタログ(0.153.4)から「gpt-6-sol は存在しない」と推定したが、GPT-6 Sol/Luna は 2026-09-22 公開で **CLI 0.157.0(09-25)からカタログに載る**。PO の呼称どおり `gpt-6-sol` が実在する
- ベースライン実測(ローカル): Claude 30 日 = 主セッション Fable 系が API 相当額の 75%・1 ターン平均 40 万トークンのキャッシュ読み取り / Codex 60 日 = 5.6-sol xhigh 42 セッション(入力 105.7M)・5.6-terra max 49 セッション(89.0M)。集計スクリプトはセッションの scratchpad に置いた(リポジトリには入れない — 後続タスク候補)

### /plan(起案・未承認)

- 計画書 `docs/features/harness-model-refresh/plan.md` を起案。ステップ 5 本(文書 2・コード 1・設定 1・実機検証 1)+ 確定ゲート(ADR-001 v1.1 + 設計書 v1.18 を単一ゲート)
- **PO 判断事項 3 点**(計画書 4 節): ① Codex 対応表 = 案 A(gpt-6-sol 一本化・推奨)/ 案 B(コア・敵対 = astra)② effort 据え置き(推奨)③ 主セッションの Opus 5.5 化をプロジェクト settings.json で機構化(推奨)
- **前提の人間作業**: Codex CLI を 0.157.x へ更新(ステップ 3 の前)

## 決定

## 未決・次の一歩

- 計画レビュー(`review normal`)→ 指摘反映 → PO 承認(判断事項 3 点の確定)→ /implement
- 未照合の典拠(openai.com・help.openai.com の 4 ページ)は CLI 更新後のカタログ実機確認で ID・effort を裏付ける
