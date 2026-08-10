---
paths:
  - "docs/**"
---

# docs 規約(ハーネス設計書 7 章の要約)

- **1テーマ1正本**。他文書からは相対リンクで参照し、内容を複製しない
- 正本は冒頭に**変更履歴表**(版・日付・変更内容・状態)を持つ。状態: draft → in-review → approved(廃止時 superseded)
- 正本は先頭に**固定文法の frontmatter**を持つ: **先頭からちょうど 3 行**(1 行目 `---`・2 行目 `status: <draft|in-review|approved|superseded>`・3 行目 `---`)。**追加キー・空行・行末コメント不可**。`docs/features/*/plan.md` は別規則(複数キー・status 行末コメント可、`status: <active|in-review>` 行はちょうど 1 行)。**現在状態の唯一の正は frontmatter**(冒頭の変更履歴表は遷移履歴)、索引 docs/README.md は派生表示 — 不一致は CI の docs-lint(`scripts/check_docs_status.py`)が失敗させる
- approved への遷移は **/finalize-doc**(敵対レビュー → 人間承認)のみ。ゲートを飛ばさない
- `docs/legacy/` は版固定 — **変更禁止**(hooks でもブロックされる)
- `docs/features/<slug>/` は **1 feature = 1 ディレクトリ**の一時作業域(plan.md〔契約 — 機構が読む状態とステップ表はここのみ〕・research.md〔調査〕・design.md〔詳細設計・任意〕等を集約。`docs/features/` 直下に単発ファイルを置かない)。plan の状態は active → in-review の2値(差し戻し再開時は active へ戻す — 設計書 6.1)。恒久的な知見は正本へ移す
- `docs/worklog/` は記録であり正本ではない(ゲート不要・形式より継続)
- 変更のたびに索引 `docs/README.md` を現行化する
