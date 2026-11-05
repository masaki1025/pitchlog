"""0040のC照合代表現だけを整合し、他比較/実形状拒否を保持する。"""

from unittest.mock import patch

import pytest
from alembic.ddl.postgresql import PostgresqlImpl
from alembic.util import CommandError
from sqlalchemy import Column, Index, MetaData, Table, Text, column, text
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.db import alembic_index_comparison as target


def _indexes(name=target._INDEX, schema=None):
    """実metadataとreflectionの差だけを持つ独立な索引を作る。"""
    m = Table(
        target._TABLE,
        MetaData(),
        Column("key", Text),
        Index(
            name,
            column("key").collate("C"),
            postgresql_where=text(target._PREDICATE),
        ),
        schema=schema,
    )
    r = Table(
        target._TABLE,
        MetaData(),
        Column("key", Text),
        Index(
            name,
            "key",
            postgresql_where=text(next(iter(target._PG_PREDICATES))),
        ),
        schema=schema,
    )
    return next(iter(m.indexes)), next(iter(r.indexes))


def _valid_row():
    """0040 migration/旧schemaauditから独立に凍結したcatalog形状。"""
    return (
        "public",
        "admin_vocabularies",
        "ix_admin_vocabularies_batted_ball_key_c",
        "btree",
        "pitchlog_owner",
        "pitchlog_owner",
        False,
        False,
        True,
        True,
        True,
        True,
        False,
        1,
        1,
        ["key"],
        ["pg_catalog.C"],
        [0],
        None,
        "((category = 'batted_ball'::text) AND (disabled = false))",
        ["pg_catalog.text_ops"],
        "i",
        "r",
    )


class _Result:
    def __init__(self, rows):
        self.rows, self.closed = rows, False

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class _Connection:
    def __init__(self, rows):
        self.result, self.queries = _Result(rows), []

    def execute(self, statement):
        self.queries.append(statement)
        return self.result


def _impl(connection, *, offline=False):
    return target.PitchlogPostgresqlImpl(dialect(), connection, offline, None, None, {})


def test_exact_c_catalog_restores_only_reflection_then_normal_comparison():
    """比較結果やoperationを消さず、標準compareの式不一致だけを解消する。"""
    m, r = _indexes()
    connection = _Connection([_valid_row()])
    impl = _impl(connection)
    assert connection.queries == []
    assert PostgresqlImpl.compare_indexes(impl, m, r).status == "different"
    members = {r}
    with patch.object(
        PostgresqlImpl, "correct_for_autogen_constraints", autospec=True
    ) as old:
        impl.correct_for_autogen_constraints(set(), members, set(), {m})
        old.assert_called_once()
    assert members == {r}
    assert len(connection.queries) == 1 and connection.result.closed
    assert PostgresqlImpl.compare_indexes(impl, m, r).status == "equal"
    assert impl.compare_indexes(m, r).status == "equal"


@pytest.mark.parametrize(
    "schema,name", [("elsewhere", target._INDEX), (None, "other_index")]
)
def test_other_index_or_schema_uses_original_comparison(schema, name):
    """同名別schemaを含め元の比較へ委譲しqueryも表現補正もしない。"""
    m, r = _indexes(name, schema)
    c = _Connection([_valid_row()])
    i = _impl(c)
    i.correct_for_autogen_constraints(set(), {r}, set(), {m})
    assert c.queries == [] and i.compare_indexes(m, r).status == "different"


@pytest.mark.parametrize("which", ["create", "drop", "offline"])
def test_create_drop_and_offline_do_not_connect_or_hide_operations(which):
    """create/dropの差分を残し、offlineはDBを取得しない。"""
    m, r = _indexes()
    c = _Connection([_valid_row()])
    i = _impl(c, offline=which == "offline")
    reflected = {r} if which != "create" else set()
    metadata = {m} if which != "drop" else set()
    i.correct_for_autogen_constraints(set(), reflected, set(), metadata)
    assert c.queries == [] and str(r.expressions[0]) == "admin_vocabularies.key"


