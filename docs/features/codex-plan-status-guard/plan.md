---
feature: codex-plan-status-guard
status: in-review         # active | in-review(/pr が PR 内で更新。完了は PR 状態・Notion・worktree 除去から導出)
承認: 済(2026-08-10・徳光 尋弥) # 未 | 済(YYYY-MM-DD・承認者)— codex_run.py が「済」でないと実行を拒否する
重さ分類: 通常            # 軽微 | 通常 | コア領域 | 機械的軽作業(ADR-001 のモデルをラッパーが自動選択)
worktree: ../../..        # worktree ルート(plan.md からの相対 or 絶対)。/task-start が設定
notion: https://app.notion.com/p/3b893b75e687819ebaa3ce597b8d97ea
branch: feature/codex-plan-status-guard
created: 2026-08-10
計画レビュー周回: 3        # 指摘反映を伴うレビュー 1 周ごとに +1(収束確認周は数えない。/plan が更新)
確定ゲート周回: 0          # 指摘反映を伴う敵対レビュー 1 周ごとに +1(同前。/finalize-doc が更新)
実行方式: 通常             # 通常 | fast(fast path 適用時に fast へ — 人間の事前 OK 必須。現在地導出が識別)
---

# 実装計画書: codex_run.py に plan status の機構強制を追加(in-review のまま /implement を拒否)

## 1. 背景・目的

