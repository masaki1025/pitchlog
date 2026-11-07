---
feature: mvp-play-export-source-publisher
status: draft
branch: feature/mvp-play-export-source-publisher
承認: 未（rootのPO委任レビュー待ち）
重さ分類: コア領域
計画レビュー周回: 0
確定ゲート周回: 0
---

# 毎球CSVの唯一SQL源を正式宣言producerへ接続する

起点c4be7454。root指示の製品接合単位で、既候補SQL/生成関数の本文を複製・変更せず、閉じたdeclarations/BODIESを供給する。0047/migration/model/current startup・正式catalog/registry/7.7はroot所有で、本枝では実行しない。

編集は次の3pathだけ:
- `backend/src/pitchlog/authz/play_export_product.py`（新規source publisher）
- `backend/tests/test_play_export_product.py`（新規専用検査）
- `docs/features/mvp-play-export-source-publisher/plan.md`

## 供給interfaceと原典

`connection_declarations()`で既producer同型の `(declarations, bodies)` を返す。`validate(asset, bodies)`で対象宣言/本文を全値照合し、対象の部分/余剰/属性変更を拒否する。必要ならrootの既producer接合形へ揃えるが、共有publisher/registryは編集しない。

原典は`docs/features/ud2-csv-export/candidates/play_export_snapshots.sql`のtable/RLS/列ACL/3index/末尾read_writer_play_export_substitute、既`play_export_writer_product.candidate_function_body/candidate_save_body/candidate_install_sql`の2関数、既`play_export_source_read_product.candidate_read_bundle`の1関数のみ。各function本文は唯一源から取得し、owner/SECURITY DEFINER/言語/volatility/search_path/引数/戻り値/ACLを閉検査する。table SELECT10列/INSERT9列をexactに保持し、既role/schemaへ勝手に権限を増やさない。SQL内の野球計算・集計式を新しく記述しない。

## ステップ

| # | 作業 | 検証/終了条件 |
|---|---|---|
| 1 | source publisherと対応する専用試験 | 10列read/9列insert、table/RLS/policy/3index、4関数の全body/属性/ACLが唯一源に一致。原典の未知/欠落/二重/形の変化は閉拒否。入力SQL本文を編集しない |
| 2 | 部分/余剰/変異の対向・型/lint・固定受渡し | 元資産positive、owner/属性/body/列ACL/policy/indexの変異negative。Ruff/Ty/専用pytest成功。固定HEAD/全差分SHA/原典SHAをrootへ渡す。正式受理・実DB・通常統合とは分離する |

rootの計画レビュー後に実装へ移る。対象source以外の編集・DDL適用・共有DB/他WTの変更は行わない。本人逐行確認/署名/P6 blindを代記しない。必要な意味判断を増やさず、技術具体化と限定非作者確認は既PO委任として追跡する。