@pytest.mark.parametrize(
    "position,value",
    [
        (0, "elsewhere"),
        (1, "wrong_table"),
        (3, "hash"),
        (4, "pitchlog_app"),
        (5, "pitchlog_app"),
        (6, True),
        (7, True),
        (8, False),
        (9, False),
        (10, False),
        (11, False),
        (12, True),
        (13, 2),
        (14, 2),
        (15, ["key", "category"]),
        (16, ["pg_catalog.POSIX"]),
        (16, ["public.C"]),
        (17, [1]),
        (18, "lower(key)"),
        (19, "((category = 'other'::text) AND (disabled = false))"),
        (19, "(((category = 'batted_ball'::text) AND disabled) = false)"),
        (20, ["pg_catalog.text_pattern_ops"]),
        (21, "I"),
        (22, "p"),
    ],
)
def test_wrong_catalog_never_receives_c_correction(position, value):
    """owner/validity/式/順序/述語/照合を独立catalogから閉拒否する。"""
    row = list(_valid_row())
    row[position] = value
    m, r = _indexes()
    c = _Connection([row])
    i = _impl(c)
    with pytest.raises(CommandError):
        i.correct_for_autogen_constraints(set(), {r}, set(), {m})
    assert str(r.expressions[0]) == "admin_vocabularies.key" and c.result.closed


@pytest.mark.parametrize(
    "rows", [[], [_valid_row(), _valid_row()], [tuple(_valid_row()[:-1])]]
)
def test_missing_duplicate_or_partial_catalog_is_not_equal(rows):
    """欠落・重複・途中行は反射補正せず拒否する。"""
    m, r = _indexes()
    c = _Connection(rows)
    with pytest.raises(CommandError):
        _impl(c).correct_for_autogen_constraints(set(), {r}, set(), {m})


@pytest.mark.parametrize(
    "mutation", ["expression", "predicate", "unique", "order", "extra-option"]
)
def test_changed_metadata_is_not_silently_accepted(mutation):
    """metadata変更をC反射差の修復に紛れ込ませない。"""
    m, r = _indexes()
    c = _Connection([_valid_row()])
    if mutation == "expression":
        m.expressions = [text("lower(key)")]
    elif mutation == "predicate":
        m.dialect_kwargs["postgresql_where"] = text("disabled = true")
    elif mutation == "unique":
        m.unique = True
    elif mutation == "order":
        m.expressions.append(column("category"))
    else:
        m.dialect_kwargs["postgresql_with"] = {"fillfactor": 50}
    with pytest.raises(CommandError):
        _impl(c).correct_for_autogen_constraints(set(), {r}, set(), {m})
    assert c.queries == []


def test_database_error_propagates_instead_of_becoming_equal():
    """実接続エラーを比較成功へ変換しない。"""
    m, r = _indexes()
    c = _Connection([_valid_row()])
    with patch.object(c, "execute", side_effect=RuntimeError("synthetic query failed")):
        with pytest.raises(RuntimeError, match="synthetic query failed"):
            _impl(c).correct_for_autogen_constraints(set(), {r}, set(), {m})
    assert str(r.expressions[0]) == "admin_vocabularies.key"


def test_official_dialect_dispatch_and_offline_constructor_do_not_connect():
    """公式dialect解決で新hookを選び、offline構築ではDBを要求しない。"""
    from alembic.ddl.impl import DefaultImpl
    from alembic.runtime.migration import MigrationContext

    assert DefaultImpl.get_by_dialect(dialect()) is target.PitchlogPostgresqlImpl
    context = MigrationContext.configure(url="postgresql://", opts={"as_sql": True})
    assert type(context.impl) is target.PitchlogPostgresqlImpl
    assert context.impl.as_sql is True
