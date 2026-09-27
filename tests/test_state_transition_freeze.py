"""状態遷移契約の凍結基準と追記専用受理履歴を検証する。"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FREEZE_SCRIPT = REPOSITORY_ROOT / "scripts" / "state_transition_freeze.py"
DESCRIPTOR_SCRIPT = REPOSITORY_ROOT / "scripts" / "check_input_axes_descriptor.py"


def _load_module(name: str, path: Path) -> Any:
    """テスト対象をsys.path変更なしでモジュールとして読む。"""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


freeze_checker = _load_module("state_transition_freeze", FREEZE_SCRIPT)
descriptor_checker = _load_module(
    "freeze_test_descriptor_checker", DESCRIPTOR_SCRIPT
)


def _descriptor() -> dict[str, Any]:
    """リポジトリの入力軸descriptorを読む。"""
    path = REPOSITORY_ROOT / descriptor_checker.DESCRIPTOR_PATH
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _declaration() -> dict[str, Any]:
    """descriptorの凍結基準宣言を返す。"""
    value = _descriptor()[freeze_checker.FREEZE_FIELD]
    assert isinstance(value, dict)
    return value


def _git_sha(root: Path, revision: str) -> str:
    """テスト用リポジトリのrevisionを完全SHAへ解決する。"""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repository_acceptance_context() -> Any:
    """実リポジトリ用の外部PR受理文脈を返す。"""
    return freeze_checker.PullRequestAcceptanceContext(
        base_sha=_git_sha(REPOSITORY_ROOT, "origin/develop"),
        head_sha=_git_sha(REPOSITORY_ROOT, "HEAD"),
        repository="masaki1025/pitchlog",
        number=81,
    )


def test_repository_history_is_one_append_from_origin_develop() -> None:
    """PR比較元で基準が無かった状態から受理記録1件だけを追記している。"""
    freeze_checker.validate_repository_history(
        REPOSITORY_ROOT,
        descriptor_checker.DESCRIPTOR_PATH,
        _declaration(),
        _repository_acceptance_context(),
    )


def test_current_identities_are_derived_from_scope_and_asset_side_criteria() -> None:
    """線の定義と現行3基準の識別値を資産側宣言だけから導出する。"""
    declaration = freeze_checker.validate_declaration(_declaration())

    assert declaration["history"][-1]["newIdentity"] == {
        "present": True,
        "values": freeze_checker.current_identities(declaration),
    }


def test_assurance_boundary_distinguishes_guaranteed_identity_from_review_scope() -> None:
    """宣言済み同一性の保証と宣言外基準の不存在の非保証を混同しない。"""
    boundary = _declaration()["scope"]["assuranceBoundary"]

    assert set(boundary["mechanicallyGuaranteed"]["subjectJsonPointers"]) == {
        "/freezeBaseline/scope",
        "/freezeBaseline/criteria",
    }
    assert (
        boundary["mechanicallyGuaranteed"]["changeWithoutAcceptanceRecord"]
        == "fail"
    )
    assert boundary["mechanicallyGuaranteed"]["comparisonSource"] == (
        "github-pull-request-event.pull_request.base.sha"
    )
    assert boundary["mechanicallyGuaranteed"]["missingComparisonSourceAction"] == (
        "fail-in-acceptance-mode"
    )
    assert boundary["mechanicallyGuaranteed"]["localInvariantModeResult"] == (
        "acceptance-transition-not-checked-explicit"
    )
    assert boundary["notMechanicallyGuaranteed"] == {
        "propertyId": "absence-of-undeclared-implementation-baselines",
        "reason": "arbitrary-program-semantic-analysis-is-undecidable",
        "normativeStatus": "prohibited-by-dev-harness-7.7-1",
        "reviewControl": "pull-request-review",
    }
    assert _declaration()["scope"]["selectionRule"][
        "knownDirectComparisonDispositions"
    ] == [
        {
            "findingId": "round10-require-exact-keys-48",
            "sourcePath": "scripts/state_transition_freeze.py",
            "construct": "_require_exact_keys.expected-key-set",
            "observedValue": 48,
            "disposition": "outside-frozen-criterion-values",
            "selectionRuleRole": "closed-object-grammar-key-set",
            "reason": (
                "宣言JSONの閉じた文法を識別するobject member名であり、"
                "凍結するchecker判断値ではない"
            ),
        }
    ]


def test_missing_declaration_is_fail_closed() -> None:
    """凍結基準宣言を取得できなければdescriptor検査を開始できない。"""
    descriptor = _descriptor()
    descriptor.pop(freeze_checker.FREEZE_FIELD)

    with pytest.raises(
        descriptor_checker.DescriptorCheckError,
        match="凍結基準宣言を検証できない",
    ):
        descriptor_checker.load_descriptor_criteria(descriptor)


def test_empty_criteria_is_fail_closed() -> None:
    """判断元が空なら中立扱いせず拒否する。"""
    declaration = copy.deepcopy(_declaration())
    declaration["criteria"]["threeWayParity"] = {}

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="空でないobject",
    ):
        freeze_checker.validate_declaration(declaration)


def test_unresolvable_comparison_source_is_fail_closed() -> None:
    """eventの比較元SHAを解決できない場合は直前基準なしと推定せず拒否する。"""
    context = freeze_checker.PullRequestAcceptanceContext(
        base_sha="0" * 40,
        head_sha=_git_sha(REPOSITORY_ROOT, "HEAD"),
        repository="masaki1025/pitchlog",
        number=81,
    )

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="rev-parse.*実行できない",
    ):
        freeze_checker.validate_repository_history(
            REPOSITORY_ROOT,
            descriptor_checker.DESCRIPTOR_PATH,
            _declaration(),
            context,
        )


def test_asset_cannot_self_report_comparison_source_across_two_commits(
    tmp_path: Path,
) -> None:
    """2コミットで比較元を自己申告しても外部PR baseとの差を隠せない。"""
    root = _copy_audited_sources(tmp_path)
    descriptor_path = root / descriptor_checker.DESCRIPTOR_PATH
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPOSITORY_ROOT / descriptor_checker.DESCRIPTOR_PATH, descriptor_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "freeze-test@example.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "freeze test"], cwd=root, check=True
    )
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    base_sha = _git_sha(root, "HEAD")

    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    declaration = descriptor[freeze_checker.FREEZE_FIELD]
    declaration["criteria"]["threeWayParity"]["branchCoverageExclusions"][
        "DRAW-04"
    ] = "改ざんした基準"
    declaration["history"][0]["newIdentity"] = {
        "present": True,
        "values": freeze_checker.current_identities(declaration),
    }
    descriptor_path.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", str(descriptor_checker.DESCRIPTOR_PATH)], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "attack A"], cwd=root, check=True)
    attack_a_sha = _git_sha(root, "HEAD")

    declaration["acceptance"]["comparisonSource"] = f"asset:{attack_a_sha}"
    declaration["scope"]["engineExpectedValues"]["acceptance"][
        "comparisonSource"
    ] = f"asset:{attack_a_sha}"
    declaration["history"][0]["newIdentity"] = {
        "present": True,
        "values": freeze_checker.current_identities(declaration),
    }
    descriptor_path.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", str(descriptor_checker.DESCRIPTOR_PATH)], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "attack B"], cwd=root, check=True)

    context = freeze_checker.PullRequestAcceptanceContext(
        base_sha=base_sha,
        head_sha=_git_sha(root, "HEAD"),
        repository="masaki1025/pitchlog",
        number=81,
    )
    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="書き換えまたは削除",
    ):
        freeze_checker.validate_repository_history(
            root,
            descriptor_checker.DESCRIPTOR_PATH,
            declaration,
            context,
        )


def test_existing_history_record_rewrite_is_red() -> None:
    """受理済み履歴の事実欄を書き換えても追記として扱わない。"""
    base = _declaration()
    current = copy.deepcopy(base)
    current["history"][0]["fact"] = "書き換えた事実"

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="書き換えまたは削除",
    ):
        freeze_checker.validate_append_only_transition(current, base)


def test_existing_history_record_deletion_is_red() -> None:
    """受理済み履歴を削除しても追記専用検査が拒否する。"""
    base = _declaration()
    current = copy.deepcopy(base)
    current["history"] = []

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="historyは空でない配列",
    ):
        freeze_checker.validate_append_only_transition(current, base)


def test_criteria_change_without_acceptance_record_is_red() -> None:
    """基準値だけを追随させて受理履歴を増やさない変更を拒否する。"""
    declaration = copy.deepcopy(_declaration())
    exclusions = declaration["criteria"]["threeWayParity"][
        "branchCoverageExclusions"
    ]
    exclusions["DRAW-04"] = "受理記録なしの変更"

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="newIdentityが現行基準の識別値と一致しない",
    ):
        freeze_checker.validate_declaration(declaration)


def test_scope_change_without_acceptance_record_is_red() -> None:
    """線の定義だけを変えても基準移動として受理履歴を要求する。"""
    declaration = copy.deepcopy(_declaration())
    declaration["scope"]["selectionRule"]["requiredRepresentation"] = (
        "changed-without-acceptance"
    )

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="newIdentityが現行基準の識別値と一致しない",
    ):
        freeze_checker.validate_declaration(declaration)


def test_criterion_set_removal_from_declaration_is_red() -> None:
    """集合宣言と基準を同時に縮小しても既存受理履歴が拒否する。"""
    declaration = copy.deepcopy(_declaration())
    removed = declaration["scope"]["criterionOrder"].pop()
    declaration["scope"]["criterionBindings"].pop(removed)
    declaration["criteria"].pop(removed)

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="newIdentityが現行基準の識別値と一致しない",
    ):
        freeze_checker.validate_declaration(declaration)


def _copy_audited_sources(tmp_path: Path) -> Path:
    """宣言が監査する検査器sourceを一時リポジトリへ複製する。"""
    root = tmp_path / "repository"
    scope = _declaration()["scope"]
    paths = {
        scope["sourceLiteralAudit"]["engineSourcePath"],
        *(binding["sourcePath"] for binding in scope["criterionBindings"].values()),
    }
    for relative_path in paths:
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT / relative_path, destination)
    return root


def test_implementation_side_criterion_set_is_red(tmp_path: Path) -> None:
    """criterion集合を検査器へ再設置すると宣言集合より小さくても拒否する。"""
    root = _copy_audited_sources(tmp_path)
    engine_path = root / _declaration()["scope"]["sourceLiteralAudit"][
        "engineSourcePath"
    ]
    source = engine_path.read_text(encoding="utf-8")
    engine_path.write_text(
        source + '\nIMPLEMENTATION_CRITERIA = ("threeWayParity",)\n',
        encoding="utf-8",
    )

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="criterion IDを検査器sourceへ直書きしている",
    ):
        freeze_checker.validate_implementation_correspondence(root, _declaration())


@pytest.mark.parametrize(
    ("target", "changed"),
    [
        ("combination", "pairwise-changed-without-acceptance"),
        ("schema-retention", "optional-after-projection"),
    ],
)
def test_unaccepted_checker_literal_is_red(
    tmp_path: Path, target: str, changed: str
) -> None:
    """descriptor・schema・検査器を同時追随しても宣言なしでは拒否する。"""
    root = _copy_audited_sources(tmp_path)
    descriptor_path = root / descriptor_checker.DESCRIPTOR_PATH
    schema_path = root / descriptor_checker.SCHEMA_PATH
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPOSITORY_ROOT / descriptor_checker.DESCRIPTOR_PATH, descriptor_path)
    shutil.copy2(REPOSITORY_ROOT / descriptor_checker.SCHEMA_PATH, schema_path)
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if target == "combination":
        descriptor["gameEndCombinationRules"]["ruleFieldCombination"] = changed
        schema["$defs"]["gameEndCombinationRules"]["properties"][
            "ruleFieldCombination"
        ]["const"] = changed
    else:
        for field in descriptor["nonCoverageFields"]:
            field["schemaRetention"] = changed
        schema["$defs"]["nonCoverageField"]["properties"]["schemaRetention"][
            "const"
        ] = changed
    descriptor["digest"] = descriptor_checker.compute_descriptor_digest(descriptor)
    descriptor_path.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert descriptor["digest"] == descriptor_checker.compute_descriptor_digest(
        descriptor
    )

    source_path = root / "scripts/check_input_axes_descriptor.py"
    source = source_path.read_text(encoding="utf-8")
    source_path.write_text(
        source
        + '\ndef _unaccepted_value(value: object) -> bool:\n'
        + f"    return value == {changed!r}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="線引き宣言とexact-set不一致",
    ):
        freeze_checker.validate_implementation_correspondence(root, _declaration())


def test_numeric_compare_injected_into_checker_is_declared_outside_mechanical_guarantee(
    tmp_path: Path,
) -> None:
    """任意コードの数値比較は現監査の保証範囲外であることを挙動でも記録する。"""
    declaration = _declaration()
    audit = declaration["scope"]["sourceLiteralAudit"]
    assert audit["assuranceLevel"] == "supplemental-non-exhaustive-regression-signal"
    assert "numeric-literal" in audit["notCoveredConstructs"]
    assert (
        declaration["scope"]["assuranceBoundary"]["notMechanicallyGuaranteed"][
            "propertyId"
        ]
        == "absence-of-undeclared-implementation-baselines"
    )

    root = _copy_audited_sources(tmp_path)
    source_path = root / "scripts/check_input_axes_descriptor.py"
    source = source_path.read_text(encoding="utf-8")
    source_path.write_text(
        source
        + "\ndef _outside_assurance_boundary(combination_rules: list[object]) -> bool:\n"
        + "    if len(combination_rules) != 3:\n"
        + "        return False\n"
        + "    return True\n",
        encoding="utf-8",
    )

    # これは合格経路の肯定ではなく、宣言した非保証境界の回帰記録である。
    freeze_checker.validate_implementation_correspondence(root, declaration)
