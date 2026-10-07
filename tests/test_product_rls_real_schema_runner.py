"""製品 RLS の対象確認と撤去入口を DB なしで検証する。"""

import base64
import importlib.util
import json
import os
import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
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
    test_role_database="initial",
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


def test_test_role_dsn_database_must_match_initial_database() -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, test_role_database="other"))
    _assert_stops_before_drop(replace(VALID_EVIDENCE, test_role_database="approved"))


def test_admin_connection_must_use_initial_database_and_superuser() -> None:
    _assert_stops_before_drop(replace(VALID_EVIDENCE, connected_database="approved"))
    _assert_stops_before_drop(replace(VALID_EVIDENCE, admin_is_superuser=False))


@pytest.mark.parametrize(
    (
        "connected_cluster",
        "deployed_cluster",
        "connected_database",
        "admin_user",
        "operand",
        "connections",
    ),
    (
        ("303", "101", "initial", "administrator", "approved", 0),
        (None, "101", "initial", "administrator", "approved", 0),
        ("", "101", "initial", "administrator", "approved", 0),
        ("101", "101", None, "administrator", "approved", 0),
        ("101", "101", "", "administrator", "approved", 0),
        ("101", "101", "initial", None, "approved", 0),
        ("101", "101", "initial", "", "approved", 0),
        ("202", "202", "initial", "administrator", "approved", 0),
        ("101", "101", "initial", "administrator", "other", 0),
        ("101", "101", "initial", "administrator", "approved", 1),
    ),
)
def test_adverse_target_values_never_issue_first_drop(
    monkeypatch: pytest.MonkeyPatch,
    connected_cluster: str | None,
    deployed_cluster: str,
    connected_database: str | None,
    admin_user: str | None,
    operand: str,
    connections: int,
) -> None:
    """偽装・欠損・共有・別 DB・他接続を SQL 発行前に拒否する。"""
    sql: list[str] = []

    class FakeCursor:
        """問い合わせと DROP を記録するカーソル。"""

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
            sql.append(statement)

        def fetchone(self) -> tuple[Any, ...]:
            return (connected_cluster, connected_database, admin_user, True, connections)

    connection = SimpleNamespace(autocommit=True, cursor=FakeCursor)
    config = runner._load_targets()
    monkeypatch.setattr(
        runner,
        "_container_cluster",
        lambda _, service: deployed_cluster if service == config.compose_service else "202",
    )

    runner._set_safe_search_path(connection)
    evidence, count = runner._evidence(
        config, connection, "approved", "initial", "initial", operand,
        with_connections=True,
    )
    with pytest.raises(runner.RunnerError):
        runner.guard_drop(
            evidence,
            count,
            lambda: runner._execute(connection, 'DROP DATABASE IF EXISTS "approved"'),
        )

    assert sql[0] == "SET SESSION search_path = pg_catalog"
    assert "pg_catalog.pg_control_system()" in sql[1]
    assert "pg_catalog.pg_stat_activity" in sql[1]
    assert not any(statement.startswith("DROP ") for statement in sql)


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


def test_scram_verifier_matches_rfc_7677_example() -> None:
    """RFC 7677 の pencil・salt・4096 回から固定した検証子と照合する。"""
    salt = base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ==")
    expected = (
        "SCRAM-SHA-256$4096:W22ZaJ0SNY7soEsUEjb6gQ==$"
        "WG5d8oPm3OtcPnkdi4Uo7BkeZkBFzpcXkuLmtbsT4qY=:"
        "wfPLwcE6nTWhTAmQ7tl2KeoiWGPlZqQxSrmfPwDl2dU="
    )
    verifier = runner._scram_verifier("pencil", salt, 4096)

    assert verifier == expected
    assert verifier.startswith("SCRAM-SHA-256$")
    assert "pencil" not in verifier


def test_role_password_sql_contains_only_scram_verifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """実際の CREATE・ALTER 文に平文を含めない。"""
    monkeypatch.setattr(runner.secrets, "token_bytes", lambda _: b"fixed-salt-16byt")
    plaintext = "plain-password-marker"
    statements = (
        runner._owner_create_sql("pitchlog_owner", plaintext),
        runner._app_password_sql(plaintext),
    )

    assert statements[0].startswith('CREATE ROLE "pitchlog_owner"')
    assert statements[1].startswith('ALTER ROLE "pitchlog_app"')
    assert all("PASSWORD 'SCRAM-SHA-256$" in statement for statement in statements)
    assert all(plaintext not in statement for statement in statements)


