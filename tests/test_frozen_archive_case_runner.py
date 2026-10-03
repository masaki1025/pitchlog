"""凍結 archive 前版比較 runner の manifest と PR 構築を検証する。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
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
    raw_manifest = json.loads(runner.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert set(raw_manifest["corpus_inputs"]) == {
        "digest",
        "files",
        "trees",
        "pinned_prefixes",
    }
    assert set(raw_manifest["corpus_inputs"]["pinned_prefixes"]) == {
        "history_record_count",
        "snapshot_names",
    }
    assert len(MANIFEST.comparison_revision) == 40
    assert MANIFEST.repository_full_name == "masaki1025/pitchlog"
    assert MANIFEST.pull_request_number == 83
    assert {path.as_posix() for path in MANIFEST.corpus_inputs.files} == {
        ".github/workflows/ci.yml",
        "scripts/check_tenant_boundary_bypass.py",
        "scripts/frozen_archive.py",
        "scripts/frozen_history.py",
        "tests/fixtures/frozen-archive-cases/runner.py",
        "tests/test_check_tenant_boundary_bypass.py",
    }
    assert {path.as_posix() for path in MANIFEST.corpus_inputs.trees} == {
        "contracts/tenant_boundary",
        "tests/fixtures/tenant_boundary",
    }
    assert runner.RUNNER_RELATIVE_PATH.as_posix() == (
        "tests/fixtures/frozen-archive-cases/runner.py"
    )
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


def _copy_corpus_inputs(destination: Path) -> Path:
    """固定対象の現況入力を変異用リポジトリルートへコピーする。"""
    destination.mkdir()
    for relative_path in MANIFEST.corpus_inputs.files:
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, target)
    for relative_tree in MANIFEST.corpus_inputs.trees:
        shutil.copytree(
            REPOSITORY_ROOT / relative_tree,
            destination / relative_tree,
        )
    return destination


def _source_with_appended_acceptance(
    destination: Path,
    construction_root: Path,
) -> Path:
    """既存の遷移記録補助で適法な v2 受理を 1 件追記する。"""
    source_root = _copy_corpus_inputs(destination)
    authority_path = source_root / runner.AUTHORITY_RELATIVE_PATH
    original = json.loads(authority_path.read_text(encoding="utf-8"))
    original_history = original["baseline_control"]["history"]
    snapshot_root = source_root / runner.HISTORY_SNAPSHOT_DIRECTORY
    original_snapshot_names = {path.name for path in snapshot_root.iterdir()}
    existing_ids = {
        record.get("acceptance_id") for record in original_history
    }
    number = MANIFEST.pull_request_number + 1
    while f"{MANIFEST.repository_full_name}#{number}" in existing_ids or number in {
        79,
        81,
    }:
        number += 1
    acceptance_id = f"{MANIFEST.repository_full_name}#{number}"

    construction_root.mkdir()
    helpers = runner._load_repository_helpers(source_root)
    repository, base_sha = helpers._initialize_test_repository(
        construction_root,
        {},
    )
    repository_authority = repository / runner.AUTHORITY_RELATIVE_PATH
    changed = json.loads(repository_authority.read_text(encoding="utf-8"))
    assert changed["baseline_control"]["history"] == original_history
    helpers._bump_asset_revision(changed)
    helpers._write_contract_asset(repository_authority, changed)
    helpers._append_current_repository_transition_record(
        repository,
        base_sha,
        acceptance_id=acceptance_id,
    )

    appended = json.loads(repository_authority.read_text(encoding="utf-8"))
    history = appended["baseline_control"]["history"]
    assert history[:-1] == original_history
    assert len(history) == len(original_history) + 1
    record = history[-1]
    assert record["record_schema_version"] == 2
    assert record["acceptance_id"] == acceptance_id
    assert acceptance_id not in existing_ids
    assert set(record) == set(original_history[-1])
    assert len(record) == 9
    aspects = {
        "declaration",
        "movement_policy",
        "external_snapshots",
        "asset_snapshots",
    }
    assert set(record["change"]["before"]) == aspects
    assert set(record["change"]["after"]) == aspects
    authority_path.write_text(
        json.dumps(appended, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    repository_snapshots = repository / runner.HISTORY_SNAPSHOT_DIRECTORY
    for snapshot in repository_snapshots.iterdir():
        target = snapshot_root / snapshot.name
        if target.exists():
            assert target.read_bytes() == snapshot.read_bytes()
        else:
            shutil.copy2(snapshot, target)
    new_names = {path.name for path in snapshot_root.iterdir()} - original_snapshot_names
    assert new_names
    assert all(
        hashlib.sha256((snapshot_root / name).read_bytes()).hexdigest() == name
        for name in new_names
    )
    return source_root


def _assert_prepare_rejects_corpus_drift(
    source_root: Path,
    destination: Path,
    monkeypatch: pytest.MonkeyPatch,
    definition: object = MANIFEST.cases[0],
    manifest: object = MANIFEST,
    expected_reason: str = "比較 corpus の入力が動いた。期待値の導き直しが要る",
) -> None:
    """prepare_case が corpus 入力の漂流を明瞭な理由で拒否することを確認する。"""
    with pytest.raises(ValueError) as error:
        runner.prepare_case(
            definition,
            destination,
            source_root,
            manifest,
            monkeypatch,
        )
    assert expected_reason in str(error.value)


def test_current_corpus_inputs_match_manifest_digest() -> None:
    """現況の corpus 入力が manifest の固定 digest と一致する。

    先に validate_corpus_inputs を呼ぶ。裸の assert を先に置くと digest の
    比較だけが表示され、「何が起きたか」「次に何をすべきか」が読めない。
    """
    runner.validate_corpus_inputs(REPOSITORY_ROOT, MANIFEST)
    assert (
        runner.corpus_input_digest(REPOSITORY_ROOT, MANIFEST)
        == MANIFEST.corpus_inputs.digest
    )


def test_prepare_case_rejects_changed_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """corpus の生成規則を持つ runner の内容変更を red にする。"""
    source_root = _copy_corpus_inputs(tmp_path / "source")
    runner_path = source_root / runner.RUNNER_RELATIVE_PATH
    runner_path.write_text(
        runner_path.read_text(encoding="utf-8")
        + "\n# corpus drift test\n",
        encoding="utf-8",
    )

    _assert_prepare_rejects_corpus_drift(
        source_root,
        tmp_path / "case",
        monkeypatch,
    )


def test_prepare_case_rejects_changed_manifest_case_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同じ green/green となるケース action の置換を red にする。"""
    source_root = _copy_corpus_inputs(tmp_path / "source")
    manifest_path = tmp_path / "manifest.json"
    raw_manifest = json.loads(
        runner.DEFAULT_MANIFEST.read_text(encoding="utf-8")
    )
    raw_manifest["cases"][0]["action"] = "recorded_movement"
    manifest_path.write_text(
        json.dumps(raw_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    changed_manifest = runner.load_manifest(manifest_path)

    _assert_prepare_rejects_corpus_drift(
        source_root,
        tmp_path / "case",
        monkeypatch,
        changed_manifest.cases[0],
        changed_manifest,
    )


def test_prepare_case_rejects_changed_contract_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """契約資産の内容変更で corpus を red にする。"""
    source_root = _copy_corpus_inputs(tmp_path / "source")
    contract_path = (
        source_root
        / "contracts/tenant_boundary/runtime-authz-contract.json"
    )
    contract_path.write_bytes(contract_path.read_bytes() + b"\n")

    _assert_prepare_rejects_corpus_drift(
        source_root,
        tmp_path / "case",
        monkeypatch,
    )


def test_prepare_case_accepts_appended_history_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """適法な v2 追記で digest が不変のまま case を準備できる。"""
    source_root = _source_with_appended_acceptance(
        tmp_path / "source",
        tmp_path / "construction",
    )
    repository = tmp_path / "construction" / "repository"
    base_sha = runner._git(repository, ["rev-parse", "HEAD"]).stdout.strip()
    authority = json.loads(
        (source_root / runner.AUTHORITY_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    acceptance_id = authority["baseline_control"]["history"][-1]["acceptance_id"]
    pull_request_number = int(acceptance_id.rsplit("#", 1)[1])
    helpers = runner._load_repository_helpers(source_root)
    event_path = tmp_path / "appended-transition-event.json"
    helpers._seal_pull_request_worktree(
        repository,
        base_sha,
        monkeypatch,
        event_path,
        number=pull_request_number,
    )
    actual_base, head_sha, merge_sha = runner._event_and_merge(
        repository, event_path, helpers
    )
    assert actual_base == base_sha
    transition = runner.PreparedCase(
        MANIFEST.cases[0], repository, event_path, base_sha, head_sha, merge_sha
    )
    transition_result = runner.run_checker(
        transition,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
    )
    assert transition_result.exit_code == 0, transition_result.stderr
    runner.validate_corpus_inputs(source_root, MANIFEST)
    assert runner.corpus_input_digest(source_root, MANIFEST) == (
        MANIFEST.corpus_inputs.digest
    )
    prepared = runner.prepare_case(
        MANIFEST.cases[0],
        tmp_path / "case",
        source_root,
        MANIFEST,
        monkeypatch,
    )
    result = runner.run_checker(
        prepared,
        runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),
    )
    assert result.exit_code == 0, result.stderr
    assert result.matches


def test_prepare_case_rejects_changed_pinned_history_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定済み履歴の書き換えを prepare_case の digest 検査で拒否する。"""
    source_root = _copy_corpus_inputs(tmp_path / "source")
    authority_path = source_root / runner.AUTHORITY_RELATIVE_PATH
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    history = authority["baseline_control"]["history"]
    assert len(history) >= MANIFEST.corpus_inputs.pinned_prefixes.history_record_count
    history[0]["reason"] += " 改竄"
    authority_path.write_text(
        json.dumps(authority, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _assert_prepare_rejects_corpus_drift(
        source_root,
        tmp_path / "case",
        monkeypatch,
    )


def test_prepare_case_rejects_missing_pinned_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """固定済み snapshot の削除を prepare_case の存在検査で拒否する。"""
    source_root = _copy_corpus_inputs(tmp_path / "source")
    name = MANIFEST.corpus_inputs.pinned_prefixes.snapshot_names[0]
    (source_root / runner.HISTORY_SNAPSHOT_DIRECTORY / name).unlink()
    _assert_prepare_rejects_corpus_drift(
        source_root,
        tmp_path / "case",
        monkeypatch,
        expected_reason="固定済み snapshot が存在しない",
    )


def test_prepare_case_rejects_changed_checker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """検査器の内容変更で corpus を red にする。"""
    source_root = _copy_corpus_inputs(tmp_path / "source")
    checker_path = source_root / runner.CHECKER_RELATIVE_PATH
    checker_path.write_text(
        checker_path.read_text(encoding="utf-8")
        + "\n# corpus drift test\n",
        encoding="utf-8",
    )

    _assert_prepare_rejects_corpus_drift(
        source_root,
        tmp_path / "case",
        monkeypatch,
    )


def _current_case_exit_codes(source_root: Path) -> dict[int, int]:
    """現版検査器を 11 ケースへ当て、ケース ID ごとの終了コードを返す。"""
    results = runner.run_cases(
        MANIFEST,
        (runner.CheckerSpec(label="current", root=REPOSITORY_ROOT),),
        source_root,
    )
    assert len(results) == len(MANIFEST.cases)
    assert {result.case_id for result in results} == {
        case.id for case in MANIFEST.cases
    }
    assert all(result.matches for result in results)
    return {result.case_id: result.exit_code for result in results}


def test_appended_history_record_does_not_change_case_outcomes(
    tmp_path: Path,
) -> None:
    """この適法な合成追記 1 件で 11 ケースの終了コードが不変と示す。"""
    before = _current_case_exit_codes(REPOSITORY_ROOT)
    source_root = _source_with_appended_acceptance(
        tmp_path / "source",
        tmp_path / "construction",
    )
    after = _current_case_exit_codes(source_root)
    assert after == before


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
