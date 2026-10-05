"""製品 RLS の対象確認と撤去入口を DB なしで検証する。"""

import importlib.util
import os
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_runner() -> Any:
    """DB 依存を読まずに runner.py を実ファイルから取り込む。"""
    name = "product_rls_real_schema_runner_module"
    path = Path(__file__).resolve().parents[1] / "scripts/product_rls_real_schema/runner.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


VALID_EVIDENCE = runner.TargetEvidence(
    connected_cluster="101",
    deployed_cluster="101",
    shared_cluster="202",
    operand_database="approved",
    approved_database="approved",
    test_role_database="approved",
    connected_database="initial",
    initial_database="initial",
    admin_user="administrator",
    admin_is_superuser=True,
)


def _assert_stops_before_drop(
    evidence: runner.TargetEvidence, other_connections: int | None = 0
) -> None:
    calls: list[str] = []

    with pytest.raises(runner.RunnerError):
        runner.guard_drop(evidence, other_connections, lambda: calls.append("DROP"))

    assert calls == []
    assert runner.main(
        lambda: runner.guard_drop(evidence, other_connections, lambda: calls.append("DROP"))
    ) == 1
    assert calls == []


def test_all_target_conditions_allow_first_drop() -> None:
    calls: list[str] = []

    runner.guard_drop(VALID_EVIDENCE, 0, lambda: calls.append("DROP"))

    assert calls == ["DROP"]


def test_shared_cluster_identity_stops_before_drop() -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, shared_cluster="101"))


def test_connected_server_must_match_actual_compose_container() -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, deployed_cluster="303"))


@pytest.mark.parametrize("operand", ("approved-extra", "approv", "other"))
def test_database_operand_requires_exact_approved_name(operand: str) -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, operand_database=operand))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("connected_cluster", None),
        ("deployed_cluster", None),
        ("shared_cluster", None),
        ("approved_database", None),
        ("admin_is_superuser", None),
    ),
)
def test_unavailable_target_value_stops_before_drop(field: str, value: None) -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, **{field: value}))


@pytest.mark.parametrize("other_connections", (1, 2, None))
def test_other_user_connection_stops_before_drop(other_connections: int | None) -> None:
    _assert_stops_before_drop(VALID_EVIDENCE, other_connections)


def test_test_role_dsn_database_must_match_approved_name() -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, test_role_database="other"))


def test_admin_connection_must_use_initial_database_and_superuser() -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, connected_database="approved"))
    _assert_stops_before_drop(replace(VALID_EVIDENCE, admin_is_superuser=False))


def test_target_digest_changes_when_only_database_name_changes() -> None:
    first = runner._target_digest("101", "first")
    second = runner._target_digest("101", "second")

    assert first != second
    assert len(first) == len(second) == 64


def test_role_names_come_from_three_sources() -> None:
    config = runner._load_targets()
    roles = runner._roles(config, "tested_from_dsn")

    assert roles.owner == runner._role_from_asset(config.owner_role_asset)
    assert roles.temporary == runner._temporary_role(
        config.temporary_role_source, config.temporary_role_constant
    )
    assert roles.tested == "tested_from_dsn"
    assert set(roles.ordered) == {
        *(runner._role_from_asset(path) for path in config.role_assets_dir.glob("*.sql")),
        roles.tested,
        roles.temporary,
    }


def test_compose_uses_project_from_target_asset() -> None:
    """worktree でも固定の Compose プロジェクトを指す。"""
    config = runner._load_targets()

    assert config.compose_project == "pitchlog"
    assert runner._compose_args(config)[2:4] == ["-p", config.compose_project]


def test_migration_url_uses_owner_on_target_database() -> None:
    admin = "postgresql://admin:dummy@127.0.0.1:65432/initial"

    assert runner._migration_url(admin, "target", "owner", "temporary") == (
        "postgresql+psycopg://owner:temporary@127.0.0.1:65432/target"
    )


def test_test_environment_uses_frozen_names_and_target_database() -> None:
    """試験の DSN 名は資産から取り、値だけを対象 DB へ向ける。"""
    admin = "postgresql://admin:dummy@127.0.0.1:65432/initial"
    tested = "postgresql://tested:dummy@127.0.0.1:65432/target"

    assert runner._test_environment(admin, tested, "target") == {
        "PITCHLOG_TEST_ADMIN_DSN": "postgresql://admin:dummy@127.0.0.1:65432/target",
        "PITCHLOG_TEST_ROLE_DSN": tested,
    }
    with pytest.raises(runner.RunnerError):
        runner._test_environment(admin, tested, "other")


