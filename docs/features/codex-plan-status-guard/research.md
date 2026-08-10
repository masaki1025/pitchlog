---
feature: codex-plan-status-guard
type: research
date: 2026-08-10
---

# 調査メモ: codex_run.py への plan status 機構強制(in-review のまま /implement を拒否)

行番号の基準: develop @ 1b344bc(本 worktree の分岐点)。調査は spec-checker / decision-tracer / Explore の 3 並列 + 単独報告典拠の原典確認(finalize-doc/SKILL.md・設計書 6.1/7.6)による。

## 問い

1. codex_run.py の現行実装のどこに、何を検証として足すべきか(挿入点・パース・拒否メッセージ・誘導先)
2. 設計書・規則との整合はとれるか。設計書 6.1 のどこを節更新すべきか。そのゲートは PR レビューで足りるか
3. 過去の決定(TSK-203 の PO 判断・差し戻し往復ライフサイクル・--resume・fast path)と矛盾しないか
4. 回帰テストはどこにどう足すか

## 結論(要約)

- 本タスクは設計書 v1.3 が「既知の残余リスク」として受容記録した欠落の解消そのもの(`docs/development/dev-harness-design-2026-08-07.md:264` が追跡タスクとして本タスクの Notion URL を名指しし「解消時に本注記を削除する」と予告済み)。**矛盾する過去決定はない**
- 原因は「`--resume` が検証をスキップする」のではなく「**status 検証がそもそも存在しない**」こと(codex_run.py 内に `status` への言及 0 件。`--resume` は全検証を通過後に分岐する)。挿入点は `cmd_implement()` の検証列(`.claude/scripts/codex_run.py:222-245`)
- in-review のまま再実装する正規導線は存在しない(差し戻し修正は「先に active へ戻す」が正 — `.claude/skills/pr/SKILL.md:43`・設計書 `:263`)。既存テスト fixture は全て `status: active` 記入済みで後方互換
- 未決 4 点は「未解決・申し送り」に列挙(①設計書更新のゲート判定〔PO 判定事項〕②パーサ厳格度 ③/finalize-doc の in-review 前提との緊張 ④cmd_fast への波及可否)

## 詳細と典拠

### 1. 決定経緯(なぜこのタスクか)

- 発端: TSK-203(feature-status)の反対側レビュー 2 周目 P1 ③「in-review のまま /implement 可能(機構強制なし)」— リポ内記録は 1 行要約のみ(`docs/worklog/2026-08-10-feature-status.md:38`。指摘原文はリポ内に無し — 後述)
- PO 判断(2026-08-10): 「③codex_run.py の status 機構強制は**別タスク起票**(本 PR は導出・表示まで — 承認済み計画の成立条件「codex_run.py 無改修」を維持)」(`docs/worklog/2026-08-10-feature-status.md:39`、起票記録 `:45`)
- 正本側の受容記録(本件の中核典拠・全文): 「**既知の残余リスク(v1.3 で受容を記録)**: `codex_run.py implement` は plan の `status` を機構検証しない — `in-review` のまま実装を起動できる(差し戻し往復は手順統制)。補償統制 = /pr の差し戻し手順(先に active へ戻す)+ 現在地導出での顕在化(…)。機構強制(`status: active` 以外の拒否)は追跡タスク(…)で解消し、**解消時に本注記を削除する**」(`docs/development/dev-harness-design-2026-08-07.md:264` — 6.1 の fast path 小節内の箇条書き)
- 設計原則との関係: 「規約は守られるべき」ではなく「規約は破れない」に寄せる(同 `:46`)。本タスクはこの原則の直接適用
- 「codex_run.py 無改修」制約は TSK-203 の計画スコープに閉じた成立条件(`docs/features/feature-status/plan.md:38`・DoD `:81`)であり、恒久規約ではない。PO 判断で明示的に別タスクへ送られたため本タスクと矛盾しない

### 2. 現行実装(codex_run.py)の事実

