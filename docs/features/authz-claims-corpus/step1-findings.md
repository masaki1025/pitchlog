## 指摘

1. **P0 — 端末内の認可判定点を表現できず、非所有タブ入力の許可反転を検出できない**  
   旧要約対応: **分類**  
   対象 ID: `check_authz_catalog.py:const:DECIDABLE_LOCATIONS`, `requirement-claims.json:claims:FR-012/list_item-013`  
   E3 は端末内の排他ロックによる非所有タブ拒否だが、`decidable_at` は `db/http` のみである。列挙値も `db/http/cache` に閉じており、クライアント・端末内・断中判定を登録不能なため、第二タブが入力を受理する実装でも指定 oracle が全通過し得る。証拠: [contracts/authz/requirement-claims.json:3356)  
   是正: クライアント／端末内の判定場所と basis/test owner を追加し、UI結果とサーバー側防御を別の原子的主張に分割する。

2. **P0 — 制御資源の操作拒否を「読み取り可視性」と誤分類している**  
   旧要約対応: **分類**  
   対象 ID: `requirement-claims.json:claims:FR-034/heading-002/list_item-005`, `requirement-claims.json:claims:FR-034/heading-002/list_item-006`, `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-005`, `auth-catalog.json:entries:CATALOG:FR-034/heading-002/list_item-006`  
   両行は7操作のテナント権限・`admin` 権限を規定するが、`AUTH_ACCESS_SCOPE/access_control`、`DB_ROW_VISIBILITY_PREDICATE`、`SCOPE:DATA_READ` である。`SCOPE:DATA_READ` は `management_operation` を含まず、操作の許可条件が管理経路へ伝播しない。証拠: [contracts/authz/auth-catalog.json:24)  
   是正: 読み取り条件と操作条件を分割し、操作側を `AUTH_OPERATION_PERMISSION`、DB mutation guard、管理操作スコープへ結線する。

3. **P0 — 招待発行・受諾の操作認可を principal state として固定している**  
   旧要約対応: **分類**  
   対象 ID: `requirement-claims.json:claims:FR-041/list_item-006`, `requirement-claims.json:claims:FR-041/list_item-007`  
   `admin` 限定、参加上限、招待有効性、直列化という独立した操作判定を含むのに、全体を `AUTH_PRINCIPAL_STATE/authentication_boundary` としている。DB/HTTP の操作ガードを欠いたまま、招待状態の永続化検査だけで充足扱いになる。証拠: [contracts/authz/requirement-claims.json:5437)  
   是正: 操作権限、招待状態、容量制約、直列化を原子的主張へ分割し、それぞれ適切な layer/basis を持たせる。

4. **P0 — 即時トークン失効の cache 判定点が欠落している**  
   旧要約対応: **分類**  
   対象 ID: `requirement-claims.json:claims:FR-035/list_item-005`, `requirement-claims.json:claims:FR-035/list_item-010`, `requirement-claims.json:claims:NFR-011/list_item-002`  
   「既存の全トークン・セッション」「全経路で即時失効」「旧トークン失効」を要求する3主張がいずれも `db/http` のみで、`cache` がない。一方、同じパスワード変更失効である `FR-036/list_item-005` は `http/cache` であり、内部的にも不整合である。証拠: [contracts/authz/requirement-claims.json:10545)  
   是正: 失効部分を `AUTH_REVOCATION_CACHE` として分離し、cache owner と即時失効 oracle を必須化する。

5. **P0 — AUTH 分類規則の適用罠が全件無効で、誤分類を検査できない**  
   旧要約対応: **分類**  
   対象 ID: `requirement-claims.json:classification_rules`, `check_authz_catalog.py:def:_validate_rule_applicability`  
   AUTH 5規則の `allowed_source_kinds`、`allowed_heading_ids`、`forbidden_source_text_patterns` がすべて空であり、検査器は空を「制約なし」と解釈する。lock は誤りを含む決定を複製・凍結するだけなので、上記 P0-2/P0-3 のような取り違えを検出しない。証拠: [scripts/check_authz_catalog.py:633)  
   是正: 各 AUTH 規則に非空の適用領域・禁止パターンを定義し、空の AUTH 適用条件を検査エラーにする。

6. **P0 — closed-world 宣言が機械的な閉包条件になっていない**  
   旧要約対応: **closed-world**  
   対象 ID: `requirement-claims.json:claims:FR-034/heading-001/paragraph-002`, `requirement-claims.json:claims:FR-034/heading-002/paragraph-001`, `requirement-claims.json:claims:FR-034/heading-002/paragraph-003`  
   「許可リスト（これがすべて）」と「共通の前提条件」は `out_of_scope`、制御資源全域宣言は通常の `auth_claim` であり、いずれにも閉じる対象集合や量化範囲がない。したがって新しい資源・経路・操作を無結線で追加しても、「行列外は404」「この3つで全域」が再検証されない。証拠: [contracts/authz/requirement-claims.json:8248)  
   是正: closed-world 主張、対象 universe、許可集合、既定拒否を専用構造にし、経路・資源・操作との exact-set を検査する。

