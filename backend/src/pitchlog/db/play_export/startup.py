"""毎球CSV原本の全構造と監査索引を通常起動で検査する。"""

from typing import Any

from sqlalchemy import DefaultClause, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.db import current_product_startup as current
from pitchlog.db.play_export.models import (
    PlayExportSnapshot,
    event_audit_index,
    play_audit_index,
    snapshot_game_index,
)


def _index_row(row: Any) -> tuple[Any, ...]:
    """既current索引署名へ、catalogの全列を情報を落とさず揃える。"""
    (
        name,
        unique,
        primary,
        valid,
        ready,
        live,
        immediate,
        method,
        columns,
        collations,
        options,
        expression,
        predicate,
        kind,
        opclasses,
        nulls_distinct,
    ) = row
    return (
        None if kind in {"p", "u"} else name,
        unique,
        primary,
        valid,
        ready,
        live,
        immediate,
        method,
        tuple(columns),
        tuple(collations),
        tuple(options),
        expression,
        current._expression(predicate),
        kind,
        tuple(opclasses),
        nulls_distinct,
    )


def _index_expected(index: Any) -> tuple[Any, ...]:
    columns = list(index.columns)
    return current._index_shape(
        index.name,
        bool(index.unique),
        False,
        [c.name for c in columns],
        [None for c in columns],
        None
        if index.dialect_options["postgresql"]["where"] is None
        else str(index.dialect_options["postgresql"]["where"]),
        opclasses=[current._opclass(c) for c in columns],
    )


def _default(value: Any) -> str | None:
    """モデルの明示defaultだけを受け付け、暗黙生成を無視しない。"""
    if value is None:
        return None
    if not isinstance(value, DefaultClause):
        raise current.CurrentProductStartupError("CSV原本のdefault宣言が不正です")
    return str(value.arg)


def check_play_export_storage(connection: Any) -> None:
    """10列/default/FK/CHECKと3索引の不足・余剰・改変を拒否する。"""
    table = PlayExportSnapshot.__table__
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT r.rolname,c.relkind,c.relpersistence,"
            "c.relrowsecurity,c.relforcerowsecurity "
            "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_roles r ON r.oid=c.relowner "
            "WHERE c.oid=pg_catalog.to_regclass('public.play_export_snapshots')"
        )
        if cursor.fetchall() != [("pitchlog_owner", "r", "p", True, True)]:
            raise current.CurrentProductStartupError("CSV原本表のowner/RLSが不一致です")
        cursor.execute(
            "SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,"
            "a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) "
            "FROM pg_attribute a LEFT JOIN pg_attrdef d "
            "ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
            "WHERE a.attrelid=%s::regclass AND a.attnum>0 "
            "AND NOT a.attisdropped ORDER BY a.attnum",
            (table.fullname,),
        )
        expected_columns = [
            (
                c.name,
                c.type.compile(dialect=dialect()).lower(),
                not c.nullable,
                "",
                "",
                _default(c.server_default),
            )
            for c in table.c
        ]
        if cursor.fetchall() != expected_columns:
            raise current.CurrentProductStartupError(
                "CSV原本表の全列/defaultが不一致です"
            )
        cursor.execute(current._CONSTRAINT_SQL, (table.fullname,))
        constraints = []
        for row in cursor.fetchall():
            kind, name, columns, remote, refs, delete, expression, *flags = row
            constraints.append(
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
        if sorted(constraints, key=repr) != current._expected_constraints(table):
            raise current.CurrentProductStartupError("CSV原本表の全制約が不一致です")
        cursor.execute(current._INDEX_SQL, (table.fullname,))
        actual_indexes = [_index_row(r) for r in cursor.fetchall()]
        primary = next(
            c for c in table.constraints if isinstance(c, PrimaryKeyConstraint)
        )
        expected_indexes = [
            _index_expected(snapshot_game_index),
            current._index_shape(
                None,
                True,
                True,
                [c.name for c in primary.columns],
                [None for c in primary.columns],
                None,
                "p",
                opclasses=[current._opclass(c) for c in primary.columns],
            ),
        ]
        if sorted(actual_indexes, key=repr) != sorted(expected_indexes, key=repr):
            raise current.CurrentProductStartupError("CSV原本表の全indexが不一致です")
        for index in (play_audit_index, event_audit_index):
            assert index.table is not None
            cursor.execute(current._INDEX_SQL, (index.table.fullname,))
            selected = [_index_row(r) for r in cursor.fetchall() if r[0] == index.name]
            if selected != [_index_expected(index)]:
                raise current.CurrentProductStartupError(
                    "CSV監査keyset索引が不一致です"
                )
