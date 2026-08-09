---
paths:
  - "docs/**"
---

# docs 規約(ハーネス設計書 7 章の要約)

- **1テーマ1正本**。他文書からは相対リンクで参照し、内容を複製しない
- 正本は冒頭に**変更履歴表**(版・日付・変更内容・状態)を持つ。状態: draft → in-review → approved(廃止時 superseded)
- 正本は先頭に**固定文法の frontmatter**を持つ: 1 行目 `---`・`status: <draft|in-review|approved|superseded>` をちょうど 1 行・`---` で終端。**状態の機械可読の正は frontmatter**とし、索引 docs/README.md の状態表記と一致させる(CI の docs-lint = `scripts/check_docs_status.py` が検査)
- approved への遷移は **/finalize-doc**(敵対レビュー → 人間承認)のみ。ゲートを飛ばさない
- `docs/legacy/` は版固定 — **変更禁止**(hooks でもブロックされる)
- `docs/features/<slug>/` は **1 feature = 1 ディレクトリ**の一時作業域(plan.md・research.md 等を集約。`docs/features/` 直下に単発ファイルを置かない)。plan の状態は active → in-review の2値。恒久的な知見は正本へ移す
- `docs/worklog/` は記録であり正本ではない(ゲート不要・形式より継続)
- 変更のたびに索引 `docs/README.md` を現行化する
