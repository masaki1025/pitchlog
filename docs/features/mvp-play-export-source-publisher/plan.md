---
feature: mvp-play-export-source-publisher
status: active
branch: feature/mvp-play-export-source-publisher
承認: PO委任によるCodex/root（2026-11-07、対象6a0e910e、計画SHA a077123c667480f74da4123bedfca90d3809be5cd0fd71f771a1802068a30c86）
重さ分類: コア領域
計画レビュー周回: 1
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

root技術補足を採用: 正式assetへindexes節/新kindを追加しない。3indexとCREATE TABLEはsource構造metadataとして比較するだけで、BODIES tableは既producer同型のRLS/REVOKEのみ。関数本文は唯一providerの全byteを保持し、role/schema/0047の配置はrootに委ねる。

ステップ1: 原典SHA0e8b9fd6…b86ca、declarations table1/function4/policy2/columnACL19、BODIES26を生成。全4関数の本文は唯一provider/候補末尾と全byte一致。CREATE TABLE/3indexはsource_structure metadataだけに保持し、認可table bodyはRLS/REVOKEのみ。専用positive/原典byte変更拒否4件、Ruff/Ty成功。正式asset/registry/0047/共有WTの変更0。次にfield/body/余剰/各provider属性の変異対向を追加する。

ステップ2結果: 専用48件/22.80s、対象Ruff/Ty成功。owner/SECURITY/volatility/search_path/引数・戻り型/GRANT OPTION/余剰SQL/全body byteの変異を拒否する。別providerが他関数を混在させてdict合成で上書きする変異も、各源の閉集合で拒否する。対象tableのPUBLIC向け余剰表GRANTをroleだけで見逃さないよう、既正式節acl_expectations=[]を明示してobject_id/IDで全値照合する（table1/function4/policy2/columnACL19/ACL0、BODIES26）。新schema/role/grantやindexes正式節を追加しない。

原典/出力証拠は ~/.cache/pitchlog/play-export-source-publisher-author-20261107/{checks.json,declarations.json,body-sha256.json,source-structure.json,pytest.log}。BODIESは公式ELEMENT header付与前のraw publisher mapとしてvalidateへ渡す。全体asset中の当該profileが無い場合はFalse、部分/余剰/属性変更はValueError。全母集合の受理や正式登録を代行しない。

残件はrootの非作者sourceレビュー、0047/model/current startup、正式catalog/registry/seal/7.7、実gameからのCSV出力/故障・越境・大容量、必須CI/通常統合。本枝はsource供給だけで、実DB/実画面/製品CSV完成とはしない。編集は指定3path、唯一provider/候補SQL/正式資産/他WTは不変更。
