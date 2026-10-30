"""所有disposableでepoch段階起動と新6role再適用を検査する。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from pitchlog.authz.product_role_contract import (
    expected_product_roles,
    generate_lifecycle_role_sql,
)
from pitchlog.db.stage_a_startup import StageAStartupError

from .conftest import DisposablePostgres
from .test_stage_a_rule_candidates import _fresh_schema_database

pytestmark = pytest.mark.requires_db


@pytest.fixture
def startup_database(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[str, str]]:
    """外部DSNへ接続せず、所有DBの実owner/adminだけを供給する。"""
    monkeypatch.delenv("PITCHLOG_TEST_ADMIN_DSN", raising=False)
    # factoryがhost/port/DBを所有containerへ置換し、下位fixtureが資格を置換する。
    monkeypatch.setenv(
        "PITCHLOG_TEST_ROLE_DSN", "dbname=unused user=unused password=unused"
    )
    with _fresh_schema_database(disposable_postgres_cluster, monkeypatch) as dsns:
        yield dsns


@pytest.fixture(autouse=True)
def verify_connection_identities(startup_database: tuple[str, str]) -> None:
    """共通外部DSN検査を所有DB両主体の実認証照合で置き換える。"""
    owner_dsn, admin_dsn = startup_database
    owner_name = conninfo_to_dict(owner_dsn)["user"]
    admin_name = conninfo_to_dict(admin_dsn)["user"]
    assert owner_name == "pitchlog_owner" and admin_name != owner_name
    for dsn, name in ((owner_dsn, owner_name), (admin_dsn, admin_name)):
        with psycopg.connect(dsn) as connection:
            assert connection.execute(
                "SELECT session_user, current_user"
            ).fetchone() == (name, name)


def test_formal_stage_a_epoch_failure_resumes_from_0034(
    startup_database: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0035適用前の故障は0034を保持し、同じ配置から35へ再開できる。"""
    from pitchlog.db import stage_a_startup as startup

    original_epoch = startup._apply_epoch
    owner_dsn, admin_dsn = startup_database

    def fail_epoch(_: str) -> None:
        raise RuntimeError("0035故障注入")

    monkeypatch.setattr(startup, "_apply_epoch", fail_epoch)
    with pytest.raises(RuntimeError, match="0035故障注入"):
        startup.advance_stage_a_from_s0(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
    with psycopg.connect(admin_dsn) as admin:
        assert admin.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchone() == ("0034_stage_a_rule_defaults",)
        assert admin.execute(
            "SELECT pg_catalog.to_regprocedure("
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
        ).fetchone() == (None,)
    monkeypatch.setattr(startup, "_apply_epoch", original_epoch)
    result = startup.resume_stage_a_after_placement(
        owner_dsn=owner_dsn, applicator_dsn=admin_dsn
    )
    assert result.completed_stage == "S3" and result.publishable is False
    repeated = startup.resume_stage_a_after_placement(
        owner_dsn=owner_dsn, applicator_dsn=admin_dsn
    )
    assert repeated.completed_stage == "S3" and repeated.publishable is False
    with psycopg.connect(admin_dsn) as admin:
        assert admin.execute(
            "SELECT version_num FROM public.alembic_version"
        ).fetchone() == ("0036_initial_right_storage",)


def test_formal_stage_a_resume_rejects_epoch_marker_without_column(
    startup_database: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0034配置後にrevisionだけを35へ偽装しても全認可を適用しない。"""
    from pitchlog.db import stage_a_startup as startup

    owner_dsn, admin_dsn = startup_database

    def fail_epoch(_: str) -> None:
        raise RuntimeError("0035故障注入")

    monkeypatch.setattr(startup, "_apply_epoch", fail_epoch)
    with pytest.raises(RuntimeError, match="0035故障注入"):
        startup.advance_stage_a_from_s0(owner_dsn=owner_dsn, applicator_dsn=admin_dsn)
    with psycopg.connect(admin_dsn) as admin:
        admin.execute(
            "UPDATE public.alembic_version SET version_num = "
            "'0035_rg1_initial_fresh_epoch'"
        )
    with pytest.raises(StageAStartupError, match="epoch実列"):
        startup.resume_stage_a_after_placement(
            owner_dsn=owner_dsn, applicator_dsn=admin_dsn
        )
    with psycopg.connect(admin_dsn) as admin:
        assert admin.execute(
            "SELECT pg_catalog.to_regprocedure("
            "'public.resolve_stage_a_rule(uuid,text,text,boolean)')"
        ).fetchone() == (None,)


_ROLE_ATTRIBUTES = (
    ("superuser", "rolsuper", "SUPERUSER", "NOSUPERUSER"),
    ("bypass_rls", "rolbypassrls", "BYPASSRLS", "NOBYPASSRLS"),
    ("login", "rolcanlogin", "LOGIN", "NOLOGIN"),
    ("create_role", "rolcreaterole", "CREATEROLE", "NOCREATEROLE"),
    ("create_db", "rolcreatedb", "CREATEDB", "NOCREATEDB"),
    ("replication", "rolreplication", "REPLICATION", "NOREPLICATION"),
    ("inherit", "rolinherit", "INHERIT", "NOINHERIT"),
)
_LIFECYCLE_ROLES = (
    "pitchlog_rg1_control_owner",
    "pitchlog_rg1_control_actor",
    "pitchlog_ledger_identity_owner",
    "pitchlog_ledger_identity_probe",
    "pitchlog_initial_actor",
    "pitchlog_initial_fn_owner",
)


def _role_snapshot(
    connection: psycopg.Connection[tuple[object, ...]], role: str
) -> tuple[object, object]:
    """全7属性と両向membershipを観測し、拒否が修復しないことを検査する。"""
    attributes = connection.execute(
        "SELECT rolsuper, rolbypassrls, rolcanlogin, rolcreaterole, rolcreatedb, "
        "rolreplication, rolinherit FROM pg_catalog.pg_roles WHERE rolname = %s",
        (role,),
    ).fetchone()
    membership = connection.execute(
        "SELECT roleid, member, admin_option FROM pg_catalog.pg_auth_members "
        "WHERE roleid = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s) "
        "OR member = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s) "
        "ORDER BY roleid, member",
        (role, role),
    ).fetchall()
    return attributes, membership


def test_lifecycle_six_roles_reapply_and_reject_all_existing_collisions(
    startup_database: tuple[str, str],
) -> None:
    """新6roleの再適用と7属性・両向membershipの全54衝突を実DBで拒否する。"""
    from typing import LiteralString, cast

    _, admin_dsn = startup_database
    expected = expected_product_roles({})
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute("CREATE ROLE lifecycle_collision_peer NOLOGIN")
        for role in _LIFECYCLE_ROLES:
            generated = sql.SQL(cast(LiteralString, generate_lifecycle_role_sql(role)))
            admin.execute(generated)
            pristine = _role_snapshot(admin, role)
            assert pristine == (
                tuple(expected[role][attribute] for attribute, *_ in _ROLE_ATTRIBUTES),
                [],
            )
            admin.execute(generated)
            assert _role_snapshot(admin, role) == pristine
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
            for mutation in (*range(7), "roleid", "member"):
                tokens = [
                    enabled if expected[role][attribute] else disabled
                    for attribute, _, enabled, disabled in _ROLE_ATTRIBUTES
                ]
                if isinstance(mutation, int):
                    attribute, _, enabled, disabled = _ROLE_ATTRIBUTES[mutation]
                    tokens[mutation] = (
                        disabled if expected[role][attribute] else enabled
                    )
                admin.execute(
                    sql.SQL("CREATE ROLE {} WITH {}").format(
                        sql.Identifier(role),
                        sql.SQL(cast(LiteralString, " ".join(tokens))),
                    )
                )
                if mutation == "roleid":
                    admin.execute(
                        sql.SQL("GRANT {} TO lifecycle_collision_peer").format(
                            sql.Identifier(role)
                        )
                    )
                elif mutation == "member":
                    admin.execute(
                        sql.SQL("GRANT lifecycle_collision_peer TO {}").format(
                            sql.Identifier(role)
                        )
                    )
                contaminated = _role_snapshot(admin, role)
                assert contaminated != pristine
                with pytest.raises(
                    psycopg.errors.RaiseException, match="role collision"
                ):
                    admin.execute(generated)
                assert _role_snapshot(admin, role) == contaminated
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        admin.execute("DROP ROLE lifecycle_collision_peer")


def test_two_lifecycle_schemas_reapply_and_reject_owner_collision(
    startup_database: tuple[str, str],
) -> None:
    """新schema2は同ownerなら再適用し、不正ownerを修復せず拒否する。"""
    from typing import LiteralString, cast

    from pitchlog.authz import product_provisioning
    from pitchlog.authz.asset_spec import PRODUCT_SPEC
    from pitchlog.authz.ddl import generate_authz_ddl

    _, admin_dsn = startup_database
    generated = generate_authz_ddl(product_provisioning._REPOSITORY_ROOT, PRODUCT_SPEC)
    elements = product_provisioning._load_product_elements()
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        for statement in generated:
            if statement.element_type == "role":
                admin.execute(sql.SQL(cast(LiteralString, statement.sql)))
        for statement in generated:
            if statement.element_type != "schema" or statement.element_id not in {
                "rg1_control",
                "pitchlog_ledger_observer",
            }:
                continue
            element = product_provisioning._element_for_statement(statement, elements)
            guarded = sql.SQL(
                cast(
                    LiteralString,
                    product_provisioning._strict_lifecycle_schema_sql(
                        element, statement.sql
                    ),
                )
            )
            for _ in range(2):
                admin.execute(guarded)
                assert admin.execute(
                    "SELECT pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace "
                    "WHERE nspname = %s",
                    (statement.element_id,),
                ).fetchone() == (element.fields["owner"],)
            admin.execute(
                sql.SQL("ALTER SCHEMA {} OWNER TO pitchlog_owner").format(
                    sql.Identifier(statement.element_id)
                )
            )
            with pytest.raises(
                psycopg.errors.RaiseException, match="schema owner collision"
            ):
                admin.execute(guarded)
            assert admin.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace "
                "WHERE nspname = %s",
                (statement.element_id,),
            ).fetchone() == ("pitchlog_owner",)
