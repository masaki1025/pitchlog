"""凍結宣言が素材収集・戦略・比較基準を実際に選ぶことを検証する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))
try:
    checker = importlib.import_module("check_frozen_baselines")
    frozen_baselines = importlib.import_module("frozen_baselines")
finally:
    sys.path.pop(0)


def _read_ledger() -> dict[str, Any]:
    """production台帳をobjectとして読む。"""
    value = json.loads(
        (REPOSITORY_ROOT / "contracts/authz/frozen-baselines.json").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(value, dict)
    return value


def _copy_declared_materials(root: Path, ledger: dict[str, Any]) -> None:
    """宣言された素材だけを合成rootへコピーする。"""
    targets = ledger["declarations"]["oracle_input"]["frozen_targets"]
    for target in targets:
        path_text = str(target).partition("#")[0]
        destination = root / path_text
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPOSITORY_ROOT / path_text).read_bytes())


def _basis_ledger(basis_series: str) -> dict[str, Any]:
    """basis切替の判定に必要な最小合成台帳を作る。"""
    accepted = frozen_baselines.IdentityValue(
        kind="literal_commit_string",
        value="a" * 40,
    )
    rejected = frozen_baselines.IdentityValue(
        kind="literal_commit_string",
        value="b" * 40,
    )
    return {
        "declarations": {
            "candidate": {"basis_series": basis_series},
            "accepted": {"basis_series": "accepted"},
            "rejected": {"basis_series": "rejected"},
        },
        "history": [
            {
                "series": "accepted",
                "new_identity": {
                    "present": True,
                    "values": [{"kind": accepted.kind, "value": accepted.value}],
                },
            },
            {
                "series": "rejected",
                "new_identity": {
                    "present": True,
                    "values": [{"kind": rejected.kind, "value": rejected.value}],
                },
            },
        ],
    }


def _current_identities(
    candidate: frozenset[Any],
) -> dict[str, frozenset[Any]]:
    """candidateと2つのbasis系列の合成識別値を返す。"""
    identity_type = frozen_baselines.IdentityValue
    return {
        "candidate": candidate,
        "accepted": frozenset(
            {identity_type(kind="literal_commit_string", value="a" * 40)}
        ),
        "rejected": frozenset(
            {identity_type(kind="literal_commit_string", value="b" * 40)}
        ),
    }


def _synthetic_dispatch_ledger(
    first_key: tuple[str, str],
    second_key: tuple[str, str],
) -> dict[str, Any]:
    """2系列が2戦略を使うdispatch検査用の合成宣言を作る。"""
    return {
        "declarations": {
            "first": {
                "frozen_targets": ["tests/material.json#/value"],
                "identity": first_key[0],
                "granularity": first_key[1],
                "basis_series": "first",
            },
            "second": {
                "frozen_targets": ["tests/material.json#/value"],
                "identity": second_key[0],
                "granularity": second_key[1],
                "basis_series": "second",
            },
        }
    }


def _tagged_strategy(
    result_kind: str,
    final_character: str,
) -> Callable[[Mapping[str, bytes], Sequence[str]], tuple[Any, ...]]:
    """JSON pointer戦略の結果へ合成registry用の差を付ける。"""

    def strategy(
        materials: Mapping[str, bytes],
        targets: Sequence[str],
    ) -> tuple[Any, ...]:
        values = frozen_baselines.literal_commit_string_at_json_pointer(
            materials, targets
        )
        return tuple(
            frozen_baselines.IdentityValue(
                kind=result_kind,
                value=value.value[:-1] + final_character,
            )
            for value in values
        )

    return strategy


def test_frozen_targets_select_the_material_population(tmp_path: Path) -> None:
    """対象を外すと台帳はredになり、その素材の改ざんは戦略へ届かない。"""
    ledger = _read_ledger()
    removed_target = (
        "contracts/authz/boundary-proposal.json#/oracle_context/oracle_commit"
    )
    mutated = copy.deepcopy(ledger)
    mutated["declarations"]["oracle_input"]["frozen_targets"].remove(removed_target)
    with pytest.raises(checker.FrozenBaselineCheckError) as caught:
        checker._check_ledger_structure(REPOSITORY_ROOT, mutated)
    assert str(caught.value).startswith(
        "schema: $.declarations.oracle_input.frozen_targets: const不一致:"
    )

    root = tmp_path / "repository"
    _copy_declared_materials(root, ledger)
    full_before = checker._derive_current_identities(root, ledger)
    removed_before = checker._derive_current_identities(root, mutated)

    removed_path = root / removed_target.partition("#")[0]
    removed_document = json.loads(removed_path.read_text(encoding="utf-8"))
    removed_document["oracle_context"]["oracle_commit"] = "0" * 40
    removed_path.write_text(
        json.dumps(removed_document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    assert checker._derive_current_identities(root, mutated) == removed_before
    assert checker._derive_current_identities(root, ledger) != full_before


def test_identity_switch_selects_a_different_injected_strategy(tmp_path: Path) -> None:
    """identity宣言だけの交換で固定registryの導出結果も交換される。"""
    root = tmp_path / "repository"
    material = root / "tests/material.json"
    material.parent.mkdir(parents=True)
    material.write_text(json.dumps({"value": "a" * 40}), encoding="utf-8")
    first_key = ("literal_commit_string", "json_pointer_value")
    second_key = ("alternate_commit_string", "json_pointer_value")
    strategy_registry = {
        first_key: _tagged_strategy("literal_commit_string", "a"),
        second_key: _tagged_strategy("alternate_commit_string", "a"),
    }
    baseline_ledger = _synthetic_dispatch_ledger(first_key, second_key)
    switched_ledger = copy.deepcopy(baseline_ledger)
    switched_ledger["declarations"]["first"]["identity"] = second_key[0]
    switched_ledger["declarations"]["second"]["identity"] = first_key[0]

    baseline = checker._derive_current_identities(
        root, baseline_ledger, strategy_registry
    )
    switched = checker._derive_current_identities(
        root, switched_ledger, strategy_registry
    )

    assert baseline["first"] != baseline["second"]
    assert switched["first"] == baseline["second"]
    assert switched["second"] == baseline["first"]
    checker._check_basis_correspondence(
        _basis_ledger("accepted"),
        _current_identities(baseline["first"]),
    )
    with pytest.raises(
        checker.FrozenBaselineCheckError,
        match="declarations.candidate の導出値がbasis_series=acceptedの履歴末尾と不一致",
    ):
        checker._check_basis_correspondence(
            _basis_ledger("accepted"),
            _current_identities(switched["first"]),
        )
    assert set(frozen_baselines.COMPARISON_STRATEGIES) == {
        ("literal_commit_string", "json_pointer_value")
    }


def test_granularity_switch_reverses_the_correspondence_result(
    tmp_path: Path,
) -> None:
    """granularity宣言だけの交換で固定registryの導出結果も交換される。"""
    root = tmp_path / "repository"
    material = root / "tests/material.json"
    material.parent.mkdir(parents=True)
    material.write_text(json.dumps({"value": "a" * 40}), encoding="utf-8")
    first_key = ("literal_commit_string", "json_pointer_value")
    second_key = ("literal_commit_string", "reversed_pointer_value")
    strategy_registry = {
        first_key: _tagged_strategy("literal_commit_string", "a"),
        second_key: _tagged_strategy("literal_commit_string", "b"),
    }
    baseline_ledger = _synthetic_dispatch_ledger(first_key, second_key)
    switched_ledger = copy.deepcopy(baseline_ledger)
    switched_ledger["declarations"]["first"]["granularity"] = second_key[1]
    switched_ledger["declarations"]["second"]["granularity"] = first_key[1]

    baseline = checker._derive_current_identities(
        root, baseline_ledger, strategy_registry
    )
    switched = checker._derive_current_identities(
        root, switched_ledger, strategy_registry
    )

    assert baseline["first"] != baseline["second"]
    assert switched["first"] == baseline["second"]
    assert switched["second"] == baseline["first"]
    checker._check_basis_correspondence(
        _basis_ledger("accepted"),
        _current_identities(baseline["first"]),
    )
    with pytest.raises(
        checker.FrozenBaselineCheckError,
        match="declarations.candidate の導出値がbasis_series=acceptedの履歴末尾と不一致",
    ):
        checker._check_basis_correspondence(
            _basis_ledger("accepted"),
            _current_identities(switched["first"]),
        )


def test_basis_series_switch_implicitly_rebases_the_expected_identity() -> None:
    """素材導出値を変えずbasisだけを替えると期待値が替わりredになる。"""
    candidate = frozenset(
        {
            frozen_baselines.IdentityValue(
                kind="literal_commit_string",
                value="a" * 40,
            )
        }
    )
    identities = _current_identities(candidate)
    checker._check_basis_correspondence(_basis_ledger("accepted"), identities)

    with pytest.raises(
        checker.FrozenBaselineCheckError,
        match="declarations.candidate の導出値がbasis_series=rejectedの履歴末尾と不一致",
    ):
        checker._check_basis_correspondence(_basis_ledger("rejected"), identities)


def test_repository_scan_has_the_declared_terminal_population() -> None:
    """実走査の幅別出現数・組数とallow-list分類を終端値で固定する。"""
    scan = checker.check_repository_source_scan(REPOSITORY_ROOT)
    entries = checker._load_worktree_scan_allowlist(REPOSITORY_ROOT)

    assert scan.occurrences_40 == 14
    assert scan.occurrences_64 == 1
    assert len({pair for pair in scan.pairs if len(pair.value) == 40}) == 10
    assert len({pair for pair in scan.pairs if len(pair.value) == 64}) == 1
    assert len(entries) == 11
    assert sum(entry.pending_removal for entry in entries) == 4
    assert sum(not entry.pending_removal for entry in entries) == 7


def test_pr197_single_anchor_requires_exact_event_and_public_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1件限定の追加でもPR識別と公開委任証拠の失敗を通さない。"""
    from scripts import check_tenant_boundary_bypass, core_guard, frozen_history

    monkeypatch.setitem(
        sys.modules, "check_tenant_boundary_bypass", check_tenant_boundary_bypass,
    )
    monkeypatch.setitem(sys.modules, "core_guard", core_guard)
    monkeypatch.setitem(sys.modules, "frozen_history", frozen_history)
    anchor = frozen_history.PR197_PIN_ORIGIN_COMMIT
    key = checker._ScanKey("scripts/frozen_history.py", anchor)
    entries = checker._load_worktree_scan_allowlist(REPOSITORY_ROOT)
    formal_base = check_tenant_boundary_bypass._pr197_fixed_expectations(
        REPOSITORY_ROOT,
    )["formal_base_revision"]
    event = checker._PullRequestEvent(
        "develop", formal_base, "b" * 40, core_guard.DELEGATION_REPOSITORY, 197,
    )
    guarded_event = core_guard.PullRequestEvent(
        event.base_sha, event.head_sha, "proof", event.number,
        event.repository, event.repository, "feature/mvp-stats-native-foundation",
    )
    monkeypatch.setattr(core_guard, "load_pull_request_event", lambda: guarded_event)
    monkeypatch.setattr(
        checker, "_git_file_bytes", lambda root, sha, path: (root / path).read_bytes(),
    )
    verified: list[str] = []
    monkeypatch.setattr(
        core_guard, "verify_delegated_confirmation",
        lambda root, current: verified.append(current.head_sha),
    )
    assert checker._verify_pr197_pin_scan_exception(
        REPOSITORY_ROOT, event, event.base_sha, entries, {key},
    ) == key
    assert verified == [event.head_sha]

    for wrong in (
        replace(event, number=198),
        replace(event, repository="other/pitchlog"),
        replace(event, base_ref="main"),
        replace(event, base_sha="c" * 40),
        replace(event, head_sha="c" * 40),
    ):
        with pytest.raises(checker.FrozenBaselineCheckError):
            checker._verify_pr197_pin_scan_exception(
                REPOSITORY_ROOT, wrong, wrong.base_sha, entries, {key},
            )
    monkeypatch.setattr(
        core_guard, "load_pull_request_event",
        lambda: replace(guarded_event, head_branch="feature/other"),
    )
    with pytest.raises(checker.FrozenBaselineCheckError, match="branch/head"):
        checker._verify_pr197_pin_scan_exception(
            REPOSITORY_ROOT, event, event.base_sha, entries, {key},
        )
    monkeypatch.setattr(core_guard, "load_pull_request_event", lambda: guarded_event)
    monkeypatch.setattr(
        core_guard, "verify_delegated_confirmation",
        lambda root, current: (_ for _ in ()).throw(core_guard.GuardError("proof missing")),
    )
    with pytest.raises(checker.FrozenBaselineCheckError, match="公開委任証拠"):
        checker._verify_pr197_pin_scan_exception(
            REPOSITORY_ROOT, event, event.base_sha, entries, {key},
        )
    with pytest.raises(checker.FrozenBaselineCheckError, match="anchor以外"):
        checker._verify_pr197_pin_scan_exception(
            REPOSITORY_ROOT, event, event.base_sha, entries,
            {checker._ScanKey("tests/unknown.py", anchor)},
        )


def test_pr197_anchor_inherited_on_develop_push_but_new_non_pr_addition_is_red(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登録後の通常継承と、新規登録のPR文脈を分離する。"""
    from scripts import frozen_history

    entries = checker._load_worktree_scan_allowlist(REPOSITORY_ROOT)
    anchor = checker._ScanKey(
        "scripts/frozen_history.py", frozen_history.PR197_PIN_ORIGIN_COMMIT,
    )
    assert checker.check_repository_source_scan(REPOSITORY_ROOT).pairs >= {anchor}
    checker._check_scan_allowlist_transition(
        base_ledger_present=True, base_entries=entries, head_entries=entries,
    )
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    assert checker._ci_requests_acceptance() is False
    before = tuple(entry for entry in entries if entry.key != anchor)
    with pytest.raises(checker.FrozenBaselineCheckError, match="エントリ追加は禁止"):
        checker._check_scan_allowlist_transition(
            base_ledger_present=True, base_entries=before, head_entries=entries,
        )
