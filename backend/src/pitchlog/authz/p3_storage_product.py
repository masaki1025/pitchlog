"""0048の閉じた保存6表へ関数ownerだけの列権限候補を描画する。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import DefaultClause
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.authz.stats_primitive_product import _add_column, _add_policy
from pitchlog.db.past_correction.models import P3_STORAGE_MODELS
from pitchlog.domaingen.core import _canonical_hash

_OWNER = "pitchlog_owner"
_FUNCTION_OWNER = "pitchlog_sync_right_fn_owner"
_PREDICATE = (
    "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
    " AND session_user = 'pitchlog_app'"
)
_COLUMN_SCHEMAS = {
    "p3_projection_capsules": (
        "sha256:1f0684b74b8139e2658ab2e2768f620a24489726aabd38bfe915d92f4b08ace2"
    ),
    "p3_projection_capsule_items": (
        "sha256:9251b4ae31acc92dae1e65bf980436e8c565235e05abe2f2ea5f7af35b0dfcdd"
    ),
    "p3_projection_heads": (
        "sha256:61258bc11a93bb75f9c89d74621465fc85a641d7002aff9965e9209390b0901b"
    ),
    "p3_projection_write_admissions": (
        "sha256:b89553ca1d7d9b924e582e7dd4effb334c019f0c46514b7deb8c097d35031f88"
    ),
    "p3_projection_page_progress": (
        "sha256:aa8436a89d977948cbe947921756d0b7423902e98bb01cede2f26fe1b5b5d7f5"
    ),
    "p3_projection_page_rows": (
        "sha256:be05bfbf6827f69eab6fc600b029e3a260e9308d0faa8543a322dabbcdf693f2"
    ),
}
_UPDATE_COLUMNS = {
    "p3_projection_heads": frozenset(
        {
            "capsule_id",
            "revision",
            "source_set_digest",
            "stats_version_id",
            "updated_at",
        }
    ),
    "p3_projection_write_admissions": frozenset({"state"}),
    "p3_projection_page_progress": frozenset(
        {
            "state",
            "item_count",
            "last_d1",
            "last_d2",
            "page_count",
            "source_page_seal",
            "evaluation_page_seal",
            "finalized_at",
        }
    ),
}
_XMIN_TABLES = frozenset(
    {
        "p3_projection_capsules",
        "p3_projection_capsule_items",
        "p3_projection_heads",
        "p3_projection_write_admissions",
    }
)


def _declared_default(value: Any) -> str | None:
    """未知の生成defaultを省略して列pinへ取り込まない。"""
    if value is None:
        return None
    if not isinstance(value, DefaultClause):
        raise ValueError("P3保存列のdefault形式が不一致")
    return str(value.arg)


def _relations() -> dict[str, list[str]]:
    """余剰列を暗黙GRANTせず、固定列型/nullable/defaultへ先に照合する。"""
    result = {}
    for model in P3_STORAGE_MODELS:
        table = model.__table__
        columns = {
            str(column.name): {
                "type": str(column.type.compile(dialect=dialect())),
                "nullable": column.nullable,
                "default": _declared_default(column.server_default),
            }
            for column in table.c
        }
        if (
            table.schema != "sync_fence"
            or table.info.get("storage_owner") != _OWNER
            or table.name in result
            or table.name not in _COLUMN_SCHEMAS
            or _canonical_hash(columns) != _COLUMN_SCHEMAS[table.name]
        ):
            raise ValueError("P3保存列の固定集合が不一致")
        result[str(table.name)] = list(columns)
    if set(result) != set(_COLUMN_SCHEMAS):
        raise ValueError("P3保存表の固定集合が不一致")
    return result


def candidate_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """構造だけの候補を返す。関数/guard供給や製品起動許可を代替しない。"""
    declarations: dict[str, list[dict[str, Any]]] = {
        "tables": [],
        "policies": [],
        "column_acl_expectations": [],
    }
    bodies: dict[str, str] = {}
    for table, columns in _relations().items():
        declarations["tables"].append(
            {
                "table_id": table,
                "schema_name": "sync_fence",
                "enable_row_level_security": True,
                "force_row_level_security": True,
            }
        )
        bodies["table|" + table] = (
            f"ALTER TABLE sync_fence.{table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE sync_fence.{table} FORCE ROW LEVEL SECURITY;\n"
            f"REVOKE ALL ON TABLE sync_fence.{table} FROM PUBLIC,pitchlog_app,"
            "pitchlog_sync_binding_actor,pitchlog_rg1_control_actor;\n"
        )
        updates = _UPDATE_COLUMNS.get(table, frozenset())
        if not updates <= set(columns):
            raise ValueError("P3保存の更新列が未定義")
        for column in columns:
            privileges = ["SELECT", "INSERT"]
            if column in updates:
                privileges.append("UPDATE")
            _add_column(declarations, bodies, "sync_fence", table, column, privileges)
        if table in _XMIN_TABLES:
            _add_column(declarations, bodies, "sync_fence", table, "xmin", ["SELECT"])
        for command in ["SELECT", "INSERT"] + (["UPDATE"] if updates else []):
            _add_policy(
                declarations,
                bodies,
                "sync_fence",
                table,
                "p3_function_" + command.lower(),
                command,
                _PREDICATE,
            )
        name = "p3_storage_owner"
        identifier = f"POLICY:{table}:{name}"
        declarations["policies"].append(
            {
                "policy_id": identifier,
                "table_id": table,
                "profile": "function_only",
                "policy_name": name,
                "command": "ALL",
                "policy_mode": "permissive",
                "role_ids": [_OWNER],
                "using_predicate_id": None,
                "using_column": None,
                "using_expression": "true",
                "with_check_predicate_id": None,
                "with_check_column": None,
                "with_check_expression": "true",
            }
        )
        bodies["policy|" + identifier] = (
            f"CREATE POLICY {name} ON sync_fence.{table} FOR ALL TO {_OWNER} "
            "USING (true) WITH CHECK (true);\n"
        )
    if (
        len(declarations["tables"]),
        len(declarations["policies"]),
        len(declarations["column_acl_expectations"]),
        len(bodies),
    ) != (6, 21, 114, 141):
        raise ValueError("P3保存の認可宣言が閉じていない")
    if any(
        row["grantee_role_id"] != _FUNCTION_OWNER or row["grant_option"] is not False
        for row in declarations["column_acl_expectations"]
    ):
        raise ValueError("P3保存列の権限主体が不一致")
    return declarations, bodies
