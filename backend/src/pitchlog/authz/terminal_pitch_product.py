"""先行登録対象のv2関数/列ACL/triggerだけを生成する。正式writerはroot。"""

import re

from pitchlog.authz.terminal_pitch_write_stamp import candidate_function_bodies

OWNER = "pitchlog_sync_right_fn_owner"
FUNCTIONS = {
    "read_play_prefix_checkpoint": (
        "uuid, uuid, bigint",
        "TABLE(record_json text)",
        True,
    ),
    "lock_play_prefix_checkpoint": (
        "uuid, uuid, uuid, bytea, uuid, uuid, bigint",
        "TABLE(record_json text)",
        True,
    ),
    "read_play_prefix_history_page": (
        "uuid, uuid, bigint, bigint, uuid, bigint, bigint, bigin"
        "t, bigint, bigint, uuid, integer",
        "TABLE(record_json text)",
        True,
    ),
    "prepare_play_prefix_projection": (
        "uuid, uuid, uuid, bytea, uuid, uuid, text",
        "TABLE(prepared boolean)",
        True,
    ),
    "assert_play_prefix_projection": ("jsonb", "void", False),
    "finish_play_prefix_projection": ("", "trigger", False),
    "guard_play_prefix_runner_insert": ("", "trigger", False),
}
RUNNER_COLUMNS = (
    "tenant_id",
    "id",
    "play_id",
    "base",
    "runner_id",
    "status",
    "status_source",
    "responsible_pitcher_id",
    "import_batch_id",
    "retired_at",
)
TRIGGERS = (
    (
        "trg_play_prefix_30_project_after",
        "play_rows",
        "AFTER",
        "finish_play_prefix_projection",
    ),
    (
        "trg_play_prefix_runner_10_admit",
        "play_runners",
        "BEFORE",
        "guard_play_prefix_runner_insert",
    ),
)


def candidate_declarations():
    """既asset形式に合う宣言/実SQLだけを返し、書込/適用しない。"""
    functions = candidate_function_bodies()
    result = {n: [] for n in ("functions", "policies", "column_acl_expectations")}
    bodies = {}
    for name, (args, returns, app) in FUNCTIONS.items():
        key = f"FUNCTION:sync_right_api:{name}({args})"
        result["functions"].append(
            {
                "function_id": key,
                "schema_name": "sync_right_api",
                "function_name": name,
                "identity_args": args,
                "function_kind": "definer",
                "owner_role_id": OWNER,
                "language": "plpgsql",
                "returns": returns,
                "security_mode": "definer",
                "volatility": "volatile",
                "search_path": ["pg_catalog", "pg_temp"],
                "acl_expectations": [
                    {
                        "grantee": "pitchlog_app",
                        "privilege": "EXECUTE",
                        "grantable": False,
                    }
                ]
                if app
                else [],
                "revoked_acl_expectations": [
                    {"grantee": r, "privilege": "EXECUTE", "grantable": False}
                    for r in (["PUBLIC"] if app else ["PUBLIC", "pitchlog_app"])
                ],
            }
        )
        identity = f"sync_right_api.{name}({args})"
        sql = (
            re.sub(
                r"\ACREATE FUNCTION\s+(?=sync_right_api\.)",
                "CREATE FUNCTION ",
                functions[name],
                count=1,
            )
            + f"\nALTER FUNCTION {identity} OWNER TO {OWNER};\n"
            + f"REVOKE ALL ON FUNCTION {identity} FROM PUBLIC,pitchlog_app;\n"
        )
        if app:
            sql += f"GRANT EXECUTE ON FUNCTION {identity} TO pitchlog_app;\n"
        for trigger, table, timing, target in TRIGGERS:
            if target == name:
                sql += (
                    f"CREATE TRIGGER {trigger} {timing} INSERT ON public.{table} "
                    f"FOR EACH ROW EXECUTE FUNCTION sync_right_api.{name}();\n"
                )
        bodies["function|" + key] = sql
    predicate = (
        "tenant_id = NULLIF(pg_catalog.current_setting('app.tena"
        "nt_id',true),'')::uuid AND session_user = 'pitchlog_app"
        "'"
    )
    for command in ("SELECT", "INSERT"):
        name = "play_prefix_" + command.lower() + "_play_runners"
        key = "POLICY:play_runners:" + name
        result["policies"].append(
            {
                "policy_id": key,
                "table_id": "play_runners",
                "profile": "function_only",
                "policy_name": name,
                "command": command,
                "policy_mode": "permissive",
                "role_ids": [OWNER],
                "using_predicate_id": None,
                "using_column": None,
                "using_expression": predicate if command == "SELECT" else None,
                "with_check_predicate_id": None,
                "with_check_column": None,
                "with_check_expression": predicate if command == "INSERT" else None,
            }
        )
        clause = "USING" if command == "SELECT" else "WITH CHECK"
        bodies["policy|" + key] = (
            f"CREATE POLICY {name} ON public.play_runners FOR {command} "
            f"TO {OWNER} {clause} ({predicate});\n"
        )
    for column in RUNNER_COLUMNS:
        key = f"COLUMN-ACL:public:play_runners:{column}:{OWNER}"
        result["column_acl_expectations"].append(
            {
                "expectation_id": key,
                "object_kind": "column",
                "object_schema": "public",
                "object_id": "play_runners",
                "column_id": column,
                "grantee_role_id": OWNER,
                "privilege_ids": ["SELECT", "INSERT"],
                "grant_option": False,
            }
        )
        bodies["column_acl_expectation|" + key] = (
            f"GRANT SELECT ({column}),INSERT ({column}) "
            f"ON TABLE public.play_runners TO {OWNER};\n"
        )
    return result, bodies


