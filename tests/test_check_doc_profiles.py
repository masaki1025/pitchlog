"""文書検査コンフォーマンスランナーのCLIとenvelopeを検証する。"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "check_doc_profiles.py"
LOADER = REPOSITORY_ROOT / "scripts" / "doc_check_profile.py"
SCHEMA = (
    REPOSITORY_ROOT
    / "scripts"
    / "design_relations"
    / "schemas"
    / "runner-envelope.schema.json"
)
SAMPLE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "profile-sample"
MINIMAL_PROFILE = SAMPLE_ROOT / "profiles" / "profile.json"
DATA_PROFILE = SAMPLE_ROOT / "profiles" / "data-model-like.json"
SAMPLE_REGISTRY = SAMPLE_ROOT / "profiles" / "registry.json"
NEW_CHECK_IDS = frozenset(
    {
        "forbidden-structure",
        "cross-consistency",
        "collection-consistency",
        "baseline-digest",
        "unique-owner",
        "reference-class",
        "attribution-destination",
        "attribution-direct",
    }
)


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load(SCRIPT, "check_doc_profiles_under_test")
profile_loader = _load(LOADER, "check_doc_profiles_loader_under_test")


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _json_result(*arguments: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = _run(*arguments, "--json")
    envelope = json.loads(result.stdout)
    return result, envelope


def _assert_schema(envelope: dict[str, Any]) -> None:
    schema = profile_loader.load_json(SCHEMA)
    profile_loader.validate_against_schema(envelope, schema)
    assert len(envelope["checks"]) == len(profile_loader.CHECK_IDS_ALL) == 22
    assert [check["check_id"] for check in envelope["checks"]] == list(
        profile_loader.CHECK_IDS_ALL
    )


@pytest.mark.parametrize(
    ("arguments", "expected_exit"),
    (
        (("--profile", str(DATA_PROFILE), "--checks", "reference-class"), 0),
        (("--profile", str(DATA_PROFILE), "--checks", "manifest-consistency"), 1),
        (("--profile", "missing-profile.json"), 2),
    ),
    ids=("pass", "violation", "input-error"),
)
def test_runner_json_envelope_covers_all_exit_codes(
    arguments: tuple[str, ...],
    expected_exit: int,
) -> None:
    """終了0・1・2をすべてスキーマ適合envelopeで返す。"""
    result, envelope = _json_result(*arguments)

    assert result.returncode == expected_exit
    assert result.stderr == ""
    assert envelope["exit_code"] == expected_exit
    assert bool(envelope["errors"]) is (expected_exit == 2)
    _assert_schema(envelope)


def test_runner_partial_marks_unselected_checks_not_run() -> None:
    """選択実行をpartialにし、未選択を対象外へ偽装しない。"""
    result, envelope = _json_result(
        "--profile",
        str(DATA_PROFILE),
        "--checks",
        "reference-class",
    )

    assert result.returncode == 0
    assert envelope["partial"] is True
    statuses = {check["check_id"]: check["status"] for check in envelope["checks"]}
    assert statuses["reference-class"] == "pass"
    assert set(statuses.values()) == {"pass", "not_run"}
    assert sum(status == "not_run" for status in statuses.values()) == 21


@pytest.mark.parametrize(
    ("profile_path", "expected_new_status"),
    ((MINIMAL_PROFILE, "not_applicable"), (DATA_PROFILE, None)),
    ids=("minimal", "data-model-like"),
)
def test_runner_executes_all_22_checks_for_both_sample_profiles(
    profile_path: Path,
    expected_new_status: str | None,
) -> None:
    """サンプル2本を入力不正なく全22検査へ通す。"""
    result, envelope = _json_result(
        "--profile",
        str(profile_path),
        "--registry",
        str(SAMPLE_REGISTRY),
    )

    assert result.returncode in {0, 1}
    assert envelope["partial"] is False
    assert envelope["errors"] == []
    _assert_schema(envelope)
    statuses = {check["check_id"]: check["status"] for check in envelope["checks"]}
    if expected_new_status is None:
        assert {statuses[check_id] for check_id in NEW_CHECK_IDS} <= {"pass", "fail"}
        assert statuses["reference-class"] == "pass"
    else:
        assert {statuses[check_id] for check_id in NEW_CHECK_IDS} == {
            expected_new_status
        }


def test_runner_rejects_unknown_invariant_kind_and_missing_profile_field(
    tmp_path: Path,
) -> None:
    """未対応kindとプロファイル必須欄欠落を終了2にする。"""
    raw_profile = profile_loader.load_json(DATA_PROFILE)
    raw_invariants = profile_loader.load_json(SAMPLE_ROOT / "doc" / "invariants.json")
    raw_invariants["declarations"] = [
        {"defect_id": "SP-01", "kind": "unsupported-kind"}
    ]
    invariant_path = tmp_path / "invalid-invariants.json"
    invariant_path.write_text(
        json.dumps(raw_invariants, ensure_ascii=False),
        encoding="utf-8",
    )
    raw_profile["invariants"] = str(invariant_path)
    invalid_kind = tmp_path / "invalid-kind.json"
    invalid_kind.write_text(
        json.dumps(raw_profile, ensure_ascii=False),
        encoding="utf-8",
    )

    result, envelope = _json_result("--profile", str(invalid_kind))
    assert result.returncode == 2
    assert envelope["errors"]
    _assert_schema(envelope)

    del raw_profile["document"]
    missing_field = tmp_path / "missing-field.json"
    missing_field.write_text(
        json.dumps(raw_profile, ensure_ascii=False),
        encoding="utf-8",
    )
    result, envelope = _json_result("--profile", str(missing_field))
    assert result.returncode == 2
    assert envelope["errors"]
    _assert_schema(envelope)


def test_runner_sample_does_not_open_sync_profile_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """サンプル実行が同期文書・manifest・oracleを開かないことを固定する。"""
    forbidden = {
        (REPOSITORY_ROOT / path).resolve()
        for path in (
            "docs/design/sync-protocol.md",
            "scripts/design_relations/sync-protocol.json",
            "scripts/design_relations/defects.json",
            "scripts/design_relations/invariants/sync-protocol.json",
            "scripts/design_relations/req-universe.json",
        )
    }
    original_open = Path.open

    def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.resolve() in forbidden:
            raise AssertionError(f"同期側パスを開いた: {path}")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    exit_code, envelope, _ = runner._run(  # noqa: SLF001
        ["--profile", str(DATA_PROFILE), "--checks", "reference-class", "--json"]
    )

    assert exit_code == 0
    assert envelope["errors"] == []