7. **P0 — HTTP 主張から経路への逆向き閉包がなく、184件中166件が無結線**  
   旧要約対応: **結線**  
   対象 ID: `check_authz_catalog.py:def:_validate_source_claim_ids`, `check_authz_catalog.py:def:validate_route_registry`  
   `source_claim_ids` の検査は未知 ID の拒否だけで、HTTP 判定可能主張側から「結線済みまたは明示的対象外」を要求しない。実測は unique source 18件、未結線166件、未結線集合 SHA-256 `05ecd55cbc2c542faca59f2d25e3609401a8cf69584edd4898d78622e1cc8be6`。DBだけは177件の exact-set がある。証拠: [scripts/check_authz_catalog.py:1603)  
   是正: HTTP 主張全件について route ID または理由付き disposition を要求し、逆向き exact-set を検査する。

8. **P0 — FR-020〜032 の拒否経路が要件由来であるのに design-origin・無出典になっている**  
   旧要約対応: **結線**  
   対象 ID: `route-registry.json:routes:ROUTE:FR-020`, `route-registry.json:routes:ROUTE:FR-032`, `requirement-claims.json:claims:FR-034/heading-001/table_row-015`, `requirement-claims.json:claims:FR-034/heading-001/table_row-021`  
   要件書は FR-020〜032 の共有グループ経由を明示的に404とするが、13経路は `origin: design`、`source_claim_ids: [scripts/check_authz_catalog.py:1425)  
   是正: 各 legacy route を対応する FR-034 表行と既定拒否主張へ結線し、要件由来 route の design 強制を廃止する。

9. **P0 — cache 判定可能17件が全派生・oracle 資産から脱落している**  
   旧要約対応: **結線**  
   対象 ID: `requirement-claims.json:claims:FR-034/heading-004/table_row-001`, `check_authz_catalog.py:def:validate_derived_assets`  
   cache 主張17件に対し、経路レジストリ結線は0件で、cache 用 registry/matrix/exact-set も存在しない。未結線集合 SHA-256 は `02e4fa87a3966d20265d607892faf8dce6659133927062629cd74305c8e38063`。付与撤回・離脱・終了・無効化後に古い許可キャッシュを返す実装を oracle が拒否できない。証拠: [scripts/check_authz_catalog.py:1603)  
   是正: cache invalidation matrix と実行所有者を派生資産化し、17件すべてを exact-set で結線する。

10. **P0 — FR-035/FR-037 の管理経路が route universe に存在せず、oracle は未実装主張を実行可能と誤認する**  
    旧要約対応: **結線**  
    対象 ID: `auth-catalog.json:entries:CATALOG:FR-035/list_item-004`, `auth-catalog.json:entries:CATALOG:FR-037/list_item-004`, `claim-mutant-map.json:claims:FR-035/list_item-004`, `claim-mutant-map.json:claims:FR-037/list_item-004`  
    registry の `management_operation` は FR-041 の8グループ操作のみで、FR-035/FR-037 から結線される ID は `FR-035/list_item-014` だけである。ところが catalog は一般管理機能も `SCOPE:CONTROL` に入れ、claim-mutant-map は management operation の source 集合にないDB主張を自動的に `probe_executable` とする。このため横断一覧・チーム無効化等に実在する経路もDDL要素もないのに「runtime kill 可能」と判定される。証拠: [scripts/check_authz_catalog.py:2690)  
    是正: システム管理経路を明示的に登録し、主張ごとの route/DDL/runtime target または `contract_only` 理由を exact-set で持たせる。

11. **P0 — conditional 12経路に許可・拒否シナリオがなく、NFR-019(b)を満たさない**  
    旧要約対応: **closed-world**  
    対象 ID: `http-route-matrix.json:routes:HTTP:ROUTE:CONTROL:GROUP_LIST`, `http-route-matrix.json:routes:HTTP:ROUTE:MANAGEMENT:ISSUE_INVITATION`, `claim-mutant-map.json:positive_cases`, `check_authz_catalog.py:def:validate_http_route_matrix`  
    control 4経路・management 8経路は `disposition: conditional` と test owner しかなく、`cells` は共有3軸の12件だけ、正例もそのうちallow 6件だけである。NFR-019 が要求する非参加、member/admin、テナント権限、最後のadmin、招待有効性、上限等は expected decision に現れない。証拠: [docs/requirements/requirements-pitchlog-2026-07-22.md:923)  
    是正: conditional 全経路について NFR-019 の条件軸を持つ閉じたシナリオ行列を作り、各 allow セルに正例を要求する。

12. **P0 — DDL oracle の SECURITY DEFINER 関数が宣言されたACLでは正常実行できない**  
    旧要約対応: **対応なし（新規）**  
    対象 ID: `ddl-elements.json:functions:authorized_shared_rows`, `ddl-elements.json:functions:read_control_resources`, `ddl-elements.json:functions:apply_representative_grant_change`, `ddl-elements.json:schemas:management_private`  
    関数所有者は基表所有者ではなく、依存表への `SELECT/DML` ACL がない。さらに `management_caller` は関数の `EXECUTE` を持つ一方、`management_private` の `USAGE` を持たない。したがって正当な許可ケースが privilege error で拒否される。証拠: [contracts/authz/ddl-elements.json:462)  
    是正: caller の schema USAGE と、各 function owner の依存表に対する最小権限を明示し、検査器で相互参照する。

13. **P0 — `app_role` の制御表直接DMLが管理認可と論理削除を迂回する**  
    旧要約対応: **対応なし（新規）**  
    対象 ID: `ddl-elements.json:acl_expectations:ACL:probe_groups:app_role`, `ddl-elements.json:acl_expectations:ACL:probe_memberships:app_role`, `ddl-elements.json:acl_expectations:ACL:probe_grants:app_role`, `ddl-elements.json:acl_expectations:ACL:probe_invitations:app_role`, `attack-tree.json:attack_goals:ATTACK:MANAGEMENT-CALLER-DIRECT-TABLE-PRIVILEGE`  
    `app_role` はグループ・参加・付与・招待表に `INSERT/UPDATE/DELETE` を持ち、RLS は現在テナント所有だけを検査する。これにより専用管理関数、テナント側権限、group admin 条件を通らず制御状態を変更でき、利用者物理削除も可能になる。attack tree は `management_caller` の直接DMLだけを扱い、この経路を欠く。証拠: [contracts/authz/attack-tree.json:54)  
    是正: `app_role` から制御表DMLを剥奪し、認可付き関数へ一本化するとともに、app_role直接DMLを攻撃木・負例へ追加する。

14. **P0 — DDL検査器が policy/ACL の認可意味を検証していない**  
    旧要約対応: **対応なし（新規）**  
    対象 ID: `check_authz_catalog.py:def:validate_ddl_elements`, `ddl-elements.json:policies:POLICY:probe_groups:tenant_boundary`  
    policy の `command` と `role_ids` はキーの存在しか検査されず、predicate ID も非空文字列なら通る。ACLも個々の参照・禁止権限を見るだけで、必要ACLの exact-set、function owner の基表権限、caller の schema USAGEを検査しない。誤った role、`USING TRUE` 相当、ACL欠落を reseal すれば検査通過する。証拠: [scripts/check_authz_catalog.py:2308)  
    是正: command・role・predicate を閉じた値域と意味的対応表で検査し、必要ACLと所有者／schema依存を exact-set にする。

15. **P1 — 比較対象パラメータを「DB principal state persistence」と誤分類している**  
    旧要約対応: **分類**  
    対象 ID: `requirement-claims.json:claims:FR-041/list_item-014`  
    原文は「選択状態をサーバーに永続化しない」と明記する一時的な要求パラメータ／400入力検証だが、`AUTH_PRINCIPAL_STATE` と `DB_PRINCIPAL_STATE_PERSISTENCE` が付いている。不要なDB認証状態テストを生み、実際の集合上限・membership検査を曖昧にする。証拠: [contracts/authz/requirement-claims.json:5642)  
    是正: HTTP入力検証と参加テナント認可を分割し、DB persistence 判定を除去する。

16. **P1 — インデントされたMarkdown表を paragraph として採取する**  
    旧要約対応: **対応なし（新規）**  
    対象 ID: `check_authz_catalog.py:def:_table_cells`, `requirement-claims.json:claims:NFR-018/paragraph-001`, `requirement-claims.json:claims:NFR-018/paragraph-002`, `requirement-claims.json:claims:NFR-018/paragraph-003`  
    `_table_cells` は行頭が直ちに `|` の場合しか表と認識しないため、要件書904〜906行の4スペースインデント表3行が paragraph に落ち、区切り行まで `OUT_NON_AUTH_REQUIREMENT` になる。現在の3行自体は認可反転を起こさないためP1だが、採取器の構造同一性は破れている。証拠: [contracts/authz/requirement-claims.json:11144)

判定: 指摘 P0 14 件・P1 2 件・P2 0 件
結論: 否決。

