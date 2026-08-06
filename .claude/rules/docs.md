---
paths:
  - "docs/**"
---

# docs 規約(ハーネス設計書 7 章の要約)

- **1テーマ1正本**。他文書からは相対リンクで参照し、内容を複製しない
- 正本は冒頭に**変更履歴表**(版・日付・変更内容・状態)を持つ。状態: draft → in-review → approved(廃止時 superseded)
- approved への遷移は **/finalize-doc**(敵対レビュー → 人間承認)のみ。ゲートを飛ばさない
- `docs/legacy/` は版固定 — **変更禁止**(hooks でもブロックされる)
- `docs/features/<slug>/` は一時文書(status: active → merged)。恒久的な知見は正本へ移す
- `docs/worklog/` は記録であり正本ではない(ゲート不要・形式より継続)
- 変更のたびに索引 `docs/README.md` を現行化する
