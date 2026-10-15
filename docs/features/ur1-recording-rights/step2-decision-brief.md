# U-R1 新ステップ2: 追補・資産・受理の判断資料

2026-10-15。対象はRG1の新2だけ。詳細は[受理順序追補案](step2-acceptance-order-addendum-proposal.md)・[個別承認資料](rg1-individual-approval-packet.md)・[承認済み最小追補](step2-minimal-addendum-proposal.md)。本資料は5件の設計方針を再審査せず、最終計画承認・正確な資産承認・候補作成許可・7.7正式受理を区別する。

## 現在地と計画の具体差分

`origin/develop`は`3f6a935a`。TSK-550の共有実行器Aは別worktreeの未コミット候補であり、developには未統合。したがってU-R1の実revision/digest/snapshotは**未確定**。Aの候補には`FunctionOperationRegistration`、固定registry、`_TenantTransaction.run_function`、`repository-contract.json`の公開面がある。U-R1はAの登録形式を再利用してRG1の固定読取2登録だけを後載せし、Bのresolver登録完了やTSK-550全体の完了を待たない。

| 判断対象 | 現行 | 提案 |
| --- | --- | --- |
| PR・7.7単位 | 新2〜6を同じPRの単一記録afterへ順次反映し、PR最終HEADを1回正式受理 | **新2を独立PRの最終製品ステップ**としてその最終候補状態を1回受理。新3以降は別PRとし各PRでbefore・番号・記録を持つ。7.7条文・`single_review_acceptance`は維持 |
| 新2の候補作成 | 正式受理を実装開始前に要求するためafterを算出できない | A統合と具体資産の個別承認、候補作成の明示許可後、ローカルで候補作成。正式台帳にはまだ記入しない |
| 検査 | 各ステップをgreenとするが未受理期間の履歴不一致を未定義 | 候補時の履歴不一致は**不合格のまま**記録・提示。受理記録反映後は作業ツリー検査、ステップコミット後は実HEADを読む凍結履歴/archive/契約差分検査とPR CIをgreenにする。検査器の緩和・skipなし |
| PR番号・snapshot | 実番号・実blobが必要 | 計画/作業ログのみの準備push/Draftは別Git許可を得る。snapshotに中間コミットが不可欠なら例外を事前提示。受理前に実承認者・日付を仮置きしない |

この変更は**実装計画のPR境界と新2/9の合格条件**に及ぶ。凍結契約の受理単位、検査器、正本7.7自体の変更は提案しない。後続PR数とレビュー負荷は増える。最終候補受理後に差分が動く場合は再提示・再受理する。

**独立レビュー後のP0反映候補（未再レビュー）**: 新2だけを独立PRにすると、コアパスの先行宣言（現行新7）とJSON登録（現行新8）が別PRへ残り、同じPRで重複帰属を登録するDoDに反する。推奨する追加計画変更は、新2PRに含むパスだけを**宣言→JSON登録→製品**の独立コミットへ配置し、6.1のステップ番号・`/<N>`を一意にすること。登録を先に置いて製品コミットを当該PRの最終受理候補にする。事前登録でguardが緑になることは候補の実検査で確かめる。後続で初めて増えるパスも該当PRで同様に扱う。現行の新2/3/5/6/7/8を単純に番号変更すると、D4と実経路結合の参照も動くため、**ステップ対応表とDoDの正式追補**を人間に提示してから計画を置換する。対応表未確定のまま製品コードやguard資産へ進まない。

| 推奨する新番号（未承認） | 現行番号 | 内容・PR境界 |
| --- | --- | --- |
| 1 | 1 | RG1接続・資源ゲート。完了済み記録を維持 |
| 2 | 7の新2PR対象部分 | 新2PRの追加パスを`AREA_PATH_ADDITIONS`とguard試験へ先行宣言する独立コミット |
| 3 | 8の新2PR対象部分 | `.claude/core-areas.json`へ新2PRの追加パス・重複帰属を登録する独立コミット。製品パスがまだ無くてもguardが緑になることを実検査する |
| 4 | 2 | RG1判定製品・DB/認可/凍結資産と正式受理記録。旧称「新2」の意味範囲。ここを新2PRの最終HEAD・受理対象とする |
| 5 | 3 | D4初期付与。D4方式は別ゲート |
| 6 | 4 | 通常/緊急引き継ぎ。必要な新規パスのguard登録は同じPRで先行/後続コミットを別途計画 |
| 7 | 5 | 復元ライフサイクル。製品open/復元開始はこの意味範囲 |
| 8 | 6 | U-S1/U-G1の実経路結合。旧称「新6」の意味範囲と別ゲートを維持 |
| 9 | 9 | U-R1全体の最終照合。各PRの7.7受理済み記録と最終HEADを再確認 |