def test_test_observations_require_all_nodes_on_exact_target() -> None:
    """資産が定める node の接続に欠落または別対象があれば中止する。"""
    expected_nodes = runner._load_targets().expected_test_nodes
    count = expected_nodes * runner.OBSERVED_CONNECTIONS_PER_NODE
    observations = [("101", "target")] * count
    runner._validate_test_observations(observations, "101", "target", expected_nodes)
    with pytest.raises(runner.RunnerError):
        runner._validate_test_observations(
            observations, "101", "target", expected_nodes + 1
        )

    with pytest.raises(runner.RunnerError):
        runner._validate_test_observations(
            observations[:-1], "101", "target", expected_nodes
        )
    observations[-1] = ("101", "other")
    with pytest.raises(runner.RunnerError):
        runner._validate_test_observations(observations, "101", "target", expected_nodes)


def test_product_tests_use_in_process_supply_and_ignore_pre_ddl_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """試験が失敗しても供給内の接続先だけで判定し、環境を戻す。"""
    calls: list[str] = []
    observations = SimpleNamespace(connections=[])

    @contextmanager
    def supply(**kwargs: Any) -> Any:
        calls.append("enter")
        assert kwargs["owner_dsn"] == "owner-secret"
        try:
            yield observations
        finally:
            calls.append("exit")

    def fake_pytest_main(arguments: list[str]) -> int:
        calls.append("pytest")
        assert len([arg for arg in arguments if arg.startswith("tests/db/test_")]) == 3
        assert os.environ["PITCHLOG_TEST_ADMIN_DSN"].endswith("/target")
        expected_nodes = runner._load_targets().expected_test_nodes
        observations.connections.extend(
            [("101", "target")] * (expected_nodes * runner.OBSERVED_CONNECTIONS_PER_NODE)
        )
        print("hidden-connection-marker")
        return 1

    fixture_module = SimpleNamespace(
        DisposablePostgres=lambda **kwargs: SimpleNamespace(**kwargs),
        supply_external_product_catalog=supply,
    )
    real_import = runner.importlib.import_module
    monkeypatch.setattr(runner, "_container_cluster", lambda *_: "101")
    monkeypatch.setattr(runner, "_container_id", lambda *_: "container")

    def fake_import(name: str) -> Any:
        return fixture_module if name == "db_fixtures" else SimpleNamespace(main=fake_pytest_main)

    monkeypatch.setattr(
        runner.importlib,
        "import_module",
        fake_import,
    )
    admin = "postgresql://admin:dummy@127.0.0.1:65432/initial"
    tested = "postgresql://tested:dummy@127.0.0.1:65432/target"
    original_directory = Path.cwd()
    try:
        runner._run_product_tests(
            runner._load_targets(),
            admin,
            "owner-secret",
            tested,
            "target",
            runner._target_digest("101", "target"),
        )
    finally:
        monkeypatch.setattr(runner.importlib, "import_module", real_import)

    assert calls == ["enter", "pytest", "exit"]
    assert Path.cwd() == original_directory
    assert "hidden-connection-marker" not in capsys.readouterr().out


def test_main_passes_generated_owner_connection_without_printing_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """再構築時の所有者接続を戻り値で受けて供給し、出力しない。"""
    received: list[str] = []

    def prepare() -> runner.PreparedTarget:
        owner_dsn = "postgresql://owner:private-marker@127.0.0.1:65432/target"
        return runner.PreparedTarget("generation", "digest", "head", owner_dsn)

    def run_tests(*args: Any) -> None:
        received.append(args[2])

    monkeypatch.setattr(runner, "_required_environment", lambda _: "unused")
    monkeypatch.setattr(runner, "_run_product_tests", run_tests)

    assert runner.main(prepare) == 0
    assert received == [
        "postgresql://owner:private-marker@127.0.0.1:65432/target"
    ]
    output = capsys.readouterr()
    assert "private-marker" not in output.out + output.err


def test_cli_does_not_print_unexpected_exception_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail() -> runner.PreparedTarget:
        raise RuntimeError("sensitive-marker")

    assert runner.main(fail) == 1
    assert "sensitive-marker" not in capsys.readouterr().err
