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
        (
            "transaction_id::numeric<=18446744073709551615",
            "transaction_id::numeric <= '18446744073709551615'::numeric",
        ),
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


@pytest.mark.parametrize(
    "bad",
    [
        "'18446744073709551616'::numeric",
        "'18446744073709551615'",
        "'18446744073709551615'::text",
        "'18446744073709551615'::bigint",
        "'18446744073709551615.1'::numeric",
        "'NaN'::numeric",
        "'Infinity'::numeric",
    ],
)
def test_numeric_deparse_preserves_limit_value_and_cast(bad):
    """実PGの整数注記だけを揃え、上限値・型・非有限値を捨てない。"""
    expected = current._expression("transaction_id::numeric<=18446744073709551615")
    assert current._expression("transaction_id::numeric<=" + bad) != expected


@pytest.mark.parametrize("bad", ["a ; SELECT 1", "a @> b", "a IS DISTINCT FROM b"])
def test_expression_unknown_syntax_is_closed(bad):
    """未対応構文は推定で同一化しない。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._expression(bad)


def test_current_models_are_closed_fourteen_with_retirement():
    """既12表を落とさず、交代receiptの型元を加える。"""
    tables = current._tables()
    assert len(tables) == 14
    assert [t.name for t in tables] == [
        "attempt_retirements",
        "first_ball_write_admissions",
        "game_lifecycle_heads",
        "lifecycle_write_admissions",
        "nonplay_write_admissions",
        "ordinary_pitch_checkpoints",
        "ordinary_pitch_history",
        "ordinary_pitch_write_admissions",
        "stats_fact_versions",
        "stats_primitive_facts",
        "stats_primitive_sources",
        "substitution_write_receipts",
        "writer_admissions",
        "writer_bindings",
    ]
    receipt = next(t for t in tables if t.name == "substitution_write_receipts")
    assert len(receipt.c) == 10
    assert {r[1] for r in current._expected_constraints(receipt) if r[0] == "f"} == {
        "substitution_write_receipts_tenant_id_attempt_id_phase_id_fkey",
        "substitution_write_receipts_tenant_id_checkpoint_id_fkey",
        "substitution_write_receipts_tenant_id_game_id_fkey",
        "substitution_write_receipts_tenant_id_source_event_id_fkey",
    }
    assert len(next(t for t in tables if t.name == "nonplay_write_admissions").c) == 43
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


def _structural_connection(fault=None, target_name="stats_fact_versions"):
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
            target = table.name == target_name
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
                if target and fault == "constraint_name" and row[0] == "f":
                    row[1] = "foreign_constraint_name"
                if target and fault == "fk_action" and row[0] == "f":
                    row[5] = "c"
                if target and fault == "fk_match" and row[0] == "f":
                    row[8] = "f" if row[8] != "f" else "s"
                if target and fault == "not_valid":
                    row[-4] = False
                if target and fault == "deferrable":
                    row[-2] = not row[-2]
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
    "fault", ["constraint_name", "fk_action", "fk_match", "not_valid", "deferrable"]
)
def test_substitution_receipt_refuses_changed_foreign_key(fault):
    """交代印の実FK名・参照属性・遅延属性を省略せず比較する。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._check_current_structure(
            _structural_connection(fault, target_name="substitution_write_receipts")
        )


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
    monkeypatch.setattr(current, "_check_attempt_retirement_guards", lambda *_: None)
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


