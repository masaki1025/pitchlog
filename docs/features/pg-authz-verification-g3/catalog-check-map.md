# PostgreSQL カタログ検査対応表

ステップ 6 の検査は、`ddl-elements.json` と二段封印済みの
`function-bodies/manifest.json`／SQL body を期待値とし、実 PostgreSQL の
`pg_*` カタログを観測する。JSON 資産自体の妥当性を検査する既存の静的検査とは
層が異なる。

関数 definition の期待値だけはソース文字列から組み立てない。まず manifest の
現物 digest と `source_commit` 上の blob を既存検査器で照合し、その封印済み DDL を
同一使い捨てクラスタ内の別 database へ適用する。そこで PostgreSQL 自身が返す
`pg_get_functiondef` を期待値とし、対象 database の値と比較する。別 database は
参照値取得前に ordered steps を完走するため、一時 role membership は残らない。
また、所有物検査は対象 database の `pg_shdepend.dbid` だけを対象とする。
この前段が不一致なら `CATALOG:FUNCTION-DIGEST:SOURCE-SEAL` で入力不正として
停止し、参照 database の値を oracle にしない。参照接続が同一クラスタの別 database
でない場合や参照関数集合が一致しない場合も
`CATALOG:FUNCTION-DIGEST:REFERENCE` で停止する。これら 2 ID は入力前提の検査 ID
であり、正常時の `CatalogReport.checked_ids` には加えない。

## 検査 ID と期待値

| 検査 ID | 資産上の期待値 | 主なカタログ観測値 |
| --- | --- | --- |
| `CATALOG:POLICY:EXACT-SET` | `policies[].table_id` と封印済み policy body の schema・policy 名 | `pg_policy` の対象集合 |
| `CATALOG:<policy_id>` | `command`、`role_ids`、`policy_mode`、`using_predicate_id`、`with_check_predicate_id` と対応する predicate／policy body | `polcmd`、`polroles`、`polpermissive`、`pg_get_expr(polqual)`、`pg_get_expr(polwithcheck)` |
| `CATALOG:FUNCTION-DIGEST:EXACT-SET` | `functions[].schema_id`／`function_id` | 対象 schema 内の `pg_proc` 全 overload |
| `CATALOG:FUNCTION-DIGEST:<function_id>` | 別 database に封印済み body を適用した `pg_get_functiondef`。残る 9 属性は body、`owner_role_id`、`security_mode`、`search_path`、関数 ACL expectation | `pg_get_functiondef`、owner、language、security、volatility、leakproof、strict、parallel、`proconfig`、ACL の 10 属性 digest |
| `CATALOG:FUNCTION-STRUCTURE:<function_id>:SQL-ATOMIC` | `functions[]` の対象集合と封印済み関数 body | `pg_language.lanname` と `pg_get_functiondef` の `BEGIN ATOMIC` |
| `CATALOG:FUNCTION-STRUCTURE:<function_id>:NO-DYNAMIC-SQL` | 封印済み body が許す静的 SQL 構造 | `pg_get_functiondef` 内の `EXECUTE`、`format(`、連結演算子の不存在 |
| `CATALOG:FUNCTION-STRUCTURE:<function_id>:DEPENDENCY-RELATIONS` | `dependency_table_ids` と `tables[].schema_id` | `pg_depend` が示す relation の exact-set |
| `CATALOG:REACHABILITY:SET` | caller 系 `roles[].role_kind` と、role 属性・schema／table／function owner | `pg_auth_members.set_option` だけを辺にした推移閉包と危険終点の交差 |
| `CATALOG:REACHABILITY:USAGE` | caller 系 `roles[].role_kind` と、role 属性・schema／table／function owner | `pg_auth_members.inherit_option` だけを辺にした推移閉包と危険終点の交差 |
| `CATALOG:ACL:TABLE:<table_id>` | `acl_expectations` の `object_kind=table` | `pg_class.relacl` の非 owner 直接 ACL |
| `CATALOG:ACL:FUNCTION:<function_id>` | `acl_expectations` の `object_kind=function` | 同名全 overload の `pg_proc.proacl` |
| `CATALOG:ACL:SCHEMA:<schema_id>` | `schemas[].usage_role_ids`／`create_role_ids` | `pg_namespace.nspacl` |
| `CATALOG:ACL:COLUMN:<expectation_id>` | `column_acl_expectations` の対象と `expected_entries` | `pg_attribute.attacl` |
| `CATALOG:ACL:DEFAULT` | 認可 role／schema に default ACL 宣言がないこと | `pg_default_acl` |
| `CATALOG:ACL:PUBLIC` | `functions[].public_execute=false` と各 ACL 期待集合に PUBLIC がないこと | 表・列・schema・routine・default ACL の PUBLIC entry |
| `CATALOG:SEARCH-PATH:<function_id>` | `functions[].search_path` | `pg_proc.proconfig`。末尾が `pg_temp` かつ出現 1 回も同時照合 |
| `CATALOG:PROVISIONER-CANNOT-SET-OWNER` | `provisioning_claim.completion_catalog_expectations` の同 ID・述語 | provisioner から全 function owner への `pg_has_role(..., 'SET')` |
| `CATALOG:PROVISIONER-CANNOT-USE-OWNER` | `provisioning_claim.completion_catalog_expectations` の同 ID・述語 | provisioner から全 function owner への `pg_has_role(..., 'USAGE')` |
| `CATALOG:OWNED-OBJECTS:BYPASSRLS` | `roles[].bypass_rls=true` と、その role を owner とする `schemas`／`tables`／`functions` | `pg_shdepend` の owner dependency（現 database と共有 object）の全 object address exact-set |
| `CATALOG:OWNED-OBJECTS:SECURITY-DEFINER` | `functions[].security_mode=definer` | 非 system schema 内の全 `prosecdef=true` routine の exact-set |

