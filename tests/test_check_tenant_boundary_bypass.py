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
        "C5_CONTEXT_PROOF_DIRECT_REFERENCE",
        "C5_CONTEXT_PROOF_INDIRECT_REFERENCE",
        "C5_CONTEXT_UNKNOWN_FACTORY",
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
        "C5_TENANT_CONTEXT_OBJECT_SETATTR_UNTYPED",
        "C5_TENANT_CONTEXT_TYPE_CALL",
        "C5_TENANT_CONTEXT_OBJECT_NEW_TYPE",
        "C5_TENANT_CONTEXT_DATACLASSES_REPLACE",
        "C5_UNKNOWN_ENGINE_ARGUMENT",
        "C5_UNKNOWN_SESSION_ARGUMENT",
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


def _external_source(path: str) -> bytes:
    """作業ツリーの外部凍結対象を読む。"""
    return (REPOSITORY_ROOT / path).read_bytes()


def _accepted_snapshot(relative_path: Path) -> dict[str, Any]:
    """純粋な遷移検査用に先頭履歴を受理済み状態へ変える。"""
    asset = _read_contract_asset(relative_path)
    entry = asset["baseline_control"]["history"][0]
    entry["source_commit"] = "abcdef0"
    entry["approved_by"] = "テスト承認者"
    entry["approved_on"] = "2026-09-20"
    return asset


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


def _scan_diff_mutation(
    baseline: str,
    mutated: str,
    *,
    path: str,
    changed_lines: frozenset[int],
    contract: Any,
) -> list[Any]:
    """差分行を入口に、基準版と変異後の全行比較を実行する。"""
    assert changed_lines
    assert (
        checker.scan_source_change(
            None,
            baseline,
            path=path,
            changed_lines=frozenset(
                range(1, len(baseline.splitlines()) + 1)
            ),
            contract=contract,
        )
        == []
    )
    return checker.scan_source_change(
        baseline,
        mutated,
        path=path,
        changed_lines=changed_lines,
        contract=contract,
    )


def _commit_test_repository(repository: Path, message: str) -> str:
    """一時リポジトリの全変更をコミットして commit ID を返す。"""
    checker._run_git(repository, ["add", "."])
    checker._run_git(
        repository,
        [
            "-c",
            "user.name=Tenant Boundary Test",
            "-c",
            "user.email=tenant-boundary@example.invalid",
            "commit",
            "-m",
            message,
        ],
    )
    return checker._run_git(repository, ["rev-parse", "HEAD"]).strip()


def _initialize_test_repository(
    tmp_path: Path,
    sources: dict[str, str],
) -> tuple[Path, str]:
    """実際の差分検査を行える最小 Git リポジトリを作る。"""
    repository = tmp_path / "repository"
    shutil.copytree(
        REPOSITORY_ROOT / "contracts" / "tenant_boundary",
        repository / "contracts" / "tenant_boundary",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "tests" / "fixtures" / "tenant_boundary",
        repository / "tests" / "fixtures" / "tenant_boundary",
    )
    script_path = repository / "scripts" / SCRIPT.name
    script_path.parent.mkdir(parents=True)
    shutil.copy2(SCRIPT, script_path)
    for relative, source in sources.items():
        path = repository / "backend" / "src" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    checker._run_git(repository, ["init"])
    return repository, _commit_test_repository(repository, "baseline")


def _write_test_repository_sources(
    repository: Path,
    sources: dict[str, str],
) -> None:
    """一時リポジトリの製品ソースを変異後の内容へ更新する。"""
    for relative, source in sources.items():
        path = repository / "backend" / "src" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def _point_default_base_ref_at(repository: Path, commit: str) -> None:
    """一時リポジトリの凍結既定比較元を指定 commit へ向ける。"""
    assert checker.DEFAULT_BASE_REF == "origin/develop"
    checker._run_git(
        repository,
        ["update-ref", "refs/remotes/origin/develop", commit],
    )


