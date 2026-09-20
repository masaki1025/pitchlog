"""テナント境界迂回検査の正例・負例・閉集合契約を検証する。"""

from __future__ import annotations

import copy
import hashlib
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
PRODUCT_APPLICATION_PATHS = (
    "pitchlog/authz/runtime_contract.py",
    "pitchlog/db/engine.py",
    "pitchlog/repositories/base.py",
    "pitchlog/repositories/binding.py",
    "pitchlog/repositories/cache_invalidation.py",
    "pitchlog/repositories/context.py",
    "pitchlog/repositories/repository_contract.py",
    "pitchlog/repositories/tenant_context_contract.py",
    "pitchlog/repositories/tokens.py",
)
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
        "C4_DIRECT_INVALIDATION_WRITE",
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
        "C5_DYNAMIC_EVAL_EXECUTE",
        "C5_DYNAMIC_EXEC",
        "C5_DYNAMIC_GETATTR_EXECUTE",
        "C5_DYNAMIC_IMPORT_PSYCOPG",
        "C5_DYNAMIC_IMPORTLIB",
        "C5_ENGINE_RETURN_ALIAS",
        "C5_ENGINE_RAW_CONNECTION",
        "C5_MULTILINE_SCALARS",
        "C5_PGCONN_EXEC",
        "C5_PSYCOPG_DIRECT",
        "C5_SET_CONFIG_FALSE",
        "C5_SET_TENANT_SQL",
        "C5_SQLALCHEMY_ORM",
        "C5_TENANT_CONTEXT_OBJECT_NEW",
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


