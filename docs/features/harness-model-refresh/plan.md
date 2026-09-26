---
feature: harness-model-refresh
status: active            # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出。codex_run.py implement は active 以外を拒否)
承認: 済(2026-09-27・徳光 尋弥)   # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3e793b75e68781a681aef2672934a736
branch: feature/harness-model-refresh
created: 2026-09-26
計画レビュー周回: 4        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
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

1. **ADR-001 v1.1 と設計書 v1.18 を単一コミットで起案**(確定ゲート開始 — 2 正本の `in-review` 化・索引・適用版の worklog 記録を同一コミットに置く: `.claude/skills/finalize-doc/SKILL.md` 手順 1): ADR-001 = Codex モデル対応表を GPT-6 世代へ再設計(案 A / 案 B を 4 節に **8 行すべて**定義し PO 判断で 1 案に確定) / 設計書 = 8.5 実行既定を `claude-opus-5-5`・`effort: high` へ(「モデルは固定のまま」の固定先を更新・`effortLevel` 併記の廃止・定義例の修正)・9.4 表の同期・**8.1 に主セッション(Claude Code 本体)の推奨設定を新設**・**変更履歴表を除く全節の現行モデル記述(6.1・8.1・8.4・9.2・9.4 の terra / Opus 5 / `gpt-5.6` エイリアス注記)を ADR-001 参照または新値へ同期**
2. **確定ゲート(/finalize-doc)を、現行 approved の対応表(`gpt-5.6-sol` xhigh・ラッパー未変更)で完了する**。approved 化の前に機構(ラッパー・agents・settings)へは触れない
3. **approved 化後に機構を同期**(文書・設定は Claude、コードとテストは Codex): `.claude/agents/*.md` / `CLAUDE.md`(`:30` の「実装は sol xhigh」・`:35` の「Opus 5・effort high 固定」)/ スキル本文の旧モデル名(`implement:50`・`research:8`)を「ラッパーが ADR-001 どおりに固定」へ一般化 / プロジェクト `.claude/settings.json` に主セッションの `model`・`modelSettings`(PO 判断③が可の場合)→ その後 `codex_run.py` の定数(`MODEL_MAP` / `RESEARCH` / `RESEARCH_DEEP` / `REVIEW_NORMAL` / `REVIEW_ADVERSARIAL`)を新表へ / **ADR-001 の決定表 ↔ 定数の構造的同期テスト**(固定構文 — 4 節)・**ラッパー各経路の引数テスト**・**agents frontmatter の固定テスト**を新設
4. **実機検証と記録**: ラッパー経路(`review normal`・`review adversarial`)のスモークで、選択案から導出した `(model, effort)` の受理と判定行の返却を確認し worklog に記録。ADR-001 の変更履歴へ実機検証の**版を上げない追随行**を追記(7.6-3 前段 — 決定内容は変えない)。不成立なら同じステップの中で巻き戻す(4 節「順序と差し戻し経路」)

### やらないこと

