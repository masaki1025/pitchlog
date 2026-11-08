---
feature: mvp-p3-finite-play-insert
status: active
branch: feature/mvp-p3-finite-play-insert-20261109
created: 2026-11-09
計画レビュー周回: 1
承認: PO委任Codex主担当/root（対象9ad40e65/plan1dc5da69、2026-11-09、記録01:54 JST）
---

# P3保存の有限INSERT列と既stamp/RLSを接続する

基点d8f7adda。短P3run4は42501/persist_p3_projection body214のpublic.play_rows INSERT*で停止。直前の原評価/全値guardを通過しており、今回D03不足を根因とはしない。ORM41列に対しfnowner INSERTは0、policyもSELECT/UPDATEのみ。rootが必要最小INSERT/RLSの技術具体化をPO委任内で許可。

編集は新backend/src/pitchlog/authz/p3_play_row_insert_product.py、既p3_projection_sql.py/p3_projection_paged_sql.pyのINSERT描画接合、専用tests/test_p3_play_row_insert_product.pyと必要owned対向test、本計画のみ。first_ball_productへの呼出接合/正式assets/canonical再生成/台帳はrootへpacket、他WTは非編集。artifact71/normal49上の源候補とmain97の859/正常0049への接合を分離する。0050はrootshared8316別候補でP1留保・未統合、将来追随は別に記録する。

- ORM41列を構造pinし、hidden_at/legacy_row_identifier/import_batch_id/migration_unverifiedはINSERT権限を与えない。他37列だけ既SELECT行へINSERT追加、grant optionなし。
- 非paged/pagedのINSERT*を同じ37列の明示INSERT/SELECTへ置換。入力の保護3値はJSON null、migration値はJSON falseを厳密要求し、欠測/非正準は拒否。DB defaultの同clean値と既全41列stamp照合を維持する。
- fnowner INSERTpolicyは既同型tenant/session述語を使い、全41列/同xid/nonce/ready→consumedの既真正P3stampを必須に保つ。WITH CHECK時点はBEFORE trigger後なのでready条件をpolicyへ重複実装しない。既trigger・guard弱化/全面GRANTなし。

| # | 作業 | 完了条件 |
| --- | --- | --- |
| 1 | 有限列SQL/認可宣言候補を固定 | 列型/default/保護4列/既ACL exact、余剰拒否、両INSERT同列・stamp不変、対象pure/型/Ruff、root非作者用packet |
| 2 | root正式helper接合後のowned検証 | 同sourceで正常受理ACK/実変更/receipt/capsule、direct/未admission/別TX/越境/保護値拒否を実PG確認。PGはrootslot明示後だけ |

既200+prefixだけのshort結果を保存成功へ上げず、実受理は既AcceptedChangeResponse/confirmationと保存原本へ束縛する。2時評価時点に未実証を残件として明示する。


## step1候補（実接合/PG未成立）

源providerは41列の型/nullable/defaultをsha256:6d4e2abc…へ固定し、37列の既SELECT宣言/描画へINSERTを追加する純overlayとINSERT policy1行を返す。保護4列は不変更。両P3 SQLfactoryは同helperで4入力のstrict JSON null/falseを要求し、同じ37列INSERT/SELECTへ置換。その他SQLを逆置換で全byte復元し、既stamp/admission消費部分を変更しない。rootのfirst_ball_product呼出接合と正式helper描画は未適用で、正式assetへの直接変更0。

専用8pure5.33秒、全Ty/対象Ruff0。初回collectionはORM.schema=None（implicit public）をpublic文字列と誤認した源guardで止まり、既ORMのNone/publicだけを正規化してsource構造pinを維持した。型検査のFromClause属性2件は実Table型確認を追加し是正、失敗log保全。root非作者/正式生成/正常受理ACK・実capsule/越境・direct/別TXのowned対向は未成立。PGは引続きGame担当後のroot明示slotまで実行しない。
