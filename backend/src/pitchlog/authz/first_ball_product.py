"""初球権検証の製品認可差分をexact集合として閉じる。"""

from __future__ import annotations

import copy
from typing import Any

ADDITIONS: dict[str, list[dict[str, Any]]] = {
    "roles": [
        {
            "role_id": "pitchlog_sync_binding_fn_owner",
            "creation": "product_ddl",
            "superuser": False,
            "bypass_rls": False,
            "login": False,
            "create_role": False,
            "create_db": False,
            "replication": False,
            "inherit": False,
        },
        {
            "role_id": "pitchlog_sync_binding_actor",
            "creation": "product_ddl",
            "superuser": False,
            "bypass_rls": False,
            "login": True,
            "create_role": False,
            "create_db": False,
            "replication": False,
            "inherit": False,
        },
        {
            "role_id": "pitchlog_sync_right_fn_owner",
            "creation": "product_ddl",
            "superuser": False,
            "bypass_rls": False,
            "login": False,
            "create_role": False,
            "create_db": False,
            "replication": False,
            "inherit": False,
        },
    ],
    "schemas": [
        {
            "schema_id": "sync_fence",
            "schema_name": "sync_fence",
            "creation": "existing",
            "owner": "pitchlog_owner",
            "ownership_path": "direct",
            "acl_expectations": [
                {
                    "grantee": "pitchlog_sync_binding_fn_owner",
                    "privilege": "USAGE",
                    "grantable": False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "USAGE", "grantable": False},
                {"grantee": "PUBLIC", "privilege": "CREATE", "grantable": False},
                {
                    "grantee": "pitchlog_sync_binding_fn_owner",
                    "privilege": "CREATE",
                    "grantable": False,
                },
            ],
        },
        {
            "schema_id": "sync_fence_api",
            "schema_name": "sync_fence_api",
            "creation": "product_ddl",
            "owner": "pitchlog_sync_binding_fn_owner",
            "ownership_path": "direct",
            "acl_expectations": [
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("USAGE"),
                    ("grantable"): False,
                },
                {
                    "grantee": "pitchlog_sync_binding_actor",
                    "privilege": "USAGE",
                    "grantable": False,
                },
                {
                    "grantee": "pitchlog_sync_right_fn_owner",
                    "privilege": "USAGE",
                    "grantable": False,
                },
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "USAGE", "grantable": False},
                {"grantee": "PUBLIC", "privilege": "CREATE", "grantable": False},
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("CREATE"),
                    ("grantable"): False,
                },
                {
                    "grantee": "pitchlog_sync_binding_actor",
                    "privilege": "CREATE",
                    "grantable": False,
                },
                {
                    "grantee": "pitchlog_sync_right_fn_owner",
                    "privilege": "CREATE",
                    "grantable": False,
                },
            ],
        },
        {
            "schema_id": "sync_right_api",
            "schema_name": "sync_right_api",
            "creation": "product_ddl",
            "owner": "pitchlog_sync_right_fn_owner",
            "ownership_path": "direct",
            "acl_expectations": [
                {"grantee": "pitchlog_app", "privilege": "USAGE", "grantable": False}
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "USAGE", "grantable": False},
                {"grantee": "PUBLIC", "privilege": "CREATE", "grantable": False},
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("CREATE"),
                    ("grantable"): False,
                },
            ],
        },
    ],
    "tables": [
        {
            "table_id": "writer_bindings",
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        },
        {
            "table_id": "writer_admissions",
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        },
        {
            "table_id": "first_ball_write_admissions",
            "schema_name": "sync_fence",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        },
    ],
    "policies": [
        {
            "policy_id": "POLICY:writer_bindings:binding_owner",
            "table_id": "writer_bindings",
            "profile": "function_only",
            "policy_name": "binding_owner",
            "command": "ALL",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_sync_binding_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            "using_expression": "true",
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": "true",
        },
        {
            "policy_id": "POLICY:writer_admissions:admission_owner",
            "table_id": "writer_admissions",
            "profile": "function_only",
            "policy_name": "admission_owner",
            "command": "ALL",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_sync_binding_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            "using_expression": "true",
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": "true",
        },
        {
            "policy_id": "POLICY:rg1_restore_gate:binding_gate",
            "table_id": "rg1_restore_gate",
            "profile": "function_only",
            "policy_name": "binding_gate",
            "command": "SELECT",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_sync_binding_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            "using_expression": "singleton_id=1",
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": None,
        },
        {
            "policy_id": "POLICY:trusted_devices:sync_first_ball_select",
            "table_id": "trusted_devices",
            "profile": "function_only",
            "policy_name": "sync_first_ball_select",
            "command": "SELECT",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_sync_right_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            ("using_expression"): (
                "tenant_id=NULLIF(pg_catalog.cu"
                "rrent_setting('app.tenant_id',"
                "true),'')::uuid"
            ),
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": None,
        },
        {
            "policy_id": "POLICY:recording_generations:sync_first_ball_select",
            "table_id": "recording_generations",
            "profile": "function_only",
            "policy_name": "sync_first_ball_select",
            "command": "SELECT",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_sync_right_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            ("using_expression"): (
                "tenant_id=NULLIF(pg_catalog.cu"
                "rrent_setting('app.tenant_id',"
                "true),'')::uuid"
            ),
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": None,
        },
        {
            "policy_id": "POLICY:trusted_devices:sync_first_ball_device_lock",
            "table_id": "trusted_devices",
            "profile": "function_only",
            "policy_name": "sync_first_ball_device_lock",
            "command": "UPDATE",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_sync_right_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            ("using_expression"): (
                "tenant_id=NULLIF(pg_catalog.cu"
                "rrent_setting('app.tenant_id',"
                "true),'')::uuid"
            ),
            "with_check_predicate_id": None,
            "with_check_column": None,
            ("with_check_expression"): (
                "tenant_id=NULLIF(pg_catalog.cu"
                "rrent_setting('app.tenant_id',"
                "true),'')::uuid"
            ),
        },
        {
            "policy_id": "POLICY:rg1_restore_gate:sync_first_ball_gate",
            "table_id": "rg1_restore_gate",
            "profile": "function_only",
            "policy_name": "sync_first_ball_gate",
            "command": "SELECT",
            "policy_mode": "permissive",
            "role_ids": ["pitchlog_sync_right_fn_owner"],
            "using_predicate_id": None,
            "using_column": None,
            "using_expression": "singleton_id=1",
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": None,
        },
    ],
    "functions": [
        {
            ("function_id"): (
                "FUNCTION:sync_fence_api:read_writer_database_identity(uuid)"
            ),
            "schema_name": "sync_fence_api",
            "function_name": "read_writer_database_identity",
            "identity_args": "uuid",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_binding_fn_owner",
            "language": "plpgsql",
            "returns": "TABLE(system_identifier text, database_oid text, "
            "postmaster_started_at timestamp with time zone)",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
            ],
        },
        {
            "function_id": "FUNCTION:sync_fence_api:read_writer_identity(uuid)",
            "schema_name": "sync_fence_api",
            "function_name": "read_writer_identity",
            "identity_args": "uuid",
            "function_kind": "invoker",
            "owner_role_id": "pitchlog_sync_binding_fn_owner",
            "language": "plpgsql",
            "returns": "TABLE(system_identifier text, database_oid text, "
            "postmaster_started_at timestamp with time zone, backend_pid "
            "integer, backend_start timestamp with time zone, "
            "transaction_id text)",
            "security_mode": "invoker",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
            ],
        },
        {
            "function_id": "FUNCTION:sync_fence_api:publish_writer_binding(uuid, "
            "uuid, uuid, jsonb, bytea)",
            "schema_name": "sync_fence_api",
            "function_name": "publish_writer_binding",
            "identity_args": "uuid, uuid, uuid, jsonb, bytea",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_binding_fn_owner",
            "language": "plpgsql",
            "returns": "void",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    "grantee": "pitchlog_sync_binding_actor",
                    "privilege": "EXECUTE",
                    "grantable": False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                },
            ],
        },
        {
            "function_id": "FUNCTION:sync_fence_api:assert_writer_binding(uuid, "
            "uuid, uuid, bytea, uuid, uuid)",
            "schema_name": "sync_fence_api",
            "function_name": "assert_writer_binding",
            "identity_args": "uuid, uuid, uuid, bytea, uuid, uuid",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_binding_fn_owner",
            "language": "plpgsql",
            "returns": "void",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                },
                {
                    "grantee": "pitchlog_sync_right_fn_owner",
                    "privilege": "EXECUTE",
                    "grantable": False,
                },
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
            ],
        },
        {
            ("function_id"): (
                "FUNCTION:sync_fence_api:close_"
                "writer_binding(uuid, uuid, uui"
                "d, uuid, uuid)"
            ),
            "schema_name": "sync_fence_api",
            "function_name": "close_writer_binding",
            "identity_args": "uuid, uuid, uuid, uuid, uuid",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_binding_fn_owner",
            "language": "plpgsql",
            "returns": "void",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    "grantee": "pitchlog_sync_binding_actor",
                    "privilege": "EXECUTE",
                    "grantable": False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                },
            ],
        },
        {
            "function_id": "FUNCTION:sync_fence_api:observe_writer_binding(uuid, "
            "uuid, uuid, uuid, uuid)",
            "schema_name": "sync_fence_api",
            "function_name": "observe_writer_binding",
            "identity_args": "uuid, uuid, uuid, uuid, uuid",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_binding_fn_owner",
            "language": "plpgsql",
            "returns": "TABLE(outcome text)",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    "grantee": "pitchlog_sync_binding_actor",
                    "privilege": "EXECUTE",
                    "grantable": False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                },
            ],
        },
        {
            "function_id": "FUNCTION:sync_fence_api:guard_writer_records()",
            "schema_name": "sync_fence_api",
            "function_name": "guard_writer_records",
            "identity_args": "",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_binding_fn_owner",
            "language": "plpgsql",
            "returns": "trigger",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                },
            ],
        },
        {
            "function_id": "FUNCTION:sync_right_api:bind_device(uuid, uuid, uuid, "
            "bytea, uuid, uuid, bytea)",
            "schema_name": "sync_right_api",
            "function_name": "bind_device",
            "identity_args": "uuid, uuid, uuid, bytea, uuid, uuid, bytea",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_right_fn_owner",
            "language": "plpgsql",
            "returns": "TABLE (device_matches boolean)",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
            ],
        },
        {
            "function_id": "FUNCTION:sync_right_api:check_current_right(uuid, uuid, "
            "uuid, bytea, uuid, uuid, bigint, bigint, bytea)",
            "schema_name": "sync_right_api",
            "function_name": "check_current_right",
            "identity_args": "uuid, uuid, uuid, bytea, uuid, uuid, bigint, bigint, "
            "bytea",
            "function_kind": "definer",
            "owner_role_id": "pitchlog_sync_right_fn_owner",
            "language": "plpgsql",
            "returns": "TABLE (recovery_matches boolean, right_matches boolean)",
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {
                    ("grantee"): ("pitchlog_app"),
                    ("privilege"): ("EXECUTE"),
                    ("grantable"): False,
                }
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
            ],
        },
    ],
    "acl_expectations": [
        {
            ("acl_id"): (
                "ACL:sync_fence:writer_bindings:pitchlog_sync_binding_fn_owner"
            ),
            "object_kind": "table",
            "object_schema": "sync_fence",
            "object_id": "writer_bindings",
            "profile": "function_only",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["SELECT", "INSERT"],
            "grant_option": False,
        },
        {
            ("acl_id"): (
                "ACL:sync_fence:writer_admissions:pitchlog_sync_binding_fn_owner"
            ),
            "object_kind": "table",
            "object_schema": "sync_fence",
            "object_id": "writer_admissions",
            "profile": "function_only",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["SELECT", "INSERT"],
            "grant_option": False,
        },
        {
            ("acl_id"): (
                "ACL:pg_catalog:pg_control_system():pitchlog_sync_binding_fn_owner"
            ),
            "object_kind": "builtin_function",
            "object_schema": "pg_catalog",
            "object_id": "pg_control_system",
            "profile": "additional_builtin_execute",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["EXECUTE"],
            "grant_option": False,
        },
    ],
    "column_acl_expectations": [
        {
            ("expectation_id"): (
                "COLUMN-ACL:sync_fence:writer_b"
                "indings:state:pitchlog_sync_bi"
                "nding_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "sync_fence",
            "object_id": "writer_bindings",
            "column_id": "state",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["UPDATE"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:sync_fence:writer_b"
                "indings:close_id:pitchlog_sync"
                "_binding_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "sync_fence",
            "object_id": "writer_bindings",
            "column_id": "close_id",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["UPDATE"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:rg1_restore_"
                "gate:singleton_id:pitchlog_syn"
                "c_binding_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": "singleton_id",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:rg1_restore_"
                "gate:state:pitchlog_sync_bindi"
                "ng_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": "state",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:rg1_restore_"
                "gate:recovery_generation:pitch"
                "log_sync_binding_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": "recovery_generation",
            "grantee_role_id": "pitchlog_sync_binding_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:trusted_devi"
                "ces:tenant_id:pitchlog_sync_ri"
                "ght_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "trusted_devices",
            "column_id": "tenant_id",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:trusted_devi"
                "ces:device_id:pitchlog_sync_ri"
                "ght_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "trusted_devices",
            "column_id": "device_id",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:trusted_devi"
                "ces:credential_digest:pitchlog"
                "_sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "trusted_devices",
            "column_id": "credential_digest",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:trusted_devi"
                "ces:revoked_at:pitchlog_sync_r"
                "ight_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "trusted_devices",
            "column_id": "revoked_at",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT", "UPDATE"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:tenant_id:pitchlog_s"
                "ync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "tenant_id",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:game_id:pitchlog_syn"
                "c_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "game_id",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:generation:pitchlog_"
                "sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "generation",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:kind:pitchlog_sync_r"
                "ight_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "kind",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:holder_device:pitchl"
                "og_sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "holder_device",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:revoked_at:pitchlog_"
                "sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "revoked_at",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:retired_at:pitchlog_"
                "sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "retired_at",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:proof_digest:pitchlo"
                "g_sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "proof_digest",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:recording_ge"
                "nerations:recovery_generation:"
                "pitchlog_sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "recording_generations",
            "column_id": "recovery_generation",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:rg1_restore_"
                "gate:singleton_id:pitchlog_syn"
                "c_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": "singleton_id",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:rg1_restore_gate:state:pitchlog_sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": "state",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
        {
            ("expectation_id"): (
                "COLUMN-ACL:public:rg1_restore_"
                "gate:recovery_generation:pitch"
                "log_sync_right_fn_owner"
            ),
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "rg1_restore_gate",
            "column_id": "recovery_generation",
            "grantee_role_id": "pitchlog_sync_right_fn_owner",
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        },
    ],
}

BODIES = {
    "role|pitchlog_sync_binding_fn_owner": "-- ELEMENT-TYPE: role\n"
    "-- ELEMENT-ID: pitchlog_sync_binding_fn_owner\n"
    "\n"
    "DO $authz$\n"
    "BEGIN\n"
    " IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE "
    "rolname='pitchlog_sync_binding_fn_owner') THEN\n"
    "  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE "
    "r.rolname='pitchlog_sync_binding_fn_owner'\n"
    "   AND r.rolcanlogin IS FALSE AND NOT r.rolsuper AND NOT "
    "r.rolbypassrls AND NOT r.rolinherit\n"
    "   AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT "
    "r.rolreplication\n"
    "   AND r.rolconnlimit=-1 AND r.rolvaliduntil IS NULL\n"
    "   AND NOT EXISTS(SELECT 1 FROM "
    "pg_catalog.pg_auth_members m WHERE m.roleid=r.oid OR "
    "m.member=r.oid)) THEN\n"
    "    RAISE EXCEPTION 'sync role collision: "
    "pitchlog_sync_binding_fn_owner';\n"
    "  END IF;\n"
    " ELSE\n"
    "  CREATE ROLE pitchlog_sync_binding_fn_owner NOLOGIN "
    "NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB "
    "NOREPLICATION;\n"
    " END IF;\n"
    "END;$authz$;\n",
    "role|pitchlog_sync_binding_actor": "-- ELEMENT-TYPE: role\n"
    "-- ELEMENT-ID: pitchlog_sync_binding_actor\n"
    "\n"
    "DO $authz$\n"
    "BEGIN\n"
    " IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE "
    "rolname='pitchlog_sync_binding_actor') THEN\n"
    "  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE "
    "r.rolname='pitchlog_sync_binding_actor'\n"
    "   AND r.rolcanlogin IS TRUE AND NOT r.rolsuper AND NOT "
    "r.rolbypassrls AND NOT r.rolinherit\n"
    "   AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT "
    "r.rolreplication\n"
    "   AND r.rolconnlimit=-1 AND r.rolvaliduntil IS NULL\n"
    "   AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members m "
    "WHERE m.roleid=r.oid OR m.member=r.oid)) THEN\n"
    "    RAISE EXCEPTION 'sync role collision: "
    "pitchlog_sync_binding_actor';\n"
    "  END IF;\n"
    " ELSE\n"
    "  CREATE ROLE pitchlog_sync_binding_actor LOGIN NOSUPERUSER "
    "NOBYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB "
    "NOREPLICATION;\n"
    " END IF;\n"
    "END;$authz$;\n",
    "role|pitchlog_sync_right_fn_owner": "-- ELEMENT-TYPE: role\n"
    "-- ELEMENT-ID: pitchlog_sync_right_fn_owner\n"
    "\n"
    "DO $authz$\n"
    "BEGIN\n"
    " IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE "
    "rolname='pitchlog_sync_right_fn_owner') THEN\n"
    "  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE "
    "r.rolname='pitchlog_sync_right_fn_owner'\n"
    "   AND r.rolcanlogin IS FALSE AND NOT r.rolsuper AND NOT "
    "r.rolbypassrls AND NOT r.rolinherit\n"
    "   AND NOT r.rolcreaterole AND NOT r.rolcreatedb AND NOT "
    "r.rolreplication\n"
    "   AND r.rolconnlimit=-1 AND r.rolvaliduntil IS NULL\n"
    "   AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members "
    "m WHERE m.roleid=r.oid OR m.member=r.oid)) THEN\n"
    "    RAISE EXCEPTION 'sync role collision: "
    "pitchlog_sync_right_fn_owner';\n"
    "  END IF;\n"
    " ELSE\n"
    "  CREATE ROLE pitchlog_sync_right_fn_owner NOLOGIN "
    "NOSUPERUSER NOBYPASSRLS NOINHERIT NOCREATEROLE NOCREATEDB "
    "NOREPLICATION;\n"
    " END IF;\n"
    "END;$authz$;\n",
    "table|writer_bindings": "-- ELEMENT-TYPE: table\n"
    "-- ELEMENT-ID: writer_bindings\n"
    "\n"
    "ALTER TABLE sync_fence.writer_bindings ENABLE ROW LEVEL SECURITY;\n"
    "ALTER TABLE sync_fence.writer_bindings FORCE ROW LEVEL SECURITY;\n"
    "REVOKE ALL ON TABLE sync_fence.writer_bindings FROM "
    "PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;\n",
    "table|writer_admissions": "-- ELEMENT-TYPE: table\n"
    "-- ELEMENT-ID: writer_admissions\n"
    "\n"
    "ALTER TABLE sync_fence.writer_admissions ENABLE ROW LEVEL SECURITY;\n"
    "ALTER TABLE sync_fence.writer_admissions FORCE ROW LEVEL SECURITY;\n"
    "REVOKE ALL ON TABLE sync_fence.writer_admissions FROM "
    "PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;\n",
    "table|first_ball_write_admissions": "-- ELEMENT-TYPE: table\n"
    "-- ELEMENT-ID: first_ball_write_admissions\n"
    "\n"
    "ALTER TABLE sync_fence.first_ball_write_admissions ENABLE ROW LEVEL SECURITY;\n"
    "ALTER TABLE sync_fence.first_ball_write_admissions FORCE ROW LEVEL SECURITY;\n"
    "REVOKE ALL ON TABLE sync_fence.first_ball_write_admissions FROM "
    "PUBLIC,pitchlog_app,pitchlog_sync_binding_actor;\n",
    ("function|FUNCTION:sync_fence_api:read_writer_database_identity(uuid)"): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_fence_api:rea"
        "d_writer_database_identity(uuid)\n\n"
        "CREATE FUNCTION sync_fence_api.rea"
        "d_writer_database_identity(p_tenan"
        "t_id uuid)\nRETURNS TABLE(system_id"
        "entifier text,database_oid text,po"
        "stmaster_started_at timestamptz)\nL"
        "ANGUAGE plpgsql VOLATILE SECURITY "
        "DEFINER SET search_path=pg_catalog"
        ",pg_temp AS $f$\nBEGIN\n IF session_"
        "user<>'pitchlog_app' OR p_tenant_i"
        "d IS NULL OR p_tenant_id IS DISTIN"
        "CT FROM NULLIF(current_setting('ap"
        "p.tenant_id',true),'')::uuid THEN\n"
        "  RAISE EXCEPTION 'writer database"
        " identity rejected' USING ERRCODE="
        "'42501';\n END IF;\n RETURN QUERY SE"
        "LECT c.system_identifier::text,d.o"
        "id::text,pg_postmaster_start_time("
        ")\n FROM pg_control_system() c CROS"
        "S JOIN pg_database d WHERE d.datna"
        "me=current_database();\nEND;$f$;\nAL"
        "TER FUNCTION sync_fence_api.read_w"
        "riter_database_identity(uuid) OWNE"
        "R TO pitchlog_sync_binding_fn_owne"
        "r;\nREVOKE ALL ON FUNCTION sync_fen"
        "ce_api.read_writer_database_identi"
        "ty(uuid) FROM PUBLIC;\nGRANT EXECUT"
        "E ON FUNCTION sync_fence_api.read_"
        "writer_database_identity(uuid) TO "
        "pitchlog_app;\n"
    ),
    ("function|FUNCTION:sync_fence_api:read_writer_identity(uuid)"): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_fence_api:rea"
        "d_writer_identity(uuid)\n\nCREATE FU"
        "NCTION sync_fence_api.read_writer_"
        "identity(p_tenant_id uuid)\nRETURNS"
        " TABLE(system_identifier text,data"
        "base_oid text,postmaster_started_a"
        "t timestamptz,backend_pid integer,"
        "backend_start timestamptz,transact"
        "ion_id text)\nLANGUAGE plpgsql VOLA"
        "TILE SECURITY INVOKER SET search_p"
        "ath=pg_catalog,pg_temp AS $f$\nBEGI"
        "N\n IF session_user<>'pitchlog_app'"
        " OR current_user<>'pitchlog_app' O"
        "R p_tenant_id IS NULL OR p_tenant_"
        "id IS DISTINCT FROM NULLIF(current"
        "_setting('app.tenant_id',true),'')"
        "::uuid THEN\n  RAISE EXCEPTION 'wri"
        "ter identity rejected' USING ERRCO"
        "DE='42501';\n END IF;\n RETURN QUERY"
        " SELECT c.system_identifier,c.data"
        "base_oid,c.postmaster_started_at,p"
        "g_backend_pid(),a.backend_start,pg"
        "_current_xact_id()::text\n FROM syn"
        "c_fence_api.read_writer_database_i"
        "dentity(p_tenant_id) c CROSS JOIN "
        "pg_stat_activity a WHERE a.pid=pg_"
        "backend_pid();\nEND;$f$;\nALTER FUNC"
        "TION sync_fence_api.read_writer_id"
        "entity(uuid) OWNER TO pitchlog_syn"
        "c_binding_fn_owner;\nREVOKE ALL ON "
        "FUNCTION sync_fence_api.read_write"
        "r_identity(uuid) FROM PUBLIC;\nGRAN"
        "T EXECUTE ON FUNCTION sync_fence_a"
        "pi.read_writer_identity(uuid) TO p"
        "itchlog_app;\n"
    ),
    (
        "function|FUNCTION:sync_fence_api:p"
        "ublish_writer_binding(uuid, uuid, "
        "uuid, jsonb, bytea)"
    ): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_fence_api:pub"
        "lish_writer_binding(uuid, uuid, uu"
        "id, jsonb, bytea)\n\nCREATE FUNCTION"
        " sync_fence_api.publish_writer_bin"
        "ding(p_tenant_id uuid,p_attempt_id"
        " uuid,p_phase_id uuid,p_binding js"
        "onb,p_nonce_digest bytea)\nRETURNS "
        "void LANGUAGE plpgsql VOLATILE SEC"
        "URITY DEFINER SET search_path=pg_c"
        "atalog,pg_temp AS $f$\nDECLARE r sy"
        "nc_fence.writer_bindings%ROWTYPE; "
        "observed_system text; observed_oid"
        " text;\nBEGIN\n IF session_user<>'pi"
        "tchlog_sync_binding_actor' OR p_te"
        "nant_id IS NULL OR p_attempt_id IS"
        " NULL OR p_phase_id IS NULL OR p_n"
        "once_digest IS NULL OR octet_lengt"
        "h(p_nonce_digest)<>32\n OR jsonb_ty"
        "peof(p_binding) IS DISTINCT FROM '"
        "object' OR ARRAY(SELECT jsonb_obje"
        "ct_keys(p_binding) ORDER BY 1) IS "
        "DISTINCT FROM ARRAY['authority_id'"
        ",'backend_pid','backend_start','bu"
        "siness_instance','codec_version','"
        "control_instance','control_version"
        "','d5','database_oid','device_id',"
        "'event_fingerprint','expires_at','"
        "game_id','internal_generation','is"
        "suer','lease_id','postmaster_start"
        "ed_at','recovery_generation','requ"
        "est_fingerprint','restore_epoch','"
        "system_identifier','transaction_id"
        "','wire_d4']::text[] THEN\n  RAISE "
        "EXCEPTION 'writer publication reje"
        "cted' USING ERRCODE='42501';\n END "
        "IF;\n -- JSONは固定関数の閉じた内部形式。欠損/nullは"
        "NOT NULL/有限CHECKでも拒否する。\n r:=jsonb_"
        "populate_record(NULL::sync_fence.w"
        "riter_bindings,p_binding);\n SELECT"
        " c.system_identifier::text,d.oid::"
        "text INTO STRICT observed_system,o"
        "bserved_oid FROM pg_control_system"
        "() c CROSS JOIN pg_database d WHER"
        "E d.datname=current_database();\n I"
        "F r.system_identifier IS DISTINCT "
        "FROM observed_system OR r.database"
        "_oid IS DISTINCT FROM observed_oid"
        " OR r.postmaster_started_at IS DIS"
        "TINCT FROM pg_postmaster_start_tim"
        "e()\n OR r.expires_at IS NULL OR r."
        "expires_at<=clock_timestamp() OR r"
        ".expires_at>clock_timestamp()+inte"
        "rval '30 seconds'\n OR NOT EXISTS(S"
        "ELECT FROM public.rg1_restore_gate"
        " g WHERE g.singleton_id=1 AND g.st"
        "ate='open' AND g.recovery_generati"
        "on=r.recovery_generation) THEN\n  R"
        "AISE EXCEPTION 'writer publication"
        " identity rejected' USING ERRCODE="
        "'42501';\n END IF;\n r.tenant_id:=p_"
        "tenant_id; r.attempt_id:=p_attempt"
        "_id; r.phase_id:=p_phase_id; r.non"
        "ce_digest:=p_nonce_digest; r.state"
        ":='open'; r.close_id:=NULL;\n INSER"
        "T INTO sync_fence.writer_bindings "
        "SELECT r.*;\nEND;$f$;\nALTER FUNCTIO"
        "N sync_fence_api.publish_writer_bi"
        "nding(uuid, uuid, uuid, jsonb, byt"
        "ea) OWNER TO pitchlog_sync_binding"
        "_fn_owner;\nREVOKE ALL ON FUNCTION "
        "sync_fence_api.publish_writer_bind"
        "ing(uuid, uuid, uuid, jsonb, bytea"
        ") FROM PUBLIC;\nGRANT EXECUTE ON FU"
        "NCTION sync_fence_api.publish_writ"
        "er_binding(uuid, uuid, uuid, jsonb"
        ", bytea) TO pitchlog_sync_binding_"
        "actor;\n"
    ),
    (
        "function|FUNCTION:sync_fence_api:a"
        "ssert_writer_binding(uuid, uuid, u"
        "uid, bytea, uuid, uuid)"
    ): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_fence_api:ass"
        "ert_writer_binding(uuid, uuid, uui"
        "d, bytea, uuid, uuid)\n\nCREATE FUNC"
        "TION sync_fence_api.assert_writer_"
        "binding(p_tenant_id uuid,p_attempt"
        "_id uuid,p_phase_id uuid,p_binding"
        "_nonce bytea,p_device_id uuid,p_ga"
        "me_id uuid)\nRETURNS void LANGUAGE "
        "plpgsql VOLATILE SECURITY DEFINER "
        "SET search_path=pg_catalog,pg_temp"
        " AS $f$\nDECLARE r sync_fence.write"
        "r_bindings%ROWTYPE; own_xid text; "
        "row_xmin text;\nBEGIN\n IF session_u"
        "ser<>'pitchlog_app' OR p_tenant_id"
        " IS NULL OR p_tenant_id IS DISTINC"
        "T FROM NULLIF(current_setting('app"
        ".tenant_id',true),'')::uuid\n OR p_"
        "binding_nonce IS NULL OR octet_len"
        "gth(p_binding_nonce)<>32 THEN\n  RA"
        "ISE EXCEPTION 'writer assertion re"
        "jected' USING ERRCODE='42501';\n EN"
        "D IF;\n SELECT b.* INTO STRICT r FR"
        "OM sync_fence.writer_bindings b WH"
        "ERE b.tenant_id=p_tenant_id AND b."
        "attempt_id=p_attempt_id AND b.phas"
        "e_id=p_phase_id FOR SHARE;\n own_xi"
        "d:=pg_current_xact_id()::text;\n IF"
        " r.state<>'open' OR r.expires_at<="
        "clock_timestamp() OR r.nonce_diges"
        "t<>sha256(p_binding_nonce)\n OR r.d"
        "evice_id IS DISTINCT FROM p_device"
        "_id OR r.game_id IS DISTINCT FROM "
        "p_game_id OR r.backend_pid<>pg_bac"
        "kend_pid() OR r.transaction_id<>ow"
        "n_xid\n OR r.postmaster_started_at<"
        ">pg_postmaster_start_time()\n\n OR N"
        "OT EXISTS(SELECT FROM pg_control_s"
        "ystem() c CROSS JOIN pg_database d"
        " WHERE d.datname=current_database("
        ") AND c.system_identifier::text=r."
        "system_identifier AND d.oid::text="
        "r.database_oid)\n OR NOT EXISTS(SEL"
        "ECT FROM public.rg1_restore_gate g"
        " WHERE g.singleton_id=1 AND g.stat"
        "e='open' AND g.recovery_generation"
        "=r.recovery_generation) THEN\n  RAI"
        "SE EXCEPTION 'writer binding rejec"
        "ted' USING ERRCODE='42501';\n END I"
        "F;\n INSERT INTO sync_fence.writer_"
        "admissions(tenant_id,attempt_id,ph"
        "ase_id,lease_id,transaction_id)\n V"
        "ALUES(p_tenant_id,p_attempt_id,p_p"
        "hase_id,r.lease_id,own_xid) ON CON"
        "FLICT DO NOTHING;\n SELECT a.xmin::"
        "text INTO STRICT row_xmin FROM syn"
        "c_fence.writer_admissions a WHERE "
        "a.tenant_id=p_tenant_id AND a.atte"
        "mpt_id=p_attempt_id AND a.phase_id"
        "=p_phase_id AND a.lease_id=r.lease"
        "_id AND a.transaction_id=own_xid;\n"
        " -- xid8は十進numericで扱う。INSERTがsubxi"
        "dで起きた初回savepoint進入を拒否する。\n IF row_x"
        "min::numeric<>mod(own_xid::numeric"
        ",4294967296::numeric) THEN\n  RAISE"
        " EXCEPTION 'writer admission requi"
        "res top-level transaction' USING E"
        "RRCODE='42501';\n END IF;\nEND;$f$;\n"
        "ALTER FUNCTION sync_fence_api.asse"
        "rt_writer_binding(uuid, uuid, uuid"
        ", bytea, uuid, uuid) OWNER TO pitc"
        "hlog_sync_binding_fn_owner;\nREVOKE"
        " ALL ON FUNCTION sync_fence_api.as"
        "sert_writer_binding(uuid, uuid, uu"
        "id, bytea, uuid, uuid) FROM PUBLIC"
        ";\nGRANT EXECUTE ON FUNCTION sync_f"
        "ence_api.assert_writer_binding(uui"
        "d, uuid, uuid, bytea, uuid, uuid) "
        "TO pitchlog_app;\nGRANT EXECUTE ON "
        "FUNCTION sync_fence_api.assert_wri"
        "ter_binding(uuid, uuid, uuid, byte"
        "a, uuid, uuid) TO pitchlog_sync_ri"
        "ght_fn_owner;\n"
    ),
    (
        "function|FUNCTION:sync_fence_api:c"
        "lose_writer_binding(uuid, uuid, uu"
        "id, uuid, uuid)"
    ): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_fence_api:clo"
        "se_writer_binding(uuid, uuid, uuid"
        ", uuid, uuid)\n\nCREATE FUNCTION syn"
        "c_fence_api.close_writer_binding(p"
        "_tenant_id uuid,p_attempt_id uuid,"
        "p_phase_id uuid,p_lease_id uuid,p_"
        "close_id uuid)\nRETURNS void LANGUA"
        "GE plpgsql VOLATILE SECURITY DEFIN"
        "ER SET search_path=pg_catalog,pg_t"
        "emp AS $f$\nDECLARE r sync_fence.wr"
        "iter_bindings%ROWTYPE;\nBEGIN\n IF s"
        "ession_user<>'pitchlog_sync_bindin"
        "g_actor' OR p_close_id IS NULL THE"
        "N RAISE EXCEPTION 'writer close re"
        "jected' USING ERRCODE='42501'; END"
        " IF;\n SELECT b.* INTO STRICT r FRO"
        "M sync_fence.writer_bindings b WHE"
        "RE b.tenant_id=p_tenant_id AND b.a"
        "ttempt_id=p_attempt_id AND b.phase"
        "_id=p_phase_id AND b.lease_id=p_le"
        "ase_id FOR UPDATE;\n IF r.state='cl"
        "osed' THEN\n  IF r.close_id IS DIST"
        "INCT FROM p_close_id THEN RAISE EX"
        "CEPTION 'writer close identity rej"
        "ected' USING ERRCODE='42501'; END "
        "IF;\n  RETURN;\n END IF;\n UPDATE syn"
        "c_fence.writer_bindings b SET stat"
        "e='closed',close_id=p_close_id WHE"
        "RE b.tenant_id=p_tenant_id AND b.a"
        "ttempt_id=p_attempt_id AND b.phase"
        "_id=p_phase_id;\nEND;$f$;\nALTER FUN"
        "CTION sync_fence_api.close_writer_"
        "binding(uuid, uuid, uuid, uuid, uu"
        "id) OWNER TO pitchlog_sync_binding"
        "_fn_owner;\nREVOKE ALL ON FUNCTION "
        "sync_fence_api.close_writer_bindin"
        "g(uuid, uuid, uuid, uuid, uuid) FR"
        "OM PUBLIC;\nGRANT EXECUTE ON FUNCTI"
        "ON sync_fence_api.close_writer_bin"
        "ding(uuid, uuid, uuid, uuid, uuid)"
        " TO pitchlog_sync_binding_actor;\n"
    ),
    (
        "function|FUNCTION:sync_fence_api:o"
        "bserve_writer_binding(uuid, uuid, "
        "uuid, uuid, uuid)"
    ): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_fence_api:obs"
        "erve_writer_binding(uuid, uuid, uu"
        "id, uuid, uuid)\n\nCREATE FUNCTION s"
        "ync_fence_api.observe_writer_bindi"
        "ng(p_tenant_id uuid,p_attempt_id u"
        "uid,p_phase_id uuid,p_lease_id uui"
        "d,p_close_id uuid)\nRETURNS TABLE(o"
        "utcome text) LANGUAGE plpgsql VOLA"
        "TILE SECURITY DEFINER SET search_p"
        "ath=pg_catalog,pg_temp AS $f$\nDECL"
        "ARE r sync_fence.writer_bindings%R"
        "OWTYPE; admission_count bigint; ma"
        "tching_count bigint; xid_status te"
        "xt;\nBEGIN\n IF session_user<>'pitch"
        "log_sync_binding_actor' OR current"
        "_setting('transaction_isolation')<"
        ">'read committed' THEN RAISE EXCEP"
        "TION 'writer observation rejected'"
        " USING ERRCODE='42501'; END IF;\n S"
        "ELECT b.* INTO STRICT r FROM sync_"
        "fence.writer_bindings b WHERE b.te"
        "nant_id=p_tenant_id AND b.attempt_"
        "id=p_attempt_id AND b.phase_id=p_p"
        "hase_id AND b.lease_id=p_lease_id;"
        "\n IF r.state<>'closed' OR r.close_"
        "id IS DISTINCT FROM p_close_id OR "
        "r.postmaster_started_at<>pg_postma"
        "ster_start_time()\n OR NOT EXISTS(S"
        "ELECT FROM pg_control_system() c C"
        "ROSS JOIN pg_database d WHERE d.da"
        "tname=current_database() AND c.sys"
        "tem_identifier::text=r.system_iden"
        "tifier AND d.oid::text=r.database_"
        "oid)\n OR NOT EXISTS(SELECT FROM pu"
        "blic.rg1_restore_gate g WHERE g.si"
        "ngleton_id=1 AND g.state='open' AN"
        "D g.recovery_generation=r.recovery"
        "_generation) THEN RETURN QUERY SEL"
        "ECT 'UNKNOWN'::text; RETURN; END I"
        "F;\n SELECT count(*),count(*) FILTE"
        "R(WHERE a.lease_id=r.lease_id AND "
        "a.transaction_id=r.transaction_id)"
        " INTO admission_count,matching_cou"
        "nt FROM sync_fence.writer_admissio"
        "ns a WHERE a.tenant_id=p_tenant_id"
        " AND a.attempt_id=p_attempt_id AND"
        " a.phase_id=p_phase_id;\n -- status"
        "は保存済み実xidだけを照会する。caller提供の任意xid照会口"
        "を作らない。\n xid_status:=pg_xact_status"
        "(r.transaction_id::xid8);\n RETURN "
        "QUERY SELECT CASE WHEN admission_c"
        "ount=1 AND matching_count=1 AND (x"
        "id_status IS NULL OR xid_status='c"
        "ommitted') THEN 'COMMITTED'\n WHEN "
        "admission_count=0 AND xid_status='"
        "aborted' THEN 'ROLLBACK_CONFIRMED'"
        "\n WHEN admission_count=0 AND xid_s"
        "tatus IN ('in progress','committed"
        "') THEN 'ENTRY_CLOSED_UNADMITTED' "
        "ELSE 'UNKNOWN' END;\nEND;$f$;\nALTER"
        " FUNCTION sync_fence_api.observe_w"
        "riter_binding(uuid, uuid, uuid, uu"
        "id, uuid) OWNER TO pitchlog_sync_b"
        "inding_fn_owner;\nREVOKE ALL ON FUN"
        "CTION sync_fence_api.observe_write"
        "r_binding(uuid, uuid, uuid, uuid, "
        "uuid) FROM PUBLIC;\nGRANT EXECUTE O"
        "N FUNCTION sync_fence_api.observe_"
        "writer_binding(uuid, uuid, uuid, u"
        "uid, uuid) TO pitchlog_sync_bindin"
        "g_actor;\n"
    ),
    ("function|FUNCTION:sync_fence_api:guard_writer_records()"): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_fence_api:gua"
        "rd_writer_records()\n\nCREATE FUNCTI"
        "ON sync_fence_api.guard_writer_rec"
        "ords()\nRETURNS trigger LANGUAGE pl"
        "pgsql VOLATILE SECURITY DEFINER SE"
        "T search_path=pg_catalog,pg_temp A"
        "S $f$\nBEGIN\n IF TG_TABLE_SCHEMA<>'"
        "sync_fence' OR TG_TABLE_NAME NOT I"
        "N ('writer_bindings','writer_admis"
        "sions') OR TG_OP IN ('DELETE','TRU"
        "NCATE') OR TG_TABLE_NAME='writer_a"
        "dmissions' THEN\n  RAISE EXCEPTION "
        "'writer security original is immut"
        "able' USING ERRCODE='42501';\n END "
        "IF;\n IF TG_OP<>'UPDATE' OR OLD.sta"
        "te<>'open' OR OLD.close_id IS NOT "
        "NULL OR NEW.state<>'closed' OR NEW"
        ".close_id IS NULL\n OR (to_jsonb(NE"
        "W)-'state'-'close_id') IS DISTINCT"
        " FROM (to_jsonb(OLD)-'state'-'clos"
        "e_id') THEN\n  RAISE EXCEPTION 'wri"
        "ter security transition rejected' "
        "USING ERRCODE='42501';\n END IF;\n R"
        "ETURN NEW;\nEND;$f$;\nALTER FUNCTION"
        " sync_fence_api.guard_writer_recor"
        "ds() OWNER TO pitchlog_sync_bindin"
        "g_fn_owner;\nREVOKE ALL ON FUNCTION"
        " sync_fence_api.guard_writer_recor"
        "ds() FROM PUBLIC;\n\nCREATE TRIGGER "
        "sync_writer_binding_immutable BEFO"
        "RE UPDATE OR DELETE ON sync_fence."
        "writer_bindings FOR EACH ROW EXECU"
        "TE FUNCTION sync_fence_api.guard_w"
        "riter_records();\nCREATE TRIGGER sy"
        "nc_writer_binding_no_truncate BEFO"
        "RE TRUNCATE ON sync_fence.writer_b"
        "indings FOR EACH STATEMENT EXECUTE"
        " FUNCTION sync_fence_api.guard_wri"
        "ter_records();\nCREATE TRIGGER sync"
        "_writer_admission_immutable BEFORE"
        " UPDATE OR DELETE ON sync_fence.wr"
        "iter_admissions FOR EACH ROW EXECU"
        "TE FUNCTION sync_fence_api.guard_w"
        "riter_records();\nCREATE TRIGGER sy"
        "nc_writer_admission_no_truncate BE"
        "FORE TRUNCATE ON sync_fence.writer"
        "_admissions FOR EACH STATEMENT EXE"
        "CUTE FUNCTION sync_fence_api.guard"
        "_writer_records();\n"
    ),
    (
        "function|FUNCTION:sync_right_api:b"
        "ind_device(uuid, uuid, uuid, bytea"
        ", uuid, uuid, bytea)"
    ): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_right_api:bin"
        "d_device(uuid, uuid, uuid, bytea, "
        "uuid, uuid, bytea)\n\nCREATE FUNCTIO"
        "N sync_right_api.bind_device(p_ten"
        "ant_id uuid,p_attempt_id uuid,p_ph"
        "ase_id uuid,p_binding_nonce bytea,"
        "p_device_id uuid,p_game_id uuid,p_"
        "credential_digest bytea)\nRETURNS T"
        "ABLE (device_matches boolean) LANG"
        "UAGE plpgsql VOLATILE SECURITY DEF"
        "INER\nSET search_path = pg_catalog,"
        "pg_temp AS $function$\nDECLARE stor"
        "ed_digest bytea; revoked timestamp"
        "tz;\nBEGIN\n\nIF session_user <> 'pit"
        "chlog_app' OR current_user <> 'pit"
        "chlog_sync_right_fn_owner'\n OR p_t"
        "enant_id IS NULL OR p_tenant_id IS"
        " DISTINCT FROM\n NULLIF(pg_catalog."
        "current_setting('app.tenant_id',tr"
        "ue),'')::uuid\n OR p_attempt_id IS "
        "NULL OR p_phase_id IS NULL OR p_de"
        "vice_id IS NULL\n OR p_game_id IS N"
        "ULL OR p_binding_nonce IS NULL\n OR"
        " pg_catalog.octet_length(p_binding"
        "_nonce) <> 32 THEN\n RAISE EXCEPTIO"
        "N 'sync writer binding rejected' U"
        "SING ERRCODE='42501';\nEND IF;\n-- 実"
        "関数未供給なら例外で閉じる。callerのnonceだけでは成功しな"
        "い。\nPERFORM sync_fence_api.assert_w"
        "riter_binding(p_tenant_id,p_attemp"
        "t_id,\n p_phase_id,p_binding_nonce,"
        "p_device_id,p_game_id);\n\nIF p_cred"
        "ential_digest IS NULL OR\n pg_catal"
        "og.octet_length(p_credential_diges"
        "t) <> 32 THEN\n RAISE EXCEPTION 'sy"
        "nc credential input rejected' USIN"
        "G ERRCODE='42501';\nEND IF;\nSELECT "
        "d.credential_digest,d.revoked_at I"
        "NTO stored_digest,revoked\n FROM pu"
        "blic.trusted_devices d\n WHERE d.te"
        "nant_id=p_tenant_id AND d.device_i"
        "d=p_device_id FOR SHARE;\nRETURN QU"
        "ERY SELECT COALESCE(FOUND AND revo"
        "ked IS NULL AND\n stored_digest=p_c"
        "redential_digest,false);\nEND;\n$fun"
        "ction$;\nALTER FUNCTION sync_right_"
        "api.bind_device(uuid, uuid, uuid, "
        "bytea, uuid, uuid, bytea) OWNER TO"
        " pitchlog_sync_right_fn_owner;\nREV"
        "OKE ALL ON FUNCTION sync_right_api"
        ".bind_device(uuid, uuid, uuid, byt"
        "ea, uuid, uuid, bytea) FROM PUBLIC"
        ";\nGRANT EXECUTE ON FUNCTION sync_r"
        "ight_api.bind_device(uuid, uuid, u"
        "uid, bytea, uuid, uuid, bytea) TO "
        "pitchlog_app;\n"
    ),
    (
        "function|FUNCTION:sync_right_api:c"
        "heck_current_right(uuid, uuid, uui"
        "d, bytea, uuid, uuid, bigint, bigi"
        "nt, bytea)"
    ): (
        "-- ELEMENT-TYPE: function\n-- ELEME"
        "NT-ID: FUNCTION:sync_right_api:che"
        "ck_current_right(uuid, uuid, uuid,"
        " bytea, uuid, uuid, bigint, bigint"
        ", bytea)\n\nCREATE FUNCTION sync_rig"
        "ht_api.check_current_right(p_tenan"
        "t_id uuid,p_attempt_id uuid,p_phas"
        "e_id uuid,p_binding_nonce bytea,p_"
        "device_id uuid,p_game_id uuid,p_in"
        "ternal_generation bigint,p_recover"
        "y_generation bigint,p_proof_digest"
        " bytea)\nRETURNS TABLE (recovery_ma"
        "tches boolean,right_matches boolea"
        "n) LANGUAGE plpgsql VOLATILE SECUR"
        "ITY DEFINER\nSET search_path = pg_c"
        "atalog,pg_temp AS $function$\nDECLA"
        "RE current_epoch bigint; gate_stat"
        "e text;\nBEGIN\n\nIF session_user <> "
        "'pitchlog_app' OR current_user <> "
        "'pitchlog_sync_right_fn_owner'\n OR"
        " p_tenant_id IS NULL OR p_tenant_i"
        "d IS DISTINCT FROM\n NULLIF(pg_cata"
        "log.current_setting('app.tenant_id"
        "',true),'')::uuid\n OR p_attempt_id"
        " IS NULL OR p_phase_id IS NULL OR "
        "p_device_id IS NULL\n OR p_game_id "
        "IS NULL OR p_binding_nonce IS NULL"
        "\n OR pg_catalog.octet_length(p_bin"
        "ding_nonce) <> 32 THEN\n RAISE EXCE"
        "PTION 'sync writer binding rejecte"
        "d' USING ERRCODE='42501';\nEND IF;\n"
        "-- 実関数未供給なら例外で閉じる。callerのnonceだけでは"
        "成功しない。\nPERFORM sync_fence_api.asse"
        "rt_writer_binding(p_tenant_id,p_at"
        "tempt_id,\n p_phase_id,p_binding_no"
        "nce,p_device_id,p_game_id);\n\nIF p_"
        "internal_generation IS NULL OR p_i"
        "nternal_generation <= 0 OR\n p_reco"
        "very_generation IS NULL OR p_recov"
        "ery_generation <= 0 OR\n p_proof_di"
        "gest IS NULL OR pg_catalog.octet_l"
        "ength(p_proof_digest) <> 32 THEN\n "
        "RAISE EXCEPTION 'sync right input "
        "rejected' USING ERRCODE='42501';\nE"
        "ND IF;\nSELECT g.recovery_generatio"
        "n,g.state INTO STRICT current_epoc"
        "h,gate_state\n FROM public.rg1_rest"
        "ore_gate g WHERE g.singleton_id=1;"
        "\nIF current_epoch IS NULL OR gate_"
        "state <> 'open' THEN\n RAISE EXCEPT"
        "ION 'sync recovery unavailable' US"
        "ING ERRCODE='55000';\nEND IF;\nIF cu"
        "rrent_epoch <> p_recovery_generati"
        "on THEN\n RETURN QUERY SELECT false"
        ",false;\n RETURN;\nEND IF;\n-- game→g"
        "eneration lockは既prefix核が保持。本関数で先取り"
        "しない。\nRETURN QUERY SELECT true,EXIS"
        "TS (\n SELECT 1 FROM public.recordi"
        "ng_generations r WHERE r.tenant_id"
        "=p_tenant_id\n AND r.game_id=p_game"
        "_id AND r.generation=p_internal_ge"
        "neration AND r.kind='normal'\n AND "
        "r.holder_device=p_device_id::text "
        "AND r.revoked_at IS NULL\n AND r.re"
        "tired_at IS NULL AND r.recovery_ge"
        "neration=current_epoch\n AND r.proo"
        "f_digest=p_proof_digest);\nEND;\n$fu"
        "nction$;\nALTER FUNCTION sync_right"
        "_api.check_current_right(uuid, uui"
        "d, uuid, bytea, uuid, uuid, bigint"
        ", bigint, bytea) OWNER TO pitchlog"
        "_sync_right_fn_owner;\nREVOKE ALL O"
        "N FUNCTION sync_right_api.check_cu"
        "rrent_right(uuid, uuid, uuid, byte"
        "a, uuid, uuid, bigint, bigint, byt"
        "ea) FROM PUBLIC;\nGRANT EXECUTE ON "
        "FUNCTION sync_right_api.check_curr"
        "ent_right(uuid, uuid, uuid, bytea,"
        " uuid, uuid, bigint, bigint, bytea"
        ") TO pitchlog_app;\n"
    ),
    "policy|POLICY:writer_bindings:binding_owner": "-- ELEMENT-TYPE: policy\n"
    "-- ELEMENT-ID: "
    "POLICY:writer_bindings:binding_owner\n"
    "\n"
    "CREATE POLICY binding_owner ON "
    "sync_fence.writer_bindings FOR ALL TO "
    "pitchlog_sync_binding_fn_owner USING (true) WITH "
    "CHECK (true);\n",
    "policy|POLICY:writer_admissions:admission_owner": "-- ELEMENT-TYPE: policy\n"
    "-- ELEMENT-ID: "
    "POLICY:writer_admissions:admission_owner\n"
    "\n"
    "CREATE POLICY admission_owner ON "
    "sync_fence.writer_admissions FOR ALL TO "
    "pitchlog_sync_binding_fn_owner USING (true) "
    "WITH CHECK (true);\n",
    "policy|POLICY:rg1_restore_gate:binding_gate": "-- ELEMENT-TYPE: policy\n"
    "-- ELEMENT-ID: "
    "POLICY:rg1_restore_gate:binding_gate\n"
    "\n"
    "CREATE POLICY binding_gate ON "
    "public.rg1_restore_gate FOR SELECT TO "
    "pitchlog_sync_binding_fn_owner USING "
    "(singleton_id=1);\n",
    ("policy|POLICY:trusted_devices:sync_first_ball_select"): (
        "-- ELEMENT-TYPE: policy\n-- ELEMENT"
        "-ID: POLICY:trusted_devices:sync_f"
        "irst_ball_select\n\nCREATE POLICY sy"
        "nc_first_ball_select ON public.tru"
        "sted_devices FOR SELECT TO pitchlo"
        "g_sync_right_fn_owner USING (tenan"
        "t_id=NULLIF(pg_catalog.current_set"
        "ting('app.tenant_id',true),'')::uu"
        "id);\n"
    ),
    ("policy|POLICY:recording_generations:sync_first_ball_select"): (
        "-- ELEMENT-TYPE: policy\n-- ELEMENT"
        "-ID: POLICY:recording_generations:"
        "sync_first_ball_select\n\nCREATE POL"
        "ICY sync_first_ball_select ON publ"
        "ic.recording_generations FOR SELEC"
        "T TO pitchlog_sync_right_fn_owner "
        "USING (tenant_id=NULLIF(pg_catalog"
        ".current_setting('app.tenant_id',t"
        "rue),'')::uuid);\n"
    ),
    ("policy|POLICY:trusted_devices:sync_first_ball_device_lock"): (
        "-- ELEMENT-TYPE: policy\n-- ELEMENT"
        "-ID: POLICY:trusted_devices:sync_f"
        "irst_ball_device_lock\n\nCREATE POLI"
        "CY sync_first_ball_device_lock ON "
        "public.trusted_devices FOR UPDATE "
        "TO pitchlog_sync_right_fn_owner US"
        "ING (tenant_id=NULLIF(pg_catalog.c"
        "urrent_setting('app.tenant_id',tru"
        "e),'')::uuid) WITH CHECK (tenant_i"
        "d=NULLIF(pg_catalog.current_settin"
        "g('app.tenant_id',true),'')::uuid)"
        ";\n"
    ),
    ("policy|POLICY:rg1_restore_gate:sync_first_ball_gate"): (
        "-- ELEMENT-TYPE: policy\n-- ELEMENT"
        "-ID: POLICY:rg1_restore_gate:sync_"
        "first_ball_gate\n\nCREATE POLICY syn"
        "c_first_ball_gate ON public.rg1_re"
        "store_gate FOR SELECT TO pitchlog_"
        "sync_right_fn_owner USING (singlet"
        "on_id=1);\n"
    ),
    ("acl_expectation|ACL:sync_fence:writer_bindings:pitchlog_sync_binding_fn_owner"): (
        "-- ELEMENT-TYPE: acl_expectation\n-"
        "- ELEMENT-ID: ACL:sync_fence:write"
        "r_bindings:pitchlog_sync_binding_f"
        "n_owner\n\nGRANT SELECT,INSERT ON TA"
        "BLE sync_fence.writer_bindings TO "
        "pitchlog_sync_binding_fn_owner;\n"
    ),
    (
        "acl_expectation|ACL:sync_fence:wri"
        "ter_admissions:pitchlog_sync_bindi"
        "ng_fn_owner"
    ): (
        "-- ELEMENT-TYPE: acl_expectation\n-"
        "- ELEMENT-ID: ACL:sync_fence:write"
        "r_admissions:pitchlog_sync_binding"
        "_fn_owner\n\nGRANT SELECT,INSERT ON "
        "TABLE sync_fence.writer_admissions"
        " TO pitchlog_sync_binding_fn_owner"
        ";\n"
    ),
    (
        "acl_expectation|ACL:pg_catalog:pg_"
        "control_system():pitchlog_sync_bin"
        "ding_fn_owner"
    ): (
        "-- ELEMENT-TYPE: acl_expectation\n-"
        "- ELEMENT-ID: ACL:pg_catalog:pg_co"
        "ntrol_system():pitchlog_sync_bindi"
        "ng_fn_owner\n\nGRANT EXECUTE ON FUNC"
        "TION pg_catalog.pg_control_system("
        ") TO pitchlog_sync_binding_fn_owne"
        "r;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "sync_fence:writer_bindings:state:p"
        "itchlog_sync_binding_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:sy"
        "nc_fence:writer_bindings:state:pit"
        "chlog_sync_binding_fn_owner\n\nGRANT"
        " UPDATE (state) ON TABLE sync_fenc"
        "e.writer_bindings TO pitchlog_sync"
        "_binding_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "sync_fence:writer_bindings:close_i"
        "d:pitchlog_sync_binding_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:sy"
        "nc_fence:writer_bindings:close_id:"
        "pitchlog_sync_binding_fn_owner\n\nGR"
        "ANT UPDATE (close_id) ON TABLE syn"
        "c_fence.writer_bindings TO pitchlo"
        "g_sync_binding_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:rg1_restore_gate:singleton_"
        "id:pitchlog_sync_binding_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:rg1_restore_gate:singleton_id"
        ":pitchlog_sync_binding_fn_owner\n\nG"
        "RANT SELECT (singleton_id) ON TABL"
        "E public.rg1_restore_gate TO pitch"
        "log_sync_binding_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:rg1_restore_gate:state:pitc"
        "hlog_sync_binding_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:rg1_restore_gate:state:pitchl"
        "og_sync_binding_fn_owner\n\nGRANT SE"
        "LECT (state) ON TABLE public.rg1_r"
        "estore_gate TO pitchlog_sync_bindi"
        "ng_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:rg1_restore_gate:recovery_g"
        "eneration:pitchlog_sync_binding_fn"
        "_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:rg1_restore_gate:recovery_gen"
        "eration:pitchlog_sync_binding_fn_o"
        "wner\n\nGRANT SELECT (recovery_gener"
        "ation) ON TABLE public.rg1_restore"
        "_gate TO pitchlog_sync_binding_fn_"
        "owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:trusted_devices:tenant_id:p"
        "itchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:trusted_devices:tenant_id:pit"
        "chlog_sync_right_fn_owner\n\nGRANT S"
        "ELECT (tenant_id) ON TABLE public."
        "trusted_devices TO pitchlog_sync_r"
        "ight_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:trusted_devices:device_id:p"
        "itchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:trusted_devices:device_id:pit"
        "chlog_sync_right_fn_owner\n\nGRANT S"
        "ELECT (device_id) ON TABLE public."
        "trusted_devices TO pitchlog_sync_r"
        "ight_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:trusted_devices:credential_"
        "digest:pitchlog_sync_right_fn_owne"
        "r"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:trusted_devices:credential_di"
        "gest:pitchlog_sync_right_fn_owner\n"
        "\nGRANT SELECT (credential_digest) "
        "ON TABLE public.trusted_devices TO"
        " pitchlog_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:trusted_devices:revoked_at:"
        "pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:trusted_devices:revoked_at:pi"
        "tchlog_sync_right_fn_owner\n\nGRANT "
        "SELECT (revoked_at) ON TABLE publi"
        "c.trusted_devices TO pitchlog_sync"
        "_right_fn_owner;\nGRANT UPDATE (rev"
        "oked_at) ON TABLE public.trusted_d"
        "evices TO pitchlog_sync_right_fn_o"
        "wner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:tenan"
        "t_id:pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:tenant_"
        "id:pitchlog_sync_right_fn_owner\n\nG"
        "RANT SELECT (tenant_id) ON TABLE p"
        "ublic.recording_generations TO pit"
        "chlog_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:game_"
        "id:pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:game_id"
        ":pitchlog_sync_right_fn_owner\n\nGRA"
        "NT SELECT (game_id) ON TABLE publi"
        "c.recording_generations TO pitchlo"
        "g_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:gener"
        "ation:pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:generat"
        "ion:pitchlog_sync_right_fn_owner\n\n"
        "GRANT SELECT (generation) ON TABLE"
        " public.recording_generations TO p"
        "itchlog_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:kind:"
        "pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:kind:pi"
        "tchlog_sync_right_fn_owner\n\nGRANT "
        "SELECT (kind) ON TABLE public.reco"
        "rding_generations TO pitchlog_sync"
        "_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:holde"
        "r_device:pitchlog_sync_right_fn_ow"
        "ner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:holder_"
        "device:pitchlog_sync_right_fn_owne"
        "r\n\nGRANT SELECT (holder_device) ON"
        " TABLE public.recording_generation"
        "s TO pitchlog_sync_right_fn_owner;"
        "\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:revok"
        "ed_at:pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:revoked"
        "_at:pitchlog_sync_right_fn_owner\n\n"
        "GRANT SELECT (revoked_at) ON TABLE"
        " public.recording_generations TO p"
        "itchlog_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:retir"
        "ed_at:pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:retired"
        "_at:pitchlog_sync_right_fn_owner\n\n"
        "GRANT SELECT (retired_at) ON TABLE"
        " public.recording_generations TO p"
        "itchlog_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:proof"
        "_digest:pitchlog_sync_right_fn_own"
        "er"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:proof_d"
        "igest:pitchlog_sync_right_fn_owner"
        "\n\nGRANT SELECT (proof_digest) ON T"
        "ABLE public.recording_generations "
        "TO pitchlog_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:recording_generations:recov"
        "ery_generation:pitchlog_sync_right"
        "_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:recording_generations:recover"
        "y_generation:pitchlog_sync_right_f"
        "n_owner\n\nGRANT SELECT (recovery_ge"
        "neration) ON TABLE public.recordin"
        "g_generations TO pitchlog_sync_rig"
        "ht_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:rg1_restore_gate:singleton_"
        "id:pitchlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:rg1_restore_gate:singleton_id"
        ":pitchlog_sync_right_fn_owner\n\nGRA"
        "NT SELECT (singleton_id) ON TABLE "
        "public.rg1_restore_gate TO pitchlo"
        "g_sync_right_fn_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:rg1_restore_gate:state:pitc"
        "hlog_sync_right_fn_owner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:rg1_restore_gate:state:pitchl"
        "og_sync_right_fn_owner\n\nGRANT SELE"
        "CT (state) ON TABLE public.rg1_res"
        "tore_gate TO pitchlog_sync_right_f"
        "n_owner;\n"
    ),
    (
        "column_acl_expectation|COLUMN-ACL:"
        "public:rg1_restore_gate:recovery_g"
        "eneration:pitchlog_sync_right_fn_o"
        "wner"
    ): (
        "-- ELEMENT-TYPE: column_acl_expect"
        "ation\n-- ELEMENT-ID: COLUMN-ACL:pu"
        "blic:rg1_restore_gate:recovery_gen"
        "eration:pitchlog_sync_right_fn_own"
        "er\n\nGRANT SELECT (recovery_generat"
        "ion) ON TABLE public.rg1_restore_g"
        "ate TO pitchlog_sync_right_fn_owne"
        "r;\n"
    ),
}

