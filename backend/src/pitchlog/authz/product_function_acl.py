"""migration由来の製品関数ACLを決定的に生成する。"""

from __future__ import annotations

import ast
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
    from pitchlog.authz.first_ball_product import declaration

    key = f"FUNCTION:{schema_name}:{function_name}({identity_args})"
    added = declaration("functions", key)
    if added is not None:
        if function_kind != added["function_kind"]:
            raise ValueError("初球migration関数種別が不一致")
        return added
    if function_kind not in {"migration_trigger", "migration_function"}:
        raise ValueError(f"migration関数種別が不正: {function_kind}")
    if (schema_name, function_name, identity_args) == (
        "public",
        "protect_initial_right_storage",
        "",
    ):
        if function_kind != "migration_trigger" or execute_grantees:
            raise ValueError("内部triggerの種別/EXECUTEが不正")
        return build_initial_function_declarations()[
            "FUNCTION:public:protect_initial_right_storage()"
        ]
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
    from pitchlog.authz.first_ball_product import body, declaration

    key = f"FUNCTION:{schema_name}:{function_name}({identity_args})"
    added = declaration("functions", key)
    if added is not None:
        expected = tuple(r["grantee"] for r in added["acl_expectations"])
        if execute_grantees != expected:
            raise ValueError("初球function EXECUTEの全集合が不一致")
        sql = body("function", key)
        if sql is None:
            raise ValueError("初球function本文がない")
        return sql
    if (schema_name, function_name, identity_args) == (
        "public",
        "protect_initial_right_storage",
        "",
    ):
        if execute_grantees:
            raise ValueError("内部triggerへ直接EXECUTE不可")
        return generate_initial_function_sql(
            "FUNCTION:public:protect_initial_right_storage()"
        )
    if (schema_name, function_name, identity_args) == (
        "public",
        "protect_recording_generations_updates",
        "",
    ):
        if execute_grantees:
            raise ValueError("世代guardへ直接EXECUTE不可")
        return generate_generation_guard_sql(_REPOSITORY_ROOT)
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
    from pitchlog.authz.first_ball_product import BINDING_OWNER, declaration

    if grantee == BINDING_OWNER:
        row = declaration(
            "acl_expectations", f"ACL:pg_catalog:pg_control_system():{grantee}"
        )
        if row is None:
            raise ValueError("初球builtin宣言がない")
        return row
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
        and grantee in BUILTIN_EXECUTE_GRANTEES | {"pitchlog_sync_binding_fn_owner"}
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
        ("bind_initial_fresh_epoch", "boolean", ("pitchlog_rg1_control_actor",)),
        (
            "controller_lease_alive",
            "boolean",
            (
                "pitchlog_rg1_control_actor",
                "pitchlog_rg1_fn_owner",
            ),
        ),
        ("read_closed_gate", "jsonb", ("pitchlog_rg1_control_actor",)),
        ("scope_binding", "text", ("pitchlog_app", "pitchlog_initial_actor")),
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
        args = ({"scope_binding": "uuid", "bind_initial_fresh_epoch": "bigint"}).get(
            name, ""
        )
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
    """既固定SQLの判定本文を保ち、CREATEの再適用表記だけを揃える。"""
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
    # 再適用で関数を二重作成しない。AS本文・引数・戻り値は一切変更しない。
    definition = re.sub(
        r"^CREATE FUNCTION ", "CREATE OR REPLACE FUNCTION ", matches[0], count=1
    )
    grants = row["acl_expectations"]
    assert isinstance(grants, list)
    physical = f"{schema}.{name}({row['identity_args']})"
    return (
        "-- ELEMENT-TYPE: function\n"
        f"-- ELEMENT-ID: {function_id}\n\n"
        + definition
        + "\n"
        + f"ALTER FUNCTION {physical} OWNER TO {row['owner_role_id']};\n"
        + f"REVOKE ALL PRIVILEGES ON FUNCTION {physical} FROM PUBLIC, pitchlog_app;\n"
        + "".join(
            f"GRANT EXECUTE ON FUNCTION {physical} TO {grant['grantee']};\n"
            for grant in grants
        )
    )


_INITIAL_FUNCTIONS: dict[str, dict[str, object]] = {
    "FUNCTION:initial_right_api:lock_device(uuid, uuid)": {
        "function_id": "FUNCTION:initial_right_api:lock_device(uuid, uuid)",
        "schema_name": "initial_right_api",
        "function_name": "lock_device",
        "identity_args": "uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(credential_digest "
        "bytea, revoked_at "
        "timestamp with "
        "time zone)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    "FUNCTION:initial_right_api:read_existing_start(uuid, uuid, uuid)": {
        "function_id": "FUNCTION:initial_right_api:read_existing_start(uuid, "
        "uuid, "
        "uuid)",
        "schema_name": "initial_right_api",
        "function_name": "read_existing_start",
        "identity_args": "uuid, uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(tenant_id "
        "uuid, "
        "game_id "
        "uuid, "
        "start_request_id "
        "uuid, "
        "device_id "
        "uuid, "
        "generation "
        "bigint, "
        "recovery_generation "
        "bigint, "
        "proof_digest "
        "bytea, "
        "key_id "
        "text, "
        "nonce "
        "bytea, "
        "ciphertext "
        "bytea)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    "FUNCTION:initial_right_api:read_start_game(uuid, uuid)": {
        "function_id": "FUNCTION:initial_right_api:read_start_game(uuid, uuid)",
        "schema_name": "initial_right_api",
        "function_name": "read_start_game",
        "identity_args": "uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(status text)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    "FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)": {
        "function_id": "FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)",
        "schema_name": "initial_right_api",
        "function_name": "lock_preparing_game",
        "identity_args": "uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "boolean",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    "FUNCTION:initial_right_api:lock_current_start(uuid, uuid, uuid)": {
        "function_id": "FUNCTION:initial_right_api:lock_current_start(uuid, "
        "uuid, "
        "uuid)",
        "schema_name": "initial_right_api",
        "function_name": "lock_current_start",
        "identity_args": "uuid, uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(tenant_id "
        "uuid, "
        "game_id "
        "uuid, "
        "start_request_id "
        "uuid, "
        "device_id "
        "uuid, "
        "generation "
        "bigint, "
        "recovery_generation "
        "bigint, "
        "proof_digest "
        "bytea, "
        "key_id "
        "text, "
        "nonce "
        "bytea, "
        "ciphertext "
        "bytea)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    "FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)": {
        "function_id": "FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)",
        "schema_name": "initial_right_api",
        "function_name": "check_business_epoch",
        "identity_args": "uuid, bigint",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "boolean",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    (
        "FUNCTION:initial_right_api:insert_initial_grant(uuid, u"
        "uid, uuid, uuid, uuid, bigint, bigint, bytea, text, byt"
        "ea, bytea)"
    ): {
        "function_id": "FUNCTION:initial_right_api:insert_initial_grant(uuid, "
        "uuid, "
        "uuid, "
        "uuid, "
        "uuid, "
        "bigint, "
        "bigint, "
        "bytea, "
        "text, "
        "bytea, "
        "bytea)",
        "schema_name": "initial_right_api",
        "function_name": "insert_initial_grant",
        "identity_args": "uuid, "
        "uuid, "
        "uuid, "
        "uuid, "
        "uuid, "
        "bigint, "
        "bigint, "
        "bytea, "
        "text, "
        "bytea, "
        "bytea",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "boolean",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    (
        "FUNCTION:initial_right_api:begin_start_attempt(uuid, uu"
        "id, uuid, uuid, bytea, uuid)"
    ): {
        "function_id": "FUNCTION:initial_right_api:begin_start_attempt(uuid, "
        "uuid, "
        "uuid, "
        "uuid, "
        "bytea, "
        "uuid)",
        "schema_name": "initial_right_api",
        "function_name": "begin_start_attempt",
        "identity_args": "uuid, uuid, uuid, uuid, bytea, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(attempt_id uuid, outcome text)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    "FUNCTION:initial_right_api:resolve_start_attempt(uuid, uuid, uuid, uuid)": {
        "function_id": "FUNCTION:initial_right_api:resolve_start_attempt(uuid, "
        "uuid, "
        "uuid, "
        "uuid)",
        "schema_name": "initial_right_api",
        "function_name": "resolve_start_attempt",
        "identity_args": "uuid, uuid, uuid, uuid",
        "function_kind": "definer",
        "owner_role_id": "pitchlog_initial_fn_owner",
        "language": "plpgsql",
        "returns": "TABLE(outcome text, generation bigint)",
        "security_mode": "definer",
        "volatility": "volatile",
        "search_path": ["pg_catalog", "pg_temp"],
        "acl_expectations": [
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            }
        ],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
        ],
    },
    "FUNCTION:public:protect_initial_right_storage()": {
        "function_id": "FUNCTION:public:protect_initial_right_storage()",
        "schema_name": "public",
        "function_name": "protect_initial_right_storage",
        "identity_args": "",
        "function_kind": "migration_trigger",
        "owner_role_id": "pitchlog_owner",
        "acl_expectations": [],
        "revoked_acl_expectations": [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False},
            {"grantee": "pitchlog_app", "privilege": "EXECUTE", "grantable": False},
            {
                "grantee": "pitchlog_initial_actor",
                "privilege": "EXECUTE",
                "grantable": False,
            },
            {
                "grantee": "pitchlog_initial_fn_owner",
                "privilege": "EXECUTE",
                "grantable": False,
            },
        ],
    },
}