`<function_id>`、`<policy_id>`、`<table_id>`、`<schema_id>`、`<expectation_id>` は
件数リテラルではなく各資産配列から展開する。

### 資産展開後の検査 ID

- Policy: `CATALOG:POLICY:EXACT-SET`、
  `CATALOG:POLICY:probe_business_rows:tenant_boundary`、
  `CATALOG:POLICY:probe_groups:tenant_boundary`、
  `CATALOG:POLICY:probe_memberships:tenant_boundary`、
  `CATALOG:POLICY:probe_grants:tenant_boundary`、
  `CATALOG:POLICY:probe_invitations:tenant_boundary`、
  `CATALOG:POLICY:probe_management_effects:tenant_boundary`
- Function digest: `CATALOG:FUNCTION-DIGEST:EXACT-SET`、
  `CATALOG:FUNCTION-DIGEST:authorized_shared_rows`、
  `CATALOG:FUNCTION-DIGEST:read_control_resources`、
  `CATALOG:FUNCTION-DIGEST:apply_representative_grant_change`
- Function structure: 各関数 ID について
  `CATALOG:FUNCTION-STRUCTURE:<function_id>:SQL-ATOMIC`、
  `CATALOG:FUNCTION-STRUCTURE:<function_id>:NO-DYNAMIC-SQL`、
  `CATALOG:FUNCTION-STRUCTURE:<function_id>:DEPENDENCY-RELATIONS`
- Reachability: `CATALOG:REACHABILITY:SET`、`CATALOG:REACHABILITY:USAGE`
- Table ACL: `CATALOG:ACL:TABLE:probe_business_rows`、
  `CATALOG:ACL:TABLE:probe_groups`、
  `CATALOG:ACL:TABLE:probe_memberships`、
  `CATALOG:ACL:TABLE:probe_grants`、
  `CATALOG:ACL:TABLE:probe_invitations`、
  `CATALOG:ACL:TABLE:probe_management_effects`
- Function ACL: `CATALOG:ACL:FUNCTION:authorized_shared_rows`、
  `CATALOG:ACL:FUNCTION:read_control_resources`、
  `CATALOG:ACL:FUNCTION:apply_representative_grant_change`
