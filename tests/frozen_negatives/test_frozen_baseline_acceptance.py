"""凍結基準台帳の受理遷移に対する負例を固定する。"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPOSITORY_ROOT / "scripts/check_frozen_baselines.py"
LEDGER_RELATIVE_PATH = Path("contracts/authz/frozen-baselines.json")
TARGET_PATHS = (
    "contracts/authz/oracle-seal.lock.json",
    "contracts/authz/attack-tree.json",
    "contracts/authz/boundary-proposal.json",
    "contracts/authz/claim-mutant-map.json",
    "contracts/authz/ddl-elements.json",
    "contracts/authz/rejected-configs.json",
    "contracts/authz/verification-evidence.json",
)
BASE_SOURCE_PATHS = (*TARGET_PATHS, "scripts/check_authz_catalog.py")
NEW_ASSET_PATHS = (
    "contracts/authz/frozen-baselines.json",
    "contracts/authz/frozen-baselines.schema.json",
    "scripts/check_frozen_baselines.py",
    "scripts/frozen_baselines.py",
)
IDENTITY_BEARING_PATHS = frozenset(
    (*BASE_SOURCE_PATHS, LEDGER_RELATIVE_PATH.as_posix())
)
IDENTITY_FREE_PATHS = frozenset(
    {
        "contracts/authz/frozen-baselines.schema.json",
        "scripts/check_frozen_baselines.py",
        "scripts/frozen_baselines.py",
    }
)
assert IDENTITY_BEARING_PATHS.isdisjoint(IDENTITY_FREE_PATHS)
assert IDENTITY_BEARING_PATHS | IDENTITY_FREE_PATHS == frozenset(
    (*BASE_SOURCE_PATHS, *NEW_ASSET_PATHS)
)
MUTATION_GUARD_PATHS = tuple(
    REPOSITORY_ROOT / path
    for path in (
        *BASE_SOURCE_PATHS,
        *NEW_ASSET_PATHS,
        ".github/workflows/ci.yml",
        "tests/test_ci_wiring.py",
    )
)
LedgerMutation = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class _AcceptanceFixture:
    """合成pull request repositoryとeventの識別値を保持する。"""

    root: Path
    event_path: Path
    anchor_sha: str
    base_sha: str
    head_sha: str
    identity_sha: str


@pytest.fixture(autouse=True)
def repository_assets_remain_byte_identical() -> Iterator[None]:
    """各負例の前後で本物の対象資産が生bytes一致することを検査する。"""
    original = {path: path.read_bytes() for path in MUTATION_GUARD_PATHS}

    yield

    assert {path: path.read_bytes() for path in MUTATION_GUARD_PATHS} == original


def _git(
    root: Path,
    *arguments: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """合成repository内でgitを実行し成功を表明する。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


def _git_sha(root: Path, revision: str) -> str:
    """合成repositoryのrevisionを完全SHAへ解決する。"""
    sha = _git(root, "rev-parse", "--verify", f"{revision}^{{commit}}").stdout.strip()
    assert len(sha) == 40
    return sha