_INITIAL_API_SQL = {
    "FUNCTION:initial_right_api:lock_device(uuid, uuid)": "-- ELEMENT-TYPE: function\n"
    "-- ELEMENT-ID: "
    "FUNCTION:initial_right_api:lock_device(uuid, "
    "uuid)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE OR REPLACE FUNCTION "
    "initial_right_api.lock_device(p_tenant_id "
    "uuid, p_device_id uuid)\n"
    "RETURNS "
    "TABLE(credential_digest bytea, "
    "revoked_at timestamptz)\n"
    "LANGUAGE plpgsql VOLATILE "
    "SECURITY DEFINER\n"
    "SET search_path TO pg_catalog, "
    "pg_temp\n"
    "AS $body$\n"
    "DECLARE v_row record;\n"
    "BEGIN\n"
    "    IF session_user <> "
    "'pitchlog_initial_actor'\n"
    "       OR current_user <> "
    "'pitchlog_initial_fn_owner'\n"
    "       OR p_tenant_id IS NULL\n"
    "       OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS DISTINCT FROM "
    "p_tenant_id::text\n"
    "       OR p_device_id IS NULL "
    "THEN\n"
    "        RAISE EXCEPTION "
    "'initial right subject or "
    "input rejected' USING "
    "ERRCODE='42501';\n"
    "    END IF;\n"
    "    BEGIN\n"
    "        SELECT "
    "d.credential_digest, "
    "d.revoked_at INTO STRICT "
    "v_row\n"
    "          FROM "
    "public.trusted_devices AS d\n"
    "         WHERE "
    "d.tenant_id=p_tenant_id AND "
    "d.device_id=p_device_id\n"
    "         LIMIT 2 FOR SHARE;\n"
    "    EXCEPTION WHEN "
    "no_data_found THEN RETURN;\n"
    "    END;\n"
    "    RETURN QUERY SELECT "
    "v_row.credential_digest, "
    "v_row.revoked_at;\n"
    "EXCEPTION WHEN "
    "integrity_constraint_violation "
    "OR too_many_rows THEN\n"
    "    -- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    RAISE EXCEPTION 'initial "
    "right operation rejected' "
    "USING ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER FUNCTION "
    "initial_right_api.lock_device(uuid, "
    "uuid) OWNER TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE ALL ON FUNCTION "
    "initial_right_api.lock_device(uuid, "
    "uuid) FROM PUBLIC, "
    "pitchlog_app;\n"
    "GRANT EXECUTE ON FUNCTION "
    "initial_right_api.lock_device(uuid, "
    "uuid) TO "
    "pitchlog_initial_actor;\n",
    (
        "FUNCTION:initial_right_api:read_existing_start(uuid, uuid, uuid)"
    ): "-- ELEMENT-TYPE: "
    "function\n"
    "-- ELEMENT-ID: "
    "FUNCTION:initial_right_api:read_existing_start(uuid, "
    "uuid, uuid)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE OR "
    "REPLACE FUNCTION "
    "initial_right_api.read_existing_start(p_tenant_id "
    "uuid, p_game_id "
    "uuid, "
    "p_start_request_id "
    "uuid)\n"
    "RETURNS "
    "TABLE(tenant_id "
    "uuid, game_id "
    "uuid, "
    "start_request_id "
    "uuid, device_id "
    "uuid, generation "
    "bigint, "
    "recovery_generation "
    "bigint, "
    "proof_digest "
    "bytea, key_id "
    "text, nonce "
    "bytea, "
    "ciphertext "
    "bytea)\n"
    "LANGUAGE plpgsql "
    "VOLATILE "
    "SECURITY "
    "DEFINER\n"
    "SET search_path "
    "TO pg_catalog, "
    "pg_temp\n"
    "AS $body$\n"
    "DECLARE v_row "
    "record;\n"
    "BEGIN\n"
    "    IF "
    "session_user <> "
    "'pitchlog_initial_actor'\n"
    "       OR "
    "current_user <> "
    "'pitchlog_initial_fn_owner'\n"
    "       OR "
    "p_tenant_id IS "
    "NULL\n"
    "       OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS DISTINCT FROM "
    "p_tenant_id::text\n"
    "       OR "
    "p_game_id IS "
    "NULL\n"
    "       OR "
    "p_start_request_id "
    "IS NULL THEN\n"
    "        RAISE "
    "EXCEPTION "
    "'initial right "
    "subject or input "
    "rejected' USING "
    "ERRCODE='42501';\n"
    "    END IF;\n"
    "    BEGIN\n"
    "        SELECT "
    "d.tenant_id, "
    "d.game_id, "
    "d.start_request_id, "
    "d.device_id,\n"
    "           "
    "g.generation, "
    "g.recovery_generation, "
    "g.proof_digest,\n"
    "           "
    "d.key_id, "
    "d.nonce, "
    "d.ciphertext\n"
    "     INTO STRICT "
    "v_row\n"
    "      FROM "
    "public.game_start_requests "
    "AS r\n"
    "      JOIN "
    "public.recording_right_deliveries "
    "AS d\n"
    "        ON "
    "(d.tenant_id,d.game_id,d.start_request_id,d.device_id) "
    "=\n"
    "           "
    "(r.tenant_id,r.game_id,r.start_request_id,r.device_id)\n"
    "      JOIN "
    "public.recording_generations "
    "AS g\n"
    "        ON "
    "(g.tenant_id,g.game_id,g.generation) "
    "= "
    "(d.tenant_id,d.game_id,d.generation)\n"
    "     WHERE "
    "r.tenant_id = "
    "p_tenant_id AND "
    "r.game_id = "
    "p_game_id\n"
    "       AND "
    "r.start_request_id "
    "= "
    "p_start_request_id\n"
    "       AND "
    "g.kind = "
    "'normal' AND "
    "g.revoked_at IS "
    "NULL AND "
    "d.revoked_at IS "
    "NULL\n"
    "       AND "
    "g.holder_device "
    "= "
    "d.device_id::text\n"
    "       AND "
    "g.proof_digest "
    "IS NOT NULL AND "
    "pg_catalog.octet_length(g.proof_digest) "
    "= 32\n"
    "       AND "
    "g.recovery_generation "
    "> 0\n"
    "       AND "
    "EXISTS (SELECT 1 "
    "FROM "
    "public.rg1_restore_gate "
    "AS e\n"
    "                    "
    "WHERE "
    "e.singleton_id = "
    "1 AND "
    "e.recovery_generation "
    "= "
    "g.recovery_generation)\n"
    "     LIMIT 2;\n"
    "    EXCEPTION "
    "WHEN "
    "no_data_found "
    "THEN RETURN;\n"
    "    END;\n"
    "    RETURN QUERY "
    "SELECT "
    "v_row.tenant_id, "
    "v_row.game_id, "
    "v_row.start_request_id, "
    "v_row.device_id, "
    "v_row.generation, "
    "v_row.recovery_generation, "
    "v_row.proof_digest, "
    "v_row.key_id, "
    "v_row.nonce, "
    "v_row.ciphertext;\n"
    "EXCEPTION WHEN "
    "integrity_constraint_violation "
    "OR too_many_rows "
    "THEN\n"
    "    -- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    RAISE "
    "EXCEPTION "
    "'initial right "
    "operation "
    "rejected' USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER FUNCTION "
    "initial_right_api.read_existing_start(uuid, "
    "uuid, uuid) "
    "OWNER TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE ALL ON "
    "FUNCTION "
    "initial_right_api.read_existing_start(uuid, "
    "uuid, uuid) FROM "
    "PUBLIC, "
    "pitchlog_app;\n"
    "GRANT EXECUTE ON "
    "FUNCTION "
    "initial_right_api.read_existing_start(uuid, "
    "uuid, uuid) TO "
    "pitchlog_initial_actor;\n",
    (
        "FUNCTION:initial_right_api:read_start_game(uuid, uuid)"
    ): "-- ELEMENT-TYPE: function\n"
    "-- ELEMENT-ID: "
    "FUNCTION:initial_right_api:read_start_game(uuid, "
    "uuid)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE OR REPLACE FUNCTION "
    "initial_right_api.read_start_game(p_tenant_id "
    "uuid, p_game_id uuid)\n"
    "RETURNS TABLE(status "
    "text)\n"
    "LANGUAGE plpgsql VOLATILE "
    "SECURITY DEFINER\n"
    "SET search_path TO "
    "pg_catalog, pg_temp\n"
    "AS $body$\n"
    "DECLARE v_status text;\n"
    "BEGIN\n"
    "    IF session_user <> "
    "'pitchlog_initial_actor'\n"
    "       OR current_user <> "
    "'pitchlog_initial_fn_owner'\n"
    "       OR p_tenant_id IS "
    "NULL\n"
    "       OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS DISTINCT FROM "
    "p_tenant_id::text\n"
    "       OR p_game_id IS "
    "NULL THEN\n"
    "        RAISE EXCEPTION "
    "'initial right subject or "
    "input rejected' USING "
    "ERRCODE='42501';\n"
    "    END IF;\n"
    "    SELECT g.status INTO "
    "v_status FROM public.games "
    "AS g\n"
    "     WHERE "
    "g.tenant_id=p_tenant_id "
    "AND g.id=p_game_id;\n"
    "    IF FOUND THEN RETURN "
    "QUERY SELECT v_status; END "
    "IF;\n"
    "EXCEPTION WHEN "
    "integrity_constraint_violation "
    "OR too_many_rows THEN\n"
    "    -- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    RAISE EXCEPTION "
    "'initial right operation "
    "rejected' USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER FUNCTION "
    "initial_right_api.read_start_game(uuid, "
    "uuid) OWNER TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE ALL ON FUNCTION "
    "initial_right_api.read_start_game(uuid, "
    "uuid) FROM PUBLIC, "
    "pitchlog_app;\n"
    "GRANT EXECUTE ON FUNCTION "
    "initial_right_api.read_start_game(uuid, "
    "uuid) TO "
    "pitchlog_initial_actor;\n",
    "FUNCTION:initial_right_api:lock_preparing_game(uuid, uuid)": "-- ELEMENT-TYPE: "
    "function\n"
    "-- ELEMENT-ID: "
    "FUNCTION:initial_right_api:lock_preparing_game(uuid, "
    "uuid)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE OR REPLACE "
    "FUNCTION "
    "initial_right_api.lock_preparing_game(p_tenant_id "
    "uuid, p_game_id uuid)\n"
    "RETURNS boolean\n"
    "LANGUAGE plpgsql "
    "VOLATILE SECURITY "
    "DEFINER\n"
    "SET search_path TO "
    "pg_catalog, pg_temp\n"
    "AS $body$\n"
    "DECLARE v_status "
    "text;\n"
    "BEGIN\n"
    "    IF session_user <> "
    "'pitchlog_initial_actor'\n"
    "       OR current_user "
    "<> "
    "'pitchlog_initial_fn_owner'\n"
    "       OR p_tenant_id "
    "IS NULL\n"
    "       OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS DISTINCT FROM "
    "p_tenant_id::text\n"
    "       OR p_game_id IS "
    "NULL THEN\n"
    "        RAISE "
    "EXCEPTION 'initial "
    "right subject or input "
    "rejected' USING "
    "ERRCODE='42501';\n"
    "    END IF;\n"
    "    SELECT g.status "
    "INTO v_status FROM "
    "public.games AS g\n"
    "     WHERE "
    "g.tenant_id=p_tenant_id "
    "AND g.id=p_game_id FOR "
    "UPDATE;\n"
    "    RETURN FOUND AND "
    "v_status = "
    "'preparing';\n"
    "EXCEPTION WHEN "
    "integrity_constraint_violation "
    "OR too_many_rows THEN\n"
    "    -- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    RAISE EXCEPTION "
    "'initial right "
    "operation rejected' "
    "USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER FUNCTION "
    "initial_right_api.lock_preparing_game(uuid, "
    "uuid) OWNER TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE ALL ON FUNCTION "
    "initial_right_api.lock_preparing_game(uuid, "
    "uuid) FROM PUBLIC, "
    "pitchlog_app;\n"
    "GRANT EXECUTE ON "
    "FUNCTION "
    "initial_right_api.lock_preparing_game(uuid, "
    "uuid) TO "
    "pitchlog_initial_actor;\n",
    (
        "FUNCTION:initial_right_api:lock_current_start(uuid, uuid, uuid)"
    ): "-- ELEMENT-TYPE: "
    "function\n"
    "-- ELEMENT-ID: "
    "FUNCTION:initial_right_api:lock_current_start(uuid, "
    "uuid, uuid)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE OR REPLACE "
    "FUNCTION "
    "initial_right_api.lock_current_start(p_tenant_id "
    "uuid, p_game_id "
    "uuid, "
    "p_start_request_id "
    "uuid)\n"
    "RETURNS "
    "TABLE(tenant_id "
    "uuid, game_id "
    "uuid, "
    "start_request_id "
    "uuid, device_id "
    "uuid, generation "
    "bigint, "
    "recovery_generation "
    "bigint, "
    "proof_digest "
    "bytea, key_id "
    "text, nonce "
    "bytea, ciphertext "
    "bytea)\n"
    "LANGUAGE plpgsql "
    "VOLATILE SECURITY "
    "DEFINER\n"
    "SET search_path "
    "TO pg_catalog, "
    "pg_temp\n"
    "AS $body$\n"
    "DECLARE v_status "
    "text; "
    "v_generation "
    "bigint; "
    "v_delivery "
    "record;\n"
    "BEGIN\n"
    "    IF "
    "session_user <> "
    "'pitchlog_initial_actor'\n"
    "       OR "
    "current_user <> "
    "'pitchlog_initial_fn_owner'\n"
    "       OR "
    "p_tenant_id IS "
    "NULL\n"
    "       OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS DISTINCT FROM "
    "p_tenant_id::text\n"
    "       OR "
    "p_game_id IS "
    "NULL\n"
    "       OR "
    "p_start_request_id "
    "IS NULL THEN\n"
    "        RAISE "
    "EXCEPTION "
    "'initial right "
    "subject or input "
    "rejected' USING "
    "ERRCODE='42501';\n"
    "    END IF;\n"
    "    -- "
    "呼出側のdevice→request→attempt排他に続け、JOIN一括lockを使わない。\n"
    "    SELECT "
    "g.status INTO "
    "v_status FROM "
    "public.games AS "
    "g\n"
    "     WHERE "
    "g.tenant_id=p_tenant_id "
    "AND "
    "g.id=p_game_id "
    "FOR UPDATE;\n"
    "    IF NOT FOUND "
    "THEN RETURN; END "
    "IF;\n"
    "    BEGIN\n"
    "        SELECT "
    "g.generation INTO "
    "STRICT "
    "v_generation FROM "
    "public.recording_generations "
    "AS g\n"
    "         WHERE "
    "g.tenant_id=p_tenant_id "
    "AND "
    "g.game_id=p_game_id\n"
    "           AND "
    "g.kind='normal' "
    "AND g.revoked_at "
    "IS NULL LIMIT 2 "
    "FOR UPDATE;\n"
    "    EXCEPTION "
    "WHEN "
    "no_data_found "
    "THEN RETURN;\n"
    "    END;\n"
    "    SELECT "
    "d.start_request_id, "
    "d.device_id, "
    "d.revoked_at INTO "
    "v_delivery\n"
    "      FROM "
    "public.recording_right_deliveries "
    "AS d\n"
    "     WHERE "
    "d.tenant_id=p_tenant_id "
    "AND "
    "d.game_id=p_game_id "
    "AND "
    "d.generation=v_generation\n"
    "     FOR UPDATE;\n"
    "    IF NOT FOUND "
    "OR "
    "v_delivery.start_request_id "
    "IS DISTINCT FROM "
    "p_start_request_id\n"
    "     OR "
    "v_delivery.revoked_at "
    "IS NOT NULL THEN "
    "RETURN; END IF;\n"
    "    RETURN QUERY "
    "SELECT "
    "r.tenant_id,r.game_id,r.start_request_id,r.device_id,r.generation,\n"
    "        "
    "r.recovery_generation,r.proof_digest,r.key_id,r.nonce,r.ciphertext\n"
    "     FROM "
    "initial_right_api.read_existing_start(p_tenant_id,p_gam"
    "e_id,p_start_request_id) "
    "AS r;\n"
    "EXCEPTION WHEN "
    "integrity_constraint_violation "
    "OR too_many_rows "
    "THEN\n"
    "    -- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    RAISE "
    "EXCEPTION "
    "'initial right "
    "operation "
    "rejected' USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER FUNCTION "
    "initial_right_api.lock_current_start(uuid, "
    "uuid, uuid) OWNER "
    "TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE ALL ON "
    "FUNCTION "
    "initial_right_api.lock_current_start(uuid, "
    "uuid, uuid) FROM "
    "PUBLIC, "
    "pitchlog_app;\n"
    "GRANT EXECUTE ON "
    "FUNCTION "
    "initial_right_api.lock_current_start(uuid, "
    "uuid, uuid) TO "
    "pitchlog_initial_actor;\n",
    "FUNCTION:initial_right_api:check_business_epoch(uuid, bigint)": "-- ELEMENT-TYPE: "
    "function\n"
    "-- ELEMENT-ID: "
    "FUNCTION:initial_right_api:check_business_epoch(uuid, "
    "bigint)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE OR REPLACE "
    "FUNCTION "
    "initial_right_api.check_business_epoch(p_tenant_id "
    "uuid, "
    "p_recovery_generation "
    "bigint)\n"
    "RETURNS boolean\n"
    "LANGUAGE plpgsql "
    "VOLATILE SECURITY "
    "DEFINER\n"
    "SET search_path TO "
    "pg_catalog, "
    "pg_temp\n"
    "AS $body$\n"
    "DECLARE v_epoch "
    "bigint;\n"
    "BEGIN\n"
    "    IF session_user "
    "<> "
    "'pitchlog_initial_actor'\n"
    "       OR "
    "current_user <> "
    "'pitchlog_initial_fn_owner'\n"
    "       OR "
    "p_tenant_id IS "
    "NULL\n"
    "       OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS DISTINCT FROM "
    "p_tenant_id::text\n"
    "       OR "
    "p_recovery_generation "
    "IS NULL\n"
    "       OR "
    "p_recovery_generation<=0 "
    "THEN\n"
    "        RAISE "
    "EXCEPTION 'initial "
    "right subject or "
    "input rejected' "
    "USING "
    "ERRCODE='42501';\n"
    "    END IF;\n"
    "    SELECT "
    "e.recovery_generation "
    "INTO v_epoch FROM "
    "public.rg1_restore_gate "
    "AS e\n"
    "     WHERE "
    "e.singleton_id=1;\n"
    "    RETURN FOUND "
    "AND "
    "p_recovery_generation>0 "
    "AND v_epoch IS NOT "
    "NULL AND "
    "v_epoch=p_recovery_generation;\n"
    "EXCEPTION WHEN "
    "integrity_constraint_violation "
    "OR too_many_rows "
    "THEN\n"
    "    -- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    RAISE EXCEPTION "
    "'initial right "
    "operation rejected' "
    "USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER FUNCTION "
    "initial_right_api.check_business_epoch(uuid, "
    "bigint) OWNER TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE ALL ON "
    "FUNCTION "
    "initial_right_api.check_business_epoch(uuid, "
    "bigint) FROM "
    "PUBLIC, "
    "pitchlog_app;\n"
    "GRANT EXECUTE ON "
    "FUNCTION "
    "initial_right_api.check_business_epoch(uuid, "
    "bigint) TO "
    "pitchlog_initial_actor;\n",
    (
        "FUNCTION:initial_right_api:insert_initial_grant(uuid, u"
        "uid, uuid, uuid, uuid, bigint, bigint, bytea, text, byt"
        "ea, bytea)"
    ): "-- "
    "ELEMENT-TYPE: "
    "function\n"
    "-- "
    "ELEMENT-ID: "
    "FUNCTION:initial_right_api:insert_initial_grant(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bigint, "
    "bigint, "
    "bytea, "
    "text, "
    "bytea, "
    "bytea)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE "
    "OR "
    "REPLACE "
    "FUNCTION "
    "initial_right_api.insert_initial_grant(p_tenant_id "
    "uuid, "
    "p_game_id "
    "uuid, "
    "p_start_request_id "
    "uuid, "
    "p_device_id "
    "uuid, "
    "p_attempt_id "
    "uuid, "
    "p_generation "
    "bigint, "
    "p_recovery_generation "
    "bigint, "
    "p_proof_digest "
    "bytea, "
    "p_key_id "
    "text, "
    "p_nonce "
    "bytea, "
    "p_ciphertext "
    "bytea)\n"
    "RETURNS "
    "boolean\n"
    "LANGUAGE "
    "plpgsql "
    "VOLATILE "
    "SECURITY "
    "DEFINER\n"
    "SET "
    "search_path "
    "TO "
    "pg_catalog, "
    "pg_temp\n"
    "AS "
    "$body$\n"
    "DECLARE "
    "v_request "
    "record; "
    "v_outcome "
    "text; "
    "v_status "
    "text; "
    "v_epoch "
    "bigint; "
    "v_count "
    "bigint;\n"
    "BEGIN\n"
    "    "
    "IF "
    "session_user "
    "<> "
    "'pitchlog_initial_actor'\n"
    "       "
    "OR "
    "current_user "
    "<> "
    "'pitchlog_initial_fn_owner'\n"
    "       "
    "OR "
    "p_tenant_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS "
    "DISTINCT "
    "FROM "
    "p_tenant_id::text\n"
    "       "
    "OR "
    "p_game_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_start_request_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_device_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_attempt_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_generation "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_recovery_generation "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_proof_digest "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_key_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_nonce "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_ciphertext "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_generation<=0\n"
    "       "
    "OR "
    "p_recovery_generation<=0\n"
    "       "
    "OR "
    "pg_catalog.octet_length(p_proof_digest)<>32\n"
    "       "
    "OR "
    "p_key_id=''\n"
    "       "
    "OR "
    "pg_catalog.octet_length(p_nonce)<>12\n"
    "       "
    "OR "
    "pg_catalog.octet_length(p_ciphertext)<>48 "
    "THEN\n"
    "        "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "subject "
    "or "
    "input "
    "rejected' "
    "USING "
    "ERRCODE='42501';\n"
    "    "
    "END "
    "IF;\n"
    "    "
    "-- "
    "固定brokerだけが既issuerの実claim結果を渡す。引数を認証proofとは扱わない。\n"
    "    "
    "-- "
    "同Session既取得lockを、device→request→attempt→gameの順で再確認する。\n"
    "    "
    "PERFORM "
    "d.device_id "
    "FROM "
    "public.trusted_devices "
    "AS "
    "d\n"
    "     "
    "WHERE "
    "d.tenant_id=p_tenant_id "
    "AND "
    "d.device_id=p_device_id "
    "AND "
    "d.revoked_at "
    "IS "
    "NULL "
    "FOR "
    "SHARE;\n"
    "    "
    "IF "
    "NOT "
    "FOUND "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "SELECT "
    "r.device_id "
    "INTO "
    "v_request "
    "FROM "
    "public.game_start_requests "
    "AS "
    "r\n"
    "     "
    "WHERE "
    "r.tenant_id=p_tenant_id "
    "AND "
    "r.game_id=p_game_id "
    "AND "
    "r.start_request_id=p_start_request_id\n"
    "     "
    "FOR "
    "UPDATE;\n"
    "    "
    "IF "
    "NOT "
    "FOUND "
    "OR "
    "v_request.device_id "
    "IS "
    "DISTINCT "
    "FROM "
    "p_device_id "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "SELECT "
    "a.outcome "
    "INTO "
    "v_outcome "
    "FROM "
    "public.game_start_attempts "
    "AS "
    "a\n"
    "     "
    "WHERE "
    "a.tenant_id=p_tenant_id "
    "AND "
    "a.attempt_id=p_attempt_id "
    "AND "
    "a.game_id=p_game_id\n"
    "       "
    "AND "
    "a.start_request_id=p_start_request_id "
    "AND "
    "a.device_id=p_device_id "
    "FOR "
    "UPDATE;\n"
    "    "
    "IF "
    "NOT "
    "FOUND "
    "OR "
    "v_outcome "
    "IS "
    "DISTINCT "
    "FROM "
    "'pending' "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "SELECT "
    "g.status "
    "INTO "
    "v_status "
    "FROM "
    "public.games "
    "AS "
    "g\n"
    "     "
    "WHERE "
    "g.tenant_id=p_tenant_id "
    "AND "
    "g.id=p_game_id "
    "FOR "
    "UPDATE;\n"
    "    "
    "IF "
    "NOT "
    "FOUND "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "-- "
    "preparing検証は既lock_preparing_game。後続start "
    "hookのstatus変更をここで上書きしない。\n"
    "    "
    "IF "
    "EXISTS "
    "(SELECT "
    "1 "
    "FROM "
    "public.recording_generations "
    "AS "
    "g\n"
    "     "
    "WHERE "
    "g.tenant_id=p_tenant_id "
    "AND "
    "g.game_id=p_game_id) "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "SELECT "
    "e.recovery_generation "
    "INTO "
    "v_epoch "
    "FROM "
    "public.rg1_restore_gate "
    "AS "
    "e "
    "WHERE "
    "e.singleton_id=1;\n"
    "    "
    "IF "
    "NOT "
    "FOUND "
    "OR "
    "v_epoch "
    "IS "
    "NULL "
    "OR "
    "v_epoch "
    "IS "
    "DISTINCT "
    "FROM "
    "p_recovery_generation "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "INSERT "
    "INTO "
    "public.recording_generations\n"
    "     "
    "(tenant_id,game_id,generation,kind,issuance_order,holde"
    "r_device,confirmed_watermark,\n"
    "      "
    "applied_prefix,proof_digest,recovery_generation)\n"
    "     "
    "VALUES "
    "(p_tenant_id,p_game_id,p_generation,'normal',1,p_device_id::text,0,0,\n"
    "             "
    "p_proof_digest,p_recovery_generation);\n"
    "    "
    "INSERT "
    "INTO "
    "public.recording_right_deliveries\n"
    "     "
    "(tenant_id,game_id,generation,start_request_id,device_i"
    "d,key_id,nonce,ciphertext)\n"
    "     "
    "VALUES "
    "(p_tenant_id,p_game_id,p_generation,p_start_request_id,"
    "p_device_id,p_key_id,p_nonce,p_ciphertext);\n"
    "    "
    "UPDATE "
    "public.game_start_attempts "
    "AS "
    "a "
    "SET "
    "outcome='committed',resolved_at=CURRENT_TIMESTAMP\n"
    "     "
    "WHERE "
    "a.tenant_id=p_tenant_id "
    "AND "
    "a.attempt_id=p_attempt_id "
    "AND "
    "a.game_id=p_game_id\n"
    "       "
    "AND "
    "a.start_request_id=p_start_request_id "
    "AND "
    "a.device_id=p_device_id "
    "AND "
    "a.outcome='pending';\n"
    "    "
    "GET "
    "DIAGNOSTICS "
    "v_count "
    "= "
    "ROW_COUNT;\n"
    "    "
    "IF "
    "v_count<>1 "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "RETURN "
    "true;\n"
    "EXCEPTION "
    "WHEN "
    "integrity_constraint_violation "
    "OR "
    "too_many_rows "
    "THEN\n"
    "    "
    "-- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER "
    "FUNCTION "
    "initial_right_api.insert_initial_grant(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bigint, "
    "bigint, "
    "bytea, "
    "text, "
    "bytea, "
    "bytea) "
    "OWNER "
    "TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE "
    "ALL "
    "ON "
    "FUNCTION "
    "initial_right_api.insert_initial_grant(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bigint, "
    "bigint, "
    "bytea, "
    "text, "
    "bytea, "
    "bytea) "
    "FROM "
    "PUBLIC, "
    "pitchlog_app;\n"
    "GRANT "
    "EXECUTE "
    "ON "
    "FUNCTION "
    "initial_right_api.insert_initial_grant(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bigint, "
    "bigint, "
    "bytea, "
    "text, "
    "bytea, "
    "bytea) "
    "TO "
    "pitchlog_initial_actor;\n",
    (
        "FUNCTION:initial_right_api:begin_start_attempt(uuid, uu"
        "id, uuid, uuid, bytea, uuid)"
    ): "-- "
    "ELEMENT-TYPE: "
    "function\n"
    "-- "
    "ELEMENT-ID: "
    "FUNCTION:initial_right_api:begin_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bytea, "
    "uuid)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE "
    "OR "
    "REPLACE "
    "FUNCTION "
    "initial_right_api.begin_start_attempt(p_tenant_id "
    "uuid, "
    "p_game_id "
    "uuid, "
    "p_start_request_id "
    "uuid, "
    "p_device_id "
    "uuid, "
    "p_request_digest "
    "bytea, "
    "p_attempt_id "
    "uuid)\n"
    "RETURNS "
    "TABLE(attempt_id "
    "uuid, "
    "outcome "
    "text)\n"
    "LANGUAGE "
    "plpgsql "
    "VOLATILE "
    "SECURITY "
    "DEFINER\n"
    "SET "
    "search_path "
    "TO "
    "pg_catalog, "
    "pg_temp\n"
    "AS "
    "$body$\n"
    "DECLARE "
    "v_request "
    "record; "
    "v_attempt "
    "record;\n"
    "BEGIN\n"
    "    "
    "IF "
    "session_user "
    "<> "
    "'pitchlog_initial_actor'\n"
    "       "
    "OR "
    "current_user "
    "<> "
    "'pitchlog_initial_fn_owner'\n"
    "       "
    "OR "
    "p_tenant_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS "
    "DISTINCT "
    "FROM "
    "p_tenant_id::text\n"
    "       "
    "OR "
    "p_game_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_start_request_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_device_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_request_digest "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "p_attempt_id "
    "IS "
    "NULL\n"
    "       "
    "OR "
    "pg_catalog.octet_length(p_request_digest)<>32 "
    "THEN\n"
    "        "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "subject "
    "or "
    "input "
    "rejected' "
    "USING "
    "ERRCODE='42501';\n"
    "    "
    "END "
    "IF;\n"
    "    "
    "-- "
    "before-business短intent専用。資格の真照合は同SessionのPython "
    "hmacが先行する。\n"
    "    "
    "PERFORM "
    "d.device_id "
    "FROM "
    "public.trusted_devices "
    "AS "
    "d\n"
    "     "
    "WHERE "
    "d.tenant_id=p_tenant_id "
    "AND "
    "d.device_id=p_device_id "
    "AND "
    "d.revoked_at "
    "IS "
    "NULL\n"
    "     "
    "FOR "
    "SHARE;\n"
    "    "
    "IF "
    "NOT "
    "FOUND "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "PERFORM "
    "g.id "
    "FROM "
    "public.games "
    "AS "
    "g "
    "WHERE "
    "g.tenant_id=p_tenant_id "
    "AND "
    "g.id=p_game_id;\n"
    "    "
    "IF "
    "NOT "
    "FOUND "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "INSERT "
    "INTO "
    "public.game_start_requests "
    "(tenant_id,game_id,start_request_id,device_id,request_digest)\n"
    "     "
    "VALUES "
    "(p_tenant_id,p_game_id,p_start_request_id,p_device_id,p"
    "_request_digest)\n"
    "     "
    "ON "
    "CONFLICT "
    "(tenant_id,game_id,start_request_id) "
    "DO "
    "NOTHING;\n"
    "    "
    "SELECT "
    "r.device_id,r.request_digest "
    "INTO "
    "STRICT "
    "v_request "
    "FROM "
    "public.game_start_requests "
    "AS "
    "r\n"
    "     "
    "WHERE "
    "r.tenant_id=p_tenant_id "
    "AND "
    "r.game_id=p_game_id "
    "AND "
    "r.start_request_id=p_start_request_id\n"
    "     "
    "FOR "
    "UPDATE;\n"
    "    "
    "IF "
    "v_request.device_id "
    "IS "
    "DISTINCT "
    "FROM "
    "p_device_id\n"
    "     "
    "OR "
    "v_request.request_digest "
    "IS "
    "DISTINCT "
    "FROM "
    "p_request_digest "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "-- "
    "旧rolled_backの再試行許可は別制御差分。期限や0行から新attemptへ進めない。\n"
    "    "
    "BEGIN\n"
    "        "
    "SELECT "
    "a.attempt_id,a.outcome "
    "INTO "
    "STRICT "
    "v_attempt "
    "FROM "
    "public.game_start_attempts "
    "AS "
    "a\n"
    "         "
    "WHERE "
    "a.tenant_id=p_tenant_id "
    "AND "
    "a.game_id=p_game_id "
    "AND "
    "a.start_request_id=p_start_request_id\n"
    "           "
    "AND "
    "a.device_id=p_device_id "
    "LIMIT "
    "2 "
    "FOR "
    "UPDATE;\n"
    "    "
    "EXCEPTION "
    "WHEN "
    "no_data_found "
    "THEN\n"
    "        "
    "INSERT "
    "INTO "
    "public.game_start_attempts "
    "(tenant_id,attempt_id,game_id,start_request_id,device_id)\n"
    "         "
    "VALUES "
    "(p_tenant_id,p_attempt_id,p_game_id,p_start_request_id,p_device_id);\n"
    "        "
    "RETURN "
    "QUERY "
    "SELECT "
    "p_attempt_id,'pending'::text;\n"
    "        "
    "RETURN;\n"
    "    "
    "END;\n"
    "    "
    "IF "
    "v_attempt.outcome "
    "NOT "
    "IN "
    "('pending','committed') "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END "
    "IF;\n"
    "    "
    "RETURN "
    "QUERY "
    "SELECT "
    "v_attempt.attempt_id,v_attempt.outcome;\n"
    "EXCEPTION "
    "WHEN "
    "integrity_constraint_violation "
    "OR "
    "too_many_rows "
    "THEN\n"
    "    "
    "-- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER "
    "FUNCTION "
    "initial_right_api.begin_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bytea, "
    "uuid) "
    "OWNER "
    "TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE "
    "ALL "
    "ON "
    "FUNCTION "
    "initial_right_api.begin_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bytea, "
    "uuid) "
    "FROM "
    "PUBLIC, "
    "pitchlog_app;\n"
    "GRANT "
    "EXECUTE "
    "ON "
    "FUNCTION "
    "initial_right_api.begin_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid, "
    "bytea, "
    "uuid) "
    "TO "
    "pitchlog_initial_actor;\n",
    "FUNCTION:initial_right_api:resolve_start_attempt(uuid, uuid, uuid, uuid)": "-- "
    "ELEMENT-TYPE: "
    "function\n"
    "-- "
    "ELEMENT-ID: "
    "FUNCTION:initial_right_api:resolve_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid)\n"
    "-- "
    "未適用候補。Python私有actorの資格/phase照合と既issuerを代替しない。\n"
    "CREATE "
    "OR "
    "REPLACE "
    "FUNCTION "
    "initial_right_api.resolve_start_attempt(p_tenant_id "
    "uuid, "
    "p_game_id "
    "uuid, "
    "p_start_request_id "
    "uuid, "
    "p_attempt_id "
    "uuid)\n"
    "RETURNS "
    "TABLE(outcome "
    "text, "
    "generation "
    "bigint)\n"
    "LANGUAGE "
    "plpgsql "
    "VOLATILE "
    "SECURITY "
    "DEFINER\n"
    "SET "
    "search_path "
    "TO "
    "pg_catalog, "
    "pg_temp\n"
    "AS "
    "$body$\n"
    "DECLARE "
    "v_device "
    "uuid; "
    "v_outcome "
    "text; "
    "v_row "
    "record;\n"
    "BEGIN\n"
    "    IF "
    "session_user "
    "<> "
    "'pitchlog_initial_actor'\n"
    "       "
    "OR "
    "current_user "
    "<> "
    "'pitchlog_initial_fn_owner'\n"
    "       "
    "OR "
    "p_tenant_id "
    "IS NULL\n"
    "       "
    "OR "
    "NULLIF(pg_catalog.current_setting('app.tenant_id',true),'') "
    "IS "
    "DISTINCT "
    "FROM "
    "p_tenant_id::text\n"
    "       "
    "OR "
    "p_game_id "
    "IS NULL\n"
    "       "
    "OR "
    "p_start_request_id "
    "IS NULL\n"
    "       "
    "OR "
    "p_attempt_id "
    "IS NULL "
    "THEN\n"
    "        "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "subject "
    "or input "
    "rejected' "
    "USING "
    "ERRCODE='42501';\n"
    "    END "
    "IF;\n"
    "    -- "
    "device資格真照合の後、reserve/claimより前。同じbusiness "
    "Sessionで保持する。\n"
    "    "
    "SELECT "
    "r.device_id "
    "INTO "
    "v_device "
    "FROM "
    "public.game_start_requests "
    "AS r\n"
    "     "
    "WHERE "
    "r.tenant_id=p_tenant_id "
    "AND "
    "r.game_id=p_game_id "
    "AND "
    "r.start_request_id=p_start_request_id\n"
    "     FOR "
    "UPDATE;\n"
    "    IF "
    "NOT "
    "FOUND "
    "THEN "
    "RETURN; "
    "END IF;\n"
    "    "
    "SELECT "
    "a.outcome "
    "INTO "
    "v_outcome "
    "FROM "
    "public.game_start_attempts "
    "AS a\n"
    "     "
    "WHERE "
    "a.tenant_id=p_tenant_id "
    "AND "
    "a.attempt_id=p_attempt_id "
    "AND "
    "a.game_id=p_game_id\n"
    "       "
    "AND "
    "a.start_request_id=p_start_request_id "
    "AND "
    "a.device_id=v_device "
    "FOR "
    "UPDATE;\n"
    "    IF "
    "NOT "
    "FOUND "
    "THEN "
    "RETURN; "
    "END IF;\n"
    "    IF "
    "v_outcome='pending' "
    "THEN\n"
    "        "
    "IF "
    "EXISTS "
    "(SELECT "
    "1 FROM "
    "public.recording_right_deliveries "
    "AS d\n"
    "           "
    "WHERE "
    "d.tenant_id=p_tenant_id "
    "AND "
    "d.game_id=p_game_id "
    "AND "
    "d.start_request_id=p_start_request_id)\n"
    "        "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END IF;\n"
    "        "
    "RETURN "
    "QUERY "
    "SELECT "
    "'pending'::text,NULL::bigint;\n"
    "    "
    "ELSIF "
    "v_outcome='committed' "
    "THEN\n"
    "        "
    "BEGIN\n"
    "            "
    "SELECT "
    "r.* INTO "
    "STRICT "
    "v_row\n"
    "              "
    "FROM "
    "initial_right_api.read_existing_start(p_tenant_id,p_gam"
    "e_id,p_start_request_id) "
    "AS r;\n"
    "        "
    "EXCEPTION "
    "WHEN "
    "no_data_found "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514';\n"
    "        "
    "END;\n"
    "        "
    "IF "
    "v_row.device_id "
    "IS "
    "DISTINCT "
    "FROM "
    "v_device "
    "THEN "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514'; "
    "END IF;\n"
    "        "
    "RETURN "
    "QUERY "
    "SELECT "
    "'committed'::text,v_row.generation;\n"
    "    "
    "ELSE\n"
    "        "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE "
    "= "
    "'23514';\n"
    "    END "
    "IF;\n"
    "EXCEPTION "
    "WHEN "
    "integrity_constraint_violation "
    "OR "
    "too_many_rows "
    "THEN\n"
    "    -- "
    "制約detailへdigest/暗号文/owner行を露出せず、transactionは失敗のまま返す。\n"
    "    "
    "RAISE "
    "EXCEPTION "
    "'initial "
    "right "
    "operation "
    "rejected' "
    "USING "
    "ERRCODE='23514';\n"
    "END;\n"
    "$body$;\n"
    "ALTER "
    "FUNCTION "
    "initial_right_api.resolve_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid) "
    "OWNER TO "
    "pitchlog_initial_fn_owner;\n"
    "REVOKE "
    "ALL ON "
    "FUNCTION "
    "initial_right_api.resolve_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid) "
    "FROM "
    "PUBLIC, "
    "pitchlog_app;\n"
    "GRANT "
    "EXECUTE "
    "ON "
    "FUNCTION "
    "initial_right_api.resolve_start_attempt(uuid, "
    "uuid, "
    "uuid, "
    "uuid) TO "
    "pitchlog_initial_actor;\n",
}