- 既定 3 並列の変更(H-35 で維持が対応済み — research.md C-7 #10)/ effort 値の引き下げ(PO 指示事項 v0.8。モデル切替と別変数として移行後の計測で再判定 — 4 節の実測期間)/ Fast・Ultra の利用(利用枠を増やす・`exec` で指定不可)
- `gpt-6-luna` の新規用途追加(機械的軽作業は 5.6-luna → 6-luna の ID 置換のみ)
- 要件書・`requirements-draft-pitchlog.md` の編集(C-5)
- **guard_paths に該当するスキルの編集**: `.claude/skills/pr/SKILL.md`(guard_paths — モデル名を含まないため変更不要。`plan/SKILL.md` は guard_paths ではないが、同じくモデル名を含まないため変更不要)。`.claude/skills/finalize-doc/SKILL.md:15` の「ADR-001 どおり sol xhigh」は、**案 A では `gpt-6-sol` xhigh となり字義どおり整合するため触らない**(古い括弧書きの精密化は次に guard_paths を触る PR へ送る)。**案 B を採る場合のみ対象に戻し**、guard_paths として人間の逐行確認・PR の実施記録行を付ける(4 節の導出表)
- **実装(コーディング)の Claude 側(Opus 5.5)への移管 — 別タスク**(PO 合意 2026-09-27): 品質面では Opus 5.5 で足りる(公式値 Terminal-Bench 4.0 66.4%・FrontierCode v1.1 54.4% — research.md B-1)が、① Codex は ChatGPT 側・Claude Code は Max 側と**利用枠が別財布**で、実装まで Max 枠へ寄せると本タスクの目的(上限内で長く働く)に反する ② 計画書ゲートの機械検証(承認・status・worktree・sandbox)は `codex_run.py implement` 側にあり、Claude 直実装を既定にするには Edit/Write への計画ゲートのフック新設が先 ③ 設計書 3 章・6.1・6.3・ADR-001 の役割分担の改訂を伴う。**当面は現行の例外経路(Claude 直実装 → `codex_run.py review normal` 必須 — CLAUDE.md)を Opus 5.5 で使う**(Codex の強制終了時・小さな修正)。既定化の判断は Opus 5.5 化後の Max 枠の実測(4 節の実測期間)を見てから
- 使用量プロファイル集計の `scripts/` 化・`autoCompactWindow` の実測比較・調査前 `git fetch` の導線明文化(後続タスク候補 — research.md 末尾)
- Codex CLI の更新そのもの(開発者の環境作業。**阻止条件 0** として人間が実施する — onboarding 1-6 のインストーラを再実行)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/adr/ADR-001-codex-model-selection.md` | **v1.1**: 決定表を固定構文(4 節)の 8 行で GPT-6 世代へ再設計(PO 確定案)・文脈(CLI 0.157.x のカタログ・料金・利用枠の重み〔代理指標〕・ベンチマーク〔未照合分は明示〕・移行前ベースライン)・理由(欠陥コスト論の GPT-6 世代への読み替え)・帰結(見直しトリガーに「実測期間終了時の再判定」「品質下限の巻き戻し条件」を追加・Ultra は対話専用・Fast 不使用・決定表の固定構文をテストが読む旨)・変更履歴行。approved 化後、ステップ 4 で実機検証の追随行(版は上げない) | **finalize-doc**(ADR-001 v1.1 + 設計書 v1.18 を単一ゲート)+ 追随行は PR レビュー |
| `docs/development/dev-harness-design-2026-08-07.md` | **v1.18**: 8.1 に主セッション推奨設定を新設・8.1 `:662` の「Opus 5 固定」を更新 / 8.5 実行既定を `claude-opus-5-5`・`effort: high`(`effortLevel` 併記廃止・定義例 `:744` 修正)/ 9.4 表を ADR-001 v1.1 と同期 + 「実機検証 = 0.157.x」+ `:826` のエイリアス注記を GPT-6 世代へ / 6.1 `:322`・9.2 `:792` の「terra medium」・8.4 `:704` の「terra high」を「ADR-001 の該当行」参照へ / 射程宣言・変更履歴行 | **finalize-doc**(同上) |
| `docs/README.md` | ADR-001・設計書の版・状態・最終更新の現行化(起案時 in-review・承認時 approved・追随行の 3 回) | PR レビュー |
| `docs/development/harness-evaluation.md` | **反映なし**(現時点)。`/pr` クローズ処理で台帳追記に該当すると判断した場合は、**先に本表へ宣言を追記してから**反映する(`.claude/skills/pr/SKILL.md` 1-3)。該当しなければ worklog に「台帳への追記なし」と理由を残す | — |
| 要件書・ADR-002〜004・onboarding.md・github-setup.md・`.claude/skills/{pr,plan}/SKILL.md` | **反映なし** | — |
| `.claude/skills/finalize-doc/SKILL.md` | **案 A: 反映なし / 案 B: `:15` の括弧書きを新値へ**(guard_paths — 逐行確認・実施記録行) | 案 B のとき PR レビュー + 逐行確認 |

**正本体系外だが同一 PR で更新するもの**: `.claude/scripts/codex_run.py`・`tests/test_codex_run.py`(同期テスト・経路テストの追加)・`tests/test_agents_frontmatter.py`(新規)・`.claude/agents/{spec-checker,legacy-analyst,decision-tracer}.md`・`CLAUDE.md`(`:30`・`:35`)・`.claude/skills/{implement,research}/SKILL.md`・`.claude/settings.json`(PO 判断③が可の場合のみ)・`docs/features/harness-model-refresh/{plan,research}.md`・worklog

## 4. 実装方針

- **重さ分類 = 通常** の根拠: 変更対象はハーネスのラッパー定数・設定・文書であり、コア領域 5 領域(設計書 6.3)の paths にも `guard_paths` にも該当しない(research.md A-4・C-7 #8。guard_paths に該当する `pr` の SKILL.md は触らず、`finalize-doc` は案 B のときだけ逐行確認付きで触る — 2 節)。ただし typo 級の軽微でもない(ラッパーの機械適用値と正本 2 本の版繰り上げを伴う)

### 阻止条件 0(コミットなし — ステップ 1 の前に人間 + Claude で確認)

1. 人間が Codex CLI を **0.157.x 以上**へ更新する(GPT-6 Sol/Luna の `minimal_client_version` = 0.155.0・カタログ追加は 0.157.0 — research.md B-3)
2. Claude が `~/.codex/models_cache.json`(更新後に再取得されたもの)で、**PO が選択した案の導出表(下記)に含まれる全 `(model, effort)`** について slug の存在と `supported_reasoning_levels` への effort の包含を確認し、版・fetched_at とともに worklog へ記録する
3. **1 組でも確認できなければ対応表を書き換えず停止**し(ステップ 1 にも進まない)、PO へ報告する(ロールアウト条件・ワークスペース条件で提供されない可能性があるため)

### 選択案 → 検証・スモーク・巻き戻しの導出表

| 選択案 | 阻止条件 0 で確認する `(model, effort)` | ステップ 4 のスモーク期待値(選択後の定数) | スモーク不成立の継続判断 | 追加で対象に入るファイル |
| --- | --- | --- | --- | --- |
| 案 A | `gpt-6-sol` × {medium, high, xhigh, max}・`gpt-6-luna` × {xhigh} | `REVIEW_NORMAL` = (`gpt-6-sol`, max)/ `REVIEW_ADVERSARIAL` = (`gpt-6-sol`, xhigh) | 対応表を変えるなら **ADR-001 v1.2**(astra 昇格を含む)を起案し新規の確定ゲート | なし |
| 案 B | 案 A の集合 + `gpt-6-astra` × {medium} | `REVIEW_NORMAL` = (`gpt-6-sol`, max)/ `REVIEW_ADVERSARIAL` = (`gpt-6-astra`, medium) | **PO 再裁定**(sol xhigh へ戻す / astra の effort 変更 等)→ ADR-001 v1.2 + 新規の確定ゲート | `.claude/skills/finalize-doc/SKILL.md:15`(guard_paths — 逐行確認・実施記録行) |

### PO 判断事項(**確定 2026-09-27・徳光 尋弥: ① 案 A ② effort 据え置き ③ 機構化する** — 以下は判断材料として保存)

**① Codex 対応表**(2 案とも 8 行すべてを定義。推奨 = 案 A。行キーは下記「決定表の固定構文」と一致させる):

| 作業(行キー) | 現行(ADR-001 v1.0) | 案 A(推奨): gpt-6-sol 一本化 | 案 B: コア・敵対 = astra |
| --- | --- | --- | --- |
| 通常実装 | `gpt-5.6-terra` max | `gpt-6-sol` max | `gpt-6-sol` max |
| 軽微な修正 | `gpt-5.6-terra` medium | `gpt-6-sol` medium | `gpt-6-sol` medium |
| コア領域の実装 | `gpt-5.6-sol` xhigh | `gpt-6-sol` xhigh | `gpt-6-astra` medium |
| 機械的軽作業 | `gpt-5.6-luna` xhigh | `gpt-6-luna` xhigh | `gpt-6-luna` xhigh |
| 一次コードレビュー | `gpt-5.6-terra` max | `gpt-6-sol` max | `gpt-6-sol` max |
| 敵対レビュー・コア領域 PR・正本確定ゲート | `gpt-5.6-sol` xhigh | `gpt-6-sol` xhigh | `gpt-6-astra` medium |
| Web 調査 | `gpt-5.6-terra` high | `gpt-6-sol` high | `gpt-6-sol` high |
| Web 調査(深い技術検証 `--deep`) | `gpt-5.6-sol` xhigh | `gpt-6-sol` xhigh | `gpt-6-astra` medium |

  - **根拠(案 A を推奨する理由)**: gpt-6-sol は 5.6-sol の後継 tier で API 単価が半額(✔ 照合済み — research.md B-2)。公式発表は "improves substantially over GPT-5.6 Sol"(FrontierCode)・"higher usage limits and lower cost" と述べる(**未照合** — Codex の原文引用。B-3)。利用枠の試算(現行比 **−35%** / 案 B **+97%**)は **Business/Enterprise の credit rate card を代理指標にしたもの**で、Plus/Pro の係数は非公開(B-3)。したがって推奨の根拠は「単価半額(照合済み)+ 旧フロンティア以上との公式声明(未照合)」であり、**品質の同等性は移行後の実測で確認する**(下記の品質下限・実測期間)
  - **案 B の位置づけ**: 上位の品質を買う代わりに Codex 側の消費が倍増する試算。effort は "Astra at Low effort can outperform Sol at High effort"(未照合)に基づき medium から始める。案 B を採る場合も通常枠は案 A と同じ
  - **品質下限・実測期間・巻き戻し条件**(PO 判断①の一部として固定): 移行後 **3 回の確定ゲート(または 4 週間)** を実測期間とし、各ゲートの周回数・P0/P1 検出数・遮断有無を worklog と台帳候補に記録する。**巻き戻し条件** = (a) 選択案の `(model, effort)` が受理されない (b) 安全分類器の遮断が 5.6-sol 時代(台帳 :20 — 1 ゲートで flagged 2 回)より増える (c) 実測期間中に「敵対レビューが計画レビュー通過後の P0 を検出できなかった」実例が出る。いずれかで **ADR-001 v1.2 を起案し新規の確定ゲート**で対応表を再改訂する(案 A なら astra 昇格を含む案・案 B なら PO 再裁定 — 導出表)。H-30 は「モデル差だけの効果とは切り分けられない」としているため、品質下限の判定は周回数でなく**検出実例の有無**で行う

**② effort**: 据え置き(推奨)。出力トークンは Codex 側消費の 3 割程度で、モデル切替と別変数として実測期間の終了時に再判定する

**③ 主セッションの機構化**(推奨 = 機構化): プロジェクト `.claude/settings.json` に `"model": "claude-opus-5-5"` と `"modelSettings": {"claude-opus-5-5": {"effortLevel": "high"}}` を追加する
  - **適用対象**: 本リポジトリを開く**全開発者の新規セッション**(共有設定 — 設計書 8.1。`~/.claude/settings.json` の `"model": "fable[1m]"` より優先される)
  - **上書き手段**: セッション内 `/model`(Fable への昇格・相談役)/ `.claude/settings.local.json`(個人の恒久上書き・gitignore 済み)
  - **effort = high の根拠**: Opus 5.5 の既定は medium で、トップレベル `effortLevel` は Opus 5.5 に効かない(✔ B-1)。現行の主セッションは Fable xhigh で運用しており、まず **high** で品質の連続性を取り、medium への引き下げは実測期間の後に判定する(Codex の推奨は medium — B-1)。**`modelSettings` 内の `effortLevel` キーは Claude Code の settings.json の正式な形**であり、agents frontmatter で廃止する `effortLevel` とは別物(前者は残す)
  - **副作用の統制**: `permissions`・`hooks` ブロックは**差分不変**(ステップ 2 の合格条件で `git diff` が `model`・`modelSettings` の 2 キー追加のみであることを確認)。`tests/test_hooks.py` のフック実在検査が引き続き緑
  - **機構化しない場合**: 8.1 の推奨記述のみとし、`.claude/settings.json` は触らない(3 節の宣言から外す)

### ADR-001 v1.1 の決定表の固定構文(同期テストが読む — ステップ 1・3 で共有)

- 位置: `## 決定` 見出しの直下にある最初の Markdown 表。ヘッダ行は `| 作業 | モデル(明示 ID 固定) | effort |` に固定
- 行: **ちょうど 8 行**。「作業」セルは上表の行キー 8 個と**完全一致**(括弧内の補足はテンプレの説明として本文側に置き、セルには含めない)。「モデル」セルは **code span ちょうど 1 個**(中身がモデル ID)。「effort」セルは `low` / `medium` / `high` / `xhigh` / `max` の**トークン 1 個**(太字・注記なし。注記は表の下の箇条書きへ)
- 行キー → ラッパー定数の対応: 通常実装 → `MODEL_MAP["通常"]` / 軽微な修正 → `MODEL_MAP["軽微"]` / コア領域の実装 → `MODEL_MAP["コア領域"]` / 機械的軽作業 → `MODEL_MAP["機械的軽作業"]` / 一次コードレビュー → `REVIEW_NORMAL` / 敵対レビュー・コア領域 PR・正本確定ゲート → `REVIEW_ADVERSARIAL` / Web 調査 → `RESEARCH` / Web 調査(深い技術検証 `--deep`) → `RESEARCH_DEEP`
- 設計書 9.4 は同じ 8 行を再掲する(意味一致を目視で確認。テストは ADR-001 のみを読む)

### 旧記述の残存検査(ステップ 1・2 の合格条件で使う正規表現 — パス別)

| 対象 | 残ってはいけないもの(`grep -P`) | 許容するもの |
| --- | --- | --- |
| 設計書(変更履歴表の版行 `^\| \*{0,2}\d+\.\d+` を除く全文) | `gpt-5\.6`・`\bterra\b`・`claude-opus-5(?!-5)`・`Opus 5(?![.\d])`・`effortLevel`(**8.1 の主セッション既定にある settings.json の `modelSettings.*.effortLevel` の 1 箇所は除く** — settings の正式キー。ステップ 1 で明確化) | `gpt-6-luna`(機械的軽作業行)・`gpt-6-sol`・`gpt-6-astra`・`claude-opus-5-5`・「Opus 5.5」・8.1 の settings.json 記述 |
| ADR-001 の決定節(`## 決定` 〜 次の `## `) | `gpt-5\.6` | 文脈・変更履歴に残す過去事実(`gpt-5.6-*` の旧表要約・旧単価) |
| `.claude/agents/*.md` | `effortLevel`・`claude-opus-5(?!-5)` | `effort: high` |
| `CLAUDE.md` | `gpt-5\.6`・`sol xhigh`・`Opus 5(?![.\d])` | 「Opus 5.5」・「ADR-001 の該当行」参照 |
| `.claude/skills/{implement,research}/SKILL.md` | `\bterra\b`・`sol xhigh`・`gpt-5\.6` | — |
| `.claude/skills/finalize-doc/SKILL.md` | (案 A: 検査対象外 — 触らない)/(案 B: `sol xhigh`) | 案 A の `sol xhigh`(gpt-6-sol xhigh と整合) |
| `.claude/settings.json` | `git diff` に `model`・`modelSettings` 以外のキー変更 | `modelSettings.claude-opus-5-5.effortLevel`(正式な形) |

### 起案値(PO 判断①を案 A・③を機構化とした場合)

- **ADR-001 v1.1**: 上表の案 A 列を固定構文で記す。通常枠とコア枠が同一モデルになるため、水準差は **effort(max / xhigh)と依頼文(6.3 の敵対姿勢・7.3-5 の規約)**で保つ。ADR-001 理由 1「コア領域と品質ゲートにフロンティア級」は「**旧フロンティア(5.6-sol)以上の水準**」と読み替え、astra への昇格を見直しトリガーに置く。文脈には移行前ベースライン(research.md A-3 の要約)と代理指標の限界を書く
- **設計書 8.5 の実行既定**: `model: claude-opus-5-5`(明示 ID・エイリアス禁止は維持)・`effort: high`(Opus 5.5 の既定は medium なので明示必須)・`effortLevel` は**公式 frontmatter リファレンスに存在しないキー**として併記を廃止(C-6 — P1-6 の原典は不明のため「公式仕様の確定(✔ B-1)」を新典拠として記録)。定義例(`:744`)も同期
- **8.1 の新設段落**: 主セッションは `claude-opus-5-5`・effort high を既定とし、Fable 5.1 は「Opus 5.5 high で足りない長期自律作業・相談役」に限定(Max の週次上限 50% 枠 — ✔ B-1)。Fast mode は使わない(プラン枠でなく usage credits を消費)。`:662` の「Opus 5 固定」は「Opus 5.5 固定」へ
- **他節の同期**: 6.1 `:322`・9.2 `:792` の「terra medium 固定」→「ADR-001 の『軽微な修正』行のモデル・effort をラッパーが固定」/ 8.4 `:704` の「terra high」→「ADR-001 の『Web 調査』行」/ 9.4 `:826` の「エイリアス(`gpt-5.6` = sol 行き)」→ GPT-6 世代のエイリアス(`gpt-6` 等)を使わない旨へ

### 順序と差し戻し経路

- **順序**: 阻止条件 0 → ステップ 1(2 正本を**単一コミット**で `in-review` 起案 + 索引 + 適用版の worklog 暫定記録)→ **/finalize-doc(現行 approved の対応表 = `gpt-5.6-sol` xhigh・ラッパー未変更で実施。7.3-1 の適用版原則と ADR-001 帰結「本表どおり自動指定」に従う)** → approved 化(索引現行化)→ ステップ 2(Claude: 設定・文書の同期)→ ステップ 3(Codex: ラッパー + テスト)→ ステップ 4(実機検証)→ /sync-docs → /pr。**確定ゲートの反映周コミットにはステップ記法を付けない**(設計書 6.1)
- **確定ゲート中の安全分類器の遮断**(台帳 H-75・:20): 判定行のない応答は周として数えず同一周を再依頼する(7.3-5)。再依頼は依頼文を「所在・理由・修正案の 3 点」形式の安全語彙へ切り替える
- **ステップ 4 のスモークが不成立の場合(ステップ 4 の条件付き結果として 1 コミットにまとめる)**: ① 遮断・判定行なしなら、同一経路を安全語彙の依頼文で **1 回だけ再実行**する(両試行を worklog に記録)② 再実行も不成立、または選択案の `(model, effort)` が拒否された場合は、ステップ 2・3 の変更を `git revert --no-commit` で作業ツリーへ戻し、worklog の記録と合わせて **`(ステップ 4/4 不成立・巻き戻し)` の 1 コミット**にする(無記法の revert コミットを作らない — `feature_status.py` が実装コミットとして誤分類し「不明」へ縮退するため)。**本 PR は停止(develop へ統合しない)**し PO へ報告する。approved の ADR-001 v1.1 には**追記しない**(現在状態の正は frontmatter のみ — 設計書 7.1-5。決定内容を変える継続判断は導出表のとおり **ADR-001 v1.2 + 新規の確定ゲート**)
- **ステップの担当**: 文書(ADR・設計書・スキル・CLAUDE.md・agents frontmatter・settings.json)は Claude が直接編集する(設計書 3 章の分担: ドキュメント = Claude)。**コードとテスト(`codex_run.py`・`tests/`)はすべて Codex へ委任**(/implement・ステップ 3)。Claude はコードに触れない(触れた場合は `review normal` を通す — CLAUDE.md)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | **ADR-001 v1.1 + 設計書 v1.18 の起案(単一コミット = 確定ゲート開始)**(Claude): ADR-001 = frontmatter `status: in-review`・変更履歴 v1.1 行(in-review・射程宣言)・決定表を固定構文の 8 行で PO 確定案に書き換え・文脈/理由/帰結の更新(旧表は変更履歴に要約保存)/ 設計書 = frontmatter `status: in-review`・変更履歴 v1.18 行(in-review・射程宣言)・8.1 新設段落と `:662`・8.5 実行既定と定義例・9.4 表と `:826`・6.1 `:322`・8.4 `:704`・9.2 `:792` の同期 / `docs/README.md` の 2 行を in-review へ / worklog に **適用版(7.3 の版数 + 条文コミット SHA)の暫定記録** | `uv run python scripts/check_docs_status.py` exit 0 / ADR-001 の決定表が固定構文(ヘッダ・8 行キー・code span 1 個・effort トークン 1 個)を満たす(目視)/ 「旧記述の残存検査」表の設計書・ADR-001 の行が 0 件 / 9.4 表の 8 行が ADR-001 の決定表と意味一致(目視)/ 単一コミットに 2 正本・索引・worklog が含まれる(`git show --stat`) |
| — | **/finalize-doc**(ADR-001 v1.1 + 設計書 v1.18 の単一ゲート。現行ラッパー = `gpt-5.6-sol` xhigh。反映周コミットはステップ記法なし)→ approved 化・索引現行化 | 7.3-2 の収束・PO 承認・`check_docs_status.py` exit 0 |
| 2 | **Claude 側設定・文書の同期**(Claude — コードには触れない): `.claude/agents/*.md` を `model: claude-opus-5-5`・`effort: high`(`effortLevel` 行削除)/ `CLAUDE.md:30` の「実装は sol xhigh」を「ADR-001 の『コア領域の実装』行のモデル・effort」参照へ・`:35` を「Opus 5.5・effort high」へ / `.claude/skills/{implement,research}/SKILL.md` の旧モデル名(`:50`・`:8`)を「ラッパーが ADR-001 どおりに固定」へ一般化(案 B なら `finalize-doc/SKILL.md:15` も — 逐行確認)/ `.claude/settings.json` に `model`・`modelSettings`(PO 判断③が機構化の場合) | 「旧記述の残存検査」表の agents・CLAUDE.md・skills・settings.json の行がすべて満たされる / `uv run pytest -c pyproject.toml tests/` green(既存テストのみ — `test_hooks.py` のフック実在検査を含む)/ 人間が新規セッションで `/model` の表示が `claude-opus-5-5`・effort high であることを確認し worklog に記録 |
| 3 | **ラッパーの対応表更新 + テスト 3 群**(Codex): `codex_run.py` の 5 定数を approved の ADR-001 v1.1 へ更新 / `tests/test_codex_run.py` に ① 固定構文で ADR-001 の決定表を読み(`## 決定` 直下の最初の表・ヘッダ固定・8 行キー・code span 1 個・effort トークン 1 個)、行キー → 定数の対応表で `(model, effort)` を照合する同期テスト ② 負例 4 種(モデル不一致・effort 不一致・行キー欠落・構文違反〔code span 2 個 / 未知の effort トークン〕を一時的な表文字列で検出)③ 経路テスト(`run_codex` を差し替え、`implement`〔重さ 4 分類〕・`fast`・`research`・`research --deep`・`review normal`・`review adversarial` の各経路が期待する `-m <model>` と `-c model_reasoning_effort=<effort>` を組み立てることを既存の fixture 方式で検証)/ `tests/test_agents_frontmatter.py` を新設(3 ファイルの `model` = `claude-opus-5-5`・`effort` = `high`・`effortLevel` 不在・`tools` = Read, Grep, Glob — ステップ 2 の状態を固定) | `uv run pytest -c pyproject.toml tests/` green・`uv run ruff check .`・`uv run ty check` green / 負例 4 種が実際に落ちることをテスト内で確認 / 定数に旧 ID `gpt-5.6-*` が残らない(`grep -P 'gpt-5\.6' .claude/scripts/codex_run.py` = 0) |
| 4 | **実機検証と記録**(Claude): `codex_run.py review normal` と `review adversarial` を短い依頼文(判定行の様式を指定)でスモーク実行し、導出表の期待値(選択案の `REVIEW_NORMAL` / `REVIEW_ADVERSARIAL`)で受理されることを確認 / 遮断・判定行なしなら安全語彙で 1 回だけ再実行 / 結果(版・日付・コマンド・受理・判定行・遮断の有無・再実行の有無)を worklog に記録 / 成立時: ADR-001 v1.1 の変更履歴へ「実機検証 0.157.x・受理確認」の追随行(版は上げない・7.6-3 前段・frontmatter は approved のまま)を追加し `docs/README.md` の最終更新を現行化 / **不成立時: 「順序と差し戻し経路」のとおり revert を含めて同じステップの 1 コミット `(ステップ 4/4 不成立・巻き戻し)` にし PR を停止** | 成立: 2 経路とも exit 0・**判定行あり・遮断なし**(再実行を含めて可)・`check_docs_status.py` exit 0 / 不成立: revert 後に `uv run pytest -c pyproject.toml tests/` green(旧状態へ戻っている)・worklog に両試行の記録・PO への報告 |

## 5. DoD(受け入れ基準)

- [ ] 阻止条件 0(CLI 0.157.x・選択案の全 `(model, effort)` のカタログ確認)が worklog に記録され、PO 判断事項 ①〜③ が承認時に確定している
- [ ] ADR-001 v1.1 と設計書 v1.18 が**単一コミットで開始し、現行 approved の対応表で回した**単一の確定ゲート(/finalize-doc・7.3)を通過して approved 化され、`docs/README.md` が現行化されている
- [ ] `codex_run.py` の対応表・`.claude/agents/*.md`・`CLAUDE.md`・`implement`/`research` スキル・(機構化の場合)`.claude/settings.json` が approved の ADR-001/8.5 と同期し、固定構文の同期テスト・負例・経路テスト・frontmatter テストを含むハーネスのテスト・ruff・ty が緑
- [ ] 実機検証(選択案の `(model, effort)` の受理・判定行・遮断なし)と移行前ベースライン(research.md A-3)が worklog と ADR-001 文脈に残り、実測期間(3 ゲートまたは 4 週間)の記録項目と巻き戻し条件が ADR-001 帰結に書かれている

## 6. テスト計画

- **単体(ハーネス・pytest — すべて Codex がステップ 3 で追加)**: ① ADR-001 決定表 ↔ `codex_run.py` 定数の同期テスト(4 節の固定構文で抽出。字面・バイト一致に依存しない)+ 負例 4 種(モデル不一致・effort 不一致・行キー欠落・構文違反)② ラッパー各経路(`implement` 4 分類・`fast`・`research`・`--deep`・`review normal`・`review adversarial`)が期待引数を組み立てる経路テスト(`run_codex` の差し替え)③ `.claude/agents/*.md` frontmatter の固定テスト ④ `tests/` 全件の回帰(件数は CI の harness ジョブの実行結果を正とする。`test_hooks.py` の settings.json フック実在検査を含む)
- **文書検査(CI docs-lint)**: `check_docs_status.py`(frontmatter 3 行・索引の版一致)・lychee(リンク)・`check_design_propagation.py`・`check_doc_coverage.py` が緑
- **設定差分(手動・ステップ 2)**: `.claude/settings.json` の差分が `model`・`modelSettings` のみ / 新規セッションでの実効 model・effort を人間が確認
- **実機(手動・ステップ 4 と確定ゲート)**: ラッパー経由の `review normal` / `review adversarial` のスモークで受理・判定行・遮断なしを確認。遮断時は安全語彙で 1 回再実行、両方不成立で revert を含むステップ 4 コミット + PR 停止(「順序と差し戻し経路」)
- **一致性・越境・E2E・故障系(NFR-019)**: 製品コードに触れないため対象外
