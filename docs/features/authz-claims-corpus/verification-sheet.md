# TSK-312 逐行確認用 突合シート(機械生成 — H-12 代替統制)

- 生成元: `attribution.json`(基準 `41884a9` との最終成果物 diff・1193 変更単位・帰属なし 0)
- 生成器: `gen_attribution.py`(再実行で再現可能)。裁定の正: `step1-rulings.json` / 指摘全文: `step1-findings.md`
- 確認の観点: 各群の変更が「裁定・既知・機械的追随」の説明と一致するか。**A 群(裁定 F 項目)を優先して読む**

## サマリ

| 群 | 帰属 | 件数 |
| --- | --- | --- |
| A | F1: 端末内の認可判定点(FR-012 E3) | 13 |
| A | F2: FR-034 7 操作の読み取り可視性への誤分類 | 16 |
| A | F3: FR-041 招待の操作認可の principal state 固定 | 25 |
| A | F4: 即時トークン失効の cache 判定点欠落 | 24 |
| A | F5: 分類規則の罠が全件無効 | 2 |
| A | F6: closed-world 宣言の機械的閉包なし | 8 |
| A | F7: HTTP 逆向き閉包なし(166 件無結線) | 190 |
| A | F8: FR-020〜032 の design-origin・無出典 | 18 |
| A | F10: FR-035/037 管理経路の universe 不在と probe_executable 誤認 | 6 |
| A | F12: SECURITY DEFINER 関数が宣言 ACL で実行不能 | 19 |
| A | F13: app_role の制御表直接 DML による迂回 | 107 |
| A | F15: FR-041 比較パラメータの誤分類 | 7 |
| A | F16: インデント表の採取欠陥(既知) | 1 |
| B | known:indent-extraction: インデント表の採取欠陥(既知) | 12 |
| B | known:exception-cells: NFR-018 例外表 2 セル(TSK-233 申し送り) | 2 |
| B | known:changelog-row: 要件書 変更履歴の追記行 | 5 |
| C | mechanical:atomic-follow: 機械的追随(atomic/oracle 参照の追随) | 456 |
| C | mechanical:reseal: 機械的追随(digest・manifest・lock・seal) | 264 |
| C | mechanical:schema-follow: 機械的追随(schema シグネチャ) | 1 |
| C | mechanical:step-tests: テスト(負例・期待件数・走査一般化) | 17 |

## F1: 端末内の認可判定点(FR-012 E3)(13 件)

- `claim-mutant-map.json:claims:FR-012/list_item-013` — modified(共帰属: F1, mechanical:atomic-follow)
- `check_authz_catalog.py:@@ -642,6 +758,128 @@ def _validate_rule_applicability(` — hunk(共帰属: F1, F15, F2, F3, F4, F6, mechanical:digest)
- `check_authz_catalog.py:@@ -657,7 +895,54 @@ def decision_projection(claim: dict[str, object]) -> dict[str` — hunk(共帰属: F1, F15, F2, F3, F4, F6, mechanical:digest)
- `check_authz_catalog.py:@@ -712,9 +1006,23 @@ def _validate_claim(` — hunk(共帰属: F1, F15, F2, F3, F4, F6, mechanical:schema-follow)
- `check_authz_catalog.py:@@ -745,7 +1058,23 @@ def _validate_claim(` — hunk(共帰属: F1, F15, F2, F3, F4, mechanical:schema-follow)
- `check_authz_catalog.py:@@ -757,7 +1086,16 @@ def _validate_claim(` — hunk(共帰属: F1, F15, F2, F3, F4, F6, mechanical:schema-follow)
- `check_authz_catalog.py:@@ -834,6 +1172,30 @@ def validate_catalog(` — hunk(共帰属: F1, F15, F2, F3, F4, F6)
- `check_authz_catalog.py:@@ -846,7 +1208,16 @@ def validate_catalog(` — hunk(共帰属: F1, F15, F2, F3, F4, F6)
- `check_authz_catalog.py:@@ -947,6 +1318,9 @@ def _validate_lock_structure(raw: object, catalog_path: str) ` — hunk(共帰属: F1, F15, F2, F3, F4, F6)
- `check_authz_catalog.py:@@ -959,16 +1333,75 @@ def _validate_lock_structure(raw: object, catalog_path: str` — hunk(共帰属: F1, F15, F2, F3, F4, F6)
- `check_authz_catalog.py:@@ -1089,11 +1522,21 @@ def _expect_closed_value(` — hunk(共帰属: F1, F15, F2, F3, F4)
- `check_authz_catalog.py:@@ -3176,11 +4226,8 @@ def validate_attack_tree(` — hunk(共帰属: F1, F13, F15, F2, F3, F4)
- `check_authz_catalog.py:@@ -3195,7 +4242,21 @@ def validate_attack_tree(` — hunk(共帰属: F1, F13, F15, F2, F3, F4)

