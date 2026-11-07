"""毎球CSVの唯一候補SQLを閉じた認可宣言へ写す。配備・正式受理はしない。"""

from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any

from pitchlog.authz import play_export_source_read_product as source_read
from pitchlog.authz import play_export_writer_product as writer
from pitchlog.authz.function_result_type import pg_result_type

_ROOT = Path(__file__).resolve().parents[4]
_SOURCE = _ROOT / "docs/features/ud2-csv-export/candidates/play_export_snapshots.sql"
_SOURCE_SHA256 = "0e8b9fd6a2ca1aecda05705f0e175f1f37f5c07566c5a6890094172fd21b86ca"
_TABLE = "play_export_snapshots"
_OWNER = "pitchlog_sync_right_fn_owner"
_APP = "pitchlog_app"
_COLUMNS = (
    "tenant_id",
    "game_id",
    "play_row_id",
    "plays_csv_json",
    "full_innings_json",
    "source_event_id",
    "play_version",
    "recording_generation",
    "event_sequence",
    "captured_at",
)
_INDEX_NAMES = (
    "ix_play_export_snapshots_game_captured",
    "ix_play_rows_export_audit",
    "ix_operation_events_export_audit",
)
_FUNCTIONS = {
    "read_writer_play_export_aggregate": (
        "uuid, uuid, uuid, uuid, text, bigint, bytea",
        "TABLE(pitcher_pitch_count bigint, top_score jsonb, bottom_score jsonb, "
        "full_innings jsonb)",
        "volatile",
    ),
    "save_writer_play_export_snapshot": (
        "uuid, uuid, uuid, uuid, text, bigint, bytea, jsonb",
        "uuid",
        "volatile",
    ),
    "read_writer_play_export_substitute": (
        "uuid, uuid, uuid, uuid, bytea",
        "TABLE(substitution_event_id uuid, substitution_d2 bigint, "
        "substitution_payload jsonb)",
        "volatile",
    ),
    "read_play_export_source_page": (
        "uuid, bigint, bigint, integer",
        "TABLE(fact_version_id uuid, revision bigint, source_set_sha256 text, "
        "source_count bigint, completion_state text, transaction_id text, "
        "recording_generation bigint, d1 bigint, d2 bigint, source_event_id uuid, "
        "play_row_id uuid, slot_version bigint, play_row_version bigint, "
        "base_event_id uuid, source_fingerprint text)",
        "stable",
    ),
}
_IDS = {
    "tables": "table_id",
    "functions": "function_id",
    "policies": "policy_id",
    "acl_expectations": "acl_id",
    "column_acl_expectations": "expectation_id",
}


def _source() -> str:
    """候補原典の全byteを固定点へ照合し、無裁定の追補を取り込まない。"""
    raw = _SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != _SOURCE_SHA256:
        raise ValueError("毎球CSV候補SQLの固定byteが不一致")
    return raw.decode("utf-8")


def source_structure() -> dict[str, Any]:
    """CREATE/索引は構造照合用metadataだけに返し、認可BODIESへ入れない。"""
    source = _source()
    table = re.search(
        r"CREATE TABLE public\.play_export_snapshots \([\s\S]*?\n\);", source
    )
    matches = re.findall(r"(CREATE INDEX (\w+)[\s\S]*?;)", source)
    # index名→原SQLへ写し、正式assetに未定義のindexes節は作らない。
    if len(matches) != 3:
        raise ValueError("毎球CSVの索引件数が不一致")
    indexes = {name: sql for sql, name in matches}
    if table is None or tuple(indexes) != _INDEX_NAMES:
        raise ValueError("毎球CSVのtable/3索引集合が不一致")
    columns = []
    for line in table[0].splitlines()[1:11]:
        field = re.fullmatch(
            r"\s*(\w+) (uuid|jsonb|bigint|timestamptz) NOT NULL(.*?),?", line
        )
        if field is None:
            raise ValueError("毎球CSVの列型/NOT NULLが不一致")
        columns.append(
            {
                "name": field[1],
                "type": field[2],
                "nullable": False,
                "suffix": field[3].removesuffix(",").strip(),
            }
        )
    if tuple(row["name"] for row in columns) != _COLUMNS:
        raise ValueError("毎球CSVの10列順が不一致")
    return {
        "source_sha256": _SOURCE_SHA256,
        "columns": columns,
        "create_table": table[0],
        "indexes": indexes,
        "read_columns": _COLUMNS,
        "insert_columns": _COLUMNS[:-1],
    }


