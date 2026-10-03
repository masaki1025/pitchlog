"""凍結基準の負例テスト母集団を pytest collection から検証する。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FROZEN_NEGATIVE_DIRECTORY = Path("tests/frozen_negatives")
FROZEN_NEGATIVE_MARKER = "frozen_negative"

EXPECTED_FROZEN_NEGATIVE_NODE_IDS: Final[frozenset[str]] = frozenset(
    {
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_unknown_top_level_key_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_missing_top_level_key_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_unknown_change_aspect_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_identity_without_registered_strategy_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_removed_movement_trigger_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_reduced_universal_lower_bound_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_additional_target_for_unknown_trigger_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_missing_self_change_rule_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_changed_code_asset_digest_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_before_locator_with_missing_symbol_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_missing_placement_change_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_absent_prior_identity_with_values_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_new_identity_different_from_derived_value_is_red",
        "tests/frozen_negatives/test_frozen_baseline_ledger.py::test_impossible_approval_date_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_non_develop_event_with_broken_environment_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_unresolvable_sha_and_non_merge_head_are_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_first_parent_different_from_event_base_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_second_parent_different_from_event_head_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_rewritten_existing_history_record_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_deleted_existing_history_record_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_same_length_history_replacement_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_second_bootstrap_after_missing_base_ledger_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_missing_inputs_and_dangling_identity_are_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_empty_changes_with_unchanged_identity_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_noop_history_change_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_reordered_history_change_is_red",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_empty_changes_with_moved_identity_is_green",
        "tests/frozen_negatives/test_frozen_baseline_acceptance.py::test_empty_changes_with_reordered_placement_is_green",
        "tests/frozen_negatives/test_frozen_baseline_scan.py::test_added_allowlist_entry_is_red",
        "tests/frozen_negatives/test_frozen_baseline_scan.py::test_changed_allowlist_value_is_red",
        "tests/frozen_negatives/test_frozen_baseline_scan.py::test_changed_allowlist_path_is_red",
        "tests/frozen_negatives/test_frozen_baseline_scan.py::test_permanent_entry_cannot_become_pending_is_red",
        "tests/frozen_negatives/test_frozen_baseline_scan.py::test_pending_entry_cannot_become_permanent_is_red",
        "tests/frozen_negatives/test_frozen_baseline_scan.py::test_embedded_docstring_and_fstring_values_are_red",
        "tests/frozen_negatives/test_frozen_baseline_ci_dispatch.py::test_ci_dispatch_missing_and_unknown_event_names_are_red",
    }
)


@dataclass(frozen=True)
class _FrozenNegativeInventory:
    """collection で得た負例の node ID と marker 欠落を保持する。"""

    node_ids: frozenset[str]
    unmarked_node_ids: frozenset[str]


class _FrozenNegativeCollector:
    """pytest collection の完了時に全 item の属性を採取する。"""

    def __init__(self) -> None:
        """collection 未完了の状態で初期化する。"""
        self.inventory: _FrozenNegativeInventory | None = None

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """選択済みの全 item から node ID と marker 欠落を採取する。"""
        node_ids = frozenset(item.nodeid for item in session.items)
        unmarked_node_ids = frozenset(
            item.nodeid
            for item in session.items
            if item.get_closest_marker(FROZEN_NEGATIVE_MARKER) is None
        )
        self.inventory = _FrozenNegativeInventory(
            node_ids=node_ids,
            unmarked_node_ids=unmarked_node_ids,
        )


def _collect_frozen_negative_inventory(root: Path) -> _FrozenNegativeInventory:
    """指定 root の負例ディレクトリを pytest collection して母集団を返す。"""
    collector = _FrozenNegativeCollector()
    exit_code = pytest.main(
        [
            str(root / FROZEN_NEGATIVE_DIRECTORY),
            "--collect-only",
            "--quiet",
            "--rootdir",
            str(root),
            "--import-mode=importlib",
            "-o",
            "markers=frozen_negative: 凍結基準の検査が red になることを固定する負例",
            "-p",
            "no:cacheprovider",
        ],
        plugins=[collector],
    )

    assert exit_code in {pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED}
    assert collector.inventory is not None
    return collector.inventory


def _inventory_failures(
    inventory: _FrozenNegativeInventory,
    expected_node_ids: frozenset[str],
) -> tuple[str, ...]:
    """期待集合との双方向差分と marker 欠落をエラー文へ変換する。"""
    failures: list[str] = []
    if inventory.node_ids != expected_node_ids:
        missing = sorted(expected_node_ids - inventory.node_ids)
        unexpected = sorted(inventory.node_ids - expected_node_ids)
        failures.append(
            f"node ID の exact-set が不一致: 不足={missing!r}; 過剰={unexpected!r}"
        )
    if inventory.unmarked_node_ids:
        failures.append(
            "frozen_negative marker が無い node ID: "
            f"{sorted(inventory.unmarked_node_ids)!r}"
        )
    return tuple(failures)


def _assert_inventory_matches(
    inventory: _FrozenNegativeInventory,
    expected_node_ids: frozenset[str],
) -> None:
    """node ID の exact-set 一致と全件の marker 保有を表明する。"""
    failures = _inventory_failures(inventory, expected_node_ids)
    if failures:
        raise AssertionError("\n".join(failures))


def _write_synthetic_test(root: Path, filename: str, source: str) -> None:
    """合成 root の負例ディレクトリへテストファイルを書く。"""
    directory = root / FROZEN_NEGATIVE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(source, encoding="utf-8")


def test_repository_inventory_matches_expected_set_of_thirty_five() -> None:
    """期待集合が明示した35件で実母集団とも一致する。"""
    assert len(EXPECTED_FROZEN_NEGATIVE_NODE_IDS) == 35

    inventory = _collect_frozen_negative_inventory(REPOSITORY_ROOT)

    _assert_inventory_matches(inventory, EXPECTED_FROZEN_NEGATIVE_NODE_IDS)


def test_added_marked_test_is_collected_and_makes_empty_expectation_red(
    tmp_path: Path,
) -> None:
    """marker 付き負例を足すと母集団へ現れ exact-set 不一致になる。"""
    node_id = "tests/frozen_negatives/test_added.py::test_added"
    _write_synthetic_test(
        tmp_path,
        "test_added.py",
        """import pytest

