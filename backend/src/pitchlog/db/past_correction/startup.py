"""0048の過去訂正6原本を実catalogの全構造へ閉照合する。"""

from typing import Any

from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.db import current_product_startup as current
from pitchlog.db.past_correction.models import P3_STORAGE_MODELS
from pitchlog.db.play_export.startup import _default, _index_row


def _expected_index(index: Any) -> tuple[Any, ...]:
    """文字列列の既定collationも含め、索引の全属性を保持する。"""
    columns = list(index.columns)
    predicate = index.dialect_options["postgresql"]["where"]
    return current._index_shape(
        index.name,
        bool(index.unique),
        False,
        [column.name for column in columns],
        [
            "default"
            if column.type.compile(dialect=dialect()).lower() == "text"
            else None
            for column in columns
        ],
        None if predicate is None else str(predicate),
        opclasses=[current._opclass(column) for column in columns],
    )


def check_p3_storage(connection: Any) -> None:
    """表/owner/RLS/列/default/全制約/indexの不足・余剰・改変を拒否する。

    認可関数・ACL・guardの正式受理と全catalog検査は別に必要。
    この関数だけで製品起動や書込許可を発行しない。
    """
    tables = [model.__table__ for model in P3_STORAGE_MODELS]
    # 全モデルを読み込み、publicとsync_fenceの外部参照を同じ型元へ解決する。
    from pitchlog.db.all_models import IMPORTED_MODEL_MODULE_NAMES

    if not IMPORTED_MODEL_MODULE_NAMES:
        raise current.CurrentProductStartupError("P3参照モデルが未供給です")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname,r.rolname,c.relkind,c.relpersistence,"
            "c.relrowsecurity,c.relforcerowsecurity "
            "FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_catalog.pg_roles r ON r.oid=c.relowner "
            "WHERE n.nspname='sync_fence' AND c.relkind IN ('r','p') "
            "AND pg_catalog.starts_with(c.relname,'p3_projection_') "
            "ORDER BY c.relname"
        )
        expected_tables = sorted(
            (table.name, table.info["storage_owner"], "r", "p", True, True)
            for table in tables
        )
        if cursor.fetchall() != expected_tables:
            raise current.CurrentProductStartupError("P3全表/owner/RLSが不一致です")
        for table in tables:
            cursor.execute(
                "SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,"
                "a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) "
                "FROM pg_attribute a LEFT JOIN pg_attrdef d "
                "ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE a.attrelid=%s::regclass AND a.attnum>0 "
                "AND NOT a.attisdropped ORDER BY a.attnum",
                (table.fullname,),
            )
            actual_columns = [
                (*row[:5], current._expression(row[5])) for row in cursor.fetchall()
            ]
            expected_columns = [
                (
                    column.name,
                    column.type.compile(dialect=dialect()).lower(),
                    not column.nullable,
                    "",
                    "",
                    current._expression(_default(column.server_default)),
                )
                for column in table.c
            ]
            if actual_columns != expected_columns:
                raise current.CurrentProductStartupError(
                    "P3全列/型/defaultが不一致です"
                )
            cursor.execute(current._CONSTRAINT_SQL, (table.fullname,))
            actual_constraints = []
            for row in cursor.fetchall():
                kind, name, columns, remote, refs, delete, expression, *flags = row
                actual_constraints.append(
                    (
                        kind,
                        None if kind in {"p", "u"} else name,
                        tuple(columns) if kind != "c" else (),
                        remote,
                        tuple(refs),
                        delete,
                        current._expression(expression),
                        *flags,
                    )
                )
            if sorted(actual_constraints, key=repr) != current._expected_constraints(
                table
            ):
                raise current.CurrentProductStartupError("P3全制約が不一致です")
            cursor.execute(current._INDEX_SQL, (table.fullname,))
            actual_indexes = [_index_row(row) for row in cursor.fetchall()]
            expected_indexes = [_expected_index(index) for index in table.indexes]
            for constraint in table.constraints:
                if isinstance(constraint, (PrimaryKeyConstraint, UniqueConstraint)):
                    columns = list(constraint.columns)
                    expected_indexes.append(
                        current._index_shape(
                            None,
                            True,
                            isinstance(constraint, PrimaryKeyConstraint),
                            [column.name for column in columns],
                            [None for _ in columns],
                            None,
                            "p"
                            if isinstance(constraint, PrimaryKeyConstraint)
                            else "u",
                            opclasses=[current._opclass(column) for column in columns],
                        )
                    )
            if sorted(actual_indexes, key=repr) != sorted(expected_indexes, key=repr):
                raise current.CurrentProductStartupError(
                    f"P3全indexが不一致です: {table.name}"
                )

    check_p3_page_guard(connection)


def check_p3_page_guard(connection: Any) -> None:
    """遅延guard関数と全6表の非内部trigger集合を正確に照合する。"""
    from pitchlog.authz.p3_storage_guard import candidate_statements

    expected_source = candidate_statements()[0].split("$p3_page_guard$")[1].strip()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT r.rolname,l.lanname,p.prokind,p.provolatile,p.proparallel,"
            "p.prosecdef,p.proisstrict,p.proleakproof,p.proretset,p.pronargs,"
            "p.proconfig,pg_catalog.pg_get_function_result(p.oid),"
            "pg_catalog.btrim(p.prosrc,E' \\t\\r\\n'),"
            "(SELECT count(*) FROM pg_catalog.aclexplode(COALESCE("
            "p.proacl,pg_catalog.acldefault('f',p.proowner))) a "
            "WHERE a.grantee<>p.proowner) "
            "FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_roles r ON r.oid=p.proowner "
            "JOIN pg_catalog.pg_language l ON l.oid=p.prolang "
            "WHERE p.oid=pg_catalog.to_regprocedure("
            "'sync_fence.p3_reject_unfinished_page_progress()')"
        )
        if cursor.fetchall() != [
            (
                "pitchlog_owner",
                "plpgsql",
                "f",
                "v",
                "u",
                True,
                False,
                False,
                False,
                0,
                ["search_path=pg_catalog, pg_temp"],
                "trigger",
                expected_source,
                0,
            )
        ]:
            raise current.CurrentProductStartupError("P3未完了guard関数が不一致です")
        for model in P3_STORAGE_MODELS:
            table = model.__table__
            cursor.execute(
                "SELECT t.tgname,t.tgenabled,t.tgtype,t.tgdeferrable,"
                "t.tginitdeferred,t.tgnargs,t.tgargs,"
                "pg_catalog.pg_get_expr(t.tgqual,t.tgrelid),"
                "t.tgoldtable,t.tgnewtable,n.nspname,p.proname,"
                "k.contype,k.condeferrable,k.condeferred,k.convalidated "
                "FROM pg_catalog.pg_trigger t "
                "JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid "
                "JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace "
                "LEFT JOIN pg_catalog.pg_constraint k ON k.oid=t.tgconstraint "
                "WHERE t.tgrelid=%s::regclass AND NOT t.tgisinternal "
                "ORDER BY t.tgname",
                (table.fullname,),
            )
            expected = []
            if table.name == "p3_projection_page_progress":
                expected = [
                    (
                        "p3_page_progress_must_finalize",
                        "O",
                        21,
                        True,
                        True,
                        0,
                        b"",
                        None,
                        None,
                        None,
                        "sync_fence",
                        "p3_reject_unfinished_page_progress",
                        "t",
                        True,
                        True,
                        True,
                    )
                ]
            if cursor.fetchall() != expected:
                raise current.CurrentProductStartupError(
                    "P3未完了guardの全trigger属性が不一致です"
                )
