"""凍結 archive 前版比較 runner の manifest と PR 構築を検証する。"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "frozen-archive-cases"
    / "runner.py"
)


def _load_runner() -> ModuleType:
    """ハイフンを含む fixture パスから runner をロードする。"""
    spec = importlib.util.spec_from_file_location(
        "frozen_archive_case_runner_under_test",
        RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_runner()
MANIFEST = runner.load_manifest()


def test_manifest_matches_design_case_set_and_transitions() -> None:
    """設計 6-3 の 11 ケースと版間遷移集合を exact-set で固定する。"""
    assert len(MANIFEST.comparison_revision) == 40
    assert MANIFEST.repository_full_name == "masaki1025/pitchlog"
    assert MANIFEST.pull_request_number == 83
    assert {case.id for case in MANIFEST.cases} == set(range(1, 12))
    transitions = {
        case.id: (case.expected["previous"], case.expected["current"])
        for case in MANIFEST.cases
    }
    assert transitions == {
        1: ("green", "green"),
        2: ("green", "green"),
        3: ("red", "red"),
        4: ("green", "red"),
        5: ("green", "red"),
        6: ("green", "red"),
        7: ("green", "red"),
        8: ("red", "red"),
        9: ("green", "green"),
        10: ("green", "green"),
        11: ("green", "red"),
    }
    assert {
        case.id: case.recorded_exit_codes["previous"]
        for case in MANIFEST.cases
    } == {
        1: 0,
        2: 0,
        3: 2,
        4: 0,
        5: 0,
        6: 0,
        7: 0,
        8: 2,
        9: 0,
        10: 0,
        11: 0,
    }


@pytest.mark.parametrize("definition", MANIFEST.cases, ids=lambda case: case.name)
def test_each_case_builds_matching_two_parent_merge_and_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    definition: object,
) -> None:
    """全ケースが同じ base/head を指す二親 merge と event を作る。"""
    prepared = runner.prepare_case(
        definition,
        tmp_path,
        REPOSITORY_ROOT,
        MANIFEST,
        monkeypatch,
    )
    event = json.loads(prepared.event_path.read_text(encoding="utf-8"))
    pull_request_number = event["pull_request"]["number"]
    parents = runner._git(
        prepared.repository,
        ["rev-list", "--parents", "-n", "1", "HEAD"],
    ).stdout.split()

    assert event == {
        "repository": {"full_name": "masaki1025/pitchlog"},
        "pull_request": {
            "number": pull_request_number,
            "base": {"ref": "develop", "sha": prepared.base_sha},
            "head": {"sha": prepared.head_sha},
        },
    }
    assert parents == [
        prepared.merge_sha,
        prepared.base_sha,
        prepared.head_sha,
    ]

    if getattr(definition, "action") in runner.RECORD_APPENDING_ACTIONS:
        base_authority = json.loads(
            runner._git(
                prepared.repository,
                [
                    "show",
                    f"{prepared.base_sha}:contracts/tenant_boundary/"
                    "base-allowlist.json",
                ],
            ).stdout
        )
        head_authority = json.loads(
            runner._git(
                prepared.repository,
                [
                    "show",
                    f"{prepared.head_sha}:contracts/tenant_boundary/"
                    "base-allowlist.json",
                ],
            ).stdout
        )
        acceptance_id = f"masaki1025/pitchlog#{pull_request_number}"
        assert acceptance_id not in {
            record.get("acceptance_id")
            for record in base_authority["baseline_control"]["history"]
        }
        assert (
            head_authority["baseline_control"]["history"][-1][
                "acceptance_id"
            ]
            == acceptance_id
        )
    else:
        assert pull_request_number == 83


def test_runner_calls_real_cli_in_pull_request_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runner が不変量注入でなく実 CLI の PR 受理経路を通す。"""
    definition = MANIFEST.cases[0]
    prepared = runner.prepare_case(
        definition,
        tmp_path,
        REPOSITORY_ROOT,
        MANIFEST,
        monkeypatch,
    )
    without_github_environment = {
        key: value
        for key, value in os.environ.items()
        if key not in runner.GITHUB_ENVIRONMENT_KEYS
    }
    hostile_ci_environment = {
        **without_github_environment,
        "GITHUB_EVENT_PATH": "/invalid/real-ci-event.json",
        "GITHUB_WORKSPACE": "/invalid/real-ci-workspace",
        "GITHUB_REPOSITORY": "invalid/real-ci-repository",
        "GITHUB_BASE_REF": "invalid-real-ci-base",
        "GITHUB_EVENT_NAME": "pull_request",
    }
    without_result = runner.run_checker(
        prepared,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
        without_github_environment,
    )
    ci_result = runner.run_checker(
        prepared,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
        hostile_ci_environment,
    )

    for result in (without_result, ci_result):
        assert result.exit_code == 0
        assert result.matches
        assert result.stdout == "tenant-boundary bypass check: ok"


