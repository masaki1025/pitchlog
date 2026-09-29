"""probe と製品の認可原子要素の写像資産を静的に検査する。"""

from __future__ import annotations

from dataclasses import dataclass


class ProbeProductMapError(ValueError):
    """probe・製品写像が閉じた契約を満たさないことを表す。"""


@dataclass(frozen=True, slots=True)
class ProbeProductMapSummary:
    """両方向 exact-set 検査で確定した集合の要約。"""

    probe_atoms: frozenset[str]
    product_atoms: frozenset[str]
    mapped_probe_atoms: frozenset[str]
    mapped_product_atoms: frozenset[str]
    explicit_non_mapping: frozenset[str]
    product_only: frozenset[str]
    one_to_many: frozenset[str]


_ASSET_KEYS = {
    "schema_version",
    "asset_kind",
    "scope",
    "source_assets",
    "mappings",
    "allowed_one_to_many",
    "explicit_non_mapping",
    "product_only",
}
_SOURCE_ASSETS = {
    "probe": "contracts/authz/ddl-elements.json",
    "product": "contracts/authz/product/ddl-elements.staged.json",
}
_ELEMENT_SECTIONS = (
    ("roles", "role", "role_id"),
    ("schemas", "schema", "schema_id"),
    ("tables", "table", "table_id"),
    ("policies", "policy", "policy_id"),
    ("functions", "function", "function_id"),
)
_REASON_KINDS = {
    "test_only_role": frozenset({"role"}),
    "external_provisioner": frozenset({"role"}),
    "deferred_to_owning_unit": frozenset({"function", "acl_privilege"}),
    "forbidden_by_canon": frozenset({"acl_privilege"}),
    "probe_schema_only": frozenset({"schema", "table", "policy"}),
}
_OWNER_UNITS = frozenset({"U-C1", "U-C2", "U-C3", "U-A2"})
_READ_CONTROL_RESOURCES = "function:read_control_resources"


def _object_rows(
    document: dict[str, object],
    key: str,
    label: str,
) -> tuple[dict[str, object], ...]:
    """指定キーを object 配列として返す。"""
    value = document[key] if key in document else None
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ProbeProductMapError(f"{label}.{key} は object 配列が必要")
    return tuple(row for row in value if isinstance(row, dict))


def _text(row: dict[str, object], key: str, label: str) -> str:
    """指定キーを空でない文字列として返す。"""
    value = row[key] if key in row else None
    if not isinstance(value, str) or not value:
        raise ProbeProductMapError(f"{label}.{key} は空でない文字列が必要")
    return value


def _strings(row: dict[str, object], key: str, label: str) -> tuple[str, ...]:
    """指定キーを重複のない文字列配列として返す。"""
    value = row[key] if key in row else None
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ProbeProductMapError(f"{label}.{key} は文字列配列が必要")
    result = tuple(item for item in value if isinstance(item, str))
    if len(result) != len(set(result)):
        raise ProbeProductMapError(f"{label}.{key} に重複がある")
    return result


def _add_atom(
    atoms: dict[str, str],
    *,
    kind: str,
    identifier: str,
    label: str,
) -> None:
    """原子要素を一意な型付き ID として追加する。"""
    atom = f"{kind}:{identifier}"
    if atom in atoms:
        raise ProbeProductMapError(f"{label} の原子要素が重複: {atom}")
    atoms[atom] = kind


def atomic_elements(
    document: dict[str, object],
    *,
    label: str,
) -> dict[str, str]:
    """資産から設計 7 節の 6 種の原子要素を機械的に導く。"""
    atoms: dict[str, str] = {}
    for section, kind, identifier_key in _ELEMENT_SECTIONS:
        for row in _object_rows(document, section, label):
            _add_atom(
                atoms,
                kind=kind,
                identifier=_text(row, identifier_key, f"{label}.{section}"),
                label=label,
            )

    for acl in _object_rows(document, "acl_expectations", label):
        acl_id = _text(acl, "acl_id", f"{label}.acl_expectations")
        for privilege in _strings(
            acl,
            "privilege_ids",
            f"{label}.acl_expectations[{acl_id}]",
        ):
            _add_atom(
                atoms,
                kind="acl_privilege",
                identifier=f"{acl_id}:{privilege}",
                label=label,
            )
    return atoms


