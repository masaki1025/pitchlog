"""チーム名正規化関数の実カタログ属性と安全条件を検査する。"""

from __future__ import annotations

import re
from typing import Any, LiteralString, cast

import psycopg
import pytest
from psycopg import sql

from .conftest import ProvisionedProductCatalog

pytestmark = pytest.mark.requires_db

_FUNCTION = "public.authn_normalize_team_name(text)"


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
    catalog_calls = set(
        re.findall(
            r'pg_catalog\.((?:"normalize")|[a-z_][a-z_0-9]*)\s*\(',
            source,
            re.IGNORECASE,
        )
    )
    if (
        re.search(r"\b(FROM|JOIN|UPDATE|INSERT|DELETE)\b", source, re.IGNORECASE)
        or re.search(r"(?<!\.)\b[a-z_][a-z_0-9]*\s*\(", source, re.IGNORECASE)
        or catalog_calls != {"lower", "btrim", '"normalize"'}
        or any(
            token not in source
            for token in (
                "pg_catalog.lower(",
                "pg_catalog.btrim(",
                'pg_catalog."normalize"(',
                "COLLATE pg_catalog.pg_c_utf8",
                "'NFKC'",
                "U&'",
            )
        )
    ):
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
        ("owner", "owner"),
        ("search_path", "search_path"),
    ),
)
def test_normalizer_catalog_mutations_are_rejected(
    provisioned_product_catalog: ProvisionedProductCatalog,
    mutation: str,
    expected: str,
) -> None:
    """権限・表参照・所有者・探索経路の各変異を検出する。"""
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
    with catalog.applicator.cursor() as cursor:
        cursor.execute(sql.SQL(cast(LiteralString, statements[mutation])))
    catalog.applicator.commit()
    try:
        assert expected in _normalizer_catalog_violations(catalog.observer)
    finally:
        catalog.observer.rollback()
