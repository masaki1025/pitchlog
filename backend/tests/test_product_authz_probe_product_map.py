"""probe ↔ 製品の原子要素写像を双方向 exact-set で検査する。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from product_authz_probe_product_map import (
    ProbeProductMapError,
    validate_probe_product_map,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MAP_PATH = _REPOSITORY_ROOT / "contracts/authz/product/probe-product-map.json"
_PROBE_PATH = _REPOSITORY_ROOT / "contracts/authz/ddl-elements.json"
_PRODUCT_PATH = _REPOSITORY_ROOT / "contracts/authz/product/ddl-elements.staged.json"


def _load_object(path: Path) -> dict[str, object]:
    """JSON object を読み込む。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _documents() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """写像・probe・staged 製品資産を返す。"""
    return (
        _load_object(_MAP_PATH),
        _load_object(_PROBE_PATH),
        _load_object(_PRODUCT_PATH),
    )


def _rows(document: dict[str, object], key: str) -> list[object]:
    """変異対象の配列を返す。"""
    value = document[key]
    assert isinstance(value, list)
    return value


def _row_by_value(
    rows: list[object],
    *,
    key: str,
    value: str,
) -> dict[str, object]:
    """指定した値を持つ一意な object 行を返す。"""
    matches = tuple(
        row for row in rows if isinstance(row, dict) and row.get(key) == value
    )
    assert len(matches) == 1
    return matches[0]


def test_probe_product_map_is_bidirectionally_exact() -> None:
    """両側の母集合を資産から導き、全原子要素を一度ずつ処分する。"""
    mapping, probe, product = _documents()
    summary = validate_probe_product_map(mapping, probe, product)

    assert len(summary.probe_atoms) == 48
    assert len(summary.product_atoms) == 195
    assert summary.probe_atoms == (
        summary.mapped_probe_atoms | summary.explicit_non_mapping
    )
    assert not summary.mapped_probe_atoms & summary.explicit_non_mapping
    assert summary.product_atoms == summary.mapped_product_atoms | summary.product_only
    assert not summary.mapped_product_atoms & summary.product_only
    assert summary.one_to_many == frozenset(
        {
            "table:probe_business_rows",
            "policy:POLICY:probe_business_rows:tenant_boundary",
            "acl_privilege:ACL:probe_business_rows:app_role:SELECT",
            "acl_privilege:ACL:probe_business_rows:app_role:INSERT",
            "acl_privilege:ACL:probe_business_rows:app_role:UPDATE",
        }
    )


def test_removing_one_probe_mapping_is_red() -> None:
    """Probe 側の写像を 1 件消すと domain の不足として拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    mappings = _rows(mutated, "mappings")
    mappings.pop(0)

    with pytest.raises(ProbeProductMapError, match="probe 原子要素"):
        validate_probe_product_map(mutated, probe, product)


def test_adding_an_unclassified_product_element_is_red() -> None:
    """製品資産へ原子要素を足して処分しない変異を拒否する。"""
    mapping, probe, product = _documents()
    mutated_product = copy.deepcopy(product)
    _rows(mutated_product, "tables").append({"table_id": "unmapped_product_table"})

    with pytest.raises(ProbeProductMapError, match="製品原子要素"):
        validate_probe_product_map(mapping, probe, mutated_product)


def test_unknown_reason_code_is_red() -> None:
    """閉じた列挙に無い理由コードを拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    row = _row_by_value(
        _rows(mutated, "explicit_non_mapping"),
        key="probe",
        value="role:outsider_role",
    )
    row["reason"] = "unknown_reason"

    with pytest.raises(ProbeProductMapError, match="未知の非写像理由コード"):
        validate_probe_product_map(mutated, probe, product)


def test_reason_code_for_the_wrong_element_kind_is_red() -> None:
    """schema・table・policy 用の理由を role へ使う変異を拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    row = _row_by_value(
        _rows(mutated, "explicit_non_mapping"),
        key="probe",
        value="role:provisioner",
    )
    row["reason"] = "probe_schema_only"

    with pytest.raises(ProbeProductMapError, match="role に使えない"):
        validate_probe_product_map(mutated, probe, product)


def test_read_control_resources_owner_other_than_u_c2_is_red() -> None:
    """制御資源読み取り関数の受け取り先を U-C2 以外へ変えられない。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    row = _row_by_value(
        _rows(mutated, "explicit_non_mapping"),
        key="probe",
        value="function:read_control_resources",
    )
    row["owner_unit"] = "U-C3"

    with pytest.raises(ProbeProductMapError, match="owner_unit は U-C2"):
        validate_probe_product_map(mutated, probe, product)


def test_unapproved_one_to_many_mapping_is_red() -> None:
    """Exact-set を保っても許可集合外の 1 対多は拒否する。"""
    mapping, probe, product = _documents()
    mutated = copy.deepcopy(mapping)
    table_mapping = _row_by_value(
        _rows(mutated, "mappings"),
        key="probe",
        value="table:probe_groups",
    )
    products = table_mapping["products"]
    assert isinstance(products, list)
    products.append("table:tenants")
    product_only = _rows(mutated, "product_only")
    product_only.remove(
        _row_by_value(product_only, key="product", value="table:tenants")
    )

    with pytest.raises(ProbeProductMapError, match="許可した 1 対多"):
        validate_probe_product_map(mutated, probe, product)


def test_app_role_delete_is_forbidden_by_canon() -> None:
    """Probe にある app_role の DELETE を正本禁止として全件処分する。"""
    mapping, probe, product = _documents()
    validate_probe_product_map(mapping, probe, product)
    rows = _rows(mapping, "explicit_non_mapping")
    delete_rows = tuple(
        row
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("probe"), str)
        and row["probe"].endswith(":app_role:DELETE")
    )

    assert len(delete_rows) == 2
    assert {row.get("reason") for row in delete_rows} == {"forbidden_by_canon"}
