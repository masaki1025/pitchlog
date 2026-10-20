"""migrationのトリガ接続集計をDBなしで検証する。"""

from pathlib import Path

import product_authz_cross_cutting_cases as cross_cutting_cases
import product_authz_tenant_owned_cases as tenant_owned_cases
import pytest


def test_migration_trigger_census_applies_drop_and_preserves_duplicate_connections(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """削除済み接続を除き、AFTERを含む同一関数の複数接続を残す。"""
    (tmp_path / "0001.py").write_text(
        "def upgrade():\n"
        "    op.execute('CREATE TRIGGER retired BEFORE UPDATE ON games "
        "FOR EACH ROW EXECUTE FUNCTION retired_fn()')\n",
        encoding="utf-8",
    )
    (tmp_path / "0002.py").write_text(
        "def upgrade():\n"
        "    op.execute('DROP TRIGGER retired ON games')\n"
        "    op.execute('CREATE TRIGGER before_guard BEFORE UPDATE ON games "
        "FOR EACH ROW EXECUTE FUNCTION guard_fn()')\n"
        "    op.execute('CREATE TRIGGER after_guard AFTER UPDATE ON games "
        "FOR EACH ROW EXECUTE FUNCTION guard_fn()')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tenant_owned_cases, "_MIGRATIONS_PATH", tmp_path)

    assert tenant_owned_cases._migration_attached_trigger_functions() == (
        "guard_fn",
        "guard_fn",
    )


def test_trigger_expectations_rejects_duplicate_after_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AFTERを含む重複接続が資産突合前に拒否される。"""
    monkeypatch.setattr(
        cross_cutting_cases,
        "_migration_attached_trigger_functions",
        lambda: ("guard_fn", "guard_fn"),
    )
    monkeypatch.setattr(
        cross_cutting_cases,
        "_migration_trigger_facts",
        lambda: ({}, {}),
    )
    monkeypatch.setattr(
        cross_cutting_cases,
        "_asset_trigger_function_names",
        lambda: frozenset({"guard_fn"}),
    )

    with pytest.raises(AssertionError, match="複数箇所に接続"):
        cross_cutting_cases.trigger_expectations()