def _read_contract_asset(relative_path: Path) -> dict[str, Any]:
    """テナント境界の契約資産を JSON object として読む。"""
    value = json.loads((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _fixture_source(path: Path) -> str:
    """fixture を UTF-8 で読む。"""
    return path.read_text(encoding="utf-8")


def _contract_digest(value: dict[str, Any]) -> str:
    """source_digest 欄を除く JSON 資産の正規化 digest を計算する。"""
    payload = dict(value)
    payload.pop("source_digest", None)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _changed_lines_containing(source: str, *needles: str) -> frozenset[int]:
    """指定文字列を含む変異行を差分母集団として返す。"""
    lines = source.splitlines()
    changed = {
        line_number
        for line_number, line in enumerate(lines, start=1)
        if any(needle in line for needle in needles)
    }
    assert all(any(needle in line for line in lines) for needle in needles)
    return frozenset(changed)


def test_positive_fixtures_pass() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_directory(POSITIVE_ROOT, contract=contract)

    assert violations == []


def test_frozen_baseline_asset_paths_are_an_exact_set() -> None:
    """tenant_boundary 配下の 7 資産を履歴検査から漏らさない。"""
    asset_root = REPOSITORY_ROOT / "contracts" / "tenant_boundary"
    actual = {
        path.relative_to(REPOSITORY_ROOT)
        for path in asset_root.glob("*.json")
    }

    assert actual == set(checker.FROZEN_BASELINE_ASSETS)


@pytest.mark.parametrize("relative_path", checker.FROZEN_BASELINE_ASSETS)
def test_every_frozen_baseline_asset_has_a_valid_chained_history(
    relative_path: Path,
) -> None:
    """7 資産の識別宣言・4 項目・直前値の連鎖を検査する。"""
    asset = _read_contract_asset(relative_path)

    history = checker._validate_baseline_control(
        asset,
        relative_path.as_posix(),
    )

    assert history


@pytest.mark.parametrize(
    "field",
    (
        "new_baseline_identifiers",
        "previous_baseline_identifiers",
        "change",
        "movement_fact",
        "reason",
        "approved_by",
        "approved_on",
    ),
)
def test_missing_baseline_history_field_is_red(field: str) -> None:
    """7.7-2 の必須記録を 1 項目でも省く変異を拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _read_contract_asset(relative_path)
    mutated = copy.deepcopy(asset)
    del mutated["baseline_control"]["history"][0][field]

    with pytest.raises(checker.ContractError):
        checker._validate_baseline_control(mutated, relative_path.as_posix())


def test_changed_baseline_history_entry_is_red() -> None:
    """既存記録の書き換えを append-only 比較で拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _read_contract_asset(relative_path)
    current = copy.deepcopy(previous)
    current["baseline_control"]["history"][0]["reason"] = "書き換え"

    with pytest.raises(checker.ContractError, match="変更・削除"):
        checker._validate_history_append_only(
            previous,
            current,
            relative_path.as_posix(),
        )


def test_deleted_baseline_history_entry_is_red() -> None:
    """既存記録の削除を append-only 比較で拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _read_contract_asset(relative_path)
    current = copy.deepcopy(previous)
    current["contract_revision"] = 6
    current["baseline_control"]["identity"]["current_identifiers"] = [
        "contract_revision:6"
    ]
    current["baseline_control"]["history"].pop()

    with pytest.raises(checker.ContractError, match="変更・削除"):
        checker._validate_history_append_only(
            previous,
            current,
            relative_path.as_posix(),
        )


def test_broken_previous_baseline_identifier_chain_is_red() -> None:
    """直前の識別値が直前行の新識別値と違う変異を拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _read_contract_asset(relative_path)
    mutated = copy.deepcopy(asset)
    mutated["baseline_control"]["history"][1][
        "previous_baseline_identifiers"
    ] = ["contract_revision:999"]

    with pytest.raises(checker.ContractError, match="連鎖"):
        checker._validate_baseline_control(mutated, relative_path.as_posix())


def test_first_history_entry_does_not_imply_no_previous_baseline() -> None:
    """履歴の先頭という理由だけで直前基準なしと推定しない。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _read_contract_asset(relative_path)
    mutated = copy.deepcopy(asset)
    mutated["baseline_control"]["history"][0][
        "previous_baseline_identifiers"
    ] = ["legacy_baseline:1"]

    history = checker._validate_baseline_control(
        mutated,
        relative_path.as_posix(),
    )

    assert history[0]["previous_baseline_identifiers"] == ["legacy_baseline:1"]


def test_baseline_removal_can_be_recorded_with_no_baseline_marker() -> None:
    """最後の基準を取り除く遷移にも履歴行を置ける。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _read_contract_asset(relative_path)
    mutated = copy.deepcopy(asset)
    first = mutated["baseline_control"]["history"][0]
    second = mutated["baseline_control"]["history"][1]
    first["previous_baseline_identifiers"] = ["legacy_baseline:1"]
    first["new_baseline_identifiers"] = [checker.NO_BASELINE]
    second["previous_baseline_identifiers"] = [checker.NO_BASELINE]

    history = checker._validate_baseline_control(
        mutated,
        relative_path.as_posix(),
    )

    assert history[0]["new_baseline_identifiers"] == [checker.NO_BASELINE]


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


def test_low_level_execution_surface_and_receiver_origins_are_sealed() -> None:
    """PGconn 実行面・re-export・factory 戻り型を閉集合に固定する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    pgconn_execution_symbols = {
        api.symbol
        for api in contract.apis
        if api.symbol.startswith("psycopg.pq.PGconn.")
    }
    assert pgconn_execution_symbols == {
        "psycopg.pq.PGconn.connect",
        "psycopg.pq.PGconn.connect_start",
        "psycopg.pq.PGconn.exec_",
        "psycopg.pq.PGconn.exec_params",
        "psycopg.pq.PGconn.exec_prepared",
        "psycopg.pq.PGconn.send_prepare",
        "psycopg.pq.PGconn.send_query",
        "psycopg.pq.PGconn.send_query_params",
        "psycopg.pq.PGconn.send_query_prepared",
    }
    assert contract.symbol_aliases["sqlalchemy.Engine"] == (
        "sqlalchemy.engine.Engine"
    )
    factory_returns = {
        item.symbol: item.returns for item in contract.receiver_factories
    }
    assert factory_returns["pitchlog.db.engine.create_database_engine"] == (
        "sqlalchemy.engine.Engine"
    )
    assert factory_returns["sqlalchemy.engine.Engine.connect"] == (
        "sqlalchemy.engine.Connection"
    )


@pytest.mark.parametrize(
    ("source", "expected_error"),
    (
        ('run = getattr(session, "exe" + "cute")\nrun(statement)\n', "TB005"),
        ('eval("session.execute")(statement)\n', "TB005"),
        (
            'driver = __import__("psyco" + "pg")\n'
            'getattr(driver, "connect")(url)\n',
            "TB005",
        ),
        (
            "from pitchlog.db.engine import create_database_engine\n"
            "database = create_database_engine()\n"
            "handle = database.connect()\n"
            'handle.exec_driver_sql("SELECT 1")\n',
            "TB005",
        ),
        (
            "from psycopg.pq import PGconn\n"
            "connection: PGconn\n"
            'connection.exec_(b"SELECT 1")\n',
            "TB005",
        ),
        (
            "from pitchlog.repositories.context import TenantContext\n"
            "object.__new__(TenantContext)\n",
            "TB007",
        ),
    ),
)
def test_reported_dynamic_bypass_examples_are_red(
    source: str,
    expected_error: str,
) -> None:
    """敵対レビューで再現された 6 経路をそのまま拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    violations = checker.scan_source(
        source,
        path="pitchlog/services/adversarial.py",
        contract=contract,
    )

    assert expected_error in {violation.code for violation in violations}


def test_session_factory_return_and_dynamic_object_new_are_red() -> None:
    """Session factory 別名と動的 object.__new__ も閉世界検査で拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    session_source = """\
from sqlalchemy.orm import Session

session_factory = Session
handle = session_factory()
handle.execute(statement)
"""
    context_source = """\
from pitchlog.repositories.context import TenantContext

getattr(object, "__new__")(TenantContext)
"""

    session_violations = checker.scan_source(
        session_source,
        path="pitchlog/services/session_factory_bypass.py",
        contract=contract,
    )
    context_violations = checker.scan_source(
        context_source,
        path="pitchlog/services/context_factory_bypass.py",
        contract=contract,
    )

    assert "TB005" in {item.code for item in session_violations}
    assert "TB007" in {item.code for item in context_violations}


def test_empty_baseline_and_empty_head_pass() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.continuity_violations({}, {}, contract=contract)
    population = checker._inspection_population({}, {}, contract=contract)
    application_violations = checker._application_population_violations(
        {},
        {},
        {},
        contract=contract,
    )

    assert violations == []
    assert population == {}
    assert application_violations == []


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


def test_tenant_context_construction_from_allowlisted_module_passes() -> None:
    """allowlist 内のテストモジュールからの構築が通ることを確認する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    test_module = (
        REPOSITORY_ROOT / "backend/tests/test_authz_tenant_context.py"
    )

    violations = checker.scan_source(
        _fixture_source(test_module),
        path=test_module.name,
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize(
    "source",
    (
        """\
from pitchlog.repositories.context import TenantContext

context = TenantContext(tenant_id)
""",
        """\
import pitchlog.repositories.context as repository_context

context = repository_context.TenantContext(tenant_id)
""",
        """\
from pitchlog.repositories.context import TenantContext as Context

context = Context(tenant_id)
""",
        """\
from pitchlog.repositories.context import TenantContext


class DerivedContext(TenantContext):
    pass


context = DerivedContext(tenant_id)
""",
    ),
)
def test_tenant_context_construction_outside_allowlist_is_red(source: str) -> None:
    """import 形を変えても allowlist 外からの構築を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/api/routers/example.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB007"}


def test_product_module_cannot_be_added_before_authenticated_entry_exists() -> None:
    """認証入口の導入前に製品モジュールを許可する変異を拒否する。"""
    asset = json.loads(
        (
            REPOSITORY_ROOT / checker.DEFAULT_TENANT_CONTEXT_ALLOWLIST
        ).read_text(encoding="utf-8")
    )
    assert isinstance(asset, dict)
    asset["allowed_product_modules"] = ["pitchlog.api.routers.example"]
    asset["source_digest"] = _contract_digest(asset)

    with pytest.raises(checker.ContractError, match="製品モジュールの生成経路は 0 件"):
        checker._load_tenant_context_allowlist(asset)


@pytest.mark.parametrize("relative_path", PRODUCT_APPLICATION_PATHS)
def test_tenant_repository_product_definition_passes_bypass_scan(
    relative_path: str,
) -> None:
    """現行の製品コードそのものが全行検査を通ることを確認する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source_path = REPOSITORY_ROOT / "backend/src" / relative_path

    violations = checker.scan_source(
        _fixture_source(source_path),
        path=relative_path,
        contract=contract,
    )

    assert violations == []


def test_tenant_binding_symbol_has_only_required_database_apis() -> None:
    """束縛シンボルのDB到達許可を必要な4 APIだけに固定する。"""
    allowlist = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )
    assert isinstance(allowlist, dict)
    allowed_symbols = allowlist["allowed_symbols"]
    assert isinstance(allowed_symbols, list)
    matching_rows = [
        row
        for row in allowed_symbols
        if isinstance(row, dict)
        and row.get("symbol")
        == "pitchlog.repositories.binding._tenant_transaction"
    ]

    assert len(matching_rows) == 1
    assert set(matching_rows[0]["allowed_api_ids"]) == {
        "SQLA_SESSION_BEGIN",
        "SQLA_SESSION_CONNECTION",
        "SQLA_SESSION_EXECUTE",
        "SQLA_TEXT",
    }


def test_repository_base_symbol_has_only_execute_database_api() -> None:
    """基底の非公開実行器に Session.execute だけを許可する。"""
    allowlist = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )
    assert isinstance(allowlist, dict)
    allowed_symbols = allowlist["allowed_symbols"]
    assert isinstance(allowed_symbols, list)
    matching_rows = [
        row
        for row in allowed_symbols
        if isinstance(row, dict)
        and row.get("symbol")
        == "pitchlog.repositories.base.TenantRepositoryBase._execute_operation"
    ]

    assert len(matching_rows) == 1
    assert matching_rows[0]["signature"] == (
        "_execute_operation(self, context: TenantContext, "
        "operation: TenantOperationToken) -> TenantOperationResult"
    )
    assert matching_rows[0]["allowed_api_ids"] == ["SQLA_SESSION_EXECUTE"]


def test_condition4_allows_only_the_declared_request_api_call() -> None:
    """葉が provider の公開型と純粋要求生成器だけを利用できる。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from uuid import UUID

from pitchlog.repositories.cache_invalidation import (
    CacheInvalidationRequest,
    CacheInvalidationTrigger,
    CachePeriod,
    SharedAggregateCacheKey,
    build_cache_invalidation_request,
)


def request_cache_refresh(
    group_id: UUID,
    requester_tenant_id: UUID,
    target_tenant_id: UUID,
) -> CacheInvalidationRequest:
    key = SharedAggregateCacheKey(
        group_id,
        requester_tenant_id,
        target_tenant_id,
        CachePeriod(None, None),
    )
    return build_cache_invalidation_request(
        CacheInvalidationTrigger.GRANT_FLAG_CHANGE,
        (key,),
    )
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/cache_request.py",
        contract=contract,
    )

    assert violations == []


def test_condition4_rejects_nonpublic_provider_import_and_call() -> None:
    """provider に置いただけの非公開実装を葉が迂回利用できない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from pitchlog.repositories.cache_invalidation import CacheInvalidationRequest


def request_cache_refresh() -> CacheInvalidationRequest:
    return CacheInvalidationRequest._create(
        trigger=None,
        keys=(),
        propagation_mode=None,
        affected_tenant_ids=None,
    )
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/cache_request.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB004"}


def test_condition4_allowed_call_symbols_are_an_exact_set() -> None:
    """条件 4 の許可呼び出しを物理キー構築と単一 factory に閉じる。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    assert contract.cache_invalidation.allowed_call_symbols == frozenset(
        {
            "pitchlog.repositories.cache_invalidation.AnalyticsChartCacheKey",
            "pitchlog.repositories.cache_invalidation.CachePeriod",
            "pitchlog.repositories.cache_invalidation.MatchCacheKey",
            "pitchlog.repositories.cache_invalidation.MatchChartSubject",
            "pitchlog.repositories.cache_invalidation.PlayerCareerCacheKey",
            "pitchlog.repositories.cache_invalidation.PlayerChartSubject",
            "pitchlog.repositories.cache_invalidation.SharedAggregateCacheKey",
            "pitchlog.repositories.cache_invalidation.TeamAggregateCacheKey",
            "pitchlog.repositories.cache_invalidation.build_cache_invalidation_request",
        }
    )


def test_repository_application_population_is_nonempty_and_green() -> None:
    """自 PR の実差分を非空母集団として適用し一致 0 を確認する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    diff = checker._run_git(
        REPOSITORY_ROOT,
        ["diff", "-U0", "origin/develop...HEAD", "--", "backend/src"],
    )
    changed_lines = checker.changed_lines_from_diff(diff)
    merge_base = checker._run_git(
        REPOSITORY_ROOT,
        ["merge-base", "origin/develop", "HEAD"],
    ).strip()
    baseline_sources = checker._git_snapshot(REPOSITORY_ROOT, merge_base)
    head_sources = checker._git_snapshot(REPOSITORY_ROOT, "HEAD")
    baseline_definitions, _ = checker._definitions(
        baseline_sources,
        contract,
    )
    head_definitions, _ = checker._definitions(head_sources, contract)
    introduced_symbols = set(head_definitions) - set(baseline_definitions)
    population = checker._inspection_population(
        changed_lines,
        head_sources,
        contract=contract,
    )

    assert population
    if introduced_symbols:
        assert checker._has_changed_lines(changed_lines)
        assert set(PRODUCT_APPLICATION_PATHS) <= {
            path for path, lines in changed_lines.items() if lines
        }
    else:
        assert set(PRODUCT_APPLICATION_PATHS) <= set(head_sources)
    violations = checker.check_repository(REPOSITORY_ROOT)

    assert violations == []


def test_first_product_introduction_with_empty_population_is_red() -> None:
    """製品シンボル導入時に三点差分が空洞化する変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    head = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    violations = checker._application_population_violations(
        {},
        {},
        head,
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB008"}


def test_merged_head_uses_real_contract_symbols_as_nonempty_population() -> None:
    """統合後に三点差分が空でも実製品の強制点を再検査する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    head = {relative: _fixture_source(POSITIVE_ROOT / relative)}

    population = checker._inspection_population({}, head, contract=contract)
    violations = checker.scan_source(
        head[relative],
        path=relative,
        changed_lines=population[relative],
        contract=contract,
    )

    assert population[relative]
    assert violations == []


def test_current_product_contract_is_rechecked_after_merge() -> None:
    """base が HEAD 自身でも実製品の強制点を再検査して通す。"""
    violations = checker.check_repository(REPOSITORY_ROOT, base_ref="HEAD")

    assert violations == []


def test_actual_base_direct_sql_mutation_is_red() -> None:
    """実際の基底の許可関数へ未許可の直接 SQL を足すと拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutated = source.replace(
        "from sqlalchemy.orm import Session",
        "from sqlalchemy import text\nfrom sqlalchemy.orm import Session",
        1,
    ).replace(
        "            execution_result = self._session.execute(\n",
        "            self._session.execute(text(\"SELECT 1\"))\n"
        "            execution_result = self._session.execute(\n",
        1,
    )

    violations = checker.scan_source(
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(
            mutated,
            "from sqlalchemy import text",
            'self._session.execute(text("SELECT 1"))',
        ),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_actual_binding_nonlocal_set_config_mutation_is_red() -> None:
    """実際の束縛文を transaction-local でなくす変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/binding.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutated = source.replace(
        "SELECT set_config('app.tenant_id', :tenant_id, true)",
        "SELECT set_config('app.tenant_id', :tenant_id, false)",
        1,
    )

    violations = checker.scan_source(
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(mutated, "set_config", "false"),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_actual_base_database_call_outside_allowed_symbol_is_red() -> None:
    """基底でも許可シンボルの外側から DB API を呼ぶ変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/base.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutated = source.replace(
        "        _operation_spec(operation)\n",
        "        self._session.execute(operation)\n"
        "        _operation_spec(operation)\n",
        1,
    )

    violations = checker.scan_source(
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(
            mutated,
            "self._session.execute(operation)",
        ),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


def test_actual_binding_unlisted_symbol_database_call_is_red() -> None:
    """allowlist に無い新設シンボルからの DB API 呼び出しを拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    relative = "pitchlog/repositories/binding.py"
    source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
    mutation = """

def _unlisted_database_access(session: Session) -> None:
    session.execute(text("SELECT 1"))
"""
    mutated = f"{source.rstrip()}{mutation}\n"

    violations = checker.scan_source(
        mutated,
        path=relative,
        changed_lines=_changed_lines_containing(
            mutated,
            "_unlisted_database_access",
            'session.execute(text("SELECT 1"))',
        ),
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB005"}


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
