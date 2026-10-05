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
        range(1, len(validated.application_steps) + 1)
    )
    assert tuple(step.sequence for step in validated.unapplication_steps) == tuple(
        range(1, len(validated.unapplication_steps) + 1)
    )
    assert tuple(
        step.reverses_application_step_id for step in validated.unapplication_steps
    ) == tuple(step.step_id for step in reversed(validated.application_steps))
    assert validated.preserved_role_ids == ("pitchlog_owner",)
    assert set(validated.operation_kinds).isdisjoint(
        operation.operation_kind for operation in PROBE_SPEC.operation_handlers
    )


def test_extension_and_new_schema_asset_is_green(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """複製した資産に新スキーマと拡張を加えて第2手順で受理する。"""
    steps_asset = copy.deepcopy(application_asset)
    elements = copy.deepcopy(ddl_elements)
    schemas = elements["schemas"]
    assert isinstance(schemas, list)
    new_schema = copy.deepcopy(schemas[1])
    new_schema["schema_id"] = "authn_crypto"
    new_schema["schema_name"] = "authn_crypto"
    schemas.append(new_schema)
    elements["extensions"] = [
        {
            "extension_id": "pgcrypto",
            "extension_name": "pgcrypto",
            "schema_name": "authn_crypto",
        }
    ]
    groups = _application_steps(steps_asset)[1]["element_groups"]
    assert isinstance(groups, list)
    groups.append("extensions")

    validated = validate_product_application_steps(steps_asset, elements, PRODUCT_SPEC)
    assert validated.application_steps[1].element_groups == (
        "databases",
        "schemas",
        "extensions",
    )


def test_migration_regular_function_uses_final_function_step(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """通常関数の要素群を migration トリガと同じ最終手順で受理する。"""
    steps_asset = copy.deepcopy(application_asset)
    elements = copy.deepcopy(ddl_elements)
    functions = elements["functions"]
    assert isinstance(functions, list)
    ordinary = copy.deepcopy(functions[0])
    ordinary["function_id"] = "FUNCTION:public:step4_ordinary()"
    ordinary["function_name"] = "step4_ordinary"
    ordinary["function_kind"] = "migration_function"
    functions.append(ordinary)
    groups = _application_steps(steps_asset)[-1]["element_groups"]
    assert isinstance(groups, list)
    groups.append("functions:migration_function")
    validated = validate_product_application_steps(steps_asset, elements, PRODUCT_SPEC)
    assert validated.application_steps[-1].element_groups[-1] == (
        "functions:migration_function"
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("missing_group", "全要素"),
        ("wrong_schema", "schema_name"),
        ("wrong_id", "extension_id"),
        ("duplicate", "重複"),
    ],
)
def test_invalid_extension_declaration_is_red(
    application_asset: dict[str, object],
    ddl_elements: dict[str, object],
    mutation: str,
    match: str,
) -> None:
    """拡張群の手順漏れと不正な宣言を拒否する。"""
    steps_asset = copy.deepcopy(application_asset)
    elements = copy.deepcopy(ddl_elements)
    extension = {
        "extension_id": "pgcrypto",
        "extension_name": "pgcrypto",
        "schema_name": "public",
    }
    elements["extensions"] = [extension]
    if mutation != "missing_group":
        groups = _application_steps(steps_asset)[1]["element_groups"]
        assert isinstance(groups, list)
        groups.append("extensions")
    if mutation == "wrong_schema":
        extension["schema_name"] = "unlisted"
    elif mutation == "wrong_id":
        extension["extension_id"] = "other"
    elif mutation == "duplicate":
        elements["extensions"].append(copy.deepcopy(extension))
    _assert_rejected(steps_asset, elements, match)


def test_definer_group_follows_helper_group(
    application_asset: dict[str, object], ddl_elements: dict[str, object]
) -> None:
    """definer関数を補助関数の後に宣言した資産だけを受理する。"""
    steps_asset = copy.deepcopy(application_asset)
    elements = copy.deepcopy(ddl_elements)
    functions = elements["functions"]
    assert isinstance(functions, list)
    definer = copy.deepcopy(functions[-1])
    definer.update(
        function_id="FUNCTION:public:test_definer(text)",
        schema_name="public",
        function_name="test_definer",
        identity_args="text",
        function_kind="definer",
        owner_role_id="pitchlog_management_fn_owner",
    )
    functions.append(definer)
    groups = _application_steps(steps_asset)[2]["element_groups"]
    assert isinstance(groups, list)
    groups.append("functions:definer")
    validated = validate_product_application_steps(steps_asset, elements, PRODUCT_SPEC)
    assert validated.application_steps[2].element_groups == (
        "functions:rls_helper",
        "functions:definer",
    )
    groups.reverse()
    _assert_rejected(steps_asset, elements, "固定順序")


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("schema_name", "unlisted", "schema_name"),
        ("owner_role_id", "unlisted", "owner_role_id"),
        ("security_mode", "invoker", "security_mode"),
        ("acl_expectations", None, "ACL付与先"),
    ],
)
def test_definer_declaration_requires_schema_owner_and_acl(
    application_asset: dict[str, object],
    ddl_elements: dict[str, object],
    field: str,
    value: object,
    match: str,
) -> None:
    """definerのスキーマ・所有者・付与先の宣言不備を拒否する。"""
    steps_asset = copy.deepcopy(application_asset)
    elements = copy.deepcopy(ddl_elements)
    functions = elements["functions"]
    assert isinstance(functions, list)
    definer = copy.deepcopy(functions[-1])
    definer["function_id"] = "FUNCTION:public:test_definer(text)"
    definer["function_name"] = "test_definer"
    definer["identity_args"] = "text"
    definer["function_kind"] = "definer"
    definer[field] = value
    functions.append(definer)
    groups = _application_steps(steps_asset)[2]["element_groups"]
    assert isinstance(groups, list)
    groups.append("functions:definer")
    _assert_rejected(steps_asset, elements, match)


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
