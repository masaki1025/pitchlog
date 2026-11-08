---
feature: mvp-p3-finite-play-insert
status: draft
branch: feature/mvp-p3-finite-play-insert-20261109
created: 2026-11-09
計画レビュー周回: 0
---

# P3保存の有限INSERT列と既stamp/RLSを接続する

基点d8f7adda。短P3run4は42501/persist_p3_projection body214のpublic.play_rows INSERT*で停止。直前の原評価/全値guardを通過しており、今回D03不足を根因とはしない。ORM41列に対しfnowner INSERTは0、policyもSELECT/UPDATEのみ。rootが必要最小INSERT/RLSの技術具体化をPO委任内で許可。

編集は新backend/src/pitchlog/authz/p3_play_row_insert_product.py、既p3_projection_sql.py/p3_projection_paged_sql.pyのINSERT描画接合、専用tests/test_p3_play_row_insert_product.pyと必要owned対向test、本計画のみ。first_ball_productへの呼出接合/正式assets/canonical再生成/台帳はrootへpacket、他WTは非編集。artifact71/normal49上の源候補とmain859/0050の正式接合を分離する。

- ORM41列を構造pinし、hidden_at/legacy_row_identifier/import_batch_id/migration_unverifiedはINSERT権限を与えない。他37列だけ既SELECT行へINSERT追加、grant optionなし。
- 非paged/pagedのINSERT*を同じ37列の明示INSERT/SELECTへ置換。入力の保護3値はJSON null、migration値はJSON falseを厳密要求し、欠測/非正準は拒否。DB defaultの同clean値と既全41列stamp照合を維持する。
- fnowner INSERTpolicyは既同型tenant/session述語を使い、全41列/同xid/nonce/ready→consumedの既真正P3stampを必須に保つ。WITH CHECK時点はBEFORE trigger後なのでready条件をpolicyへ重複実装しない。既trigger・guard弱化/全面GRANTなし。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 有限列SQL/認可宣言候補を固定 | 列型/default/保護4列/既ACL exact、余剰拒否、両INSERT同列・stamp不変、対象pure/型/Ruff、root非作者用packet |
| 2 | root正式helper接合後のowned検証 | 同sourceで正常受理ACK/実変更/receipt/capsule、direct/未admission/別TX/越境/保護値拒否を実PG確認。PGはrootslot明示後だけ |

既200+prefixだけのshort結果を保存成功へ上げず、実受理は既AcceptedChangeResponse/confirmationと保存原本へ束縛する。2時評価時点に未実証を残件として明示する。