def test_safe_search_path_is_committed_before_later_rollback() -> None:
    """接続直後の設定を commit し、後の rollback で戻さない。"""
    events: list[str] = []

    class FakeCursor:
        """検索経路の設定を記録するカーソル。"""

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def execute(self, statement: str) -> None:
            events.append(statement)

    connection = SimpleNamespace(
        autocommit=False,
        cursor=FakeCursor,
        commit=lambda: events.append("commit"),
        rollback=lambda: events.append("rollback"),
    )

    runner._set_safe_search_path(connection)
    connection.rollback()

    assert events == ["SET SESSION search_path = pg_catalog", "commit", "rollback"]


def test_remaining_catalog_queries_are_schema_qualified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """対象照合・ロール存在・検査主体の全問い合わせを修飾する。"""
    queries: list[str] = []

    def fetch_one(_connection: Any, query: str, *_params: Any) -> tuple[Any, ...]:
        queries.append(query)
        if "system_identifier" in query:
            return (101, "approved")
        if "role.oid" in query:
            return (42,)
        return (True,)

    config = runner._load_targets()
    monkeypatch.setattr(runner, "_fetch_one", fetch_one)
    monkeypatch.setattr(
        runner,
        "_container_cluster",
        lambda _, service: "101" if service == config.compose_service else "202",
    )
    connection = SimpleNamespace(rollback=lambda: None)

    runner._assert_target_connection(config, connection, "101", "approved")
    assert runner._role_exists(connection, "pitchlog_owner")
    assert runner._catalog_violations(
        connection,
        lambda *_args, **_kwargs: SimpleNamespace(ok=True, violations=()),
    ) == 0
    assert "pg_catalog.pg_control_system()" in queries[0]
    assert "pg_catalog.current_database()" in queries[0]
    assert "pg_catalog.pg_roles" in queries[1]
    assert "pg_catalog.current_user()" in queries[2]


def test_test_environment_uses_frozen_names_and_initial_database() -> None:
    """試験の 2 接続を初期化時 DB へ向け、対象 DB を拒否する。"""
    admin = "postgresql://admin:dummy@127.0.0.1:65432/initial"
    tested = "postgresql://tested:dummy@127.0.0.1:65432/initial"

    assert runner._test_environment(admin, tested, "target", "initial") == {
        "PITCHLOG_TEST_ADMIN_DSN": admin,
        "PITCHLOG_TEST_ROLE_DSN": tested,
    }
    with pytest.raises(runner.RunnerError):
        runner._test_environment(admin, tested, "target", "other")
    target_role_dsn = "postgresql://tested:dummy@127.0.0.1:65432/target"
    with pytest.raises(runner.RunnerError):
        runner._test_environment(admin, target_role_dsn, "target", "initial")


def test_test_observations_require_all_nodes_on_exact_target() -> None:
    """資産が定める node の接続に欠落または別対象があれば中止する。"""
    expected_nodes = len(runner._expected_nodes(runner._load_targets().expected_nodes_asset))
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


def test_product_application_checks_target_before_apply_and_catalog_afterward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """適用直前の照合から適用・検査・拒否試行への順を固定する。"""
    events: list[str] = []

    class FakeProvisioningError(Exception):
        """非許可主体の適用拒否を表す。"""

    class FakeConnection:
        """適用主体だけを持つ DB 不要の接続。"""

        def __init__(self, kind: str) -> None:
            self.kind = kind
            self.autocommit = False

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def rollback(self) -> None:
            pass

        def commit(self) -> None:
            pass

    def connect(dsn: str) -> FakeConnection:
        if "pitchlog_app:" in dsn:
            return FakeConnection("app")
        if "owner:" in dsn:
            return FakeConnection("owner")
        return FakeConnection("admin")

    def apply(connection: FakeConnection) -> None:
        if connection.kind == "admin":
            events.append("apply")
            return
        events.append(f"reject_{connection.kind}")
        raise FakeProvisioningError("rejected")

    provisioning = SimpleNamespace(
        apply_product_authz_ddl=apply,
        ProductProvisioningError=FakeProvisioningError,
    )
    catalog = SimpleNamespace(inspect_product_authz_catalog=lambda *_: None)
    real_import = runner.importlib.import_module

    def fake_import(name: str) -> Any:
        return provisioning if name.endswith("product_provisioning") else catalog

    monkeypatch.setattr(runner.importlib, "import_module", fake_import)
    monkeypatch.setattr(runner, "_driver", lambda: SimpleNamespace(connect=connect))
    monkeypatch.setattr(
        runner, "_assert_target_connection", lambda *_: events.append("target_check")
    )
    monkeypatch.setattr(
        runner, "_catalog_violations", lambda *_: events.append("catalog") or 0
    )
    monkeypatch.setattr(
        runner,
        "_execute",
        lambda _, sql: events.append(
            "search_path"
            if sql.startswith("SET SESSION")
            else "clear_password"
            if sql.endswith("PASSWORD NULL")
            else "set_password"
        ),
    )
    monkeypatch.setattr(runner.secrets, "token_urlsafe", lambda _: "temporary")
    admin = "postgresql://admin:dummy@127.0.0.1:65432/initial"
    owner = "postgresql://owner:dummy@127.0.0.1:65432/target"
    try:
        result = runner._apply_product_ddl(
            runner._load_targets(), admin, owner, "target", "101", "generation"
        )
    finally:
        monkeypatch.setattr(runner.importlib, "import_module", real_import)

    assert events == [
        "search_path",
        "target_check",
        "apply",
        "catalog",
        "search_path",
        "catalog",
        "reject_owner",
        "catalog",
        "target_check",
        "set_password",
        "search_path",
        "catalog",
        "reject_app",
        "catalog",
        "target_check",
        "clear_password",
        "catalog",
    ]
    assert result == runner.ApplicationResult("generation", "generation", 0)