def _actual_implementation_mutation(case_id: str) -> tuple[str, str, str]:
    """既存の製品変異テストと同じ基準版・変異版を返す。"""
    if case_id == "base-direct-sql":
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
    elif case_id == "binding-nonlocal-set-config":
        relative = "pitchlog/repositories/binding.py"
        source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
        mutated = source.replace(
            "SELECT set_config('app.tenant_id', :tenant_id, true)",
            "SELECT set_config('app.tenant_id', :tenant_id, false)",
            1,
        )
    elif case_id == "base-call-outside-allowed-symbol":
        relative = "pitchlog/repositories/base.py"
        source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
        mutated = source.replace(
            "        _operation_spec(operation)\n",
            "        self._session.execute(operation)\n"
            "        _operation_spec(operation)\n",
            1,
        )
    elif case_id == "binding-unlisted-symbol":
        relative = "pitchlog/repositories/binding.py"
        source = _fixture_source(REPOSITORY_ROOT / "backend/src" / relative)
        mutation = """

def _unlisted_database_access(session: Session) -> None:
    session.execute(text("SELECT 1"))
"""
        mutated = f"{source.rstrip()}{mutation}\n"
    else:
        raise AssertionError(f"未定義の実装変異: {case_id}")

    assert mutated != source
    return relative, source, mutated


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

    assert len(history) == 1
    assert history[0]["source_commit"] == checker.PENDING_SOURCE_COMMIT
    assert history[0]["previous_baseline_identifiers"] == [checker.NO_BASELINE]


