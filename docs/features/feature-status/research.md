---
feature: feature-status
type: research
date: 2026-08-10
---

# 調査メモ: feature 現在地の導出機構 + plan.md 3 ファイル分割の影響範囲

## 問い

1. TSK-203(plan frontmatter 拡張 + `scripts/feature_status.py` + SessionStart 注入)の修正箇所はどこか — plan.md を読む・書く・検証する既存機構(スクリプト・スキル・フック・CI・テスト)の全数
2. PO 追加要望「plan.md の役割別 3 ファイル分割」の影響範囲はどこか。TSK-203 の DoD「保存が必要な事実は plan.md frontmatter で持つ(新ファイルを作らない)」と矛盾しないか
3. 過去決定(state.yaml 不採用・状態管理の正 = frontmatter・7.6 決定表 ほか)との整合と、必要な改訂ゲートはどれか

調査体制: spec-checker・decision-tracer・Explore の 3 並列(legacy-analyst は旧システムとの接点なしのため除外 — ci-foundation と同判断)。主要典拠は統合時に原典再確認済み。

## 結論(要約)

1. **3 分割は DoD「新ファイルを作らない」と矛盾しない** — 同 DoD の射程は「保存型 state.yaml = 状態の第 2 正本を作らない」(docs/worklog/2026-08-10-ci-foundation.md:42)であり、feature ディレクトリ配下の補助資料追加は設計書 6.1 が明示的に許容(dev-harness-design:246)
2. ただし**分割の自由度は機構上低い**: frontmatter(承認・worktree・重さ分類・branch・status)と実装ステップ表は plan.md 1 ファイルに残すことが必須(codex_run.py:214-245 が単一ファイル引数で機構検証・check_docs_status.py:405-410 と session_context.py:76-88 は `*/plan.md` 固定 glob)
3. **推奨は A 案**「plan.md = 機械可読の契約(frontmatter + 6 節骨格)を維持、詳細設計を design.md へ、調査は research.md(既存)」— パーサ 3 本・スキル群は無改修で成立し、設計書は 6.1 の節更新(PR レビュー)で足りる可能性が高い。6 節を物理分配する B 案は設計書 v1.3 + /finalize-doc + 23 ファイル同時改訂で非推奨
4. TSK-203 本体の修正箇所は「新規 scripts/feature_status.py + tests」「session_context.py(注入追加 + **先頭 800 文字制限の解消が P0**)」「plan-template.md のキー追加」「設計書 8.3 表ほか節更新」。frontmatter キー追加は既存 2 パーサと後方互換
5. 欠落規定が 2 点あり /plan で決める: 導出結果×Notion 不一致の裁定(**feature_status.py は Notion を書き換えない**を宣言)/ 非対話時の縮退方向(fail-open + 縮退明示)

## 詳細と典拠

### §1 TSK-203 の修正箇所(全数)

#### 新規: `scripts/feature_status.py` + `tests/test_feature_status.py`

- 置き場は `scripts/`(「Python・OS 非依存」— dev-harness-design:150。`.claude/scripts/` は Codex ラッパー専用)
- テストは NFR-019 の前例準拠(requirements:677-680・dev-harness-design:547・.github/workflows/ci.yml:70-81 の harness ジョブ = `uv run pytest tests/`・ci-foundation/plan.md:123-127)。**CI はディレクトリ一括実行のためテストを書かなくても緑になる — 計画書 6 節での明示が唯一の担保**
- 再利用できる既存部品:
  | 部品 | 出典 |
  | --- | --- |
  | `git()`(timeout=10・失敗時空文字) | .claude/hooks/session_context.py:19-26 |
  | `list_worktrees()`(worktree list --porcelain パーサ) | .claude/hooks/session_context.py:29-43 |
  | `parse_frontmatter()`(plan frontmatter の dict 化) | .claude/scripts/codex_run.py:76-86 |
  | `has_filled_step_row()`(ステップ表検出 — bool のみ。行内容抽出は要拡張) | .claude/scripts/codex_run.py:57-73 |
  | `parse_table_cells()` / `is_table_separator()`(Markdown 表パーサ) | scripts/check_docs_status.py:104-127 |
  | `worktree_branch()` / `git_common_dir()`(ブランチ・リポ同一性照合) | .claude/scripts/codex_run.py:96-137 |
  | fail-closed な JSON 読み込み | scripts/core_guard.py:58-98 |
