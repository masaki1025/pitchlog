"""Owned PGだけで製品認可の再適用と新9関数・4trigger衝突を検査する。"""

from __future__ import annotations

import re
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.pq import TransactionStatus

from pitchlog.authz.first_ball_product import ADDITIONS
from pitchlog.authz.product_catalog import (
    ProductCatalogReport,
    inspect_product_authz_catalog,
)
from pitchlog.authz.product_provisioning import apply_product_authz_ddl

from .sync_writer_binding_support import owned_binding_database

pytestmark = pytest.mark.requires_db

_NAMES = frozenset(
    {
        "read_writer_database_identity",
        "read_writer_identity",
        "publish_writer_binding",
        "assert_writer_binding",
        "close_writer_binding",
        "observe_writer_binding",
        "guard_writer_records",
        "bind_device",
        "check_current_right",
    }
)
_TRIGGERS = (
    ("writer_bindings", "sync_writer_binding_immutable", 27),
    ("writer_bindings", "sync_writer_binding_no_truncate", 34),
    ("writer_admissions", "sync_writer_admission_immutable", 27),
    ("writer_admissions", "sync_writer_admission_no_truncate", 34),
)


def _idle(connection: psycopg.Connection[Any]) -> None:
    """正式適用器へ未完transactionを渡さない。"""
    assert connection.info.transaction_status is TransactionStatus.IDLE
    assert connection.autocommit is False


def _report(
    observer: psycopg.Connection[Any], privileged_oid: int
) -> ProductCatalogReport:
    """公開検査と次の観測のtransactionを分離する。"""
    try:
        return inspect_product_authz_catalog(
            observer, privileged_role_oids=frozenset({privileged_oid})
        )
    finally:
        observer.rollback()


def _snapshot(
    observer: psycopg.Connection[Any], *, normalize_policy_oid: bool = False
) -> tuple[tuple[Any, ...], ...]:
    """所有DBの非system定義と権限を統計・時刻を除いて比較する。"""
    try:
        # 新schemaを含む全非system対象。既snapshotのpublic限定を継承しない。
        queries = (
            "SELECT rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,"
            "rolcanlogin,rolreplication,rolconnlimit,rolvaliduntil,rolbypassrls,"
            "rolconfig FROM pg_catalog.pg_roles ORDER BY rolname",
            "SELECT to_jsonb(m) FROM pg_catalog.pg_auth_members m "
            "ORDER BY roleid,member,grantor",
            "SELECT nspname,nspowner,nspacl FROM pg_catalog.pg_namespace "
            "WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema' "
            "ORDER BY nspname",
            "SELECT n.nspname,c.relname,c.oid,c.relkind,c.relowner,c.relacl,"
            "c.relrowsecurity,c.relforcerowsecurity,c.reloptions "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' "
            "AND n.nspname<>'information_schema' ORDER BY n.nspname,c.relname",
            (
                "SELECT n.nspname,c.relname,a.attnum,a.attname,"
                + (
                    "CASE WHEN a.attacl IS NULL THEN NULL ELSE "
                    "ARRAY(SELECT x FROM unnest(a.attacl) x ORDER BY x::text) END "
                    if normalize_policy_oid
                    else "a.attacl "
                )
                + "FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c "
                "ON c.oid=a.attrelid JOIN pg_catalog.pg_namespace n "
                "ON n.oid=c.relnamespace WHERE n.nspname NOT LIKE 'pg_%' "
                "AND n.nspname<>'information_schema' AND a.attnum>0 "
                "ORDER BY n.nspname,c.relname,a.attnum"
            ),
            "SELECT n.nspname,p.proname,p.oid,to_jsonb(p),"
            "pg_catalog.pg_get_functiondef(p.oid) FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema' "
            "AND p.prokind IN ('f','p') ORDER BY n.nspname,p.oid",
            "SELECT to_jsonb(t) FROM pg_catalog.pg_trigger t "
            "JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema' "
            "ORDER BY t.tgrelid,t.tgname",
            (
                "SELECT to_jsonb(p) - 'oid' FROM pg_catalog.pg_policy p "
                "ORDER BY polrelid,polname"
                if normalize_policy_oid
                else "SELECT to_jsonb(p) FROM pg_catalog.pg_policy p "
                "ORDER BY polrelid,polname"
            ),
            "SELECT to_jsonb(d) FROM pg_catalog.pg_default_acl d "
            "ORDER BY defaclrole,defaclnamespace,defaclobjtype",
            "SELECT datname,datdba,datacl FROM pg_catalog.pg_database "
            "WHERE datname=current_database()",
        )
        return tuple(tuple(observer.execute(query).fetchall()) for query in queries)
    finally:
        observer.rollback()


