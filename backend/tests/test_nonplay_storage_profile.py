"""0042の唯一guard原本・ACL-only適用・全trigger属性を検査する。"""

import ast
import copy

import pytest

from pitchlog.authz import first_ball_product as installer
from pitchlog.authz import nonplay_storage_profile as profile
from pitchlog.authz import product_catalog as catalog


def test_guard_body_and_all_attributes_come_from_unique_literal():
    """migrationを実行せず、唯一のAST literal全文に束縛する。"""
    tree = ast.parse(profile._MIGRATION.read_text())
    upgrade = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"
    )
    literals = [
        n.value.args[0].value
        for n in upgrade.body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.args[0], ast.Constant)
        and isinstance(n.value.args[0].value, str)
    ]
    sql = next(
        s for s in literals if "CREATE FUNCTION public.protect_nonplay_admission()" in s
    )
    details = profile.guard_details()
    assert details[:9] == (
        "public",
        "protect_nonplay_admission",
        "",
        "pitchlog_owner",
        False,
        "plpgsql",
        "trigger",
        "v",
        ("search_path=pg_catalog, pg_temp",),
    )
    assert details[9] == sql.split("$guard$")[1].strip()
    assert isinstance(details[9], str)
    assert len(details[9]) > 1800


def test_installer_only_changes_acl_never_creates_or_grants_guard():
    """適用器へ内部migration関数を登録し、作成・再作成・PUBLIC付与はしない。"""
    row = profile.declaration()
    assert installer.declaration("functions", profile.FUNCTION_ID) == row
    assert row["function_kind"] == "migration_trigger"
    assert row["owner_role_id"] == "pitchlog_owner"
    assert row["acl_expectations"] == []
    assert [r["grantee"] for r in row["revoked_acl_expectations"]] == [
        "PUBLIC",
        "pitchlog_app",
    ]
    canonical = installer.body("function", profile.FUNCTION_ID)
    assert canonical is not None
    assert "CREATE" not in canonical and "GRANT" not in canonical
    assert (
        installer.application_function_sql(profile.FUNCTION_ID, canonical) == canonical
    )
    assert profile.guard_details() in installer.function_details()
    with pytest.raises(ValueError):
        installer.application_function_sql(
            profile.FUNCTION_ID, canonical + "GRANT EXECUTE TO PUBLIC;"
        )


def test_duplicate_registration_preserves_all_existing_values(monkeypatch):
    """同IDを黙って上書きせず旧宣言・旧SQLを全値保持する。"""
    declarations, bodies = copy.deepcopy(installer.ADDITIONS), dict(installer.BODIES)
    monkeypatch.setattr(installer, "ADDITIONS", copy.deepcopy(declarations))
    monkeypatch.setattr(installer, "BODIES", dict(bodies))
    with pytest.raises(ValueError):
        installer._activate_nonplay_storage_guard()
    assert installer.ADDITIONS == declarations and installer.BODIES == bodies


@pytest.mark.parametrize(
    "mutation",
    ["definer", "owner", "grant", "timing", "table", "extra", "nonliteral", "python"],
)
def test_changed_migration_is_rejected_without_executing_it(
    tmp_path, monkeypatch, mutation
):
    """未知Python・任意関数・別owner/triggerを正規profileに補修しない。"""
    source = profile._MIGRATION.read_text()
    replacements = {
        "definer": (
            "RETURNS trigger LANGUAGE plpgsql SET",
            "RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET",
        ),
        "owner": (
            "ALTER FUNCTION public.protect_nonplay_admission() OWNER TO pitchlog_owner",
            "ALTER FUNCTION public.protect_nonplay_admission() OWNER TO pitchlog_app",
        ),
        "grant": (
            "REVOKE ALL ON FUNCTION public.protect_nonplay_admission()",
            "GRANT EXECUTE ON FUNCTION public.protect_nonplay_admission()",
        ),
        "timing": ("guard BEFORE INSERT", "guard AFTER INSERT"),
        "table": (
            "ON sync_fence.nonplay_write_admissions FOR EACH ROW",
            "ON public.play_rows FOR EACH ROW",
        ),
        "extra": (
            '    op.execute(\n        "ALTER FUNCTION',
            (
                '    op.execute("CREATE FUNCTION public.protect_nonplay'
                '_admission()")\n    op.execute(\n        "ALTER FUNCTION'
            ),
        ),
        "nonliteral": (
            '    op.execute(\n        "ALTER FUNCTION',
            '    op.execute(\n        unknown + "ALTER FUNCTION',
        ),
        "python": (
            "    op.execute(",
            '    raise RuntimeError("must not execute")\n    op.execute(',
        ),
    }
    old, new = replacements[mutation]
    assert old in source
    path = tmp_path / "migration.py"
    path.write_text(source.replace(old, new, 1))
    monkeypatch.setattr(profile, "_MIGRATION", path)
    with pytest.raises(ValueError):
        profile.guard_details()


