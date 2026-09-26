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

### 計画レビュー 1 周目(`review normal`・terra max・340K tok・判定 = 否決 P0×1 / P1×7)— 全件採用

| # | 重大度 | 要旨 | 採否・反映 |
| --- | --- | --- | --- |
| 1 | P0 | 未承認の対応表でラッパーを先に書き換え、確定ゲートを新モデルで回す順序(ADR-001 帰結「本表どおり自動指定」・7.3-1 適用版原則に反する) | 採用: 順序を「起案 → 確定ゲート(現行 5.6-sol xhigh)→ 機構同期 → 実機検証」へ。スモーク不成立時の revert 経路を明記 |
| 2 | P1 | `pr/SKILL.md` は guard_paths(core-areas.json:8)なのに非該当と書いていた | 採用: pr/plan の SKILL.md はモデル名を含まないため対象外へ。finalize-doc(guard_paths)も触らず次の guard_paths PR へ送ると明記 |
| 3 | P1 | 台帳の反映宣言が条件付き(/pr は宣言済み未反映で中断する) | 採用: 「反映なし(該当時は先に 3 節へ宣言追記)」へ |
| 4 | P1 | 案 A/B が決定可能な粒度でなく、推奨根拠が未照合事実・代理試算に依存 | 採用: 2 案とも 7 行を定義、試算を代理指標と明記、品質下限・実測期間(3 ゲート/4 週)・巻き戻し条件を PO 判断へ |
| 5 | P1 | CLI 更新後の利用可否確認が定数書換えの後 | 採用: 阻止条件 0(コミットなし・確認不能なら停止)を新設 |
| 6 | P1 | 共有 settings.json の副作用・実効確認が不足 | 採用: 適用対象・上書き手段・permissions/hooks 差分不変・新規セッションでの実効確認を PO 判断③と合格条件へ |
| 7 | P1 | 同期テストが Markdown 表のバイト一致に依存し、経路を検証しない | 採用: 構造的抽出 + 負例 3 種 + 経路テストへ。9.4 の合格条件も意味一致へ |
| 8 | P1 | 安全分類器の遮断を観測に留め、失敗判定・復旧が無い | 採用: 合格条件に「判定行あり・遮断なし」、不成立時は安全語彙へ切替・周回不算入・revert を明記 |

- frontmatter `計画レビュー周回` を 1 へ

### 計画レビュー 2 周目(`review normal`・terra max・268K tok・判定 = 否決 P0×3 / P1×3)— 全件採用

| # | 重大度 | 要旨 | 採否・反映 |
| --- | --- | --- | --- |
| 1 | P0 | 確定ゲート開始(2 正本の in-review 化・索引・適用版の worklog 記録)が同一コミットになっていない(finalize-doc 手順 1) | 採用: ステップ 1 を「ADR-001 v1.1 + 設計書 v1.18 の起案を単一コミット」へ統合(ステップ総数 5 → 4) |
| 2 | P0 | 案 B が阻止条件 0・スモーク期待値・巻き戻し文言・スキル/CLAUDE.md の更新範囲に伝播していない | 採用: 「選択案 → 検証する (model, effort) の集合」の導出表を置き、阻止条件・スモーク・巻き戻しを選択後値で分岐。CLAUDE.md:30 を対象に追加、finalize-doc SKILL は案 B のときのみ対象(逐行確認) |
| 3 | P0 | スモーク不成立時に approved の ADR へ in-review 追随行を足す経路が規約(現在状態 = frontmatter のみ)に反する | 採用: 不成立時は revert + worklog 記録 + PR 不統合で停止。対応表を変える継続判断は ADR-001 v1.2 + 新規確定ゲート |
| 4 | P1 | 「構造的抽出」の文法が一意でない(Web 調査行に 2 組の model/effort) | 採用: ADR の決定表を固定ヘッダ・8 行(--deep を独立行)・行あたり code span 1 個・effort トークン 1 個の固定構文にし、行キー → 定数の対応と負例を明記 |
| 5 | P1 | 設計書 6.1・8.1・8.4・9.2 に残る terra/Opus 5 の現行記述が更新範囲外 | 採用: 設計書 v1.18 の対象を「変更履歴表を除く全節」へ広げ、grep の合格条件に |
| 6 | P1 | スモーク遮断時に安全語彙で再試行せず即 revert | 採用: 同一経路を安全語彙で 1 回だけ再実行し、両方不成立で revert。両試行を worklog へ |

- frontmatter `計画レビュー周回` を 2 へ

## 決定

## 未決・次の一歩

- 計画レビュー(`review normal`)→ 指摘反映 → PO 承認(判断事項 3 点の確定)→ /implement
- 未照合の典拠(openai.com・help.openai.com の 4 ページ)は CLI 更新後のカタログ実機確認で ID・effort を裏付ける
