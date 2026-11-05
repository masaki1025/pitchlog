"""current配置の順序・構造比較・固定profileをPGなしで検査する。"""

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pitchlog.db import current_product_startup as current


@pytest.mark.parametrize(
    "left,right",
    [
        ("a=1 AND (b=2 OR c=3)", "(a = 1) AND ((b = 2) OR (c = 3))"),
        (
            "provider_kind IN ('first_ball','ordinary')",
            "provider_kind = ANY(ARRAY['first_ball'::text,'ordinary'::text])",
        ),
        (
            "amount NOT IN ('NaN'::numeric,'Infinity'::numeric)",
            "amount <> ALL(ARRAY['NaN'::numeric,'Infinity'::numeric])",
        ),
        ("array_position(a,NULL) IS NULL", "(array_position(a,NULL::text) IS NULL)"),
        (
            "category='batted_ball' AND disabled=false",
            "((category = 'batted_ball'::text) AND (NOT disabled))",
        ),
        ("amount>=0", "amount >= (0)::numeric"),
    ],
)
def test_expression_accepts_only_documented_pg_deparse(left, right):
    """括弧の構造を保ち、PGの既知literal注記だけを揃える。"""
    assert current._expression(left) == current._expression(right)


@pytest.mark.parametrize(
    "bad",
    [
        "a=1 OR (b=2 AND c=3)",
        "a=1 AND (b=3 OR c=3)",
        "a=1 AND (b=2 OR c=3)::boolean",
        "a=1 AND (b=2 OR c=3) OR true",
    ],
)
def test_expression_does_not_ignore_precedence_types_or_values(bad):
    """括弧・cast・値を捨てたtoken一致へ緩めない。"""
    assert current._expression("a=1 AND (b=2 OR c=3)") != current._expression(bad)


