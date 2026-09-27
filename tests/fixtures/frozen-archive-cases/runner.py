"""凍結 archive の前版・新版比較ケースを PR 受理モードで実行する。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

FIXTURE_ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = FIXTURE_ROOT / "manifest.json"
DEFAULT_SOURCE_ROOT = FIXTURE_ROOT.parents[2]
CHECKER_RELATIVE_PATH = Path("scripts/check_tenant_boundary_bypass.py")
HISTORY_SNAPSHOT_DIRECTORY = Path(
    "contracts/tenant_boundary/history-snapshots"
)
EXPECTED_CASE_IDS = frozenset(range(1, 12))
GITHUB_ENVIRONMENT_KEYS = frozenset(
    {
        "GITHUB_EVENT_PATH",
        "GITHUB_WORKSPACE",
        "GITHUB_REPOSITORY",
        "GITHUB_BASE_REF",
        "GITHUB_EVENT_NAME",
    }
)
EXPECTED_ACTIONS = frozenset(
    {
        "unchanged",
        "recorded_movement",
        "unchanged_identifier",
        "new_orphan_snapshot",
        "snapshot_count_over_limit",
        "snapshot_bytes_over_limit",
        "noncanonical_existing_reference",
        "noncanonical_appended_reference",
        "missing_existing_v2_reference",
    }
)
RECORD_APPENDING_ACTIONS = frozenset(
    {
        "recorded_movement",
        "unchanged_identifier",
        "noncanonical_appended_reference",
    }
)


@dataclass(frozen=True)
class CaseDefinition:
    """manifest に固定した比較ケースを表す。"""

    id: int
    name: str
    description: str
    action: str
    parameters: dict[str, int]
    expected: dict[str, str]
    recorded_exit_codes: dict[str, int | None]


@dataclass(frozen=True)
class Manifest:
    """前版比較 corpus の固定情報を表す。"""

    comparison_revision: str
    repository_full_name: str
    pull_request_number: int
    cases: tuple[CaseDefinition, ...]


@dataclass(frozen=True)
class CheckerSpec:
    """比較に用いる検査器の表示名と作業木を表す。"""

    label: str
    root: Path


@dataclass(frozen=True)
class PreparedCase:
    """二親 merge と GitHub event を封入した合成リポジトリを表す。"""

    definition: CaseDefinition
    repository: Path
    event_path: Path
    base_sha: str
    head_sha: str
    merge_sha: str


@dataclass(frozen=True)
class RunResult:
    """1 ケースへ 1 版の CLI を当てた結果を表す。"""

    case_id: int
    checker: str
    expected: str
    expected_exit_code: int | None
    exit_code: int
    stdout: str
    stderr: str

    @property
    def matches(self) -> bool:
        """green/red と、記録済みなら終了コードの双方が一致するか返す。"""
        outcome_matches = (self.exit_code == 0) == (self.expected == "green")
        code_matches = (
            self.expected_exit_code is None
            or self.exit_code == self.expected_exit_code
        )
        return outcome_matches and code_matches


def _object(value: object, location: str) -> dict[str, Any]:
    """JSON object を検査して返す。"""
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{location} は文字列キーの object が必要")
    return value


def _string(value: object, location: str) -> str:
    """空でない文字列を検査して返す。"""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{location} は空でない文字列が必要")
    return value


def _positive_integer(value: object, location: str) -> int:
    """正の整数を検査して返す。"""
    if type(value) is not int or value <= 0:
        raise ValueError(f"{location} は正の整数が必要")
    return value


def load_manifest(path: Path = DEFAULT_MANIFEST) -> Manifest:
    """比較ケース manifest を exact-set で読む。

    Args:
        path: 読み込む manifest のパス。

    Returns:
        検証済みの比較 manifest。

    Raises:
        ValueError: manifest の構造または 11 ケースの集合が不正な場合。
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"比較 manifest を読めない: {path}: {error}") from error
    root = _object(raw, "manifest")
    if set(root) != {
        "schema_version",
        "comparison_revision",
        "repository_full_name",
        "pull_request_number",
        "cases",
    }:
        raise ValueError("manifest のキー集合が不正")
    if root["schema_version"] != 1:
        raise ValueError("manifest.schema_version は 1 が必要")
    raw_cases = root["cases"]
    if not isinstance(raw_cases, list):
        raise ValueError("manifest.cases は配列が必要")

    cases: list[CaseDefinition] = []
    for index, raw_case in enumerate(raw_cases):
        location = f"manifest.cases[{index}]"
        case = _object(raw_case, location)
        allowed_keys = {
            "id",
            "name",
            "description",
            "action",
            "parameters",
            "expected",
            "recorded_exit_codes",
        }
        if not set(case) <= allowed_keys or set(case) < allowed_keys - {
            "parameters"
        }:
            raise ValueError(f"{location} のキー集合が不正")
        case_id = _positive_integer(case["id"], f"{location}.id")
        action = _string(case["action"], f"{location}.action")
        if action not in EXPECTED_ACTIONS:
            raise ValueError(f"{location}.action が未知: {action}")
        parameters = _object(case.get("parameters", {}), f"{location}.parameters")
        if not all(type(value) is int for value in parameters.values()):
            raise ValueError(f"{location}.parameters の値は整数が必要")
        expected = _object(case["expected"], f"{location}.expected")
        recorded = _object(
            case["recorded_exit_codes"],
            f"{location}.recorded_exit_codes",
        )
        if set(expected) != {"previous", "current"} or set(recorded) != {
            "previous",
            "current",
        }:
            raise ValueError(f"{location} の版ラベルが不正")
        parsed_expected = {
            label: _string(value, f"{location}.expected.{label}")
            for label, value in expected.items()
        }
        if set(parsed_expected.values()) - {"green", "red"}:
            raise ValueError(f"{location}.expected は green/red が必要")
        if not all(
            value is None or type(value) is int for value in recorded.values()
        ):
            raise ValueError(
                f"{location}.recorded_exit_codes は整数または null が必要"
            )
        cases.append(
            CaseDefinition(
                id=case_id,
                name=_string(case["name"], f"{location}.name"),
                description=_string(
                    case["description"],
                    f"{location}.description",
                ),
                action=action,
                parameters={key: int(value) for key, value in parameters.items()},
                expected=parsed_expected,
                recorded_exit_codes={
                    key: value if isinstance(value, int) else None
                    for key, value in recorded.items()
                },
            )
        )
    if {case.id for case in cases} != EXPECTED_CASE_IDS:
        raise ValueError("manifest.cases の ID が 1〜11 と exact-set 不一致")
    if len({case.name for case in cases}) != len(cases):
        raise ValueError("manifest.cases.name は一意でなければならない")

    comparison_revision = _string(
        root["comparison_revision"],
        "manifest.comparison_revision",
    )
    if (
        len(comparison_revision) != 40
        or any(character not in "0123456789abcdef" for character in comparison_revision)
    ):
        raise ValueError("manifest.comparison_revision は 40 桁小文字 hex が必要")
    return Manifest(
        comparison_revision=comparison_revision,
        repository_full_name=_string(
            root["repository_full_name"],
            "manifest.repository_full_name",
        ),
        pull_request_number=_positive_integer(
            root["pull_request_number"],
            "manifest.pull_request_number",
        ),
        cases=tuple(sorted(cases, key=lambda item: item.id)),
    )