def _assert_triggers(observer: psycopg.Connection[Any]) -> None:
    """正常4構造を実観測する。公開catalogのtrigger検査とは呼ばない。"""
    try:
        rows = observer.execute(
            "SELECT c.relname,t.tgname,t.tgtype,t.tgenabled,t.tgisinternal,"
            "t.tgdeferrable,t.tginitdeferred,t.tgconstraint,t.tgnargs,"
            "t.tgattr::text,t.tgqual,t.tgargs,t.tgoldtable,t.tgnewtable,"
            "t.tgfoid='sync_fence_api.guard_writer_records()'::regprocedure "
            "FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c "
            "ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname='sync_fence' "
            "AND c.relname IN ('writer_bindings','writer_admissions') "
            "AND NOT t.tgisinternal ORDER BY c.relname,t.tgname"
        ).fetchall()
        expected = sorted(
            (
                table,
                name,
                kind,
                "O",
                False,
                False,
                False,
                0,
                0,
                "",
                None,
                b"",
                None,
                None,
                True,
            )
            for table, name, kind in _TRIGGERS
        )
        assert rows == expected
    finally:
        observer.rollback()


def _subject(applicator: psycopg.Connection[Any], expected: str) -> None:
    """成功・拒否後の外部適用主体を保持する。"""
    _idle(applicator)
    try:
        assert applicator.execute(
            "SELECT session_user::text,current_user::text"
        ).fetchone() == (
            expected,
            expected,
        )
    finally:
        applicator.rollback()