- `cmd_implement()`(`.claude/scripts/codex_run.py:214-257`)の検証順: 引数(:217)→ plan 実在(:219)→ frontmatter パース(:222)→ **承認「済」**(:223-225)→ worktree 値・実在・親ディレクトリ名(:226-229)→ 重さ分類(:230-232)→ ステップ表(:233-236)→ branch 文法(:237-239)→ worktree 登録(:240-242)→ ブランチ一致(:243-244)→ 同一リポジトリ(:245)→ モデル決定(:246)→ プロンプト(:247)→ sandbox 安全キー(:250)→ `--resume` 時のみ `.codex-session` 実在(:251-255)
- **`--resume` は検証をスキップしない**: :215-216 でフラグ抽出後、全検証を無条件通過してから分岐。「in-review のまま実装できる」の機構的根拠は **status 検証の不存在**(`status` / `in-review` への言及 0 件 — grep 確認済み)
- 拒否時の挙動: `die()`(:44-46)= `codex_run: エラー: {msg}` を stderr へ・`sys.exit(2)`。メッセージ書式の慣行 = 「何が不正か(実値を括弧で埋込)。どうすべきか(誘導スキル名)(設計書 節番号)」。実例: 「計画書が未承認(承認: {approval})。/plan のレビューと人間承認を先に(設計書 6.1)」(:225)
- frontmatter パーサ `parse_frontmatter()`(:76-86): 正規表現でブロック抽出 → 行走査で `":"` 1 回 split・`v.split("#")[0].strip()` で行末コメント除去。**重複キーは後勝ちで黙って採用・値の語彙検証なし・サイズ上限なし**。`status` キーは dict に入るが未参照
- 対照(厳格版の先行実装): `scripts/feature_status.py:18-19` `STATUS_LINE_RE = re.compile(r"^status:\s*(active|in-review)(?:\s+#.*)?$")`・候補行がちょうど 1 行でなければ解析失敗(:302-307)・機構読取キーの重複拒否(:24-35, :316-319)・8KiB 上限(:15)
- サブコマンドは 4 つ(:321-334): `implement`(plan 検証あり・workspace-write)/ `fast`(**plan.md を読まない** :260-274)/ `research`(read-only)/ `review`(read-only)。fast・research・review は plan 検証なし

### 3. 設計書・規則の関連規定

- 6.1 の機構検証列挙(節更新の対象): 「**計画承認前に `/implement` は実行できない**(`codex_run.py` ラッパーが計画書の承認ステータスを機構検証し、未承認なら実行を拒否する)…」(`dev-harness-design-2026-08-07.md:250`)。status は列挙に含まれていない。9.2 側の列挙「計画承認・worktree・sandbox・モデル対応表 9.4」(`:504`)も同様
- status ライフサイクル: 2 値 `active → in-review`・merged を Git に置かない(`:262`)。**差し戻しの往復**: 「修正の再開時は**先に plan を `in-review → active` に戻し**(…)修正・検証完了で `active → in-review` に戻す」・fast からの昇格は `status: active`・`実行方式: 通常`・`承認: 未` へ一括(`:263`)。in-review への遷移責務は /pr のクローズ処理(`.claude/skills/pr/SKILL.md:13`)。マージ後は in-review のまま残る(`.claude/skills/task-done/SKILL.md:25`)
- frontmatter 文法規則: plan.md は「複数キー・status 行末コメント可、`status: <active|in-review>` 行はちょうど 1 行」(`.claude/rules/docs.md:10`、設計書 7.1-5 `:315`)。拡張キー表は「重複・不正値…は導出が『不正値/解析失敗』として表示で顕在化 — **黙って解釈しない**」(`:273`)
- 更新ゲートの決定表: 「実装追随の節更新・変更履歴追記は PR レビューで足りる。**版繰り上げを伴う構造的変更**(…)はその部分だけ 7.3 の確定ゲート」(7.6-3 `:366` — 原典確認済み)。版を上げない追記でも変更履歴表への行追加は必要(v1.0 同版追記の実例 `:27`)
- codex_run.py 改修自体への特別統制: なし。`.claude/core-areas.json` の `guard_paths` に codex_run.py は含まれず(:3-9。`areas[].paths` は全て空)、コア領域 5 領域にも非該当 → 人間逐行確認の CI 必須化は機構上かからない。通常統制(Claude 一次レビュー or `review normal`・CI harness ジョブ green)のみ(設計書 `:290`・`:293`・`:560`)

### 4. 整合性判定(矛盾チェック)

- **in-review のまま再実装する正規導線は存在しない** — 通常経路の差し戻し修正は「先に active へ戻してから `--resume`」(`pr/SKILL.md:43`)、fast の差し戻しは `codex_run.py fast` 新規実行 or Claude 直修正(`--resume` 不使用・同 :43)、fast→通常昇格は一括遷移(設計書 `:263`)。マージ後の in-review plan は worktree 除去済みのため worktree 実在照合(:240-242)でも止まる → **新ガードはすべての正規導線と整合**
- `--resume` の存在意義(2 ステップ目以降・差し戻しの文脈維持 — 設計書 `:503`)と矛盾しない。前置条件(active 復帰)が機構化されるのみ
- fast path: `cmd_fast` は plan.md を読まないため implement 経路の status 検証は fast を壊さない(fast 適用時も plan は `status: active` のまま保持 — `.claude/skills/implement/SKILL.md:50`)
- 「in-review のまま実装」が正規容認された前例: なし(手順違反 + 残余リスクとして受容記録、の位置づけ)
- 要件書との関係: NFR-019(`docs/requirements/requirements-pitchlog-2026-07-22.md:677-680`)はプロダクトの CI テスト規約。ハーネス自身のテスト根拠は設計書側(「hooks は pytest で単体テストする(tests/ 全件)」`:407`・CI `harness` ジョブ `:560`)。要件書 2.2 Won't・改善台帳にハーネス関連項目なし
- 注意: 設計書 `:407` により、ドキュメントに固定テスト件数を書くのは規約違反(「固定件数は腐るため書かない — v1.3」)