IDS = {
    "roles": "role_id",
    "schemas": "schema_id",
    "tables": "table_id",
    "policies": "policy_id",
    "functions": "function_id",
    "acl_expectations": "acl_id",
    "column_acl_expectations": "expectation_id",
}
ROLES = frozenset(row["role_id"] for row in ADDITIONS["roles"])
TABLES = frozenset(
    {"writer_bindings", "writer_admissions", "first_ball_write_admissions"}
)
SCHEMAS = frozenset(row["schema_name"] for row in ADDITIONS["schemas"])
BINDING_OWNER = "pitchlog_sync_binding_fn_owner"
DB_GRANT = {
    "grantee": "pitchlog_sync_binding_actor",
    "privilege": "CONNECT",
    "grantable": False,
}
DB_REVOKES = [
    {"grantee": "pitchlog_sync_binding_actor", "privilege": p, "grantable": False}
    for p in ("CREATE", "TEMPORARY")
]
PUBLIC_GRANTS = [
    {"grantee": p, "privilege": "USAGE", "grantable": False}
    for p in ("pitchlog_sync_binding_fn_owner", "pitchlog_sync_right_fn_owner")
]


def _reserved(row: dict[str, Any], section: str) -> bool:
    """新namespace/新ownerの別名や余剰行も閉集合へ送る。"""
    key = row.get(IDS[section])
    expected = {r[IDS[section]] for r in ADDITIONS[section]}
    return (
        key in expected
        or row.get("role_id") in ROLES
        or row.get("owner_role_id") in ROLES
        or row.get("grantee_role_id") in ROLES
        or row.get("schema_name") in SCHEMAS
        or row.get("object_schema") in SCHEMAS
        or row.get("table_id") in TABLES
        or any(r in ROLES for r in row.get("role_ids", []))
        or (
            isinstance(key, str)
            and (
                "sync_fence" in key
                or "sync_right" in key
                or "sync_binding" in key
                or "sync_first_ball" in key
            )
        )
    )