def test_owned_full_apply_repeats_and_rejects_nine_functions_four_triggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """単一所有clusterで正常1・本文9・無効化4を直列に実証する。"""
    functions = ADDITIONS["functions"]
    assert len(functions) == 9
    assert {row["function_name"] for row in functions} == _NAMES
    visited_functions: set[str] = set()
    visited_triggers: set[str] = set()
    with owned_binding_database(monkeypatch) as owner:
        # 外部供給fixture/共有DSNを受け取らず、生成直後の所有資源だけを使う。
        with (
            psycopg.connect(owner.authority.database.business_admin) as applicator,
            psycopg.connect(owner.authority.database.business_admin) as observer,
        ):
            identity = applicator.execute(
                "SELECT session_user::text,current_user::text,oid "
                "FROM pg_catalog.pg_roles WHERE rolname=session_user"
            ).fetchone()
            applicator.rollback()
            assert identity is not None and identity[0] == identity[1]
            subject, _, privileged_oid = identity
            first_report = _report(observer, privileged_oid)
            assert first_report.ok
            _assert_triggers(observer)
            # 正式applyはpolicyをDROP/CREATEする。正常再適用だけpolicy OIDを除く。
            first_snapshot = _snapshot(observer, normalize_policy_oid=True)
            # 初回はowned fixture内の正式apply。ここがその後の二度目。
            apply_product_authz_ddl(applicator)
            _subject(applicator, subject)
            assert _report(observer, privileged_oid) == first_report
            second_snapshot = _snapshot(observer, normalize_policy_oid=True)
            for index, (before, after) in enumerate(
                zip(first_snapshot, second_snapshot, strict=True)
            ):
                assert before == after, (
                    index,
                    [row for row in before if row not in after],
                    [row for row in after if row not in before],
                )
            # 故障対向では全policy OIDも含め、rollback前後を厳密比較する。
            pristine = _snapshot(observer)

            for row in functions:
                case = str(row["function_id"])
                identity_sql = (
                    f"{row['schema_name']}.{row['function_name']}"
                    f"({row['identity_args']})"
                )
                original_row = applicator.execute(
                    "SELECT pg_catalog.pg_get_functiondef("
                    "pg_catalog.to_regprocedure(%s))",
                    (identity_sql,),
                ).fetchone()
                applicator.rollback()
                assert original_row is not None and type(original_row[0]) is str
                original = original_row[0]
                markers = list(re.finditer(r"\bAS (\$[A-Za-z0-9_]*\$)", original))
                assert len(markers) == 1, case
                insertion = markers[0].end()
                mutated = (
                    original[:insertion]
                    + "\n-- owned catalog mutation probe\n"
                    + original[insertion:]
                )
                try:
                    applicator.execute(mutated.encode())
                    applicator.commit()
                    contaminated = _snapshot(observer)
                    assert contaminated != pristine, case
                    report = _report(observer, privileged_oid)
                    assert not report.ok, case
                    assert any(
                        v.check_id == "PRODUCT-CATALOG:LIFECYCLE-FUNCTION-DETAILS"
                        for v in report.violations
                    ), case
                    with pytest.raises(
                        psycopg.errors.RaiseException,
                        match="first ball function definition collision",
                    ) as error:
                        apply_product_authz_ddl(applicator)
                    assert error.value.sqlstate == "P0001", case
                    _subject(applicator, subject)
                    assert _snapshot(observer) == contaminated, case
                    visited_functions.add(case)
                finally:
                    applicator.rollback()
                    applicator.execute(original.encode())
                    applicator.commit()
                assert _snapshot(observer) == pristine, case
                assert _report(observer, privileged_oid).ok, case

            for table, name, _ in _TRIGGERS:
                case = f"sync_fence.{table}/{name}"
                target = sql.Identifier("sync_fence", table)
                trigger = sql.Identifier(name)
                try:
                    applicator.execute(
                        sql.SQL("ALTER TABLE {} DISABLE TRIGGER {}").format(
                            target, trigger
                        )
                    )
                    applicator.commit()
                    state = observer.execute(
                        "SELECT tgenabled FROM pg_catalog.pg_trigger "
                        "WHERE tgrelid=%s::regclass AND tgname=%s",
                        (f"sync_fence.{table}", name),
                    ).fetchall()
                    observer.rollback()
                    assert state == [("D",)], case
                    contaminated = _snapshot(observer)
                    assert contaminated != pristine, case
                    # 公開catalogにtrigger構造検出を仮定しない。
                    with pytest.raises(
                        psycopg.errors.RaiseException,
                        match="first ball trigger definition collision",
                    ) as error:
                        apply_product_authz_ddl(applicator)
                    assert error.value.sqlstate == "P0001", case
                    _subject(applicator, subject)
                    assert _snapshot(observer) == contaminated, case
                    visited_triggers.add(case)
                finally:
                    observer.rollback()
                    applicator.rollback()
                    applicator.execute(
                        sql.SQL("ALTER TABLE {} ENABLE TRIGGER {}").format(
                            target, trigger
                        )
                    )
                    applicator.commit()
                assert _snapshot(observer) == pristine, case
                _assert_triggers(observer)
                assert _report(observer, privileged_oid).ok, case
            assert visited_functions == {str(row["function_id"]) for row in functions}
            assert visited_triggers == {
                f"sync_fence.{table}/{name}" for table, name, _ in _TRIGGERS
            }