def _mapping_rows(
    mapping: dict[str, object],
    probe_atoms: dict[str, str],
    product_atoms: dict[str, str],
) -> tuple[dict[str, object], ...]:
    """型を保つ一意な写像行を検査して返す。"""
    rows = _object_rows(mapping, "mappings", "probe-product-map")
    seen_probe: set[str] = set()
    seen_product: set[str] = set()
    for row in rows:
        if set(row) != {"probe", "products"}:
            raise ProbeProductMapError("mappings のキーが exact-set でない")
        probe = _text(row, "probe", "mappings")
        products = _strings(row, "products", f"mappings[{probe}]")
        if not products:
            raise ProbeProductMapError(f"mappings[{probe}] の像が空")
        if probe not in probe_atoms:
            raise ProbeProductMapError(f"写像元が probe 原子要素でない: {probe}")
        if probe in seen_probe:
            raise ProbeProductMapError(f"probe 原子要素の写像が重複: {probe}")
        seen_probe.add(probe)
        for product in products:
            if product not in product_atoms:
                raise ProbeProductMapError(f"写像先が製品原子要素でない: {product}")
            if probe_atoms[probe] != product_atoms[product]:
                raise ProbeProductMapError(
                    f"異なる種別の原子要素を写像できない: {probe} -> {product}"
                )
            if product in seen_product:
                raise ProbeProductMapError(f"製品原子要素の像が重複: {product}")
            seen_product.add(product)
    return rows


def _explicit_non_mapping_rows(
    mapping: dict[str, object],
    probe_atoms: dict[str, str],
) -> tuple[dict[str, object], ...]:
    """Probe 側の理由付き非写像を閉じた列挙で検査する。"""
    rows = _object_rows(
        mapping,
        "explicit_non_mapping",
        "probe-product-map",
    )
    seen: set[str] = set()
    for row in rows:
        probe = _text(row, "probe", "explicit_non_mapping")
        reason = _text(row, "reason", f"explicit_non_mapping[{probe}]")
        if probe not in probe_atoms:
            raise ProbeProductMapError(f"非写像元が probe 原子要素でない: {probe}")
        if probe in seen:
            raise ProbeProductMapError(f"probe 非写像が重複: {probe}")
        seen.add(probe)
        allowed_kinds = _REASON_KINDS.get(reason)
        if allowed_kinds is None:
            raise ProbeProductMapError(f"未知の非写像理由コード: {reason}")
        if probe_atoms[probe] not in allowed_kinds:
            raise ProbeProductMapError(
                f"{reason} を {probe_atoms[probe]} に使えない: {probe}"
            )
        if reason == "deferred_to_owning_unit":
            if set(row) != {"probe", "reason", "owner_unit"}:
                raise ProbeProductMapError(f"{probe} は owner_unit が必要")
            owner_unit = _text(row, "owner_unit", f"explicit_non_mapping[{probe}]")
            if owner_unit not in _OWNER_UNITS:
                raise ProbeProductMapError(f"未知の owner_unit: {owner_unit}")
        elif set(row) != {"probe", "reason"}:
            raise ProbeProductMapError(f"{probe} に owner_unit を指定できない")
    return rows


def _product_only_rows(
    mapping: dict[str, object],
    product_atoms: dict[str, str],
) -> tuple[dict[str, object], ...]:
    """製品側だけに存在する原子要素を検査して返す。"""
    rows = _object_rows(mapping, "product_only", "probe-product-map")
    seen: set[str] = set()
    for row in rows:
        if set(row) != {"product", "reason"}:
            raise ProbeProductMapError("product_only のキーが exact-set でない")
        product = _text(row, "product", "product_only")
        if _text(row, "reason", f"product_only[{product}]") != "product_only":
            raise ProbeProductMapError("製品側の非写像理由は product_only が必要")
        if product not in product_atoms:
            raise ProbeProductMapError(f"product_only が製品原子要素でない: {product}")
        if product in seen:
            raise ProbeProductMapError(f"product_only が重複: {product}")
        seen.add(product)
    return rows