- PR 状態: スクリプトから gh を叩く既存実装は**ゼロ**(スキル手順のみ — task-done/SKILL.md:13 の `gh pr view <branch> --json state` が唯一の前例)。`gh pr view` / `gh pr list` は許可済み(settings.json:21-24)、`gh api` は ask(:30-32)
- Notion 照合: スクリプトからの Notion API 呼び出しは**ゼロ**。「対話時のみ」は設計書 11.3 の明文どおり(dev-harness-design:624「Notion MCP は対話セッションの認証に依存するため、CI・ヘッドレス実行からは使わない前提で設計する」)。ステータス語彙・遷移対応の機械可読正本は `.claude/notion-map.json`(:24-27 語彙・:28-62 transitions)— **ハードコードは 11.1 違反**(dev-harness-design:587)。人間運用に開放された 5 選択肢(未着手・準備中・保留中・着手可・作業中 — dev-harness-design:599-600)を異常扱いしないこと

#### 変更: `.claude/hooks/session_context.py`(+ tests/test_hooks.py)

- 現行: SessionStart 登録は 1 本のみ(settings.json:95-104)。注入は①ブランチ+未コミット件数(:55-61)②進行中 feature(:63-90)③最新 worklog 冒頭 15 行(:92-101)。全経路 fail-silent
- 注入方式は 2 択: (1) settings.json に 2 本目の hook 追加(複数登録の実績なし) / (2) session_context.py の `lines` へ統合(:103)。**(2) が配線テスト(tests/test_hooks.py:56-69)・出力テスト(:319-329)の変更最小**
- **P0 — 先頭 800 文字制限**: `plan.read_text()[:800]`(session_context.py:78)の範囲内に `status:`(:81 部分一致)と `^branch:`(:85-87 完全一致)が無いと**進行中 feature が無言で消える**。ci-foundation 実測で frontmatter+前文 = 447 文字・残余 ≒ 350 文字(Explore 実測)— TSK-203 のキー追加で枯渇し得る。**frontmatter 拡張と同一 PR で読み取り方式を frontmatter ブロック全体の走査に改修し、回帰テストで固定する**(hooks のテスト必須 — dev-harness-design:394)
- hooks 制約: Python 標準ライブラリのみ(dev-harness-design:383)・`/usr/bin/python3` 絶対パス起動(:394)・timeout 設計(session_context.py:19-26 の `timeout=10` に相当)

#### 変更: `docs/development/templates/plan-template.md`

- frontmatter 8 キー(:1-10)が文法の実質的正本。拡張キーを追記(意味・記入者コメント)
- キー追加は既存 2 パーサと**後方互換**: codex_run.py:82-85 は任意キーを dict 化するだけ、check_docs_status.py の `^status\s*:`(:22)は `status_xxx:` 形式に誤マッチしない(Explore 検証)

#### 変更(節更新): 正本・派生文書

- 設計書 8.3 表 session_context 行(dev-harness-design:392)へ注入項目追加、6.1/7.6-4 へ導出機構の記述追記 — **実装追随の節更新 = PR レビューで可**(7.6-3 dev-harness-design:353)
- plan frontmatter の**文法規約**そのもの(7.1-5 dev-harness-design:302)は「複数キー可・status 行ちょうど 1 行」のみ規定 → キー追加は規約文言に触れない。**拡張キーの意味を規約化する場合のみ**構造的変更の判定対象(判定宣言は計画書 3 節で — 7.6-1 dev-harness-design:351)
- docs/README.md:20(SessionStart 説明)の追随

#### 設計上の欠落(既存規定になし — /plan で決定必須)

1. **導出結果 × Notion の不一致裁定**: 明文規定なし(spec-checker C-3)。近接規定は「正本は Git」(dev-harness-design:121)・7.4 分担(:331-337)・完了の組導出(:260)のみで優先順位なし。7.1-5 の前例(:302「黙ってどちらかが勝つのではなく、修正されるまでマージしない」)に倣い「**不一致を表示で顕在化し、feature_status.py は Notion を書き換えない**」を計画書で宣言する。**6.4 の例外終端「PR closed + Notion 取り下げ」は正常**(dev-harness-design:290)— 異常判定しないこと
2. **非対話時の縮退方向**: 一般規定なし。前例は fail-open(format_on_save — dev-harness-design:391・session_context.py:4「失敗時は沈黙」)と fail-closed(core-guard :546・/research 秘密走査 :654)に分かれる。表示系ツールとして **fail-open + 「Notion 未照合」を表示に明示**(無言縮退の禁止 — NFR-015 の類推適用前例 dev-harness-design:436/619)を計画書 4 節で決定し 8.3 表へ反映
3. **frontmatter 拡張キーの具体設計はリポ内に存在しない**(Explore 確認 — TSK-203 の由来は worklog:42 の 1 行のみ)。**注意(P1)**: 正本の finalize-doc 状態を plan frontmatter へ複製すると 7.1-1「内容を複製しない」(dev-harness-design:298)と DoD 3 の趣旨(二重正本回避)に反する。plan に置いてよいのは **feature 作業自身の進行事実**(計画レビュー周回数・敵対レビュー周回数・差し戻し回数等)に限り、正本の status は当該正本の frontmatter から導出する(spec-checker C-4)