def _function_bundle(sql: str) -> dict[str, tuple[dict[str, Any], str, str]]:
    """既唯一providerの全関数byteを切り出し、閉署名と属性だけを検査する。"""
    pattern = re.compile(
        r"(?P<body>CREATE FUNCTION stats_api\.(?P<name>\w+)\((?P<args>[^()]*)\)"
        r"\s+RETURNS (?P<returns>TABLE\([^()]*\)|uuid)\s+LANGUAGE plpgsql "
        r"(?P<volatility>VOLATILE|STABLE) SECURITY DEFINER\s+"
        r"SET search_path=pg_catalog,pg_temp AS (?P<tag>\$\w+\$)"
        r"[\s\S]*?(?P=tag);\n?)"
        r"(?P<acl>ALTER FUNCTION[\s\S]*?GRANT EXECUTE ON FUNCTION[^;]*;\n?)"
    )
    values = {}
    cursor = 0
    for match in pattern.finditer(sql):
        if sql[cursor : match.start()].strip():
            raise ValueError("毎球CSV関数外の未知SQL")
        name = match["name"]
        if name not in _FUNCTIONS or name in values:
            raise ValueError("毎球CSV関数の未知/重複")
        arguments = [arg.strip().split() for arg in match["args"].split(",")]
        if any(
            len(arg) != 2 or re.fullmatch(r"p_[a-z0-9_]+", arg[0]) is None
            for arg in arguments
        ):
            raise ValueError("毎球CSV関数引数が不正")
        identity = ", ".join(arg[1] for arg in arguments)
        returns = pg_result_type(" ".join(match["returns"].split()))
        volatility = match["volatility"].lower()
        if (identity, returns, volatility) != _FUNCTIONS[name]:
            raise ValueError("毎球CSVの閉署名/戻り値/実行属性が不一致")
        full_name = f"stats_api.{name}({identity})"
        expected_acl = (
            f"ALTER FUNCTION {full_name} OWNER TO {_OWNER};"
            f"REVOKE ALL ON FUNCTION {full_name} FROM PUBLIC,{_APP};"
            f"GRANT EXECUTE ON FUNCTION {full_name} TO {_APP};"
        )
        if re.sub(r"\s+", "", match["acl"]) != re.sub(r"\s+", "", expected_acl):
            raise ValueError("毎球CSV関数owner/ACLが不一致")
        identifier = f"FUNCTION:stats_api:{name}({identity})"
        row = {
            "function_id": identifier,
            "schema_name": "stats_api",
            "function_name": name,
            "identity_args": identity,
            "function_kind": "definer",
            "owner_role_id": _OWNER,
            "language": "plpgsql",
            "returns": returns,
            "security_mode": "definer",
            "volatility": volatility,
            "search_path": ["pg_catalog", "pg_temp"],
            "acl_expectations": [
                {"grantee": _APP, "privilege": "EXECUTE", "grantable": False}
            ],
            "revoked_acl_expectations": [
                {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
            ],
        }
        values[name] = (row, match[0], match["body"])
        cursor = match.end()
    if sql[cursor:].strip() or not values:
        raise ValueError("毎球CSV関数bundleが部分/余剰")
    return values


def connection_declarations() -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """既4関数/19列ACL/2policyだけを、既role不変更で供給する。"""
    source = _source()
    source_structure()
    declarations: dict[str, list[dict[str, Any]]] = {key: [] for key in _IDS}
    bodies = {}
    declarations["tables"].append(
        {
            "table_id": _TABLE,
            "schema_name": "public",
            "enable_row_level_security": True,
            "force_row_level_security": True,
        }
    )
    table_tail = re.search(
        r"ALTER TABLE public\.play_export_snapshots ENABLE[\s\S]*?"
        r"REVOKE ALL ON TABLE[^;]+;\n",
        source,
    )
    if table_tail is None:
        raise ValueError("毎球CSVのRLS/REVOKE原典がない")
    bodies["table|" + _TABLE] = table_tail[0]
    grants = re.findall(
        r"GRANT (SELECT|INSERT) \(([^)]+)\) ON public\."
        r"play_export_snapshots TO (\w+);",
        source,
    )
    if [
        (p, tuple(c.strip() for c in cols.split(",")), role) for p, cols, role in grants
    ] != [("SELECT", _COLUMNS, _APP), ("INSERT", _COLUMNS[:-1], _OWNER)]:
        raise ValueError("毎球CSVのSELECT10列/INSERT9列が不一致")
    for privilege, columns, role in grants:
        for column in (v.strip() for v in columns.split(",")):
            identifier = f"COLUMN-ACL:public:{_TABLE}:{column}:{role}"
            declarations["column_acl_expectations"].append(
                {
                    "expectation_id": identifier,
                    "object_kind": "column",
                    "object_schema": "public",
                    "object_id": _TABLE,
                    "column_id": column,
                    "grantee_role_id": role,
                    "privilege_ids": [privilege],
                    "grant_option": False,
                }
            )
            bodies["column_acl_expectation|" + identifier] = (
                f"GRANT {privilege} ({column}) ON public.{_TABLE} TO {role};\n"
            )
    policy_pattern = re.compile(
        r"CREATE POLICY (\w+) ON public\.play_export_snapshots\s+"
        r"FOR (SELECT|INSERT) TO (\w+)\s+(USING|WITH CHECK) \(([\s\S]*?)\n  \);"
    )
    policies = list(policy_pattern.finditer(source))
    if [(m[1], m[2], m[3], m[4]) for m in policies] != [
        ("play_export_snapshots_select", "SELECT", _APP, "USING"),
        ("play_export_snapshots_insert", "INSERT", _OWNER, "WITH CHECK"),
    ]:
        raise ValueError("毎球CSVのpolicy集合が不一致")
    for match in policies:
        name, command, role, _, expression = match.groups()
        identifier = f"POLICY:{_TABLE}:{name}"
        declarations["policies"].append(
            {
                "policy_id": identifier,
                "table_id": _TABLE,
                "profile": "function_only",
                "policy_name": name,
                "command": command,
                "policy_mode": "permissive",
                "role_ids": [role],
                "using_predicate_id": None,
                "using_column": None,
                "using_expression": " ".join(expression.split())
                if command == "SELECT"
                else None,
                "with_check_predicate_id": None,
                "with_check_column": None,
                "with_check_expression": " ".join(expression.split())
                if command == "INSERT"
                else None,
            }
        )
        bodies["policy|" + identifier] = match[0] + "\n"
    writer_values = _function_bundle(writer.candidate_install_sql())
    if set(writer_values) != {
        "read_writer_play_export_aggregate",
        "save_writer_play_export_snapshot",
    }:
        raise ValueError("毎球CSV writer関数集合が不一致")
    if (
        writer_values["read_writer_play_export_aggregate"][2]
        != writer.candidate_function_body()
        or writer_values["save_writer_play_export_snapshot"][2]
        != writer.candidate_save_body()
    ):
        raise ValueError("毎球CSV writer本文の唯一源が不一致")
    tail = source[
        source.index("CREATE FUNCTION stats_api.read_writer_play_export_substitute(") :
    ]
    substitute_values = _function_bundle(tail)
    read_values = _function_bundle(source_read.candidate_read_bundle()[1])
    if set(substitute_values) != {"read_writer_play_export_substitute"} or set(
        read_values
    ) != {"read_play_export_source_page"}:
        raise ValueError("毎球CSVの個別関数源が部分/余剰")
    values = writer_values | substitute_values | read_values
    if set(values) != set(_FUNCTIONS):
        raise ValueError("毎球CSVの4関数集合が不一致")
    for name in _FUNCTIONS:
        row, sql, _ = values[name]
        declarations["functions"].append(row)
        bodies["function|" + row["function_id"]] = sql
    return copy.deepcopy(declarations), dict(bodies)


def _exact(left: Any, right: Any) -> bool:
    """bool/intの同値化を含めず、宣言の全型/全値を比較する。"""
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


def validate(asset: dict[str, Any], bodies: dict[str, str]) -> bool:
    """全体資産内の当該閉集合だけを照合し、正式受理そのものは行わない。"""
    if type(asset) is not dict or type(bodies) is not dict:
        raise ValueError("毎球CSV宣言/本文の型が不正")
    selected_rows = {}
    for section, id_field in _IDS.items():
        rows = asset.get(section)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("毎球CSV宣言の配列が不正")
        selected_rows[section] = [
            row
            for row in rows
            if any(
                "play_export" in str(row.get(key, ""))
                for key in (id_field, "table_id", "object_id", "function_name")
            )
        ]
    if any(type(key) is not str for key in bodies):
        raise ValueError("毎球CSV本文keyの型が不正")
    selected = {key: value for key, value in bodies.items() if "play_export" in key}
    if not selected and not any(selected_rows.values()):
        return False
    expected, expected_bodies = connection_declarations()
    for section, chosen in selected_rows.items():
        if len(chosen) != len(expected[section]) or any(
            sum(_exact(row, target) for row in chosen) != 1
            for target in expected[section]
        ):
            raise ValueError("毎球CSV宣言の部分/余剰/全field不一致: " + section)
    if not _exact(selected, expected_bodies):
        raise ValueError("毎球CSV本文の部分/余剰/全byte不一致")
    return True
