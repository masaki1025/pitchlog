"""0042 migration唯一原本から内部guardとtrigger全値を取得する。"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, LiteralString

FUNCTION_ID = "FUNCTION:public:protect_nonplay_admission()"
_FUNCTION = "public.protect_nonplay_admission()"
_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "migrations/versions/0042_nonplay_write_admission.py"
)


def _migration_statements() -> tuple[str, ...]:
    """upgrade内のliteralだけを読む。Python/migration自体は実行しない。"""
    tree = ast.parse(_MIGRATION.read_text(encoding="utf-8"))
    upgrades = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    ]
    if len(upgrades) != 1:
        raise ValueError("0042 upgradeが一意でない")
    statements = []
    for node in upgrades[0].body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and type(node.value.value) is str
        ):
            continue  # docstringだけは実行文でない。
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            raise ValueError("0042 upgradeに未知の実行形")
        call = node.value
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "op"
            and call.func.attr == "execute"
            and len(call.args) == 1
            and not call.keywords
            and isinstance(call.args[0], ast.Constant)
            and type(call.args[0].value) is str
        ):
            raise ValueError("0042 SQLが単一literalでない")
        statements.append(call.args[0].value)
    return tuple(statements)


def guard_details() -> tuple[object, ...]:
    """関数本体を唯一AST原本へ束縛し、owner/ACL/trigger配置も確認する。"""
    statements = _migration_statements()
    candidates = [
        s
        for s in statements
        if re.search(
            r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+public\.protect_nonplay_admission\b",
            s,
            re.I,
        )
    ]
    if len(candidates) != 1:
        raise ValueError("0042 guard定義が一意でない")
    match = re.fullmatch(
        r"\s*CREATE FUNCTION public\.protect_nonplay_admission\(\)\s+"
        r"RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS\s*"
        r"\$guard\$(.*?)\$guard\$;\s*",
        candidates[0],
        re.S,
    )
    if match is None:
        raise ValueError("0042 guardの呼出属性が不一致")
    related = [
        " ".join(s.split()).rstrip(";")
        for s in statements
        if "protect_nonplay_admission" in s and s != candidates[0]
    ]
    if related != [
        "ALTER FUNCTION public.protect_nonplay_admission() OWNER TO pitchlog_owner",
        (
            "REVOKE ALL ON FUNCTION public.protect_nonplay_admissio"
            "n() FROM PUBLIC,pitchlog_app"
        ),
        (
            "CREATE TRIGGER trg_nonplay_admission_guard BEFORE INSE"
            "RT OR UPDATE OR DELETE ON sync_fence.nonplay_write_adm"
            "issions FOR EACH ROW EXECUTE FUNCTION public.protect_n"
            "onplay_admission()"
        ),
        (
            "CREATE TRIGGER trg_nonplay_admission_no_truncate BEFOR"
            "E TRUNCATE ON sync_fence.nonplay_write_admissions FOR "
            "EACH STATEMENT EXECUTE FUNCTION public.protect_nonplay"
            "_admission()"
        ),
    ]:
        raise ValueError("0042 guardのowner/ACL/trigger原本が不一致")
    return (
        "public",
        "protect_nonplay_admission",
        "",
        "pitchlog_owner",
        False,
        "plpgsql",
        "trigger",
        "v",
        ("search_path=pg_catalog, pg_temp",),
        match[1].strip(),
    )


def declaration() -> dict[str, Any]:
    """migration所有のinvokerへapp/PUBLICの実行権を与えない。"""
    guard_details()
    return {
        "function_id": FUNCTION_ID,
        "schema_name": "public",
        "function_name": "protect_nonplay_admission",
        "identity_args": "",
        "function_kind": "migration_trigger",
        "owner_role_id": "pitchlog_owner",
        "acl_expectations": [],
        "revoked_acl_expectations": [
            {"grantee": role, "privilege": "EXECUTE", "grantable": False}
            for role in ("PUBLIC", "pitchlog_app")
        ],
    }


def acl_sql() -> str:
    """CREATEはmigrationだけが担い、publisherはACLだけを扱う。"""
    guard_details()
    return f"REVOKE EXECUTE ON FUNCTION {_FUNCTION} FROM PUBLIC, pitchlog_app;\n"


def trigger_expectations() -> tuple[tuple[object, ...], ...]:
    """表の非内部triggerは既migrationの2件に完全一致させる。"""
    guard_details()
    return tuple(
        (
            name,
            kind,
            "O",
            "public",
            "protect_nonplay_admission",
            "pitchlog_owner",
            False,
            [],
            False,
            False,
            True,
            True,
            0,
            "",
            None,
            None,
        )
        for name, kind in (
            ("trg_nonplay_admission_guard", 31),
            ("trg_nonplay_admission_no_truncate", 34),
        )
    )


def trigger_query() -> LiteralString:
    """全trigger属性を取得し、追加・削除も既正規比較へ渡す。"""
    from pitchlog.authz.first_ball_write_stamp import STAMP_TRIGGER_QUERY

    return STAMP_TRIGGER_QUERY.replace(
        "t.tgrelid='public.play_rows'::pg_catalog.regclass",
        "t.tgrelid='sync_fence.nonplay_write_admissions'::pg_catalog.regclass",
    ).replace("AND t.tgname<>'trg_play_prefix_30_project_after'", "")