@pytest.mark.parametrize(
    "field",
    (
        "source_commit",
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
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    current["baseline_control"]["history"][0]["reason"] = "書き換え"

    with pytest.raises(checker.ContractError):
        checker._validate_history_append_only(
            previous,
            current,
            relative_path.as_posix(),
        )


def test_deleted_baseline_history_entry_is_red() -> None:
    """既存記録の削除を append-only 比較で拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    current["contract_revision"] = 6
    current["baseline_control"]["identity"]["current_identifiers"] = [
        "contract_revision:6"
    ]
    current["baseline_control"]["history"].pop()

    with pytest.raises(checker.ContractError):
        checker._validate_history_append_only(
            previous,
            current,
            relative_path.as_posix(),
        )


def test_merge_base_pending_history_is_still_append_only() -> None:
    """merge-base に現にある記録は未承認表示でも書き換えを拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _read_contract_asset(relative_path)
    current = copy.deepcopy(previous)
    current["baseline_control"]["history"][0]["reason"] = "書き換え"

    with pytest.raises(checker.ContractError, match="既存履歴"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=_external_source,
            current_external_loader=_external_source,
        )


def test_first_adoption_previous_identifier_must_be_no_baseline() -> None:
    """merge-base に資産が無い初回受理の直前値を推測値にできない。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    asset = _read_contract_asset(relative_path)
    mutated = copy.deepcopy(asset)
    mutated["baseline_control"]["history"][0][
        "previous_baseline_identifiers"
    ] = ["contract_revision:999"]

    with pytest.raises(checker.ContractError, match="NO_BASELINE"):
        checker._validate_baseline_transition(
            None,
            mutated,
            relative_path.as_posix(),
            previous_external_loader=lambda _path: b"",
            current_external_loader=_external_source,
        )


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


def test_reported_pattern_removal_without_revision_or_history_is_red() -> None:
    """禁止 pattern を黙って 1 本削る敵対レビュー再現を射影比較で拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    current["conditions"][0]["patterns"].pop()

    with pytest.raises(checker.ContractError, match="ちょうど 1 件"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=_external_source,
            current_external_loader=_external_source,
        )


def test_history_added_without_projection_movement_is_red() -> None:
    """射影が動いていない受理への不要な履歴追加を拒否する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)
    extra = copy.deepcopy(current["baseline_control"]["history"][-1])
    extra["source_commit"] = "abcdef1"
    current_identifiers = current["baseline_control"]["identity"][
        "current_identifiers"
    ]
    extra["previous_baseline_identifiers"] = list(current_identifiers)
    extra["new_baseline_identifiers"] = list(current_identifiers)
    current["baseline_control"]["history"].append(extra)

    with pytest.raises(checker.ContractError, match="射影が動いていない"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=_external_source,
            current_external_loader=_external_source,
        )


def test_checker_pass_fail_mapping_change_requires_revision_and_history() -> None:
    """検査器自身の変更も外部凍結射影の移動として検出する。"""
    relative_path = checker.FROZEN_BASELINE_ASSETS[0]
    previous = _accepted_snapshot(relative_path)
    current = copy.deepcopy(previous)

    with pytest.raises(checker.ContractError, match="ちょうど 1 件"):
        checker._validate_baseline_transition(
            previous,
            current,
            relative_path.as_posix(),
            previous_external_loader=lambda _path: b"old pass/fail mapping",
            current_external_loader=lambda _path: b"new pass/fail mapping",
        )


def test_negative_fixture_ids_are_an_exact_set_and_each_fixture_is_red() -> None:
    contract = checker.load_contract(REPOSITORY_ROOT)
    fixture_ids = {fixture.id for fixture in contract.negative_fixtures}
    assert fixture_ids == EXPECTED_NEGATIVE_IDS

    observed_conditions: set[int] = set()
    for fixture in contract.negative_fixtures:
        path = NEGATIVE_ROOT / fixture.path
        source = _fixture_source(path)
        violations = checker.scan_source_change(
            None,
            source,
            path=fixture.path,
            changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
            contract=contract,
        )
        codes = {violation.code for violation in violations}
        assert fixture.expected_error in codes, (
            f"{fixture.id} が期待どおり red でない: "
            f"expected={fixture.expected_error}, actual={sorted(codes)}"
        )
        observed_conditions.add(fixture.condition)

    assert observed_conditions == {1, 2, 3, 4, 5}


@pytest.mark.parametrize("condition", (1, 2, 3, 4, 5))
def test_all_negative_fixtures_are_red_through_real_commit_diff(
    tmp_path: Path,
    condition: int,
) -> None:
    """契約済み負例 68 本を条件別の実コミット列で拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    assert {fixture.id for fixture in contract.negative_fixtures} == (
        EXPECTED_NEGATIVE_IDS
    )
    fixtures = tuple(
        fixture
        for fixture in contract.negative_fixtures
        if fixture.condition == condition
    )
    assert fixtures
    baseline_sources = {fixture.path: "pass\n" for fixture in fixtures}
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        baseline_sources,
    )

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0

    mutated_sources = {
        fixture.path: _fixture_source(NEGATIVE_ROOT / fixture.path)
        for fixture in fixtures
    }
    _write_test_repository_sources(repository, mutated_sources)
    _commit_test_repository(repository, "apply all negative fixtures")
    violations = checker.check_repository(repository, base_ref=base_ref)
    observed = {(violation.path, violation.code) for violation in violations}

    for fixture in fixtures:
        assert (fixture.path, fixture.expected_error) in observed, (
            f"{fixture.id} が実コミット列で期待どおり red でない: "
            f"expected={fixture.expected_error}"
        )
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


@pytest.mark.parametrize(
    ("declaration", "expected_error"),
    (
        ("base_ref", r"extra=\['base_ref'\]"),
        ("comparison_ref", r"extra=\['comparison_ref'\]"),
        ("concrete_command", "三点差分 template が必要"),
    ),
)
def test_asset_declared_base_ref_is_contract_error_through_real_commit_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    declaration: str,
    expected_error: str,
) -> None:
    """比較元の自己申告と直接 SQL を同じ commit に置いても no-op にさせない。"""
    relative = "pitchlog/services/impact_probe.py"
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: "pass\n"},
    )
    _point_default_base_ref_at(repository, base_ref)
    impact_probe = '''\
from sqlalchemy.orm import Session


def read_other_tenant(work: Session) -> object:
    return work.execute("SELECT * FROM games")
'''
    _write_test_repository_sources(repository, {relative: impact_probe})
    allowlist_path = repository / checker.DEFAULT_ALLOWLIST
    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    assert isinstance(allowlist, dict)
    diff_contract = allowlist["diff"]
    assert isinstance(diff_contract, dict)
    if declaration == "concrete_command":
        command = diff_contract["command"]
        assert isinstance(command, list)
        command[3] = "HEAD...HEAD"
    else:
        diff_contract[declaration] = "HEAD"
    allowlist_path.write_text(
        json.dumps(allowlist, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _commit_test_repository(repository, "attempt self-declared base ref")

    with pytest.raises(checker.ContractError, match=expected_error):
        checker.load_contract(repository)
    assert checker.main(["--root", str(repository)]) == 2
    assert "tenant-boundary contract error" in capsys.readouterr().err


@pytest.mark.parametrize("provide_base_ref", (True, False))
def test_impact_probe_is_red_through_external_or_default_real_commit_cli(
    tmp_path: Path,
    provide_base_ref: bool,
) -> None:
    """外部指定と凍結既定値のどちらでも強制点迂回を拒否する。"""
    relative = "pitchlog/services/impact_probe.py"
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: "pass\n"},
    )
    _point_default_base_ref_at(repository, base_ref)
    impact_probe = '''\
from sqlalchemy.orm import Session


def read_other_tenant(work: Session) -> object:
    return work.execute("SELECT * FROM games")
'''
    _write_test_repository_sources(repository, {relative: impact_probe})
    _commit_test_repository(repository, "add tenant boundary bypass")
    selected_base_ref = base_ref if provide_base_ref else None
    violations = checker.check_repository(
        repository,
        base_ref=selected_base_ref,
    )
    arguments = ["--root", str(repository)]
    if selected_base_ref is not None:
        arguments.extend(("--base-ref", selected_base_ref))

    assert (relative, "TB005") in {
        (violation.path, violation.code) for violation in violations
    }
    assert checker.main(arguments) == 1


