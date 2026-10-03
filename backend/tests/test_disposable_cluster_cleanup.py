"""使い捨て PostgreSQL コンテナの破棄経路を検査する。"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import cast

import db_fixtures
import pytest


@pytest.mark.parametrize(
    "failure_stage",
    [
        pytest.param(None, id="success"),
        pytest.param("run", id="run-error"),
        pytest.param("port", id="port-error"),
        pytest.param("wait", id="wait-error"),
    ],
)
def test_disposable_cluster_removes_container_and_volumes(
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str | None,
) -> None:
    """正常終了と各起動失敗で同名コンテナの匿名ボリュームを回収する。"""
    for variable_name in db_fixtures._dsn_names():
        monkeypatch.setenv(
            variable_name, "postgresql://fixture:dummy@invalid.local/unused"
        )

    calls: list[tuple[tuple[str, ...], bool]] = []
    wait_calls: list[str] = []
    original_error = RuntimeError(f"{failure_stage} failed")

    def record_docker(
        *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Docker 呼び出しを記録し、指定段階だけ失敗させる。"""
        calls.append((arguments, check))
        if arguments[0] == failure_stage:
            raise original_error
        stdout = "127.0.0.1:54321\n" if arguments[0] == "port" else ""
        return subprocess.CompletedProcess(["docker", *arguments], 0, stdout, "")

    def wait_for_postgres(dsn: str) -> None:
        """実接続を避け、指定時だけ待機失敗を再現する。"""
        wait_calls.append(dsn)
        if failure_stage == "wait":
            raise original_error

    monkeypatch.setattr(db_fixtures, "_run_docker", record_docker)
    monkeypatch.setattr(db_fixtures, "_wait_for_postgres", wait_for_postgres)
    fixture_function = cast(
        Callable[
            [], Callable[[], AbstractContextManager[db_fixtures.DisposablePostgres]]
        ],
        getattr(db_fixtures.disposable_postgres_cluster, "__wrapped__"),
    )
    factory = fixture_function()

    if failure_stage is None:
        with factory() as cluster:
            container_name = cluster.container_name
    else:
        with pytest.raises(RuntimeError) as raised:
            with factory():
                pass
        assert raised.value is original_error

    run_calls = [arguments for arguments, _ in calls if arguments[0] == "run"]
    assert len(run_calls) == 1
    run_arguments = run_calls[0]
    assert run_arguments[:3] == ("run", "--detach", "--rm")
    image = db_fixtures.load_expectations()["database_environment"]["image"]["expected"]
    assert isinstance(image, str)
    assert run_arguments.index("--rm") < run_arguments.index(image)
    container_name_from_run = run_arguments[run_arguments.index("--name") + 1]

    assert calls[-1] == (
        ("rm", "--force", "--volumes", container_name_from_run),
        False,
    )
    assert sum(arguments[0] == "rm" for arguments, _ in calls) == 1
    if failure_stage is None:
        assert container_name == container_name_from_run

    expected_commands = (
        ("run", "rm")
        if failure_stage == "run"
        else (
            "run",
            "port",
            "rm",
        )
    )
    assert tuple(arguments[0] for arguments, _ in calls) == expected_commands
    assert len(wait_calls) == (0 if failure_stage in ("run", "port") else 1)
