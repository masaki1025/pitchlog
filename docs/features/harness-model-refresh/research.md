---
feature: harness-model-refresh
type: research
date: 2026-09-26
---

# 調査メモ: モデル世代更新(Opus 5.5・GPT-6 Astra)とトークン効率改善

## 問い

1. 新モデルの事実(ID・位置づけ・料金・effort・廃止予定)は何か。PO の呼称「GPT-6 sol」は何を指すか
2. 現行ハーネスのトークン消費はどこに偏っているか(主セッション / サブエージェント / Codex 実装 / Codex レビュー)
3. サブスクの利用上限内で「より長く作業できる」ようにするには、どの設定・規律を変えるのが効くか。品質を落としてはいけない箇所はどこか
4. 変更が過去の決定(ADR-001・設計書 8.5/9.4・台帳)と矛盾しないか。どのゲートを通すか

## 結論(要約)

1. **新モデルの事実**: Claude **Opus 5.5 = `claude-opus-5-5`**(2026-09-22・$4/$20・cache read $0.20・1M ctx・既定 effort medium。公式に「Fable 5.1 相当の性能で Opus 5 より 40% 安い」)。GPT-6 世代は **`gpt-6-astra`(09-03)/ `gpt-6-sol`・`gpt-6-luna`(09-22)** の 3 つで **terra 相当は無い**。PO の呼称「GPT-6 sol」は実在の `gpt-6-sol`(B-2)。gpt-6-sol は 5.6-sol の**半額・ChatGPT 利用枠の消費重みも半分**(5.6-terra と同じ)で、公式に "improves substantially over GPT-5.6 Sol"(FrontierCode)。**本機の Codex CLI 0.153.4 では gpt-6-sol/luna が使えず、0.157.x への更新が前提**(B-3 — カタログ追加は公式変更履歴で 0.156.1 hotfix・GitHub リリースノートで 0.157.0)
2. **消費の偏り**(A-3): Claude 側は主セッション(Fable 系)が約 8 割で、支配項は 1 ターン平均 40 万トークンのキャッシュ読み取り。Codex 側は sol xhigh(敵対レビュー)と terra max(実装)が同程度で入力の 9 割超がキャッシュ。**単価が最も高い箇所 = Fable の主セッションと 5.6-sol の敵対レビュー**
3. **効く変更**(品質を落とさない範囲): ① 主セッションを **Opus 5.5** へ(Fable は Max の週次上限の 50% までしか使えず速く消費する — 公式。Opus 5.5 は Fable 5.1 相当の性能)② 調査サブエージェント 3 本を **`claude-opus-5-5`・`effort: high`** へ(cache read $0.50 → $0.20・ベンチ向上)③ Codex 対応表を **GPT-6 世代へ再設計**: terra 枠 → gpt-6-sol・5.6-sol 枠 → gpt-6-sol(旧フロンティア以上の水準を半分の重みで)。astra は単価・重みが 5.6-sol の 2.5 倍で「長く働く」目的に反するため**本版では対応表に載せず**、昇格が必要になった実例で改訂する。**effort 値は据え置き**(PO 指示事項 v0.8。出力は消費の 3 割程度で、モデル切替と別変数として計測後に再判定)。Fast / Ultra は使わない(利用枠を増やす・exec で指定不可)
4. **ゲート**(C-1・C-2・C-7): ADR-001 は決定内容の変更 = **v1.1 へ版繰り上げ + 7.3 確定ゲート**。設計書 8.5 は「モデルは固定のまま」の条文があるため **v1.18 へ版繰り上げ**(8.5 実行既定・9.4 表・8.1 主セッション推奨の新設)し、**ADR-001 と単一の確定ゲートで一括**(先例 v1.15/ADR-004)。要件書は触らない(C-5)。`effortLevel` 併記は公式仕様の確定を典拠に廃止(C-6)。対応表 ↔ `MODEL_MAP` の同期テストを新設(C-7 #6)。並列度 3 は変えない(H-35)

## 詳細と典拠

### A. ローカルで確認できた事実(2026-09-26 実査)

#### A-1. Codex CLI とモデルカタログ

- Codex CLI **0.153.4**(`--version` で確認)。ADR-001 決定時は v0.146.1(`docs/adr/ADR-001-codex-model-selection.md:22`)
- モデルカタログ `~/.codex/models_cache.json`(fetched_at 2026-09-23T03:48Z・client_version 0.153.4)の内容:

| slug | 表示名 | priority | 公式説明(description) | effort 候補 | 既定 effort | 備考 |
| --- | --- | --- | --- | --- | --- | --- |
| `gpt-6-astra` | GPT-6-Astra | 1 | Frontier intelligence for the most demanding work | low / medium / high / xhigh / max / **ultra** | medium | `multi_agent_reasoning_effort: xhigh`。availability_nux: "This is GPT-6, a new generation of intelligence. Astra is state-of-the-art in coding, computer use, science, and professional work." |
| `gpt-reserve` | GPT-Reserve | 3(hide) | Fast and affordable agentic coding model | low〜max | medium | 非表示(未公開 tier と推定 — 不明) |
| `gpt-5.6-sol` | GPT-5.6-Sol | 4 | **Older** coding model for complex work | low〜ultra | low | |
| `gpt-5.6-terra` | GPT-5.6-Terra | 7 | **Older** balanced model for straightforward work | low〜ultra | medium | |
| `gpt-5.6-luna` | GPT-5.6-Luna | 8 | (略) | low〜max | medium | |
| `gpt-5.5` | GPT-5.5 | 12 | | low〜xhigh | medium | **2026-10-14 廃止**(`upgrade.retirement_at`)。後継 = gpt-5.6-sol |

- **`gpt-6-sol` という slug はカタログに存在しない**。GPT-6 世代で列挙されるのは `gpt-6-astra` のみ(2026-09-23 時点)。PO の呼称「gpt6sol」は astra を指すと解釈する(**要 PO 確認**)
- 全モデル共通: `context_window` 272,000 / `max_context_window` 872,000 / `effective_context_window_percent` 95。"Fast" サービス tier(priority)は astra が「2x speed, **increased usage**」・他は「1.5x speed, increased usage」— **速度 tier は利用枠の消費を増やす**方向
- 本機の Codex セッション履歴には **gpt-6-astra xhigh を対話モードで使った実績が 1 件**(2026-09-06・pitchlog・入力 274 万トークン中キャッシュ 259 万)

#### A-2. Claude Code とモデル ID

- Claude Code **2.1.283**(`--version` で確認)。バイナリ内のモデル一覧(`/home/walter/.local/share/claude/versions/2.1.283`)に `claude-opus-5-5` が存在し、設定ドキュメント文字列に「**Opus 5.5 (`claude-opus-5-5`), now the default Opus model — 1M context**」の記述がある(availableModels の説明文中)。API の正式な料金・effort は Web 調査(B)で確認する
- 現在の利用者設定(`~/.claude/settings.json`): `"model": "fable[1m]"`・`"effortLevel": "xhigh"`・`modelSettings["claude-fable-5"].effortLevel = "high"`。**主セッションは Claude Fable(1M コンテキスト)を xhigh で運用している**
- 調査サブエージェント 3 本(`.claude/agents/{spec-checker,legacy-analyst,decision-tracer}.md:5-7`)は `model: claude-opus-5`・`effort: high`・`effortLevel: high`

#### A-3. トークン消費のベースライン(ローカル実測)

**Claude 側**(`~/.claude/projects/-home-walter-projects-pitchlog/**/*.jsonl` の assistant メッセージ usage を集計。直近 30 日・16 ファイル。API 単価は claude-api スキルの表〔Fable $10/$50・Opus $5/$25・cache write 1.25x・cache read 0.1x〕で換算した**相対比較用の概算**であり、サブスク上限の消費率そのものではない):

| モデル | 役割 | ターン数 | cache 書込 | cache 読取 | 出力 | API 相当額 | 1 ターン平均コンテキスト |
| --- | --- | --- | --- | --- | --- | --- | --- |
| claude-fable-5 | 主セッション | 477 | 5.3M | **187.5M** | 754K | **$291.7(75%)** | **約 40 万 tok** |
| claude-fable-5 | サブエージェント(継承) | 118 | 1.7M | 17.8M | 136K | $46.5 | 約 17 万 tok |
| claude-opus-5 | サブエージェント(調査 3 本) | 365 | 2.3M | 31.5M | 194K | $34.9 | 約 9 万 tok |
| claude-fable-5-1 | 主セッション(直近) | 21 | 0.6M | 2.9M | 94K | $14.7 | 約 17 万 tok |

- 観測: **主セッションが約 8 割**。支配項は**キャッシュ読み取り**(1 ターンあたり平均 40 万トークンのコンテキストを再送している)。出力トークンは総額の 1 割程度
- 含意: 「モデル単価」と「1 ターンあたりのコンテキスト量」の 2 つが利用枠消費を決める。前者はモデル/effort の選択、後者はセッション設計(コンテキスト衛生)の問題
- 限界: ローカル 1 台分のみ(リモートの 998 コミット分は別機での作業と推定され未計測)。サブスク上限の重み付けは Web 調査(B-2)で確認する

**Codex 側**(`~/.codex/sessions/**/*.jsonl` の最終 `token_count` を集計。直近 60 日):

| モデル | effort | 経路 | 対象 | セッション数 | 入力(うちキャッシュ) | 出力 | うち推論 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-5.6-sol | xhigh | exec(ラッパー) | pitchlog | 42 | 105.7M(96.6M) | 790K | 577K |
| gpt-5.6-terra | max | exec(ラッパー) | pitchlog | 49 | 89.0M(81.0M) | 1,221K | 932K |
| gpt-5.6-sol | ultra | 対話(TUI) | 他プロジェクト | 12 | 42.9M(41.0M) | 212K | 112K |
| gpt-5.6-terra | high | exec(research) | pitchlog | 1 | 3.5M | 11K | 5K |
| gpt-6-astra | xhigh | 対話(TUI) | pitchlog | 1 | 2.7M(2.6M) | 12K | 5K |

- 観測: Codex 側は **sol xhigh(敵対レビュー・確定ゲート)と terra max(実装・一次レビュー)が同程度の入力量**。ここでもキャッシュ入力が 9 割超
- 台帳の既存観測(`docs/development/harness-evaluation.md` の候補節・2026-09): `--resume` を重ねた実装セッションは**累計トークンが単調増加**し 97 万トークンに達して失敗、新規セッションでは 14 万トークンで成功した実測がある → **Codex 側もセッションの肥大が消費を押し上げる**

#### A-4. ハーネスで「モデル ID・effort」を保持している箇所(変更対象の候補)

| 箇所 | 内容 | 出典 |
| --- | --- | --- |
| `docs/adr/ADR-001-codex-model-selection.md` | Codex モデル対応表の正本(approved v1.0)。「モデル世代交代の際は本 ADR を改訂して切り替える」 | 同書 帰結節 |
| `.claude/scripts/codex_run.py:31-40` | `MODEL_MAP` / `RESEARCH` / `RESEARCH_DEEP` / `REVIEW_NORMAL` / `REVIEW_ADVERSARIAL`(ADR-001 の機械適用) | 同ファイル |
| `docs/development/dev-harness-design-2026-08-07.md` 9.4 | 対応表の複製(ADR-001 参照) | 同書 9.4 |
| 同 8.5 | 調査サブエージェント: `model: claude-opus-5` 固定・effort high・既定 3 並列 | 同書 8.5 |
| `.claude/agents/*.md:5-7` | frontmatter `model` / `effort` / `effortLevel` | 3 ファイル |
| `CLAUDE.md:35` | 「モデルは Opus 5・effort high 固定」 | 同ファイル |
| `.claude/skills/{implement,research,plan,pr,finalize-doc}/SKILL.md` | 「terra medium 固定」「terra high」「sol xhigh」の自然言語記述 | 各 SKILL.md |
| `tests/` | **MODEL_MAP・agents frontmatter を検査するテストは存在しない**(`tests/` 配下に gpt-5.6 / MODEL_MAP / claude-opus-5 の参照が 0 件) | 実査 |

- `.claude/core-areas.json` の `guard_paths` には `codex_run.py`・`.claude/agents/*`・ADR は**含まれない**(含まれるのは `.claude/skills/{pr,release,task-done,finalize-doc}/SKILL.md`・`core-areas.json`・検査スクリプト群)。→ finalize-doc の SKILL.md を触る場合は逐行確認チェックが付く

### B. Web 調査(Codex `research`・terra high・live search。2026-09-26 実施。**重要事実は Claude が公式 URL を再取得して照合済み**〔照合済み = ✔〕)

#### B-1. Anthropic 側(Claude Opus 5.5・Claude Code)

| 項目 | 事実 | 典拠 |
| --- | --- | --- |
| Opus 5.5 の ID・公開日 | `claude-opus-5-5`。**2026-09-22 公開**。Retirement は 2027-09-22 より前にはない | ✔ https://platform.claude.com/docs/en/models/opus-5-5/overview |
| Opus 5.5 の料金 | input **$4** / output **$20** / 5m cache write $5 / 1h cache write $8 / **cache read $0.20**(base input の 5%) | ✔ 同上 |
| Opus 5.5 の能力・既定 | 1M context・最大出力 128K・adaptive thinking(常時 on)・effort low/medium/high/xhigh/max・**既定 effort = medium**(Fable 5.1 の既定は high) | ✔ 同上 |
| Opus 5.5 の位置づけ | "performs at the level of Claude Fable 5.1 on most work and costs 40% less to run than Opus 5"。Terminal-Bench 4.0: Opus 5.5 66.4% / Fable 5.1 55.8% / Opus 5 52.3%。FrontierCode v1.1: 54.4 / 50.3 / 48.0。CursorBench 4.0: 57.8 / 51.8 / 46.6。AutomationBench: 40.0 / 31.4 / 26.9 | ✔ https://www.anthropic.com/claude-opus-5-5 (2026-09-22) |
| 比較単価(API) | Fable 5.1 $10/$50・cache read $0.25(2.5%)/ Opus 5 $5/$25・cache read $0.50 / Opus 5.5 $4/$20・cache read $0.20 / Sonnet 5 $2/$10 | ✔ opus-5-5 overview の比較表 + pricing |
| Max プランでの Fable | "You can use up to **50% of your weekly usage limits** on Fable models at no extra cost." / "They draw from your plan's regular weekly usage limits and **use them faster than other Claude models**." | ✔ https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan |
| 上限の重み付け | モデル別の数値係数・cache read の算入式は**公開されていない(不明)**。消費は会話長・複雑さ・ツール・モデル・effort に依存すると記載 | Codex 調査(support.claude.com/en/articles/11647753・9797557)— 係数は不明のまま |
| サブエージェント frontmatter の正式キー | `model`(`sonnet`/`opus`/`haiku`/`fable`/完全 ID/`inherit`)と **`effort`**(low/medium/high/xhigh/max・省略時はセッション継承)。**`effortLevel` は frontmatter のキーではない**(表に無い → 無視される)。解決順 = 呼び出し時 `model` → frontmatter → `CLAUDE_CODE_SUBAGENT_MODEL` → 主会話モデル | ✔ https://code.claude.com/docs/en/sub-agents |
| エイリアス解決 | `opus` → **`claude-opus-5-5`**(Anthropic API 直結。Microsoft Foundry では opus-4-6)/ `fable` → Fable 5.1 | ✔ https://code.claude.com/docs/en/model-config |
| effort の解決順と落とし穴 | 明示(`CLAUDE_CODE_EFFORT_LEVEL` / `--effort` / `/effort`)→ 設定(`modelSettings` のモデル別 or トップレベル `effortLevel`)→ モデル既定。**トップレベル `effortLevel` は Opus 5.5 には適用されない**("A top-level `effortLevel` in your user settings file doesn't count for Opus 5.5 … Opus 5.5 and models released after it start at their own default until you choose a level for them") | ✔ 同上 |
| 1M コンテキスト | Fable 5.1 / Fable 5 / Sonnet 5 / Opus 4.7 以降は**全プランで常に 1M**(`[1m]` の選択・usage credits 不要)。200K 超のプレミアム単価は無い | ✔ 同上 |
| 自動コンパクション | `autoCompactWindow`(100K〜1M)/ 環境変数 `CLAUDE_CODE_AUTO_COMPACT_WINDOW`。未設定なら native 1M モデルは**約 967K で圧縮**(= 1 ターン 40 万トークンの再送が起こる余地) | ✔ 同上 |
| Fast mode | Max/Pro ではプラン枠でなく **usage credits を直接消費** → 「上限内で長く」の目的に不適 | Codex 調査(code.claude.com/docs/en/fast-mode)— 未照合 |
| サブエージェントの効果 | 別コンテキストで動き要約だけが戻るため主セッションの膨張を抑える。ただし初回は親 cache を読めず自前で温める(消費ゼロではない) | Codex 調査(code.claude.com/docs/en/prompt-caching)— 未照合 |

- Codex(terra high)の推奨案: 主セッション = `claude-opus-5-5` / medium / 1M。サブエージェントは「探索・列挙・抽出 = haiku」「照合・影響範囲 = opus-5-5 medium」「誤りを許容しない読取りレビュー = opus-5-5 high」。Fable 5.1 は Opus 5.5 high でも足りない長期自律作業に限り、週次 Fable 残量を見て昇格
- Claude の評価: 主セッションの Opus 5.5 化は**公式事実 3 点**(Fable は週次上限の 50% までかつ速く消費 / Opus 5.5 は Fable 5.1 相当の性能で単価 1/2.5 / cache read も $0.20 vs $0.25)から堅い。サブエージェントの haiku 化は「典拠必須・不明と答える」規律(8.5)の維持が前提であり、調査 3 本は**出典の正確さが成果物**なので medium 以上を保つ方が安全(後述の C と合わせて判定)

#### B-2. OpenAI 側(GPT-6 世代・Codex)

**A-1 の訂正**: GPT-6 世代は **`gpt-6-astra` / `gpt-6-sol` / `gpt-6-luna` の 3 モデル**(terra 相当は無い)。Sol と Luna は **2026-09-22 公開**で、本機の Codex CLI 0.153.4(2026-09-04)のカタログには載らない。**PO の呼称「GPT-6 sol」は実在の `gpt-6-sol` を指す**(A-1 の「astra と解釈」を撤回)。

| 項目 | 事実 | 典拠 |
| --- | --- | --- |
| GPT-6 の 3 モデルと位置づけ | Astra = "our most intelligent model yet … software engineering, science, and professional work" / **Sol = "Built to power complex coding and agentic workflows"("strong reasoning on demanding tasks")** / Luna = "efficient, repeatable work at scale" | ✔ https://developers.openai.com/api/docs/guides/latest-model / ✔ https://developers.openai.com/api/docs/models/gpt-6-sol |
| 公開日 | Astra 2026-09-03 / Sol・Luna 2026-09-22 | Codex 調査(openai.com/index/introducing-gpt-6-sol-and-luna/ — **Claude からは 403 で未照合**)。Codex CLI 0.157.0(2026-09-25)が "Added GPT-6 Sol and Luna" と整合 |
| API 料金($/1M: input / cached / output) | **astra $10 / $1 / $50** ・ **sol $2 / $0.20 / $10** ・ **luna $0.10 / $0.01 / $0.50** ・ 5.6-sol $4 / $0.40 / $20(2026-08-21 改定の promotional・少なくとも 2026-11-21 まで)・ 5.6-terra $2 / $0.20 / $12 ・ 5.6-luna $0.20 / $0.02 / $1.20。Fast(旧 priority)は全モデル **2 倍**。長コンテキスト(272K 超)は概ね 2 倍 | ✔ https://developers.openai.com/api/docs/pricing |
| 含意(単価) | **gpt-6-sol は gpt-5.6-sol の半額・gpt-5.6-terra と同じ input 単価で output は 17% 安い**。gpt-6-astra は 5.6-sol の 2.5 倍 | 上記から算出 |
| 能力・effort | Sol: ctx 1,050,000・最大出力 128K・effort `none/low/medium(既定)/high/xhigh/max`・知識 2026-04-20。Astra: ctx 1,050,000・128K・effort `low〜max`(**`none` 不可**)・知識 2026-04-30。**`ultra` は API の effort 値ではない**(Codex/Work 側の「max 推論 + 自動タスク委任」モード) | ✔ 各モデルページ / ✔ latest-model ガイド |
| Astra のトークン効率 | "achieves stronger results while using substantially fewer output tokens—delivering a lower estimated API cost per task than earlier models despite its higher per-token pricing" | ✔ latest-model ガイド |
| ChatGPT サブスクの消費重み | Business/Enterprise の credit rate card(2026-09-24 更新)では 1M tok あたり **Astra 250 / 25 / 1,250・Sol 50 / 5 / 250・Luna 2.5 / 0.25 / 12.5**(input/cached/output)。5.6-sol 比で Astra は 0.4 倍しか使えず、**GPT-6 Sol は 2 倍長く使える**(5.6-terra と同等)。**Plus/Pro のモデル別固定倍率は非公開(不明)** | Codex 調査(help.openai.com/en/articles/11481834 — **403 で未照合**) |
| effort と消費 | 公式は「高い effort は利用枠をより多く使い得るが常に良い結果になるわけではない」。**"Astra low は Sol high を上回り得る"**。Ultra は追加 agent が走るため固定倍率不明・通常既定には不適 | Codex 調査(help.openai.com/en/articles/20001516・2026-09-18 更新 — **403 で未照合**) |
| ベンチマーク(Astra vs 5.6-sol) | Terminal-Bench 4.0 57.9% vs 37.3% / DeepSWE v1.1 74.1 vs 72.7 / FrontierCode 1.1 Main 53.3 vs 47.5 / 同 Extended 64.5 vs 60.6。SWE-Bench Pro の掲載なし。**GPT-6 Sol の公式ベンチマークは未取得**(発表ページ 403) | Codex 調査(openai.com/index/gpt-6-astra/ — 未照合) |
| gpt-5.6 の廃止予定 | 公式 Deprecations に sol/terra/luna の廃止日・後継告知なし(**不明**)。gpt-5.5 のみ 2026-10-14 廃止(A-1 のカタログと一致) | Codex 調査(developers.openai.com/api/docs/deprecations) |
| **Codex CLI の要更新** | GitHub リリースノートでは **0.157.0(2026-09-25)に "Added GPT-6 Sol and Luna to the model catalog … migration prompts for older models"**。**公式変更履歴(learn.chatgpt.com/docs/changelog)では 0.156.1(0.156.0 向け hotfix)でカタログへ追加**(確定ゲート 14 回目の指摘 — 両出典を併記)。最新安定版は 0.157.1(2026-09-26)。本機は 0.153.4 → `gpt-6-sol` / `gpt-6-luna` を使うには **CLI 更新が前提**(運用下限 = 本機確認済みの 0.157.0) | ✔ `gh release view rust-v0.157.0 -R openai/codex` / 公式変更履歴は Codex レビュアの照合 |
| CLI 0.150〜0.153 の節約系 | 0.152.0: MCP ツールごとの `output_token_limit` / 0.153.0: `features.context_management.experimental_mode`(token-budget context・history notes・`new_context`)/ 0.157.0: "Resume model context from the latest compaction boundary"。config キー `tool_output_token_limit`・`model_auto_compact_token_limit`(既定 = raw window の 90%)。**これらを小さくしても節約の保証はない**(圧縮が早まり再読込が増え得る) | Codex 調査(github.com/openai/codex releases・config_toml.rs)— リリースノートは ✔ |

- Codex(terra high)の推奨案: 機械的軽作業 = luna low / 通常実装 = **sol medium** / コア領域 = astra **low** から(必要時 medium)/ 一次レビュー = sol high / 敵対レビュー = astra medium / Web 調査 = sol medium / Fast・Ultra は既定にしない
- Claude の評価: 「通常枠を gpt-5.6-terra → gpt-6-sol へ」は**単価同等以下で上位世代**なので異論なし。「コア領域・敵対レビューを astra へ」は単価 2.5 倍・Business 重み 2.5 倍で、**effort を下げても消費が減る保証はない**(効果は "fewer output tokens" の一般論のみ)。一方 **gpt-6-sol は 5.6-sol の後継 tier で単価半額**であり、`xhigh` で回せば**敵対レビューの消費は理論上半減**する。ADR-001 の原則「欠陥コストで線を引く = コア領域と品質ゲートにフロンティア級」を GPT-6 世代で読み替えると、フロンティア = astra だが、**旧フロンティア(5.6-sol)と同等以上の水準を gpt-6-sol が保つか**が判定の分かれ目 → GPT-6 Sol の公式ベンチマークを追加取得して計画で 2 案(A: sol xhigh 一本化 / B: astra low〜medium)を PO に提示する

#### B-3. 追加調査(GPT-6 Sol の位置づけ・利用枠の重み・CLI 対応 — Codex research 2 回目・原文引用)

| 項目 | 原文(引用) | 典拠 |
| --- | --- | --- |
| GPT-6 Sol の位置づけ | "GPT-6 Sol can take on difficult work tasks while giving you more room to iterate with **higher usage limits and lower cost**" / "We trained GPT-6 Sol and Luna with similar methods as GPT-6 Astra, bringing the advances behind Astra's state-of-the-art performance in professional work, factuality, coding, computer use, and alignment to faster, more affordable models." | openai.com/index/introducing-gpt-6-sol-and-luna/(2026-09-22)— Claude からは 403・Codex の原文引用 |
| GPT-6 Sol vs 5.6 Sol | "On FrontierCode … **GPT-6 Sol improves substantially over GPT-5.6 Sol, and is able to match Claude Fable 5.1 xhigh at much lower cost.**" / "On DeepSWE v1.1 … GPT-6 Sol at max effort scores 68.8%"(5.6 Sol の同条件値・SWE-Bench Pro・Terminal-Bench 4.0 の掲載は**不明**) | 同上 |
| 価格移行 | "reducing API prices for Sol and Luna by 50% compared with their GPT-5.6 promotional pricing" / "GPT-5.6 Sol → GPT-6 Sol \| $4 → $2 \| $20 → $10 \| 50% cheaper"。"successor" / "replaces" の明示は**不明** | 同上 |
| 提供範囲 | "available in ChatGPT Work and Codex starting today for all Plus, Pro, Business, Enterprise, and Edu users." | 同上 |
| Astra vs 5.6 Sol(抜粋) | Terminal-Bench 4.0 57.9% vs 37.3% / DeepSWE v1.1 74.1 vs 72.7 / FrontierCode 1.1 Main 53.3 vs 47.5 / AutomationBench 41.4 vs 18.1 / "approximately 9% … lower estimated API cost per task" | openai.com/index/gpt-6-astra/(更新 2026-09-22) |
| 利用枠の消費重み(credits / 1M tok: input / cached / output) | "GPT-6 Astra \| 250 \| 25 \| 1,250" / "**GPT-6 Sol \| 50 \| 5 \| 250**" / "GPT-6 Luna \| 2.5 \| 0.25 \| 12.5" / "**GPT-5.6 Sol \| 100 \| 10 \| 500**" / "GPT-5.6 Terra \| 50 \| 5 \| 300" / "GPT-5.6 Luna \| 5 \| 0.5 \| 30"。"Fast mode is charged at 2.5× the Standard rate." / Ultra: "uses maximum reasoning and may run additional agents … credit usage still depends on the model used and the tokens produced by the task and any agents it runs." | help.openai.com/en/articles/11481834(Business/Enterprise rate card・"Updated: 4 days ago")— Plus/Pro の係数は非公開のため**代理指標**として使う |
| effort と利用枠 | "**Astra at Low effort can outperform Sol at High effort.**" / "Higher effort can use more of your allowance and does not always produce a better result." / "A reasoning level does not set a fixed amount of usage for a task or guarantee a better result." | help.openai.com/en/articles/20001516("Updated: 10 days ago") |
| CLI 対応 | rust-v0.157.1 の `models.json` に `"slug": "gpt-6-sol"` があり `supported_reasoning_levels` に `"effort": "xhigh"` を含む。`"minimal_client_version": "0.155.0"` | github.com/openai/codex/blob/rust-v0.157.1/codex-rs/models-manager/models.json |

**Codex 60 日実測(A-3)を rate card の重みで換算した試算**(Plus/Pro の係数は非公開なので相対比較のみ):

| 経路 | 現行(モデル・credits) | 案 A: gpt-6-sol 一本化 | 案 B: コア・敵対 = astra |
| --- | --- | --- | --- |
| 敵対レビュー・確定ゲート(sol xhigh 42 セッション: 非キャッシュ入力 9.0M・キャッシュ 96.6M・出力 0.79M) | 5.6-sol: 9.0×100 + 96.6×10 + 0.79×500 ≈ **2,260** | gpt-6-sol: ≈ **1,130**(半減) | astra: ≈ **5,650**(2.5 倍。effort 引き下げで出力が減っても入力側は減らない) |
| 実装・一次レビュー(terra max 49 セッション: 非キャッシュ 8.0M・キャッシュ 81.0M・出力 1.22M) | 5.6-terra: 8.0×50 + 81.0×5 + 1.22×300 ≈ **1,170** | gpt-6-sol: ≈ **1,110**(出力 300→250 分だけ減) | 同左 |
| 合計 | ≈ 3,430 | ≈ **2,240(−35%)** | ≈ 6,760(+97%) |

- 含意: **利用枠を「より長く」使う目的では案 A が唯一整合**する。案 B は上位の品質を買う代わりに Codex 側の消費を倍増させる。出力トークンは合計の 3 割程度で、effort 引き下げの効果はモデル切替より小さい(別変数として計測後に判定)

### C. 決定経緯(decision-tracer・Opus 5 high・2026-09-26)

#### C-1. ADR-001 の決定・見直しトリガー・改訂ゲート

- **決定**(`docs/adr/ADR-001-codex-model-selection.md:32-42`): 作業の重さで機械的に選ぶ 7 行の表。**理由 4 点**(`:46-49`): ① 欠陥コストで線を引く(要件書 R-3/R-5・G-1 の取り返しのつかなさ → コア領域と品質ゲートにフロンティア級)② 物量は terra(SWE-Bench Pro 1.2pt 差でコスト半分)③ レビュー水準の連続性(要件フェーズの sol 敵対レビュー実績・公式クラウドレビュー担当も sol)④ **エイリアス禁止・明示 ID 固定**(8.5 の Opus 5 固定と同じ規律)
- **帰結・見直しトリガー**(`:53-55`): 「**モデル世代交代(tier 名は維持されつつ各 tier が独自更新される)の際は本 ADR を改訂して切り替える**」/ トリガー = terra 起因の欠陥・料金/レート改定・**新 tier 登場**。→ 今回は 3 つのうち「世代交代」「料金改定」「新 tier 登場」の 3 条件すべてが成立
- **当時の前提**(`:21-28`): codex-cli v0.146.1 のカタログ + 公式ドキュメント(2026-08-07)。`model_reasoning_effort=max` の CLI 受理を実機検証済み。ADR-001 の 5.6-sol 単価「$5/$30」は **2026-08-21 の改定で $4/$20 に変わっており陳腐化**(B-2)
- **改訂ゲート**: 7.2 の体系表で `docs/adr/` の確定ゲートは「必須(軽量版可)」(設計書 `:425`)。7.6-3: 実装追随の節更新 = PR レビュー / **版繰り上げを伴う構造的変更 = 7.3 確定ゲート**(`:513`)。先例 = ADR-003: 決定内容を変えない追随は「版は上げない」(`ADR-003:13`)、内容改訂は 7.3 確定ゲート(`ADR-003:11`)。ADR-001 自身の 2026-08-17 行は「決定内容の変更なし」と明記(`ADR-001:11`)。→ **モデル対応表の書き換えは決定内容の変更 = 版繰り上げ(1.0 → 1.1)+ /finalize-doc**
- **様式**(H-62 決着済み・`harness-evaluation.md:1224-1233`): 変更履歴表への行追加・frontmatter ちょうど 3 行(7.1-5 `:417`)・**索引 `docs/README.md:16` の版と最終更新の同時更新**(`scripts/check_docs_status.py:694,:704` が変更履歴表の最大版と索引の版を比較 — 不一致は docs-lint が落とす)

#### C-2. 設計書 8.5「Opus 5 固定・effort high・既定 3 並列」の経緯とゲート

- **決定**(設計書 `:731`): `model: claude-opus-5` を明示 ID で固定・effort high(`effort`・`effortLevel` 併記)・既定 3 並列で重さに応じ増減・**「effort も重さに応じて調整してよい(モデルは固定のまま)」**。CLAUDE.md に転記して既定動作にする(8.1 `:662`)。導線側にも「既定 3 並列」(8.4 `:703`・`.claude/skills/investigate/SKILL.md:10`)
- **経緯**: v0.3 でサブエージェント 3 本を具体化(`:20`)、**v0.4 で実行既定を確定**(`:21`)。v1.0 の確定ゲート(敵対レビュー 5 周 → PO 承認 2026-08-07)で一括 approved(`:35`)。同時に「全員 read-only・Web ツールなし(Web 調査 = Codex の分担を機構化)」「出典必須・不明と答える」(`:719`・`:732`)
- **8.5 を変えた先例**: v1.5 = legacy-analyst 典拠欄への追加を「節更新・版は上げない(7.6-3 前段)」で approved(`:49`)/ v1.4・v1.6 = 確定ゲートの反映周で処理(`:44`・`:50`)
- **整合/矛盾**: 今回の対象は**実行設定そのもの(規範)**で、8.5 は「モデルは固定のまま」と明示している → 運用裁量で動かせず**条文改訂が必要**。台帳 **H-19**(`harness-evaluation.md:172-181`): 「実装追随の節更新 = PR レビュー」で起案した判定が**連続 6 件、レビューで確定ゲートへ覆っている**(前段で通った実例は 1 件のみ)→ 前段判定は覆るリスクが高い。メモリ(エージェントチーム試行)にも「8.5 改訂は /task-start → 計画書 → /finalize-doc のゲートを通す」合意が記録されている(正本ではない)。→ **8.5 の実行既定の変更は設計書の版繰り上げ + 7.3 確定ゲート**として計画する(ADR-001 v1.1 と単一ゲートで一括検証 — ADR-004 / v1.15 の先例)

#### C-3. 9.4・6.3 の水準決定と、台帳のモデル・effort・コスト関連 H-*

- **9.4**(設計書 `:826-828`): エイリアス禁止・明示 ID 固定 / 「本表は `codex_run.py` が機械適用する(人が都度選ばず、スキルの自然言語にも依存しない)」/ max の CLI 指定可否は v0.146.1 で実機検証。effort 値は **v0.8(2026-08-07)で PO 指示により改訂**(通常・一次レビュー = terra max・軽微 = terra medium・コア領域 = sol xhigh・軽作業 = luna xhigh・`/research` 行追加。ADR-001 も同時改訂 `:25`)→ **effort の値は PO 指示事項**であり、今回の改訂でも PO 判断を明示的に取る
- **6.3**(`:369-385`): 「書いた側の反対側を必須レビュアにする」(Codex 単独 = 自己批准・Claude 単独 = 動くコードの穴の検出力不足 `:381`)/ コア領域 PR は人間の逐行確認必須(`:383`)。欠陥コスト論の正は ADR-001 理由 1
- **台帳の関連項目**(`docs/development/harness-evaluation.md`):
  - **H-30**(`:929-939`): 確定ゲート 1 周目(sol xhigh)が計画レビュー 6 周(terra max)で見えなかった P0 3 件を検出。限界 = 「観点も違うためモデル差だけの効果とは切り分けられない」(`:935`)→ **敵対レビューの水準を下げる根拠にも上げる根拠にもならない**(観点差の可能性)
  - **H-25**(`:288-297`): 計画レビュー 5〜6 周・7 タスクで再発。「コストが高いという観測であって無駄ではない。判断が必要なのはコストと効果の釣り合い」
  - **H-43**(`:345-354`): 計画レビューと確定ゲートは別クラスの欠陥 → 計画周回数を代理指標に確定ゲートの見積を下げると外す
  - **H-35**(`:984-993`): /investigate 3 並列が P0・文書間不一致 4 件を検出 → 対応案「3 並列を維持し、矛盾する報告は原典で裁定」(対応済み)→ **並列度 3 は据え置く根拠**
  - **H-75**(`:641-650`)+ 2026-09-21 追記の新規②(`:20`): セキュリティ中核のコア領域を敵対レビューに掛けると**提供側の安全分類器が指摘出力を遮断**(3 周目 flagged 2 回・指摘 0 件)。出力形式を「所在・理由・修正案の 3 点」に絞ると全指摘を受領。→ **モデル変更時に分類器挙動が変わり得る(astra は上位モデルで分類器が強い可能性)**。移行後の最初の敵対レビューで観測する
  - **H-68 4 例目**(`:18`): 設計書 v1.17 の確定ゲートでレビュー 12 回・反映 9 周・指摘 42 件(sol xhigh)→ 確定ゲート 1 件あたりの Codex 消費が大きい実例(A-3 の sol xhigh 42 セッション・105M 入力と整合)
  - 候補「長時間実行がメモリ不足で強制終了」(`:1615-1640`)・「出力ゼロで強制終了」(`:2019-2033`): `--resume` 累計 97 万トークン到達。通算 19 回 + 23 回の実測で「セッション肥大が原因」の見立ては**誤りと判明**(効くのは再実行のみ・再実行上限 2 回 → Claude 直接実装 + review normal)。→ **A-3 の「Codex 側もセッション肥大が消費を押し上げる」は "消費" については真だが "失敗の原因" ではない**。切り分けて書く
  - **サブスク利用上限に言及した H-*・候補は無い(不明)** → 本タスクが初出

#### C-4. 主セッション(Claude Code 本体)のモデル・effort・コンテキスト運用

- **正本に決定なし(不明)**。8.1(`:662`)が CLAUDE.md へ書けと定めるのは調査サブエージェントの既定であって Claude 本体ではない → 主セッションのモデル/effort は**現状「利用者設定の私事」**。ハーネスとして推奨値を持つなら**新規の規範**(設計書に節を新設 or 8.1 に追記)になる
- **/cost 実測**(`docs/worklog/2026-08-16-harness-design-review-team-investigate.md:21-24`): 合計 $27.98(チームメイト 3 名 Opus 5 = $16.24・出力 176K・キャッシュ読 9.7M / リーダー Fable 5 = $11.74・出力 80K・キャッシュ読 4.5M)。費用の一部は **6 日古い develop 基準で調査したため指摘 25 件中 7 件が既決**という無駄(台帳候補(9) `:1910-1914`)→ 調査前の `git fetch` を導線に明文化する改訂が昇格条件
- **上位モデル(fable)を相談役に使った実例**: `docs/worklog/2026-09-09-pg-authz-verification-g2.md:341-345`(根拠 5 件を原典で追認・1 件不採用)・`docs/worklog/2026-09-09-orm-schema-migration.md:147,:190,:1139` → **Fable を「常用」ではなく「相談役・昇格枠」に置く運用は既に実例がある**
- メモリの運用知見(正本ではない): レビュー出力は全文ファイル保存・adversarial/implement は background(`memory/codex-run-operational-lessons.md:13-14`)

#### C-5. 要件書の決定記録との関係

- D-38 / D-41 / D-42 / D-44(`docs/requirements/requirements-draft-pitchlog.md:407-441`)はレビュー体制(Opus・Codex sol ultra/xhigh)の**実施事実の記録**であり、将来の体制を縛る規範条項ではない。要件書本体でモデル名が出るのは変更履歴行のみ(`requirements-pitchlog-2026-07-22.md:11,:14,:15,:30`)。**FR/NFR の規範条文にモデル名は無い**(grep 実測)
- 判定: モデル変更は要件側の規範に影響しない。過去の履歴行は書き換えない(設計書 v1.4 の「過去事実は保存」`:44` と同型)。`requirements-draft-pitchlog.md` は変更履歴表を持たない免除文書で、編集は「履歴を残さず approved 正本を書き換える経路」になる(台帳候補(8) `:1904-1908`)→ **触らない**

#### C-6. `effort` と `effortLevel` の併記(P1-6)

- 規定 = 8.5 `:731`「effort・effortLevel を併記 — 公式キーの表記ゆれ対策、P1-6」。実装 = 3 エージェントとも両キー + 行末コメント(`.claude/agents/*.md:5-7`)。**内部不整合**: 8.5 の定義例(`:739-751`)は `effortLevel` のみで、本文の併記規定と食い違ったまま
- **P1-6 の指摘原文は追えない(不明)**(worklog 2026-08-07・設計書 v0.10 の P1×13 列挙に該当なし)。9.4 `:827` も同じ P1-6 を引く → 「実行設定を人や自然言語に委ねず機構で効かせる」型の指摘と読める
- 現行事実(B-1・公式 frontmatter リファレンス): 正式キーは **`effort`** のみ、未知キーは無視 → `effortLevel` は無害だが無効。**「表記ゆれ対策」の前提(公式キーが不確か)は解消済み**。整理するなら「公式仕様の確定を典拠に併記規定を廃止」と経緯を書く(原典不在のまま黙って外さない)

#### C-7. 今回の変更案と過去の決定の突き合わせ(矛盾の洗い出し)

| # | 種別 | 内容 | 計画への反映 |
| --- | --- | --- | --- |
| 1 | **矛盾(最重)** | 8.5「モデルは固定のまま」(`:731`)。Opus 5 → 5.5 は運用裁量では不可・条文改訂が必要。前段(節更新)起案は H-19 の実測 6 件どおり後段へ覆るリスク | **設計書の版繰り上げ + 7.3 確定ゲート**(ADR-001 v1.1 と単一ゲートで一括) |
| 2 | 整合 | 明示 ID 固定・エイリアス禁止(ADR-001:49・9.4 `:826`)は新 ID 直書きで保たれる | `claude-opus-5-5`・`gpt-6-sol` 等を直書き。`opus` エイリアスは使わない |
| 3 | **前提の失効** | ADR-001 帰結の「tier 名は維持されつつ各 tier が独自更新される」(`:54`)。GPT-6 は sol/luna を継ぐが **terra が無く astra が加わった** → 「重さ 4 分類 → tier」の当てはめを作り直す(ID 置換では済まない)。見直しトリガー「新 tier 登場」該当 | ADR-001 v1.1 は対応表を**再設計**として起案(理由節も更新) |
| 4 | 未検証 | effort 上限の根拠は v0.146.1 の実機検証(ADR-001:26)。新モデルでの xhigh/max 受理は同水準の実機検証が要る | 計画ステップに **実機検証(exec 経路で `-c model_reasoning_effort=xhigh`/`max` を新 ID に対して受理確認)** を置く。CLI 0.157.1 更新が前提 |
| 5 | 矛盾(水準を下げる場合) | 敵対レビュー・コア領域の水準を下げると ADR-001 理由 1・3 と 6.3 `:381` に正面から当たる。H-30 は反証にならない(観点差)。モデルを動かさずコストを下げた実測は別にある(台帳 `:22` 重大度基準の明示・`:20` 出力形式 3 点化) | **旧フロンティア(5.6-sol)以上の水準を維持**することを移行の必須条件にする(gpt-6-sol の位置づけ・ベンチマークで判定 — research_c)。コスト削減はモデル単価とセッション衛生で取り、水準は下げない |
| 6 | 要同期 | 9.4 `:827` の機械適用先 = `codex_run.py:31-40`。**表と実装の乖離を固定する自動テストが無い** | ステップに「ADR-001 の表 ↔ `MODEL_MAP` 等の同期テスト」を追加(tests/test_codex_run.py) |
| 7 | 様式 | ADR-001: 変更履歴表追記・frontmatter 3 行・`docs/README.md:16` の版/最終更新同期(`check_docs_status.py:694,:704`) | /finalize-doc の手順どおり |
| 8 | コア領域判定 | `codex_run.py`・`.claude/agents/*.md` は guard_paths にも各領域 paths にも無い → core-guard 非対象。`.claude/skills/{pr,release,task-done,finalize-doc}/SKILL.md` は guard_paths | finalize-doc の SKILL.md は**触らない**(sol xhigh の記述は「ラッパーが ADR-001 どおり」へ一般化する場合のみ最小変更 → 触るなら逐行確認対象と明記) |
| 9 | 典拠不在 | `effortLevel` の削除は原典不明のまま規約を外す | C-6 のとおり「公式仕様の確定」を新典拠として廃止を起案(黙って外さない) |
| 10 | 並列度 | 既定 3 並列は 4 箇所(8.5 `:731` / 8.4 `:703` / investigate SKILL `:10` / CLAUDE.md)。H-35 は 3 並列維持で対応済み | **3 並列は変えない**(スコープ外) |

## 未解決・申し送り

- **PO 判断が要る点**(計画書 4 節に転記): ① Codex 対応表 = 案 A(gpt-6-sol 一本化・astra は載せない)か案 B(コア領域・敵対 = astra)か ② effort 値の据え置き(推奨)か引き下げか ③ 主セッションの Opus 5.5 化をプロジェクト `.claude/settings.json` で機構化するか(推奨)、8.1 の推奨記述にとどめるか
- **未照合の典拠**: openai.com / help.openai.com の 4 ページは Claude からの取得が 403 で、Codex の原文引用に依存(B-2・B-3)。**Codex CLI 更新後にカタログ(`models_cache.json`)で `gpt-6-sol` の存在・effort 候補を実機確認する**ことで ID と effort は独立に裏付けられる
- **不明のまま**: Claude Max のモデル別消費係数・cache read の算入式 / OpenAI Plus・Pro のモデル別係数 / GPT-6 Sol の SWE-Bench Pro・Terminal-Bench 4.0 / gpt-5.6 sol・terra・luna の廃止日 / P1-6 の指摘原文
- **後続タスク候補**(本タスクの範囲外): 使用量プロファイル集計スクリプト(`~/.claude/projects` と `~/.codex/sessions` の JSONL 集計 — 本メモ A-3 の手順)を `scripts/` に置いて移行後の効果測定を定型化する / `autoCompactWindow` の設定値(主セッションの 1 ターン 40 万トークンの再送を抑えるか)の実測比較 / 調査前 `git fetch` の導線明文化(台帳候補(9))
- **観測項目(移行後の最初の敵対レビューで)**: 安全分類器による指摘遮断の再現有無(C-3 の H-75・台帳 :20)、`xhigh`/`max` の受理(C-7 #4)