### §2 plan.md 実物の密度分析(分割動機の裏付け)

| plan | 全体 | 肥大箇所 | 実測 |
| --- | --- | --- | --- |
| ci-foundation/plan.md | 127 行 | **4 節(実装方針 3,625 字 + ステップ表 1,976 字)= 全体の約 55%**。frontmatter 固定文法仕様・core-guard 実行契約・ci.yml 仕様など「詳細設計」が畳み込まれている(:69-95) | Explore 実測 |
| harness-baseline-merge/plan.md | 67 行 | 2 節「やること」に統制条項が凝縮(:26 単独で約 900 字) | Explore 実測 |

→ 肥大の主因は「**詳細設計の記述**が計画書に同居していること」。frontmatter・ステップ表・DoD などの機械可読部分は肥大していない。

### §3 3 ファイル分割の判定

#### 矛盾しない根拠

- DoD 3「新ファイルを作らない」の由来 = 「保存型 state.yaml は二重正本のため不採用」(docs/worklog/2026-08-10-ci-foundation.md:42)。禁じるのは**状態の第 2 の保存場所**
- feature ディレクトリの複数ファイル構成は既に許容: 標準構成「plan.md(必須)/ research.md / .codex-session / **補助資料(命名自由で任意追加)**」(dev-harness-design:246)・7.2 表(:313)・rules/docs.md:13
- 分割先で内容を複製せず相対リンク参照なら 7.1-1(dev-harness-design:298)とも整合

#### 分割で壊してはいけない不変条件(機構検証済み)

1. `/implement` に渡す 1 ファイル(plan.md)に `承認`・`worktree`・`重さ分類`・`branch` と「実装ステップ」表が同居(codex_run.py:214-245・:57-73 — 外へ出すと全実装拒否)
2. `status: <active|in-review>` 行は plan.md にちょうど 1 行(check_docs_status.py:304-342)。分割ファイルは `*/plan.md` 固定 glob(:405-410)の**検査対象外** — 状態を分割先へ移すと検査が空洞化し 7.1-5 の担保が消える
3. plan.md 先頭に status/branch を保つ(session_context.py:78-87 — §1 の 800 文字問題と同根)
4. 節番号参照の同期: 3 節=/pr(pr/SKILL.md:20)・/sync-docs(sync-docs/SKILL.md:13,24)、4 節=/implement(implement/SKILL.md:13)、5 節=PR テンプレ(pull_request_template.md:15)、6 節=/plan(plan/SKILL.md:11-18)+ 設計書 6.1(:238-245)
5. `.codex-session` は plan.md の親ディレクトリ(codex_run.py:89-90 — ファイル名非依存で分割耐性あり)
6. fast path は plan.md をメタデータとして参照(implement/SKILL.md:50・pr/SKILL.md:25)
7. lychee が `docs/features/**` を走査(ci.yml:48-50)— 分割ファイル間の相対リンク切れは即 CI red

#### A 案(推奨): 役割分担 — plan.md は契約、記述を逃がす

| ファイル | 役割 | 状態 |
| --- | --- | --- |
| plan.md | **機械可読の契約**: frontmatter(全キー)+ 6 節の骨格(3 節表・4 節ステップ表・5 節 DoD は本体維持、詳細は design.md へ相対リンク) | 既存(スリム化) |
| research.md | 調査メモ(/investigate・/research の統合先) | 既存のまま |
| design.md | **詳細設計・検討メモ**(ci-foundation 4 節に畳み込まれていた類の記述)— 補助資料枠 | 新設(テンプレ追加) |

- **パーサ 3 本(codex_run.py・check_docs_status.py・session_context.py)とスキル群・PR テンプレは無改修**(不変条件をすべて満たす)
- 修正ファイル: plan-template.md(4 節に「詳細は design.md へ」の導線)/ design.md テンプレ新設(templates/)/ plan/SKILL.md・task-start/SKILL.md(生成・記入手順)/ 設計書 6.1:246 の標準構成へ design.md 追記 + 索引:30・rules/docs.md:13 の追随
- ゲート: 6.1:246 は**任意追加が既に許容されている補助資料の標準化**であり、必須構成 6 節(:238-245)に触れない → **実装追随の節更新(PR レビュー)と判定できる**。ただし 6.4 で「節更新」判定を撤回し版繰り上げへ切り替えた前例(dev-harness-design:30)があるため、**最終判定は計画書 3 節で宣言し PO 承認に委ねる**

