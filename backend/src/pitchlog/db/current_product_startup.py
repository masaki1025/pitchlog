"""旧0039段階を保ち、current0042の実構造と全認可を接合する。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from runpy import run_path
from typing import Any, cast

import psycopg
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    Table,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import dialect

from pitchlog.authz.product_catalog import inspect_product_authz_catalog
from pitchlog.authz.product_provisioning import (
    apply_product_authz_before_rule_placement,
    apply_product_authz_ddl,
)
from pitchlog.db import stage_a_startup as legacy
from pitchlog.db.game_state.stats import (
    StatsFactVersion,
    StatsPrimitiveFact,
    StatsPrimitiveSource,
)
from pitchlog.db.writer_binding.lifecycle_models import (
    GameLifecycleHead,
    LifecycleWriteAdmission,
)
from pitchlog.db.writer_binding.nonplay_models import NonplayWriteAdmission
from pitchlog.db.writer_binding.substitution_models import SubstitutionWriteReceipt

CURRENT_REVISION = "0045_stats_native27_metric_keys"
_INDEX_REVISION = "0040_batted_vocabulary_index"
_STATS_MODELS = (StatsFactVersion, StatsPrimitiveSource, StatsPrimitiveFact)


class CurrentProductStartupError(legacy.StageAStartupError):
    """currentの配置・構造・認可が閉じて成立していない。"""


@dataclass(frozen=True, slots=True)
class CurrentProductStartupResult:
    """current配置完了を示すが運用公開を許可しない。"""

    completed_revision: str = CURRENT_REVISION
    publishable: bool = False

    def __post_init__(self) -> None:
        """任意版や公開成功を構築できないようにする。"""
        if self.completed_revision != CURRENT_REVISION or self.publishable is not False:
            raise CurrentProductStartupError(
                "current結果の版または公開許可が不一致です"
            )


_TOKEN = re.compile(
    r"\s*(?:('(?:[^']|'')*')|([0-9]+)|([A-Za-z_][A-Za-z_0-9]*)|(::|<=|>=|<>|!=|!~|<@|[(),\[\]~<>=+*/-]))"
)


class _Expression:
    """CHECK/indexの有限SQL式を括弧・型・順序を保って構文比較する。"""

    def __init__(self, value: str) -> None:
        self.tokens: list[str] = []
        while value.strip():
            match = _TOKEN.match(value)
            if match is None:
                raise CurrentProductStartupError("未対応の構造検査式です")
            self.tokens.append(next(x for x in match.groups() if x is not None))
            value = value[match.end() :]
        self.position = 0

    def peek(self) -> str:
        return (
            self.tokens[self.position].lower()
            if self.position < len(self.tokens)
            else ""
        )

    def take(self, expected: str | None = None) -> str:
        value = self.peek()
        if not value or (expected is not None and value != expected):
            raise CurrentProductStartupError("構造検査式の構文が不一致です")
        raw = self.tokens[self.position]
        self.position += 1
        return raw if raw.startswith("'") else value

    def sequence(self, end: str) -> tuple[Any, ...]:
        values = []
        if self.peek() != end:
            while True:
                values.append(self.expression())
                if self.peek() != ",":
                    break
                self.take(",")
        self.take(end)
        return tuple(values)

    def expression(self, minimum: int = 0) -> Any:
        token = self.take()
        if token == "(":
            left = self.expression()
            self.take(")")
        elif token == "not":
            left = ("not", self.expression(25))
        elif token == "-":
            left = ("negative", self.expression(60))
        elif token == "array":
            self.take("[")
            left = ("array", self.sequence("]"))
        elif token.startswith("'"):
            left = ("text", token[1:-1].replace("''", "'"))
        elif token.isdigit():
            left = ("integer", int(token))
        elif self.peek() == "(":
            self.take("(")
            left = ("call", token, self.sequence(")"))
        else:
            left = ("name", token)
        while self.peek():
            op = self.peek()
            if op == "::":
                self.take()
                kind = self.take()
                if self.peek() == "[":
                    self.take("[")
                    self.take("]")
                    kind += "[]"
                # PGがtext literal/NULL/ARRAYへ表示する型注記だけを同一化する。
                harmless = (
                    kind == "text"
                    and left[0] in {"text", "name"}
                    and (left[0] == "text" or left == ("name", "null"))
                )
                harmless |= kind == "text[]" and left[0] == "array"
                # bigint上限超の整数をPGはquoted numericへ逆変換する。
                # 正準十進整数だけを同値化し、NaN/小数/指数/別型は捨てない。
                if (
                    kind == "numeric"
                    and left[0] == "text"
                    and re.fullmatch(r"0|[1-9][0-9]*", left[1])
                ):
                    left = ("integer", int(left[1]))
                harmless |= kind == "numeric" and left[0] == "integer"
                if not harmless:
                    left = ("cast", kind, left)
                continue
            precedence = {
                "or": 10,
                "and": 20,
                "is": 30,
                "in": 30,
                "not": 30,
                "=": 30,
                "<>": 30,
                "!=": 30,
                ">": 30,
                "<": 30,
                ">=": 30,
                "<=": 30,
                "~": 30,
                "!~": 30,
                "<@": 30,
                "+": 40,
                "-": 40,
                "*": 50,
                "/": 50,
            }.get(op, -1)
            if precedence < minimum:
                break
            self.take()
            if op == "is":
                negative = self.peek() == "not"
                if negative:
                    self.take()
                self.take("null")
                left = ("is-not-null" if negative else "is-null", left)
                continue
            if op in {"in", "not"}:
                if op == "not":
                    self.take("in")
                self.take("(")
                right = ("call", "any", (("array", self.sequence(")")),))
                result = ("=", left, right)
                left = ("not", result) if op == "not" else result
                continue
            right = self.expression(precedence + 1)
            if op in {"<>", "!="} and right[:2] == ("call", "all"):
                left = ("not", ("=", left, ("call", "any", right[2])))
            elif op == "=" and right in {("name", "false"), ("name", "true")}:
                left = ("not", left) if right == ("name", "false") else left
            else:
                left = ("<>" if op == "!=" else op, left, right)
        return left


def _expression(value: str | None) -> Any:
    if value is None:
        return None
    parser = _Expression(value)
    result = parser.expression()
    if parser.peek():
        raise CurrentProductStartupError("構造検査式に余剰があります")
    return result


def _tables() -> tuple[Table, ...]:
    """旧6表と成績3表・非play1表を既採用型定義から一度だけ取得する。"""
    from pitchlog.db.all_models import IMPORTED_MODEL_MODULE_NAMES
    from pitchlog.db.game_state import models as game_models
    from pitchlog.db.writer_binding.ordinary_models import (
        OrdinaryPitchCheckpoint,
        OrdinaryPitchHistory,
        OrdinaryPitchWriteAdmission,
    )
    from pitchlog.sync.control_provider.writer_binding_models import (
        FirstBallWriteAdmission,
        WriterAdmission,
        WriterBinding,
    )

    if (
        not IMPORTED_MODEL_MODULE_NAMES
        or cast(Table, game_models.Game.__table__).name != "games"
    ):
        raise CurrentProductStartupError("current参照モデルが不一致です")
    models = (
        WriterBinding,
        WriterAdmission,
        FirstBallWriteAdmission,
        OrdinaryPitchCheckpoint,
        OrdinaryPitchWriteAdmission,
        OrdinaryPitchHistory,
        *_STATS_MODELS,
        NonplayWriteAdmission,
        LifecycleWriteAdmission,
        GameLifecycleHead,
        SubstitutionWriteReceipt,
    )
    return tuple(
        sorted((cast(Table, m.__table__) for m in models), key=lambda t: t.name)
    )


def _revision(connection: Any) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        rows = cursor.fetchall()
    if len(rows) != 1 or rows[0][0] not in {
        legacy._PLACEMENT_REVISION,
        legacy._EPOCH_REVISION,
        *legacy._POST_INITIAL_REVISIONS,
        CURRENT_REVISION,
    }:
        raise CurrentProductStartupError("current配置のrevisionが不一致です")
    return rows[0][0]


def _fk_action(value: str | None) -> str:
    """宣言済FK動作だけをPG catalogの記号へ対応させる。"""
    mapping = {
        None: "a",
        "NO ACTION": "a",
        "RESTRICT": "r",
        "CASCADE": "c",
        "SET NULL": "n",
        "SET DEFAULT": "d",
    }
    if value not in mapping:
        raise CurrentProductStartupError("未知のFK動作です")
    return mapping[value]


def _fk_match(value: str | None) -> str:
    """MATCH FULL/SIMPLEの実宣言を保持し、未知を推測しない。"""
    mapping = {None: "s", "SIMPLE": "s", "FULL": "f"}
    if value not in mapping:
        raise CurrentProductStartupError("未知のFK MATCHです")
    return mapping[value]


def _initially_deferred(constraint: Any) -> bool:
    """遅延宣言の型と整合を失わず実catalog値へ対応させる。"""
    if constraint.deferrable not in (None, False, True) or type(
        constraint.deferrable
    ) not in (type(None), bool):
        raise CurrentProductStartupError("制約deferrableの型が不一致です")
    if constraint.initially not in (None, "IMMEDIATE", "DEFERRED"):
        raise CurrentProductStartupError("未知の初期遅延制約です")
    if constraint.initially == "DEFERRED" and constraint.deferrable is not True:
        raise CurrentProductStartupError("遅延制約の宣言が矛盾しています")
    return constraint.initially == "DEFERRED"


def _expected_constraints(table: Table) -> list[tuple[Any, ...]]:
    """型定義からPK/UK/FK/CHECKの構造全値を取得する。"""
    rows = []
    for constraint in table.constraints:
        fields: tuple[Any, ...]
        if isinstance(constraint, CheckConstraint):
            fields = (
                "c",
                constraint.name,
                (),
                None,
                (),
                None,
                _expression(str(constraint.sqltext)),
            )
        elif isinstance(constraint, ForeignKeyConstraint):
            elements = list(constraint.elements)
            remote = elements[0].column.table
            fields = (
                "f",
                constraint.name,
                tuple(c.name for c in constraint.columns),
                (remote.fullname if remote.schema else "public." + remote.name),
                tuple(e.column.name for e in elements),
                _fk_action(constraint.ondelete),
                None,
            )
        elif isinstance(constraint, (PrimaryKeyConstraint, UniqueConstraint)):
            fields = (
                "p" if isinstance(constraint, PrimaryKeyConstraint) else "u",
                None,
                tuple(c.name for c in constraint.columns),
                None,
                (),
                None,
                None,
            )
        else:
            raise CurrentProductStartupError("未知のcurrent制約です")
        rows.append(
            (
                *fields,
                *(
                    (_fk_action(constraint.onupdate), _fk_match(constraint.match))
                    if isinstance(constraint, ForeignKeyConstraint)
                    else (None, None)
                ),
                True,
                fields[0] != "c",
                constraint.deferrable is True,
                _initially_deferred(constraint),
            )
        )
    return sorted(rows, key=repr)


_CONSTRAINT_SQL = """
SELECT k.contype,k.conname,
 ARRAY(SELECT a.attname FROM unnest(k.conkey) WITH ORDINALITY s(id,n)
       JOIN pg_attribute a ON a.attrelid=k.conrelid AND a.attnum=s.id ORDER BY s.n),
 CASE WHEN k.contype='f' THEN (SELECT n.nspname||'.'||c.relname FROM pg_class c
       JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=k.confrelid) END,
 ARRAY(SELECT a.attname FROM unnest(k.confkey) WITH ORDINALITY s(id,n)
       JOIN pg_attribute a ON a.attrelid=k.confrelid AND a.attnum=s.id ORDER BY s.n),
 CASE WHEN k.contype='f' THEN k.confdeltype::text END,
 CASE WHEN k.contype='c' THEN pg_get_expr(k.conbin,k.conrelid) END,
 CASE WHEN k.contype='f' THEN k.confupdtype::text END,
 CASE WHEN k.contype='f' THEN k.confmatchtype::text END,
 k.convalidated,k.connoinherit,k.condeferrable,k.condeferred
