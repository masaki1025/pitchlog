"""チーム名正規化関数の実カタログ属性と安全条件を検査する。"""

from __future__ import annotations

from typing import Any, LiteralString, cast

import psycopg
import pytest
from psycopg import sql

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_FUNCTION = "public.authn_normalize_team_name(text)"
_ALLOWED_CALLS = frozenset(
    {("pg_catalog", "lower"), ("pg_catalog", "btrim"), ("pg_catalog", '"normalize"')}
)
_ALLOWED_OPERATORS = frozenset({"collate"})


def _sql_tokens(source: str) -> tuple[tuple[str, str], ...] | None:
    """単一 SELECT の SQL を全字消費して字句へ分け、不明な構文を拒否する。"""
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(source):
        character = source[index]
        if character.isspace():
            index += 1
            continue
        if source[index : index + 3].lower() == "u&'":
            kind, delimiter = "unicode_string", "'"
            index += 3
        elif character in {"'", '"'}:
            kind = "string" if character == "'" else "quoted_name"
            delimiter = character
            index += 1
        else:
            kind = ""
            delimiter = ""
        if kind:
            start = index
            while index < len(source):
                if source[index] != delimiter:
                    index += 1
                    continue
                if source[index : index + 2] == delimiter * 2:
                    index += 2
                    continue
                break
            if index == len(source):
                return None
            value = source[start:index]
            tokens.append((kind, "*" if kind == "unicode_string" else value))
            index += 1
            continue
        if character == "$":
            index += 1
            start = index
            while index < len(source) and source[index].isdigit():
                index += 1
            if start == index:
                return None
            tokens.append(("parameter", source[start:index]))
            continue
        if character.isascii() and (character.isalpha() or character == "_"):
            start = index
            index += 1
            while (
                index < len(source)
                and source[index].isascii()
                and (source[index].isalnum() or source[index] == "_")
            ):
                index += 1
            tokens.append(("word", source[start:index].lower()))
            continue
        if character in "().,;:+-*/|=<>":
            tokens.append(("punct", character))
            index += 1
            continue
        return None
    return tuple(tokens)


def _normalizer_body_is_safe(source: str) -> bool:
    """許可した組み込み呼出しと COLLATE だけの式を構文全体で照合する。"""
    tokens = _sql_tokens(source)
    if tokens is None:
        return False
    if tokens and tokens[-1] == ("punct", ";"):
        tokens = tokens[:-1]
    calls: list[tuple[str, str]] = []
    for index, token in enumerate(tokens):
        if token != ("punct", "("):
            continue
        if index < 3 or tokens[index - 2] != ("punct", "."):
            return False
        schema, name = tokens[index - 3], tokens[index - 1]
        if schema[0] != "word" or name[0] not in {"word", "quoted_name"}:
            return False
        calls.append((schema[1], name[1] if name[0] == "word" else f'"{name[1]}"'))
    if set(calls) != _ALLOWED_CALLS or len(calls) != len(_ALLOWED_CALLS):
        return False
    if {value for kind, value in tokens if kind == "word" and value == "collate"} != (
        _ALLOWED_OPERATORS
    ):
        return False
    expected = (
        ("word", "select"),
        ("word", "pg_catalog"),
        ("punct", "."),
        ("word", "lower"),
        ("punct", "("),
        ("word", "pg_catalog"),
        ("punct", "."),
        ("word", "btrim"),
        ("punct", "("),
        ("word", "pg_catalog"),
        ("punct", "."),
        ("quoted_name", "normalize"),
        ("punct", "("),
        ("parameter", "1"),
        ("punct", ","),
        ("string", "NFKC"),
        ("punct", ")"),
        ("punct", ","),
        ("unicode_string", "*"),
        ("punct", ")"),
        ("word", "collate"),
        ("word", "pg_catalog"),
        ("punct", "."),
        ("word", "pg_c_utf8"),
        ("punct", ")"),
    )
    return tokens == expected