#### B 案(非推奨): 6 節を 3 ファイルへ物理分配

- 設計書 6.1「plan.md の必須構成」(:238-245)の**構造的規約変更** → v1.3 版繰り上げ + /finalize-doc 必須(7.6-3 :353。前例: 7 章規約 v1.0→1.1 — ci-foundation/plan.md:54)
- P0 改修: codex_run.py(:57-73,214-245)・check_docs_status.py(:405-410,304-342)・session_context.py(:76-88)・plan-template.md・tests/test_hooks.py 7 箇所(:344-512)・tests/test_check_docs_status.py 5 箇所(:100-237)
- P1 追随: スキル 7 本(task-start:22・plan:9-28・implement:13-50・pr:13-32・sync-docs:13-24・task-done:13-25・investigate:18)
- P2 規約: 設計書多数節(:224,238-248,260,302,313,351-354,392,409-414,489,494-495)・rules/docs.md:10,13・README.md:30・AGENTS.md:15・CLAUDE.md:44・**PR テンプレ(:6,9,15,26 — guard_paths 該当につき core-guard の人間逐行確認が発火** .claude/core-areas.json:3-9)
- P3 波及: 既存 plan 2 本の新旧混在整合(7.6-4「マージ後の計画書は履歴として閉じる」:354)・guard_common.py:18-26(ラッパー引数形・`#` 含みパス不可)
- 合計 20 超ファイルの同時改訂。**密度低減という目的に対して過大**

### §4 ゲート判定まとめ(7.6-3 — dev-harness-design:353)

| 変更対象 | ゲート | 根拠 |
| --- | --- | --- |
| 設計書 8.3 表・6.1/7.6-4 への実装追随追記(TSK-203) | PR レビュー | 7.6-3 前段 |
| 設計書 6.1:246 標準構成への design.md 追記(A 案) | PR レビュー(**PO 判定次第で finalize** — 6.4 の判定撤回前例 :30) | 7.6-3・先例 |
| 設計書 6.1 必須構成の分配(B 案) | **/finalize-doc + v1.3** | 7.6-3 後段・先例 ci-foundation/plan.md:54 |
| plan-template.md・design.md テンプレ | PR レビュー(templates はゲート表 7.2:306-315 の対象外・docs-lint 除外 check_docs_status.py:15-19。**テンプレ専用のゲート規定は存在しない = 不明**) | decision-tracer 調査 |
| .claude/skills/*・scripts/*・hooks/* | PR レビュー(正本ゲート対象外)。ただし **pr/SKILL.md・PR テンプレ・ci.yml は guard_paths** → core-guard 逐行確認チェック発火 | .claude/core-areas.json:3-9・dev-harness-design:546 |
| rules/docs.md・docs/README.md | PR レビュー(7 章の要約・派生表示)。設計書本体と**同一 PR** で(7.6-2 :352) | rules/docs.md:1・dev-harness-design:302 |

### §5 事実訂正(記録)

- Notion タスク本文の「v0.15 P1-4『merged を Git に置かない』」は**出典の取り違え** — 正しくは **v0.10 の P1-4**(dev-harness-design:18 変更履歴・:260 本文)。v0.15 の P1 群はステップ表構造検証・branch 必須化など(:23)
- 設計書内の表記揺れ: 変更履歴 v0.10 は「plan 状態の 3 値化」(:18)、本文は「2値」(:260)— 次回設計書改訂時の掃除候補
- 改善台帳の現物は I-27 まで(improvements-from-baseball-scoring.md:196-211)。開発プロセスへの言及は「追記候補」の 1 件のみで本件に接点なし

## 未解決・申し送り

- **A 案 / B 案の採否と、A 案のゲート判定(節更新 or 版繰り上げ)は PO 決定事項** — /plan の 3 節で宣言して承認を得る
- frontmatter 拡張キーの具体設計(キー名・値文法・記入責務)は /plan で新規に起こす。**正本の finalize 状態を複製しない**(feature 作業自身の進行事実に限る)を設計原則に
- feature_status.py の導出レベル設計: hook(非対話)= git のみ / 対話 = +gh(allow 済み範囲)+Notion(MCP)— の段階縮退と「未照合」の明示表示
- Notion タスク本文の出典訂正(v0.15 → v0.10)は /plan 時のタスク更新に含める
- 800 文字制限の解消は frontmatter 拡張と**同一 PR・回帰テスト付き**が必須(進行中 feature の無言消失は導出機構の自己否定になるため)
