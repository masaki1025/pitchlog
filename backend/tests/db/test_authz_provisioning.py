"""認可 DDL 適用器の順序・原子性・冪等性を実 PostgreSQL で検証する。"""

from __future__ import annotations

import json
import re
import secrets
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, LiteralString, cast

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.pq import TransactionStatus

from pitchlog.authz import provisioning
from pitchlog.authz.ddl import DDLStatement, generate_authz_ddl

from .conftest import DisposablePostgres

pytestmark = pytest.mark.requires_db

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DDL_ELEMENTS_PATH = REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
PROVISIONING_PATH = REPOSITORY_ROOT / "backend/src/pitchlog/authz/provisioning.py"
_FUNCTION_ARGUMENTS_RE = re.compile(r"(?ms)^CREATE FUNCTION\b.*?\((.*?)\)\s*RETURNS")
_MEMBERSHIP_MODE_RE = re.compile(r"pg_has_role\([^)]*'([A-Z]+)'\)")
_SIMPLE_SQL_END_RE = re.compile(r"(?m);\s*$")


@dataclass(frozen=True)
class _IntermediateObservation:
    """別接続から見た関数の可視性と EXECUTE 権限を表す。"""

    catalog_visible: bool
    execute_privilege: bool
    execution_attempted: bool