@pytest.mark.parametrize("provide_base_ref", (True, False))
def test_safe_change_passes_external_or_default_real_commit_cli(
    tmp_path: Path,
    provide_base_ref: bool,
) -> None:
    """比較元の供給経路にかかわらず正当な変更を過剰拒否しない。"""
    relative = "pitchlog/services/report.py"
    baseline = 'REPORT_LABEL = "before"\n'
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    _point_default_base_ref_at(repository, base_ref)
    _write_test_repository_sources(
        repository,
        {relative: baseline.replace("before", "after")},
    )
    _commit_test_repository(repository, "update non-database report")
    selected_base_ref = base_ref if provide_base_ref else None
    arguments = ["--root", str(repository)]
    if selected_base_ref is not None:
        arguments.extend(("--base-ref", selected_base_ref))

    assert checker.check_repository(
        repository,
        base_ref=selected_base_ref,
    ) == []
    assert checker.main(arguments) == 0


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
    changed_files = checker.changed_files_from_diff(diff)

    assert changed == {"pitchlog/example.py": frozenset({3, 4, 9})}
    assert changed_files == {"pitchlog/example.py"}


def test_pure_line_deletion_is_red_through_real_commit_diff(tmp_path: Path) -> None:
    """新側追加行 0 の純粋削除でも ``--base-ref`` 経路で再検査する。"""
    relative = "pitchlog/services/deletion.py"
    baseline = '''\
from sqlalchemy.orm import Session


class Report:
    pass


def handler(work: Session, safe: Report) -> object:
    work = safe
    return work.execute()
'''
    head = baseline.replace("    work = safe\n", "")
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    source_path = repository / "backend" / "src" / relative
    source_path.write_text(head, encoding="utf-8")
    _commit_test_repository(repository, "remove safe rebinding")
    diff = checker._run_git(
        repository,
        ["diff", "-U0", f"{base_ref}...HEAD", "--", "backend/src"],
    )

    assert checker.changed_lines_from_diff(diff) == {relative: frozenset()}
    assert checker.changed_files_from_diff(diff) == {relative}
    violations = checker.check_repository(repository, base_ref=base_ref)

    assert "TB005" in {violation.code for violation in violations}
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_pure_rename_is_conservatively_red_through_real_commit_diff(
    tmp_path: Path,
) -> None:
    """純粋改名は rename 先を新規ファイルとして ``--base-ref`` 検査する。"""
    old_relative = "pitchlog/services/old_handler.py"
    new_relative = "pitchlog/services/new_handler.py"
    source = '''\
from sqlalchemy.orm import Session


def handler(work: Session) -> object:
    return work.execute()
'''
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {old_relative: source},
    )
    checker._run_git(
        repository,
        [
            "mv",
            f"backend/src/{old_relative}",
            f"backend/src/{new_relative}",
        ],
    )
    _commit_test_repository(repository, "rename handler")
    diff = checker._run_git(
        repository,
        ["diff", "-U0", f"{base_ref}...HEAD", "--", "backend/src"],
    )

    assert checker.changed_lines_from_diff(diff) == {}
    assert checker.changed_files_from_diff(diff) == {new_relative}
    violations = checker.check_repository(repository, base_ref=base_ref)

    assert "TB005" in {violation.code for violation in violations}
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_pure_rename_of_non_database_code_passes_real_commit_diff(
    tmp_path: Path,
) -> None:
    """非 DB コードの純粋改名は実コミット列と CLI の経路で通す。"""
    old_relative = "pitchlog/services/old_report.py"
    new_relative = "pitchlog/services/new_report.py"
    source = '''\
class Report:
    def execute(self) -> str:
        return "ready"


def render(report: Report) -> str:
    return report.execute()
'''
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {old_relative: source},
    )

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0

    checker._run_git(
        repository,
        [
            "mv",
            f"backend/src/{old_relative}",
            f"backend/src/{new_relative}",
        ],
    )
    _commit_test_repository(repository, "rename non-database report")

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0