@pytest.mark.frozen_negative
def test_added() -> None:
    pass
""",
    )

    inventory = _collect_frozen_negative_inventory(tmp_path)

    assert inventory.node_ids == frozenset({node_id})
    assert inventory.unmarked_node_ids == frozenset()
    with pytest.raises(AssertionError) as error:
        _assert_inventory_matches(inventory, frozenset())
    assert str(error.value) == (
        "node ID の exact-set が不一致: 不足=[]; "
        f"過剰=[{node_id!r}]"
    )


def test_added_unmarked_test_is_collected_and_fails_both_checks(tmp_path: Path) -> None:
    """marker 無し負例も母集団へ現れ集合照合と必須属性検査がともに落ちる。"""
    node_id = "tests/frozen_negatives/test_unmarked.py::test_unmarked"
    _write_synthetic_test(
        tmp_path,
        "test_unmarked.py",
        """def test_unmarked() -> None:
    pass
""",
    )

    inventory = _collect_frozen_negative_inventory(tmp_path)

    assert inventory.node_ids == frozenset({node_id})
    assert inventory.unmarked_node_ids == frozenset({node_id})
    with pytest.raises(AssertionError) as error:
        _assert_inventory_matches(inventory, frozenset())
    assert str(error.value) == (
        "node ID の exact-set が不一致: 不足=[]; "
        f"過剰=[{node_id!r}]\n"
        f"frozen_negative marker が無い node ID: [{node_id!r}]"
    )


def test_expected_but_missing_test_makes_inventory_red(tmp_path: Path) -> None:
    """期待集合だけにある node ID は不足として検出される。"""
    missing_node_id = "tests/frozen_negatives/test_missing.py::test_missing"
    (tmp_path / FROZEN_NEGATIVE_DIRECTORY).mkdir(parents=True)

    inventory = _collect_frozen_negative_inventory(tmp_path)

    assert inventory.node_ids == frozenset()
    with pytest.raises(AssertionError) as error:
        _assert_inventory_matches(inventory, frozenset({missing_node_id}))
    assert str(error.value) == (
        "node ID の exact-set が不一致: "
        f"不足=[{missing_node_id!r}]; 過剰=[]"
    )


def test_node_id_prefix_is_not_treated_as_an_exact_match(tmp_path: Path) -> None:
    """接頭辞だけが同じ別 node ID を期待対象として取り違えない。"""
    expected_node_id = "tests/frozen_negatives/test_prefix.py::test_case"
    actual_node_id = "tests/frozen_negatives/test_prefix.py::test_case_extended"
    _write_synthetic_test(
        tmp_path,
        "test_prefix.py",
        """import pytest

@pytest.mark.frozen_negative
def test_case_extended() -> None:
    pass
""",
    )

    inventory = _collect_frozen_negative_inventory(tmp_path)

    assert inventory.node_ids == frozenset({actual_node_id})
    with pytest.raises(AssertionError) as error:
        _assert_inventory_matches(inventory, frozenset({expected_node_id}))
    assert str(error.value) == (
        "node ID の exact-set が不一致: "
        f"不足=[{expected_node_id!r}]; 過剰=[{actual_node_id!r}]"
    )
