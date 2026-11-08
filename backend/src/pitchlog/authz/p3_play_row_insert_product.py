"""既P3 stampを維持し、保護4列を除く有限INSERTだけを描画する。"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import DefaultClause, Table
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.db.game_state.models import PlayRow
from pitchlog.domaingen.core import _canonical_hash

_OWNER = "pitchlog_sync_right_fn_owner"
_TABLE = PlayRow.__table__
_SHAPE = "sha256:6d4e2abc751bedf1296dc2695db676de8adcb3a48a921e682a8b74ebfa7faad5"
_PROTECTED = frozenset(
    {"hidden_at", "legacy_row_identifier", "import_batch_id", "migration_unverified"}
)
_PREDICATE = (
    "tenant_id = NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')::uuid"
    " AND session_user = 'pitchlog_app'"
)
_OLD_INSERT = (
    " INSERT INTO public.play_rows SELECT (pg_catalog.jsonb_populate_record(\n"
    " NULL::public.play_rows,item->'play_row')).*;"
)


def insert_columns() -> tuple[str, ...]:
    """未知列/defaultを暗黙GRANTせず、固定41列の許可37列だけ返す。"""
    table = _TABLE
    if (
        not isinstance(table, Table)
        or table.schema not in (None, "public")
        or table.name != "play_rows"
    ):
        raise ValueError("P3物理表の型が不一致")
    shape = {}
    for column in table.c:
        default = column.server_default
        if default is not None and not isinstance(default, DefaultClause):
            raise ValueError("P3物理列defaultが未知")
        shape[str(column.name)] = {
            "type": str(column.type.compile(dialect=dialect())),
            "nullable": column.nullable,
            "default": None if default is None else str(default.arg),
        }
    if len(shape) != 41 or _canonical_hash(shape) != _SHAPE:
        raise ValueError("P3物理列集合/型/defaultが不一致")
    columns = tuple(sorted(set(shape) - _PROTECTED))
    if len(columns) != 37:
        raise ValueError("P3有限INSERT列数が不一致")
    return columns


def rewrite_p3_play_insert(sql: str, kind: str) -> str:
    """全41列stampへ渡すclean値を保ち、同じ37列だけを明示INSERTする。"""
    names = {
        "single": ("persist_p3_projection", "P3 projection rejected"),
        "page": ("append_p3_projection_page", "P3 page append rejected"),
    }
    if kind not in names or type(sql) is not str:
        raise ValueError("P3 INSERT描画の呼出が未知")
    name, rejection = names[kind]
    if (
        sql.count(f"CREATE FUNCTION sync_right_api.{name}(") != 1
        or sql.count("CREATE FUNCTION ") != 1
        or sql.count(_OLD_INSERT) != 1
    ):
        raise ValueError("P3 INSERT正規源の境界が不一致")
    columns = insert_columns()
    null_checks = "\n OR ".join(
        f"item->'play_row'->'{column}' IS DISTINCT FROM 'null'::jsonb"
        for column in sorted(_PROTECTED - {"migration_unverified"})
    )
    replacement = (
        " IF " + null_checks + "\n OR item->'play_row'->'migration_unverified'"
        " IS DISTINCT FROM 'false'::jsonb THEN\n"
        + f" RAISE EXCEPTION '{rejection}' USING ERRCODE='42501'; END IF;\n"
        + " INSERT INTO public.play_rows ("
        + ",".join(columns)
        + ")\n"
        + " SELECT "
        + ",".join("r." + column for column in columns)
        + " FROM pg_catalog.jsonb_populate_record(\n"
        " NULL::public.play_rows,item->'play_row') r;"
    )
    return sql.replace(_OLD_INSERT, replacement, 1)


def extend_p3_play_insert(declarations, bodies):
    """既37列SELECTへ必要なINSERTだけを追加し、保護列/他ownerは維持する。"""
    result, rendered = deepcopy(declarations), deepcopy(bodies)
    rows = result["column_acl_expectations"]
    for row in rows:
        if (
            row.get("object_schema") == "public"
            and row.get("object_id") == "play_rows"
            and row.get("grantee_role_id") == _OWNER
            and "INSERT" in row.get("privilege_ids", [])
        ):
            raise ValueError("P3 INSERT権限の基線が既に異なる")
    for column in insert_columns():
        identifier = f"COLUMN-ACL:public:play_rows:{column}:{_OWNER}"
        expected = {
            "expectation_id": identifier,
            "object_kind": "column",
            "object_schema": "public",
            "object_id": "play_rows",
            "column_id": column,
            "grantee_role_id": _OWNER,
            "privilege_ids": ["SELECT"],
            "grant_option": False,
        }
        selected = [row for row in rows if row.get("expectation_id") == identifier]
        key = "column_acl_expectation|" + identifier
        header = (
            f"-- ELEMENT-TYPE: column_acl_expectation\n-- ELEMENT-ID: {identifier}\n\n"
        )
        old = f"GRANT SELECT ({column}) ON TABLE public.play_rows TO {_OWNER};\n"
        if (
            selected != [expected]
            or _canonical_hash(selected[0]) != _canonical_hash(expected)
            or rendered.get(key) != header + old
        ):
            raise ValueError("P3既列ACLの全値/正規描画が不一致")
        selected[0]["privilege_ids"] = ["SELECT", "INSERT"]
        rendered[key] = header + (
            f"GRANT SELECT ({column}), INSERT ({column}) "
            f"ON TABLE public.play_rows TO {_OWNER};\n"
        )
    if any(
        row.get("table_id") == "play_rows"
        and _OWNER in row.get("role_ids", [])
        and row.get("command") in {"INSERT", "ALL"}
        for row in result["policies"]
    ):
        raise ValueError("P3 INSERT policyの基線が既に異なる")
    identifier = "POLICY:play_rows:p3_finite_insert"
    result["policies"].append(
        {
            "policy_id": identifier,
            "table_id": "play_rows",
            "profile": "function_only",
            "policy_name": "p3_finite_insert",
            "command": "INSERT",
            "policy_mode": "permissive",
            "role_ids": [_OWNER],
            "using_predicate_id": None,
            "using_column": None,
            "using_expression": None,
            "with_check_predicate_id": None,
            "with_check_column": None,
            "with_check_expression": _PREDICATE,
        }
    )
    key = "policy|" + identifier
    if key in rendered:
        raise ValueError("P3 INSERT policy描画が重複")
    rendered[key] = (
        "-- ELEMENT-TYPE: policy\n" + f"-- ELEMENT-ID: {identifier}\n\n"
        "CREATE POLICY p3_finite_insert ON public.play_rows AS PERMISSIVE "
        f"FOR INSERT TO {_OWNER} WITH CHECK ({_PREDICATE});\n"
    )
    return result, rendered