def test_pre_full_keeps_only_the_verified_migration_guards(monkeypatch):
    """0036の関数と既投影identity triggerだけをpre-fullに含める。"""
    functions, *_ = current._pre_full_expected()
    assert ("public", "protect_initial_right_storage", "") in functions
    assert ("public", "protect_nonplay_admission", "") in functions
    pairs = current._pre_full_catalog_pairs()
    np_key = "PRODUCT-CATALOG:NONPLAY-STORAGE-TRIGGERS"
    from pitchlog.authz.nonplay_storage_profile import trigger_expectations

    assert pairs[np_key] == (trigger_expectations(), trigger_expectations())
    first_key = "PRODUCT-CATALOG:FIRST-BALL-TRIGGERS"
    play_key = "PRODUCT-CATALOG:PLAY-PREFIX-TRIGGERS"
    first = pairs[first_key][1]
    play = pairs[play_key][1]
    assert len(first) == len(play) == 1
    assert first[0][0] == "trg_play_rows_projection_identity_immutable"
    assert play[0] == ("play_rows", *first[0])
    violations = [
        SimpleNamespace(check_id=key, expected=full, actual=pre)
        for key, (full, pre) in pairs.items()
        if full != pre
    ]
    report = SimpleNamespace(
        ok=False, checked_ids=tuple(pairs), violations=tuple(violations)
    )
    monkeypatch.setattr(current, "_catalog", lambda connection: report)
    assert current._require_pre_or_full_catalog(object()) == "pre-full"
    for key in (first_key, play_key):
        item = next(v for v in violations if v.check_id == key)
        original = item.actual
        for bad in ((), pairs[key][0], original + original):
            item.actual = bad
            with pytest.raises(current.CurrentProductStartupError):
                current._require_pre_or_full_catalog(object())
        item.actual = original


def test_current_finish_closes_read_transaction_before_idle_authz_apply(monkeypatch):
    """全事前read接続を終結し、別IDLE接続で既適用器を実行する。"""
    monkeypatch.setattr(current, "_check_attempt_retirement_guards", lambda *_: None)
    trace = []
    connections = []

    @contextmanager
    def connect(_dsn):
        connection = SimpleNamespace(dirty=False, closed=False, number=len(connections))
        connections.append(connection)
        try:
            yield connection
        finally:
            connection.closed = True
            trace.append(("closed", connection.number))

    def read(connection, name):
        assert not connection.closed
        connection.dirty = True
        trace.append((name, connection.number))

    monkeypatch.setattr(current.psycopg, "connect", connect)

    def revision(connection):
        read(connection, "revision")
        return current.CURRENT_REVISION

    monkeypatch.setattr(current, "_revision", revision)
    names = [
        "_check_current_structure",
        "_check_current_indexes",
        "_check_current_rules",
        "_check_current_public_storage",
        "_require_pre_or_full_catalog",
    ]
    for name in names:
        monkeypatch.setattr(
            current, name, lambda connection, n=name: read(connection, n)
        )

    def apply(connection):
        assert not connection.dirty and not connection.closed
        assert connections[1].closed
        assert [name for name, number in trace if number == 1] == [*names, "closed"]
        trace.append(("apply", connection.number))

    monkeypatch.setattr(current, "apply_product_authz_ddl", apply)

    def catalog(connection):
        read(connection, "catalog")
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(current, "_catalog", catalog)
    assert (
        current._finish_current("owner", "admin")
        == current.CurrentProductStartupResult()
    )
    assert len(connections) == 4 and all(c.closed for c in connections)
    assert ("apply", 2) in trace and ("catalog", 3) in trace


def _snapshot_profile_asset(profile):
    """実DB出力から作らず、既3/新currentの全schema・私有表を列挙する。"""
    legacy = [
        "public",
        "authz_private",
        "authn",
        "authn_crypto",
        "rg1_api",
        "rg1_control",
        "pitchlog_ledger_observer",
        "initial_right_api",
    ]
    schemas = list(legacy)
    tables = []
    if profile != "legacy":
        schemas += ["sync_fence", "sync_fence_api", "sync_right_api"]
        tables += [
            "writer_bindings",
            "writer_admissions",
            "first_ball_write_admissions",
            "ordinary_pitch_checkpoints",
            "ordinary_pitch_write_admissions",
            "ordinary_pitch_history",
        ]
    if profile in ("vocabulary", "current"):
        schemas.append("recording_vocab_api")
    if profile == "current":
        schemas.append("stats_api")
        tables += [
            "stats_fact_versions",
            "stats_primitive_sources",
            "stats_primitive_facts",
        ]
    owners = ["pitchlog_rg1_control_owner", "pitchlog_ledger_identity_owner"]
    if tables:
        owners.append("pitchlog_sync_binding_fn_owner")
    return {
        "schemas": [{"schema_name": name} for name in schemas],
        "tables": [{"table_id": name, "schema_name": "sync_fence"} for name in tables],
        "acl_expectations": [
            {
                "acl_id": f"ACL:pg_catalog:pg_control_system():{owner}",
                "object_kind": "builtin_function",
                "object_schema": "pg_catalog",
                "object_id": "pg_control_system",
                "profile": "additional_builtin_execute",
                "grantee_role_id": owner,
                "privilege_ids": ["EXECUTE"],
                "grant_option": False,
            }
            for owner in sorted(owners)
        ],
    }