- Schema ACL: `CATALOG:ACL:SCHEMA:probe_data`、
  `CATALOG:ACL:SCHEMA:authz_private`、
  `CATALOG:ACL:SCHEMA:management_private`
- その他の ACL: `CATALOG:ACL:COLUMN:COLUMN-ACL:ALL-PROBE-TABLES:NO-EXPLICIT-GRANTS`、
  `CATALOG:ACL:DEFAULT`、`CATALOG:ACL:PUBLIC`
- Search path: `CATALOG:SEARCH-PATH:authorized_shared_rows`、
  `CATALOG:SEARCH-PATH:read_control_resources`、
  `CATALOG:SEARCH-PATH:apply_representative_grant_change`
- Provisioning completion: `CATALOG:PROVISIONER-CANNOT-SET-OWNER`、
  `CATALOG:PROVISIONER-CANNOT-USE-OWNER`
- Owned objects: `CATALOG:OWNED-OBJECTS:BYPASSRLS`、
  `CATALOG:OWNED-OBJECTS:SECURITY-DEFINER`

## R-1・R-2・R-8 対応

| 要求 | 検査 ID | 対応内容 |
| --- | --- | --- |
| R-1: 読み取り関数を `LANGUAGE SQL BEGIN ATOMIC` に固定 | `CATALOG:FUNCTION-STRUCTURE:<function_id>:SQL-ATOMIC` | 実関数の language と定義構造を検査する。 |
| R-1: 動的 SQL を禁止 | `CATALOG:FUNCTION-STRUCTURE:<function_id>:NO-DYNAMIC-SQL` | 実関数定義の禁止構文を検査する。 |
| R-1: 宣言外 relation 参照を禁止 | `CATALOG:FUNCTION-STRUCTURE:<function_id>:DEPENDENCY-RELATIONS` | `pg_depend` と `dependency_table_ids` を exact-set 照合する。SELECT と DML の双方を同じ依存関係として捕捉する。 |
| R-1: 封印後の関数差し替えを禁止 | `CATALOG:FUNCTION-DIGEST:SOURCE-SEAL`、`CATALOG:FUNCTION-DIGEST:EXACT-SET`、`CATALOG:FUNCTION-DIGEST:<function_id>` | manifest の現物・`source_commit` 照合を先に要求する。通過した body を別 database へ適用して definition を生成し、実関数の 10 属性 digest を比較する。 |
| R-1: 安全な固定 search path | `CATALOG:SEARCH-PATH:<function_id>` | 資産列との一致、末尾 `pg_temp`、出現 1 回を検査する。 |
| R-1: PUBLIC 実行を禁止し、名前付き実行だけを許可 | `CATALOG:ACL:FUNCTION:<function_id>`、`CATALOG:ACL:PUBLIC` | 全 overload の直接 ACL と PUBLIC の不存在を検査する。 |
| R-2: caller から危険ロールへの `SET` 到達を禁止 | `CATALOG:REACHABILITY:SET` | `set_option` の推移閉包を独立計算する。 |
| R-2: caller から危険ロールへの権限継承到達を禁止 | `CATALOG:REACHABILITY:USAGE` | `inherit_option` の推移閉包を独立計算する。 |
| R-2: 危険 owner／SECURITY DEFINER routine を採用集合へ閉じる | `CATALOG:OWNED-OBJECTS:BYPASSRLS`、`CATALOG:OWNED-OBJECTS:SECURITY-DEFINER` | BYPASSRLS owner の所有物と全 definer routine を exact-set 照合する。 |
| R-8: provisioning 完了後に一時 `SET` 経路を残さない | `CATALOG:PROVISIONER-CANNOT-SET-OWNER` | 資産の完了時述語を全 function owner へ評価する。 |
| R-8: provisioning 完了後に一時継承経路を残さない | `CATALOG:PROVISIONER-CANNOT-USE-OWNER` | 資産の完了時述語を全 function owner へ評価する。 |

R-1・R-2・R-8 の本ステップ対象には未対応項目がない。
