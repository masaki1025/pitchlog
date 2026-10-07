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
- 2026-10-07: ステップ 2(Codex 委任)→ `backend/tests/db/test_system_vocab_category_fk_db.py`(①〜⑥・パラメタ込み 12 件)。使い捨て postgres で 12 passed
- 2026-10-07: 変異の再現(scratchpad の書き換えスクリプトで migration 0029 を一時的に変え、必ず元に戻す — 戻った後の差分 0 を確認)。11 変異すべてで**狙った 1 件だけ**が red:

  | 変異 | red になった試験 |
  | --- | --- |
  | (a) FK を単列へ戻す(3 本を 1 本ずつ) | ① `test_head_rejects_cross_category_foreign_keys[<表>]` の当該表のみ |
  | (b) CHECK を外す(3 表を 1 表ずつ) | ② `test_category_columns_reject_wrong_values_and_null[<表>]` の当該表のみ |
  | (c) 事前検査の分岐を外す(3 分岐を 1 つずつ) | ④ `test_preflight_rejects_force_hidden_mismatch[<表>]` の当該表のみ(`DID NOT RAISE`)|
  | (d) `MATCH FULL` → `SIMPLE` / FK の列順を (category, key) に入れ替え | `test_schema_audit.py::test_schema_manifest_matches_catalog_and_cross_table_rules`(:884 の foreign_key 差分) |

  - (c) の失敗が `DID NOT RAISE` だったこと = **事前検査を外すと、FORCE RLS で所有者から隠れた区分違いの行が残ったまま 0029 の upgrade が通る**(FK 作成時の初期検証が隠れた行を見落とす)。事前検査の必要性を実測で確かめた(計画書 4-2 の根拠の裏付け)
- 2026-10-07: backend 全件(DB を含む・`-c pyproject.toml --cov`)1336 passed / 4 skipped・alembic 3 点 OK・ruff/ty OK
- 2026-10-07: **ステップ 1 是正**(f8b640f7): ルート `tests/` で `test_check_tenant_boundary_bypass.py` の 2 件が red — ステップ 1 の ORM の定数列 3 本の `server_default=text(...)` が TB005(変更行の `sqlalchemy.text`)。**ステップ 1 の確認時は走査がコミット前の HEAD を読んでいて見逃した**(U-A1 β worklog 2026-10-04 :182 と同じ落とし穴 — 迂回の走査はコミット後に回す)。Codex へ差し戻し → `literal_column("'<値>'")` へ(`server_default.arg` の文字列・DDL の DEFAULT は不変を確認)。是正後: 走査 2 件 green / schema_audit・新 DB テスト・往復 14 passed / alembic check OK / 非 DB 939 passed

## 決定

- 【裁定 2026-10-06・山田正輝】ゲート = 実装追随で PR レビュー(data-model.md は 10-3 ⚠ 項の記録更新のみ・版据え置き・主キーは残す)/ 射程 = system 層 3 FK のみ(admin 4・tenant 7 は別タスク)— research.md「判断点」
- ステップ 1 の是正: `test_alembic_migrations.py` のテナント内複合 FK 検査(tenant_id を必ず含むことの assert)を「参照先が tenant_id を持つ FK」に限定し、除外した FK の参照先が manifest で tenant_id を forbidden_columns に持つことを別に照合する(Codex 2 回差し戻し — 1 回目は恒真の assert だった)

## 未決・次の一歩

- **PR の人間逐行確認で見てもらう点**: 上記のテナント内複合 FK 検査の限定(テナント分離の検査の意味に関わる)
- ステップ 2(新 DB テスト・ミューテーション再現 (a)〜(d))→ ステップ 3(data-model 10-3・封印 2 つ・シート)
- admin / tenant 層の同型非拘束 → TSK-489 起票済み