これは**提案であり、現行ステップ表をまだ変更しない**。新5〜8で追加パスが生じる場合の独立宣言/登録コミットは、必要な時点のPRごとに6.1適合の小ステップを追加する追補が要る。ステップ番号の変更は既存の作業ログとU-G1/U-S1への申し送りにも対応表を付け、過去記録を改変しない。上表を承認しない場合、新2PR単独完了とコアパス同一PR登録を両立する代案が必要。

**コミットとPRの境界**: 新1の既存記録は保持する。新2は`tests/test_core_guard.py`と`scripts/core_guard.py`の追加層を宣言する独立コミット、新3は`.claude/core-areas.json`のみの登録コミット、新4はRG1製品・認可・凍結・7.7のステップコミットとする。新2〜4を**同じRG1先行PR**に置き、受理単位は新4を含む同PRの最終HEAD。新5〜8はD4・引き継ぎ・復元・実経路結合の後続PRへ送り、各PRが追加するパスについて同じ宣言→登録の前処理を個別計画する。新9は複数PRの履歴を照合する。各コミットの`(ステップ k/9)`は上表の新番号を用い、1件名に1トークンとする。現行ブランチの過去コミットは書き換えず、最終承認後に後続ブランチの計画現在地を照合する。

**guardで先登録が成立する根拠と検査**: `scripts/core_guard.py`の`validate_area_path_layers()`はmerge-baseのpathsと宣言済み追加層の順序・全数を照合し、対象ファイルの存在を合格条件にしていない。`verify_area_path_baseline()`は各コミットを走査し、JSONと基線定義を同一コミットで変更した場合を拒否する。隔離テスト`tests/test_core_guard.py::test_tenant_declaration_accepts_json_before_registration`は合成repoで宣言コミット→JSON登録コミットを受理し、追加パターンに対応する製品ファイルを作らない。`test_addition_layer_requires_complete_declared_suffix`は部分登録・並べ替えを拒否する。2026-10-15の実測は`uv run pytest tests/test_core_guard.py -k 'tenant_declaration_accepts_json_before_registration or addition_layer_requires_complete_declared_suffix' -q -n 0`で**2 passed**。新2/3の候補時には新しいRG1パターンの宣言→登録を隔離PR履歴で再検査し、PR本文のコア逐行確認欄も新4の最終HEADで満たす。guardの実装を緩めない。

**新2/3のJSON追加パス候補**: `recording-rights.paths`へ、実際に編集する`backend/src/pitchlog/repositories/rg1.py`、`backend/src/pitchlog/repositories/operation_registry.py`、`backend/src/pitchlog/authz/classification.py`、`backend/src/pitchlog/authz/product_control_access.py`、`backend/src/pitchlog/authz/product_catalog.py`、`scripts/check_authz_catalog.py`、RG1試験の確定ファイル名、RG1固有の認可資産ファイルを追加する。`sync-protocol.paths`/`tenant-isolation.paths`に重複帰属すべき実変更パスも同じ宣言・登録に含める。現在の`.claude/core-areas.json`は`recording-rights`に`db/recording_rights/*`を、`tenant-isolation`に`repositories/*`と`authz/*`を既登録。**この列挙は候補**であり、A統合後に実変更ファイルと既登録パターンを集合照合し、必要な追加パターンの完全順列を新2コミット前に固定する。存在しない将来ファイルを広域globで過剰登録しない。

## 正確な資産候補の形（未承認）

以下は現行認可資産のキーと既承認5方針に合わせた**申請用候補**。この文書のSQL/JSONを製品資産に書き込んだ状態ではない。A統合後の実基線で最終の全行差分・catalog結果を提示し、別途個別承認する。SQL適用は既存の製品認可適用器に一本化する。