def _read_asset() -> dict[str, object]:
    """DDL 要素資産を JSON object として読む。"""
    raw = json.loads(DDL_ELEMENTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _object_rows(asset: dict[str, object], key: str) -> list[dict[str, object]]:
    """資産の object 配列を型確認して返す。"""
    raw_rows = asset[key]
    assert isinstance(raw_rows, list)
    rows: list[dict[str, object]] = []
    for raw_row in raw_rows:
        assert isinstance(raw_row, dict)
        rows.append(raw_row)
    return rows


def _string(value: object) -> str:
    """資産値が文字列であることを確認する。"""
    assert isinstance(value, str)
    return value


def _function_argument_count(statement: DDLStatement) -> int:
    """関数 body の宣言部から呼び出し引数数を導出する。"""
    match = _FUNCTION_ARGUMENTS_RE.search(statement.sql)
    assert match is not None
    declarations = [part.strip() for part in match.group(1).split(",")]
    return len([declaration for declaration in declarations if declaration])


def _function_observer(
    dsn: str,
    asset: dict[str, object],
) -> tuple[
    Callable[[DDLStatement], None],
    list[_IntermediateObservation],
]:
    """関数作成中に別接続で可視性と PUBLIC 由来の実行可否を観測する。"""
    functions = {
        _string(row["function_id"]): row for row in _object_rows(asset, "functions")
    }
    observations: list[_IntermediateObservation] = []

    def observe(statement: DDLStatement) -> None:
        """別の管理接続から権限を照合し、呼び出しも実際に試みる。"""
        function = functions[statement.element_id]
        schema_id = _string(function["schema_id"])
        execute_role_ids = function["execute_role_ids"]
        assert isinstance(execute_role_ids, list)
        assert execute_role_ids
        caller_id = _string(execute_role_ids[0])
        with psycopg.connect(dsn, autocommit=True) as observer_connection:
            with observer_connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT routine.oid,
                           pg_catalog.has_function_privilege(
                               %s,
                               routine.oid,
                               'EXECUTE'
                           )
                    FROM pg_catalog.pg_proc AS routine
                    JOIN pg_catalog.pg_namespace AS namespace
                      ON namespace.oid = routine.pronamespace
                    WHERE namespace.nspname = %s
                      AND routine.proname = %s
                    ORDER BY routine.oid
                    """,
                    (caller_id, schema_id, statement.element_id),
                )
                privilege_rows = cursor.fetchall()
                catalog_visible = bool(privilege_rows)
                execute_privilege = bool(privilege_rows) and all(
                    bool(row[1]) for row in privilege_rows
                )
                cursor.execute(
                    sql.SQL("SET SESSION AUTHORIZATION {}").format(
                        sql.Identifier(caller_id)
                    )
                )
                null_arguments = sql.SQL(", ").join(
                    sql.SQL("NULL") for _ in range(_function_argument_count(statement))
                )
                try:
                    cursor.execute(
                        sql.SQL("SELECT * FROM {}.{}({})").format(
                            sql.Identifier(schema_id),
                            sql.Identifier(statement.element_id),
                            null_arguments,
                        )
                    )
                except psycopg.Error:
                    pass
        observations.append(
            _IntermediateObservation(
                catalog_visible=catalog_visible,
                execute_privilege=execute_privilege,
                execution_attempted=True,
            )
        )

    return observe, observations


def _assert_intermediate_is_closed(
    observations: list[_IntermediateObservation],
    expected_count: int,
) -> None:
    """全関数が中間状態で不可視かつ EXECUTE 不可能であることを要求する。"""
    assert len(observations) == expected_count
    assert all(observation.execution_attempted for observation in observations)
    assert all(not observation.catalog_visible for observation in observations)
    assert all(not observation.execute_privilege for observation in observations)


def _owner_role_ids(asset: dict[str, object]) -> tuple[str, ...]:
    """schema・table・function の所有ロールを資産順で導出する。"""
    owner_ids = {
        _string(row["owner_role_id"])
        for key in ("schemas", "tables", "functions")
        for row in _object_rows(asset, key)
    }
    return tuple(
        role_id
        for role in _object_rows(asset, "roles")
        if (role_id := _string(role["role_id"])) in owner_ids
    )


def _provisioner_id(asset: dict[str, object]) -> str:
    """資産から external provisioner を一意に導出する。"""
    provisioners = [
        row
        for row in _object_rows(asset, "roles")
        if row["role_kind"] == "external_provisioner"
    ]
    assert len(provisioners) == 1
    return _string(provisioners[0]["role_id"])


def _grant_external_database_create(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> None:
    """Ordered steps 外の外部前提として database CREATE を付与する。"""
    role_id = _provisioner_id(asset)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
        assert row is not None
        database_name = _string(row[0])
        cursor.execute(
            sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                sql.Identifier(database_name),
                sql.Identifier(role_id),
            )
        )
    connection.commit()


def _revoke_external_database_connect(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> None:
    """接続済み session から CONNECT 外部前提を負例用に除く。"""
    role_id = _provisioner_id(asset)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
        assert row is not None
        database_name = _string(row[0])
        cursor.execute(
            sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC, {}").format(
                sql.Identifier(database_name),
                sql.Identifier(role_id),
            )
        )
    connection.commit()


def _grant_external_database_connect(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> None:
    """Ordered steps 外の外部前提として database CONNECT を戻す。"""
    role_id = _provisioner_id(asset)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
        assert row is not None
        database_name = _string(row[0])
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database_name),
                sql.Identifier(role_id),
            )
        )
    connection.commit()


def _prepare_external_provisioner(
    connection: psycopg.Connection[Any],
    cluster: DisposablePostgres,
    asset: dict[str, object],
    *,
    grant_create: bool,
) -> str:
    """外部 provisioner を資産どおり作り、直接接続用 DSN を返す。"""
    role_id = _provisioner_id(asset)
    role_statements = [
        statement
        for statement in generate_authz_ddl(REPOSITORY_ROOT)
        if statement.element_type == "role" and statement.element_id == role_id
    ]
    assert len(role_statements) == 1
    password = secrets.token_urlsafe()
    with connection.cursor() as cursor:
        # ロールと database 権限は provisioning_claim.ordered_steps 外の外部前提。
        cursor.execute(role_statements[0].sql.encode("utf-8"))
        cursor.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(role_id),
                sql.Literal(password),
            )
        )
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
        assert row is not None
        database_name = _string(row[0])
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database_name),
                sql.Identifier(role_id),
            )
        )
    connection.commit()
    if grant_create:
        _grant_external_database_create(connection, asset)

    return make_conninfo(cluster.admin_dsn, user=role_id, password=password)


@contextmanager
def _provisioning_connections(
    cluster: DisposablePostgres,
    asset: dict[str, object],
    *,
    grant_create: bool = True,
) -> Iterator[tuple[psycopg.Connection[Any], psycopg.Connection[Any]]]:
    """外部前提を整え、管理接続と provisioner 実接続を供給する。"""
    with psycopg.connect(cluster.admin_dsn) as admin_connection:
        provisioner_dsn = _prepare_external_provisioner(
            admin_connection,
            cluster,
            asset,
            grant_create=grant_create,
        )
        with psycopg.connect(provisioner_dsn) as provisioner_connection:
            yield admin_connection, provisioner_connection


def _owner_membership_modes(asset: dict[str, object]) -> tuple[str, ...]:
    """完了時 catalog 期待値から pg_has_role の検査 mode を導出する。"""
    claim = asset["provisioning_claim"]
    assert isinstance(claim, dict)
    expectations = claim["completion_catalog_expectations"]
    assert isinstance(expectations, list)
    modes: list[str] = []
    for expectation in expectations:
        assert isinstance(expectation, dict)
        predicate = _string(expectation["inspection_predicate"])
        match = _MEMBERSHIP_MODE_RE.search(predicate)
        assert match is not None
        modes.append(match.group(1))
    assert modes
    return tuple(modes)


def _expected_checkpoint_elements(
    asset: dict[str, object], statements: tuple[DDLStatement, ...]
) -> list[tuple[str, str, str]]:
    """資産手順と body の文末から期待する checkpoint 列を独立に導出する。"""
    role_statements = {
        statement.element_id: statement
        for statement in statements
        if statement.element_type == "role"
    }
    owner_statements = [role_statements[role_id] for role_id in _owner_role_ids(asset)]
    provisioner_id = _provisioner_id(asset)

    by_operation: dict[str, list[DDLStatement]] = {
        provisioning._CREATE_OWNER: [],
        provisioning._OPEN_SET_PATH: owner_statements,
        provisioning._ASSIGN_OBJECTS: [],
        provisioning._CLOSE_FUNCTION_ACL: [],
        provisioning._CLOSE_SET_PATH: [
            statement for statement in owner_statements for _ in ("set", "inherit")
        ],
    }
    for statement in statements:
        if statement.element_type == "role":
            if statement.element_id == provisioner_id:
                continue
            by_operation[provisioning._CREATE_OWNER].extend(
                statement for _ in ("create", "normalize")
            )
        elif statement.element_type == "function":
            by_operation[provisioning._ASSIGN_OBJECTS].extend(
                statement for _ in ("body", "owner")
            )
            by_operation[provisioning._CLOSE_FUNCTION_ACL].append(statement)
        elif statement.element_type.endswith("acl_expectation"):
            by_operation[provisioning._CLOSE_FUNCTION_ACL].extend(
                statement for _ in _SIMPLE_SQL_END_RE.finditer(statement.sql)
            )
        else:
            if statement.element_type == "policy":
                by_operation[provisioning._ASSIGN_OBJECTS].append(statement)
            by_operation[provisioning._ASSIGN_OBJECTS].extend(
                statement for _ in _SIMPLE_SQL_END_RE.finditer(statement.sql)
            )
            if statement.element_type == "schema":
                by_operation[provisioning._ASSIGN_OBJECTS].append(statement)

    claim = asset["provisioning_claim"]
    assert isinstance(claim, dict)
    raw_steps = claim["ordered_steps"]
    assert isinstance(raw_steps, list)
    expected: list[tuple[str, str, str]] = []
    for raw_step in sorted(raw_steps, key=lambda item: item["sequence"]):
        assert isinstance(raw_step, dict)
        step_id = _string(raw_step["step_id"])
        operation_kind = _string(raw_step["operation_kind"])
        expected.extend(
            (step_id, statement.element_type, statement.element_id)
            for statement in by_operation[operation_kind]
        )
    return expected


def _assert_owner_memberships_closed(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> None:
    """Provisioner から全所有ロールへの到達が資産どおり閉じたことを要求する。"""
    provisioner_id = _provisioner_id(asset)
    with connection.cursor() as cursor:
        for owner_id in _owner_role_ids(asset):
            for mode in _owner_membership_modes(asset):
                cursor.execute(
                    "SELECT pg_catalog.pg_has_role(%s, %s, %s)",
                    (provisioner_id, owner_id, mode),
                )
                row = cursor.fetchone()
                assert row is not None
                assert row[0] is False


def _catalog_snapshot(
    connection: psycopg.Connection[Any], asset: dict[str, object]
) -> tuple[tuple[object, ...], ...]:
    """二回適用で比較する認可 object のカタログ状態を採取する。"""
    role_ids = [_string(row["role_id"]) for row in _object_rows(asset, "roles")]
    schema_ids = [_string(row["schema_id"]) for row in _object_rows(asset, "schemas")]
    table_ids = [_string(row["table_id"]) for row in _object_rows(asset, "tables")]
    function_ids = [
        _string(row["function_id"]) for row in _object_rows(asset, "functions")
    ]
    rows: list[tuple[object, ...]] = []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 'role', rolname, rolcanlogin, rolbypassrls,
                   rolcreaterole, rolinherit
            FROM pg_catalog.pg_roles
            WHERE rolname = ANY(%s)
            ORDER BY rolname
            """,
            (role_ids,),
        )
        rows.extend(tuple(row) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 'membership', granted.rolname, member.rolname,
                   membership.admin_option,
                   membership.inherit_option,
                   membership.set_option
            FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS granted
              ON granted.oid = membership.roleid
            JOIN pg_catalog.pg_roles AS member
              ON member.oid = membership.member
            WHERE granted.rolname = ANY(%s)
              AND member.rolname = %s
            ORDER BY granted.rolname, member.rolname,
                     membership.grantor
            """,
            (list(_owner_role_ids(asset)), _provisioner_id(asset)),
        )
        rows.extend(tuple(row) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 'schema', namespace.nspname,
                   pg_catalog.pg_get_userbyid(namespace.nspowner),
                   namespace.nspacl::text
            FROM pg_catalog.pg_namespace AS namespace
            WHERE namespace.nspname = ANY(%s)
            ORDER BY namespace.nspname
            """,
            (schema_ids,),
        )
        rows.extend(tuple(row) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 'table', relation.relname,
                   pg_catalog.pg_get_userbyid(relation.relowner),
                   relation.relrowsecurity, relation.relforcerowsecurity,
                   relation.relacl::text
            FROM pg_catalog.pg_class AS relation
            WHERE relation.relkind = 'r'
              AND relation.relname = ANY(%s)
            ORDER BY relation.relname
            """,
            (table_ids,),
        )
        rows.extend(tuple(row) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 'policy', policy.polname, relation.relname,
                   policy.polpermissive, policy.polcmd,
                   pg_catalog.pg_get_expr(policy.polqual, policy.polrelid),
                   pg_catalog.pg_get_expr(policy.polwithcheck, policy.polrelid)
            FROM pg_catalog.pg_policy AS policy
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = policy.polrelid
            WHERE relation.relname = ANY(%s)
            ORDER BY relation.relname, policy.polname
            """,
            (table_ids,),
        )
        rows.extend(tuple(row) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 'function', routine.proname,
                   pg_catalog.pg_get_userbyid(routine.proowner),
                   routine.prosecdef, routine.proconfig, routine.proacl::text,
                   pg_catalog.pg_get_function_identity_arguments(routine.oid),
                   pg_catalog.pg_get_function_result(routine.oid),
                   routine.prosrc
            FROM pg_catalog.pg_proc AS routine
            WHERE routine.proname = ANY(%s)
            ORDER BY routine.proname,
                     pg_catalog.pg_get_function_identity_arguments(routine.oid)
            """,
            (function_ids,),
        )
        rows.extend(tuple(row) for row in cursor.fetchall())
        cursor.execute(
            """
            SELECT 'column', relation.relname, attribute.attname,
                   attribute.attacl::text
            FROM pg_catalog.pg_attribute AS attribute
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = attribute.attrelid
            WHERE relation.relname = ANY(%s)
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
            ORDER BY relation.relname, attribute.attnum
            """,
            (table_ids,),
        )
        rows.extend(tuple(row) for row in cursor.fetchall())
    connection.commit()
    return tuple(rows)


def _old_table_grant_target(
    asset: dict[str, object],
) -> tuple[str, str, str, str]:
    """ACL 期待値に無い表権限を資産から 1 組導出する。"""
    enums = asset["enums"]
    assert isinstance(enums, dict)
    all_privileges = enums["table_privilege_ids"]
    assert isinstance(all_privileges, list)
    tables = {_string(row["table_id"]): row for row in _object_rows(asset, "tables")}
    for acl in _object_rows(asset, "acl_expectations"):
        if acl["object_kind"] != "table":
            continue
        expected_privileges = acl["privilege_ids"]
        assert isinstance(expected_privileges, list)
        missing = [
            _string(privilege)
            for privilege in all_privileges
            if privilege not in expected_privileges
        ]
        if not missing:
            continue
        table_id = _string(acl["object_id"])
        table = tables[table_id]
        return (
            _string(acl["grantee_role_id"]),
            _string(table["schema_id"]),
            table_id,
            missing[0],
        )
    raise AssertionError("古い直接GRANTの負例対象を資産から導出できない")


def _grant_table_privilege(
    connection: psycopg.Connection[Any],
    target: tuple[str, str, str, str],
) -> None:
    """負例用の古い直接表 GRANT を注入する。"""
    role_id, schema_id, table_id, privilege = target
    assert privilege.isalpha() and privilege.isupper()
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("GRANT {} ON TABLE {}.{} TO {}").format(
                sql.SQL(cast(LiteralString, privilege)),
                sql.Identifier(schema_id),
                sql.Identifier(table_id),
                sql.Identifier(role_id),
            )
        )
    connection.commit()


def _assert_table_privilege_absent(
    connection: psycopg.Connection[Any],
    target: tuple[str, str, str, str],
) -> None:
    """注入した直接表権限が存在しないことを要求する。"""
    role_id, schema_id, table_id, privilege = target
    qualified_name = sql.Identifier(schema_id, table_id).as_string(connection)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_catalog.has_table_privilege(%s, %s, %s)",
            (role_id, qualified_name, privilege),
        )
        row = cursor.fetchone()
    connection.commit()
    assert row is not None
    assert row[0] is False


def test_reapplication_converges_and_removes_old_direct_grants(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """空クラスタへの二回適用が収束し、古い GRANT も毎回除く。"""
    asset = _read_asset()
    target = _old_table_grant_target(asset)
    with disposable_postgres_cluster() as cluster:
        with _provisioning_connections(cluster, asset, grant_create=False) as (
            admin_connection,
            provisioner_connection,
        ):
            _revoke_external_database_connect(admin_connection, asset)
            with pytest.raises(provisioning.ProvisioningError) as error:
                provisioning.apply_authz_ddl(provisioner_connection, REPOSITORY_ROOT)
            message = str(error.value)
            assert "外部前提が満たされていない" in message
            assert "CREATE" in message
            assert "CONNECT" in message
            assert "不足: CREATE, CONNECT" in message

            # 不足していた外部前提を ordered_steps の呼び出し前に付与する。
            _grant_external_database_connect(admin_connection, asset)
            _grant_external_database_create(admin_connection, asset)
            first = provisioning.apply_authz_ddl(
                provisioner_connection, REPOSITORY_ROOT
            )
            first_snapshot = _catalog_snapshot(admin_connection, asset)

            second = provisioning.apply_authz_ddl(
                provisioner_connection, REPOSITORY_ROOT
            )
            second_snapshot = _catalog_snapshot(admin_connection, asset)
            assert first_snapshot == second_snapshot
            assert first.checkpoints == second.checkpoints

            _grant_table_privilege(admin_connection, target)
            normalized_once = provisioning.apply_authz_ddl(
                provisioner_connection, REPOSITORY_ROOT
            )
            _assert_table_privilege_absent(admin_connection, target)
            normalized_once_snapshot = _catalog_snapshot(admin_connection, asset)

            _grant_table_privilege(admin_connection, target)
            normalized_twice = provisioning.apply_authz_ddl(
                provisioner_connection, REPOSITORY_ROOT
            )
            _assert_table_privilege_absent(admin_connection, target)
            normalized_twice_snapshot = _catalog_snapshot(admin_connection, asset)

            assert first_snapshot == normalized_once_snapshot
            assert normalized_once_snapshot == normalized_twice_snapshot
            assert normalized_once.checkpoints == normalized_twice.checkpoints
            _assert_owner_memberships_closed(admin_connection, asset)


def test_asset_sequence_and_checkpoint_log_ignore_handler_mapping_order(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handler 定義順を逆転しても資産 sequence と checkpoint 連番を保つ。"""
    asset = _read_asset()
    original_handlers = provisioning._OPERATION_HANDLERS
    reversed_handlers = dict(reversed(tuple(original_handlers.items())))
    assert tuple(reversed_handlers) == tuple(reversed(tuple(original_handlers)))
    monkeypatch.setattr(provisioning, "_OPERATION_HANDLERS", reversed_handlers)

    with disposable_postgres_cluster() as cluster:
        with _provisioning_connections(cluster, asset) as (
            _admin_connection,
            provisioner_connection,
        ):
            result = provisioning.apply_authz_ddl(
                provisioner_connection, REPOSITORY_ROOT
            )

    claim = asset["provisioning_claim"]
    assert isinstance(claim, dict)
    raw_steps = claim["ordered_steps"]
    assert isinstance(raw_steps, list)
    expected_steps = [
        _string(step["step_id"])
        for step in sorted(raw_steps, key=lambda step: step["sequence"])
        if isinstance(step, dict)
    ]
    observed_steps = list(dict.fromkeys(item.step_id for item in result.checkpoints))
    assert observed_steps == expected_steps
    checkpoint_ids = [item.checkpoint_id for item in result.checkpoints]
    assert len(checkpoint_ids) == len(set(checkpoint_ids))
    statements = generate_authz_ddl(REPOSITORY_ROOT)
    valid_elements = {
        (statement.element_type, statement.element_id) for statement in statements
    }
    assert all(
        (checkpoint.element_type, checkpoint.element_id) in valid_elements
        for checkpoint in result.checkpoints
    )
    assert [
        (checkpoint.step_id, checkpoint.element_type, checkpoint.element_id)
        for checkpoint in result.checkpoints
    ] == _expected_checkpoint_elements(asset, statements)
    by_step: defaultdict[str, list[int]] = defaultdict(list)
    for checkpoint in result.checkpoints:
        assert checkpoint.checkpoint_id == (
            f"{checkpoint.step_id}#{checkpoint.ordinal}"
        )
        by_step[checkpoint.step_id].append(checkpoint.ordinal)
    for ordinals in by_step.values():
        assert ordinals == list(range(1, len(ordinals) + 1))
    forbidden_role_switch = "SET" + " ROLE"
    source = PROVISIONING_PATH.read_text(encoding="utf-8")
    assert forbidden_role_switch not in source
    assert "SET SESSION AUTHORIZATION" not in source


def test_function_creation_is_not_observable_before_acl_closure(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """関数作成後・REVOKE 前でも別接続には未commitとして見えない。"""
    asset = _read_asset()
    with disposable_postgres_cluster() as cluster:
        observe, observations = _function_observer(cluster.admin_dsn, asset)
        transaction_statuses: list[TransactionStatus] = []
        with _provisioning_connections(cluster, asset) as (
            _admin_connection,
            provisioner_connection,
        ):

            def observe_in_transaction(statement: DDLStatement) -> None:
                """主接続のtransaction状態を採取して別接続観測を実行する。"""
                transaction_statuses.append(
                    provisioner_connection.info.transaction_status
                )
                observe(statement)

            provisioning._apply_authz_ddl(
                provisioner_connection,
                REPOSITORY_ROOT,
                on_function_created=observe_in_transaction,
            )

    assert transaction_statuses
    assert all(status == TransactionStatus.INTRANS for status in transaction_statuses)
    _assert_intermediate_is_closed(
        observations,
        len(_object_rows(asset, "functions")),
    )


def test_split_function_transaction_mutant_is_red(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """関数作成を先にcommitする変異は中間 PUBLIC 実行を観測してredになる。"""
    asset = _read_asset()
    with disposable_postgres_cluster() as cluster:
        observe, observations = _function_observer(cluster.admin_dsn, asset)
        transaction_statuses: list[TransactionStatus] = []
        with _provisioning_connections(cluster, asset) as (
            _admin_connection,
            provisioner_connection,
        ):

            def observe_after_commit(statement: DDLStatement) -> None:
                """故障時の主接続状態を採取して別接続観測を実行する。"""
                transaction_statuses.append(
                    provisioner_connection.info.transaction_status
                )
                observe(statement)

            provisioning._apply_authz_ddl(
                provisioner_connection,
                REPOSITORY_ROOT,
                on_function_created=observe_after_commit,
                faults=provisioning._ProvisioningFaults(
                    split_function_transaction=True
                ),
            )

    assert transaction_statuses
    assert all(status == TransactionStatus.IDLE for status in transaction_statuses)
    assert all(observation.execution_attempted for observation in observations)
    assert all(observation.catalog_visible for observation in observations)
    assert all(observation.execute_privilege for observation in observations)
    with pytest.raises(AssertionError):
        _assert_intermediate_is_closed(
            observations,
            len(_object_rows(asset, "functions")),
        )


def test_deferred_set_membership_mutant_fails_application(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """手順2を手順3より後ろへ送る変異は所有 object の作成自体に失敗する。"""
    original_ordered_steps = provisioning._ordered_steps

    def move_open_after_assignment(
        asset: dict[str, object],
    ) -> tuple[provisioning._ProvisioningStep, ...]:
        """資産解釈後の手順2だけを手順3の直後へ移す。"""
        steps = list(original_ordered_steps(asset))
        open_step = next(
            step for step in steps if step.operation_kind == provisioning._OPEN_SET_PATH
        )
        steps.remove(open_step)
        assign_index = next(
            index
            for index, step in enumerate(steps)
            if step.operation_kind == provisioning._ASSIGN_OBJECTS
        )
        steps.insert(assign_index + 1, open_step)
        return tuple(steps)

    monkeypatch.setattr(provisioning, "_ordered_steps", move_open_after_assignment)
    asset = _read_asset()
    with disposable_postgres_cluster() as cluster:
        with _provisioning_connections(cluster, asset) as (
            _admin_connection,
            provisioner_connection,
        ):
            with pytest.raises(provisioning.ProvisioningError):
                provisioning.apply_authz_ddl(provisioner_connection, REPOSITORY_ROOT)


def test_omitted_membership_revoke_mutant_is_red(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """手順5のREVOKEを省く変異はprovisionerのSET到達が残ってredになる。"""
    asset = _read_asset()
    with disposable_postgres_cluster() as cluster:
        with _provisioning_connections(cluster, asset) as (
            admin_connection,
            provisioner_connection,
        ):
            provisioning._apply_authz_ddl(
                provisioner_connection,
                REPOSITORY_ROOT,
                faults=provisioning._ProvisioningFaults(skip_membership_revoke=True),
            )
            with pytest.raises(AssertionError):
                _assert_owner_memberships_closed(admin_connection, asset)


def test_skipped_acl_normalization_mutant_keeps_old_grant_and_is_red(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """ACL正規化を省く変異は古い直接GRANTを残してredになる。"""
    asset = _read_asset()
    target = _old_table_grant_target(asset)
    with disposable_postgres_cluster() as cluster:
        with _provisioning_connections(cluster, asset) as (
            admin_connection,
            provisioner_connection,
        ):
            provisioning.apply_authz_ddl(provisioner_connection, REPOSITORY_ROOT)
            _grant_table_privilege(admin_connection, target)
            provisioning._apply_authz_ddl(
                provisioner_connection,
                REPOSITORY_ROOT,
                faults=provisioning._ProvisioningFaults(skip_acl_normalization=True),
            )
            with pytest.raises(AssertionError):
                _assert_table_privilege_absent(admin_connection, target)
