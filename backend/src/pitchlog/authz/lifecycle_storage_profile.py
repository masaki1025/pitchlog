"""0043 migration原本から終了再開の内部guardとtriggerを閉じて導く。"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, LiteralString

_MIGRATION = (
    Path(__file__).resolve().parents[3] / "migrations/versions/0043_game_lifecycle.py"
)
_GUARDS = {
    "protect_lifecycle_write_admissions": "lifecycle_write_admissions",
    "protect_game_lifecycle_heads": "game_lifecycle_heads",
}


def _statements() -> tuple[str, ...]:
    """upgradeのop.executeに置いた定数SQLだけを読む。"""
    tree = ast.parse(_MIGRATION.read_text(encoding="utf-8"))
    funcs = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    ]
    if len(funcs) != 1:
        raise ValueError("0043 upgradeが一意でありません")
    result = []
    for node in ast.walk(funcs[0]):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
            and node.func.attr == "execute"
            and len(node.args) == 1
        ):
            continue
        try:
            sql = ast.literal_eval(node.args[0])
        except (ValueError, TypeError):
            continue
        if type(sql) is str:
            result.append(sql)
    return tuple(result)


def guard_details(name: str) -> tuple[object, ...]:
    """唯一CREATEとowner/ACL/表triggerをmigration実値に束縛する。"""
    if name not in _GUARDS:
        raise ValueError("未知の終了再開内部guardです")
    table = _GUARDS[name]
    statements = _statements()
    create = [
        s
        for s in statements
        if re.search(r"\bCREATE FUNCTION public\." + name + r"\(\)", s)
    ]
    if len(create) != 1:
        raise ValueError("0043 guard CREATEが一意でありません")
    match = re.fullmatch(
        r"\s*CREATE FUNCTION public\." + name + r"\(\) RETURNS trigger\s*"
        r"LANGUAGE plpgsql SET search_path=pg_catalog,pg_temp AS\s*"
        r"\$guard\$(.*?)\$guard\$;\s*",
        create[0],
        re.S,
    )
    if match is None:
        raise ValueError("0043 guard属性が不一致です")
    related = [
        " ".join(s.split()).rstrip(";")
        for s in statements
        if name in s and s != create[0]
    ]
    expected = [
        f"ALTER FUNCTION public.{name}() OWNER TO pitchlog_owner",
        f"REVOKE ALL ON FUNCTION public.{name}() FROM PUBLIC,pitchlog_app",
        f"CREATE TRIGGER trg_{table}_guard BEFORE INSERT OR UPDATE OR DELETE ON "
        f"sync_fence.{table} FOR EACH ROW EXECUTE FUNCTION public.{name}()",
        f"CREATE TRIGGER trg_{table}_no_truncate BEFORE TRUNCATE ON "
        f"sync_fence.{table} FOR EACH STATEMENT EXECUTE FUNCTION public.{name}()",
    ]
    if related != expected:
        raise ValueError("0043 guard owner/ACL/triggerが不一致です")
    return (
        "public",
        name,
        "",
        "pitchlog_owner",
        False,
        "plpgsql",
        "trigger",
        "v",
        ("search_path=pg_catalog, pg_temp",),
        match[1].strip(),
    )


def declarations() -> tuple[tuple[dict[str, Any], str], ...]:
    """migrationがCREATEする二関数へACL-only本文を与える。"""
    result = []
    for name in _GUARDS:
        guard_details(name)
        row = {
            "function_id": f"FUNCTION:public:{name}()",
            "schema_name": "public",
            "function_name": name,
            "identity_args": "",
            "function_kind": "migration_trigger",
            "owner_role_id": "pitchlog_owner",
            "acl_expectations": [],
            "revoked_acl_expectations": [
                {"grantee": r, "privilege": "EXECUTE", "grantable": False}
                for r in ("PUBLIC", "pitchlog_app")
            ],
        }
        result.append(
            (
                row,
                f"REVOKE EXECUTE ON FUNCTION public.{name}() "
                "FROM PUBLIC, pitchlog_app;\n",
            )
        )
    return tuple(result)


def trigger_expectations() -> tuple[tuple[object, ...], ...]:
    """0043の新2表の非内部trigger4件を固定する。"""
    result = []
    for name, table in _GUARDS.items():
        guard_details(name)
        for suffix, kind in (("guard", 31), ("no_truncate", 34)):
            result.append(
                (
                    f"trg_{table}_{suffix}",
                    kind,
                    "O",
                    "public",
                    name,
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
            )
    return tuple(sorted(result))


def trigger_query() -> LiteralString:
    """既trigger catalog queryの2表集合だけへ対象を広げる。"""
    from pitchlog.authz.nonplay_storage_profile import trigger_query as old_query

    sql = old_query()
    sql = sql.replace(
        "t.tgrelid='sync_fence.nonplay_write_admissions'::pg_catalog.regclass",
        "t.tgrelid IN ('sync_fence.lifecycle_write_admissions'::pg_catalog.regclass,"
        "'sync_fence.game_lifecycle_heads'::pg_catalog.regclass)",
    )
    return sql