@pytest.mark.parametrize(
    "profile,schema_count,private_count",
    [
        ("legacy", 8, 0),
        ("private", 11, 6),
        ("vocabulary", 12, 6),
        ("current", 13, 9),
    ],
)
def test_snapshot_profile_preserves_old_three_and_one_full_current(
    profile, schema_count, private_count
):
    """全4個の有限対だけを許し、宣言の元順序と全名を保存する。"""
    import db_fixtures as fixtures

    asset = _snapshot_profile_asset(profile)
    schemas, rows = fixtures._snapshot_product_profile(asset)
    assert len(schemas) == schema_count and len(rows) == private_count
    assert schemas == tuple(row["schema_name"] for row in asset["schemas"])
    assert rows == tuple(
        (row["table_id"], row["schema_name"]) for row in asset["tables"]
    )
    asset["schemas"].reverse()
    asset["tables"].reverse()
    reversed_schemas, reversed_rows = fixtures._snapshot_product_profile(asset)
    assert reversed_schemas == schemas[::-1] and reversed_rows == rows[::-1]


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-schema",
        "missing-schema",
        "duplicate-schema",
        "schema-type",
        "schema-missing-name",
        "schema-section-type",
        "schema-row-type",
        "missing-stats-one",
        "missing-stats-two",
        "missing-stats-all",
        "duplicate-table",
        "unknown-table",
        "wrong-table-schema",
        "table-name-type",
        "table-schema-type",
        "table-missing-name",
        "table-row-type",
        "table-section-type",
        "stats-without-vocabulary",
        "stats-without-private",
        "new-tables-old-schema",
        "new-schema-old-tables",
        "duplicate-stats-table",
    ],
)
def test_snapshot_profile_refuses_incomplete_or_forged_current(mutation):
    """statsの一部供給や別schema・型補修を正常profileへ推測しない。"""
    import db_fixtures as fixtures

    asset = _snapshot_profile_asset("current")
    if mutation == "unknown-schema":
        asset["schemas"].append({"schema_name": "unknown"})
    elif mutation == "missing-schema":
        asset["schemas"].pop(0)
    elif mutation == "duplicate-schema":
        asset["schemas"].append(dict(asset["schemas"][0]))
    elif mutation == "schema-type":
        asset["schemas"][0]["schema_name"] = 1
    elif mutation == "schema-missing-name":
        del asset["schemas"][0]["schema_name"]
    elif mutation == "schema-section-type":
        asset["schemas"] = ()
    elif mutation == "schema-row-type":
        asset["schemas"][0] = "public"
    elif mutation in ("missing-stats-one", "missing-stats-two", "missing-stats-all"):
        count = {
            "missing-stats-one": 1,
            "missing-stats-two": 2,
            "missing-stats-all": 3,
        }[mutation]
        del asset["tables"][-count:]
    elif mutation == "duplicate-table":
        asset["tables"].append(dict(asset["tables"][0]))
    elif mutation == "unknown-table":
        asset["tables"][-1]["table_id"] = "unknown"
    elif mutation == "wrong-table-schema":
        asset["tables"][-1]["schema_name"] = "stats_api"
    elif mutation == "table-name-type":
        asset["tables"][-1]["table_id"] = 1
    elif mutation == "table-schema-type":
        asset["tables"][-1]["schema_name"] = 1
    elif mutation == "table-missing-name":
        del asset["tables"][-1]["table_id"]
    elif mutation == "table-row-type":
        asset["tables"][-1] = "stats_primitive_facts"
    elif mutation == "table-section-type":
        asset["tables"] = ()
    elif mutation == "stats-without-vocabulary":
        asset["schemas"] = [
            r for r in asset["schemas"] if r["schema_name"] != "recording_vocab_api"
        ]
    elif mutation == "stats-without-private":
        asset["schemas"] = [
            r for r in asset["schemas"] if r["schema_name"] != "sync_right_api"
        ]
    elif mutation == "new-tables-old-schema":
        asset["schemas"] = _snapshot_profile_asset("vocabulary")["schemas"]
    elif mutation == "new-schema-old-tables":
        asset["tables"] = _snapshot_profile_asset("vocabulary")["tables"]
    elif mutation == "duplicate-stats-table":
        asset["tables"].append(dict(asset["tables"][-1]))
    with pytest.raises(AssertionError):
        fixtures._snapshot_product_profile(asset)