def test_current_checker_rejects_stale_record_after_accepting_single_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正しい単一遷移を受理し、記録後の凍結実体変異を拒否する。"""
    definition = MANIFEST.cases[1]
    prepared = runner.prepare_case(
        definition,
        tmp_path,
        REPOSITORY_ROOT,
        MANIFEST,
        monkeypatch,
    )

    assert prepared.base_sha != MANIFEST.comparison_revision
    accepted = runner.run_checker(
        prepared,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
    )
    assert accepted.exit_code == 0, accepted.stderr
    assert accepted.matches
    assert accepted.stdout == "tenant-boundary bypass check: ok"

    stale = runner.make_record_stale_by_changing_frozen_implementation(
        prepared,
        REPOSITORY_ROOT,
        monkeypatch,
    )
    changed_paths = runner._git(
        stale.repository,
        ["diff", "--name-only", prepared.head_sha, stale.head_sha],
    )
    assert changed_paths.returncode == 0, changed_paths.stderr
    assert changed_paths.stdout.splitlines() == [
        runner.CHECKER_RELATIVE_PATH.as_posix()
    ]

    rejected = runner.run_checker(
        stale,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
    )
    assert rejected.exit_code != 0
    assert not rejected.matches
    assert "actual.after.external_snapshots" in rejected.stderr


def _snapshot_names_at(repository: Path, revision: str) -> frozenset[str]:
    """指定 revision に存在する履歴 snapshot 名を返す。"""
    result = runner._git(
        repository,
        [
            "ls-tree",
            "-r",
            "--name-only",
            revision,
            "--",
            runner.HISTORY_SNAPSHOT_DIRECTORY.as_posix(),
        ],
    )
    assert result.returncode == 0, result.stderr
    return frozenset(
        Path(line).name for line in result.stdout.splitlines() if line
    )


def test_current_checker_accepts_distinct_referenced_snapshot_sets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """比較元と HEAD の異なる集合を別々に算出して正しい追記を受理する。"""
    definition = MANIFEST.cases[1]
    prepared = runner.prepare_case(
        definition,
        tmp_path,
        REPOSITORY_ROOT,
        MANIFEST,
        monkeypatch,
    )

    assert _snapshot_names_at(
        prepared.repository,
        prepared.base_sha,
    ) != _snapshot_names_at(prepared.repository, prepared.head_sha)

    result = runner.run_checker(
        prepared,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
    )

    assert result.exit_code == 0, result.stderr
    assert result.matches


@pytest.mark.parametrize("case_id", [4, 5, 6, 7])
def test_current_checker_rejects_archive_mutations_through_production_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case_id: int,
) -> None:
    """本番 PR 受理経路で孤児・閾値超過・非正規参照を拒否する。"""
    definition = MANIFEST.cases[case_id - 1]
    prepared = runner.prepare_case(
        definition,
        tmp_path,
        REPOSITORY_ROOT,
        MANIFEST,
        monkeypatch,
    )

    result = runner.run_checker(
        prepared,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
    )

    assert result.exit_code != 0
    assert result.matches, result.stderr


def test_current_checker_grandfathers_base_orphans(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """比較元から存在する孤児29件を本番 PR 受理経路で grandfather する。"""
    definition = MANIFEST.cases[8]
    prepared = runner.prepare_case(
        definition,
        tmp_path,
        REPOSITORY_ROOT,
        MANIFEST,
        monkeypatch,
    )

    result = runner.run_checker(
        prepared,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
    )

    assert result.exit_code == 0, result.stderr
    assert result.matches
