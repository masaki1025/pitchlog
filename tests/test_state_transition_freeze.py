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
        number=131,
    )


def test_repository_history_is_append_only_from_origin_develop() -> None:
    """PR比較元から同じPRの受理記録を順に追記している。"""
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


def test_provisional_approval_fields_stay_consistent() -> None:
    """PR #81の暫定記録でapprovedByだけを人名へ変える偽装を拒否する。"""
    current = copy.deepcopy(_declaration())
    record = current["history"][0]
    assert record["approvedBy"] == "未承認(PR #81 のレビュー待ち)"
    assert record["approvedBy"] in record["fact"]

    record["approvedBy"] = "承認者"
    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="暫定記録の整合が崩れている",
    ):
        freeze_checker.validate_declaration(current)


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
    root = _copy_audited_sources(tmp_path, revision="origin/develop")
    descriptor_path = root / descriptor_checker.DESCRIPTOR_PATH
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor_path.write_text(
        subprocess.run(
            ["git", "show", f"origin/develop:{descriptor_checker.DESCRIPTOR_PATH}"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout,
        encoding="utf-8",
    )
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
    # 末尾記録を書き換える。先頭を書き換えると、履歴が2件以上のとき後続記録との
    # 連鎖検査が先に落ち、比較元との差の検出へ届かない。
    declaration["criteria"]["threeWayParity"]["branchCoverageExclusions"][
        "DRAW-04"
    ] = "改ざんした基準"
    declaration["history"][-1]["newIdentity"] = {
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
    declaration["history"][-1]["newIdentity"] = {
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
    """比較元の履歴の事実欄を書き換えても追記として扱わない。"""
    base = _declaration()
    current = copy.deepcopy(base)
    current["history"][0]["fact"] = (
        "未承認(PR #81 のレビュー待ち)。書き換えた事実"
    )

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


def _copy_audited_sources(tmp_path: Path, revision: str | None = None) -> Path:
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
        if revision is None:
            shutil.copy2(REPOSITORY_ROOT / relative_path, destination)
        else:
            source = subprocess.run(
                ["git", "show", f"{revision}:{relative_path}"],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            destination.write_text(source, encoding="utf-8")
    return root


def _create_unchanged_followup_repository(tmp_path: Path) -> tuple[Path, str, str]:
    """現行descriptorを比較元に持つ基準無変更の後続PR相当を作る。"""
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
    subprocess.run(["git", "commit", "-qm", "accepted baseline"], cwd=root, check=True)
    base_sha = _git_sha(root, "HEAD")
    marker = root / "unrelated.txt"
    marker.write_text("基準に触れない後続PR\n", encoding="utf-8")
    subprocess.run(["git", "add", marker.name], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "unrelated change"], cwd=root, check=True)
    return root, base_sha, _git_sha(root, "HEAD")


def test_unchanged_followup_pr_keeps_prior_acceptance_id_green(
    tmp_path: Path,
) -> None:
    """基準無変更の後続PRは過去PRの受理IDを再照合しない。"""
    root, base_sha, head_sha = _create_unchanged_followup_repository(tmp_path)
    descriptor = json.loads(
        (root / descriptor_checker.DESCRIPTOR_PATH).read_text(encoding="utf-8")
    )
    declaration = descriptor[freeze_checker.FREEZE_FIELD]
    repository, number = _latest_acceptance_parts()
    context = freeze_checker.PullRequestAcceptanceContext(
        base_sha=base_sha,
        head_sha=head_sha,
        repository=repository,
        number=number + 1,
    )
    # 末尾記録は過去PRの受理IDで、後続PRの受理IDとは異なる。
    assert freeze_checker.ACCEPTANCE_ID_PATTERN.fullmatch(
        declaration["history"][-1]["acceptanceId"]
    )
    assert declaration["history"][-1]["acceptanceId"] != context.acceptance_id

    freeze_checker.validate_repository_history(
        root,
        descriptor_checker.DESCRIPTOR_PATH,
        declaration,
        context,
    )


def _latest_acceptance_parts() -> tuple[str, int]:
    """現行descriptorの末尾受理記録から repository と PR 番号を導く。"""
    acceptance_id = _declaration()["history"][-1]["acceptanceId"]
    assert freeze_checker.ACCEPTANCE_ID_PATTERN.fullmatch(acceptance_id)
    repository, number = acceptance_id.rsplit("#", 1)
    return repository, int(number)


def _declaration_before_latest_record() -> dict[str, Any]:
    """現行宣言から末尾の受理記録1件を合成的に戻した比較元を作る。

    戻し方は検査器の再生(各記録の changes[].before を再生状態と照合する)の逆で、
    末尾記録の受理直前の状態になる。
    """
    current = copy.deepcopy(_declaration())
    latest = current["history"][-1]
    base = copy.deepcopy(current)
    base["history"] = base["history"][:-1]
    definition_id = current["scope"]["identityCriterionId"]
    for change in latest["changes"]:
        criterion_id = change["criterionId"]
        before = change["before"]
        if criterion_id == definition_id:
            assert before["present"], "定義の基準は末尾記録の前にも存在する"
            scope = copy.deepcopy(before["value"])
            base["scope"] = scope
            # 宣言のトップレベルは scope の期待値との一致を検査されるため揃える。
            expected = scope["engineExpectedValues"]
            base["schemaVersion"] = expected["schemaVersion"]
            base["acceptance"] = copy.deepcopy(expected["acceptance"])
            base["identitySpec"] = copy.deepcopy(expected["identitySpec"])
        elif before["present"]:
            base["criteria"][criterion_id] = copy.deepcopy(before["value"])
        else:
            base["criteria"].pop(criterion_id, None)
    return base


def _create_changed_baseline_repository(tmp_path: Path) -> tuple[Path, str, str]:
    """既存の凍結基準へ受理記録を1件追記したPR相当を作る。

    比較元は `origin/develop` から取らず、現行descriptorから末尾記録を戻して
    合成する。`origin/develop` との差を使うと、descriptor を変えるブランチでしか
    成立せず、マージ後は比較元と HEAD が同一になって追記が 0 件になる。
    """
    root = _copy_audited_sources(tmp_path)
    descriptor_path = root / descriptor_checker.DESCRIPTOR_PATH
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    base_descriptor = copy.deepcopy(_descriptor())
    base_descriptor[freeze_checker.FREEZE_FIELD] = _declaration_before_latest_record()
    descriptor_path.write_text(
        json.dumps(base_descriptor, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "freeze-test@example.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "freeze test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "accepted prior baseline"],
        cwd=root,
        check=True,
    )
    base_sha = _git_sha(root, "HEAD")
    shutil.copy2(REPOSITORY_ROOT / descriptor_checker.DESCRIPTOR_PATH, descriptor_path)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "new baseline accepted"], cwd=root, check=True
    )
    return root, base_sha, _git_sha(root, "HEAD")


def test_changed_pr_accepts_matching_acceptance_id(tmp_path: Path) -> None:
    """基準を動かしたPRは、PR番号と一致する受理IDを受理する。"""
    root, base_sha, head_sha = _create_changed_baseline_repository(tmp_path)
    base = freeze_checker.load_base_declaration(
        root, descriptor_checker.DESCRIPTOR_PATH, base_sha
    )
    assert base is not None
    # 追加記録があること(= 受理IDの照合の枝へ入ること)を前提として確かめる。
    assert len(_declaration()["history"]) - len(base["history"]) >= 1
    repository, number = _latest_acceptance_parts()
    freeze_checker.validate_repository_history(
        root,
        descriptor_checker.DESCRIPTOR_PATH,
        _declaration(),
        freeze_checker.PullRequestAcceptanceContext(
            base_sha=base_sha,
            head_sha=head_sha,
            repository=repository,
            number=number,
        ),
    )


def test_changed_pr_rejects_acceptance_id_from_another_pr(tmp_path: Path) -> None:
    """基準を動かしたPRでは追加記録を現在のPR番号と照合する。"""
    root, base_sha, head_sha = _create_changed_baseline_repository(tmp_path)
    repository, number = _latest_acceptance_parts()
    wrong_context = freeze_checker.PullRequestAcceptanceContext(
        base_sha=base_sha,
        head_sha=head_sha,
        repository=repository,
        number=number + 1,
    )

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="追加受理記録のacceptanceIdがPR eventと一致しない",
    ):
        freeze_checker.validate_repository_history(
            root,
            descriptor_checker.DESCRIPTOR_PATH,
            _declaration(),
            wrong_context,
        )


def test_unchanged_pr_rejects_spurious_acceptance_record() -> None:
    """基準無変更なのに受理記録を足す変更を拒否する。"""
    base = _declaration()
    current = copy.deepcopy(base)
    spurious = copy.deepcopy(current["history"][-1])
    spurious["acceptanceId"] = "masaki1025/pitchlog#82"
    spurious["priorIdentity"] = copy.deepcopy(current["history"][-1]["newIdentity"])
    spurious["approvedBy"] = "未承認(PR #82 のレビュー待ち)"
    spurious["fact"] = "未承認(PR #82 のレビュー待ち)。無変更の追加記録"
    current["history"].append(spurious)

    with pytest.raises(
        freeze_checker.FreezeBaselineError,
        match="受理記録のchangesが比較元から導出した変更前後と一致しない",
    ):
        freeze_checker.validate_append_only_transition(current, base)


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