def test_catalog_violation_stops_product_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """カタログ違反を成功扱いにせず中止する。"""
    connection = SimpleNamespace(rollback=lambda: None)
    monkeypatch.setattr(runner, "_fetch_one", lambda *_: (42,))

    with pytest.raises(runner.RunnerError, match="カタログ"):
        runner._catalog_violations(
            connection,
            lambda *_args, **_kwargs: SimpleNamespace(
                ok=False, violations=("violation",)
            ),
        )


def test_unrejected_application_stops_runner() -> None:
    """非許可主体の適用が通れば中止する。"""
    connection = SimpleNamespace(rollback=lambda: None)

    with pytest.raises(runner.RunnerError, match="拒否されなかった"):
        runner._require_application_rejection(
            connection, lambda _: None, RuntimeError
        )


def _passed_reports(nodes: frozenset[str]) -> runner._NodeReports:
    """各 node の全フェーズを passed とした観測を作る。"""
    reports = runner._NodeReports()
    reports.outcomes = {
        node: [
            ("setup", "passed", False),
            ("call", "passed", False),
            ("teardown", "passed", False),
        ]
        for node in nodes
    }
    return reports


def test_missing_executed_node_is_rejected() -> None:
    """期待集合の node が 1 件欠ければ差分を示して中止する。"""
    expected = runner._expected_nodes(runner._load_targets().expected_nodes_asset)
    missing = min(expected)
    reports = _passed_reports(expected - {missing})

    with pytest.raises(runner.RunnerError, match="不足") as error:
        runner._validate_node_reports(expected, reports, 0)
    assert missing in str(error.value)


def test_unexpected_executed_node_is_rejected() -> None:
    """期待集合に無い node が 1 件混ざれば差分を示して中止する。"""
    expected = runner._expected_nodes(runner._load_targets().expected_nodes_asset)
    extra = "tests/db/test_product_authz_other_profiles.py::test_unexpected"
    reports = _passed_reports(expected | {extra})

    with pytest.raises(runner.RunnerError, match="余分") as error:
        runner._validate_node_reports(expected, reports, 0)
    assert extra in str(error.value)


def test_skipped_node_is_not_counted_as_green() -> None:
    """48 件がそろっていても skip を passed に数えない。"""
    expected = runner._expected_nodes(runner._load_targets().expected_nodes_asset)
    reports = _passed_reports(expected)
    skipped = min(expected)
    reports.outcomes[skipped][1] = ("call", "skipped", False)

    with pytest.raises(runner.RunnerError, match="全件 passed") as error:
        runner._validate_node_reports(expected, reports, 0)
    assert skipped in str(error.value)


def test_different_generation_ids_are_rejected() -> None:
    """適用・カタログ検査・再実行の生成回のずれを拒否する。"""
    prepared = runner.PreparedTarget("generation", "digest", "head", "private")
    report = Path("/tmp/product-rls-generation-demo/report.xml")
    for application_id, catalog_id, test_id in (
        ("other", "generation", "generation"),
        ("generation", "other", "generation"),
        ("generation", "generation", "other"),
    ):
        result = runner.RunResult(
            runner.ApplicationResult(application_id, catalog_id, 0),
            runner.TestResult(test_id, "nodes", report, True),
        )
        with pytest.raises(runner.RunnerError, match="生成 ID"):
            runner._assert_generation_ids(prepared, result)