def test_same_violation_moved_between_functions_is_red_through_real_commit_diff(
    tmp_path: Path,
) -> None:
    """同種違反を別関数へ移しても基準版の件数で相殺させない。"""
    relative = "pitchlog/services/moved_violation.py"
    baseline = '''\
from sqlalchemy.orm import Session


def alpha(work: Session) -> object:
    return work.execute()


def beta(work: Session) -> object:
    return None
'''
    head = baseline.replace(
        "def alpha(work: Session) -> object:\n    return work.execute()",
        "def alpha(work: Session) -> object:\n    return None",
    ).replace(
        "def beta(work: Session) -> object:\n    return None",
        "def beta(work: Session) -> object:\n    return work.execute()",
    )
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    source_path = repository / "backend" / "src" / relative
    source_path.write_text(head, encoding="utf-8")
    _commit_test_repository(repository, "move violation")

    violations = checker.check_repository(repository, base_ref=base_ref)

    assert {
        (violation.code, violation.scope)
        for violation in violations
        if violation.code == "TB005"
    } == {("TB005", "pitchlog.services.moved_violation.beta")}
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


def test_terminal_database_rebinding_stays_green_through_real_commit_diff(
    tmp_path: Path,
) -> None:
    """終端分岐だけの DB 再束縛を後続の非 DB receiver へ混入させない。"""
    relative = "pitchlog/services/terminal_rebinding.py"
    baseline = '''\
from sqlalchemy.orm import Session


class Report:
    pass


def handler(work: Report, database: Session, flag: bool) -> object:
    if flag:
        return None
    return work.execute()
'''
    head = baseline.replace(
        "    if flag:\n        return None",
        "    if flag:\n        work = database\n        return None",
    )
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )
    source_path = repository / "backend" / "src" / relative
    source_path.write_text(head, encoding="utf-8")
    _commit_test_repository(repository, "add terminal rebinding")

    violations = checker.check_repository(repository, base_ref=base_ref)

    assert violations == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0


def test_unchanged_preexisting_violation_is_not_reintroduced() -> None:
    """変更ファイル全体を再走査しても基準版と同じ違反は新規扱いしない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    baseline = """\
def can_cross_tenant() -> bool:
    return True


def ordinary_change() -> bool:
    return False
"""
    head = """\
def can_cross_tenant() -> bool:
    return True


def ordinary_change() -> bool:
    return True
"""

    violations = checker.scan_source_change(
        baseline,
        head,
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
    source = """\
from pitchlog.repositories.context import TenantContext


def make_tenant_context(tenant_id):
    return TenantContext(tenant_id)
"""

    violations = checker.scan_source(
        source,
        path="test_authz_tenant_context.py",
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


def test_tenant_context_integrity_secret_reference_outside_allowlist_is_red() -> None:
    """発行証跡のプロセス秘密を許可シンボル外から参照できない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from pitchlog.repositories.context import _TENANT_CONTEXT_SECRET

leaked = _TENANT_CONTEXT_SECRET
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/leak_context_secret.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB007"}