```sql
CREATE TABLE public.rg1_restore_gate (
    singleton_id smallint PRIMARY KEY CHECK (singleton_id = 1),
    state text NOT NULL CHECK (state IN ('closed', 'open'))
);
INSERT INTO public.rg1_restore_gate (singleton_id, state) VALUES (1, 'closed');
ALTER TABLE public.rg1_restore_gate ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rg1_restore_gate FORCE ROW LEVEL SECURITY;
CREATE ROLE pitchlog_rg1_fn_owner NOLOGIN NOSUPERUSER NOBYPASSRLS
    NOCREATEDB NOCREATEROLE NOREPLICATION NOINHERIT;
CREATE SCHEMA rg1_api AUTHORIZATION pitchlog_owner;
REVOKE ALL ON SCHEMA rg1_api FROM PUBLIC;
GRANT USAGE ON SCHEMA rg1_api TO pitchlog_app;
GRANT USAGE ON SCHEMA public TO pitchlog_rg1_fn_owner;
GRANT SELECT (singleton_id, state), UPDATE (singleton_id)
    ON public.rg1_restore_gate TO pitchlog_rg1_fn_owner;
CREATE POLICY rg1_fn_select_singleton ON public.rg1_restore_gate
    FOR SELECT TO pitchlog_rg1_fn_owner USING (singleton_id = 1);
CREATE POLICY rg1_fn_lock_singleton ON public.rg1_restore_gate
    FOR UPDATE TO pitchlog_rg1_fn_owner
    USING (singleton_id = 1) WITH CHECK (singleton_id = 1);
```

上記の表・role・schema作成順とseedはmigration/製品認可適用器の責務に従って分割する。`pitchlog_app`には表ACL・role membership・schema CREATEを付与しない。関数は`rg1_api.rg1_read_open()`と`rg1_api.rg1_assert_open_before_commit()`の**引数なし・boolean戻り**のみ。前者はsingleton行を非ロックで、後者は同じ行を厳密な`FOR SHARE NOWAIT`で読む。両者はtenant GUCの欠損/不正を成功にせず、行欠損・読取例外はfail-closed、新4（旧新2）では古い`open`行でも`false`を返す。`SECURITY DEFINER`、専用owner、固定search_path、完全修飾表名にし、関数作成と同じtransactionで`REVOKE EXECUTE ... FROM PUBLIC`、`GRANT EXECUTE ... TO pitchlog_app`を**この2件だけ**実行する。復元開始関数と製品open成功は旧新5側に置く。関数本文・GUC判定・戻り例外分類を最終DDLとして確定する前に実DBで検証する。

**2関数のSQL本文候補**（製品資産では未作成。`app.tenant_id`は認証根拠ではなく、欠損/不正入力を閉じるための形検査）:

```sql
CREATE FUNCTION rg1_api.rg1_read_open() RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $rg1$
DECLARE
    tenant_context uuid;
    gate_state text;
BEGIN
    tenant_context := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
    IF tenant_context IS NULL THEN RETURN false; END IF;
    SELECT state INTO STRICT gate_state
      FROM public.rg1_restore_gate WHERE singleton_id = 1;
    RETURN false;
END;
$rg1$;
ALTER FUNCTION rg1_api.rg1_read_open() OWNER TO pitchlog_rg1_fn_owner;
REVOKE EXECUTE ON FUNCTION rg1_api.rg1_read_open() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rg1_api.rg1_read_open() TO pitchlog_app;

CREATE FUNCTION rg1_api.rg1_assert_open_before_commit() RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $rg1$
DECLARE
    tenant_context uuid;
    gate_state text;
BEGIN
    tenant_context := NULLIF(pg_catalog.current_setting('app.tenant_id', true), '')::uuid;
    IF tenant_context IS NULL THEN RETURN false; END IF;
    SELECT state INTO STRICT gate_state
      FROM public.rg1_restore_gate WHERE singleton_id = 1
      FOR SHARE NOWAIT;
    RETURN false;
END;
$rg1$;
ALTER FUNCTION rg1_api.rg1_assert_open_before_commit()
    OWNER TO pitchlog_rg1_fn_owner;
REVOKE EXECUTE ON FUNCTION rg1_api.rg1_assert_open_before_commit() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rg1_api.rg1_assert_open_before_commit() TO pitchlog_app;
```