def _assert_special_non_mappings(
    probe_document: dict[str, object],
    non_mapping_by_probe: dict[str, dict[str, object]],
) -> None:
    """設計で個別指定された関数と DELETE の処分を検査する。"""
    read_control = non_mapping_by_probe.get(_READ_CONTROL_RESOURCES)
    if read_control is None or read_control.get("reason") != "deferred_to_owning_unit":
        raise ProbeProductMapError(
            "read_control_resources は deferred_to_owning_unit が必要"
        )
    if read_control.get("owner_unit") != "U-C2":
        raise ProbeProductMapError(
            "read_control_resources の owner_unit は U-C2 が必要"
        )

    for acl in _object_rows(
        probe_document,
        "acl_expectations",
        "probe",
    ):
        if acl.get("grantee_role_id") != "app_role":
            continue
        privileges = _strings(acl, "privilege_ids", "probe.acl_expectations")
        if "DELETE" not in privileges:
            continue
        acl_id = _text(acl, "acl_id", "probe.acl_expectations")
        atom = f"acl_privilege:{acl_id}:DELETE"
        row = non_mapping_by_probe.get(atom)
        if row is None or row.get("reason") != "forbidden_by_canon":
            raise ProbeProductMapError(
                f"app_role の DELETE は forbidden_by_canon が必要: {atom}"
            )


def validate_probe_product_map(
    mapping: dict[str, object],
    probe_document: dict[str, object],
    product_document: dict[str, object],
) -> ProbeProductMapSummary:
    """写像資産を両資産から導いた母集合と双方向 exact-set 照合する。"""
    if set(mapping) != _ASSET_KEYS:
        raise ProbeProductMapError("probe-product-map のキーが exact-set でない")
    if mapping.get("schema_version") != 1:
        raise ProbeProductMapError("probe-product-map.schema_version が不正")
    if mapping.get("asset_kind") != "probe_product_map":
        raise ProbeProductMapError("probe-product-map.asset_kind が不正")
    if mapping.get("scope") != "product":
        raise ProbeProductMapError("probe-product-map.scope が不正")
    if mapping.get("source_assets") != _SOURCE_ASSETS:
        raise ProbeProductMapError(
            "母集合は probe 資産と staged 製品資産だけから取る必要がある"
        )

    probe_atoms = atomic_elements(probe_document, label="probe")
    product_atoms = atomic_elements(product_document, label="product")
    mappings = _mapping_rows(mapping, probe_atoms, product_atoms)
    non_mappings = _explicit_non_mapping_rows(mapping, probe_atoms)
    product_only_rows = _product_only_rows(mapping, product_atoms)

    mapped_probe = frozenset(_text(row, "probe", "mappings") for row in mappings)
    mapped_product = frozenset(
        product for row in mappings for product in _strings(row, "products", "mappings")
    )
    explicit_non_mapping = frozenset(
        _text(row, "probe", "explicit_non_mapping") for row in non_mappings
    )
    product_only = frozenset(
        _text(row, "product", "product_only") for row in product_only_rows
    )
    if mapped_probe & explicit_non_mapping:
        raise ProbeProductMapError("probe 原子要素が写像と非写像の両方にある")
    if mapped_probe | explicit_non_mapping != frozenset(probe_atoms):
        raise ProbeProductMapError("probe 原子要素が双方向 exact-set でない")
    if mapped_product & product_only:
        raise ProbeProductMapError("製品原子要素が像と product_only の両方にある")
    if mapped_product | product_only != frozenset(product_atoms):
        raise ProbeProductMapError("製品原子要素が双方向 exact-set でない")

    allowed_one_to_many = frozenset(
        _strings(mapping, "allowed_one_to_many", "probe-product-map")
    )
    actual_one_to_many = frozenset(
        _text(row, "probe", "mappings")
        for row in mappings
        if len(_strings(row, "products", "mappings")) > 1
    )
    if allowed_one_to_many != actual_one_to_many:
        raise ProbeProductMapError("許可した 1 対多と実際の 1 対多が一致しない")

    non_mapping_by_probe = {
        _text(row, "probe", "explicit_non_mapping"): row for row in non_mappings
    }
    _assert_special_non_mappings(probe_document, non_mapping_by_probe)
    return ProbeProductMapSummary(
        probe_atoms=frozenset(probe_atoms),
        product_atoms=frozenset(product_atoms),
        mapped_probe_atoms=mapped_probe,
        mapped_product_atoms=mapped_product,
        explicit_non_mapping=explicit_non_mapping,
        product_only=product_only,
        one_to_many=actual_one_to_many,
    )
