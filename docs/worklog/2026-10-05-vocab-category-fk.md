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
- 2026-10-07: PR #98(data-model v0.6)のマージを受け、develop(`1fdf1eec` — #97・#98 を含む)を取り込み(`4ded6a44`・衝突なし)
- 2026-10-07: **ステップ 3**(`5cb46677`): Claude が data-model.md 10-3 節の ⚠ 項を是正済みの記録へ・変更履歴 1 行(v0.6 据え置き・実装追随)・`docs/README.md`(日付 2026-10-07)を書き、Codex が封印 2 つを取り直し(Claude が `sha256sum` / `git hash-object` で一致を確認)。受入突合シートは `--carry-judgments-from 4ded6a44` で再生成 — N3 が 99 → 101 行(本書の書き換えで「変えない」の出現が 2 つ増えた)。新しい 2 行(出現 001 = 変更履歴の行・出現 080 = 「3-4 節は変えない」)は対象外、番号ずれの 89 行は 3 列一致で旧判定を戻した → **人間承認(2026-10-07)** → amend。期待行数を追随
- 2026-10-07: `codex_run.py review normal`(正本の差分)→ **P2 1 件**: 「層をまたぐ誤参照」は 10-3 の層の定義と食い違う(試合区分・在籍区分はどちらもシステム固定の層)→ 「システム固定の層の中で区分をまたぐ誤参照」へ直し、封印を取り直して amend(シートは不変)。他の観点 A〜D は指摘なし
- 2026-10-07: 取り込み後の確認: backend 全件(DB を含む)1336 passed / 4 skipped・alembic 3 点 OK / ルート `tests/` 2927 passed・ruff・ty・shared-preconditions・frozen-baselines(--invariants-only)OK(コミット後に実行)
- 2026-10-07: 受入シートの旧判定の理由にある data-model.md の行番号参照 13 か所は、**develop の時点で既に約 25 行ずれている**(例: 「§4-3 冒頭(:637)」の実際は :662)。本 PR の起因ではないので触れない
- 2026-10-08: 共有の `/tmp`(7.7GB の tmpfs)が `/tmp/pytest-of-ymdms` 7.4GB で満杯になり、ルート `tests/` の実行が出力を失った。10-05〜10-06 の古い basetemp(約 4.5GB・走行中のものは無し)を削除して再実行。TSK-236 タブへ連絡(同タブの実行は無事)
- 2026-10-09: `/pr` の直前に develop が進んだ(#99・#102・#103 — #103 が data-model.md と封印 2 つを変更)。**未 push の履歴を組み直す `reset --hard` は自動モードで拒否** → 人間判断で「上に積んでマージ」。マージ `9726aa63` で衝突 4 ファイルを解決(変更履歴は両方の行を残し TSK-480 の行を 2026-10-09 で先頭へ / README の索引は develop 側に TSK-480 の追随を足す / 封印 2 つは取り込み後の data-model.md から `sha256sum`・`git hash-object` で取り直し)。受入シートの再生成は差分 0・空欄 0(承認のやり直し不要)
- 2026-10-09: 取り込み後の確認: ルート `tests/` 28342 passed(#102 で xdist 並列)・ruff・ty・shared-preconditions・frozen-baselines OK / backend 全件(DB を含む・`-c pyproject.toml --cov`)1336 passed / 4 skipped・ruff format/check・ty OK・alembic upgrade head / current --check-heads / check OK

## 結果(/pr 時点)

- **実装**: migration 0029 で `system_vocabularies` を参照する 3 本の FK に `category` を拘束(参照元の定数列 + 参照先の `UNIQUE (key, category)` + `MATCH FULL` の複合 FK・FORCE RLS 下でも全行を見る事前検査)。ORM・schema manifest・既存テストを追随。新しい DB テスト 12 件と変異 11 種の再現
- **正本への反映**: data-model.md 10-3 節の ⚠ 項を是正済みの記録へ(実装追随・v0.6 据え置き)・変更履歴・`docs/README.md`・封印 2 つ・受入突合シート(判定の引き継ぎは人間承認 2 回)
- **ハーネス運用評価台帳**: **既存候補 2 件へ実測を追記**(コミット前の全試験が迂回の走査を見逃した — 別タスクで 3 例目 / 共有の `/tmp` が 3 日で再び満杯)。**新規候補は立てない・`H-*` は採番しない**(いずれも既存候補の再発で、二重計上を避けるため。採番は PO 判断)

## 決定

- 【裁定 2026-10-06・山田正輝】ゲート = 実装追随で PR レビュー(data-model.md は 10-3 ⚠ 項の記録更新のみ・版据え置き・主キーは残す)/ 射程 = system 層 3 FK のみ(admin 4・tenant 7 は別タスク)— research.md「判断点」
- ステップ 1 の是正: `test_alembic_migrations.py` のテナント内複合 FK 検査(tenant_id を必ず含むことの assert)を「参照先が tenant_id を持つ FK」に限定し、除外した FK の参照先が manifest で tenant_id を forbidden_columns に持つことを別に照合する(Codex 2 回差し戻し — 1 回目は恒真の assert だった)

## 未決・次の一歩

- **PR の人間逐行確認で見てもらう点**: 上記のテナント内複合 FK 検査の限定(テナント分離の検査の意味に関わる)
- ステップ 3 は PR #98 のマージを待ってから行った(人間判断 2026-10-07 — 取り込みと封印の取り直しを 1 回で済ませるため)
- 次: PR の CI・敵対レビュー・人間の逐行確認 → マージ。PR 後に U-M1・TSK-479・U-G1 の状態を測り直す。マージ後に使い捨ての DB コンテナ `pitchlog-tsk480-db` を名指しで撤去する
- admin / tenant 層の同型非拘束 → TSK-489 起票済み