- Notion タスク: [TSK-205 codex_run.py に plan status の機構強制を追加](https://app.notion.com/p/3b893b75e687819ebaa3ce597b8d97ea)
- 発端: feature-status(TSK-203)反対側レビュー 2 周目 P1 ③「in-review のまま /implement 可能(機構強制なし)」→ PO 判断(2026-08-10)で別タスク化(`docs/worklog/2026-08-10-feature-status.md:38-39,45`)
- 設計書 v1.3 は本欠落を**既知の残余リスクとして受容記録**し、本タスクでの解消と「解消時に本注記を削除する」ことを予告済み(`docs/development/dev-harness-design-2026-08-07.md:264`)。本タスクは設計原則「規約は守られるべき」ではなく「規約は破れない」(同 `:46`)の直接適用
- 要件対応: 直接対応する製品 FR/NFR は**なし**(ハーネス改修 — [research.md](research.md) §4)。関連規範 = 設計書 8.3 `:407`(hooks・ラッパーの pytest)・AGENTS.md「実装 PR はテストを伴う(NFR-019)」
- 調査の詳細と典拠: [research.md](research.md)(3 並列調査 + 原典確認。矛盾する過去決定なし)

## 2. スコープ

### やること

1. `.claude/scripts/codex_run.py` の frontmatter 抽出の開始・終端認識を是正する(**完全一致の単独行 `---` のみ** — docs-lint〔`scripts/check_docs_status.py:324,328`〕と同一文法。現行は `--- 任意文字列` も終端扱いで、status 検証の迂回経路になる〔レビュー 1 周目 P0〕。ラッパーが docs-lint の拒否する形式を受け入れない fail-closed 整合〔2 周目 P1-1〕)
2. 同 `cmd_implement()` に plan status の機構検証を追加する(`active` 以外は拒否・差し戻し往復手順へ誘導)
3. `tests/test_hooks.py` のラッパー検証節に拒否・誘導・通過の回帰テストを追加する
4. 設計書 6.1/9.2 の節更新(機構検証列挙への status 追記・6.1 の残余リスク注記削除・変更履歴表追記)と、機構検証を列挙する周辺文書の追随(3 節に列挙)

### やらないこと

- `cmd_fast` / `cmd_research` / `cmd_review` への status 検証の波及(fast は plan.md を読まない設計。波及は新たな決定事項 — research.md 未解決④。必要なら別タスク)
- `parse_frontmatter()` のその他の厳格化(status 以外のキーの重複検出・8KiB サイズ上限・YAML 化)や既存検証キー(承認・重さ分類・worktree・branch)の仕様変更。**例外 = やること 1 の終端認識是正のみ**(status 検証と既存キーが同じ抽出結果を共有するための前提)
- `scripts/feature_status.py`・`scripts/check_docs_status.py` の変更(無改修で green のまま)。**feature_status.py の delimiter 空白許容**(`:349,:357` — strip 後一致)**と本是正〔完全一致〕の差異は揃えない**: 強制の門番はラッパーと docs-lint で、両者は同一文法になる。feature_status.py はそれより広い入力を**表示するだけ**(強制に関与しない)の既存許容であり、揃えるにはタスク DoD(codex_run.py + テスト + 設計書)を超える改修が要る — 受容として本計画に記録(2 周目 P1-1 の残余)
- `.claude/skills/pr/SKILL.md` の変更(現行文言のまま正。guard_paths 該当のため触れない — research.md §3)
- 設計書の構造変更(変更は 6.1・9.2 の該当箇所と変更履歴表に閉じる)

## 3. 影響する正本

| 正本 | 変更内容 | ゲート(PRレビュー / finalize-doc) |
| --- | --- | --- |
| `docs/development/dev-harness-design-2026-08-07.md` | 6.1 `:250` の機構検証列挙へ status 検証を追記 / 6.1 `:264` の残余リスク注記を削除 / 8.4 `:423` の「承認済み計画書(未承認なら中断)」を「`status: active` かつ承認済み(in-review・未承認は中断)」へ追随 / 9.2 `:504` の列挙と `:507` の implement コマンド注記(「承認・worktree・モデルを検証」)へ status を追記 / 変更履歴表へ 1 行追記(版は繰り上げない起案)。**追記文言はいずれも implement 限定**(例:「`codex_run.py implement` が plan status〔`active` 以外拒否〕を機構検証」— fast/research/review が検証すると読める書き方をしない〔2 周目 P2-1・3 周目補完〕) | **PR レビュー**(7.6-3 前段「実装追随の節更新」)として起案。**根拠**: v1.3 自身が `:264` で本タスクによる解消と注記削除を予告済み = 予告された実装追随であり、新たな規約の新設・構造変更ではない(往復ライフサイクル自体は v1.3 確定済み)。**PO 判定(2026-08-10)= PR レビューで確定**(research.md 未解決①の解消。格上げ〔版繰り上げ + /finalize-doc〕の場合のステップ差し替え条項は不発動) |
| `docs/README.md` | 索引の状態・版・最終更新の表示を**確認して現行化する**(表示値が不変ならその確認結果を PR 本文に記す。「版繰り上げがないから反映なし」とはしない) | PR レビュー |
| 要件書・ADR-001 | **反映なし**(製品要件・モデル対応表に触れない) | — |

正本外の追随(同一 PR で運ぶ):

- `CLAUDE.md`: codex_run.py の機構検証列挙へ「plan status(implement)」を追記(文言は implement に限定 — fast は plan を読まない)
- `.claude/skills/implement/SKILL.md:9`: 同上(implement 限定の文言)
- `.claude/skills/finalize-doc/SKILL.md`: 「確定ゲート周回でコード修正が必要になり、**かつ plan が in-review の場合は**、先に /pr の差し戻し手順で `active` へ戻してから /implement する」旨の前置 1 行(research.md 未解決③の解消。通常フロー〔正本反映が /pr より先・plan は active〕には影響しない)
- `docs/development/templates/plan-template.md:3`: status 行コメントへ「`codex_run.py implement` が active 以外を拒否」を追記

## 4. 実装方針

- **重さ分類 = 通常 の根拠**: ガード機構そのものの変更であり typo・微調整の類(軽微)ではない。かつ正本(設計書)への影響を伴う。→ ADR-001 の「通常実装」= `gpt-5.6-terra` / effort max をラッパーが自動適用
- **コア領域判定: 非該当**。同期プロトコル・状況計算・記録権・テナント分離・データ移行のいずれにも触れない。`.claude/core-areas.json` の `guard_paths` にも `codex_run.py` は含まれない(research.md §3)
- **役割分担**: ステップ 1(コード+テスト)は /implement で Codex へ委任。ステップ 2(文書追随のみ・実装コード非接触)は Claude が直接行う(CLAUDE.md 役割分担 — ドキュメントは Claude の役割)

### 検証仕様(ステップ 1 の契約)

- **frontmatter 抽出の是正(前提)**: `parse_frontmatter()` の開始・終端認識を「**完全一致の単独行 `---`**(空白も許さない — docs-lint `scripts/check_docs_status.py:324,328` と同一文法)」へ是正する。現行の正規表現 `\n---` は `--- 任意文字列` の行も終端と誤認し、その後ろに 2 個目の `status:` 行を置くと status 検証を素通りする(P0 の迂回経路)。**偽終端行は本文の一部として扱われ、frontmatter が分断されないこと**(2 個目の status 行が重複として検出されること)をテスト #7 で固定する。status 検証は**この是正後の抽出結果と同じ frontmatter 本文**に対して行う(独自の生テキスト再読はしない — 抽出の分裂が迂回経路になるため)。なお `scripts/feature_status.py:349,:357` は strip 後一致(空白許容)だが、表示専用の既存許容として揃えない(2 節「やらないこと」参照)
- **判定手順**(`scripts/feature_status.py:301-307` と同一手順・同一正規表現リテラル。import 共有はしない — スクリプト独立性を維持し、相互参照コメントで対応を固定):
  - 抽出済み frontmatter 本文を `splitlines()` し、各行に候補判定 `^status\s*:`(match)を適用。候補行がちょうど 1 行であること — 0 行(欠落)・2 行以上(重複)は拒否
  - 候補行が `^status:\s*(active|in-review)(?:\s+#.*)?$` に fullmatch すること — 不一致(不正値・コロン前空白等の崩れた文法)は拒否
  - 値が `active` であること — `in-review` は拒否し差し戻し往復手順へ誘導
  - CRLF は `read_text()`(universal newlines)+ `splitlines()` により判定前に除去される(feature_status.py と同挙動)— テストで固定
- **挿入点**: `cmd_implement()` の frontmatter パース直後・承認検証の**前**(`codex_run.py:223` の手前)。差し戻し再開時(status: in-review・承認: 済)に状態系の誘導を承認系エラーより先に出すため。`--resume` の有無にかかわらず全検証が走る現行構造は維持(status 検証は resume 分岐より前)
- **拒否メッセージ**(既存 `die()` 書式の慣行「何が不正か(実値)。どうすべきか(誘導)(設計書 節番号)」に従う):
  - in-review: 「計画書が in-review(PR 段階)。修正の再開は先に plan frontmatter を `status: active` に戻す — /pr の**差し戻し**手順(設計書 6.1 差し戻しの往復)」相当。**stderr に「差し戻し」を必ず含める**(テストのアサート対象)
  - 欠落・重複・不正値: 「計画書の status 行が不正(<欠落|重複|実値>)。`status: <active|in-review>` をちょうど 1 行(設計書 7.1-5)」相当。**stderr に「status」を必ず含める**
  - いずれも `die()` 経由(stderr・exit 2)
- 既存の implement 系テスト fixture は全て `status: active`(単独行終端)記入済みのため後方互換(research.md §5)

### 実装ステップ(コミット単位 — 設計書 6.1 段階実装)

| # | ステップ(何を作るか) | 合格条件(このステップの検証方法) |
| --- | --- | --- |
| 1 | `codex_run.py`: frontmatter 開始・終端認識の是正(完全一致の単独行 `---`)+ `cmd_implement()` へ「検証仕様」どおりの status 機構検証を追加 + モジュール docstring の使い方行(`:4,7`)へ status 検証を追随(implement 限定の文言)。`tests/test_hooks.py` のラッパー検証節に 6 節の表のケース全件の回帰テストを追加 | リポジトリルートで `uv run pytest tests/` が全件 green(6 節の新規ケースを全件含む・既存テストは無修正)。差分が `codex_run.py`・`tests/test_hooks.py` のみ |
| 2 | 設計書 6.1/8.4/9.2 の節更新(`:250` 列挙追記・`:264` 注記削除・`:423` 追随・`:504`/`:507` 追記・変更履歴表 1 行)+ `docs/README.md` の現行化(確認結果の明記を含む)+ 正本外追随 4 件(CLAUDE.md / implement/SKILL.md / finalize-doc/SKILL.md / plan-template.md — 3 節の宣言どおり) | `python scripts/check_docs_status.py` green・設計書から残余リスク注記が消えている・diff が 3 節の宣言範囲のみ |

## 5. DoD(受け入れ基準)

<!-- Notion タスクの DoD と同期(2026-08-10 取得)。項目 4 は計画レビュー 1 周目 P1-3 で追加 — 承認時に Notion 側 DoD へも追記して同期する -->

- [ ] `codex_run.py implement` が計画書 frontmatter の `status` を検証し、`active` 以外(in-review 等)なら実行を拒否して差し戻し往復手順(/pr の差し戻し節)へ誘導する
- [ ] tests/test_hooks.py に拒否・誘導の回帰テストを追加する
- [ ] 設計書 6.1(ラッパー機構検証の列挙)を追随する(節更新)
- [ ] 3 節で宣言した正本反映(6.1/8.4/9.2 の列挙・説明の追随・`:264` 注記削除・変更履歴表追記)・正本外追随 4 件(CLAUDE.md・implement/SKILL.md・finalize-doc/SKILL.md・plan-template.md)・`docs/README.md` の現行化(確認結果の明記を含む)が同一 PR に含まれている

## 6. テスト計画

- 種別: **ハーネス単体テスト**(pytest — 設計書 8.3 `:407`・CI `harness` ジョブ `:560`)。製品コード非接触のため NFR-019 の一致性・越境・E2E・故障系は対象外
- 方式: `tests/test_hooks.py` ラッパー検証節の既存 `run_wrapper()` → `returncode == 2` + stderr キーワード方式。**通過系は「status 検証を通過して次の検証(未承認)エラーに到達する」ことで判定する**(codex 本体は起動しない経路のみ — 既存節の規律)

| # | ケース | 期待 |
| --- | --- | --- |
| 1 | `status: in-review`(承認: 済・worktree 等は有効) | 拒否(exit 2)・stderr に「差し戻し」 |
| 2 | `status: in-review`・`承認: 未`・`--resume`(セッションファイルなし) | 拒否・stderr に「差し戻し」を含み、「未承認」「セッション」を**含まない**(status 検証が承認・resume より先に走る契約の固定 — P1-1) |
| 3 | status 行なし | 拒否・stderr に「status」 |
| 4 | status 候補行 2 行(重複) | 拒否・stderr に「status」 |
| 5 | 不正値 `status: merged` | 拒否・stderr に「status」 |
| 6a | 文法崩れ `status : active`(コロン前空白) | 拒否・stderr に「status」(候補 1 行だが厳格不一致) |
| 6b | 文法崩れ `status: activeX` | 同上 |
| 7 | 終端偽装: frontmatter 内に `--- 任意文字列` 行 → その後に 2 個目の `status:` 行 → 完全一致の `---` | 拒否・stderr に「status」と「重複」を含み、「未承認」「worktree」を**含まない**(偽終端で frontmatter が分断されず、2 個目の status 行が重複として検出される — P0 回帰の実証。2 周目 P1-2) |
| 8 | 通過系: `status: active # 行末コメント` + `承認: 未` | status 検証を通過し「未承認」で拒否(stderr に「status」「差し戻し」が**出ない**) |
| 9 | 通過系: CRLF 改行の plan(`status: active`・`承認: 未`)— fixture は `write_bytes()` で `\r\n` を実書き込み | 同上(CRLF が判定を壊さない — P1-2) |
| 10 | 空白付き delimiter: 開始行・終端行それぞれ `--- `(末尾スペース)/ `---\t`(パラメトライズ。`status: active`・`承認: 未` を記入) | 拒否・stderr に「frontmatter」を含み「未承認」に到達しない(完全一致文法の回帰 — strip 実装への後退防止。3 周目 P1-1 補完) |

- 後方互換: 既存 implement 系テスト(fixture 全件 `status: active`)が無修正で green のままであること