def build_initial_function_declarations() -> dict[str, dict[str, object]]:
    """公開9ABIと非公開migration trigger1を区別した閉宣言を返す。"""
    from copy import deepcopy

    return deepcopy(_INITIAL_FUNCTIONS)


def generate_initial_function_sql(function_id: str) -> str:
    """初期9APIの単一SQL定義または内部triggerの最小ACLを生成する。"""
    from pitchlog.authz.initial_start_sql import (
        generate_start_function_sql,
        start_function_declarations,
    )

    if function_id == LOOKUP_FUNCTION_ID:
        return generate_lookup_function_sql()
    if function_id == ENROLL_FUNCTION_ID:
        return generate_enrollment_function_sql()
    if function_id in start_function_declarations():
        return generate_start_function_sql(function_id)
    if function_id in _INITIAL_API_SQL:
        return _INITIAL_API_SQL[function_id]
    if function_id == "FUNCTION:public:protect_initial_right_storage()":
        return (
            "-- ELEMENT-TYPE: function\n"
            f"-- ELEMENT-ID: {function_id}\n\n"
            "REVOKE EXECUTE ON FUNCTION public.protect_initial_right_storage() "
            "FROM PUBLIC, pitchlog_app, pitchlog_initial_actor, pitc"
            "hlog_initial_fn_owner;\n"
        )
    raise ValueError("初期関数が閉集合にない")


