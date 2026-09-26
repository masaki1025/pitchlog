"""製品認可の適用・取り外し手順資産を静的に検査する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pitchlog.authz.asset_spec import (
    PROBE_SPEC,
    PRODUCT_SPEC,
    AuthzApplicationStepsError,
    load_product_application_steps,
    validate_product_application_steps,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _read_json_object(path: Path) -> dict[str, object]:
    """試験対象の JSON object を読む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


@pytest.fixture
def application_asset() -> dict[str, object]:
    """変異ごとに独立した適用手順資産を返す。"""
    assert PRODUCT_SPEC.application_steps_path is not None
    return _read_json_object(_REPOSITORY_ROOT / PRODUCT_SPEC.application_steps_path)


@pytest.fixture(scope="module")
def ddl_elements() -> dict[str, object]:
    """被覆の母集合になる staged DDL 要素資産を返す。"""
    return _read_json_object(_REPOSITORY_ROOT / PRODUCT_SPEC.ddl_elements_path)


def _application_steps(asset: dict[str, object]) -> list[dict[str, object]]:
    """変異対象の適用手順配列を型付きで取得する。"""
    steps = asset["application_steps"]
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return [step for step in steps if isinstance(step, dict)]


def _operation_kinds(asset: dict[str, object]) -> list[str]:
    """変異対象の操作種別配列を型付きで取得する。"""
    operation_kinds = asset["operation_kinds"]
    assert isinstance(operation_kinds, list)
    assert all(isinstance(item, str) for item in operation_kinds)
    return [item for item in operation_kinds if isinstance(item, str)]


def _assert_rejected(
    asset: dict[str, object], ddl_elements: dict[str, object], match: str
) -> None:
    """変異した資産が静的検査で拒否されることを表明する。"""
    with pytest.raises(AuthzApplicationStepsError, match=match):
        validate_product_application_steps(asset, ddl_elements, PRODUCT_SPEC)


def test_product_application_steps_asset_is_green() -> None:
    """正規資産が 7 手順・単一 transaction・逆順の契約を満たす。"""
    validated = load_product_application_steps(_REPOSITORY_ROOT, PRODUCT_SPEC)

    assert PRODUCT_SPEC.operation_handlers == ()
    assert PRODUCT_SPEC.application_steps_path == Path(
        "contracts/authz/product/application-steps.json"
    )
    assert validated.transaction == "single"
    assert tuple(step.sequence for step in validated.application_steps) == tuple(
        range(1, 8)
    )
    assert tuple(step.sequence for step in validated.unapplication_steps) == tuple(
        range(1, 8)
    )
    assert tuple(
        step.reverses_application_step_id for step in validated.unapplication_steps
    ) == tuple(step.step_id for step in reversed(validated.application_steps))
    assert validated.preserved_role_ids == ("pitchlog_owner",)
    assert set(validated.operation_kinds).isdisjoint(
        operation.operation_kind for operation in PROBE_SPEC.operation_handlers
    )


def test_swapping_helper_functions_and_policies_is_red(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """補助関数より先にポリシーを置く変異を拒否する。"""
    mutated = copy.deepcopy(application_asset)
    steps = _application_steps(mutated)
    steps[2]["element_groups"], steps[4]["element_groups"] = (
        steps[4]["element_groups"],
        steps[2]["element_groups"],
    )

    _assert_rejected(mutated, ddl_elements, "固定順序")


def test_omitting_an_element_group_is_red(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """PRODUCT_SPEC の要素群を割り当てから 1 つ外す変異を拒否する。"""
    mutated = copy.deepcopy(application_asset)
    steps = _application_steps(mutated)
    steps[1]["element_groups"] = ["databases"]

    _assert_rejected(mutated, ddl_elements, "全要素")


def test_assigning_an_element_group_to_two_steps_is_red(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """同じ要素群を 2 手順へ重複して割り当てる変異を拒否する。"""
    mutated = copy.deepcopy(application_asset)
    steps = _application_steps(mutated)
    groups = steps[3]["element_groups"]
    assert isinstance(groups, list)
    groups.append("roles")

    _assert_rejected(mutated, ddl_elements, "重複")


def test_omitting_predicates_is_red(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """ポリシー生成の入力 predicates を割り当てから外す変異を拒否する。"""
    mutated = copy.deepcopy(application_asset)
    steps = _application_steps(mutated)
    steps[4]["element_groups"] = ["policies"]

    _assert_rejected(mutated, ddl_elements, "全要素")


def test_mixing_a_probe_operation_kind_is_red(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """製品の閉集合へ probe の操作種別を混ぜる変異を拒否する。"""
    mutated = copy.deepcopy(application_asset)
    steps = _application_steps(mutated)
    operation_kinds = _operation_kinds(mutated)
    probe_operation = PROBE_SPEC.operation_handlers[0].operation_kind
    steps[0]["operation_kind"] = probe_operation
    operation_kinds[0] = probe_operation
    mutated["operation_kinds"] = operation_kinds

    _assert_rejected(mutated, ddl_elements, "交差")


def test_per_step_transaction_is_red(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """手順ごとの transaction に弱める変異を拒否する。"""
    mutated = copy.deepcopy(application_asset)
    mutated["transaction"] = "per_step"

    _assert_rejected(mutated, ddl_elements, "single")