def test_tenant_context_integrity_secret_dynamic_reference_is_red() -> None:
    """getattr を使っても発行証跡の秘密へ到達できない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
import pitchlog.repositories.context as context_module

leaked = getattr(context_module, "_TENANT_CONTEXT_SECRET")
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/dynamic_context_secret.py",
        contract=contract,
    )

    assert {violation.code for violation in violations} == {"TB007"}


def test_known_non_database_receivers_and_unrelated_replace_pass() -> None:
    """由来が既知の非 DB 型にある同名メソッドと DTO 複製は拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
import dataclasses
from pitchlog.clients import ImportedClient


class NonDatabaseClient:
    def execute(self):
        return None

    def connect(self):
        return None

    def delete(self):
        return None

    def copy(self):
        return None

    def merge(self):
        return None


@dataclasses.dataclass(frozen=True)
class FrozenDto:
    value: int


def use_client(client: NonDatabaseClient, dto: FrozenDto):
    client.execute()
    client.connect()
    client.delete()
    client.copy()
    client.merge()
    return dataclasses.replace(dto, value=2)


def use_imported_client(client: ImportedClient):
    client.execute()
    client.connect()


def make_client() -> NonDatabaseClient:
    return NonDatabaseClient()


client = NonDatabaseClient()
factory_client = make_client()
dto = FrozenDto(value=1)
use_client(client, dto)
factory_client.execute()
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/non_database_client.py",
        contract=contract,
    )

    assert violations == []


def test_local_database_type_name_shadow_mutation_is_red() -> None:
    """安全なローカル型が DB 型名を shadow する変異だけを拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
class Report:
    pass


def render(work: Report):
    return work.execute("render")
"""
    mutated = source.replace("Report", "Session")
    changed_lines = _changed_lines_containing(
        mutated,
        "class Session",
        "work: Session",
    )
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )
    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/report_renderer.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    "insertion",
    (
        "    work = other\n",
        "    if flag:\n        work = other\n",
    ),
)
def test_non_database_receiver_rebinding_mutation_is_red(insertion: str) -> None:
    """非 DB 注釈を未解決値で上書きする直線・分岐変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
class Report:
    pass


def render(work: Report, other, flag):
    return work.execute("render")
"""
    mutated = source.replace(
        '    return work.execute("render")\n',
        f'{insertion}    return work.execute("render")\n',
    )
    changed_lines = _changed_lines_containing(mutated, "work = other")
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )
    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/report_rebinding.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


def test_unresolved_attribute_constructor_mutation_is_red() -> None:
    """receiver の型証明を外した属性 callable 変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from application.factories import ContextFactory


def make(mod: ContextFactory, tenant_id):
    return mod.TenantContext(tenant_id)
"""
    mutated = source.replace("mod: ContextFactory", "mod")
    changed_lines = _changed_lines_containing(mutated, "def make(mod,")
    assert _changed_lines_containing(mutated, "mod.TenantContext").isdisjoint(
        changed_lines
    )
    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/context_factory.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB007" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    ("typing_import", "safe_annotation", "database_annotation"),
    (
        ("Optional", "Optional[Report]", "Optional[Session]"),
        (
            "Annotated",
            'Annotated[Report, "dep"]',
            'Annotated[Session, "dep"]',
        ),
        ("Union", "Union[Report, None]", "Union[Session, None]"),
    ),
)
def test_database_type_inside_annotation_wrapper_mutation_is_red(
    typing_import: str,
    safe_annotation: str,
    database_annotation: str,
) -> None:
    """標準ラッパー内の注釈だけを DB 型へ変える変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
from typing import {typing_import}
from sqlalchemy.orm import Session


class Report:
    pass


def render(work: {safe_annotation}):
    return work.execute("render")
'''
    mutated = source.replace(safe_annotation, database_annotation)
    changed_lines = _changed_lines_containing(mutated, database_annotation)
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/wrapped_database_type.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    ("typing_import", "annotation"),
    (
        ("Optional", "Optional[Report]"),
        ("Annotated", 'Annotated[Report, "dep"]'),
        ("Union", "Union[Report, None]"),
    ),
)
def test_non_database_type_inside_annotation_wrapper_passes(
    typing_import: str,
    annotation: str,
) -> None:
    """全構成型が既知の非 DB 型ならラッパー注釈を許可する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