def generate_generation_guard_sql(root: Path) -> str:
    """0036と同一の世代不変guard定義からprofileのbodyを生成する。"""
    migration = (
        root / "backend/migrations/versions/0036_initial_recording_right_storage.py"
    )
    try:
        tree = ast.parse(migration.read_text(encoding="utf-8"))
        bindings = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and node.id == "_GENERATION_GUARD_SQL"
        ]
        declarations = [
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_GENERATION_GUARD_SQL"
        ]
        other_bindings = any(
            (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name == "_GENERATION_GUARD_SQL"
            )
            or (
                isinstance(node, ast.alias)
                and (node.asname or node.name.split(".")[0]) == "_GENERATION_GUARD_SQL"
            )
            for node in ast.walk(tree)
        )
        if other_bindings or len(bindings) != 1 or len(declarations) != 1:
            raise ValueError("固定定数の単一トップレベル代入でない")
        declaration = declarations[0]
        values = ast.literal_eval(declaration.value)
        if (
            type(values) is not tuple
            or len(values) != 3
            or any(type(value) is not str or not value.strip() for value in values)
        ):
            raise ValueError("固定DDL三要素でない")
        sql = values[0]
    except (OSError, SyntaxError, ValueError, TypeError) as exc:
        raise ValueError("0036の世代guard供給が不正") from exc
    return (
        "-- ELEMENT-TYPE: function\n"
        "-- ELEMENT-ID: FUNCTION:public:protect_recording_genera"
        "tions_updates()\n\n" + sql.rstrip(";\n") + ";\n"
        "REVOKE EXECUTE ON FUNCTION public.protect_recording_gen"
        "erations_updates() "
        "FROM PUBLIC, pitchlog_app;\n"
    )


