---
feature: harness-model-refresh
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e793b75e68781a681aef2672934a736
branch: feature/harness-model-refresh
created: 2026-09-26
計画レビュー周回: 1        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
反映周コミット: 適用       # 適用 | 規約制定前(必須・既定値なし。確定ゲートの反映周コミット突合の適用境界 — 設計書 6.1)
---

# 実装計画書: ハーネスのモデル世代更新とトークン効率改善(Opus 5.5・GPT-6 Sol)

## 1. 背景・目的

- Notion: [TSK-463](https://app.notion.com/p/3e793b75e68781a681aef2672934a736)。PO 指示(2026-09-26): 「Opus 5.5・GPT-6 が出たのでそれらを使い、サブスクの利用上限内でより長く作業できるようトークン効率を改善する」
- 関連要件: 本タスクは製品機能ではなく開発ハーネスの改訂であり、要件書の FR/NFR は対象外(要件書の規範条文にモデル名は無い — [research.md](research.md) C-5)。ハーネス側の規範は設計書 8.5(調査サブエージェント)・9.4(モデル対応表)・[ADR-001](../../adr/ADR-001-codex-model-selection.md)
- ADR-001 の見直しトリガー 3 条件(世代交代・料金改定・新 tier 登場)がすべて成立した(research.md C-1)。GPT-6 世代に terra は無く astra が加わったため、ID 置換ではなく対応表の再設計になる(C-7 #3)
- 実測(research.md A-3): Claude 側は主セッション(Fable 系)が消費の約 8 割・1 ターン平均 40 万トークンのキャッシュ読み取り。Codex 側は 5.6-sol xhigh(敵対レビュー)と 5.6-terra max(実装)が同程度。単価の高い箇所 = Fable の主セッションと 5.6-sol の敵対レビュー

## 2. スコープ

### やること

1. **ADR-001 を v1.1 へ改訂**(決定内容の変更 = 版繰り上げ・7.3 確定ゲート): Codex モデル対応表を GPT-6 世代へ再設計する。案 A / 案 B の 2 案を 4 節に**7 行すべて**定義し、PO 判断で 1 案に確定してから起案する
2. **設計書を v1.18 へ改訂**(単一の確定ゲートで ADR-001 と一括 — 先例 v1.15): 8.5 実行既定を `claude-opus-5-5`・`effort: high` へ(「モデルは固定のまま」の固定先を更新・`effortLevel` 併記の廃止・定義例の修正)/ 9.4 表を ADR-001 v1.1 と同期 / **8.1 に主セッション(Claude Code 本体)の推奨設定を新設**
3. **確定ゲート(/finalize-doc)を、現行 approved の対応表(`gpt-5.6-sol` xhigh・ラッパー未変更)で完了する**。approved 化の前に機構(ラッパー・agents・settings)へは触れない
4. **approved 化後に機構を同期**: `codex_run.py` の定数(`MODEL_MAP` / `RESEARCH` / `RESEARCH_DEEP` / `REVIEW_NORMAL` / `REVIEW_ADVERSARIAL`)を新表へ / **ADR-001 の表 ↔ 定数の構造的同期テスト**と**ラッパー各経路の引数テスト**・**agents frontmatter の固定テスト**を新設 / `.claude/agents/*.md` / `CLAUDE.md` / スキル本文の旧モデル名(`implement`・`research` の 2 本)を「ラッパーが ADR-001 どおりに固定」へ一般化 / プロジェクト `.claude/settings.json` に主セッションの `model`・`modelSettings`(PO 判断③が可の場合)
5. **実機検証と記録**: ラッパー経路(`review normal`・`review adversarial`)のスモークで新 ID の `max`・`xhigh` 受理と判定行の返却を確認し worklog に記録。ADR-001 の文脈へ実機検証の版を**版を上げない追随行**で追記(7.6-3 前段)

### やらないこと

- 既定 3 並列の変更(H-35 で維持が対応済み — research.md C-7 #10)/ effort 値の引き下げ(PO 指示事項 v0.8。モデル切替と別変数として移行後の計測で再判定 — 4 節の実測期間)/ Fast・Ultra の利用(利用枠を増やす・`exec` で指定不可)
- `gpt-6-luna` の新規用途追加(機械的軽作業は 5.6-luna → 6-luna の ID 置換のみ)
- 要件書・`requirements-draft-pitchlog.md` の編集(C-5)
- **guard_paths に該当するスキルの編集**: `.claude/skills/pr/SKILL.md`(モデル名を含まないため変更不要)・`.claude/skills/finalize-doc/SKILL.md`(`:15` の「ADR-001 どおり sol xhigh」は "ADR-001 どおり" が主語でラッパーが決めるため実害なし。**古い括弧書きの除去は次に guard_paths を触る PR へ送る** — 本 PR を逐行確認・SHA 拘束マージの対象にしないため)
- 使用量プロファイル集計の `scripts/` 化・`autoCompactWindow` の実測比較・調査前 `git fetch` の導線明文化(後続タスク候補 — research.md 末尾)
- Codex CLI の更新そのもの(開発者の環境作業。**阻止条件 0** として人間が実施する — onboarding 1-6 のインストーラを再実行)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/adr/ADR-001-codex-model-selection.md` | **v1.1**: 対応表を GPT-6 世代へ再設計(PO 確定案)・文脈(CLI 0.157.x のカタログ・料金・利用枠の重み〔代理指標〕・ベンチマーク〔未照合分は明示〕・移行前ベースライン)・理由(欠陥コスト論の GPT-6 世代への読み替え)・帰結(見直しトリガーに「astra への昇格が必要になった実例」「実測期間終了時の再判定」を追加・Ultra は対話専用・Fast 不使用)・変更履歴行。approved 化後、ステップ 5 で実機検証の追随行(版は上げない) | **finalize-doc**(ADR-001 v1.1 + 設計書 v1.18 を単一ゲート)+ 追随行は PR レビュー |
| `docs/development/dev-harness-design-2026-08-07.md` | **v1.18**: 8.1 に主セッション推奨設定を新設 / 8.5 実行既定を `claude-opus-5-5`・`effort: high`(`effortLevel` 併記廃止・定義例修正)/ 9.4 表を ADR-001 v1.1 と同期 + 「実機検証 = 0.157.x」/ 射程宣言・変更履歴行 | **finalize-doc**(同上) |
| `docs/README.md` | ADR-001・設計書の版・状態・最終更新の現行化(起案時 in-review・承認時 approved の 2 回) | PR レビュー |
| `docs/development/harness-evaluation.md` | **反映なし**(現時点)。`/pr` クローズ処理で台帳追記に該当すると判断した場合は、**先に本表へ宣言を追記してから**反映する(`.claude/skills/pr/SKILL.md` 1-3)。該当しなければ worklog に「台帳への追記なし」と理由を残す | — |
| 要件書・ADR-002〜004・onboarding.md・github-setup.md・`.claude/skills/{pr,finalize-doc,plan}/SKILL.md` | **反映なし** | — |

**正本体系外だが同一 PR で更新するもの**: `.claude/scripts/codex_run.py`・`tests/test_codex_run.py`(同期テスト・経路テストの追加)・`tests/test_agents_frontmatter.py`(新規)・`.claude/agents/{spec-checker,legacy-analyst,decision-tracer}.md`・`CLAUDE.md`・`.claude/skills/{implement,research}/SKILL.md`・`.claude/settings.json`(PO 判断③が可の場合のみ)・`docs/features/harness-model-refresh/{plan,research}.md`・worklog

## 4. 実装方針

- **重さ分類 = 通常** の根拠: 変更対象はハーネスのラッパー定数・設定・文書であり、コア領域 5 領域(設計書 6.3)の paths にも `guard_paths` にも該当しない(research.md A-4・C-7 #8。guard_paths に該当する `pr`・`finalize-doc` の SKILL.md は**触らない** — 2 節)。ただし typo 級の軽微でもない(ラッパーの機械適用値と正本 2 本の版繰り上げを伴う)

### 阻止条件 0(コミットなし — ステップ 1 の前に人間 + Claude で確認)

1. 人間が Codex CLI を **0.157.x 以上**へ更新する(GPT-6 Sol/Luna の `minimal_client_version` = 0.155.0・カタログ追加は 0.157.0 — research.md B-3)
2. Claude が `~/.codex/models_cache.json`(更新後に再取得されたもの)で `gpt-6-sol`・`gpt-6-luna` の存在と `supported_reasoning_levels` に `max`・`xhigh`・`medium`・`high` が含まれることを確認し、版・fetched_at とともに worklog へ記録する
3. **確認できなければ対応表を書き換えず停止**し(ステップ 1 にも進まない)、PO へ報告する(ロールアウト条件・ワークスペース条件で提供されない可能性があるため)

### PO 判断事項(承認時に明示的に確定する — 計画レビュー前の暫定値は推奨案)

**① Codex 対応表**(2 案とも 7 行すべてを定義。推奨 = 案 A):

| 作業 | 現行(ADR-001 v1.0) | 案 A(推奨): gpt-6-sol 一本化 | 案 B: コア・敵対 = astra |
| --- | --- | --- | --- |
| 通常実装(CRUD・画面・帳票・テスト) | `gpt-5.6-terra` max | `gpt-6-sol` max | `gpt-6-sol` max |
| 軽微な修正(小さな差分・微調整) | `gpt-5.6-terra` medium | `gpt-6-sol` medium | `gpt-6-sol` medium |
| コア領域の実装(6.3 のリスト) | `gpt-5.6-sol` xhigh | `gpt-6-sol` xhigh | `gpt-6-astra` medium |
| 機械的軽作業(リネーム・ボイラープレート) | `gpt-5.6-luna` xhigh | `gpt-6-luna` xhigh | `gpt-6-luna` xhigh |
| 一次コードレビュー(通常 PR) | `gpt-5.6-terra` max | `gpt-6-sol` max | `gpt-6-sol` max |
| 敵対レビュー・コア領域 PR・正本確定ゲート | `gpt-5.6-sol` xhigh | `gpt-6-sol` xhigh | `gpt-6-astra` medium |
| Web 調査(/research)/ `--deep` | `gpt-5.6-terra` high / `gpt-5.6-sol` xhigh | `gpt-6-sol` high / `gpt-6-sol` xhigh | `gpt-6-sol` high / `gpt-6-astra` medium |

  - **根拠(案 A を推奨する理由)**: gpt-6-sol は 5.6-sol の後継 tier で API 単価が半額(✔ 照合済み — research.md B-2)。公式発表は "improves substantially over GPT-5.6 Sol"(FrontierCode)・"higher usage limits and lower cost" と述べる(**未照合** — Codex の原文引用。B-3)。利用枠の試算(現行比 **−35%** / 案 B **+97%**)は **Business/Enterprise の credit rate card を代理指標にしたもの**で、Plus/Pro の係数は非公開(B-3)。したがって推奨の根拠は「単価半額(照合済み)+ 旧フロンティア以上との公式声明(未照合)」であり、**品質の同等性は移行後の実測で確認する**(下記の品質下限・実測期間)
  - **案 B の位置づけ**: 上位の品質を買う代わりに Codex 側の消費が倍増する試算。effort は "Astra at Low effort can outperform Sol at High effort"(未照合)に基づき medium から始める。案 B を採る場合も通常枠は案 A と同じ
  - **品質下限・実測期間・巻き戻し条件**(PO 判断①の一部として固定): 移行後 **3 回の確定ゲート(または 4 週間)** を実測期間とし、各ゲートの周回数・P0/P1 検出数・遮断有無を worklog と台帳候補に記録する。**巻き戻し条件** = (a) 新 ID で `max`/`xhigh` が受理されない (b) 安全分類器の遮断が 5.6-sol 時代(台帳 :20 — 1 ゲートで flagged 2 回)より増える (c) 実測期間中に「敵対レビューが計画レビュー通過後の P0 を検出できなかった」実例が出る。いずれかで **astra への昇格(案 B 相当)を ADR-001 v1.2 として再改訂**する(見直しトリガーに明記)。H-30 は「モデル差だけの効果とは切り分けられない」としているため、品質下限の判定は周回数でなく**検出実例の有無**で行う

**② effort**: 据え置き(推奨)。出力トークンは Codex 側消費の 3 割程度で、モデル切替と別変数として実測期間の終了時に再判定する

**③ 主セッションの機構化**(推奨 = 機構化): プロジェクト `.claude/settings.json` に `"model": "claude-opus-5-5"` と `"modelSettings": {"claude-opus-5-5": {"effortLevel": "high"}}` を追加する
  - **適用対象**: 本リポジトリを開く**全開発者の新規セッション**(共有設定 — 設計書 8.1。`~/.claude/settings.json` の `"model": "fable[1m]"` より優先される)
  - **上書き手段**: セッション内 `/model`(Fable への昇格・相談役)/ `.claude/settings.local.json`(個人の恒久上書き・gitignore 済み)
  - **effort = high の根拠**: Opus 5.5 の既定は medium で、トップレベル `effortLevel` は Opus 5.5 に効かない(✔ B-1)。現行の主セッションは Fable xhigh で運用しており、まず **high** で品質の連続性を取り、medium への引き下げは実測期間の後に判定する(Codex の推奨は medium — B-1)
  - **副作用の統制**: `permissions`・`hooks` ブロックは**差分不変**(ステップ 4 の合格条件で `git diff` が `model`・`modelSettings` の 2 キー追加のみであることを確認)。`tests/test_hooks.py` のフック実在検査が引き続き緑
  - **機構化しない場合**: 8.1 の推奨記述のみとし、`.claude/settings.json` は触らない(3 節の宣言から外す)

### 起案値(PO 判断①を案 A・③を機構化とした場合)

- **ADR-001 v1.1**: 上表の案 A 列。通常枠とコア枠が同一モデルになるため、水準差は **effort(max / xhigh)と依頼文(6.3 の敵対姿勢・7.3-5 の規約)**で保つ。ADR-001 理由 1「コア領域と品質ゲートにフロンティア級」は「**旧フロンティア(5.6-sol)以上の水準**」と読み替え、astra への昇格を見直しトリガーに置く。文脈には移行前ベースライン(research.md A-3 の要約)と代理指標の限界を書く
- **設計書 8.5 の実行既定**: `model: claude-opus-5-5`(明示 ID・エイリアス禁止は維持)・`effort: high`(Opus 5.5 の既定は medium なので明示必須)・`effortLevel` は**公式 frontmatter リファレンスに存在しないキー**として併記を廃止(C-6 — P1-6 の原典は不明のため「公式仕様の確定(✔ B-1)」を新典拠として記録)
- **8.1 の新設段落**: 主セッションは `claude-opus-5-5`・effort high を既定とし、Fable 5.1 は「Opus 5.5 high で足りない長期自律作業・相談役」に限定(Max の週次上限 50% 枠 — ✔ B-1)。Fast mode は使わない(プラン枠でなく usage credits を消費)

### 順序と差し戻し経路

- **順序**: 阻止条件 0 → ステップ 1・2(正本を in-review で起案)→ **/finalize-doc(現行 approved の対応表 = `gpt-5.6-sol` xhigh・ラッパー未変更で実施。7.3-1 の適用版原則と ADR-001 帰結「本表どおり自動指定」に従う)** → approved 化 → ステップ 3〜5(機構の同期・実機検証)→ /sync-docs → /pr。**確定ゲートの反映周コミットにはステップ記法を付けない**(設計書 6.1)
- **確定ゲート中の安全分類器の遮断**(台帳 H-75・:20): 判定行のない応答は周として数えず同一周を再依頼する(7.3-5)。再依頼は依頼文を「所在・理由・修正案の 3 点」形式の安全語彙へ切り替える
- **ステップ 5 のスモークが不成立**(新 ID で `max`/`xhigh` が拒否される・判定行が返らない・遮断される)**の場合**: ステップ 3・4 のコミットを `git revert`(各 1 コミット)し、ADR-001 へ「実機検証不成立」の変更履歴行(in-review)を追加して PO 裁定へ上げる。approved 正本と機構の乖離は revert により解消される
- **ステップの担当**: 文書(ADR・設計書・スキル・CLAUDE.md・agents frontmatter・settings)は Claude が直接編集する(設計書 3 章の分担: ドキュメント = Claude)。**コード(`codex_run.py`・`tests/`)は Codex へ委任**(/implement)。Claude が例外的にコードへ触れた場合は `review normal` を通す

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **ADR-001 v1.1 起案**(Claude): frontmatter `status: in-review`・変更履歴に v1.1 行(in-review・射程宣言を含む)・文脈/決定/理由/帰結を PO 確定案で書き換え(旧表は変更履歴に要約保存・見直しトリガー 2 点追加)・`docs/README.md` の ADR-001 行を in-review/1.1 へ現行化 | `uv run python scripts/check_docs_status.py` が exit 0(索引の版 = 変更履歴表の最大版)/ 決定表 7 行のモデル・effort が 4 節の PO 確定案と一致(目視)/ 旧 ID `gpt-5.6-*` が決定節に残らない(`grep` — 文脈・変更履歴の過去事実は除く) |
| 2 | **設計書 v1.18 起案**(Claude): 変更履歴に v1.18 行(in-review・射程宣言)・8.1 主セッション推奨段落の新設・8.5 実行既定の更新と定義例修正・9.4 表の同期と実機検証注記の更新・`docs/README.md` 現行化 | `check_docs_status.py` exit 0 / 8.5・9.4 の規範記述に `claude-opus-5`(5.5 でない)・`effortLevel`・`gpt-5.6-*` が残らない(`grep` — 変更履歴の過去事実は除く)/ 9.4 表の 7 行(モデル・effort)が ADR-001 v1.1 の決定表と意味一致(目視) |
| — | **/finalize-doc**(ADR-001 v1.1 + 設計書 v1.18 の単一ゲート。現行ラッパー = `gpt-5.6-sol` xhigh。反映周コミットはステップ記法なし)→ approved 化・索引現行化 | 7.3-2 の収束・PO 承認・`check_docs_status.py` exit 0 |
| 3 | **ラッパーの対応表更新 + 同期テスト・経路テスト**(Codex): `codex_run.py` の 5 定数を approved の ADR-001 v1.1 へ更新 / `tests/test_codex_run.py` に ① ADR-001 の決定表を**構造的に**読む(行の「作業」見出し → モデル・effort を抽出し、`MODEL_MAP` の 4 分類・`RESEARCH`・`RESEARCH_DEEP`・`REVIEW_NORMAL`・`REVIEW_ADVERSARIAL` との対応表で照合)同期テスト ② 負例 3 種(モデル不一致・effort 不一致・役割行の欠落を一時的な表文字列で検出)③ 経路テスト(`run_codex` を差し替え、`implement`〔重さ 4 分類〕・`fast`・`research`・`research --deep`・`review normal`・`review adversarial` の各経路が期待する `-m <model>` と `-c model_reasoning_effort=<effort>` を組み立てることを既存の fixture 方式で検証) | `uv run pytest -c pyproject.toml tests/` green・`uv run ruff check .`・`uv run ty check` green / 負例 3 種が実際に落ちることをテスト内で確認 / 定数に旧 ID `gpt-5.6-*` が残らない |
| 4 | **Claude 側設定の同期**(Claude): `.claude/agents/*.md` を `model: claude-opus-5-5`・`effort: high`(`effortLevel` 行削除)/ `CLAUDE.md:35` を「Opus 5.5・effort high」へ / `.claude/skills/{implement,research}/SKILL.md` の旧モデル名(`:50`・`:8`)を「ラッパーが ADR-001 どおりに固定」へ一般化 / `.claude/settings.json` に `model`・`modelSettings`(PO 判断③が機構化の場合)/ `tests/test_agents_frontmatter.py` を新設(3 ファイルの `model` = `claude-opus-5-5`・`effort` = `high`・`effortLevel` 不在・`tools` = Read, Grep, Glob) | `uv run pytest -c pyproject.toml tests/` green(`test_hooks.py` のフック実在検査を含む)/ `.claude`・`CLAUDE.md` に `gpt-5.6`・`claude-opus-5`(5.5 でない)・`effortLevel` の記述が変更履歴・過去事実以外で 0 件(`grep`)/ `.claude/settings.json` の `git diff` が `model`・`modelSettings` の 2 キー追加のみ(`permissions`・`hooks` 不変)/ 人間が新規セッションで `/model` の表示が `claude-opus-5-5`・effort high であることを確認し worklog に記録 |
| 5 | **実機検証と記録**(Claude): `codex_run.py review normal`(→ 新表の max)と `review adversarial`(→ xhigh)を短い依頼文(判定行の様式を指定)でスモーク実行 / 結果(版・日付・コマンド・受理・判定行・遮断の有無)を worklog に記録 / ADR-001 v1.1 の変更履歴へ「実機検証 0.157.x・受理確認」の追随行(版は上げない・7.6-3 前段)を追加し `docs/README.md` の最終更新を現行化 | 2 経路とも exit 0・**判定行あり・遮断なし** / 不成立なら「順序と差し戻し経路」の revert 手順へ / `check_docs_status.py` exit 0 |

## 5. DoD(受け入れ基準)

- [ ] 阻止条件 0(CLI 0.157.x・カタログ上の `gpt-6-sol`/`gpt-6-luna` と effort 候補)が worklog に記録され、PO 判断事項 ①〜③ が承認時に確定している
- [ ] ADR-001 v1.1 と設計書 v1.18 が**現行 approved の対応表で回した**単一の確定ゲート(/finalize-doc・7.3)を通過して approved 化され、`docs/README.md` が現行化されている
- [ ] `codex_run.py` の対応表・`.claude/agents/*.md`・`CLAUDE.md`・`implement`/`research` スキル・(機構化の場合)`.claude/settings.json` が approved の ADR-001/8.5 と同期し、同期テスト・負例・経路テスト・frontmatter テストを含むハーネスのテスト・ruff・ty が緑
- [ ] 実機検証(新 ID の max/xhigh 受理・判定行・遮断なし)と移行前ベースライン(research.md A-3)が worklog と ADR-001 文脈に残り、実測期間(3 ゲートまたは 4 週間)の記録項目と巻き戻し条件が ADR-001 帰結に書かれている

## 6. テスト計画

- **単体(ハーネス・pytest)**: ① ADR-001 決定表 ↔ `codex_run.py` 定数の**構造的**同期テスト(表の「作業」見出しをキーに抽出。字面・バイト一致に依存しない)+ 負例 3 種(モデル不一致・effort 不一致・役割行欠落)② ラッパー各経路(`implement` 4 分類・`fast`・`research`・`--deep`・`review normal`・`review adversarial`)が期待引数を組み立てる経路テスト(`run_codex` の差し替え)③ `.claude/agents/*.md` frontmatter の固定テスト ④ 既存テスト全件(`tests/` 32 ファイル)の回帰(`test_hooks.py` の settings.json フック実在検査を含む)
- **文書検査(CI docs-lint)**: `check_docs_status.py`(frontmatter 3 行・索引の版一致)・lychee(リンク)・`check_design_propagation.py`・`check_doc_coverage.py` が緑
- **設定差分(手動・ステップ 4)**: `.claude/settings.json` の差分が `model`・`modelSettings` のみ / 新規セッションでの実効 model・effort を人間が確認
- **実機(手動・ステップ 5 と確定ゲート)**: ラッパー経由の `review normal` / `review adversarial` のスモークで受理・判定行・遮断なしを確認。不成立時は「順序と差し戻し経路」の手順(安全語彙への切替・周回不算入・revert)
- **一致性・越境・E2E・故障系(NFR-019)**: 製品コードに触れないため対象外