@pytest.mark.parametrize("profile", ["legacy", "private", "vocabulary", "current"])
def test_original_snapshot_uses_closed_profile_and_every_query(monkeypatch, profile):
    """元snapshotの全13取得とschema/私有表引数に新実値が流れることを観測する。"""
    from dataclasses import fields

    import db_fixtures as fixtures

    asset = _snapshot_profile_asset(profile)
    trace = []

    class Connection:
        @contextmanager
        def cursor(self):
            yield object()

    def fetch(cursor, query, params=()):
        assert cursor is not None
        trace.append((query, params))
        return (("snapshot-query-observation", len(trace)),)

    monkeypatch.setattr(fixtures, "_fetch_snapshot_rows", fetch)
    result = fixtures._snapshot_product_catalog(
        cast(Any, Connection()), ("test_role",), asset=asset
    )
    assert len(trace) == len(fields(result)) == 13
    assert [getattr(result, f.name) for f in fields(result)] == [
        (("snapshot-query-observation", n),) for n in range(1, 14)
    ]
    schema_names = [r["schema_name"] for r in asset["schemas"]]
    table_names = [r["table_id"] for r in asset["tables"]]
    assert sum(params == (schema_names,) for _, params in trace) == 4
    assert sum(params == (table_names,) for _, params in trace) == 4
    function_acl = trace[9][1]
    assert function_acl == (schema_names, ["pg_control_system"])
    if profile == "current":
        assert all(
            name in table_names
            for name in [
                "stats_fact_versions",
                "stats_primitive_sources",
                "stats_primitive_facts",
            ]
        )

    def rejected(_asset):
        raise AssertionError("closed-profile-sentinel")

    monkeypatch.setattr(fixtures, "_snapshot_product_profile", rejected)
    with pytest.raises(AssertionError, match="closed-profile-sentinel"):
        fixtures._snapshot_product_catalog(
            cast(Any, Connection()), ("test_role",), asset=asset
        )
    assert len(trace) == 13


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "wrong-role", "grant", "wrong-privilege"]
)
def test_snapshot_keeps_old_builtin_exact_rejection(monkeypatch, mutation):
    """新schema profileが既builtin3主体の閉検査を迂回しない。"""
    import db_fixtures as fixtures

    asset = _snapshot_profile_asset("current")
    if mutation == "missing":
        asset["acl_expectations"].pop()
    elif mutation == "extra":
        asset["acl_expectations"].append(dict(asset["acl_expectations"][0]))
    elif mutation == "wrong-role":
        asset["acl_expectations"][0]["grantee_role_id"] = "unknown"
    elif mutation == "grant":
        asset["acl_expectations"][0]["grant_option"] = True
    elif mutation == "wrong-privilege":
        asset["acl_expectations"][0]["privilege_ids"] = ["SELECT"]
    with pytest.raises(AssertionError, match="builtin exact"):
        fixtures._snapshot_product_catalog(cast(Any, object()), (), asset=asset)