ENROLL_FUNCTION_ID = "FUNCTION:initial_right_api:enroll_device(uuid, uuid, bytea)"


def build_enrollment_function_declarations() -> dict[str, dict[str, object]]:
    """新1ABIだけを既初期ownerへ閉じ、旧9宣言を変えない。"""
    from copy import deepcopy

    row = deepcopy(
        _INITIAL_FUNCTIONS["FUNCTION:initial_right_api:lock_device(uuid, uuid)"]
    )
    row.update(
        function_id=ENROLL_FUNCTION_ID,
        function_name="enroll_device",
        identity_args="uuid, uuid, bytea",
        returns="uuid",
    )
    return {ENROLL_FUNCTION_ID: row}


def generate_enrollment_function_sql() -> str:
    """owner列INSERT3だけを使う固定関数。tenantと実session主体を再照合する。"""
    return f"""-- ELEMENT-TYPE: function
-- ELEMENT-ID: {ENROLL_FUNCTION_ID}

CREATE OR REPLACE FUNCTION initial_right_api.enroll_device(
    p_tenant_id uuid, p_device_id uuid, p_credential_digest bytea)
RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL OR p_device_id IS NULL
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')
          IS DISTINCT FROM p_tenant_id::text
       OR p_credential_digest IS NULL
       OR pg_catalog.octet_length(p_credential_digest) <> 32 THEN
        RAISE EXCEPTION 'initial enrollment subject or input rejected'
            USING ERRCODE='42501';
    END IF;
    INSERT INTO public.trusted_devices(tenant_id,device_id,credential_digest)
    VALUES (p_tenant_id,p_device_id,p_credential_digest);
    RETURN p_device_id;
END
$body$;
ALTER FUNCTION initial_right_api.enroll_device(uuid, uuid, bytea)
    OWNER TO pitchlog_initial_fn_owner;
REVOKE EXECUTE ON FUNCTION initial_right_api.enroll_device(uuid, uuid, bytea)
    FROM PUBLIC, pitchlog_app, pitchlog_initial_auth_verifier;
GRANT EXECUTE ON FUNCTION initial_right_api.enroll_device(uuid, uuid, bytea)
    TO pitchlog_initial_actor;
"""