def active(asset: dict[str, Any]) -> bool:
    """新宣言が一つでもあれば部分profileとして全検査する。"""
    return any(
        _reserved(row, k)
        for k in IDS
        for row in asset.get(k, [])
        if isinstance(row, dict)
    ) or any(
        a.get("grantee") in ROLES
        for section in ("databases", "schemas")
        for row in asset.get(section, [])
        if isinstance(row, dict)
        for field in ("acl_expectations", "revoked_acl_expectations")
        for a in row.get(field, [])
        if isinstance(a, dict)
    )


def _exact(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _exact(left[k], right[k]) for k in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _exact(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def validate(asset: dict[str, Any]) -> bool:
    """新全集合/全fieldと必要な既ACL追記を検査する。"""
    if not active(asset):
        return False
    for section, id_field in IDS.items():
        rows = asset.get(section)
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError("初球認可資産の配列が不正")
        chosen = [r for r in rows if _reserved(r, section)]
        if (
            len(chosen) != len(ADDITIONS[section])
            or {r.get(id_field) for r in chosen}
            != {r[id_field] for r in ADDITIONS[section]}
            or any(not any(_exact(r, e) for e in ADDITIONS[section]) for r in chosen)
        ):
            raise ValueError("初球認可資産の部分/余剰/全field不一致: " + section)
    db = asset.get("databases")
    pub = [r for r in asset.get("schemas", []) if r.get("schema_name") == "public"]
    if (
        not isinstance(db, list)
        or len(db) != 1
        or db[0].get("acl_expectations", []).count(DB_GRANT) != 1
        or any(
            db[0].get(("revoked_acl_expectations"), []).count(x) != 1
            for x in DB_REVOKES
        )
    ):
        raise ValueError("初球DB CONNECT/拒否宣言の必要全値がない")
    if len(pub) != 1 or any(
        pub[0].get("acl_expectations", []).count(x) != 1 for x in PUBLIC_GRANTS
    ):
        raise ValueError("初球ownerのpublic USAGE宣言がない")
    legacy_database_rows(db)
    legacy_schema_rows(asset.get("schemas"))
    return True


def legacy_database_rows(value: Any) -> Any:
    """既DB検査へ渡す前にexact追加CONNECTだけを分離する。"""
    result = copy.deepcopy(value)
    if not isinstance(result, list):
        return result
    for row in result:
        if not isinstance(row, dict):
            continue
        found = [
            x
            for x in row.get("acl_expectations", [])
            + row.get("revoked_acl_expectations", [])
            if x.get("grantee") in ROLES
        ]
        if found:
            if found != [DB_GRANT, *DB_REVOKES]:
                raise ValueError("初球DB権限の閉集合が不一致")
            row["acl_expectations"].remove(DB_GRANT)
            for x in DB_REVOKES:
                row["revoked_acl_expectations"].remove(x)
    return result


def legacy_schema_rows(value: Any) -> Any:
    """既schema全値は保持し、新schemaとpublic USAGEだけ分離する。"""
    if not isinstance(value, list):
        return value
    result = copy.deepcopy(value)
    chosen = [
        x for x in result if isinstance(x, dict) and x.get("schema_name") in SCHEMAS
    ]
    if chosen and chosen != ADDITIONS["schemas"]:
        raise ValueError("初球schema全集合が不一致")
    result = [x for x in result if x not in chosen]
    for row in result:
        if not isinstance(row, dict):
            continue
        found = [
            x for x in row.get("acl_expectations", []) if x.get("grantee") in ROLES
        ]
        if found:
            if row.get("schema_name") != "public" or found != PUBLIC_GRANTS:
                raise ValueError("初球public USAGEが不一致")
            for x in PUBLIC_GRANTS:
                row["acl_expectations"].remove(x)
    return result


def legacy_asset(asset: dict[str, Any]) -> dict[str, Any]:
    """新exact部分だけを除き、旧検査用の忠実な投影を返す。"""
    if not validate(asset):
        return asset
    result = copy.deepcopy(asset)
    for section in IDS:
        result[section] = [
            row for row in result[section] if row not in ADDITIONS[section]
        ]
    result["databases"] = legacy_database_rows(result["databases"])
    # schema新行は既に除去済み。public追記だけ戻す。
    result["schemas"] = legacy_schema_rows(result["schemas"])
    return result


def declaration(section: str, key: str) -> dict[str, Any] | None:
    """閉じたIDの独立宣言だけを返す。"""
    return next(
        (copy.deepcopy(r) for r in ADDITIONS[section] if r[IDS[section]] == key), None
    )


def body(kind: str, key: str) -> str | None:
    """初球exact要素の凍結描画結果を返す。"""
    return BODIES.get(kind + "|" + key)


def require_row(section: str, row: dict[str, Any]) -> str | None:
    """新ownerへの任意権限はexact行以外拒否する。"""
    if not _reserved(row, section):
        return None
    expected = declaration(section, row.get(IDS[section], ""))
    if expected != row:
        raise ValueError("初球権限の全field不一致")
    kind = {
        "policies": "policy",
        "acl_expectations": "acl_expectation",
        "column_acl_expectations": "column_acl_expectation",
    }[section]
    return body(kind, row[IDS[section]])


def pre_rule_deferred_ids() -> frozenset[str]:
    """0037前は新roleだけ先行し、未作成表/関数依存を全て保留する。"""
    return frozenset(row[IDS[k]] for k in IDS if k != "roles" for row in ADDITIONS[k])


def function_details() -> tuple[tuple[object, ...], ...]:
    """新9関数の実本文/属性をcanonical SQLへ全値束縛する。"""
    import re

    result = []
    for row in ADDITIONS["functions"]:
        sql = body("function", row["function_id"])
        if sql is None:
            raise ValueError("初球関数本文がない")
        delimiter = re.search(r"\bAS\s+(\$[A-Za-z0-9_]*\$)", sql)
        if delimiter is None:
            raise ValueError("初球関数本文のdelimiterがない")
        pieces = sql.split(delimiter.group(1))
        if len(pieces) != 3:
            raise ValueError("初球関数本文が一意でない")
        result.append(
            (
                row["schema_name"],
                row["function_name"],
                row["identity_args"],
                row["owner_role_id"],
                row["security_mode"] == "definer",
                row["language"],
                _pg_result_type(row["returns"]),
                "v",
                ("search_path=pg_catalog, pg_temp",),
                pieces[1].strip(),
            )
        )
    return tuple(sorted(result))


def _pg_result_type(value: str) -> str:
    """新9関数の戻り宣言をpg_get_function_resultの表記へ揃える。"""
    import re

    return re.sub(r"\bTABLE\s*\(", "TABLE(", value)


def _sql_literal(value: str) -> str:
    """凍結文字列をSQLの単一文字列literalへ閉じ込める。"""
    return "'" + value.replace("'", "''") + "'"


def _function_argument_names(sql: str) -> tuple[tuple[str, ...], bool]:
    """凍結CREATEだけから入出力引数名を抽出し曖昧な宣言を拒否する。"""
    import re

    match = re.search(
        r"CREATE FUNCTION [a-z_]+\.[a-z_]+\(([^)]*)\)\s*RETURNS\s+"
        r"(?:(TABLE)\s*\(([^)]*)\)|(?:void|trigger))",
        sql,
    )
    if match is None:
        raise ValueError("初球関数の固定引数宣言がない")
    fields = [p.strip() for p in match[1].split(",") if p.strip()]
    table = match[2] is not None
    if table:
        fields += [p.strip() for p in match[3].split(",")]
    names = []
    for field in fields:
        name, separator, _ = field.partition(" ")
        if not separator or re.fullmatch(r"[a-z_][a-z0-9_]*", name) is None:
            raise ValueError("初球関数の引数名が固定形式でない")
        names.append(name)
    return tuple(names), table


def _guard_reapply_check(function_identity: str) -> str:
    """既guardの全4trigger構造を確認し欠落/余剰/改変を修復で隠さない。"""
    if function_identity != "sync_fence_api.guard_writer_records()":
        return ""
    rows = (
        ("sync_writer_binding_immutable", "writer_bindings", 27),
        ("sync_writer_binding_no_truncate", "writer_bindings", 34),
        ("sync_writer_admission_immutable", "writer_admissions", 27),
        ("sync_writer_admission_no_truncate", "writer_admissions", 34),
    )
    expected = " OR ".join(
        f"(t.tgname={_sql_literal(name)} AND "
        f"t.tgrelid={_sql_literal('sync_fence.' + table)}::pg_catalog.regclass "
        f"AND t.tgtype={kind})"
        for name, table, kind in rows
    )
    return f"""
    IF (SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger t
        WHERE t.tgrelid IN ('sync_fence.writer_bindings'::pg_catalog.regclass,
                           'sync_fence.writer_admissions'::pg_catalog.regclass)
          AND NOT t.tgisinternal) <> 4
       OR (SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger t
           WHERE ({expected}) AND NOT t.tgisinternal
             AND t.tgfoid=existing AND t.tgenabled='O'
             AND NOT t.tgdeferrable AND NOT t.tginitdeferred
             AND t.tgconstraint=0 AND t.tgnargs=0 AND t.tgattr::text=''
             AND t.tgqual IS NULL AND t.tgargs=''::pg_catalog.bytea
             AND t.tgoldtable IS NULL AND t.tgnewtable IS NULL) <> 4 THEN
        RAISE EXCEPTION 'first ball trigger definition collision';
    END IF;"""


def application_function_sql(function_id: str, sql: str) -> str | None:
    """新exact9を初回だけ作成し、再適用は既全値一致のときだけ保つ。"""
    import json

    row = declaration("functions", function_id)
    if row is None:
        return None
    canonical = body("function", function_id)
    if canonical is None or sql != canonical:
        raise ValueError("初球関数の適用本文が凍結値と不一致")
    identity = f"{row['schema_name']}.{row['function_name']}({row['identity_args']})"
    details = next(
        d
        for d in function_details()
        if d[:2] == (row["schema_name"], row["function_name"])
    )
    names, returns_set = _function_argument_names(sql)
    names_sql = (
        "ARRAY["
        + ",".join(_sql_literal(name) for name in names)
        + "]::pg_catalog.text[]"
        if names
        else "NULL::pg_catalog.text[]"
    )
    input_count = len(row["identity_args"].split(",")) if row["identity_args"] else 0
    modes = (
        *("i" for _ in range(input_count)),
        *("t" for _ in range(len(names) - input_count)),
    )
    modes_sql = (
        "ARRAY["
        + ",".join(_sql_literal(mode) for mode in modes)
        + ']::pg_catalog."char"[]'
        if returns_set
        else 'NULL::pg_catalog."char"[]'
    )
    # owner自身の暗黙権限を除いた全EXECUTEを既catalogと同じ全集合で比較する。
    acl = sorted(
        [
            [r["grantee"], r["privilege"], r["grantable"]]
            for r in row["acl_expectations"]
        ]
    )
    acl_sql = (
        _sql_literal(json.dumps(acl, separators=(",", ":"))) + "::pg_catalog.jsonb"
    )
    return f"""DO $first_ball_reapply$
DECLARE existing pg_catalog.oid;
BEGIN
    existing := pg_catalog.to_regprocedure({_sql_literal(identity)})::pg_catalog.oid;
    IF existing IS NULL THEN
        EXECUTE {_sql_literal(sql)};
        RETURN;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_roles o ON o.oid=p.proowner
        JOIN pg_catalog.pg_language l ON l.oid=p.prolang
        WHERE p.oid=existing AND o.rolname={_sql_literal(row["owner_role_id"])}
          AND l.lanname={_sql_literal(row["language"])}
          AND p.prokind='f' AND p.provolatile='v' AND p.proparallel='u'
          AND NOT p.proisstrict AND NOT p.proleakproof AND p.provariadic=0
          AND p.pronargdefaults=0 AND p.proargnames IS NOT DISTINCT FROM {names_sql}
          AND p.proargmodes IS NOT DISTINCT FROM {modes_sql}
          AND p.procost=100 AND p.prorows={1000 if returns_set else 0}
          AND p.prosupport=0 AND p.probin IS NULL AND p.prosqlbody IS NULL
          AND p.protrftypes IS NULL
          AND p.prosecdef={str(row["security_mode"] == "definer").upper()}
          AND p.proretset={str(returns_set).upper()}
          AND pg_catalog.pg_get_function_result(p.oid)={_sql_literal(str(details[6]))}
          AND p.proconfig=ARRAY['search_path=pg_catalog, pg_temp']::pg_catalog.text[]
          AND pg_catalog.btrim(p.prosrc, E' \\t\\r\\n')={_sql_literal(str(details[9]))}
    ) THEN
        RAISE EXCEPTION 'first ball function definition collision';
    END IF;
    IF (SELECT COALESCE(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
                CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE g.rolname END,
                a.privilege_type,a.is_grantable)
                ORDER BY CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE g.rolname END,
                         a.privilege_type,a.is_grantable),'[]'::pg_catalog.jsonb)
        FROM pg_catalog.pg_proc p
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
        LEFT JOIN pg_catalog.pg_roles g ON g.oid=a.grantee
        WHERE p.oid=existing AND a.grantee<>p.proowner) IS DISTINCT FROM {acl_sql} THEN
        RAISE EXCEPTION 'first ball function privilege collision';
    END IF;{_guard_reapply_check(identity)}
END;
$first_ball_reapply$;"""