def test_nonplay_fk_full_and_deferred_flags_follow_actual_model():
    """元stats制約を保ち、非playのFULL/遅延をNO ACTIONへ潰さない。"""
    from sqlalchemy import ForeignKeyConstraint

    table = next(t for t in current._tables() if t.name == "nonplay_write_admissions")
    rows = {r[1]: r for r in current._expected_constraints(table) if r[0] == "f"}
    fks = {c.name: c for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert any(c.match == "FULL" for c in fks.values())
    assert any(c.deferrable is True and c.initially == "DEFERRED" for c in fks.values())
    for name, constraint in fks.items():
        row = rows[name]
        assert row[5] == row[7] == "a"
        assert row[8] == ("f" if constraint.match == "FULL" else "s")
        assert row[-2] is (constraint.deferrable is True)
        assert row[-1] is (constraint.initially == "DEFERRED")


@pytest.mark.parametrize("value", ["CASCADE wrong", "cascade", "UNKNOWN"])
def test_unknown_fk_actions_are_not_coerced(value):
    """未知actionを既定NO ACTIONへ補完しない。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._fk_action(value)


@pytest.mark.parametrize("value", ["PARTIAL", "full", "UNKNOWN"])
def test_unknown_fk_match_is_not_simple(value):
    """未採用MATCHをSIMPLEへ補完しない。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._fk_match(value)


def test_negative_regex_deparse_is_preserved_not_treated_as_positive():
    """実modelの!~だけを追加し、演算の符号を保持する。"""
    assert current._expression("value !~ '[0-9]'") == current._expression(
        "(value !~ '[0-9]'::text)"
    )
    assert current._expression("value !~ '[0-9]'") != current._expression(
        "value ~ '[0-9]'"
    )


def test_revision41_rejected_without_migration_or_repair(monkeypatch):
    """旧41全catalogの独立供給前は、未知partialを現42へ修復しない。"""

    class Cursor:
        def execute(self, sql):
            assert sql == "SELECT version_num FROM public.alembic_version"

        def fetchall(self):
            return [("0041_stats_fact_versions",)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    connection = SimpleNamespace(cursor=Cursor)
    with pytest.raises(current.CurrentProductStartupError, match="revision"):
        current._revision(connection)


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
        "check",
        "fk_action",
        "fk_match",
        "not_valid",
        "deferrable",
        "constraint_extra",
    ],
)
def test_nonplay_full_structure_refuses_each_changed_field(fault):
    """追加表を存在確認だけへ縮小せず、全属性の閉拒否を保つ。"""
    with pytest.raises(current.CurrentProductStartupError):
        current._check_current_structure(
            _structural_connection(fault, "nonplay_write_admissions")
        )


def _snapshot42_asset():
    from pitchlog.authz.nonplay_storage_profile import declaration

    asset = _snapshot_profile_asset("current")
    asset["tables"].append(
        {"table_id": "nonplay_write_admissions", "schema_name": "sync_fence"}
    )
    asset["functions"] = [declaration()]
    return asset


def test_snapshot42_preserves_full_old41_and_adds_only_closed_tenth_table():
    """旧9表を同じまま残し、新10表は正規内部guardとの対でだけ許す。"""
    import db_fixtures as fixtures

    old = fixtures._snapshot_product_profile(_snapshot_profile_asset("current"))
    new = fixtures._snapshot_product_profile(_snapshot42_asset())
    assert new[0] == old[0]
    assert new[1] == (*old[1], ("nonplay_write_admissions", "sync_fence"))


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "duplicate",
        "schema",
        "guard-missing",
        "guard-duplicate",
        "owner",
        "public-execute",
        "guard-bool",
    ],
)
def test_snapshot42_rejects_unknown_partial_table_or_guard(mutation):
    """新profileの欠落・余剰・owner/権限違いは旧41として救済しない。"""
    import db_fixtures as fixtures

    asset = _snapshot42_asset()
    if mutation == "missing":
        asset["tables"].pop()
    elif mutation == "extra":
        asset["tables"].append({"table_id": "unknown", "schema_name": "sync_fence"})
    elif mutation == "duplicate":
        asset["tables"].append(dict(asset["tables"][-1]))
    elif mutation == "schema":
        asset["tables"][-1]["schema_name"] = "public"
    elif mutation == "guard-missing":
        asset["functions"].clear()
    elif mutation == "guard-duplicate":
        asset["functions"].append(dict(asset["functions"][0]))
    elif mutation == "owner":
        asset["functions"][0]["owner_role_id"] = "pitchlog_app"
    elif mutation == "guard-bool":
        asset["functions"][0]["revoked_acl_expectations"][0]["grantable"] = 0
    else:
        asset["functions"][0]["acl_expectations"] = [
            {"grantee": "PUBLIC", "privilege": "EXECUTE", "grantable": False}
        ]
    with pytest.raises(AssertionError):
        fixtures._snapshot_product_profile(asset)
