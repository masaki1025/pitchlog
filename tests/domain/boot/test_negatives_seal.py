"""封印系 BOOT 条項の負例が既存機構を個別に落とすことを検査する。"""

from __future__ import annotations

import ast
import importlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
BACKEND_SRC = ROOT / "backend/src"
NEGATIVE_DIR = ROOT / "backend/tests/domain/boot/negatives/seal"
CLAUSES_ASSET = ROOT / "backend/domain/boot-clauses.json"
CHECK_SETS_ASSET = ROOT / "backend/domain/check-sets.json"
BOOT_SEAL_ASSET = ROOT / "backend/domain/boot-seal.json"
BOOT_REPORT_SCHEMA = ROOT / "backend/domain/boot-report.schema.json"
SEAL_SOURCE = BACKEND_SRC / "pitchlog/domaincheck/seal.py"
NEGATIVE_FIXTURES = tuple(sorted(NEGATIVE_DIR.glob("*.json")))

sys.path.insert(0, str(BACKEND_SRC))
CLAUSES = importlib.import_module("pitchlog.domaincheck.boot.clauses")
PHASE2 = importlib.import_module("pitchlog.domaincheck.boot.phase2")
REPORT = importlib.import_module("pitchlog.domaincheck.boot.report")
STALL = importlib.import_module("pitchlog.domaincheck.boot.stall")

_CASE_KEYS = frozenset({"caseId", "clauseId", "mechanism", "violation"})


def _load_case(path: Path) -> dict[str, Any]:
    """厳密キー集合を持つ負例 fixture を読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert frozenset(value) == _CASE_KEYS
    string_fields = _CASE_KEYS - {"violation"}
    assert all(
        isinstance(value[field], str) and value[field] for field in string_fields
    )
    assert isinstance(value["violation"], dict)
    return value


def _seal_clause_ids() -> frozenset[str]:
    """対応表の逆引き結果から封印系条項を意味で選ぶ。"""
    clauses = CLAUSES.load_and_validate_registry(ROOT)
    semantic_markers = (
        "宣言の更新のみをもって解消としてはならない",
        "出力のない緑は本規定の充足とみなさない",
    )
    return frozenset(
        clause.identifier
        for clause in clauses
        if clause.identifier.startswith("BOOT-SEAL")
        or any(marker in clause.normative_text for marker in semantic_markers)
    )


def _write_json(path: Path, value: object) -> None:
    """合成資産を人間が確認できる JSON として書く。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _git(root: Path, *arguments: str) -> str:
    """合成履歴の Git コマンドを実行して標準出力を返す。"""
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _run_seal(root: Path, arguments: list[str]) -> int:
    """既存の封印 CLI を独立プロセスで実行する。"""
    environment: dict[str, str] = dict(os.environ)
    environment["PYTHONPATH"] = str(BACKEND_SRC)
    environment.pop("CI", None)
    result = subprocess.run(
        [sys.executable, "-m", "pitchlog.domaincheck.seal", *arguments],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


def _classification_exemption(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """報告分類を無視し、封印 ID の集合包含だけで免除を判定する。"""
    check_sets = json.loads(CHECK_SETS_ASSET.read_text(encoding="utf-8"))
    decision = check_sets["exemptionDecision"]
    predicate = decision["predicate"]
    violation = case["violation"]
    finding_id = violation["findingId"]
    sealed_ids = set(violation["sealedFindingIds"])
    report_kinds = {
        entry["id"] for entry in check_sets["reportVocabulary"]["values"]
    }
    if (
        predicate["operator"] != "set-subset"
        or set(decision["dependsOnlyOn"])
        != {"findingId", "sealedSet.unresolvedFindingIds"}
        or violation["reportKind"] not in report_kinds
    ):
        return 2
    if disabled:
        sealed_ids.add(finding_id)
    return 0 if {finding_id} <= sealed_ids else 1


def _git_subcommands(source: str) -> frozenset[str]:
    """実行可能な `_run_git` 呼び出しの定数サブコマンドを集める。"""
    tree = ast.parse(source)
    return frozenset(
        call.args[1].value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "_run_git"
        and len(call.args) >= 2
        and isinstance(call.args[1], ast.Constant)
        and isinstance(call.args[1].value, str)
    )


def _merge_base_comparison(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """比較元導出へ禁止サブコマンドを入れたソース変異を検出する。"""
    source = SEAL_SOURCE.read_text(encoding="utf-8")
    violation = case["violation"]
    forbidden = violation["forbiddenSubcommand"]
    allowed = violation["allowedSubcommand"]
    if not disabled:
        original = f'"{allowed}"'
        replacement = f'"{forbidden}"'
        changed = source.replace(original, replacement, 1)
        if changed == source:
            return 2
        source = changed
    return 1 if forbidden in _git_subcommands(source) else 0


def _fixed_base_rewrite(
    case: dict[str, Any],
    temporary_root: Path,
    disabled: bool,
) -> int:
    """Git 初出後に固定比較元を書き換えた封印を既存 CLI へ渡す。"""
    violation = case["violation"]
    asset_path = Path(violation["assetPath"])
    seal_path = Path(violation["sealPath"])
    repository = temporary_root / case["caseId"]
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "Step 22 Test")
    _git(repository, "config", "user.email", "step22@example.invalid")
    _write_json(repository / asset_path, {"value": 1})
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "base")
    base_commit = _git(repository, "rev-parse", "HEAD")
    common = [
        "--root",
        str(repository),
        "--asset",
        asset_path.as_posix(),
        "--seal",
        seal_path.as_posix(),
    ]
    assert _run_seal(
        repository,
        [*common, "--base-commit", base_commit, "--reseal"],
    ) == 0
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "introduce seal")
    current_commit = _git(repository, "rev-parse", "HEAD")
    verification_base = base_commit
    if not disabled:
        seal = json.loads((repository / seal_path).read_text(encoding="utf-8"))
        seal["baseCommitOid"] = current_commit
        _write_json(repository / seal_path, seal)
        verification_base = current_commit
    return _run_seal(
        repository,
        [*common, "--base-commit", verification_base, "--verify"],
    )