@pytest.mark.parametrize("bad", ["a ; SELECT 1", "a @> b", "a IS DISTINCT FROM b"])
def test_expression_unknown_syntax_is_closed(bad):
    """未対応構文は推定で同一化しない。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._expression(bad)


def test_old_and_stats_models_are_closed_nine_and_fifty_four():
    """既6表を落とさず、新3表54列の型元だけを利用する。"""
    tables = current._tables()
    assert len(tables) == 9
    assert [t.name for t in tables] == [
        "first_ball_write_admissions",
        "ordinary_pitch_checkpoints",
        "ordinary_pitch_history",
        "ordinary_pitch_write_admissions",
        "stats_fact_versions",
        "stats_primitive_facts",
        "stats_primitive_sources",
        "writer_admissions",
        "writer_bindings",
    ]
    stats = [t for t in tables if t.name.startswith("stats_")]
    assert [len(t.c) for t in stats] == [20, 9, 25]
    for table in stats:
        constraints = current._expected_constraints(table)
        assert constraints and all(row[-4] is True for row in constraints)


def test_current_result_never_publishes_or_accepts_other_revision():
    """版と公開フラグの値域を閉じる。"""
    assert current.CurrentProductStartupResult().publishable is False
    for kwargs in (
        {"publishable": True},
        {"completed_revision": "0039_ordinary_pitch_storage"},
    ):
        with pytest.raises(current.CurrentProductStartupError):
            current.CurrentProductStartupResult(**cast(Any, kwargs))


def test_advance_preserves_old_stage_and_module_attribute_seed_hook(monkeypatch):
    """旧各検査を実0039まで呼び、差替え可能な既seed hookを維持する。"""
    trace = []
    names = [
        "_require_same_database",
        "_require_s0",
        "_apply_placement",
        "_require_placed_state",
        "_apply_epoch",
        "_require_epoch_state",
        "_apply_initial_storage",
        "_require_initial_state",
        "_apply_writer_storage",
        "_require_writer_state",
    ]
    for name in names:
        monkeypatch.setattr(
            current.legacy, name, lambda *a, n=name, **kw: trace.append(n)
        )

    @contextmanager
    def connect(dsn):
        trace.append("connect")
        yield object()

    monkeypatch.setattr(current.psycopg, "connect", connect)
    monkeypatch.setattr(
        current,
        "apply_product_authz_before_rule_placement",
        lambda c: trace.append("pre-rule"),
    )
    monkeypatch.setattr(
        current,
        "_finish_current",
        lambda *a: trace.append("finish") or current.CurrentProductStartupResult(),
    )
    result = current.advance_current_product_from_s0(
        owner_dsn="owner", applicator_dsn="admin"
    )
    assert trace == [names[0], names[1], "connect", "pre-rule", *names[2:], "finish"]
    assert result == current.CurrentProductStartupResult()


@pytest.mark.parametrize(
    "at",
    [
        "_require_same_database",
        "_require_s0",
        "_apply_placement",
        "_require_placed_state",
        "_apply_epoch",
        "_require_epoch_state",
        "_apply_initial_storage",
        "_require_initial_state",
        "_apply_writer_storage",
        "_require_writer_state",
    ],
)
def test_any_old_stage_failure_never_reaches_current_or_success(monkeypatch, at):
    """既段階の失敗を成功へ補完しない。"""
    trace = []
    for name in [
        "_require_same_database",
        "_require_s0",
        "_apply_placement",
        "_require_placed_state",
        "_apply_epoch",
        "_require_epoch_state",
        "_apply_initial_storage",
        "_require_initial_state",
        "_apply_writer_storage",
        "_require_writer_state",
    ]:

        def call(*args, n=name, **kwargs):
            trace.append(n)
            if n == at:
                raise RuntimeError("stage rejected")

        monkeypatch.setattr(current.legacy, name, call)

    @contextmanager
    def connect(_dsn):
        yield object()

    monkeypatch.setattr(current.psycopg, "connect", connect)
    monkeypatch.setattr(
        current, "apply_product_authz_before_rule_placement", lambda c: None
    )
    monkeypatch.setattr(
        current, "_finish_current", lambda *a: pytest.fail("current reached")
    )
    with pytest.raises(RuntimeError, match="stage rejected"):
        current.advance_current_product_from_s0(
            owner_dsn="owner", applicator_dsn="admin"
        )
    assert trace[-1] == at


def test_selected_helper_preserves_old_all_operation_outputs():
    """固定Gitの抽出前算法と全生成SQL/手順/拒否を比較する。"""
    import subprocess
    import sys
    from types import ModuleType

    from pitchlog.authz import product_provisioning as product

    root = product._REPOSITORY_ROOT
    # root採用前の正当Gitを原典にし、現在木から期待算法を採取しない。
    original = subprocess.check_output(
        ["git", "show", "363e1bf0:backend/src/pitchlog/authz/product_provisioning.py"],
        cwd=root,
    )
    old = ModuleType("_current_original_provisioning")
    old.__file__ = product.__file__
    sys.modules[old.__name__] = old
    exec(compile(original, "<immutable-original-provisioning>", "exec"), old.__dict__)
    old.__dict__["_REPOSITORY_ROOT"] = root
    for operation in product.ProductOperation:
        old_operation = old.ProductOperation(operation.value)
        try:
            expected = old._build_operation_statements(old_operation)
        except product.ProductProvisioningError:
            raise AssertionError("元モジュールの型混同") from None
        except Exception as error:
            with pytest.raises(product.ProductProvisioningError) as caught:
                product._build_operation_statements(operation)
            assert str(caught.value) == str(error)
        else:
            actual = product._build_operation_statements(operation)
            assert actual[0] == expected[0]
            assert [(r.sequence, r.sql) for r in actual[1]] == [
                (r.sequence, r.sql) for r in expected[1]
            ]


@pytest.mark.parametrize("kind", ["unknown", True, None, 1])
def test_selected_helper_refuses_caller_defined_operation(kind):
    """任意operationや真偽値を受け付けない。"""
    from pitchlog.authz import product_provisioning as product

    with pytest.raises(product.ProductProvisioningError):
        product._selected_product_ddl(kind)


def test_pre_full_expected_uses_exact_selected_declarations():
    """要素不足をsubset成功で補完せず既選択の閉集合を取得する。"""
    functions, schemas, policies, table_acl, columns, _, _ = (
        current._pre_full_expected()
    )
    assert "sync_fence" in schemas and "stats_api" not in schemas
    assert not any(key[0] == "stats_api" for key in functions)
    assert not any(key[0] == "sync_fence" for key in policies)
    assert not any(key[0] == "sync_fence" for key in table_acl | columns)


@pytest.mark.parametrize("bad", ["unknown", "partial", "extra"])
def test_pre_full_unknown_partial_or_extra_grants_are_rejected(monkeypatch, bad):
    """部分適用や余剰を正規pre-fullへ読み替えない。"""
    expected = (
        (
            "sync_fence",
            "stats_primitive_facts",
            "pitchlog_sync_binding_fn_owner",
            "SELECT",
            False,
        ),
    )
    actual = (
        () if bad == "unknown" else (expected if bad == "partial" else (("forged",),))
    )
    report = SimpleNamespace(
        checked_ids=tuple(current._pre_full_catalog_pairs()),
        ok=False,
        violations=[
            SimpleNamespace(
                check_id="unknown" if bad == "unknown" else "PRODUCT-CATALOG:TABLE-ACL",
                expected=expected,
                actual=actual,
            )
        ],
    )
    monkeypatch.setattr(current, "_catalog", lambda _: report)
    with pytest.raises(current.CurrentProductStartupError):
        current._require_pre_or_full_catalog(object())


def _structural_connection(fault=None):
    """型モデル原典をcatalog観測doubleへ投影し、比較対象だけを故障させる。"""
    from sqlalchemy import CheckConstraint
    from sqlalchemy.dialects.postgresql import dialect

    tables = {t.fullname: t for t in current._tables()}

    class Cursor:
        def execute(self, statement, params=None):
            self.sql, self.params = statement, params

        def fetchall(self):
            if "SELECT n.nspname,r.rolname" in self.sql:
                return [
                    (
                        "sync_fence",
                        "foreign" if fault == "schema_owner" else "pitchlog_owner",
                    )
                ]
            if "c.relrowsecurity" in self.sql:
                rows = [(t.name, "pitchlog_owner", True, True) for t in tables.values()]
                if fault == "table_extra":
                    rows.append(("unknown", "pitchlog_owner", True, True))
                if fault == "table_missing":
                    rows.pop()
                if fault == "table_owner":
                    rows[0] = (rows[0][0], "foreign", True, True)
                if fault == "rls":
                    rows[0] = (*rows[0][:2], False, True)
                if fault == "force_rls":
                    rows[0] = (*rows[0][:3], False)
                return rows
            assert self.params is not None
            table = tables[self.params[0]]
            target = table.name == "stats_fact_versions"
            if "a.attnum>0" in self.sql:
                rows: list[Any] = [
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
                fields = {
                    "column_type": (1, "integer"),
                    "column_null": (2, False),
                    "identity": (3, "a"),
                    "generated": (4, "s"),
                    "default": (5, "0"),
                }
                if target and fault in fields:
                    index, value = fields[fault]
                    row = list(rows[0])
                    row[index] = value
                    rows[0] = tuple(row)
                if target and fault == "column_order":
                    rows[0], rows[1] = rows[1], rows[0]
                if target and fault == "column_missing":
                    rows.pop()
                return rows
            if "pg_get_constraintdef" in self.sql:
                rows = [
                    r for r in current.legacy._WRITER_CONSTRAINTS if r[0] == table.name
                ]
                if fault == "old_constraint" and table.name == "writer_bindings":
                    rows = rows[:-1]
                return rows
            checks = {
                x.name: str(x.sqltext)
                for x in table.constraints
                if isinstance(x, CheckConstraint)
            }
            rows = []
            for fields in current._expected_constraints(table):
                row = list(fields)
                row[1] = row[1] or "automatic_name"
                row[2], row[4] = list(row[2]), list(row[4])
                row[6] = checks[row[1]] if row[0] == "c" else None
                if target and fault == "check" and row[0] == "c":
                    row[6] = "true"
                if target and fault == "fk_action" and row[0] == "f":
                    row[5] = "c"
                if target and fault == "fk_match" and row[0] == "f":
                    row[8] = "f"
                if target and fault == "not_valid":
                    row[-4] = False
                if target and fault == "deferrable":
                    row[-2] = True
                rows.append(tuple(row))
            if target and fault == "constraint_extra":
                rows.append(rows[0])
            return rows

    cursor = Cursor()

    @contextmanager
    def context():
        yield cursor

    return SimpleNamespace(cursor=context)


def test_structural_all_nine_tables_and_model_constraints_positive():
    """PG成功を代用せず、全閉比較への供給形だけを確認する。"""
    current._check_current_structure(_structural_connection())


@pytest.mark.parametrize(
    "fault",
    [
        "schema_owner",
        "table_extra",
        "table_missing",
        "table_owner",
        "rls",
        "force_rls",
        "column_type",
        "column_null",
        "identity",
        "generated",
        "default",
        "column_order",
        "column_missing",
        "old_constraint",
        "check",
        "fk_action",
        "fk_match",
        "not_valid",
        "deferrable",
        "constraint_extra",
    ],
)
def test_structural_comparison_refuses_every_changed_field(fault):
    """旧制約と新列/PKFKCHECK全属性の不足・余剰・変更を拒否する。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._check_current_structure(_structural_connection(fault))


