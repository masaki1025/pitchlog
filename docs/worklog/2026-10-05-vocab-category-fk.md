---
date: 2026-10-05
topic: TSK-480 — system_vocabularies の FK に category 強制を入れる
branch: feature/vocab-category-fk
---

# 作業ログ: 2026-10-05 TSK-480 — system_vocabularies の FK に category 強制を入れる

## やったこと

- 2026-10-05: /task-start(develop 27ff94eb 起点)。Notion TSK-480 を進行中へ
- 2026-10-06: /investigate(4 本並列)→ `docs/features/vocab-category-fk/research.md`

## 決定

- 【裁定 2026-10-06・山田正輝】ゲート = 実装追随で PR レビュー(data-model.md は 10-3 ⚠ 項の記録更新のみ・版据え置き・主キーは残す)/ 射程 = system 層 3 FK のみ(admin 4・tenant 7 は別タスク)— research.md「判断点」

## 未決・次の一歩

- admin / tenant 層の同型非拘束 → TSK-489 起票済み
- /plan で計画書を起こす(重さ分類はコア領域の見込み — TSK-475 と同じ当てはめ)