def test_docker_is_unreachable_in_filtered_path_and_restored_afterward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """複数の docker 配置ディレクトリをすべて外し、元の PATH へ戻す。"""
    first = tmp_path / "first"
    second = tmp_path / "second"
    safe = tmp_path / "safe"
    for directory in (first, second, safe):
        directory.mkdir()
    for directory in (first, second):
        docker = directory / "docker"
        docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        docker.chmod(0o755)
    original = os.pathsep.join(str(path) for path in (first, safe, second))
    monkeypatch.setenv("PATH", original)
    assert runner.shutil.which("docker") == str(first / "docker")

    with runner._without_docker_on_path():
        assert os.environ["PATH"] == str(safe)
        assert runner.shutil.which("docker") is None

    assert os.environ["PATH"] == original
    assert runner.shutil.which("docker") == str(first / "docker")


def test_docker_constraint_refuses_unreachable_check_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATH を絞った後も docker が見えれば中止し、PATH を戻す。"""
    monkeypatch.setenv("PATH", "/dev/null")
    monkeypatch.setattr(runner.shutil, "which", lambda *_args, **_kwargs: "/fake/docker")

    with pytest.raises(runner.RunnerError, match="docker"):
        with runner._without_docker_on_path():
            pytest.fail("到達検査が通った")

    assert os.environ["PATH"] == "/dev/null"


def test_docker_constraint_restores_path_after_test_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """試験が例外で終わっても元の PATH を復元する。"""
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(ValueError, match="test failed"):
        with runner._without_docker_on_path():
            assert runner.shutil.which("docker") is None
            raise ValueError("test failed")

    assert os.environ["PATH"] == str(tmp_path)
    assert runner.shutil.which("docker") == str(docker)


def test_junit_report_keeps_only_names_and_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """pytest の XML から接続文字列や捕捉出力を除いて残す。"""
    config = runner._load_targets()
    expected = runner._expected_nodes(config.expected_nodes_asset)
    observed = SimpleNamespace(
        connections=[("101", "target")]
        * (len(expected) * runner.OBSERVED_CONNECTIONS_PER_NODE)
    )
    original_import = runner.importlib.import_module
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert runner.shutil.which("docker") == str(docker)

    def fake_main(args: list[str], *, plugins: list[Any]) -> int:
        assert runner.shutil.which("docker") is None
        report_arg = next(arg for arg in args if arg.startswith("--junitxml="))
        report_path = Path(report_arg.split("=", 1)[1])
        suites = ET.Element("testsuites", hostname="private-marker")
        suite = ET.SubElement(suites, "testsuite", hostname="private-marker")
        for node in expected:
            module, name = node.split("::", 1)
            testcase = ET.SubElement(
                suite, "testcase", classname=Path(module).stem, name=name
            )
            ET.SubElement(testcase, "system-out").text = "postgresql://private-marker"
            for phase in ("setup", "call", "teardown"):
                plugins[0].pytest_runtest_logreport(
                    SimpleNamespace(nodeid=node, when=phase, outcome="passed")
                )
        ET.ElementTree(suites).write(report_path, encoding="utf-8")
        print("private-marker")
        return 0

    def fake_import(name: str) -> Any:
        return SimpleNamespace(main=fake_main) if name == "pytest" else original_import(name)

    monkeypatch.setattr(runner.importlib, "import_module", fake_import)
    result = runner._run_product_tests(config, observed, "101", "target", "generation")
    assert runner.shutil.which("docker") == str(docker)
    assert os.environ["PATH"] == str(tmp_path)
    assert result.docker_unreachable_during_tests is True
    report = result.junit_report.read_text(encoding="utf-8")
    assert "private-marker" not in report + capsys.readouterr().out
    assert "postgresql://" not in report
    assert len(ET.fromstring(report).findall(".//testcase")) == len(expected)


def test_junit_failure_details_are_redacted(tmp_path: Path) -> None:
    """失敗時の例外文に含まれる接続文字列も成果物へ残さない。"""
    node = "tests/db/test_product_authz_other_profiles.py::test_example"
    path = tmp_path / "report.xml"
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    case = ET.SubElement(
        suite,
        "testcase",
        classname="tests.db.test_product_authz_other_profiles",
        name="test_example",
    )
    failure = ET.SubElement(case, "failure", message="postgresql://private-marker")
    failure.text = "postgresql://private-marker"
    ET.ElementTree(root).write(path, encoding="utf-8")

    assert runner._redact_junit_report(path, frozenset({node})) == [
        ("test_product_authz_other_profiles", "test_example", "failure")
    ]
    report = path.read_text(encoding="utf-8")
    assert "private-marker" not in report
    assert "<failure" in report


def test_product_evidence_applies_before_in_process_tests(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """同一の供給内で適用から試験へ進み、環境を戻す。"""
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

    def fake_run_tests(*args: Any) -> runner.TestResult:
        calls.append("pytest")
        assert os.environ["PITCHLOG_TEST_ADMIN_DSN"].endswith("/initial")
        return runner.TestResult(
            "generation", "digest", Path("/tmp/product-rls-generation-demo/report.xml"), True
        )

    fixture_module = SimpleNamespace(
        DisposablePostgres=lambda **kwargs: SimpleNamespace(**kwargs),
        supply_external_product_catalog=supply,
    )
    real_import = runner.importlib.import_module
    monkeypatch.setattr(runner, "_container_cluster", lambda *_: "101")
    monkeypatch.setattr(runner, "_container_id", lambda *_: "container")
    monkeypatch.setattr(
        runner,
        "_apply_product_ddl",
        lambda *_: calls.append("apply")
        or runner.ApplicationResult("generation", "generation", 0),
    )
    monkeypatch.setattr(runner, "_run_product_tests", fake_run_tests)

    def fake_import(name: str) -> Any:
        assert name == "db_fixtures"
        return fixture_module

    monkeypatch.setattr(
        runner.importlib,
        "import_module",
        fake_import,
    )
    admin = "postgresql://admin:dummy@127.0.0.1:65432/initial"
    tested = "postgresql://tested:dummy@127.0.0.1:65432/initial"
    original_directory = Path.cwd()
    try:
        result = runner._run_product_evidence(
            runner._load_targets(),
            admin,
            "owner-secret",
            tested,
            "target",
            "initial",
            runner._target_digest("101", "target"),
            "generation",
        )
    finally:
        monkeypatch.setattr(runner.importlib, "import_module", real_import)

    assert result.application.catalog_violations == 0
    assert result.tests.generation_id == "generation"
    assert calls == ["enter", "apply", "pytest", "exit"]
    assert Path.cwd() == original_directory
    assert "hidden-connection-marker" not in capsys.readouterr().out


def test_main_passes_generated_owner_connection_without_printing_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """再構築時の所有者接続を戻り値で受けて供給し、出力しない。"""
    received: list[str] = []

    def prepare() -> runner.PreparedTarget:
        owner_dsn = (
            "postgresql://user-private:password-private@host-private.invalid:65432/"
            "database-private"
        )
        return runner.PreparedTarget("generation", "digest", "head", owner_dsn)

    def run_tests(*args: Any) -> runner.RunResult:
        received.append(args[2])
        return runner.RunResult(
            runner.ApplicationResult("generation", "generation", 0),
            runner.TestResult(
                "generation",
                "node-digest",
                Path("/tmp/product-rls-generation-demo/report.xml"),
                True,
            ),
        )

    monkeypatch.setattr(runner, "_required_environment", lambda _: "unused")
    monkeypatch.setattr(runner, "_run_product_evidence", run_tests)
    monkeypatch.setattr(runner, "_ddl_asset_digest", lambda: "ddl-digest")
    monkeypatch.setattr(runner, "_test_tree_commit", lambda: "a" * 40)

    assert runner.main(prepare) == 0
    assert received == [
        "postgresql://user-private:password-private@host-private.invalid:65432/"
        "database-private"
    ]
    output = capsys.readouterr()
    assert all(
        value not in output.out + output.err
        for value in (
            "postgresql://",
            "user-private",
            "password-private",
            "host-private.invalid",
            "65432",
            "database-private",
        )
    )
    evidence = json.loads(output.out)
    started_at = datetime.fromisoformat(evidence["started_at"])
    finished_at = datetime.fromisoformat(evidence["finished_at"])
    assert started_at <= finished_at
    assert started_at.tzinfo == finished_at.tzinfo == timezone.utc
    assert started_at.microsecond == finished_at.microsecond == 0
    assert evidence["catalog_violations"] == 0
    assert evidence["expected_nodes_asset"] == "expected-nodes-27ff94eb.txt"
    assert evidence["executed_nodes"] == "node-digest"
    assert evidence["docker_unreachable_during_tests"] is True


def test_cli_does_not_print_unexpected_exception_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail() -> runner.PreparedTarget:
        raise RuntimeError("sensitive-marker")

    assert runner.main(fail) == 1
    assert "sensitive-marker" not in capsys.readouterr().err