@pytest.mark.parametrize(
    "fault", [None, "one_full", "extra", "unknown", "missing_check"]
)
def test_pre_full_requires_one_complete_profile_not_mix(monkeypatch, fault):
    """違反のないfull分類が混じる部分適用もpre-fullとして許さない。"""
    pairs = current._pre_full_catalog_pairs()
    violations = [
        SimpleNamespace(check_id=key, expected=full, actual=pre)
        for key, (full, pre) in pairs.items()
        if full != pre
    ]
    assert violations
    checked = list(pairs)
    if fault == "one_full":
        violations.pop()
    elif fault == "extra":
        first = violations[0]
        first.actual = (*first.actual, ("forged",))
    elif fault == "unknown":
        violations.append(SimpleNamespace(check_id="UNKNOWN", expected=(), actual=(1,)))
    elif fault == "missing_check":
        checked.pop()
    report = SimpleNamespace(ok=False, checked_ids=checked, violations=violations)
    monkeypatch.setattr(current, "_catalog", lambda _: report)
    if fault is None:
        assert current._require_pre_or_full_catalog(object()) == "pre-full"
    else:
        with pytest.raises(current.CurrentProductStartupError):
            current._require_pre_or_full_catalog(object())


def _index_connection(fault=None):
    """既型metadataのindex観測を供給し、比較拒否を独立に変異させる。"""
    from sqlalchemy import PrimaryKeyConstraint, UniqueConstraint

    tables = {t.fullname: t for t in current._tables()}

    class Cursor:
        def execute(self, _sql, params):
            self.name = params[0]

        def fetchall(self):
            if self.name == "public.admin_vocabularies":
                rows = [
                    (
                        "pk_admin_vocabularies",
                        True,
                        True,
                        True,
                        True,
                        True,
                        True,
                        "btree",
                        ["key"],
                        ["default"],
                        [0],
                        None,
                        None,
                        "p",
                        ["text_ops"],
                        False,
                    ),
                    (
                        "ix_admin_vocabularies_batted_ball_key_c",
                        False,
                        False,
                        True,
                        True,
                        True,
                        True,
                        "btree",
                        ["key"],
                        ["C"],
                        [0],
                        None,
                        "category='batted_ball' AND disabled=false",
                        None,
                        ["text_ops"],
                        False,
                    ),
                ]
                target = list(rows[1])
                mutations = {
                    "wrong_collation": (9, ["default"]),
                    "wrong_key": (8, ["category"]),
                    "wrong_predicate": (12, "category='batted_ball' OR disabled=false"),
                    "cast_expression": (11, "key::varchar"),
                    "wrong_method": (7, "hash"),
                    "invalid": (3, False),
                    "not_ready": (4, False),
                    "unique": (1, True),
                    "desc": (10, [1]),
                    "wrong_opclass": (14, ["text_pattern_ops"]),
                    "nulls_distinct": (15, True),
                }
                if fault in mutations:
                    field, value = mutations[fault]
                    target[field] = value
                    rows[1] = tuple(target)
                if fault == "missing":
                    rows.pop()
                if fault == "extra":
                    rows.append(tuple(["unknown", *rows[1][1:]]))
                return rows
            table = tables[self.name]
            rows = []
            for con in table.constraints:
                if isinstance(con, (PrimaryKeyConstraint, UniqueConstraint)):
                    cols = list(con.columns)
                    primary = isinstance(con, PrimaryKeyConstraint)
                    rows.append(
                        (
                            "automatic",
                            True,
                            primary,
                            True,
                            True,
                            True,
                            True,
                            "btree",
                            [c.name for c in cols],
                            [
                                "default" if current._opclass(c) == "text_ops" else None
                                for c in cols
                            ],
                            [0] * len(cols),
                            None,
                            None,
                            "p" if primary else "u",
                            [current._opclass(c) for c in cols],
                            False,
                        )
                    )
            for index in table.indexes:
                cols = [cast(Any, c) for c in index.expressions]
                pred = index.dialect_options["postgresql"]["where"]
                rows.append(
                    (
                        index.name,
                        bool(index.unique),
                        False,
                        True,
                        True,
                        True,
                        True,
                        "btree",
                        [c.name for c in cols],
                        [
                            "default" if current._opclass(c) == "text_ops" else None
                            for c in cols
                        ],
                        [0] * len(cols),
                        None,
                        None if pred is None else str(pred),
                        None,
                        [current._opclass(c) for c in cols],
                        False,
                    )
                )
            if fault == "old_index_missing" and table.name == "writer_bindings":
                rows.pop()
            return rows

    cursor = Cursor()

    @contextmanager
    def context():
        yield cursor

    return SimpleNamespace(cursor=context)


