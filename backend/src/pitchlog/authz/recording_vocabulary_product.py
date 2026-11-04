"""有効打球語彙readの有限宣言/SQLをcanonical producerへ供給する。"""

import copy

ADDITIONS = {
    "roles": [
        {
            "role_id": "pitchlog_recording_vocab_fn_owner",
            "creation": "product_ddl",
            "superuser": False,
            "bypass_rls": False,
            "login": False,
            "create_role": False,
            "create_db": False,
            "replication": False,
            "inherit": False,
        }
    ],
    "schemas": [
        {
            "schema_id": "recording_vocab_api",
            "schema_name": "recording_vocab_api",
            "creation": "product_ddl",
            "owner": "pitchlog_recording_vocab_fn_owner",
            "ownership_path": "direct",
            "acl_expectations": [
                {"grantee": "pitchlog_app", "privilege": "USAGE", "grantable": False}
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "USAGE", "grantable": False},
                {"grantee": "PUBLIC", "privilege": "CREATE", "grantable": False},
                {"grantee": "pitchlog_app", "privilege": "CREATE", "grantable": False},
            ],
        }
    ],
    "functions": [
        {
            "function_id": (
                "FUNCTION:recording_vocab_api:"
                "read_batted_ball_options(uuid, integer, text)"
            ),
            "schema_name": "recording_vocab_api",
            "function_name": "read_batted_ball_options",
            "identity_args": "uuid, integer, text",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_recording_vocab_fn_owner",
            "language": "plpgsql",
            "returns": "TABLE(key text, display_name text)",
            "security_mode": "definer",
            "volatility": "stable",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False}
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
            ],
        }
    ],
    "policies": [
        {
            "policy_id": "POLICY:admin_vocabularies:recording_vocab_select_batted_ball",
            "table_id": "admin_vocabularies",
            "profile": "function_only",
            "policy_name": "recording_vocab_select_batted_ball",
            "command": "SELECT",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_recording_vocab_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            "using_expression": "category = 'batted_ball' AND disabled = false AND "
            "session_user = 'pitchlog_app' AND "
            "NULLIF(pg_catalog.current_setting('app.tenant_id', "
            "true), '') IS NOT NULL",
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": None,
        }
    ],
    "column_acl_expectations": [
        {
            "expectation_id": (
                "COLUMN-ACL:public:admin_vocabularies:key:pitchlog_"
                "recording_vocab_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "admin_vocabularies",
            "column_id": "key",
            "grantee_role_id": "pitchlog_recording_vocab_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            "expectation_id": (
                "COLUMN-ACL:public:admin_vocabularies:category:pitc"
                "hlog_recording_vocab_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "admin_vocabularies",
            "column_id": "category",
            "grantee_role_id": "pitchlog_recording_vocab_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            "expectation_id": (
                "COLUMN-ACL:public:admin_vocabularies:display_name:"
                "pitchlog_recording_vocab_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "admin_vocabularies",
            "column_id": "display_name",
            "grantee_role_id": "pitchlog_recording_vocab_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            "expectation_id": (
                "COLUMN-ACL:public:admin_vocabularies:disabled:pitc"
                "hlog_recording_vocab_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "admin_vocabularies",
            "column_id": "disabled",
            "grantee_role_id": "pitchlog_recording_vocab_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
    ],
}

BODIES = {
    (
        "function|FUNCTION:recording_vocab_api:read_batted_"
        "ball_options(uuid, integer, text)"
    ): "CREATE "
    "FUNCTION "
    "recording_vocab_api.read_batted_ball_options(\n"
    "  "
    "p_tenant_id "
    "uuid, "
    "p_page_size "
    "integer, "
    "p_cursor_key "
    "text\n"
    ") "
    "RETURNS "
    "TABLE(key "
    "text, "
    "display_name "
    "text)\n"
    "LANGUAGE "
    "plpgsql "
    "STABLE "
    "SECURITY "
    "DEFINER\n"
    "SET "
    "search_path "
    "= "
    "pg_catalog, "
    "pg_temp\n"
    "AS "
    "$function$\n"
    "BEGIN\n"
    "  "
    "IF "
    "session_user "
    "<> "
    "'pitchlog_app'\n"
    "     "
    "OR "
    "current_user "
    "<> "
    "'pitchlog_recording_vocab_fn_owner'\n"
    "     "
    "OR "
    "p_tenant_id "
    "IS "
    "NULL\n"
    "     "
    "OR "
    "pg_catalog.current_setting('app.tenant_id', "
    "true)\n"
    "        "
    "IS "
    "DISTINCT "
    "FROM "
    "p_tenant_id::text "
    "THEN\n"
    "    "
    "RAISE "
    "EXCEPTION "
    "USING "
    "ERRCODE "
    "= "
    "'42501', "
    "MESSAGE "
    "= "
    "'recording "
    "vocabulary "
    "scope "
    "mismatch';\n"
    "  "
    "END "
    "IF;\n"
    "  "
    "IF "
    "p_page_size "
    "IS "
    "NULL "
    "OR "
    "p_page_size "
    "< "
    "1 "
    "OR "
    "p_page_size "
    "> "
    "100 "
    "OR "
    "p_cursor_key "
    "IS "
    "NULL "
    "THEN\n"
    "    "
    "RAISE "
    "EXCEPTION "
    "USING "
    "ERRCODE "
    "= "
    "'22023', "
    "MESSAGE "
    "= "
    "'recording "
    "vocabulary "
    "page "
    "invalid';\n"
    "  "
    "END "
    "IF;\n"
    "  "
    "IF "
    "p_cursor_key "
    "= "
    "'' "
    "THEN\n"
    "    "
    "RETURN "
    "QUERY\n"
    "      "
    "SELECT "
    "v.key, "
    "v.display_name\n"
    "      "
    "FROM "
    "public.admin_vocabularies "
    "AS "
    "v\n"
    "      "
    "WHERE "
    "v.category "
    "= "
    "'batted_ball' "
    "AND "
    "v.disabled "
    "= "
    "false\n"
    "      "
    "ORDER "
    "BY "
    "v.key "
    "COLLATE "
    '"C"\n'
    "      "
    "LIMIT "
    "p_page_size "
    "+ "
    "1;\n"
    "  "
    "ELSE\n"
    "    "
    "RETURN "
    "QUERY\n"
    "      "
    "SELECT "
    "v.key, "
    "v.display_name\n"
    "      "
    "FROM "
    "public.admin_vocabularies "
    "AS "
    "v\n"
    "      "
    "WHERE "
    "v.category "
    "= "
    "'batted_ball' "
    "AND "
    "v.disabled "
    "= "
    "false\n"
    "        "
    "AND "
    "v.key "
    "COLLATE "
    '"C" '
    "> "
    "p_cursor_key "
    "COLLATE "
    '"C"\n'
    "      "
    "ORDER "
    "BY "
    "v.key "
    "COLLATE "
    '"C"\n'
    "      "
    "LIMIT "
    "p_page_size "
    "+ "
    "1;\n"
    "  "
    "END "
    "IF;\n"
    "END;\n"
    "$function$;\n"
    "\n"
    "ALTER "
    "FUNCTION "
    "recording_vocab_api.read_batted_ball_options(uuid, "
    "integer, "
    "text) "
    "OWNER "
    "TO "
    "pitchlog_recording_vocab_fn_owner;\n"
    "REVOKE "
    "ALL "
    "ON "
    "FUNCTION "
    "recording_vocab_api.read_batted_ball_options(uuid, "
    "integer, "
    "text) "
    "FROM "
    "PUBLIC,pitchlog_app;\n"
    "GRANT "
    "EXECUTE "
    "ON "
    "FUNCTION "
    "recording_vocab_api.read_batted_ball_options(uuid, "
    "integer, "
    "text) "
    "TO "
    "pitchlog_app;\n",
    (
        "policy|POLICY:admin_vocabularies:recording_vocab_select_batted_ball"
    ): "CREATE POLICY "
    "recording_vocab_select_batted_ball "
    "ON "
    "public.admin_vocabularies "
    "AS PERMISSIVE FOR "
    "SELECT TO "
    "pitchlog_recording_vocab_fn_owner "
    "USING (category = "
    "'batted_ball' AND "
    "disabled = false "
    "AND session_user "
    "= 'pitchlog_app' "
    "AND "
    "NULLIF(pg_catalog.current_setting('app.tenant_id', "
    "true), '') IS NOT "
    "NULL);\n",
    (
        "column_acl_expectation|COLUMN-ACL:public:admin_voc"
        "abularies:key:pitchlog_recording_vocab_fn_owner"
    ): "GRANT "
    "SELECT "
    "(key) "
    "ON "
    "TABLE "
    "public.admin_vocabularies "
    "TO "
    "pitchlog_recording_vocab_fn_owner;\n",
    (
        "column_acl_expectation|COLUMN-ACL:public:admin_voc"
        "abularies:category:pitchlog_recording_vocab_fn_own"
        "er"
    ): "GRANT "
    "SELECT "
    "(category) "
    "ON "
    "TABLE "
    "public.admin_vocabularies "
    "TO "
    "pitchlog_recording_vocab_fn_owner;\n",
    (
        "column_acl_expectation|COLUMN-ACL:public:admin_voc"
        "abularies:display_name:pitchlog_recording_vocab_fn"
        "_owner"
    ): "GRANT "
    "SELECT "
    "(display_name) "
    "ON "
    "TABLE "
    "public.admin_vocabularies "
    "TO "
    "pitchlog_recording_vocab_fn_owner;\n",
    (
        "column_acl_expectation|COLUMN-ACL:public:admin_voc"
        "abularies:disabled:pitchlog_recording_vocab_fn_own"
        "er"
    ): "GRANT "
    "SELECT "
    "(disabled) "
    "ON "
    "TABLE "
    "public.admin_vocabularies "
    "TO "
    "pitchlog_recording_vocab_fn_owner;\n",
    "role|pitchlog_recording_vocab_fn_owner": "DO $authz$\n"
    "BEGIN\n"
    " IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles "
    "WHERE "
    "rolname='pitchlog_recording_vocab_fn_owner') "
    "THEN\n"
    "  IF NOT EXISTS(SELECT 1 FROM "
    "pg_catalog.pg_roles r WHERE "
    "r.rolname='pitchlog_recording_vocab_fn_owner'\n"
    "   AND r.rolcanlogin IS FALSE AND NOT "
    "r.rolsuper AND NOT r.rolbypassrls AND NOT "
    "r.rolinherit\n"
    "   AND NOT r.rolcreaterole AND NOT "
    "r.rolcreatedb AND NOT r.rolreplication\n"
    "   AND r.rolconnlimit=-1 AND r.rolvaliduntil "
    "IS NULL\n"
    "   AND NOT EXISTS(SELECT 1 FROM "
    "pg_catalog.pg_auth_members m WHERE "
    "m.roleid=r.oid OR m.member=r.oid)) THEN\n"
    "    RAISE EXCEPTION 'sync role collision: "
    "pitchlog_recording_vocab_fn_owner';\n"
    "  END IF;\n"
    " ELSE\n"
    "  CREATE ROLE "
    "pitchlog_recording_vocab_fn_owner NOLOGIN "
    "NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEROLE "
    "NOCREATEDB NOREPLICATION;\n"
    " END IF;\n"
    "END;$authz$;\n",
    "schema|recording_vocab_api": "DO $recording_vocab_schema$\n"
    "BEGIN\n"
    " IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n\n"
    "  JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner\n"
    "  WHERE n.nspname='recording_vocab_api' AND "
    "r.rolname='pitchlog_recording_vocab_fn_owner') THEN\n"
    "  IF EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE "
    "nspname='recording_vocab_api') THEN\n"
    "   RAISE EXCEPTION 'recording vocabulary schema "
    "collision';\n"
    "  END IF;\n"
    "  CREATE SCHEMA recording_vocab_api AUTHORIZATION "
    "pitchlog_recording_vocab_fn_owner;\n"
    " END IF;\n"
    "END;$recording_vocab_schema$;\n"
    "REVOKE ALL ON SCHEMA recording_vocab_api FROM PUBLIC;\n"
    "REVOKE CREATE ON SCHEMA recording_vocab_api FROM "
    "pitchlog_app;\n"
    "GRANT USAGE ON SCHEMA recording_vocab_api TO "
    "pitchlog_app;\n",
}

PUBLIC_USAGE_SQL = (
    "GRANT USAGE ON SCHEMA public TO pitchlog_recording_vocab_fn_owner;\n"
)


def candidate_declarations():
    """正式publisherが独立値から派生するためのコピーを返す。"""
    return copy.deepcopy(ADDITIONS), dict(BODIES)