def require_registered_product(*, artifact_sha256=None):
    """正式runtime/repository/DDL登録が揃わなければ新modeだけを閉じる。"""
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator, SchemaError, ValidationError

    root = Path(__file__).resolve().parents[4]
    try:
        ddl = json.loads(
            (root / "contracts/authz/product/ddl-elements.json").read_text()
        )
        repository = json.loads(
            (root / "contracts/tenant_boundary/repository-contract.json").read_text()
        )
        declarations, _ = candidate_declarations()
        identifiers = {
            "functions": "function_id",
            "policies": "policy_id",
            "column_acl_expectations": "expectation_id",
        }
        for section, rows in declarations.items():
            key = identifiers[section]
            actual = {r[key]: r for r in ddl[section]}
            if len(actual) != len(ddl[section]) or any(
                actual.get(r[key]) != r for r in rows
            ):
                raise ValueError
        manifest = json.loads(
            (root / "backend/domain/play-prefix-manifest.json").read_text()
        )
        catalog = json.loads(
            (root / "backend/domain/play-prefix-property-catalog.json").read_text()
        )
        schema = json.loads(
            (
                root / "backend/domain/play-prefix-property-catalog.schema.json"
            ).read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(catalog)
        if artifact_sha256 is None:
            import hashlib

            artifact_sha256 = hashlib.sha256(
                (root / "frontend/public/domain/pitchlog-domain.js").read_bytes()
            ).hexdigest()
        if (
            manifest.get("propertyCatalog", {}).get("path")
            != "backend/domain/play-prefix-property-catalog.json"
            or manifest.get("propertyCatalog", {}).get("schema")
            != "backend/domain/play-prefix-property-catalog.schema.json"
            or not any(
                c.get("calculation") == "play-prefix-v2"
                and c.get("source", {}).get("path")
                == "frontend/src/domain/playPrefixContinuation.ts"
                and any(
                    t.get("hash") == "sha256:" + artifact_sha256
                    and t.get("invocation", {}).get("operation")
                    == "derivePlayPrefixWithContinuation"
                    for t in c.get("directTargets", [])
                )
                for c in manifest.get("calculations", [])
            )
        ):
            raise ValueError
        operations = set(repository["product_function_operation_ids"])
        if (
            not {f"SYNC_PLAY_PREFIX:{n}" for n, (_, _, app) in FUNCTIONS.items() if app}
            <= operations
        ):
            raise ValueError
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        RecursionError,
        ValidationError,
        SchemaError,
    ):
        from pitchlog.repositories.ordinary_prefix import OrdinaryPrefixError

        raise OrdinaryPrefixError from None
