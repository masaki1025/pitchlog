---
date: 2026-10-05
topic: TSK-480 — system_vocabularies の FK に category 強制を入れる
branch: feature/vocab-category-fk
---

# 作業ログ: 2026-10-05 TSK-480 — system_vocabularies の FK に category 強制を入れる

## やったこと

- 2026-10-05: /task-start(develop 27ff94eb 起点)。Notion TSK-480 を進行中へ
- 2026-10-06: /investigate(4 本並列)→ `docs/features/vocab-category-fk/research.md`
- 2026-10-06: /plan(敵対レビュー 5 周 — 1〜4 周否決・全反映、5 周目承認可)→ 人間承認(c8f06edb)
- 2026-10-07: ステップ 1(Codex 委任)→ bcc2b7ee。使い捨て postgres で backend 全件 1323 passed / 1 failed / 4 skipped → 是正後に該当テスト green。alembic upgrade head / current --check-heads / check OK。ルート tests/ はシートの 1 件を除き green → シート再生成後 test_orm_acceptance_sheets.py 13 passed
- 2026-10-07: 受入突合シートを `--carry-judgments-from c8f06edb` で再生成。判定が空になった 34 行(3 列とも旧行と一致)は旧判定を戻し、変更 4 表・10-3 に当たる持ち越し 39 行とあわせて人間承認 → ステップ 1 へ amend(差分は N7 の列契約 3 行のみ)

## 決定

- 【裁定 2026-10-06・山田正輝】ゲート = 実装追随で PR レビュー(data-model.md は 10-3 ⚠ 項の記録更新のみ・版据え置き・主キーは残す)/ 射程 = system 層 3 FK のみ(admin 4・tenant 7 は別タスク)— research.md「判断点」
- ステップ 1 の是正: `test_alembic_migrations.py` のテナント内複合 FK 検査(tenant_id を必ず含むことの assert)を「参照先が tenant_id を持つ FK」に限定し、除外した FK の参照先が manifest で tenant_id を forbidden_columns に持つことを別に照合する(Codex 2 回差し戻し — 1 回目は恒真の assert だった)

## 未決・次の一歩

- **PR の人間逐行確認で見てもらう点**: 上記のテナント内複合 FK 検査の限定(テナント分離の検査の意味に関わる)
- ステップ 2(新 DB テスト・ミューテーション再現 (a)〜(d))→ ステップ 3(data-model 10-3・封印 2 つ・シート)
- admin / tenant 層の同型非拘束 → TSK-489 起票済み