def test_actual_catalog_query_and_expectation_are_wired():
    """未知triggerをfilterせず、既16属性を全て実catalogで観測する。"""
    from pitchlog.authz.first_ball_write_stamp import STAMP_TRIGGER_QUERY

    query = catalog._query_for_id(catalog.CatalogQueryId.NONPLAY_STORAGE_TRIGGERS)
    assert query == profile.trigger_query()
    assert "sync_fence.nonplay_write_admissions" in query
    assert "t.tgname<>" not in query
    assert query.replace(
        "sync_fence.nonplay_write_admissions", "public.play_rows"
    ) == STAMP_TRIGGER_QUERY.replace(
        "AND t.tgname<>'trg_play_prefix_30_project_after'", ""
    )
    expected = profile.trigger_expectations()
    assert [r[:2] for r in expected] == [
        ("trg_nonplay_admission_guard", 31),
        ("trg_nonplay_admission_no_truncate", 34),
    ]
    assert (
        catalog._actual_nonplay_storage_triggers(tuple((list(r),) for r in expected))
        == expected
    )
    assert "'protect_nonplay_admission'" in catalog._LIFECYCLE_FUNCTION_DETAILS_QUERY


@pytest.mark.parametrize("index", range(16))
def test_all_trigger_attributes_are_preserved_for_comparison(index):
    """一部属性の射影・無視をせず、変更をそのまま比較へ渡す。"""
    expected = profile.trigger_expectations()
    rows = [(list(r),) for r in expected]
    value = rows[0][0][index]
    rows[0][0][index] = (
        not value
        if type(value) is bool
        else value + 1
        if type(value) is int
        else ["unknown"]
        if type(value) is list
        else "unknown"
    )
    assert catalog._actual_nonplay_storage_triggers(tuple(rows)) != expected


@pytest.mark.parametrize("index", [1, 6, 8, 9, 10, 11, 12])
def test_bool_int_substitutions_cannot_be_silently_equal(index):
    """bool/intのPython同値を正規catalog値として受けない。"""
    rows = [(list(r),) for r in profile.trigger_expectations()]
    value = rows[0][0][index]
    rows[0][0][index] = int(value) if type(value) is bool else True
    with pytest.raises(catalog.ProductCatalogError):
        catalog._actual_nonplay_storage_triggers(tuple(rows))


@pytest.mark.parametrize("mutation", ["missing", "extra", "order"])
def test_trigger_set_and_order_are_not_filtered(mutation):
    """未知・欠落・逆順を正規集合へ丸めない。"""
    expected = profile.trigger_expectations()
    rows = [(list(r),) for r in expected]
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append((list(expected[0]),))
    else:
        rows.reverse()
    assert catalog._actual_nonplay_storage_triggers(tuple(rows)) != expected


def test_unapplication_never_restores_public_execute_for_new_internal_guard():
    """旧generic migration triggerのPUBLIC復元を内部guardへ流用しない。"""
    from pathlib import PurePosixPath

    from pitchlog.authz.ddl import DDLStatement
    from pitchlog.authz.product_provisioning import (
        _ProductElement,
        _unapplication_sql,
    )

    row = profile.declaration()
    element = _ProductElement("function", profile.FUNCTION_ID, row)
    statement = DDLStatement(
        "function", profile.FUNCTION_ID, PurePosixPath("unused"), profile.acl_sql()
    )
    sql = _unapplication_sql(statement, element, (element,), ())
    assert (
        sql == 'REVOKE EXECUTE ON FUNCTION "public"."protect_nonplay_admission"() '
        "FROM PUBLIC, pitchlog_app;"
    )
    assert "GRANT" not in sql and "DROP" not in sql


def test_catalog_requests_new_query_only_for_actual_new_guard():
    """他の旧profileへ新queryを混ぜず、新profileでは省略できない。"""
    from types import SimpleNamespace
    from typing import Any, cast

    def requests(functions):
        expectations = SimpleNamespace(
            schema_names=(),
            table_names=(),
            function_names=functions,
            role_ids=(),
            permanent_privileged_role_ids=(),
        )
        return catalog._catalog_requests(cast(Any, expectations), frozenset())

    assert not any(
        r.query_id is catalog.CatalogQueryId.NONPLAY_STORAGE_TRIGGERS
        for r in requests(())
    )
    new = requests(("protect_nonplay_admission",))
    assert (
        sum(r.query_id is catalog.CatalogQueryId.NONPLAY_STORAGE_TRIGGERS for r in new)
        == 1
    )


def test_prefull_requires_canonical_migration_guard_not_declared_by_ad_hoc_name(
    monkeypatch,
):
    """正規登録がない新guardを、既存DBにあるという理由だけで受け入れない。"""
    from pitchlog.authz import product_provisioning as provisioning
    from pitchlog.db import current_product_startup as current

    rows = [
        provisioning._ProductElement("function", key, dict[str, object](row))
        for key, row in (
            (profile.FUNCTION_ID, profile.declaration()),
            (
                "FUNCTION:public:protect_initial_right_storage()",
                {
                    "schema_name": "public",
                    "function_name": "protect_initial_right_storage",
                    "identity_args": "",
                },
            ),
        )
    ]
    monkeypatch.setattr(
        provisioning, "_selected_product_ddl", lambda _operation: (None, ())
    )
    monkeypatch.setattr(provisioning, "_load_product_elements", lambda: tuple(rows))
    functions, *_ = current._pre_full_expected()
    assert functions == {
        ("public", "protect_initial_right_storage", ""),
        ("public", "protect_nonplay_admission", ""),
    }
    rows.pop(0)
    with pytest.raises(current.CurrentProductStartupError, match="0042内部保護関数"):
        current._pre_full_expected()
