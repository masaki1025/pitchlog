---
feature: harness-model-refresh
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 未                  # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e793b75e68781a681aef2672934a736
branch: feature/harness-model-refresh
created: 2026-09-26
計画レビュー周回: 0        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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

1. **ADR-001 を v1.1 へ改訂**(決定内容の変更 = 版繰り上げ・7.3 確定ゲート): Codex モデル対応表を GPT-6 世代へ再設計する — 案 A(推奨): terra 枠と 5.6-sol 枠をともに **`gpt-6-sol`** へ(effort 据え置き)、`gpt-6-astra` は本版では載せない / 案 B: コア領域・敵対レビューを `gpt-6-astra` へ(PO 判断 — 4 節)
2. **設計書を v1.18 へ改訂**(単一の確定ゲートで ADR-001 と一括 — 先例 v1.15): 8.5 実行既定を `claude-opus-5-5`・`effort: high` へ(「モデルは固定のまま」の固定先を更新・`effortLevel` 併記の廃止・定義例の修正)/ 9.4 表を ADR-001 v1.1 と同期 / **8.1 に主セッション(Claude Code 本体)の推奨設定を新設**(`claude-opus-5-5`・effort high・Fable 5.1 は相談役・昇格枠)
3. **機構の同期**: `codex_run.py` の `MODEL_MAP` / `RESEARCH` / `RESEARCH_DEEP` / `REVIEW_NORMAL` / `REVIEW_ADVERSARIAL` を新表へ更新し、**ADR-001 の表 ↔ 定数の同期テスト**と **agents frontmatter の固定テスト**を新設 / `.claude/agents/*.md` frontmatter / CLAUDE.md の記述 / スキル本文の旧モデル名(implement・research・plan・pr)を「ラッパーが ADR-001 どおりに固定」へ一般化 / プロジェクト `.claude/settings.json` に主セッションの `model`・`modelSettings` を機構化(PO 判断 — 4 節)
4. **実機検証と記録**: Codex CLI 0.157.x での `gpt-6-sol` の `max`・`xhigh` 受理をラッパー経路(`review normal`・`review adversarial` のスモーク)で確認し worklog に記録する(C-7 #4)。移行前ベースライン(research.md A-3)を ADR-001 文脈へ要約転記する

### やらないこと

- 既定 3 並列の変更(H-35 で維持が対応済み — C-7 #10)/ effort 値の引き下げ(PO 指示事項 v0.8。モデル切替と別変数として移行後の計測で再判定)/ Fast・Ultra の利用(利用枠を増やす・`exec` で指定不可)
- `gpt-6-luna` の新規用途追加(機械的軽作業は 5.6-luna → 6-luna の ID 置換のみ)
- 要件書・`requirements-draft-pitchlog.md` の編集(C-5)/ `.claude/skills/finalize-doc/SKILL.md` の編集(guard_paths 該当。sol xhigh の記述は「ラッパーが ADR-001 どおり」と読めるため据え置き — C-7 #8)
- 使用量プロファイル集計の `scripts/` 化・`autoCompactWindow` の実測比較・調査前 `git fetch` の導線明文化(後続タスク候補 — research.md 末尾)
- Codex CLI の更新そのもの(開発者の環境作業。**ステップ 3 の前提**として人間が実施する — onboarding 1-6 のインストーラを再実行)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/adr/ADR-001-codex-model-selection.md` | **v1.1**: 対応表を GPT-6 世代へ再設計(案 A)・文脈(CLI 0.157.x のカタログ・料金・利用枠の重み・ベンチマーク)・理由(欠陥コスト論の GPT-6 世代への読み替え)・帰結(見直しトリガーに「astra への昇格が必要になった実例」を追加・Ultra は対話専用・Fast 不使用)・変更履歴行 | **finalize-doc**(ADR-001 v1.1 + 設計書 v1.18 を単一ゲート) |
| `docs/development/dev-harness-design-2026-08-07.md` | **v1.18**: 8.1 に主セッション推奨設定を新設 / 8.5 実行既定を `claude-opus-5-5`・`effort: high`(`effortLevel` 併記廃止・定義例修正)/ 9.4 表を ADR-001 v1.1 と同期 + 「実機検証 = 0.157.x」/ 射程宣言・変更履歴行 | **finalize-doc**(同上) |
| `docs/README.md` | ADR-001・設計書の版・状態・最終更新の現行化 | PR レビュー |
| `docs/development/harness-evaluation.md` | `/pr` クローズ処理で判断(サブスク利用上限に関する項目は台帳に無い — 初出。候補節へ「モデル世代更新の効果測定」を起票する見込み) | PR レビュー |
| 要件書・ADR-002〜004・onboarding.md・github-setup.md | **反映なし** | — |

**正本体系外だが同一 PR で更新するもの**: `.claude/scripts/codex_run.py`・`tests/test_codex_run.py`(新規テスト)・`tests/test_agents_frontmatter.py`(新規)・`.claude/agents/{spec-checker,legacy-analyst,decision-tracer}.md`・`CLAUDE.md`・`.claude/skills/{implement,research,plan,pr}/SKILL.md`・`.claude/settings.json`・`docs/features/harness-model-refresh/{plan,research}.md`・worklog

## 4. 実装方針

- **重さ分類 = 通常** の根拠: 変更対象はハーネスのラッパー定数・設定・文書であり、コア領域 5 領域(設計書 6.3)の paths にも `guard_paths` にも該当しない(research.md A-4・C-7 #8)。ただし typo 級の軽微でもない(ラッパーの機械適用値と正本 2 本の版繰り上げを伴う)
- **PO 判断事項**(承認時に明示的に確定する — 計画レビュー前の暫定値は推奨案):
  1. **Codex 対応表**: 案 A(推奨)= 全枠 `gpt-6-sol`(effort 据え置き)・`gpt-6-astra` は載せない / 案 B = コア領域・敵対レビューのみ `gpt-6-astra`(effort は low〜medium から)。根拠: 案 A は利用枠の消費が現行比 −35%(試算・research.md B-3)で、gpt-6-sol は公式に 5.6-sol を "improves substantially" と上回るため旧フロンティアの水準を保つ。案 B は消費 +97%
  2. **effort**: 据え置き(推奨)。移行後の計測で再判定
  3. **主セッションの機構化**: プロジェクト `.claude/settings.json` に `"model": "claude-opus-5-5"` と `"modelSettings": {"claude-opus-5-5": {"effortLevel": "high"}}` を置く(推奨。Opus 5.5 は既定 medium でトップレベル `effortLevel` が効かないため — research.md B-1)。セッション内の `/model` で Fable へ昇格できる
- **ADR-001 v1.1 の対応表(案 A・起案値)**:

| 作業 | モデル(明示 ID 固定) | effort |
| --- | --- | --- |
| 通常実装(CRUD・画面・帳票・テスト) | `gpt-6-sol` | max |
| 軽微な修正(小さな差分・微調整) | `gpt-6-sol` | medium |
| コア領域の実装(6.3 のリスト) | `gpt-6-sol` | xhigh |
| 機械的軽作業(リネーム・ボイラープレート) | `gpt-6-luna` | xhigh |
| 一次コードレビュー(通常 PR) | `gpt-6-sol` | max |
| 敵対レビュー・コア領域 PR・正本確定ゲート | `gpt-6-sol` | xhigh |
| Web 調査(/research) | `gpt-6-sol` | high(`--deep` は xhigh) |

  - 通常枠とコア枠が同一モデルになるため、水準差は **effort(max / xhigh)と依頼文(6.3 の敵対姿勢・7.3-5 の規約)**で保つ。ADR-001 理由 1「コア領域と品質ゲートにフロンティア級」は「**旧フロンティア(5.6-sol)以上の水準**」と読み替え、astra への昇格を見直しトリガーに置く
- **設計書 8.5 の実行既定(起案値)**: `model: claude-opus-5-5`(明示 ID・エイリアス禁止は維持)・`effort: high`(Opus 5.5 の既定は medium なので明示必須)・`effortLevel` は**公式 frontmatter リファレンスに存在しないキー**として併記を廃止(C-6 — P1-6 の原典は不明のため「公式仕様の確定」を新典拠として記録)
- **8.1 の新設段落(起案値)**: 主セッションは `claude-opus-5-5`・effort high を既定とし、Fable 5.1 は「Opus 5.5 high で足りない長期自律作業・相談役」に限定(Max の週次上限 50% 枠 — research.md B-1)。Fast mode は使わない(プラン枠でなく usage credits を消費)
- **ステップの担当**: 文書(ADR・設計書・スキル・CLAUDE.md・agents frontmatter・settings)は Claude が直接編集する(設計書 3 章の分担: ドキュメント = Claude)。**コード(`codex_run.py`・`tests/`)は Codex へ委任**(/implement)。Claude が例外的にコードへ触れた場合は `review normal` を通す
- **順序の意図**: 正本の起案(ステップ 1・2 = in-review)→ 機構の同期(3・4)→ 実機検証(5)→ **確定ゲート(/finalize-doc)は新対応表のラッパーで回す**(= 敵対レビュー自体が `gpt-6-sol xhigh` の実機検証を兼ねる — C-7 #4)。**ステップ 3 の前に人間が Codex CLI を 0.157.x へ更新する**(GPT-6 Sol の `minimal_client_version` = 0.155.0)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **ADR-001 v1.1 起案**(Claude): frontmatter `status: in-review`・変更履歴に v1.1 行(in-review・射程宣言を含む)・文脈/決定/理由/帰結を案 A で書き換え(旧表は変更履歴に要約保存)・`docs/README.md:16` を in-review/1.1 へ現行化 | `uv run python scripts/check_docs_status.py` が exit 0(索引の版 = 変更履歴表の最大版)/ 旧 ID `gpt-5.6-*` が決定表に残らない(`grep`)/ 対応表の 7 行が 4 節の起案値と一致 |
| 2 | **設計書 v1.18 起案**(Claude): 変更履歴に v1.18 行(in-review・射程宣言)・8.1 主セッション推奨段落の新設・8.5 実行既定の更新と定義例修正・9.4 表の同期と実機検証注記の更新・`docs/README.md` 現行化 | `check_docs_status.py` exit 0 / 8.5・9.4 に `claude-opus-5`(5.5 でない)・`effortLevel`・`gpt-5.6-*` の規範記述が残らない(`grep` — 変更履歴の過去事実は除く)/ 9.4 表が ADR-001 v1.1 の表とバイト一致 |
| 3 | **ラッパーの対応表更新 + 同期テスト**(Codex): `codex_run.py` の `MODEL_MAP`・`RESEARCH`・`RESEARCH_DEEP`・`REVIEW_NORMAL`・`REVIEW_ADVERSARIAL` を ADR-001 v1.1 の表へ更新 / `tests/test_codex_run.py` に「ADR-001 の決定表(Markdown)を読み、モデル ID と effort が定数と一致する」テストを追加(表の行見出し → 定数の対応を固定)/ 旧 ID を含む定数が無いことの負例 | `uv run pytest -c pyproject.toml tests/` green・`uv run ruff check .`・`uv run ty check` green / 新テストが ADR の表を書き換えると落ちることを一時変更で確認(worklog に記録) |
| 4 | **Claude 側設定の同期**(Claude): `.claude/agents/*.md` を `model: claude-opus-5-5`・`effort: high`(`effortLevel` 行削除)/ `CLAUDE.md:35` を「Opus 5.5・effort high」へ / `.claude/skills/{implement,research,plan,pr}/SKILL.md` の旧モデル名を「ラッパーが ADR-001 どおりに固定」へ一般化 / `.claude/settings.json` に `model`・`modelSettings`(PO 判断③が可の場合)/ `tests/test_agents_frontmatter.py` を新設(3 ファイルの `model`・`effort` が設計書 8.5 の既定値と一致・`effortLevel` 不在・`tools` が Read/Grep/Glob のまま) | `uv run pytest -c pyproject.toml tests/` green / `grep -rn "gpt-5.6\|claude-opus-5[^-]\|effortLevel" .claude CLAUDE.md` が変更履歴・過去事実以外で 0 件 / `.claude/settings.json` が JSON として妥当 |
| 5 | **実機検証と記録**(Claude): CLI 更新後のカタログ(`~/.codex/models_cache.json`)で `gpt-6-sol`・`gpt-6-luna` と effort 候補を確認 / `codex_run.py review normal`(max)と `review adversarial`(xhigh)を短い依頼文でスモーク実行し受理を確認 / 結果と移行前ベースライン(research.md A-3)を worklog に記録し、ADR-001 v1.1 の文脈へ「実機検証 0.157.x」を追記 | 2 経路とも exit 0 で判定行を返す / worklog に版・日付・コマンド・結果が残る / ADR-001 の文脈に実機検証の版が書かれている |

## 5. DoD(受け入れ基準)

- [ ] ADR-001 v1.1 と設計書 v1.18 が単一の確定ゲート(/finalize-doc・7.3)を通過して approved 化され、`docs/README.md` が現行化されている
- [ ] `codex_run.py` の対応表・`.claude/agents/*.md`・`CLAUDE.md`・スキル本文が改訂後の ADR-001/8.5 と同期し、同期テスト 2 本を含むハーネスのテスト・ruff・ty が緑
- [ ] 移行前のトークン消費ベースライン(research.md A-3)と、主セッション/サブエージェント/Codex の推奨構成が正本(ADR-001 文脈・設計書 8.1/8.5/9.4)に記録され、実機検証(0.157.x・`gpt-6-sol` の max/xhigh 受理)が worklog に残っている

## 6. テスト計画

- **単体(ハーネス・pytest)**: ① ADR-001 の決定表 ↔ `codex_run.py` の定数の同期テスト(正例: 現行表と一致 / 負例: 表の 1 セルを変えた一時コピーで不一致を検出)② `.claude/agents/*.md` frontmatter の固定テスト(`model` = `claude-opus-5-5`・`effort` = `high`・`effortLevel` 不在・`tools` = Read, Grep, Glob)③ 既存テスト全件(`tests/` 32 ファイル)の回帰
- **文書検査(CI docs-lint)**: `check_docs_status.py`(frontmatter 3 行・索引の版一致)・lychee(リンク)・`check_design_propagation.py`・`check_doc_coverage.py` が緑
- **実機(手動・ステップ 5)**: ラッパー経由の `review normal`(gpt-6-sol max)/ `review adversarial`(gpt-6-sol xhigh)のスモークで受理と判定行を確認。確定ゲート本番でも安全分類器の遮断有無を観測(research.md 末尾)
- **一致性・越境・E2E・故障系(NFR-019)**: 製品コードに触れないため対象外
