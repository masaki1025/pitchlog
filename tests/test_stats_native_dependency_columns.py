"""成績同TX照合用xmin四宣言だけをsystem列依存として許可する。"""

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
spec = importlib.util.spec_from_file_location(
    "stats_dependency_checker_under_test", ROOT / "scripts/check_authz_catalog.py"
)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


def _rows():
    """採用canonical全宣言から本物四行を読む。"""
    product = importlib.import_module("pitchlog.authz.stats_primitive_product")
    declarations, _ = product.candidate_declarations()
    return {
        row["expectation_id"]: row
        for row in declarations["column_acl_expectations"]
        if row["column_id"] == "xmin"
    }


def test_only_four_canonical_system_columns_are_accepted():
    """利用者列を捏造せず、system列四件だけを再現する。"""
    rows = _rows()
    assert len(rows) == 4
    assert checker._product_stats_xmin_columns(rows) == frozenset({
        ("operation_events", "xmin"), ("play_rows", "xmin"),
        ("idempotency_ledger", "xmin"), ("ordinary_pitch_checkpoints", "xmin"),
    })
    assert checker._product_stats_xmin_columns({}) == frozenset()


@pytest.mark.parametrize("field,value", [
    ("object_schema", "attacker"), ("object_id", "players"),
    ("grantee_role_id", "pitchlog_app"), ("privilege_ids", ["UPDATE"]),
    ("grant_option", True), ("grant_option", 0), ("object_id", []), ("expectation_id", "forged"),
    ("object_kind", "table"), ("extra", True),
])
def test_system_column_exception_rejects_any_declaration_mutation(field, value):
    """名前だけ同じxminを認可の迂回に使えない。"""
    rows = copy.deepcopy(_rows())
    next(iter(rows.values()))[field] = value
    with pytest.raises(checker.CatalogError):
        checker._product_stats_xmin_columns(rows)
