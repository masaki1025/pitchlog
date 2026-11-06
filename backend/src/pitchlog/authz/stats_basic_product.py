"""基本成績read関数と必要最小の列・行認可を製品宣言へ供給する。"""

from __future__ import annotations

from typing import Any

from pitchlog.authz.stats_primitive_product import _add_column, _add_policy
from pitchlog.stats.basic_sql import _READ_ARGS, _READ_RETURNS, read_function_body

_OWNER = "pitchlog_sync_right_fn_owner"
_APP = "pitchlog_app"
_FUNCTION_ID = (
    "FUNCTION:stats_basic_api:read_basic_stats("
    "uuid, text, text, text, text, text, boolean, text, integer, text)"
)


def connection_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """旧成績・LC認可へ不足するread権限だけを閉じて追加する。"""
    declarations: dict[str, list[dict[str, Any]]] = {
        "schemas": [
            {
                "schema_id": "stats_basic_api",
                "schema_name": "stats_basic_api",
                "creation": "product_ddl",
                "owner": "pitchlog_owner",
                "ownership_path": "direct",
                "acl_expectations": [
                    {"grantee": _APP, "privilege": "USAGE", "grantable": False},
                    {"grantee": _OWNER, "privilege": "USAGE", "grantable": False},
                ],
                "revoked_acl_expectations": [
                    {"grantee": role, "privilege": right, "grantable": False}
                    for role, right in (
                        ("PUBLIC", "USAGE"),
                        ("PUBLIC", "CREATE"),
                        (_APP, "CREATE"),
                        (_OWNER, "CREATE"),
                    )
                ],
            }
        ],
        "functions": [
            {
                "function_id": _FUNCTION_ID,
                "schema_name": "stats_basic_api",
                "function_name": "read_basic_stats",
                "identity_args": (
                    "uuid, text, text, text, text, text, boolean, text, integer, text"
                ),
                "function_kind": "definer",
                "owner_role_id": _OWNER,
                "language": "plpgsql",
                "returns": "TABLE(" + _READ_RETURNS + ")",
                "security_mode": "definer",
                "volatility": "stable",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": [
                    {"grantee": _APP, "privilege": "EXECUTE", "grantable": False}
                ],
                "revoked_acl_expectations": [
                    {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
                ],
            }
        ],
        "column_acl_expectations": [],
        "policies": [],
    }
    if _READ_ARGS.count(",") != 9:
        raise ValueError("基本成績read署名の引数数が不一致です")
    identity = (
        "stats_basic_api.read_basic_stats("
        + declarations["functions"][0]["identity_args"]
        + ")"
    )
    bodies = {
        "function|" + _FUNCTION_ID: (
            read_function_body()
            + f"\nALTER FUNCTION {identity} OWNER TO {_OWNER};\n"
            + f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,pitchlog_app;\n"
            + f"GRANT EXECUTE ON FUNCTION {identity} TO pitchlog_app;\n"
        )
    }
    bodies["schema|stats_basic_api"] = (
        "DO $stats_basic_schema$\nBEGIN\n"
        " IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_namespace n\n"
        "  JOIN pg_catalog.pg_roles r ON r.oid=n.nspowner\n"
        "  WHERE n.nspname='stats_basic_api' AND r.rolname='pitchlog_owner') THEN\n"
        "  IF EXISTS(SELECT 1 FROM pg_catalog.pg_namespace WHERE "
        "nspname='stats_basic_api') THEN\n"
        "   RAISE EXCEPTION 'basic stats schema owner collision';\n"
        "  END IF;\n"
        "  CREATE SCHEMA stats_basic_api AUTHORIZATION pitchlog_owner;\n"
        " END IF;\nEND;$stats_basic_schema$;\n"
        "REVOKE ALL ON SCHEMA stats_basic_api FROM PUBLIC;\n"
        "REVOKE CREATE ON SCHEMA stats_basic_api FROM "
        "pitchlog_app,pitchlog_sync_right_fn_owner;\n"
        "GRANT USAGE ON SCHEMA stats_basic_api TO "
        "pitchlog_app,pitchlog_sync_right_fn_owner;\n"
    )
    for table, columns in {
        "games": (
            "scheduled_at",
            "game_type_key",
            "away_team_record_id",
            "home_team_record_id",
        ),
        "players": ("name", "uniform_number", "team_record_id", "hidden_at"),
        "team_records": ("tenant_id", "id", "name", "kind", "hidden_at"),
        "game_lineups": (
            "tenant_id",
            "game_id",
            "team_record_id",
            "entries_with_uniform_number_snapshot",
            "import_batch_id",
        ),
    }.items():
        for column in columns:
            _add_column(declarations, bodies, "public", table, column, ["SELECT"])
    predicate = (
        "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
        " AND session_user = 'pitchlog_app'"
        " AND current_user = 'pitchlog_sync_right_fn_owner'"
    )
    _add_policy(
        declarations,
        bodies,
        "public",
        "team_records",
        "stats_basic_select",
        "SELECT",
        predicate,
    )
    _add_policy(
        declarations,
        bodies,
        "public",
        "game_lineups",
        "stats_basic_select",
        "SELECT",
        predicate,
    )
    if [len(declarations[key]) for key in declarations] != [1, 1, 18, 2]:
        raise ValueError("基本成績read宣言の有限集合が不一致です")
    return declarations, bodies
