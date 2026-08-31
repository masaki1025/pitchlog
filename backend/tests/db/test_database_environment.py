"""PostgreSQL 実環境と凍結済み期待値を検査する。"""

from __future__ import annotations

import copy
import subprocess
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import psycopg
import pytest

from .conftest import DisposablePostgres
from .environment_contract import (
    OBSERVATION_KEYS,
    environment_mismatches,
    load_expectations,
    observe_database_environment,
)

pytestmark = pytest.mark.requires_db


def test_database_observations_match_frozen_expectations(
    admin_connection: psycopg.Connection[Any],
) -> None:
    """SQL で観測した 5 値を資産の厳密期待値と突合する。"""
    asset = load_expectations()
    observations = observe_database_environment(admin_connection)
    assert environment_mismatches(asset, observations) == []


def _mutated_value(value: object) -> object:
    """型を保ったまま元と異なる値を作る。

    Args:
        value: 変異対象の値。

    Returns:
        元と異なる同型の値。
    """
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return f"{value}-mutated"
    raise AssertionError(f"未対応の変異型: {type(value).__name__}")


def test_every_observed_expectation_key_mutation_is_red(
    admin_connection: psycopg.Connection[Any],
) -> None:
    """SQL 観測対象の全 5 キーを 1 つずつ壊し、すべて拒否する。"""
    asset = load_expectations()
    observations = observe_database_environment(admin_connection)
    escaped: list[str] = []

    for key in OBSERVATION_KEYS:
        mutated = copy.deepcopy(asset)
        expectation = mutated["database_environment"][key]
        expectation["expected"] = _mutated_value(expectation["expected"])
        if not environment_mismatches(mutated, observations):
            escaped.append(key)

    assert len(OBSERVATION_KEYS) == 5
    assert escaped == [], f"期待値変異がすり抜けた: {escaped}"


def test_disposable_cluster_is_started_and_destroyed(
    disposable_postgres_cluster: Callable[
        [], AbstractContextManager[DisposablePostgres]
    ],
) -> None:
    """使い捨てクラスタが実際に起動し、context 終了後に消えることを示す。"""
    container_name = ""
    with disposable_postgres_cluster() as cluster:
        container_name = cluster.container_name
        inspection = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container_name],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert inspection.stdout.strip() == "true"
        with psycopg.connect(cluster.admin_dsn) as connection:
            assert (
                environment_mismatches(
                    load_expectations(), observe_database_environment(connection)
                )
                == []
            )

    assert container_name
    inspection = subprocess.run(
        ["docker", "inspect", container_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert inspection.returncode != 0, "使い捨てクラスタのコンテナが残存している"