戻り値は新4では意図的に常に`false`であり、`gate_state`を`true`判定に使用しない。行ロックは当該transactionの終端まで保持する。`SELECT INTO STRICT`の欠損や`NOWAIT`衝突は例外としてscopeをrollbackし、Port境界でB7/P3 B10へ写す。未定義の例外を成功に変えない。関数作成・owner変更・PUBLIC剥奪・app限定付与は**同一transaction**に束ね、既定EXECUTEが外部へ露出する中間確定を作らない。列ACL/2 policyの順序、definer実行時のロック権限、例外分類は実DBで測定してから最終資産承認へ提出する。

```json
{
  "table": "rg1_restore_gate",
  "profile": "function_only",
  "access_path": {
    "reason": "restore_gate_global_mutable",
    "owner_unit": "U-R1"
  }
}
```

上の1行を`contracts/authz/product/table-classification.json`の`tables`へ加える。`ddl-elements.json`へrole 1件（`login:false,bypass_rls:false,inherit:false`等は上記DDLに一致）、`rg1_api` schema 1件、`public` schemaの専用owner`USAGE` 1件、表1件（`enable_row_level_security:true,force_row_level_security:true`）、SELECT/UPDATE policy各1件、列ACLと2関数のEXECUTE宣言を加える。既存の`exposure-facts.json`にはRG1だけの新事実と`data-model.md`の正確な証拠節を加え、`classification.py`の閉じた`FACT_KINDS`/`FUNCTION_ONLY_FACT_KINDS`/`FUNCTION_OWNER_UNITS`には**RG1専用例外だけ**を加える。現行の`non_tenant`事実へ追加すると`global_read_only`を強制するため、同kindは使わない。正本§3-2のrole数・用途と特別露出事実の改訂は7.6/必要な7.3で別確定する。派生manifest/lock/oracle/運用catalogは実入力が変わるものだけ追随する。

`ddl-elements.json`の主要追加行は次の**申請用JSON候補**とする。配列上の挿入位置、生成されたfunction body/manifest、canonical digestはA統合後の実差分で確定する。既存の行・順序を改変しない。

```json
{
  "role": {
    "role_id": "pitchlog_rg1_fn_owner", "creation": "product_ddl",
    "superuser": false, "bypass_rls": false, "login": false,
    "create_role": false, "create_db": false, "replication": false,
    "inherit": false
  },
  "table": {
    "table_id": "rg1_restore_gate", "schema_name": "public",
    "enable_row_level_security": true, "force_row_level_security": true
  },
  "select_policy": {
    "policy_id": "POLICY:rg1_restore_gate:rg1_fn_select_singleton",
    "table_id": "rg1_restore_gate", "profile": "function_only",
    "policy_name": "rg1_fn_select_singleton", "command": "SELECT",
    "policy_mode": "permissive", "role_ids": ["pitchlog_rg1_fn_owner"],
    "using_predicate_id": null, "using_column": null,
    "using_expression": "singleton_id = 1",
    "with_check_predicate_id": null, "with_check_column": null,
    "with_check_expression": null
  },
  "update_policy": {
    "policy_id": "POLICY:rg1_restore_gate:rg1_fn_lock_singleton",
    "table_id": "rg1_restore_gate", "profile": "function_only",
    "policy_name": "rg1_fn_lock_singleton", "command": "UPDATE",
    "policy_mode": "permissive", "role_ids": ["pitchlog_rg1_fn_owner"],
    "using_predicate_id": null, "using_column": null,
    "using_expression": "singleton_id = 1",
    "with_check_predicate_id": null, "with_check_column": null,
    "with_check_expression": "singleton_id = 1"
  },
  "read_function": {
    "function_id": "FUNCTION:rg1_api:rg1_read_open()",
    "schema_name": "rg1_api", "function_name": "rg1_read_open",
    "identity_args": "", "function_kind": "definer",
    "owner_role_id": "pitchlog_rg1_fn_owner", "language": "plpgsql",
    "returns": "boolean", "security_mode": "definer", "volatility": "volatile",
    "search_path": ["pg_catalog", "pg_temp"],
    "acl_expectations": [{"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": false}],
    "revoked_acl_expectations": [{"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": false}]
  },
  "commit_function": {
    "function_id": "FUNCTION:rg1_api:rg1_assert_open_before_commit()",
    "schema_name": "rg1_api", "function_name": "rg1_assert_open_before_commit",
    "identity_args": "", "function_kind": "definer",
    "owner_role_id": "pitchlog_rg1_fn_owner", "language": "plpgsql",
    "returns": "boolean", "security_mode": "definer", "volatility": "volatile",
    "search_path": ["pg_catalog", "pg_temp"],
    "acl_expectations": [{"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": false}],
    "revoked_acl_expectations": [{"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": false}]
  }
}
```