FROM pg_constraint k WHERE k.conrelid=%s::regclass ORDER BY k.conname
"""


def _check_current_structure(connection: Any) -> None:
    """sync_fence全10表と承認済構造を不足/余剰とも拒否する。"""
    tables = _tables()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT n.nspname,r.rolname FROM pg_namespace n JOIN pg_roles r "
            "ON r.oid=n.nspowner WHERE n.nspname='sync_fence'"
        )
        if cursor.fetchall() != [("sync_fence", "pitchlog_owner")]:
            raise CurrentProductStartupError("current schema ownerが不一致です")
        cursor.execute(
            "SELECT c.relname,r.rolname,c.relrowsecurity,c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='sync_fence' "
            "AND c.relkind IN ('r','p') ORDER BY c.relname"
        )
        if cursor.fetchall() != [
            (t.name, "pitchlog_owner", True, True) for t in tables
        ]:
            raise CurrentProductStartupError("current全表/owner/RLSが不一致です")
        for table in tables:
            cursor.execute(
                "SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,"
                "a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) "
                "FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid "
                "AND d.adnum=a.attnum WHERE a.attrelid=to_regclass(%s) "
                "AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
                (table.fullname,),
            )
            expected = [
                (
                    c.name,
                    c.type.compile(dialect=dialect()).lower(),
                    not c.nullable,
                    "",
                    "",
                    None,
                )
                for c in table.c
            ]
            if cursor.fetchall() != expected:
                raise CurrentProductStartupError("current全列の型/属性が不一致です")
            if table.name not in {
                m.__table__.name
                for m in (
                    *_STATS_MODELS,
                    NonplayWriteAdmission,
                    LifecycleWriteAdmission,
                    GameLifecycleHead,
                    SubstitutionWriteReceipt,
                )
            }:
                cursor.execute(
                    "SELECT c.relname,k.conname,pg_get_constraintdef(k.oid),"
                    "k.convalidated,k.connoinherit FROM pg_constraint k "
                    "JOIN pg_class c ON c.oid=k.conrelid "
                    "WHERE k.conrelid=%s::regclass ORDER BY k.conname",
                    (table.fullname,),
                )
                expected_old = [
                    row for row in legacy._WRITER_CONSTRAINTS if row[0] == table.name
                ]
                if cursor.fetchall() != expected_old:
                    raise CurrentProductStartupError("旧writer制約が不一致です")
                continue
            cursor.execute(_CONSTRAINT_SQL, (table.fullname,))
            actual = []
            for row in cursor.fetchall():
                kind, name, cols, remote, refs, delete, expr, *flags = row
                actual.append(
                    (
                        kind,
                        None if kind in {"p", "u"} else name,
                        tuple(cols) if kind != "c" else (),
                        remote,
                        tuple(refs),
                        delete,
                        _expression(expr),
                        *flags,
                    )
                )
            if sorted(actual, key=repr) != _expected_constraints(table):
                raise CurrentProductStartupError("current全制約が不一致です")


_INDEX_SQL = """
SELECT c.relname,i.indisunique,i.indisprimary,i.indisvalid,i.indisready,i.indislive,
 i.indimmediate,a.amname,
 ARRAY(SELECT x.attname FROM unnest(i.indkey) WITH ORDINALITY s(id,n)
       LEFT JOIN pg_attribute x ON x.attrelid=i.indrelid AND x.attnum=s.id
       ORDER BY s.n),
 ARRAY(SELECT co.collname FROM unnest(i.indcollation) WITH ORDINALITY s(id,n)
       LEFT JOIN pg_collation co ON co.oid=s.id ORDER BY s.n),
 i.indoption::smallint[],pg_get_expr(i.indexprs,i.indrelid),
 pg_get_expr(i.indpred,i.indrelid),k.contype,
 ARRAY(SELECT o.opcname FROM unnest(i.indclass) WITH ORDINALITY s(id,n)
       JOIN pg_opclass o ON o.oid=s.id ORDER BY s.n),i.indnullsnotdistinct
FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
JOIN pg_am a ON a.oid=c.relam
LEFT JOIN pg_constraint k ON k.conindid=i.indexrelid AND k.conrelid=i.indrelid
WHERE i.indrelid=%s::regclass ORDER BY c.relname
"""


def _index_shape(
    name, unique, primary, columns, collations, predicate, kind=None, opclasses=()
):
    return (
        None if kind in {"p", "u"} else name,
        unique,
        primary,
        True,
        True,
        True,
        True,
        "btree",
        tuple(columns),
        tuple(collations),
        (0,) * len(columns),
        None,
        _expression(predicate),
        kind,
        tuple(opclasses),
        False,
    )


def _opclass(column):
    names = {
        "uuid": "uuid_ops",
        "text": "text_ops",
        "bigint": "int8_ops",
        "integer": "int4_ops",
        "bytea": "bytea_ops",
    }
    kind = column.type.compile(dialect=dialect()).lower()
    if kind not in names:
        raise CurrentProductStartupError("未知のindex列型です")
    return names[kind]


def _check_current_indexes(connection: Any) -> None:
    """全10表の全indexと0040の固定keyset索引を閉じて照合する。"""
    with connection.cursor() as cursor:
        for table in _tables():
            expected = []
            for constraint in table.constraints:
                if isinstance(constraint, (PrimaryKeyConstraint, UniqueConstraint)):
                    cols = list(constraint.columns)
                    kind = "p" if isinstance(constraint, PrimaryKeyConstraint) else "u"
                    expected.append(
                        _index_shape(
                            None,
                            True,
                            kind == "p",
                            [c.name for c in cols],
                            [
                                "default"
                                if c.type.compile(dialect=dialect()).lower() == "text"
                                else None
                                for c in cols
                            ],
                            None,
                            kind,
                            opclasses=[_opclass(c) for c in cols],
                        )
                    )
            for index in table.indexes:
                cols = [cast(Any, c) for c in index.expressions]
                pred = index.dialect_options["postgresql"]["where"]
                expected.append(
                    _index_shape(
                        index.name,
                        bool(index.unique),
                        False,
                        [c.name for c in cols],
                        [
                            "default"
                            if c.type.compile(dialect=dialect()).lower() == "text"
                            else None
                            for c in cols
                        ],
                        None if pred is None else str(pred),
                        opclasses=[_opclass(c) for c in cols],
                    )
                )
            cursor.execute(_INDEX_SQL, (table.fullname,))
            actual = []
            for row in cursor.fetchall():
                (
                    name,
                    unique,
                    primary,
                    valid,
                    ready,
                    live,
                    immediate,
                    method,
                    cols,
                    colls,
                    options,
                    expression,
                    pred,
                    kind,
                    opclasses,
                    nulls_not_distinct,
                ) = row
                actual.append(
                    (
                        None if kind in {"p", "u"} else name,
                        unique,
                        primary,
                        valid,
                        ready,
                        live,
                        immediate,
                        method,
                        tuple(cols),
                        tuple(colls),
                        tuple(options),
                        expression,
                        _expression(pred),
                        kind,
                        tuple(opclasses),
                        nulls_not_distinct,
                    )
                )
            if sorted(actual, key=repr) != sorted(expected, key=repr):
                raise CurrentProductStartupError("current全indexが不一致です")
        cursor.execute(_INDEX_SQL, ("public.admin_vocabularies",))
        all_admin = cursor.fetchall()
        if {r[0] for r in all_admin} != {
            "pk_admin_vocabularies",
            "ix_admin_vocabularies_batted_ball_key_c",
        } or len(all_admin) != 2:
            raise CurrentProductStartupError("admin語彙のindex集合が不一致です")
        primary = next(r for r in all_admin if r[0] == "pk_admin_vocabularies")
        if (
            *primary[:8],
            tuple(primary[8]),
            tuple(primary[9]),
            tuple(primary[10]),
            primary[11],
            _expression(primary[12]),
            primary[13],
            tuple(primary[14]),
            primary[15],
        ) != (
            "pk_admin_vocabularies",
            True,
            True,
            True,
            True,
            True,
            True,
            "btree",
            ("key",),
            ("default",),
            (0,),
            None,
            None,
            "p",
            ("text_ops",),
            False,
        ):
            raise CurrentProductStartupError("既admin語彙PK indexが不一致です")
        selected = [
            r for r in all_admin if r[0] == "ix_admin_vocabularies_batted_ball_key_c"
        ]
        expected_predicate = _expression("category='batted_ball' AND disabled=false")
        if len(selected) != 1:
            raise CurrentProductStartupError("0040索引が不足/重複しています")
        row = selected[0]
        if (
            *row[:8],
            tuple(row[8]),
            tuple(row[9]),
            tuple(row[10]),
            row[11],
            _expression(row[12]),
            row[13],
            tuple(row[14]),
            row[15],
        ) != (
            "ix_admin_vocabularies_batted_ball_key_c",
            False,
            False,
            True,
            True,
            True,
            True,
            "btree",
            ("key",),
            ("C",),
            (0,),
            None,
            expected_predicate,
            None,
            ("text_ops",),
            False,
        ):
            raise CurrentProductStartupError("0040索引の全属性が不一致です")


def _catalog(connection: Any):
    with connection.cursor() as cursor:
        cursor.execute("SELECT oid FROM pg_roles WHERE rolname=current_user")
        row = cursor.fetchone()
    if row is None or type(row[0]) is not int:
        raise CurrentProductStartupError("current検査主体がありません")
    return inspect_product_authz_catalog(
        connection, privileged_role_oids=frozenset({row[0]})
    )


def _pre_full_expected():
    """既適用器のselected要素を使い、保留算法を二重実装しない。"""
    from pitchlog.authz.product_provisioning import (
        ProductOperation,
        _load_product_elements,
        _selected_product_ddl,
    )

    _, selected = _selected_product_ddl(ProductOperation.APPLY_PRE_RULE)
    ids = {row.element_id for row in selected}
    elements = _load_product_elements()
    present = [row for row in elements if row.element_id in ids]
    functions = {
        (
            r.fields["schema_name"],
            r.fields["function_name"],
            r.fields.get("identity_args", ""),
        )
        for r in present
        if r.element_type == "function"
    }
    # 旧0036の実構造検査が先に保証した内部保護関数はmigration由来で既存。
    migration_function = ("public", "protect_initial_right_storage", "")
    canonical_functions = {
        (
            r.fields["schema_name"],
            r.fields["function_name"],
            r.fields.get("identity_args", ""),
        )
        for r in elements
        if r.element_type == "function"
    }
    if migration_function not in canonical_functions:
        raise CurrentProductStartupError("0036内部保護関数の正規宣言がありません")
    functions.add(migration_function)
    nonplay_guard = ("public", "protect_nonplay_admission", "")
    if nonplay_guard not in canonical_functions:
        raise CurrentProductStartupError("0042内部保護関数の正規宣言がありません")
    functions.add(nonplay_guard)
    for name in (
        "protect_lifecycle_write_admissions",
        "protect_game_lifecycle_heads",
    ):
        guard = ("public", name, "")
        if guard not in canonical_functions:
            raise CurrentProductStartupError("0043内部保護関数の正規宣言がありません")
        functions.add(guard)
    schemas = {r.fields["schema_name"] for r in present if r.element_type == "schema"}
    # sync_fenceは0037/0041のowner migrationが配置する。権限は別に閉照合する。
    schemas.add("sync_fence")
    tables = {
        r.fields["table_id"]: r.fields["schema_name"]
        for r in elements
        if r.element_type == "table"
    }
    policies = {
        (
            tables[r.fields["table_id"]],
            r.fields["table_id"],
            r.fields.get("policy_name", "pitchlog_app_" + str(r.fields.get("profile"))),
        )
        for r in present
        if r.element_type == "policy"
    }
    table_acl, column_acl, schema_acl, builtin_acl = set(), set(), set(), set()
    for row in present:
        f = cast(dict[str, Any], row.fields)
        if row.element_type in {"acl_expectation", "column_acl_expectation"}:
            if f.get("object_kind") == "builtin_function":
                for privilege in f["privilege_ids"]:
                    builtin_acl.add(
                        (
                            f["object_schema"],
                            f["object_id"],
                            "",
                            f["grantee_role_id"],
                            privilege.upper(),
                            f["grant_option"],
                        )
                    )
                continue
            for privilege in f["privilege_ids"]:
                base = (f["object_schema"], f["object_id"])
                if row.element_type == "column_acl_expectation":
                    column_acl.add(
                        (
                            *base,
                            f["column_id"],
                            f["grantee_role_id"],
                            privilege.upper(),
                            f["grant_option"],
                        )
                    )
                else:
                    table_acl.add(
                        (
                            *base,
                            f["grantee_role_id"],
                            privilege.upper(),
                            f["grant_option"],
                        )
                    )
        elif row.element_type == "schema":
            for grant in f["acl_expectations"]:
                schema_acl.add(
                    (
                        f["schema_name"],
                        grant["grantee"],
                        grant["privilege"].upper(),
                        grant["grantable"],
                    )
                )
    return functions, schemas, policies, table_acl, column_acl, schema_acl, builtin_acl


def _pre_full_catalog_pairs():
    """正規全期待と既selected由来pre期待を全分類分まとめる。"""
    from pitchlog.authz.first_ball_write_stamp import stamp_trigger_expectations
    from pitchlog.authz.product_catalog import (
        _expected_lifecycle_function_details,
        _load_product_expectations,
    )
    from pitchlog.authz.terminal_pitch_write_stamp import trigger_expectations

    full = _load_product_expectations()
    functions, schemas, policies, table_acl, column_acl, schema_acl, builtin_acl = (
        _pre_full_expected()
    )
    fields = {
        "SCHEMAS": (full.schemas, lambda r: r[0] in schemas),
        "SCHEMA-ACL": (full.schema_acl, lambda r: r in schema_acl),
        "POLICIES": (full.policies, lambda r: r[:3] in policies),
        "TABLE-ACL": (full.table_acl, lambda r: r in table_acl),
        "COLUMN-ACL": (full.column_acl, lambda r: r in column_acl),
        "FUNCTIONS": (full.functions, lambda r: r[:3] in functions),
        "FUNCTION-ACL": (full.function_acl, lambda r: r[:3] in functions),
        "BUILTIN-ADDITIONAL-EXECUTE": (
            full.builtin_function_acl,
            lambda r: r in builtin_acl,
        ),
        "LIFECYCLE-FUNCTION-DETAILS": (
            _expected_lifecycle_function_details(),
            lambda r: r[:3] in functions,
        ),
    }
    pairs = {
        "PRODUCT-CATALOG:" + key: (rows, tuple(r for r in rows if keep(r)))
        for key, (rows, keep) in fields.items()
    }
    identity_trigger = "trg_play_rows_projection_identity_immutable"
    first_triggers = stamp_trigger_expectations()
    migration_first = tuple(r for r in first_triggers if r[0] == identity_trigger)
    if len(migration_first) != 1:
        raise CurrentProductStartupError("migration由来のplay_rows保護宣言が不一致です")
    pairs["PRODUCT-CATALOG:FIRST-BALL-TRIGGERS"] = (first_triggers, migration_first)
    pairs["PRODUCT-CATALOG:PLAY-PREFIX-TRIGGERS"] = (
        tuple(
            (
                "play_runners"
                if r[0] == "trg_play_prefix_runner_10_admit"
                else "play_rows",
                *r,
            )
            for r in trigger_expectations()
        ),
        tuple(
            ("play_rows", *r)
            for r in trigger_expectations()
            if r[0] == identity_trigger
        ),
    )
    if len(pairs["PRODUCT-CATALOG:PLAY-PREFIX-TRIGGERS"][1]) != 1:
        raise CurrentProductStartupError("migration由来のprefix保護宣言が不一致です")
    from pitchlog.authz.nonplay_storage_profile import (
        trigger_expectations as nonplay_triggers,
    )

    pairs["PRODUCT-CATALOG:NONPLAY-STORAGE-TRIGGERS"] = (
        nonplay_triggers(),
        nonplay_triggers(),
    )
    from pitchlog.authz.lifecycle_storage_profile import (
        trigger_expectations as lifecycle_triggers,
    )

    pairs["PRODUCT-CATALOG:LIFECYCLE-STORAGE-TRIGGERS"] = (
        lifecycle_triggers(),
        lifecycle_triggers(),
    )
    return pairs


def _require_pre_or_full_catalog(connection: Any) -> str:
    """fullまたは既適用器の正確なpre-fullだけを許し、partialを補修しない。"""
    report = _catalog(connection)
    if report.ok:
        return "full"
    pairs = _pre_full_catalog_pairs()
    violations = {v.check_id: v for v in report.violations}
    if len(violations) != len(report.violations) or set(violations) - pairs.keys():
        raise CurrentProductStartupError("current pre-fullの未知catalog差分です")
    # 違反の無い分類もfull値を観測したものとして比較する。
    # 一部だけfullの混合状態を、残差のsubsetとして許さない。
    for check, (full, pre) in pairs.items():
        if check not in report.checked_ids:
            raise CurrentProductStartupError("current pre-fullの検査が欠落しています")
        violation = violations.get(check)
        if violation is not None and violation.expected != full:
            raise CurrentProductStartupError("current catalogの正規期待が不一致です")
        actual = full if violation is None else violation.actual
        if actual != pre:
            raise CurrentProductStartupError("currentの部分認可/余剰権限を拒否します")
    return "pre-full"


def _apply_current_storage(owner_dsn: str) -> None:
    """現行0045まで同owner transactionへ配置し、途中故障を全部戻す。"""
    engine = create_engine(legacy._owner_url(owner_dsn))
    try:
        with engine.begin() as connection:
            raw = connection.connection.driver_connection
            if raw is None or _revision(raw) != legacy._WRITER_REVISION:
                raise CurrentProductStartupError("current配置前は実0039が必要です")
            legacy._check_writer_storage(raw, legacy._WRITER_REVISION)
            config = Config(str(legacy._BACKEND_ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, CURRENT_REVISION)
            if _revision(raw) != CURRENT_REVISION:
                raise CurrentProductStartupError("current配置後の版が不一致です")
            _check_current_structure(raw)
            _check_current_indexes(raw)
            _check_current_public_storage(raw)
    finally:
        engine.dispose()


def _finish_current(owner_dsn: str, applicator_dsn: str) -> CurrentProductStartupResult:
    with psycopg.connect(applicator_dsn) as connection:
        revision = _revision(connection)
    if revision == legacy._WRITER_REVISION:
        legacy._require_writer_state(applicator_dsn)
        _apply_current_storage(owner_dsn)
    elif revision != CURRENT_REVISION:
        raise CurrentProductStartupError("current確定前の段階が不一致です")
    with psycopg.connect(applicator_dsn) as connection:
        _check_current_structure(connection)
        _check_current_indexes(connection)
        _check_current_rules(connection)
        _check_current_public_storage(connection)
        _require_pre_or_full_catalog(connection)
    with psycopg.connect(applicator_dsn) as connection:
        apply_product_authz_ddl(connection)
    with psycopg.connect(applicator_dsn) as connection:
        if _revision(connection) != CURRENT_REVISION:
            raise CurrentProductStartupError("current確定版が不一致です")
        _check_current_structure(connection)
        _check_current_indexes(connection)
        _check_current_rules(connection)
        _check_current_public_storage(connection)
        if not _catalog(connection).ok:
            raise CurrentProductStartupError("current全catalogが不一致です")
    return CurrentProductStartupResult()


def advance_current_product_from_s0(
    *,
    owner_dsn: str,
    applicator_dsn: str,
) -> CurrentProductStartupResult:
    """旧S0〜0039の実前提成立後、currentを非公開で接合する。"""
    legacy._require_same_database(owner_dsn, applicator_dsn)
    legacy._require_s0(owner_dsn)
    with psycopg.connect(applicator_dsn) as connection:
        apply_product_authz_before_rule_placement(connection)
    legacy._apply_placement(owner_dsn)
    legacy._require_placed_state(applicator_dsn)
    legacy._apply_epoch(owner_dsn)
    legacy._require_epoch_state(applicator_dsn)
    # module属性をその時点で呼び、既seed hookを必ず維持する。
    legacy._apply_initial_storage(owner_dsn)
    legacy._require_initial_state(applicator_dsn)
    legacy._apply_writer_storage(owner_dsn)
    legacy._require_writer_state(applicator_dsn)
    return _finish_current(owner_dsn, applicator_dsn)


def resume_current_product_after_placement(
    *,
    owner_dsn: str,
    applicator_dsn: str,
) -> CurrentProductStartupResult:
    """同版0042は再migrationせず、旧中間段階は元の有限前提で再開する。"""
    legacy._require_same_database(owner_dsn, applicator_dsn)
    with psycopg.connect(owner_dsn) as owner, owner.cursor() as cursor:
        cursor.execute("SELECT current_user,session_user")
        if cursor.fetchone() != ("pitchlog_owner", "pitchlog_owner"):
            raise CurrentProductStartupError("current再開のowner主体が不一致です")
        revision = _revision(owner)
    if revision != CURRENT_REVISION:
        revision = legacy._require_placed_state(applicator_dsn)
        if revision == legacy._PLACEMENT_REVISION:
            legacy._apply_epoch(owner_dsn)
        legacy._require_epoch_state(applicator_dsn)
        if revision not in legacy._POST_INITIAL_REVISIONS:
            legacy._apply_initial_storage(owner_dsn)
        legacy._require_initial_state(applicator_dsn)
        legacy._apply_writer_storage(owner_dsn)
        legacy._require_writer_state(applicator_dsn)
    return _finish_current(owner_dsn, applicator_dsn)


def _check_current_rules(connection: Any) -> None:
    """0042でも同じ規則5行と配置owner/RLS/一時policy撤去を保持する。"""
    rules = run_path(str(legacy._PLACEMENT_SOURCE))["_RULES"]
    if not isinstance(rules, tuple) or len(rules) != 5:
        raise CurrentProductStartupError("current固定規則が不一致です")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id::text,regulation_innings,called_game_conditions,"
            "extra_innings_limit,tiebreak_rule,uses_dh FROM public.rule_sets "
            "WHERE id=ANY(%s::uuid[]) ORDER BY id::text",
            ([r[1] for r in rules],),
        )
        if cursor.fetchall() != sorted(
            (rid, 9, cold, limit, tie, True) for _, rid, cold, limit, tie in rules
        ):
            raise CurrentProductStartupError("current規則5行が不一致です")
        cursor.execute(
            "SELECT game_type_key,game_type_category,rule_set_id::text "
            "FROM public.game_type_rule_defaults WHERE game_type_key=ANY(%s) "
            "ORDER BY game_type_key",
            ([r[0] for r in rules],),
        )
        if cursor.fetchall() != sorted((r[0], "game_type", r[1]) for r in rules):
            raise CurrentProductStartupError("current既定5行が不一致です")
        cursor.execute(
            "SELECT relname,pg_get_userbyid(relowner),relrowsecurity,"
            "relforcerowsecurity FROM pg_class WHERE oid IN "
            "('public.rule_sets'::regclass,'public.game_type_rule_defaults'::regclass) "
            "ORDER BY relname"
        )
        if cursor.fetchall() != [
            ("game_type_rule_defaults", "pitchlog_owner", True, True),
            ("rule_sets", "pitchlog_owner", True, True),
        ]:
            raise CurrentProductStartupError("current規則配置owner/RLSが不一致です")
        cursor.execute(
            "SELECT policyname FROM pg_policies WHERE schemaname='public' "
            "AND policyname LIKE 'tsk550_seed_%'"
        )
        if cursor.fetchall():
            raise CurrentProductStartupError("current一時policyが残っています")


def _check_current_public_storage(connection: Any) -> None:
    """0042後も既0035/36の全実構造期待を変えず再検査する。"""
    with connection.cursor() as cursor:
        cursor.execute(
            (
                "SELECT a.atttypid::regtype::text, a.attnotnull, a.attident"
                "ity, a.attgenerated, pg_get_expr(d.adbin, d.adrelid) FROM "
                "pg_catalog.pg_attribute a LEFT JOIN pg_catalog.pg_attrdef "
                "d ON d.adrelid = a.attrelid AND d.adnum = a.attnum WHERE a"
                ".attrelid = 'public.rg1_restore_gate'::regclass AND a.attn"
                "ame = 'recovery_generation' AND NOT a.attisdropped"
            )
        )
        if cursor.fetchall() != [("bigint", False, "", "", None)]:
            raise CurrentProductStartupError("0035のepoch実列定義が不一致です")
        cursor.execute(
            (
                "SELECT pg_get_constraintdef(oid), convalidated, connoinher"
                "it FROM pg_catalog.pg_constraint WHERE conrelid = 'public."
                "rg1_restore_gate'::regclass AND conname = 'ck_rg1_restore_"
                "gate_recovery_generation' AND contype = 'c'"
            )
        )
        if cursor.fetchall() != [
            (
                "CHECK (((recovery_generation IS NULL) OR (recovery_generation > 0)))",
                True,
                False,
            )
        ]:
            raise CurrentProductStartupError("0035のepoch実制約が不一致です")
        cursor.execute(
            (
                "SELECT a.attname, a.atttypid::regtype::text, a.attnotnull,"
                " a.attidentity, a.attgenerated, pg_get_expr(d.adbin, d.adr"
                "elid) FROM pg_catalog.pg_attribute a LEFT JOIN pg_catalog."
                "pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE a.attrelid='public.recording_generations'::regclass "
                "AND a.attname IN ('proof_digest','recovery_generation') AN"
                "D NOT a.attisdropped ORDER BY a.attname"
            )
        )
        if cursor.fetchall() != [
            ("proof_digest", "bytea", False, "", "", None),
            ("recovery_generation", "bigint", False, "", "", None),
        ]:
            raise CurrentProductStartupError("0036の世代証拠実列が不一致です")
        cursor.execute(
            (
                "SELECT conname, pg_get_constraintdef(oid), convalidated, c"
                "onnoinherit FROM pg_catalog.pg_constraint WHERE conrelid='"
                "public.recording_generations'::regclass AND conname IN ('c"
                "k_recording_generations_proof_digest', 'ck_recording_gener"
                "ations_recovery_generation') AND contype='c' ORDER BY conn"
                "ame"
            )
        )
        if cursor.fetchall() != [
            (
                "ck_recording_generations_proof_digest",
                "CHECK (((proof_digest IS NULL) OR (octet_length(proof_digest) = 32)))",
                True,
                False,
            ),
            (
                "ck_recording_generations_recovery_generation",
                "CHECK (((recovery_generation IS NULL) OR (recovery_generation > 0)))",
                True,
                False,
            ),
        ]:
            raise CurrentProductStartupError("0036の世代証拠実制約が不一致です")
        tables = (
            "game_start_attempts",
            "game_start_requests",
            "recording_right_deliveries",
            "trusted_devices",
        )
        cursor.execute(
            (
                "SELECT c.relname, r.rolname, c.relrowsecurity, c.relforcer"
                "owsecurity FROM pg_catalog.pg_class c JOIN pg_catalog.pg_n"
                "amespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_role"
                "s r ON r.oid=c.relowner WHERE n.nspname='public' AND c.rel"
                "kind='r' AND c.relname=ANY(%s) ORDER BY c.relname"
            ),
            (list(tables),),
        )
        if cursor.fetchall() != [
            (table, "pitchlog_owner", True, True) for table in tables
        ]:
            raise CurrentProductStartupError("0036の4表owner/RLSが不一致です")
        cursor.execute(
            (
                "SELECT c.relname, t.tgname, t.tgenabled, t.tgtype, p.prona"
                "me, r.rolname, p.prosecdef, p.proconfig FROM pg_catalog.pg"
                "_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid J"
                "OIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN"
                " pg_catalog.pg_proc p ON p.oid=t.tgfoid JOIN pg_catalog.pg"
                "_roles r ON r.oid=p.proowner WHERE n.nspname='public' AND "
                "c.relname=ANY(%s) AND NOT t.tgisinternal ORDER BY c.relnam"
                "e,t.tgname"
            ),
            (list(tables),),
        )
        if cursor.fetchall() != [
            (
                table,
                f"trg_{table}_initial_right_guard",
                "O",
                27,
                "protect_initial_right_storage",
                "pitchlog_owner",
                False,
                ["search_path=pg_catalog, pg_temp"],
            )
            for table in tables
        ]:
            raise CurrentProductStartupError("0036の内部保護triggerが不一致です")
        cursor.execute(
            (
                "SELECT t.tgname, t.tgenabled, t.tgtype, n.nspname, p.prona"
                "me, ARRAY(SELECT a.attname FROM unnest(t.tgattr::smallint["
                "]) WITH ORDINALITY AS member(attnum, ordinal_position) JOI"
                "N pg_catalog.pg_attribute a ON a.attrelid=t.tgrelid AND a."
                "attnum=member.attnum ORDER BY member.ordinal_position) FRO"
                "M pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.o"
                "id=t.tgfoid JOIN pg_catalog.pg_namespace n ON n.oid=p.pron"
                "amespace WHERE t.tgrelid='public.recording_generations'::r"
                "egclass AND t.tgname='trg_recording_generations_update_gua"
                "rd' AND NOT t.tgisinternal"
            )
        )
        if cursor.fetchall() != [
            (
                "trg_recording_generations_update_guard",
                "O",
                19,
                "public",
                "protect_recording_generations_updates",
                [
                    "generation",
                    "kind",
                    "issuance_order",
                    "holder_device",
                    "granted_at",
                    "confirmed_watermark",
                    "proof_digest",
                    "recovery_generation",
                ],
            )
        ]:
            raise CurrentProductStartupError("0036の世代guard発火列が不一致です")
