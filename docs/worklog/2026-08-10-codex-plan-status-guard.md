---
date: 2026-08-10
topic: codex_run.py に plan status の機構強制を追加(in-review のまま /implement を拒否)
branch: feature/codex-plan-status-guard
---

# 作業ログ: 2026-08-10 codex_run.py に plan status の機構強制を追加

## やったこと

- /task-start: Notion タスク TSK-205 を取得(既存起票・DoD 3 点設定済み)→ `feature/codex-plan-status-guard` ブランチ + worktree 作成(origin/develop 起点・HEAD 1b344bc)→ 計画書雛形・本 worklog 作成
- /investigate: 3 並列(spec-checker / decision-tracer / Explore)+ 単独報告典拠の原典確認 → `docs/features/codex-plan-status-guard/research.md` に統合。要点: 本タスクは設計書 6.1 :264 の既知残余リスク解消そのもの(注記が解消時削除を予告済み)・矛盾する過去決定なし・`--resume` は検証をスキップせず原因は status 検証の不存在・既存テスト fixture は全て `status: active` 記入済みで後方互換

- /plan: 計画書 6 節を記入(research.md 未解決 4 点の起案: ①ゲート = 7.6-3 前段で起案し PO 確認 ②status 検証は feature_status.py と同一リテラルの厳格判定 ③finalize-doc へ前置 1 行をスコープ内 ④cmd_fast 波及はスコープ外)
- 計画レビュー 1 周目(review normal・terra max): **判定「要修正」— P0×1 / P1×5 / P2×2 — 全 8 件採用**(周回 0 → 1)。P0 = frontmatter 終端の曖昧さ(`\n---` が行全体を検証せず `--- 任意文字列` も終端扱い → 2 個目の status 行でガード迂回可能。feature_status.py:354 の単独行終端と分裂)→ 原典確認のうえ「終端認識の是正」をスコープ例外として追加。P1 = --resume×順序のテスト固定 / splitlines 手順の明文化と CRLF・コメント・文法崩れのケース追加 / DoD の宣言回収(項目 4 追加)/ ゲート起案の根拠明記+格上げ時手順の具体化 / README「常に現行化」への是正。P2 = finalize-doc 前置文言を in-review 限定に / テンプレ等の文言を implement 限定に

- 計画レビュー 2 周目: **判定「要修正」— 新規 P0×0 / P1×2 / P2×2**(1 周目 8 件は全件「反映済み」と検証)→ 全 4 件採用(周回 1 → 2)。P1-1 = delimiter 文法の 3 系統不一致 → **ラッパーを docs-lint(完全一致 `---`)側へ揃える形で採用**(feature_status.py の空白許容は表示専用の既存差異として受容を計画に記録 — 3 系統統一はタスク DoD を超えるため不採用の変形)/ P1-2 = テスト #7 の期待を「『status』『重複』を含み『未承認』『worktree』を含まない」に固定 / P2-1 = 設計書・docstring の追記文言を implement 限定に / P2-2 = #6 を 6a/6b に分割・#9 は write_bytes で CRLF 実書き込み

- 計画レビュー 3 周目: **判定「要修正」— 新規指摘なし・2 周目 2 件の反映不足補完 ×2 — 全件採用**(周回 2 → 3)。①空白付き delimiter(`--- `/`---\t`)拒否の回帰テスト追加(ケース #10 — strip 実装への後退防止)②設計書の追随漏れ 2 箇所(8.4 :423「承認済み計画書」→「status: active かつ承認済み」・9.2 :507 コマンド注記へ status 追記)を宣言範囲へ追加

- 計画レビュー 4 周目(収束確認): **判定「承認可」— 新規指摘なし**・3 周目補完 2 件(#10 テスト・設計書 8.4/9.2 追随)は「反映済み」と検証 → 収束(指摘反映を伴う周回 = 3・収束確認周はカウント外)。人間承認へ

## 決定

- status 検証の判定手順は `feature_status.py:301-307` と同一(候補 `^status\s*:` ちょうど 1 行 → `^status:\s*(active|in-review)(?:\s+#.*)?$` fullmatch → 値 active)。正規表現は同一リテラル+相互参照コメント(import 共有はしない)
- frontmatter の開始・終端は**完全一致の単独行 `---`**へ是正(docs-lint = check_docs_status.py:324,328 と同一文法。ラッパーが lint の拒否する形式を受け入れない fail-closed 整合)。status 検証は是正後の同一抽出結果に対して行う(P0 対応)
- feature_status.py の delimiter 空白許容との残余差異は受容(表示専用・強制に関与しない。揃えるのは DoD 超過)

- **PO 承認(2026-08-10)**: 計画書を承認(承認: 済〔2026-08-10・徳光 尋弥〕に更新・起票コミット)
- **PO 判定(2026-08-10)**: 設計書更新のゲート = **7.6-3 前段(PR レビュー)で確定**(research.md 未解決①の解消。根拠 = v1.3 :264 が本タスクによる解消と注記削除を予告済み。格上げ条項は不発動)

- /implement ステップ 1(2026-08-11): Codex 委任(terra max)— frontmatter 抽出を完全一致 `---` へ是正 + `require_active_plan_status()` を承認検証の前に挿入 + 回帰テスト追加。検証: diff 宣言 2 ファイルのみ・既存テスト無修正(+166/-0)・**213 passed を独立再実行で確認** → コミット `abb1137`(ステップ 1/2)
- /implement ステップ 2(2026-08-11): Claude 直(文書のみ)— 設計書 6.1 列挙追記・残余リスク注記削除・8.4/9.2 追随・変更履歴 1 行(v1.3 同版・PR レビューゲート)+ README 最終更新現行化 + 追随 4 件(CLAUDE.md・implement/finalize-doc スキル・plan テンプレ)。検証: check_docs_status.py green・注記 0 件・213 passed → コミット `a0a0165`(ステップ 2/2)
- 総合検証: 全 diff = 計画宣言範囲のみ・DoD 4 項目充足・feature_status.py 導出「実装完了・/pr 前(2/2)」を実機確認(ドッグフーディング)

## 未決・次の一歩

- /pr で PR 作成(正本反映はステップ 2 で実施済み — /pr の宣言突合で確認される。Notion DoD 項目 4 は承認時に同期済み)