これは`ddl-elements.json`のルートへ`role`等のキーを追加する指示ではなく、既存`roles`/`tables`/`policies`/`functions`配列へ入れる**各行の完全な値**を一つの表示用objectに束ねたもの。`rg1_api` schemaのACL、`public` schemaのowner USAGE、列SELECT/UPDATE ACL、RG1専用露出事実も同じ差分に含める。これらは既存asset schemaと実DB検査の結果を踏まえ、正式個別承認前に全行差分として提示する。

`repository-contract.json`はAの実登録形式が確定してから、RG1用token/operation ID各2件、`SQLA_SELECT`限定の`pitchlog.repositories.rg1._build_rg1_read_statement`（`kind`は`precheck`/`commit_check`の2値だけ）を追加する。`operation_registry.py`の製品登録も2件だけ。Aの共有実行器・既存シンボルの許可、DML経路、テナント束縛は拡大しない。`base-allowlist.json`ほか7資産のrevision・digest・snapshot・入力blob・movement_fact/reasonは**A統合後の最新develop**から採取し、この文書の仮値や旧試算を使用しない。

**現行JSON/検査器との正確な衝突**: `ddl-elements.json`には`column_acl_expectations`群が既にあり、列単位の候補を宣言できる。ただし現行`backend/src/pitchlog/authz/product_control_access.py::generate_function_owner_column_acl_sql`と`scripts/check_authz_catalog.py`の追加definer用列ACLは`privilege_ids == ["SELECT"]`だけを受理する。必要最小の`UPDATE(singleton_id)`を下記のように書くと現行検査は**不合格**。表全体のUPDATEへ広げて回避しない。RG1の`singleton_id`列・専用owner・commit-check関数IDの組合せ**1件だけ**に`["UPDATE"]`を許可し、生成SQL・catalog exact-set・負例を同じ個別資産差分へ含める必要がある。これは5項目の方針承認に含まれる権限の具体化だが、**検査器と凍結資産の正確な変更は別承認対象**。

```json
{
  "expectation_id": "COLUMN-ACL:public:rg1_restore_gate:singleton_id:pitchlog_rg1_fn_owner",
  "object_kind": "column",
  "object_schema": "public",
  "object_id": "rg1_restore_gate",
  "column_id": "singleton_id",
  "grantee_role_id": "pitchlog_rg1_fn_owner",
  "privilege_ids": ["UPDATE"],
  "grant_option": false,
  "function_id": "FUNCTION:rg1_api:rg1_assert_open_before_commit()"
}
```

`SELECT(singleton_id,state)`も同じ群の2行で宣言し、`UPDATE(state)`、表UPDATE、他ownerのUPDATEを拒否する。現行checkerの`SELECT`限定を一般化するのではなく、RG1 exact tupleだけを許す。`data-model.md`の新事実とDDL/JSON全体の最終承認前に、生成SQLと実DBで`SELECT FOR SHARE NOWAIT`がこの列権限・SELECT/UPDATE policy下で通るかを測定する。通らなければ権限を独断で拡大せず、差分を再提示する。

## 資産の候補集合と確認点

次は**設計方針から導いた審査対象**であり、正確なDDL/JSON承認値ではない。A統合後の実形式で全行差分を固定してから個別承認を受ける。