### 5. テスト・CI の現状

- 配置: `tests/test_hooks.py:532` 以降がラッパー検証節(「codex 本体は起動しない経路のみ」)。`WRAPPER` 定義 :534、共通ヘルパ `run_wrapper()` :537-541(サブプロセス起動 → `returncode == 2` と stderr の日本語キーワードを検証)
- 拒否系テストの型の実例: `test_wrapper_rejects_unapproved_plan`(:550-559 — plan を tmp_path に書き `assert "未承認".encode("utf-8") in r.stderr`)・`test_wrapper_rejects_empty_step_table`(:667-680)
- **既存の implement 系 fixture は全て frontmatter に `status: active` を記入済み**(:552, :565, :580, :615, :673, :694, :710)→ status 検証を必須化しても既存テストは通る(後方互換)
- 実行: リポジトリルートで `uv run pytest tests/`(`pyproject.toml:12-13` testpaths・CI `.github/workflows/ci.yml:81`)。conftest.py は無し

### 6. 実装上の判断材料

- 挿入点: 承認検証(:223-225)の直前または直後が自然。「状態の検証(status)→ 承認の検証(承認)」の順なら差し戻し再開時のメッセージが先に出る — 順序は /plan で決定
- 誘導先の正確な表現: /pr スキルに「差し戻し」の独立見出しは無く、「レビュー導線の案内」節(`pr/SKILL.md:39`)配下の箇条書き「**差し戻しが発生したら**」(:43)が正。正本側の同義記述は設計書 6.1「差し戻しの往復」(`:263`)。die メッセージは既存書式の慣行に合わせる(§2)
- 設計書の節更新(実装追随)の候補: ①6.1 `:250` の列挙へ status 追記 ②6.1 `:264` の残余リスク注記を削除(本文が予告済み)③9.2 `:504` の列挙へ追記。周辺の追随候補(要スコープ判断): 8.4 `:423`・`CLAUDE.md:48`・`.claude/skills/implement/SKILL.md:9`・`.claude/skills/plan/SKILL.md:31`・`codex_run.py` docstring(:4,7)・`docs/development/templates/plan-template.md:3`(status 行コメントへの注記追加)
- codex_guard(`.claude/hooks/codex_guard.py`)は生 codex をブロックしてラッパーへ誘導する側で plan.md を読まない — 本変更の対象外。hooks 配線は `.claude/settings.json:56-73`(配線検査テスト `tests/test_hooks.py:58-71`)

## 未解決・申し送り

1. **設計書更新のゲート判定(PO 判定事項)**: 文言どおりなら 6.1 列挙追記 + :264 注記削除は 7.6-3 前段「実装追随の節更新」= PR レビューで可(設計書自身が解消時削除を予告済み)。ただし直近 2 件(v1.3 `:32`・ci-foundation v1.1 `docs/features/ci-foundation/plan.md:31`)は「当初 7.6-3 前段として起案 → PO 判定で版繰り上げ + 7.3 確定ゲートへ切替」の前例。「手順統制 → 機構強制」への格上げを構造的変更と見るかの明示規定は無い — /plan の「影響する正本」欄で判定を仰ぐ
2. **パーサ厳格度**: codex_run.py の現行パーサは重複 status 行を後勝ちで黙って採用し得る。`feature_status.py` の厳格判定(ちょうど 1 行・語彙 `active|in-review` のみ)と割れると「implement は通るが導出は解析失敗」等の不整合が起きる。「黙って解釈しない」(`:273`)に照らすと status 検証に限り厳格側(1 行・語彙検証)へ寄せるのが整合的だが、既存キー(承認・重さ分類等)への波及はスコープ拡大 — 検証範囲を /plan で確定する
3. **/finalize-doc との緊張(原典確認済み)**: `finalize-doc/SKILL.md:16` は周回カウンタ更新先の plan を「status が active|in-review」で解決する = in-review での確定ゲート実行を許容する前提。確定ゲート周回でコード修正(Codex 差し戻し)が必要になった場合(前例: `docs/worklog/2026-08-10-feature-status.md:42`)、新ガード下では先に active へ戻す往復(`pr/SKILL.md:43`)が必要になる。挙動は既存規定 `:263` と整合するが、finalize-doc スキル側にその前置の明文が無い — スキル文書への 1 行追記をスコープに含めるか申し送りにするか /plan で判断
4. **cmd_fast への波及可否**: fast は plan.md を読まないため本 DoD(implement のみ)の対象外が自然。fast の差し戻し再開は status in-review のまま `cmd_fast` で行われ得る(既存決定に該当記述なし — 新たな決定事項になるため、入れるなら明示の判断が要る)
5. **P1-3 指摘原文の所在**: リポ内は 1 行要約のみ(`docs/worklog/2026-08-10-feature-status.md:38`)。全文は Notion タスクまたはレビュー出力ファイル(リポ外)の可能性(推測)。計画上は Notion タスク本文の記載(DoD・背景)で十分
