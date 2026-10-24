"""migration由来の製品関数ACLを決定的に生成する。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pitchlog.authz.asset_spec import PRODUCT_SPEC

_IDENTIFIER_INITIALS = "abcdefghijklmnopqrstuvwxyz_"
_IDENTIFIER_CHARACTERS = f"{_IDENTIFIER_INITIALS}0123456789"
_ARGUMENT_TYPE = (
    r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?(?:\[\])?(?: [a-z_][a-z0-9_]*)*"
)
_IDENTITY_ARGS_RE = re.compile(rf"{_ARGUMENT_TYPE}(?:, {_ARGUMENT_TYPE})*\Z")
_REPOSITORY_ROOT = Path(__file__).parents[4]


def valid_product_identity_args(value: str) -> bool:
    """SQL に安全な型名だけからなる引数列を判定する。"""
    return value == "" or _IDENTITY_ARGS_RE.fullmatch(value) is not None


def _declared_identity_args() -> frozenset[str]:
    """製品関数の宣言から許可する引数の形を読む。"""
    path = _REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path
    try:
        asset = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("製品関数の宣言を読めない") from error
    if not isinstance(asset, dict) or not isinstance(asset.get("functions"), list):
        raise ValueError("製品関数の宣言が不正")
    rows = asset["functions"]
    if not all(
        isinstance(row, dict) and isinstance(row.get("identity_args"), str)
        for row in rows
    ):
        raise ValueError("製品関数の引数宣言が不正")
    return frozenset(row["identity_args"] for row in rows)


def _require_identifier(value: str, label: str) -> None:
    """引用を要しない小文字のSQL識別子だけを許可する。"""
    if (
        not value
        or value[0] not in _IDENTIFIER_INITIALS
        or any(character not in _IDENTIFIER_CHARACTERS for character in value)
    ):
        raise ValueError(f"{label}が不正: {value!r}")


def product_function_id(
    schema_name: str,
    function_name: str,
    identity_args: str,
) -> str:
    """物理識別子から製品関数IDを生成する。

    Args:
        schema_name: 関数を置くスキーマ名。
        function_name: 関数名。
        identity_args: ``pg_get_function_identity_arguments`` 相当の引数列。

    Returns:
        スキーマ・名前・引数を含む一意な要素ID。

    Raises:
        ValueError: 識別子または製品資産で許可しない引数列が現れた場合。
    """
    _require_identifier(schema_name, "関数スキーマ識別子")
    _require_identifier(function_name, "関数名識別子")
    if not valid_product_identity_args(identity_args):
        raise ValueError(f"製品関数のidentity_argsの形が不正: {identity_args!r}")
    if identity_args not in _declared_identity_args():
        raise ValueError(f"製品関数のidentity_argsが資産宣言にない: {identity_args!r}")
    return f"FUNCTION:{schema_name}:{function_name}({identity_args})"


def build_product_function_acl_declaration(
    schema_name: str,
    function_name: str,
    identity_args: str,
    *,
    function_kind: str = "migration_trigger",
    execute_grantees: tuple[str, ...] = (),
) -> dict[str, object]:
    """migration由来の関数の所有者とACL期待を組み立てる。"""
    if function_kind not in {"migration_trigger", "migration_function"}:
        raise ValueError(f"migration関数種別が不正: {function_kind}")
    return {
        "function_id": product_function_id(
            schema_name,
            function_name,
            identity_args,
        ),
        "schema_name": schema_name,
        "function_name": function_name,
        "identity_args": identity_args,
        "function_kind": function_kind,
        "owner_role_id": "pitchlog_owner",
        "acl_expectations": [
            {"grantee": role, "privilege": "EXECUTE", "grantable": False}
            for role in execute_grantees
        ],
        "revoked_acl_expectations": [
            {
                "grantee": "PUBLIC",
                "privilege": "EXECUTE",
                "grantable": False,
            },
            {
                "grantee": "pitchlog_app",
                "privilege": "EXECUTE",
                "grantable": False,
            },
        ],
    }


def generate_product_function_acl_sql(
    schema_name: str,
    function_name: str,
    identity_args: str,
    *,
    execute_grantees: tuple[str, ...] = (),
) -> str:
    """PUBLICを剥奪し、宣言したロールだけへ実行権を与えるSQLを生成する。"""
    function_id = product_function_id(
        schema_name,
        function_name,
        identity_args,
    )
    physical_name = f"{schema_name}.{function_name}({identity_args})"
    return (
        "-- ELEMENT-TYPE: function\n"
        f"-- ELEMENT-ID: {function_id}\n"
        "\n"
        f"REVOKE EXECUTE ON FUNCTION {physical_name} FROM PUBLIC;\n"
        f"REVOKE EXECUTE ON FUNCTION {physical_name} FROM pitchlog_app;\n"
        + "".join(
            f"GRANT EXECUTE ON FUNCTION {physical_name} TO {role};\n"
            for role in execute_grantees
        )
    )


BUILTIN_EXECUTE_GRANTEES = frozenset(
    {
        "pitchlog_rg1_control_owner",
        "pitchlog_ledger_identity_owner",
    }
)


def build_builtin_execute_declaration(grantee: str) -> dict[str, object]:
    """pg_control_system引数無しへの追加明示EXECUTEだけを宣言する。"""
    if grantee not in BUILTIN_EXECUTE_GRANTEES:
        raise ValueError("builtinの追加EXECUTE主体が閉集合にない")
    return {
        "acl_id": f"ACL:pg_catalog:pg_control_system():{grantee}",
        "object_kind": "builtin_function",
        "object_schema": "pg_catalog",
        "object_id": "pg_control_system",
        "profile": "additional_builtin_execute",
        "grantee_role_id": grantee,
        "privilege_ids": ["EXECUTE"],
        "grant_option": False,
    }


def is_builtin_execute_declaration(declaration: dict[str, object]) -> bool:
    """署名/主体/全8fieldを独立の有限宣言へ照合する。"""
    grantee = declaration.get("grantee_role_id")
    return (
        declaration.get("grant_option") is False
        and isinstance(grantee, str)
        and grantee in BUILTIN_EXECUTE_GRANTEES
        and (declaration == build_builtin_execute_declaration(grantee))
    )


def generate_builtin_execute_sql(declaration: dict[str, object]) -> str:
    """PUBLICやbuiltin所有者を変更せず追加grant1件だけを生成する。"""
    if not is_builtin_execute_declaration(declaration):
        raise ValueError("builtinの追加EXECUTE宣言がexact集合と一致しない")
    grantee = str(declaration["grantee_role_id"])
    return (
        "-- ELEMENT-TYPE: acl_expectation\n"
        f"-- ELEMENT-ID: {declaration['acl_id']}\n\n"
        "GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() "
        f"TO {grantee};\n"
    )


def build_lifecycle_function_declarations() -> dict[str, dict[str, object]]:
    """固定source由来のcontrol7と業務identity1の属性/EXECUTEを閉じる。"""
    signatures = (
        ("try_controller_lease", "boolean", ("pitchlog_rg1_control_actor",)),
        ("release_controller_lease", "boolean", ("pitchlog_rg1_control_actor",)),
        ("close_gate", "boolean", ("pitchlog_rg1_control_actor",)),
        ("open_fresh_gate", "boolean", ("pitchlog_rg1_control_actor",)),
        (
            "controller_lease_alive",
            "boolean",
            (
                "pitchlog_rg1_control_actor",
                "pitchlog_rg1_fn_owner",
            ),
        ),
        ("read_closed_gate", "jsonb", ("pitchlog_rg1_control_actor",)),
        ("scope_binding", "text", ("pitchlog_app",)),
        ("identity", "jsonb", ("pitchlog_ledger_identity_probe",)),
    )
    result: dict[str, dict[str, object]] = {}
    for name, returns, grantees in signatures:
        identity = name == "identity"
        schema = "pitchlog_ledger_observer" if identity else "rg1_control"
        owner = (
            "pitchlog_ledger_identity_owner"
            if identity
            else "pitchlog_rg1_control_owner"
        )
        args = "uuid" if name == "scope_binding" else ""
        function_id = f"FUNCTION:{schema}:{name}({args})"
        result[function_id] = {
            "function_id": function_id,
            "schema_name": schema,
            "function_name": name,
            "identity_args": args,
            "function_kind": "definer",
            "owner_role_id": owner,
            "language": "sql" if identity else "plpgsql",
            "returns": returns,
            "security_mode": "definer",
            "volatility": "volatile",
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {"grantee": role, "privilege": "EXECUTE", "grantable": False}
                for role in grantees
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            ],
        }
    return result


def generate_lifecycle_function_sql(function_id: str, root: Path) -> str:
    """既固定SQLのCREATE本文をそのまま配置し、第2の判定本文を作らない。"""
    declarations = build_lifecycle_function_declarations()
    if function_id not in declarations:
        raise ValueError("固定ライフサイクル関数の集合外")
    row = declarations[function_id]
    schema, name = str(row["schema_name"]), str(row["function_name"])
    path = (
        "backend/src/pitchlog/durable_rights_ledger/business_identity.sql"
        if schema == "pitchlog_ledger_observer"
        else "backend/src/pitchlog/recording_rights/rg1_lifecycle.sql"
    )
    source = (root / path).read_text(encoding="utf-8")
    delimiter = r"\$\$" if schema == "pitchlog_ledger_observer" else r"\$function\$"
    pattern = (
        rf"CREATE (?:OR REPLACE )?FUNCTION {re.escape(schema)}\.{re.escape(name)}"
        rf"\([^)]*\).*?{delimiter}.*?{delimiter};"
    )
    matches = re.findall(pattern, source, re.DOTALL)
    if len(matches) != 1:
        raise ValueError("固定ライフサイクル関数本文を一意に読めない")
    grants = row["acl_expectations"]
    assert isinstance(grants, list)
    physical = f"{schema}.{name}({row['identity_args']})"
    return (
        "-- ELEMENT-TYPE: function\n"
        f"-- ELEMENT-ID: {function_id}\n\n"
        + matches[0]
        + "\n"
        + f"ALTER FUNCTION {physical} OWNER TO {row['owner_role_id']};\n"
        + f"REVOKE ALL PRIVILEGES ON FUNCTION {physical} FROM PUBLIC, pitchlog_app;\n"
        + "".join(
            f"GRANT EXECUTE ON FUNCTION {physical} TO {grant['grantee']};\n"
            for grant in grants
        )
    )