| 資産 | 提案する具体的な差分 | 未確定・拒否条件 |
| --- | --- | --- |
| DB DDL | `public.rg1_restore_gate(singleton_id smallint PRIMARY KEY CHECK(singleton_id=1), state text NOT NULL CHECK(state IN ('closed','open')))`の1行`(1,'closed')`、`ENABLE/FORCE ROW LEVEL SECURITY`。`rg1_api` schema、`pitchlog_rg1_fn_owner`=`NOLOGIN/NOBYPASSRLS`。同ownerだけ`SELECT(singleton_id,state)`と`UPDATE(singleton_id)`、singleton限定SELECT/UPDATE policy。読取2関数は`SECURITY DEFINER`・固定search_path・PUBLIC EXECUTE剥奪、appには2件だけEXECUTE | 正確なSQL・seed/RLS適用順、role/schema/列ACLの実効値と既存policy合成は実DBで検証。app表ACL、INSERT/DELETE policy、復元開始関数、製品openを追加しない |
| 関数・固定登録 | `rg1_api.rg1_read_open()`は③-a非ロック、`rg1_api.rg1_assert_open_before_commit()`は⑧`FOR SHARE NOWAIT`。両者は新2では古いopen行でも常にfalse。Aの固定関数registryへtoken/operation ID各2件、固定SQL、exact bool結果、0/複数行・未知token拒否 | function bodyとTSK-550実登録schemaの最終形はA統合後に確定。任意SQL、Session、汎用FOR SHARE、DML実行器の緩和なし |
| JSON/正本 | `data-model.md`§3-2の専用roleとRG1の非テナント制御事実、`table-classification.json`のRG1 1表`function_only`/`owner_unit: U-R1`、露出事実・owner許可集合、`ddl-elements.json`/function-bodies/manifest/認可runtimeの1表・2関数・ACL/policy、repository-contractの2登録と必要な最小SQLA_SELECT symbol/正負fixtureを差分化 | 現行分類器は非テナント`function_only`を拒否するため、正本7.6・必要な7.3と認可担当のゲートが必要。既存分類・既存関数/allowlist symbolの権限拡大なし。実JSON key、revision、digestはA統合後に提示 |
| 派生・履歴 | 変化した入力に限りlock/oracle、archive、7資産のsnapshotを追随。authorityは`base-allowlist.json`。新2PR番号の単一記録を候補afterと照合して正式受理後に追記 | 既受理済み履歴・before・PR #72 markerは不変。A統合後の実before/after、blob、movement_fact/reasonと人間の受理記録が必要 |

## 試験と7.7の停止点

1. **候補段階**: PostgreSQL実DBでowner属性、FORCE RLS、policy/ACL exact-set、app表4操作・PUBLIC/未知関数EXECUTE拒否、他policyとの合成、`FOR SHARE NOWAIT`競合、欠損/不正状態/読取例外のfail-closedを確認する。隔離DBの開状態行に対する直接行ロック正常系と、製品2関数の常閉拒否を**別試験**にする。P3はB10、全scope取消、隠れた自動再送なし。
2. **固定実行器**: Aの2登録についてtoken偽造・失効・余計なbind・未知kind・型違い・SQL束縛値/同一scopeを検証し、既存DMLやテナント境界の負例を維持する。U-G1/U-S1実経路の結合は新6。
3. **7.7候補提示**: 実before/after revision・canonical digest・snapshot/blob・全変更ファイル・movement_fact/reason・PR番号と独立レビューを人間へ提示する。履歴検査の予期した赤を明示し、受理済みとは記録しない。
4. **正式受理後**: 実承認者/日付を転記してauthority台帳1件、派生資産/archiveを整合させる。作業ツリーでDB/認可・pytest/ruff/ty等を確認し、許可されたコミット後にGit HEADを読む履歴・契約差分検査とPR CIをgreenにする。コアガードと人間逐行確認もPRの完了ゲート。未受理の候補をpush・mergeしない。

## 残る人間判断の順序

1. 本[順序追補案](step2-acceptance-order-addendum-proposal.md)の**最終計画承認**。追加独立レビューでP0/P1が残れば修正案・影響を再提示する。
2. A統合後、正確なDDL/JSON・必要正本、候補作成の限定許可、必要なら準備push/Draftまたはsnapshot中間コミットのGit操作を個別に判断する。
3. 候補の実revision/digest/snapshot/全差分に対し、PR最終候補状態の7.7正式受理を判断する。

D4方式・製品open/復元開始は新5側、新6実経路結合は別ゲート。mergeは本資料の射程外。
