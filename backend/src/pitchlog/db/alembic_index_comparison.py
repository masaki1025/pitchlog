"""0040の実C照合だけを反射索引へ戻し、Alembic標準比較へ委譲する。"""

from __future__ import annotations

from typing import NoReturn

from alembic.ddl.postgresql import PostgresqlImpl
from alembic.util import CommandError
from sqlalchemy import text

_INDEX = "ix_admin_vocabularies_batted_ball_key_c"
_TABLE = "admin_vocabularies"
_PREDICATE = "category = 'batted_ball' AND disabled = false"
# pg_get_exprの既知の表記だけ。括弧を一般除去すると結合順の異なる述語も通る。
_PG_PREDICATES = frozenset(
    {
        "((category = 'batted_ball'::text) AND (disabled = false))",
        "(category = 'batted_ball'::text) AND (disabled = false)",
        "((category = 'batted_ball'::text) AND (NOT disabled))",
    }
)
_CATALOG_SQL = """
SELECT tn.nspname,t.relname,x.relname,am.amname,tr.rolname,xr.rolname,
 i.indisunique,i.indisprimary,i.indisvalid,i.indisready,i.indislive,
 i.indimmediate,i.indnullsnotdistinct,i.indnkeyatts,i.indnatts,
 ARRAY(SELECT a.attname FROM unnest(i.indkey) WITH ORDINALITY s(id,n)
 LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=s.id
 ORDER BY s.n),
 ARRAY(SELECT cn.nspname||'.'||co.collname
 FROM unnest(i.indcollation) WITH ORDINALITY s(id,n)
 LEFT JOIN pg_catalog.pg_collation co ON co.oid=s.id
 LEFT JOIN pg_catalog.pg_namespace cn ON cn.oid=co.collnamespace ORDER BY s.n),
 i.indoption::smallint[],pg_catalog.pg_get_expr(i.indexprs,i.indrelid),
 pg_catalog.pg_get_expr(i.indpred,i.indrelid),
 ARRAY(SELECT opn.nspname||'.'||o.opcname
 FROM unnest(i.indclass) WITH ORDINALITY s(id,n)
 JOIN pg_catalog.pg_opclass o ON o.oid=s.id
 JOIN pg_catalog.pg_namespace opn ON opn.oid=o.opcnamespace ORDER BY s.n),
 x.relkind,t.relkind
FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class x ON x.oid=i.indexrelid
JOIN pg_catalog.pg_namespace xn ON xn.oid=x.relnamespace
JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
JOIN pg_catalog.pg_namespace tn ON tn.oid=t.relnamespace
JOIN pg_catalog.pg_am am ON am.oid=x.relam
JOIN pg_catalog.pg_roles tr ON tr.oid=t.relowner
JOIN pg_catalog.pg_roles xr ON xr.oid=x.relowner
WHERE xn.nspname='public' AND x.relname='ix_admin_vocabularies_batted_ball_key_c'
LIMIT 2
"""
_EXPECTED = (
    "public",
    _TABLE,
    _INDEX,
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
    ("key",),
    ("pg_catalog.C",),
    (0,),
    None,
    None,
    ("pg_catalog.text_ops",),
    "i",
    "r",
)


def _reject() -> NoReturn:
    """索引名/資格原値を漏らさず、差異を成功扱いしない。"""
    raise CommandError("0040索引の実カタログ/metadataが承認形と一致しません")


def _catalog_is_exact(rows) -> None:
    """C照合・式・述語・列順・owner・有効性を独立した実catalogで確認する。"""
    if len(rows) != 1 or len(rows[0]) != len(_EXPECTED):
        _reject()
    row = list(rows[0])
    if any(type(row[position]) is not bool for position in range(6, 13)):
        _reject()
    if any(type(row[position]) is not int for position in (13, 14)):
        _reject()
    for position in (15, 16, 17, 20):
        if not isinstance(row[position], (tuple, list)):
            _reject()
        row[position] = tuple(row[position])
    if row[19] not in _PG_PREDICATES:
        _reject()
    row[19] = None
    if tuple(row) != _EXPECTED:
        _reject()


def _target(index) -> bool:
    """同名の別schema/tableや他索引を対象にしない。"""
    return (
        index.name == _INDEX
        and index.table is not None
        and index.table.name == _TABLE
        and index.table.schema in (None, "public")
    )


class PitchlogPostgresqlImpl(PostgresqlImpl):
    """Alembicのdialect hookで既標準処理を維持し、対象1だけ反射を整合する。"""

    __dialect__ = "postgresql"

    def correct_for_autogen_constraints(
        self,
        conn_unique_constraints,
        conn_indexes,
        metadata_unique_constraints,
        metadata_indexes,
    ):
        """公式hookの標準補正後、実catalog証明があるC照合だけを表現する。"""
        super().correct_for_autogen_constraints(
            conn_unique_constraints,
            conn_indexes,
            metadata_unique_constraints,
            metadata_indexes,
        )
        if self.as_sql:
            return
        metadata = [index for index in metadata_indexes if _target(index)]
        reflected = [index for index in conn_indexes if _target(index)]
        # create/dropは標準Alembicへ委譲し、差分を消さない。
        if not metadata or not reflected:
            return
        if len(metadata) != 1 or len(reflected) != 1 or self.connection is None:
            _reject()
        m, r = metadata[0], reflected[0]
        if (
            m.unique
            or len(m.expressions) != 1
            or self._compile_element(m.expressions[0]) != 'key COLLATE "C"'
            or set(m.dialect_kwargs) != {"postgresql_where"}
            or str(m.dialect_kwargs["postgresql_where"]) != _PREDICATE
        ):
            _reject()
        if (
            r.unique
            or len(r.expressions) != 1
            or self._compile_element(r.expressions[0]) not in {"key", 'key COLLATE "C"'}
        ):
            _reject()
        result = self.connection.execute(text(_CATALOG_SQL))
        try:
            _catalog_is_exact(result.fetchall())
        finally:
            result.close()
        if self._compile_element(r.expressions[0]) == "key":
            r.expressions = [r.expressions[0].collate("C")]
        # 集合も比較結果も除外せず、この後の通常compare_indexesへそのまま渡す。