def _normalizer_catalog_violations(connection: psycopg.Connection[Any]) -> list[str]:
    """関数の宣言属性と本体を実カタログから照合する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT namespace.nspname, owner.rolname, routine.prosecdef,
                   routine.provolatile, routine.proisstrict,
                   routine.proparallel, routine.proconfig, routine.prosrc
            FROM pg_catalog.pg_proc AS routine
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = routine.pronamespace
            JOIN pg_catalog.pg_roles AS owner
              ON owner.oid = routine.proowner
            WHERE routine.oid = %s::pg_catalog.regprocedure
            """,
            (_FUNCTION,),
        )
        row = cursor.fetchone()
    if row is None:
        return ["function_absent"]
    schema, owner, security_definer, volatility, strict, parallel, config, source = row
    violations: list[str] = []
    if schema != "public":
        violations.append("schema")
    if owner != "pitchlog_owner":
        violations.append("owner")
    if security_definer is not False:
        violations.append("security_invoker")
    if volatility != "i" or strict is not True or parallel != "s":
        violations.append("immutable_strict_parallel_safe")
    if config != ["search_path=pg_catalog, pg_temp"]:
        violations.append("search_path")
    if not isinstance(source, str):
        violations.append("body")
        return violations
    if not _normalizer_body_is_safe(source):
        violations.append("body")
    return violations


def test_normalizer_catalog_has_pure_invoker_shape(
    provisioned_product_catalog: ProvisionedProductCatalog,
) -> None:
    """Migration の正規化関数を所有者・属性・本体まで照合する。"""
    catalog = provisioned_product_catalog
    try:
        assert _normalizer_catalog_violations(catalog.observer) == []
    finally:
        catalog.observer.rollback()


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("security_definer", "security_invoker"),
        ("table_reference", "body"),
        ("other_schema_call", "body"),
        ("unqualified_call", "body"),
        ("owner", "owner"),
        ("search_path", "search_path"),
    ),
)
def test_normalizer_catalog_mutations_are_rejected(
    provisioned_product_catalog: ProvisionedProductCatalog,
    mutation: str,
    expected: str,
) -> None:
    """属性・表参照・許可外の関数呼出し・探索経路の各変異を検出する。"""
    catalog = provisioned_product_catalog
    statements = {
        "security_definer": f"ALTER FUNCTION {_FUNCTION} SECURITY DEFINER",
        "table_reference": f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION} RETURNS text
            LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SECURITY INVOKER
            SET search_path = pg_catalog, pg_temp
            AS $body$ SELECT name FROM public.tenants LIMIT 1 $body$
        """,
        "owner": f"ALTER FUNCTION {_FUNCTION} OWNER TO pitchlog_app",
        "search_path": f"ALTER FUNCTION {_FUNCTION} RESET search_path",
    }
    catalog.observer.rollback()
    if mutation in {"other_schema_call", "unqualified_call"}:
        with catalog.observer.cursor() as cursor:
            cursor.execute(
                "SELECT prosrc FROM pg_catalog.pg_proc "
                "WHERE oid = %s::pg_catalog.regprocedure",
                (_FUNCTION,),
            )
            row = cursor.fetchone()
        catalog.observer.rollback()
        assert row is not None and isinstance(row[0], str)
        extra = (
            "public.unapproved_helper($1)"
            if mutation == "other_schema_call"
            else "upper($1)"
        )
        altered_body = row[0].strip().removesuffix(";") + " || " + extra
    with catalog.applicator.cursor() as cursor:
        if mutation == "other_schema_call":
            cursor.execute(
                "CREATE FUNCTION public.unapproved_helper(text) RETURNS text "
                "LANGUAGE sql IMMUTABLE STRICT AS $$ SELECT $1 $$"
            )
        if mutation in {"other_schema_call", "unqualified_call"}:
            cursor.execute(
                sql.SQL(
                    "CREATE OR REPLACE FUNCTION public.authn_normalize_team_name(text) "
                    "RETURNS text LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE "
                    "SECURITY INVOKER SET search_path = pg_catalog, pg_temp "
                    "AS {}"
                ).format(sql.Literal(altered_body))
            )
        else:
            cursor.execute(sql.SQL(cast(LiteralString, statements[mutation])))
    catalog.applicator.commit()
    try:
        assert expected in _normalizer_catalog_violations(catalog.observer)
    finally:
        catalog.observer.rollback()