def _load_repository_helpers(source_root: Path) -> ModuleType:
    """既存テストの合成リポジトリ補助を再利用する。"""
    helper_path = source_root / "tests/test_check_tenant_boundary_bypass.py"
    resolved_helper = helper_path.resolve()
    for module in tuple(sys.modules.values()):
        module_file = getattr(module, "__file__", None)
        if module_file is not None and Path(module_file).resolve() == resolved_helper:
            return module
    module_name = "_frozen_archive_case_repository_helpers"
    spec = importlib.util.spec_from_file_location(module_name, helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"既存テスト補助をロードできない: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _read_json_object(path: Path) -> dict[str, Any]:
    """UTF-8 JSON object を読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, str(path))


def _first_v2_record(authority: dict[str, Any]) -> dict[str, Any]:
    """authority の最初の v2 記録を返す。"""
    control = _object(authority["baseline_control"], "baseline_control")
    history = control["history"]
    if not isinstance(history, list):
        raise ValueError("baseline_control.history は配列が必要")
    for raw_record in history:
        record = _object(raw_record, "baseline_control.history[]")
        if record.get("record_schema_version") == 2:
            return record
    raise ValueError("比較 fixture に v2 記録が無い")


def _external_snapshot_entry(record: dict[str, Any]) -> dict[str, Any]:
    """v2 記録の before 側から最初の外部 snapshot 行を返す。"""
    change = _object(record["change"], "record.change")
    before = _object(change["before"], "record.change.before")
    snapshots = before["external_snapshots"]
    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError("record.change.before.external_snapshots は非空配列が必要")
    return _object(snapshots[0], "record.change.before.external_snapshots[0]")


def _mutate_existing_reference(
    repository: Path,
    helpers: ModuleType,
    *,
    remove: bool,
) -> None:
    """既存 v2 prefix の参照を非正規化または欠落させる。"""
    authority_path = repository / helpers.checker.DEFAULT_ALLOWLIST
    authority = _read_json_object(authority_path)
    snapshot = _external_snapshot_entry(_first_v2_record(authority))
    if remove:
        snapshot.pop("snapshot_ref")
    else:
        digest = _string(snapshot["sha256"], "snapshot.sha256")
        snapshot["snapshot_ref"] = f"invalid-history-snapshots/{digest}"
    helpers._write_contract_asset(authority_path, authority)


def _apply_recorded_movement(
    repository: Path,
    base_sha: str,
    helpers: ModuleType,
    *,
    bump_identifier: bool,
    acceptance_id: str,
) -> None:
    """movement policy の変更と、その実遷移に一致する記録を作る。"""
    authority_path = repository / helpers.checker.DEFAULT_ALLOWLIST
    authority = _read_json_object(authority_path)
    control = _object(authority["baseline_control"], "baseline_control")
    policy = _object(control["movement_policy"], "movement_policy")
    triggers = policy["movement_triggers"]
    if not isinstance(triggers, list):
        raise ValueError("movement_policy.movement_triggers は配列が必要")
    triggers.append("archive_case_mapping")
    if bump_identifier:
        helpers._bump_asset_revision(authority)
    helpers._write_contract_asset(authority_path, authority)
    helpers._append_current_repository_transition_record(
        repository,
        base_sha,
        acceptance_id=acceptance_id,
    )


def _add_snapshot_count_case(
    repository: Path,
    helpers: ModuleType,
    target_count: int,
) -> None:
    """snapshot の総件数を指定値まで増やす。"""
    snapshot_root = repository / HISTORY_SNAPSHOT_DIRECTORY
    index = 0
    while len(tuple(snapshot_root.iterdir())) < target_count:
        helpers._write_content_snapshot(
            repository,
            f"frozen archive count case {index}\n".encode(),
        )
        index += 1


def _add_snapshot_bytes_case(
    repository: Path,
    helpers: ModuleType,
    target_bytes: int,
) -> None:
    """snapshot の総バイト数を指定値まで増やす。"""
    snapshot_root = repository / HISTORY_SNAPSHOT_DIRECTORY
    current_bytes = sum(path.stat().st_size for path in snapshot_root.iterdir())
    if current_bytes >= target_bytes:
        raise ValueError("比較 fixture が既に snapshot バイト閾値を超えている")
    helpers._write_content_snapshot(
        repository,
        b"x" * (target_bytes - current_bytes),
    )


def _apply_case_action(
    definition: CaseDefinition,
    repository: Path,
    base_sha: str,
    helpers: ModuleType,
    acceptance_id: str,
) -> None:
    """比較元 commit の後にケース固有の HEAD 変異を加える。"""
    if definition.action in {
        "unchanged",
        "noncanonical_existing_reference",
        "missing_existing_v2_reference",
    }:
        return
    if definition.action == "recorded_movement":
        _apply_recorded_movement(
            repository,
            base_sha,
            helpers,
            bump_identifier=True,
            acceptance_id=acceptance_id,
        )
        return
    if definition.action == "unchanged_identifier":
        _apply_recorded_movement(
            repository,
            base_sha,
            helpers,
            bump_identifier=False,
            acceptance_id=acceptance_id,
        )
        return
    if definition.action == "new_orphan_snapshot":
        helpers._write_content_snapshot(repository, b"new orphan snapshot\n")
        return
    if definition.action == "snapshot_count_over_limit":
        _add_snapshot_count_case(
            repository,
            helpers,
            definition.parameters["target_snapshot_count"],
        )
        return
    if definition.action == "snapshot_bytes_over_limit":
        _add_snapshot_bytes_case(
            repository,
            helpers,
            definition.parameters["target_snapshot_bytes"],
        )
        return
    if definition.action == "noncanonical_appended_reference":
        _apply_recorded_movement(
            repository,
            base_sha,
            helpers,
            bump_identifier=True,
            acceptance_id=acceptance_id,
        )
        authority_path = repository / helpers.checker.DEFAULT_ALLOWLIST
        authority = _read_json_object(authority_path)
        control = _object(authority["baseline_control"], "baseline_control")
        history = control["history"]
        if not isinstance(history, list) or not history:
            raise ValueError("追記 v2 記録が無い")
        snapshot = _external_snapshot_entry(
            _object(history[-1], "baseline_control.history[-1]")
        )
        digest = _string(snapshot["sha256"], "snapshot.sha256")
        snapshot["snapshot_ref"] = f"invalid-history-snapshots/{digest}"
        helpers._write_contract_asset(authority_path, authority)
        return
    raise ValueError(f"HEAD 変異として扱えない action: {definition.action}")


def _event_and_merge(
    repository: Path,
    event_path: Path,
    helpers: ModuleType,
) -> tuple[str, str, str]:
    """event と二親 merge が同じ PR 遷移を指すことを検証する。"""
    event = _object(
        json.loads(event_path.read_text(encoding="utf-8")),
        "github_event",
    )
    pull_request = _object(event["pull_request"], "github_event.pull_request")
    base = _object(pull_request["base"], "github_event.pull_request.base")
    head = _object(pull_request["head"], "github_event.pull_request.head")
    base_sha = _string(base["sha"], "github_event.pull_request.base.sha")
    head_sha = _string(head["sha"], "github_event.pull_request.head.sha")
    parent_line = helpers.checker._run_git(
        repository,
        ["rev-list", "--parents", "-n", "1", "HEAD"],
    ).split()
    if len(parent_line) != 3 or parent_line[1:] != [base_sha, head_sha]:
        raise ValueError("GitHub event と二親 merge が不一致")
    return base_sha, head_sha, parent_line[0]


def _pull_request_number_for_case(
    definition: CaseDefinition,
    repository: Path,
    helpers: ModuleType,
    manifest: Manifest,
) -> int:
    """記録追記ケースへ比較元履歴で未使用の PR 番号を割り当てる。

    Args:
        definition: 構築する比較ケース。
        repository: 比較元の契約資産を持つ合成リポジトリ。
        helpers: 既存テストからロードした補助モジュール。
        manifest: 比較 corpus の固定情報。

    Returns:
        event と追記記録の双方へ設定する PR 番号。
    """
    if definition.action not in RECORD_APPENDING_ACTIONS:
        return manifest.pull_request_number

    authority_path = repository / helpers.checker.DEFAULT_ALLOWLIST
    authority = _read_json_object(authority_path)
    control = _object(authority["baseline_control"], "baseline_control")
    history = control["history"]
    if not isinstance(history, list):
        raise ValueError("baseline_control.history は配列が必要")
    acceptance_ids: set[str] = set()
    for index, raw_record in enumerate(history):
        location = f"baseline_control.history[{index}]"
        record = _object(raw_record, location)
        if "acceptance_id" not in record:
            continue
        acceptance_ids.add(
            _string(record["acceptance_id"], f"{location}.acceptance_id")
        )
    pull_request_number = manifest.pull_request_number
    while (
        f"{manifest.repository_full_name}#{pull_request_number}"
        in acceptance_ids
    ):
        pull_request_number += 1
    return pull_request_number


def prepare_case(
    definition: CaseDefinition,
    destination: Path,
    source_root: Path,
    manifest: Manifest,
    monkeypatch: pytest.MonkeyPatch,
) -> PreparedCase:
    """同じ入力を複数版へ渡せる PR 受理用リポジトリを作る。

    Args:
        definition: 作る比較ケース。
        destination: ケース固有の作業ディレクトリ。
        source_root: 現行 fixture と既存テスト補助を読むリポジトリ。
        manifest: 比較 corpus の固定情報。
        monkeypatch: event 環境を一時設定する pytest 補助。

    Returns:
        event と二親 merge を検証済みの合成リポジトリ。
    """
    helpers = _load_repository_helpers(source_root)
    repository, base_sha = helpers._initialize_test_repository(destination, {})
    if definition.action in {
        "noncanonical_existing_reference",
        "missing_existing_v2_reference",
    }:
        _mutate_existing_reference(
            repository,
            helpers,
            remove=definition.action == "missing_existing_v2_reference",
        )
        base_sha = helpers._commit_test_repository(
            repository,
            f"case {definition.id} comparison base",
        )
    pull_request_number = _pull_request_number_for_case(
        definition,
        repository,
        helpers,
        manifest,
    )
    acceptance_id = f"{manifest.repository_full_name}#{pull_request_number}"
    _apply_case_action(
        definition,
        repository,
        base_sha,
        helpers,
        acceptance_id,
    )
    event_path = destination / "pull-request-event.json"
    helpers._seal_pull_request_worktree(
        repository,
        base_sha,
        monkeypatch,
        event_path,
        number=pull_request_number,
    )
    actual_base, head_sha, merge_sha = _event_and_merge(
        repository,
        event_path,
        helpers,
    )
    event = _object(
        json.loads(event_path.read_text(encoding="utf-8")),
        "github_event",
    )
    event_repository = _object(event["repository"], "github_event.repository")
    pull_request = _object(event["pull_request"], "github_event.pull_request")
    base = _object(pull_request["base"], "github_event.pull_request.base")
    if (
        event_repository.get("full_name") != manifest.repository_full_name
        or pull_request.get("number") != pull_request_number
        or base.get("ref") != "develop"
        or actual_base != base_sha
    ):
        raise ValueError("GitHub event の PR 受理情報が manifest と不一致")
    return PreparedCase(
        definition=definition,
        repository=repository,
        event_path=event_path,
        base_sha=base_sha,
        head_sha=head_sha,
        merge_sha=merge_sha,
    )


def make_record_stale_by_changing_frozen_implementation(
    prepared: PreparedCase,
    source_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> PreparedCase:
    """記録済み遷移の凍結実体だけを変えた PR 受理入力を作る。

    Args:
        prepared: 正しい単一遷移を封入済みの合成リポジトリ。
        source_root: 現行のテスト補助を読むリポジトリ。
        monkeypatch: event 環境を一時設定する pytest 補助。

    Returns:
        記録を更新せず凍結実体だけを変えた PR 受理用リポジトリ。
    """
    helpers = _load_repository_helpers(source_root)
    event = _object(
        json.loads(prepared.event_path.read_text(encoding="utf-8")),
        "github_event",
    )
    pull_request = _object(event["pull_request"], "github_event.pull_request")
    pull_request_number = _positive_integer(
        pull_request["number"],
        "github_event.pull_request.number",
    )
    implementation_path = prepared.repository / CHECKER_RELATIVE_PATH
    implementation_path.write_text(
        implementation_path.read_text(encoding="utf-8")
        + "\n# 記録を陳腐化させる合成変異。\n",
        encoding="utf-8",
    )
    helpers._seal_pull_request_worktree(
        prepared.repository,
        prepared.base_sha,
        monkeypatch,
        prepared.event_path,
        number=pull_request_number,
    )
    base_sha, head_sha, merge_sha = _event_and_merge(
        prepared.repository,
        prepared.event_path,
        helpers,
    )
    return PreparedCase(
        definition=prepared.definition,
        repository=prepared.repository,
        event_path=prepared.event_path,
        base_sha=base_sha,
        head_sha=head_sha,
        merge_sha=merge_sha,
    )


def _git(
    root: Path,
    arguments: list[str],
) -> subprocess.CompletedProcess[str]:
    """検査器作業木に対して read-only の Git コマンドを実行する。"""
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def validate_checker_spec(spec: CheckerSpec, manifest: Manifest) -> None:
    """検査器パスと、前版なら固定 SHA・detached・清潔性を検証する。"""
    checker_path = spec.root / CHECKER_RELATIVE_PATH
    if not checker_path.is_file():
        raise ValueError(f"検査器が存在しない: {checker_path}")
    if spec.label != "previous":
        return
    revision = _git(spec.root, ["rev-parse", "HEAD"])
    if revision.returncode != 0 or revision.stdout.strip() != manifest.comparison_revision:
        raise ValueError(
            "前版検査器は manifest.comparison_revision の作業木が必要"
        )
    branch = _git(spec.root, ["symbolic-ref", "-q", "HEAD"])
    if branch.returncode == 0:
        raise ValueError("前版検査器は detached HEAD が必要")
    status = _git(spec.root, ["status", "--porcelain", "--untracked-files=all"])
    if status.returncode != 0 or status.stdout:
        raise ValueError("前版検査器は清潔な作業木が必要")


def run_checker(
    prepared: PreparedCase,
    spec: CheckerSpec,
    source_environment: dict[str, str] | None = None,
) -> RunResult:
    """指定版の CLI を合成リポジトリへ PR 受理モードで当てる。"""
    environment = dict(
        os.environ if source_environment is None else source_environment
    )
    event = _object(
        json.loads(prepared.event_path.read_text(encoding="utf-8")),
        "github_event",
    )
    event_repository = _object(event["repository"], "github_event.repository")
    pull_request = _object(event["pull_request"], "github_event.pull_request")
    base = _object(pull_request["base"], "github_event.pull_request.base")
    environment.update(
        {
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(prepared.event_path),
            "GITHUB_WORKSPACE": str(prepared.repository),
            "GITHUB_REPOSITORY": _string(
                event_repository["full_name"],
                "github_event.repository.full_name",
            ),
            "GITHUB_BASE_REF": _string(
                base["ref"],
                "github_event.pull_request.base.ref",
            ),
        }
    )
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(spec.root / CHECKER_RELATIVE_PATH),
            "--root",
            str(prepared.repository),
        ],
        cwd=spec.root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    definition = prepared.definition
    return RunResult(
        case_id=definition.id,
        checker=spec.label,
        expected=definition.expected[spec.label],
        expected_exit_code=definition.recorded_exit_codes[spec.label],
        exit_code=result.returncode,
        stdout=result.stdout.strip(),
        stderr=result.stderr.strip(),
    )


def run_cases(
    manifest: Manifest,
    checker_specs: tuple[CheckerSpec, ...],
    source_root: Path,
    selected_case_ids: frozenset[int] | None = None,
) -> tuple[RunResult, ...]:
    """各ケースを 1 回だけ構築し、同じリポジトリを全版へ渡す。"""
    for spec in checker_specs:
        validate_checker_spec(spec, manifest)
    selected = tuple(
        case
        for case in manifest.cases
        if selected_case_ids is None or case.id in selected_case_ids
    )
    if selected_case_ids is not None and {case.id for case in selected} != set(
        selected_case_ids
    ):
        raise ValueError("指定された case ID が manifest に存在しない")

    results: list[RunResult] = []
    with tempfile.TemporaryDirectory(prefix="frozen-archive-cases-") as raw:
        temporary_root = Path(raw)
        for definition in selected:
            monkeypatch = pytest.MonkeyPatch()
            try:
                prepared = prepare_case(
                    definition,
                    temporary_root / f"case-{definition.id:02d}",
                    source_root,
                    manifest,
                    monkeypatch,
                )
                for spec in checker_specs:
                    results.append(run_checker(prepared, spec))
            finally:
                monkeypatch.undo()
    return tuple(results)


def _checker_spec(raw: str) -> CheckerSpec:
    """``previous=/path`` 形式の CLI 値を読む。"""
    label, separator, raw_path = raw.partition("=")
    if separator != "=" or label not in {"previous", "current"} or not raw_path:
        raise argparse.ArgumentTypeError(
            "--checker は previous=/path または current=/path が必要"
        )
    return CheckerSpec(label=label, root=Path(raw_path).resolve())


def _result_payload(results: tuple[RunResult, ...]) -> dict[str, object]:
    """実行結果を機械集計用 JSON object にする。"""
    return {
        "results": [
            {
                "case_id": result.case_id,
                "checker": result.checker,
                "expected": result.expected,
                "expected_exit_code": result.expected_exit_code,
                "exit_code": result.exit_code,
                "matches": result.matches,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            for result in results
        ],
        "all_matched": all(result.matches for result in results),
    }


def main(argv: list[str] | None = None) -> int:
    """比較 runner の CLI 入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument(
        "--checker",
        action="append",
        type=_checker_spec,
        required=True,
        help="previous=/path または current=/path。複数指定で同じ入力へ当てる",
    )
    parser.add_argument("--case", action="append", type=int, dest="case_ids")
    args = parser.parse_args(argv)
    labels = [spec.label for spec in args.checker]
    if len(labels) != len(set(labels)):
        parser.error("--checker の版ラベルを重複できない")
    try:
        manifest = load_manifest(args.manifest.resolve())
        results = run_cases(
            manifest,
            tuple(args.checker),
            args.source_root.resolve(),
            (
                frozenset(args.case_ids)
                if args.case_ids is not None
                else None
            ),
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"runner_error": str(error)}, ensure_ascii=False))
        return 2
    payload = _result_payload(results)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["all_matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