## F2: FR-034 7 操作の読み取り可視性への誤分類(16 件)

- `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-005` — removed
- `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-005#operation-permission` — added
- `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-005#read-access` — added
- `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-006` — removed
- `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-006#operation-permission` — added
- `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-006#read-access` — added
- `claim-mutant-map.json:claims:FR-034/heading-002/list_item-005` — removed(共帰属: F2, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-034/heading-002/list_item-005#operation-permission` — added(共帰属: F2, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-034/heading-002/list_item-005#read-access` — added(共帰属: F2, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-034/heading-002/list_item-006` — removed(共帰属: F2, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-034/heading-002/list_item-006#operation-permission` — added(共帰属: F2, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-034/heading-002/list_item-006#read-access` — added(共帰属: F2, mechanical:atomic-follow)
- `requirement-claims.json:claims:FR-034/heading-002/list_item-005` — modified
- `requirement-claims.json:claims:FR-034/heading-002/list_item-006` — modified
- `requirement-claims.lock.json:decisions:FR-034/heading-002/list_item-005` — modified
- `requirement-claims.lock.json:decisions:FR-034/heading-002/list_item-006` — modified

## F3: FR-041 招待の操作認可の principal state 固定(25 件)

- `auth-catalog.json:entries:CATALOG:FR-041/list_item-006` — removed
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-006#capacity-constraint` — added
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-006#invitation-state` — added
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-006#issue-permission` — added
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-007` — removed
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-007#accept-permission` — added
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-007#acceptance-serialization` — added
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-007#capacity-constraint` — added
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-007#invitation-state` — added
- `claim-mutant-map.json:claims:FR-041/list_item-006` — removed(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-006#capacity-constraint` — added(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-006#invitation-state` — added(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-006#issue-permission` — added(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-007` — removed(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-007#accept-permission` — added(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-007#acceptance-serialization` — added(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-007#capacity-constraint` — added(共帰属: F3, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-007#invitation-state` — added(共帰属: F3, mechanical:atomic-follow)
- `requirement-claims.json:claims:FR-041/list_item-006` — modified
- `requirement-claims.json:claims:FR-041/list_item-007` — modified
- `requirement-claims.lock.json:decisions:FR-041/list_item-006` — modified
- `requirement-claims.lock.json:decisions:FR-041/list_item-007` — modified
- `route-registry.json:management_operations:accept_invitation` — modified
- `route-registry.json:management_operations:issue_invitation` — modified
- `route-registry.json:management_operations:revoke_invitation` — modified

## F4: 即時トークン失効の cache 判定点欠落(24 件)

- `auth-catalog.json:entries:CATALOG:FR-035/list_item-005` — removed
- `auth-catalog.json:entries:CATALOG:FR-035/list_item-005#principal-state` — added
- `auth-catalog.json:entries:CATALOG:FR-035/list_item-005#revocation` — added
- `auth-catalog.json:entries:CATALOG:FR-035/list_item-010` — removed
- `auth-catalog.json:entries:CATALOG:FR-035/list_item-010#password-state` — added
- `auth-catalog.json:entries:CATALOG:FR-035/list_item-010#revocation` — added
- `auth-catalog.json:entries:CATALOG:NFR-011/list_item-002` — removed
- `auth-catalog.json:entries:CATALOG:NFR-011/list_item-002#credential-state` — added
- `auth-catalog.json:entries:CATALOG:NFR-011/list_item-002#revocation` — added
- `claim-mutant-map.json:claims:FR-035/list_item-005` — removed(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-035/list_item-005#principal-state` — added(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-035/list_item-005#revocation` — added(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-035/list_item-010` — removed(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-035/list_item-010#password-state` — added(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-035/list_item-010#revocation` — added(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:NFR-011/list_item-002` — removed(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:NFR-011/list_item-002#credential-state` — added(共帰属: F4, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:NFR-011/list_item-002#revocation` — added(共帰属: F4, mechanical:atomic-follow)
- `requirement-claims.json:claims:FR-035/list_item-005` — modified
- `requirement-claims.json:claims:FR-035/list_item-010` — modified
- `requirement-claims.json:claims:NFR-011/list_item-002` — modified
- `requirement-claims.lock.json:decisions:FR-035/list_item-005` — modified
- `requirement-claims.lock.json:decisions:FR-035/list_item-010` — modified
- `requirement-claims.lock.json:decisions:NFR-011/list_item-002` — modified

## F5: 分類規則の罠が全件無効(2 件)

- `requirement-claims.json:classification_rules` — modified
- `check_authz_catalog.py:@@ -518,6 +630,10 @@ def _parse_classification_rules(raw: object) -> dict[str, Cla` — hunk

## F6: closed-world 宣言の機械的閉包なし(8 件)

- `requirement-claims.json:claims:FR-034/heading-001/paragraph-002` — modified
- `requirement-claims.json:claims:FR-034/heading-002/paragraph-001` — modified
- `requirement-claims.json:claims:FR-034/heading-002/paragraph-003` — modified
- `requirement-claims.lock.json:decisions:FR-034/heading-001/paragraph-002` — modified
- `requirement-claims.lock.json:decisions:FR-034/heading-002/paragraph-001` — modified
- `requirement-claims.lock.json:decisions:FR-034/heading-002/paragraph-003` — modified
- `check_authz_catalog.py:@@ -49,6 +61,7 @@ SOURCE_KINDS = frozenset(` — hunk
- `check_authz_catalog.py:@@ -732,6 +1040,11 @@ def _validate_claim(` — hunk(共帰属: F6, mechanical:schema-follow)

## F7: HTTP 逆向き閉包なし(166 件無結線)(190 件)

- `route-registry.json:claim_dispositions:APPENDIX-C/blockquote-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:APPENDIX-C/table_row-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:APPENDIX-C/table_row-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:APPENDIX-C/table_row-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:APPENDIX-C/table_row-010@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:APPENDIX-ITEM-A-5/blockquote-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:APPENDIX-ITEM-A-5/blockquote-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:APPENDIX-ITEM-A-5/paragraph-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-007/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-007/list_item-011@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-012/list_item-010@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-012/list_item-013@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-012/list_item-015@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-012/list_item-018@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-010@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-013/list_item-011@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-014/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-017/list_item-009@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-017/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-019/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-019/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-033/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-033/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-033/list_item-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-033/list_item-006@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-033/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-033/list_item-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/list_item-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/list_item-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/list_item-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/paragraph-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/paragraph-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/paragraph-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/paragraph-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/paragraph-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-010@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-011@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-012@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-013@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-014@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-022@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-001/table_row-023@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-005#operation-permission@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-005#read-access@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-006#operation-permission@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/list_item-006#read-access@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/paragraph-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/paragraph-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-002/table_row-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-003/paragraph-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-003/table_row-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-003/table_row-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/list_item-001@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/list_item-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/paragraph-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/paragraph-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-001@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-002@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-003@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-004@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-009@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/heading-004/table_row-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-034/list_item-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-005#principal-state@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-005#revocation@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-005#revocation@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-010#password-state@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-010#revocation@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-010#revocation@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-011@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-012@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-013@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-015@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-016@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-035/list_item-016@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-036/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-036/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-036/list_item-005@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-036/list_item-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-036/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-036/list_item-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-037/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-037/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-037/list_item-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-037/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-037/list_item-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-037/list_item-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-037/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-039/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-039/list_item-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-039/list_item-009@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-010@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-011@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-012@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-013@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-014#participant-authorization@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-014#request-validation@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-018@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-019@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-020@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:FR-041/list_item-021@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-009/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-010/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-010/list_item-004@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-010/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-011/list_item-002#credential-state@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-011/list_item-002#revocation@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-011/list_item-002#revocation@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-011/list_item-003@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-011/list_item-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-012/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-012/list_item-003@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-012/list_item-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-019/paragraph-001@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:NFR-019/paragraph-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-1.1/paragraph-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-1.1/paragraph-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-2.2/list_item-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-2.2/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-2.2/list_item-008@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-2.2/list_item-012@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/heading-001/list_item-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/heading-001/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/heading-001/list_item-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/heading-001/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/heading-001/list_item-005@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/heading-001/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/table_row-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/table_row-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/table_row-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-3/table_row-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-4.0-1/code_line-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-4.0-1/code_line-011@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-4.0-2/list_item-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-4.0-3/table_row-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-4.0-3/table_row-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-6.2/list_item-003@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-6.2/list_item-003@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-6.4/list_item-001@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-7.1/list_item-004@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-8/list_item-002@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-8/list_item-002@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-8/list_item-006@cache` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-8/list_item-006@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-9/table_row-007@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-9/table_row-011@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-9/table_row-012@http` — added(共帰属: F7, F9)
- `route-registry.json:claim_dispositions:SECTION-9/table_row-013@http` — added(共帰属: F7, F9)
- `check_authz_catalog.py:@@ -1109,6 +1552,21 @@ def _db_claims_by_id(catalog: dict[str, object]) -> dict[st` — hunk(共帰属: F7, F9)
- `check_authz_catalog.py:@@ -1198,6 +1656,90 @@ def _validate_design_provenance(raw: object, root: Path) ->` — hunk(共帰属: F7, F9)
- `check_authz_catalog.py:@@ -1230,6 +1772,7 @@ def validate_route_registry(` — hunk(共帰属: F7, F9)
- `check_authz_catalog.py:@@ -1479,10 +2022,32 @@ def validate_route_registry(` — hunk(共帰属: F7, F9)
- `check_authz_catalog.py:@@ -1820,6 +2385,21 @@ def _derived_lock_entries(` — hunk(共帰属: F7, F9)

## F8: FR-020〜032 の design-origin・無出典(18 件)

- `route-registry.json:routes:ROUTE:FR-020` — modified
- `route-registry.json:routes:ROUTE:FR-021` — modified
- `route-registry.json:routes:ROUTE:FR-022` — modified
- `route-registry.json:routes:ROUTE:FR-023` — modified
- `route-registry.json:routes:ROUTE:FR-024` — modified
- `route-registry.json:routes:ROUTE:FR-025` — modified
- `route-registry.json:routes:ROUTE:FR-026` — modified
- `route-registry.json:routes:ROUTE:FR-027` — modified
- `route-registry.json:routes:ROUTE:FR-028` — modified
- `route-registry.json:routes:ROUTE:FR-029` — modified
- `route-registry.json:routes:ROUTE:FR-030` — modified
- `route-registry.json:routes:ROUTE:FR-031` — modified
- `route-registry.json:routes:ROUTE:FR-032` — modified
- `route-registry.json:routes:ROUTE:MANAGEMENT:ACCEPT_INVITATION` — modified
- `route-registry.json:routes:ROUTE:MANAGEMENT:ISSUE_INVITATION` — modified
- `route-registry.json:routes:ROUTE:MANAGEMENT:REVOKE_INVITATION` — modified
- `check_authz_catalog.py:@@ -67,6 +80,15 @@ CHANNELS = frozenset({"screen", "export"})` — hunk
- `check_authz_catalog.py:@@ -1424,8 +1967,8 @@ def validate_route_registry(` — hunk

## F10: FR-035/037 管理経路の universe 不在と probe_executable 誤認(6 件)

- `claim-mutant-map.json:classification_rules` — modified(共帰属: F10, F13)
- `check_authz_catalog.py:@@ -83,6 +105,18 @@ FORBIDDEN_EVACUATED_IMPORT_TERMS = (` — hunk(共帰属: F10, F13)
- `check_authz_catalog.py:@@ -2584,6 +3301,267 @@ def _has_db_decision(claim: dict[str, object]) -> bool:` — hunk(共帰属: F10, F13)
- `check_authz_catalog.py:@@ -2705,26 +3683,52 @@ def validate_claim_mutant_map(` — hunk(共帰属: F10, F7, F9)
- `check_authz_catalog.py:@@ -2735,10 +3739,17 @@ def validate_claim_mutant_map(` — hunk
- `check_authz_catalog.py:@@ -2746,13 +3757,27 @@ def validate_claim_mutant_map(` — hunk(共帰属: F10, F7, F9)

## F12: SECURITY DEFINER 関数が宣言 ACL で実行不能(19 件)

- `ddl-elements.json:acl_expectations:ACL:probe_business_rows:shared_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_grants:management_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_grants:shared_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_groups:shared_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_invitations:shared_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_management_effects:management_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_memberships:management_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_memberships:shared_fn_owner` — added(共帰属: F12, F14)
- `ddl-elements.json:functions:apply_representative_grant_change` — modified(共帰属: F12, F14)
- `ddl-elements.json:predicates:PREDICATE:CURRENT_TENANT_OWNS_ROW` — added(共帰属: F12, F14)
- `ddl-elements.json:schemas:management_private` — modified(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2067,6 +2647,7 @@ def validate_ddl_elements(raw: object, root: Path) -> dict[s` — hunk(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2227,6 +2808,27 @@ def validate_ddl_elements(raw: object, root: Path) -> dict[` — hunk(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2247,12 +2849,27 @@ def validate_ddl_elements(raw: object, root: Path) -> dict` — hunk(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2261,6 +2878,8 @@ def validate_ddl_elements(raw: object, root: Path) -> dict[s` — hunk(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2275,7 +2894,9 @@ def validate_ddl_elements(raw: object, root: Path) -> dict[s` — hunk(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2301,12 +2922,51 @@ def validate_ddl_elements(raw: object, root: Path) -> dict` — hunk(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2335,10 +2995,59 @@ def validate_ddl_elements(raw: object, root: Path) -> dict` — hunk(共帰属: F12, F14)
- `check_authz_catalog.py:@@ -2503,6 +3212,14 @@ def validate_ddl_elements(raw: object, root: Path) -> dict[` — hunk(共帰属: F12, F13, F14)

## F13: app_role の制御表直接 DML による迂回(107 件)

- `attack-tree.json:attack_goals:ATTACK:APP-ROLE-DIRECT-CONTROL-DML` — added(共帰属: F13, F13)
- `attack-tree.json:minimal_cut_sets:CUT-APP-ROLE-DIRECT-GRANTS-DML` — added(共帰属: F13, F13)
- `attack-tree.json:minimal_cut_sets:CUT-APP-ROLE-DIRECT-GROUPS-DML` — added(共帰属: F13, F13)
- `attack-tree.json:minimal_cut_sets:CUT-APP-ROLE-DIRECT-INVITATIONS-DML` — added(共帰属: F13, F13)
- `attack-tree.json:minimal_cut_sets:CUT-APP-ROLE-DIRECT-MEMBERSHIPS-DML` — added(共帰属: F13, F13)
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_ADD_PERMISSIVE_USING_TRUE+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_ADD_PERMISSIVE_USING_TRUE+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_ADD_PERMISSIVE_USING_TRUE+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_ADD_PERMISSIVE_USING_TRUE+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_DISABLE_FORCE_RLS+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_DISABLE_FORCE_RLS+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_DISABLE_FORCE_RLS+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_DISABLE_FORCE_RLS+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_DATABASE_TEMPORARY+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_DATABASE_TEMPORARY+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_DATABASE_TEMPORARY+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_DATABASE_TEMPORARY+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_APP_SCHEMA_CREATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_DELETE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_INSERT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_MAINTAIN` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_REFERENCES` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_SELECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRIGGER` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRUNCATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_UPDATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_EXECUTE_TO_APP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_GRANT_ROLE_MEMBERSHIP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_OMIT_PUBLIC_REVOKE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_REMOVE_OWNER_BYPASSRLS` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_REMOVE_PG_TEMP_FROM_SEARCH_PATH` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_REMOVE_WITH_CHECK` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_SPLIT_MANAGEMENT_AUTHORIZATION_AND_SIDE_EFFECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML+MUT:CONFIG:CFG_SWAP_FUNCTION_OWNER` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_APP_SCHEMA_CREATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_DELETE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_INSERT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_MAINTAIN` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_REFERENCES` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_SELECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRIGGER` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRUNCATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_UPDATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_EXECUTE_TO_APP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_GRANT_ROLE_MEMBERSHIP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_OMIT_PUBLIC_REVOKE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_REMOVE_OWNER_BYPASSRLS` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_REMOVE_PG_TEMP_FROM_SEARCH_PATH` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_REMOVE_WITH_CHECK` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_SPLIT_MANAGEMENT_AUTHORIZATION_AND_SIDE_EFFECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML+MUT:CONFIG:CFG_SWAP_FUNCTION_OWNER` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_APP_SCHEMA_CREATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_DELETE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_INSERT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_MAINTAIN` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_REFERENCES` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_SELECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRIGGER` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRUNCATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_UPDATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_EXECUTE_TO_APP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_GRANT_ROLE_MEMBERSHIP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_OMIT_PUBLIC_REVOKE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_REMOVE_OWNER_BYPASSRLS` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_REMOVE_PG_TEMP_FROM_SEARCH_PATH` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_REMOVE_WITH_CHECK` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_SPLIT_MANAGEMENT_AUTHORIZATION_AND_SIDE_EFFECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML+MUT:CONFIG:CFG_SWAP_FUNCTION_OWNER` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_APP_SCHEMA_CREATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_DELETE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_INSERT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_MAINTAIN` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_REFERENCES` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_SELECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRIGGER` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_TRUNCATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_CALLER_TABLE_UPDATE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_MANAGEMENT_EXECUTE_TO_APP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_GRANT_ROLE_MEMBERSHIP` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_OMIT_PUBLIC_REVOKE` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_REMOVE_OWNER_BYPASSRLS` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_REMOVE_PG_TEMP_FROM_SEARCH_PATH` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_REMOVE_WITH_CHECK` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_SPLIT_MANAGEMENT_AUTHORIZATION_AND_SIDE_EFFECT` — added
- `attack-tree.json:two_factor_interactions:PAIR:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML+MUT:CONFIG:CFG_SWAP_FUNCTION_OWNER` — added
- `claim-mutant-map.json:mutants:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GRANTS_DML` — added(共帰属: F13, mechanical:atomic-follow)
- `claim-mutant-map.json:mutants:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_GROUPS_DML` — added(共帰属: F13, mechanical:atomic-follow)
- `claim-mutant-map.json:mutants:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_INVITATIONS_DML` — added(共帰属: F13, mechanical:atomic-follow)
- `claim-mutant-map.json:mutants:MUT:CONFIG:CFG_GRANT_APP_ROLE_PROBE_MEMBERSHIPS_DML` — added(共帰属: F13, mechanical:atomic-follow)
- `claim-mutant-map.json:table_privilege_mutation_rule` — modified(共帰属: F13, F10, F13)
- `ddl-elements.json:acl_expectations:ACL:probe_grants:app_role` — modified(共帰属: F13, F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_groups:app_role` — modified(共帰属: F13, F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_invitations:app_role` — modified(共帰属: F13, F12, F14)
- `ddl-elements.json:acl_expectations:ACL:probe_memberships:app_role` — modified(共帰属: F13, F12, F14)
- `ddl-elements.json:functions:authorized_shared_rows` — modified(共帰属: F13, F12, F14)
- `ddl-elements.json:functions:read_control_resources` — modified(共帰属: F13, F12, F14)
- `check_authz_catalog.py:@@ -14,6 +14,18 @@ from itertools import combinations` — hunk
- `check_authz_catalog.py:@@ -135,6 +169,83 @@ MANAGEMENT_PROBE_CLAIM_IDS = frozenset(` — hunk
- `check_authz_catalog.py:@@ -2929,46 +3954,73 @@ def validate_claim_mutant_map(` — hunk
- `check_authz_catalog.py:@@ -2976,14 +4028,10 @@ def validate_claim_mutant_map(` — hunk
- `check_authz_catalog.py:@@ -3085,6 +4133,8 @@ def validate_claim_mutant_map(` — hunk

## F15: FR-041 比較パラメータの誤分類(7 件)

- `auth-catalog.json:entries:CATALOG:FR-041/list_item-014` — removed
- `auth-catalog.json:entries:CATALOG:FR-041/list_item-014#participant-authorization` — added
- `claim-mutant-map.json:claims:FR-041/list_item-014` — removed(共帰属: F15, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-014#participant-authorization` — added(共帰属: F15, mechanical:atomic-follow)
- `claim-mutant-map.json:claims:FR-041/list_item-014#request-validation` — added(共帰属: F15, mechanical:atomic-follow)
- `requirement-claims.json:claims:FR-041/list_item-014` — modified
- `requirement-claims.lock.json:decisions:FR-041/list_item-014` — modified

## F16: インデント表の採取欠陥(既知)(1 件)

- `check_authz_catalog.py:@@ -227,9 +338,10 @@ def git_blob_digest(data: bytes) -> str:` — hunk

## known:indent-extraction: インデント表の採取欠陥(既知)(12 件)

- `requirement-claims.json:claims:NFR-018/paragraph-001` — removed
- `requirement-claims.json:claims:NFR-018/paragraph-002` — removed
- `requirement-claims.json:claims:NFR-018/paragraph-003` — removed
- `requirement-claims.json:claims:NFR-018/table_delimiter-001` — added
- `requirement-claims.json:claims:NFR-018/table_header-001` — added
- `requirement-claims.json:claims:NFR-018/table_row-001` — added(共帰属: known:indent-extraction, known:exception-cells)
- `requirement-claims.lock.json:decisions:NFR-018/paragraph-001` — removed
- `requirement-claims.lock.json:decisions:NFR-018/paragraph-002` — removed
- `requirement-claims.lock.json:decisions:NFR-018/paragraph-003` — removed
- `requirement-claims.lock.json:decisions:NFR-018/table_delimiter-001` — added
- `requirement-claims.lock.json:decisions:NFR-018/table_header-001` — added
- `requirement-claims.lock.json:decisions:NFR-018/table_row-001` — added(共帰属: known:indent-extraction, known:exception-cells)

## known:exception-cells: NFR-018 例外表 2 セル(TSK-233 申し送り)(2 件)

- `docs/README.md` — file
- `requirements-pitchlog-2026-07-22.md:NFR-018 例外表 2 セル` — hunk

## known:changelog-row: 要件書 変更履歴の追記行(5 件)

- `requirement-claims.json:claims:CHANGELOG/table_row-028` — modified
- `requirement-claims.json:claims:CHANGELOG/table_row-029` — added
- `requirement-claims.lock.json:decisions:CHANGELOG/table_row-028` — modified
- `requirement-claims.lock.json:decisions:CHANGELOG/table_row-029` — added
- `requirements-pitchlog-2026-07-22.md:変更履歴 1 行` — hunk

## mechanical:atomic-follow: 機械的追随(atomic/oracle 参照の追随)(456 件)

- `boundary-proposal.json:oracle_context` — modified(共帰属: mechanical:atomic-follow, mechanical:reseal)
- `boundary-proposal.json:pending_human_reviews:PENDING-ALL-LOGICAL-SCOPE` — modified
- `boundary-proposal.json:pending_human_reviews:PENDING-MANAGEMENT-COMMAND-COUNT` — modified
- `claim-mutant-map.json:claims:APPENDIX-C/blockquote-001` — modified
- `claim-mutant-map.json:claims:APPENDIX-C/table_row-004` — modified
- `claim-mutant-map.json:claims:APPENDIX-C/table_row-006` — modified
- `claim-mutant-map.json:claims:APPENDIX-C/table_row-009` — modified
- `claim-mutant-map.json:claims:APPENDIX-C/table_row-010` — modified
- `claim-mutant-map.json:claims:APPENDIX-ITEM-A-5/blockquote-002` — modified
- `claim-mutant-map.json:claims:APPENDIX-ITEM-A-5/blockquote-006` — modified
- `claim-mutant-map.json:claims:APPENDIX-ITEM-A-5/paragraph-003` — modified
- `claim-mutant-map.json:claims:FR-007/list_item-009` — modified
- `claim-mutant-map.json:claims:FR-007/list_item-011` — modified
- `claim-mutant-map.json:claims:FR-012/list_item-010` — modified
- `claim-mutant-map.json:claims:FR-012/list_item-015` — modified
- `claim-mutant-map.json:claims:FR-012/list_item-018` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-002` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-004` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-005` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-006` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-007` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-008` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-009` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-010` — modified
- `claim-mutant-map.json:claims:FR-013/list_item-011` — modified
- `claim-mutant-map.json:claims:FR-014/list_item-009` — modified
- `claim-mutant-map.json:claims:FR-017/list_item-009` — modified
- `claim-mutant-map.json:claims:FR-019/list_item-006` — modified
- `claim-mutant-map.json:claims:FR-019/list_item-009` — modified
- `claim-mutant-map.json:claims:FR-033/list_item-002` — modified
- `claim-mutant-map.json:claims:FR-033/list_item-004` — modified
- `claim-mutant-map.json:claims:FR-033/list_item-005` — modified
- `claim-mutant-map.json:claims:FR-033/list_item-006` — modified
- `claim-mutant-map.json:claims:FR-033/list_item-007` — modified
- `claim-mutant-map.json:claims:FR-034/heading-001/list_item-001` — modified
- `claim-mutant-map.json:claims:FR-034/heading-001/list_item-002` — modified
- `claim-mutant-map.json:claims:FR-034/heading-001/list_item-003` — modified
- `claim-mutant-map.json:claims:FR-034/heading-001/list_item-004` — modified
- `claim-mutant-map.json:claims:FR-034/heading-001/list_item-005` — modified
- `claim-mutant-map.json:claims:FR-034/heading-001/list_item-006` — modified
- …ほか 416 件(全数は attribution.json)

## mechanical:reseal: 機械的追随(digest・manifest・lock・seal)(264 件)

- `attack-tree.json:oracle_context` — modified
- `auth-catalog.json:input_manifest` — modified
- `auth-catalog.lock.json:aggregate_decision_digest` — modified
- `auth-catalog.lock.json:asset_digest` — modified
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-034/heading-002/list_item-005` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-034/heading-002/list_item-005#operation-permission` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-034/heading-002/list_item-005#read-access` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-034/heading-002/list_item-006` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-034/heading-002/list_item-006#operation-permission` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-034/heading-002/list_item-006#read-access` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-035/list_item-005` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-035/list_item-005#principal-state` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-035/list_item-005#revocation` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-035/list_item-010` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-035/list_item-010#password-state` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-035/list_item-010#revocation` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-006` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-006#capacity-constraint` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-006#invitation-state` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-006#issue-permission` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-007` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-007#accept-permission` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-007#acceptance-serialization` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-007#capacity-constraint` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-007#invitation-state` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-014` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:FR-041/list_item-014#participant-authorization` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:NFR-011/list_item-002` — removed
- `auth-catalog.lock.json:entries:catalog:CATALOG:NFR-011/list_item-002#credential-state` — added
- `auth-catalog.lock.json:entries:catalog:CATALOG:NFR-011/list_item-002#revocation` — added
- `auth-catalog.lock.json:entry_count` — modified
- `claim-mutant-map.json:oracle_context` — modified
- `ddl-elements.json:oracle_context` — modified
- `http-route-matrix.json:input_manifest` — modified
- `http-route-matrix.lock.json:asset_digest` — modified
- `oracle-seal.lock.json:input_assets:contracts/authz/auth-catalog.json` — modified
- `oracle-seal.lock.json:input_assets:contracts/authz/auth-catalog.lock.json` — modified
- `oracle-seal.lock.json:input_assets:contracts/authz/http-route-matrix.json` — modified
- `oracle-seal.lock.json:input_assets:contracts/authz/http-route-matrix.lock.json` — modified
- `oracle-seal.lock.json:input_assets:contracts/authz/requirement-claims.json` — modified
- …ほか 224 件(全数は attribution.json)

## mechanical:schema-follow: 機械的追随(schema シグネチャ)(1 件)

- `check_authz_catalog.py:@@ -696,7 +981,16 @@ def _validate_claim(` — hunk

## mechanical:step-tests: テスト(負例・期待件数・走査一般化)(17 件)

- `tests/fixtures/authz_claims/atomic-claim.json` — file
- `tests/fixtures/authz_claims/atomic-route-references.json` — file
- `tests/fixtures/authz_claims/auth-catalog-atomic.json` — file
- `tests/fixtures/authz_claims/claim-execution-support.json` — file
- `tests/fixtures/authz_claims/ddl-elements.json` — file
- `tests/fixtures/authz_claims/empty-auth-rule.json` — file
- `tests/fixtures/authz_claims/indented-tables.md` — file
- `tests/fixtures/authz_claims/invalid-atomic-claims.json` — file
- `tests/fixtures/authz_claims/invalid-claim-dispositions.json` — file
- `tests/fixtures/authz_claims/invalid-claim-execution-support.json` — file
- `tests/fixtures/authz_claims/invalid-closed-world.json` — file
- `tests/fixtures/authz_claims/invalid-ddl-elements.json` — file
- `tests/fixtures/authz_claims/requirement-claims.json` — file
- `tests/fixtures/authz_claims/requirement-claims.lock.json` — file
- `tests/fixtures/authz_claims/route-registry.json` — file
- `tests/fixtures/authz_claims/route-registry.lock.json` — file
- `tests/test_check_authz_catalog.py` — file