from typing import {typing_import}


class Report:
    pass


def render(work: {annotation}):
    return work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/wrapped_report.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


def test_unknown_union_member_mutation_is_red() -> None:
    """Union に未解決型が混ざる変異は非 DB 証明を失う。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = '''\
from typing import Union


class Report:
    pass


def render(work: Union[Report, None]):
    return work.execute("render")
'''
    mutated = source.replace(
        "Union[Report, None]",
        "Union[Report, UnknownDependency]",
    )
    changed_lines = _changed_lines_containing(
        mutated,
        "Union[Report, UnknownDependency]",
    )
    assert _changed_lines_containing(mutated, 'work.execute("render")').isdisjoint(
        changed_lines
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/unknown_union_member.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


def test_database_typed_class_attribute_mutation_is_red() -> None:
    """非 DB container の属性注釈だけを DB 型へ変える変異を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = '''\
from sqlalchemy.orm import Session


class Report:
    pass


class Dependencies:
    database: Report


def load(dependencies: Dependencies):
    return dependencies.database.execute(statement)
'''
    mutated = source.replace("database: Report", "database: Session")
    changed_lines = _changed_lines_containing(mutated, "database: Session")
    assert _changed_lines_containing(
        mutated,
        "dependencies.database.execute",
    ).isdisjoint(changed_lines)

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/dependencies.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    "use_expression",
    (
        "    handle = dependencies.make()\n    return handle.execute(statement)\n",
        "    return dependencies.make().execute(statement)\n",
    ),
)
def test_unresolved_method_result_mutation_is_red(use_expression: str) -> None:
    """未解決メソッド結果は代入有無にかかわらず DB 候補として拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


class Dependencies:
    def make(self) -> Report:
        return Report()


def load(dependencies: Dependencies):
{use_expression}'''
    mutated = source.replace(" -> Report", "")
    changed_lines = _changed_lines_containing(mutated, "def make(self):")
    assert _changed_lines_containing(mutated, ".execute(statement)").isdisjoint(
        changed_lines
    )

    violations = _scan_diff_mutation(
        source,
        mutated,
        path="pitchlog/services/dependency_factory.py",
        changed_lines=changed_lines,
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    ("receiver_name", "receiver_type", "method"),
    (
        ("session", "Report", "execute"),
        ("connection", "Report", "execute"),
        ("engine", "Pool", "connect"),
        ("db_engine", "Pool", "connect"),
    ),
)
def test_database_receiver_name_on_known_non_database_type_passes(
    receiver_name: str,
    receiver_type: str,
    method: str,
) -> None:
    """inventory の receiver 名だけでは既知の非 DB 型を拒否しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


class Pool:
    pass


def use({receiver_name}: {receiver_type}):
    return {receiver_name}.{method}()
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/named_non_database_receiver.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize(
    "terminal_branch",
    (
        "        return None",
        "        raise ValueError",
    ),
)
def test_terminal_if_branch_does_not_pollute_following_flow(
    terminal_branch: str,
) -> None:
    """return・raise で終端した分岐を後続の由来へ合流しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


def render(work: Report, other, flag):
    if flag:
        work = other
{terminal_branch}
    return work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/terminal_branch.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


@pytest.mark.parametrize("loop_control", ("break", "continue"))
def test_terminal_loop_branch_does_not_pollute_remaining_body(
    loop_control: str,
) -> None:
    """break・continue で終端した分岐を同一 loop body の後続へ合流しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = f'''\
class Report:
    pass


def render(work: Report, other, items):
    for item in items:
        if item:
            work = other
            {loop_control}
        work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/terminal_loop_branch.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


def test_terminal_try_branches_do_not_pollute_following_flow() -> None:
    """try の return・raise 経路を後続へ合流しない。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = '''\
class Report:
    pass


def render(work: Report, other, flag):
    try:
        if flag:
            work = other
            return None
    except ValueError:
        work = other
        raise
    return work.execute("render")
