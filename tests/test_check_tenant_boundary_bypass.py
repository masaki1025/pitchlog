"""テナント境界迂回検査の正例・負例・閉集合契約を検証する。"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_tenant_boundary_bypass.py"
POSITIVE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary" / "positive"
NEGATIVE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary" / "negative"
EXPECTED_NEGATIVE_IDS = frozenset(
    {
        "C1_ASSERT_OWNER_SHAPES",
        "C1_CAN_SHAPES",
        "C1_CHECK_ACCESS_SHAPES",
        "C1_HAS_PERMISSION_SHAPES",
        "C1_IS_ALLOWED_SHAPES",
        "C1_MAY_SHAPES",
        "C1_REQUIRE_ROLE_SHAPES",
        "C2_GENERATION_IMPORT",
        "C2_IDEMPOTENCY_KEY_IMPORT",
        "C2_IDEMPOTENT_KEY_IMPORT",
        "C2_REVISION_NO_IMPORT",
        "C2_SEQ_NO_IMPORT",
        "C2_SEQUENCE_NO_IMPORT",
        "C2_TOMBSTONE_IMPORT",
        "C3_AT_BAT_RESULT_IMPORT",
        "C3_AVG_IMPORT",
        "C3_EARNED_RUN_IMPORT",
        "C3_ERA_IMPORT",
        "C3_INNING_STATE_IMPORT",
        "C3_OBP_IMPORT",
        "C3_RBI_IMPORT",
        "C3_RESPONSIBLE_PITCHER_IMPORT",
        "C3_SLG_IMPORT",
        "C4_CACHE_CLEAR_API",
        "C4_EVICT_API",
        "C4_INVALIDATE_API",
        "C4_PURGE_CACHE_API",
        "C4_TRIGGER_CORRECT_PLAY",
        "C4_TRIGGER_DISABLE_TENANT",
        "C4_TRIGGER_END_GROUP",
        "C4_TRIGGER_GAME_LIFECYCLE",
        "C4_TRIGGER_GRANT_FLAG",
        "C4_TRIGGER_LEAVE_GROUP",
        "C4_TRIGGER_PLAYER_IDENTITY",
        "C4_TRIGGER_POSTGAME_CORRECTION",
        "C4_TRIGGER_REENABLE_TENANT",
        "C4_TRIGGER_RESTORED_SYNC",
        "C4_TRIGGER_ROSTER_STATUS",
        "C4_TRIGGER_SETTING",
        "C4_TRIGGER_SUBSTITUTION",
        "C4_TRIGGER_UNDO",
        "C5_ALIAS_EXECUTE",
        "C5_ASYNC_SESSION",
        "C5_BASE_INTERNAL_MUTATIONS",
        "C5_ENGINE_RAW_CONNECTION",
        "C5_MULTILINE_SCALARS",
        "C5_PSYCOPG_DIRECT",
        "C5_SET_CONFIG_FALSE",
        "C5_SET_TENANT_SQL",
        "C5_SQLALCHEMY_ORM",
    }
)


def _load_checker() -> ModuleType:
    """検査器をリポジトリの import 設定に依存せず読む。"""
    spec = importlib.util.spec_from_file_location(
        "check_tenant_boundary_bypass_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _fixture_source(path: Path) -> str:
    """fixture を UTF-8 で読む。"""
    return path.read_text(encoding="utf-8")


def test_positive_fixtures_pass() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_directory(POSITIVE_ROOT, contract=contract)

    assert violations == []


def test_negative_fixture_ids_are_an_exact_set_and_each_fixture_is_red() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    fixture_ids = {fixture.id for fixture in contract.negative_fixtures}
    assert fixture_ids == EXPECTED_NEGATIVE_IDS

    observed_conditions: set[int] = set()
    for fixture in contract.negative_fixtures:
        path = NEGATIVE_ROOT / fixture.path
        violations = checker.scan_source(
            _fixture_source(path),
            path=fixture.path,
            contract=contract,
        )
        codes = {violation.code for violation in violations}
        assert fixture.expected_error in codes, (
            f"{fixture.id} が期待どおり red でない: "
            f"expected={fixture.expected_error}, actual={sorted(codes)}"
        )
        observed_conditions.add(fixture.condition)

    assert observed_conditions == {1, 2, 3, 4, 5}


def test_reject_all_mutant_kills_positive_fixture() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_directory(
        POSITIVE_ROOT,
        contract=contract,
        reject_all_db_calls=True,
    )

    assert {violation.code for violation in violations} == {"TB900"}


def test_api_added_outside_sealed_inventory_is_red(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(
        REPOSITORY_ROOT / "contracts" / "tenant_boundary",
        repository / "contracts" / "tenant_boundary",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary",
        repository / "tests" / "fixtures" / "tenant_boundary",
    )
    inventory_path = repository / checker.DEFAULT_INVENTORY
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert isinstance(inventory, dict)
    apis = inventory["apis"]
    assert isinstance(apis, list)
    apis.append(
        {
            "id": "OUTSIDE_INVENTORY_API",
            "symbol": "outside.database.execute",
            "kind": "function",
            "receivers": [],
        }
    )
    inventory_path.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(checker.ContractError, match="inventory の集合が封印値と不一致"):
        checker.load_contract(repository)


def test_empty_baseline_and_empty_head_pass() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.continuity_violations({}, {}, contract=contract)

    assert violations == []


def test_removing_symbol_that_existed_in_baseline_is_red() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    baseline = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    violations = checker.continuity_violations(baseline, {}, contract=contract)

    assert {violation.code for violation in violations} == {"TB006"}
    assert {
        violation.symbol for violation in violations
    } == {
        "pitchlog.repositories.base.TenantRepositoryBase._execute_operation"
    }


def test_first_introduction_of_contract_symbol_is_not_a_rollback() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    head = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    violations = checker.continuity_violations({}, head, contract=contract)

    assert violations == []


def test_diff_parser_selects_only_new_side_backend_lines() -> None:
    diff = """\
