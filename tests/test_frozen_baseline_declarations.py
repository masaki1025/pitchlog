"""凍結宣言が素材収集・戦略・比較基準を実際に選ぶことを検証する。"""

from __future__ import annotations

import copy
import importlib
import json
import sys
from collections.abc import Mapping, Sequence
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


def _synthetic_declaration(identity: str, granularity: str) -> dict[str, Any]:
    """戦略dispatchだけに必要な単一系列の合成宣言を作る。"""
    return {
        "declarations": {
            "candidate": {
                "frozen_targets": ["tests/material.json#/value"],
                "identity": identity,
                "granularity": granularity,
                "basis_series": "candidate",
            }
        }
    }


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
    """identity切替で合成registryの比較方法が変わり判定がredになる。"""
    root = tmp_path / "repository"
    material = root / "tests/material.json"
    material.parent.mkdir(parents=True)
    material.write_text(json.dumps({"value": "a" * 40}), encoding="utf-8")

    baseline = checker._derive_current_identities(
        root,
        _synthetic_declaration("literal_commit_string", "json_pointer_value"),
        frozen_baselines.COMPARISON_STRATEGIES,
    )["candidate"]

    def alternate_identity(
        materials: Mapping[str, bytes],
        targets: Sequence[str],
    ) -> tuple[Any, ...]:
        values = frozen_baselines.literal_commit_string_at_json_pointer(
            materials, targets
        )
        return tuple(
            frozen_baselines.IdentityValue(
                kind="alternate_commit_string",
                value=value.value,
            )
            for value in values
        )

    switched = checker._derive_current_identities(
        root,
        _synthetic_declaration("alternate_commit_string", "json_pointer_value"),
        {("alternate_commit_string", "json_pointer_value"): alternate_identity},
    )["candidate"]
    checker._check_basis_correspondence(
        _basis_ledger("accepted"),
        _current_identities(baseline),
    )
    with pytest.raises(
        checker.FrozenBaselineCheckError,
        match="declarations.candidate の導出値がbasis_series=acceptedの履歴末尾と不一致",
    ):
        checker._check_basis_correspondence(
            _basis_ledger("accepted"),
            _current_identities(switched),
        )
    assert switched != baseline
    assert set(frozen_baselines.COMPARISON_STRATEGIES) == {
        ("literal_commit_string", "json_pointer_value")
    }


def test_granularity_switch_reverses_the_correspondence_result(
    tmp_path: Path,
) -> None:
    """granularity切替で同じ素材の判定がgreenからredへ反転する。"""
    root = tmp_path / "repository"
    material = root / "tests/material.json"
    material.parent.mkdir(parents=True)
    material.write_text(json.dumps({"value": "a" * 40}), encoding="utf-8")
    baseline = checker._derive_current_identities(
        root,
        _synthetic_declaration("literal_commit_string", "json_pointer_value"),
        frozen_baselines.COMPARISON_STRATEGIES,
    )["candidate"]

    def changed_granularity(
        materials: Mapping[str, bytes],
        targets: Sequence[str],
    ) -> tuple[Any, ...]:
        values = frozen_baselines.literal_commit_string_at_json_pointer(
            materials, targets
        )
        return tuple(
            frozen_baselines.IdentityValue(
                kind=value.kind,
                value=value.value[:-1] + "c",
            )
            for value in values
        )

    switched = checker._derive_current_identities(
        root,
        _synthetic_declaration("literal_commit_string", "reversed_pointer_value"),
        {
            ("literal_commit_string", "reversed_pointer_value"): (
                changed_granularity
            )
        },
    )["candidate"]
    checker._check_basis_correspondence(
        _basis_ledger("accepted"),
        _current_identities(baseline),
    )
    with pytest.raises(
        checker.FrozenBaselineCheckError,
        match="declarations.candidate の導出値がbasis_series=acceptedの履歴末尾と不一致",
    ):
        checker._check_basis_correspondence(
            _basis_ledger("accepted"),
            _current_identities(switched),
        )
    assert switched != baseline


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

    assert scan.occurrences_40 == 13
    assert scan.occurrences_64 == 1
    assert len({pair for pair in scan.pairs if len(pair.value) == 40}) == 9
    assert len({pair for pair in scan.pairs if len(pair.value) == 64}) == 1
    assert len(entries) == 10
    assert sum(entry.pending_removal for entry in entries) == 4
    assert sum(not entry.pending_removal for entry in entries) == 6