'''

    violations = checker.scan_source_change(
        None,
        source,
        path="pitchlog/services/terminal_try_branch.py",
        changed_lines=frozenset(range(1, len(source.splitlines()) + 1)),
        contract=contract,
    )

    assert violations == []


def test_database_receiver_from_local_factory_return_is_red() -> None:
    """ローカル factory の戻り型が DB receiver なら迂回を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from sqlalchemy.orm import Session


def make_session() -> Session:
    return Session()


handle = make_session()
handle.execute(statement)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/local_session_factory.py",
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


def test_imported_object_without_non_database_type_proof_is_red() -> None:
    """import だけでは非 DB receiver と証明せず、危険メソッド名を拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    source = """\
from application.dependencies import client

client.execute(statement)
"""

    violations = checker.scan_source(
        source,
        path="pitchlog/services/imported_unknown_client.py",
        contract=contract,
    )

    assert "TB005" in {violation.code for violation in violations}


@pytest.mark.parametrize(
    "source",
    (
        """\
from pitchlog.repositories.context import _tenant_context_proof as derive

proof_factory = derive
proof_factory(tenant_id)
""",
        """\
import pitchlog.repositories.context as context_module

module_alias = context_module
derive = module_alias._tenant_context_proof
proof_factory = derive
proof_factory(tenant_id)
""",
        """\
def forge(factory, tenant_id):
    return factory(tenant_id)
""",
    ),
)
def test_proof_factory_aliases_and_unresolved_callable_are_red(source: str) -> None:
    """証跡導出の多段別名と未解決 callable を fail-closed で拒否する。"""
    contract = checker.load_contract(REPOSITORY_ROOT)

    violations = checker.scan_source(
        source,
        path="pitchlog/services/context_proof_bypass.py",
        contract=contract,
    )

    assert "TB007" in {violation.code for violation in violations}


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
    """空差分でも実製品の強制点を再検査して通す。"""
    contract = checker.load_contract(REPOSITORY_ROOT)
    head_sources = checker._git_snapshot(REPOSITORY_ROOT, "HEAD")
    population = checker._inspection_population(
        {},
        head_sources,
        contract=contract,
    )
    violations = checker._changed_source_violations(
        REPOSITORY_ROOT,
        population,
        contract,
    )

    assert population
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

    violations = _scan_diff_mutation(
        source,
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

    violations = _scan_diff_mutation(
        source,
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

    violations = _scan_diff_mutation(
        source,
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

    violations = _scan_diff_mutation(
        source,
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


@pytest.mark.parametrize(
    "case_id",
    (
        "base-direct-sql",
        "binding-nonlocal-set-config",
        "base-call-outside-allowed-symbol",
        "binding-unlisted-symbol",
    ),
)
def test_actual_implementation_mutation_is_red_through_real_commit_diff(
    tmp_path: Path,
    case_id: str,
) -> None:
    """実製品への 4 変異を実コミット列と CLI の経路で拒否する。"""
    relative, baseline, mutated = _actual_implementation_mutation(case_id)
    repository, base_ref = _initialize_test_repository(
        tmp_path,
        {relative: baseline},
    )

    assert checker.check_repository(repository, base_ref=base_ref) == []
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 0

    _write_test_repository_sources(repository, {relative: mutated})
    _commit_test_repository(repository, f"apply {case_id} mutation")
    violations = checker.check_repository(repository, base_ref=base_ref)

    assert (relative, "TB005") in {
        (violation.path, violation.code) for violation in violations
    }
    assert checker.main(["--root", str(repository), "--base-ref", base_ref]) == 1


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


def test_default_base_ref_belongs_only_to_frozen_checker_procedure() -> None:
    """比較元の実値を資産へ戻さず、検査器の変更履歴対象に固定する。"""
    allowlist: dict[str, Any] = json.loads(
        (REPOSITORY_ROOT / checker.DEFAULT_ALLOWLIST).read_text(encoding="utf-8")
    )

    assert allowlist["diff"] == {
        "command": [
            "git",
            "diff",
            "-U0",
            "{base_ref}...HEAD",
            "--",
            "backend/src",
        ]
    }
    assert checker.DEFAULT_BASE_REF == "origin/develop"
    assert allowlist["baseline_control"]["identity"]["frozen_projection"][
        "external_files"
    ] == ["scripts/check_tenant_boundary_bypass.py"]