diff --git a/backend/src/pitchlog/example.py b/backend/src/pitchlog/example.py
--- a/backend/src/pitchlog/example.py
+++ b/backend/src/pitchlog/example.py
@@ -2,0 +3,2 @@
+first = 1
+second = 2
@@ -8 +9 @@
-old = 1
+new = 2
diff --git a/docs/example.md b/docs/example.md
--- a/docs/example.md
+++ b/docs/example.md
@@ -0,0 +1 @@
+ignored
"""

    changed = checker.changed_lines_from_diff(diff)

    assert changed == {"pitchlog/example.py": frozenset({3, 4, 9})}


def test_unchanged_forbidden_line_is_outside_diff_scope() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
def can_cross_tenant() -> bool:
    return True


def ordinary_change() -> bool:
    return True
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/example.py",
        changed_lines=frozenset({6}),
        contract=contract,
    )

    assert violations == []


def test_imported_session_annotation_resolves_arbitrary_receiver_alias() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from sqlalchemy.orm import Session


def load(short_name: Session) -> object:
    return short_name.execute("SELECT 1")
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/typed_alias.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_repository_diff_is_green_before_product_code_is_added() -> None:
    violations = checker.check_repository(REPOSITORY_ROOT)

    assert violations == []


def test_manifest_rows_keep_the_required_exact_shape() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_NEGATIVE_FIXTURES).read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(manifest, dict)
    fixtures = manifest["fixtures"]
    assert isinstance(fixtures, list)
    for row in fixtures:
        assert isinstance(row, dict)
        assert set(row) == {
            "id",
            "path",
            "condition",
            "mutation",
            "expected_error",
        }


def test_contract_declares_ci_job_without_wiring_it() -> None:
    allowlist: dict[str, Any] = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )

    assert allowlist["ci"] == {
        "job": "tenant-boundary-bypass",
        "command": "uv run python scripts/check_tenant_boundary_bypass.py",
    }