def _ledger_oracle_input_identity() -> str:
    """実台帳のoracle_input系列から最新の識別値を導出する。"""
    ledger = json.loads(
        (REPOSITORY_ROOT / LEDGER_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    assert isinstance(ledger, dict)
    history = ledger.get("history")
    assert isinstance(history, list)
    assert all(isinstance(record, dict) for record in history)
    records = [record for record in history if record.get("series") == "oracle_input"]
    assert records, "台帳にoracle_input系列の履歴が必要です"

    new_identity = records[-1].get("new_identity")
    assert isinstance(new_identity, dict)
    assert new_identity.get("present") is True
    values = new_identity.get("values")
    assert isinstance(values, list)
    assert len(values) == 1
    identity = values[0]
    assert isinstance(identity, dict)
    assert identity.get("kind") == "literal_commit_string"
    value = identity.get("value")
    assert isinstance(value, str)
    assert len(value) == 40
    assert set(value) <= set("0123456789abcdef")
    return value


def _copy_with_identity(root: Path, path_text: str, identity: str) -> None:
    """実資産を合成repositoryへコピーしcommit識別値だけを置換する。"""
    source = REPOSITORY_ROOT / path_text
    destination = root / path_text
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source.read_bytes()
    recorded_identity = _ledger_oracle_input_identity().encode()
    replacement = identity.encode()
    occurrence_count = source_bytes.count(recorded_identity)
    classified_paths = IDENTITY_BEARING_PATHS | IDENTITY_FREE_PATHS
    assert path_text in classified_paths, f"識別値の有無が未分類です: {path_text}"
    if path_text in IDENTITY_BEARING_PATHS:
        assert occurrence_count >= 1, (
            f"{path_text}: 台帳導出識別値が1回以上必要です: "
            f"occurrences={occurrence_count}"
        )
        assert replacement != recorded_identity, (
            f"{path_text}: 置換後の識別値が台帳導出識別値と同一です"
        )
    else:
        assert occurrence_count == 0, (
            f"{path_text}: 台帳導出識別値を含まないはずです: "
            f"occurrences={occurrence_count}"
        )
    replaced_bytes = source_bytes.replace(recorded_identity, replacement)
    assert (replaced_bytes != source_bytes) == (path_text in IDENTITY_BEARING_PATHS), (
        f"{path_text}: 識別値置換の実行結果がパス分類と一致しません"
    )
    destination.write_bytes(replaced_bytes)


def _read_ledger(root: Path) -> dict[str, Any]:
    """合成repositoryの台帳をobjectとして読む。"""
    value = json.loads((root / LEDGER_RELATIVE_PATH).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_ledger(root: Path, ledger: dict[str, Any]) -> None:
    """合成repositoryの台帳を整形済みJSONとして書く。"""
    (root / LEDGER_RELATIVE_PATH).write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _copy_base_sources(root: Path, identity: str) -> None:
    """base treeに存在する旧ソースと対象JSONをコピーする。"""
    for path_text in BASE_SOURCE_PATHS:
        _copy_with_identity(root, path_text, identity)


def _copy_new_assets(root: Path, identity: str) -> None:
    """headで新設される台帳・schema・検査コードをコピーする。"""
    for path_text in NEW_ASSET_PATHS:
        _copy_with_identity(root, path_text, identity)


def _add_noop_history_record(ledger: dict[str, Any]) -> None:
    """通常遷移の削除検査用に有効な2件目の履歴を追加する。"""
    previous = ledger["history"][-1]
    acceptance = copy.deepcopy(ledger["acceptance"])
    placement = copy.deepcopy(ledger["placements"]["oracle_input"])
    ledger["history"].append(
        {
            "acceptance_id": "masaki1025/pitchlog#90",
            "series": "oracle_input",
            "new_identity": copy.deepcopy(previous["new_identity"]),
            "prior_identity": copy.deepcopy(previous["new_identity"]),
            "changes": [
                {
                    "aspect": "acceptance",
                    "before": acceptance,
                    "after": copy.deepcopy(acceptance),
                }
            ],
            "placement_change": {
                "before": placement,
                "after": copy.deepcopy(placement),
            },
            "moved": False,
            "reason": "追記のみ検査の合成base記録",
            "approved_by": "山田正輝",
            "approved_at": "2026-09-21",
        }
    )


def _build_repository(
    root: Path,
    *,
    bootstrap: bool = False,
    pull_request_number: int = 99,
    dangling_identity: bool = False,
    base_mutation: LedgerMutation | None = None,
    head_mutation: LedgerMutation | None = None,
) -> _AcceptanceFixture:
    """完全履歴を持つsynthetic mergeとpull request eventを合成する。"""
    root.mkdir(parents=True)
    _git(root, "init", "-b", "develop")
    _git(root, "config", "user.name", "Pitchlog Test")
    _git(root, "config", "user.email", "pitchlog-test@example.invalid")
    (root / "anchor.txt").write_text("anchor\n", encoding="utf-8")
    _git(root, "add", "anchor.txt")
    _git(root, "commit", "-m", "anchor")
    anchor_sha = _git_sha(root, "HEAD")
    identity_sha = anchor_sha
    if dangling_identity:
        tree_sha = _git(root, "rev-parse", f"{anchor_sha}^{{tree}}").stdout.strip()
        identity_sha = _git(
            root,
            "commit-tree",
            tree_sha,
            input_text="dangling identity\n",
        ).stdout.strip()
        assert len(identity_sha) == 40

    _copy_base_sources(root, identity_sha)
    if not bootstrap:
        _copy_new_assets(root, identity_sha)
        if base_mutation is not None:
            ledger = _read_ledger(root)
            base_mutation(ledger)
            _write_ledger(root, ledger)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    base_sha = _git_sha(root, "HEAD")

    _git(root, "checkout", "-b", "feature")
    if bootstrap:
        _copy_new_assets(root, identity_sha)
    (root / "head-marker.txt").write_text("head\n", encoding="utf-8")
    if head_mutation is not None:
        ledger = _read_ledger(root)
        head_mutation(ledger)
        _write_ledger(root, ledger)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "head")
    head_sha = _git_sha(root, "HEAD")
    _git(root, "checkout", "develop")
    _git(root, "merge", "--no-ff", "--no-edit", "feature")

    event = {
        "repository": {"full_name": "masaki1025/pitchlog"},
        "pull_request": {
            "number": pull_request_number,
            "base": {"ref": "develop", "sha": base_sha},
            "head": {"sha": head_sha},
        },
    }
    event_path = root / "event.json"
    event_path.write_text(json.dumps(event), encoding="utf-8")
    return _AcceptanceFixture(
        root=root,
        event_path=event_path,
        anchor_sha=anchor_sha,
        base_sha=base_sha,
        head_sha=head_sha,
        identity_sha=identity_sha,
    )


def _read_event(fixture: _AcceptanceFixture) -> dict[str, Any]:
    """合成pull request eventをobjectとして読む。"""
    value = json.loads(fixture.event_path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_event(fixture: _AcceptanceFixture, event: dict[str, Any]) -> None:
    """変異したpull request eventを書く。"""
    fixture.event_path.write_text(json.dumps(event), encoding="utf-8")


def _run_acceptance(
    fixture: _AcceptanceFixture,
    *,
    include_event: bool = True,
) -> subprocess.CompletedProcess[str]:
    """合成repositoryへ受理遷移検査を実行する。"""
    environment = os.environ.copy()
    environment.pop("GITHUB_EVENT_PATH", None)
    if include_event:
        environment["GITHUB_EVENT_PATH"] = str(fixture.event_path)
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER_PATH),
            "--acceptance",
            "--root",
            str(fixture.root),
            "--ledger",
            str(fixture.root / LEDGER_RELATIVE_PATH),
        ],
        cwd=fixture.root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_normal_baseline_green(fixture: _AcceptanceFixture) -> None:
    """通常受理遷移の変異前fixtureがgreenであることを表明する。"""
    result = _run_acceptance(fixture)
    assert result.returncode == 0
    assert result.stdout == "frozen-baselines: OK\n"
    assert result.stderr == ""


def _assert_bootstrap_baseline_green(fixture: _AcceptanceFixture) -> None:
    """初回bootstrap fixtureが明示メッセージ付きでgreenであることを表明する。"""
    result = _run_acceptance(fixture)
    assert result.returncode == 0
    assert result.stdout == (
        "frozen-baselines: bootstrap acceptance: 初回の信頼根は人間の逐行確認\n"
        "frozen-baselines: bootstrap経路は、台帳を含むbase SHAで新たに評価される"
        "develop宛PRでは到達しない\n"
        "frozen-baselines: OK\n"
    )
    assert result.stderr == ""


def _assert_red(
    fixture: _AcceptanceFixture,
    expected_message: str,
    *,
    include_event: bool = True,
) -> None:
    """受理検査が期待メッセージだけを出してredになることを表明する。"""
    result = _run_acceptance(fixture, include_event=include_event)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"frozen-baselines: ERROR: {expected_message}\n"


@pytest.mark.frozen_negative
def test_non_develop_event_does_not_enter_acceptance_transition(tmp_path: Path) -> None:
    """N15: develop以外のPRは内部不変量だけで終了する。"""
    fixture = _build_repository(tmp_path / "repository")
    _assert_normal_baseline_green(fixture)
    event = _read_event(fixture)
    event["pull_request"]["base"] = {"ref": "release", "sha": "0" * 40}
    event["pull_request"]["head"] = {"sha": "f" * 40}
    _write_event(fixture, event)

    result = _run_acceptance(fixture)
    assert result.returncode == 0
    assert result.stdout == (
        "frozen-baselines: acceptance not evaluated: "
        "pull_request.base.ref='release' は develop でない\n"
        "frozen-baselines: OK\n"
    )
    assert result.stderr == ""


@pytest.mark.frozen_negative
def test_first_parent_different_from_event_base_is_red(tmp_path: Path) -> None:
    """N16: HEAD第1親とevent baseの不一致を拒否する。"""
    fixture = _build_repository(tmp_path / "baseline")
    _assert_normal_baseline_green(fixture)
    mutant = _build_repository(tmp_path / "mutant")
    event = _read_event(mutant)
    event["pull_request"]["base"]["sha"] = mutant.anchor_sha
    _write_event(mutant, event)

    _assert_red(
        mutant,
        "HEADの第1親がbase.shaと不一致: "
        f"期待={mutant.anchor_sha}; 実際={mutant.base_sha}",
    )


@pytest.mark.frozen_negative
def test_second_parent_different_from_event_head_is_red(tmp_path: Path) -> None:
    """N17: HEAD第2親とevent headの不一致を拒否する。"""
    fixture = _build_repository(tmp_path / "baseline")
    _assert_normal_baseline_green(fixture)
    mutant = _build_repository(tmp_path / "mutant")
    event = _read_event(mutant)
    event["pull_request"]["head"]["sha"] = mutant.anchor_sha
    _write_event(mutant, event)

    _assert_red(
        mutant,
        "HEADの第2親がhead.shaと不一致: "
        f"期待={mutant.anchor_sha}; 実際={mutant.head_sha}",
    )


@pytest.mark.frozen_negative
def test_rewritten_existing_history_record_is_red(tmp_path: Path) -> None:
    """N18: 既存履歴の1バイト相当の書き換えを拒否する。"""
    fixture = _build_repository(tmp_path / "baseline")
    _assert_normal_baseline_green(fixture)

    def mutate(ledger: dict[str, Any]) -> None:
        ledger["history"][0]["approved_at"] = "2026-09-22"

    mutant = _build_repository(tmp_path / "mutant", head_mutation=mutate)
    _assert_red(mutant, "historyの既存記録が書き換えられた: index=0")


@pytest.mark.frozen_negative
def test_deleted_existing_history_record_is_red(tmp_path: Path) -> None:
    """N19: baseにある有効な既存履歴の削除を拒否する。"""
    fixture = _build_repository(tmp_path / "baseline")
    _assert_normal_baseline_green(fixture)

    def remove_last(ledger: dict[str, Any]) -> None:
        ledger["history"].pop()

    mutant = _build_repository(
        tmp_path / "mutant",
        base_mutation=_add_noop_history_record,
        head_mutation=remove_last,
    )
    _assert_red(mutant, "historyの既存記録が削除された: base=2; head=1")


@pytest.mark.frozen_negative
def test_same_length_history_replacement_is_red(tmp_path: Path) -> None:
    """N20: 件数を維持した履歴recordの置換を拒否する。"""
    fixture = _build_repository(tmp_path / "baseline")
    _assert_normal_baseline_green(fixture)

    def replace_record(ledger: dict[str, Any]) -> None:
        replacement = copy.deepcopy(ledger["history"].pop(0))
        replacement["acceptance_id"] = "masaki1025/pitchlog#999"
        ledger["history"].append(replacement)

    mutant = _build_repository(tmp_path / "mutant", head_mutation=replace_record)
    _assert_red(mutant, "historyの同数置換を検出した: index=0")


@pytest.mark.frozen_negative
def test_second_bootstrap_after_missing_base_ledger_is_red(tmp_path: Path) -> None:
    """N21: 初回ID以外でbase台帳不在経路へ入ることを拒否する。"""
    fixture = _build_repository(
        tmp_path / "baseline",
        bootstrap=True,
        pull_request_number=73,
    )
    _assert_bootstrap_baseline_green(fixture)
    mutant = _build_repository(
        tmp_path / "mutant",
        bootstrap=True,
        pull_request_number=74,
    )

    _assert_red(
        mutant,
        "bootstrap: base台帳不在を許す初回acceptance_idと不一致: "
        "期待=masaki1025/pitchlog#73; 実際=masaki1025/pitchlog#74",
    )


@pytest.mark.frozen_negative
def test_missing_inputs_and_dangling_identity_are_red(tmp_path: Path) -> None:
    """N22: git・event欠落とHEADから到達不能なcommitをfail-closedにする。"""
    fixture = _build_repository(tmp_path / "baseline")
    _assert_normal_baseline_green(fixture)

    git_directory = fixture.root / ".git"
    hidden_git_directory = fixture.root / ".git-hidden"
    git_directory.rename(hidden_git_directory)
    try:
        _assert_red(fixture, "受理遷移検査には .git が必要")
    finally:
        hidden_git_directory.rename(git_directory)

    _assert_red(fixture, "GITHUB_EVENT_PATH が設定されていない", include_event=False)

    dangling = _build_repository(
        tmp_path / "dangling",
        dangling_identity=True,
    )
    existence = subprocess.run(
        ["git", "cat-file", "-e", f"{dangling.identity_sha}^{{commit}}"],
        cwd=dangling.root,
        check=False,
    )
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", dangling.identity_sha, "HEAD"],
        cwd=dangling.root,
        check=False,
    )
    assert existence.returncode == 0
    assert ancestry.returncode == 1
    _assert_red(
        dangling,
        f"識別値commitがHEADから到達不能: {dangling.identity_sha}",
    )