def test_all_indexes_positive_preserves_old_and_new_shapes():
    """新3indexだけでなく旧6表と0040の全indexを比較する。"""
    current._check_current_indexes(_index_connection())


@pytest.mark.parametrize(
    "fault",
    [
        "wrong_collation",
        "wrong_key",
        "wrong_predicate",
        "cast_expression",
        "wrong_method",
        "invalid",
        "not_ready",
        "unique",
        "desc",
        "wrong_opclass",
        "nulls_distinct",
        "missing",
        "extra",
        "old_index_missing",
    ],
)
def test_all_index_shapes_reject_changes(fault):
    """indexの見かけの名前一致だけで型・対象・有効性を承認しない。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._check_current_indexes(_index_connection(fault))


def test_current41_finish_never_calls_old_validators_or_migration(monkeypatch):
    """0041再開は新全構造/full判定だけで、旧0039markerを偽装しない。"""
    trace = []

    @contextmanager
    def connect(_dsn):
        yield object()

    monkeypatch.setattr(current.psycopg, "connect", connect)
    monkeypatch.setattr(current, "_revision", lambda _: current.CURRENT_REVISION)
    for name in [
        "_check_current_structure",
        "_check_current_indexes",
        "_check_current_rules",
        "_check_current_public_storage",
    ]:
        monkeypatch.setattr(current, name, lambda _, n=name: trace.append(n))
    monkeypatch.setattr(
        current, "_require_pre_or_full_catalog", lambda _: trace.append("pre-full")
    )
    monkeypatch.setattr(current, "_catalog", lambda _: SimpleNamespace(ok=True))
    monkeypatch.setattr(
        current, "apply_product_authz_ddl", lambda _: trace.append("full-apply")
    )
    monkeypatch.setattr(
        current, "_apply_current_storage", lambda _: pytest.fail("migration")
    )
    monkeypatch.setattr(
        current.legacy, "_require_writer_state", lambda _: pytest.fail("old41")
    )
    assert (
        current._finish_current("owner", "admin")
        == current.CurrentProductStartupResult()
    )
    assert trace.index("pre-full") < trace.index("full-apply")
    assert (
        trace.count("_check_current_structure")
        == trace.count("_check_current_public_storage")
        == 2
    )


@pytest.mark.parametrize(
    "phase",
    [
        "_check_current_structure",
        "_check_current_indexes",
        "_check_current_rules",
        "_check_current_public_storage",
        "_require_pre_or_full_catalog",
    ],
)
def test_current41_failure_never_reaches_full_repair(monkeypatch, phase):
    """実観測の失敗を全認可適用で補修しない。"""

    @contextmanager
    def connect(_dsn):
        yield object()

    monkeypatch.setattr(current.psycopg, "connect", connect)
    monkeypatch.setattr(current, "_revision", lambda _: current.CURRENT_REVISION)
    for name in [
        "_check_current_structure",
        "_check_current_indexes",
        "_check_current_rules",
        "_check_current_public_storage",
        "_require_pre_or_full_catalog",
    ]:

        def call(_, n=name):
            if n == phase:
                raise current.CurrentProductStartupError("closed")

        monkeypatch.setattr(current, name, call)
    monkeypatch.setattr(
        current, "apply_product_authz_ddl", lambda _: pytest.fail("repair")
    )
    with pytest.raises(current.CurrentProductStartupError):
        current._finish_current("owner", "admin")


def test_pre_full_builtin_execute_is_exact_selected_declaration(monkeypatch):
    """保留されたbinding ownerだけを除き、未知主体や欠落を受け入れない。"""
    from types import SimpleNamespace

    check = "PRODUCT-CATALOG:BUILTIN-ADDITIONAL-EXECUTE"
    pairs = current._pre_full_catalog_pairs()
    full, pre = pairs[check]
    assert {row[3] for row in full} == {
        "pitchlog_rg1_control_owner",
        "pitchlog_ledger_identity_owner",
        "pitchlog_sync_binding_fn_owner",
    }
    assert {row[3] for row in pre} == {
        "pitchlog_rg1_control_owner",
        "pitchlog_ledger_identity_owner",
    }
    violations = [
        SimpleNamespace(check_id=key, expected=f, actual=p)
        for key, (f, p) in pairs.items()
        if f != p
    ]
    report = SimpleNamespace(
        ok=False,
        checked_ids=tuple(pairs),
        violations=tuple(violations),
    )
    monkeypatch.setattr(current, "_catalog", lambda connection: report)
    assert current._require_pre_or_full_catalog(object()) == "pre-full"
    base = next(v for v in violations if v.check_id == check)
    for bad in (
        (),
        full,
        pre
        + (("pg_catalog", "pg_control_system", "", "pitchlog_app", "EXECUTE", False),),
    ):
        base.actual = bad
        with pytest.raises(current.CurrentProductStartupError):
            current._require_pre_or_full_catalog(object())
    base.actual = pre