def _unresolved_reappearance(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """未解消件数の再増加を既存の状態遷移へ渡す。"""
    violation = case["violation"]
    starting = violation["startingUnresolvedCount"]
    observed = starting if disabled else violation["observedUnresolvedCount"]
    state = STALL.activate(STALL.defined_state(starting), "activation")
    try:
        STALL.observe_pr_integration(state, "integration", observed)
    except STALL.CheckerViolation:
        return 1
    except STALL.CheckerExecutionError:
        return 2
    return 0


def _declaration_only_resolution(
    case: dict[str, Any],
    _temporary_root: Path,
    disabled: bool,
) -> int:
    """宣言だけの変更に対する解消主張を既存の意味判定と照合する。"""
    universe = PHASE2.load_target_universe(ROOT)
    target_id = universe.targets[0].identifier
    state = STALL.activate(STALL.defined_state(1), "activation")
    declaration_only = PHASE2.SemanticSnapshot(
        declarations=frozenset({target_id}),
        generated=frozenset(),
        product_calls=frozenset(),
        vector_checks=frozenset(),
        property_checks=frozenset(),
        mutation_checks=frozenset(),
    )
    decision = PHASE2.classify_phase2(
        state,
        universe,
        PHASE2.SemanticSnapshot.empty(),
        declaration_only,
    )
    sealed_asset = json.loads(BOOT_SEAL_ASSET.read_text(encoding="utf-8"))
    resolved = REPORT.resolved_element_ids_from_phase2(sealed_asset, decision)
    claims_resolution = False if disabled else case["violation"]["claimsResolution"]
    return 0 if claims_resolution == bool(resolved) else 1


def _missing_report_output(
    case: dict[str, Any],
    temporary_root: Path,
    disabled: bool,
) -> int:
    """未解消一覧を出さない緑を既存のレポート検査へ渡す。"""
    repository = temporary_root / case["caseId"]
    domain = repository / "backend/domain"
    domain.mkdir(parents=True)
    shutil.copy2(BOOT_SEAL_ASSET, domain / BOOT_SEAL_ASSET.name)
    shutil.copy2(BOOT_REPORT_SCHEMA, domain / BOOT_REPORT_SCHEMA.name)
    emit_report = True if disabled else case["violation"]["emitReport"]
    if emit_report:
        REPORT.emit_boot_report(repository, frozenset())
    try:
        REPORT.accept_transition_green(repository, frozenset())
    except REPORT.CheckerViolation:
        return 1
    except REPORT.CheckerExecutionError:
        return 2
    return 0


CaseExecutor = Callable[[dict[str, Any], Path, bool], int]
_EXECUTORS: dict[str, CaseExecutor] = {
    "classification-exemption": _classification_exemption,
    "merge-base-comparison": _merge_base_comparison,
    "fixed-base-rewrite": _fixed_base_rewrite,
    "unresolved-reappearance": _unresolved_reappearance,
    "declaration-only-resolution": _declaration_only_resolution,
    "missing-report-output": _missing_report_output,
}


def _execute_case(case: dict[str, Any], root: Path, disabled: bool) -> int:
    """負例が選んだ既存機構を実行し 3 値の結果を返す。"""
    try:
        executor = _EXECUTORS[case["mechanism"]]
    except KeyError:
        return 2
    return executor(case, root, disabled)


def test_seal_clause_set_and_existing_negative_cases_have_no_difference() -> None:
    cases = tuple(_load_case(path) for path in NEGATIVE_FIXTURES)
    expected_clauses = _seal_clause_ids()
    actual_clauses = frozenset(case["clauseId"] for case in cases)
    registry = json.loads(CLAUSES_ASSET.read_text(encoding="utf-8"))
    registered = {
        entry["id"]: frozenset(entry["negativeCaseIds"])
        for entry in registry["clauses"]
        if entry["id"] in expected_clauses
    }
    fixture_ids = {
        clause_id: frozenset(
            case["caseId"] for case in cases if case["clauseId"] == clause_id
        )
        for clause_id in expected_clauses
    }

    assert len(expected_clauses) == 6
    assert actual_clauses == expected_clauses
    assert all(fixture_ids[clause_id] for clause_id in expected_clauses)
    assert registered == fixture_ids
    assert len({case["caseId"] for case in cases}) == len(cases)


def test_negative_fixtures_are_not_pytest_modules() -> None:
    assert NEGATIVE_FIXTURES
    assert all(path.suffix == ".json" for path in NEGATIVE_FIXTURES)
    assert all(not path.name.startswith("test_") for path in NEGATIVE_FIXTURES)


@pytest.mark.parametrize("fixture_path", NEGATIVE_FIXTURES, ids=lambda path: path.stem)
def test_each_seal_negative_fails_individually(
    fixture_path: Path,
    tmp_path: Path,
) -> None:
    case = _load_case(fixture_path)

    assert _execute_case(case, tmp_path, disabled=False) == 1


@pytest.mark.parametrize("fixture_path", NEGATIVE_FIXTURES, ids=lambda path: path.stem)
def test_disabling_each_seal_negative_makes_its_check_green(
    fixture_path: Path,
    tmp_path: Path,
) -> None:
    case = _load_case(fixture_path)

    assert _execute_case(case, tmp_path, disabled=True) == 0