LOOKUP_FUNCTION_ID = (
    "FUNCTION:initial_right_api:lookup_existing_start_attemp"
    "t(uuid, uuid, uuid, uuid, bytea)"
)


def lookup_assets_present(asset: dict[str, object]) -> bool:
    """任意の未知関数を包括許可せず、新lookup宣言だけを識別する。"""
    rows = asset.get("functions")
    return isinstance(rows, list) and any(
        isinstance(row, dict)
        and (
            row.get("function_id") == LOOKUP_FUNCTION_ID
            or row.get("function_name") == "lookup_existing_start_attempt"
        )
        for row in rows
    )


def build_lookup_function_declarations() -> dict[str, dict[str, object]]:
    """旧9/start2/enroll1を変えない非作成lookup1宣言。"""
    from copy import deepcopy

    row = deepcopy(
        _INITIAL_FUNCTIONS["FUNCTION:initial_right_api:lock_device(uuid, uuid)"]
    )
    row.update(
        function_id=LOOKUP_FUNCTION_ID,
        function_name="lookup_existing_start_attempt",
        identity_args="uuid, uuid, uuid, uuid, bytea",
        returns="TABLE(attempt_id uuid, outcome text)",
    )
    return {LOOKUP_FUNCTION_ID: row}


def generate_lookup_function_sql() -> str:
    """資格照合後のrequest/attempt排他だけを行い、欠損から作成しない。"""
    return f"""-- ELEMENT-TYPE: function
-- ELEMENT-ID: {LOOKUP_FUNCTION_ID}

CREATE OR REPLACE FUNCTION initial_right_api.lookup_existing_start_attempt(
    p_tenant_id uuid, p_game_id uuid, p_start_request_id uuid,
    p_device_id uuid, p_request_digest bytea)
RETURNS TABLE(attempt_id uuid, outcome text)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path TO pg_catalog, pg_temp
AS $body$
DECLARE req record; attempt record;
BEGIN
    IF session_user <> 'pitchlog_initial_actor'
       OR current_user <> 'pitchlog_initial_fn_owner'
       OR p_tenant_id IS NULL OR p_game_id IS NULL
       OR p_start_request_id IS NULL OR p_device_id IS NULL
       OR p_request_digest IS NULL
       OR pg_catalog.octet_length(p_request_digest) <> 32
       OR NULLIF(pg_catalog.current_setting('app.tenant_id',true),'')
          IS DISTINCT FROM p_tenant_id::text THEN
        RAISE EXCEPTION 'initial lookup subject rejected' USING ERRCODE='42501';
    END IF;
    SELECT r.device_id,r.request_digest INTO req
      FROM public.game_start_requests r
      WHERE r.tenant_id=p_tenant_id AND r.game_id=p_game_id
        AND r.start_request_id=p_start_request_id FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    IF req.device_id IS DISTINCT FROM p_device_id
       OR req.request_digest IS DISTINCT FROM p_request_digest THEN
        RAISE EXCEPTION 'initial lookup owner rejected' USING ERRCODE='42501';
    END IF;
    BEGIN
        SELECT a.attempt_id,a.outcome INTO STRICT attempt
          FROM public.game_start_attempts a
          WHERE a.tenant_id=p_tenant_id AND a.game_id=p_game_id
            AND a.start_request_id=p_start_request_id AND a.device_id=p_device_id
          LIMIT 2 FOR UPDATE;
    EXCEPTION WHEN no_data_found THEN RETURN;
    END;
    IF attempt.outcome NOT IN ('pending','committed') THEN
        RAISE EXCEPTION 'initial lookup remains unresolved' USING ERRCODE='42501';
    END IF;
    RETURN QUERY SELECT attempt.attempt_id,attempt.outcome;
EXCEPTION WHEN integrity_constraint_violation OR too_many_rows THEN
    RAISE EXCEPTION 'initial lookup rejected' USING ERRCODE='23514';
END;
$body$;
ALTER FUNCTION initial_right_api.lookup_existing_start_attempt(
    uuid, uuid, uuid, uuid, bytea) OWNER TO pitchlog_initial_fn_owner;
REVOKE EXECUTE ON FUNCTION initial_right_api.lookup_existing_start_attempt(
    uuid, uuid, uuid, uuid, bytea)
    FROM PUBLIC, pitchlog_app, pitchlog_initial_auth_verifier;
GRANT EXECUTE ON FUNCTION initial_right_api.lookup_existing_start_attempt(
    uuid, uuid, uuid, uuid, bytea) TO pitchlog_initial_actor;
"""
